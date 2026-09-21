"""全局参数解析测试：三源写法、来源合并与冲突、解码、properties 命名空间。

回归的都是"静默报空"这一类 bug——旧实现只认 ``GPARAM``/``UNITS``，
真实文件用的却是 ``PARAMETER``/``UNIT``，于是 233 个全局参数被报成 0；
``properties.xml`` 因为有命名空间被报成 0 条。错误答案比"未解析"更有害，
因为它让追问到此为止。
"""

from __future__ import annotations

from ameparse.archive import decode_text
from ameparse.parsers import AmegpParser, PlParser, parse_globals
from ameparse.parsers.globals import merge_globals
from _fixtures import AMEGP, AMEGP_LEGACY, PL, PROPERTIES


# ---------------------------------------------------------------- 三源写法


def test_amegp_real_child_element_shape():
    """.amegp 的真实写法：PARAMETER + 子元素（UNIT 单数）。"""
    gps = AmegpParser().parse(AMEGP)
    names = [g.varname for g in gps]
    assert names == ["gconst", "gderived", "gtwin", "gtwin__SUB1", "gunused"]
    g = gps[0]
    assert g.value == "9.81" and g.default == "9.81"
    assert g.units == "m/s2" and g.min == "0"
    assert g.max == "1.00000000000000e+30"
    assert g.source == ".amegp"


def test_amegp_accepts_legacy_gparam_spelling():
    """旧写法仍要能吃：历史样本就是这么写的。"""
    gps = AmegpParser().parse(AMEGP_LEGACY)
    assert [g.varname for g in gps] == ["glegacy"]
    assert gps[0].value == "3" and gps[0].units == "null"


def test_pl_attribute_shape_and_scoping():
    """.pl 是属性式，且必须只取 GLOBAL_PARAMS_LIST 段。

    .pl 全文件通常有上千个 PARAMETER（组件参数，与 .cir 重复）；不限定子树
    就会把组件参数当成全局参数。
    """
    gps = PlParser().parse(PL)
    assert [g.varname for g in gps] == ["gconst", "gplonly"]
    assert gps[0].value == "1.5" and gps[0].units == "m/s2"
    assert gps[0].source == ".pl"
    # 组件参数段（PARAMS_LIST 里的 displ@pump01）不算全局
    assert all(not g.varname.startswith("displ") for g in gps)


def test_cir_group_shape():
    """.cir 是分组式：GLOBALPARAMS/GROUP/GLOBALPARAM/GLOB_PARAM_NAME。"""
    text = """<CIR><CIRCUIT>
 <GLOBAL_PARAMS_LIST>
  <GROUP>
   <GROUP_ID>g1</GROUP_ID>
   <GLOBALPARAM>
    <GLOB_PARAM_NAME>rho_foam</GLOB_PARAM_NAME>
    <TITLE>foam density</TITLE>
    <TYPE>Real</TYPE>
    <UNITS>kg/m**3</UNITS>
    <VALUE>220</VALUE>
   </GLOBALPARAM>
  </GROUP>
 </GLOBAL_PARAMS_LIST>
</CIRCUIT></CIR>"""
    gps = parse_globals(text, ".cir")
    assert len(gps) == 1
    g = gps[0]
    assert (g.varname, g.value, g.units, g.type) == ("rho_foam", "220", "kg/m**3", "Real")
    assert g.source == ".cir"


def test_cir_reads_every_global_params_list_section():
    """两个 GLOBAL_PARAMS_LIST 段各带一部分定义，都要取到。

    旧实现用 Node.find（只返回首个容器），会再漏一半。
    """
    text = """<CIR><CIRCUIT>
 <GLOBAL_PARAMS_LIST><GLOBALPARAM><GLOB_PARAM_NAME>a</GLOB_PARAM_NAME>
  <VALUE>1</VALUE></GLOBALPARAM></GLOBAL_PARAMS_LIST>
 <SOMETHING/>
 <GLOBAL_PARAMS_LIST><GLOBALPARAM><GLOB_PARAM_NAME>b</GLOB_PARAM_NAME>
  <VALUE>2</VALUE></GLOBALPARAM></GLOBAL_PARAMS_LIST>
</CIRCUIT></CIR>"""
    assert [g.varname for g in parse_globals(text, ".cir")] == ["a", "b"]


def test_unknown_source_and_empty_text():
    assert parse_globals("<x/>", ".nope") == []
    assert parse_globals("", ".amegp") == []
    assert AmegpParser().parse("") == []


