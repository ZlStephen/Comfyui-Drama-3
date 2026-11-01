"""Verify campplus-zh-en.onnx through the plugin's OWN SpeakerEmbedder.

The upstream model-manifest.json does not list this file, so there is no
authoritative sha256 for it. Instead of trusting a hash we cannot source, this
drives the plugin's own class - the same code path T8DramaVoiceLibrary /
T8DramaCreative* uses - on the audio the smoke test just produced.
"""
from __future__ import annotations

import json
import os
import sys

PLUGIN = (r"G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI"
          r"\custom_nodes\Comfyui-Drama-3")
CAMPPLUS = (r"G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI"
             r"\user\drama3_t8\native-host\models\campplus-zh-en.onnx")
AUDIO = r"D:\ComfyUI\output\Drama3_T8\smoke_test_00001.flac"
OUT = r"H:\Object\Comfyui mcp\drama3_campplus_check.json"

sys.path.insert(0, PLUGIN)

result = {"campplus": CAMPPLUS, "audio": AUDIO}

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

wave, sr = sf.read(AUDIO, dtype="float32", always_2d=True)
wave = wave.mean(axis=1)
result["audio"] = {"sample_rate": sr, "samples": int(wave.size),
                    "duration_s": round(wave.size / sr, 2),
                    "peak": float(np.abs(wave).max())}

from drama3_t8.creative_transcript import SpeakerEmbedder  # noqa: E402

embedder = SpeakerEmbedder(CAMPPLUS)
result["plugin_metadata"] = dict(embedder.metadata)
result["plugin_accepted"] = True
result["plugin_sha256_of_file"] = embedder.sha256

vec = embedder.embedding(wave, sr)
result["embedding"] = {
    "dim": int(vec.shape[0]),
    "norm": float(np.linalg.norm(vec)),
    "finite": bool(np.isfinite(vec).all()),
    "max_abs": float(np.abs(vec).max()),
}
result["verdict"] = "pass" if (vec.shape[0] > 0 and np.isfinite(vec).all()
                               and np.linalg.norm(vec) > 1e-8) else "fail"

with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(result, fh, indent=2, ensure_ascii=False)
print(json.dumps(result, indent=2, ensure_ascii=False))
print("VERDICT:", result["verdict"])
sys.exit(0 if result["verdict"] == "pass" else 1)
