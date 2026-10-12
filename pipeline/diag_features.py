"""Raw-signal stage of the proposed fault-diagnosis method (Part I).

For every (file, channel) snapshot this computes speed-tolerant fault-signature
scores from an adaptively demodulated envelope spectrum:

  1. Adaptive demodulation band (infogram-style). A bank of band-pass filters
     (1, 2 and 4 kHz wide, half-overlapping, 0.5-9.75 kHz, plus the fixed
     1-9 kHz band) is applied in the FFT domain; the band whose envelope
     spectrum is spikiest (highest kurtosis over 5-1000 Hz) is kept. That
     rewards *periodic* impacts rather than one random spike, which plain
     time-domain kurtosis latches onto. Defect impacts excite a structural
     resonance whose location differs per sensor and moves as damage grows,
     so a fixed band (features.py uses 1-9 kHz) dilutes them with noise.
  2. Whitened squared-envelope spectrum: divided by its running median so a
     peak is measured as a ratio to the local noise floor, independent of
     overall vibration level.
  3. Order-domain comb matching with a speed-scale search. Defect frequencies
     are fixed multiples (orders) of shaft speed, but the true speed on the IMS
     rig is ~2.5% below the nominal 2000 rpm (the outer-race line sits at
     ~230 Hz, not the catalogue 236.4 Hz). Each comb is evaluated over a scale
     factor alpha in [0.95, 1.01] and the best alignment is kept.

Comb scores (mean log peak-to-floor ratio over the comb's lines):
  outer   : 1-3 x BPFO
  inner   : 1-3 x BPFI, plus 1-2 x BPFI +/- shaft sidebands (inner race turns
            with the shaft, so its impacts are amplitude-modulated at 1x)
  roller  : 1-3 x 2*BSF, plus 1-4 x FTF (a rolling-element defect travels
            with the cage, so it is modulated at the cage frequency)
  shaft   : 1-8 x shaft (reference comb; not a bearing-specific defect)
Columns nom_score_* repeat the combs at the catalogue speed only (ablation).

Usage:
    python pipeline/diag_features.py            # all three sets
    python pipeline/diag_features.py --sets 2
Outputs: pipeline/outputs/diag_scores_set{N}.csv
"""
import argparse
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
from scipy import ndimage, stats

from features import FS, OUT_DIR, SETS, parse_timestamp

# Defect frequencies as orders of shaft speed for the Rexnord ZA-2115
# (16 rollers, Pd = 2.815 in, Bd = 0.331 in, contact angle 15.17 deg).
SHAFT_HZ = 2000 / 60
ORDERS = {"bpfo": 7.092, "bpfi": 8.908, "bsf2": 8.394, "ftf": 0.443, "shaft": 1.0}

ALPHAS = np.arange(0.95, 1.0101, 0.0025)   # speed-scale search grid
NOMINAL = np.array([1.0])                   # ablation: catalogue speed only
BANDWIDTHS = (1000, 2000, 4000)            # Hz; >= 3x BPFI so harmonics survive
F_LO, F_HI = 500, 9750
NFFT = 2 * 20480                            # zero-padded envelope FFT (0.49 Hz bins)
TOL_HZ = 1.5                                # peak search half-width around a line
FLOOR_HZ = 20                               # running-median width for the noise floor


def _comb_lines():
    """Each comb as a list of (order, weight) lines."""
    o = ORDERS
    return {
        "outer": [(h * o["bpfo"], 1.0) for h in (1, 2, 3)],
        "inner": [(h * o["bpfi"], 1.0) for h in (1, 2, 3)]
                 + [(h * o["bpfi"] + s, 0.5) for h in (1, 2) for s in (-1, 1)],
        "roller": [(h * o["bsf2"], 1.0) for h in (1, 2, 3)]
                  + [(h * o["ftf"], 0.5) for h in (1, 2, 3, 4)],
        "shaft": [(h * o["shaft"], 1.0) for h in range(1, 9)],
    }


COMBS = _comb_lines()


def candidate_bands():
    bands = [(1000, 9000)]
    for bw in BANDWIDTHS:
        fc = F_LO + bw / 2
        while fc + bw / 2 <= F_HI:
            bands.append((fc - bw / 2, fc + bw / 2))
            fc += bw / 2
    return bands


BANDS = candidate_bands()
_FE = np.fft.rfftfreq(NFFT, 1 / FS)
_CYCLIC = (_FE > 5) & (_FE < 1000)   # envelope-spectrum range used to rank bands


def envelope_spectrum(env2: np.ndarray) -> np.ndarray:
    env2 = env2 - env2.mean()
    return np.abs(np.fft.rfft(env2 * np.hanning(len(env2)), n=NFFT))


def select_band(x: np.ndarray):
    """Return (criterion, band, envelope spectrum) of the best candidate band."""
    X = np.fft.fft(x)
    f = np.abs(np.fft.fftfreq(len(x), 1 / FS))
    pos = np.fft.fftfreq(len(x)) > 0
    best = (-np.inf, None, None)
    for lo, hi in BANDS:
        # Analytic signal of the band: keep positive frequencies only, doubled.
        env2 = np.abs(np.fft.ifft(np.where(pos & (f >= lo) & (f < hi), 2 * X, 0))) ** 2
        E = envelope_spectrum(env2)
        k = stats.kurtosis(E[_CYCLIC], fisher=False)
        if k > best[0]:
            best = (k, (lo, hi), E)
    return best


def comb_scores(E: np.ndarray, alphas: np.ndarray = ALPHAS) -> dict:
    df = FS / NFFT
    floor = ndimage.median_filter(E, size=int(FLOOR_HZ / df) | 1) + 1e-12
    S = np.log(np.maximum(E / floor, 1e-3))
    # Local max within +/- TOL_HZ, so each line lookup is one index.
    S_max = ndimage.maximum_filter1d(S, size=2 * int(TOL_HZ / df) + 1)

    out = {}
    for name, lines in COMBS.items():
        orders = np.array([o for o, _ in lines])
        w = np.array([w for _, w in lines])
        bins = np.rint(np.outer(alphas * SHAFT_HZ, orders) / df).astype(int)
        vals = (S_max[bins] * w).sum(1) / w.sum()     # one score per alpha
        i = int(np.argmax(vals))
        out[f"score_{name}"] = float(vals[i])
        out[f"alpha_{name}"] = float(alphas[i])
    return out


def snapshot_features(x: np.ndarray) -> dict:
    x = x - x.mean()
    spiky, (lo, hi), E = select_band(x)
    nominal = {f"nom_{k}": v for k, v in comb_scores(E, NOMINAL).items()
               if k.startswith("score_")}
    return {"band_lo": lo, "band_hi": hi, "env_spec_kurtosis": spiky,
            **comb_scores(E), **nominal}


def process_file(args) -> list[dict]:
    path, set_no, channels = args
    data = pd.read_csv(path, sep=r"\s+", header=None, engine="c").to_numpy()
    ts = parse_timestamp(path.name)
    rows = []
    for ch_idx, (bearing, axis) in enumerate(channels):
        row = {"set": set_no, "file": path.name, "timestamp": ts,
               "channel": ch_idx + 1, "bearing": bearing, "axis": axis}
        row.update(snapshot_features(data[:, ch_idx]))
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
        out = OUT_DIR / f"diag_scores_set{s}.csv"
        df.to_csv(out, index=False)
        print(f"  wrote {out} ({len(df)} rows)")


if __name__ == "__main__":
    main()
