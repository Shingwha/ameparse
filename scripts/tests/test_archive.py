"""tar 归档访问层测试。"""

from __future__ import annotations

from ameparse import Amefile, Member
from _fixtures import make_ame_bytes


def test_members_and_names(ame_path):
    with Amefile(ame_path) as ame:
        names = ame.names()
        assert "TestModel_.cir" in names
        assert "TestModel_.results" in names
        assert ame.model_name == "TestModel"
        members = ame.members()
        cir = next(m for m in members if m.name == "TestModel_.cir")
        assert isinstance(cir, Member) and cir.is_file and cir.size > 0
        assert cir.to_dict() == {"name": cir.name, "size": cir.size, "is_file": True}


def test_read_and_exists(ame_path):
    with Amefile(ame_path) as ame:
        assert ame.exists(".cir")
        assert not ame.exists(".nonexistent")
        assert ame.read(".cir") is not None
        assert ame.read(".nonexistent") is None
        text = ame.read_text(".cir")
        assert text.startswith("<?xml")
        # 大成员可读但不进解析白名单（由 core 的 SKIP 控制）
        assert ame.read_text(".results") is not None


def test_from_bytes():
    data = make_ame_bytes("BytesModel")
    ame = Amefile.from_bytes(data)
    assert ame.model_name == "BytesModel"
    assert ame.exists(".cir")
    assert b"<CIR" in ame.read(".cir")
