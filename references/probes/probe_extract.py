"""探针：从 .ame 中提取指定成员到目录，并打印关键文件的头部内容。"""
import os
import sys
import tarfile

SKIP_EXT = (".results", ".mexw64", ".obj", ".c", ".ameperf", ".pl", ".ssf", ".vl.crc")

def extract(path: str, outdir: str):
    os.makedirs(outdir, exist_ok=True)
    with tarfile.open(path, mode="r:") as tf:
        for m in tf.getmembers():
            if not m.isfile():
                continue
            if m.name.endswith(SKIP_EXT):
                continue
            tf.extract(m, outdir, filter="data")
            print(f"  extracted: {m.name} ({m.size}B)")

def head(path: str, n: int = 60):
    print(f"\n----- head {n} of {os.path.basename(path)} -----")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i >= n:
                    print("  ... (truncated)")
                    break
                print(f"  {i+1:4d}| {line.rstrip()}")
    except Exception as e:
        print(f"  ERROR: {e}")

if __name__ == "__main__":
    ame, outdir = sys.argv[1], sys.argv[2]
    extract(ame, outdir)
    for fn in sorted(os.listdir(outdir)):
        full = os.path.join(outdir, fn)
        if os.path.isdir(full):
            for sub in sorted(os.listdir(full)):
                head(os.path.join(full, sub), 40)
        else:
            head(full)
