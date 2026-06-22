"""The AssetDoctor N-panel (3D viewport sidebar > AssetDoctor).

Each feature exposes a read-only/report action and, where relevant, an explicit
Apply action so the report-first → apply workflow is reachable without the F9
redo panel. Detailed findings print to the system console
(Window > Toggle System Console on Windows) and, when enabled in Utilities, to
debugLog.txt. Button tooltips come from each operator's ``description()``.
"""

import os
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
        # No severity icon — they added clutter without clear value (user, 2026-06-16).
        full = item.label + (f"   [{item.detail}]" if item.detail else "")
        op = row.operator("assetdoctor.row_label", text=item.label,
                          icon="NONE", emboss=False)
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


class ASSETDOCTOR_PG_broken_lib(bpy.types.PropertyGroup):
    """One broken/missing library link, for the per-link relink list (F7).

    ``ops.relink._populate_broken_links`` fills the collection from the current
    file's missing libraries; ``target`` is the auto-found same-name candidate (or
    a file the user picked). ``selected`` is the per-row checkbox so the user
    relinks only the links they choose — e.g. one broken material library."""

    # `name` (PropertyGroup built-in) holds the library datablock name.
    stored: bpy.props.StringProperty()  # type: ignore[valid-type]
    target: bpy.props.StringProperty()  # type: ignore[valid-type]
    has_candidate: bpy.props.BoolProperty()  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=False, name="",
        description="Include this link when you Relink Selected")  # type: ignore[valid-type]
    # F6 B1 grouping (images only): original containing directory + a representative
    # material, so the user can point a whole group at one folder.
    group: bpy.props.StringProperty()  # type: ignore[valid-type]
    material: bpy.props.StringProperty()  # type: ignore[valid-type]


class ASSETDOCTOR_UL_broken_libs(bpy.types.UIList):
    """Per-link relink list: checkbox + broken library name + its target file (or
    a 'pick a file' hint) + a file-picker button. Lets the user fix one specific
    broken link without running a bulk pass."""

    bl_idname = "ASSETDOCTOR_UL_broken_libs"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.name)
            return
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        row.label(text=item.name, icon="LIBRARY_DATA_BROKEN")
        target = row.row()
        target.alignment = "RIGHT"
        if item.target:
            target.label(text=os.path.basename(item.target) or item.target,
                         icon="CHECKMARK" if item.has_candidate else "QUESTION")
        else:
            target.label(text="no match — pick a file", icon="QUESTION")
        row.operator("assetdoctor.relink_pick_file", text="", icon="FILEBROWSER").index = index


class ASSETDOCTOR_UL_broken_imgs(bpy.types.UIList):
    """Per-texture relink list (F6): checkbox + missing image name + its target
    file (or a 'pick a file' hint) + a file-picker button. Same shape as the
    broken-library list, reusing ASSETDOCTOR_PG_broken_lib for the rows."""

    bl_idname = "ASSETDOCTOR_UL_broken_imgs"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type == "GRID":
            layout.alignment = "CENTER"
            layout.label(text=item.name)
            return
        row = layout.row(align=True)
        row.prop(item, "selected", text="")
        row.label(text=item.name, icon="IMAGE_DATA")
        target = row.row()
        target.alignment = "RIGHT"
        if item.target:
            target.label(text=os.path.basename(item.target) or item.target,
                         icon="CHECKMARK" if item.has_candidate else "QUESTION")
        else:
            target.label(text="no match — pick a file", icon="QUESTION")
        row.operator("assetdoctor.relink_pick_texture", text="", icon="FILEBROWSER").index = index


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
        # Shared live progress (shown only while a modal op — scan, make-local… —
        # runs). Kept on the parent panel so it stays visible above every section.
        _draw_progress(self.layout, context.window_manager)


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


def _libraries_at_a_glance():
    """Instant linked-library health from ``bpy.data`` (in memory, no scan):
    (total, missing, absolute) over ``bpy.data.libraries``."""
    total = missing = absolute = 0
    for lib in bpy.data.libraries:
        fp = lib.filepath
        if not fp:
            continue
        total += 1
        if not fp.startswith("//"):
            absolute += 1
        try:
            if not pathlib.Path(bpy.path.abspath(fp)).is_file():
                missing += 1
        except Exception:
            missing += 1
    return total, missing, absolute


