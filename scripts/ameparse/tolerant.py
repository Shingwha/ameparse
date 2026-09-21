"""容错式 XML 行解析器。

``.cir``（v2410）名义上是 XML，实际并不合法：
表达式字段（VISIBILITY / VALUE / DEF_VALUE 等）里带未转义的 ``&&`` 和 ``<``
（如 ``(Tengine<=0)*80``），``xml.etree`` 直接报错。

本模块用"逐标签扫描"策略：在每个 ``<`` 处尝试匹配标签；匹配不上就按文本字符
处理。因此既能容忍一行多标签，也能容忍文本中的裸 ``<`` / ``&``。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_TAG_AT_RE = re.compile(r'<(/?)([A-Za-z_][\w.:-]*)((?:\s+[\w:.-]+="[^"]*")*?)\s*(/?)>')
_ATTR_RE = re.compile(r'([\w:.-]+)="([^"]*)"')


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    text: str = ""
    children: list = field(default_factory=list)
    parent: Node | None = None

    # -- 查询辅助 -------------------------------------------------------
    def find(self, tag: str) -> Node | None:
        for c in self.children:
            if c.tag == tag:
                return c
        return None

    def findall(self, tag: str) -> list[Node]:
        return [c for c in self.children if c.tag == tag]

    def iter(self, tag: str):
        for c in self.children:
            if c.tag == tag:
                yield c
            yield from c.iter(tag)

    def text_of(self, tag: str, default: str = "") -> str:
        n = self.find(tag)
        return n.text if n is not None else default

    # -- ElementTree 兼容层（容错解析与 ET 解析结果可混用） ---------------
    @property
    def attrib(self) -> dict:
        return self.attrs

    def findtext(self, tag: str, default: str = "") -> str:
        return self.text_of(tag, default)

    def path(self) -> str:
        parts, n = [], self
        while n is not None and n.tag != "#root":
            parts.append(n.tag)
            n = n.parent
        return "/".join(reversed(parts))


def _append_text(node: Node, text: str) -> None:
    text = text.strip()
    if text:
        node.text += (" " if node.text else "") + text


def _pop_to(stack: list, name: str) -> None:
    for i in range(len(stack) - 1, 0, -1):
        if stack[i].tag == name:
            del stack[i:]
            return


def _parse_line(line: str, stack: list) -> None:
    pos, n = 0, len(line)
    pending = ""
    while pos < n:
        lt = line.find("<", pos)
        if lt < 0:
            pending += line[pos:]
            break
        if lt > pos:
            pending += line[pos:lt]
        m = _TAG_AT_RE.match(line, lt)
        if not m:
            # 裸 <（表达式文本，如 (x<=0)）——按文本处理
            pending += "<"
            pos = lt + 1
            continue
        _append_text(stack[-1], pending)
        pending = ""
        closing, name, attrstr, selfclose = m.groups()
        if closing:
            _pop_to(stack, name)
        else:
            node = Node(name, dict(_ATTR_RE.findall(attrstr)), parent=stack[-1])
            stack[-1].children.append(node)
            if not selfclose:
                stack.append(node)
        pos = m.end()
    _append_text(stack[-1], pending)


def parse(text: str) -> Node:
    """把整段文本解析成 Node 树。返回 ``#root`` 伪根节点。"""
    root = Node("#root")
    stack = [root]
    for line in text.splitlines():
        _parse_line(line, stack)
    return root


def parse_file(path: str, encoding: str = "latin-1") -> Node:
    with open(path, "r", encoding=encoding, errors="replace") as f:
        return parse(f.read())
