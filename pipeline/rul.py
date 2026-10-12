"""Baseline RUL models for the IMS run-to-failure bearings.

There are only four run-to-failure examples (set1 B3, set1 B4, set2 B1,
set3 B3), so every model is evaluated leave-one-run-out: the held-out run's
data is never used for training, thresholds or scaling. The headline result is
set 2 bearing 1.

Labels: RUL (hours) = time of last live snapshot - snapshot time, capped at
--cap hours (piecewise-linear target). A healthy bearing looks the same 500 h or
100 h before failure, so asking a model to tell them apart is noise.

Models
  gbm : gradient-boosted trees on normalised, smoothed features from the
        three training runs.
  hi  : health-indicator extrapolation. HI = log(RMS / healthy RMS). After a
        degradation onset is detected, fit a line to HI (i.e. exponential RMS
        growth) and extrapolate to the failure threshold learned from the
        training runs. Uses no learning across runs except that threshold.

Usage:  python pipeline/rul.py [--cap 100] [--test 2:1]
Outputs: pipeline/outputs/rul_predictions.csv, rul_metrics.csv,
         rul_set2_b1.png, rul_all_runs.png
"""
import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from common import FAILED_RUNS, OUT_DIR, bearing_frame, load_features

# Positive-valued features, normalised as log(value / healthy baseline).
FEATURES = ["rms", "peak", "p2p", "kurtosis", "crest", "shape", "impulse",
            "spec_centroid", "band_0_1k", "band_1_3k", "band_3_6k", "band_6_10k",
            "env_bpfo", "env_bpfi", "env_bsf", "env_ftf"]
BASELINE_FRAC = 0.2   # first 20% of a run defines "healthy"
SMOOTH = 6            # causal rolling median, snapshots (~1 h)
TREND_LAG = 36        # snapshots (~6 h) for the trend feature

COLORS = {"true": "#52514e", "gbm": "#2a78d6", "hi": "#eb6834"}


def build_run(set_no: int, bearing: int, cap: float) -> pd.DataFrame:
    """Feature matrix + RUL labels for one bearing, all causal."""
    b = bearing_frame(load_features(set_no), bearing)
    n_base = max(20, int(len(b) * BASELINE_FRAC))
    base = b[FEATURES].iloc[:n_base].median()

    out = pd.DataFrame({"set": set_no, "bearing": bearing,
                        "timestamp": b["timestamp"], "hours": b["hours"]})
    for f in FEATURES:
        z = np.log(b[f] / base[f]).rolling(SMOOTH, min_periods=1).median()
        out[f"{f}_lvl"] = z
        out[f"{f}_trend"] = z - z.shift(TREND_LAG).fillna(z.iloc[0])
    # Spread of the health indicator during the healthy window (for onset detection)
    out.attrs["hi_sigma"] = out["rms_lvl"].iloc[:n_base].std()

    rul = b["hours"].iloc[-1] - b["hours"]
    out["rul_true"] = rul
    out["rul_label"] = rul.clip(upper=cap)
    return out


def feature_cols(df):
    return [c for c in df.columns if c.endswith(("_lvl", "_trend"))]


def fit_gbm(train: pd.DataFrame, cap: float) -> HistGradientBoostingRegressor:
    # Balance: every run counts equally, and within a run the healthy (capped)
    # and degrading portions count equally. Otherwise set 3's ~6000 healthy
    # snapshots dominate.
    w = np.ones(len(train))
    for _, idx in train.groupby(["set", "bearing"]).groups.items():
        sub = train.loc[idx]
        degr = (sub["rul_label"] < cap).to_numpy()
        for mask in (degr, ~degr):
            if mask.any():
                w[train.index.get_indexer(idx[mask])] = 0.5 / mask.sum()
    model = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05,
                                          max_leaf_nodes=15, min_samples_leaf=40,
                                          l2_regularization=1.0, random_state=0)
    model.fit(train[feature_cols(train)], train["rul_label"], sample_weight=w)
    return model


def hi_predict(run: pd.DataFrame, threshold: float, cap: float,
               min_points: int = 12) -> np.ndarray:
    """Online exponential-degradation extrapolation on the RMS health indicator."""
    hi = run["rms_lvl"].to_numpy()
    t = run["hours"].to_numpy()
    onset_level = max(3 * run.attrs["hi_sigma"], np.log(1.2))
    above = pd.Series(hi > onset_level).rolling(SMOOTH).sum().to_numpy() == SMOOTH
    onset = int(np.argmax(above)) if above.any() else None

    pred = np.full(len(run), cap)
    if onset is None:
        return pred
    for i in range(onset + min_points, len(run)):
        tt, yy = t[onset:i + 1], hi[onset:i + 1]
        slope, icpt = np.polyfit(tt, yy, 1)
        if slope <= 0:
            # Temporary dip in the HI: once degradation has started, don't
            # snap back to "healthy" - carry the last estimate forward.
            pred[i] = max(pred[i - 1] - (t[i] - t[i - 1]), 0)
            continue
        if hi[i] >= threshold:
            pred[i] = 0.0
        else:
            pred[i] = np.clip((threshold - icpt) / slope - t[i], 0, cap)
    return pred


