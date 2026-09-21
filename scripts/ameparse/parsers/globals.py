"""全局参数解析：来源注册表 + 三种真实写法的统一提取。

同一个全局参数在真实 ``.ame`` 里可能出现在三个成员中，取值还可能不一致：

============  ==========================================================
成员          写法
============  ==========================================================
``.amegp``    ``GLOBAL_PARAMS_LIST > PARAMETER``（子元素式，权威来源）
``.cir``      ``GLOBAL_PARAMS_LIST > GROUP? > GLOBALPARAM``
``.pl``       ``GLOBAL_PARAMS_LIST > PARAMETER``（属性式，值在 XML 属性上）
============  ==========================================================

``.pl`` 在 ``GLOBAL_PARAMS_LIST`` 之外还有上千个 ``PARAMETER``（组件参数，
与 ``.cir`` 重复），所以提取一律先定位到该列表子树——否则会把组件参数
当成全局参数。

``EXTRACTORS`` 是来源注册表：新增一个来源只需加一条
``成员后缀 -> 定义标签``。定义节点统一交给 :func:`_from_node`，它先找子元素
再退回属性，因此子元素式、属性式、以及历史旧写法（``GPARAM``/``UNITS``）
三种都能吃。

历史坑：旧实现只认 ``GPARAM``/``UNITS``，而真实文件用的是
``PARAMETER``/``UNIT``，于是 233 个全局参数被静默报成 0——一个自信的零
比"未解析"更有害，因为它让追问到此为止。
"""

from __future__ import annotations

from dataclasses import replace

from ..model.circuit import GlobalParam
from ..tolerant import Node, iter_local, parse as parse_tolerant

#: 全局参数列表容器标签（三种成员一致）
LIST_TAG = "GLOBAL_PARAMS_LIST"

#: 来源注册表：成员后缀 -> 该来源里定义全局参数的标签（按优先级）
EXTRACTORS: dict = {
    ".amegp": ("PARAMETER", "GPARAM"),
    ".cir": ("GLOBALPARAM", "GPARAM"),
    ".pl": ("PARAMETER",),
}


def _pick(node: Node, child_tags: tuple, attr_names: tuple) -> str:
    """取字段值：先找子元素（``.amegp``/``.cir``），再退回属性（``.pl``）。"""
    for tag in child_tags:
        v = node.text_of(tag)
        if v:
            return v
    for name in attr_names:
        v = node.attrs.get(name)
        if v:
            return v
    return ""


def _from_node(node: Node, source: str) -> GlobalParam:
    """一个定义节点 → GlobalParam（子元素式 / 属性式通吃）。"""
    return GlobalParam(
        varname=_pick(node, ("VARNAME", "GLOB_PARAM_NAME"),
                      ("Data_Path", "VARNAME", "GLOB_PARAM_NAME")),
        title=_pick(node, ("TITLE",), ("TITLE",)),
        value=_pick(node, ("VALUE",), ("VALUE",)),
        units=_pick(node, ("UNIT", "UNITS"), ("UNITS", "UNIT")),
        default=_pick(node, ("DEFAULT", "DEF_VALUE"), ("DEFAULT", "DEF_VALUE")),
        min=_pick(node, ("MIN_VALUE", "MIN"), ("MIN_VALUE", "MIN")),
        max=_pick(node, ("MAX_VALUE", "MAX"), ("MAX_VALUE", "MAX")),
        type=_pick(node, ("TYPE",), ("TYPE",)),
        source=source,
    )


def extract_globals(root, source: str) -> list:
    """从**已解析**的树里提取定义（``.cir`` 已有树，避免重复解析大文件）。

    ``.cir`` 可能有两个 ``GLOBAL_PARAMS_LIST`` 段，所以遍历全部容器而不是
    只取第一个（``Node.find`` 只返回首个，旧实现因此还会再漏一半）。
    同名重复定义按首次出现保留，顺序稳定。
    """
    tags = EXTRACTORS.get(source)
    if not tags:
        return []
    holders = list(iter_local(root, LIST_TAG)) or [root]
    out: list = []
    seen: set = set()
    for holder in holders:
        for tag in tags:
            for node in iter_local(holder, tag):
                gp = _from_node(node, source)
                if gp.varname and gp.varname not in seen:
                    seen.add(gp.varname)
                    out.append(gp)
    return out


def parse_globals(text: str, source: str) -> list:
    """解析单个成员的全局参数定义（未知来源或空文本 → 空列表）。"""
    if not text or source not in EXTRACTORS:
        return []
    return extract_globals(parse_tolerant(text), source)


#: 权威来源顺序：同名取值分歧时以靠前者交付，且分歧必须报告
SOURCE_PRECEDENCE = (".amegp", ".cir", ".pl")


def merge_globals(by_source: dict) -> tuple:
    """多来源定义 → ``(合并列表, 冲突列表)``。

    ``by_source`` 形如 ``{".amegp": [GlobalParam], ".cir": [...], ".pl": [...]}``。
    规则：

    - 取值以 :data:`SOURCE_PRECEDENCE` 中靠前且有值的来源为准；
    - 标题/单位/上下界等元信息从任一有值的来源补齐（子元素式来源带得最全）；
    - 同名**取值分歧**记入冲突列表，绝不静默择一——真实模型里
      ``.amegp`` 与 ``.cir``/``.pl`` 不一致是常见的交付事故，而按声明
      过时的那个来源跑出来的结果与预期会完全不同。

    返回的每一条 ``source`` 字段标明交付值来自哪个来源。
    """
    order = {s: i for i, s in enumerate(SOURCE_PRECEDENCE)}
    index: dict = {}
    for src, items in by_source.items():
        for gp in items:
            index.setdefault(gp.varname, []).append(gp)

    names = sorted(index, key=lambda n: (min(order.get(g.source, len(order))
                                             for g in index[n]), n))
    merged: list = []
    conflicts: list = []
    for name in names:
        entries = sorted(index[name],
                         key=lambda g: order.get(g.source, len(order)))
        with_value = [e for e in entries if e.value] or entries
        primary = with_value[0]
        out = replace(primary)
        for attr in ("title", "units", "default", "min", "max", "type"):
            if not getattr(out, attr):
                for e in entries:
                    if getattr(e, attr):
                        setattr(out, attr, getattr(e, attr))
                        break
        merged.append(out)

        values = {e.source: e.value for e in entries if e.value}
        if len(set(values.values())) > 1:
            conflicts.append({
                "name": name,
                "authoritative": out.value,
                "values": [{"source": s, "value": v}
                           for s, v in sorted(values.items(),
                                              key=lambda kv: order.get(kv[0], len(order)))],
            })
    return merged, conflicts


class AmegpParser:
    """``.amegp`` → [GlobalParam]（全局参数；定义取值的权威来源）。"""

    suffix = ".amegp"

    def parse(self, text: str) -> list:
        return parse_globals(text, ".amegp")


class PlParser:
    """``.pl`` → [GlobalParam]（只取 ``GLOBAL_PARAMS_LIST`` 段）。

    ``.pl`` 其余 ``PARAMETER`` 段是组件参数，与 ``.cir`` 重复，不在此解析。
    """

    suffix = ".pl"

    def parse(self, text: str) -> list:
        return parse_globals(text, ".pl")


def parse_amegp(text: str) -> list:
    return AmegpParser().parse(text)
