"""Robustness checks for the Part II strategy comparison (maintenance.py).

  1. Cross-talk: is set 1 B3's early AI alarm B3's own signal, or B4's fault
     heard through the shared housing? Compares which features drive each
     bearing's autoencoder error, and Stage B fault evidence, 71-12 h before end.
  2. Thresholds: Stage A and the autoencoder were tuned on these 12 bearings.
     Re-scores physics / AI / physics OR AI over 27 threshold settings.
  3. Leave one test out: costs recomputed on the other two tests (preventive
     re-tuned on them), to show how much one bearing moves the ranking.
  4. Needless replacement cost: a false alarm may cost more than a planned
     replacement (downtime). Re-scores with needless = 1, 2, 5.

Usage:  python pipeline/maintenance_checks.py      (~1 min, CPU)
Needs:  features.py, diagnosis.py, dl_diagnosis.py outputs
Outputs: pipeline/outputs/maintenance_check_{crosstalk,thresholds,leave_test_out,needless}.csv
"""
import itertools

import numpy as np
import pandas as pd
import torch

import diagnosis as G
import dl_diagnosis as D
from common import FAILED_RUNS, OUT_DIR, load_features
from maintenance import T_GRID, TEST_END_H, age_replacement, outcome, rate

LEAD, RATIO = 24.0, 10.0
FAILED = {(s, b) for s, b, _ in FAILED_RUNS}


def crosstalk():
    f = load_features(1)
    x = np.log(f.pivot_table(index="timestamp", columns="bearing", values=D.AE_FEATURES, aggfunc="mean"))
    n, bs = G.n_healthy(len(x)), sorted(f["bearing"].unique())
    tr = np.concatenate([x.xs(b, axis=1, level="bearing")[D.AE_FEATURES].iloc[:n].to_numpy() for b in bs])
    mu, sd = tr.mean(0), tr.std(0) + 1e-6
    torch.manual_seed(0)                          # same training as dl_diagnosis.ae_detection
    model, t = D.AE(), torch.tensor((tr - mu) / sd, dtype=torch.float32)
    opt = torch.optim.Adam(model.parameters(), lr=3e-3)
    for _ in range(600):
        opt.zero_grad()
        ((model(t) - t) ** 2).mean().backward()
        opt.step()
    left = (x.index[-1] - x.index).total_seconds().to_numpy() / 3600
    win = (left <= 71) & (left > 12)
    tl = pd.read_csv(OUT_DIR / "diag_timeline.csv")
    rows = []
    for b in (3, 4):
        v = torch.tensor((x.xs(b, axis=1, level="bearing")[D.AE_FEATURES].to_numpy() - mu) / sd,
                         dtype=torch.float32)
        with torch.no_grad():
            e = ((model(v) - v) ** 2).numpy()
        rise = e[win].mean(0) - e[:n].mean(0)
        fei = tl[(tl.set == 1) & (tl.bearing == b) & (tl.hours_before_end <= 71) & (tl.hours_before_end > 12)]
        for feat, r in zip(D.AE_FEATURES, rise):
            rows.append({"bearing": f"set1 B{b}", "feature": feat, "ae_error_rise": r})
        for col in ("fei_outer", "fei_inner", "fei_roller"):
            rows.append({"bearing": f"set1 B{b}", "feature": col, "ae_error_rise": np.nan,
                         "mean_fei": fei[col].mean()})
    out = pd.DataFrame(rows)
    out.to_csv(OUT_DIR / "maintenance_check_crosstalk.csv", index=False)
    for b in ("set1 B3", "set1 B4"):
        d = out[out.bearing == b]
        top = d.dropna(subset=["ae_error_rise"]).nlargest(4, "ae_error_rise")["feature"].tolist()
        fei = d.dropna(subset=["mean_fei"]).set_index("feature")["mean_fei"].round(2).to_dict()
        print(f"{b}: AE error driven by {top}; Stage B FEI 71-12 h before end {fei}")


def contrasts():
    data = {}
    for s in (1, 2, 3):
        f = load_features(s)
        cA = G.detection(f)[1]
        cB = D.ae_detection(f)[0]
        left = (cA.index[-1] - cA.index).total_seconds().to_numpy() / 3600
        data[s] = (cA, cB, left, G.n_healthy(len(cA)))
    return data


def alarm_h(c, b, n, left, k, floor):
    ref = c[b].iloc[:n].to_numpy()
    a = G.persistent(c[b].to_numpy() > np.median(ref) + max(k * G.robust_sd(ref), floor))
    return np.nan if a is None else left[a]


