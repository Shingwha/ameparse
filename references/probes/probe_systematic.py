"""系统检验实体编号假设。

假设空间：
  M1  全部条目(comp+line)按 CIRCUIT_SCOPE_ID 排序赋号 1..507
  M2  仅 comp 按 CIRCUIT_SCOPE_ID 排序赋号 1..380（连线另论）
  M3  全部条目按文件出现顺序（对照组，已知失败）

检验：
  T-A 线端点兼容：线 (A,Pa)-(B,Pb)，持有 CONNECT(ℓ,·) 的两个组件应恰好是 A、B，
      且引用所在端口号 = Pa / Pb  → 验证“CONNECT 引用指向线”
  T-B 端点即直连：线 (A,Pa)-(B,Pb) 应在 comp(A) 的端口 Pa 处有 CONNECT(B,·)
      → 验证“CONNECT 引用指向组件、线只是图形副本”
  T-C 对称性：(A,P)→(E,Q) 与 (E,Q)→(A,P) 互为镜像 → 验证双向存储
"""
import sys
from pathlib import Path
sys.path.insert(0, '.')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "ameparse"))
from ameparse.tolerant import parse
from collections import defaultdict

raw = open(sys.argv[1] if len(sys.argv) > 1 else 'out_HEV_GWCD_40/HEV_GWCD_40_.cir', encoding='latin-1').read()
root = parse(raw)
circuit = root.find('CIR').find('CIRCUIT')


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


comps = dfs_comps(circuit.find('COMPS_LIST'))
lines = list(root.iter('LINE'))
all_items = comps + lines

# 每个组件的端口 -> [(entity, port)]，以及端口号 -> 引用集合
comp_port_refs = {}   # comp_idx -> {port_no(1-based): [(E,Q)]}
for i, c in enumerate(comps):
    d = {}
    ports = c.find('COMP_PORTS_LIST')
    if ports:
        for pi, port in enumerate(ports.findall('COMP_PORT'), start=1):
            cl = port.find('CONNECT_LIST')
            if cl:
                d[pi] = [(int(conn.text_of('CONNECT_ENTITY_NUM')),
                          int(conn.text_of('CONNECT_ENTITY_PORT')))
                         for conn in cl.findall('CONNECT')]
    comp_port_refs[i] = d

def scope(c):
    return int(c.text_of('CIRCUIT_SCOPE_ID') or 0)

def run(name, ent_of_comp, ent_of_line):
    """ent_of_comp: comp_idx -> entity; ent_of_line: line_idx -> entity"""
    comp_by_ent = {e: i for i, e in ent_of_comp.items()}
    line_by_ent = {e: i for i, e in ent_of_line.items()}

    # T-A: 对每条线，找引用其实体号的组件端口
    ref_index = defaultdict(list)   # (entity, None) -> [(comp_idx, port_no, Q)]
    for i, d in comp_port_refs.items():
        for p, refs in d.items():
            for (e, q) in refs:
                ref_index[(e, None)].append((i, p, q))
                ref_index[(e, q)].append((i, p, q))

    ta_ok = ta_tot = 0
    ta_fail = []
    for li, l in enumerate(lines):
        le = ent_of_line.get(li)
        if le is None:
            continue
        a = (int(l.text_of('LINE_START_ENTITY')), int(l.text_of('LINE_START_PORT')))
        b = (int(l.text_of('LINE_END_ENTITY')), int(l.text_of('LINE_END_PORT')))
        if a[0] <= 0 or b[0] <= 0:
            continue
        for (ae, ap) in (a, b):
            ta_tot += 1
            # 组件 ae 必须在端口 ap（±1）处引用线实体 le
            ca = comp_by_ent.get(ae)
            hit = False
            if ca is not None:
                for dp in (0, 1, -1):
                    for (e, q) in comp_port_refs[ca].get(ap + dp, []):
                        if e == le:
                            hit = True
            if hit:
                ta_ok += 1
            elif len(ta_fail) < 4:
                ta_fail.append((le, a, b))
    print(f'[{name}] T-A 线端点兼容: {ta_ok}/{ta_tot}', ta_fail[:2] if ta_fail else '')

    # T-B: 线端点 (A,Pa)-(B,Pb) 应为 comp(A) 端口 Pa 上的直接 CONNECT
    tb_ok = tb_tot = 0
    tb_fail = []
    for l in lines:
        a = (int(l.text_of('LINE_START_ENTITY')), int(l.text_of('LINE_START_PORT')))
        b = (int(l.text_of('LINE_END_ENTITY')), int(l.text_of('LINE_END_PORT')))
        if a[0] <= 0 or b[0] <= 0:
            continue
        tb_tot += 1
        ca, cb = comp_by_ent.get(a[0]), comp_by_ent.get(b[0])
        hit = False
        for cx, other, port in ((ca, b, a[1]), (cb, a, b[1])):
            if cx is None:
                continue
            for dp in (0, 1, -1):
                for (e, q) in comp_port_refs[cx].get(port + dp, []):
                    if e == other[0]:
                        hit = True
        if hit:
            tb_ok += 1
        elif len(tb_fail) < 4:
            tb_fail.append((a, b))
    print(f'[{name}] T-B 端点即直连: {tb_ok}/{tb_tot}', tb_fail[:2] if tb_fail else '')

    # T-C: 对称性
    fwd = set()
    for i, d in comp_port_refs.items():
        for p, refs in d.items():
            for (e, q) in refs:
                if e in comp_by_ent:
                    fwd.add((ent_of_comp[i], p, e, q))
    sym = sum(1 for (x, p, e, q) in fwd if (e, q, x, p) in fwd)
    print(f'[{name}] T-C 对称: {sym}/{len(fwd)}')


# M1: comps+lines 按 scope 排序
items_sorted = sorted(range(len(all_items)), key=lambda i: scope(all_items[i]))
ent1 = {}
for rank, i in enumerate(items_sorted, start=1):
    ent1[i] = rank
run('M1 scope(comp+line)',
    {i: ent1[i] for i in range(len(comps))},
    {i: ent1[len(comps) + i] for i in range(len(lines))})

# M2: 仅 comps 按 scope 排序
comps_sorted = sorted(range(len(comps)), key=lambda i: scope(comps[i]))
ent2 = {i: r for r, i in enumerate(comps_sorted, start=1)}
lines_sorted = sorted(range(len(lines)), key=lambda i: scope(lines[i]))
entl2 = {i: len(comps) + r for r, i in enumerate(lines_sorted, start=1)}
run('M2 scope(comp only)', ent2, entl2)

# M3: 文件顺序（对照组）
run('M3 file order',
    {i: i + 1 for i in range(len(comps))},
    {i: len(comps) + i + 1 for i in range(len(lines))})
