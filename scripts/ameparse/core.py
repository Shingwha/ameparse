"""``Model`` 门面：一个 ``.ame`` 的完整解析结果与查询 API。

用法::

    from ameparse import Model

    m = Model.from_file("HEV_GWCD_40.ame")
    pack = m.component("BatPackGene")          # Component 对象
    m.param("Uinit@BatPackGene")               # 按 名称@别名 查参数
    m.neighbors("BatPackGene")                 # 图查询（触发 .c 懒解析）
    m.to_dict()                                # 全量模型卡 JSON

加载边界：``.cir`` 与各小成员在构造时 eager 解析（快）；
``compiled`` / ``graph`` 依赖 ``.c`` 编译产物，首次访问才解析——
纯查参数/变量的场景不为连接图买单。

模型卡 JSON schema 见 ``to_dict`` docstring；schema 键结构是下游
（知识库/评测任务卡）的数据契约，只增不改。
"""

from __future__ import annotations

from pathlib import Path

from .archive import Amefile, Member
from .errors import (
    AmbiguousAlias,
    ArchiveError,
    GraphUnavailable,
    MemberNotFound,
)
from .linking import GraphResolver, Linker
from .model.circuit import CircuitModel, Component, Param, Var
from .model.compiled import CompiledTopology
from .model.declarations import Declarations
from .model.graph import ConnectionGraph
from .model.metadata import (
    ModelInfo,
    Properties,
    SavedVariable,
    SimOptions,
    StudyParams,
    Units,
)
from .parsers import (
    MEMBER_PARSERS,
    AmegpParser,
    CirParser,
    CompiledParser,
    ModelInfoParser,
    ParamFileParser,
    PropertiesParser,
    SimParser,
    SsfParser,
    StudyParamParser,
    UnitsParser,
    VarFileParser,
)

# 模型卡 schema 版本（键结构变更时递增）
SCHEMA_VERSION = 1

# .ame 内体积大且与模型结构无关的成员（.c 单独按需读取，不在此列报错，
# 但同样不进 archive_members 清单）
SKIP_MEMBER_SUFFIXES = (".results", ".mexw64", ".obj", ".c", ".ameperf", ".png")

_UNSET = object()


