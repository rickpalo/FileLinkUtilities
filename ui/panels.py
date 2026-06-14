"""The AssetDoctor N-panel (3D viewport sidebar > AssetDoctor).

Each feature exposes a read-only/report action and, where relevant, an explicit
Apply action so the report-first → apply workflow is reachable without the F9
redo panel. Detailed findings print to the system console
(Window > Toggle System Console on Windows) and, when enabled in Utilities, to
debugLog.txt. Button tooltips come from each operator's ``description()``.
"""

import pathlib

import bpy

DOC_URL = "https://github.com/rickpalo/AssetDoctor/tree/main/docs"

_ADDON_VERSION = None


def _addon_version() -> str:
    """Addon version read once from the manifest (single source of truth)."""
    global _ADDON_VERSION
    if _ADDON_VERSION is None:
        try:
            import tomllib

            manifest = pathlib.Path(__file__).resolve().parent.parent / "blender_manifest.toml"
            _ADDON_VERSION = tomllib.loads(manifest.read_text(encoding="utf-8")).get("version", "?")
        except Exception:
            _ADDON_VERSION = "?"
    return _ADDON_VERSION

# Severity -> Blender icon for tree rows ("info" shows no icon to reduce noise).
_SEVERITY_ICON = {"info": "NONE", "warning": "ERROR", "error": "CANCEL"}


def _draw_tree(layout, rows, expanded_prop, max_rows=200):
    """Render flattened tree Rows: indent + expand toggle + label + right-aligned
    detail + optional select button. Shared by the Report and Resource panels.

    Capped at ``max_rows`` because the N-panel doesn't virtualize manually-drawn
    rows — a huge expansion can otherwise leave rows blank. Beyond the cap we show
    a hint to use Export for the full list."""
    col = layout.column(align=True)
    for r in rows[:max_rows]:
        row = col.row(align=True)
        if r.indent:
            row.separator(factor=r.indent * 1.4)
        if r.has_children:
            icon = "TRIA_DOWN" if r.expanded else "TRIA_RIGHT"
            op = row.operator("assetdoctor.report_toggle", text="", icon=icon, emboss=False)
            op.key = r.key
            op.prop = expanded_prop
        else:
            row.label(text="", icon="BLANK1")
        # Label as a tooltip-bearing button: tooltip shows the full text (full path,
        # full message + size) even when the narrow panel truncates the display.
        full = r.label + (f"   [{r.detail}]" if r.detail else "")
        op = row.operator("assetdoctor.row_label", text=r.label,
                          icon=_SEVERITY_ICON.get(r.severity, "NONE"), emboss=False)
        op.text = full
        op.key = r.key
        op.prop = expanded_prop
        op.has_children = r.has_children
        if r.ref:
            op.ref_type = r.ref["type"]
            op.ref_name = r.ref["name"]
        if r.detail:
            sub = row.row()
            sub.alignment = "RIGHT"
            sub.label(text=r.detail)
    if len(rows) > max_rows:
        col.label(text=f"+{len(rows) - max_rows} more — use Export… for the full list",
                  icon="INFO")


