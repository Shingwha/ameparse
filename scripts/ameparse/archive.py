"""``.ame`` 归档访问：物理格式是 tar（POSIX/GNU），直接可开，无需外部工具。

tar 内成员以 ``模型名_.扩展名`` 命名（如 ``HEV_GWCD_40_.cir``），
少量成员带子路径（如 ``模型名_.props/properties.xml``）。
"""

from __future__ import annotations

import io
import re
import tarfile
from dataclasses import dataclass

# XML 头部的 encoding 声明
_DECL_RE = re.compile(rb'encoding="([A-Za-z0-9_.\-]+)"')

# 声明成这些编码时仍先按 UTF-8 试：AMESim 把 .cir 标成 ISO-8859-1，
# 实际写的却是 UTF-8（实测舱体与 PB62 两个模型），照声明解码会把中文
# 标题全部变成乱码，而 UTF-8 是 ASCII 超集、纯 ASCII 内容两者等价。
_TRY_UTF8_FIRST = ("iso-8859-1", "latin-1", "latin1", "us-ascii", "ascii", "")


def decode_text(data: bytes, default: str = "latin-1") -> str:
    """按 XML 声明解码，未声明或声明为 latin 系则先试 UTF-8。

    UTF-8 解不出来才退回 ``default``（``errors="replace"``，绝不抛异常）。
    """
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        # UTF-16 BOM：声明本身也是 UTF-16 编码的，别指望用正则认出它
        return data.decode("utf-16", errors="replace")
    decl = _DECL_RE.search(data[:200])
    enc = decl.group(1).decode("ascii", "ignore").lower() if decl else ""
    if enc not in _TRY_UTF8_FIRST:
        try:
            return data.decode(enc, errors="replace")
        except LookupError:
            pass
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(default, errors="replace")


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
        return decode_text(data, encoding)

    # -- 便捷属性 -------------------------------------------------------
    @property
    def model_name(self) -> str:
        """取第一个成员的公共前缀，即模型名（去掉末尾 ``_.``）。"""
        for m in self._tf.getmembers():
            base = m.name.rsplit("/", 1)[-1]
            if "_." in base:
                return base.split("_.", 1)[0]
        return ""
