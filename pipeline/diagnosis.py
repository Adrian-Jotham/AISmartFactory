"""Proposed fault-diagnosis method (Part I): detect, locate and identify bearing
faults on the IMS run-to-failure data with no labelled fault examples.

The method splits "where/when" from "what", because they need opposite things.
On this rig all four bearings share one shaft and housing, so a defect's
envelope signature reaches every sensor almost equally (set 3: the outer-race
lines are as strong on B4 as on the failing B3). Level-invariant spectral
evidence therefore says *what* the defect is but not *where*; vibration energy
growth says *where* but not *what*.

A. Where / when: peer-contrast energy detection
   HI_b(t)  = log(RMS_b(t) / median RMS_b over its healthy window)
   C_b(t)   = HI_b(t) - median of the other bearings' HI(t)
   Subtracting the peers cancels rig-wide changes (load, temperature,
   cross-talk). Alarm when C_b stays above max(K_SIGMA * robust sd of C_b in
   the healthy window, C_FLOOR) for PERSIST consecutive snapshots.

B. What: spectral defect identification (signal stage in diag_features.py)
   1. Demodulation band chosen per snapshot by envelope-spectrum spikiness.
   2. Whitened squared-envelope spectrum (peak / local noise floor).
   3. Order-domain comb scores for outer race, inner race (+ shaft sidebands)
      and rolling element (+ cage modulation), with a +/-3% speed-scale search.
      The IMS rig runs ~2.5% below its nominal 2000 rpm, so catalogue
      frequencies miss the lines.
   4. Fleet reference: the pooled healthy window of all sensors in the test
      gives a robust z-score per comb, the Fault Evidence Index (FEI). A
      bearing's own early history is not a safe reference: set 2 B1's
      outer-race line is visible from its first hours.
   5. Verdict for an alarmed bearing: the defect with the largest mean FEI
      from the alarm onward, or "unspecified" if none reaches UNSPEC_FEI.

Comparison (same alarms from A, identification varied):
   proposed, no speed search, own-history reference, and the baseline =
   existing fixed-band (1-9 kHz) nominal-frequency envelope amplitudes from
   features_set{N}.csv with an own-history reference. Besides the verdict,
   "separation" = true defect's mean evidence after the alarm divided by the
   strongest wrong defect's; ~1 means the verdict was a coin flip.
Detection is also compared against a plain own-history energy threshold.

Usage:  python pipeline/diagnosis.py
Outputs: pipeline/outputs/diag_summary.csv, diag_comparison.csv,
         diag_timeline.csv, diag_detection.png, diag_fei_failed.png,
         diag_envelope_examples.png
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import ndimage

from common import BEARING_COLORS, FAILED_RUNS, OUT_DIR, load_features
from diag_features import COMBS, FS, NFFT, SETS, SHAFT_HZ, comb_scores, select_band

DEFECTS = ["outer", "inner", "roller"]
TRUTH_NAME = {"outer race": "outer", "inner race": "inner", "roller element": "roller"}

BASELINE_FRAC = 0.2   # first 20% of a test = healthy reference
SMOOTH = 6            # causal rolling median, snapshots (~1 h at 10 min)
PERSIST = 6           # consecutive exceedances to raise an alarm
K_SIGMA = 8.0         # alarm limit in robust sd of the healthy contrast ...
C_FLOOR = 0.15        # ... but never below +16% energy vs. the peers
UNSPEC_FEI = 1.0      # mean FEI needed to name a defect
LABEL_FEI = 3.0       # FEI needed to label a single snapshot
EVAL_HOURS = 48       # snapshot-level accuracy window before failure

# Identification variants: (source, score column template, reference)
ID_VARIANTS = {
    "proposed":              ("diag", "score_{}", "fleet"),
    "no speed search":       ("diag", "nom_score_{}", "fleet"),
    "own-history ref.":      ("diag", "score_{}", "own"),
    "baseline (fixed band)": ("feat", None, "own"),
}
BASELINE_COLS = {"outer": "env_bpfo", "inner": "env_bpfi", "roller": "env_bsf"}

DEFECT_COLORS = {"outer": "#2a78d6", "inner": "#eb6834", "roller": "#1baf7a"}
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"


def robust_sd(x: np.ndarray) -> float:
    return 1.4826 * np.median(np.abs(x - np.median(x)))


def robust_z(x: np.ndarray, ref: np.ndarray) -> np.ndarray:
    return (x - np.median(ref)) / max(robust_sd(ref), 1e-9)


def n_healthy(n: int) -> int:
    return max(20, int(n * BASELINE_FRAC))


def persistent(mask: np.ndarray) -> int | None:
    run = pd.Series(mask).rolling(PERSIST).sum().to_numpy() == PERSIST
    return int(np.argmax(run)) if run.any() else None


# ---------------------------------------------------------------- A: detection
def detection(feats: pd.DataFrame):
    """Per-bearing energy HI, peer contrast, limits and alarm indices."""
    rms = feats.pivot_table(index="timestamp", columns="bearing", values="rms",
                            aggfunc="mean")
    n = n_healthy(len(rms))
    hi = np.log(rms / rms.iloc[:n].median()).rolling(SMOOTH, min_periods=1).median()
    contrast = pd.DataFrame({b: hi[b] - hi.drop(columns=b).median(axis=1)
                             for b in hi.columns})
    limits, alarms, own_alarms = {}, {}, {}
    for b in hi.columns:
        ref = contrast[b].iloc[:n].to_numpy()
        limits[b] = np.median(ref) + max(K_SIGMA * robust_sd(ref), C_FLOOR)
        alarms[b] = persistent(contrast[b].to_numpy() > limits[b])
        # Ablation: same rule on the bearing's own HI, no peer subtraction.
        ref = hi[b].iloc[:n].to_numpy()
        own_alarms[b] = persistent(
            hi[b].to_numpy() > np.median(ref) + max(K_SIGMA * robust_sd(ref), C_FLOOR))
    return hi, contrast, limits, alarms, own_alarms


# ----------------------------------------------------------- B: identification
def fault_evidence(df: pd.DataFrame, cols: dict, reference: str) -> dict:
    """FEI per defect as a (timestamp x bearing) frame."""
    times = np.sort(df["timestamp"].unique())
    healthy = df["timestamp"].isin(times[:n_healthy(len(times))]).to_numpy()
    out = {}
    for d, col in cols.items():
        x = df[col].to_numpy()
        z = np.empty(len(df))
        if reference == "fleet":
            z[:] = robust_z(x, x[healthy])
        else:
            for _, idx in df.groupby("channel").indices.items():
                z[idx] = robust_z(x[idx], x[idx][healthy[idx]])
        # Average the sensors of a bearing (set 1 has x and y), then smooth.
        out[d] = (df.assign(z=z)
                  .pivot_table(index="timestamp", columns="bearing", values="z",
                               aggfunc="mean")
                  .rolling(SMOOTH, min_periods=1).median())
    return out


def identify(fei: np.ndarray, alarm: int | None) -> str:
    if alarm is None:
        return "healthy"
    mean = np.clip(fei[alarm:], 0, None).mean(0)
    return DEFECTS[int(mean.argmax())] if mean.max() >= UNSPEC_FEI else "unspecified"


def load_set(set_no: int):
    feats = load_features(set_no)
    diag = pd.read_csv(OUT_DIR / f"diag_scores_set{set_no}.csv", parse_dates=["timestamp"])
    diag = diag[diag["file"].isin(set(feats["file"]))]
    return {"diag": diag.sort_values(["timestamp", "channel"]).reset_index(drop=True),
            "feat": feats}


def evaluate():
    failed = {(s, b): TRUTH_NAME[m] for s, b, m in FAILED_RUNS}
    rows, timelines = [], []
    for set_no in (1, 2, 3):
        data = load_set(set_no)
        hi, contrast, limits, alarms, own_alarms = detection(data["feat"])
        times = hi.index
        left = ((times[-1] - times).total_seconds() / 3600).to_numpy()
        lead = {b: (round(left[a], 1) if a is not None else np.nan)
                for b, a in alarms.items()}

        fei_by_variant = {}
        for name, (source, tmpl, ref) in ID_VARIANTS.items():
            cols = ({d: tmpl.format(d) for d in DEFECTS} if source == "diag"
                    else BASELINE_COLS)
            ev = fault_evidence(data[source], cols, ref)
            fei_by_variant[name] = {b: np.stack([ev[d][b].reindex(times).to_numpy()
                                                 for d in DEFECTS], 1)
                                    for b in hi.columns}

        for b in hi.columns:
            truth = failed.get((set_no, b), "healthy")
            row = {"set": set_no, "bearing": b, "truth": truth,
                   "alarm_h_before_end": lead[b],
                   "own_hi_alarm_h_before_end": (round(left[own_alarms[b]], 1)
                                                 if own_alarms[b] is not None else np.nan)}
            for name, per_b in fei_by_variant.items():
                fei = per_b[b]
                row[f"verdict[{name}]"] = identify(fei, alarms[b])
                if truth != "healthy" and alarms[b] is not None:
                    # Separation: true defect's mean evidence after the alarm
                    # over the strongest wrong defect's. ~1 = a coin flip.
                    mean = np.clip(fei[alarms[b]:], 0, None).mean(0)
                    k = DEFECTS.index(truth)
                    row[f"sep[{name}]"] = round(
                        float(mean[k] / max(np.delete(mean, k).max(), 1e-3)), 2)
                if truth != "healthy":
                    last = left <= EVAL_HOURS
                    lab = np.where(fei.max(1) >= LABEL_FEI,
                                   np.array(DEFECTS)[fei.argmax(1)], "none")
                    row[f"acc{EVAL_HOURS}h[{name}]"] = round(float((lab[last] == truth).mean()), 3)
            rows.append(row)

            tl = pd.DataFrame({"set": set_no, "bearing": b, "timestamp": times,
                               "hours_before_end": left, "hi": hi[b].to_numpy(),
                               "contrast": contrast[b].to_numpy(),
                               "contrast_limit": limits[b]})
            for name in ("proposed", "baseline (fixed band)"):
                tag = "fei" if name == "proposed" else "base"
                for i, d in enumerate(DEFECTS):
                    tl[f"{tag}_{d}"] = fei_by_variant[name][b][:, i]
            timelines.append(tl)
    return pd.DataFrame(rows), pd.concat(timelines, ignore_index=True)


def compare(summary: pd.DataFrame) -> pd.DataFrame:
    f = summary[summary["truth"] != "healthy"]
    h = summary[summary["truth"] == "healthy"]
    rows = [{
        "stage": "detection", "variant": "peer-contrast energy (proposed)",
        "faulty_detected": f"{f['alarm_h_before_end'].notna().sum()}/{len(f)}",
        "healthy_false_alarms": f"{h['alarm_h_before_end'].notna().sum()}/{len(h)}",
        "median_lead_h": f["alarm_h_before_end"].median(),
    }, {
        "stage": "detection", "variant": "own-history energy",
        "faulty_detected": f"{f['own_hi_alarm_h_before_end'].notna().sum()}/{len(f)}",
        "healthy_false_alarms": f"{h['own_hi_alarm_h_before_end'].notna().sum()}/{len(h)}",
        "median_lead_h": f["own_hi_alarm_h_before_end"].median(),
    }]
    for name in ID_VARIANTS:
        rows.append({
            "stage": "identification", "variant": name,
            "faulty_correct": f"{(f[f'verdict[{name}]'] == f['truth']).sum()}/{len(f)}",
            f"mean_acc_last{EVAL_HOURS}h": round(f[f"acc{EVAL_HOURS}h[{name}]"].mean(), 3),
            "separation_min": f[f"sep[{name}]"].min(),
            "separation_median": f[f"sep[{name}]"].median(),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------- plots
def style_axes(ax):
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#a9a8a2")
    ax.tick_params(colors=MUTED, labelsize=9)


def plot_detection(timeline: pd.DataFrame, summary: pd.DataFrame):
    failed = {(s, b): m for s, b, m in FAILED_RUNS}
    fig, axes = plt.subplots(3, 1, figsize=(11, 9))
    for ax, set_no in zip(axes, (1, 2, 3)):
        t = timeline[(timeline["set"] == set_no) & (timeline["hours_before_end"] <= 200)]
        for b, g in t.groupby("bearing"):
            name = f"B{b}" + (f" (failed: {failed[(set_no, b)]})" if (set_no, b) in failed else "")
            ax.plot(-g["hours_before_end"], g["contrast"], color=BEARING_COLORS[b],
                    linewidth=1.4 if (set_no, b) in failed else 0.9, label=name)
            a = summary[(summary["set"] == set_no) & (summary["bearing"] == b)]
            lead = a["alarm_h_before_end"].iloc[0]
            if pd.notna(lead) and lead <= 200:
                ax.axvline(-lead, color=BEARING_COLORS[b], linewidth=0.8, linestyle=":")
            elif pd.notna(lead):
                ax.text(0.99, 0.95, f"B{b}: brief alarm {lead:.0f} h before end (off-axis)",
                        transform=ax.transAxes, ha="right", va="top", fontsize=8,
                        color=MUTED)
        ax.axhline(C_FLOOR, color=MUTED, linewidth=0.8, linestyle="--")
        ax.set_title(f"Set {set_no}", fontsize=10, loc="left", color=INK)
        ax.set_ylabel("Energy growth vs. peers\n(log RMS ratio)", color=INK, fontsize=9)
        ax.legend(frameon=False, fontsize=8, ncol=4, loc="upper left")
        style_axes(ax)
    axes[-1].set_xlabel("Hours before end of test", color=INK)
    fig.suptitle("A. Where/when: peer-contrast energy growth, last 200 h "
                 f"(dashed = floor {C_FLOOR:g}; dotted = alarm time)",
                 fontsize=11, x=0.01, ha="left", color=INK)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "diag_detection.png", dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def plot_failed(timeline: pd.DataFrame, summary: pd.DataFrame):
    shown = (("fei", "proposed"), ("base", "baseline (fixed band)"))
    fig, axes = plt.subplots(len(FAILED_RUNS), 2, figsize=(13, 11))
    for row_axes, (s, b, mode) in zip(axes, FAILED_RUNS):
        t = timeline[(timeline["set"] == s) & (timeline["bearing"] == b)
                     & (timeline["hours_before_end"] <= 150)]
        info = summary[(summary["set"] == s) & (summary["bearing"] == b)].iloc[0]
        for ax, (tag, name) in zip(row_axes, shown):
            for d in DEFECTS:
                ax.plot(-t["hours_before_end"], t[f"{tag}_{d}"], color=DEFECT_COLORS[d],
                        linewidth=1.4, label=d)
            if pd.notna(info["alarm_h_before_end"]):
                ax.axvline(-info["alarm_h_before_end"], color=MUTED, linewidth=0.8,
                           linestyle=":")
            ax.set_title(f"Set {s} B{b}, truth {mode} | {name}: {info[f'verdict[{name}]']}",
                         fontsize=9.5, loc="left", color=INK)
            ax.set_ylabel("FEI (z)", color=INK, fontsize=9)
            style_axes(ax)
    for ax in axes[-1]:
        ax.set_xlabel("Hours before end of test", color=INK)
    axes[0, 0].legend(frameon=False, fontsize=9, ncol=3, loc="upper left")
    fig.suptitle("B. What: fault evidence per defect type on the failed bearings, last 150 h "
                 "(dotted = alarm from A)",
                 fontsize=11, x=0.01, ha="left", color=INK)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "diag_fei_failed.png", dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def plot_envelopes(timeline: pd.DataFrame):
    """Whitened envelope spectrum of each failed bearing at its strongest evidence."""
    fig, axes = plt.subplots(len(FAILED_RUNS), 1, figsize=(11, 10))
    for ax, (s, b, mode) in zip(axes, FAILED_RUNS):
        feats = load_features(s)
        t = timeline[(timeline["set"] == s) & (timeline["bearing"] == b)]
        best = t.loc[t[f"fei_{TRUTH_NAME[mode]}"].idxmax()]
        snap = feats[feats["timestamp"] <= best["timestamp"]].iloc[-1]
        ch = feats.loc[feats["bearing"] == b, "channel"].min() - 1
        x = pd.read_csv(SETS[s]["dir"] / snap["file"], sep=r"\s+", header=None).to_numpy()[:, ch]
        _, (lo, hi), E = select_band(x - x.mean())
        df = FS / NFFT
        S = E / (ndimage.median_filter(E, size=int(20 / df) | 1) + 1e-12)
        f = np.arange(len(S)) * df
        m = (f > 2) & (f <= 1000)
        ax.plot(f[m], S[m], color=MUTED, linewidth=0.7)
        sc = comb_scores(E)
        top = TRUTH_NAME[mode]
        for d in DEFECTS:
            for order, w in COMBS[d]:
                fl = order * sc[f"alpha_{d}"] * SHAFT_HZ
                if (w == 1.0 or d == top) and fl <= 1000:
                    ax.axvline(fl, color=DEFECT_COLORS[d], linewidth=1.1 if d == top else 0.8,
                               alpha=0.9 if d == top else 0.35,
                               linestyle="-" if d == top else "--")
        rpm = sc[f"alpha_{top}"] * SHAFT_HZ * 60
        ax.set_title(f"Set {s} B{b} ({mode}), {best['hours_before_end']:.0f} h before end: "
                     f"band {lo / 1e3:g}-{hi / 1e3:g} kHz, best-fit speed {rpm:.0f} rpm",
                     fontsize=9.5, loc="left", color=INK)
        ax.set_ylabel("Peak / noise floor", color=INK, fontsize=9)
        style_axes(ax)
    axes[-1].set_xlabel("Envelope frequency (Hz)", color=INK)
    handles = [plt.Line2D([], [], color=DEFECT_COLORS[d], label=f"{d} comb") for d in DEFECTS]
    axes[0].legend(handles=handles, frameon=False, fontsize=9, ncol=3, loc="upper right")
    fig.suptitle("Whitened envelope spectra at peak evidence (solid = true defect's comb "
                 "incl. sidebands / cage lines; dashed = other combs)",
                 fontsize=11, x=0.01, ha="left", color=INK)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "diag_envelope_examples.png", dpi=130, facecolor="#fcfcfb")
    plt.close(fig)


def main():
    summary, timeline = evaluate()
    comparison = compare(summary)
    summary.to_csv(OUT_DIR / "diag_summary.csv", index=False)
    comparison.to_csv(OUT_DIR / "diag_comparison.csv", index=False)
    timeline.to_csv(OUT_DIR / "diag_timeline.csv", index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    print(summary.to_string(index=False))
    print()
    print(comparison.to_string(index=False))
    plot_detection(timeline, summary)
    plot_failed(timeline, summary)
    plot_envelopes(timeline)
    print(f"wrote CSVs and plots to {OUT_DIR}")


if __name__ == "__main__":
    main()
