"""元信息类成员解析：``.modelinfo`` / ``.sim`` / ``.studyparam`` / ``.units`` /
``.props/properties.xml``。

全局参数（``.amegp``/``.cir``/``.pl`` 三源）在 :mod:`.globals` 里统一处理。
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from ..model.metadata import (
    BatchParam,
    ModelInfo,
    ModelInput,
    ModelOutput,
    Properties,
    PropertyEntry,
    SimOptions,
    StudyParam,
    StudyParams,
    Units,
)
from ..tolerant import iter_local, parse as parse_tolerant

# 头部字段可能换行书写，独立匹配；无 INTERFACE 的是无外部接口的纯模型
_OUTPUT_RE = re.compile(r'OUTPUT\s+(\d+)\s*;\s*"([^"]*)"\s*;\s*"([^"]*)"')
_INPUT_RE = re.compile(
    r'INPUT\s+(\d+)\s*;\s*"([^"]*)"\s*;\s*"([^"]*)"\s*;\s*"([^"]*)"'
)


def _xml_root(text: str):
    """合法 XML 走 ElementTree，失败退回容错解析（两者接口兼容）。"""
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        return parse_tolerant(text)


class ModelInfoParser:
    """``.modelinfo`` → ModelInfo（状态数 + Simulink 接口输入输出表）。"""

    suffix = ".modelinfo"

    def parse(self, text: str) -> ModelInfo:
        info = ModelInfo()
        for key, attr, conv in (
            ("NUM_STATES", "states", int),
            ("NUM_DISCRETE_STATES", "discrete_states", int),
            ("IS_EXPLICIT", "is_explicit", lambda v: bool(int(v))),
        ):
            m = re.search(rf"\b{key}\s+(\d+)", text)
            if m:
                setattr(info, attr, conv(m.group(1)))
        m = re.search(r'\bINTERFACE\s+"([^"]*)"', text)
        if m:
            info.interface = m.group(1)
        for m in _OUTPUT_RE.finditer(text):
            info.outputs.append(
                ModelOutput(index=int(m.group(1)), external_name=m.group(2),
                            data_path=m.group(3))
            )
        for m in _INPUT_RE.finditer(text):
            info.inputs.append(
                ModelInput(index=int(m.group(1)), external_name=m.group(2),
                           data_path=m.group(3), start_value=m.group(4))
            )
        return info


class SimParser:
    """``.sim`` → SimOptions（两行数字；final_time/print_interval 按前三个字段）。"""

    suffix = ".sim"

    def parse(self, text: str) -> SimOptions:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        nums = [ln.split() for ln in lines]
        opts = SimOptions(raw=lines,
                          values=[[float(x) for x in row] for row in nums])
        if len(nums) >= 1 and len(nums[0]) >= 3:
            opts.start_time = float(nums[0][0])
            opts.final_time = float(nums[0][1])
            opts.print_interval = float(nums[0][2])
        return opts


class StudyParamParser:
    """``.studyparam`` → StudyParams（研究/批量参数，含上下界）。"""

    suffix = ".studyparam"

    def parse(self, text: str) -> StudyParams:
        root = _xml_root(text)
        out = StudyParams()
        for sp in root.iter("STUDY_PARAM"):
            out.study_params.append(
                StudyParam(
                    name=sp.findtext("STUDY_PARAM_NAME", ""),
                    value=sp.findtext("VALUE", ""),
                    upper_bound=sp.findtext("UPPER_BOUND", ""),
                    lower_bound=sp.findtext("LOWER_BOUND", ""),
                    origin=sp.findtext("ORIGIN", ""),
                    type=sp.findtext("PARAM_TYPE", ""),
                    amesim_name=sp.findtext("AMESIM_NAME", ""),
                    title=sp.findtext("TITLE", ""),
                    submodel=sp.findtext("SUB_NAME", ""),
                    instance=sp.findtext("INSTANCE", ""),
                    alias_path=sp.findtext("ALIAS_PATH", ""),
                )
            )
        for bp in root.iter("PARAM"):
            if bp.findtext("PARAM_NAME") is None:
                continue
            out.batch_params.append(
                BatchParam(
                    name=bp.findtext("PARAM_NAME", ""),
                    unit=bp.findtext("PARAM_UNIT", ""),
                    range_value=bp.findtext("RANGE_VALUE", ""),
                    set_values=[e.text or "" for e in bp if e.tag == "SET_VALUE"],
                )
            )
        return out


class UnitsParser:
    """``.units`` → Units（单位制配置摘要）。"""

    suffix = ".units"

    def parse(self, text: str) -> Units:
        root = _xml_root(text)
        cfg = next(root.iter("Configuration_Definition"), None)
        return Units(
            active_configuration_id=root.attrib.get("Active_Configuration_Id", ""),
            configuration_name=cfg.attrib.get("Name", "") if cfg is not None else "",
            domains=len(cfg.findall("Domain_Definition")) if cfg is not None else 0,
            unit_definitions=len(list(root.iter("Unit_Definition"))),
        )


class PropertiesParser:
    """``.props/properties.xml`` → Properties。

    真实文件根节点带 ``xmlns="amesim-property-instances"``，ET 展开后标签是
    ``{amesim-property-instances}property``，因此必须按 local name 匹配
    （``iter_local``）——直接 ``iter("property")`` 会一条都找不到，把整张
    属性表静默报成空。``sticker`` 属性是模型作者标的置信度贴纸
    （Low confidence / High importance）。
    """

    suffix = "properties.xml"

    def parse(self, text: str) -> Properties:
        root = _xml_root(text)
        props = Properties()
        for p in iter_local(root, "property"):
            props.entries.append(
                PropertyEntry(
                    id=p.attrib.get("id", ""),
                    name=p.attrib.get("name", ""),
                    target=p.attrib.get("target", ""),
                    sticker=p.attrib.get("sticker", ""),
                )
            )
        return props


def parse_modelinfo(text: str) -> ModelInfo:
    return ModelInfoParser().parse(text)


def parse_sim(text: str) -> SimOptions:
    return SimParser().parse(text)


def parse_studyparam(text: str) -> StudyParams:
    return StudyParamParser().parse(text)


def parse_units(text: str) -> Units:
    return UnitsParser().parse(text)


def parse_properties(text: str) -> Properties:
    return PropertiesParser().parse(text)
