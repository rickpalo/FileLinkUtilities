"""Sidebar (N-panel) UI for AssetDoctor."""

from .panels import (
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
)

# Parent first, then its collapsible child panels, then the report/resource panels.
REGISTER_CLASSES = (
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
)
