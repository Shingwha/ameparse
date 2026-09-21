"""连接图数据类：别名级电路图（纯数据 + 图查询）。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class PortRef:
    """图中的端点：组件别名 + 1-based 端口号。"""

    component: str
    port: int


@dataclass(frozen=True)
class Edge:
    """一条别名级连接边。

    ``kind`` 记录解析来源（direct | net | component，不进序列化）；
    ``a_type``/``b_type`` 是两端端口类型（elect/thermal/signal/...，
    来自组件端口表），供按域过滤连接关系。
    """

    a: PortRef
    b: PortRef
    kind: str = "direct"
    a_type: str = ""
    b_type: str = ""

    @property
    def domain(self) -> str:
        """边的端口域（两端口同域；取 a 端类型）。"""
        return self.a_type


class ConnectionGraph:
    """别名级连接图：节点是组件端口，边是连接。

    由 :class:`~ameparse.linking.resolver.GraphResolver` 构建；
    端口号一律 1-based（``.cir`` 原始的 0-based 目标端口在解析时转换）。
    """

    def __init__(self, edges=()):
        # 边规范化存储：端点对排序 + 去重（按 (a, b)，首见者保留）+ 全表排序
        norm: dict = {}
        for e in edges:
            a, b, *rest = e
            kind = rest[0] if len(rest) > 0 else "direct"
            ta = rest[1] if len(rest) > 1 else ""
            tb = rest[2] if len(rest) > 2 else ""
            key = (a, b) if (a, b) <= (b, a) else (b, a)
            if key not in norm:
                norm[key] = (kind, ta, tb)
        self._edges = sorted(
            ((a, b, *v) for (a, b), v in norm.items()), key=lambda e: (e[0], e[1])
        )
        self._adj: dict = {}        # alias -> {port: set[PortRef]}
        for a, b, *_rest in self._edges:
            self._adj.setdefault(a.component, {}).setdefault(a.port, set()).add(b)
            self._adj.setdefault(b.component, {}).setdefault(b.port, set()).add(a)
        # 解析统计（GraphResolver 填充）
        self.entity_components: dict = {}
        self.wires: list = []
        self.nets: list = []
        self.stats: dict = {}

    # -- 基本查询 -------------------------------------------------------
    def edges(self, domain: str | None = None) -> list:
        """边列表（按端点排序）。

        domain: 按端口域过滤（端口类型，如 ``"thermal"``/``"elect"``/
        ``"signal"``），两端任一匹配即保留——回路级分析只看单一域的连接。
        """
        out = [Edge(a, b, kind, ta, tb) for a, b, kind, ta, tb in self._edges]
        if domain is not None:
            out = [e for e in out if e.a_type == domain or e.b_type == domain]
        return out

    def ports_of(self, component: str) -> dict:
        """别名 -> {端口号: [邻居 PortRef, ...]}。"""
        return {p: sorted(v) for p, v in self._adj.get(component, {}).items()}

    def neighbors(self, component: str, port: int | None = None):
        """邻居查询：``port=None`` 返回 {端口: [PortRef]}；否则返回该端口的列表。"""
        adj = self._adj.get(component, {})
        if port is not None:
            return sorted(adj.get(port, ()))
        return {p: sorted(v) for p, v in adj.items()}

    # -- 图算法 ---------------------------------------------------------
    def subgraph(self, seed: str, hops: int = 1) -> set:
        """从 ``seed`` 出发 ``hops`` 跳内可达的组件别名集合（BFS，含 seed）。"""
        seen = {seed}
        frontier = [seed]
        for _ in range(max(0, hops)):
            nxt = []
            for alias in frontier:
                for port_map in (self._adj.get(alias) or {}).values():
                    for ref in port_map:
                        if ref.component not in seen:
                            seen.add(ref.component)
                            nxt.append(ref.component)
            frontier = nxt
        return seen

    def subcircuits(self) -> list:
        """连通分量（无向图的连通组件）——子回路拆分的基础（§10.5）。"""
        seen: set = set()
        out = []
        for alias in self._adj:
            if alias in seen:
                continue
            comp = {alias}
            queue = deque([alias])
            while queue:
                cur = queue.popleft()
                for port_map in (self._adj.get(cur) or {}).values():
                    for ref in port_map:
                        if ref.component not in comp:
                            comp.add(ref.component)
                            queue.append(ref.component)
            seen |= comp
            out.append(comp)
        return out

    def shortest_path(self, a: str, b: str) -> list | None:
        """两组件间的连接路径（组件别名序列，BFS 最短）；不可达返回 None。"""
        if a not in self._adj or b not in self._adj:
            return None
        if a == b:
            return [a]
        prev = {a: None}
        queue = deque([a])
        while queue:
            cur = queue.popleft()
            for port_map in (self._adj.get(cur) or {}).values():
                for ref in port_map:
                    if ref.component in prev:
                        continue
                    prev[ref.component] = cur
                    if ref.component == b:
                        path = [b]
                        while prev[path[-1]] is not None:
                            path.append(prev[path[-1]])
                        return list(reversed(path))
                    queue.append(ref.component)
        return None

    # -- 序列化 ---------------------------------------------------------
    def to_dict(self) -> dict:
        neighbors: dict = {}
        for a, b, *_rest in self._edges:
            neighbors.setdefault(a.component, {}).setdefault(a.port, []).append([b.component, b.port])
            neighbors.setdefault(b.component, {}).setdefault(b.port, []).append([a.component, a.port])
        return {
            "available": True,
            "edges": [{"from": [a.component, a.port], "to": [b.component, b.port]}
                      for a, b, *_rest in self._edges],
            "neighbors": neighbors,
            "entity_components": dict(self.entity_components),
            "stats": dict(self.stats),
        }
