"""bpy operators for AssetDoctor (the only code allowed to import bpy besides ui/prefs).

Each operator is thin: gather bpy data -> hand to assetdoctor.core -> show a
report -> on explicit Apply, mutate (after an auto-backup). The operators below
are scaffold stubs that register cleanly; feature logic arrives per-milestone.
"""

from .scan_folder import ASSETDOCTOR_OT_scan_folder
from .dep_scan import ASSETDOCTOR_OT_scan_dependencies
from .reversedep import ASSETDOCTOR_OT_check_dependents
from .datablock_inspect import (
    ASSETDOCTOR_OT_analyze_overrides,
    ASSETDOCTOR_OT_scan_missing_datablocks,
    ASSETDOCTOR_OT_scan_all_missing,
)
from .relink import (
    ASSETDOCTOR_OT_normalize_library_paths,
    ASSETDOCTOR_OT_relink_pick_file,
    ASSETDOCTOR_OT_relink_selected,
    ASSETDOCTOR_OT_scan_broken_links,
)
from .datablock_reconnect import (
    ASSETDOCTOR_OT_scan_reconnect_targets,
    ASSETDOCTOR_OT_reconnect_pick_source,
    ASSETDOCTOR_OT_reconnect_selected,
    ASSETDOCTOR_OT_reconnect_category_toggle,
)
from .datablock_dup import (
    ASSETDOCTOR_OT_scan_datablock_dups,
    ASSETDOCTOR_OT_merge_datablock_selected,
    ASSETDOCTOR_OT_datablock_category_toggle,
)
from .examine_library import (
    ASSETDOCTOR_OT_examine_library,
    ASSETDOCTOR_OT_examine_pick_source,
    ASSETDOCTOR_OT_examine_apply_selected,
    ASSETDOCTOR_OT_examine_category_toggle,
)
from .image_relink import (
    ASSETDOCTOR_OT_scan_broken_textures,
    ASSETDOCTOR_OT_relink_folder_search,
    ASSETDOCTOR_OT_search_textures_folder,
    ASSETDOCTOR_OT_suggest_fuzzy_matches,
    ASSETDOCTOR_OT_suggest_from_material,
    ASSETDOCTOR_OT_suggest_from_blend,
    ASSETDOCTOR_OT_accept_match,
    ASSETDOCTOR_OT_accept_material_matches,
    ASSETDOCTOR_OT_accept_all_matches,
    ASSETDOCTOR_OT_tex_category_toggle,
    ASSETDOCTOR_OT_point_group_at_folder,
    ASSETDOCTOR_OT_relink_pick_texture,
    ASSETDOCTOR_OT_relink_textures_selected,
)
from .image_dedup import (
    ASSETDOCTOR_OT_scan_dup_textures,
    ASSETDOCTOR_OT_scan_content_dups,
    ASSETDOCTOR_OT_merge_dup_selected,
    ASSETDOCTOR_OT_dup_material_keeper,
    ASSETDOCTOR_OT_dup_category_toggle,
    ASSETDOCTOR_OT_scan_res_variants,
)
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
    ASSETDOCTOR_OT_report_expand_all,
    ASSETDOCTOR_OT_report_select,
    ASSETDOCTOR_OT_report_toggle,
    ASSETDOCTOR_OT_row_label,
    ASSETDOCTOR_OT_select_datablock,
)

REGISTER_CLASSES = (
    ASSETDOCTOR_OT_scan_folder,
    ASSETDOCTOR_OT_scan_dependencies,
    ASSETDOCTOR_OT_check_dependents,
    ASSETDOCTOR_OT_analyze_overrides,
    ASSETDOCTOR_OT_scan_missing_datablocks,
    ASSETDOCTOR_OT_scan_all_missing,
    ASSETDOCTOR_OT_scan_broken_links,
    ASSETDOCTOR_OT_relink_pick_file,
    ASSETDOCTOR_OT_relink_selected,
    ASSETDOCTOR_OT_normalize_library_paths,
    ASSETDOCTOR_OT_scan_reconnect_targets,
    ASSETDOCTOR_OT_reconnect_pick_source,
    ASSETDOCTOR_OT_reconnect_selected,
    ASSETDOCTOR_OT_reconnect_category_toggle,
    ASSETDOCTOR_OT_scan_datablock_dups,
    ASSETDOCTOR_OT_merge_datablock_selected,
    ASSETDOCTOR_OT_datablock_category_toggle,
    ASSETDOCTOR_OT_examine_library,
    ASSETDOCTOR_OT_examine_pick_source,
    ASSETDOCTOR_OT_examine_apply_selected,
    ASSETDOCTOR_OT_examine_category_toggle,
    ASSETDOCTOR_OT_scan_broken_textures,
    ASSETDOCTOR_OT_relink_folder_search,
    ASSETDOCTOR_OT_search_textures_folder,
    ASSETDOCTOR_OT_suggest_fuzzy_matches,
    ASSETDOCTOR_OT_suggest_from_material,
    ASSETDOCTOR_OT_suggest_from_blend,
    ASSETDOCTOR_OT_accept_match,
    ASSETDOCTOR_OT_accept_material_matches,
    ASSETDOCTOR_OT_accept_all_matches,
    ASSETDOCTOR_OT_tex_category_toggle,
    ASSETDOCTOR_OT_point_group_at_folder,
    ASSETDOCTOR_OT_relink_pick_texture,
    ASSETDOCTOR_OT_relink_textures_selected,
    ASSETDOCTOR_OT_scan_dup_textures,
    ASSETDOCTOR_OT_scan_content_dups,
    ASSETDOCTOR_OT_merge_dup_selected,
    ASSETDOCTOR_OT_dup_material_keeper,
    ASSETDOCTOR_OT_dup_category_toggle,
    ASSETDOCTOR_OT_scan_res_variants,
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
    ASSETDOCTOR_OT_report_expand_all,
    ASSETDOCTOR_OT_report_select,
    ASSETDOCTOR_OT_report_clear,
    ASSETDOCTOR_OT_row_label,
    ASSETDOCTOR_OT_select_datablock,
    ASSETDOCTOR_OT_export_report,
)
