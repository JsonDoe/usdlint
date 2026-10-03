"""Qt models that present a report as a sortable, filterable table."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeAlias

from Qt import QtCore, QtGui, QtWidgets

from usdguard.core import Issue, Report, Severity

if TYPE_CHECKING:
    from collections.abc import Callable

COLUMNS = ("Severity", "Check", "Prim", "Layer", "Message")
"""Column titles, in display order."""

SEVERITY_COLUMN, CHECK_COLUMN, PRIM_COLUMN, LAYER_COLUMN, MESSAGE_COLUMN = (
    range(len(COLUMNS))
)

_USER_ROLE = int(QtCore.Qt.ItemDataRole.UserRole)
SORT_ROLE = _USER_ROLE + 1
"""Role returning the sort key of a cell (numeric for severities)."""
ISSUE_ROLE = _USER_ROLE + 2
"""Role returning the :class:`~usdguard.core.Issue` of a row."""

_DISPLAY = int(QtCore.Qt.ItemDataRole.DisplayRole)
_TOOLTIP = int(QtCore.Qt.ItemDataRole.ToolTipRole)
_FOREGROUND = int(QtCore.Qt.ItemDataRole.ForegroundRole)
_DECORATION = int(QtCore.Qt.ItemDataRole.DecorationRole)
_HORIZONTAL = QtCore.Qt.Orientation.Horizontal

_COLORS = {
    Severity.ERROR: "#d64541",
    Severity.WARNING: "#c78500",
    Severity.INFO: "#3b7dd8",
}
_ICONS = {
    Severity.ERROR: QtWidgets.QStyle.StandardPixmap.SP_MessageBoxCritical,
    Severity.WARNING: QtWidgets.QStyle.StandardPixmap.SP_MessageBoxWarning,
    Severity.INFO: QtWidgets.QStyle.StandardPixmap.SP_MessageBoxInformation,
}

_CELL_TEXT: tuple[Callable[[Issue], str], ...] = (
    lambda issue: issue.severity.label,
    lambda issue: issue.check_id,
    lambda issue: issue.prim_path or "-",
    lambda issue: issue.layer,
    lambda issue: issue.message,
)

ModelIndex: TypeAlias = "QtCore.QModelIndex | QtCore.QPersistentModelIndex"


class ReportTableModel(QtCore.QAbstractTableModel):
    """Read-only table model over the issues of a :class:`Report`.

    One row per issue, in report order, with the columns of
    :data:`COLUMNS`. Severity cells are colored and carry an icon.
    """

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._issues: tuple[Issue, ...] = ()

    def set_report(self, report: Report | None) -> None:
        """Show the issues of ``report``, or nothing for ``None``."""
        self.beginResetModel()
        self._issues = report.issues if report is not None else ()
        self.endResetModel()

    def issue(self, row: int) -> Issue:
        """Return the issue shown on ``row``."""
        return self._issues[row]

    def check_ids(self) -> list[str]:
        """Return the sorted ids of the checks that reported issues."""
        return sorted({issue.check_id for issue in self._issues})

    def rowCount(self, parent: ModelIndex | None = None) -> int:
        """Return the number of issues (zero below the root)."""
        return (
            0 if parent is not None and parent.isValid() else len(self._issues)
        )

    def columnCount(self, parent: ModelIndex | None = None) -> int:
        """Return the number of columns (zero below the root)."""
        return 0 if parent is not None and parent.isValid() else len(COLUMNS)

    def data(self, index: ModelIndex, role: int = _DISPLAY) -> Any:
        """Return the cell content for ``role``."""
        if not index.isValid():
            return None
        issue = self._issues[index.row()]
        column = index.column()
        if role in (_DISPLAY, _TOOLTIP):
            text = _CELL_TEXT[column](issue)
            if role == _TOOLTIP and column == MESSAGE_COLUMN and issue.layer:
                return f"{text}\nLayer: {issue.layer}"
            return text
        if role == SORT_ROLE:
            if column == SEVERITY_COLUMN:
                return int(issue.severity)
            return _CELL_TEXT[column](issue)
        if role == ISSUE_ROLE:
            return issue
        if column == SEVERITY_COLUMN and role == _FOREGROUND:
            return QtGui.QColor(_COLORS[issue.severity])
        if column == SEVERITY_COLUMN and role == _DECORATION:
            style = QtWidgets.QApplication.style()
            return style.standardIcon(_ICONS[issue.severity])
        return None

    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = _DISPLAY,
    ) -> Any:
        """Return the column titles."""
        if orientation == _HORIZONTAL and role == _DISPLAY:
            return COLUMNS[section]
        return None


class ReportFilterProxyModel(QtCore.QSortFilterProxyModel):
    """Filters a :class:`ReportTableModel` by severity and check id.

    Sorting uses :data:`SORT_ROLE`, so severities sort by seriousness
    rather than alphabetically.
    """

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._minimum = Severity.INFO
        self._check_id = ""
        self.setSortRole(SORT_ROLE)

    @property
    def minimum_severity(self) -> Severity:
        """Least severe issue shown."""
        return self._minimum

    @property
    def check_id(self) -> str:
        """Check whose issues are shown; empty shows every check."""
        return self._check_id

    def set_minimum_severity(self, severity: Severity) -> None:
        """Hide issues less severe than ``severity``."""
        self._begin_filter_change()
        self._minimum = severity
        self._end_filter_change()

    def set_check_id(self, check_id: str) -> None:
        """Show only the issues of ``check_id``; empty shows all checks."""
        self._begin_filter_change()
        self._check_id = check_id
        self._end_filter_change()

    def _begin_filter_change(self) -> None:
        # Qt 6.10 replaced invalidateFilter() with this begin/end pair;
        # PySide2 and older PySide6 releases only have invalidateFilter().
        begin = getattr(self, "beginFilterChange", None)
        if begin is not None:
            begin()

    def _end_filter_change(self) -> None:
        end = getattr(self, "endFilterChange", None)
        if end is not None:
            end()
        else:
            self.invalidateFilter()

    def filterAcceptsRow(
        self, source_row: int, source_parent: ModelIndex
    ) -> bool:
        """Accept issues matching the severity and check filters."""
        source = self.sourceModel()
        if not isinstance(source, ReportTableModel):
            return True
        issue = source.issue(source_row)
        return issue.severity >= self._minimum and (
            not self._check_id or issue.check_id == self._check_id
        )