def _draw_progress(layout, wm):
    """Shared progress bar + Pause/Resume + ESC hint, drawn while a modal runs."""
    if not getattr(wm, "assetdoctor_op_active", False):
        return False
    col = layout.column()
    col.progress(
        factor=wm.assetdoctor_op_progress,
        type="BAR",
        text=wm.assetdoctor_op_status or "Working…",
    )
    row = col.row(align=True)
    paused = getattr(wm, "assetdoctor_op_paused", False)
    row.operator("assetdoctor.toggle_pause",
                 text="Resume" if paused else "Pause",
                 icon="PLAY" if paused else "PAUSE")
    row.operator("assetdoctor.request_cancel", text="Cancel (or ESC)", icon="X")
    return True


class ASSETDOCTOR_PT_scene_deps(bpy.types.Panel):
    """F7 Link & Dependency Doctor, in Properties > Scene (this is scene-data
    hygiene, not a 3D/render activity). The N-panel keeps the legacy tools for now;
    features migrate here one at a time."""

    bl_label = "AssetDoctor — Dependencies"
    bl_idname = "ASSETDOCTOR_PT_scene_deps"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"

    def draw_header(self, context):
        self.layout.label(text=f"v{_addon_version()}", icon="LINKED")

    # The F7 reports this panel can show (offline scan, live analysis, path fixes).
    _F7_FEATURES = (("f7", "Dependencies"), ("f7live", "Overrides & Dups"),
                    ("f7fix", "Path Fixes"), ("f6tex", "Missing Textures"),
                    ("f6dup", "Duplicate Textures"))

    def draw(self, context):
        from ..core.report import Report
        from ..ops.report_store import TREE_FEATURES, active_feature, data_prop

        layout = self.layout
        wm = context.window_manager

        # Instant "at a glance" from bpy.data (already in memory — no scan needed):
        # the current file + its linked-library health, so the panel is useful the
        # moment it opens; the deep scan/analyze are compact opt-in buttons.
        fname = bpy.path.basename(bpy.data.filepath) or "(unsaved)"
        layout.label(text=f"{fname}  ·  v{_addon_version()}", icon="FILE_BLEND")
        total, missing, absolute = _libraries_at_a_glance()
        bits = [f"{total} linked librar{'y' if total == 1 else 'ies'}"]
        if missing:
            bits.append(f"{missing} missing")
        if absolute:
            bits.append(f"{absolute} absolute")
        layout.label(text="   ·   ".join(bits), icon="LIBRARY_DATA_DIRECT")

        # Scan Dependencies reads the .blend FROM DISK (offline BAT), so it reflects
        # the last SAVED state — unsaved relinks/fixes won't show until you save.
        # Warn when the file is dirty so a stale "missing link" isn't confusing.
        if bpy.data.filepath and bpy.data.is_dirty:
            warn = layout.row()
            warn.alert = True
            warn.label(text="Unsaved changes — save before Scan deps (it reads from disk)",
                       icon="ERROR")

        # Compact one-row actions (both operate on the CURRENT file).
        row = layout.row(align=True)
        row.operator("assetdoctor.scan_dependencies", text="Scan deps", icon="VIEWZOOM")
        row.operator("assetdoctor.analyze_overrides", text="Analyze", icon="LIBRARY_DATA_OVERRIDE")

        # Phase 3 path fixes are TWO independent jobs (user, 2026-06-21):
        #  (1) relink broken/missing library links — per-link + pick-a-file, so you
        #      can fix one specific link (e.g. a broken material library);
        #  (2) normalize the paths of libraries that already resolve.
        links = layout.box().column(align=True)
        links.label(text="Broken links", icon="LIBRARY_DATA_BROKEN")
        links.operator("assetdoctor.scan_broken_links", text="Find Broken Links", icon="VIEWZOOM")
        if len(wm.assetdoctor_broken_libs):
            links.template_list(
                "ASSETDOCTOR_UL_broken_libs", "brokenlibs",
                wm, "assetdoctor_broken_libs",
                wm, "assetdoctor_broken_index", rows=4)
            links.operator("assetdoctor.relink_selected",
                           text="Relink Selected (creates backup)", icon="FILE_REFRESH")

        norm = layout.box().column(align=True)
        norm.label(text="Path normalization", icon="FILE_REFRESH")
        nr = norm.row(align=True)
        nr.operator("assetdoctor.normalize_library_paths", text="Check").apply = False
        nr.operator("assetdoctor.normalize_library_paths",
                    text="Normalize (creates backup)", icon="CHECKMARK").apply = True

        # F6 Layer 1: relink missing image textures (the magenta) — per-texture,
        # auto-fixing doubled path segments / finding files by name, pick-a-file.
        tex = layout.box().column(align=True)
        tex.label(text="Missing textures", icon="IMAGE_DATA")
        tex.operator("assetdoctor.scan_broken_textures", text="Find Missing Textures", icon="VIEWZOOM")
        if len(wm.assetdoctor_broken_imgs):
            tex.template_list(
                "ASSETDOCTOR_UL_broken_imgs", "brokenimgs",
                wm, "assetdoctor_broken_imgs",
                wm, "assetdoctor_broken_imgs_index", rows=4)
            tex.operator("assetdoctor.relink_textures_selected",
                         text="Relink Selected (creates backup)", icon="FILE_REFRESH")

            # B1: point a whole GROUP at one folder. Group by original folder, or by
            # material when that folder is gone; matching fills targets, then Relink.
            mode = wm.assetdoctor_tex_group_by
            grp = tex.box().column(align=True)
            grp.label(text="Fix a group at once", icon="OUTLINER_OB_GROUP_INSTANCE")
            grp.row(align=True).prop(wm, "assetdoctor_tex_group_by", expand=True)
            counts: dict[str, int] = {}
            for item in wm.assetdoctor_broken_imgs:
                key = item.group if mode == "DIR" else item.material
                if key:
                    counts[key] = counts.get(key, 0) + 1
            if counts:
                for key in sorted(counts):
                    disp = (os.path.basename(key.rstrip("/")) or key) if mode == "DIR" else key
                    grow = grp.row(align=True)
                    grow.label(text=f"{disp}  ({counts[key]})",
                               icon="FILE_FOLDER" if mode == "DIR" else "MATERIAL")
                    op = grow.operator("assetdoctor.point_group_at_folder",
                                       text="Point at folder…", icon="FILEBROWSER")
                    op.group_key = key
                    op.by = mode
            else:
                grp.label(text="(no material assigned to these)" if mode == "MATERIAL"
                          else "(no folder info)", icon="INFO")

        # Follow-up A: Blender's native recursive search (by filename) over a chosen
        # folder; reports found vs still-missing. Affects ALL external files.
        tex.operator("assetdoctor.find_missing_files_folder",
                     text="Find Missing Files (folder)…", icon="FILEBROWSER")

        # F6 Layer 2 (step 3): merge content-identical .NNN duplicate image
        # datablocks (verified by dimensions + hash). Separate from relinking.
        dup = layout.box().column(align=True)
        dup.label(text="Duplicate textures (.NNN)", icon="IMAGE_DATA")
        drow = dup.row(align=True)
        drow.operator("assetdoctor.dedup_textures", text="Find (report)",
                      icon="VIEWZOOM").apply = False
        drow.operator("assetdoctor.dedup_textures",
                      text="Merge (creates backup)").apply = True

        # While a scan runs, show only the progress (avoids the cramped overlap
        # of progress + empty-state hint the user reported).
        if _draw_progress(layout, wm):
            return

        # Which F7 reports exist; a small selector when more than one.
        present = [(k, lbl) for k, lbl in self._F7_FEATURES if getattr(wm, data_prop(k), "")]
        if not present:
            layout.separator()
            layout.label(text="Run a scan or analysis to see results.", icon="INFO")
            return

        active = active_feature(wm)
        if active not in dict(present):
            active = present[0][0]
        layout.separator()
        selrow = layout.row(align=True)
        for key, lbl in present:
            selrow.operator("assetdoctor.report_select", text=lbl,
                            depress=(key == active)).feature = key
        selrow.operator("assetdoctor.export_report", text="", icon="EXPORT").source = "report"

        if active not in TREE_FEATURES:
            try:
                report = Report.from_json(getattr(wm, data_prop(active)))
            except Exception:
                layout.label(text="(could not read report)", icon="ERROR")
                return
            layout.label(text=report.title, icon="PRESET")
        layout.template_list(
            "ASSETDOCTOR_UL_tree", "f7report",
            wm, "assetdoctor_report_rows",
            wm, "assetdoctor_report_index",
            rows=14, sort_lock=True,
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