def score(recs, w, lead=LEAD, cf=RATIO, needless=1.0):
    """recs: (failed, end_h) per bearing; w: alarm hours before end per bearing."""
    caught = sum(f and x >= lead for (f, _), x in zip(recs, w))
    false = sum((not f) and not np.isnan(x) for (f, _), x in zip(recs, w))
    cost = rate([outcome(e, f, x, lead, cf, cp=1.0 if f else needless) for (f, e), x in zip(recs, w)])
    return caught, false, cost


def thresholds(data):
    rows = []
    for k, fa, fb in itertools.product((6, 8, 10), (0.10, 0.15, 0.20), (0.4, 0.5, 0.6)):
        recs, phys, ai = [], [], []
        for s, (cA, cB, left, n) in data.items():
            for b in cA.columns:
                recs.append(((s, b) in FAILED, TEST_END_H[s]))
                phys.append(alarm_h(cA, b, n, left, k, fa))
                ai.append(alarm_h(cB, b, n, left, k, fb))
        for name, w in (("physics", phys), ("AI", ai), ("physics OR AI", list(np.fmax(phys, ai)))):
            c, fl, cost = score(recs, w)
            rows.append({"k_sigma": k, "physics_floor": fa, "ai_floor": fb, "strategy": name,
                         "failures_caught": c, "needless_replacements": fl, "cost_per_1000h": cost})
    out = pd.DataFrame(rows)
    out.to_csv(OUT_DIR / "maintenance_check_thresholds.csv", index=False)
    g = out.groupby("strategy")
    print(pd.DataFrame({"settings_with_4_of_4": g["failures_caught"].apply(lambda v: (v == 4).sum()),
                        "settings": g.size(),
                        "cost_min": g["cost_per_1000h"].min().round(2),
                        "cost_max": g["cost_per_1000h"].max().round(2)}).to_string())


def default_bearings():
    b = pd.read_csv(OUT_DIR / "dl_summary.csv")
    b["failed"] = b["truth"] != "healthy"
    b["end_h"] = b["set"].map(TEST_END_H)
    b["either"] = np.fmax(b["stageA_alarm_h"], b["ae_alarm_h"])
    return b


def leave_test_out(b):
    rows = []
    for out_set in (None, 1, 2, 3):
        d = b if out_set is None else b[b["set"] != out_set]
        recs = list(zip(d["failed"], d["end_h"]))
        row = {"held_out": "none" if out_set is None else f"set {out_set}",
               "failures": int(d["failed"].sum()),
               "reactive": rate([(RATIO if f else 0.0, e) for f, e in recs]),
               "preventive": min(rate([age_replacement(e, f, T, RATIO) for f, e in recs]) for T in T_GRID)}
        for name, col in (("physics", "stageA_alarm_h"), ("AI", "ae_alarm_h"), ("physics OR AI", "either")):
            row[name] = score(recs, d[col].to_numpy(float))[2]
        rows.append(row)
    out = pd.DataFrame(rows)
    out.to_csv(OUT_DIR / "maintenance_check_leave_test_out.csv", index=False)
    print(out.round(2).to_string(index=False))


def needless_cost(b):
    recs = list(zip(b["failed"], b["end_h"]))
    rows = [{"needless_cost": cn, **{name: score(recs, b[col].to_numpy(float), needless=cn)[2]
                                     for name, col in (("physics", "stageA_alarm_h"), ("AI", "ae_alarm_h"),
                                                       ("physics OR AI", "either"))}}
            for cn in (1.0, 2.0, 5.0)]
    out = pd.DataFrame(rows)
    out.to_csv(OUT_DIR / "maintenance_check_needless.csv", index=False)
    print(out.round(2).to_string(index=False))


def main():
    print("1. Cross-talk check (set 1 B3 vs B4)")
    crosstalk()
    print("\n2. Threshold sweep, 27 settings (lead 24 h, breakdown 10x)")
    thresholds(contrasts())
    b = default_bearings()
    print("\n3. Leave one test out: cost per 1,000 h (lead 24 h, breakdown 10x)")
    leave_test_out(b)
    print("\n4. Needless replacement cost (planned = 1, breakdown = 10)")
    needless_cost(b)
    print(f"\nwrote maintenance_check_*.csv to {OUT_DIR}")


if __name__ == "__main__":
    main()
