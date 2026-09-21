"""连接图解析：``.cir`` 的 CONNECT 引用 + 编译态拓扑（``.c``）联合解析。

``.cir`` 的 ``CONNECT (E, Q)`` 表示"本端口连到实体 E 的第 Q 个端口
（0-based）"。实体 E 有两种：

- **真实组件**：其若干端口分别被不同组件引用（如 entity 61 =
  powersensor_elect_2：BatPackGene.2 连其 3 口、current_transducer.3 连其 1 口）；
- **DIRECT 直连线**：仅 2 个挂载（端口 0/1），编译时被内联——两端在 ``.c``
  里共享同一 ``v[]`` 槽位。

实体编号是内部 sketch id（按端口域全局编号，文件内无显式存储），
无法由静态顺序推导（四种假设全部实测失败，见 references/probes/）；
以 ``.c`` 的槽位共享为罗塞塔石碑，用"端口号匹配"投票即可把实体号解析为
组件别名，进而把 .cir 的全量引用（含信号/remote 连接）翻译成别名级连接图。

残留：约 15% 多挂载实体无法投票定位，按"网络节点"处理（挂载点两两相连）；
本模块依赖 ``.c`` 存在（无则上层不建图）。
"""

from __future__ import annotations

from collections import defaultdict

from ..model.circuit import CircuitModel
from ..model.compiled import CompiledTopology
from ..model.graph import ConnectionGraph, PortRef


def _domain(port_type: str) -> str:
    return "REMOTE" if port_type.startswith("remote") else port_type


class GraphResolver:
    """(CircuitModel, CompiledTopology) → :class:`ConnectionGraph`。

    两份输入都来自已解析对象（不再重复解析 ``.cir`` 文本）。
    """

    def __init__(self, circuit: CircuitModel, topology: CompiledTopology):
        self._circuit = circuit
        self._topology = topology

    # ---------------------------------------------------------------- 解析

    def resolve(self) -> ConnectionGraph:
        groups = self._collect_attachments()

        # 编译邻居表（直连）：(alias, port) -> {(alias, port)}，端口 1-based
        neighbors: dict = defaultdict(set)
        for (a, pa), (b, pb) in self._topology.direct_edges:
            neighbors[(a, pa)].add((b, pb))
            neighbors[(b, pb)].add((a, pa))

        # 端口域表：(别名, 端口号) -> 端口类型，边的域信息来源
        ptype: dict = {}
        for comp in self._circuit.components:
            for p in comp.ports:
                ptype[(comp.alias, p.index)] = p.type

        edges: list = []            # [(PortRef, PortRef, kind, a_type, b_type)]

        def _add(a: tuple, b: tuple, kind: str) -> None:
            pa, pb = PortRef(*a), PortRef(*b)
            ta, tb = ptype.get(a, ""), ptype.get(b, "")
            if (pa, pb) <= (pb, pa):
                edges.append((pa, pb, kind, ta, tb))
            else:
                edges.append((pb, pa, kind, tb, ta))

        entity_components: dict = {}
        wires: list = []
        nets: list = []

        for key, att in sorted(groups.items(), key=lambda kv: str(kv[0])):
            att = sorted(att)
            # 1) 双挂载且编译态互为邻居 → DIRECT 直连线（内联）
            if len(att) == 2:
                (a1, p1, _), (a2, p2, _) = att
                if (a2, p2) in neighbors.get((a1, p1), ()):
                    _add((a1, p1), (a2, p2), "direct")
                    wires.append({"attachments": [list(x[:2]) for x in att]})
                    continue
            # 2) 投票：引用 (C,P)->(E,Q)，编译邻居 (nb,np) 满足 np-1==Q
            #    （编译态 1-based，.cir 目标侧 0-based）则投票 E=nb
            votes: dict = defaultdict(int)
            for (a, p, q) in att:
                for (nb, np_) in neighbors.get((a, p), ()):
                    if np_ - 1 == q:
                        votes[nb] += 1
            attach_aliases = {x[0] for x in att}
            candidates = {nb: n for nb, n in votes.items() if nb not in attach_aliases}
            if candidates:
                alias = max(candidates, key=lambda nb: candidates[nb])
                entity_components[key] = alias
                for (a, p, q) in att:
                    _add((a, p), (alias, q + 1), "component")
            elif len(att) == 2:
                # 无投票的双挂载：按直连线处理（信号发射→接收等）
                (a1, p1, _), (a2, p2, _) = att
                _add((a1, p1), (a2, p2), "direct")
                wires.append({"attachments": [list(x[:2]) for x in att]})
            else:
                # 多挂载且无组件证据：按网络（bus）处理，挂载点两两相连
                nets.append({"attachments": [list(x[:2]) for x in att]})
                for i in range(len(att)):
                    for j in range(i + 1, len(att)):
                        if att[i][0] != att[j][0]:
                            _add(tuple(att[i][:2]), tuple(att[j][:2]), "net")

        graph = ConnectionGraph(edges)
        graph.entity_components = {str(k): v for k, v in entity_components.items()}
        graph.wires = wires
        graph.nets = nets
        graph.stats = {
            "groups": len(groups),
            "resolved_components": len(entity_components),
            "wires": len(wires),
            "nets": len(nets),
            "edges": len(graph.edges()),
        }
        return graph

    # ---------------------------------------------------------------- 内部

    def _collect_attachments(self) -> dict:
        """(命名空间, 域, 实体号) -> {(别名, 本方 1-based 端口, 目标 0-based 端口)}。

        命名空间实测必须取平面 "TOP"：entity 编号按端口域全局有效，
        97.3% 编译态互验就是在平面命名空间下取得的。按电路层级分层
        （"SC:<scope_id>"）会把同一实体的挂载拆散，投票失效
        （实测 951 边掉到 859）——旧实现因父链错位恰好落在此行为上，
        这里显式保留。域按端口类型（remote* 归并为 REMOTE）。
        """
        groups: dict = defaultdict(set)
        for comp in self._circuit.components:
            alias = comp.alias
            for port in comp.ports:
                dom = _domain(port.type)
                for c in port.connects:
                    if c.entity > 0:
                        groups[("TOP", dom, c.entity)].add(
                            (alias, port.index, c.port)
                        )
        return groups
