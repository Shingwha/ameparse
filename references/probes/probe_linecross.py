"""探针：测试候选映射下——线端点 (A,Pa)-(B,Pb) 是否对应 A 或 B 端口上的直接 CONNECT 引用。"""
import sys
sys.path.insert(0, '.')
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

# 候选映射：scope 排序
items = sorted(allc, key=lambda c: int(c.text_of('CIRCUIT_SCOPE_ID')))
M = {id(c): i for i, c in enumerate(items, 1)}      # comp -> entity
MINV = {i: c for i, c in enumerate(items, 1)}       # entity -> comp


def refs_from(c):
    """comp 各端口的直接引用 {(target_ent, port)}，端口允许 ±1 模糊。"""
    out = set()
    ports = c.find('COMP_PORTS_LIST')
    if not ports:
        return out
    for pi, port in enumerate(ports.findall('COMP_PORT'), start=1):
        cl = port.find('CONNECT_LIST')
        if not cl:
            continue
        for conn in cl.findall('CONNECT'):
            e = int(conn.text_of('CONNECT_ENTITY_NUM'))
            q = int(conn.text_of('CONNECT_ENTITY_PORT'))
            out.add((e, q))
    return out


ok = tot = 0
examples = []
for l in lines:
    a = (int(l.text_of('LINE_START_ENTITY')), int(l.text_of('LINE_START_PORT')))
    b = (int(l.text_of('LINE_END_ENTITY')), int(l.text_of('LINE_END_PORT')))
    if a[0] <= 0 or b[0] <= 0:
        continue
    tot += 1
    ca, cb = MINV.get(a[0]), MINV.get(b[0])
    hit = False
    if ca is not None:
        ra = refs_from(ca)
        for dp in (0, 1, -1):
            if (b[0], b[1] + dp) in ra or (a[0], a[1] + dp) in ra:
                hit = True
    if not hit and cb is not None:
        rb = refs_from(cb)
        for dp in (0, 1, -1):
            if (a[0], a[1] + dp) in rb or (b[0], b[1] + dp) in rb:
                hit = True
    if hit:
        ok += 1
    elif len(examples) < 5:
        examples.append((a, b))
print(f'scope mapping: line endpoints matching direct refs: {ok}/{tot}')
for e in examples:
    print('  fail:', e)
