"""``.c`` 编译产物解析（代码生成器编译产物）→ 编译态拓扑。

为什么需要它：``.cir`` 的端口连接用内部实体编号（创建顺序产物）表达，
无法静态还原为组件别名。而编译产物 ``.c`` 里：

- ``SUBSTRUC[i]`` 表给出每个子模型实例的变量区间：
  ``{ {inst, &EVIA[k], &IVIA[m], PVIA, &PIA[n], ...}, {...}, "SUBMODEL", inst, NULL }``
- ``EVIA_Vn[7] = {v_slot, -1, var_idx, ...}`` 且定义上方注释带变量名
  （``// variable I1 (Oneline var)``，覆盖率 100%）；
- **两个实例的端口变量共享同一 ``v[]`` 槽位即表示二者相连**
  （直接连接在编译后就是同一个状态变量）。

本解析器只提取 ``.c`` 自身的事实（实例表 / 槽位 / 拷贝语句）；
槽位 → 组件端口的归属需要 ``.cir`` 侧数据，见
:meth:`ameparse.model.compiled.CompiledTopology.attach_ports`。
"""

from __future__ import annotations

import re

from ..model.compiled import CompiledTopology, Instance

# EVIA_Vn[7] = {slot, -1, idx, -1, a, b, c}，前一行注释为变量名
_EVIA_RE = re.compile(
    r"(?://\s*variable\s+(\w+)\s*\(([^)]*)\)\s*\n)?"
    r"static const int EVIA_V(\d+)\[7\]\s*=\s*\{\s*(-?\d+)",
    re.M,
)
# SUBSTRUC 表项（第二重结构含 6 对 {a,b}，外层还有包装括号）
_SUBSTRUC_RE = re.compile(
    r"\{\s*\{\s*(\d+)\s*,\s*&EVIA\[(\d+)\]\s*,\s*(?:&IVIA\[(\d+)\]|NULL)\s*,"
    r"\s*PVIA\s*,\s*(?:&PIA\[(\d+)\]|NULL)[^}]*\}"
    r"(?:\s*,\s*\{[^}]*\})*\s*\}"
    r"\s*,\s*\"([A-Z0-9_]+)\"\s*,\s*(\d+)"
)
_COPY_RE = re.compile(r"\bv\s*\[\s*(\d+)\s*\]\s*=\s*v\s*\[\s*(\d+)\s*\]\s*;")


class CompiledParser:
    """``.c`` 文本 → :class:`~ameparse.model.compiled.CompiledTopology`。"""

    suffix = ".c"

    def evia(self, text: str) -> dict:
        """EVIA_Vn -> (变量名, 类型, v_slot)。"""
        return {
            int(idx): (name, kind, int(slot))
            for name, kind, idx, slot in _EVIA_RE.findall(text)
        }

    def substruc(self, text: str) -> list:
        """SUBSTRUC 表项 -> [(子模型, 实例号, evia_start)]，按 evia_start 排序。"""
        entries = []
        for _inst, evia, _ivia, _pia, sub, inst in _SUBSTRUC_RE.findall(text):
            entries.append((sub, int(inst), int(evia)))
        entries.sort(key=lambda e: e[2])
        return entries

    def copies(self, text: str) -> list:
        """纯拷贝语句 ``v[X] = v[Y];``（信号/remote 接线的编译形态）。"""
        return [(int(a), int(b)) for a, b in _COPY_RE.findall(text)]

    def parse(self, text: str) -> CompiledTopology:
        evia = self.evia(text)
        entries = self.substruc(text)
        topo = CompiledTopology()
        topo.copies = self.copies(text)

        for i, (sub, inst, start) in enumerate(entries):
            end = entries[i + 1][2] if i + 1 < len(entries) else len(evia)
            key = (sub, inst)
            inst_obj = Instance(submodel=sub, instance=inst)
            for n in range(start, end):
                if n not in evia:
                    continue
                name, kind, slot = evia[n]
                inst_obj.variables.append((name, kind, slot))
                topo.slot_users.setdefault(slot, []).append((key, name))
            topo.instances[key] = inst_obj
        return topo


def build_topology(c_text: str, alias_of: dict, port_of: dict) -> CompiledTopology:
    """单步工具：解析 ``.c`` 并完成槽位→端口挂载。

    alias_of: (子模型, 实例号) -> 别名；port_of: 别名 -> {变量名: 1-based 端口号}。
    """
    topo = CompiledParser().parse(c_text)
    topo.attach_ports(alias_of, port_of)
    return topo
