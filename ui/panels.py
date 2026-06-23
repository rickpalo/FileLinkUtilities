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
    icon: bpy.props.StringProperty()  # optional per-node icon override (e.g. File Map)  # type: ignore[valid-type]
    guide: bpy.props.StringProperty()  # precomputed "│  ├─ "-style indent-guide prefix  # type: ignore[valid-type]
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
        # Indent guide: a "│  ├─ "-style connector (precomputed in core.tree) reads
        # clearer than blank space, especially in deep trees like the F7 File Map.
        if item.guide:
            row.label(text=item.guide, icon="NONE")
        if item.has_children:
            tri = "TRIA_DOWN" if item.expanded else "TRIA_RIGHT"
            op = row.operator("assetdoctor.report_toggle", text="", icon=tri, emboss=False)
            op.key = item.key
            op.prop = item.prop
        else:
            row.label(text="", icon="BLANK1")
        # Per-node icon override (e.g. the File Map's blend/missing/external-folder
        # icons) — most rows don't set one, keeping today's icon-free look.
        if item.icon:
            row.label(text="", icon=item.icon)
        # Label as a tooltip-bearing button: tooltip shows the full text (full path,
        # full message + size) even when the narrow panel truncates the display.
        # No severity icon — they added clutter without clear value (user, 2026-06-16).
        full = item.label + (f"   [{item.detail}]" if item.detail else "")
        # Width-aware status lines: a top-level info row (e.g. the "✓ … clean"
        # status) drops its " — …" explanatory tail on a narrow panel, so the gist
        # stays readable without sideways scrolling; the tooltip keeps the full text.
        display = item.label
        region = context.region
        if (item.indent == 0 and not item.has_children and item.severity == "info"
                and " — " in item.label and region and region.width < 320):
            display = item.label.split(" — ", 1)[0]
        op = row.operator("assetdoctor.row_label", text=display,
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
    # F6 step 4 "Possible Matches": a FUZZY-proposed file for a texture that exact
    # search couldn't place (vendor-renamed channels, etc.). Staged separately from
    # ``target`` — the user reviews + Accepts, which copies ``proposal`` into
    # ``target``. ``proposal_confidence`` is "high"/"medium"/"low";
    # ``proposal_res_mismatch`` flags a different resolution (lossy — lower trust).
    proposal: bpy.props.StringProperty()  # type: ignore[valid-type]
    proposal_confidence: bpy.props.StringProperty()  # type: ignore[valid-type]
    proposal_res_mismatch: bpy.props.BoolProperty()  # type: ignore[valid-type]


# Keeps a strong reference to each row's keeper-enum items list. Dynamic
# EnumProperty item callbacks MUST NOT let the returned strings be garbage-collected
# (a well-known Blender crash) — caching the list here pins them for the row's life.
_KEEPER_ITEMS_CACHE: dict[str, list] = {}


def _keeper_enum_items(self, context):
    """Items for a duplicate family's keeper dropdown = its member datablock names
    (canonical first). Built from the row's newline-joined ``members`` string."""
    names = [n for n in self.members.split("\n") if n]
    items = [(n, n, "Keep this datablock; merge the others into it", i)
             for i, n in enumerate(names)]
    _KEEPER_ITEMS_CACHE[self.members] = items  # pin against GC
    return items or [("", "", "")]


class ASSETDOCTOR_PG_dup_family(bpy.types.PropertyGroup):
    """One content-identical ``.NNN`` duplicate family, for the redesigned Duplicate
    Materials/Textures list. ``members`` (newline-joined, canonical first) feeds the
    ``keeper`` dropdown so the user can pick which datablock survives; ``selected``
    is the per-family include checkbox for Merge Selected."""

    # `name` (built-in) = the family base name.
    members: bpy.props.StringProperty()  # type: ignore[valid-type]
    keeper: bpy.props.EnumProperty(
        name="Keep", description="Which datablock to keep; the rest merge into it",
        items=_keeper_enum_items)  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=True, name="",
        description="Include this family when you Merge Selected")  # type: ignore[valid-type]
    material: bpy.props.StringProperty()  # type: ignore[valid-type]
    # Eyedropper override: when the auto-attributed material looks wrong (its name
    # doesn't match the texture's), point this at the correct material to re-group
    # the family under it. Organizational only — it does NOT rewire node trees.
    material_override: bpy.props.PointerProperty(type=bpy.types.Material)  # type: ignore[valid-type]
    removable: bpy.props.IntProperty()  # type: ignore[valid-type]


# Keeps a strong reference to each row's reconnect-target enum items list, the
# same GC-pin trick as _KEEPER_ITEMS_CACHE — dynamic EnumProperty item callbacks
# must not let the returned strings be garbage-collected.
_RECONNECT_ITEMS_CACHE: dict[str, list] = {}


def _reconnect_target_items(self, context):
    """Items for a missing block's reconnect-target dropdown = the names available
    in its chosen source .blend (``ops.datablock_reconnect._enumerate_group`` fills
    ``candidates``, already ranked so the suggested name is first — Blender shows a
    fresh dynamic enum's first item by default, so that's how the suggestion
    becomes the default selection without an explicit (fragile) assignment)."""
    names = [n for n in self.candidates.split("\n") if n]
    if not names:
        return [("", "(pick a source .blend first)", "")]
    items = [(n, n, "Reconnect to this datablock", i) for i, n in enumerate(names)]
    _RECONNECT_ITEMS_CACHE[self.candidates] = items  # pin against GC
    return items


