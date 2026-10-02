"""Tests for stage.metadata."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from usdguard.checks.stage import StageMetadataCheck
from usdguard.runner import run

if TYPE_CHECKING:
    from collections.abc import Callable

    from pxr import Usd

    StageFactory = Callable[[str], Usd.Stage]

COMPLETE = """
#usda 1.0
(
    defaultPrim = "asset"
    metersPerUnit = 0.01
    upAxis = "Y"
)
def Xform "asset" {}
"""


def messages(stage: Usd.Stage, check: StageMetadataCheck) -> list[str]:
    return [issue.message for issue in run(stage, [check]).issues]


def test_complete_metadata_passes(make_stage: StageFactory) -> None:
    assert messages(make_stage(COMPLETE), StageMetadataCheck()) == []


def test_missing_metadata_is_reported(make_stage: StageFactory) -> None:
    stage = make_stage('def Xform "asset" {}')

    assert messages(stage, StageMetadataCheck()) == [
        "defaultPrim is not authored",
        "metersPerUnit is not authored; expected 0.01",
        "upAxis is not authored; expected 'Y'",
    ]


def test_unexpected_values_are_reported(make_stage: StageFactory) -> None:
    stage = make_stage(
        """
        #usda 1.0
        (
            defaultPrim = "missing"
            metersPerUnit = 1
            upAxis = "Z"
        )
        def Xform "asset" {}
        """
    )

    assert messages(stage, StageMetadataCheck()) == [
        "defaultPrim 'missing' does not name an existing prim",
        "metersPerUnit is 1; expected 0.01",
        "upAxis is 'Z'; expected 'Y'",
    ]


def test_meters_per_unit_tolerates_float_noise(
    make_stage: StageFactory,
) -> None:
    stage = make_stage(COMPLETE.replace("0.01", "0.010000000000000002"))

    assert messages(stage, StageMetadataCheck()) == []


def test_expectations_are_configurable(make_stage: StageFactory) -> None:
    stage = make_stage('#usda 1.0\n(\n metersPerUnit = 1\n upAxis = "Z"\n)')
    check = StageMetadataCheck(
        up_axis="Z", meters_per_unit=1, require_default_prim=False
    )

    assert messages(stage, check) == []


def test_each_test_can_be_disabled(make_stage: StageFactory) -> None:
    check = StageMetadataCheck(
        up_axis=None, meters_per_unit=None, require_default_prim=False
    )

    assert messages(make_stage('def Xform "asset" {}'), check) == []


@pytest.mark.parametrize(
    ("options", "message"),
    [
        ({"up_axis": "X"}, "up_axis must be one of 'Y', 'Z', not 'X'"),
        ({"meters_per_unit": 0}, "meters_per_unit must be a positive"),
        ({"meters_per_unit": "1"}, "meters_per_unit must be a number"),
        ({"meters_per_unit": True}, "meters_per_unit must be a number"),
        ({"require_default_prim": "yes"}, "must be true or false"),
    ],
)
def test_invalid_options_are_rejected(
    options: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        StageMetadataCheck(**options)  # type: ignore[arg-type]
