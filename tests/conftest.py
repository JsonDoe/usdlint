"""Shared fixtures: in-memory stages built from inline USDA text."""

from __future__ import annotations

import textwrap
from collections.abc import Callable
from pathlib import Path

import pytest
from pxr import Sdf, Usd

StageFactory = Callable[[str], Usd.Stage]

DATA_DIR = Path(__file__).parent / "data"


@pytest.fixture
def make_stage() -> StageFactory:
    """Return a function that builds an in-memory stage from USDA text.

    The ``#usda 1.0`` header is optional and indentation is removed, so
    tests can inline small, readable scenes.
    """

    def build(text: str) -> Usd.Stage:
        text = textwrap.dedent(text).strip()
        if not text.startswith("#usda"):
            text = f"#usda 1.0\n{text}"
        layer = Sdf.Layer.CreateAnonymous(".usda")
        if not layer.ImportFromString(text):
            pytest.fail(f"invalid USDA fixture:\n{text}")
        return Usd.Stage.Open(layer)

    return build


@pytest.fixture
def data_dir() -> Path:
    """Directory of the hand-written ``.usda`` fixtures."""
    return DATA_DIR
