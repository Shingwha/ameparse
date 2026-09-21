"""从 .cir 按实体（net）分组挂载点，构建别名级连接图，并与编译拓扑交叉验证。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ameparse"))

import tarfile
from collections import defaultdict

from ameparse.tolerant import parse
from ameparse.cir import parse_cir
from ameparse.textfiles import parse_param_file, parse_var_file
from ameparse.ctopo import build_topology

AME = sys.argv[1] if len(sys.argv) > 1 else '../资源/HEV_GWCD_40.ame'
model = AME.split('/')[-1].split('\\')[-1].replace('.ame', '')

with tarfile.open(AME) as tf:
    c_text = tf.extractfile(f'{model}_.c').read().decode('latin-1')
    raw = parse(tf.extractfile(f'{model}_.cir').read().decode('latin-1'))
    cir = parse_cir(tf.extractfile(f'{model}_.cir').read().decode('latin-1'))
    decls = parse_param_file(tf.extractfile(f'{model}_.param').read().decode('latin-1'))
    vdecls = parse_var_file(tf.extractfile(f'{model}_.var').read().decode('latin-1'))

# ---- .cir 实体网络图 ------------------------------------------------------
attachments = {}    # entity -> set((alias, port))
port_type = {}      # (alias, port) -> type
for comp in raw.iter('COMP'):
    alias = comp.text_of('ALIAS')
    pl = comp.find('COMP_PORTS_LIST')
    if pl is None:
        continue
    for pi, port in enumerate(pl.findall('COMP_PORT'), start=1):
        port_type[(alias, pi)] = port.text_of('PORT_TYPE')
        cl = port.find('CONNECT_LIST')
        if cl is None:
            continue
        for conn in cl.findall('CONNECT'):
            e = int(conn.text_of('CONNECT_ENTITY_NUM'))
            if e > 0:
                attachments.setdefault(e, set()).add((alias, pi))

edges = set()
for e, att in attachments.items():
    att = sorted(att)
    for i in range(len(att)):
        for j in range(i + 1, len(att)):
            edges.add((att[i], att[j]))
print(f'.cir 网络图: {len(attachments)} 个实体(net) / {len(edges)} 条边')

# 端口类型一致性检查（同一 net 上的端口类型应相同域）
type_conflict = 0
for e, att in attachments.items():
    types = {port_type.get(a) for a in att}
    types.discard(None)
    if len(types) > 1:
        type_conflict += 1
        if type_conflict <= 3:
            print(f'  类型不一致 net {e}: {[(a, port_type.get(a)) for a in sorted(att)]}')
print(f'端口类型不一致的 net: {type_conflict}/{len(attachments)}')

# ---- 编译拓扑（交叉验证） --------------------------------------------------
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
compiled_edges = {(tuple(e['from']), tuple(e['to'])) for e in topo.edges}
print(f'编译拓扑: {len(compiled_edges)} 条边')

# 交叉: 编译边是否都在 .cir 图中
hit = sum(1 for e in compiled_edges if e in edges)
print(f'编译边在 .cir 图中的比例: {hit}/{len(compiled_edges)}')
miss = [e for e in compiled_edges if e not in edges][:5]
for e in miss:
    print('  MISS:', e)

# 反向: .cir 图中编译能确认的比例
hit2 = sum(1 for e in edges if e in compiled_edges)
print(f'.cir 边被编译确认: {hit2}/{len(edges)}')

# BatPackGene 邻居对照
bp_cir = set()
for e, att in attachments.items():
    if ('BatPackGene', 1) in att or ('BatPackGene', 2) in att or ('BatPackGene', 3) in att or ('BatPackGene', 4) in att:
        for a in att:
            if a[0] != 'BatPackGene':
                bp_cir.add(a)
print('.cir BatPackGene 邻居:', sorted(bp_cir))
bp_comp = set()
for e in topo.edges:
    (a, pa), (b, pb) = e['from'], e['to']
    if a[0] == 'BatPackGene':
        bp_comp.add((b, pb))
    if b[0] == 'BatPackGene':
        bp_comp.add((a, pa))
print('编译 BatPackGene 邻居:', sorted(bp_comp))
