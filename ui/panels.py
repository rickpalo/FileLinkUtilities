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


class ASSETDOCTOR_PG_tree_row(bpy.types.PropertyGroup):
    """One flattened, indented tree row, materialised so a ``UIList`` can draw it.

    The Report/Resource trees used to be drawn as manual rows, but the N-panel
    doesn't virtualize those, so a large expansion left rows blank past a point.
    A ``UIList`` virtualizes (only visible rows are realised) and scrolls, fixing
    that for any size. ``ops.report_store`` rebuilds the collection from
    ``core.tree.flatten_visible`` whenever the report or its expansion changes."""

    indent: bpy.props.IntProperty()  # type: ignore[valid-type]
    key: bpy.props.StringProperty()  # type: ignore[valid-type]
    label: bpy.props.StringProperty()  # type: ignore[valid-type]
    severity: bpy.props.StringProperty(default="info")  # type: ignore[valid-type]
    has_children: bpy.props.BoolProperty()  # type: ignore[valid-type]
    expanded: bpy.props.BoolProperty()  # type: ignore[valid-type]
    detail: bpy.props.StringProperty()  # type: ignore[valid-type]
    ref_type: bpy.props.StringProperty()  # type: ignore[valid-type]
    ref_name: bpy.props.StringProperty()  # type: ignore[valid-type]
    prop: bpy.props.StringProperty()  # expanded-keys WM prop this row belongs to


class ASSETDOCTOR_UL_tree(bpy.types.UIList):
    """Virtualized, scrollable tree for the Report and Resource panels: indent +
    expand toggle + tooltip-bearing label + right-aligned detail. Shared by both."""

    bl_idname = "ASSETDOCTOR_UL_tree"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.label)
            return
        row = layout.row(align=True)
        if item.indent:
            row.separator(factor=item.indent * 1.4)
        if item.has_children:
            tri = "TRIA_DOWN" if item.expanded else "TRIA_RIGHT"
            op = row.operator("assetdoctor.report_toggle", text="", icon=tri, emboss=False)
            op.key = item.key
            op.prop = item.prop
        else:
            row.label(text="", icon="BLANK1")
        # Label as a tooltip-bearing button: tooltip shows the full text (full path,
        # full message + size) even when the narrow panel truncates the display.
        full = item.label + (f"   [{item.detail}]" if item.detail else "")
        op = row.operator("assetdoctor.row_label", text=item.label,
                          icon=_SEVERITY_ICON.get(item.severity, "NONE"), emboss=False)
        op.text = full
        op.key = item.key
        op.prop = item.prop
        op.has_children = item.has_children
        if item.ref_type:
            op.ref_type = item.ref_type
            op.ref_name = item.ref_name
        if item.detail:
            sub = row.row()
            sub.alignment = "RIGHT"
            sub.label(text=item.detail)


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
        wm = context.window_manager

        # Shared live progress (shown only while a modal op — scan, make-local… — runs).
        # Kept on the parent panel so it stays visible above every (collapsible) section.
        if getattr(wm, "assetdoctor_op_active", False):
            col = layout.column()
            col.progress(
                factor=wm.assetdoctor_op_progress,
                type="BAR",
                text=wm.assetdoctor_op_status or "Working…",
            )
            col.label(text="Press ESC to cancel", icon="CANCEL")


class _FeaturePanel:
    """Shared bl_* attributes for the collapsible feature sub-panels.

    Each feature is a child panel of ASSETDOCTOR_PT_main so Blender gives it a
    native collapse triangle and remembers its open/closed state per-file."""
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AssetDoctor"
    bl_parent_id = "ASSETDOCTOR_PT_main"


class ASSETDOCTOR_PT_project(_FeaturePanel, bpy.types.Panel):
    bl_label = "Project (folder)"
    bl_idname = "ASSETDOCTOR_PT_project"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        layout.prop(scene, "assetdoctor_scan_dir", text="")
        op = layout.operator("assetdoctor.scan_folder", text="Scan Link Map", icon="VIEWZOOM")
        op.directory = scene.assetdoctor_scan_dir