class ASSETDOCTOR_PG_missing_block(bpy.types.PropertyGroup):
    """One missing (placeholder) data-block staged for RECONNECT (Batch C). Rows
    group by ``library`` in the panel — one source-.blend pick applies to the whole
    group, since a broken/renamed library's blocks usually all need the same fix.
    ``ops.datablock_reconnect`` fills/enumerates/applies this list."""

    # `name` (built-in) = the missing block's own name.
    kind: bpy.props.StringProperty()  # type: ignore[valid-type]
    collection: bpy.props.StringProperty()  # bpy.data attribute, e.g. "materials"  # type: ignore[valid-type]
    library: bpy.props.StringProperty()  # original source library path (group key)  # type: ignore[valid-type]
    source_blend: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]
    candidates: bpy.props.StringProperty()  # newline-joined names, ranked (best first)  # type: ignore[valid-type]
    confidence: bpy.props.StringProperty(default="none")  # type: ignore[valid-type]
    target: bpy.props.EnumProperty(
        name="Reconnect to", items=_reconnect_target_items)  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=False, name="",
        description="Include this data-block when you Reconnect Selected")  # type: ignore[valid-type]


# Same GC-pin trick as _KEEPER_ITEMS_CACHE, separate cache for this list's rows.
_GENERIC_KEEPER_CACHE: dict[str, list] = {}


def _generic_keeper_items(self, context):
    """Items for a generic duplicate family's keeper dropdown = its member
    datablock names (canonical first, like the image-dedup keeper)."""
    names = [n for n in self.members.split("\n") if n]
    items = [(n, n, "Keep this datablock; merge the others into it", i)
             for i, n in enumerate(names)]
    _GENERIC_KEEPER_CACHE[self.members] = items  # pin against GC
    return items or [("", "", "")]


class ASSETDOCTOR_PG_datablock_family(bpy.types.PropertyGroup):
    """One content-identical ``.NNN`` duplicate family for the generic Duplicate
    Data-blocks list (Batch C #3) — any datablock type ``ops.datablock_dup``
    fingerprints, grouped by ``kind`` in the panel (no material attribution; that
    concept is texture-specific)."""

    # `name` (built-in) = "{bpy.data attribute}:{family base name}".
    kind: bpy.props.StringProperty()  # display label, e.g. "Action"  # type: ignore[valid-type]
    collection: bpy.props.StringProperty()  # bpy.data attribute, e.g. "actions"  # type: ignore[valid-type]
    members: bpy.props.StringProperty()  # newline-joined, canonical first  # type: ignore[valid-type]
    keeper: bpy.props.EnumProperty(
        name="Keep", description="Which datablock to keep; the rest merge into it",
        items=_generic_keeper_items)  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=True, name="",
        description="Include this family when you Merge Selected")  # type: ignore[valid-type]
    removable: bpy.props.IntProperty()  # type: ignore[valid-type]


# Same GC-pin trick as _RECONNECT_ITEMS_CACHE, separate cache for this list.
_EXAMINE_ITEMS_CACHE: dict[str, list] = {}


def _examine_target_items(self, context):
    """Items for an Examine Library row's manual-pick dropdown = the names found
    in the .blend the user picked via Pick a Specific Item (ranked, closest-name
    first; the user is free to pick ANY of them, e.g. a Sphere for a Cube)."""
    names = [n for n in self.candidates.split("\n") if n]
    if not names:
        return [("", "(pick a .blend first)", "")]
    items = [(n, n, "Relink to this datablock", i) for i, n in enumerate(names)]
    _EXAMINE_ITEMS_CACHE[self.candidates] = items  # pin against GC
    return items


class ASSETDOCTOR_PG_examine_row(bpy.types.PropertyGroup):
    """One datablock the EXAMINED library currently provides (Examine Library —
    distinct from the missing-data-block reconnect list: these links are NOT
    broken, the user just wants to stop depending on this library for them).

    ``ops.examine_library`` fills/applies this list. Per row: accept the
    in-memory suggestion (``use_suggested``), tick Make Local, or manually pick a
    specific source + item (``source_blend``/``target``) — mutually exclusive,
    checked in that priority order on Apply."""

    # `name` (built-in) = the datablock's own name.
    kind: bpy.props.StringProperty()  # type: ignore[valid-type]
    collection: bpy.props.StringProperty()  # bpy.data attribute  # type: ignore[valid-type]
    suggested_kind: bpy.props.StringProperty(default="none")  # "local" | "library" | "none"  # type: ignore[valid-type]
    suggested_name: bpy.props.StringProperty()  # type: ignore[valid-type]
    suggested_library: bpy.props.StringProperty()  # filepath, when suggested_kind == "library"  # type: ignore[valid-type]
    use_suggested: bpy.props.BoolProperty(default=False)  # type: ignore[valid-type]
    make_local: bpy.props.BoolProperty(
        default=False, name="",
        description="Sever the link and keep using THIS copy locally")  # type: ignore[valid-type]
    source_blend: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]
    candidates: bpy.props.StringProperty()  # newline-joined names from source_blend  # type: ignore[valid-type]
    target: bpy.props.EnumProperty(
        name="Relink to", items=_examine_target_items)  # type: ignore[valid-type]
    selected: bpy.props.BoolProperty(
        default=False, name="",
        description="Include this data-block when you Apply Selected")  # type: ignore[valid-type]


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
        layout.operator("assetdoctor.make_local", text="Report (Dry Run)").apply = False
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
        layout.operator("assetdoctor.material_dedup", text="Find Duplicates (Report)").apply = False
        layout.operator("assetdoctor.material_dedup", text="Dedup & Remap (Apply)").apply = True


class ASSETDOCTOR_PT_orphans(_FeaturePanel, bpy.types.Panel):
    bl_label = "Orphans & Fake Users"
    bl_idname = "ASSETDOCTOR_PT_orphans"
    bl_order = 3

    def draw(self, context):
        layout = self.layout
        layout.operator("assetdoctor.scan_orphans", text="Scan (Report)").purge_orphans = False
        layout.operator("assetdoctor.scan_orphans", text="Scan + Purge Orphans").purge_orphans = True


