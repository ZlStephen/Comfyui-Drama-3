"""TTS -> ASR round trip: transcribe the speech the smoke test just produced.

The strongest available end-to-end proof that the deployment works: the
plugin's own TTS generated the audio and the plugin's own ASR reads it back.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

COMFY = "http://127.0.0.1:8188"
WORKFLOW = r"H:\Object\Comfyui mcp\drama3_roundtrip_api.json"
OUT = r"H:\Object\Comfyui mcp\drama3_roundtrip.json"
LOG = r"H:\Object\Comfyui mcp\_drama3_roundtrip.log"


def log(m: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def get(url, payload=None, timeout=180):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read().decode()
    return json.loads(body) if body.strip() else {}


def main() -> int:
    wf = json.load(open(WORKFLOW, encoding="utf-8"))
    pid = None
    for attempt in range(1, 6):
        try:
            resp = get(f"{COMFY}/prompt", {"prompt": wf, "client_id": "drama3-roundtrip"},
                       timeout=900)
            pid = resp.get("prompt_id")
            if pid:
                log(f"submitted on attempt {attempt}, prompt_id={pid}")
                break
            log(f"attempt {attempt} refused: {json.dumps(resp, ensure_ascii=False)[:900]}")
            json.dump({"status": "submit-failed", "response": resp},
                      open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            return 2
        except Exception as e:  # noqa: BLE001
            log(f"attempt {attempt} failed: {type(e).__name__}: {e}")
            time.sleep(20)
    if not pid:
        log("could not submit after 5 attempts")
        return 2

    t0 = time.time()
    while time.time() - t0 < 1800:
        try:
            hist = get(f"{COMFY}/history/{pid}")
        except Exception:  # noqa: BLE001
            hist = {}
        entry = hist.get(pid)
        if entry:
            st = entry.get("status", {})
            log(f"status={st.get('status_str')}")
            outs = entry.get("outputs", {})
            text = ""
            for node, val in outs.items():
                for t in val.get("text", []) or []:
                    text += t.get("text", "")
            result = {"status": st.get("status_str"), "prompt_id": pid,
                      "outputs": outs, "text": text,
                      "messages": st.get("messages")}
            json.dump(result, open(OUT, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
            log(f"TRANSCRIPT: {text!r}")
            return 0 if st.get("status_str") == "success" else 1
        time.sleep(5)
    log("timed out")
    return 1


if __name__ == "__main__":
    sys.exit(main())
