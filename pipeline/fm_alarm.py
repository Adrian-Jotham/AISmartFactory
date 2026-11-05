"""Alarms from pretrained foundation models, used zero-shot (no training on IMS
by us). Two models:

  moment    MOMENT-1-small (Goswami et al., ICML 2024): general time-series
            model, 38M parameters. Input: 512 samples, instance-normalised.
            Each 1-s snapshot -> 40 windows of 512 samples.
  unifault  UniFault-Tiny (Eldele et al., 2025): bearing-vibration model,
            0.8M parameters. Input: 0.1 s resampled to 1024 samples, min-max
            scaled with the healthy window's range. Each snapshot -> 10 windows.
            Caution: IMS is one of the paper's datasets, so parts of it were
            probably in UniFault's pretraining data.

Each window is embedded and the window embeddings of a snapshot are averaged.
The anomaly score of a snapshot is the mean squared z-distance to its 5 nearest
healthy embeddings (first 20% of the test, all bearings pooled, like the AI
alarm). The score goes through the SAME peer-contrast + persistence rule as the
AI alarm (dl_diagnosis.score_alarms), with no retuning.

Needs the raw IMS files, `pip install momentfm` (pins old numpy/transformers:
use a separate virtual environment) and the UniFault-Tiny checkpoint
(github.com/emadeldeen24/UniFault) at --unifault_ckpt.

Usage:  python pipeline/fm_alarm.py --unifault_ckpt path/to/pretrain-epoch=1.ckpt
Outputs: pipeline/outputs/fm_{model}_emb_set{N}.npy (cached embeddings, gitignored)
         pipeline/outputs/fm_summary.csv  (alarm hours before the end, per bearing and model)
         pipeline/outputs/fm_threshold_sweep.csv  (same 9 K x floor settings as the AI-alarm check)
"""
import argparse
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import torch
from scipy.signal import resample_poly
from torch import nn

from common import FAILED_RUNS, OUT_DIR, load_features
from diagnosis import n_healthy
from dl_diagnosis import score_alarms
from features import SETS
from maintenance import TEST_END_H, outcome, rate

K_NN = 5


def read(path):
    return pd.read_csv(path, sep=r"\s+", header=None, engine="c").to_numpy(np.float32)


