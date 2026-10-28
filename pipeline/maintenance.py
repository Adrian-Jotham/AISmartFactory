"""Part II decision layer: when to plan maintenance.

Combines Part I and the gbm RUL model from rul.py:
  1. gbm predicts RUL (hours, capped at --cap).
  2. Conformal lower bound: RUL_low = pred - q, where q is the --alpha quantile
     of calibration residuals (pred - true). Overestimating RUL is the
     dangerous error, so the bound is one-sided.
  3. Gate: maintenance can only be planned after the Part I Stage A alarm
     (diag_summary.csv). Part I says "it is failing", Part II says "act now".
  4. PLAN maintenance once RUL_low < --lead hours (parts + crew lead time).

Evaluation is leave-one-run-out over the 4 failed bearings. Calibration for a
held-out run is nested leave-one-out over its 3 training runs (train on 2,
residuals on the 3rd), so the held-out run never touches the bound. Healthy
bearings use gbm trained on all 4 runs and q from the 4 outer LORO residuals.

Usage:  python pipeline/maintenance.py [--cap 100] [--lead 24] [--alpha 0.9]
Needs:  features.py, diag_features.py, diagnosis.py (diag_summary.csv)
Outputs: pipeline/outputs/maintenance_summary.csv, maintenance_decisions.png
"""
import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import FAILED_RUNS, OUT_DIR
from rul import build_run, feature_cols, fit_gbm, style_axes

COLORS = {"true": "#52514e", "gbm": "#2a78d6", "low": "#7b4fd6",
          "gate": "#efeee9", "lead": "#d03b3b"}


