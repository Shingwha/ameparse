"""Command line entry.

Agent-friendly query flow (drill down, keep each command's stdout small)::

    ameparse model.ame --settings                    # version / sim options / io
    ameparse model.ame --components --submodel ESSBATPA01
    ameparse model.ame --subgraph BatPackGene --hops 2   # local graph (nodes+edges)
    ameparse model.ame --neighbors BatPackGene
    ameparse model.ame --params --component BatPackGene --modified-only
    ameparse model.ame --param Uinit@BatPackGene
    ameparse model.ame --variable q1@pump01
    ameparse model.ame --variables --component BatPackGene --saved
    ameparse model.ame --search temperature
    ameparse model.ame --study-params
    ameparse model.ame --component BatPackGene --no-variables
    ameparse model.ame --summary / --saved-variables / --csv OUT_DIR
    ameparse model.ame -o card.json                 # full card (never cat to context)
    ameparse export --resources DIR --out DIR       # batch: sources/ cards/ csv/

Guardrails: list commands (--components/--params/--variables) refuse to run
without a narrowing filter unless --all is given — full listings can be
thousands of rows and must not end up in an agent's context.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .core import Model

# 局部图节点数上限（超过提示减小 hops，防上下文自爆）
_SUBGRAPH_NODE_CAP = 300
# 关键词搜索每类结果上限
_SEARCH_CAP = 100


def _dump(obj, indent=2) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=indent))


def _fail(msg: str) -> int:
    print(msg, file=sys.stderr)
    return 1


def _component_row(c) -> dict:
    return {
        "alias": c.alias,
        "submodel": c.submodel.name if c.submodel else None,
        "instance": c.submodel.instance if c.submodel else None,
        "path": c.path_str,
        "ports": [p.type for p in c.ports],
        "params": len(c.params),
        "is_supercomponent": c.is_supercomponent,
    }


def _param_row(p) -> dict:
    return {
        "id": p.id,
        "title": p.title,
        "value": p.value_view,
        "unit": p.units,
        "default": p.default_view,
        "min": p.min,
        "max": p.max,
    }


def _variable_row(v) -> dict:
    return {
        "id": v.id,
        "title": v.title,
        "unit": v.units,
        "kind": v.kind,
        "saved": v.saved,
    }


def _local_graph(model, seed: str, hops: int, domain) -> dict:
    """局部图视图：nodes（含端口类型）+ edges（含两端域），~KB 级。"""
    g = model._require_graph()
    names = g.subgraph(seed, hops)
    nodes = [
        {
            "alias": c.alias,
            "submodel": c.submodel.name if c.submodel else None,
            "path": c.path_str,
            "ports": [{"index": p.index, "type": p.type} for p in c.ports],
        }
        for c in model.circuit.components if c.alias in names
    ]
    if len(nodes) > _SUBGRAPH_NODE_CAP:
        raise ValueError(
            f"local graph has {len(nodes)} nodes (> {_SUBGRAPH_NODE_CAP}); "
            f"reduce --hops or export the full card and analyze it in code")
    edges = [
        {"from": [e.a.component, e.a.port], "to": [e.b.component, e.b.port],
         "from_type": e.a_type, "to_type": e.b_type}
        for e in g.edges(domain=domain)
        if e.a.component in names and e.b.component in names
    ]
    return {"seed": seed, "hops": hops, "domain": domain,
            "nodes": nodes, "edges": edges}


def _cmd_parse(argv: list) -> int:
    ap = argparse.ArgumentParser(
        prog="ameparse",
        description="Parse .ame model files: structure/params/variables/graph "
        "(standalone, no external software or license required)",
    )
    ap.add_argument("ame", help="path to the .ame file")
    ap.add_argument("-o", "--output", help="write full card JSON to this file")
    ap.add_argument("--indent", type=int, default=2)
    # -- 快照视图 -----------------------------------------------------
    ap.add_argument("--summary", action="store_true", help="print counts overview")
    ap.add_argument("--settings", action="store_true",
                    help="print model settings: version, simulation options, model io")
    # -- 组件 ---------------------------------------------------------
    ap.add_argument("--components", action="store_true",
                    help="list components (compact rows; requires a filter or --all)")
    ap.add_argument("--component", metavar="ALIAS",
                    help="print one component by alias (ambiguous aliases list candidate paths)")
    ap.add_argument("--no-params", action="store_true",
                    help="with --component: omit the params array")
    ap.add_argument("--no-variables", action="store_true",
                    help="with --component: omit the variables array")
    # -- 参数/变量 ------------------------------------------------------
    ap.add_argument("--param", metavar="ID",
                    help="print one parameter by 'name@alias' (value/bounds/unit)")
    ap.add_argument("--variable", metavar="ID",
                    help="print one variable by 'name@alias' (includes saved status)")
    ap.add_argument("--params", action="store_true",
                    help="list params as compact rows (requires a filter or --all)")
    ap.add_argument("--variables", action="store_true",
                    help="list variables as compact rows (requires a filter or --all)")
    ap.add_argument("--alias", help="filter: exact component alias")
    ap.add_argument("--submodel", help="filter: submodel name (e.g. ESSBATPA01)")
    ap.add_argument("--modified-only", action="store_true",
                    help="with --params: only values differing from default")
    ap.add_argument("--saved", action="store_true",
                    help="with --variables: only variables in the .ssf save list "
                         "(retrievable via ameloadvarst; authoritative)")
    ap.add_argument("--save-flag", action="store_true",
                    help="with --variables: filter by the .cir SAVE_VALUE flag "
                         "(the 'saveable' declaration, may differ from --saved)")
    ap.add_argument("--hidden", action="store_true",
                    help="with --variables: only hidden variables (.var HIDDEN section)")
    # -- 检索 / 其他 ----------------------------------------------------
    ap.add_argument("--search", metavar="KEYWORD",
                    help="search params & variables by name/title substring")
    ap.add_argument("--study-params", action="store_true",
                    help="print study/batch parameters with bounds")
    # -- 图 -------------------------------------------------------------
    ap.add_argument("--neighbors", metavar="ALIAS", help="print component neighbors by port")
    ap.add_argument("--subgraph", metavar="ALIAS",
                    help="print the local graph around ALIAS (nodes with port types + edges)")
    ap.add_argument("--hops", type=int, default=2, help="hops for --subgraph (default 2)")
    ap.add_argument("--domain", help="filter edges by port type (e.g. thermal/elect/signal)")
    # -- 导出 -----------------------------------------------------------
    ap.add_argument("--saved-variables", action="store_true",
                    help="print the full .ssf save list (retrievable via ameloadvarst)")
    ap.add_argument("--csv", metavar="DIR", help="write params/variables CSV tables to DIR")
    ap.add_argument("--all", action="store_true",
                    help="override the no-filter guardrail on list commands")
    args = ap.parse_args(argv)

    model = Model.from_file(args.ame)

    if args.summary:
        print(f"model: {model.name}  (ame version {model.ame_version})")
        for k, v in model.counts.items():
            print(f"  {k:24s} {v}")
        io = model.model_info
        if io.states is not None:
            print(f"  states={io.states} discrete={io.discrete_states} "
                  f"interface={io.interface or 'none'}")
        sim = model.simulation
        if sim.final_time is not None:
            print(f"  final_time={sim.final_time:g} print_interval={sim.print_interval:g}")
        return 0

    if args.settings:
        sim = model.simulation
        _dump({
            "model": model.name,
            "ame_version": model.ame_version,
            "simulation": {
                "start_time": sim.start_time,
                "final_time": sim.final_time,
                "print_interval": sim.print_interval,
                # 已确认映射仅前三个字段；其余按下标取（含义随版本未确认）
                "values": sim.values,
                "raw": sim.raw,
            },
            "model_io": model.model_info.to_dict(),
            "study_params": len(model.study.study_params),
            "global_params": len(model.global_params),
        }, args.indent)
        return 0

    if args.components:
        if not (args.alias or args.submodel or args.all):
            return _fail("--components needs a filter (--alias/--submodel) or --all; "
                         "unfiltered listings can be hundreds of rows")
        rows = model.components(alias=args.alias, submodel=args.submodel,
                                top_level=None, supercomponent=None)
        _dump([_component_row(c) for c in rows], args.indent)
        return 0

    if args.params:
        if not (args.component or args.submodel or args.all):
            return _fail("--params needs a filter (--component/--submodel) or --all; "
                         "unfiltered listings can be thousands of rows")
        rows = model.params(component=args.component, submodel=args.submodel,
                            modified_only=args.modified_only)
        _dump([_param_row(p) for p in rows], args.indent)
        return 0

    if args.variables:
        if not (args.component or args.submodel or args.all):
            return _fail("--variables needs a filter (--component/--submodel) or --all; "
                         "unfiltered listings can be thousands of rows")
        rows = model.variables(component=args.component, submodel=args.submodel,
                               kind=None, saved=True if args.saved else None,
                               hidden=True if args.hidden else None)
        if args.save_flag:
            rows = [v for v in rows if v.save_value]
        _dump([_variable_row(v) for v in rows], args.indent)
        return 0

    if args.component:
        try:
            comp = model.component(args.component)
        except KeyError as e:
            return _fail(f"component not found: {e.args[0]}")
        except Exception as e:                     # AmbiguousAlias
            return _fail(str(e))
        d = comp.to_dict()
        if args.no_params:
            d.pop("params", None)
        if args.no_variables:
            d.pop("variables", None)
        _dump(d, args.indent)
        return 0

    if args.param:
        try:
            _dump(model.param(args.param).to_dict(), args.indent)
        except Exception as e:
            return _fail(str(e))
        return 0

    if args.variable:
        try:
            _dump(model.variable(args.variable).to_dict(), args.indent)
        except Exception as e:
            return _fail(str(e))
        return 0

    if args.search is not None:
        kw = args.search.lower()
        params = [p for p in model.params()
                  if kw in p.varname.lower() or kw in p.title.lower()]
        variables = [v for v in model.variables()
                     if kw in v.varname.lower() or kw in v.title.lower()]
        truncated = len(params) > _SEARCH_CAP or len(variables) > _SEARCH_CAP
        _dump({
            "keyword": args.search,
            "params": [_param_row(p) for p in params[:_SEARCH_CAP]],
            "variables": [_variable_row(v) for v in variables[:_SEARCH_CAP]],
            "truncated": truncated,
        }, args.indent)
        return 0

    if args.study_params:
        _dump(model.study.to_dict(), args.indent)
        return 0

    if args.neighbors:
        try:
            nbs = model.neighbors(args.neighbors)
        except Exception as e:
            return _fail(str(e))
        _dump({str(k): [[r.component, r.port] for r in v] for k, v in nbs.items()},
               args.indent)
        return 0

    if args.subgraph:
        try:
            _dump(_local_graph(model, args.subgraph, args.hops, args.domain),
                  args.indent)
        except Exception as e:
            return _fail(str(e))
        return 0

    if args.saved_variables:
        _dump([s.to_dict() for s in model.saved_variables], args.indent)
        return 0

    if args.csv:
        paths = model.to_csv(args.csv)
        for kind, p in paths.items():
            print(f"wrote {p}")
        return 0

    text = json.dumps(model.to_dict(), ensure_ascii=False, indent=args.indent)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0


def _cmd_export(argv: list) -> int:
    from .export import export

    ap = argparse.ArgumentParser(
        prog="ameparse export",
        description="Parse every .ame under --resources and export "
        "sources/ + cards/ + csv/ under --out",
    )
    ap.add_argument("--resources", default=".", help="directory containing .ame files")
    ap.add_argument("--out", default="ameparse-out", help="output root directory")
    args = ap.parse_args(argv)

    resources = Path(args.resources)
    ames = sorted(resources.glob("*.ame"), key=lambda p: p.stat().st_size)
    if not ames:
        return _fail(f"no .ame files found in: {resources}")

    for ame in ames:
        t0 = time.perf_counter()
        model = Model.from_file(str(ame))
        written = export(model, args.out)
        dt = time.perf_counter() - t0
        print(f"[OK] {model.name}: {model.counts['components']} components, "
              f"{model.counts['params']} params, {model.counts['variables']} variables, "
              f"{model.counts['supercomponents']} supercomponents "
              f"({len(written)} artifact kinds, {dt:.1f}s)")
    print(f"\nexported to: {args.out}")
    return 0


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "export":
        return _cmd_export(argv[1:])
    return _cmd_parse(argv)


if __name__ == "__main__":
    raise SystemExit(main())
