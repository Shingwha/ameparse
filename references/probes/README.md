# 探索期探针（格式逆向工程证据，非解析器本体）
#
# 这些脚本是开发 ameparse 时的调查工具，记录了 .cir 实体编号问题的完整推理过程：
# 结论——CONNECT/LINE 中的 entity 编号是创建顺序产物，文件内无显式存储，
# 无法由文件顺序 / DFS 顺序 / 文档交错顺序 / CIRCUIT_SCOPE_ID 顺序推导
# （四种顺序的对称性与端口有效性检验均失败，见各 probe 输出）。
# 因此解析器保留原始实体号，未做别名解析。
#
# - probe_tar.py        列出 .ame tar 成员清单与大小
# - probe_extract.py    提取小成员并打印头部内容
# - cir_parse.py        初版行级容错解析器（后被 scripts/ameparse/tolerant.py 取代）
# - probe_entity.py     线端点兼容性检验
# - probe_portvalid.py  端口有效性检验（引用端口号是否超出组件端口数）
# - probe_linecross.py  线端点 vs 直接引用匹配检验
