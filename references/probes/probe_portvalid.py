"""探针：端口有效性检验——引用 (E,Q) 中 E 对应的组件必须有 >=Q 个端口。"""
import sys
sys.path.insert(0, '.')
from collections import Counter
from cir_parse import parse

raw = open(sys.argv[1] if len(sys.argv) > 1 else 'out_HEV_GWCD_40/HEV_GWCD_40_.cir', encoding='latin-1').read()
root = parse(raw)
circuit = root.find('CIR').find('CIRCUIT')
comps = circuit.find('COMPS_LIST').findall('COMP')
lines = circuit.find('LINES_LIST').findall('LINE')


def dfs_comps(cl):
    out = []
    for c in cl.findall('COMP'):
        out.append(c)
        sc = c.find('SUPERCOMPONENT')
        if sc is not None:
            nc = sc.find('CIRCUIT')
            if nc is not None:
                out.extend(dfs_comps(nc.find('COMPS_LIST')))
    return out


allc = dfs_comps(circuit.find('COMPS_LIST'))
alll = list(root.iter('LINE'))
n = len(allc)


def portcount(c):
    ports = c.find('COMP_PORTS_LIST')
    return len(ports.findall('COMP_PORT')) if ports else 0


def refs_of(c):
    out = []
    ports = c.find('COMP_PORTS_LIST')
    if not ports:
        return out
    for pi, port in enumerate(ports.findall('COMP_PORT'), start=1):
        cl = port.find('CONNECT_LIST')
        if not cl:
            continue
        for conn in cl.findall('CONNECT'):
            out.append((pi, int(conn.text_of('CONNECT_ENTITY_NUM')), int(conn.text_of('CONNECT_ENTITY_PORT'))))
    return out


def check(name, cmap):
    """cmap: id(comp)->entity. 检查每个 ref (E,Q)：E 是组件则端口数是否够，是线则 Q 应为 0/1。"""
    comp_by_ent = {e: c for c in comps for e in [cmap[id(c)]]}
    line_ents = set()
    ok = bad_port = bad_lineport = out_of_range = 0
    dist = Counter()
    for l in alll:
        line_ents.add(lm_val(l))
    for c in allc:
        for pi, e, q in refs_of(c):
            if e <= 0:
                continue
            dist[e] += 1
            target = comp_by_ent.get(e)
            if target is not None:
                pc = portcount(target)
                if 0 <= q <= pc:  # 0-based or 1-based? accept both
                    ok += 1
                else:
                    bad_port += 1
            elif e in line_ents:
                if q in (0, 1):
                    ok += 1
                else:
                    bad_lineport += 1
            else:
                out_of_range += 1
    print(f'{name}: ok={ok} bad_port={bad_port} bad_lineport={bad_lineport} out_of_range={out_of_range}')


def lm_val(l):
    return int(l.text_of('LINE_START_ENTITY'))  # 只是为了线实体集合占位；下面两种映射各自处理


# mapping 1: DFS 文档序 (comps 1..N, lines N+1..N+M)
cm1 = {id(c): i for i, c in enumerate(allc, 1)}
check('dfs', cm1)

# mapping 2: 全文档交错序 (comps 与 lines 按文档出现顺序统一编号)
seq = []


def walk(cir):
    cl = cir.find('COMPS_LIST')
    if cl is not None:
        for c in cl.findall('COMP'):
            seq.append(('C', c))
            sc = c.find('SUPERCOMPONENT')
            if sc is not None:
                nc = sc.find('CIRCUIT')
                if nc is not None:
                    walk(nc)
    ll = cir.find('LINES_LIST')
    if ll is not None:
        for l in ll.findall('LINE'):
            seq.append(('L', l))


walk(circuit)
ent2 = {(k, id(n)): i for i, (k, n) in enumerate(seq, 1)}
cm2 = {id(c): ent2[('C', id(c))] for c in allc}
check('doc_interleaved', cm2)

# mapping 3: 按 CIRCUIT_SCOPE_ID 排序
items = [('C', int(c.text_of('CIRCUIT_SCOPE_ID')), c) for c in allc] + \
        [('L', int(l.text_of('CIRCUIT_SCOPE_ID')), l) for l in alll]
items.sort(key=lambda x: x[1])
cm3 = {id(c): i for i, (k, s, n) in enumerate(items, 1) if k == 'C'}
check('scope_sorted', cm3)
