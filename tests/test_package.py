"""Smoke tests for the package scaffold and the USD runtime."""

from importlib.metadata import version

from pxr import Usd

import usdguard


def test_version_is_single_sourced() -> None:
    assert usdguard.__version__ == version("usdguard")


def test_usd_runtime_creates_in_memory_stage() -> None:
    stage = Usd.Stage.CreateInMemory()

    assert stage.GetPseudoRoot().IsValid()
