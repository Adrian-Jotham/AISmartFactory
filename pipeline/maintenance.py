"""Part II: which maintenance strategy should the factory use?

Every strategy is replayed on the same 12 IMS bearings (4 failed, 8 healthy
until their test ended) and scored by cost per 1,000 operating hours:

  reactive      run to failure, repair after the breakdown
  preventive    replace every T hours (T tuned on this same data: optimistic)
  physics       condition-based, Part I Stage A alarm (diag_summary.csv)
  AI            condition-based, autoencoder alarm (dl_summary.csv, no labels)
  physics OR AI condition-based, whichever alarm fires first
  oracle        replace each failing bearing just in time (lower bound)

Condition-based: the crew replaces the bearing --lead hours after the alarm
(parts + scheduling). If it breaks first, that is a breakdown. An alarm on a
healthy bearing is a needless replacement.

Costs: planned replacement = 1, breakdown = --ratio (downtime, secondary
damage, rush parts). Cost rate = total cost / total hours run, the usual
renewal-reward estimate with each bearing as one cycle.

Usage:  python pipeline/maintenance.py [--lead 24] [--ratio 10]
Needs:  diagnosis.py and dl_diagnosis.py outputs
Outputs: pipeline/outputs/maintenance_strategies.csv, maintenance_cost_curve.csv,
         maintenance_lead_sweep.csv, maintenance_strategies.png
"""
import argparse

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import OUT_DIR
from rul import style_axes

TEST_END_H = {1: 827.6, 2: 163.5, 3: 1073.1}   # last live snapshot of each test
T_GRID = np.arange(24, 1100, 4)                # preventive intervals searched
LEADS = (4, 8, 12, 24, 48, 72)                 # crew lead times swept (h)
RATIOS = np.array([1.5, 2, 3, 5, 7, 10, 15, 20, 30, 50, 70, 100])
COLORS = {"reactive": "#d64545", "preventive": "#8a9a9b", "physics": "#1f8a8a",
          "AI": "#7b4fd6", "physics OR AI": "#f26b4f", "oracle": "#12262b"}


def outcome(end, failed, warn, lead, cf, cp=1.0):
    """(cost, hours run) for one bearing under a condition-based rule.

    end: hours the bearing ran in the test; warn: alarm, hours before `end`
    (nan = never alarmed)."""
    if np.isnan(warn):
        return (cf if failed else 0.0), end
    act = end - warn + lead                      # crew arrives
    if failed and act > end:
        return cf, end                           # broke before the crew came
    return cp, min(act, end)


def age_replacement(end, failed, T, cf, cp=1.0):
    if end > T:
        return cp, T
    return (cf if failed else 0.0), end


def rate(pairs):
    cost, hours = np.array(pairs).sum(0)
    return 1000 * cost / hours


