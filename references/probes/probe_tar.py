"""探针：列出 .ame (tar) 内部成员清单及大小。"""
import sys
import tarfile

def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"

for path in sys.argv[1:]:
    print(f"\n===== {path} =====")
    with tarfile.open(path, mode="r:") as tf:
        members = tf.getmembers()
        print(f"成员总数: {len(members)}")
        total = sum(m.size for m in members)
        print(f"解压总大小: {human(total)}")
        for m in sorted(members, key=lambda x: x.name):
            print(f"  {human(m.size):>10}  {m.name}")
