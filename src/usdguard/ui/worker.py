"""Background validation for the UI.

:func:`validate` is the whole validation of one file, in plain Python.
:class:`ValidationWorker` runs it in a ``QThread`` so the UI stays
responsive. The worker opens its own stage in that thread and only
emits the immutable :class:`~usdguard.core.Report`; no USD object ever
crosses threads.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from Qt import QtCore

from usdguard.errors import StageOpenError, UsdGuardError
from usdguard.profiles import DEFAULT_PROFILE, build_checks, load_profile
from usdguard.registry import CheckRegistry
from usdguard.runner import (
    open_failure_report,
    open_stage,
    run,
    usd_diagnostics_to_logging,
)

if TYPE_CHECKING:
    from usdguard.core import Report, Severity
    from usdguard.runner import LoadPolicy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationRequest:
    """What to validate, as plain data that is safe to pass to a thread.

    Attributes:
        path: Stage file to validate.
        profile: Profile name or file.
        load: Payload policy; ``None`` uses the profile's.
        fail_on: Failing severity; ``None`` uses the profile's.
    """

    path: str
    profile: str = DEFAULT_PROFILE
    load: LoadPolicy | None = None
    fail_on: Severity | None = None


def validate(request: ValidationRequest) -> Report:
    """Validate the stage described by ``request`` and return its report.

    A stage that cannot be opened produces a report with a single
    ``usdguard.open`` issue, as in the CLI.

    Raises:
        UsdGuardError: The profile or a check plugin is invalid.
    """
    profile = load_profile(request.profile)
    checks = build_checks(profile, CheckRegistry())
    fail_on = request.fail_on or profile.fail_on
    with usd_diagnostics_to_logging():
        try:
            stage = open_stage(request.path, load=request.load or profile.load)
        except StageOpenError as error:
            return open_failure_report(error, fail_on=fail_on)
        return run(
            stage,
            checks,
            stage_path=request.path,
            fail_on=fail_on,
            severity_overrides=profile.severity,
        )


class ValidationWorker(QtCore.QObject):
    """Runs :func:`validate` when its thread starts.

    Move the worker to a ``QThread``, connect ``thread.started`` to
    :meth:`run`, and listen to :attr:`finished` or :attr:`failed`.
    Exactly one of them is emitted per run.

    Attributes:
        finished: Emitted with the :class:`~usdguard.core.Report`.
        failed: Emitted with an error message when validation could not
            run, for instance because of an invalid profile.
    """

    finished = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, request: ValidationRequest) -> None:
        super().__init__()
        self.request = request

    @QtCore.Slot()
    def run(self) -> None:
        """Validate the request and emit the outcome."""
        try:
            report = validate(self.request)
        except UsdGuardError as error:
            self.failed.emit(str(error))
            return
        except Exception as error:
            logger.exception("Validation of %s crashed", self.request.path)
            self.failed.emit(f"Unexpected error: {error!r}")
            return
        self.finished.emit(report)