def selfcheck():
    assert outcome(100, True, np.nan, 24, 10) == (10, 100)      # no alarm: breakdown
    assert outcome(100, True, 50, 24, 10) == (1, 74)            # caught, 26 h of life wasted
    assert outcome(100, True, 10, 24, 10) == (10, 100)          # alarm too late
    assert outcome(100, False, 5, 24, 10) == (1, 100)           # false alarm still costs a crew
    assert age_replacement(100, True, 80, 10) == (1, 80)
    assert age_replacement(100, False, 120, 10) == (0, 100)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lead", type=float, default=24.0, help="hours from alarm to replacement")
    ap.add_argument("--ratio", type=float, default=10.0, help="breakdown cost / planned cost")
    args = ap.parse_args()
    selfcheck()

    b = pd.read_csv(OUT_DIR / "dl_summary.csv")[["set", "bearing", "truth", "stageA_alarm_h", "ae_alarm_h"]]
    b["failed"] = b["truth"] != "healthy"
    b["end_h"] = b["set"].map(TEST_END_H)
    triggers = {"physics": b["stageA_alarm_h"].to_numpy(float),
                "AI": b["ae_alarm_h"].to_numpy(float)}
    triggers["physics OR AI"] = np.fmax(triggers["physics"], triggers["AI"])  # earliest alarm
    end, failed = b["end_h"].to_numpy(), b["failed"].to_numpy()

    def cost_rates(cf, lead):
        out = {"reactive": rate([(cf if f else 0.0, e) for e, f in zip(end, failed)])}
        prev = [rate([age_replacement(e, f, T, cf) for e, f in zip(end, failed)]) for T in T_GRID]
        out["preventive"] = min(prev)
        out["preventive_T"] = T_GRID[int(np.argmin(prev))]
        for name, w in triggers.items():
            out[name] = rate([outcome(e, f, x, lead, cf) for e, f, x in zip(end, failed, w)])
        out["oracle"] = rate([(1.0 if f else 0.0, e) for e, f in zip(end, failed)])
        return out

    # Per-strategy outcome table at the chosen lead and ratio
    base = cost_rates(args.ratio, args.lead)
    rows = [{"strategy": "reactive", "failures_caught": 0, "breakdowns": int(failed.sum()),
             "needless_replacements": 0, "mean_life_wasted_h": 0.0},
            {"strategy": f"preventive (every {base['preventive_T']} h)"}]
    T = base["preventive_T"]
    rows[1].update(failures_caught=int((failed & (end > T)).sum()),
                   breakdowns=int((failed & (end <= T)).sum()),
                   needless_replacements=int((~failed & (end > T)).sum()),
                   mean_life_wasted_h=float(np.mean((end - T)[failed & (end > T)]))
                   if (failed & (end > T)).any() else 0.0)
    for name, w in triggers.items():
        caught = failed & (w >= args.lead)
        rows.append({"strategy": name, "failures_caught": int(caught.sum()),
                     "breakdowns": int(failed.sum() - caught.sum()),
                     "needless_replacements": int((~failed & ~np.isnan(w)).sum()),
                     "mean_life_wasted_h": float(np.mean(w[caught] - args.lead)) if caught.any() else 0.0})
    rows.append({"strategy": "oracle", "failures_caught": int(failed.sum()), "breakdowns": 0,
                 "needless_replacements": 0, "mean_life_wasted_h": 0.0})
    keys = ["reactive", "preventive", *triggers, "oracle"]
    for r, k in zip(rows, keys):
        r[f"cost_per_1000h(ratio={args.ratio:g})"] = base[k]
    table = pd.DataFrame(rows)
    table.to_csv(OUT_DIR / "maintenance_strategies.csv", index=False)
    print(f"Lead time {args.lead:g} h, breakdown costs {args.ratio:g}x a planned replacement:")
    print(table.round(2).to_string(index=False))

    # Cost rate vs breakdown cost ratio
    curve = pd.DataFrame([{"ratio": r, **cost_rates(r, args.lead)} for r in RATIOS])
    curve.to_csv(OUT_DIR / "maintenance_cost_curve.csv", index=False)
    print("\nCost per 1,000 h vs breakdown cost ratio:")
    print(curve.round(2).to_string(index=False))

    # How fast must the crew act? Failures caught and cost vs lead time
    sweep = []
    for L in LEADS:
        c = cost_rates(args.ratio, L)
        for name, w in triggers.items():
            sweep.append({"lead_h": L, "strategy": name,
                          "failures_caught": int((failed & (w >= L)).sum()),
                          f"cost_per_1000h(ratio={args.ratio:g})": c[name]})
    sweep = pd.DataFrame(sweep)
    sweep.to_csv(OUT_DIR / "maintenance_lead_sweep.csv", index=False)
    print("\nLead-time sweep (condition-based strategies):")
    print(sweep.round(2).to_string(index=False))

    fig, ax = plt.subplots(figsize=(9, 5))
    for k in keys:
        ax.plot(curve["ratio"], curve[k], color=COLORS[k], linewidth=2.2 if k == "physics OR AI" else 1.6,
                linestyle="--" if k == "oracle" else "-", label=k)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(RATIOS[[0, 2, 3, 5, 7, 9, 11]], labels=[f"{r:g}x" for r in RATIOS[[0, 2, 3, 5, 7, 9, 11]]])
    ax.set_xlabel("Breakdown cost / planned replacement cost", color="#0b0b0b")
    ax.set_ylabel("Cost per 1,000 operating hours", color="#0b0b0b")
    ax.set_title(f"Maintenance strategies on the 12 IMS bearings (lead time {args.lead:g} h)",
                 fontsize=10, loc="left", color="#0b0b0b")
    style_axes(ax)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "maintenance_strategies.png", dpi=130, facecolor="#fcfcfb")
    plt.close(fig)
    print(f"wrote maintenance_strategies.csv, maintenance_cost_curve.csv, "
          f"maintenance_lead_sweep.csv, maintenance_strategies.png to {OUT_DIR}")


if __name__ == "__main__":
    main()
