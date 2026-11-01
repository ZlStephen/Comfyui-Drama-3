"""Rebuild the adapted workflows against the CURRENT node schema.

The upstream repo ships workflows whose widget VALUES were authored for an
older node layout. T8DramaGenerate, for example, lost one widget in the
middle and gained one at the end, so every value after the loss sits one slot
off - and upstream's own workflows/workflow_basic.json fails ComfyUI's own
validation against its own v0.3.2 code.

The shift is NOT uniform (a widget was removed in the middle), so this uses a
sequence alignment, not an offset:

  - slots  = current schema's widget slots, required (schema order) then
             optional (schema order) - the order ComfyUI's frontend uses
  - values = the upstream file's stored widgets_values
  - DP aligns them allowing skips on both sides, scoring a COMBO slot only
             when the value is actually one of its options, and scoring a
             primitive slot only on an exact type match
  - a skipped slot falls back to the schema default (always legal); a skipped
             value is reported so nothing disappears silently
"""
from __future__ import annotations

import json
import os
import sys

COMFY = r"G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI"
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
        opts = getattr(inp, "options", None)
        entry = {"name": inp.id, "type": inp.io_type,
                 "options": list(opts) if isinstance(opts, (list, tuple)) and opts else None,
                 "default": getattr(inp, "default", None)}
        (opt if inp.optional else req).append(entry)
    SLOTS[cls.__name__] = req + opt

SKIP = -0.7

# Semantic overrides: slots whose stored value is legal but the WRONG one.
# T8DramaTranscribe.asr_model held the forced-aligner weights; it only worked
# because a non-empty model_path outranks the combo (nodes.py:347-370), and it
# would break the moment a user clears model_path. Type- and option-based
# alignment cannot catch this - the value IS a legal option - so it is stated.
OVERRIDES = {
    ("T8DramaTranscribe", "asr_model"): "qwen3-asr-06b.safetensors",
}


def match_score(slot, value):
    t = slot["type"]
    if t == "COMBO":
        return 4.0 if isinstance(value, str) and value in (slot["options"] or []) else -1.0
    if t == "STRING":
        return 2.0 if isinstance(value, str) else -1.0
    if t == "BOOLEAN":
        return 2.0 if isinstance(value, bool) else -1.0
    if t == "INT":
        return 2.0 if (isinstance(value, int) and not isinstance(value, bool)) else -1.0
    if t == "FLOAT":
        if isinstance(value, bool):
            return -1.0
        return 2.0 if isinstance(value, (int, float)) else -1.0
    return 0.0


def align(slots, values):
    """DP alignment -> list of (slot_index, value_index|None)."""
    n, m = len(slots), len(values)
    neg = -1e9
    dp = [[neg] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            cur = dp[i][j]
            if cur == neg:
                continue
            if i < n and j < m:
                s = match_score(slots[i], values[j])
                if s > -1e8:
                    cand = cur + s
                    if cand > dp[i + 1][j + 1]:
                        dp[i + 1][j + 1] = cand
                        back[i + 1][j + 1] = ("m", i, j)
            if i < n:
                cand = cur + SKIP
                if cand > dp[i + 1][j]:
                    dp[i + 1][j] = cand
                    back[i + 1][j] = ("s", i, j)
            if j < m:
                cand = cur + SKIP
                if cand > dp[i][j + 1]:
                    dp[i][j + 1] = cand
                    back[i][j + 1] = ("v", i, j)
    # walk back
    pairs, i, j = [], n, m
    while i > 0 or j > 0:
        step = back[i][j]
        if step is None:
            break
        kind, pi, pj = step
        if kind == "m":
            pairs.append((pi, pj))
        i, j = pi, pj
    pairs.reverse()
    return pairs


def rebuild(node):
    slots = SLOTS.get(node.get("type", ""))
    if not slots:
        return None
    values = node.get("widgets_values") or []
    if not values:
        return None
    pairs = align(slots, values)
    out = []
    used = set()
    overridden = []
    for i, slot in enumerate(slots):
        hit = next((j for (si, j) in pairs if si == i), None)
        if hit is not None:
            used.add(hit)
            out.append(values[hit])
        else:
            out.append(slot["default"])
    for i, slot in enumerate(slots):
        forced = OVERRIDES.get((node.get("type", ""), slot["name"]))
        if forced is not None and out[i] != forced:
            out[i] = forced
            overridden.append(f"{slot['name']}={forced}")
    dropped = [values[j] for j in range(len(values)) if j not in used]
    node["widgets_values"] = out
    return {"kept": len(used), "slots": len(slots), "dropped": dropped,
            "overridden": overridden,
            "names": [slots[i]["name"] for i, _ in pairs]}


report = {}
for fname in sorted(os.listdir(WF_DIR)):
    if not fname.endswith(".json"):
        continue
    path = os.path.join(WF_DIR, fname)
    wf = json.load(open(path, encoding="utf-8"))
    changes = []
    for node in wf.get("nodes", []):
        res = rebuild(node)
        if res and (res["dropped"] or res.get("overridden")):
            changes.append({"node": node.get("type"), "id": node.get("id"), **res})
    if changes:
        report[fname] = changes
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(wf, fh, ensure_ascii=False, indent=2)

print(f"workflows changed: {len(report)}")
for fname, changes in report.items():
    print(f"\n=== {fname}")
    for c in changes:
        print(f"   {c['node']:<24} id={c['id']:<3} kept={c['kept']}/{c['slots']} "
              f"dropped={c['dropped']} overridden={c.get('overridden')}")
        print(f"      matched: {c['names']}")

out_report = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "workflow_rebuild_report.json")
json.dump(report, open(out_report, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"\nreport -> {out_report}")
