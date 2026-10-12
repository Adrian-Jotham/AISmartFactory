"""Extract per-file, per-channel vibration features from the IMS bearing dataset.

Each raw file is a 1.024 s snapshot (20,480 samples @ 20 kHz) with one column
per accelerometer channel. This script turns every (file, channel) pair into
one row of time-domain, frequency-domain and envelope-spectrum features.

Usage:
    python pipeline/features.py            # all three sets
    python pipeline/features.py --sets 2   # just set 2
Outputs: pipeline/outputs/features_set{N}.csv
"""
import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import signal, stats

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = Path(__file__).resolve().parent / "outputs"

FS = 20_000  # Hz
SHAFT_HZ = 2000 / 60  # 33.3 Hz

# Rexnord ZA-2115 characteristic defect frequencies at 2000 RPM
# (Qiu et al., J. Sound Vib. 289 (2006)).
FAULT_FREQS = {"bpfo": 236.4, "bpfi": 296.9, "bsf": 279.8, "ftf": 14.8}

SETS = {
    1: {
        "dir": ROOT / "1st_test" / "1st_test",
        # 8 channels: two (x, y) per bearing
        "channels": [(1, "x"), (1, "y"), (2, "x"), (2, "y"),
                     (3, "x"), (3, "y"), (4, "x"), (4, "y")],
    },
    2: {
        "dir": ROOT / "2nd_test" / "2nd_test",
        "channels": [(1, ""), (2, ""), (3, ""), (4, "")],
    },
    3: {
        "dir": ROOT / "3rd_test" / "4th_test" / "txt",
        "channels": [(1, ""), (2, ""), (3, ""), (4, "")],
    },
}

BANDS = [(0, 1000), (1000, 3000), (3000, 6000), (6000, 10000)]

# Band-pass for envelope analysis: keep the structural-resonance region excited
# by defect impacts, drop shaft/gear-mesh energy at low frequency.
_ENV_SOS = signal.butter(4, [1000, 9000], btype="bandpass", fs=FS, output="sos")


def parse_timestamp(name: str) -> datetime:
    return datetime.strptime(name, "%Y.%m.%d.%H.%M.%S")


def envelope_amplitude(spec: np.ndarray, freqs: np.ndarray, f0: float,
                       harmonics: int = 3, tol: float = 3.0) -> float:
    """Sum of peak envelope-spectrum amplitudes at f0 and its harmonics."""
    total = 0.0
    for k in range(1, harmonics + 1):
        mask = np.abs(freqs - k * f0) <= tol
        if mask.any():
            total += spec[mask].max()
    return total


def channel_features(x: np.ndarray) -> dict:
    x = x - x.mean()
    absx = np.abs(x)
    rms = np.sqrt(np.mean(x ** 2))
    peak = absx.max()
    mean_abs = absx.mean()

    feats = {
        "rms": rms,
        "peak": peak,
        "p2p": x.max() - x.min(),
        "kurtosis": stats.kurtosis(x, fisher=False),  # ~3 for a healthy bearing
        "skewness": stats.skew(x),
        "crest": peak / rms,
        "shape": rms / mean_abs,
        "impulse": peak / mean_abs,
    }

    # Spectrum
    spec = np.abs(np.fft.rfft(x)) / len(x)
    freqs = np.fft.rfftfreq(len(x), 1 / FS)
    power = spec ** 2
    feats["spec_centroid"] = float((freqs * power).sum() / power.sum())
    for lo, hi in BANDS:
        m = (freqs >= lo) & (freqs < hi)
        feats[f"band_{lo // 1000}_{hi // 1000}k"] = float(np.sqrt(power[m].sum()))

    # Envelope spectrum
    env = np.abs(signal.hilbert(signal.sosfiltfilt(_ENV_SOS, x)))
    env -= env.mean()
    env_spec = np.abs(np.fft.rfft(env)) / len(env)
    for name, f0 in FAULT_FREQS.items():
        feats[f"env_{name}"] = envelope_amplitude(env_spec, freqs, f0)

    return feats


def process_file(args) -> list[dict]:
    path, set_no, channels = args
    data = pd.read_csv(path, sep=r"\s+", header=None, engine="c").to_numpy()
    ts = parse_timestamp(path.name)
    rows = []
    for ch_idx, (bearing, axis) in enumerate(channels):
        row = {
            "set": set_no,
            "file": path.name,
            "timestamp": ts,
            "channel": ch_idx + 1,
            "bearing": bearing,
            "axis": axis,
        }
        row.update(channel_features(data[:, ch_idx]))
        rows.append(row)
    return rows


def extract_set(set_no: int, workers: int) -> pd.DataFrame:
    cfg = SETS[set_no]
    files = sorted((p for p in cfg["dir"].iterdir() if p.is_file()),
                   key=lambda p: parse_timestamp(p.name))
    print(f"Set {set_no}: {len(files)} files from {cfg['dir']}")
    jobs = [(p, set_no, cfg["channels"]) for p in files]
    rows = []
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for i, file_rows in enumerate(ex.map(process_file, jobs, chunksize=16), 1):
            rows.extend(file_rows)
            if i % 500 == 0 or i == len(files):
                print(f"  {i}/{len(files)}")
    df = pd.DataFrame(rows)
    start = df["timestamp"].min()
    df.insert(3, "hours", (df["timestamp"] - start).dt.total_seconds() / 3600)
    return df


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sets", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--workers", type=int, default=None)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for s in args.sets:
        df = extract_set(s, args.workers)
        out = OUT_DIR / f"features_set{s}.csv"
        df.to_csv(out, index=False)
        print(f"  wrote {out} ({len(df)} rows)")


if __name__ == "__main__":
    main()
