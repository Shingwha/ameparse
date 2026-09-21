# ameparse 设计与决策记录

> 文档分工：README 是使用入口；[FORMAT.md](FORMAT.md) 是 `.ame` 格式知识的权威
> 版本；[API.md](API.md) 是使用侧 API 参考。本文记录架构设计、约定与全部设计
> 决策/偏差的历史，面向维护者与后续上下文。
>
> 本仓库是**独立通用解析器**：不依赖特定模型（仓库不含模型数据），不依赖
> 外部项目文档。§7 为历史记录，其中出现的项目语境（决策引用、模型名）仅作
> 溯源，不再是本仓库的依赖。

## 0. 范围与不变量

**不变量（正确性约束）**：

1. 零第三方依赖（stdlib only）——CI/Linux 可移植、无 license 依赖；
2. `tolerant.py` 对非法 XML 的容忍行为（未转义 `&&`/`<`、一行多标签）；
3. 连接图解法（.c 编译拓扑投票）逻辑与回归数字（外部回归套件 BASELINE）；
4. model card JSON schema 是下游（知识库/评测任务卡）的数据契约，只增不改；
5. 性能特征：只读白名单成员，绝不整体读 `.results`；中文路径正常
   （`latin-1` + `errors="replace"`、CSV `utf-8-sig`）。

## 1. 设计原则

1. **一层只做一件事**：传输 → 原语 → 数据 → 解析 → 集成 → 门面 → 序列化，依赖只能向下。
2. **数据与解析彻底分离**：`model/` 的 dataclass 无 IO、无正则、不认识 tar；
   `parsers/` 不碰门面、不组装卡片。
3. **一个 tar 成员一个解析器**：注册表驱动（后缀 → 解析器），缺成员跳过、坏成员
   报 `ParseError` 带成员名。加一种新成员 = 加一个类 + 一行注册。
4. **身份显式化**：组件 `ComponentKey(path, alias)`；参数/变量 `(key, varname)`
   内部键 + `名称@别名` 展示 id；端口 1-based 全库统一。
5. **查询即 API**：`Model` 提供语义查询，使用者不需要啃 dict。
6. **序列化是设计而非副产品**：`to_dict()`（全量）/`to_compact_dict()`
   （Tool 返回形态）/`to_csv()`（平表）各司其职。

## 2. 架构与模块

仓库为 skill 结构（安装单元是 `scripts/`：`cd scripts && uv tool install .`）：

```
ameparse/
├── README.md               # 使用入口（安装/快速开始/文档导航）
├── SKILL.md                # Agent 用法（六阶段查询流 + 命令表）
├── scripts/                # 安装单元（uv project）
│   ├── pyproject.toml / uv.lock
│   ├── ameparse/           # 包（下述七层）
│   └── tests/              # 纯合成测试
└── references/             # 文档：FORMAT / API / DESIGN / ROADMAP + probes（证据链）
```

```
.ame(tar) ──Amefile──▶ 成员文本 ──parsers/──▶ 数据类(model/) ──linking/──▶ Model ──▶ export
```

```
scripts/ameparse/
├── errors.py              # 异常层次
├── archive.py             # L0 传输：Amefile（tar 访问 + from_bytes/exists）
├── tolerant.py            # L1 原语：Node/parse（容错 XML 扫描器，行为不可变）
├── textfmt.py             # L1 原语：.param/.var/.ssf 行格式切分
├── model/                 # L2 数据：纯 dataclass
│   ├── circuit.py         #   ComponentKey/ConnectRef/Param/Var/Port/Submodel/
│   │                      #   Component/Line/Supercomponent/GlobalParam/CircuitModel
│   ├── declarations.py    #   ParamDecl/VarDecl/Declarations（索引）
│   ├── metadata.py        #   ModelInfo/SimOptions/StudyParams/Units/Properties/SavedVariable
│   ├── compiled.py        #   CompiledTopology（attach_ports 槽位→端口挂载）
│   └── graph.py           #   PortRef/Edge/ConnectionGraph（subgraph/subcircuits/path）
├── parsers/               # L3 解析：一个成员一个解析器
│   ├── __init__.py        #   MemberParser 协议 + MEMBER_PARSERS 注册表（加载白名单）
│   ├── cir.py             #   CirParser（端口序号/scope_level 在解析期定型）
│   ├── compiled.py        #   CompiledParser（.c 事实提取）+ build_topology
│   ├── declarations.py    #   .param/.var/.ssf 三个行格式解析器
│   └── metadata.py        #   .modelinfo/.sim/.studyparam/.units/.amegp/properties
├── linking/               # L4 集成：跨成员合并
│   ├── linker.py          #   Linker：声明合并 + declared_param_count 归属
│   └── resolver.py        #   GraphResolver：实体投票 → ConnectionGraph
├── core.py                # L5 门面：Model（懒加载 + 查询 + to_dict）
├── export.py              # L6 视图：compact card / CSV / 源文件 / export()
└── cli.py                 # 命令行 + export 子命令
```

