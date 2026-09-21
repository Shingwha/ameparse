"""序列化测试：to_dict / compact_card / export 结构 / CSV（纯合成模型）。

真实模型的黄金回归由使用方在模型侧维护独立回归套件（随模型走）。
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pytest

from ameparse import Model
from ameparse.export import compact_card, write_param_csv, write_var_csv

pytestmark_synthetic = pytest.mark.usefixtures("model")


def test_to_dict_structure(model):
    card = model.to_dict()
    assert card["schema_version"] == 1
    assert card["model"] == "TestModel"
    assert card["ame_version"] == "2410"
    assert card["counts"]["components"] == 3
    assert card["counts"]["supercomponents"] == 1
    assert card["model_io"]["states"] == 2
    assert card["simulation"]["final_time"] == 40000.0
    assert card["saved_variables"][0]["data_path"] == "q1@pump01"
    assert card["declared_variables"][1]["hidden"] is True
    # .results 不进 archive_members
    assert all(not m["name"].endswith(".results") for m in card["archive_members"])
    # 参数声明合并
    pump = next(c for c in card["components"] if c["alias"] == "pump01")
    p = pump["params"][0]
    assert p["id"] == "displ@pump01" and p["value"] == 71.0
    assert p["param_id"] == 1 and p["data_path"] == "displ@pump01"
    # 图可用
    assert card["graph"]["available"] is True
    # JSON 可序列化
    json.dumps(card, ensure_ascii=False)


def test_compact_card(model):
    card = compact_card(model)
    assert card["model"] == "TestModel"
    assert card["states"] == 2
    assert card["counts"]["components"] == 3
    pump = card["components"][0]
    assert pump["params"][0] == {
        "id": "displ@pump01", "value": 71.0, "unit": "cc/rev",
        "default": 50.0, "min": "0", "max": "1.00000000000000e+30",
    }
    assert "edges" in card and card["counts"]["edges"] == 1
    assert card["observable_variables"] == ["q1@pump01"]


def test_csv_tables(model, tmp_path):
    p = tmp_path / "p.csv"
    v = tmp_path / "v.csv"
    n = write_param_csv(model, p)
    assert n == 3
    rows = list(csv.reader(p.read_text(encoding="utf-8-sig").splitlines()))
    assert rows[0][:6] == ["model", "alias", "path", "submodel", "instance", "param_id"]
    assert rows[1][0] == "TestModel" and rows[1][1] == "pump01"
    assert rows[1][5] == "1"                          # param_id（声明合并）
    assert rows[1][9] == "71.0"                       # value

    n = write_var_csv(model, v)
    assert n == 3
    rows = list(csv.reader(v.read_text(encoding="utf-8-sig").splitlines()))
    # w@pump01 是隐藏变量（id 为第 12 列，hidden 第 10 列）
    wrow = next(r for r in rows[1:] if r[11] == "w@pump01")
    assert wrow[9] == "True"                          # hidden


def test_to_csv(model, tmp_path):
    paths = model.to_csv(tmp_path)
    assert paths["params"].name == "TestModel.params.csv"
    assert paths["variables"].exists()


def test_export_structure(model, tmp_path):
    """export() 输出英文化目录结构：sources/ + cards/ + csv/。

    源文件以裸扩展名命名（cir/param/...，与 tar 成员视图一致）。
    """
    from ameparse.export import export
    written = export(model, tmp_path)
    assert (tmp_path / "sources" / "TestModel" / "cir").exists()
    assert (tmp_path / "sources" / "TestModel" / "param").exists()
    full = tmp_path / "cards" / "TestModel.full.json"
    compact = tmp_path / "cards" / "TestModel.compact.json"
    assert full.exists() and compact.exists()
    assert json.loads(full.read_text(encoding="utf-8"))["model"] == "TestModel"
    assert json.loads(compact.read_text(encoding="utf-8"))["states"] == 2
    assert (tmp_path / "csv" / "TestModel.params.csv").exists()
    assert (tmp_path / "csv" / "TestModel.variables.csv").exists()
    assert set(written) == {"sources", "full_card", "compact_card",
                            "params_csv", "variables_csv"}
