# `.ame` 格式逆向结论与限制

> `.ame` 格式知识的权威版本（v2410 实测）。逆向证据链见 `probes/`。

## 物理格式

`.ame` 是 **POSIX/GNU tar 归档**（`tarfile.open(mode="r:")` 直接可读）。
tar 内成员命名 `模型名_.扩展名`（如 `MyModel_.cir`），少量带子路径
（`.props/properties.xml`）：

| 成员 | 内容 | 解析 |
|---|---|---|
| `*.cir` | **核心**：电路结构 XML（组件/子模型/参数值/端口连接） | `parsers/cir.py` |
| `*.c` | 编译产物：SUBSTRUC/EVIA 表 = 编译态拓扑 | `parsers/compiled.py` |
| `*.param` | 参数声明表（子模型+实例+标题+单位+Param_Id） | `parsers/declarations.py` |
| `*.var` | 变量全表（HIDDEN 标记分隔可见/隐藏变量） | `parsers/declarations.py` |
| `*.ssf` | save strategy：保存变量清单（`ameloadvarst` 可取数的前提） | `parsers/declarations.py` |
| `*.modelinfo` | 状态数、Simulink/外部接口输入输出表 | `parsers/metadata.py` |
| `*.amegp` | 全局参数（XML，见"全局参数三源"） | `parsers/globals.py` |
| `*.pl` | 参数表平文件，含全局参数段 `GLOBAL_PARAMS_LIST` | `parsers/globals.py` |
| `*.sim` | 仿真选项（起止时间、打印间隔等，两行数字） | `parsers/metadata.py` |
| `*.studyparam` | 研究/批量运行参数（合法 XML，含上下界） | `parsers/metadata.py` |
| `*.units` / `*.props/properties.xml` | 单位、属性实例（`property` 带 `sticker` 置信度贴纸） | `parsers/metadata.py` |
| `*.views` / `*.sad` / `*.data` | 视图 / 敏感度 / 参数值平文件 | 不解析（导出源文件时保留） |
| `*.results` / `*.mexw64` / `*.obj` / `*.png` / `*.ameperf` | 结果/编译产物/端口标注图/性能日志（体积大，**列出但不读取**） | — |
| `*.amegp.1` / `*.param.1` / `*.pl.crc_*` | 带序号的备份副本（与主成员同内容） | 主成员优先 |

**归档清单必须完整**：`archive_members` 列出**全部**成员（名字+大小），
只有解析是白名单制的。早先的实现把 `.results`/`.png`/`.ameperf` 从清单里
整个删掉，导致清单漏成员——漏掉的成员没人会再去找，而 `.000.png`
（端口标注图）和 `.results`（上次仿真结果）对分析是有价值的。

行级声明文件（`.param`/`.var`/`.ssf`）统一格式：
`子模型 instance N 标题 [单位] key=value ... Data_Path=名称@别名`；
标题可能自带方括号，单位提取见 `textfmt.split_title_unit` 的三条规则。
`.data` 是按 `.param` 声明顺序的参数值平文件（可做独立交叉验证）；
`.cir` 的 `RPARAM_n[2]={k,1}` 中 k 即 `.data` 行索引（0-based）。

## `.cir` 的两个坑与解法

1. **不是合法 XML**：`VISIBILITY` / `VALUE` 等表达式字段含未转义的 `&&` 和 `<`
   （如 `(Tengine<=0)*80`、`(a == 1) && (b == 2)`），`xml.etree` 直接报错。
   本项目用 `tolerant.py` 的逐行容错解析器处理（利用其"一行一标签"的排版）。
2. **实体编号无法由静态顺序推导**（本项目最硬的逆向成果，证据链在 `probes/`）：
   端口连接 `CONNECT_ENTITY_NUM` 使用内部 sketch 实体号（**按端口域
   全局编号**，创建顺序产物，文件内无显式存储）。实测**文件顺序 / DFS 顺序 /
   文档交错顺序 / CIRCUIT_SCOPE_ID 顺序四种假设全部失败**（每种假设 × 三种
   检验均 ~0 命中）。
   **解法**（`parsers/compiled.py` + `linking/resolver.py`）：转向编译产物
   `.c`——`SUBSTRUC` 表给出每个子模型实例的变量区间，`EVIA_Vn` 给出每个变量
   的 `v[]` 槽位（定义上方注释带变量名，覆盖率 100%）；**两个实例的端口变量
   共享同一槽位即相连**（直接连接编译后就是同一个状态变量；`v[X]=v[Y];`
   拷贝语句表达信号广播）。以编译态直连为"罗塞塔石碑"，用端口号匹配（`.cir`
   目标端口为 0-based，即 EVARS 端口号 − 1）**投票**，把实体号解析为组件别名，
   进而将 `.cir` 的全量引用（含信号 / remote 连接）翻译成**别名级连接图**。
   两源交叉验证：编译态 223 条直连边中 97.3% 在 `.cir` 图中得到印证（余下为
   `.cir` 图更精确——保留节点组件为图中节点）。
   实体还有两种形态：**真实组件**（多个端口被不同组件引用）与 **DIRECT
   直连线**（仅 2 个挂载，编译时被内联）。
   重构期发现：早期"按电路层级分组"的实现是死代码——分层会把同一实体的挂载
   拆散、投票失效（951 边掉到 859）；平面命名空间才是验证过的行为。

## 全局参数三源

同一个全局参数可能在**三个成员**里各有一份定义，取值还可能不一致
（实测 PB62：234 个全局中 8 个在 `.amegp` 与 `.cir` 之间分歧）：

