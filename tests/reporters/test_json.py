"""Tests for the JSON reporter and its documented schema."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import usdguard
from usdguard.reporters import render
from usdguard.reporters.json import SCHEMA_VERSION, render_json

if TYPE_CHECKING:
    from usdguard.reporters import StageResult


def test_json_report_follows_schema_version_1(
    results: list[StageResult],
) -> None:
    document = json.loads(render_json(results, profile="studio"))

    assert document["schema_version"] == SCHEMA_VERSION == 1
    assert document["tool"] == {
        "name": "usdguard",
        "version": usdguard.__version__,
    }
    assert document["profile"] == "studio"
    assert [run["stage"] for run in document["runs"]] == [
        "assets/chair/chair.usda",
        "assets/table.usda",
        "missing.usda",
    ]
    first = document["runs"][0]
    assert first["summary"] == {"error": 1, "warning": 1, "info": 1}
    assert first["issues"][1] == {
        "check_id": "geom.extent",
        "severity": "warning",
        "message": "Mesh has no authored extent",
        "prim_path": "/chair/seat",
        "layer": "assets/chair/geo.usda",
    }
    assert document["runs"][1]["issues"] == []
    assert document["runs"][2]["issues"][0]["check_id"] == "usdguard.open"


def test_json_report_is_deterministic(results: list[StageResult]) -> None:
    text = render("json", results, profile="default")

    assert text == render("json", list(results), profile="default")
    assert text.endswith("}\n")
    assert list(json.loads(text)) == sorted(json.loads(text))
    assert text.index('"check_id"') < text.index('"layer"')