class ASSETDOCTOR_PT_geometry(_FeaturePanel, bpy.types.Panel):
    bl_label = "Duplicate Geometry"
    bl_idname = "ASSETDOCTOR_PT_geometry"
    bl_order = 4

    def draw(self, context):
        layout = self.layout
        layout.operator("assetdoctor.instance_geometry", text="Find Duplicates (Report)").apply = False
        layout.operator("assetdoctor.instance_geometry", text="Instance & Merge (Apply)").apply = True


class ASSETDOCTOR_PT_resource_tools(_FeaturePanel, bpy.types.Panel):
    bl_label = "Resource Analyzer"
    bl_idname = "ASSETDOCTOR_PT_resource_tools"
    bl_order = 5

    def draw(self, context):
        layout = self.layout
        layout.operator("assetdoctor.analyze_resources", text="Analyze Memory/Disk", icon="VIEWZOOM")
        layout.operator("assetdoctor.profile_render", text="Profile Render (Real RAM)", icon="RENDER_STILL")


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
    # f6tex (the old before/after Missing-Textures report) is gone — the Missing
    # Textures section now lists everything inline, so no separate report is needed.
    # f6dup is intentionally NOT here — the Duplicate Materials/Textures section now
    # lists everything inline (with a keeper dropdown), so it needs no report slot in
    # the selector; the report is still built + stashed for the inline Export button.
    _F7_FEATURES = (("f7", "Dependencies"), ("f7live", "Overrides & Dups"),
                    ("f7miss", "Missing Data-blocks"), ("f7rev", "Safe to Delete?"),
                    ("f7links", "Broken Links"), ("f7fix", "Path Fixes"),
                    ("f6res", "Resolution Variants"))

    def draw(self, context):
        from ..core.report import Report
        from ..ops.report_store import TREE_FEATURES, active_feature, data_prop, exp_prop

        layout = self.layout
        wm = context.window_manager

        # Instant "at a glance" from bpy.data (already in memory — no scan needed):
        # the current file + its linked-library health, so the panel is useful the
        # moment it opens; the deep scan/analyze are compact opt-in buttons.
        fname = bpy.path.basename(bpy.data.filepath) or "(unsaved)"
        layout.label(text=fname, icon="FILE_BLEND")  # version lives in the panel header
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

        # Progress bar + Pause/Cancel ride at the TOP (right under the file/link info)
        # so a running scan is visible without scrolling (user, 2026-06-23).
        _draw_progress(layout, wm)

        # Compact one-row actions (both operate on the CURRENT file).
        row = layout.row(align=True)
        row.operator("assetdoctor.scan_dependencies", text="Scan Deps", icon="VIEWZOOM")
        row.operator("assetdoctor.analyze_overrides", text="Analyze", icon="LIBRARY_DATA_OVERRIDE")

        # Batch C #3: act on the duplicate_family findings Analyze's Overrides &
        # Dups report surfaces (Objects/Actions/Node Groups/etc. — Materials/Meshes/
        # Images already have their own dedicated dedup tools below/elsewhere).
        self._draw_datablock_dups(context, layout, wm)

        # Folder-wide link map (graphical). Distinct scope from the current-file
        # tools below: pick a directory, scan EVERY .blend in it (recursive, backups
        # skipped), and open an interactive file→file graph in the browser.
        pmap = layout.box().column(align=True)
        pmap.label(text="Project link map (folder → graph)", icon="NODETREE")
        pmap.prop(context.scene, "assetdoctor_scan_dir", text="")
        pmap.operator("assetdoctor.scan_folder", text="Scan Folder → Open Graph",
                      icon="VIEWZOOM").directory = context.scene.assetdoctor_scan_dir

        # Reverse-dependency: before deleting a .blend, find who links TO it (scans
        # the Project Folder above). The inverse of the top-down scan.
        rev = layout.box().column(align=True)
        rev.label(text="Safe to delete? (who links this file)", icon="TRASH")
        rev.prop(context.scene, "assetdoctor_dep_target", text="")
        rev.operator("assetdoctor.check_dependents", text="Check What Links This",
                     icon="VIEWZOOM")
        verdict = wm.assetdoctor_dep_verdict
        if verdict == "unsafe":
            vrow = rev.row()
            vrow.alert = True
            vrow.label(text=wm.assetdoctor_dep_verdict_text, icon="ERROR")
        elif verdict == "safe":
            rev.label(text=wm.assetdoctor_dep_verdict_text, icon="CHECKMARK")
        elif verdict == "not_scanned":
            vrow = rev.row()
            vrow.alert = True
            vrow.label(text=wm.assetdoctor_dep_verdict_text, icon="ERROR")

        # Phase 3 path fixes are TWO independent jobs (user, 2026-06-21):
        #  (1) relink broken/missing library links — per-link + pick-a-file, so you
        #      can fix one specific link (e.g. a broken material library);
        #  (2) normalize the paths of libraries that already resolve.
        links = layout.box().column(align=True)
        links.label(text="Broken links & missing data-blocks", icon="LIBRARY_DATA_BROKEN")
        # A broken LINK is a whole library .blend that can't be found; a missing
        # DATA-BLOCK is one linked material/object that didn't resolve (often because
        # a link is broken). "Find All Missing" runs both.
        brow = links.row(align=True)
        brow.operator("assetdoctor.scan_broken_links", text="Find Broken Links",
                      icon="LIBRARY_DATA_BROKEN")
        brow.operator("assetdoctor.scan_missing_datablocks", text="Find Missing Data-blocks",
                      icon="LIBRARY_DATA_OVERRIDE")
        links.operator("assetdoctor.scan_all_missing", text="Find All Missing", icon="VIEWZOOM")
        if len(wm.assetdoctor_broken_libs):
            links.template_list(
                "ASSETDOCTOR_UL_broken_libs", "brokenlibs",
                wm, "assetdoctor_broken_libs",
                wm, "assetdoctor_broken_index", rows=4)
            links.operator("assetdoctor.relink_selected",
                           text="Relink Selected (Creates Backup)", icon="FILE_REFRESH")

        # Batch C #2: reconnect missing data-blocks to a real datablock in a chosen
        # source .blend (separate from the broken-LIBRARY-link relinker above — a
        # missing data-block's library can resolve fine; the block itself was just
        # renamed/removed at the source).
        self._draw_reconnect(context, layout, wm)

        # Examine Library: proactively retarget AWAY from a chosen WORKING library
        # (e.g. a shared bundle causing circular references) — distinct from the
        # reconnect box above, which only triggers on BROKEN placeholders.
        self._draw_examine_library(context, layout, wm)

        norm = layout.box().column(align=True)
        norm.label(text="Path normalization", icon="FILE_REFRESH")
        nr = norm.row(align=True)
        nr.operator("assetdoctor.normalize_library_paths", text="Check").apply = False
        nr.operator("assetdoctor.normalize_library_paths",
                    text="Normalize (Creates Backup)", icon="CHECKMARK").apply = True

        # F6: missing image textures (the magenta). Everything lists inline here —
        # header summary, then collapsible material/folder categories with per-file
        # rows — so no separate report is needed. The three relink paths share one
        # "stage a target → Relink Selected applies" model:
        #   • Search a folder (recursive) — stage matches for ALL missing textures
        #   • category folder button      — stage matches for one group
        #   • per-file file button        — pick one file
        self._draw_missing_textures(context, layout, wm)

        # F6 Layer 2: merge content-identical .NNN duplicate image datablocks
        # (verified by dimensions + hash). Redesigned to mirror the Missing section:
        # collapsible material groups, a per-family keeper dropdown, inline summary.
        self._draw_duplicate_textures(context, layout, wm)

        # Which F7 reports exist; a small selector when more than one. The Reports
        # area always gets its own header so a lone report isn't mistaken for part of
        # the section above it (user, 2026-06-23).
        layout.separator()
        layout.label(text="Reports", icon="PRESET")
        present = [(k, lbl) for k, lbl in self._F7_FEATURES if getattr(wm, data_prop(k), "")]
        if not present:
            layout.label(text="Run a scan or analysis to see results.", icon="INFO")
            return

        active = active_feature(wm)
        if active not in dict(present):
            active = present[0][0]
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
            titlerow = layout.row(align=True)
            titlerow.label(text=report.title, icon="PRESET")
        else:
            titlerow = layout.row(align=True)
        # Expand/Collapse All — deep trees (e.g. the File Map) are tedious to open
        # one row at a time.
        titlerow.alignment = "RIGHT"
        ea = titlerow.operator("assetdoctor.report_expand_all", text="", icon="ZOOM_IN")
        ea.feature, ea.prop, ea.expand = active, exp_prop(active), True
        ca = titlerow.operator("assetdoctor.report_expand_all", text="", icon="ZOOM_OUT")
        ca.feature, ca.prop, ca.expand = active, exp_prop(active), False
        layout.template_list(
            "ASSETDOCTOR_UL_tree", "f7report",
            wm, "assetdoctor_report_rows",
            wm, "assetdoctor_report_index",
            rows=14, sort_lock=True,
        )

    def _draw_missing_textures(self, context, layout, wm):
        """The unified Missing Textures section: a header summary, then collapsible
        material/folder categories whose members are per-file rows. All three relink
        paths STAGE a target (folder-search / category-folder / per-file pick); the
        single Relink Selected then applies. Replaces the old flat list + report."""
        n_missing = len(wm.assetdoctor_broken_imgs)
        scanned = wm.assetdoctor_tex_scanned
        found = max(wm.assetdoctor_tex_initial_missing - n_missing, 0)
        # "matched" = still-missing textures that already have a staged target file
        # (auto-found, group-pointed, picked, or an accepted proposal) ready to relink.
        matched = sum(1 for it in wm.assetdoctor_broken_imgs if it.target)
        narrow = bool(context.region) and context.region.width < 320

        tex = layout.box().column(align=True)
        # Header summary (the visible result — no separate report needed). Before a
        # scan: just the title; after: missing + how many are matched (staged) +
        # how many were already relinked. Briefer on a narrow panel.
        title = "Missing Materials/Textures"
        if not scanned:
            head = title
        elif n_missing == 0:
            head = f"{title} — none missing" + (f" ({found} relinked)" if found else "")
        elif narrow:
            head = f"Missing — {n_missing}✗"
            if matched:
                head += f" {matched}⇒"
            if found:
                head += f" {found}✓"
        else:
            bits = [f"{n_missing} missing"]
            if matched:
                bits.append(f"{matched} matched")
            if found:
                bits.append(f"{found} relinked")
            head = f"{title} — " + ", ".join(bits)
        tex.label(text=head, icon="IMAGE_DATA")
        tex.operator("assetdoctor.scan_broken_textures", text="List Missing Textures",
                     icon="VIEWZOOM")
        if not (scanned and n_missing):
            return

        # Recursive staged search over ALL missing textures (between List and the list).
        # Exact-basename first; the fuzzy matcher is the FALLBACK for vendor-renamed
        # files (proposals land in the Possible Matches sub-section below).
        srow = tex.row(align=True)
        srow.operator("assetdoctor.search_textures_folder",
                      text="Search a Folder (Recursive)…", icon="FILEBROWSER")
        srow.operator("assetdoctor.suggest_fuzzy_matches",
                      text="Suggest Matches…", icon="ZOOM_SELECTED")
        # B4 eyedropper: borrow a WORKING material's existing textures as substitute
        # candidates for the missing ones (matched by name → staged as Possible
        # Matches). The picker is the standard material datablock field + eyedropper.
        tex.label(text="Substitute from a material's textures:", icon="EYEDROPPER")
        mrow = tex.row(align=True)
        mrow.prop(wm, "assetdoctor_tex_source_material", text="")
        mrow.operator("assetdoctor.suggest_from_material", text="Suggest",
                      icon="ZOOM_SELECTED")
        # …or borrow the texture files another .blend references (offline BAT harvest).
        tex.operator("assetdoctor.suggest_from_blend",
                     text="Substitute from Another .blend…", icon="FILE_BLEND")
        tex.separator()
        hrow = tex.row(align=True)
        hrow.label(text="Missing Textures", icon="IMAGE_DATA")
        hrow.operator("assetdoctor.relink_textures_selected", text="Relink Selected",
                      icon="FILE_REFRESH")

        # Group by MATERIAL only (the folder view was dropped — user, 2026-06-22).
        mode = "MATERIAL"
        expanded = set(filter(None, wm.assetdoctor_tex_expanded.split("\n")))
        # Sentinel for items with no folder/material (no group button). NOT "\x00" —
        # a real bug: Blender's StringProperty round-trips through a C string, which
        # truncates at the first NUL byte, so storing a lone "\x00" in
        # assetdoctor_tex_expanded silently came back empty and the "(no material)"
        # triangle could never stay expanded.
        UNGROUPED = "\x02"
        groups: dict[str, list] = {}
        order: list[str] = []
        for idx, item in enumerate(wm.assetdoctor_broken_imgs):
            raw = (item.group if mode == "DIR" else item.material) or UNGROUPED
            if raw not in groups:
                groups[raw] = []
                order.append(raw)
            groups[raw].append((idx, item))

        for raw in sorted(order):
            members = groups[raw]
            total = len(members)
            matched = sum(1 for _i, it in members if it.target)
            if raw == UNGROUPED:
                disp = "(no material)" if mode == "MATERIAL" else "(no folder)"
            else:
                disp = (os.path.basename(raw.rstrip("/")) or raw) if mode == "DIR" else raw
            is_exp = raw in expanded
            crow = tex.row(align=True)
            crow.operator("assetdoctor.tex_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = raw
            label = f"{disp}  ({matched} of {total} matched)" if matched else f"{disp}  ({total})"
            crow.label(text=label,
                       icon="CHECKMARK" if matched and matched == total else
                       ("FILE_FOLDER" if mode == "DIR" else "MATERIAL"))
            # Category-level "point at a folder" (stages targets for the whole group).
            if raw != UNGROUPED:
                cop = crow.operator("assetdoctor.point_group_at_folder", text="",
                                    icon="FILE_FOLDER")
                cop.group_key = raw
                cop.by = mode
            if not is_exp:
                continue
            # Individual files: checkbox + name + staged target + per-file file picker.
            for idx, item in members:
                frow = tex.row(align=True)
                frow.separator(factor=2.0)
                frow.prop(item, "selected", text="")
                frow.label(text=item.name, icon="IMAGE_DATA")
                tgt = frow.row()
                tgt.alignment = "RIGHT"
                if item.target:
                    tgt.label(text=os.path.basename(item.target) or item.target, icon="CHECKMARK")
                else:
                    tgt.label(text="no match", icon="QUESTION")
                frow.operator("assetdoctor.relink_pick_texture", text="",
                              icon="FILEBROWSER").index = idx

        self._draw_possible_matches(context, tex, wm)

    # Confidence band -> (icon, short label, rank). Higher rank sorts to the top.
    _CONF = {"high": ("CHECKMARK", "high", 2),
             "medium": ("QUESTION", "med", 1),
             "low": ("DOT", "low", 0)}

    # Below this name-token overlap, a duplicate family's material looks mis-attributed
    # (e.g. a lightBlue texture under a brown material) → flag it + offer the eyedropper.
    _DUP_MISMATCH_AFFINITY = 0.5

    def _draw_possible_matches(self, context, tex, wm):
        """F6 step 4 — the FUZZY proposals (a vendor-renamed file the exact search
        couldn't place). A second list grouped by material, COLLAPSIBLE and collapsed
        by default (so a long Suggest-Matches result doesn't bury the panel), with
        materials ordered by their best confidence (high first). Accept one row, a
        whole material, or all; accepting moves the proposal into the Missing Textures
        list above (ticked)."""
        proposals = [(idx, item) for idx, item in enumerate(wm.assetdoctor_broken_imgs)
                     if item.proposal and not item.target]
        if not proposals:
            return

        tex.separator()
        hrow = tex.row(align=True)
        hrow.label(text=f"Possible Matches — {len(proposals)}", icon="ZOOM_SELECTED")
        hrow.operator("assetdoctor.accept_all_matches", text="Accept All", icon="CHECKMARK")
        tex.label(text="Name-similarity guesses — review before accepting.", icon="INFO")

        # Category keys are namespaced ("\x01" + material) so they don't collide with
        # the Missing list's material keys in the shared expanded-set.
        PM = "\x01"
        expanded = set(filter(None, wm.assetdoctor_tex_expanded.split("\n")))

        groups: dict[str, list] = {}
        for idx, item in proposals:
            groups.setdefault(item.material or "(no material)", []).append((idx, item))

        def conf_rank(it):
            return self._CONF.get(it.proposal_confidence, ("DOT", "?", 0))[2]

        def cat_rank(members):
            return max(conf_rank(it) for _i, it in members)

        # Materials ordered by best confidence (high→low), then name.
        for key in sorted(groups, key=lambda k: (-cat_rank(groups[k]), k.lower())):
            members = sorted(groups[key], key=lambda pair: -conf_rank(pair[1]))
            ckey = PM + key
            is_exp = ckey in expanded
            best_lbl = self._CONF.get(
                {2: "high", 1: "medium", 0: "low"}[cat_rank(members)], ("", "?", 0))[1]
            crow = tex.row(align=True)
            crow.operator("assetdoctor.tex_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = ckey
            crow.label(text=f"{key}  ({len(members)}, {best_lbl})", icon="MATERIAL")
            # Material-level accept (the whole rolled-up group) — CHECKMARK marks the
            # group action, distinct from the single-row IMPORT below.
            crow.operator("assetdoctor.accept_material_matches", text="",
                          icon="CHECKMARK").material = key
            if not is_exp:
                continue
            for idx, item in members:
                frow = tex.row(align=True)
                frow.separator(factor=2.0)
                frow.label(text=item.name, icon="IMAGE_DATA")
                prop = frow.row()
                prop.alignment = "RIGHT"
                icon, conf, _r = self._CONF.get(item.proposal_confidence, ("DOT", "?", 0))
                tag = f"{conf}, diff res" if item.proposal_res_mismatch else conf
                prop.label(text=f"{os.path.basename(item.proposal)}  ({tag})", icon=icon)
                frow.operator("assetdoctor.accept_match", text="",
                              icon="IMPORT").index = idx

    # Reconnect confidence -> (icon, short label). "none" shows neither — the row
    # just offers the source's full candidate list with no particular guess.
    _RECONNECT_CONF = {
        "exact": ("CHECKMARK", "exact"),
        "numbered": ("FILE_REFRESH", "renamed"),
        "fuzzy": ("QUESTION", "fuzzy"),
        "none": ("BLANK1", ""),
    }

    def _draw_datablock_dups(self, context, layout, wm):
        """Batch C #3 — generic Duplicate Data-blocks: find .NNN families across
        Objects/Actions/Node Groups/etc. (Materials/Meshes/Images keep their own
        dedicated tools), group by KIND, pick a keeper per family, Merge Selected.
        Mirrors the Duplicate Materials/Textures section's shape."""
        families = wm.assetdoctor_datablock_families
        scanned = wm.assetdoctor_datablock_scanned
        removable = wm.assetdoctor_datablock_removable
        conflicts = wm.assetdoctor_datablock_conflicts

        box = layout.box().column(align=True)
        if not scanned:
            head = "Duplicate Data-blocks"
        elif not len(families) and not conflicts:
            head = "Duplicate Data-blocks — none found"
        else:
            kinds = len({row.kind for row in families})
            bits = [f"{kinds} kind(s)", f"{removable} removable"]
            if conflicts:
                bits.append(f"{conflicts} differing/unverified")
            head = "Duplicate Data-blocks — " + ", ".join(bits)
        box.label(text=head, icon="LIBRARY_DATA_OVERRIDE")
        box.label(text="Objects, Actions, Node Groups, etc. — Materials/Meshes/Images "
                  "have their own dedup tools.", icon="INFO")

        brow = box.row(align=True)
        brow.operator("assetdoctor.scan_datablock_dups", text="Find Duplicates", icon="VIEWZOOM")
        if scanned and len(families):
            brow.operator("assetdoctor.merge_datablock_selected",
                          text="Merge Selected (Backup)", icon="AREA_JOIN")
        if not (scanned and (len(families) or conflicts)):
            return

        expanded = set(filter(None, wm.assetdoctor_datablock_expanded.split("\n")))
        groups: dict[str, list] = {}
        for row in families:
            groups.setdefault(row.kind, []).append(row)

        for kind in sorted(groups, key=str.lower):
            members = groups[kind]
            removable_here = sum(r.removable for r in members)
            is_exp = kind in expanded
            crow = box.row(align=True)
            crow.operator("assetdoctor.datablock_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = kind
            crow.label(text=f"{kind}  ({len(members)} family, −{removable_here})",
                      icon="LIBRARY_DATA_OVERRIDE")
            if not is_exp:
                continue
            for row in members:
                frow = box.row(align=True)
                frow.separator(factor=2.0)
                frow.prop(row, "selected", text="")
                base = row.name.split(":", 1)[-1]
                frow.label(text=f"{base}  (−{row.removable})", icon="LIBRARY_DATA_OVERRIDE")
                keep = frow.row()
                keep.alignment = "RIGHT"
                keep.label(text="keep", icon="PINNED")
                keep.prop(row, "keeper", text="")

        conflict_lines = [ln for ln in wm.assetdoctor_datablock_conflicts_text.split("\n") if ln]
        if conflict_lines:
            ckey = "\x03conflicts"
            is_exp = ckey in expanded
            crow = box.row(align=True)
            crow.operator("assetdoctor.datablock_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = ckey
            crow.label(text=f"Different content / unverified — kept separate ({len(conflict_lines)})",
                      icon="QUESTION")
            if is_exp:
                for ln in conflict_lines:
                    r = box.row(align=True)
                    r.separator(factor=2.0)
                    r.label(text=ln, icon="DOT")

    def _draw_reconnect(self, context, layout, wm):
        """Batch C #2 — reconnect missing data-blocks. Rows group by their broken/
        renamed source LIBRARY (the natural unit — one library's blocks usually all
        need the same fix); a group-level file picker peeks a chosen source .blend
        (never loads it) and suggests the closest name per row (core.reconnect);
        Reconnect Selected links the ticked rows in and user_remaps the placeholders.
        Mirrors the Duplicate Materials/Textures section's grouped shape."""
        rows = wm.assetdoctor_missing_blocks
        scanned = wm.assetdoctor_missing_scanned

        box = layout.box().column(align=True)
        libs = len({r.library for r in rows})
        staged = sum(1 for r in rows if r.selected and r.target)
        if not scanned:
            head = "Datablock Reconnect"
        elif not len(rows):
            head = "Datablock Reconnect — none found"
        else:
            head = f"Datablock Reconnect — {len(rows)} missing, {libs} group(s), {staged} staged"
        box.label(text=head, icon="LIBRARY_DATA_OVERRIDE")

        brow = box.row(align=True)
        brow.operator("assetdoctor.scan_reconnect_targets",
                     text="Find Reconnectable Data-blocks", icon="VIEWZOOM")
        if scanned and len(rows):
            brow.operator("assetdoctor.reconnect_selected",
                          text="Reconnect Selected (Backup)", icon="LINKED")
        if not (scanned and len(rows)):
            return

        expanded = set(filter(None, wm.assetdoctor_missing_expanded.split("\n")))
        groups: dict[str, list] = {}
        order: list[str] = []
        for item in rows:
            if item.library not in groups:
                groups[item.library] = []
                order.append(item.library)
            groups[item.library].append(item)

        for library in sorted(order, key=lambda lib: (-len(groups[lib]), lib.lower())):
            members = groups[library]
            matched = sum(1 for m in members if m.confidence != "none")
            is_exp = library in expanded
            crow = box.row(align=True)
            crow.operator("assetdoctor.reconnect_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = library
            disp = library or "(unknown library)"
            label = (f"{disp}  ({matched} of {len(members)} suggested)" if matched
                     else f"{disp}  ({len(members)})")
            crow.label(text=label, icon="LIBRARY_DATA_BROKEN")
            pick = crow.operator("assetdoctor.reconnect_pick_source", text="",
                                 icon="FILEBROWSER")
            pick.library = library
            if not is_exp:
                continue
            source = members[0].source_blend
            srow = box.row(align=True)
            srow.separator(factor=2.0)
            if source:
                srow.label(text=os.path.basename(source), icon="FILE_BLEND")
            else:
                srow.label(text="no source picked yet — click the folder icon above",
                          icon="QUESTION")
            for item in members:
                frow = box.row(align=True)
                frow.separator(factor=2.0)
                frow.prop(item, "selected", text="")
                frow.label(text=f"{item.kind}: {item.name}", icon="LIBRARY_DATA_BROKEN")
                icon, conf_label = self._RECONNECT_CONF.get(item.confidence, ("BLANK1", ""))
                if conf_label:
                    cf = frow.row()
                    cf.alignment = "RIGHT"
                    cf.label(text=conf_label, icon=icon)
                frow.prop(item, "target", text="")

    def _draw_examine_library(self, context, layout, wm):
        """Examine Library: list everything the current file links from a chosen
        (working) library and offer to re-source it from memory first — local,
        then another already-loaded library — falling back to Make Local or a
        per-row manual file+item pick. Grouped by KIND, mirrors the Duplicate
        Data-blocks section's shape."""
        rows = wm.assetdoctor_examine_rows
        scanned = wm.assetdoctor_examine_scanned

        box = layout.box().column(align=True)
        box.label(text="Examine Library", icon="LIBRARY_DATA_DIRECT")
        box.label(text="Retarget everything a library provides to your local file or "
                  "another library (e.g. to break a circular reference).", icon="INFO")
        pick = box.row(align=True)
        pick.prop_search(wm, "assetdoctor_examine_library_pick", bpy.data, "libraries", text="")
        pick.operator("assetdoctor.examine_library", text="Examine", icon="VIEWZOOM")

        if scanned and len(rows):
            staged = sum(1 for r in rows if r.selected)
            suggested = sum(1 for r in rows if r.suggested_kind != "none")
            box.label(text=f"{len(rows)} data-block(s) from {wm.assetdoctor_examine_library} — "
                      f"{suggested} in-memory match(es), {staged} staged",
                      icon="LIBRARY_DATA_OVERRIDE")
            box.operator("assetdoctor.examine_apply_selected",
                         text="Apply Selected (Backup)", icon="LINKED")
        elif scanned:
            box.label(text="✓ Nothing currently links from that library", icon="CHECKMARK")
        if not (scanned and len(rows)):
            return

        expanded = set(filter(None, wm.assetdoctor_examine_expanded.split("\n")))
        groups: dict[str, list] = {}
        for idx, item in enumerate(rows):
            groups.setdefault(item.kind, []).append((idx, item))

        for kind in sorted(groups, key=str.lower):
            members = groups[kind]
            is_exp = kind in expanded
            crow = box.row(align=True)
            crow.operator("assetdoctor.examine_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = kind
            crow.label(text=f"{kind}  ({len(members)})", icon="LIBRARY_DATA_DIRECT")
            if not is_exp:
                continue
            for idx, item in members:
                frow = box.row(align=True)
                frow.separator(factor=2.0)
                frow.prop(item, "selected", text="")
                frow.label(text=item.name, icon="LIBRARY_DATA_DIRECT")
                if item.make_local:
                    pass  # the Make Local checkbox below already says it all
                elif item.use_suggested and item.suggested_kind == "local":
                    s = frow.row()
                    s.alignment = "RIGHT"
                    s.label(text=f"local: {item.suggested_name}", icon="CHECKMARK")
                elif item.use_suggested and item.suggested_kind == "library":
                    s = frow.row()
                    s.alignment = "RIGHT"
                    s.label(text=f"{os.path.basename(item.suggested_library)}: "
                                f"{item.suggested_name}", icon="CHECKMARK")
                elif item.source_blend:
                    frow.prop(item, "target", text="")
                else:
                    s = frow.row()
                    s.alignment = "RIGHT"
                    s.label(text="no in-memory match", icon="QUESTION")
                frow.prop(item, "make_local", text="", icon="FILE_TICK")
                frow.operator("assetdoctor.examine_pick_source", text="",
                              icon="FILEBROWSER").index = idx

    def _draw_duplicate_textures(self, context, layout, wm):
        """F6 Layer 2 — the redesigned Duplicate Materials/Textures section: an inline
        summary header, top Find/Merge/Export, then collapsible material groups whose
        rows are the .NNN families, each with an include checkbox + a keeper dropdown
        (pick which datablock survives). Mirrors the Missing section; no separate
        report (it's still stashed for the Export button)."""
        scanned = wm.assetdoctor_dup_scanned
        families = wm.assetdoctor_dup_families
        narrow = bool(context.region) and context.region.width < 320

        dup = layout.box().column(align=True)
        # Summary header (the visible result). Materials = distinct groups with a
        # merge; Textures redundant = total removable datablocks.
        mats = len({row.material or "(no material)" for row in families})
        removable = wm.assetdoctor_dup_removable
        conflicts = wm.assetdoctor_dup_conflicts
        if not scanned:
            head = "Duplicate Materials/Textures"
        elif not len(families) and not conflicts:
            head = "Duplicate Materials/Textures — none found"
        elif narrow:
            head = f"Duplicates — {mats} mat / {removable} tex"
        else:
            bits = [f"{mats} material(s)", f"{removable} texture(s) redundant"]
            if conflicts:
                bits.append(f"{conflicts} differing")
            head = "Duplicate Materials/Textures — " + ", ".join(bits)
        dup.label(text=head, icon="IMAGE_DATA")

        brow = dup.row(align=True)
        brow.operator("assetdoctor.scan_dup_textures", text="Find .NNN", icon="VIEWZOOM")
        # Layer 3 — deep content-overlap scan (hashes every image; modal w/ progress).
        brow.operator("assetdoctor.scan_content_dups", text="Find Content Dups",
                      icon="ZOOM_ALL")
        if scanned and len(families):
            brow.operator("assetdoctor.merge_dup_selected",
                          text="Merge Selected (Backup)", icon="AREA_JOIN")
            brow.operator("assetdoctor.export_report", text="",
                          icon="EXPORT").feature = "f6dup"
        # F6 Layer 2 (footprint) — resolution variants (1k/2k) are NOT duplicates;
        # standardizing them is lossy, so this is a report-only analysis (independent
        # of the .NNN merge scan). Result opens in the Resolution Variants report below.
        dup.operator("assetdoctor.scan_res_variants",
                     text="Resolution Variants (Footprint, Report)…", icon="FULLSCREEN_ENTER")
        if not (scanned and (len(families) or conflicts)):
            return

        from ..core.imagematch import name_affinity

        def _eff_mat(row):
            return (row.material_override.name if row.material_override
                    else (row.material or "(no material)"))

        def _mismatch(row):
            # An "apparent mismatch" = the (effective) material's name barely overlaps
            # the texture's name, e.g. a lightBlue texture under a brown material.
            eff = _eff_mat(row)
            return eff != "(no material)" and name_affinity(row.name, eff) < self._DUP_MISMATCH_AFFINITY

        expanded = set(filter(None, wm.assetdoctor_dup_expanded.split("\n")))
        groups: dict[str, list] = {}
        for row in families:
            groups.setdefault(_eff_mat(row), []).append(row)

        for key in sorted(groups, key=str.lower):
            members = groups[key]
            removable_here = sum(r.removable for r in members)
            mism = [r for r in members if _mismatch(r)]
            is_exp = key in expanded
            crow = dup.row(align=True)
            crow.operator("assetdoctor.dup_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = key
            # Alert only the label (not the whole row) when some textures here don't
            # look like they belong to this material.
            lab = crow.row()
            lab.alert = bool(mism)
            suffix = f", ⚠{len(mism)} mismatch" if mism else ""
            lab.label(text=f"{key}  ({len(members)} family, −{removable_here}{suffix})",
                      icon="ERROR" if mism else "MATERIAL")
            # Master keeper for the whole material (sets every family's keeper by a
            # policy) — the material-level counterpart to the per-family dropdowns.
            crow.operator("assetdoctor.dup_material_keeper", text="",
                          icon="DOWNARROW_HLT").material = key
            if not is_exp:
                continue
            for row in members:
                bad = _mismatch(row)
                frow = dup.row(align=True)
                frow.separator(factor=2.0)
                frow.prop(row, "selected", text="")
                name = frow.row()
                name.alert = bad
                name.label(text=f"{row.name}  (−{row.removable})",
                           icon="ERROR" if bad else "IMAGE_DATA")
                # Alternate material picker (eyedropper): re-home a mis-attributed
                # family under the correct material. Shown when it looks wrong (or was
                # already overridden). Organizational only — doesn't rewire nodes.
                if bad or row.material_override:
                    frow.prop(row, "material_override", text="")
                keep = frow.row()
                keep.alignment = "RIGHT"
                keep.label(text="keep", icon="PINNED")
                keep.prop(row, "keeper", text="")

        # Families with differing content — shown (collapsible) but never merged.
        conflict_lines = [ln for ln in wm.assetdoctor_dup_conflicts_text.split("\n") if ln]
        if conflict_lines:
            ckey = "\x02conflicts"
            is_exp = ckey in expanded
            crow = dup.row(align=True)
            crow.operator("assetdoctor.dup_category_toggle", text="",
                          icon="TRIA_DOWN" if is_exp else "TRIA_RIGHT", emboss=False).key = ckey
            crow.label(text=f"Different content — kept separate ({len(conflict_lines)})",
                       icon="QUESTION")
            if is_exp:
                for ln in conflict_lines:
                    r = dup.row(align=True)
                    r.separator(factor=2.0)
                    r.label(text=ln, icon="DOT")


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