要点：

- **懒加载边界**：`.cir` 与小成员 eager；`.c` 文本加载时读入但不解析，
  `compiled`/`graph` 首次访问才解析——纯查参数/变量的场景不为连接图买单。
- **`.cir` 只解析一遍**：`alias_map()`/`port_map()` 从 `CircuitModel` 对象导出，
  不再重扫 Node 树（旧实现解析两遍）。
- **归档只打开一次**（旧实现开两次）。

## 3. 类设计（关键签名）

```python
class Amefile:                                    # L0
    def members() -> list[Member]; read/read_text(suffix); exists(suffix)
    @classmethod from_bytes(data)

# model/（纯数据 + 领域计算）
ComponentKey(path: tuple, alias: str)             # 组件唯一键
Param: varname/title/kind/value/.../declaration   # .declaration = Linker 挂点
       .id = "名称@别名"; .is_modified; .value_view
Var:  .../port_index(1-based); .id
Port: index(1-based)/type/name/tag/connects       # connects: [ConnectRef(entity, port_raw)]
Component: key/alias/path/ports/submodel/
           .params/.variables/.modified_params/.is_plumbing
CircuitModel: components(DFS 序)/lines/supercomponents/global_params/
              connections(原始实体引用)/alias_map()/port_map()
CompiledTopology: instances/slot_users/copies/
                  attach_ports(alias_of, port_of)/direct_edges/edges
ConnectionGraph: edges()/neighbors(alias, port=None)/subgraph(seed, hops)/
                 subcircuits()/shortest_path(a, b)/to_dict()

class Linker:                                     # L4
    link(circuit) -> None                         # in-place 声明合并 + 归属
class GraphResolver:
    resolve() -> ConnectionGraph                  # 输入 CircuitModel + CompiledTopology

class Model:                                      # L5 门面
    @classmethod from_file(path) / from_archive(ame)
    circuit/declarations/compiled/graph(懒)/graph_error
    model_info/simulation/study/units/properties/global_params/saved_variables
    component(alias, *, path=None) / components(**filters) / submodel_distribution()
    param(id) / params(**filters) / variable(id) / variables(**filters)
    neighbors/subgraph/subcircuits/path
    to_dict() / to_compact_dict() / to_csv(out_dir)
```

## 4. 函数与命名约定

**模块级函数**只保留两类：单步工具（`parse_cir(text)`、`build_topology(...)`、
`parse_param_file(text)` 等薄封装）与纯变换（`compact_card(model)`、
`write_param_csv`）；能成为类方法的不设模块函数。

**代码命名**：数据类字段与 JSON 键对齐（`to_dict` 零翻译）；布尔统一裸形容词
（`hidden`/`saved`）或 `is_` 前缀；常量 `UPPER_SNAKE`；成员后缀集中在
`MEMBER_PARSERS` 注册表键。**代码注释/docstring 中文，用户可见文本英文。**

**领域术语（禁同义词）**：

| 概念 | 统一用名 | 不叫 |
|---|---|---|
| 组件实例名 | `alias` | name / instance_name |
| 子模型名 | `submodel` | component_type |
| 端口号（1-based） | `port` | pin / index |
| 内部实体号（0-based 原文） | `entity` | sketch_id |
| 编译态变量槽位 | `slot` | v_index |
| 连接图的边 | `edge` | link |
| `.cir` 原始端口引用表 | `connections` | raw_edges |

## 5. JSON schema 与错误设计

