"""容错式 .cir 行级解析器（上游 "XML" 有未转义的 & 和 <，不能用标准 XML 库）。

格式特征：生成器输出是规整的一行一标签；文本内容不跨行也不以 < 开头。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TAG_RE = re.compile(
    r'^\s*<(/?)([A-Za-z_][\w.:-]*)((?:\s+[\w:.-]+="[^"]*")*?)\s*(/?)>(.*)$'
)
ATTR_RE = re.compile(r'([\w:.-]+)="([^"]*)"')


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    text: str = ""
    children: list = field(default_factory=list)
    parent: "Node | None" = None

    def find(self, tag: str):
        for c in self.children:
            if c.tag == tag:
                return c
        return None

    def findall(self, tag: str) -> list:
        return [c for c in self.children if c.tag == tag]

    def iter(self, tag: str):
        for c in self.children:
            if c.tag == tag:
                yield c
            yield from c.iter(tag)

    def text_of(self, tag: str, default: str = "") -> str:
        n = self.find(tag)
        return n.text if n is not None else default

    def path(self) -> str:
        parts, n = [], self
        while n is not None:
            parts.append(n.tag)
            n = n.parent
        return "/".join(reversed(parts))


def parse(text: str) -> Node:
    root = Node("#root")
    stack = [root]
    for line in text.splitlines():
        m = TAG_RE.match(line)
        if not m:
            t = line.strip()
            if t:
                stack[-1].text += (" " if stack[-1].text else "") + t
            continue
        closing, name, attrstr, selfclose, rest = m.groups()
        if closing:
            for i in range(len(stack) - 1, 0, -1):
                if stack[i].tag == name:
                    del stack[i:]
                    break
            continue
        node = Node(name, dict(ATTR_RE.findall(attrstr)), parent=stack[-1])
        stack[-1].children.append(node)
        # 同行闭合：<TAG>text</TAG>
        m2 = re.match(r"^(.*)</" + re.escape(name) + r">\s*$", rest)
        if m2:
            node.text = m2.group(1).strip()
        elif selfclose:
            pass
        else:
            node.text = rest.strip()
            stack.append(node)
    return root
