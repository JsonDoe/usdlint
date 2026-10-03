"""Settings for the Qt UI tests (marked ``ui``, excluded by default).

Run them with ``uv sync --extra ui --group ui`` then
``uv run pytest -m ui --no-cov``. Without Qt or pytest-qt installed, the
UI tests are not collected at all.
"""

import importlib
import os
from pathlib import Path

import pytest

# Render off-screen so the tests run on headless CI machines.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STAGES = Path(__file__).parents[2] / "examples" / "stages"


def _qt_available() -> bool:
    try:
        importlib.import_module("Qt")
        importlib.import_module("pytestqt")
    except ImportError:
        return False
    return True


if not _qt_available():
    collect_ignore_glob = ["test_*.py"]


@pytest.fixture
def stages() -> Path:
    """Directory of the example stages."""
    return STAGES
