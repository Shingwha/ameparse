"""ameparse — `.ame` 模型文件解析器（纯标准库，无需外部软件 / license）。

快速上手::

    from ameparse import Model

    m = Model.from_file("HEV_GWCD_40.ame")
    m.component("BatPackGene")        # 组件对象（重名需 path= 限定）
    m.param("Uinit@BatPackGene")      # 参数（名称@别名，与 ameputp 一致）
    m.neighbors("BatPackGene")        # 连接图查询
    m.to_dict()                       # 全量模型卡 JSON
"""

from .archive import Amefile, Member
from .core import Model, parse_model
from .errors import (
    AmbiguousAlias,
    AmeparseError,
    ArchiveError,
    CirParseError,
    CompiledParseError,
    GraphUnavailable,
    MemberNotFound,
    ParseError,
)
from .model import (
    CircuitModel,
    CompiledTopology,
    Component,
    ComponentKey,
    ConnectionGraph,
    Declarations,
    Edge,
    Param,
    PortRef,
    Submodel,
    Var,
)

__all__ = [
    "AmbiguousAlias", "Amefile", "AmeparseError", "ArchiveError",
    "CircuitModel", "CirParseError", "CompiledParseError", "CompiledTopology",
    "Component", "ComponentKey", "ConnectionGraph", "Declarations", "Edge",
    "GraphUnavailable", "Member", "MemberNotFound", "Model", "Param",
    "ParseError", "PortRef", "Submodel", "Var", "parse_model",
]
__version__ = "0.5.0"
