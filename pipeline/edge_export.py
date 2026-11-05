"""Edge check for the AI alarm: export the 524-parameter autoencoder to ONNX
(float32 and int8), then re-run the full alarm rule with each exported model
and check that every alarm time is unchanged.

Usage:  python pipeline/edge_export.py
Outputs: pipeline/outputs/edge_export.csv  (size, latency, alarm agreement per test)
         pipeline/outputs/ae_set{N}.onnx, ae_set{N}_int8.onnx
         pipeline/outputs/ae_set{N}_norm.json  (feature order, mean and sd of the log features, for edge_benchmark.py)
"""
import json
import time

import numpy as np
import onnxruntime as ort
import pandas as pd
import torch
from onnxruntime.quantization import QuantType, quantize_dynamic

from common import OUT_DIR, load_features
from diagnosis import n_healthy
from dl_diagnosis import AE, AE_FEATURES, ae_detection


def session(path):
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def main():
    rows = []
    for s in (1, 2, 3):
        feats = load_features(s)
        f32, i8 = OUT_DIR / f"ae_set{s}.onnx", OUT_DIR / f"ae_set{s}_int8.onnx"
        sess = {}

        def run(model, v, kind):
            if not sess:  # first call: export the trained model, quantize, open both
                model.eval()
                torch.onnx.export(model, torch.zeros(1, len(AE_FEATURES)), f32, input_names=["x"],
                                  output_names=["y"], dynamic_axes={"x": {0: "n"}, "y": {0: "n"}},
                                  dynamo=False)
                quantize_dynamic(f32, i8, weight_type=QuantType.QInt8)
                sess["f32"], sess["int8"] = session(f32), session(i8)
            return sess[kind].run(None, {"x": v})[0]

        # input scaling, computed exactly as in ae_detection(), saved for the edge device
        x = np.log(feats.pivot_table(index="timestamp", columns="bearing", values=AE_FEATURES, aggfunc="mean"))
        n = n_healthy(len(x))
        tr = np.concatenate([x.xs(b, axis=1, level="bearing")[AE_FEATURES].iloc[:n].to_numpy()
                             for b in sorted(feats["bearing"].unique())])
        (OUT_DIR / f"ae_set{s}_norm.json").write_text(json.dumps(
            {"features": AE_FEATURES, "mean": tr.mean(0).tolist(), "sd": (tr.std(0) + 1e-6).tolist()}))

        _, ref = ae_detection(feats)
        _, a32 = ae_detection(feats, infer=lambda m, v: run(m, v, "f32"))
        _, a8 = ae_detection(feats, infer=lambda m, v: run(m, v, "int8"))

        x1 = np.zeros((1, len(AE_FEATURES)), np.float32)
        lat = {}
        for k in ("f32", "int8"):
            for _ in range(200):
                sess[k].run(None, {"x": x1})
            t = time.perf_counter()
            for _ in range(2000):
                sess[k].run(None, {"x": x1})
            lat[k] = (time.perf_counter() - t) / 2000 * 1e6
        rows.append({"set": s,
                     "params": sum(p.numel() for p in AE().parameters()),
                     "onnx_f32_bytes": f32.stat().st_size, "onnx_int8_bytes": i8.stat().st_size,
                     "latency_f32_us": round(lat["f32"], 1), "latency_int8_us": round(lat["int8"], 1),
                     "alarms_same_f32": a32 == ref, "alarms_same_int8": a8 == ref,
                     "n_alarms": sum(v is not None for v in ref.values())})
        print(rows[-1])
    out = pd.DataFrame(rows)
    out.to_csv(OUT_DIR / "edge_export.csv", index=False)
    assert out["alarms_same_f32"].all(), "float32 ONNX must reproduce the PyTorch alarms exactly"


if __name__ == "__main__":
    main()