- `to_dict()` 键结构见 [API.md](API.md)『序列化与导出』与 `Model.to_dict()` docstring；
  `schema_version: 1`，只增不改。紧凑卡 `to_compact_dict()` 是 Tool 返回形态
  （组件/参数/变量/连接图的精简子集，键结构以实现为准）。
- 异常层次：`AmeparseError` ← `ArchiveError` / `MemberNotFound` / `ParseError`
  （`CirParseError`/`CompiledParseError`）/ `GraphUnavailable` / `AmbiguousAlias`。
  约定：**可预期的缺失不是异常**（无 `.c` → `graph is None` + `graph_error`）；
  **结构损坏才是异常**；图查询方法需要图时抛 `GraphUnavailable`。

## 6. 测试结构

```
tests/
├── _fixtures.py + conftest.py   # 合成 .ame/.c/.cir 构造器
├── test_archive / test_tolerant(+textfmt) / test_cir_parser
├── test_declaration_parsers     # .param/.var/.ssf + 元信息六件
├── test_resolver(+compiled)     # 实体投票、槽位直连
├── test_model_queries           # Model 查询 API + AmbiguousAlias/GraphUnavailable
└── test_serialization           # to_dict/compact/CSV/export 结构
```

仓库测试**纯合成、零外部依赖**（不依赖任何真实模型，任意机器可跑）。
对特定真实模型的回归（黄金文件逐键对比 + 基准数字核对 + 冒烟断言）由
使用方在模型侧维护独立回归套件（黄金文件 + 基准数字，随模型走）。

## 7. 决策与偏差记录（历史）

**已拍板**（2026-09-21）：门面类名 `Model`；`graph` 不可用返回 `None +
graph_error`；`component(alias)` 重名抛 `AmbiguousAlias`（`path=` 限定，
`path=""` 即顶层）；`to_dict()` 保持键结构 + `schema_version`。

**实施偏差**（重构 C1-C6，每步一个提交，详见 git log）：

1. parsers/ 合并为 4 个模块（cir/compiled/declarations/metadata）而非每成员
   一个文件——同类解析器共用原语，小文件只增加导航成本。
2. `ConnectRef.port` 保留 `.cir` 原文（目标侧 0-based），1-based 转换移到
   `GraphResolver`——原始连接表忠实于文件，转换点唯一。
3. **连接图用平面命名空间**：旧实现按电路层级分组的代码是死代码（父链
   错位），entity 编号实测按端口域全局有效；分层会把同一实体的挂载拆散、
   投票失效（951 边 → 859）。`Component.scope_level` 保留为元数据。
4. **同名端口变量不去重**：`output` 等通用名在不同端口是不同信号（HEV
   7 个组件受影响，全模型 222 个变量曾被丢弃）。旧 dict 去重是数据结构
   副作用而非设计；id 重复时 `variable(id)` 抛 `AmbiguousAlias`。
5. **`declared_param_count` 归属规则**（替代旧 `endswith("@别名")` 串户）：
   精确 (别名+子模型+实例号) → 实例号错位回退（子模型名，实测存在如
   rotaryload2 的 MECRL0 0 vs 1）→ 别名唯一；命中者全部计数（跨层级副本
   共享声明）。点分别名（`SC名.intvarsensor`）无对应 COMP，不归属。
6. 修复旧 `CompiledTopology.neighbors` 死代码 bug（解包后仍索引 `a[0]`，
   永远返回空）与 `_enrich` 退化匹配的 `or -1` falsy 瑕疵（0 是合法
   SUB_ID/SUB_UNIT）。
7. 黄金文件语义：由"旧实现输出"刷新为"当前实现输出"，差异仅上述 4/5 两类
   修正；基准数字不变，变量数 +7/+1。
8. **通用化收敛**（0.3.0）：删除 `digest.py`（报告不属于解析器，用查询 API
   自行拼装）；导出结构英文化 `sources/ + cards/*.full|compact.json +
   csv/`；用户可见文本（notes/异常/CLI）英文化；export 默认
   `--resources . --out ameparse-out`；卡片文件名对称化
   `<model>.full.json` / `<model>.compact.json`。
