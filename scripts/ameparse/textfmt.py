"""行级声明文件（``.param`` / ``.var`` / ``.ssf``）的格式原语。

统一行格式::

    子模型 instance N 标题 [单位] key=value ... Data_Path=名称@别名
"""

from __future__ import annotations

import re

_DECL_HEAD_RE = re.compile(r"^(?P<submodel>\S+)\s+instance\s+(?P<instance>\d+)\s+(?P<rest>.*)$")
_KV_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=([^\s]*)")
_KV_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=\S*")


def split_title_unit(left: str) -> tuple[str, str]:
    """从 ``标题 [单位] 属性...`` 左半部分拆出标题与单位。

    规则（按优先级）：
    1. 以 ``]`` 结尾 → 尾部方括号是单位（``current at port 1 [A]``）；
    2. 第一个方括号后只跟 key=value 属性 → 该方括号是单位
       （``initial cell voltage [V] Is_Delta=0``）；
    3. 否则方括号属于标题本身（``additional resistance [Ohm] expression = f(...)``）。
    """
    if left.endswith("]"):
        lb = left.rfind("[")
        if lb > 0:
            return left[:lb].rstrip(), left[lb + 1 : -1]
        return left, ""
    lb = left.find("[")
    if lb >= 0:
        rb = left.find("]", lb)
        if rb >= 0:
            after = left[rb + 1 :].strip()
            if after and all(_KV_TOKEN_RE.fullmatch(t) for t in after.split()):
                return left[:lb].rstrip(), left[lb + 1 : rb]
    return left, ""


def split_declaration(line: str) -> dict | None:
    """``子模型 instance N 标题 [单位] key=value ... Data_Path=名称@别名``

    标题可能自带方括号（如 ``additional resistance [Ohm] expression = f(...)``），
    因此单位只在左半部分**以 ] 结尾**时提取；此时 title 去掉尾部 ``[unit]``，
    与 .cir 中的 TITLE 保持一致。
    """
    m = _DECL_HEAD_RE.match(line.strip())
    if not m:
        return None
    rest = m.group("rest")
    cut = len(rest)
    for key in (" Param_Id=", " Data_Path="):
        i = rest.find(key)
        if i >= 0:
            cut = min(cut, i)
    left = rest[:cut].rstrip()
    kv = dict(_KV_RE.findall(rest[cut:]))
    data_path = kv.pop("Data_Path", "")
    param_id = int(kv.pop("Param_Id", 0) or 0)
    title, unit = split_title_unit(left)
    return {
        "submodel": m.group("submodel"),
        "instance": int(m.group("instance")),
        "title": title,
        "unit": unit,
        "title_raw": left,
        "param_id": param_id,
        "attributes": kv,
        "data_path": data_path,
    }
