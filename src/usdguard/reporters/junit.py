"""JUnit XML report, for CI systems that display test results.

Each stage is a ``testsuite`` and each check that ran is a ``testcase``,
so a passing check shows up as a passing test. Every issue at or above
the report's ``fail_on`` severity becomes a ``failure`` element of its
check's testcase; less severe issues are listed in ``system-out``. A
stage that cannot be opened has a single testcase with an ``error``
element.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

from usdguard.runner import OPEN_CHECK_ID

if TYPE_CHECKING:
    from usdguard.core import Issue
    from usdguard.reporters import StageResult


def render_junit(results: list[StageResult], *, profile: str) -> str:
    """Render the results as a JUnit XML document.

    Args:
        results: One entry per validated stage.
        profile: Name of the profile used, stored as a suite property.
    """
    root = ET.Element("testsuites", name="usdguard")
    totals = {"tests": 0, "failures": 0, "errors": 0}
    for result in results:
        suite = _suite(result, profile)
        root.append(suite)
        for key in totals:
            totals[key] += int(suite.get(key, "0"))
    for key, value in totals.items():
        root.set(key, str(value))
    ET.indent(root)
    body = ET.tostring(root, encoding="unicode")
    return f'<?xml version="1.0" encoding="utf-8"?>\n{body}\n'


def _suite(result: StageResult, profile: str) -> ET.Element:
    report = result.report
    suite = ET.Element("testsuite", name=result.stage)
    properties = ET.SubElement(suite, "properties")
    ET.SubElement(properties, "property", name="profile", value=profile)
    ET.SubElement(
        properties, "property", name="fail_on", value=report.fail_on.label
    )
    failures = errors = 0
    for check_id in report.check_ids:
        case = ET.SubElement(
            suite, "testcase", classname=result.stage, name=check_id
        )
        issues = [i for i in report.issues if i.check_id == check_id]
        passed: list[Issue] = []
        for issue in issues:
            if check_id == OPEN_CHECK_ID:
                _problem(case, "error", issue)
                errors += 1
            elif issue.severity >= report.fail_on:
                _problem(case, "failure", issue)
                failures += 1
            else:
                passed.append(issue)
        if passed:
            ET.SubElement(case, "system-out").text = "\n".join(
                _describe(issue) for issue in passed
            )
    suite.set("tests", str(len(report.check_ids)))
    suite.set("failures", str(failures))
    suite.set("errors", str(errors))
    suite.set("skipped", "0")
    return suite


def _problem(case: ET.Element, tag: str, issue: Issue) -> None:
    element = ET.SubElement(
        case, tag, message=issue.message, type=issue.severity.label
    )
    element.text = _describe(issue)


def _describe(issue: Issue) -> str:
    parts = [f"[{issue.severity.label}] {issue.message}"]
    if issue.prim_path:
        parts.append(f"prim: {issue.prim_path}")
    if issue.layer:
        parts.append(f"layer: {issue.layer}")
    return "; ".join(parts)
