"""Verify the Drama-3 weights on disk against the upstream model-manifest.json.

The tree API's lfs.sha256 does NOT match the bytes on disk (measured); the
upstream model-manifest.json does. This uses the manifest as the authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

WORKSPACE = r"H:\Object\Comfyui mcp"
UPSTREAM_MANIFEST = os.path.join(WORKSPACE, "drama3_upstream_model_manifest.json")
OUT_MANIFEST = os.path.join(WORKSPACE, "drama3_model_manifest.json")

COMFY = r"G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI"
MODELS_J = r"J:\ComfyUI-Shared\models"
MODELS_G = r"G:\Comfy-Desktop\ComfyUI-Shared\models"

# repo path -> local absolute path. Where a file must exist in two places the
# list carries both; the second is a hardlink of the first.
LAYOUT = {
    "drama3-t8-fp8.safetensors": [
        rf"{MODELS_J}\diffusion_models\drama3-t8-fp8.safetensors"],
    "drama3-text-head.safetensors": [
        rf"{MODELS_J}\diffusion_models\drama3-text-head.safetensors"],
    "drama3-line-head.safetensors": [
        rf"{MODELS_J}\diffusion_models\drama3-line-head.safetensors"],
    "qwen3-asr-06b.safetensors": [
        rf"{MODELS_J}\asr\qwen3-asr-06b.safetensors",
        rf"{MODELS_J}\diffusion_models\qwen3-asr-06b.safetensors"],
    "drama3-codec.safetensors": [
        rf"{MODELS_J}\vae\drama3-codec.safetensors"],
    "qwen-aligner/config.json": [
        rf"{COMFY}\models\asr\qwen-aligner\config.json"],
    "qwen-aligner/chat_template.json": [
        rf"{COMFY}\models\asr\qwen-aligner\chat_template.json"],
    "qwen-aligner/generation_config.json": [
        rf"{COMFY}\models\asr\qwen-aligner\generation_config.json"],
    "qwen-aligner/merges.txt": [
        rf"{COMFY}\models\asr\qwen-aligner\merges.txt"],
    "qwen-aligner/model.safetensors": [
        rf"{COMFY}\models\asr\qwen-aligner\model.safetensors"],
    "qwen-aligner/preprocessor_config.json": [
        rf"{COMFY}\models\asr\qwen-aligner\preprocessor_config.json"],
    "qwen-aligner/tokenizer_config.json": [
        rf"{COMFY}\models\asr\qwen-aligner\tokenizer_config.json"],
    "qwen-aligner/vocab.json": [
        rf"{COMFY}\models\asr\qwen-aligner\vocab.json"],
    "Confucius4-R2T2-GGUF/Confucius4-R2T2-Q8_0.gguf": [
        rf"{COMFY}\models\asr\Confucius4-R2T2-GGUF\Confucius4-R2T2-Q8_0.gguf"],
    "Confucius4-R2T2-GGUF/mmproj-Confucius4-R2T2-Q8_0.gguf": [
        rf"{COMFY}\models\asr\Confucius4-R2T2-GGUF\mmproj-Confucius4-R2T2-Q8_0.gguf"],
    "FireRedVAD-ONNX/fireredvad_stream_vad_with_cache.onnx": [
        rf"{COMFY}\models\asr\FireRedVAD-ONNX\fireredvad_stream_vad_with_cache.onnx"],
    "FireRedVAD-ONNX/cmvn.ark": [
        rf"{COMFY}\models\asr\FireRedVAD-ONNX\cmvn.ark"],
    "campplus-zh-en.onnx": [
        rf"{COMFY}\user\drama3_t8\native-host\models\campplus-zh-en.onnx"],
}

# Small companion files the manifest lists without a sha256.
NO_HASH_OK = True


def sha256(path: str, chunk: int = 8 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main() -> int:
    manifest = json.load(open(UPSTREAM_MANIFEST, encoding="utf-8"))
    entries = {f["path"]: f for f in manifest["files"]}

    rows = []
    ok = miss = bad = 0
    for repo_path, targets in LAYOUT.items():
        entry = entries.get(repo_path)
        expect_bytes = entry["bytes"] if entry else None
        expect_sha = entry.get("sha256") if entry else None
        for t in targets:
            row = {
                "repo_path": repo_path,
                "local_path": t,
                "expected_bytes": expect_bytes,
                "expected_sha256": expect_sha,
            }
            if not os.path.exists(t):
                row.update(status="missing", actual_bytes=None, actual_sha256=None)
                miss += 1
            else:
                size = os.path.getsize(t)
                row["actual_bytes"] = size
                if expect_bytes is not None and size != expect_bytes:
                    row["status"] = "size-mismatch"
                    bad += 1
                elif expect_sha:
                    t0 = time.time()
                    got = sha256(t)
                    row["actual_sha256"] = got
                    row["hash_seconds"] = round(time.time() - t0, 1)
                    if got == expect_sha:
                        row["status"] = "ok"
                        ok += 1
                    else:
                        row["status"] = "sha256-mismatch"
                        bad += 1
                else:
                    row["status"] = "ok-no-hash"
                    ok += 1
            rows.append(row)
            flag = {"ok": "OK  ", "ok-no-hash": "OK* ", "missing": "MISS",
                    "size-mismatch": "SIZE", "sha256-mismatch": "SHA "}.get(row["status"], "??  ")
            print(f"  [{flag}] {repo_path:52s} -> {os.path.basename(t):48s}")

    out = {
        "source": "t8star/Drama-3-Comfy model-manifest.json (upstream authority)",
        "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "totals": {"ok": ok, "missing": miss, "bad": bad},
        "files": rows,
    }
    with open(OUT_MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    print(f"\nok={ok} missing={miss} bad={bad} -> {OUT_MANIFEST}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
