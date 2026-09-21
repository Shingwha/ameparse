# Python API 参考

> 面向使用的对象级 API 参考。架构与类设计理由见 `DESIGN.md`；
> 命令行用法见根目录 `SKILL.md`。

## 装载

```python
from ameparse import Model

m = Model.from_file("model.ame")          # 亦可用 Amefile + Model.from_archive
m.name, m.ame_version                     # "HEV_GWCD_40", "2410"
m.source_path                             # Path | None
```

加载边界：`.cir` 与各小成员构造时 eager 解析（快）；`compiled`（`.c` 编译态
拓扑）与 `graph`（别名级连接图）**懒加载**——纯查参数/变量的场景不为连接图
买单：:

```python
m.compiled                                # CompiledTopology | None（首次访问才解析 .c）
m.graph                                   # ConnectionGraph | None
m.graph_error                             # 不可用原因（无 .c / 解析失败）；None 表示无异常
```

不可用是**可预期状态不是异常**：`graph` 为 `None`；查询方法（neighbors 等）
需要图时抛 `GraphUnavailable`。

## 节（sections）

| 属性 | 类型 | 内容 |
|---|---|---|
| `m.circuit` | `CircuitModel` | 全部组件（DFS 序）、连线、超级组件、全局参数、原始连接表 |
| `m.declarations` | `Declarations` | `.param` / `.var` 全量声明（含索引） |
| `m.model_info` | `ModelInfo` | 状态数、Simulink/外部接口输入输出 |
| `m.simulation` | `SimOptions` | 起止时间 / 打印间隔 + `values`（按下标取未确认字段）+ `raw` |
| `m.study` | `StudyParams` | 研究/批量参数（含上下界） |
| `m.units` / `m.properties` | `Units` / `Properties \| None` | 单位配置、属性实例 |
| `m.global_params` | `[GlobalParam]` | 全局参数（`.amegp`/`.cir`/`.pl` 三源合并，`source` 标明交付值来源） |
| `m.global_conflicts` | `[dict]` | 同名全局的跨来源取值分歧（不静默择一） |
| `m.global_param(name)` | `GlobalParam` | 单个全局量；不存在抛 `KeyError` |
| `m.refs` | `GlobalRefIndex` | 引用索引（懒解析，只需 `.cir`，不依赖 `.c`） |
| `m.global_ref_summary()` | `dict` | 引用计数 + `unused`/`twins`/`undefined_refs` |
| `m.saved_variables` | `[SavedVariable]` | `.ssf` 保存清单（`ameloadvarst` 可取数判据） |
| `m.archive_members` | `[Member]` | tar 成员清单（列出全部成员；只有解析是白名单制） |
| `m.counts` | `dict` | 组件/参数/变量/边/全局量/属性等统计 |

`GlobalRefIndex`：`refs(name)` → `[GlobalRef]`，`ref_count(name)`，
`total_refs`，以及 `summary_dict()` / `to_dict()` 两种视图。
`GlobalRef` 字段：`name` / `owner_id`（`名称@别名`）/ `alias` / `kind`
（`param`/`variable`/`global`）/ `role`（`value` 整值 / `expression` 表达式）/
`path`（组件路径，别名可重名）/ `expr`。
变量命中要读成**该状态初值**被这个全局量驱动——这是"这个旋钮影响哪些状态"的
直接答案。

## 组件查询

```python
m.component("BatPackGene")                    # Component；重名抛 AmbiguousAlias
m.component("BatPackGene", path="SC名 > 子SC名")   # 用超级组件链消歧（path="" 为顶层）
m.components(submodel="ESSBATPA01")           # 过滤：alias/submodel/library_id/
                                              #   top_level/supercomponent
m.submodel_distribution()                     # 子模型名 → 实例数（知识库检索键）
```

**组件唯一键**是 `(path, alias)`（别名会在超级组件内外重复）——`Component.key`
即此结构，`c.alias` / `c.path` / `c.path_str` 为便捷访问。

## 参数 / 变量查询

```python
m.param("Uinit@BatPackGene")                  # Param（名称@别名，与 ameputp 一致）
m.params(component="BatPackGene",             # 过滤：component/submodel/modified_only
         modified_only=True)
m.variable("q1@pump01")                       # Var
m.variables(component="BatPackGene",          # 过滤：component/submodel/kind/
            saved=True, hidden=None)          #   saved/hidden
```