# ------------------------------------------------------------------ UniFault-Tiny
class UniFaultTiny(nn.Module):
    """Re-implementation of the UniFault backbone (model/model.py, Transformer_utils.py);
    loads the released tensors by name."""

    def __init__(self, d=128, heads=4, depth=4, patch=64, n_patch=16):
        super().__init__()
        self.patch, self.heads = patch, heads
        self.patch_embed = nn.Linear(patch, d)
        self.pos_embed = nn.Parameter(torch.zeros(1, n_patch, d))
        self.layers = nn.ModuleList(nn.ModuleDict({
            "q": nn.Linear(d, d), "k": nn.Linear(d, d), "v": nn.Linear(d, d), "o": nn.Linear(d, d),
            "ff1": nn.Linear(d, 4 * d), "ff2": nn.Linear(4 * d, d),
            "n1": nn.LayerNorm(d), "n2": nn.LayerNorm(d)}) for _ in range(depth))
        self.norm = nn.LayerNorm(d)

    def load(self, ckpt):
        sd = torch.load(ckpt, map_location="cpu", weights_only=True)["state_dict"]
        names = {"q": "attention.query_projection", "k": "attention.key_projection",
                 "v": "attention.value_projection", "o": "attention.out_projection",
                 "ff1": "conv1", "ff2": "conv2", "n1": "norm1", "n2": "norm2"}
        mine = {"patch_embed.weight": sd["model.patch_embed.input_layer.weight"],
                "patch_embed.bias": sd["model.patch_embed.input_layer.bias"],
                "pos_embed": sd["model.pos_embed"],
                "norm.weight": sd["model.encoder.norm.weight"], "norm.bias": sd["model.encoder.norm.bias"]}
        for i in range(len(self.layers)):
            for a, b in names.items():
                for p in ("weight", "bias"):
                    mine[f"layers.{i}.{a}.{p}"] = sd[f"model.encoder.attn_layers.{i}.{b}.{p}"]
        self.load_state_dict(mine)
        return self

    def forward(self, x):                                   # x: (B, 1024)
        x = self.patch_embed(x.unflatten(-1, (-1, self.patch))) + self.pos_embed
        B, L, D = x.shape
        for l in self.layers:
            q, k, v = (l[n](x).view(B, L, self.heads, -1).transpose(1, 2) for n in "qkv")
            a = torch.softmax(q @ k.transpose(-1, -2) / (D // self.heads) ** 0.5, -1) @ v
            x = l["n1"](x + l["o"](a.transpose(1, 2).reshape(B, L, D)))
            x = l["n2"](x + l["ff2"](nn.functional.silu(l["ff1"](x))))
        return self.norm(x).mean(1)                         # (B, 128)


def unifault_windows(data, lo, hi):
    """(20480, C) snapshot -> (C*10, 1024): 10 windows of 0.1 s, 20 kHz -> 10.24 kHz, min-max."""
    x = resample_poly(data, 1, 2, axis=0)[:10 * 1024]
    x = (x - lo) / (hi - lo + 1e-6)
    return x.T.reshape(-1, 1024).astype(np.float32)


# ------------------------------------------------------------------ embedding
@torch.no_grad()
def embed_set(s, files, kind, model, n):
    C = len(SETS[s]["channels"])
    paths = [SETS[s]["dir"] / f for f in files]
    lo = hi = None
    if kind == "unifault":                                  # healthy-window range per channel
        with ThreadPoolExecutor(8) as pool:
            h = np.stack([resample_poly(d, 1, 2, axis=0) for d in pool.map(read, paths[:n])])
        lo, hi = h.min((0, 1)), h.max((0, 1))
    out = []
    with ThreadPoolExecutor(8) as pool:
        for i, data in enumerate(pool.map(read, paths)):
            if kind == "moment":
                x = torch.from_numpy(data[:512 * 40].T.reshape(C * 40, 1, 512)).cuda()
                e = model.embed(x_enc=x).embeddings
            else:
                e = model(torch.from_numpy(unifault_windows(data, lo, hi)).cuda())
            out.append(e.reshape(C, -1, e.shape[-1]).mean(1).float().cpu().numpy())
            if i % 1000 == 0:
                print(f"{kind} set {s}: {i}/{len(files)}")
    return np.stack(out)                                    # (time, channel, d)


def knn_score(E, bearing_of, n):
    bearings = sorted(set(bearing_of))
    Eb = np.stack([E[:, bearing_of == b].mean(1) for b in bearings], 1)    # (time, bearing, d)
    tr = Eb[:n].reshape(-1, Eb.shape[-1])
    mu, sd = tr.mean(0), tr.std(0) + 1e-6
    trz = torch.from_numpy((tr - mu) / sd).cuda()
    err = {}
    for k, b in enumerate(bearings):
        z = torch.from_numpy((Eb[:, k] - mu) / sd).cuda()
        d = torch.cdist(z, trz) ** 2 / z.shape[1]
        own = torch.arange(n, device=d.device)
        d[own, own * len(bearings) + k] = float("inf")     # a healthy point is not its own neighbour
        err[b] = d.topk(K_NN, largest=False).values.mean(1).cpu().numpy()
    return err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--unifault_ckpt", required=True)
    args = ap.parse_args()

    from momentfm import MOMENTPipeline
    moment = MOMENTPipeline.from_pretrained("AutonLab/MOMENT-1-small",
                                            model_kwargs={"task_name": "embedding"})
    moment.init()
    models = {"moment": moment.cuda().eval(),
              "unifault": UniFaultTiny().load(args.unifault_ckpt).cuda().eval()}

    failed = {(s, b): m for s, b, m in FAILED_RUNS}
    rows, scores = [], {}
    for s in (1, 2, 3):
        feats = load_features(s)
        files = list(dict.fromkeys(feats.sort_values("timestamp")["file"]))   # live snapshots, time order
        n = n_healthy(len(files))
        times = pd.to_datetime(feats.drop_duplicates("file").set_index("file").loc[files, "timestamp"])
        left = ((times.iloc[-1] - times).dt.total_seconds() / 3600).to_numpy()
        bearing_of = np.array([b for b, _ in SETS[s]["channels"]])
        alarms = {}
        for kind, model in models.items():
            cache = OUT_DIR / f"fm_{kind}_emb_set{s}.npy"
            if cache.exists():
                E = np.load(cache)
            else:
                E = embed_set(s, files, kind, model, n)
                np.save(cache, E)
            err = pd.DataFrame(knn_score(E, bearing_of, n), index=times.values)
            scores[kind, s] = (err, n, left)
            _, alarms[kind] = score_alarms(err, n)
        for b in sorted(set(bearing_of)):
            row = {"set": s, "bearing": b, "truth": failed.get((s, b), "healthy")}
            for kind in models:
                a = alarms[kind][b]
                row[f"{kind}_alarm_h"] = round(left[a], 1) if a is not None else np.nan
            rows.append(row)
            print(row)
    pd.DataFrame(rows).to_csv(OUT_DIR / "fm_summary.csv", index=False)

    # Threshold sensitivity: the grid used for the AI alarm (maintenance_checks.py), lead 24 h, breakdown 10x
    sweep = []
    for k in (6, 8, 10):
        for floor in (0.4, 0.5, 0.6):
            for kind in models:
                res = []
                for s in (1, 2, 3):
                    err, n, left = scores[kind, s]
                    _, al = score_alarms(err, n, floor=floor, k_sigma=k)
                    res += [(TEST_END_H[s], (s, b) in failed, left[a] if a is not None else np.nan)
                            for b, a in al.items()]
                sweep.append({"model": kind, "k_sigma": k, "floor": floor,
                              "caught": sum(f and w >= 24 for _, f, w in res),
                              "false_alarms": sum(not f and not np.isnan(w) for _, f, w in res),
                              "cost_per_1000h": round(rate([outcome(e, f, w, 24, 10) for e, f, w in res]), 2)})
    sweep = pd.DataFrame(sweep)
    sweep.to_csv(OUT_DIR / "fm_threshold_sweep.csv", index=False)
    print(sweep.groupby("model")[["caught", "false_alarms", "cost_per_1000h"]].agg(["min", "max"]))


if __name__ == "__main__":
    main()
