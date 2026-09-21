"""全量验证：用 1028 条 .cir CONNECT 引用投票反推 实体号→别名，
并交叉验证 LINE 端点。端口约定：.cir 目标端口为 0-based（= EVARS 端口号 - 1）。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ameparse"))

import tarfile
from collections import Counter, defaultdict

from ameparse.tolerant import parse
from ameparse.cir import parse_cir
from ameparse.textfiles import parse_param_file, parse_var_file
from ameparse.ctopo import build_topology

AME = sys.argv[1] if len(sys.argv) > 1 else '../资源/HEV_GWCD_40.ame'
model = AME.split('/')[-1].split('\\')[-1].replace('.ame', '')

with tarfile.open(AME) as tf:
    c_text = tf.extractfile(f'{model}_.c').read().decode('latin-1')
    cir = parse_cir(tf.extractfile(f'{model}_.cir').read().decode('latin-1'))
    decls = parse_param_file(tf.extractfile(f'{model}_.param').read().decode('latin-1'))
    vdecls = parse_var_file(tf.extractfile(f'{model}_.var').read().decode('latin-1'))
    raw = parse(tf.extractfile(f'{model}_.cir').read().decode('latin-1'))

alias_of = {}
for d in decls + vdecls:
    alias_of.setdefault((d.submodel, d.instance), d.data_path.split('@', 1)[-1])
port_of = {}
for comp_node in raw.iter('COMP'):
    alias = comp_node.text_of('ALIAS')
    sm = comp_node.find('SUBMODEL')
    if sm is None:
        continue
    m = {}
    evars = sm.find('EVARS_LIST')
    if evars is not None:
        for pi, port in enumerate(evars.findall('PORT'), start=1):
            for evar in port.findall('EVAR'):
                m[evar.text_of('VARNAME')] = pi
    port_of[alias] = m

topo = build_topology(c_text, alias_of, port_of)
print(f'编译拓扑: {len(topo.instances)} 实例 / {len(topo.edges)} 边 / {len(topo.nodes)} 节点')

compiled = defaultdict(set)
for e in topo.edges:
    (a, pa), (b, pb) = e['from'], e['to']
    compiled[(a, pa)].add((b, pb))
    compiled[(b, pb)].add((a, pa))

# ---- 投票: .cir (A,Pa) -> (E,Q) -----------------------------------------
cir_connects = []
for comp in cir.components:
    for p in comp.ports:
        for (e, q) in p.connects:
            if e > 0:
                cir_connects.append((comp.alias, p.index, e, q))

votes = defaultdict(Counter)
for (a, pa, e, q) in cir_connects:
    for (nb, np_) in compiled.get((a, pa), ()):
        if np_ - 1 == q:      # 严格 0-based（EVARS 端口号 - 1）
            votes[e][nb] += 1

ent2alias = {}
conflicts = []
for e, c in votes.items():
    top = c.most_common()
    if len(top) == 1 or top[0][1] > top[1][1]:
        ent2alias[e] = top[0][0]
    if len(top) > 1 and top[0][1] == top[1][1]:
        conflicts.append((e, top[:3]))
print(f'实体号覆盖: {len(ent2alias)}/{len(set(e for _,_,e,_ in cir_connects))}，平票冲突: {len(conflicts)}')
for e, c in conflicts[:6]:
    print(f'   entity {e}: {c}')

# ---- 用映射验证全部引用 --------------------------------------------------
alias_portcount = {c.alias: len(c.ports) for c in cir.components}
ok = bad = unknown = 0
for (a, pa, e, q) in cir_connects:
    nb = ent2alias.get(e)
    if nb is None:
        unknown += 1
        continue
    if 0 <= q < alias_portcount.get(nb, 0):
        ok += 1
    else:
        bad += 1
        if bad <= 5:
            print(f'   BAD: {a} port{pa} -> entity {e}({nb}) port {q}, 该组件仅 {alias_portcount.get(nb)} 端口')
print(f'引用验证(0-based): ok={ok} bad={bad} unknown={unknown}')

# ---- LINE 端点验证 -------------------------------------------------------
line_ok = line_bad = line_unknown = 0
for l in cir.lines:
    for (e, q) in (l.start, l.end):
        if e <= 0:
            continue
        nb = ent2alias.get(e)
        if nb is None:
            line_unknown += 1
        elif 0 <= q < alias_portcount.get(nb, 0):
            line_ok += 1
        else:
            line_bad += 1
print(f'LINE 端点验证: ok={line_ok} bad={line_bad} unknown={line_unknown} (共 {len(cir.lines)} 条线)')

# ---- 输出映射表示例 ------------------------------------------------------
print('\n实体号→别名（前 15）:')
for e in sorted(ent2alias)[:15]:
    print(f'  {e} -> {ent2alias[e]}')

# 保存映射供后续使用
import json
json.dump({str(k): v for k, v in ent2alias.items()},
          open('ent2alias.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
print('\n已保存 ent2alias.json')
