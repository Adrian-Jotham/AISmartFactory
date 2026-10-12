"""Plot RMS and kurtosis over time for every bearing in every set.

Usage:  python pipeline/plots.py
Outputs: pipeline/outputs/trend_set{N}.png
"""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from common import BEARING_COLORS, FAILED_RUNS, OUT_DIR, load_features

FEATURES = [("rms", "RMS (g)"), ("kurtosis", "Kurtosis")]
SMOOTH = 12  # snapshots (~2 h) for the rolling-median overlay


def style_axes(ax):
    ax.grid(axis="y", color="#e6e5e0", linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#a9a8a2")
    ax.tick_params(colors="#52514e", labelsize=9)


def plot_set(set_no: int):
    df = load_features(set_no)
    failed = {b: mode for s, b, mode in FAILED_RUNS if s == set_no}

    fig, axes = plt.subplots(len(FEATURES), 1, figsize=(11, 6.5), sharex=True)
    for ax, (col, label) in zip(axes, FEATURES):
        for (bearing, axis), g in df.groupby(["bearing", "axis"]):
            color = BEARING_COLORS[bearing]
            linestyle = "--" if axis == "y" else "-"
            name = f"Bearing {bearing}" + (f" {axis}" if axis else "")
            if bearing in failed:
                name += f" (failed: {failed[bearing]})"
            ax.plot(g["hours"], g[col], color=color, alpha=0.15, linewidth=0.6)
            ax.plot(g["hours"], g[col].rolling(SMOOTH, min_periods=1).median(),
                    color=color, linewidth=1.6, linestyle=linestyle, label=name)
        ax.set_ylabel(label, color="#0b0b0b")
        style_axes(ax)
    axes[0].set_yscale("log")
    axes[1].set_yscale("log")
    axes[-1].set_xlabel("Hours since start of test", color="#0b0b0b")
    axes[0].legend(frameon=False, fontsize=9, ncol=2, loc="upper left")
    fig.suptitle(f"IMS set {set_no}: vibration RMS and kurtosis per bearing "
                 f"(faint = raw snapshot, solid = {SMOOTH}-snapshot rolling median)",
                 fontsize=11, x=0.01, ha="left", color="#0b0b0b")
    fig.tight_layout()
    out = OUT_DIR / f"trend_set{set_no}.png"
    fig.savefig(out, dpi=130, facecolor="#fcfcfb")
    plt.close(fig)
    print(f"wrote {out}")


if __name__ == "__main__":
    for s in (1, 2, 3):
        plot_set(s)
