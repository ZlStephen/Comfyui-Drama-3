"""Run a delivered UI workflow file against the live ComfyUI.

ComfyUI's API takes a prompt graph whose inputs are NAMED, while the UI
workflow file stores widget values POSITIONALLY. This converts one into the
other and submits it - so the delivered workflow file is exercised exactly as
the user will load it, not a hand-built prompt that merely resembles it.

Widget slot order, taken from the live /object_info:
    slots = [n for n in (required order + optional order) if n is a widget]
Widget types are COMBO / STRING / INT / FLOAT / BOOLEAN; AUDIO, LATENT, IMAGE,
MASK and the plugin's own socket types are links, not slots. This holds for
core nodes (SaveAudio -> filename_prefix) and for the plugin's v3 nodes alike.

Usage:
    python deployment/qa/run_workflow.py workflow_basic.json
    python deployment/qa/run_workflow.py workflow_asr.json overrides.json
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("DRAMA3_API", "http://127.0.0.1:8188")
COMFY = os.environ.get("DRAMA3_COMFY_ROOT",
                       r"G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI")
PLUGIN = os.path.join(COMFY, "custom_nodes", "Comfyui-Drama-3")
WF_DIR = os.path.join(PLUGIN, "deployment", "workflows")
WIDGET_TYPES = {"COMBO", "STRING", "INT", "FLOAT", "BOOLEAN"}

_slots_cache: dict[str, list[str]] = {}
_live: dict | None = None


def live_info() -> dict:
    global _live
    if _live is None:
        with urllib.request.urlopen(f"{API}/object_info", timeout=900) as r:
            _live = json.loads(r.read().decode())
    return _live


def _named(spec) -> list[tuple[str, str]]:
    """Normalise a node's required/optional spec into [(name, type), ...]."""
    if isinstance(spec, dict):
        out = []
        for name, val in spec.items():
            if isinstance(val, list) and val and isinstance(val[0], str):
                out.append((name, val[0]))
            elif isinstance(val, str):
                out.append((name, val))
            else:
                out.append((name, ""))
        return out
    if isinstance(spec, list):
        out = []
        for item in spec:
            if isinstance(item, (list, tuple)) and item:
                name = item[0]
                t = item[1] if len(item) > 1 and isinstance(item[1], str) else ""
                out.append((name, t))
        return out
    return []


def _forced(spec) -> set[str]:
    """Names declared with force_input=True - those are LINKS, never widgets.

    SaveText's `text` is a STRING input but arrives as a socket; counting it
    as a widget shifts every later widget by one and drops `format` entirely.
    """
    forced: set[str] = set()
    if isinstance(spec, dict):
        items = spec.items()
    elif isinstance(spec, list):
        items = []
        for item in spec:
            if isinstance(item, (list, tuple)) and item:
                items.append((item[0], item[1] if len(item) > 1 else ""))
    else:
        items = []
    for name, val in items:
        if isinstance(val, list) and len(val) > 1 and isinstance(val[1], dict):
            if val[1].get("force_input"):
                forced.add(name)
    return forced


def slots_for(ntype: str) -> list[str]:
    if ntype not in _slots_cache:
        inp = (live_info().get(ntype) or {}).get("input") or {}
        forced: set[str] = set()
        for sect in ("required", "optional"):
            forced |= _forced(inp.get(sect))
        names = []
        for sect in ("required", "optional"):
            for name, t in _named(inp.get(sect)):
                if name in forced:
                    continue
                if t in WIDGET_TYPES:
                    names.append(name)
        _slots_cache[ntype] = names
    return _slots_cache[ntype]


def to_api(wf: dict) -> dict:
    live = live_info()
    link_src = {link[0]: (link[1], link[2]) for link in wf.get("links", []) or []}
    prompt = {}
    dropped = []
    for node in wf.get("nodes", []):
        ntype = node.get("type", "")
        if ntype not in live:
            # Frontend-only nodes (Note, group boxes) have no backend
            # implementation; the ComfyUI frontend drops them on API export too.
            dropped.append(f"{node['id']}:{ntype}")
            continue
        api_in = {}
        values = node.get("widgets_values") or []
        for idx, wname in enumerate(slots_for(ntype)):
            if idx < len(values):
                api_in[wname] = values[idx]
        for inp in node.get("inputs", []) or []:
            lid = inp.get("link")
            if lid is None:
                continue
            origin = link_src.get(lid)
            if origin is not None:
                api_in[inp["name"]] = [str(origin[0]), origin[1]]
        prompt[str(node["id"])] = {"class_type": ntype, "inputs": api_in}
    if dropped:
        print(f"    dropped frontend-only nodes: {', '.join(dropped)}")
    return prompt


def post(url, payload, timeout=900):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode()
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode(errors="replace"), "http_status": e.code}
    return json.loads(body) if body.strip() else {}


def run(wf_name: str, overrides=None, poll_s: int = 3600):
    wf = json.load(open(os.path.join(WF_DIR, wf_name), encoding="utf-8"))
    prompt = to_api(wf)
    for node_id, patch in (overrides or {}).items():
        prompt[node_id]["inputs"].update(patch)
    print(f"--- {wf_name}: {len(prompt)} nodes")
    resp = post(f"{API}/prompt", {"prompt": prompt, "client_id": "drama3-wf-run"})
    if "error" in resp:
        print("   REFUSED:", str(resp["error"])[:1500])
        return {"status": "refused", "response": resp}
    pid = resp["prompt_id"]
    print(f"   prompt_id={pid}")
    t0 = time.time()
    while time.time() - t0 < poll_s:
        with urllib.request.urlopen(f"{API}/history/{pid}", timeout=300) as r:
            hist = json.loads(r.read().decode())
        if pid in hist:
            e = hist[pid]
            st = e.get("status", {})
            print(f"   status={st.get('status_str')}  ({time.time()-t0:.0f}s)")
            errors = []
            for m in e.get("status", {}).get("messages", []):
                v = m[1] if isinstance(m, (list, tuple)) and len(m) > 1 else None
                if isinstance(v, dict) and v.get("type") == "execution_error":
                    print("   ERROR:", v.get("exception_type"), v.get("exception_message"))
                    errors.append({
                        "node": v.get("node_id"),
                        "type": v.get("exception_type"),
                        "message": str(v.get("exception_message"))[:2000],
                        "traceback": str(v.get("traceback"))[-2000:],
                    })
            for node_id, val in e.get("outputs", {}).items():
                t = val.get("text")
                if isinstance(t, list):
                    txt = "".join(x if isinstance(x, str) else x.get("text", "") for x in t)
                    if txt.strip():
                        print(f"   TEXT[{node_id}]: {txt[:300]}")
                for f in val.get("audio", []) or []:
                    print(f"   AUDIO[{node_id}]: {f.get('filename')} sub={f.get('subfolder')}")
                for f in val.get("gifs", []) or []:
                    print(f"   FILE[{node_id}]: {f.get('filename')}")
            return {"status": st.get("status_str"), "outputs": e.get("outputs", {}),
                    "prompt_id": pid, "errors": errors}
        time.sleep(4)
    print("   timed out")
    return {"status": "timeout", "prompt_id": pid}


if __name__ == "__main__":
    name = sys.argv[1]
    over = None
    if len(sys.argv) > 2:
        arg = sys.argv[2]
        over = (json.load(open(arg, encoding="utf-8")) if arg.lower().endswith(".json")
                else json.loads(arg))
    out = run(name, over)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           f"run_{name.replace('.json', '')}.json"), "w",
              encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