def test_duplicate_name_keeps_first():
    text = """<GLOBAL_PARAMS_LIST>
 <PARAMETER><VARNAME>d</VARNAME><VALUE>1</VALUE></PARAMETER>
 <PARAMETER><VARNAME>d</VARNAME><VALUE>2</VALUE></PARAMETER>
</GLOBAL_PARAMS_LIST>"""
    gps = parse_globals(text, ".amegp")
    assert [(g.varname, g.value) for g in gps] == [("d", "1")]


# ---------------------------------------------------------------- 来源合并


def test_merge_precedence_and_conflicts():
    """.amegp 权威；分歧必须报出来，不能静默择一。"""
    by_source = {
        ".amegp": AmegpParser().parse(AMEGP),
        ".cir": [],
        ".pl": PlParser().parse(PL),
    }
    merged, conflicts = merge_globals(by_source)
    assert [g.varname for g in merged] == [
        "gconst", "gderived", "gtwin", "gtwin__SUB1", "gunused", "gplonly"]
    gconst = next(g for g in merged if g.varname == "gconst")
    assert gconst.value == "9.81"          # .amegp 优先于 .pl 的 1.5
    assert gconst.source == ".amegp"
    gplonly = next(g for g in merged if g.varname == "gplonly")
    assert (gplonly.value, gplonly.source) == ("42", ".pl")
    assert [c["name"] for c in conflicts] == ["gconst"]
    assert conflicts[0]["authoritative"] == "9.81"
    assert {v["source"]: v["value"] for v in conflicts[0]["values"]} == {
        ".amegp": "9.81", ".pl": "1.5"}


def test_merge_fills_metadata_from_any_source():
    """取值来自权威来源，元信息可从任一有值的来源补齐。"""
    by_source = {
        ".amegp": AmegpParser().parse(
            "<GLOBAL_PARAMS_LIST><PARAMETER><VARNAME>x</VARNAME>"
            "<VALUE>1</VALUE><UNIT>bar</UNIT></PARAMETER></GLOBAL_PARAMS_LIST>"),
        ".pl": PlParser().parse(
            "<PL><GLOBAL_PARAMS_LIST><PARAMETER Data_Path=\"x\" VALUE=\"1\" "
            "TITLE=\"from pl\"/></GLOBAL_PARAMS_LIST></PL>"),
    }
    merged, conflicts = merge_globals(by_source)
    assert conflicts == []                 # 取值一致 → 不算冲突
    assert merged[0].units == "bar"
    assert merged[0].title == "from pl"     # 标题只有 .pl 有，补过来


def test_merge_empty():
    assert merge_globals({}) == ([], [])


# ---------------------------------------------------------------- 解码


def test_decode_text_honours_utf8_over_mislabeled_latin1():
    """AMESim 把 .cir 标成 ISO-8859-1，实际写的是 UTF-8 中文。

    照声明解码会把所有中文标题变成乱码——标题正是这些模型最有信息量的部分。
    """
    raw = '<?xml version="1.0" encoding="ISO-8859-1"?><T>回风温度</T>'.encode("utf-8")
    assert "回风温度" in decode_text(raw)


def test_decode_text_handles_utf16_bom():
    """UTF-16 的声明本身也是 UTF-16 编码，只能靠 BOM 认出来。"""
    raw = '<?xml version="1.0" encoding="UTF-16"?><T>x</T>'.encode("utf-16")
    assert "<T>x</T>" in decode_text(raw)


def test_decode_text_falls_back_without_raising():
    """非 UTF-8 字节退回 latin-1，不抛异常也不丢内容。"""
    out = decode_text(b"\xff\xff latin1 \xe9")
    assert "latin1" in out and "é" in out


# ---------------------------------------------------------------- properties


def test_properties_namespace_and_sticker():
    """真实 properties.xml 根节点带命名空间，且 sticker 是置信度贴纸。"""
    from ameparse.parsers import PropertiesParser
    props = PropertiesParser().parse(PROPERTIES)
    assert props.count == 2
    by_id = {e.id: e for e in props.entries}
    assert by_id["p1"].target == "model:"
    assert by_id["p2"].sticker == "Low confidence"
    assert by_id["p2"].target == "aliaspath:pump01"
    assert props.to_dict()["properties"][1]["sticker"] == "Low confidence"
