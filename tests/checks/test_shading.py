"""Tests for shading.material_binding."""

from __future__ import annotations

from typing import TYPE_CHECKING

from usdguard.checks.shading import MaterialBindingCheck
from usdguard.core import Context
from usdguard.runner import run

if TYPE_CHECKING:
    from collections.abc import Callable

    from pxr import Usd

    StageFactory = Callable[[str], Usd.Stage]

SCENE = """
def Xform "chair" (prepend apiSchemas = ["MaterialBindingAPI"])
{
    rel material:binding = </looks/wood>

    def Mesh "seat" {}
    def Mesh "proxy_box"
    {
        uniform token purpose = "proxy"
    }
    def Mesh "guide_curve"
    {
        uniform token purpose = "guide"
    }
}
def Xform "lamp"
{
    def Mesh "shade" {}
    def Mesh "bulb" (prepend apiSchemas = ["MaterialBindingAPI"])
    {
        rel material:binding = </looks/missing>
    }
    def Mesh "render_only"
    {
        uniform token purpose = "render"
    }
}
def Scope "looks"
{
    def Material "wood" {}
}
"""


def test_unbound_renderable_gprims_are_reported(
    make_stage: StageFactory,
) -> None:
    report = run(make_stage(SCENE), [MaterialBindingCheck()])

    assert [(i.prim_path, i.message) for i in report.issues] == [
        ("/lamp/bulb", "Mesh has no bound material"),
        ("/lamp/render_only", "Mesh has no bound material"),
        ("/lamp/shade", "Mesh has no bound material"),
    ]


def test_resolved_bindings_are_cached(make_stage: StageFactory) -> None:
    context = Context(stage=make_stage(SCENE))

    list(MaterialBindingCheck().check_stage(context))

    assert context.cache["shading.material_binding"] == {
        "/chair/seat": "/looks/wood",
        "/lamp/bulb": "",
        "/lamp/render_only": "",
        "/lamp/shade": "",
    }


def test_stage_without_gprims_passes(make_stage: StageFactory) -> None:
    context = Context(stage=make_stage('def Xform "empty" {}'))

    assert list(MaterialBindingCheck().check_stage(context)) == []
    assert context.cache["shading.material_binding"] == {}


def test_bindings_on_instances_apply_to_instance_proxies(
    make_stage: StageFactory,
) -> None:
    stage = make_stage(
        """
        def Xform "set"
        {
            def Xform "tree_1" (instanceable = true
                prepend apiSchemas = ["MaterialBindingAPI"]
                prepend references = </tree_src>)
            {
                rel material:binding = </looks/bark>
            }
            def Xform "tree_2" (instanceable = true
                prepend references = </tree_src>) {}
        }
        over "tree_src"
        {
            def Mesh "trunk" {}
        }
        def Scope "looks"
        {
            def Material "bark" {}
        }
        """
    )

    report = run(stage, [MaterialBindingCheck()])

    assert [issue.prim_path for issue in report.issues] == [
        "/set/tree_2/trunk"
    ]
