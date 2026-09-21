"""容错 XML 扫描器与行格式原语测试。"""

from __future__ import annotations

from ameparse.tolerant import parse
from ameparse.textfmt import split_declaration, split_title_unit


def test_tolerates_unescaped_ampersand_and_lt():
    """VISIBILITY 里的 && 与 VALUE 里的 < 不能导致解析失败。"""
    root = parse(
        "<A>\n<VISIBILITY>(mode == 1) && (sub == 2)</VISIBILITY>\n"
        "<VALUE>(x<=0)*10+(0<x)*20</VALUE>\n</A>"
    )
    a = root.find("A")
    assert a.text_of("VISIBILITY") == "(mode == 1) && (sub == 2)"
    assert a.text_of("VALUE") == "(x<=0)*10+(0<x)*20"


def test_multiple_tags_on_one_line():
    root = parse("<A><B>1</B><C>2</C></A>")
    a = root.find("A")
    assert a.text_of("B") == "1" and a.text_of("C") == "2"


def test_attrs_and_iter():
    root = parse('<CIR DOC_VERSION="2" AME_VERSION="2410"><CIRCUIT/></CIR>')
    cir = root.find("CIR")
    assert cir.attrs["AME_VERSION"] == "2410"
    assert len(list(cir.iter("CIRCUIT"))) == 1


# ---------------------------------------------------------------- textfmt


def test_split_title_unit_three_rules():
    # 规则 1：以 ] 结尾 → 尾部方括号是单位
    assert split_title_unit("current at port 1 [A]") == ("current at port 1", "A")
    # 规则 2：第一个方括号后只跟 key=value → 方括号是单位
    assert split_title_unit("initial cell voltage [V] Is_Delta=0") == (
        "initial cell voltage", "V")
    # 规则 3：方括号属于标题本身
    title, unit = split_title_unit("additional resistance [Ohm] expression = f(...)")
    assert unit == "" and title.startswith("additional resistance")


def test_split_declaration():
    d = split_declaration(
        "ESSBATPA01 instance 1 initial cell voltage [V] Is_Delta=0 "
        "Param_Id=212 Data_Path=Uinit@BatPackGene"
    )
    assert d["submodel"] == "ESSBATPA01"
    assert d["instance"] == 1
    assert d["title"] == "initial cell voltage"
    assert d["unit"] == "V"
    assert d["param_id"] == 212
    assert d["data_path"] == "Uinit@BatPackGene"
    # 属性只捕获 Param_Id/Data_Path 切点之后的 key=value
    # （Is_Delta 在标题区，与旧实现一致不进 attributes）
    assert d["attributes"] == {}
    # 非声明行返回 None
    assert split_declaration("random text without instance") is None
