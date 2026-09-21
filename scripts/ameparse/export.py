"""Serialization views: compact card (§10.4 tool payload), parameter/variable
CSV tables, raw member export, and one-shot export.

Output structure (``export()``)::

    <out>/
    ├── sources/<model>/                    raw members extracted from the .ame tar
    ├── cards/<model>.full.json             full card (Model.to_dict())
    ├── cards/<model>.compact.json          compact card (§10.4 tool payload)
    └── csv/<model>.params.csv              flat tables (utf-8-sig, Excel-friendly)
        csv/<model>.variables.csv

Custom reports (Markdown etc.) are intentionally not part of the package:
build them from the query API (see references/API.md).
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .archive import Amefile

# Exported source members (text-like; .results/.mexw64/.obj etc. are skipped)
KEEP_SUFFIXES = (
    ".cir", ".param", ".var", ".ssf", ".modelinfo", ".amegp", ".sim",
    ".studyparam", ".units", ".sad", ".views", ".data", ".state",
)


# ---------------------------------------------------------------- compact card


def compact_card(model) -> dict:
    """Compact model card aligned with the §10.4 schema (tool payload)."""
    components = []
    for c in model.components():
        components.append(
            {
                "alias": c.alias,
                "submodel": c.submodel.name if c.submodel else None,
                "instance": c.submodel.instance if c.submodel else None,
                "library": c.library_id,
                "path": c.path_str,
                "ports": [{"index": p.index, "type": p.type} for p in c.ports],
                "params": [
                    {
                        "id": p.id,
                        "value": p.value_view,
                        "unit": p.units,
                        "default": p.default_view,
                        "min": p.min,
                        "max": p.max,
                    }
                    for p in c.params
                ],
                "variables": [
                    {"id": v.id, "unit": v.units, "saved": v.saved}
                    for v in c.variables
                ],
            }
        )
    saved = [v.data_path for v in model.saved_variables]
    card = {
        "model": model.name,
        "ame_version": model.ame_version,
        "simulation": {
            "final_time": model.simulation.final_time,
            "print_interval": model.simulation.print_interval,
        },
        "states": model.model_info.states,
        "counts": {
            "components": len(components),
            "params": sum(len(c["params"]) for c in components),
            "variables": sum(len(c["variables"]) for c in components),
            "saved_variables": len(saved),
        },
        "components": components,
        "supercomponents": [
            {"name": s.name, "path": s.path} for s in model.circuit.supercomponents
        ],
        "observable_variables": saved,
        "notes": model.to_dict()["notes"],
    }
    g = model.graph
    if g is not None:
        gd = g.to_dict()
        card["edges"] = gd["edges"]
        card["neighbors"] = gd["neighbors"]
        card["counts"]["edges"] = len(gd["edges"])
    return card


# ---------------------------------------------------------------- CSV tables


def write_param_csv(model, path) -> int:
    n = 0
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["model", "alias", "path", "submodel", "instance",
                    "param_id", "name", "title", "type", "value", "unit",
                    "default", "min", "max", "id"])
        for c in model.components():
            for p in c.params:
                w.writerow([model.name, c.alias, c.path_str,
                            c.submodel.name if c.submodel else None,
                            c.submodel.instance if c.submodel else None,
                            p.declaration.param_id if p.declaration else "",
                            p.varname, p.title, p.kind, p.value_view,
                            p.units, p.default_view, p.min, p.max, p.id])
                n += 1
    return n


def write_var_csv(model, path) -> int:
    hidden_paths = model.declarations.hidden_paths
    n = 0
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["model", "alias", "path", "submodel", "instance",
                    "name", "title", "unit", "kind", "hidden", "saved", "id"])
        for c in model.components():
            for v in c.variables:
                w.writerow([model.name, c.alias, c.path_str,
                            c.submodel.name if c.submodel else None,
                            c.submodel.instance if c.submodel else None,
                            v.varname, v.title, v.units, v.kind,
                            v.id in hidden_paths, v.save_value, v.id])
                n += 1
    return n


# ---------------------------------------------------------------- raw members


def export_sources(ame_path, dest) -> list:
    """Extract raw members: top-level ``<model>_.<ext>`` files plus
    ``.props/properties.xml``; skips bulky/compiled members and the
    ``pltth`` / ``tools`` directories."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    written = []
    with Amefile(str(ame_path)) as ame:
        for m in ame.members():
            if not m.is_file:
                continue
            rel = m.name.split("_.", 1)[-1] if "_." in m.name else m.name
            if rel != m.name and rel.split("/")[0] in (
                "pltth", "tools", "props"
            ) and rel != "props/properties.xml":
                continue
            if not m.name.lower().endswith(KEEP_SUFFIXES):
                continue
            data = ame.read_exact(m.name)
            if data is None:
                continue
            out = dest / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(data)
            written.append(str(out.relative_to(dest.parent)))
    return written


# ---------------------------------------------------------------- one-shot


def export(model, out_dir, *, sources=True, full_card=True, compact=True,
           csv=True) -> dict:
    """Export one model into ``sources/`` + ``cards/`` + ``csv/``;
    returns {kind: path or list}."""
    out = Path(out_dir)
    written: dict = {}

    if sources and model.source_path is not None:
        written["sources"] = export_sources(
            model.source_path, out / "sources" / model.name)

    if full_card:
        p = out / "cards" / f"{model.name}.full.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(model.to_dict(), ensure_ascii=False, indent=1),
                     encoding="utf-8")
        written["full_card"] = p

    if compact:
        p = out / "cards" / f"{model.name}.compact.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(compact_card(model), ensure_ascii=False, indent=1),
                     encoding="utf-8")
        written["compact_card"] = p

    if csv:
        p = out / "csv" / f"{model.name}.params.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        write_param_csv(model, p)
        v = out / "csv" / f"{model.name}.variables.csv"
        v.parent.mkdir(parents=True, exist_ok=True)
        write_var_csv(model, v)
        written["params_csv"] = p
        written["variables_csv"] = v

    return written
