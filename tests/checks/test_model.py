"""Tests for model.hierarchy."""

from __future__ import annotations

from typing import TYPE_CHECKING

from usdguard.checks.model import ModelHierarchyCheck
from usdguard.runner import run

if TYPE_CHECKING:
    from collections.abc import Callable

    from pxr import Usd

    StageFactory = Callable[[str], Usd.Stage]


def issues(stage: Usd.Stage) -> list[tuple[str, str]]:
    report = run(stage, [ModelHierarchyCheck()])
    return [(issue.prim_path, issue.message) for issue in report.issues]


def test_contiguous_model_hierarchy_passes(make_stage: StageFactory) -> None:
    stage = make_stage(
        """
        def Xform "set" (kind = "assembly")
        {
            def Xform "room" (kind = "group")
            {
                def Xform "chair" (kind = "component")
                {
                    def Xform "leg" (kind = "subcomponent") {}
                }
            }
        }
        def Xform "prop" (kind = "component") {}
        """
    )

    assert issues(stage) == []


def test_component_under_component_is_reported(
    make_stage: StageFactory,
) -> None:
    stage = make_stage(
        """
        def Xform "chair" (kind = "component")
        {
            def Xform "cushion" (kind = "component") {}
        }
        """
    )

    assert issues(stage) == [
        (
            "/chair/cushion",
            "Prim has kind 'component' but is not a model: its parent "
            "/chair is a component, which cannot contain models",
        )
    ]


def test_gap_in_the_group_chain_is_reported(make_stage: StageFactory) -> None:
    stage = make_stage(
        """
        def Xform "set" (kind = "assembly")
        {
            def Xform "loose"
            {
                def Xform "props" (kind = "group")
                {
                    def Xform "lamp" (kind = "component") {}
                }
            }
        }
        """
    )

    assert issues(stage) == [
        (
            "/set/loose/props",
            "Prim has kind 'group' but is not a model: its parent "
            "/set/loose has no kind instead of a group kind",
        ),
        (
            "/set/loose/props/lamp",
            "Prim has kind 'component' but is not a model: its parent "
            "group /set/loose/props is itself outside the hierarchy",
        ),
    ]


def test_parent_with_a_non_model_kind_is_named(
    make_stage: StageFactory,
) -> None:
    stage = make_stage(
        """
        def Xform "chair" (kind = "component")
        {
            def Xform "parts" (kind = "subcomponent")
            {
                def Xform "screw" (kind = "component") {}
            }
        }
        """
    )

    assert issues(stage) == [
        (
            "/chair/parts/screw",
            "Prim has kind 'component' but is not a model: its parent "
            "/chair/parts has kind 'subcomponent' instead of a group kind",
        )
    ]
