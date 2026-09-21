"""最终验证：(层级, 域, 实体) 分组的 .cir 连接图 vs 编译态拓扑。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ameparse"))

import tarfile
from collections import defaultdict

from ameparse.tolerant import parse
from ameparse.textfiles import parse_param_file, parse_var_file
from ameparse.ctopo import build_topology

AME = sys.argv[1] if len(sys.argv) > 1 else '../资源/HEV_GWCD_40.ame'
model = AME.split('/')[-1].split('\\')[-1].replace('.ame', '')

with tarfile.open(AME) as tf:
    c_text = tf.extractfile(f'{model}_.c').read().decode('latin-1')
    raw = parse(tf.extractfile(f'{model}_.cir').read().decode('latin-1'))
    decls = parse_param_file(tf.extractfile(f'{model}_.param').read().decode('latin-1'))
    vdecls = parse_var_file(tf.extractfile(f'{model}_.var').read().decode('latin-1'))


def circuit_id(comp):
    n = comp.parent.parent
    if n is None or n.tag != 'CIRCUIT':
        return '?'
    sc = n.parent
    if sc is None:
        return '?'
    if sc.tag == 'SUPERCOMPONENT':
        return 'SC:' + sc.parent.text_of('CIRCUIT_SCOPE_ID')
    return 'TOP'


def domain(t):
    return t.replace('remote', 'REMOTE') if t.startswith('remote') else t


groups = defaultdict(set)   # (level, domain, entity) -> {(alias, port)}
for comp in raw.iter('COMP'):
    alias = comp.text_of('ALIAS')
    level = circuit_id(comp)
    pl = comp.find('COMP_PORTS_LIST')
    if pl is None:
        continue
    for pi, port in enumerate(pl.findall('COMP_PORT'), start=1):
        cl = port.find('CONNECT_LIST')
        if cl is None:
            continue
        for conn in cl.findall('CONNECT'):
            e = int(conn.text_of('CONNECT_ENTITY_NUM'))
            if e > 0:
                groups[(level, domain(port.text_of('PORT_TYPE')), e)].add((alias, pi))

edges = set()
for k, att in groups.items():
    att = sorted(att)
    for i in range(len(att)):
        for j in range(i + 1, len(att)):
            if att[i][0] != att[j][0]:
                edges.add((att[i], att[j]))
print(f'.cir 连接图: {len(groups)} 个线组 / {len(edges)} 条边')

# ---- 编译拓扑 --------------------------------------------------------------
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
compiled = {(tuple(e['from']), tuple(e['to'])) for e in topo.edges}

hit = sum(1 for e in edges if e in compiled)
hit2 = sum(1 for e in compiled if e in edges)
print(f'.cir 边被编译确认: {hit}/{len(edges)}')
print(f'编译边在 .cir 图中: {hit2}/{len(compiled)}')
miss = [e for e in edges if e not in compiled][:8]
for e in miss:
    print('  MISS:', e)
miss2 = [e for e in compiled if e not in edges][:8]
for e in miss2:
    print('  MISS2(编译有 .cir 无):', e)
