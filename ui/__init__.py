"""Sidebar (N-panel) UI for AssetDoctor."""

from .panels import (
    ASSETDOCTOR_PG_tree_row,
    ASSETDOCTOR_PG_broken_lib,
    ASSETDOCTOR_UL_tree,
    ASSETDOCTOR_UL_broken_libs,
    ASSETDOCTOR_UL_broken_imgs,
    ASSETDOCTOR_PT_main,
    ASSETDOCTOR_PT_project,
    ASSETDOCTOR_PT_make_local,
    ASSETDOCTOR_PT_materials,
    ASSETDOCTOR_PT_orphans,
    ASSETDOCTOR_PT_geometry,
    ASSETDOCTOR_PT_resource_tools,
    ASSETDOCTOR_PT_utilities,
    ASSETDOCTOR_PT_report,
    ASSETDOCTOR_PT_resources,
    ASSETDOCTOR_PT_scene_deps,
)

# PropertyGroup + UIList first (panels' template_list draws them, and the WM
# CollectionProperty in register() needs the PropertyGroup to exist), then the
# parent panel, its collapsible children, and the report/resource panels.
REGISTER_CLASSES = (
    ASSETDOCTOR_PG_tree_row,
    ASSETDOCTOR_PG_broken_lib,
    ASSETDOCTOR_UL_tree,
    ASSETDOCTOR_UL_broken_libs,
    ASSETDOCTOR_UL_broken_imgs,
    ASSETDOCTOR_PT_main,
    ASSETDOCTOR_PT_project,
    ASSETDOCTOR_PT_make_local,
    ASSETDOCTOR_PT_materials,
    ASSETDOCTOR_PT_orphans,
    ASSETDOCTOR_PT_geometry,
    ASSETDOCTOR_PT_resource_tools,
    ASSETDOCTOR_PT_utilities,
    ASSETDOCTOR_PT_report,
    ASSETDOCTOR_PT_resources,
    ASSETDOCTOR_PT_scene_deps,
)
