"""解析层：一个 tar 成员一个解析器，统一 ``parse(text)`` 协议。

``MEMBER_PARSERS`` 是加载白名单——"能读什么"由注册表声明，
大体积成员（``.results``/``.mexw64``/``.obj``）从机制上被挡在外面。
``.c`` 不在自动解析列（重），由 :class:`ameparse.core.Model` 懒加载。
"""

from __future__ import annotations

from typing import Protocol

from .cir import CirParser, parse_cir
from .compiled import CompiledParser, build_topology
from .declarations import (
    ParamFileParser,
    SsfParser,
    VarFileParser,
    parse_param_file,
    parse_ssf_file,
    parse_var_file,
)
from .metadata import (
    AmegpParser,
    ModelInfoParser,
    PropertiesParser,
    SimParser,
    StudyParamParser,
    UnitsParser,
    parse_amegp,
    parse_modelinfo,
    parse_properties,
    parse_sim,
    parse_studyparam,
    parse_units,
)


class MemberParser(Protocol):
    """成员解析器协议：``suffix`` + ``parse(text)``。"""

    suffix: str

    def parse(self, text: str): ...


# 加载白名单：成员后缀 → 解析器（实例无状态，可共享）
MEMBER_PARSERS: dict = {
    ".cir": CirParser(),
    ".param": ParamFileParser(),
    ".var": VarFileParser(),
    ".ssf": SsfParser(),
    ".modelinfo": ModelInfoParser(),
    ".amegp": AmegpParser(),
    ".sim": SimParser(),
    ".studyparam": StudyParamParser(),
    ".units": UnitsParser(),
    "properties.xml": PropertiesParser(),
}

__all__ = [
    "MEMBER_PARSERS", "MemberParser",
    "AmegpParser", "CirParser", "CompiledParser", "ModelInfoParser",
    "ParamFileParser", "PropertiesParser", "SimParser", "SsfParser",
    "StudyParamParser", "UnitsParser", "VarFileParser",
    "build_topology", "parse_amegp", "parse_cir", "parse_modelinfo",
    "parse_param_file", "parse_properties", "parse_sim", "parse_ssf_file",
    "parse_studyparam", "parse_units", "parse_var_file",
]
