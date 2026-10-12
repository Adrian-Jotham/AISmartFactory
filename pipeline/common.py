"""Shared loading / cleaning helpers for the IMS bearing pipeline."""
from pathlib import Path

import pandas as pd

OUT_DIR = Path(__file__).resolve().parent / "outputs"

# Run-to-failure examples: (set, bearing, failure mode)
FAILED_RUNS = [
    (1, 3, "inner race"),
    (1, 4, "roller element"),
    (2, 1, "outer race"),
    (3, 3, "outer race"),
]

# Snapshots whose RMS is far below anything physical were recorded after the rig
# stopped (last 2 files of set 2, last file of set 3). Drop them.
DEAD_RMS = 0.02

# Validated categorical palette (dataviz reference palette, light mode), one
# fixed slot per bearing.
BEARING_COLORS = {1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a", 4: "#eda100"}


def load_features(set_no: int) -> pd.DataFrame:
    """Per-(file, channel) features with dead snapshots removed."""
    df = pd.read_csv(OUT_DIR / f"features_set{set_no}.csv", parse_dates=["timestamp"])
    df["axis"] = df["axis"].fillna("")  # sets 2/3 have one unnamed axis per bearing
    dead = df.groupby("file")["rms"].transform("min") < DEAD_RMS
    n_dead = df.loc[dead, "file"].nunique()
    if n_dead:
        print(f"set {set_no}: dropping {n_dead} dead snapshot(s)")
    return df[~dead].sort_values(["timestamp", "channel"]).reset_index(drop=True)


def bearing_frame(df: pd.DataFrame, bearing: int) -> pd.DataFrame:
    """One row per snapshot for a bearing; set 1's x/y channels are averaged."""
    num = df.select_dtypes("number").columns.difference(["set", "channel", "bearing"])
    return (df[df["bearing"] == bearing]
            .groupby("timestamp", as_index=False)[list(num)].mean()
            .sort_values("timestamp")
            .reset_index(drop=True))
