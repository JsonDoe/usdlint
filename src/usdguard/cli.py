"""Command-line interface: ``usdguard check|list-checks|explain``.

Exit codes are meant for CI: 0 when no issue reaches the ``fail_on``
severity, 1 when one does, and 2 for usage, configuration or
stage-open errors. With several stages, the highest code wins.
"""

from __future__ import annotations

import argparse
import contextlib
import glob
import inspect
import logging
import os
import sys
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, TextIO, cast

import usdguard
from usdguard.core import Severity, StageCheck
from usdguard.errors import ConfigError, StageOpenError, UsdGuardError
from usdguard.profiles import (
    DEFAULT_PROFILE,
    build_checks,
    load_profile,
    option_defaults,
)
from usdguard.registry import CheckRegistry
from usdguard.reporters import FORMATS, StageResult, render
from usdguard.runner import (
    LOAD_POLICIES,
    open_failure_report,
    open_stage,
    run,
    usd_diagnostics_to_logging,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from usdguard.core import Check, Report
    from usdguard.profiles import Profile
    from usdguard.runner import LoadPolicy

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_ISSUES = 1
EXIT_ERROR = 2

_GLOB_CHARS = frozenset("*?[")


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return its exit code.

    Args:
        argv: Arguments without the program name; defaults to
            ``sys.argv[1:]``.
    """
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # --help, --version and usage errors
        return exc.code if isinstance(exc.code, int) else EXIT_ERROR
    with _logging_to_stderr(args.verbose, args.quiet):
        try:
            code: int = args.handler(args)
        except UsdGuardError as exc:
            logger.error("%s", exc)
            return EXIT_ERROR
    return code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="usdguard",
        description="Validate USD stages against studio policy.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"usdguard {usdguard.__version__}",
    )
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="log progress (-v) and debug details (-vv) to stderr",
    )
    verbosity.add_argument(
        "-q", "--quiet", action="store_true", help="only log errors"
    )
    commands = parser.add_subparsers(
        title="commands", dest="command", required=True
    )

    check = commands.add_parser(
        "check",
        help="validate stages",
        description="Validate USD stages and report the issues found.",
    )
    check.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="stage file or glob pattern, such as 'assets/**/*.usda'",
    )
    check.add_argument(
        "--profile",
        default=DEFAULT_PROFILE,
        metavar="NAME|FILE",
        help="profile name or TOML file (default: %(default)s)",
    )
    check.add_argument(
        "--format",
        choices=FORMATS,
        default="text",
        help="report format (default: %(default)s)",
    )
    check.add_argument(
        "-o", "--output", metavar="FILE", help="write the report to FILE"
    )
    check.add_argument(
        "--fail-on",
        choices=[severity.label for severity in Severity],
        help="lowest severity that fails the run (default: from profile)",
    )
    check.add_argument(
        "--load",
        choices=LOAD_POLICIES,
        help="payload policy (default: from profile)",
    )
    check.set_defaults(handler=_check)

    list_checks = commands.add_parser(
        "list-checks", help="list the available checks"
    )
    list_checks.set_defaults(handler=_list_checks)

    explain = commands.add_parser(
        "explain", help="describe a check and its options"
    )
    explain.add_argument("check_id", metavar="CHECK_ID")
    explain.set_defaults(handler=_explain)
    return parser


def _check(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    checks = build_checks(profile, CheckRegistry())
    fail_on = (
        Severity.from_label(args.fail_on) if args.fail_on else profile.fail_on
    )
    load = cast("LoadPolicy", args.load or profile.load)
    results: list[StageResult] = []
    exit_code = EXIT_OK
    for label, path in _expand(args.paths):
        report, code = _check_stage(
            path, label, checks, profile, fail_on, load
        )
        results.append(StageResult(stage=label, report=report))
        exit_code = max(exit_code, code)
    color = (
        args.format == "text"
        and args.output is None
        and _stdout_supports_color()
    )
    document = render(args.format, results, profile=profile.name, color=color)
    if args.output:
        with Path(args.output).open("w", encoding="utf-8", newline="\n") as f:
            f.write(document)
    else:
        _write(sys.stdout, document)
    return exit_code


def _check_stage(
    path: str | None,
    label: str,
    checks: list[Check],
    profile: Profile,
    fail_on: Severity,
    load: LoadPolicy,
) -> tuple[Report, int]:
    if path is None:
        error = StageOpenError(f"No file matches {label!r}")
        logger.error("%s", error)
        return open_failure_report(error, fail_on=fail_on), EXIT_ERROR
    logger.info("Checking %s", label)
    with usd_diagnostics_to_logging():
        try:
            stage = open_stage(path, load=load)
        except StageOpenError as error:
            logger.error("%s", error)
            return open_failure_report(error, fail_on=fail_on), EXIT_ERROR
        report = run(
            stage,
            checks,
            stage_path=path,
            fail_on=fail_on,
            severity_overrides=profile.severity,
        )
    return report, report.exit_code


def _expand(patterns: Sequence[str]) -> Iterator[tuple[str, str | None]]:
    """Yield ``(label, path)`` per stage, expanding globs in Python.

    Windows shells do not expand wildcards, so patterns are expanded
    here (``**`` matches nested directories). A pattern that matches no
    file yields its own label with no path. Labels use forward slashes
    so reports read the same on every platform.
    """
    seen: set[str] = set()
    for pattern in patterns:
        if _GLOB_CHARS.isdisjoint(pattern):
            matches = [pattern]
        else:
            # Path.glob rejects absolute patterns; glob.glob does not.
            matches = sorted(glob.glob(pattern, recursive=True))  # noqa: PTH207
            if not matches:
                yield PurePath(pattern).as_posix(), None
                continue
        for match in matches:
            label = PurePath(match).as_posix()
            if label not in seen:
                seen.add(label)
                yield label, match


def _list_checks(args: argparse.Namespace) -> int:
    classes = CheckRegistry().load_all()
    rows = [
        (
            check_id,
            "stage" if issubclass(cls, StageCheck) else "prim",
            cls.severity.label,
            cls.description,
        )
        for check_id, cls in classes.items()
    ]
    header = ("CHECK", "TYPE", "SEVERITY", "DESCRIPTION")
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(3)]
    lines = [
        "  ".join(
            [
                *(c.ljust(w) for c, w in zip(row[:3], widths, strict=True)),
                row[3],
            ]
        )
        for row in [header, *rows]
    ]
    _write(sys.stdout, "\n".join(lines) + "\n")
    return EXIT_OK


def _explain(args: argparse.Namespace) -> int:
    registry = CheckRegistry()
    if args.check_id not in registry:
        raise ConfigError(registry.unknown_check_message(args.check_id))
    cls = registry.get(args.check_id)
    kind = "stage" if issubclass(cls, StageCheck) else "prim"
    lines = [
        cls.check_id,
        "=" * len(cls.check_id),
        cls.description,
        "",
        f"Type: {kind} check",
        f"Default severity: {cls.severity.label}",
    ]
    options = option_defaults(cls)
    if options:
        lines.append("Options (default value):")
        lines.extend(
            f"  {name} = {value!r}" for name, value in options.items()
        )
    else:
        lines.append("Options: none")
    lines.extend(["", inspect.getdoc(cls) or ""])
    _write(sys.stdout, "\n".join(lines).rstrip() + "\n")
    return EXIT_OK


def _stdout_supports_color() -> bool:
    """Color only for terminals, and never when ``NO_COLOR`` is set."""
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ


def _write(stream: TextIO, text: str) -> None:
    """Write ``text``, replacing characters the stream cannot encode."""
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = stream.encoding or "utf-8"
        stream.write(text.encode(encoding, "replace").decode(encoding))


@contextlib.contextmanager
def _logging_to_stderr(verbose: int, quiet: bool) -> Iterator[None]:
    """Attach a stderr handler to the ``usdguard`` logger for one run."""
    if quiet:
        level = logging.ERROR
    elif verbose > 1:
        level = logging.DEBUG
    elif verbose == 1:
        level = logging.INFO
    else:
        level = logging.WARNING
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_Formatter())
    package_logger = logging.getLogger("usdguard")
    previous_level = package_logger.level
    package_logger.addHandler(handler)
    package_logger.setLevel(level)
    try:
        yield
    finally:
        package_logger.removeHandler(handler)
        package_logger.setLevel(previous_level)


class _Formatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        return f"usdguard: {record.levelname.lower()}: {message}"
