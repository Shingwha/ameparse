"""``.ame`` 归档访问：物理格式是 tar（POSIX/GNU），直接可开，无需外部工具。

tar 内成员以 ``模型名_.扩展名`` 命名（如 ``HEV_GWCD_40_.cir``），
少量成员带子路径（如 ``模型名_.props/properties.xml``）。
"""

from __future__ import annotations

import io
import tarfile
from dataclasses import dataclass


@dataclass(frozen=True)
class Member:
    name: str
    size: int
    is_file: bool

    def to_dict(self) -> dict:
        return {"name": self.name, "size": self.size, "is_file": self.is_file}


class Amefile:
    """只读访问一个 ``.ame``（tar）归档。"""

    def __init__(self, path: str):
        self.path = str(path)
        self._tf = tarfile.open(self.path, mode="r:")

    @classmethod
    def from_bytes(cls, data: bytes) -> "Amefile":
        """从内存字节构造（测试/管道场景）。"""
        obj = cls.__new__(cls)
        obj.path = "<bytes>"
        obj._tf = tarfile.open(fileobj=io.BytesIO(data), mode="r:")
        return obj

    def __enter__(self) -> "Amefile":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._tf.close()

    # -- 成员 -----------------------------------------------------------
    def members(self) -> list[Member]:
        return [
            Member(m.name, m.size, m.isfile())
            for m in sorted(self._tf.getmembers(), key=lambda x: x.name)
        ]

    def names(self) -> list[str]:
        return self._tf.getnames()

    def _find(self, suffix: str) -> str | None:
        suffix = suffix.lower()
        for m in self._tf.getmembers():
            if m.isfile() and m.name.lower().endswith(suffix):
                return m.name
        return None

    def exists(self, suffix: str) -> bool:
        return self._find(suffix) is not None

    def read(self, suffix: str) -> bytes | None:
        """按扩展名读取成员内容（大小写不敏感）；不存在返回 None。"""
        name = self._find(suffix)
        if name is None:
            return None
        f = self._tf.extractfile(name)
        return f.read() if f else None

    def read_exact(self, name: str) -> bytes | None:
        """按精确成员名读取。"""
        try:
            f = self._tf.extractfile(name)
        except KeyError:
            return None
        return f.read() if f else None

    def read_text(self, suffix: str, encoding: str = "latin-1") -> str | None:
        data = self.read(suffix)
        if data is None:
            return None
        return data.decode(encoding, errors="replace")

    # -- 便捷属性 -------------------------------------------------------
    @property
    def model_name(self) -> str:
        """取第一个成员的公共前缀，即模型名（去掉末尾 ``_.``）。"""
        for m in self._tf.getmembers():
            base = m.name.rsplit("/", 1)[-1]
            if "_." in base:
                return base.split("_.", 1)[0]
        return ""
