"""Tests for compliance.usdchecker."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from pxr import Usd, UsdValidation

from usdguard.checks.compliance import UsdCheckerCheck
from usdguard.core import Issue, Severity
from usdguard.runner import run

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    StageFactory = Callable[[str], Usd.Stage]

NESTED_GPRIMS = "usdGeomValidators:EncapsulationChecker"


def open_data(data_dir: Path, name: str) -> Usd.Stage:
    return Usd.Stage.Open(str(data_dir / "compliance" / name))


def test_compliant_stage_passes(data_dir: Path) -> None:
    stage = open_data(data_dir, "clean.usda")

    assert run(stage, [UsdCheckerCheck()]).issues == ()


def test_validator_errors_are_reported(data_dir: Path) -> None:
    stage = open_data(data_dir, "nested_gprims.usda")

    report = run(stage, [UsdCheckerCheck()])

    (issue,) = report.issues
    assert issue.severity is Severity.ERROR
    assert issue.prim_path == "/chair/outer/inner"
    assert issue.message.startswith(
        f"{NESTED_GPRIMS}.InvalidNestedGprims: Gprim </chair/outer/inner>"
    )


def test_keywords_select_validators(data_dir: Path) -> None:
    stage = open_data(data_dir, "nested_gprims.usda")
    check = UsdCheckerCheck(keywords=["UsdShadeValidators"])

    assert NESTED_GPRIMS not in check.validator_names
    assert run(stage, [check]).issues == ()


def test_excluded_validators_do_not_run(data_dir: Path) -> None:
    stage = open_data(data_dir, "nested_gprims.usda")

    report = run(stage, [UsdCheckerCheck(exclude=[NESTED_GPRIMS])])

    assert report.issues == ()


def test_root_package_validator_is_left_out_like_usdchecker() -> None:
    names = UsdCheckerCheck().validator_names

    assert "usdUtilsValidators:RootPackageValidator" not in names
    assert NESTED_GPRIMS in names


def test_in_memory_stages_are_skipped_with_a_note(
    make_stage: StageFactory,
) -> None:
    stage = make_stage(
        """
        def Mesh "outer"
        {
            def Mesh "inner" {}
        }
        """
    )

    (issue,) = run(stage, [UsdCheckerCheck()]).issues

    assert issue.severity is Severity.INFO
    assert "anonymous" in issue.message


@pytest.mark.parametrize(
    ("options", "message"),
    [
        (
            {"exclude": ["nope:Validator"]},
            "unknown validators: nope:Validator",
        ),
        ({"keywords": ["NoSuchKeyword"]}, "no validator matches keywords"),
        ({"keywords": "UsdGeomValidators"}, "keywords must be a list"),
        ({"exclude": [1]}, "exclude must be a list of strings"),
    ],
)
def test_invalid_options_are_rejected(
    options: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        UsdCheckerCheck(**options)  # type: ignore[arg-type]


def fake_error(
    error_type: object, sites: list[object], *, no_error: bool = False
) -> SimpleNamespace:
    return SimpleNamespace(
        GetType=lambda: error_type,
        HasNoError=lambda: no_error,
        GetSites=lambda: sites,
        GetIdentifier=lambda: "fake:Validator.Name",
        GetMessage=lambda: "message",
    )


def fake_site(
    *, prim: str = "", prop: str = "", layer: object = None
) -> SimpleNamespace:
    return SimpleNamespace(
        IsPrim=lambda: bool(prim),
        IsProperty=lambda: bool(prop),
        GetPrim=lambda: SimpleNamespace(GetPath=lambda: prim),
        GetProperty=lambda: SimpleNamespace(
            GetPrimPath=lambda: prop.split(".")[0]
        ),
        GetLayer=lambda: layer,
    )


def layer(identifier: str, *, anonymous: bool = False) -> SimpleNamespace:
    return SimpleNamespace(identifier=identifier, anonymous=anonymous)


def test_validation_results_map_to_severities() -> None:
    check = UsdCheckerCheck()
    error_types = UsdValidation.ValidationErrorType

    severities = [
        [issue.severity for issue in check._issues(fake_error(kind, []))]
        for kind in (
            error_types.Error,
            error_types.Warn,
            error_types.Info,
            error_types.None_,
        )
    ]
    placeholder = fake_error(error_types.Error, [], no_error=True)

    assert severities == [
        [Severity.ERROR],
        [Severity.WARNING],
        [Severity.INFO],
        [],
    ]
    assert list(check._issues(placeholder)) == []


def test_sites_give_the_prim_path_and_layer() -> None:
    check = UsdCheckerCheck()
    error_types = UsdValidation.ValidationErrorType
    sites = [
        fake_site(layer=layer("anon:1", anonymous=True)),
        fake_site(prop="/a/b.size", layer=layer("/assets/a.usda")),
        fake_site(prim="/ignored", layer=layer("/assets/b.usda")),
    ]

    (issue,) = check._issues(fake_error(error_types.Error, sites))

    assert issue == Issue(
        "compliance.usdchecker",
        Severity.ERROR,
        "fake:Validator.Name: message",
        "/a/b",
        "/assets/a.usda",
    )
