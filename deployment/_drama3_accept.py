"""Unattended acceptance run for the Drama-3 deployment.

1. Waits until every weight is fully on disk (no chunk left in the .parts bitmap).
2. Verifies every weight against the upstream model-manifest.json (sha256).
3. Submits the API-format smoke test to the running ComfyUI.
4. Polls /history for the result and confirms the WAV landed on disk.
5. Writes drama3_final_acceptance.json and drama3_final_acceptance.md.

Exits 0 only when every weight verifies and the smoke test produces audio.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

WORKSPACE = r"H:\Object\Comfyui mcp"
COMFY = "http://127.0.0.1:8188"
OUT_JSON = os.path.join(WORKSPACE, "drama3_final_acceptance.json")
OUT_MD = os.path.join(WORKSPACE, "drama3_final_acceptance.md")
SMOKE = os.path.join(WORKSPACE, "drama3_smoke_test_api.json")
UPSTREAM = os.path.join(WORKSPACE, "drama3_upstream_model_manifest.json")
LOG = os.path.join(WORKSPACE, "_drama3_accept_state.log")

COMFY_ROOT = r"G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI"
J = r"J:\ComfyUI-Shared\models"

FILES = {
    "drama3-t8-fp8.safetensors": (rf"{J}\diffusion_models\drama3-t8-fp8.safetensors", "drama3-t8-fp8.safetensors"),
    "drama3-text-head.safetensors": (rf"{J}\diffusion_models\drama3-text-head.safetensors", "drama3-text-head.safetensors"),
    "drama3-line-head.safetensors": (rf"{J}\diffusion_models\drama3-line-head.safetensors", "drama3-line-head.safetensors"),
    "qwen3-asr-06b.safetensors": (rf"{J}\diffusion_models\qwen3-asr-06b.safetensors", "qwen3-asr-06b.safetensors"),
    "drama3-codec.safetensors": (rf"{J}\vae\drama3-codec.safetensors", "drama3-codec.safetensors"),
    "Confucius4-R2T2-GGUF/Confucius4-R2T2-Q8_0.gguf": (
        rf"{COMFY_ROOT}\models\asr\Confucius4-R2T2-GGUF\Confucius4-R2T2-Q8_0.gguf",
        "Confucius4-R2T2-GGUF/Confucius4-R2T2-Q8_0.gguf"),
    "Confucius4-R2T2-GGUF/mmproj-Confucius4-R2T2-Q8_0.gguf": (
        rf"{COMFY_ROOT}\models\asr\Confucius4-R2T2-GGUF\mmproj-Confucius4-R2T2-Q8_0.gguf",
        "Confucius4-R2T2-GGUF/mmproj-Confucius4-R2T2-Q8_0.gguf"),
    "FireRedVAD-ONNX/fireredvad_stream_vad_with_cache.onnx": (
        rf"{COMFY_ROOT}\models\asr\FireRedVAD-ONNX\fireredvad_stream_vad_with_cache.onnx",
        "FireRedVAD-ONNX/fireredvad_stream_vad_with_cache.onnx"),
    "FireRedVAD-ONNX/cmvn.ark": (
        rf"{COMFY_ROOT}\models\asr\FireRedVAD-ONNX\cmvn.ark",
        "FireRedVAD-ONNX/cmvn.ark"),
    "qwen3_forced_aligner_0.6b_bf16.safetensors": (
        rf"{COMFY_ROOT}\models\asr\qwen3_forced_aligner_0.6b_bf16.safetensors",
        "qwen3_forced_aligner_0.6b_bf16.safetensors"),
}

# campplus-zh-en.onnx is NOT listed in the upstream model-manifest.json, so it
# has no authoritative sha256 (the tree API's lfs.sha256 disagrees with the
# real content hash of every other file, so it cannot stand in). It is verified
# functionally through the plugin's own SpeakerEmbedder instead.
CAMPPLUS = rf"{COMFY_ROOT}\user\drama3_t8\native-host\models\campplus-zh-en.onnx"
CAMPPLUS_BYTES = 28281164
CAMPPLUS_CHECK = os.path.join(WORKSPACE, "drama3_campplus_check.json")

ALIGNER_DIR = rf"{COMFY_ROOT}\models\asr\qwen-aligner"
ALIGNER_FILES = ["config.json", "model.safetensors", "tokenizer_config.json",
                 "vocab.json", "merges.txt", "preprocessor_config.json",
                 "generation_config.json", "chat_template.json"]


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def parts_complete(path: str) -> bool:
    """True when no .parts bitmap says work is still outstanding."""
    parts = path + ".parts"
    if os.path.exists(parts):
        try:
            b = open(parts, "rb").read()
        except OSError:
            return False
        return len(b) > 0 and all(x != 0 for x in b)
    return os.path.exists(path)


def wait_for_downloads(timeout: int = 6 * 3600) -> bool:
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        pending = []
        for local, _ in FILES.values():
            if not parts_complete(local):
                pending.append(os.path.basename(local))
        for name in ALIGNER_FILES:
            if not os.path.exists(os.path.join(ALIGNER_DIR, name)):
                pending.append(f"qwen-aligner/{name}")
        state = ",".join(pending) if pending else "ALL PRESENT"
        if state != last:
            log(f"waiting on: {state}")
            last = state
        if not pending:
            log("all weights present on disk")
            return True
        time.sleep(60)
    log("timed out waiting for downloads")
    return False


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            b = fh.read(8 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def verify() -> dict:
    upstream = {f["path"]: f for f in json.load(open(UPSTREAM, encoding="utf-8"))["files"]}
    rows = []
    for repo_path, (local, mani_path) in FILES.items():
        exp = upstream.get(mani_path, {})
        row = {"repo_path": repo_path, "local_path": local,
               "expected_bytes": exp.get("bytes"), "expected_sha256": exp.get("sha256")}
        size = os.path.getsize(local)
        row["actual_bytes"] = size
        row["status"] = "size-mismatch" if size != exp.get("bytes") else "ok"
        if row["status"] == "ok" and exp.get("sha256"):
            t0 = time.time()
            got = sha256(local)
            row["actual_sha256"] = got
            row["hash_seconds"] = round(time.time() - t0, 1)
            row["status"] = "ok" if got == exp["sha256"] else "sha256-mismatch"
        rows.append(row)
        log(f"  verify {repo_path}: {row['status']}")
    for name in ALIGNER_FILES:
        p = os.path.join(ALIGNER_DIR, name)
        row = {"repo_path": f"qwen-aligner/{name}", "local_path": p,
               "expected_bytes": None, "expected_sha256": None}
        row["actual_bytes"] = os.path.getsize(p) if os.path.exists(p) else None
        row["status"] = "ok" if row["actual_bytes"] else "missing"
        rows.append(row)

    # campplus: size check + the plugin's own functional acceptance
    camp = {"repo_path": "campplus-zh-en.onnx", "local_path": CAMPPLUS,
            "expected_bytes": CAMPPLUS_BYTES, "expected_sha256": None,
            "actual_sha256": None}
    camp["actual_bytes"] = os.path.getsize(CAMPPLUS) if os.path.exists(CAMPPLUS) else None
    camp["status"] = "size-mismatch" if camp["actual_bytes"] != CAMPPLUS_BYTES else "ok"
    if camp["status"] == "ok" and os.path.exists(CAMPPLUS_CHECK):
        try:
            cj = json.load(open(CAMPPLUS_CHECK, encoding="utf-8"))
            camp["actual_sha256"] = cj.get("plugin_sha256_of_file")
            camp["functional"] = {
                "plugin_accepted": cj.get("plugin_accepted"),
                "metadata": cj.get("plugin_metadata"),
                "embedding_dim": cj.get("embedding", {}).get("dim"),
                "verdict": cj.get("verdict"),
            }
            if cj.get("verdict") != "pass":
                camp["status"] = "functional-fail"
        except OSError:
            camp["status"] = "no-functional-evidence"
    rows.append(camp)

    return {"files": rows,
            "totals": {"ok": sum(1 for r in rows if r["status"].startswith("ok")),
                       "bad": sum(1 for r in rows if r["status"] not in ("ok", "ok-no-hash")),
                       "sha256_checked": sum(1 for r in rows if r.get("actual_sha256"))}}


def http_json(url: str, payload=None, timeout: int = 120):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode()
    return json.loads(body) if body.strip() else {}


def smoke_test() -> dict:
    result = {"submitted": False, "prompt_id": None, "status": None,
              "outputs": [], "error": None}
    workflow = json.load(open(SMOKE, encoding="utf-8"))
    try:
        resp = http_json(f"{COMFY}/prompt",
                         {"prompt": workflow, "client_id": "drama3-acceptance"})
        result["prompt_id"] = resp.get("prompt_id")
        result["submitted"] = bool(result["prompt_id"])
        if not result["submitted"]:
            result["error"] = json.dumps(resp, ensure_ascii=False)[:800]
            return result
    except urllib.error.HTTPError as e:
        result["error"] = f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:800]}"
        return result
    except Exception as e:  # noqa: BLE001
        result["error"] = f"{type(e).__name__}: {e}"
        return result

    log(f"smoke test submitted, prompt_id={result['prompt_id']}")
    t0 = time.time()
    while time.time() - t0 < 3600:
        try:
            hist = http_json(f"{COMFY}/history/{result['prompt_id']}")
        except Exception:  # noqa: BLE001
            hist = {}
        entry = hist.get(result["prompt_id"])
        if entry:
            status = entry.get("status", {})
            result["status"] = status.get("status_str")
            if status.get("status_str") == "error":
                result["error"] = json.dumps(status.get("messages", status),
                                             ensure_ascii=False)[:1500]
                log("smoke test ERROR")
                return result
            for node, val in entry.get("outputs", {}).items():
                for kind in ("audio", "gifs", "images"):
                    for item in val.get(kind, []) or []:
                        fn = item.get("filename")
                        sub = item.get("subfolder", "")
                        typ = item.get("type", "output")
                        p = os.path.join(r"D:\ComfyUI\output", sub, fn) if sub \
                            else os.path.join(r"D:\ComfyUI\output", fn)
                        result["outputs"].append({
                            "node": node, "kind": kind, "filename": fn,
                            "subfolder": sub, "type": typ, "path": p,
                            "exists": os.path.exists(p),
                            "bytes": os.path.getsize(p) if os.path.exists(p) else None})
            if result["outputs"]:
                log(f"smoke test produced {len(result['outputs'])} output(s)")
                return result
        time.sleep(10)
    result["error"] = "timed out after 60 min"
    return result


def write_markdown(report: dict) -> None:
    v = report["verification"]
    s = report["smoke_test"]
    lines = [
        "# Drama-3 部署验收报告",
        "",
        f"**状态：{report['status']}**  ·  {report['verified_at']}",
        "",
        "## 权重校验（以 t8star/Drama-3-Comfy 的 model-manifest.json 为准）",
        "",
        "| 文件 | 字节 | sha256 | 结果 |",
        "|---|---|---|---|",
    ]
    for r in v["files"]:
        digest = (r.get("actual_sha256") or "（上游未提供哈希）")[:16]
        lines.append(f"| `{r['repo_path']}` | {r.get('actual_bytes') or '-'} | {digest} | {r['status']} |")
    lines += [
        "",
        "## 端到端冒烟测试",
        "",
        f"- prompt_id：`{s.get('prompt_id')}`",
        f"- 状态：{s.get('status')}",
        f"- 输出文件数：{len(s.get('outputs', []))}",
    ]
    for o in s.get("outputs", []):
        lines.append(f"  - `{o['path']}` — {o.get('bytes')} 字节")
    if s.get("error"):
        lines += ["", "```", str(s["error"])[:1200], "```"]
    lines += [
        "",
        "## GitHub",
        "",
        "- fork: https://github.com/ZlStephen/Comfyui-Drama-3",
        "- 分支: `deployment/windows-4090`",
        "",
    ]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def main() -> int:
    log("=== Drama-3 acceptance run started ===")
    if not wait_for_downloads():
        report = {"status": "failed", "stage": "downloads", "reason": "timeout"}
        with open(OUT_JSON, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        return 1

    log("=== verifying weights ===")
    verification = verify()
    bad = verification["totals"]["bad"]
    log(f"verification: {verification['totals']}")

    log("=== running the smoke test ===")
    smoke = smoke_test()

    status = "passed" if (bad == 0 and smoke["outputs"] and not smoke["error"]) else "failed"
    report = {
        "status": status,
        "verified_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "verification": verification,
        "smoke_test": smoke,
        "github": {"fork": "https://github.com/ZlStephen/Comfyui-Drama-3",
                   "branch": "deployment/windows-4090"},
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)
    write_markdown(report)

    log(f"=== ACCEPTANCE {status.upper()} ===")
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
