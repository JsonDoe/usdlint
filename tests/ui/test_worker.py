"""Tests for background validation."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import pytest
from Qt import QtCore

from usdguard.core import Issue, Report, Severity
from usdguard.errors import ConfigError
from usdguard.ui import worker as worker_module
from usdguard.ui.worker import ValidationRequest, ValidationWorker, validate

if TYPE_CHECKING:
    from pathlib import Path

    from pytestqt.qtbot import QtBot

pytestmark = pytest.mark.ui


def test_validate_returns_the_report(stages: Path) -> None:
    clean = validate(ValidationRequest(str(stages / "chair.usda")))
    broken = validate(ValidationRequest(str(stages / "chair_broken.usda")))

    assert clean.issues == ()
    assert broken.exit_code == 1


def test_validate_applies_request_overrides(data_dir: Path) -> None:
    path = str(data_dir / "payload" / "asset.usda")
    request = ValidationRequest(
        path, load="none", fail_on=Severity.WARNING, profile="default"
    )

    report = validate(request)

    assert not [i for i in report.issues if i.check_id.startswith("geom.")]
    assert report.fail_on is Severity.WARNING


def test_unopenable_stages_give_an_open_failure(tmp_path: Path) -> None:
    report = validate(ValidationRequest(str(tmp_path / "missing.usda")))

    (issue,) = report.issues
    assert issue.check_id == "usdguard.open"


def test_invalid_profiles_raise(stages: Path) -> None:
    with pytest.raises(ConfigError, match="profile 'nope' not found"):
        validate(ValidationRequest(str(stages / "chair.usda"), profile="nope"))


def run_in_thread(
    qtbot: QtBot, worker: ValidationWorker, signal: str
) -> list[object]:
    thread = QtCore.QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    try:
        with qtbot.waitSignal(getattr(worker, signal), timeout=60_000) as got:
            thread.start()
    finally:
        thread.quit()
        thread.wait()
    return list(got.args or [])


def test_worker_validates_off_the_main_thread_and_emits_plain_data(
    qtbot: QtBot, stages: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    threads: list[int] = []
    original = worker_module.validate

    def recording_validate(request: ValidationRequest) -> Report:
        threads.append(threading.get_ident())
        return original(request)

    monkeypatch.setattr(worker_module, "validate", recording_validate)
    worker = ValidationWorker(
        ValidationRequest(str(stages / "chair_broken.usda"))
    )

    (report,) = run_in_thread(qtbot, worker, "finished")

    assert threads
    assert threads[0] != threading.get_ident()
    assert isinstance(report, Report)
    assert report.issues
    assert all(isinstance(issue, Issue) for issue in report.issues)
    assert all(
        isinstance(value, str)
        for issue in report.issues
        for value in (issue.check_id, issue.message, issue.prim_path)
    )


def test_worker_reports_configuration_errors(
    qtbot: QtBot, stages: Path
) -> None:
    worker = ValidationWorker(
        ValidationRequest(str(stages / "chair.usda"), profile="nope")
    )

    (message,) = run_in_thread(qtbot, worker, "failed")

    assert "profile 'nope' not found" in str(message)


def test_worker_reports_unexpected_crashes(
    qtbot: QtBot,
    stages: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def crash(request: ValidationRequest) -> Report:
        message = "boom"
        raise RuntimeError(message)

    monkeypatch.setattr(worker_module, "validate", crash)
    caplog.set_level(logging.ERROR, logger="usdguard")
    worker = ValidationWorker(ValidationRequest(str(stages / "chair.usda")))

    (message,) = run_in_thread(qtbot, worker, "failed")

    assert message == "Unexpected error: RuntimeError('boom')"
    assert "crashed" in caplog.text