class ASSETDOCTOR_PT_make_local(_FeaturePanel, bpy.types.Panel):
    bl_label = "Make Local"
    bl_idname = "ASSETDOCTOR_PT_make_local"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        layout.operator("assetdoctor.make_local", text="Report (dry run)").apply = False
        row = layout.row(align=True)
        op = row.operator("assetdoctor.make_local", text="→ New File")
        op.apply = True
        op.mode = "NEW_FILE"
        op = row.operator("assetdoctor.make_local", text="→ In Place")
        op.apply = True
        op.mode = "IN_PLACE"


class ASSETDOCTOR_PT_materials(_FeaturePanel, bpy.types.Panel):
    bl_label = "Duplicate Materials"
    bl_idname = "ASSETDOCTOR_PT_materials"
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        layout.operator("assetdoctor.material_dedup", text="Find Duplicates (report)").apply = False
        layout.operator("assetdoctor.material_dedup", text="Dedup & Remap (apply)").apply = True


class ASSETDOCTOR_PT_orphans(_FeaturePanel, bpy.types.Panel):
    bl_label = "Orphans & Fake Users"
    bl_idname = "ASSETDOCTOR_PT_orphans"
    bl_order = 3

    def draw(self, context):
        layout = self.layout
        layout.operator("assetdoctor.scan_orphans", text="Scan (report)").purge_orphans = False
        layout.operator("assetdoctor.scan_orphans", text="Scan + Purge Orphans").purge_orphans = True


class ASSETDOCTOR_PT_geometry(_FeaturePanel, bpy.types.Panel):
    bl_label = "Duplicate Geometry"
    bl_idname = "ASSETDOCTOR_PT_geometry"
    bl_order = 4

    def draw(self, context):
        layout = self.layout
        layout.operator("assetdoctor.instance_geometry", text="Find Duplicates (report)").apply = False
        layout.operator("assetdoctor.instance_geometry", text="Instance & Merge (apply)").apply = True


class ASSETDOCTOR_PT_resource_tools(_FeaturePanel, bpy.types.Panel):
    bl_label = "Resource Analyzer"
    bl_idname = "ASSETDOCTOR_PT_resource_tools"
    bl_order = 5

    def draw(self, context):
        layout = self.layout
        layout.operator("assetdoctor.analyze_resources", text="Analyze Memory/Disk", icon="VIEWZOOM")
        layout.operator("assetdoctor.profile_render", text="Profile Render (real RAM)", icon="RENDER_STILL")


class ASSETDOCTOR_PT_utilities(_FeaturePanel, bpy.types.Panel):
    bl_label = "Utilities"
    bl_idname = "ASSETDOCTOR_PT_utilities"
    bl_order = 6
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, "assetdoctor_debug_log")
        layout.operator("assetdoctor.open_preferences",
                        text="Lists & Backups: Add-on Preferences…", icon="PREFERENCES")


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
        from ..ops.report_store import (
            active_feature, available_features, data_prop,
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
        layout.template_list(
            "ASSETDOCTOR_UL_tree", "report",
            wm, "assetdoctor_report_rows",
            wm, "assetdoctor_report_index",
            rows=12, sort_lock=True,
        )


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
        layout = self.layout
        wm = context.window_manager

        layout.label(text="RAM / VRAM estimated; disk accurate", icon="INFO")
        if wm.assetdoctor_profiled_ram:
            layout.label(text=f"Profiled real peak RAM: {wm.assetdoctor_profiled_ram}",
                         icon="RENDER_STILL")
        layout.operator("assetdoctor.export_report", text="Export…", icon="EXPORT").source = "resource"
        layout.template_list(
            "ASSETDOCTOR_UL_tree", "resource",
            wm, "assetdoctor_resource_rows",
            wm, "assetdoctor_resource_index",
            rows=12, sort_lock=True,
        )
