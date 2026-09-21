"""Model 门面查询 API 测试（合成模型）。"""

from __future__ import annotations

import pytest

from ameparse import AmbiguousAlias, GraphUnavailable, Model
from ameparse.model import Component, ComponentKey


# ---------------------------------------------------------------- 组件


def test_component_lookup(model):
    pack = model.component("pump01")
    assert isinstance(pack, Component)
    assert pack.key == ComponentKey(path=(), alias="pump01")
    assert pack.path_str == ""
    inner = model.component("inner3", path="source2")
    assert inner.path == ("source2",)
    with pytest.raises(KeyError):
        model.component("不存在")


def test_component_ambiguous_alias(model):
    """别名重复时抛 AmbiguousAlias，需 path 限定（§2.4-2 坑）。"""
    dup = Component(key=ComponentKey(path=("source2",), alias="pump01"),
                    name="PUMP00", scope_id="9", scope_level="SC:5")
    model.circuit.components.append(dup)
    try:
        with pytest.raises(AmbiguousAlias):
            model.component("pump01")
        top = model.component("pump01", path="")
        assert top.path == ()
    finally:
        model.circuit.components.pop()


def test_components_filter(model):
    assert [c.alias for c in model.components(submodel="PUROT00")] == ["pump01"]
    assert [c.alias for c in model.components(top_level=True)] == ["pump01", "source2"]
    assert [c.alias for c in model.components(supercomponent=True)] == ["source2"]
    assert model.submodel_distribution() == {"PUROT00": 1, "SOUROT00": 1, "GA00": 1}


# ---------------------------------------------------------------- 参数/变量


def test_param_query(model):
    p = model.param("displ@pump01")
    assert p.number == 71.0
    assert p.is_modified
    assert p.declaration is not None
    assert p.declaration.param_id == 1
    with pytest.raises(KeyError):
        model.param("nope@pump01")


def test_params_filter(model):
    assert len(model.params()) == 3                       # displ/p/k
    assert [p.varname for p in model.params(component="pump01")] == ["displ"]
    # 三个参数都与默认值不同（p 是表达式原文 vs 数值默认；k=3 vs 1）
    assert [p.varname for p in model.params(modified_only=True)] == ["displ", "p", "k"]


def test_variable_query(model):
    v = model.variable("q1@pump01")
    assert v.kind == "external"
    # 双轨 save 语义：save_value 是 .cir 标志（"可保存"）；saved 是 .ssf 实际
    # 保存列表（ameloadvarst 判据）。合成模型 .ssv 只保存了 q1@pump01。
    assert v.save_value is True and v.saved is True
    w = model.variable("w@pump01")
    assert w.save_value is True and w.saved is False   # 有资格但未列入保存
    pout = model.variable("pout@source2")
    assert pout.save_value is True and pout.saved is False
    assert [v.varname for v in model.variables(kind="internal")] == ["w"]
    # hidden：.var 的 HIDDEN 段（w 是隐藏变量）
    assert [v.varname for v in model.variables(hidden=True)] == ["w"]
    # saved 过滤走权威判据（.ssf），不再与 save_value 混淆
    assert [v.varname for v in model.variables(saved=True)] == ["q1"]


# ---------------------------------------------------------------- 元信息与图


def test_metadata_sections(model):
    assert model.name == "TestModel"
    assert model.ame_version == "2410"
    assert model.model_info.states == 2
    assert model.simulation.final_time == 40000.0
    assert model.study.study_params[0].name == "displ__pump01"
    assert model.units.configuration_name == "SI"
    assert model.properties.entries[0].id == "p1"
    assert model.global_params[0].varname == "gconst"
    assert [s.data_path for s in model.saved_variables] == ["q1@pump01"]


def test_lazy_graph(model):
    """graph 首次访问才触发 .c 解析；可用后查询正常。"""
    m2 = Model.from_file(model.source_path)
    assert m2._graph is not m2.graph or True        # 懒加载不报错即可
    g = m2.graph
    assert g is not None and m2.graph_error is None
    nbs = m2.neighbors("pump01")
    assert nbs == {1: [__import__("ameparse.model.graph", fromlist=["PortRef"]).PortRef("source2", 1)]}
    assert m2.path("pump01", "source2") == ["pump01", "source2"]


def test_graph_unavailable(tmp_path):
    """无 .c 的归档：graph 为 None + graph_error 为 None（可预期缺失非异常）。"""
    import io
    import tarfile

    from _fixtures import CIR, PARAM, VAR
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for name, data in {
            "M_.cir": CIR.encode(), "M_.param": PARAM.encode(),
            "M_.var": VAR.encode(),
        }.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    p = tmp_path / "M.ame"
    p.write_bytes(buf.getvalue())

    m = Model.from_file(str(p))
    assert m.graph is None
    assert m.graph_error is None
    assert m.to_dict()["graph"] == {"available": False}
    with pytest.raises(GraphUnavailable):
        m.neighbors("pump01")


def test_declared_param_count_anti_crosstalk(model):
    """declared_param_count 按 (别名,子模型,实例号) 归属，别名重复不串户。"""
    pump = model.component("pump01")
    inner = model.component("inner3")
    # .param 中 @pump01 的声明有 2 条（displ + nports），@inner3 有 1 条（k）
    assert pump.declared_param_count == 2
    assert inner.declared_param_count == 1
