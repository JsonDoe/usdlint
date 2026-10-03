"""Entry point of the ``usdguard-ui`` command."""

from __future__ import annotations

import argparse
import logging
import sys
from typing import TYPE_CHECKING, cast

from usdguard.profiles import DEFAULT_PROFILE

if TYPE_CHECKING:
    from collections.abc import Sequence

    from usdguard.ui.window import MainWindow

logger = logging.getLogger(__name__)

EXIT_ERROR = 2


def main(argv: Sequence[str] | None = None) -> int:
    """Open the usdguard window and return the application exit code.

    Args:
        argv: Arguments without the program name; defaults to
            ``sys.argv[1:]``.
    """
    parser = argparse.ArgumentParser(
        prog="usdguard-ui", description="Validate USD stages interactively."
    )
    parser.add_argument(
        "stage", nargs="?", help="stage file to validate on startup"
    )
    parser.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        metavar="NAME|FILE",
        help="profile name or TOML file (default: %(default)s)",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # --help and usage errors
        return exc.code if isinstance(exc.code, int) else EXIT_ERROR
    logging.basicConfig(
        level=logging.INFO, format="usdguard-ui: %(levelname)s: %(message)s"
    )
    try:
        from Qt import QtWidgets
    except ImportError as error:
        logger.error(
            "the UI needs Qt (%s); install it with: pip install "
            '"usdguard[ui]"',
            error,
        )
        return EXIT_ERROR
    # The stubs omit it, but instance() returns None before the first
    # QApplication is created.
    existing = cast(
        "QtWidgets.QApplication | None", QtWidgets.QApplication.instance()
    )
    app = (
        existing
        if existing is not None
        else QtWidgets.QApplication(sys.argv[:1])
    )
    window = create_window(stage=args.stage, profile=args.profile)
    window.show()
    run = getattr(app, "exec", None) or app.exec_
    return int(run())


def create_window(
    stage: str | None = None, profile: str = DEFAULT_PROFILE
) -> MainWindow:
    """Create the main window, validating ``stage`` if one is given.

    A ``QApplication`` must exist.
    """
    from usdguard.ui.window import MainWindow

    window = MainWindow()
    window.set_profile(profile)
    if stage:
        window.set_stage_path(stage)
        window.validate()
    return window
