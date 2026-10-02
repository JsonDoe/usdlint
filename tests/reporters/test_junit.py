"""Tests for the JUnit XML reporter."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from usdguard.reporters import render
from usdguard.reporters.junit import render_junit

if TYPE_CHECKING:
    from usdguard.reporters import StageResult


def parse(results: list[StageResult]) -> ET.Element:
    return ET.fromstring(render_junit(results, profile="studio"))


def test_one_testsuite_per_stage_and_one_testcase_per_check(
    results: list[StageResult],
) -> None:
    root = parse(results)

    suites = root.findall("testsuite")
    assert [suite.get("name") for suite in suites] == [
        "assets/chair/chair.usda",
        "assets/table.usda",
        "missing.usda",
    ]
    assert [case.get("name") for case in suites[0].iter("testcase")] == [
        "geom.extent",
        "naming.prim_name",
        "stage.metadata",
    ]
    assert root.attrib == {
        "name": "usdguard",
        "tests": "7",
        "failures": "1",
        "errors": "1",
    }


def test_issues_at_or_above_fail_on_are_failures(
    results: list[StageResult],
) -> None:
    chair = parse(results).find("testsuite")
    assert chair is not None
    cases = {case.get("name"): case for case in chair.iter("testcase")}

    failure = cases["stage.metadata"].find("failure")
    assert failure is not None
    assert failure.attrib == {
        "message": "upAxis is not authored; expected 'Y'",
        "type": "error",
    }
    assert cases["geom.extent"].find("failure") is None
    system_out = cases["geom.extent"].findtext("system-out")
    assert system_out == (
        "[warning] Mesh has no authored extent; prim: /chair/seat; "
        "layer: assets/chair/geo.usda"
    )
    assert chair.get("failures") == "1"
    properties = {
        prop.get("name"): prop.get("value") for prop in chair.iter("property")
    }
    assert properties == {"profile": "studio", "fail_on": "error"}


def test_stages_that_cannot_open_are_errors(
    results: list[StageResult],
) -> None:
    suite = parse(results).findall("testsuite")[2]

    (case,) = suite.iter("testcase")
    error = case.find("error")
    assert case.get("name") == "usdguard.open"
    assert error is not None
    assert error.get("message") == "Cannot open stage 'missing.usda'"
    assert suite.get("errors") == "1"


def test_junit_report_declares_utf8_and_is_stable(
    results: list[StageResult],
) -> None:
    text = render("junit", results, profile="default")

    assert text.startswith('<?xml version="1.0" encoding="utf-8"?>\n')
    assert text == render("junit", results, profile="default")