def first_plan(rul_est, hours_left, lead, gate_h=np.inf):
    """Hours before the end when PLAN first fires; 0 if it never does."""
    hit = np.flatnonzero((rul_est < lead) & (hours_left <= gate_h))
    return float(hours_left[hit[0]]) if hit.size else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cap", type=float, default=100.0, help="RUL cap in hours")
    ap.add_argument("--lead", type=float, default=24.0,
                    help="maintenance lead time in hours (plan when RUL_low < lead)")
    ap.add_argument("--alpha", type=float, default=0.9,
                    help="target coverage of the conformal lower bound")
    args = ap.parse_args()
    cap, lead, alpha = args.cap, args.lead, args.alpha

    diag = pd.read_csv(OUT_DIR / "diag_summary.csv").set_index(["set", "bearing"])
    alarm_h = diag["alarm_h_before_end"].fillna(-1.0)   # -1: no alarm, gate never opens
    runs = {(s, b): build_run(s, b, cap) for s, b, _ in FAILED_RUNS}
    modes = {(s, b): m for s, b, m in FAILED_RUNS}

    def predict(train_keys, df):
        model = fit_gbm(pd.concat([runs[k] for k in train_keys], ignore_index=True), cap)
        return np.clip(model.predict(df[feature_cols(df)]), 0, cap)

    def residuals(pred, df):
        m = df["rul_true"].to_numpy() <= cap
        return pred[m] - df["rul_true"].to_numpy()[m]

    rows, curves, outer_resid = [], {}, []
    for key, test in runs.items():
        train = [k for k in runs if k != key]
        cal = [residuals(predict([k for k in train if k != c], runs[c]), runs[c])
               for c in train]
        q = np.quantile(np.concatenate(cal), alpha)

        pred = predict(train, test)
        outer_resid.append(residuals(pred, test))
        low = np.clip(pred - q, 0, cap)
        y = test["rul_true"].to_numpy()
        m = y <= cap
        curves[key] = (test, pred, low)
        rows.append({"set": key[0], "bearing": key[1], "truth": modes[key],
                     "alarm_h_before_end": diag.loc[key, "alarm_h_before_end"],
                     "margin_h": q, "coverage": (y[m] >= low[m]).mean(),
                     "plan_gbm_h": first_plan(pred, y, lead),
                     "plan_conformal_h": first_plan(low, y, lead),
                     "plan_gated_h": first_plan(low, y, lead, alarm_h[key])})

    # Healthy bearings: would the decision layer send a crew to a good bearing?
    q_all = np.quantile(np.concatenate(outer_resid), alpha)
    for key in diag.index[diag["truth"] == "healthy"]:
        df = build_run(*key, cap)
        pred = predict(list(runs), df)
        low = np.clip(pred - q_all, 0, cap)
        y = df["rul_true"].to_numpy()        # hours before the end of the test
        rows.append({"set": key[0], "bearing": key[1], "truth": "healthy",
                     "alarm_h_before_end": diag.loc[key, "alarm_h_before_end"],
                     "margin_h": q_all, "coverage": np.nan,
                     "plan_gbm_h": first_plan(pred, y, lead),
                     "plan_conformal_h": first_plan(low, y, lead),
                     "plan_gated_h": first_plan(low, y, lead, alarm_h[key])})

    summ = pd.DataFrame(rows)
    summ.to_csv(OUT_DIR / "maintenance_summary.csv", index=False)
    f, h = summ[summ["truth"] != "healthy"], summ[summ["truth"] == "healthy"]
    print(f"PLAN when RUL lower bound < {lead:g} h; target coverage {alpha:.0%}.")
    print("plan_*_h = hours before the end when PLAN first fires (0 = never).")
    print(summ.round(2).to_string(index=False))
    for col in ("plan_gbm_h", "plan_conformal_h", "plan_gated_h"):
        msg = f"{col:17s} failed planned >= {lead:g} h ahead: {(f[col] >= lead).sum()}/4"
        if h[col].notna().all():
            msg += f"   healthy bearings with a PLAN: {(h[col] > 0).sum()}/{len(h)}"
        print(msg)

    # Figure: one panel per failed run
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.5))
    for ax, (key, (df, pred, low)) in zip(axes.flat, curves.items()):
        y = df["rul_true"].to_numpy()
        win = y <= 2 * cap
        x = -y[win]
        a = diag.loc[key, "alarm_h_before_end"]
        ax.axvspan(-a, 0, color=COLORS["gate"], label="After Part I alarm")
        ax.axhline(lead, color=COLORS["lead"], linestyle=":", linewidth=1,
                   label=f"Lead time ({lead:g} h)")
        ax.plot(x, np.minimum(y, cap)[win], color=COLORS["true"], linestyle="--",
                linewidth=1.6, label=f"True RUL (capped at {cap:g} h)")
        ax.plot(x, pred[win], color=COLORS["gbm"], linewidth=1.2, label="Gradient boosting")
        ax.plot(x, low[win], color=COLORS["low"], linewidth=1.6,
                label=f"Conformal lower bound ({alpha:.0%})")
        t_plan = first_plan(low, y, lead, a)
        if t_plan > 0:
            ax.axvline(-t_plan, color=COLORS["low"], linewidth=1)
            ax.annotate(f"PLAN {t_plan:.0f} h ahead", (-t_plan, cap * 0.92),
                        xytext=(4, 0), textcoords="offset points",
                        fontsize=8, color=COLORS["low"])
        ax.set_title(f"Set {key[0]} bearing {key[1]} ({modes[key]})", fontsize=10,
                     loc="left", color="#0b0b0b")
        ax.set_xlabel("Hours before failure", color="#0b0b0b")
        ax.set_ylabel("RUL (h)", color="#0b0b0b")
        style_axes(ax)
    axes[0, 0].legend(frameon=False, fontsize=7.5, loc="lower left")
    fig.suptitle("When to plan maintenance: Part I alarm gates a conformal RUL bound "
                 "(each run held out)", fontsize=11, x=0.01, ha="left", color="#0b0b0b")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "maintenance_decisions.png", dpi=130, facecolor="#fcfcfb")
    plt.close(fig)
    print(f"wrote maintenance_summary.csv and maintenance_decisions.png to {OUT_DIR}")


if __name__ == "__main__":
    main()