class ASSETDOCTOR_PT_main(bpy.types.Panel):
    bl_label = "AssetDoctor"
    bl_idname = "ASSETDOCTOR_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AssetDoctor"

    def draw_header(self, context):
        # Title (bl_label) at left, then version, then the doc icon pinned far right.
        layout = self.layout
        layout.label(text=f"v{_addon_version()}")
        sub = layout.row()
        sub.alignment = "RIGHT"
        sub.operator("wm.url_open", text="", icon="HELP", emboss=False).url = DOC_URL

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        wm = context.window_manager

        # Live scan progress (shown only while the modal folder scan runs).
        if getattr(wm, "assetdoctor_scan_active", False):
            col = layout.column()
            col.progress(
                factor=wm.assetdoctor_scan_progress,
                type="BAR",
                text=wm.assetdoctor_scan_status or "Scanning…",
            )
            col.label(text="Press ESC to cancel", icon="CANCEL")

        box = layout.box()
        box.label(text="Project (folder)", icon="FILE_FOLDER")
        box.prop(scene, "assetdoctor_scan_dir", text="")
        op = box.operator("assetdoctor.scan_folder", text="Scan Link Map", icon="VIEWZOOM")
        op.directory = scene.assetdoctor_scan_dir

        box = layout.box()
        box.label(text="Make Local", icon="LINKED")
        box.operator("assetdoctor.make_local", text="Report (dry run)").apply = False
        row = box.row(align=True)
        op = row.operator("assetdoctor.make_local", text="→ New File")
        op.apply = True
        op.mode = "NEW_FILE"
        op = row.operator("assetdoctor.make_local", text="→ In Place")
        op.apply = True
        op.mode = "IN_PLACE"

        box = layout.box()
        box.label(text="Duplicate Materials", icon="MATERIAL")
        box.operator("assetdoctor.material_dedup", text="Find Duplicates (report)").apply = False
        box.operator("assetdoctor.material_dedup", text="Dedup & Remap (apply)").apply = True

        box = layout.box()
        box.label(text="Orphans & Fake Users", icon="ORPHAN_DATA")
        box.operator("assetdoctor.scan_orphans", text="Scan (report)").purge_orphans = False
        box.operator("assetdoctor.scan_orphans", text="Scan + Purge Orphans").purge_orphans = True

        box = layout.box()
        box.label(text="Duplicate Geometry", icon="MESH_DATA")
        box.operator("assetdoctor.instance_geometry", text="Find Duplicates (report)").apply = False
        box.operator("assetdoctor.instance_geometry", text="Instance & Merge (apply)").apply = True

        box = layout.box()
        box.label(text="Resource Analyzer", icon="DISK_DRIVE")
        box.operator("assetdoctor.analyze_resources", text="Analyze Memory/Disk", icon="VIEWZOOM")
        box.operator("assetdoctor.profile_render", text="Profile Render (real RAM)", icon="RENDER_STILL")

        layout.label(text="Lists/backups: Add-on Preferences", icon="PREFERENCES")

        box = layout.box()
        box.label(text="Utilities", icon="TOOL_SETTINGS")
        box.prop(scene, "assetdoctor_debug_log")


class ASSETDOCTOR_PT_report(bpy.types.Panel):
    bl_label = "Report"
    bl_idname = "ASSETDOCTOR_PT_report"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AssetDoctor"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 1

    @classmethod
    def poll(cls, context):
        from ..ops.report_store import available_features

        return bool(available_features(context.window_manager))

    def draw_header(self, context):
        self.layout.operator("assetdoctor.report_clear", text="", icon="X", emboss=False)

    def draw(self, context):
        from ..core.report import Report
        from ..core.tree import flatten_visible, report_to_tree
        from ..ops.report_store import (
            active_feature, available_features, data_prop, exp_prop, get_expanded,
        )

        layout = self.layout
        wm = context.window_manager
        avail = available_features(wm)
        active = active_feature(wm)

        # Persistent-report selector: one button per report that exists.
        selrow = layout.row(align=True)
        for key, label in avail:
            selrow.operator("assetdoctor.report_select", text=label,
                            depress=(key == active)).feature = key
        layout.operator("assetdoctor.export_report", text="Export…", icon="EXPORT").source = "report"

        try:
            report = Report.from_json(getattr(wm, data_prop(active)))
        except Exception:
            layout.label(text="(could not read report)", icon="ERROR")
            return

        layout.label(text=report.title, icon="PRESET")
        rows = flatten_visible(report_to_tree(report), get_expanded(wm, exp_prop(active)))
        _draw_tree(layout, rows, exp_prop(active))


class ASSETDOCTOR_PT_resources(bpy.types.Panel):
    bl_label = "Resource Usage (estimate)"
    bl_idname = "ASSETDOCTOR_PT_resources"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AssetDoctor"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 2

    @classmethod
    def poll(cls, context):
        return bool(context.window_manager.assetdoctor_resource_tree)

    def draw(self, context):
        from ..core.tree import flatten_visible, nodes_from_json
        from ..ops.report_store import get_expanded

        layout = self.layout
        wm = context.window_manager
        try:
            nodes = nodes_from_json(wm.assetdoctor_resource_tree)
        except Exception:
            layout.label(text="(could not read resource data)", icon="ERROR")
            return

        layout.label(text="RAM / VRAM estimated; disk accurate", icon="INFO")
        if wm.assetdoctor_profiled_ram:
            layout.label(text=f"Profiled real peak RAM: {wm.assetdoctor_profiled_ram}",
                         icon="RENDER_STILL")
        layout.operator("assetdoctor.export_report", text="Export…", icon="EXPORT").source = "resource"
        rows = flatten_visible(nodes, get_expanded(wm, "assetdoctor_resource_expanded"))
        _draw_tree(layout, rows, "assetdoctor_resource_expanded")
