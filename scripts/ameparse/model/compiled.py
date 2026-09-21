"""编译态拓扑数据类（``.c`` 解析产物，纯数据 + 拓扑计算）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Instance:
    """``.c`` SUBSTRUC 表中的一个子模型实例。"""

    submodel: str
    instance: int
    alias: str = ""                 # 由 attach_ports 依 (子模型,实例号)→别名 解析
    variables: list = field(default_factory=list)   # [(name, kind, v_slot)]


class CompiledTopology:
    """编译态拓扑：实例表 + 变量槽位共享关系。

    ``direct_edges`` 只含"共享同一 ``v[]`` 槽位"的直连（DIRECT 线内联后的形态）；
    ``edges``/``nodes`` 还含拷贝语句（``v[X] = v[Y];``，信号广播）合并后的网络。
    """

    def __init__(self) -> None:
        self.instances: dict = {}        # (submodel, inst) -> Instance
        self.slot_users: dict = {}       # v_slot -> [(key, name)]
        self.copies: list = []           # [(x, y)]：v[X] = v[Y]; 拷贝语句（信号广播）
        self.nodes: list = []            # [{slot, type, ports:[(alias,port)]}]
        self.edges: list = []            # [{from:[alias,port], to:[alias,port]}]
        self.direct_edges: set = set()   # {(alias,port), (alias,port)}
        self.unresolved_vars: list = []

    # -- 槽位 → 端口挂载（需要 .cir 侧的别名表与端口表） ------------------
    def attach_ports(self, alias_of: dict, port_of: dict) -> None:
        """alias_of: (子模型, 实例号) -> 别名；port_of: 别名 -> {变量名: 1-based 端口号}。

        把编译态槽位归属到组件端口：仅登记为端口变量（EVAR）的参与，
        共享槽位的两个端口即相连（直接连接编译后是同一个状态变量）；
        ``copies``（拷贝语句）把多个槽位连成同一信号网络。
        """
        for key, inst in self.instances.items():
            inst.alias = alias_of.get(key, f"{inst.submodel}#{inst.instance}")

        slot_ports: dict = {}
        for inst in self.instances.values():
            ports = port_of.get(inst.alias, {})
            for name, _kind, slot in inst.variables:
                pidx = ports.get(name)
                if pidx is None:
                    if len(self.slot_users.get(slot, [])) > 1:
                        self.unresolved_vars.append(
                            {"alias": inst.alias, "variable": name, "slot": slot}
                        )
                    continue
                slot_ports.setdefault(slot, []).append((inst.alias, pidx))

        # 拷贝语句把多个槽位连成同一信号网络（union-find）
        parent = {s: s for s in slot_ports}

        # 先记录纯共享槽位的直连（DIRECT 线内联后的形态）
        for slot, attaches in slot_ports.items():
            uniq = sorted(set(attaches))
            for i in range(len(uniq)):
                for j in range(i + 1, len(uniq)):
                    if uniq[i][0] != uniq[j][0]:
                        self.direct_edges.add((uniq[i], uniq[j]))

        def find(x):
            while parent.get(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        for x, y in self.copies:
            parent.setdefault(x, x)
            parent.setdefault(y, y)
            union(x, y)

        groups: dict = {}
        for s in slot_ports:
            groups.setdefault(find(s), []).extend(slot_ports[s])

        seen = set()
        for _root, attaches in sorted(groups.items()):
            # 去重（同一别名同一端口在组内只算一次）
            uniq = sorted(set(attaches))
            if len(uniq) < 2:
                continue
            self.nodes.append({"ports": [list(a) for a in uniq]})
            for i in range(len(uniq)):
                for j in range(i + 1, len(uniq)):
                    a, b = uniq[i], uniq[j]
                    if a[0] == b[0]:      # 同组件的不同端口不产生边
                        continue
                    ekey = (a[0], a[1], b[0], b[1])
                    rekey = (b[0], b[1], a[0], a[1])
                    if ekey in seen or rekey in seen:
                        continue
                    seen.add(ekey)
                    self.edges.append({"from": [a[0], a[1]], "to": [b[0], b[1]]})

    def neighbors(self, alias: str) -> dict:
        """别名 -> {端口号: [(邻居别名, 邻居端口)]}（编译态边，1-based）。"""
        out: dict = {}
        for e in self.edges:
            a, pa = e["from"]
            b, pb = e["to"]
            if a == alias:
                out.setdefault(pa, []).append((b, pb))
            if b == alias:
                out.setdefault(pb, []).append((a, pa))
        return out
