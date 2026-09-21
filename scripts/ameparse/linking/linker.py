"""声明合并：把 ``.param`` / ``.var`` 声明挂到 ``.cir`` 的参数/组件对象上。

合并规则（与旧 modelcard._enrich 一致，串户 bug 已修，见下）：

- 参数按 ``Data_Path``（``名称@别名``）精确匹配声明；
- 匹配不上时按 ``(Param_Id, 实例号)`` 退化匹配，唯一候选才采用；
- ``.cir`` 的 TITLE/UNITS 是权威；``.param`` 提供 Param_Id 与属性。

``declared_param_count`` 的归属规则（修复旧版 ``endswith("@别名")`` 串户），
按优先级回退，命中者**全部**计数（跨层级复制的组件共享同一份声明）::

    1. 别名 + (子模型, 实例号) 精确一致；
    2. 实例号错位（.cir 的 SUB_UNIT 与 .param 的 instance 不一致，
       实测存在，如 rotaryload2 的 MECRL0 0 vs 1）→ 别名 + 子模型名一致；
    3. 该别名下唯一组件。

别名在超级组件内外重复且子模型不同时（references/FORMAT.md『标识与编号约定』），
声明只归属子模型匹配的那个组件。
"""

from __future__ import annotations

from ..model.circuit import CircuitModel
from ..model.declarations import Declarations


class Linker:
    """把 :class:`Declarations` 与 save 清单合并进 :class:`CircuitModel`（in-place）。

    ``saved_paths``：``.ssf`` 实际保存列表的 Data_Path 集合（ameloadvarst
    可取数判据）；非空时回填每个 :class:`Var` 的 ``saved``。
    """

    def __init__(self, declarations: Declarations, saved_paths=()):
        self._decls = declarations
        self._saved_paths = frozenset(saved_paths)

    def link(self, circuit: CircuitModel) -> None:
        by_path = self._decls.params_by_path
        by_instance = self._decls.params_by_instance
        for comp in circuit.components:
            sm = comp.submodel
            if sm is None:
                continue
            for p in sm.params:
                decl = by_path.get(p.id)
                if decl is None:
                    # 退化匹配：按 Param_Id（CIRCUIT_SCOPE_ID 与 Param_Id 同源）
                    # 注意 sub_id == 0 是合法值，不能按 falsy 判缺失
                    sub_id = p.sub_id if p.sub_id is not None else -1
                    inst = sm.instance if sm.instance is not None else -1
                    cand = [
                        d
                        for (_s, i, pid), d in by_instance.items()
                        if pid == sub_id and d.instance == inst
                    ]
                    decl = cand[0] if len(cand) == 1 else None
                p.declaration = decl
            if self._saved_paths:
                for v in [*sm.external_vars, *sm.internal_vars]:
                    v.saved = v.id in self._saved_paths
        self._attribute_declarations(circuit)

    # ---------------------------------------------------------------- 归属

    def _attribute_declarations(self, circuit: CircuitModel) -> None:
        """把 .param 声明逐条归属到组件，填 ``declared_param_count``。"""
        by_alias: dict = {}
        for comp in circuit.components:
            by_alias.setdefault(comp.alias, []).append(comp)

        counts: dict = {}
        for d in self._decls.params:
            if "@" not in d.data_path:
                continue
            for target in self._attribute_one(
                by_alias.get(d.data_path.rsplit("@", 1)[-1], []),
                d.submodel, d.instance,
            ):
                counts[id(target)] = counts.get(id(target), 0) + 1
        for comp in circuit.components:
            comp.declared_param_count = counts.get(id(comp), 0)

    @staticmethod
    def _attribute_one(comps: list, submodel: str, instance: int) -> list:
        """归属一条声明；返回目标组件列表（可空）。

        跨层级复制的组件（同别名、同子模型、同实例号，分处顶层与不同
        超级组件内）共享同一份 .param 声明——归属到全部匹配者。
        """
        if not comps:
            return []
        exact = [
            c for c in comps
            if c.submodel is not None
            and (c.submodel.name, c.submodel.instance) == (submodel, instance)
        ]
        if exact:
            return exact
        by_name = [c for c in comps if c.submodel is not None
                   and c.submodel.name == submodel]
        if by_name:
            return by_name                 # 实例号错位但子模型名一致
        if len(comps) == 1:
            return comps                   # 别名唯一（如无子模型的超级组件）
        return []

    def alias_map(self) -> dict:
        """(子模型, 实例号) -> 别名（.param 优先、.var 补充，先到先得）。

        与旧实现逐字一致；供编译拓扑的槽位挂载使用。
        """
        out: dict = {}
        for d in self._decls.params + self._decls.variables:
            if d.data_path:
                out.setdefault(
                    (d.submodel, d.instance), d.data_path.split("@", 1)[-1]
                )
        return out