class Model:
    """一个 ``.ame`` 模型的完整解析结果。"""

    # ---------------------------------------------------------------- 加载

    @classmethod
    def from_file(cls, path) -> "Model":
        try:
            ame = Amefile(path)
        except Exception as e:  # tarfile.ReadError / OSError 等
            raise ArchiveError(f"cannot open {path}: {e}") from e
        with ame:
            return cls.from_archive(ame, source_path=path)

    @classmethod
    def from_archive(cls, ame: Amefile, source_path=None) -> "Model":
        """从已打开的 :class:`Amefile` 构造（读完全部所需成员后关闭归档）。"""
        m = cls.__new__(cls)
        m._init(ame, source_path)
        return m

    def _init(self, ame: Amefile, source_path=None) -> None:
        self.source_path = Path(source_path) if source_path is not None else None
        self.graph_error: str | None = None

        # 成员文本一次读完（含 .c 的文本；.c 的解析推迟到首次访问）
        texts: dict = {}
        for suffix in MEMBER_PARSERS:
            t = ame.read_text(suffix)
            if t is not None:
                texts[suffix] = t
        self._c_text = ame.read_text(".c")
        self._archive_members = [
            m for m in ame.members()
            if not m.name.lower().endswith(SKIP_MEMBER_SUFFIXES)
        ]
        self.name = ame.model_name or (
            self.source_path.stem if self.source_path is not None else ""
        )

        cir_text = texts.get(".cir")
        if cir_text is None:
            raise MemberNotFound(
                f"{self.source_path or '<archive>'}: no .cir member found "
                "(not a valid .ame)"
            )
        self._circuit: CircuitModel = CirParser().parse(cir_text)

        self._declarations = Declarations(
            params=ParamFileParser().parse(texts.get(".param") or ""),
            variables=VarFileParser().parse(texts.get(".var") or ""),
        )
        self._saved_variables = SsfParser().parse(texts.get(".ssf") or "")
        linker = Linker(
            self._declarations,
            saved_paths={s.data_path for s in self._saved_variables},
        )
        linker.link(self._circuit)
        self._alias_of = linker.alias_map()

        self._model_info: ModelInfo = ModelInfoParser().parse(
            texts.get(".modelinfo") or "")
        self._simulation: SimOptions = SimParser().parse(texts.get(".sim") or "")
        self._study: StudyParams = StudyParamParser().parse(
            texts.get(".studyparam") or "")
        self._units: Units = UnitsParser().parse(texts.get(".units") or "")
        props_text = texts.get("properties.xml")
        self._properties = PropertiesParser().parse(props_text) if props_text else None
        self._global_params = AmegpParser().parse(texts.get(".amegp") or "")

        self._compiled = _UNSET
        self._graph = _UNSET

    # ---------------------------------------------------------------- 节

    @property
    def circuit(self) -> CircuitModel:
        return self._circuit

    @property
    def declarations(self) -> Declarations:
        return self._declarations

    @property
    def model_info(self) -> ModelInfo:
        return self._model_info

    @property
    def simulation(self) -> SimOptions:
        return self._simulation

    @property
    def study(self) -> StudyParams:
        return self._study

    @property
    def units(self) -> Units:
        return self._units

    @property
    def properties(self):
        """Properties | None（成员缺失时为 None，序列化为 {}）。"""
        return self._properties

    @property
    def global_params(self) -> list:
        return self._global_params

    @property
    def saved_variables(self) -> list:
        """保存变量清单（ameloadvarst 可取数的前提）。"""
        return self._saved_variables

    @property
    def archive_members(self) -> list:
        return self._archive_members

    @property
    def ame_version(self) -> str:
        return self._circuit.ame_version

    @property
    def compiled(self):
        """编译态拓扑（CompiledTopology | None）。首次访问才解析 ``.c``。"""
        if self._compiled is _UNSET:
            self._compiled = None
            if self._c_text:
                try:
                    topo = CompiledParser().parse(self._c_text)
                    topo.attach_ports(self._alias_of, self._circuit.port_map())
                    self._compiled = topo
                except Exception as e:  # noqa: BLE001
                    self.graph_error = f"compiled topology parse failed: {e}"
        return self._compiled

    @property
    def graph(self):
        """别名级连接图（ConnectionGraph | None）。

        不可用（无 ``.c`` 或解析失败）时返回 None，原因见 ``graph_error``——
        可预期的缺失不是异常。
        """
        if self._graph is _UNSET:
            self._graph = None
            topo = self.compiled
            if topo is not None:
                try:
                    self._graph = GraphResolver(self._circuit, topo).resolve()
                except Exception as e:  # noqa: BLE001
                    self.graph_error = f"connection graph resolution failed: {e}"
        return self._graph

    def _require_graph(self) -> ConnectionGraph:
        g = self.graph
        if g is None:
            raise GraphUnavailable(self.graph_error or "connection graph unavailable")
        return g

    # ---------------------------------------------------------------- 组件

    def component(self, alias: str, *, path=None) -> Component:
        """按别名取组件；别名重复时抛 :class:`AmbiguousAlias`，
        用 ``path="SC名 > 子SC名"`` 限定（顶层为 ``path=""``）。"""
        key_path = None
        if path is not None:
            if isinstance(path, str):
                key_path = () if path == "" else tuple(path.split(" > "))
            else:
                key_path = tuple(path)
        matches = [
            c for c in self._circuit.components
            if c.alias == alias and (key_path is None or c.path == key_path)
        ]
        if not matches:
            raise KeyError(f"component not found: {alias}"
                           + (f" (path={' > '.join(key_path)})" if key_path else ""))
        if len(matches) > 1:
            raise AmbiguousAlias(
                f"alias {alias!r} matches {len(matches)} components "
                "(duplicated inside/outside supercomponents); qualify with path=; "
                "candidates: "
                + ", ".join(repr(c.path_str) for c in matches)
            )
        return matches[0]

    def components(self, *, alias=None, submodel=None, library_id=None,
                   top_level=None, supercomponent=None) -> list:
        """组件过滤查询（保持 DFS 序）。"""
        out = self._circuit.components
        if alias is not None:
            out = [c for c in out if c.alias == alias]
        if submodel is not None:
            out = [c for c in out if c.submodel is not None
                   and c.submodel.name == submodel]
        if library_id is not None:
            out = [c for c in out if c.library_id == library_id]
        if top_level is not None:
            out = [c for c in out if (not c.path) == bool(top_level)]
        if supercomponent is not None:
            out = [c for c in out if c.is_supercomponent == bool(supercomponent)]
        return list(out)

    def submodel_distribution(self) -> dict:
        """子模型名 -> 实例数（子模型名是知识库手册页的检索键）。"""
        dist: dict = {}
        for c in self._circuit.components:
            if c.submodel is not None:
                dist[c.submodel.name] = dist.get(c.submodel.name, 0) + 1
        return dist

    # ---------------------------------------------------------------- 参数/变量

    def param(self, qualified_id: str) -> Param:
        """按 ``名称@别名`` 取参数（与 ``ameputp`` 标识一致）。"""
        matches = [p for c in self._circuit.components if c.submodel is not None
                   for p in c.submodel.params if p.id == qualified_id]
        if not matches:
            raise KeyError(f"parameter not found: {qualified_id}")
        if len(matches) > 1:
            raise AmbiguousAlias(
                f"{qualified_id!r} matches {len(matches)} parameters (duplicated alias)")
        return matches[0]

    def params(self, *, component=None, submodel=None,
               modified_only=False) -> list:
        """参数过滤查询。component 接受别名或 Component。"""
        comps = self._component_scope(component, submodel)
        out = [p for c in comps for p in c.params]
        if modified_only:
            out = [p for p in out if p.is_modified]
        return out

    def variable(self, qualified_id: str) -> Var:
        matches = [v for c in self._circuit.components if c.submodel is not None
                   for v in c.variables if v.id == qualified_id]
        if not matches:
            raise KeyError(f"variable not found: {qualified_id}")
        if len(matches) > 1:
            raise AmbiguousAlias(
                f"{qualified_id!r} matches {len(matches)} variables "
                "(same varname on several ports)")
        return matches[0]

    def variables(self, *, component=None, submodel=None, kind=None, saved=None,
                  hidden=None) -> list:
        """变量过滤查询。

        kind: internal/external；hidden: bool（.var 的 HIDDEN 段）；
        ``saved``: bool——**以 .ssf 实际保存列表为准**（ameloadvarst 可取数
        判据），不是 ``Var.save_value`` 标志（那是"可保存"声明，可能矛盾）。
        """
        comps = self._component_scope(component, submodel)
        out = [v for c in comps for v in c.variables]
        if kind is not None:
            out = [v for v in out if v.kind == kind]
        if saved is not None:
            out = [v for v in out if bool(v.saved) == bool(saved)]
        if hidden is not None:
            hidden_paths = self._declarations.hidden_paths
            out = [v for v in out if (v.id in hidden_paths) == bool(hidden)]
        return out

    def _component_scope(self, component, submodel):
        if component is None:
            if submodel is None:
                return self._circuit.components
            return self.components(submodel=submodel)
        comp = component if isinstance(component, Component) else self.component(component)
        return [comp]

    # ---------------------------------------------------------------- 图查询

    def neighbors(self, alias: str, port: int | None = None):
        """邻居：``port=None`` 返回 {端口号: [PortRef]}，否则返回该端口列表。"""
        return self._require_graph().neighbors(alias, port)

    def subgraph(self, alias: str, hops: int = 1) -> list:
        """从 alias 出发 hops 跳内的组件（图切分/子回路拆分的基础）。"""
        names = self._require_graph().subgraph(alias, hops)
        return [c for c in self._circuit.components if c.alias in names]

    def subcircuits(self) -> list:
        """连通分量（组件列表的列表，按规模降序）。"""
        groups = self._require_graph().subcircuits()
        groups.sort(key=len, reverse=True)
        return [[c for c in self._circuit.components if c.alias in g] for g in groups]

    def path(self, a: str, b: str):
        """两组件间的连接路径（别名序列，BFS 最短）；不可达返回 None。"""
        return self._require_graph().shortest_path(a, b)

    # ---------------------------------------------------------------- 统计与序列化

    @property
    def counts(self) -> dict:
        circuit = self._circuit
        return {
            "components": len(circuit.components),
            "top_level_components": len(circuit.top_level_components),
            "supercomponents": len(circuit.supercomponents),
            "lines": len(circuit.lines),
            "connections": len(circuit.connections),
            "params": sum(len(c.params) for c in circuit.components),
            "variables": sum(len(c.variables) for c in circuit.components),
            "declared_params": len(self._declarations.params),
            "declared_variables": len(self._declarations.variables),
            "saved_variables": len(self._saved_variables),
        }

    def to_dict(self) -> dict:
        """全量模型卡 JSON（schema 见模块 docstring；结构是下游数据契约）。"""
        circuit = self._circuit
        components = [c.to_dict() for c in circuit.components]

        graph = self.graph
        if graph is not None:
            graph_section = graph.to_dict()
        else:
            graph_section = {"available": False}
            if self.graph_error:
                graph_section["error"] = self.graph_error

        saved_paths = {s.data_path for s in self._saved_variables}

        notes = [
            "Entity numbers are an artifact of model creation order and are not "
            "stored explicitly; connections/lines keep the raw entity numbers.",
            "The graph section is the alias-level connection graph, resolved from "
            ".cir references plus compiled topology (.c SUBSTRUC/EVIA shared "
            "slots); edges are [alias, port].",
            "Parameter values come from .cir (RPARAM/IPARAM/TPARAM VALUE); "
            "titles/units/Param_Id are merged from .param declarations keyed by "
            "Data_Path=name@alias.",
        ]
        if graph is None:
            notes.append("graph unavailable (no compiled .c product or resolution "
                         "failed): " + (self.graph_error or "unknown reason"))

        return {
            "schema_version": SCHEMA_VERSION,
            "model": self.name,
            "ame_version": circuit.ame_version,
            "doc_version": circuit.doc_version,
            "generator": {
                "application": circuit.application,
                "major_version": circuit.major_version,
            },
            "counts": self.counts,
            "components": components,
            "connections": circuit.connections,
            "graph": graph_section,
            "lines": [l.to_dict() for l in circuit.lines],
            "supercomponents": [s.to_dict() for s in circuit.supercomponents],
            "global_params": [g.to_dict() for g in self._global_params],
            "simulation": self._simulation.to_dict(),
            "study_params": [s.to_dict() for s in self._study.study_params],
            "batch_params": [b.to_dict() for b in self._study.batch_params],
            "model_io": self._model_info.to_dict(),
            "saved_variables": [s.to_dict() for s in self._saved_variables],
            "declared_params": [d.to_dict() for d in self._declarations.params],
            "declared_variables": [
                {**v.to_dict(), "saved": v.data_path in saved_paths}
                for v in self._declarations.variables
            ],
            "units": self._units.to_dict(),
            "properties": self._properties.to_dict() if self._properties else {},
            "archive_members": [m.to_dict() for m in self._archive_members],
            "notes": notes,
        }

    def to_compact_dict(self) -> dict:
        """紧凑 model card（Tool 返回形态：组件/参数/变量/连接图的精简子集）。"""
        from .export import compact_card
        return compact_card(self)

    def to_csv(self, out_dir) -> dict:
        """导出参数表/变量表 CSV，返回 {类型: 路径}。"""
        return write_csv_tables(self, out_dir)


def parse_model(path) -> Model:
    """解析一个 ``.ame``（``Model.from_file`` 的快捷方式）。"""
    return Model.from_file(path)


def write_csv_tables(model: Model, out_dir) -> dict:
    from pathlib import Path as _P
    out = _P(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    from .export import write_param_csv, write_var_csv
    p = out / f"{model.name}.params.csv"
    v = out / f"{model.name}.variables.csv"
    write_param_csv(model, p)
    write_var_csv(model, v)
    return {"params": p, "variables": v}