def metrics(df: pd.DataFrame, col: str, cap: float) -> dict:
    d = df[df["rul_true"] <= cap]          # the part where RUL is actually knowable
    err = d[col] - d["rul_true"]
    return {"rmse_h": np.sqrt(np.mean(err ** 2)), "mae_h": np.mean(np.abs(err)),
            "n": len(d)}


def style_axes(ax):
    ax.grid(color="#e6e5e0", linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#a9a8a2")
    ax.tick_params(colors="#52514e", labelsize=9)


def plot_run(ax, df, cap, title, window=None):
    hrs_to_fail = df["rul_true"]
    m = hrs_to_fail <= (window or hrs_to_fail.max())
    x = -hrs_to_fail[m]
    ax.plot(x, df.loc[m, "rul_label"], color=COLORS["true"], linestyle="--",
            linewidth=1.6, label=f"True RUL (capped at {cap:g} h)")
    ax.plot(x, df.loc[m, "pred_gbm"], color=COLORS["gbm"], linewidth=1.4,
            label="Gradient boosting")
    ax.plot(x, df.loc[m, "pred_hi"], color=COLORS["hi"], linewidth=1.4,
            label="HI extrapolation")
    ax.set_title(title, fontsize=10, loc="left", color="#0b0b0b")
    ax.set_xlabel("Hours before failure", color="#0b0b0b")
    ax.set_ylabel("RUL (h)", color="#0b0b0b")
    style_axes(ax)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cap", type=float, default=100.0,
                    help="RUL cap in hours for the piecewise-linear target")
    ap.add_argument("--test", default="2:1", help="headline run as SET:BEARING")
    args = ap.parse_args()
    cap = args.cap
    test_key = tuple(int(v) for v in args.test.split(":"))

    runs = {(s, b): build_run(s, b, cap) for s, b, _ in FAILED_RUNS}
    modes = {(s, b): m for s, b, m in FAILED_RUNS}

    preds, rows = [], []
    for key, test in runs.items():
        train_keys = [k for k in runs if k != key]
        train = pd.concat([runs[k] for k in train_keys], ignore_index=True)

        model = fit_gbm(train, cap)
        threshold = np.median([runs[k]["rms_lvl"].iloc[-1] for k in train_keys])

        test = test.copy()
        test["pred_gbm"] = np.clip(model.predict(test[feature_cols(test)]), 0, cap)
        test["pred_hi"] = hi_predict(test, threshold, cap)
        preds.append(test)

        for name in ("gbm", "hi"):
            rows.append({"set": key[0], "bearing": key[1], "failure": modes[key],
                         "model": name, **metrics(test, f"pred_{name}", cap)})

    pred_df = pd.concat(preds, ignore_index=True)
    keep = ["set", "bearing", "timestamp", "hours", "rul_true", "rul_label",
            "pred_gbm", "pred_hi"]
    pred_df[keep].to_csv(OUT_DIR / "rul_predictions.csv", index=False)
    met = pd.DataFrame(rows)
    met.to_csv(OUT_DIR / "rul_metrics.csv", index=False)

    print(f"Leave-one-run-out errors over the last {cap:g} h of each run (hours):")
    print(met.round(1).to_string(index=False))

    # Headline plot
    s, b = test_key
    head = pred_df[(pred_df["set"] == s) & (pred_df["bearing"] == b)]
    fig, ax = plt.subplots(figsize=(10, 4.8))
    plot_run(ax, head, cap, f"Set {s} bearing {b} ({modes[test_key]} failure), "
             "trained on the other three runs", window=2 * cap)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT_DIR / f"rul_set{s}_b{b}.png", dpi=130, facecolor="#fcfcfb")
    plt.close(fig)

    # All runs
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5))
    for ax, (key, df) in zip(axes.flat, pred_df.groupby(["set", "bearing"])):
        plot_run(ax, df, cap, f"Set {key[0]} bearing {key[1]} ({modes[key]})",
                 window=2 * cap)
    axes[0, 0].legend(frameon=False, fontsize=8)
    fig.suptitle("Leave-one-run-out RUL predictions (each panel's run held out)",
                 fontsize=11, x=0.01, ha="left", color="#0b0b0b")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "rul_all_runs.png", dpi=130, facecolor="#fcfcfb")
    plt.close(fig)
    print(f"wrote plots and CSVs to {OUT_DIR}")


if __name__ == "__main__":
    main()
