"""``.param`` / ``.var`` 声明表数据类（纯数据）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property


@dataclass
class ParamDecl:
    """``.param`` 中的一行参数声明（含元数据，值在 .cir 中）。"""

    submodel: str
    instance: int
    title: str
    unit: str
    param_id: int
    data_path: str
    attributes: dict = field(default_factory=dict)
    title_raw: str = ""

    def to_dict(self) -> dict:
        return {
            "submodel": self.submodel,
            "instance": self.instance,
            "title": self.title,
            "unit": self.unit,
            "param_id": self.param_id,
            "data_path": self.data_path,
            "attributes": self.attributes,
            "title_raw": self.title_raw,
        }


@dataclass
class VarDecl:
    """``.var`` 中的一行变量声明。"""

    submodel: str
    instance: int
    title: str
    unit: str
    data_path: str
    hidden: bool = False

    def to_dict(self) -> dict:
        return {
            "submodel": self.submodel,
            "instance": self.instance,
            "title": self.title,
            "unit": self.unit,
            "data_path": self.data_path,
            "hidden": self.hidden,
        }


@dataclass
class Declarations:
    """``.param`` + ``.var`` 两个声明表的容器与索引。"""

    params: list = field(default_factory=list)     # [ParamDecl]
    variables: list = field(default_factory=list)  # [VarDecl]

    @cached_property
    def params_by_path(self) -> dict:
        """Data_Path（名称@别名）→ ParamDecl；同键后者覆盖（与原实现一致）。"""
        return {d.data_path: d for d in self.params if d.data_path}

    @cached_property
    def params_by_instance(self) -> dict:
        """(子模型, 实例号, Param_Id) → ParamDecl；同键后者覆盖（与原实现一致）。"""
        out: dict = {}
        for d in self.params:
            out[(d.submodel, d.instance, d.param_id)] = d
        return out

    @cached_property
    def hidden_paths(self) -> set:
        """隐藏变量的 Data_Path 集合（``.var`` 的 HIDDEN 段）。"""
        return {d.data_path for d in self.variables if d.hidden}
