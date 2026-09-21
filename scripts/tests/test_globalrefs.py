"""全局参数引用索引测试（GlobalRefResolver）。

用零件级构造（手搭 CircuitModel）而不是整包 fixture，便于精确控制引用点：
整值引用、表达式引用、状态初值引用、全局之间互相引用，以及三类诊断。
"""

from __future__ import annotations

from ameparse.linking import GlobalRefResolver
from ameparse.model import CircuitModel, Component, ComponentKey, Param, Submodel, Var


def _comp(alias: str, params=(), vars=(), path=(), inst: int = 1) -> Component:
    sm = Submodel(name="TEST00", instance=inst)
    for p in params:
        sm.params.append(p)
    for v in vars:
        sm.internal_vars.append(v)
    return Component(key=ComponentKey(path=path, alias=alias), submodel=sm)


def _param(alias: str, name: str, value: str, default: str = "0") -> Param:
    return Param(varname=name, title="", kind="real", alias=alias,
                 value=value, default=default)


def _var(alias: str, name: str, value: str) -> Var:
    return Var(varname=name, title="", kind="internal", alias=alias, value=value)


def _resolve(comps, names, values) -> object:
    circuit = CircuitModel(components=list(comps))
    return GlobalRefResolver(circuit, names, values).resolve()


# ---------------------------------------------------------------- 引用识别


def test_whole_value_and_expression_roles():
    """整值引用与表达式引用要分清——标定时整值引用是"直接绑到某个旋钮上"。"""
    comps = [
        _comp("c1", params=[
            _param("c1", "gain", "G1"),            # 整值
            _param("c1", "area", "G2*2+1"),        # 表达式
        ]),
        _comp("c2", vars=[_var("c2", "t2", "G1"),  # 变量取值 = 状态初值
                          _var("c2", "t3", "G1+ G2")]),
    ]
    idx = _resolve(comps, ["G1", "G2"], {"G1": "1", "G2": "2"})
    assert idx.ref_count("G1") == 3
    roles = {(r.owner_id, r.role) for r in idx.refs("G1")}
    assert roles == {("gain@c1", "value"), ("t2@c2", "value"),
                     ("t3@c2", "expression")}
    assert idx.ref_count("G2") == 2
    assert {r.role for r in idx.refs("G2")} == {"expression"}


def test_ref_carries_kind_path_and_expr():
    comps = [_comp("dup", path=("SUPER",), inst=2,
                   params=[_param("dup", "k", "G1*3")])]
    idx = _resolve(comps, ["G1"], {"G1": "1"})
    r = idx.refs("G1")[0]
    assert r.kind == "param" and r.path == "SUPER" and r.alias == "dup"
    assert r.expr == "G1*3"
    d = r.to_dict()
    assert d["owner_id"] == "k@dup" and d["role"] == "expression"


def test_word_boundary_prevents_prefix_collision():
    """``LF_eta`` 不能匹配到 ``LF_eta7`` 里，``x_`` 后缀也不能被切。"""
    comps = [_comp("c1", params=[
        _param("c1", "a", "LF_eta7"),
        _param("c1", "b", "LF_eta7_x"),
        _param("c1", "c", "notLF_eta7"),
    ])]
    idx = _resolve(comps, ["LF_eta", "LF_eta7", "LF_eta7_x"],
                   {"LF_eta": "0", "LF_eta7": "1", "LF_eta7_x": "2"})
    assert idx.ref_count("LF_eta7") == 1
    assert idx.ref_count("LF_eta7_x") == 1
    assert idx.ref_count("LF_eta") == 0
    assert idx.unused == ["LF_eta"]


def test_global_to_global_reference_counts():
    """全局定义里引用另一个全局，也要算引用。

    否则 ``LF_mtotal_initial`` 这类"只被别的全局用到"的量会被误报成
    "定义了却无人引用"。
    """
    idx = _resolve([_comp("c1")], ["G1", "G2"],
                   {"G1": "1", "G2": "G1*3600/2"})
    assert idx.ref_count("G1") == 1
    r = idx.refs("G1")[0]
    assert r.kind == "global" and r.owner_id == "G2"
    assert idx.unused == ["G2"]


def test_unused_and_empty_circuit():
    idx = _resolve([_comp("c1")], ["G1", "G2"], {"G1": "1", "G2": "2"})
    assert idx.unused == ["G1", "G2"]
    assert idx.total_refs == 0
    idx0 = _resolve([], [], {})
    assert idx0.by_global == {} and idx0.unused == []


# ---------------------------------------------------------------- 诊断


def test_undefined_refs_only_inside_global_definitions():
    """悬空引用只在全局定义里检测，且要报出宿主与原文。

    不在组件取值里做 token 级检测是有意的：那里可能是任意字符串
    （``materialName = 'PU'``/'Cell_Width'），token 扫描会产出几十条噪音，
    把真正的悬空引用埋掉。
    """
    idx = _resolve([_comp("c1", params=[_param("c1", "k", "PU")])],
                   ["G1"], {"G1": "G2*2"})
    assert idx.undefined_refs == [
        {"owner": "G1", "expr": "G2*2", "names": ["G2"]}]
    # 组件取值里的裸词不报（PU 是字符串值，不是悬空全局引用）
    assert idx.ref_count("G2") == 0


def test_undefined_refs_ignores_builtins():
    idx = _resolve([], ["G1"], {"G1": "sqrt(G1_other)+pi*min(1,2)"})
    assert idx.undefined_refs[0]["names"] == ["G1_other"]


def test_twins_divergent_values():
    """封装交付物的重名陷阱：X 与 X__实例后缀 同时存在且取值不同。"""
    idx = _resolve([], ["SOC_upper_limit", "SOC_upper_limit__PACK1",
                        "T_enter", "T_enter__PACK1"],
                   {"SOC_upper_limit": "90", "SOC_upper_limit__PACK1": "100",
                    "T_enter": "20", "T_enter__PACK1": "20"})
    assert [t["base"] for t in idx.twins] == ["SOC_upper_limit"]
    members = {m["name"]: m["value"] for m in idx.twins[0]["members"]}
    assert members == {"SOC_upper_limit": "90", "SOC_upper_limit__PACK1": "100"}


def test_no_twins_when_values_agree():
    idx = _resolve([], ["A", "A__X"], {"A": "1", "A__X": "1"})
    assert idx.twins == []


# ---------------------------------------------------------------- 视图


def test_summary_and_full_dict_shapes():
    comps = [_comp("c1", params=[_param("c1", "k", "G1")])]
    idx = _resolve(comps, ["G1", "G2"], {"G1": "1", "G2": "2"})
    s = idx.summary_dict()
    assert s["counts"] == {"G1": 1} and s["total_refs"] == 1
    assert s["unused"] == ["G2"] and s["twins"] == [] and s["undefined_refs"] == []
    full = idx.to_dict()
    assert full["refs"]["G1"][0]["owner_id"] == "k@c1"
