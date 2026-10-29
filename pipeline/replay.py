"""Data for bearing_replay.html, a seven-step story of test 2 for a general audience.

Every bearing: alarm hours before the end (physics = Stage A, AI = autoencoder),
recomputed with the Part I functions and checked against dl_summary.csv; the
page's cost model scores all 12 bearings from these.
Test 2 only, on a 15-minute grid, per bearing:
  rms    vibration level, g
  phys   Stage A peer contrast / its alarm limit (1 = limit)
  dx     mean Stage B fault evidence (clipped at 0) per defect from the physics
         alarm onward, the input of diagnosis.identify; checked against its verdict
The JSON is written into the page's <script id="replay-data"> block.

Usage:  python pipeline/replay.py      (~20 s, CPU; needs torch)
"""
import json
import re

import numpy as np
import pandas as pd

import diagnosis as G
import dl_diagnosis as D
from common import FAILED_RUNS, OUT_DIR, load_features
from maintenance import TEST_END_H

PAGE = OUT_DIR.parent.parent / "bearing_replay.html"
STORY, BIN_H = 2, 0.25
TRUTH = {(s, b): G.TRUTH_NAME[m] for s, b, m in FAILED_RUNS}


def r3(a):
    return [None if np.isnan(v) else round(float(v), 3) for v in a]


def export_set(s, summary):
    f = load_features(s)
    _, cA, limA, alA, _ = G.detection(f)
    _, alB = D.ae_detection(f)
    rms = f.pivot_table(index="timestamp", columns="bearing", values="rms", aggfunc="mean")
    hours = ((rms.index - rms.index[0]).total_seconds() / 3600).to_numpy()
    left = hours[-1] - hours
    assert abs(hours[-1] - TEST_END_H[s]) < 0.05
    out = {"id": s, "end": TEST_END_H[s], "bearings": []}
    if s == STORY:
        ev = G.fault_evidence(G.load_set(s)["diag"], {d: f"score_{d}" for d in G.DEFECTS}, "fleet")
        bins = (hours // BIN_H).astype(int)
        last = pd.Series(hours).groupby(bins).apply(lambda g: g.index[-1]).to_numpy()   # last snapshot per bin
        med = lambda v: pd.Series(v).groupby(bins).median().to_numpy()
        out.update(dt=BIN_H, t=r3(pd.Series(hours).groupby(bins).mean().to_numpy()))
    for b in rms.columns:
        row = summary[(summary["set"] == s) & (summary["bearing"] == b)].iloc[0]
        warn = {k: (round(float(left[a]), 1) if a is not None else None)
                for k, a in (("stageA_alarm_h", alA[b]), ("ae_alarm_h", alB[b]))}
        for k, v in warn.items():
            assert v == (None if np.isnan(row[k]) else float(row[k])), (s, b, k, v, row[k])
        brg = {"b": int(b), "truth": TRUTH.get((s, b), "healthy"),
               "warnPhys": warn["stageA_alarm_h"], "warnAI": warn["ae_alarm_h"]}
        if s == STORY:
            fei = np.clip(np.stack([ev[d][b].reindex(rms.index).to_numpy() for d in G.DEFECTS], 1), 0, None)
            dx = np.full((len(last), 3), np.nan)
            if alA[b] is not None:
                a = alA[b]
                run = np.cumsum(fei[a:], 0) / np.arange(1, len(fei) - a + 1)[:, None]
                ok = last >= a
                dx[ok] = run[last[ok] - a]
                v = run[-1]
                verdict = G.DEFECTS[int(v.argmax())] if v.max() >= G.UNSPEC_FEI else "unspecified"
                assert verdict == row["verdict[proposed]"], (s, b, verdict, row["verdict[proposed]"])
            brg.update(rms=r3(med(rms[b].to_numpy())), phys=r3(med(cA[b].to_numpy() / limA[b])),
                       dx=[r3(dx[:, i]) for i in range(3)])
        out["bearings"].append(brg)
    return out


def main():
    summary = pd.read_csv(OUT_DIR / "dl_summary.csv")
    data = {"tests": [export_set(s, summary) for s in (1, 2, 3)]}
    for t in data["tests"]:
        print(f"set {t['id']}: " + ", ".join(f"B{b['b']} phys={b['warnPhys']} ai={b['warnAI']}" for b in t["bearings"]))
    page = PAGE.read_text(encoding="utf-8")
    block = re.compile(r'(<script id="replay-data" type="application/json">).*?(</script>)', re.S)
    assert block.search(page), "replay-data block not found"
    page = block.sub(lambda m: m.group(1) + json.dumps(data, separators=(",", ":")) + m.group(2), page)
    PAGE.write_text(page, encoding="utf-8")
    print(f"alarm hours and verdicts match dl_summary.csv; wrote replay data into {PAGE.name} ({len(page) / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
