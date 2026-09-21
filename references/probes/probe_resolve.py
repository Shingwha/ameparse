"""最终验证：resolve_graph 产物的自洽性与交叉验证。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ameparse"))

import tarfile
from collections import defaultdict

from ameparse.tolerant import parse
from ameparse.textfiles import parse_param_file, parse_var_file
from ameparse.ctopo import build_topology
from ameparse.resolve import resolve_graph

AME = sys.argv[1] if len(sys.argv) > 1 else '../资源/HEV_GWCD_40.ame'
model = AME.split('/')[-1].split('\\')[-1].replace('.ame', '')

with tarfile.open(AME) as tf:
    c_text = tf.extractfile(f'{model}_.c').read().decode('latin-1')
    cir_text = tf.extractfile(f'{model}_.cir').read().decode('latin-1')
    raw = parse(cir_text)
    decls = parse_param_file(tf.extractfile(f'{model}_.param').read().decode('latin-1'))
    vdecls = parse_var_file(tf.extractfile(f'{model}_.var').read().decode('latin-1'))

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
print(f'编译拓扑: {len(topo.instances)} 实例 / {len(topo.edges)} 边(含拷贝) / {len(topo.direct_edges)} 直连边')

result = resolve_graph(cir_text, c_text, alias_of, port_of, topo.direct_edges)
print('解析统计:', result['stats'])

edges = {e for e in result['edges']}
compiled = {(tuple(e['from']), tuple(e['to'])) for e in topo.edges}
direct = topo.direct_edges

# 1) .cir 直连线判定 vs 编译直连
hit = sum(1 for e in edges if e in direct)
print(f'.cir 图中属于编译直连的边: {hit}/{len(edges)}')
# 2) 编译直连是否都在 .cir 图中
hit2 = sum(1 for e in direct if e in edges)
print(f'编译直连边在 .cir 图中: {hit2}/{len(direct)}')
miss = [e for e in direct if e not in edges][:6]
for e in miss:
    print('  MISS:', e)

# 3) 端口类型一致性（.cir 图）
port_type = {}
for comp in raw.iter('COMP'):
    alias = comp.text_of('ALIAS')
    pl = comp.find('COMP_PORTS_LIST')
    if pl is None:
        continue
    for pi, port in enumerate(pl.findall('COMP_PORT'), start=1):
        port_type[(alias, pi)] = port.text_of('PORT_TYPE')
conflict = 0
for (a, pa), (b, pb) in edges:
    ta, tb = port_type.get((a, pa)), port_type.get((b, pb))
    na = None if (ta or '').startswith('remote') else ta
    nb = None if (tb or '').startswith('remote') else tb
    if na and nb and na != nb:
        conflict += 1
        if conflict <= 4:
            print(f'  类型冲突: {a}.{pa}({ta}) - {b}.{pb}({tb})')
print(f'.cir 图端口类型冲突: {conflict}/{len(edges)}')

# 4) BatPackGene 最终邻居
bp = set()
for (a, pa), (b, pb) in edges:
    if a == 'BatPackGene':
        bp.add((b, pb))
    if b == 'BatPackGene':
        bp.add((a, pa))
print('BatPackGene 最终邻居:', sorted(bp))

# 5) 组件节点覆盖率
aliases_in_graph = {x[0] for e in edges for x in e}
all_aliases = {c.text_of('ALIAS') for c in raw.iter('COMP')}
print(f'出现在图中的组件: {len(aliases_in_graph)}/{len(all_aliases)}')
