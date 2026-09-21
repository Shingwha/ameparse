"""从编译产物 .c 提取编译态拓扑：

机制 a（函数调用型）:  n = K; sub_(&n, &v[a], &v[b], ..., RPx, IPx, TPx, ISx, PSx, ...);
                      AME_POST_SUBMODCALL_WITH_DISCON(..., "SUBMODEL", K);
   端口变量按 extern 签名顺序对应 v[] 槽位；两个实例的端口变量共享同一槽位 = 直连。
机制 c（内联方程型）:  v[X] = v[Y] + v[Z];  —— 简单子模型被内联，槽位关系即连线。
"""
import re
import sys
from collections import defaultdict

# ---- extern 签名: sub_ (int *n, double *port_1_v2, ..., int *IP, ...) --------
_EXTERN_RE = re.compile(
    r"extern\s+void\s+(\w+)_\(\s*int\s*\*\s*n\s*,([^;]*?)\)\s*;", re.S)

# ---- 调用块 ------------------------------------------------------------------
_N_ASSIGN = re.compile(r"\bn\s*=\s*(\d+)\s*;")
_POST_CALL = re.compile(
    r'AME_POST_SUBMODCALL_\w+\([^)]*?"([A-Z0-9_]+)"\s*,\s*(\d+)\s*\)')
_CALL_ARGS = re.compile(r"(\w+)_\(\s*&\s*n\s*,([^;]*?)\)\s*;", re.S)
_V_ARG = re.compile(r"&\s*v\s*\[\s*(\d+)\s*\]")


def parse_externs(text):
    """sub_ -> [arg_name, ...]（去掉 n 与 RP/IP/TP/IS/PS/sflag/t 等非变量参数）"""
    sigs = {}
    for m in _EXTERN_RE.finditer(text):
        fname, argstr = m.group(1), m.group(2)
        args = []
        for part in argstr.split(","):
            part = part.strip()
            if not part:
                continue
            am = re.match(r"double\s*\*\s*(\w+)", part)
            if am:
                args.append(am.group(1))
            # int *IP / RPx / IPx / TPx / ISx / PSx / &sflag / &t 等跳过
        sigs[fname] = args
    return sigs


def parse_calls(text, sigs):
    """返回 {(submodel, instance): [(arg_name, slot), ...]}（多阶段调用合并去重）"""
    out = defaultdict(dict)   # key -> {arg_name: slot}
    # 按 POST 宏切分：每个调用块以 AME_POST_SUBMODCALL 结尾
    for m in _POST_CALL.finditer(text):
        sub, inst = m.group(1), int(m.group(2))
        # 向前找最近的调用语句（同一 block 内）
        start = text.rfind("\n", 0, m.start())
        # 向前扫描最多 3000 字符找 func_(&n, ...)
        window = text[max(0, m.start() - 3000):m.start()]
        calls = list(_CALL_ARGS.finditer(window))
        if not calls:
            continue
        cm = calls[-1]
        fname, argstr = cm.group(1), cm.group(2)
        args = sigs.get(fname)
        if args is None:
            continue
        vids = [int(x) for x in _V_ARG.findall(argstr)]
        # v 参数按序对应签名中的 double* 参数
        d = out[(sub, inst)]
        for name, slot in zip(args, vids):
            if name.startswith("port_") or name.startswith("int_"):
                d[name] = slot
    return out


def main():
    text = open(sys.argv[1], encoding="latin-1").read()
    sigs = parse_externs(text)
    print(f"extern 签名数: {len(sigs)}")
    calls = parse_calls(text, sigs)
    print(f"调用块解析: {len(calls)} 个 (submodel, instance)")

    # 槽位 -> [(key, arg_name)]
    slot_map = defaultdict(list)
    for key, d in calls.items():
        for name, slot in d.items():
            slot_map[slot].append((key, name))

    shared = {s: v for s, v in slot_map.items() if len(v) > 1}
    print(f"v[] 槽位总数: {len(slot_map)}，被多实例共享的: {len(shared)}")

    # 统计：仅 port_ 变量共享的槽位（候选直连）
    port_shared = {}
    for s, v in shared.items():
        pv = [(k, n) for k, n in v if n.startswith("port_")]
        if len(pv) > 1:
            port_shared[s] = pv
    print(f"端口变量共享槽位（候选连接）: {len(port_shared)}")
    for s, pv in list(port_shared.items())[:8]:
        print(f"  v[{s}]: {pv}")

    # 直连边（去重）
    edges = set()
    for s, pv in port_shared.items():
        for i in range(len(pv)):
            for j in range(i + 1, len(pv)):
                (k1, n1), (k2, n2) = pv[i], pv[j]
                edges.add((k1, n1, k2, n2))
    print(f"直连边（实例级，含端口变量名）: {len(edges)}")
    for e in list(edges)[:8]:
        print("  ", e)


if __name__ == "__main__":
    main()
