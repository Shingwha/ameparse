"""CLI 查询命令测试（合成模型，直接驱动 main(argv)）。"""

from __future__ import annotations

import json

import pytest

from ameparse.cli import main


def _run(argv, ame_path, capsys):
    code = main([ame_path, *argv])
    out = capsys.readouterr().out
    return code, out


def _json(out):
    return json.loads(out)


# ---------------------------------------------------------------- 快照视图


def test_settings(ame_path, capsys):
    code, out = _run(["--settings"], ame_path, capsys)
    assert code == 0
    s = _json(out)
    assert s["ame_version"] == "2410"
    assert s["simulation"]["final_time"] == 40000.0
    # values 提供全字段数值（未确认字段按下标取）
    assert s["simulation"]["values"][0][:3] == [0.0, 40000.0, 1.0]
    assert s["model_io"]["states"] == 2
    assert "schema_version" not in s          # 小快照，不是卡


def test_summary(ame_path, capsys):
    code, out = _run(["--summary"], ame_path, capsys)
    assert code == 0 and "components" in out and "final_time=40000" in out


# ---------------------------------------------------------------- 组件


def test_components_with_filter(ame_path, capsys):
    code, out = _run(["--components", "--submodel", "PUROT00"], ame_path, capsys)
    assert code == 0
    rows = _json(out)
    assert len(rows) == 1
    assert rows[0]["alias"] == "pump01"
    assert rows[0]["submodel"] == "PUROT00"
    assert rows[0]["ports"] == ["hyd"]
    assert rows[0]["params"] == 1


def test_components_guardrail(ame_path, capsys):
    """无过滤拒绝执行（防上下文自爆），--all 显式覆盖。"""
    code, _ = _run(["--components"], ame_path, capsys)
    assert code == 1
    code, out = _run(["--components", "--all"], ame_path, capsys)
    assert code == 0 and len(_json(out)) == 3


def test_component_trimming(ame_path, capsys):
    code, out = _run(["--component", "pump01", "--no-variables"], ame_path, capsys)
    assert code == 0
    d = _json(out)
    assert "params" in d and "variables" not in d


# ---------------------------------------------------------------- 参数/变量


def test_param_single(ame_path, capsys):
    code, out = _run(["--param", "displ@pump01"], ame_path, capsys)
    assert code == 0
    p = _json(out)
    assert p["id"] == "displ@pump01"
    assert p["value"] == 71.0 and p["unit"] == "cc/rev"
    assert p["min"] == "0"


def test_variable_single_includes_saved(ame_path, capsys):
    code, out = _run(["--variable", "q1@pump01"], ame_path, capsys)
    assert code == 0
    v = _json(out)
    assert v["saved"] is True and v["save"] is True
    code, out = _run(["--variable", "w@pump01"], ame_path, capsys)
    assert _json(out)["saved"] is False       # 有标志但不在 .ssf 列表


def test_params_filter(ame_path, capsys):
    code, out = _run(["--params", "--component", "pump01", "--modified-only"],
                     ame_path, capsys)
    assert code == 0
    rows = _json(out)
    assert [r["id"] for r in rows] == ["displ@pump01"]
    assert rows[0]["default"] == 50.0


def test_params_guardrail(ame_path, capsys):
    assert _run(["--params"], ame_path, capsys)[0] == 1
    assert _run(["--params", "--all"], ame_path, capsys)[0] == 0


def test_variables_saved_filter(ame_path, capsys):
    """--saved 走 .ssf 权威判据；--save-flag 走 .cir 标志——两者可不同。"""
    code, out = _run(["--variables", "--component", "pump01", "--saved"],
                     ame_path, capsys)
    assert code == 0
    assert [v["id"] for v in _json(out)] == ["q1@pump01"]

    code, out = _run(["--variables", "--component", "pump01", "--save-flag"],
                     ame_path, capsys)
    assert [v["id"] for v in _json(out)] == ["q1@pump01", "w@pump01"]


def test_variables_guardrail(ame_path, capsys):
    assert _run(["--variables"], ame_path, capsys)[0] == 1
    assert _run(["--variables", "--all"], ame_path, capsys)[0] == 0


# ---------------------------------------------------------------- 检索


def test_search(ame_path, capsys):
    """按名称/标题子串搜参数与变量（物理语言 → 标识符的翻译入口）。"""
    code, out = _run(["--search", "pressure"], ame_path, capsys)
    assert code == 0
    r = _json(out)
    assert r["keyword"] == "pressure" and r["truncated"] is False
    assert [p["id"] for p in r["params"]] == ["p@source2"]
    assert {v["id"] for v in r["variables"]} == {"pout@source2"}


