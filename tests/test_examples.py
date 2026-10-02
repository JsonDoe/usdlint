"""The example stages and profiles behave as their README says."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from usdguard import cli
from usdguard.profiles import load_profile
from usdguard.runner import open_stage

EXAMPLES = Path(__file__).parents[1] / "examples"
STAGES = EXAMPLES / "stages"


@pytest.mark.parametrize(
    "name", ["chair.usda", "table.usda", "room_layout.usda"]
)
def test_clean_examples_pass_the_default_profile(
    name: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["check", str(STAGES / name)]) == 0
    assert "  no issues\n" in capsys.readouterr().out


def test_broken_example_fails_every_builtin_check(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stage = str(STAGES / "chair_broken.usda")

    assert cli.main(["check", stage, "--format", "json"]) == 1

    issues = json.loads(capsys.readouterr().out)["runs"][0]["issues"]
    checks = {issue["check_id"] for issue in issues}
    assert checks == set(load_profile("default", environ={}).checks)


def test_room_layout_payload_is_hidden_with_load_none() -> None:
    path = str(STAGES / "room_layout.usda")

    def has_table(load: str) -> bool:
        stage = open_stage(path, load=load)  # type: ignore[arg-type]
        return stage.GetPrimAtPath(
            "/room_GRP/props_GRP/table01_GRP"
        ).IsLoaded()

    assert has_table("all")
    assert not has_table("none")


def test_example_profile_is_valid(capsys: pytest.CaptureFixture[str]) -> None:
    profile = str(EXAMPLES / "profiles" / "lenient.toml")
    stage = str(STAGES / "chair_broken.usda")

    assert cli.main(["check", stage, "--profile", profile]) == 1
    assert "naming.prim_name" in capsys.readouterr().out
