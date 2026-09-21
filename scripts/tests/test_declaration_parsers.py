"""声明类与元信息类成员解析器测试。"""

from __future__ import annotations

from ameparse.parsers import (
    AmegpParser,
    ModelInfoParser,
    PropertiesParser,
    SimParser,
    StudyParamParser,
    UnitsParser,
    parse_param_file,
    parse_ssf_file,
    parse_var_file,
)
from _fixtures import (
    AMEGP,
    MODELINFO,
    MODELINFO_NO_IFACE,
    PARAM,
    PROPERTIES,
    SIM,
    SSF,
    STUDYPARAM,
    UNITS,
    VAR,
)


def test_param_file():
    decls = parse_param_file(PARAM)
    assert len(decls) == 4
    d = decls[0]
    assert (d.submodel, d.instance, d.title, d.unit, d.param_id) == (
        "PUROT00", 1, "displacement", "cc/rev", 1)
    assert d.data_path == "displ@pump01"


def test_var_file_hidden_toggle():
    decls = parse_var_file(VAR)
    assert decls[0].hidden is False
    assert decls[1].hidden is True      # HIDDEN 之后


def test_ssf_flag():
    saved = parse_ssf_file(SSF)
    assert len(saved) == 1
    s = saved[0]
    assert s.flag == 1
    assert s.data_path == "q1@pump01"
    assert s.alias == "pump01" and s.varname == "q1"


def test_modelinfo_with_interface():
    info = ModelInfoParser().parse(MODELINFO)
    assert info.states == 2
    assert info.interface == "AMESim"
    assert info.outputs[0].external_name == "Veh_Velocity"
    assert info.inputs[0].start_value.startswith("0.")
    assert info.to_dict()["outputs"][0]["data_path"] == "Veh_Velocity@amesim_interface"


def test_modelinfo_without_interface():
    """无 INTERFACE 的纯模型（RGL 类）。"""
    info = ModelInfoParser().parse(MODELINFO_NO_IFACE)
    assert info.states == 252
    assert info.discrete_states == 154
    assert info.is_explicit is True
    assert info.interface == ""


def test_sim():
    sim = SimParser().parse(SIM)
    assert sim.start_time == 0.0
    assert sim.final_time == 40000.0
    assert sim.print_interval == 1.0
    assert sim.raw and sim.raw[0].startswith("0 40000")
    # 空 .sim：只有 raw
    empty = SimParser().parse("")
    assert empty.to_dict() == {"raw": []}


def test_studyparam():
    study = StudyParamParser().parse(STUDYPARAM)
    assert study.study_params[0].name == "displ__pump01"
    assert study.study_params[0].lower_bound == "0"
    assert study.batch_params[0].name == "displ@pump01"
    assert study.batch_params[0].set_values == ["50", "100"]


def test_units_and_properties_and_amegp():
    units = UnitsParser().parse(UNITS)
    assert units.active_configuration_id == "1"
    assert units.configuration_name == "SI"
    assert units.domains == 1 and units.unit_definitions == 1

    props = PropertiesParser().parse(PROPERTIES)
    assert props.count == 2
    assert props.entries[0].id == "p1"
    assert props.entries[1].sticker == "Low confidence"

    gps = AmegpParser().parse(AMEGP)
    assert gps[0].varname == "gconst"
    assert gps[0].value == "9.81"
