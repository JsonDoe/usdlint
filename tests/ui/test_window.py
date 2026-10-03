"""Tests for the main window and the usdguard-ui entry point."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from Qt import QtCore, QtWidgets

from usdguard.ui import app as app_module
from usdguard.ui.window import MainWindow, _dropped_stage

if TYPE_CHECKING:
    from pytestqt.qtbot import QtBot

pytestmark = pytest.mark.ui

TIMEOUT = 60_000


@pytest.fixture
def window(qtbot: QtBot) -> MainWindow:
    main_window = MainWindow()
    qtbot.addWidget(main_window)
    return main_window


def validate(qtbot: QtBot, window: MainWindow, path: Path | str) -> None:
    window.set_stage_path(str(path))
    with qtbot.waitSignal(window.validation_done, timeout=TIMEOUT):
        assert window.validate()


def status(window: MainWindow) -> str:
    return window.statusBar().currentMessage()


def test_initial_state(window: MainWindow) -> None:
    assert window.proxy.rowCount() == 0
    assert window.count_label.text() == "No issues"
    assert window.profile_combo.currentText() == "default"
    assert status(window).startswith("Choose a stage file")
    assert window.report is None


def test_validate_needs_a_stage(window: MainWindow) -> None:
    assert not window.validate()
    assert status(window) == "Choose a stage file first."


def test_broken_stage_lists_every_issue(
    qtbot: QtBot, window: MainWindow, stages: Path
) -> None:
    validate(qtbot, window, stages / "chair_broken.usda")

    report = window.report
    assert report is not None
    assert window.proxy.rowCount() == len(report.issues) == 17
    assert window.count_label.text() == "17 of 17 issues shown"
    assert status(window).startswith(
        "14 errors, 3 warnings, 0 info. FAILED (fail on error) in "
    )
    combo = [
        window.check_combo.itemText(i)
        for i in range(window.check_combo.count())
    ]
    assert combo[0] == "All checks"
    assert len(combo) == 11
    assert window.validate_button.isEnabled()
    assert not window.is_running()


def test_clean_stage_passes(
    qtbot: QtBot, window: MainWindow, stages: Path
) -> None:
    validate(qtbot, window, stages / "chair.usda")

    assert window.count_label.text() == "No issues"
    assert "PASSED" in status(window)


def test_filters_narrow_the_table(
    qtbot: QtBot, window: MainWindow, stages: Path
) -> None:
    validate(qtbot, window, stages / "chair_broken.usda")

    window.severity_combo.setCurrentIndex(2)  # errors only
    assert window.proxy.rowCount() == 14

    window.check_combo.setCurrentIndex(
        window.check_combo.findData("geom.extent")
    )
    assert window.proxy.rowCount() == 2
    assert window.count_label.text() == "2 of 17 issues shown"

    validate(qtbot, window, stages / "chair_broken.usda")
    assert window.check_combo.currentData() == "geom.extent"


def test_selection_shows_details_and_can_be_copied(
    qtbot: QtBot, window: MainWindow, stages: Path
) -> None:
    validate(qtbot, window, stages / "chair_broken.usda")
    window.check_combo.setCurrentIndex(
        window.check_combo.findData("model.hierarchy")
    )

    window.table.selectRow(0)

    details = window.details.toPlainText()
    assert details.startswith("ERROR  model.hierarchy\n")
    assert "Prim:  /chair_GRP/cushion_GRP" in details
    copy_prim, copy_message = window.table.actions()
    copy_prim.trigger()
    clipboard = QtWidgets.QApplication.clipboard()
    assert clipboard.text() == "/chair_GRP/cushion_GRP"
    copy_message.trigger()
    assert clipboard.text().startswith("Prim has kind 'component'")


def test_failures_are_reported_in_the_window(
    qtbot: QtBot, window: MainWindow, stages: Path
) -> None:
    window.set_profile("nope")

    validate(qtbot, window, stages / "chair.usda")

    assert "profile 'nope' not found" in status(window)
    assert "profile 'nope' not found" in window.details.toPlainText()
    assert window.report is None


def test_unopenable_stages_show_the_open_error(
    qtbot: QtBot, window: MainWindow, tmp_path: Path
) -> None:
    validate(qtbot, window, tmp_path / "missing.usda")

    assert window.proxy.rowCount() == 1
    assert window.proxy.index(0, 1).data() == "usdguard.open"


def test_payload_choice_is_applied(
    qtbot: QtBot, window: MainWindow, data_dir: Path
) -> None:
    path = data_dir / "payload" / "asset.usda"
    validate(qtbot, window, path)
    loaded = window.proxy.rowCount()

    window.load_combo.setCurrentIndex(window.load_combo.findData("none"))
    validate(qtbot, window, path)

    assert window.proxy.rowCount() < loaded


def test_only_one_validation_runs_at_a_time(
    qtbot: QtBot, window: MainWindow, stages: Path
) -> None:
    window.set_stage_path(str(stages / "room_layout.usda"))
    with qtbot.waitSignal(window.validation_done, timeout=TIMEOUT):
        assert window.validate()
        assert window.is_running()
        assert not window.validate_button.isEnabled()
        assert not window.validate()


def test_closing_waits_for_a_running_validation(
    qtbot: QtBot, window: MainWindow, stages: Path
) -> None:
    window.set_stage_path(str(stages / "room_layout.usda"))
    window.validate()

    window.close()

    qtbot.waitUntil(lambda: not window.is_running(), timeout=TIMEOUT)


def mime_with(*paths: str) -> QtCore.QMimeData:
    mime = QtCore.QMimeData()
    mime.setUrls([QtCore.QUrl.fromLocalFile(path) for path in paths])
    return mime


def test_only_single_usd_files_can_be_dropped(tmp_path: Path) -> None:
    stage = str(tmp_path / "a.usda")

    assert Path(_dropped_stage(mime_with(stage))) == Path(stage)
    assert _dropped_stage(mime_with(str(tmp_path / "a.txt"))) == ""
    assert _dropped_stage(mime_with(stage, stage)) == ""
    assert _dropped_stage(QtCore.QMimeData()) == ""
    assert _dropped_stage(None) == ""


def test_dropping_a_stage_validates_it(
    qtbot: QtBot, window: MainWindow, stages: Path
) -> None:
    path = str(stages / "chair.usda")
    accepted: list[bool] = []
    event = SimpleNamespace(
        mimeData=lambda: mime_with(path),
        acceptProposedAction=lambda: accepted.append(True),
    )

    window.dragEnterEvent(event)  # type: ignore[arg-type]
    with qtbot.waitSignal(window.validation_done, timeout=TIMEOUT):
        window.dropEvent(event)  # type: ignore[arg-type]

    assert accepted == [True, True]
    assert Path(window.path_edit.text()) == Path(path)


def test_create_window_validates_the_given_stage(
    qtbot: QtBot, stages: Path
) -> None:
    window = app_module.create_window(
        stage=str(stages / "chair_broken.usda"), profile="default"
    )
    qtbot.addWidget(window)

    with qtbot.waitSignal(window.validation_done, timeout=TIMEOUT):
        pass

    assert window.report is not None


def test_ui_entry_point_runs_the_application(
    qapp: QtWidgets.QApplication, monkeypatch: pytest.MonkeyPatch
) -> None:
    # PySide2 only has exec_(); app.main() uses whichever exists.
    name = "exec" if hasattr(qapp, "exec") else "exec_"
    monkeypatch.setattr(qapp, name, lambda: 0)

    assert app_module.main(["--profile", "default"]) == 0


def test_ui_entry_point_explains_a_missing_qt(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setitem(sys.modules, "Qt", None)

    assert app_module.main([]) == 2
    assert 'pip install "usdguard[ui]"' in caplog.text


def test_ui_entry_point_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert app_module.main(["--help"]) == 0
    assert "usdguard-ui" in capsys.readouterr().out
