"""元信息数据类：``.modelinfo`` / ``.sim`` / ``.studyparam`` / ``.units`` /
``.props/properties.xml`` / ``.ssf`` / ``.amegp``（纯数据）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ModelOutput:
    index: int
    external_name: str = ""
    data_path: str = ""

    def to_dict(self) -> dict:
        return {"index": self.index, "external_name": self.external_name,
                "data_path": self.data_path}


@dataclass
class ModelInput:
    index: int
    external_name: str = ""
    data_path: str = ""
    start_value: str = ""

    def to_dict(self) -> dict:
        return {"index": self.index, "external_name": self.external_name,
                "data_path": self.data_path, "start_value": self.start_value}


@dataclass
class ModelInfo:
    """``.modelinfo``：状态数 + Simulink 接口输入输出表。

    无 ``INTERFACE`` 字段的是无外部接口的纯模型。
    """

    states: int | None = None
    discrete_states: int | None = None
    is_explicit: bool | None = None
    interface: str = ""
    inputs: list = field(default_factory=list)    # [ModelInput]
    outputs: list = field(default_factory=list)   # [ModelOutput]

    def to_dict(self) -> dict:
        return {
            "states": self.states,
            "discrete_states": self.discrete_states,
            "is_explicit": self.is_explicit,
            "interface": self.interface,
            "inputs": [i.to_dict() for i in self.inputs],
            "outputs": [o.to_dict() for o in self.outputs],
        }


@dataclass
class SimOptions:
    """``.sim``：仿真选项（两行数字）。

    已确认映射（v2410 布局）：第一行前三个字段 = start_time /
    final_time / print_interval。其余字段含义随版本变化未确认（第一行
    第 5 个数值疑似积分容差），统一放 ``values``（两行的数值列表，可按
    下标访问），原文完整保留在 ``raw``。**不猜名字：未确认字段不给名**。
    """

    raw: list = field(default_factory=list)
    values: list = field(default_factory=list)   # [[float, ...], [float, ...]]
    start_time: float | None = None
    final_time: float | None = None
    print_interval: float | None = None

    def to_dict(self) -> dict:
        d: dict = {"raw": list(self.raw)}
        if self.start_time is not None:
            d["start_time"] = self.start_time
        if self.final_time is not None:
            d["final_time"] = self.final_time
        if self.print_interval is not None:
            d["print_interval"] = self.print_interval
        return d


@dataclass
class StudyParam:
    """``.studyparam`` 中的一个研究参数（含上下界，评测任务卡用）。"""

    name: str = ""
    value: str = ""
    upper_bound: str = ""
    lower_bound: str = ""
    origin: str = ""
    type: str = ""
    amesim_name: str = ""
    title: str = ""
    submodel: str = ""
    instance: str = ""
    alias_path: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "value": self.value,
            "upper_bound": self.upper_bound,
            "lower_bound": self.lower_bound,
            "origin": self.origin,
            "type": self.type,
            "amesim_name": self.amesim_name,
            "title": self.title,
            "submodel": self.submodel,
            "instance": self.instance,
            "alias_path": self.alias_path,
        }


@dataclass
class BatchParam:
    """批量运行参数（取值集合）。"""

    name: str = ""
    unit: str = ""
    range_value: str = ""
    set_values: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "unit": self.unit,
                "range_value": self.range_value, "set_values": list(self.set_values)}


@dataclass
class StudyParams:
    study_params: list = field(default_factory=list)   # [StudyParam]
    batch_params: list = field(default_factory=list)   # [BatchParam]

    def to_dict(self) -> dict:
        return {
            "study_params": [s.to_dict() for s in self.study_params],
            "batch_params": [b.to_dict() for b in self.batch_params],
        }


@dataclass
class Units:
    """``.units``：单位制配置摘要。"""

    active_configuration_id: str = ""
    configuration_name: str = ""
    domains: int = 0
    unit_definitions: int = 0

    def to_dict(self) -> dict:
        return {
            "active_configuration_id": self.active_configuration_id,
            "configuration_name": self.configuration_name,
            "domains": self.domains,
            "unit_definitions": self.unit_definitions,
        }


@dataclass
class PropertyEntry:
    id: str = ""
    name: str = ""
    target: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "target": self.target}


@dataclass
class Properties:
    """``.props/properties.xml``：模型属性表。"""

    entries: list = field(default_factory=list)   # [PropertyEntry]

    @property
    def count(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict:
        return {"properties": [e.to_dict() for e in self.entries],
                "count": self.count}


@dataclass
class SavedVariable:
    """``.ssf``（save strategy）中的一行：在模型 save 列表里的变量，
    是 ``ameloadvarst`` 能取数的前提。"""

    data_path: str = ""
    title: str = ""
    unit: str = ""
    submodel: str = ""
    instance: int = 0
    param_id: int = 0
    flag: int | None = None
    attributes: dict = field(default_factory=dict)
    title_raw: str = ""

    @property
    def alias(self) -> str:
        return self.data_path.split("@", 1)[-1] if "@" in self.data_path else ""

    @property
    def varname(self) -> str:
        return self.data_path.split("@", 1)[0] if "@" in self.data_path else self.data_path

    def to_dict(self) -> dict:
        return {
            "data_path": self.data_path,
            "title": self.title,
            "unit": self.unit,
            "submodel": self.submodel,
            "instance": self.instance,
            "param_id": self.param_id,
        }
