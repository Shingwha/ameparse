"""数据层：纯 dataclass（无 IO / 正则 / 解析）。"""

from .circuit import (
    CircuitModel,
    Component,
    ComponentKey,
    ConnectRef,
    GlobalParam,
    Line,
    Param,
    Port,
    Submodel,
    Supercomponent,
    Var,
    to_bool,
    to_number,
)
from .compiled import CompiledTopology, Instance
from .declarations import Declarations, ParamDecl, VarDecl
from .graph import ConnectionGraph, Edge, PortRef
from .metadata import (
    BatchParam,
    ModelInfo,
    ModelInput,
    ModelOutput,
    Properties,
    PropertyEntry,
    SavedVariable,
    SimOptions,
    StudyParam,
    StudyParams,
    Units,
)

__all__ = [
    "BatchParam", "CircuitModel", "CompiledTopology", "Component", "ComponentKey",
    "ConnectionGraph", "ConnectRef", "Declarations", "Edge", "GlobalParam",
    "Instance", "Line", "ModelInfo", "ModelInput", "ModelOutput", "Param",
    "ParamDecl", "Port", "PortRef", "Properties", "PropertyEntry", "SavedVariable",
    "SimOptions", "StudyParam", "StudyParams", "Submodel", "Supercomponent",
    "Units", "Var", "VarDecl", "to_bool", "to_number",
]
