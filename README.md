# ameparse

`.ame` 模型文件解析器：提取组件、子模型绑定、参数、变量、别名级连接图与
仿真设置，提供命令行与对象级查询 API。

## 安装

```bash
cd scripts && uv tool install .     # 装一次，之后直接使用 ameparse 命令
```

开发模式（改代码即时生效）：
`cd scripts && uv sync --extra dev && uv run ameparse model.ame --summary`

## 快速开始

```bash
ameparse model.ame --settings                 # 版本 / 仿真选项 / 接口
ameparse model.ame --components --submodel ESSBATPA01
ameparse model.ame --param Uinit@BatPackGene  # 单参数：值 / 边界 / 单位
ameparse model.ame --variable q1@pump01       # 单变量（含 saved 可取数判据）
ameparse model.ame --neighbors BatPackGene    # 连接关系
ameparse model.ame -o card.json               # 全量 model card JSON
ameparse export --resources DIR --out DIR     # 批量：sources/ + cards/ + csv/
```

```python
from ameparse import Model

m = Model.from_file("model.ame")
m.component("BatPackGene").params             # 组件与参数
m.param("Uinit@BatPackGene").value            # 按 名称@别名 取参数（与 ameputp 一致）
m.subgraph("BatPackGene", hops=2)             # 局部连接图
m.to_dict()                                   # 全量 model card
```

## 文档

| 文档 | 内容 |
|---|---|
| [SKILL.md](SKILL.md) | 面向 Agent 的完整用法：六阶段查询流、全部命令行、约定与坑 |
| [references/API.md](references/API.md) | Python API 参考：装载、节、各类查询、数据类、序列化、错误 |
| [references/FORMAT.md](references/FORMAT.md) | `.ame` 格式逆向结论（tar 成员、`.cir` 两坑与解法）、标识约定、已知限制 |
| [references/DESIGN.md](references/DESIGN.md) | 七层架构、类设计、命名约定、决策与偏差记录 |
| [references/ROADMAP.md](references/ROADMAP.md) | 路线图 |
| [references/probes/](references/probes/) | 格式探索期探针（实体编号逆向证据链） |

## 测试

```bash
cd scripts && uv sync --extra dev && uv run pytest   # 59 个纯合成用例，秒级，零外部依赖
```

仓库不含任何模型数据；对特定真实模型的回归保障（黄金文件逐键对比 + 基准数字
核对）由使用方在模型侧维护。

## 性能

tarfile 随机访问只读 `.cir`/`.c` 等小成员，`.results` 等大文件绝不读取：
百 MB 级模型纯解析秒级，含连接图 1~4s。

## License

暂未声明（默认保留所有权利）；如需放开请补充 LICENSE 文件。
