"""电路结构数据类（``.cir`` 解析产物，纯数据 + 领域计算）。

层级结构::

    CircuitModel
    ├── components: [Component]        全部组件（含超级组件内嵌套，DFS 序）
    ├── lines: [Line]                  连线（DIRECT 直连线）
    ├── supercomponents: [Supercomponent]
    ├── global_params: [GlobalParam]
    └── connections: [dict]            原始端口引用表（实体空间，溯源用）

参数/变量的对外标识为 ``名称@别名``（如 ``Uinit@BatPackGene``，
与 ``ameputp`` / ``amegetparamnamefromui`` 一致）。

端口号约定：组件自身端口（``Port.index``、``Var.port_index``）与连接图
（``PortRef.port``）一律 1-based；``ConnectRef.port`` 是 ``.cir`` 原文值
（目标侧 0-based），转换只发生在 GraphResolver。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from .declarations import ParamDecl


# ---------------------------------------------------------------- 值转换


def to_number(raw):
    """'3.30000000000000e+00' → 3.3；无法转换返回 None。"""
    if raw is None:
        return None
    s = raw.strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return None


def to_bool(raw) -> bool | None:
    if raw is None:
        return None
    s = raw.strip().lower()
    if s in ("true", "1"):
        return True
    if s in ("false", "0"):
        return False
    return None


# ---------------------------------------------------------------- 标识


@dataclass(frozen=True)
class ComponentKey:
    """组件唯一键：超级组件的外层与内层组件可能同名（别名重复坑），
    唯一键是 (超级组件链, 别名)，与 ``CIRCUIT_SCOPE_ID`` 同源。"""

    path: tuple = ()                 # 超级组件链（顶层为 ()）
    alias: str = ""


@dataclass(frozen=True)
class ConnectRef:
    """端口的原始连接引用（``.cir`` 的 CONNECT_ENTITY_NUM/PORT 原文）。

    ``port`` 是目标侧 0-based 原始值，供溯源；语义层端口一律 1-based。
    """

    entity: int                      # 内部 sketch 实体号
    port: int


# ---------------------------------------------------------------- 元素


@dataclass
class Param:
    """``.cir`` 的 RPARAM/IPARAM/TPARAM（值以 .cir 为权威）。"""

    varname: str
    title: str
    kind: str                        # real | integer | text
    alias: str = ""                  # 所属组件别名（解析时已知）
    value: str = ""                  # 原文（可能是表达式）
    default: str = ""
    min: str = ""
    max: str = ""
    units: str = ""
    visibility: str = ""
    sub_id: int | None = None
    enums: list = field(default_factory=list)   # [(code, label)]
    text_type: str = ""
    tokens: str = ""
    declaration: ParamDecl | None = None        # Linker 合并的 .param 声明

    @cached_property
    def number(self):
        return to_number(self.value)

    @cached_property
    def default_number(self):
        return to_number(self.default)

    @property
    def id(self) -> str:
        """全限定标识：``VARNAME@ALIAS``。"""
        return f"{self.varname}@{self.alias}"

    @property
    def value_view(self):
        """序列化值：能数值化则数值化，否则保留原文。"""
        return self.number if self.number is not None else self.value

    @property
    def default_view(self):
        return self.default_number if self.default_number is not None else self.default

    @property
    def is_modified(self) -> bool:
        """值 ≠ 默认值（标定/配置的重点对象）。"""
        return self.value_view != self.default_view

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "name": self.varname,
            "title": self.title,
            "type": self.kind,
            "value": self.value_view,
            "unit": self.units,
            "default": self.default_view,
            "min": self.min,
            "max": self.max,
        }
        if self.enums:
            d["enums"] = [{"value": v, "label": l} for v, l in self.enums]
        if self.declaration is not None:
            # .cir 的 TITLE/UNITS 是权威；.param 提供 Param_Id 与属性
            d["param_id"] = self.declaration.param_id
            d["data_path"] = self.declaration.data_path
            d["declared_title"] = self.declaration.title_raw
            d["attributes"] = self.declaration.attributes
        return d


@dataclass
class Var:
    """``.cir`` 的 IVAR（内部）/ EVAR（外部，按端口分组）。

    两个"保存"概念不同：``save_value`` 是 ``.cir`` 的 SAVE_VALUE 标志
    （该变量**有资格**被保存，子模型层声明）；``saved`` 是 ``.ssf`` 实际
    保存列表的成员（结果提取的前提——Simulation Scripting 的
    ``ameloadvarst`` 只认这个）。两者可能矛盾（实测存在标志 True 但
    未列入保存策略的变量），**取数判据一律以 ``saved`` 为准**。
    """

    varname: str
    title: str
    kind: str                        # internal | external
    alias: str = ""
    units: str = ""
    sub_id: int | None = None
    save_value: bool | None = None   # .cir 标志："可保存"
    saved: bool | None = None        # .ssf 实际保存列表（Linker 回填，权威判据）
    visibility: bool | None = None
    value: str = ""
    dimension: int | None = None
    io: str = ""
    port_tag: str = ""
    port_index: int | None = None    # 外部变量在 EVARS_LIST 中的 1-based 端口序号
    varname2: str = ""

    @property
    def id(self) -> str:
        return f"{self.varname}@{self.alias}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.varname,
            "title": self.title,
            "unit": self.units,
            "kind": self.kind,
            "save": self.save_value,
            "saved": self.saved,
            "value": self.value,
        }


@dataclass
class Port:
    """组件端口。``index`` 为 1-based，与 EVARS_LIST 的 PORT 顺序一致。"""

    index: int
    type: str = ""                   # elect / thermal / signal / ...
    name: str = ""
    tag: str = ""
    connects: list = field(default_factory=list)   # [ConnectRef]


@dataclass
class Submodel:
    """组件绑定的子模型（SUB_NAME + SUB_UNIT 实例号）。"""

    name: str = ""
    instance: int | None = None
    label: str = ""
    dir: str = ""
    params: list = field(default_factory=list)         # [Param]，保序
    internal_vars: list = field(default_factory=list)  # [Var]
    external_vars: list = field(default_factory=list)  # [Var]
    param_groups: list = field(default_factory=list)

    def param(self, varname: str) -> Param | None:
        return next((p for p in self.params if p.varname == varname), None)

    def variable(self, varname: str) -> Var | None:
        for v in self.external_vars:
            if v.varname == varname:
                return v
        for v in self.internal_vars:
            if v.varname == varname:
                return v
        return None


@dataclass
class Component:
    """电路组件（COMP）。"""

    key: ComponentKey
    name: str = ""                   # COMP_NAME
    display_name: str = ""
    icon_description: str = ""
    library_id: str = ""             # COMP_LIBRARY_ID
    position: str = ""
    depth: int | None = None
    scope_id: str = ""               # CIRCUIT_SCOPE_ID
    scope_level: str = "TOP"         # 所属电路层级（"TOP" 或 "SC:<外层scope_id>"）
    ports: list = field(default_factory=list)   # [Port]
    submodel: Submodel | None = None
    is_supercomponent: bool = False
    port_maps: list = field(default_factory=list)
    declared_param_count: int = 0    # Linker 按 (别名,子模型,实例号) 归属统计

    @property
    def alias(self) -> str:
        return self.key.alias

    @property
    def path(self) -> tuple:
        return self.key.path

    @property
    def path_str(self) -> str:
        return " > ".join(self.path)

    def param_id(self, varname: str) -> str:
        return f"{varname}@{self.alias}"

    @property
    def params(self) -> list:
        return self.submodel.params if self.submodel else []

    @property
    def variables(self) -> list:
        if not self.submodel:
            return []
        return [*self.submodel.external_vars, *self.submodel.internal_vars]

    @property
    def modified_params(self) -> list:
        return [p for p in self.params if p.is_modified]

    @property
    def is_plumbing(self) -> bool:
        """纯信号类组件：所有端口都是 signal/空——控制链路"管道"。"""
        types = {p.type for p in self.ports}
        return bool(types) and types <= {"signal", ""}

    def to_dict(self) -> dict:
        sm = self.submodel
        d = {
            "alias": self.alias,
            "name": self.name,
            "display_name": self.display_name,
            "icon_description": self.icon_description,
            "library_id": self.library_id,
            "path": self.path_str,
            "submodel": sm.name if sm else None,
            "submodel_instance": sm.instance if sm else None,
            "ports": [
                {
                    "index": p.index,
                    "type": p.type,
                    "name": p.name,
                    "connects": [[c.entity, c.port] for c in p.connects],
                }
                for p in self.ports
            ],
            "params": [p.to_dict() for p in self.params],
            "variables": [v.to_dict() for v in self.variables],
            "declared_param_count": self.declared_param_count,
        }
        if self.is_supercomponent:
            d["is_supercomponent"] = True
            d["port_maps"] = list(self.port_maps)
        return d


@dataclass
class Line:
    """连线（自带 DIRECT 子模型）。start/end 为 (实体号, 端口号)。"""

    alias: str
    type: str
    points: str
    start: tuple
    end: tuple
    submodel_name: str = ""
    path: tuple = ()

    def to_dict(self) -> dict:
        return {
            "alias": self.alias,
            "path": " > ".join(self.path),
            "type": self.type,
            "start": {"entity": self.start[0], "port": self.start[1]},
            "end": {"entity": self.end[0], "port": self.end[1]},
            "submodel": self.submodel_name,
        }


@dataclass
class Supercomponent:
    """超级组件（子回路）元信息。"""

    name: str
    path: str = ""
    type: str = ""
    category: str = ""
    local: bool | None = None
    port_maps: list = field(default_factory=list)
    extraction_main_element: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "type": self.type,
            "category": self.category,
            "local": self.local,
            "port_maps": list(self.port_maps),
            "extraction_main_element": self.extraction_main_element,
        }


@dataclass
class GlobalParam:
    """一个全局参数（AMESim Global Parameter）。

    同名全局可能在 ``.amegp``/``.cir``/``.pl`` 三处都有定义且取值不一致，
    ``source`` 记录本条来自哪个成员；跨来源分歧由 ``Model`` 汇总进
    ``global_conflicts``，不在这里择一。
    """

    varname: str = ""
    title: str = ""
    value: str = ""
    units: str = ""
    default: str = ""
    min: str = ""
    max: str = ""
    type: str = ""
    source: str = ""                 # ".amegp" | ".cir" | ".pl"

    def to_dict(self) -> dict:
        return {"varname": self.varname, "title": self.title,
                "value": self.value, "units": self.units,
                "default": self.default, "min": self.min, "max": self.max,
                "type": self.type, "source": self.source}


@dataclass
class CircuitModel:
    """整个 ``.cir`` 的解析结果。"""

    doc_version: str = ""
    ame_version: str = ""
    major_version: str = ""
    highest_id: str = ""
    application: str = ""
    components: list = field(default_factory=list)   # [Component]，DFS 序
    lines: list = field(default_factory=list)
    supercomponents: list = field(default_factory=list)
    global_params: list = field(default_factory=list)
    connections: list = field(default_factory=list)  # 原始端口引用（实体空间）

    @property
    def top_level_components(self) -> list:
        return [c for c in self.components if not c.path]

    def alias_map(self) -> dict:
        """(子模型名, 实例号) -> 别名（来自组件表）。"""
        out: dict = {}
        for c in self.components:
            sm = c.submodel
            if sm is not None and sm.name:
                out.setdefault((sm.name, sm.instance), c.alias)
        return out

    def port_map(self) -> dict:
        """别名 -> {端口变量名: 1-based 端口号}（EVARS_LIST 的 PORT 顺序）。"""
        out: dict = {}
        for c in self.components:
            sm = c.submodel
            if sm is None:
                continue
            m = {}
            for v in sm.external_vars:
                if v.port_index is not None:
                    m[v.varname] = v.port_index
            out[c.alias] = m
        return out

    def to_dict(self) -> dict:
        return {
            "doc_version": self.doc_version,
            "ame_version": self.ame_version,
            "components": [c.to_dict() for c in self.components],
            "connections": list(self.connections),
            "lines": [l.to_dict() for l in self.lines],
            "supercomponents": [s.to_dict() for s in self.supercomponents],
            "global_params": [g.to_dict() for g in self.global_params],
        }
