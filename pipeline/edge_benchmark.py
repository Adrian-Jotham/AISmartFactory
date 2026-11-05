"""Edge benchmark of the AI alarm's full per-snapshot path, from raw file to
anomaly score, on whatever machine runs it (laptop, Raspberry Pi):

  read      parse the raw IMS text file (20,480 rows x 4 sensors)
  features  16 condition features per sensor (features.channel_features: FFT, band energies, envelope)
  infer     log, scale (ae_set2_norm.json), ONNX autoencoder, reconstruction error

Runs single-threaded so numbers are comparable across devices. Writes the scores,
so two machines can be checked for identical results.

Needs only numpy, scipy, pandas, onnxruntime and features.py (no torch).
Usage:  python edge_benchmark.py --snapshots DIR --model ae_set2.onnx --norm ae_set2_norm.json --out scores.csv [--summary timing.csv]
        python edge_benchmark.py --compare laptop_scores.csv pi_scores.csv
"""
import argparse
import json
import os
import platform
import time
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np
import pandas as pd

from features import channel_features

try:
    import resource                      # Linux only (peak memory)
except ImportError:
    resource = None


def device():
    try:
        return Path("/proc/device-tree/model").read_text().strip("\0 \n")
    except OSError:
        return platform.processor() or platform.machine()


def run(args):
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = so.inter_op_num_threads = 1
    sess = ort.InferenceSession(args.model, so, providers=["CPUExecutionProvider"])
    norm = json.loads(Path(args.norm).read_text())
    mu, sd, names = np.array(norm["mean"]), np.array(norm["sd"]), norm["features"]

    files = sorted(Path(args.snapshots).iterdir())
    rows, t = [], {"read": [], "features": [], "infer": []}
    for i, f in enumerate(files):
        t0 = time.perf_counter()
        data = pd.read_csv(f, sep=r"\s+", header=None, engine="c").to_numpy()
        t1 = time.perf_counter()
        feats = [channel_features(data[:, ch]) for ch in range(data.shape[1])]
        t2 = time.perf_counter()
        v = ((np.log(np.array([[fe[k] for k in names] for fe in feats])) - mu) / sd).astype(np.float32)
        err = ((sess.run(None, {"x": v})[0] - v) ** 2).mean(1)
        t3 = time.perf_counter()
        if i >= args.warmup:
            for k, a, b in (("read", t0, t1), ("features", t1, t2), ("infer", t2, t3)):
                t[k].append((b - a) * 1e3)
        rows += [{"file": f.name, "bearing": b + 1, "rms": feats[b]["rms"], "score": float(err[b])}
                 for b in range(len(err))]
    pd.DataFrame(rows).to_csv(args.out, index=False)

    tot = np.add(np.add(t["read"], t["features"]), t["infer"])
    print(f"device: {device()} | python {platform.python_version()} | single thread")
    print(f"snapshots timed: {len(tot)} (4 sensors each, {args.warmup} warm-up skipped)")
    for k, v in (*t.items(), ("total", tot), ("compute (features + infer)", np.add(t["features"], t["infer"]))):
        print(f"  {k:28s} median {np.median(v):8.2f} ms   p95 {np.percentile(v, 95):8.2f} ms")
    mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 if resource else float("nan")
    if resource:
        print(f"  peak memory (RSS)            {mem:.0f} MB")
    if args.summary:
        row = {"device": device(), "python": platform.python_version(), "snapshots_timed": len(tot), "sensors": 4}
        for k, v in (*t.items(), ("total", tot), ("compute", np.add(t["features"], t["infer"]))):
            row[f"{k}_median_ms"], row[f"{k}_p95_ms"] = round(float(np.median(v)), 2), round(float(np.percentile(v, 95)), 2)
        row["peak_rss_mb"] = round(mem) if resource else None
        pd.DataFrame([row]).to_csv(args.summary, index=False)


def compare(a, b):
    x, y = pd.read_csv(a), pd.read_csv(b)
    assert (x[["file", "bearing"]].values == y[["file", "bearing"]].values).all()
    rel = (x.score - y.score).abs() / x.score.abs()
    print(f"{len(x)} scores compared: max relative difference {rel.max():.2e}")
    print(f"rms max relative difference {((x.rms - y.rms).abs() / x.rms).max():.2e}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshots"), ap.add_argument("--model"), ap.add_argument("--norm")
    ap.add_argument("--out", default="edge_scores.csv")
    ap.add_argument("--summary", help="write a one-row CSV with the timings")
    ap.add_argument("--warmup", type=int, default=5)
    ap.add_argument("--compare", nargs=2)
    args = ap.parse_args()
    compare(*args.compare) if args.compare else run(args)
