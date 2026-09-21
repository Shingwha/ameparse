"""集成层：跨成员合并（声明 → 电路对象）、连接图与全局参数引用解析。"""

from .globalrefs import GlobalRef, GlobalRefIndex, GlobalRefResolver
from .linker import Linker
from .resolver import GraphResolver

__all__ = ["GlobalRef", "GlobalRefIndex", "GlobalRefResolver",
           "Linker", "GraphResolver"]
