"""``.cir`` 电路结构解析（v2410，DOC_VERSION=2，XML 风格）。

``.cir`` 不是合法 XML（表达式字段带未转义的 ``&&`` 和 ``<``），
必须走 :mod:`ameparse.tolerant` 的容错扫描器。

``CirParser`` 是端口号语义的唯一转换点之一：组件自身端口序号（1-based，
与 EVARS_LIST 的 PORT 顺序一致）在这里确定；``ConnectRef.port`` 保留
``.cir`` 原文值（目标侧 0-based），1-based 转换发生在 GraphResolver。
"""

from __future__ import annotations

from ..errors import CirParseError
from ..model.circuit import (
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
from ..tolerant import Node, parse


class CirParser:
    """``.cir`` 文本 → :class:`~ameparse.model.circuit.CircuitModel`。"""

    suffix = ".cir"

    def parse(self, text: str) -> CircuitModel:
        root = parse(text)
        cir = root.find("CIR")
        if cir is None:
            raise CirParseError(".cir", "未找到 <CIR> 根元素")
        model = CircuitModel(
            doc_version=cir.attrs.get("DOC_VERSION", ""),
            ame_version=cir.attrs.get("AME_VERSION", ""),
            major_version=cir.attrs.get("MAJ", ""),
        )
        circuit = cir.find("CIRCUIT")
        if circuit is None:
            raise CirParseError(".cir", "未找到 <CIRCUIT>")
        model.highest_id = circuit.text_of("CIRCUIT_HIGHEST_ID")
        model.application = circuit.text_of("AME_APPLICATION")
        self._walk(circuit, (), "TOP", model)
        return model

    # ---------------------------------------------------------------- 元素

    def _param(self, node: Node, kind: str, alias: str) -> Param:
        p = Param(
            varname=node.text_of("VARNAME"),
            title=node.text_of("TITLE"),
            kind=kind,
            alias=alias,
            value=node.text_of("VALUE"),
            default=node.text_of("DEF_VALUE"),
            min=node.text_of("MIN_VALUE"),
            max=node.text_of("MAX_VALUE"),
            units=node.text_of("UNITS"),
            visibility=node.text_of("VISIBILITY"),
            sub_id=to_number(node.text_of("SUB_ID")),
            text_type=node.text_of("TEXT_TYPE"),
            tokens=node.text_of("TOKEN_LIST"),
        )
        enums_node = node.find("ENUM_LIST")
        if enums_node is not None:
            for e in enums_node.findall("ENUM"):
                label = e.text_of("ENUM_STRING")
                p.enums.append((e.text, label))
        return p

    def _var(self, node: Node, kind: str, alias: str,
             port_tag: str = "", port_index: int | None = None) -> Var:
        return Var(
            varname=node.text_of("VARNAME"),
            title=node.text_of("TITLE"),
            kind=kind,
            alias=alias,
            units=node.text_of("UNITS"),
            sub_id=to_number(node.text_of("SUB_ID")),
            save_value=to_bool(node.text_of("SAVE_VALUE")),
            visibility=to_bool(node.text_of("VISIBILITY")),
            value=node.text_of("VALUE"),
            dimension=to_number(node.text_of("DIMENSION")),
            io=node.text_of("IO"),
            port_tag=port_tag,
            port_index=port_index,
            varname2=node.text_of("VARNAME2"),
        )

    def _submodel(self, node: Node, alias: str) -> Submodel:
        sm = Submodel(
            name=node.text_of("SUB_NAME"),
            label=node.text_of("SUB_LABEL"),
            dir=node.text_of("SUB_DIR"),
        )
        inst = to_number(node.text_of("SUB_UNIT"))
        sm.instance = int(inst) if inst is not None else None

        # 同名参数/变量可能出现在不同端口上（实测：output/x 等通用名，
        # 各端口是不同信号）——全部保留，不做 dict 式去重（旧实现会丢数据）
        for key, kind in (("RPARAM", "real"), ("IPARAM", "integer"), ("TPARAM", "text")):
            holder = node.find(f"{key}S_LIST")
            if holder is None:
                continue
            for item in holder.findall(key):
                sm.params.append(self._param(item, kind, alias))

        ivars_node = node.find("IVARS_LIST")
        if ivars_node is not None:
            for item in ivars_node.findall("IVAR"):
                sm.internal_vars.append(self._var(item, "internal", alias))

        evars_node = node.find("EVARS_LIST")
        if evars_node is not None:
            for pi, port in enumerate(evars_node.findall("PORT"), start=1):
                tag = ""
                for ch in port.children:
                    if ch.tag == "PORT_TAG":
                        tag = ch.text
                for item in port.findall("EVAR"):
                    sm.external_vars.append(
                        self._var(item, "external", alias, port_tag=tag, port_index=pi))

        groups = node.find("PARAMS_GROUPS_LIST")
        if groups is not None:
            for g in groups.findall("PARAMS_GROUP"):
                elements = []
                for el in g.iter("PARAM_GROUP_ELEMENT"):
                    elements.append(
                        {
                            "varname": el.text_of("VARNAME"),
                            "display": el.text_of("PARAM_GROUP_ELEMENT_DISPLAY"),
                        }
                    )
                sm.param_groups.append(
                    {
                        "varname": g.text_of("VARNAME"),
                        "title": g.text_of("TITLE"),
                        "elements": elements,
                    }
                )
        return sm

    def _component(self, node: Node, path: tuple, level: str) -> Component:
        alias = node.text_of("ALIAS")
        comp = Component(
            key=ComponentKey(path=path, alias=alias),
            name=node.text_of("COMP_NAME"),
            display_name=node.text_of("COMP_DISPLAYNAME"),
            icon_description=node.text_of("COMP_ICON_DESCRIPTION"),
            library_id=node.text_of("COMP_LIBRARY_ID"),
            position=node.text_of("COMP_POS"),
            depth=to_number(node.text_of("COMP_DEPTH")),
            scope_id=node.text_of("CIRCUIT_SCOPE_ID"),
            scope_level=level,
        )
        ports_node = node.find("COMP_PORTS_LIST")
        if ports_node is not None:
            for i, port_node in enumerate(ports_node.findall("COMP_PORT"), start=1):
                p = Port(
                    index=i,
                    type=port_node.text_of("PORT_TYPE"),
                    name=port_node.text_of("PORT_NAME"),
                    tag=port_node.text_of("PORT_TAG"),
                )
                cl = port_node.find("CONNECT_LIST")
                if cl is not None:
                    for conn in cl.findall("CONNECT"):
                        e = to_number(conn.text_of("CONNECT_ENTITY_NUM"))
                        q = to_number(conn.text_of("CONNECT_ENTITY_PORT"))
                        if e is not None and q is not None:
                            p.connects.append(ConnectRef(int(e), int(q)))
                comp.ports.append(p)

        sm_node = node.find("SUBMODEL")
        if sm_node is not None:
            comp.submodel = self._submodel(sm_node, alias)

        sc = node.find("SUPERCOMPONENT")
        if sc is not None:
            comp.is_supercomponent = True
            for pm in sc.findall("SC_PORTS_MAP_LIST"):
                for entry in pm.findall("SC_PORT_MAP"):
                    comp.port_maps.append(entry.text)
        return comp

    # ---------------------------------------------------------------- 遍历

    def _walk(self, circuit: Node, path: tuple, level: str, model: CircuitModel) -> None:
        comps_node = circuit.find("COMPS_LIST")
        if comps_node is not None:
            for comp_node in comps_node.findall("COMP"):
                comp = self._component(comp_node, path, level)
                model.components.append(comp)
                for p in comp.ports:
                    for c in p.connects:
                        model.connections.append(
                            {"from": [comp.alias, p.index], "to": [c.entity, c.port]}
                        )
                sc = comp_node.find("SUPERCOMPONENT")
                if sc is not None:
                    nested = sc.find("CIRCUIT")
                    ed = sc.find("EXTRACTION_DATA")
                    model.supercomponents.append(
                        Supercomponent(
                            name=comp.alias,
                            path=" > ".join(path),
                            type=sc.text_of("SC_TYPE"),
                            category=sc.text_of("CATNAME"),
                            local=to_bool(sc.text_of("SC_LOCAL")),
                            port_maps=list(comp.port_maps),
                            extraction_main_element=(
                                ed.text_of("MAIN_ELEMENT") if ed is not None else ""
                            ),
                        )
                    )
                    if nested is not None:
                        self._walk(nested, path + (comp.alias,), f"SC:{comp.scope_id}", model)

        lines_node = circuit.find("LINES_LIST")
        if lines_node is not None:
            for line_node in lines_node.findall("LINE"):
                start = (
                    to_number(line_node.text_of("LINE_START_ENTITY")),
                    to_number(line_node.text_of("LINE_START_PORT")),
                )
                end = (
                    to_number(line_node.text_of("LINE_END_ENTITY")),
                    to_number(line_node.text_of("LINE_END_PORT")),
                )
                sm = line_node.find("SUBMODEL")
                model.lines.append(
                    Line(
                        alias=line_node.text_of("ALIAS"),
                        type=line_node.text_of("LINE_TYPE"),
                        points=line_node.text_of("LINE_POINTS"),
                        start=(int(start[0]), int(start[1])),
                        end=(int(end[0]), int(end[1])),
                        submodel_name=sm.text_of("SUB_NAME") if sm is not None else "",
                        path=path,
                    )
                )

        gp_node = circuit.find("GLOBAL_PARAMS_LIST")
        if gp_node is not None:
            for gp in gp_node.iter("GPARAM"):
                model.global_params.append(
                    GlobalParam(
                        varname=gp.text_of("VARNAME"),
                        title=gp.text_of("TITLE"),
                        value=gp.text_of("VALUE"),
                        units=gp.text_of("UNITS"),
                    )
                )


def parse_cir(text: str) -> CircuitModel:
    """解析 ``.cir`` 文本（单步工具快捷方式）。"""
    return CirParser().parse(text)
