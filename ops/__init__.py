"""bpy operators for AssetDoctor (the only code allowed to import bpy besides ui/prefs).

Each operator is thin: gather bpy data -> hand to assetdoctor.core -> show a
report -> on explicit Apply, mutate (after an auto-backup). The operators below
are scaffold stubs that register cleanly; feature logic arrives per-milestone.
"""

from .scan_folder import ASSETDOCTOR_OT_scan_folder
from .dep_scan import ASSETDOCTOR_OT_scan_dependencies
from .datablock_inspect import ASSETDOCTOR_OT_analyze_overrides
from .relink import ASSETDOCTOR_OT_fix_library_paths
from .progress import ASSETDOCTOR_OT_toggle_pause, ASSETDOCTOR_OT_request_cancel
from .make_local import ASSETDOCTOR_OT_make_local
from .material_dedup import ASSETDOCTOR_OT_material_dedup
from .orphans import ASSETDOCTOR_OT_scan_orphans
from .instance_dedup import ASSETDOCTOR_OT_instance_geometry
from .resource import ASSETDOCTOR_OT_analyze_resources, ASSETDOCTOR_OT_profile_render
from .open_preferences import ASSETDOCTOR_OT_open_preferences
from .report_store import (
    ASSETDOCTOR_OT_export_report,
    ASSETDOCTOR_OT_report_clear,
    ASSETDOCTOR_OT_report_select,
    ASSETDOCTOR_OT_report_toggle,
    ASSETDOCTOR_OT_row_label,
    ASSETDOCTOR_OT_select_datablock,
)

REGISTER_CLASSES = (
    ASSETDOCTOR_OT_scan_folder,
    ASSETDOCTOR_OT_scan_dependencies,
    ASSETDOCTOR_OT_analyze_overrides,
    ASSETDOCTOR_OT_fix_library_paths,
    ASSETDOCTOR_OT_toggle_pause,
    ASSETDOCTOR_OT_request_cancel,
    ASSETDOCTOR_OT_make_local,
    ASSETDOCTOR_OT_material_dedup,
    ASSETDOCTOR_OT_scan_orphans,
    ASSETDOCTOR_OT_instance_geometry,
    ASSETDOCTOR_OT_analyze_resources,
    ASSETDOCTOR_OT_profile_render,
    ASSETDOCTOR_OT_open_preferences,
    ASSETDOCTOR_OT_report_toggle,
    ASSETDOCTOR_OT_report_select,
    ASSETDOCTOR_OT_report_clear,
    ASSETDOCTOR_OT_row_label,
    ASSETDOCTOR_OT_select_datablock,
    ASSETDOCTOR_OT_export_report,
)
