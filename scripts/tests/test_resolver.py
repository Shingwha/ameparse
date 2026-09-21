"""编译态拓扑（.c 解析）与连接图解析（GraphResolver）测试。"""

from __future__ import annotations

from ameparse.linking import GraphResolver
from ameparse.model import PortRef
from ameparse.parsers import CompiledParser, build_topology, parse_cir, parse_param_file, parse_var_file
from _fixtures import CIR, FAKE_C, PARAM, VAR


def _alias_of():
    out = {}
    for d in parse_param_file(PARAM) + parse_var_file(VAR):
        if d.data_path:
            out.setdefault((d.submodel, d.instance), d.data_path.split("@", 1)[-1])
    return out


def test_compiled_parse_instances_and_slots():
    topo = CompiledParser().parse(FAKE_C)
    assert set(topo.instances) == {("PUROT00", 1), ("SOUROT00", 2)}
    inst = topo.instances[("PUROT00", 1)]
    assert inst.variables == [("q1", "Basic var", 5)]
    assert topo.slot_users[5] == [(("PUROT00", 1), "q1"), (("SOUROT00", 2), "pout")]


def test_attach_ports_direct_edges():
    """共享槽位（v[5]）→ pump01.1 与 source2.1 直连。"""
    cir = parse_cir(CIR)
    topo = build_topology(FAKE_C, _alias_of(), cir.port_map())
    assert topo.instances[("PUROT00", 1)].alias == "pump01"
    assert sorted(topo.direct_edges) == [(("pump01", 1), ("source2", 1))]
    assert topo.neighbors("pump01") == {1: [("source2", 1)]}


def test_resolver_wire_detection():
    """实体 2 是 DIRECT 线（双挂载且编译态互为邻居）→ 解析为别名级边。"""
    cir = parse_cir(CIR)
    topo = build_topology(FAKE_C, _alias_of(), cir.port_map())
    g = GraphResolver(cir, topo).resolve()
    assert g.stats["wires"] == 1
    assert g.stats["edges"] == 1
    from ameparse.model import Edge
    assert g.edges() == [Edge(PortRef("pump01", 1), PortRef("source2", 1),
                              "direct", "hyd", "hyd")]
    # 边带端口域：可按域过滤（回路级分析）
    assert g.edges(domain="hyd") == g.edges()
    assert g.edges(domain="signal") == []
    nb = g.to_dict()["neighbors"]
    assert nb["pump01"] == {1: [["source2", 1]]}
    assert nb["source2"] == {1: [["pump01", 1]]}


def test_graph_queries():
    cir = parse_cir(CIR)
    g = GraphResolver(cir, build_topology(FAKE_C, _alias_of(), cir.port_map())).resolve()
    assert g.subgraph("pump01", hops=3) == {"pump01", "source2"}
    assert [sorted(s) for s in g.subcircuits()] == [["pump01", "source2"]]
    assert g.shortest_path("pump01", "source2") == ["pump01", "source2"]
    assert g.shortest_path("pump01", "inner3") is None
    assert g.ports_of("pump01") == {1: [PortRef("source2", 1)]}
