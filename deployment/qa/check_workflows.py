"""Validate the 19 delivered workflows against the CURRENT node schema.

Every widget of every node is checked against the plugin's own
define_schema(): COMBO membership, STRING/INT/FLOAT/BOOLEAN type, and
min/max range. The widget slot order is the one ComfyUI's frontend uses -
required widget inputs (schema order) first, then optional ones - which is
what widgets_values stores.

Usage:
    python deployment/qa/check_workflows.py
"""
from __future__ import annotations

import json
import os
import sys

COMFY = os.environ.get("DRAMA3_COMFY_ROOT",
                       r"G:\Comfy-Desktop\ComfyUI-Installs\ComfyUI\ComfyUI")
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
                 "default": getattr(inp, "default", None),
                 "min": getattr(inp, "min", None), "max": getattr(inp, "max", None)}
        (opt if inp.optional else req).append(entry)
    SLOTS[cls.__name__] = req + opt

problems = []
checked = 0
files = 0

for fname in sorted(os.listdir(WF_DIR)):
    if not fname.endswith(".json"):
        continue
    files += 1
    wf = json.load(open(os.path.join(WF_DIR, fname), encoding="utf-8"))
    for node in wf.get("nodes", []):
        ntype = node.get("type", "")
        if ntype not in SLOTS:
            if ntype.startswith("T8Drama"):
                problems.append((fname, ntype, "-", "NODE NOT FOUND"))
            continue
        slots = SLOTS[ntype]
        values = node.get("widgets_values") or []
        if len(values) != len(slots):
            problems.append((fname, ntype, "-",
                             f"widget count {len(values)} != schema slots {len(slots)}"))
        for i, slot in enumerate(slots):
            if i >= len(values):
                problems.append((fname, ntype, slot["name"], "MISSING VALUE"))
                continue
            val = values[i]
            checked += 1
            t = slot["type"]
            if t == "COMBO":
                opts = slot["options"] or []
                # An empty option list means the combo is filled at runtime
                # (e.g. existing session files); any string is then legal.
                if opts and val not in opts:
                    problems.append((fname, ntype, slot["name"], f"not an option: {val!r}"))
                elif not opts and not isinstance(val, str):
                    problems.append((fname, ntype, slot["name"], f"not a string: {val!r}"))
            elif t == "STRING":
                if not isinstance(val, str):
                    problems.append((fname, ntype, slot["name"], f"not a string: {val!r}"))
            elif t == "BOOLEAN":
                if not isinstance(val, bool):
                    problems.append((fname, ntype, slot["name"], f"not a bool: {val!r}"))
            elif t == "INT":
                if isinstance(val, bool) or not isinstance(val, int):
                    problems.append((fname, ntype, slot["name"], f"not an int: {val!r}"))
                else:
                    if slot["min"] is not None and val < slot["min"]:
                        problems.append((fname, ntype, slot["name"], f"{val} < min {slot['min']}"))
                    if slot["max"] is not None and val > slot["max"]:
                        problems.append((fname, ntype, slot["name"], f"{val} > max {slot['max']}"))
            elif t == "FLOAT":
                if isinstance(val, bool) or not isinstance(val, (int, float)):
                    problems.append((fname, ntype, slot["name"], f"not a float: {val!r}"))
                else:
                    if slot["min"] is not None and val < slot["min"]:
                        problems.append((fname, ntype, slot["name"], f"{val} < min {slot['min']}"))
                    if slot["max"] is not None and val > slot["max"]:
                        problems.append((fname, ntype, slot["name"], f"{val} > max {slot['max']}"))

print(f"workflow files: {files}")
print(f"widget values checked: {checked}")
if problems:
    print(f"PROBLEMS: {len(problems)}")
    for f, t, w, v in problems:
        print(f"  {f:<36} {t:<28} {w:<20} {v}")
    sys.exit(1)
print("PROBLEMS: 0 - all workflows match the current schema")