| 来源 | 写法 |
|---|---|
| `.amegp` | `<GLOBAL_PARAMS_LIST>` → `<PARAMETER EVAL_ORDER="-1">` → 子元素 `VARNAME`/`TITLE`/`VALUE`/`DEFAULT`/`MIN_VALUE`/`MAX_VALUE`/**`UNIT`** |
| `.cir` | `<GLOBAL_PARAMS_LIST>` → `GROUP`（可省）→ `<GLOBALPARAM>` → 子元素 `GLOB_PARAM_NAME`/`VALUE`/`UNITS` |
| `.pl` | `<GLOBAL_PARAMS_LIST>` → `<PARAMETER Data_Path="名字" VALUE="…" UNITS="…"/>`（**属性式**） |

三个坑，都踩过：

1. **拼写**：旧实现只认 `GPARAM`/`UNITS`，而真实文件用 `PARAMETER`/`UNIT`
   （单数）。结果是 233 个全局参数被静默报成 0——一个自信的零比"未解析"
   更有害，它让追问到此为止。两种拼写现在都吃。
2. **容器不止一个**：`.cir` 里可能有**两个** `GLOBAL_PARAMS_LIST` 段各带
   一部分定义，用 `find`（只取首个）会再漏一半。要遍历全部容器。
3. **`.pl` 必须限定子树**：`.pl` 全文件常有上千个 `PARAMETER`（组件参数，
   与 `.cir` 重复），不限定在 `GLOBAL_PARAMS_LIST` 内就会把它们当成全局参数。
4. **编码标错**：`.cir` 声明 `encoding="ISO-8859-1"`，实际写入的是 UTF-8
   （舱体与 PB62 两个模型实测）。照声明解码会把**所有中文标题变成乱码**，
   而这些标题正是模型最有信息量的部分（`LF_beta7` = 回风局部区内送风直接
   卷吸比例）。解码一律先试 UTF-8、失败才退回 latin-1；UTF-16 靠 BOM 识别
   （其声明本身也是 UTF-16 编码，正则认不出来）。

合并规则：取值以 `.amegp` 为准（`SOURCE_PRECEDENCE`），元信息从任一有值的
来源补齐，**同名分歧进 `global_conflicts` 而不静默择一**——按过时的那个来源
跑出来的结果与预期完全不同。

引用点：全局名以**裸名**出现在 `.cir` 的取值里，参数
（`RPARAM`/`IPARAM`/`TPARAM`）与变量（`IVAR`/`EVAR`）两侧都有；`EVAR` 的
`VALUE` 就是**状态初值**，所以"这个旋钮影响哪些状态"可以直接从引用索引读出。
整值引用（`<VALUE>LF_Gduct_front_air</VALUE>`）与表达式引用
（`<VALUE>LF_Mduct_front*LF_duct_surface_fraction</VALUE>`）用 `role` 区分。
注意 `hconvExpression`/`filesolarflux` 这类**文本参数**也承载全局引用
（实测舱体模型的 4 条风道换热支路就靠它），不能因为类型是 text 就跳过。

## 结构层级

```
CIR → CIRCUIT
      ├── COMPS_LIST → COMP        组件（ALIAS=实例名, COMP_LIBRARY_ID=库组件）
      │     └── SUPERCOMPONENT     超级组件（子回路），内含嵌套 CIRCUIT → COMPS_LIST
      ├── LINES_LIST → LINE        连线（子模型 DIRECT）
      └── GLOBAL_PARAMS_LIST
COMP 内含：端口表（COMP_PORT + CONNECT_LIST）+ SUBMODEL 绑定
SUBMODEL 内含：SUB_NAME（如 ESSBATPA01）+ SUB_UNIT（实例号）
              + RPARAM/IPARAM/TPARAM（参数值/单位/上下界/可见性/枚举）
              + IVAR/EVAR（内部/外部变量，带 SAVE_VALUE，外部变量按端口分组）
```

## 标识与编号约定

- **参数/变量标识** = `名称@别名`（如 `Uinit@BatPackGene`），与 Simulation
  Scripting 的 `ameputp` / `amegetparamnamefromui` 一致。
  注意：同名变量可能出现在不同端口上（如 `output` 在端口 8/9 是两个不同
  信号），此时 id 重复、两者都保留（`variable(id)` 抛 `AmbiguousAlias`）。
- **组件唯一键** = `(path, alias)`（超级组件链 + 别名）——别名会重复
  （超级组件内外同名），不能只用 alias 查询。
- **端口号**：组件自身端口（`Port.index`、图查询 `PortRef.port`）一律
  **1-based**（与 EVARS_LIST 的 PORT 顺序一致）；`ConnectRef.port` 是 `.cir`
  原文值（目标侧 **0-based**），转换只发生在 `GraphResolver`。
- **子模型名**（如 `ESSBATPA01`）是查库手册知识库的检索键。

## 已知限制

- 连接图依赖 `.c` 编译产物存在；无 `.c` 时 `Model.graph` 为
  `None`（`graph_error` 给原因），仅保留原始实体号 `connections`。
- 约 15% 多挂载实体无法投票定位组件，按"网络节点"处理（挂载点两两相连）；
  端口类型冲突率约 1%。
- `.param` 中点分别名声明（`SC名.intvarsensor`，超级组件内嵌 sensor 元素）
  在 `.cir` 中无对应 COMP，`declared_param_count` 不归属任何组件。
- `.sim` 字段位置含义随版本变化，`final_time`/`print_interval` 按 2410 布局
  解释，其余字段按下标访问（`SimOptions.values`），原始数字在 `raw` 中保留。
- 旧版（pre-2410）的 `.cir` 是行级文本格式（本解析器按 2410 XML 格式实现）；
  换版本需先跑 `probes/` 校准。
