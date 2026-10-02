"""Tests for the command-line interface, called in-process."""

from __future__ import annotations

import io
import json
import runpy
import subprocess
import sys
import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

import pytest

import usdguard
from usdguard import cli
from usdguard.profiles import PROFILE_PATH_ENV

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(PROFILE_PATH_ENV, raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)


@pytest.fixture
def clean(data_dir: Path) -> str:
    """A stage that passes the default profile without any issue."""
    return str(data_dir / "cli" / "clean_asset.usda")


@pytest.fixture
def warnings_only(data_dir: Path) -> str:
    """A stage whose only issues are naming warnings."""
    return str(data_dir / "compliance" / "clean.usda")


@pytest.fixture
def failing(data_dir: Path) -> str:
    """A stage with errors, whose geometry comes from a payload."""
    return str(data_dir / "payload" / "asset.usda")


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out == f"usdguard {usdguard.__version__}\n"


def test_help_succeeds(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--help"]) == 0
    assert "list-checks" in capsys.readouterr().out


def test_a_command_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 2
    assert "required" in capsys.readouterr().err


def test_verbose_and_quiet_are_exclusive(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["-v", "-q", "list-checks"]) == 2
    assert "not allowed" in capsys.readouterr().err


def test_list_checks(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["list-checks"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0].split() == ["CHECK", "TYPE", "SEVERITY", "DESCRIPTION"]
    ids = [line.split()[0] for line in lines[1:]]
    assert ids == sorted(ids)
    assert "geom.extent" in ids
    assert any(
        line.startswith("stage.metadata            stage  error")
        for line in lines
    )


def test_explain(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["explain", "naming.prim_name"]) == 0

    out = capsys.readouterr().out
    assert out.startswith("naming.prim_name\n================\n")
    assert "Type: prim check" in out
    assert "  rules = None" in out
    assert "Example:" in out


def test_explain_a_check_without_options(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["explain", "model.hierarchy"]) == 0
    assert "Options: none" in capsys.readouterr().out


def test_explain_unknown_check(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["explain", "naming.prim"]) == 2
    assert capsys.readouterr().err == (
        "usdguard: error: unknown check 'naming.prim'; did you mean "
        "'naming.prim_name'?\n"
    )


def test_clean_stage_passes(
    clean: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["check", clean]) == 0

    out = capsys.readouterr().out
    assert "  no issues\n" in out
    assert out.endswith("PASSED (fail on error)\n")


def test_errors_fail_the_run(
    failing: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["check", failing]) == 1
    assert "FAILED (fail on error)" in capsys.readouterr().out


def test_fail_on_controls_the_exit_code(warnings_only: str) -> None:
    assert cli.main(["check", warnings_only]) == 0
    assert cli.main(["check", warnings_only, "--fail-on", "warning"]) == 1


def test_unopenable_stages_exit_2_and_others_still_run(
    tmp_path: Path, clean: str, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = str(tmp_path / "missing.usda")

    assert cli.main(["check", missing, clean]) == 2

    captured = capsys.readouterr()
    assert "usdguard.open" in captured.out
    assert "  no issues\n" in captured.out
    assert "usdguard: error: Cannot open stage" in captured.err


def test_globs_are_expanded_in_python(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(data_dir)

    cli.main(["check", "--format", "json", "compliance/*.usda", "**/clean*"])

    runs = json.loads(capsys.readouterr().out)["runs"]
    assert [run["stage"] for run in runs] == [
        "compliance/clean.usda",
        "compliance/nested_gprims.usda",
        "cli/clean_asset.usda",
    ]


def test_globs_without_match_exit_2(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["check", "no/such/*.usda"]) == 2

    captured = capsys.readouterr()
    assert "No file matches 'no/such/*.usda'" in captured.err
    assert "no/such/*.usda\n  error  usdguard.open" in captured.out


def test_json_output_is_deterministic(
    failing: str, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["check", failing, "--format", "json"])
    first = capsys.readouterr().out
    cli.main(["check", failing, "--format", "json"])

    assert capsys.readouterr().out == first
    assert json.loads(first)["profile"] == "default"


def test_junit_report_written_to_a_file(
    tmp_path: Path, failing: str, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "report.xml"

    code = cli.main(["check", failing, "--format", "junit", "-o", str(output)])

    assert code == 1
    assert capsys.readouterr().out == ""
    data = output.read_bytes()
    assert b"\r\n" not in data
    suite = ET.fromstring(data).find("testsuite")
    assert suite is not None
    assert suite.get("tests") == "10"


def test_load_none_hides_payload_geometry(
    failing: str, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(["check", failing, "--format", "json", "--load", "none"])

    issues = json.loads(capsys.readouterr().out)["runs"][0]["issues"]
    assert not [i for i in issues if i["check_id"].startswith("geom.")]


def test_profile_file(
    tmp_path: Path, failing: str, capsys: pytest.CaptureFixture[str]
) -> None:
    profile = tmp_path / "metadata_only.toml"
    profile.write_text('checks = ["stage.metadata"]\n', encoding="utf-8")

    cli.main(["check", failing, "--profile", str(profile), "--format", "json"])

    document = json.loads(capsys.readouterr().out)
    assert document["profile"] == "metadata_only"
    issues = document["runs"][0]["issues"]
    assert {issue["check_id"] for issue in issues} == {"stage.metadata"}


def test_profile_found_in_profile_path(
    tmp_path: Path,
    failing: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "lenient.toml").write_text(
        'checks = ["geom.extent", "geom.primvar_size", "stage.metadata"]\n'
        "[severity]\n"
        '"geom.extent" = "info"\n'
        '"geom.primvar_size" = "info"\n'
        '"stage.metadata" = "info"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv(PROFILE_PATH_ENV, str(tmp_path))

    code = cli.main(["check", failing, "--profile", "lenient"])

    assert code == 0
    assert "PASSED" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("profile_text", "message"),
    [
        ('checks = ["stage.metadat"]', "did you mean 'stage.metadata'?"),
        (
            '[options."stage.metadata"]\nupaxis = "Y"\n',
            "Valid options: up_axis",
        ),
        ('fail_on = "fatal"', "invalid severity 'fatal'"),
        ('[options."naming.prim_name"]\nrules = {Mesh = "("}', "regular"),
    ],
)
def test_invalid_profiles_exit_2(
    tmp_path: Path,
    clean: str,
    capsys: pytest.CaptureFixture[str],
    profile_text: str,
    message: str,
) -> None:
    profile = tmp_path / "bad.toml"
    profile.write_text(profile_text, encoding="utf-8")

    assert cli.main(["check", clean, "--profile", str(profile)]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert message in captured.err


def test_unknown_profile_exits_2(
    clean: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["check", clean, "--profile", "nope"]) == 2
    assert "profile 'nope' not found" in capsys.readouterr().err


def test_verbose_logs_progress_and_usd_diagnostics(
    data_dir: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    stage = str(data_dir / "deps" / "missing.usda")

    cli.main(["-v", "check", stage])

    err = capfd.readouterr().err
    assert "usdguard: info: Checking " in err
    assert "usdguard: info: USD: " in err
    assert "Warning: in" not in err


def test_double_verbose_enables_debug_logging(
    clean: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["-vv", "check", clean]) == 0
    assert "usdguard: info: Checking " in capsys.readouterr().err


def test_usd_diagnostics_are_hidden_by_default(
    data_dir: Path, capfd: pytest.CaptureFixture[str]
) -> None:
    cli.main(["check", str(data_dir / "deps" / "missing.usda")])

    assert capfd.readouterr().err == ""


def test_quiet_still_reports_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["-q", "check", str(tmp_path / "missing.usda")]) == 2
    assert "usdguard: error:" in capsys.readouterr().err


def test_color_only_for_terminals_without_no_color(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    assert not cli._stdout_supports_color()

    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    assert cli._stdout_supports_color()

    monkeypatch.setenv("NO_COLOR", "1")
    assert not cli._stdout_supports_color()


def test_text_is_colored_on_terminals(
    clean: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "_stdout_supports_color", lambda: True)

    cli.main(["check", clean])

    assert "\033[32mPASSED\033[0m" in capsys.readouterr().out


def test_unencodable_characters_are_replaced() -> None:
    stream = io.TextIOWrapper(io.BytesIO(), encoding="ascii", newline="")

    cli._write(stream, "prim /café\n")

    stream.flush()
    assert stream.buffer.getvalue() == b"prim /caf?\n"  # type: ignore[attr-defined]


def test_module_entry_point(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["usdguard", "--version"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("usdguard", run_name="__main__", alter_sys=True)

    assert excinfo.value.code == 0


def test_subprocess_smoke() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "usdguard", "list-checks"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "compliance.usdchecker" in completed.stdout
