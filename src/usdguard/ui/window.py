"""Main window: pick a stage and a profile, validate, browse the issues."""

from __future__ import annotations

import time
from pathlib import Path

from Qt import QtCore, QtGui, QtWidgets

from usdguard.core import Issue, Report, Severity
from usdguard.profiles import DEFAULT_PROFILE, builtin_profiles
from usdguard.ui.model import (
    ISSUE_ROLE,
    MESSAGE_COLUMN,
    ReportFilterProxyModel,
    ReportTableModel,
)
from usdguard.ui.worker import ValidationRequest, ValidationWorker

USD_SUFFIXES = (".usd", ".usda", ".usdc", ".usdz")
_USD_FILTER = "USD files (*.usd *.usda *.usdc *.usdz);;All files (*)"
_LOAD_CHOICES = (
    ("Payloads: from profile", None),
    ("Payloads: load all", "all"),
    ("Payloads: load none", "none"),
)
_SEVERITY_CHOICES = (
    ("All severities", Severity.INFO),
    ("Warnings and errors", Severity.WARNING),
    ("Errors only", Severity.ERROR),
)
_ALL_CHECKS = "All checks"


class MainWindow(QtWidgets.QMainWindow):
    """The usdguard validation window.

    Attributes:
        validation_done: Emitted once a validation started by
            :meth:`validate` has finished, successfully or not.
    """

    validation_done = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("usdguard")
        self.resize(1180, 680)
        self.setAcceptDrops(True)
        self._report: Report | None = None
        self._thread: QtCore.QThread | None = None
        self._worker: ValidationWorker | None = None
        self._started = 0.0
        self.model = ReportTableModel(self)
        self.proxy = ReportFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self._build_widgets()
        self._show_status("Choose a stage file, or drop one on the window.")

    # Public API -----------------------------------------------------

    @property
    def report(self) -> Report | None:
        """Report of the last successful validation."""
        return self._report

    def is_running(self) -> bool:
        """Return whether a validation is in progress."""
        return self._thread is not None

    def set_stage_path(self, path: str) -> None:
        """Set the stage to validate."""
        self.path_edit.setText(path)

    def set_profile(self, profile: str) -> None:
        """Set the profile name or file used for the next validation."""
        self.profile_combo.setEditText(profile)

    def validate(self) -> bool:
        """Start validating the chosen stage in a worker thread.

        Returns:
            Whether a validation was started: ``False`` when no stage is
            chosen or a validation is already running.
        """
        path = self.path_edit.text().strip()
        if not path:
            self._show_status("Choose a stage file first.", error=True)
            return False
        if self.is_running():
            return False
        request = ValidationRequest(
            path=path,
            profile=self.profile_combo.currentText().strip()
            or DEFAULT_PROFILE,
            load=self.load_combo.currentData(),
        )
        thread = QtCore.QThread(self)
        worker = ValidationWorker(request)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._thread, self._worker = thread, worker
        self._started = time.perf_counter()
        self._set_busy(True)
        self._show_status(f"Validating {path}...")
        thread.start()
        return True

    # Qt events ------------------------------------------------------

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        """Let a running validation finish before closing."""
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
        super().closeEvent(event)

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        """Accept drops of a single USD file."""
        if _dropped_stage(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        """Validate the dropped USD file."""
        path = _dropped_stage(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.set_stage_path(path)
            self.validate()

    # Construction ---------------------------------------------------

    def _build_widgets(self) -> None:
        self.path_edit = QtWidgets.QLineEdit()
        self.path_edit.setPlaceholderText(
            "Stage file (.usd, .usda, .usdc, .usdz)"
        )
        self.path_edit.returnPressed.connect(self.validate)
        browse = QtWidgets.QPushButton("Browse...")
        browse.clicked.connect(self._browse_stage)

        self.profile_combo = QtWidgets.QComboBox()
        self.profile_combo.setEditable(True)
        self.profile_combo.addItems(builtin_profiles())
        self.profile_combo.setEditText(DEFAULT_PROFILE)
        self.profile_combo.setToolTip(
            "Built-in profile, profile name found in USDGUARD_PROFILE_PATH, "
            "or path to a TOML profile"
        )
        self.profile_combo.setMinimumContentsLength(24)
        profile_browse = QtWidgets.QPushButton("...")
        profile_browse.setMaximumWidth(36)
        profile_browse.setToolTip("Choose a TOML profile file")
        profile_browse.clicked.connect(self._browse_profile)

        self.load_combo = QtWidgets.QComboBox()
        for label, value in _LOAD_CHOICES:
            self.load_combo.addItem(label, value)

        self.validate_button = QtWidgets.QPushButton("Validate")
        self.validate_button.setDefault(True)
        self.validate_button.clicked.connect(self.validate)

        self.severity_combo = QtWidgets.QComboBox()
        for label, severity in _SEVERITY_CHOICES:
            self.severity_combo.addItem(label, int(severity))
        self.severity_combo.currentIndexChanged.connect(self._apply_filters)
        self.check_combo = QtWidgets.QComboBox()
        self.check_combo.addItem(_ALL_CHECKS, "")
        self.check_combo.currentIndexChanged.connect(self._apply_filters)
        self.count_label = QtWidgets.QLabel()

        self.table = QtWidgets.QTableView()
        self.table.setModel(self.proxy)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(-1, QtCore.Qt.SortOrder.AscendingOrder)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        for column in range(MESSAGE_COLUMN):
            header.setSectionResizeMode(
                column, QtWidgets.QHeaderView.ResizeMode.ResizeToContents
            )
        self.table.setContextMenuPolicy(
            QtCore.Qt.ContextMenuPolicy.ActionsContextMenu
        )
        copy_prim = QtGui.QAction("Copy prim path", self.table)
        copy_prim.triggered.connect(lambda: self._copy("prim"))
        copy_message = QtGui.QAction("Copy message", self.table)
        copy_message.triggered.connect(lambda: self._copy("message"))
        self.table.addActions([copy_prim, copy_message])
        self.table.selectionModel().currentRowChanged.connect(
            self._show_details
        )

        self.details = QtWidgets.QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setPlaceholderText("Select an issue to see its details.")

        stage_row = QtWidgets.QHBoxLayout()
        stage_row.addWidget(QtWidgets.QLabel("Stage:"))
        stage_row.addWidget(self.path_edit, stretch=1)
        stage_row.addWidget(browse)

        options_row = QtWidgets.QHBoxLayout()
        options_row.addWidget(QtWidgets.QLabel("Profile:"))
        options_row.addWidget(self.profile_combo)
        options_row.addWidget(profile_browse)
        options_row.addSpacing(12)
        options_row.addWidget(self.load_combo)
        options_row.addStretch(1)
        options_row.addWidget(self.validate_button)

        filter_row = QtWidgets.QHBoxLayout()
        filter_row.addWidget(QtWidgets.QLabel("Show:"))
        filter_row.addWidget(self.severity_combo)
        filter_row.addWidget(self.check_combo)
        filter_row.addStretch(1)
        filter_row.addWidget(self.count_label)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self.table)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(stage_row)
        layout.addLayout(options_row)
        layout.addLayout(filter_row)
        layout.addWidget(splitter, stretch=1)
        central = QtWidgets.QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

        browse_action = QtGui.QAction("Open stage", self)
        browse_action.setShortcut(QtGui.QKeySequence.StandardKey.Open)
        browse_action.triggered.connect(self._browse_stage)
        validate_action = QtGui.QAction("Validate", self)
        validate_action.setShortcut(QtGui.QKeySequence.StandardKey.Refresh)
        validate_action.triggered.connect(self.validate)
        self.addActions([browse_action, validate_action])
        self._update_count()

    # Slots ----------------------------------------------------------

    @QtCore.Slot(object)
    def _on_finished(self, report: object) -> None:
        if not isinstance(report, Report):  # the worker only emits reports
            return
        self._report = report
        self.model.set_report(report)
        self._fill_check_combo()
        self._apply_filters()
        self.details.clear()
        self._finish()
        elapsed = time.perf_counter() - self._started
        self._show_status(
            _summary(report, elapsed), error=bool(report.exit_code)
        )
        self.validation_done.emit()

    @QtCore.Slot(str)
    def _on_failed(self, message: str) -> None:
        self._report = None
        self.model.set_report(None)
        self._fill_check_combo()
        self._update_count()
        self.details.setPlainText(message)
        self._finish()
        self._show_status(message, error=True)
        self.validation_done.emit()

    def _finish(self) -> None:
        self._thread = None
        self._worker = None
        self._set_busy(False)

    def _apply_filters(self) -> None:
        self.proxy.set_minimum_severity(
            Severity(int(self.severity_combo.currentData()))
        )
        self.proxy.set_check_id(str(self.check_combo.currentData() or ""))
        self._update_count()

    def _show_details(self, current: QtCore.QModelIndex) -> None:
        issue = self._issue_at(current)
        self.details.setPlainText("" if issue is None else _describe(issue))

    def _browse_stage(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open a USD stage", self._start_directory(), _USD_FILTER
        )
        if path:
            self.set_stage_path(path)
            self.validate()

    def _browse_profile(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Open a profile", "", "TOML profiles (*.toml)"
        )
        if path:
            self.set_profile(path)

    def _copy(self, what: str) -> None:
        issue = self._issue_at(self.table.currentIndex())
        if issue is not None:
            text = issue.prim_path if what == "prim" else issue.message
            QtWidgets.QApplication.clipboard().setText(text)

    # Helpers --------------------------------------------------------

    def _issue_at(self, index: QtCore.QModelIndex) -> Issue | None:
        if not index.isValid():
            return None
        issue = self.proxy.index(index.row(), MESSAGE_COLUMN).data(ISSUE_ROLE)
        return issue if isinstance(issue, Issue) else None

    def _fill_check_combo(self) -> None:
        current = self.check_combo.currentData()
        self.check_combo.blockSignals(True)
        self.check_combo.clear()
        self.check_combo.addItem(_ALL_CHECKS, "")
        for check_id in self.model.check_ids():
            self.check_combo.addItem(check_id, check_id)
        position = self.check_combo.findData(current)
        self.check_combo.setCurrentIndex(max(position, 0))
        self.check_combo.blockSignals(False)

    def _update_count(self) -> None:
        shown = self.proxy.rowCount()
        total = self.model.rowCount()
        self.count_label.setText(
            f"{shown} of {total} issues shown" if total else "No issues"
        )

    def _set_busy(self, busy: bool) -> None:
        self.validate_button.setEnabled(not busy)
        self.validate_button.setText("Validating..." if busy else "Validate")

    def _show_status(self, message: str, *, error: bool = False) -> None:
        bar = self.statusBar()
        bar.setStyleSheet("color: #d64541;" if error else "")
        bar.showMessage(message)

    def _start_directory(self) -> str:
        current = self.path_edit.text().strip()
        return str(Path(current).parent) if current else ""


def _dropped_stage(mime: QtCore.QMimeData | None) -> str:
    """Return the path of a single dropped USD file, or an empty string."""
    if mime is None or not mime.hasUrls():
        return ""
    urls = mime.urls()
    if len(urls) != 1 or not urls[0].isLocalFile():
        return ""
    path = urls[0].toLocalFile()
    return path if path.lower().endswith(USD_SUFFIXES) else ""


def _summary(report: Report, seconds: float) -> str:
    counts = ", ".join(
        _plural(count, severity) for severity, count in report.counts().items()
    )
    verdict = "FAILED" if report.exit_code else "PASSED"
    return (
        f"{counts}. {verdict} (fail on {report.fail_on.label}) "
        f"in {seconds:.2f} s"
    )


def _plural(count: int, severity: Severity) -> str:
    if count == 1 or severity is Severity.INFO:
        return f"{count} {severity.label}"
    return f"{count} {severity.label}s"


def _describe(issue: Issue) -> str:
    lines = [
        f"{issue.severity.label.upper()}  {issue.check_id}",
        f"Prim:  {issue.prim_path or '(stage)'}",
    ]
    if issue.layer:
        lines.append(f"Layer: {issue.layer}")
    lines.extend(["", issue.message])
    return "\n".join(lines)
