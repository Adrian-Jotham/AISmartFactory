"""Feature stage for the deep-learning variant: one whitened envelope spectrum
per (snapshot, sensor), stored as a fixed-length vector for the networks.

Each spectrum is the same one Stage B of the proposed method reads
(adaptive band, squared envelope, divided by its running-median noise floor),
as log(peak / floor), cut to 0-1000 Hz and max-pooled to 1024 bins (~0.98 Hz).

Usage:  python pipeline/dl_spectra.py
Outputs: pipeline/outputs/dl_spectra_set{N}.npy (float16, rows x 1024)
         pipeline/outputs/dl_index_set{N}.csv  (one row per spectrum)
"""
import argparse
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
from scipy import ndimage

from diag_features import FS, NFFT, select_band
from features import OUT_DIR, SETS, parse_timestamp

FLOOR_HZ = 20
F_MAX = 1000.0
N_BINS = 1024
DF = FS / NFFT
_RAW_BINS = 2 * N_BINS  # 2048 x 0.488 Hz = 1000 Hz, pooled by 2


def spectrum(x: np.ndarray) -> np.ndarray:
    _, _, E = select_band(x - x.mean())
    floor = ndimage.median_filter(E, size=int(FLOOR_HZ / DF) | 1) + 1e-12
    S = np.log(np.maximum(E / floor, 1e-3))[:_RAW_BINS]
    return S.reshape(N_BINS, 2).max(1).astype(np.float16)


def process_file(args):
    path, set_no, channels = args
    data = pd.read_csv(path, sep=r"\s+", header=None, engine="c").to_numpy()
    ts = parse_timestamp(path.name)
    rows, specs = [], []
    for ch_idx, (bearing, axis) in enumerate(channels):
        rows.append({"set": set_no, "file": path.name, "timestamp": ts,
                     "channel": ch_idx + 1, "bearing": bearing, "axis": axis})
        specs.append(spectrum(data[:, ch_idx]))
    return rows, specs


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sets", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()
    for s in args.sets:
        cfg = SETS[s]
        files = sorted((p for p in cfg["dir"].iterdir() if p.is_file()),
                       key=lambda p: parse_timestamp(p.name))
        print(f"Set {s}: {len(files)} files")
        rows, specs = [], []
        with ProcessPoolExecutor(max_workers=args.workers) as ex:
            for r, sp in ex.map(process_file, [(p, s, cfg["channels"]) for p in files],
                                chunksize=16):
                rows += r
                specs += sp
        idx = pd.DataFrame(rows)
        idx.insert(3, "hours", (idx["timestamp"] - idx["timestamp"].min()).dt.total_seconds() / 3600)
        idx.to_csv(OUT_DIR / f"dl_index_set{s}.csv", index=False)
        np.save(OUT_DIR / f"dl_spectra_set{s}.npy", np.stack(specs))
        print(f"  wrote {len(idx)} spectra")


if __name__ == "__main__":
    main()