**两个 "saved" 语义不同**（实测可能矛盾，务必区分）：

| 字段 | 含义 | 用途 |
|---|---|---|
| `v.save_value` | `.cir` 的 SAVE_VALUE 标志（"**有资格**被保存"，子模型层声明） | 改 save 列表时的候选池 |
| `v.saved` | `.ssf` 实际保存列表的成员（Linker 回填） | **取数判据**：`ameloadvarst` 只认这个 |

`m.variables(saved=True)` 按后者过滤；`.cir` 标志用 `variables()` 后再按
`v.save_value` 筛（CLI 对应 `--saved` / `--save-flag`）。

`Param` 便捷属性：`p.id`（名称@别名）、`p.number`（数值化）、`p.value_view`
（序列化值）、`p.is_modified`（值 ≠ 默认值）、`p.declaration`（合并的
`.param` 声明，含 `param_id`/属性）。

## 图查询

```python
m.neighbors("BatPackGene")                    # {端口号: [PortRef]}（首个访问触发 .c 解析）
m.neighbors("BatPackGene", port=1)            # 单端口邻居
m.subgraph("BatPackGene", hops=2)             # 周围 N 跳的组件（局部图）
m.subcircuits()                               # 连通分量（按规模降序）
m.path("BatPackGene", "vehicle")              # 两组件间最短路径（别名序列）| None

g = m.graph                                   # ConnectionGraph
g.edges()                                     # [Edge]（含 a_type/b_type 端口域）
g.edges(domain="thermal")                     # 按端口域过滤（elect/thermal/signal/...）
g.shortest_path("a", "b")
g.stats                                       # 解析统计（groups/wires/nets/edges/...）
```

端口一律 1-based；`Edge.a_type`/`b_type` 是两端端口类型（来自组件端口表）。
整车模型的连通分量常是"一个大团"（域耦合），回路级分析请配合 `domain=` 过滤。

## 数据类速查

`model/` 下为纯 dataclass（`scripts/ameparse/model/`）：

- `Component`：`key/alias/path/name/display_name/library_id/ports/submodel/
  is_supercomponent`，以及 `params/variables/modified_params/is_plumbing`；
- `Submodel`：`name/instance/label/params/internal_vars/external_vars` +
  `param(varname)` / `variable(varname)` 查找；
- `Port`：`index`(1-based)/`type`/`name`/`connects`（原始 `ConnectRef`）；
- `Var`：`id/title/units/kind/save_value/saved/port_tag/port_index`；
- `CircuitModel`：`components/lines/supercomponents/global_params/connections` +
  `alias_map()` / `port_map()`。

## 序列化与导出

```python
m.to_dict()                                   # 全量 model card（schema_version=1，只增不改）
m.to_compact_dict()                           # compact card（Tool 返回形态）
m.to_csv(out_dir)                             # 参数表/变量表 CSV

from ameparse.export import export
export(m, out_dir)                            # sources/ + cards/ + csv/ 一键四层
```

`cards/<model>.full.json` 键结构：`components`（参数/变量/端口）、`connections`
（实体号空间，原始溯源）、`graph`（edges/neighbors/stats）、`simulation`/
`model_io`/`saved_variables`/`study_params`/`declared_params`/
`declared_variables`/`notes`。

自定义报告用查询 API 拼装：

```python
for c in sorted(m.components(), key=lambda c: -len(c.modified_params))[:25]:
    for p in c.modified_params:
        print(f"- {p.id} = {p.value_view} {p.units} — {p.title}")
```

## 错误层次

```
AmeparseError
├── ArchiveError          # 打不开 / 不是 tar
├── MemberNotFound        # 必需成员缺失（如无 .cir）
├── ParseError            # 成员解析失败（携带成员名；CirParseError/CompiledParseError）
├── GraphUnavailable      # 需要图但不可用（cli 查询场景）
└── AmbiguousAlias        # 重名组件/参数/变量，报错信息列出候选 path=
```

约定：**可预期的缺失不是异常**（无 `.c` → `graph is None`）；**结构损坏才是
异常**。