9. **查询粒度与 save 语义修正**（0.4.0）：
   - `Var.saved` 由 Linker 按 `.ssf` 回填，是 `ameloadvarst` 可取数的
     **权威判据**；`Var.save_value` 保留为 `.cir`"可保存"标志（两者实测
     可能矛盾，如 Temp@BatPackGene 前者 True 后者 False）。
     `variables(saved=)`、紧凑卡与 CLI `--saved` 全部改走权威判据，
     `.cir` 标志单独暴露（API 字段 / CLI `--save-flag`）。全量卡变量条目
     新增 `saved` 键（schema 只增不改，外部黄金文件已刷新）。
   - `SimOptions.values`（两行数值列表）提供未确认字段的下标访问，
     不给未确认字段命名。
   - `Edge` 携带两端端口类型（`a_type`/`b_type`），`graph.edges(domain=)`
     按域过滤——回路级分析的前提（整车图连通分量 370/380，拆分必须按域切）。
   - CLI 补齐查询命令：`--settings`/`--components`/`--param`/`--variable`/
     `--params`/`--variables`/`--search`/`--study-params`；`--subgraph`
     升级为**局部图**视图（nodes 带端口类型 + edges 带域 + `--domain`
     过滤 + 节点数上限）；`--component` 支持 `--no-params/--no-variables`
     裁剪；列表命令无过滤拒绝执行（`--all` 覆盖）——防上下文自爆。
   - `--component` 单组件 dump 与 `--params/--variables --component` 共享
     dest：列表旗标优先，`--component` 值作其过滤器。
10. **全局参数可见性修正**（0.5.0）：修掉三个"静默报空"的 bug——它们共同
    的害处是给出**自信的错误答案**，比"未解析"更有害（会让追问到此为止）：
    - `AmegpParser` 只认 `GPARAM`/`UNITS`，真实 `.amegp` 用 `PARAMETER`/`UNIT`
      → 233 个全局参数报 0。`.cir` 侧同一错误（`GLOBALPARAM`/`GLOB_PARAM_NAME`），
      且用 `find` 只取首个容器，两个 `GLOBAL_PARAMS_LIST` 段会再漏一半。
      现在三源（`.amegp`/`.cir`/`.pl`）统一走 `parsers/globals.py` 的
      **来源注册表** `EXTRACTORS`（加来源 = 加一条记录），节点级同时兼容
      子元素式与属性式。
    - `PropertiesParser` 用 `iter("property")`，真实文件根节点带
      `xmlns="amesim-property-instances"` → ET 标签是 `{ns}property`，整张
      属性表（含 `sticker` 置信度贴纸）报 0。新增命名空间无关的
      `tolerant.iter_local`。
    - `SKIP_MEMBER_SUFFIXES` 把 `.results`/`.png`/`.ameperf` 从
      `archive_members` 里整个删掉 → 清单漏成员（漏掉的成员没人会再去找）。
      现在清单列全部成员，"不解析"与"不列出"是两件事。
    - 解码：`.cir` 声明 `ISO-8859-1` 实际写 UTF-8，照声明解码把所有中文标题
      变乱码（标题正是这类模型信息量最大的部分）。`archive.decode_text`
      改为先试 UTF-8、失败退回 latin-1，UTF-16 靠 BOM 识别。
    - 合并：`.amegp` 权威，分歧进 `global_conflicts` 而**不静默择一**；
      引用索引 `linking/globalrefs.py` 把全部已声明名一次编译成联合正则
      （O(取值数)，实测 234 全局 × 3870 引用 0.06s），并给三类机械诊断
      （`conflicts`/`twins`/`unused`/`undefined_refs`）。同一份数据在
      "扁平可编辑模型"上是便利，在"封装受保护交付物"上才是真正的杠杆点——
      PB62 实测：234 个全局里 8 个跨来源分歧、8 组孪生名取值不一致，
      而那些都只能靠人肉翻文件才能发现。
    - CLI 新增 `--globals`/`--global NAME`/`--with-refs`；`--search` 覆盖
      全局参数。三源皆空时输出 `note` 而不是裸 `[]`（见 `NO_GLOBALS_NOTE`）。
    - 不做的：`orphans`（组件取值里 token 级"悬空引用"）。组件取值可能是
      任意字符串（`materialName='PU'`/`'Cell_Width'`），token 扫描在舱体与
      PB62 上分别产出 5/20 条噪音，且找不到能把材料名与真悬空引用分开的
      机械判据。宁可不报，也不报一堆假的——诊断只在类型无歧义的全局定义
      表达式里做（`undefined_refs`）。
