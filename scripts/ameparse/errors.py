"""ameparse 异常层次。

约定：**可预期的缺失不是异常**（无 ``.c`` → ``Model.graph`` 为 ``None`` 并带
``graph_error`` 原因）；**结构损坏才是异常**。
"""

from __future__ import annotations


class AmeparseError(Exception):
    """ameparse 所有异常的基类。"""


class ArchiveError(AmeparseError):
    """无法打开 ``.ame``（不是 tar / 文件不存在 / 无权限）。"""


class MemberNotFound(AmeparseError):
    """必需成员缺失（如无 ``.cir``）。"""


class ParseError(AmeparseError):
    """成员解析失败。携带成员名与行号上下文。"""

    def __init__(self, member: str, message: str, line: int | None = None):
        self.member = member
        self.line = line
        where = f"{member}:{line}" if line is not None else member
        super().__init__(f"{where}: {message}")


class CirParseError(ParseError):
    """``.cir`` 解析失败。"""


class CompiledParseError(ParseError):
    """``.c`` 编译产物解析失败。"""


class GraphUnavailable(AmeparseError):
    """连接图不可用（无 ``.c`` 或拓扑解析失败）。

    ``Model.graph`` 不可用时返回 ``None``，原因见 ``Model.graph_error``；
    本异常供需要强制要求图的调用方使用。
    """


class AmbiguousAlias(AmeparseError):
    """``component(alias)`` / ``param(id)`` 命中多个且未用 ``path`` 限定。

    别名在超级组件内外会重复（组件唯一键是 ``(path, alias)``），
    查询命中多个时必须显式限定。
    """
