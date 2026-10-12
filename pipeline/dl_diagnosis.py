"""Deep-learning variant of the Part I fault diagnosis (features -> networks).

The IMS data holds 4 failures: 2 outer race, 1 inner race, 1 rolling element.
A network trained on real fault labels therefore never sees an inner-race or
rolling-element example when that run is held out. This script compares three
ways of using deep learning, all scored on the same bearings as the proposed
(physics + statistics) method in diagnosis.py:

D1. Autoencoder detection (where / when)
    A dense autoencoder learns to reconstruct 16 log condition features
    (RMS, kurtosis, crest, band energies, envelope amplitudes ...) of HEALTHY
    snapshots only: the first 20% of every bearing in the test. Its
    reconstruction error is the health index; the same peer contrast and
    persistence rule as Stage A turns it into alarms. No fault labels.

D2. Sim-to-real CNN identification (what)
    A 1D convolutional network reads the whitened envelope spectrum
    (dl_spectra.py: 0-1000 Hz, 1024 bins) and outputs healthy / outer / inner /
    roller. It is trained ONLY on synthetic examples: real healthy spectra from
    the OTHER two tests, with fault combs injected at the bearing's defect
    orders and a random speed (0.95-1.01 x nominal), plus random distractor
    lines. It never sees a real fault, nor any data from the test it is
    scored on. Verdict = class with the highest mean probability from the
    Stage A alarm onward.

D3. Supervised CNN on real labels (naive baseline)
    Same network, trained leave-one-run-out on real spectra: snapshots after
    the alarm of the other failed runs, labelled with their true defect, plus
    healthy-window snapshots.

Usage:  python pipeline/dl_diagnosis.py
Outputs: pipeline/outputs/dl_summary.csv, dl_comparison.csv,
         dl_synthetic_examples.png, dl_ae_detection.png, dl_cnn_probs.png
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from torch import nn

from common import BEARING_COLORS, FAILED_RUNS, OUT_DIR, load_features
from diag_features import FS, NFFT, ORDERS, SHAFT_HZ
from diagnosis import (BASELINE_FRAC, C_FLOOR, K_SIGMA, PERSIST, SMOOTH, TRUTH_NAME,
                       detection, n_healthy, persistent, robust_sd)

torch.set_num_threads(16)
CLASSES = ["healthy", "outer", "inner", "roller"]
DEFECTS = CLASSES[1:]
N_BINS = 1024
FREQ = (2 * np.arange(N_BINS) + 0.5) * FS / NFFT     # Hz at each pooled bin
BIN_HZ = FREQ[1] - FREQ[0]
AE_FEATURES = ["rms", "peak", "p2p", "kurtosis", "crest", "shape", "impulse",
               "spec_centroid", "band_0_1k", "band_1_3k", "band_3_6k", "band_6_10k",
               "env_bpfo", "env_bpfi", "env_bsf", "env_ftf"]
AE_FLOOR = 0.5        # log reconstruction-error contrast floor (~65% above peers)
UNSPEC_P = 0.3        # mean fault probability needed to name a defect
EVAL_HOURS = 48
STEPS_SIM, STEPS_SUP, BATCH = 2500, 1500, 256

DEFECT_COLORS = {"healthy": "#8a8984", "outer": "#2a78d6", "inner": "#eb6834",
                 "roller": "#1baf7a"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"


# ------------------------------------------------------------------ data
def load_spectra(set_no: int):
    live = set(load_features(set_no)["file"])
    idx = pd.read_csv(OUT_DIR / f"dl_index_set{set_no}.csv", parse_dates=["timestamp"])
    X = np.load(OUT_DIR / f"dl_spectra_set{set_no}.npy")
    keep = idx["file"].isin(live).to_numpy()
    idx = idx[keep].reset_index(drop=True)
    times = np.sort(idx["timestamp"].unique())
    idx["healthy_window"] = idx["timestamp"].isin(times[:n_healthy(len(times))])
    return idx, np.clip(X[keep].astype(np.float32), -2, 6)


# ------------------------------------------------------------- D1: autoencoder
class AE(nn.Module):
    def __init__(self, d=len(AE_FEATURES)):
        super().__init__()
        self.enc = nn.Sequential(nn.Linear(d, 12), nn.Tanh(), nn.Linear(12, 4))
        self.dec = nn.Sequential(nn.Linear(4, 12), nn.Tanh(), nn.Linear(12, d))

    def forward(self, x):
        return self.dec(self.enc(x))


def ae_detection(feats: pd.DataFrame, seed=0):
    """Reconstruction-error health index per bearing, peer contrast, alarms."""
    x = np.log(feats.pivot_table(index="timestamp", columns="bearing",
                                 values=AE_FEATURES, aggfunc="mean"))
    bearings = sorted(feats["bearing"].unique())
    n = n_healthy(len(x))
    tr = np.concatenate([x.xs(b, axis=1, level="bearing")[AE_FEATURES].iloc[:n].to_numpy()
                         for b in bearings])
    mu, sd = tr.mean(0), tr.std(0) + 1e-6
    torch.manual_seed(seed)
    model = AE()
    opt = torch.optim.Adam(model.parameters(), lr=3e-3)
    t = torch.tensor((tr - mu) / sd, dtype=torch.float32)
    for _ in range(600):
        opt.zero_grad()
        loss = ((model(t) - t) ** 2).mean()
        loss.backward()
        opt.step()
    err = {}
    with torch.no_grad():
        for b in bearings:
            v = torch.tensor((x.xs(b, axis=1, level="bearing")[AE_FEATURES].to_numpy() - mu) / sd,
                             dtype=torch.float32)
            err[b] = ((model(v) - v) ** 2).mean(1).numpy()
    err = pd.DataFrame(err, index=x.index).rolling(SMOOTH, min_periods=1).median()
    hi = np.log(err / err.iloc[:n].median())
    contrast = pd.DataFrame({b: hi[b] - hi.drop(columns=b).median(axis=1) for b in bearings})
    alarms = {}
    for b in bearings:
        ref = contrast[b].iloc[:n].to_numpy()
        lim = np.median(ref) + max(K_SIGMA * robust_sd(ref), AE_FLOOR)
        alarms[b] = persistent(contrast[b].to_numpy() > lim)
    return contrast, alarms


# ------------------------------------------------------------ CNN + synthesis
class SpecCNN(nn.Module):
    def __init__(self, n_out=4):
        super().__init__()
        def block(i, o, k):
            return [nn.Conv1d(i, o, k, padding=k // 2), nn.BatchNorm1d(o), nn.ReLU(), nn.MaxPool1d(2)]
        self.features = nn.Sequential(*block(1, 16, 9), *block(16, 32, 7),
                                      *block(32, 32, 5), *block(32, 32, 5))
        self.head = nn.Sequential(nn.Flatten(), nn.Dropout(0.3), nn.Linear(32 * 64, 64),
                                  nn.ReLU(), nn.Linear(64, n_out))

    def forward(self, x):
        return self.head(self.features(x.unsqueeze(1)))


def _add_line(S, f0, amp, rng):
    if 0 < f0 < FREQ[-1]:
        w = rng.uniform(0.4, 1.0)
        S += amp * np.exp(-0.5 * ((FREQ - f0) / w) ** 2)


def synthesize(bg: np.ndarray, rng: np.random.Generator):
    """Batch of synthetic spectra: real healthy background + injected combs."""
    n = len(bg)
    S = bg[rng.integers(0, n, BATCH)].copy()
    y = rng.integers(0, 4, BATCH)
    for i in range(BATCH):
        fr = SHAFT_HZ * rng.uniform(0.95, 1.01)
        # distractors every class can carry: shaft harmonics, random lines
        if rng.random() < 0.5:
            for k in range(1, 11):
                if rng.random() < 0.4:
                    _add_line(S[i], k * fr, rng.uniform(0.3, 2.0), rng)
        for _ in range(rng.integers(0, 4)):
            _add_line(S[i], rng.uniform(5, 1000), rng.uniform(0.5, 2.5), rng)
        a = rng.uniform(0.8, 3.5)
        c = CLASSES[y[i]]
        if c == "outer":
            for h in (1, 2, 3, 4):
                if rng.random() < 0.85:
                    _add_line(S[i], h * ORDERS["bpfo"] * fr, a * rng.uniform(0.3, 1.0), rng)
        elif c == "inner":
            for h in (1, 2, 3):
                if rng.random() < 0.85:
                    _add_line(S[i], h * ORDERS["bpfi"] * fr, a * rng.uniform(0.3, 1.0), rng)
                for sb in (-1, 1):
                    if rng.random() < 0.6:
                        _add_line(S[i], h * ORDERS["bpfi"] * fr + sb * fr,
                                  a * rng.uniform(0.2, 0.7), rng)
        elif c == "roller":
            for h in (1, 2, 3):
                if rng.random() < 0.6:
                    _add_line(S[i], h * ORDERS["bsf2"] * fr, a * rng.uniform(0.2, 0.8), rng)
            for h in range(1, 7):
                if rng.random() < 0.75:
                    _add_line(S[i], h * ORDERS["ftf"] * fr, a * rng.uniform(0.3, 1.0), rng)
    return np.clip(S, -2, 6), y


def train(model, batches, steps, seed):
    torch.manual_seed(seed)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, steps)
    lossf = nn.CrossEntropyLoss()
    model.train()
    for _ in range(steps):
        x, y = batches()
        opt.zero_grad()
        loss = lossf(model(torch.tensor(x)), torch.tensor(y))
        loss.backward()
        opt.step()
        sched.step()
    model.eval()
    return model


def predict(model, X):
    with torch.no_grad():
        out = [torch.softmax(model(torch.tensor(X[i:i + 4096])), 1).numpy()
               for i in range(0, len(X), 4096)]
    return np.concatenate(out)


def bearing_probs(idx, P):
    """Mean class probability per (timestamp, bearing), smoothed: dict b -> (T x 4)."""
    df = idx[["timestamp", "bearing"]].copy()
    for k, c in enumerate(CLASSES):
        df[c] = P[:, k]
    g = df.groupby(["timestamp", "bearing"])[CLASSES].mean()
    return {b: g.xs(b, level="bearing").rolling(SMOOTH, min_periods=1).median()
            for b in sorted(idx["bearing"].unique())}


def verdict(p: np.ndarray, alarm):
    if alarm is None:
        return "healthy", None
    mean = p[alarm:, 1:].mean(0)
    v = DEFECTS[int(mean.argmax())] if mean.max() >= UNSPEC_P else "unspecified"
    return v, mean


# ------------------------------------------------------------------ main
def main():
    rng = np.random.default_rng(0)
    failed = {(s, b): TRUTH_NAME[m] for s, b, m in FAILED_RUNS}
    spec = {s: load_spectra(s) for s in (1, 2, 3)}
    feats = {s: load_features(s) for s in (1, 2, 3)}

    rows, curves = [], {}
    sim_val = {}
    for s in (1, 2, 3):
        idx, X = spec[s]
        _, _, _, alarms, _ = detection(feats[s])                  # Stage A alarms
        ae_contrast, ae_alarms = ae_detection(feats[s])

        # D2: background = healthy windows of the OTHER tests only
        bg = np.concatenate([spec[o][1][spec[o][0]["healthy_window"].to_numpy()]
                             for o in (1, 2, 3) if o != s])
        model = train(SpecCNN(), lambda: synthesize(bg, rng), STEPS_SIM, seed=s)
        xv, yv = synthesize(bg, np.random.default_rng(100 + s))
        sim_val[s] = float((predict(model, xv).argmax(1) == yv).mean())
        probs_sim = bearing_probs(idx, predict(model, X))
        print(f"set {s}: sim-trained CNN, synthetic validation accuracy {sim_val[s]:.3f}")

        times = probs_sim[1].index
        left = ((times[-1] - times).total_seconds() / 3600).to_numpy()
        for b in sorted(idx["bearing"].unique()):
            truth = failed.get((s, b), "healthy")
            p = probs_sim[b].to_numpy()
            v, mean = verdict(p, alarms[b])
            lab = np.array(CLASSES)[p.argmax(1)]
            row = {"set": s, "bearing": b, "truth": truth,
                   "stageA_alarm_h": round(left[alarms[b]], 1) if alarms[b] is not None else np.nan,
                   "ae_alarm_h": round(left[ae_alarms[b]], 1) if ae_alarms[b] is not None else np.nan,
                   "verdict_sim_cnn": v,
                   # share of snapshots outside the last 48 h called a fault
                   "fault_calls_before_last48h": round(float((lab[left > EVAL_HOURS] != "healthy").mean()), 3)}
            if truth != "healthy":
                k = DEFECTS.index(truth)
                row["sep_sim_cnn"] = round(float(mean[k] / max(np.delete(mean, k).max(), 1e-3)), 2)
                row["acc48_sim_cnn"] = round(float((lab[left <= EVAL_HOURS] == truth).mean()), 3)
                curves[(s, b)] = (left, p)
            rows.append(row)
        if s == 2:
            ae_plot = (ae_contrast, ae_alarms)

    summary = pd.DataFrame(rows)

    # D3: supervised CNN, leave-one-run-out on real labels
    stage_a = {s: detection(feats[s])[3] for s in (1, 2, 3)}
    labelled = []
    for s in (1, 2, 3):
        idx, X = spec[s]
        times = np.sort(idx["timestamp"].unique())
        for b in sorted(idx["bearing"].unique()):
            m = (idx["bearing"] == b).to_numpy()
            if (s, b) in failed and stage_a[s][b] is not None:
                fault = (idx["timestamp"] >= times[stage_a[s][b]]).to_numpy() & m
                labelled.append((s, b, X[fault], CLASSES.index(failed[(s, b)])))
            healthy = idx["healthy_window"].to_numpy() & m
            labelled.append((s, b, X[healthy], 0))
    for (s, b), truth in failed.items():
        train_sets = [(x, y) for (ss, bb, x, y) in labelled if (ss, bb) != (s, b) and len(x)]
        present = sorted({y for _, y in train_sets})
        pools = {c: np.concatenate([x for x, y in train_sets if y == c]) for c in present}
        srng = np.random.default_rng(7)

        def batches():
            ys = srng.choice(present, BATCH)
            xs = np.stack([pools[c][srng.integers(len(pools[c]))] for c in ys])
            return np.roll(xs, srng.integers(-6, 7), axis=1).astype(np.float32), ys
        model = train(SpecCNN(), batches, STEPS_SUP, seed=11)
        idx, X = spec[s]
        pb = bearing_probs(idx, predict(model, X))[b]
        p, times = pb.to_numpy(), pb.index
        left = ((times[-1] - times).total_seconds() / 3600).to_numpy()
        v, mean = verdict(p, stage_a[s][b])
        k = DEFECTS.index(truth)
        i = (summary["set"] == s) & (summary["bearing"] == b)
        summary.loc[i, "verdict_sup_cnn"] = v
        summary.loc[i, "sep_sup_cnn"] = round(float(mean[k] / max(np.delete(mean, k).max(), 1e-3)), 2)
        summary.loc[i, "acc48_sup_cnn"] = round(float((np.array(CLASSES)[p.argmax(1)][left <= EVAL_HOURS] == truth).mean()), 3)
        summary.loc[i, "sup_classes_seen"] = "/".join(CLASSES[c] for c in present)

    # Proposed method (physics + statistics) for reference
    ref = pd.read_csv(OUT_DIR / "diag_summary.csv")
    summary = summary.merge(ref[["set", "bearing", "verdict[proposed]", "sep[proposed]",
                                 "acc48h[proposed]"]], on=["set", "bearing"], how="left")
    summary.to_csv(OUT_DIR / "dl_summary.csv", index=False)

    f = summary[summary["truth"] != "healthy"]
    h = summary[summary["truth"] == "healthy"]
    comp = pd.DataFrame([
        {"stage": "detection", "method": "Stage A: peer-contrast energy",
         "faulty_detected": f"{f['stageA_alarm_h'].notna().sum()}/4",
         "healthy_false_alarms": f"{h['stageA_alarm_h'].notna().sum()}/8",
         "median_lead_h": f["stageA_alarm_h"].median()},
        {"stage": "detection", "method": "D1: autoencoder + peer contrast",
         "faulty_detected": f"{f['ae_alarm_h'].notna().sum()}/4",
         "healthy_false_alarms": f"{h['ae_alarm_h'].notna().sum()}/8",
         "median_lead_h": f["ae_alarm_h"].median()},
        {"stage": "identification", "method": "Stage B: physics combs (proposed)",
         "faulty_correct": f"{(f['verdict[proposed]'] == f['truth']).sum()}/4",
         "sep_min": f["sep[proposed]"].min(), "sep_median": f["sep[proposed]"].median(),
         "acc48_mean": round(f["acc48h[proposed]"].mean(), 3)},
        {"stage": "identification", "method": "D2: CNN trained on synthetic faults",
         "faulty_correct": f"{(f['verdict_sim_cnn'] == f['truth']).sum()}/4",
         "sep_min": f["sep_sim_cnn"].min(), "sep_median": f["sep_sim_cnn"].median(),
         "acc48_mean": round(f["acc48_sim_cnn"].mean(), 3)},
        {"stage": "identification", "method": "D3: CNN supervised on real labels (LORO)",
         "faulty_correct": f"{(f['verdict_sup_cnn'] == f['truth']).sum()}/4",
         "sep_min": f["sep_sup_cnn"].min(), "sep_median": f["sep_sup_cnn"].median(),
         "acc48_mean": round(f["acc48_sup_cnn"].mean(), 3)},
    ])
    comp.to_csv(OUT_DIR / "dl_comparison.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(summary.to_string(index=False))
    print()
    print(comp.to_string(index=False))
    print("synthetic validation accuracy per held-out test:", sim_val)

    plot_synthetic(spec)
    plot_probs(curves, summary)
    plot_ae(feats)
    print(f"wrote CSVs and plots to {OUT_DIR}")


# ------------------------------------------------------------------ plots
def style_axes(ax):
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#a9a8a2")
    ax.tick_params(colors=MUTED, labelsize=9)


def plot_synthetic(spec):
    idx, X = spec[3]
    bg = X[idx["healthy_window"].to_numpy()]
    rng = np.random.default_rng(3)
    S, y = synthesize(bg, rng)
    fig, axes = plt.subplots(4, 1, figsize=(11, 8), sharex=True)
    for ax, c in zip(axes, range(4)):
        i = int(np.argmax(y == c))
        ax.plot(FREQ, S[i], color=DEFECT_COLORS[CLASSES[c]], linewidth=0.7)
        ax.set_title(f"Synthetic training example: {CLASSES[c]}", fontsize=10, loc="left", color=INK)
        ax.set_ylabel("log peak / floor", color=INK, fontsize=9)
        ax.set_ylim(-2, 6)
        style_axes(ax)
    axes[-1].set_xlabel("Envelope frequency (Hz)", color=INK)
    fig.suptitle("D2 training data: a real healthy spectrum plus an injected fault comb "
                 "(random speed, random distractor lines)", fontsize=11, x=0.01, ha="left", color=INK)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "dl_synthetic_examples.png", dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def plot_probs(curves, summary):
    fig, axes = plt.subplots(len(FAILED_RUNS), 1, figsize=(11, 10), sharex=True)
    for ax, (s, b, mode) in zip(axes, FAILED_RUNS):
        left, p = curves[(s, b)]
        win = left <= 150
        for k, c in enumerate(CLASSES):
            ax.plot(-left[win], p[win, k], color=DEFECT_COLORS[c], linewidth=1.3, label=c)
        info = summary[(summary["set"] == s) & (summary["bearing"] == b)].iloc[0]
        if pd.notna(info["stageA_alarm_h"]) and info["stageA_alarm_h"] <= 150:
            ax.axvline(-info["stageA_alarm_h"], color=MUTED, linewidth=0.8, linestyle=":")
        ax.set_title(f"Set {s} B{b}, truth {mode} | sim-trained CNN verdict: {info['verdict_sim_cnn']}",
                     fontsize=9.5, loc="left", color=INK)
        ax.set_ylabel("Probability", color=INK, fontsize=9)
        ax.set_ylim(0, 1)
        style_axes(ax)
    axes[0].legend(frameon=False, fontsize=9, ncol=4, loc="upper left")
    axes[-1].set_xlabel("Hours before end of test", color=INK)
    fig.suptitle("D2: class probabilities from the CNN trained only on synthetic faults "
                 "(last 150 h; dotted = Stage A alarm)", fontsize=11, x=0.01, ha="left", color=INK)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "dl_cnn_probs.png", dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def plot_ae(feats):
    failed = {(s, b): m for s, b, m in FAILED_RUNS}
    fig, axes = plt.subplots(3, 1, figsize=(11, 9))
    for ax, s in zip(axes, (1, 2, 3)):
        contrast, alarms = ae_detection(feats[s])
        left = ((contrast.index[-1] - contrast.index).total_seconds() / 3600).to_numpy()
        win = left <= 200
        for b in contrast.columns:
            name = f"B{b}" + (f" (failed: {failed[(s, b)]})" if (s, b) in failed else "")
            ax.plot(-left[win], contrast[b].to_numpy()[win], color=BEARING_COLORS[b],
                    linewidth=1.4 if (s, b) in failed else 0.9, label=name)
            if alarms[b] is not None and left[alarms[b]] <= 200:
                ax.axvline(-left[alarms[b]], color=BEARING_COLORS[b], linewidth=0.8, linestyle=":")
        ax.axhline(AE_FLOOR, color=MUTED, linewidth=0.8, linestyle="--")
        ax.set_title(f"Set {s}", fontsize=10, loc="left", color=INK)
        ax.set_ylabel("log reconstruction error\nvs. peers", color=INK, fontsize=9)
        ax.legend(frameon=False, fontsize=8, ncol=4, loc="upper left")
        style_axes(ax)
    axes[-1].set_xlabel("Hours before end of test", color=INK)
    fig.suptitle(f"D1: autoencoder reconstruction error, peer contrast, last 200 h "
                 f"(dashed = floor {AE_FLOOR:g}; dotted = alarm)", fontsize=11, x=0.01, ha="left", color=INK)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "dl_ae_detection.png", dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


if __name__ == "__main__":
    main()
