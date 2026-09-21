"""pytest fixtures：合成 .ame 构造（仓库测试零外部依赖，任意机器可跑）。"""

from __future__ import annotations

import pytest

from _fixtures import make_ame


@pytest.fixture(scope="session")
def ame_path(tmp_path_factory) -> str:
    p = tmp_path_factory.mktemp("ame") / "TestModel.ame"
    return make_ame(p)


@pytest.fixture(scope="session")
def model(ame_path):
    from ameparse import Model
    return Model.from_file(ame_path)
