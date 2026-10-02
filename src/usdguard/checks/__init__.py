"""Built-in checks.

Each module groups checks by family; the ``check_id`` prefix names the
family. Built-in checks are registered through the same
``usdguard.checks`` entry points as third-party plugins, so they can be
listed, configured and overridden in exactly the same way.

==========================  =====  =====================================
check_id                    Kind   Summary
==========================  =====  =====================================
naming.prim_name            prim   Prim names match a regex per type.
stage.metadata              stage  upAxis, metersPerUnit, defaultPrim.
deps.absolute_arc_path      stage  Composition arcs use relative paths.
deps.absolute_asset_attr    prim   Asset attributes use relative paths.
deps.unresolved             stage  Every dependency resolves.
shading.material_binding    stage  Renderable gprims have a material.
model.hierarchy             prim   Model kinds form a valid hierarchy.
geom.primvar_size           prim   Mesh primvar sizes match topology.
geom.extent                 prim   Boundables author a correct extent.
compliance.usdchecker       stage  OpenUSD's validators pass.
==========================  =====  =====================================
"""
