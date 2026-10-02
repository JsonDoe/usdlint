"""Tests for naming.prim_name."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from usdguard.checks.naming import PrimNameCheck
from usdguard.runner import run

if TYPE_CHECKING:
    from collections.abc import Callable

    from pxr import Usd

    StageFactory = Callable[[str], Usd.Stage]

RULES = {
    "Mesh": "^[a-z][a-zA-Z0-9]*_GEO$",
    "Xform": "^[a-z][a-zA-Z0-9]*_GRP$",
}

GOOD_SCENE = """
def Xform "chair_GRP"
{
    def Mesh "seat_GEO" {}
    def Scope "Looks" {}
}
"""

BAD_SCENE = """
def Xform "chair_GRP"
{
    def Mesh "seat_GEO" {}
    def Mesh "Leg1" {}
    def Xform "legs" {}
}
"""


def test_names_matching_their_rule_pass(make_stage: StageFactory) -> None:
    report = run(make_stage(GOOD_SCENE), [PrimNameCheck(rules=RULES)])

    assert report.issues == ()


def test_names_not_matching_their_rule_are_reported(
    make_stage: StageFactory,
) -> None:
    report = run(make_stage(BAD_SCENE), [PrimNameCheck(rules=RULES)])

    assert [(i.prim_path, i.message) for i in report.issues] == [
        (
            "/chair_GRP/Leg1",
            "Mesh name 'Leg1' does not match '^[a-z][a-zA-Z0-9]*_GEO$'",
        ),
        (
            "/chair_GRP/legs",
            "Xform name 'legs' does not match '^[a-z][a-zA-Z0-9]*_GRP$'",
        ),
    ]


def test_the_whole_name_must_match(make_stage: StageFactory) -> None:
    stage = make_stage('def Mesh "body_GEO_old" {}')

    report = run(stage, [PrimNameCheck(rules={"Mesh": "[a-z]+_GEO"})])

    assert [issue.prim_path for issue in report.issues] == ["/body_GEO_old"]


def test_without_rules_nothing_is_checked(make_stage: StageFactory) -> None:
    assert run(make_stage(BAD_SCENE), [PrimNameCheck()]).issues == ()


def test_prims_in_prototypes_are_reported_once_by_prototype_path(
    make_stage: StageFactory,
) -> None:
    stage = make_stage(
        """
        def Xform "set_GRP"
        {
            def Xform "tree1_GRP" (instanceable = true
                prepend references = </tree_src>) {}
            def Xform "tree2_GRP" (instanceable = true
                prepend references = </tree_src>) {}
        }
        over "tree_src"
        {
            def Mesh "Leaves" {}
        }
        """
    )

    report = run(stage, [PrimNameCheck(rules=RULES)])

    assert [issue.prim_path for issue in report.issues] == [
        "/__Prototype_1/Leaves"
    ]


def test_invalid_regular_expressions_are_rejected() -> None:
    with pytest.raises(ValueError, match="invalid regular expression"):
        PrimNameCheck(rules={"Mesh": "([a-z]"})


@pytest.mark.parametrize("rules", [{"Mesh": 3}, ["Mesh"], "Mesh"])
def test_rules_must_map_type_names_to_strings(rules: object) -> None:
    with pytest.raises(ValueError, match="rules must be a table of strings"):
        PrimNameCheck(rules=rules)  # type: ignore[arg-type]