# ---------------------------------------------------------------- 图


def test_subgraph_local_graph(ame_path, capsys):
    code, out = _run(["--subgraph", "pump01", "--hops", "2"], ame_path, capsys)
    assert code == 0
    g = _json(out)
    assert g["seed"] == "pump01" and g["hops"] == 2
    aliases = {n["alias"] for n in g["nodes"]}
    assert aliases == {"pump01", "source2"}
    pump = next(n for n in g["nodes"] if n["alias"] == "pump01")
    assert pump["ports"] == [{"index": 1, "type": "hyd"}]
    assert g["edges"] == [{"from": ["pump01", 1], "to": ["source2", 1],
                           "from_type": "hyd", "to_type": "hyd"}]
    # 按域过滤
    code, out = _run(["--subgraph", "pump01", "--domain", "signal"],
                     ame_path, capsys)
    assert code == 0 and _json(out)["edges"] == []


def test_neighbors(ame_path, capsys):
    code, out = _run(["--neighbors", "pump01"], ame_path, capsys)
    assert code == 0
    assert _json(out) == {"1": [["source2", 1]]}


def test_study_params(ame_path, capsys):
    code, out = _run(["--study-params"], ame_path, capsys)
    assert code == 0
    s = _json(out)
    assert s["study_params"][0]["name"] == "displ__pump01"
    assert s["batch_params"][0]["set_values"] == ["50", "100"]


def test_error_paths(ame_path, capsys):
    assert _run(["--param", "nope@x"], ame_path, capsys)[0] == 1
    assert _run(["--component", "nope"], ame_path, capsys)[0] == 1


# ---------------------------------------------------------------- 全局参数


def test_globals(ame_path, capsys):
    code, out = _run(["--globals"], ame_path, capsys)
    assert code == 0
    r = _json(out)
    names = [g["name"] for g in r["global_params"]]
    assert names == ["gconst", "gderived", "gtwin", "gtwin__SUB1",
                     "gunused", "gplonly"]
    gconst = r["global_params"][0]
    assert gconst["value"] == "9.81" and gconst["source"] == ".amegp"
    assert gconst["unit"] == "m/s2"
    assert next(g for g in r["global_params"] if g["name"] == "gtwin")["refs"] == 1
    # 冲突与三类诊断一并给出，不必再单独跑一条命令
    assert [c["name"] for c in r["conflicts"]] == ["gconst"]
    assert [t["base"] for t in r["twins"]] == ["gtwin"]
    assert [d["owner"] for d in r["undefined_refs"]] == ["gderived"]
    assert "gunused" in r["unused"]


def test_global_detail_with_refs(ame_path, capsys):
    code, out = _run(["--global", "gtwin"], ame_path, capsys)
    assert code == 0
    g = _json(out)
    assert g["name"] == "gtwin" and g["value"] == "1"
    assert len(g["refs"]) == 1
    ref = g["refs"][0]
    assert ref["owner_id"] == "q1@pump01"
    assert ref["kind"] == "variable" and ref["role"] == "value"
    assert g["conflicts"] == []


def test_global_detail_surfaces_conflict(ame_path, capsys):
    code, out = _run(["--global", "gconst"], ame_path, capsys)
    assert code == 0
    g = _json(out)
    assert g["value"] == "9.81"
    assert g["conflicts"][0]["authoritative"] == "9.81"


def test_global_unknown_name_fails(ame_path, capsys):
    assert _run(["--global", "nope"], ame_path, capsys)[0] == 1


def test_globals_never_reports_a_bare_zero(tmp_path, capsys):
    """三源皆空时要给说明，而不是一个会被误读成"这模型没有全局参数"的 0。"""
    import io
    import tarfile

    from ameparse.cli import NO_GLOBALS_NOTE
    payload = (b"<CIR><CIRCUIT><COMPS_LIST/>"
               b"<GLOBAL_PARAMS_LIST/></CIRCUIT></CIR>")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        info = tarfile.TarInfo("NoGlobals_.cir")
        info.size = len(payload)
        tf.addfile(info, io.BytesIO(payload))
    path = tmp_path / "NoGlobals.ame"
    path.write_bytes(buf.getvalue())

    code, out = _run(["--globals"], str(path), capsys)
    assert code == 0
    r = _json(out)
    assert r["global_params"] == []
    assert r["note"] == NO_GLOBALS_NOTE


def test_search_covers_globals(ame_path, capsys):
    code, out = _run(["--search", "twin"], ame_path, capsys)
    assert code == 0
    r = _json(out)
    assert [g["name"] for g in r["globals"]] == ["gtwin", "gtwin__SUB1"]
