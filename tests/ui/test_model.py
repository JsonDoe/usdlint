"""Tests for the report table model and its filter proxy."""

from __future__ import annotations

import pytest
from Qt import QtCore, QtGui

from usdguard.core import Issue, Report, Severity
from usdguard.ui.model import (
    COLUMNS,
    ISSUE_ROLE,
    SORT_ROLE,
    ReportFilterProxyModel,
    ReportTableModel,
)

pytestmark = pytest.mark.ui

DISPLAY = QtCore.Qt.ItemDataRole.DisplayRole
HORIZONTAL = QtCore.Qt.Orientation.Horizontal

ISSUES = (
    Issue("stage.metadata", Severity.ERROR, "upAxis is not authored"),
    Issue("geom.extent", Severity.ERROR, "stale extent", "/chair/back"),
    Issue(
        "geom.extent",
        Severity.WARNING,
        "Mesh has no authored extent",
        "/chair/seat",
        "chair.usda",
    ),
    Issue("naming.prim_name", Severity.INFO, "bad name", "/chair/Leg1"),
)


@pytest.fixture
def model(qapp: object) -> ReportTableModel:
    table = ReportTableModel()
    table.set_report(Report(issues=ISSUES))
    return table


@pytest.fixture
def proxy(model: ReportTableModel) -> ReportFilterProxyModel:
    filtered = ReportFilterProxyModel()
    filtered.setSourceModel(model)
    return filtered


def cell(model: QtCore.QAbstractItemModel, row: int, column: int) -> object:
    return model.index(row, column).data(DISPLAY)


def test_one_row_per_issue_and_the_documented_columns(
    model: ReportTableModel,
) -> None:
    assert (model.rowCount(), model.columnCount()) == (4, len(COLUMNS))
    assert [model.headerData(i, HORIZONTAL) for i in range(5)] == list(COLUMNS)
    assert model.headerData(0, QtCore.Qt.Orientation.Vertical) is None
    assert model.rowCount(model.index(0, 0)) == 0
    assert model.columnCount(model.index(0, 0)) == 0


def test_cells_show_the_issue_fields(model: ReportTableModel) -> None:
    assert [cell(model, 2, column) for column in range(5)] == [
        "warning",
        "geom.extent",
        "/chair/seat",
        "chair.usda",
        "Mesh has no authored extent",
    ]
    assert cell(model, 0, 2) == "-"
    assert model.index(0, 0).data(QtCore.Qt.ItemDataRole.EditRole) is None
    assert model.data(QtCore.QModelIndex()) is None


def test_message_tooltip_names_the_layer(model: ReportTableModel) -> None:
    tooltip = model.index(2, 4).data(QtCore.Qt.ItemDataRole.ToolTipRole)

    assert tooltip == "Mesh has no authored extent\nLayer: chair.usda"


def test_severity_cells_are_colored_with_an_icon(
    model: ReportTableModel,
) -> None:
    color = model.index(0, 0).data(QtCore.Qt.ItemDataRole.ForegroundRole)
    icon = model.index(0, 0).data(QtCore.Qt.ItemDataRole.DecorationRole)

    assert isinstance(color, QtGui.QColor)
    assert color.name() == "#d64541"
    assert isinstance(icon, QtGui.QIcon)
    assert not icon.isNull()
    assert (
        model.index(0, 1).data(QtCore.Qt.ItemDataRole.DecorationRole) is None
    )


def test_custom_roles(model: ReportTableModel) -> None:
    assert model.index(3, 0).data(SORT_ROLE) == int(Severity.INFO)
    assert model.index(3, 1).data(SORT_ROLE) == "naming.prim_name"
    assert model.index(1, 4).data(ISSUE_ROLE) is ISSUES[1]


def test_reports_can_be_replaced_and_cleared(model: ReportTableModel) -> None:
    assert model.check_ids() == [
        "geom.extent",
        "naming.prim_name",
        "stage.metadata",
    ]

    model.set_report(None)

    assert model.rowCount() == 0
    assert model.check_ids() == []


def test_proxy_filters_by_severity_and_check(
    proxy: ReportFilterProxyModel,
) -> None:
    assert proxy.rowCount() == 4

    proxy.set_minimum_severity(Severity.WARNING)
    assert proxy.rowCount() == 3
    assert proxy.minimum_severity is Severity.WARNING

    proxy.set_check_id("geom.extent")
    assert proxy.rowCount() == 2
    assert proxy.check_id == "geom.extent"

    proxy.set_minimum_severity(Severity.ERROR)
    assert [cell(proxy, 0, 4)] == ["stale extent"]

    proxy.set_check_id("")
    proxy.set_minimum_severity(Severity.INFO)
    assert proxy.rowCount() == 4


def test_proxy_sorts_severities_by_seriousness(
    proxy: ReportFilterProxyModel,
) -> None:
    proxy.sort(0, QtCore.Qt.SortOrder.AscendingOrder)
    assert [cell(proxy, row, 0) for row in range(4)] == [
        "info",
        "warning",
        "error",
        "error",
    ]

    proxy.sort(0, QtCore.Qt.SortOrder.DescendingOrder)
    assert cell(proxy, 0, 0) == "error"


def test_proxy_accepts_rows_of_other_models(qapp: object) -> None:
    proxy = ReportFilterProxyModel()
    source = QtGui.QStandardItemModel(2, 1)
    proxy.setSourceModel(source)

    assert proxy.rowCount() == 2
