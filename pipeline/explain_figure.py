"""Teaching figure: what a bearing fault looks like in the raw signal and in
the envelope spectrum (set 2 bearing 1, healthy vs. near failure).

Usage:  python pipeline/explain_figure.py
Output: pipeline/outputs/explain_signal.png
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import ndimage

from common import OUT_DIR, load_features
from diag_features import FS, NFFT, SETS, select_band

INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e6e5e0"
HEALTHY, FAULTY = "#8a8984", "#2a78d6"


def style_axes(ax):
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#a9a8a2")
    ax.tick_params(colors=MUTED, labelsize=9)


def main():
    feats = load_features(2)
    files = feats["file"].unique()
    picks = {"Healthy (hour 5)": (files[30], HEALTHY),
             "Near failure (20 h before end)": (files[-121], FAULTY)}

    fig, axes = plt.subplots(2, 2, figsize=(12, 6.5))
    for col, (label, (name, color)) in enumerate(picks.items()):
        x = pd.read_csv(SETS[2]["dir"] / name, sep=r"\s+", header=None).to_numpy()[:, 0]
        x = x - x.mean()
        t = np.arange(len(x)) / FS * 1000
        m = t <= 50
        ax = axes[0, col]
        ax.plot(t[m], x[m], color=color, linewidth=0.7)
        ax.set_ylim(-1.2, 1.2)
        ax.set_title(f"{label}: raw vibration, first 50 ms", fontsize=10,
                     loc="left", color=INK)
        ax.set_xlabel("Time (ms)", color=INK)
        ax.set_ylabel("Acceleration (g)", color=INK)
        style_axes(ax)

        _, _, E = select_band(x)
        df = FS / NFFT
        S = E / (ndimage.median_filter(E, size=int(20 / df) | 1) + 1e-12)
        f = np.arange(len(S)) * df
        m = (f > 2) & (f <= 800)
        ax = axes[1, col]
        ax.plot(f[m], S[m], color=color, linewidth=0.8)
        for h in (1, 2, 3):
            ax.axvline(h * 230.4, color="#eb6834", linewidth=0.8, linestyle="--", alpha=0.7)
        ax.set_ylim(0, 50)
        ax.set_title(f"{label}: envelope spectrum\n(dashed = outer-race rhythm 230 Hz and its multiples)",
                     fontsize=10, loc="left", color=INK)
        ax.set_xlabel("Repetition frequency (Hz)", color=INK)
        ax.set_ylabel("Peak / noise floor", color=INK)
        style_axes(ax)
    fig.suptitle("Set 2 bearing 1: a damaged outer race adds a 230-per-second 'click' "
                 "that the envelope spectrum turns into sharp peaks",
                 fontsize=11, x=0.01, ha="left", color=INK)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "explain_signal.png", dpi=130, facecolor="#fcfcfb")
    plt.close(fig)
    print(f"wrote {OUT_DIR / 'explain_signal.png'}")


if __name__ == "__main__":
    main()
