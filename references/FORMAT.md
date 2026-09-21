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
| `*.amegp` | 全局参数（XML，常见为空） | `parsers/metadata.py` |
| `*.sim` | 仿真选项（起止时间、打印间隔等，两行数字） | `parsers/metadata.py` |
| `*.studyparam` | 研究/批量运行参数（合法 XML，含上下界） | `parsers/metadata.py` |
| `*.units` / `*.props/properties.xml` | 单位、属性实例 | `parsers/metadata.py` |
| `*.views` / `*.sad` / `*.data` | 视图 / 敏感度 / 参数值平文件 | 不解析（导出源文件时保留） |
| `*.results` / `*.mexw64` / `*.obj` | 结果/编译产物（体积大，**绝不读取**） | — |

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
