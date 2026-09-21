"""全局参数引用索引：谁在用这个全局量 + 三类机械可判定的异常。

全局量在 ``.cir`` 里以**裸名**出现在取值中，既可能是整值
（``<VALUE>LF_Gduct_front_air</VALUE>``），也可能是表达式的一部分
（``<VALUE>LF_Mduct_front*LF_duct_surface_fraction</VALUE>``）；参数
（RPARAM/IPARAM/TPARAM）与变量（IVAR/EVAR——`EVAR` 的取值就是状态初值，
例如某个热节点的 ``t2`` 初温写成 ``LF_Tfront_init``）两侧都会出现。

实现上把**全部已定义名一次编译成联合正则**，每个取值只扫一遍
（O(取值数)），而不是每个名字各扫一遍全部取值——后者在 PB62 那种
12073 参数 / 21801 变量 × 233 全局量的规模上会退化。

三类诊断都是机械可判定的，不需要人逐个翻：

- ``undefined_refs``：全局定义里引用了未定义的名（悬空引用，标定会静默
  打到空处）
- ``unused`` ：已定义但无人引用（含"没被任何其他全局引用"）
- ``twins``  ：``X`` 与 ``X__后缀`` 同时存在且取值分歧——封装交付物里的
  重名陷阱：改了一个而另一个没改
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..model.circuit import CircuitModel

# 标识符边界：全局名可含下划线，两侧不能紧邻标识符字符
_BEFORE = r"(?<![A-Za-z0-9_])"
_AFTER = r"(?![A-Za-z0-9_])"

#: 孪生名的分隔符（``SOC_upper_limit__PB62BATTERY_1``）
TWIN_SEP = "__"

#: 表达式里的内建记号（函数/常量/关键字），不算未解析引用
_EXPR_BUILTINS = frozenset({
    "abs", "acos", "asin", "atan", "atan2", "ceil", "cos", "cosh", "exp",
    "floor", "int", "ln", "log", "log10", "max", "min", "mod", "pi", "pow",
    "sgn", "sign", "sin", "sinh", "sqrt", "tan", "tanh", "if", "then",
    "else", "and", "or", "not", "true", "false", "time", "t", "table1d",
    "table2d", "interp", "der", "delay", "step", "ramp", "e",
})


@dataclass(frozen=True)
class GlobalRef:
    """一处引用：某个组件的某个参数或变量的取值里出现了某个全局名。"""

    name: str
    owner_id: str            # 参数/变量的 名称@别名
    alias: str
    kind: str                # "param" | "variable"
    role: str                # "value"（整值）| "expression"（表达式的一部分）
    path: str = ""           # 组件路径（别名可在超组件内外重名）
    expr: str = ""           # role="expression" 时的取值原文

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "owner_id": self.owner_id,
            "alias": self.alias,
            "kind": self.kind,
            "role": self.role,
            "path": self.path,
            "expr": self.expr,
        }


@dataclass
class GlobalRefIndex:
    """全局名 → 引用列表，外加三类诊断。"""

    by_global: dict = field(default_factory=dict)   # name -> [GlobalRef]
    undefined_refs: list = field(default_factory=list)   # 全局定义里引用了未定义的名
    unused: list = field(default_factory=list)      # 已定义但无人引用
    twins: list = field(default_factory=list)       # 同基名且取值分歧

    def refs(self, name: str) -> list:
        return self.by_global.get(name, [])

    def ref_count(self, name: str) -> int:
        return len(self.by_global.get(name, []))

    @property
    def total_refs(self) -> int:
        return sum(len(v) for v in self.by_global.values())

    def summary_dict(self) -> dict:
        """紧凑视图（进模型卡）：每个全局的引用数 + 三类诊断。"""
        return {
            "counts": {n: len(rs) for n, rs in sorted(self.by_global.items())},
            "total_refs": self.total_refs,
            "undefined_refs": list(self.undefined_refs),
            "unused": list(self.unused),
            "twins": list(self.twins),
        }

    def to_dict(self) -> dict:
        """全量视图（CLI 单参数下钻用）：含逐条引用。"""
        return {
            "refs": {n: [r.to_dict() for r in rs]
                     for n, rs in sorted(self.by_global.items())},
            "undefined_refs": list(self.undefined_refs),
            "unused": list(self.unused),
            "twins": list(self.twins),
        }


class GlobalRefResolver:
    """:class:`CircuitModel` + 已定义全局名 → :class:`GlobalRefIndex`。

    ``values`` 必传（``name -> 取值``）：既用于扫描全局之间的引用，也用于
    孪生名取值比对。
    """

    def __init__(self, circuit: CircuitModel, names, values: dict | None = None):
        self._circuit = circuit
        self._names = [n for n in dict.fromkeys(names) if n]
        self._values = values or {}

    # ---------------------------------------------------------------- 解析

    def _pattern(self):
        """全部已定义名 → 一个联合正则（长名优先，避免前缀互相遮挡）。"""
        if not self._names:
            return None
        alts = sorted(self._names, key=len, reverse=True)
        return re.compile(_BEFORE + "(?:" + "|".join(re.escape(n) for n in alts)
                          + ")" + _AFTER)

    def _owner_values(self, comp):
        """产出 ``(owner_id, value, kind)``：参数与变量（含状态初值）。"""
        for p in comp.params:
            yield p.id, p.value, "param"
        for v in comp.variables:
            yield v.id, v.value, "variable"

    def _sites(self):
        """所有引用点：组件参数/变量 + 全局自身的取值（全局之间也会互相引用）。

        ``LF_mtotal_initial`` 的取值就是一条含 ``LF_Qinitial``/``LF_RHevap_initial``
        /``LF_Tevap_initial`` 的表达式——漏掉全局之间的引用，这三个会被误报成
        "定义了却无人引用"。
        """
        for comp in self._circuit.components:
            for owner_id, value, kind in self._owner_values(comp):
                yield comp, owner_id, value, kind
        for name, value in self._values.items():
            yield None, name, value, "global"

    def resolve(self) -> GlobalRefIndex:
        idx = GlobalRefIndex()
        rx = self._pattern()
        defined = set(self._names)
        for comp, owner_id, value, kind in self._sites():
            if not value or rx is None:
                continue
            self._scan(idx, rx, comp, owner_id, value, kind, value.strip())

        idx.undefined_refs = self._undefined_refs(defined)
        idx.unused = sorted(defined - set(idx.by_global))
        idx.twins = self._twins(defined)
        return idx

    def _scan(self, idx, rx, comp, owner_id, value, kind, stripped) -> None:
        for m in rx.finditer(value):
            name = m.group(0)
            role = "value" if stripped == name else "expression"
            idx.by_global.setdefault(name, []).append(
                GlobalRef(name=name, owner_id=owner_id,
                          alias=comp.alias if comp else "",
                          kind=kind, role=role,
                          path=comp.path_str if comp else "",
                          expr="" if role == "value" else value))

    def _undefined_refs(self, defined: set) -> list:
        """全局**定义**里引用了未定义的名。

        只在全局定义的表达式里做 token 级检测，不在组件取值里做：全局定义
        按构造就是数值表达式（``LF_Qinitial/3600*((101300-...)``），出现的
        标识符只能是全局量或内建函数；而组件取值可能是任意字符串——舱体模型
        里 ``materialName@th_solid_data = 'PU'/'steel'``、PB62 里
        ``'Cell_Width'/'Box'`` 都是材料名，token 级扫描会产出几十条噪音，
        把真正的悬空引用埋掉。宁可不报，也不报一堆假的。
        """
        out = []
        for name, value in sorted(self._values.items()):
            if not value:
                continue
            hits = [t for t in _ident_tokens(value)
                    if t not in defined and t not in _EXPR_BUILTINS]
            if hits:
                out.append({"owner": name, "expr": value,
                            "names": sorted(set(hits))})
        return out

    def _twins(self, defined: set) -> list:
        """同基名（``X`` 与 ``X__后缀``）且取值分歧的组。"""
        by_base: dict = {}
        for n in self._names:
            by_base.setdefault(n.split(TWIN_SEP, 1)[0], []).append(n)
        out = []
        for base, members in sorted(by_base.items()):
            if len(members) < 2:
                continue
            vals = {m: self._values.get(m, "") for m in members}
            if len(set(vals.values())) < 2:
                continue
            out.append({
                "base": base,
                "members": [{"name": m, "value": vals[m]} for m in sorted(members)],
            })
        return out


def _ident_tokens(value: str):
    """取值里的标识符记号（不含纯数字）。"""
    for m in re.finditer(r"[A-Za-z_][A-Za-z0-9_.]*", value):
        yield m.group(0)
