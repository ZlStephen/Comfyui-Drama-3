"""Run a delivered UI workflow file against the live ComfyUI.

ComfyUI's API takes a prompt graph whose inputs are NAMED, while the UI
workflow file stores widget values POSITIONALLY. This converts one into the
other using the plugin's own schema for the widget order, then submits and
polls - so the delivered workflow file is exercised exactly as the user will
load it, not a hand-built prompt that merely resembles it.

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

COMFY = os.environ.get("DRAMA3_COMFY_ROOT",
                       r"G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI")
API = os.environ.get("DRAMA3_API", "http://127.0.0.1:8188")
PLUGIN = os.path.join(COMFY, "custom_nodes", "Comfyui-Drama-3")
WF_DIR = os.path.join(PLUGIN, "deployment", "workflows")

os.chdir(COMFY)
sys.path.insert(0, COMFY)
sys.path.insert(0, PLUGIN)

import utils.extra_config  # noqa: E402

cfg = os.path.join(COMFY, "extra_model_paths.yaml")
if os.path.isfile(cfg):
    utils.extra_config.load_extra_path_config(cfg)

WIDGET_TYPES = {"COMBO", "STRING", "INT", "FLOAT", "BOOLEAN"}

import drama3_t8.nodes as nodes_mod  # noqa: E402
from drama3_t8.creative_nodes import get_creative_nodes  # noqa: E402

classes = [getattr(nodes_mod, n) for n in dir(nodes_mod)
           if isinstance(getattr(nodes_mod, n), type) and n.startswith("T8Drama")]
classes += list(get_creative_nodes(nodes_mod.EngineType,
                                   getattr(nodes_mod, "ReferencesType", None),
                                   nodes_mod.SessionType))

SLOTS = {}
for cls in classes:
    try:
        schema = cls.define_schema()
    except Exception:  # noqa: BLE001
        continue
    req, opt = [], []
    for inp in getattr(schema, "inputs", []) or []:
        if inp.io_type not in WIDGET_TYPES:
            continue
        (opt if inp.optional else req).append(inp.id)
    SLOTS[cls.__name__] = req + opt


def to_api(wf: dict) -> dict:
    # Frontend-only nodes (Note, group boxes) have no backend implementation;
    # the ComfyUI frontend drops them on API export too.
    with urllib.request.urlopen(f"{API}/object_info", timeout=900) as r:
        live = json.loads(r.read().decode())
    link_src = {link[0]: (link[1], link[2]) for link in wf.get("links", []) or []}
    prompt = {}
    dropped = []
    for node in wf.get("nodes", []):
        ntype = node.get("type", "")
        if ntype not in live:
            dropped.append(f"{node['id']}:{ntype}")
            continue
        api_in = {}
        values = node.get("widgets_values") or []
        for idx, wname in enumerate(SLOTS.get(ntype, [])):
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


def run(wf_name: str, overrides=None, poll_s: int = 1800):
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
            for m in e.get("status", {}).get("messages", []):
                v = m[1] if isinstance(m, (list, tuple)) and len(m) > 1 else None
                if isinstance(v, dict) and v.get("type") == "execution_error":
                    print("   ERROR:", v.get("exception_type"), v.get("exception_message"))
            for node_id, val in e.get("outputs", {}).items():
                t = val.get("text")
                if isinstance(t, list):
                    txt = "".join(x if isinstance(x, str) else x.get("text", "") for x in t)
                    if txt.strip():
                        print(f"   TEXT[{node_id}]: {txt}")
                for f in val.get("audio", []) or []:
                    print(f"   AUDIO[{node_id}]: {f.get('filename')} sub={f.get('subfolder')}")
            return {"status": st.get("status_str"), "outputs": e.get("outputs", {}),
                    "prompt_id": pid}
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
