""".cir 解析测试（CirParser）。"""

from __future__ import annotations

from ameparse.errors import CirParseError
from ameparse.model import ConnectRef
from ameparse.parsers import CirParser, parse_cir
from _fixtures import CIR


def test_basic_structure():
    model = parse_cir(CIR)
    assert model.ame_version == "2410"
    assert model.doc_version == "2"
    assert len(model.components) == 3          # 含超级组件内的 inner3
    pump = model.components[0]
    assert pump.alias == "pump01"
    assert pump.submodel.name == "PUROT00"
    assert pump.submodel.instance == 1
    assert pump.scope_level == "TOP"


def test_param_values_and_expression_text():
    model = parse_cir(CIR)
    pump = model.components[0]
    displ = pump.submodel.param("displ")
    assert displ.number == 71.0
    assert displ.default_number == 50.0
    assert displ.units == "cc/rev"
    assert displ.id == "displ@pump01"
    assert displ.is_modified
    # 未转义 < 的表达式原文保留
    src = model.components[1]
    assert src.submodel.param("p").value.startswith("(x<=0)")


def test_connections_raw_entity_refs():
    """原始连接表保留实体号；ConnectRef.port 是 .cir 原文（目标侧 0-based）。"""
    model = parse_cir(CIR)
    assert model.connections == [
        {"from": ["pump01", 1], "to": [2, 0]},
        {"from": ["source2", 1], "to": [2, 1]},
    ]
    pump = model.components[0]
    assert pump.ports[0].connects == [ConnectRef(entity=2, port=0)]


def test_port_indices_are_one_based():
    model = parse_cir(CIR)
    pump = model.components[0]
    assert [p.index for p in pump.ports] == [1]
    # 外部变量的 port_index 与 EVARS_LIST 的 PORT 顺序一致（1-based）
    q1 = pump.submodel.external_vars[0]
    assert q1.varname == "q1" and q1.port_index == 1


def test_supercomponent_nesting_and_levels():
    model = parse_cir(CIR)
    inner = [c for c in model.components if c.path]
    assert len(inner) == 1
    assert inner[0].alias == "inner3"
    assert inner[0].path == ("source2",)
    assert inner[0].scope_level.startswith("SC:")
    assert len(model.supercomponents) == 1
    sc = model.supercomponents[0]
    assert sc.name == "source2"
    assert sc.port_maps == ["1 0 2 1 signal 0.000000 0.000000"]
    assert model.components[1].is_supercomponent


def test_lines_and_variables():
    model = parse_cir(CIR)
    assert len(model.lines) == 1
    line = model.lines[0]
    assert line.start == (1, 1) and line.end == (2, 1)
    assert line.submodel_name == "DIRECT"
    pump_sm = model.components[0].submodel
    assert pump_sm.external_vars[0].units == "L/min"
    assert pump_sm.external_vars[0].save_value is True
    assert pump_sm.internal_vars[0].varname2 == "dw"


def test_alias_map_and_port_map():
    model = parse_cir(CIR)
    assert model.alias_map() == {
        ("PUROT00", 1): "pump01",
        ("SOUROT00", 2): "source2",
        ("GA00", 3): "inner3",
    }
    assert model.port_map()["pump01"] == {"q1": 1}
    assert model.port_map()["inner3"] == {}       # 无外部端口变量


def test_invalid_cir_raises():
    try:
        CirParser().parse("<NOT_CIR/>")
        raise AssertionError("应当抛 CirParseError")
    except CirParseError as e:
        assert ".cir" in str(e)
