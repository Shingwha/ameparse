"""探针：检验候选实体编号映射——每条线的两端组件必须在对应端口引用该线的实体号。"""
import sys
sys.path.insert(0, '.')
from collections import defaultdict
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


def comp_ref_ports(c):
    d = {}
    ports = c.find('COMP_PORTS_LIST')
    if not ports:
        return d
    for pi, port in enumerate(ports.findall('COMP_PORT'), start=1):
        cl = port.find('CONNECT_LIST')
        if not cl:
            continue
        for conn in cl.findall('CONNECT'):
            e = int(conn.text_of('CONNECT_ENTITY_NUM'))
            d.setdefault(e, set()).add(pi)
    return d


def m_dfs():
    cm = {id(c): i for i, c in enumerate(allc, 1)}
    lm = {id(l): len(allc) + i for i, l in enumerate(alll, 1)}
    return 'dfs_comps_then_lines', cm, lm


def m_doc_interleaved():
    seq = []

    def walk_cir(cir):
        cl = cir.find('COMPS_LIST')
        if cl is not None:
            for c in cl.findall('COMP'):
                seq.append(('C', c))
                sc = c.find('SUPERCOMPONENT')
                if sc is not None:
                    nc = sc.find('CIRCUIT')
                    if nc is not None:
                        walk_cir(nc)
        ll = cir.find('LINES_LIST')
        if ll is not None:
            for l in ll.findall('LINE'):
                seq.append(('L', l))

    walk_cir(circuit)
    ent = {(k, id(n)): i for i, (k, n) in enumerate(seq, 1)}
    cm = {id(c): ent[('C', id(c))] for c in allc}
    lm = {id(l): ent[('L', id(l))] for l in alll}
    return 'doc_interleaved', cm, lm


for builder in (m_dfs, m_doc_interleaved):
    name, cm, lm = builder()
    refidx = defaultdict(set)  # (ref_entity, port) -> comp entity set
    for c in allc:
        ci = cm[id(c)]
        for e, ports in comp_ref_ports(c).items():
            for p in ports:
                refidx[(e, p)].add(ci)

    ok = tot = 0
    fails = []
    for l in alll:
        le = lm[id(l)]
        a = (int(l.text_of('LINE_START_ENTITY')), int(l.text_of('LINE_START_PORT')))
        b = (int(l.text_of('LINE_END_ENTITY')), int(l.text_of('LINE_END_PORT')))
        for (ae, ap) in (a, b):
            if ae <= 0:
                continue
            tot += 1
            hit = any(ae in refidx.get((le, ap + dp), set()) for dp in (0, 1, -1))
            if hit:
                ok += 1
            elif len(fails) < 5:
                fails.append((le, a, b))
    print(f'{name}: line-endpoint compatible {ok}/{tot}')
    for f in fails:
        print('   fail:', f)
