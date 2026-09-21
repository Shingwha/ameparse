"""声明类文本成员解析：``.param`` / ``.var`` / ``.ssf``（行格式，见 textfmt）。"""

from __future__ import annotations

import re

from ..model.declarations import ParamDecl, VarDecl
from ..model.metadata import SavedVariable
from ..textfmt import split_declaration


class ParamFileParser:
    """``.param`` → [ParamDecl]（参数声明表：标题/单位/Param_Id/Data_Path）。"""

    suffix = ".param"

    def parse(self, text: str) -> list:
        out = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            d = split_declaration(line)
            if d:
                out.append(ParamDecl(**{k: d[k] for k in ParamDecl.__dataclass_fields__}))
        return out


class VarFileParser:
    """``.var`` → [VarDecl]。``HIDDEN`` 行之后的块为隐藏变量。"""

    suffix = ".var"

    def parse(self, text: str) -> list:
        out = []
        hidden = False
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped == "HIDDEN":
                hidden = True
                continue
            d = split_declaration(stripped)
            if d:
                out.append(
                    VarDecl(
                        submodel=d["submodel"],
                        instance=d["instance"],
                        title=d["title"],
                        unit=d["unit"],
                        data_path=d["data_path"],
                        hidden=hidden,
                    )
                )
        return out


class SsfParser:
    """``.ssf``（save strategy）→ [SavedVariable]：保存变量清单
    （``ameloadvarst`` 能取数的前提）。行首可有标志位。"""

    suffix = ".ssf"

    def parse(self, text: str) -> list:
        out = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            flag = None
            if re.match(r"^\d+\s+\S+", stripped):
                flag = int(stripped.split(None, 1)[0])
                stripped = stripped.split(None, 1)[1]
            d = split_declaration(stripped)
            if d:
                out.append(
                    SavedVariable(
                        data_path=d["data_path"],
                        title=d["title"],
                        unit=d["unit"],
                        submodel=d["submodel"],
                        instance=d["instance"],
                        param_id=d["param_id"],
                        flag=flag,
                        attributes=d["attributes"],
                        title_raw=d["title_raw"],
                    )
                )
        return out


def parse_param_file(text: str) -> list:
    return ParamFileParser().parse(text)


def parse_var_file(text: str) -> list:
    return VarFileParser().parse(text)


def parse_ssf_file(text: str) -> list:
    return SsfParser().parse(text)
