"""Persistent per-feature report registry + the operators driving the report UI.

Each feature keeps its OWN report (JSON) + expanded-keys on the WindowManager, so
a Materials report survives a later Geometry scan; the Report panel has a selector
to switch between whichever reports exist. Plus operators for expand/collapse,
select-the-datablock (with the agreed non-intrusive behaviour), row labels (which
carry the full text as a tooltip), clear, and export.
"""

import os

import bpy

from ..core.report import Report, default_export_filename
from ..core.tree import (
    all_keys,
    flatten_visible,
    nodes_from_json,
    nodes_to_json,
    report_to_tree,
    top_level_keys,
)
from .pickers import FilePickerMixin
from .progress import set_result

# (key, label) for each feature that produces a report. F5 resource is separate.
FEATURES = [
    ("f1", "Link Map"),
    ("f2", "Make Local"),
    ("f3", "Materials"),
    ("f4", "Orphans"),
    ("geo", "Geometry"),
    ("f7", "Dependencies"),
    ("f7chain", "Link Chain Analysis"),
    ("f7flatten", "Flatten Plan"),
    ("f7live", "Overrides"),
    ("f7rev", "Safe to Delete?"),
    ("f7links", "Broken Library Links"),
    ("f7fix", "Path Fixes"),
    ("f6tex", "Missing Textures"),
    ("f6dup", "Duplicate Textures"),
    ("f6res", "Resolution Variants"),
    ("f9", "Dry-Run Render Warnings"),
]


# Features whose stored JSON is a TreeNode list (not a flat Report). The F7
# dependency view needs arbitrary hierarchy (the file map), which Report can't hold.
TREE_FEATURES = {"f7"}


def data_prop(feature: str) -> str:
    return f"assetdoctor_rep_{feature}"


def exp_prop(feature: str) -> str:
    return f"assetdoctor_repx_{feature}"


def stash_report(context, report, feature: str, set_active: bool = True) -> None:
    """Persist a feature's report. Categories start COLLAPSED so a large report
    (hundreds of findings) doesn't draw as one giant column — the N-panel doesn't
    virtualize manual rows, which can leave rows blank. The user expands one
    category at a time.

    ``set_active=False`` for features (e.g. f6dup) whose report is only kept
    around for the inline Export button — the real UI for that feature lives
    elsewhere (the Duplicate Materials/Textures section), so stashing it must
    not steal the report selector away from whatever the user is looking at."""
    wm = context.window_manager
    setattr(wm, data_prop(feature), report.to_json())
    setattr(wm, exp_prop(feature), "")  # collapsed
    if set_active:
        wm.assetdoctor_active_report = feature
    rebuild_report_rows(wm)


def stash_tree(context, nodes, feature: str) -> None:
    """Persist a feature whose data is a TreeNode tree (vs a flat Report). Opens
    the top-level sections (e.g. Summary / File map / Errors) by default."""
    wm = context.window_manager
    setattr(wm, data_prop(feature), nodes_to_json(nodes))
    setattr(wm, exp_prop(feature), "\n".join(top_level_keys(nodes)))
    wm.assetdoctor_active_report = feature
    rebuild_report_rows(wm)


def available_features(wm):
    return [(k, label) for k, label in FEATURES if getattr(wm, data_prop(k))]


def active_feature(wm) -> str:
    a = wm.assetdoctor_active_report
    if a and getattr(wm, data_prop(a), ""):
        return a
    avail = available_features(wm)
    return avail[0][0] if avail else ""


def get_expanded(wm, prop: str) -> set[str]:
    raw = getattr(wm, prop)
    return set(raw.split("\n")) if raw else set()


def set_expanded(wm, keys: set[str], prop: str) -> None:
    setattr(wm, prop, "\n".join(sorted(keys)))


# --- UIList materialisation -------------------------------------------------
# The Report/Resource panels draw a UIList over a CollectionProperty of rows
# (virtualized + scrollable, so large reports no longer blank out). The JSON on
# the WindowManager stays the source of truth; these helpers re-flatten it into
# the collection whenever the shown report or its expansion changes.

RESOURCE_EXP_PROP = "assetdoctor_resource_expanded"


def _fill_rows(coll, rows, prop: str) -> None:
    coll.clear()
    for r in rows:
        item = coll.add()
        item.name = r.label  # so the UIList's built-in search box filters on it
        item.indent = r.indent
        item.key = r.key
        item.label = r.label
        item.severity = r.severity
        item.has_children = r.has_children
        item.expanded = r.expanded
        item.detail = r.detail
        item.icon = r.icon
        item.prop = prop
        item.ram = r.ram
        item.vram = r.vram
        item.disk = r.disk
        if r.ref:
            item.ref_type = r.ref.get("type", "")
            item.ref_name = r.ref.get("name", "")
        if r.popup:
            item.popup_parent = r.popup.get("parent", "")
            item.popup_basename = r.popup.get("basename", "")


def rebuild_report_rows(wm) -> None:
    """Refill ``assetdoctor_report_rows`` from the active feature's report JSON."""
    coll = wm.assetdoctor_report_rows
    active = active_feature(wm)
    if not active:
        coll.clear()
        return
    raw = getattr(wm, data_prop(active), "")
    try:
        if active in TREE_FEATURES:
            nodes = nodes_from_json(raw)
        else:
            nodes = report_to_tree(Report.from_json(raw))
    except Exception:
        coll.clear()
        return
    rows = flatten_visible(nodes, get_expanded(wm, exp_prop(active)))
    _fill_rows(coll, rows, exp_prop(active))


def rebuild_resource_rows(wm) -> None:
    """Refill ``assetdoctor_resource_rows`` from the resource tree JSON."""
    coll = wm.assetdoctor_resource_rows
    raw = getattr(wm, "assetdoctor_resource_tree", "")
    if not raw:
        coll.clear()
        return
    try:
        nodes = nodes_from_json(raw)
    except Exception:
        coll.clear()
        return
    rows = flatten_visible(nodes, get_expanded(wm, RESOURCE_EXP_PROP))
    _fill_rows(coll, rows, RESOURCE_EXP_PROP)


def rebuild_rows_for_prop(wm, prop: str) -> None:
    """Rebuild whichever virtualized collection a toggle on ``prop`` affects.

    Only two ``prop`` families are backed by a virtualized ``CollectionProperty``
    today: ``RESOURCE_EXP_PROP`` and any feature's own ``exp_prop`` (always
    ``"assetdoctor_repx_<feature>"``, see ``exp_prop()``) for the Reports tab.
    ``ASSETDOCTOR_OT_row_toggle`` (docs/TODO.md Group 12) is now the ONE toggle
    operator for every grouped section in the addon, not just these two, so an
    unconditional "anything else must be a report feature" ``else`` would be
    wrong — it would silently rebuild the Reports tab's rows (wasted work, and
    liable to clobber the wrong report) every time an unrelated section (e.g.
    Missing Textures) toggles a group. No-op for any other ``prop`` — those
    sections still draw manually and have nothing to rebuild (yet; see Group
    12's phased rollout for sections gaining their own virtualized collection)."""
    if prop == RESOURCE_EXP_PROP:
        rebuild_resource_rows(wm)
    elif prop.startswith("assetdoctor_repx_"):
        rebuild_report_rows(wm)
    elif prop in ("assetdoctor_flatten_expanded", "assetdoctor_flatten_deselected"):
        from .linkchain import rebuild_flatten_picker_rows  # lazy — avoids circular import
        rebuild_flatten_picker_rows(wm)


def _index_prop_for(prop: str) -> str:
    return "assetdoctor_resource_index" if prop == RESOURCE_EXP_PROP else "assetdoctor_report_index"


def focus_row(wm, prop: str, key: str) -> None:
    """Point the list's active index at the row identified by ``key`` (after a
    rebuild) so Blender's ``template_list`` scrolls to keep it visible. Without
    this, expanding/collapsing a row deep in a long report re-filled the whole
    collection from scratch with no active-index change, so the list appeared to
    jump back to the top instead of staying where you clicked (user, 2026-06-23).
    No-op for a ``prop`` that isn't one of the two virtualized collections today
    (every other grouped section still draws manually) — same guard as
    ``rebuild_rows_for_prop``, see there for why a blanket "else" would be wrong
    now that one shared toggle op (below) serves every section."""
    if prop == RESOURCE_EXP_PROP or prop.startswith("assetdoctor_repx_"):
        coll = wm.assetdoctor_resource_rows if prop == RESOURCE_EXP_PROP else wm.assetdoctor_report_rows
        for i, item in enumerate(coll):
            if item.key == key and item.prop == prop:
                setattr(wm, _index_prop_for(prop), i)
                return
    elif prop in ("assetdoctor_flatten_expanded", "assetdoctor_flatten_deselected"):
        for i, item in enumerate(wm.assetdoctor_flatten_picker_rows):
            if item.key == key:
                wm.assetdoctor_flatten_picker_active = i
                return


class ASSETDOCTOR_OT_row_toggle(bpy.types.Operator):
    """The one generic expand/collapse (and, via a differently-named ``prop``,
    select/deselect — see ``ops.linkchain``'s Flatten-candidate groups) toggle
    for every grouped results section in the addon (docs/TODO.md Group 12,
    2026-06-27). Replaces 8 near-identical operator classes that each
    hand-rolled the same "toggle ``key`` in/out of a newline-joined WM
    string-set named ``prop``" logic — one per section, plus this one's own
    two predecessors (``report_toggle``/``toggle_inline_detail``).

    ``prop`` defaults to ``assetdoctor_detail_expanded``, the one shared
    bucket used by every inline Analyze-button disclosure (a node's own key
    already embeds its report's feature tag, so two features' keys never
    collide there); every other section passes its own dedicated ``prop``
    explicitly. ``rebuild_rows_for_prop``/``focus_row`` are no-ops for any
    ``prop`` that isn't (yet) backed by a virtualized row collection — see
    those functions — so this is a pure behavior-preserving merge for the
    ~11 sections still drawn manually; only the Reports tab/Resource Usage
    case (the two ``prop`` families ``report_toggle`` used to serve) gets the
    rebuild+refocus treatment today. Redraws BOTH the area and its region
    (``ASSETDOCTOR_OT_flatten_category_toggle`` added the region redraw
    2026-06-27 as a defensive fix for a reported "drill-down arrows stop
    responding" issue; adopted here for every section, not just Flatten's)."""

    bl_idname = "assetdoctor.row_toggle"
    bl_label = "Expand/Collapse"
    bl_options = {"INTERNAL"}

    key: bpy.props.StringProperty()  # type: ignore[valid-type]
    prop: bpy.props.StringProperty(default="assetdoctor_detail_expanded")  # type: ignore[valid-type]

    def execute(self, context):
        wm = context.window_manager
        keys = get_expanded(wm, self.prop)
        keys.discard(self.key) if self.key in keys else keys.add(self.key)
        set_expanded(wm, keys, self.prop)
        rebuild_rows_for_prop(wm, self.prop)
        focus_row(wm, self.prop, self.key)
        if context.area:
            context.area.tag_redraw()
        if context.region:
            context.region.tag_redraw()
        return {"FINISHED"}


class ASSETDOCTOR_OT_row_label(bpy.types.Operator):
    """A tree row's label as a button: its tooltip is the full text (so long
    paths/messages are readable in the narrow panel), and clicking it does the
    row's natural action (expand/collapse a parent, or select a leaf's datablock)."""

    bl_idname = "assetdoctor.row_label"
    bl_label = "Row"
    bl_options = {"INTERNAL"}

    text: bpy.props.StringProperty()  # full text -> shown as tooltip
    key: bpy.props.StringProperty()
    prop: bpy.props.StringProperty()
    has_children: bpy.props.BoolProperty()
    ref_type: bpy.props.StringProperty()
    ref_name: bpy.props.StringProperty()
    popup_parent: bpy.props.StringProperty()
    popup_basename: bpy.props.StringProperty()

    @classmethod
    def description(cls, context, properties):
        return properties.text or "—"

    def execute(self, context):
        if self.has_children and self.prop:
            wm = context.window_manager
            keys = get_expanded(wm, self.prop)
            keys.discard(self.key) if self.key in keys else keys.add(self.key)
            set_expanded(wm, keys, self.prop)
            rebuild_rows_for_prop(wm, self.prop)
            focus_row(wm, self.prop, self.key)
            if context.area:
                context.area.tag_redraw()
        elif self.popup_parent:
            bpy.ops.assetdoctor.show_linked_from(
                "INVOKE_DEFAULT", parent=self.popup_parent, basename=self.popup_basename)
        elif self.ref_type:
            bpy.ops.assetdoctor.select_datablock(type=self.ref_type, name=self.ref_name)
        return {"FINISHED"}


def _reveal_in_outliner(context, filter_name: str = "") -> None:
    """Best-effort: frame + expand the active object's hierarchy in an open
    Outliner, the same as typing its name there. ``outliner.show_active`` needs
    an Outliner area/region in the override context, which this panel's own
    Properties-editor context doesn't have — find one if the user has it open.

    ``outliner.show_active`` only ever reveals the ACTIVE OBJECT — Blender has
    no public API to scroll-to/highlight an arbitrary non-object ID (a
    Material, an Image) directly, in ANY display mode, including Blend File /
    Orphan Data (user-confirmed 2026-06-24: setting the active material slot
    alone did not focus the material there). ``filter_name``, when given, is
    set as the Outliner's own name filter (``SpaceOutliner.filter_text`` — the
    same search box the header's magnifying-glass icon opens) on every open
    Outliner, narrowing its rows to matches regardless of display mode. This
    DOES mutate persistent Outliner UI state (the filter stays set until
    cleared/replaced) — the deliberate, only-available alternative once
    ``show_active`` alone is confirmed insufficient for a non-object target."""
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "OUTLINER":
                continue
            region = next((r for r in area.regions if r.type == "WINDOW"), None)
            if region is None:
                continue
            try:
                with context.temp_override(window=window, area=area, region=region):
                    bpy.ops.outliner.show_active()
            except Exception:
                pass
            if filter_name:
                try:
                    area.spaces[0].filter_text = filter_name
                except Exception:
                    pass
            return


def resolve_datablock(type_name: str, name: str):
    """Find the ID datablock matching a "Type/Name" ref (generic walk over every
    ``bpy.data`` collection) — shared by click-to-select here and Phase 4's
    flatten-apply (resolving an overridden pointer property's coerced
    "Type/Name" string back to a real datablock)."""
    for prop in bpy.data.bl_rna.properties:
        if prop.type != "COLLECTION":
            continue
        coll = getattr(bpy.data, prop.identifier, None)
        if coll is None:
            continue
        try:
            cand = coll.get(name)
        except (TypeError, AttributeError):
            continue
        if cand is not None and type(cand).__name__ == type_name:
            return cand
    return None


class ASSETDOCTOR_OT_select_datablock(bpy.types.Operator):
    bl_idname = "assetdoctor.select_datablock"
    bl_label = "Select"
    bl_description = "Select the object(s) this finding refers to (the Outliner follows the active object)"
    bl_options = {"INTERNAL"}

    type: bpy.props.StringProperty()  # type: ignore[valid-type]
    name: bpy.props.StringProperty()  # type: ignore[valid-type]

    def execute(self, context):
        targets, materials = self._find_objects(context)
        if not targets:
            # Non-intrusive: don't open/rearrange editors; hint where to look.
            # STICKY (not just a self.report() toast, user feedback 2026-06-25
            # item e) — a transient toast is easy to miss and reads as "the
            # click did nothing" even though this IS the real answer (most
            # duplicate-family members are exactly this: dead weight with no
            # real user). Also covers the case where a real user exists but
            # its collection is excluded from the current view layer, which
            # "has no users in the scene" technically doesn't distinguish.
            msg = (f"{self.type}/{self.name}: no user found in the current view "
                   "layer (it may be unused, or its collection is excluded) — "
                   "check Outliner → Display Mode → Blender File / Orphan Data")
            self.report({"INFO"}, msg)
            set_result(context, msg, ok=False)
            return {"CANCELLED"}

        for obj in context.view_layer.objects:
            obj.select_set(False)
        for obj in targets:
            obj.select_set(True)
        context.view_layer.objects.active = targets[0]

        # Highlight the connecting Material's slot on the active object — covers
        # both a direct Material click AND something deeper (e.g. an Image two
        # hops below the Material it's used in, user report 2026-06-24: clicking a
        # missing texture didn't highlight "the material from whence it came").
        # CONFIRMED (live test, 2026-06-24) that alone doesn't focus the material
        # in the Outliner — show_active is active-OBJECT-only — so for anything
        # that isn't a direct Object click, ALSO narrow the Outliner via its own
        # name filter (the connecting material's name, else the clicked target's
        # own name) so it's findable regardless of display mode.
        filter_name = ""
        if self.type != "Object":
            for i, slot in enumerate(targets[0].material_slots):
                if slot.material in materials:
                    targets[0].active_material_index = i
                    filter_name = slot.material.name
                    break
            if not filter_name:
                filter_name = self.name

        _reveal_in_outliner(context, filter_name)
        tail = f" — Outliner filtered to '{filter_name}'" if filter_name else ""
        self.report({"INFO"}, f"Selected {len(targets)} object(s) using {self.name}{tail}")
        return {"FINISHED"}

    def _resolve_target(self):
        """Find the ID datablock matching this finding's type-name + name."""
        return resolve_datablock(self.type, self.name)

    def _find_objects(self, context):
        """Scene objects that use the datablock, directly or transitively, plus any
        Material(s) found ALONG THE WAY (so a Material slot can be highlighted on
        the resulting active object even when the click started from something
        deeper than a Material — e.g. an Image used by a Material used by an
        Object: ``(objects, materials)``.

        ``bpy.data.user_map()`` maps each id -> the set of ids that USE it, so we
        walk it forward from the target up to the using objects."""
        scene_objs = set(context.view_layer.objects)
        target = self._resolve_target()
        if target is None:
            return [], set()
        if isinstance(target, bpy.types.Object):
            return ([target] if target in scene_objs else []), set()
        materials = {target} if isinstance(target, bpy.types.Material) else set()

        user_map = bpy.data.user_map()
        found, seen, stack = [], set(), [target]
        while stack:
            cur = stack.pop()
            for user in user_map.get(cur, ()):
                if user in seen:
                    continue
                seen.add(user)
                if isinstance(user, bpy.types.Material):
                    materials.add(user)
                if isinstance(user, bpy.types.Object):
                    if user in scene_objs and user not in found:
                        found.append(user)
                else:
                    stack.append(user)
        return found, materials


class ASSETDOCTOR_OT_show_linked_from(bpy.types.Operator):
    """"Show what's linked from here" for an INDIRECT File Map row (item 2,
    2026-06-26): the row's file was never directly linked into the open file
    (only a library-of-a-library), so it has no real ``bpy.data.libraries``
    entry for ``select_datablock`` to find. Reads the PARENT file offline
    instead (the already-built ``core.datablock_links.datablocks_from_library``)
    and lists exactly what it pulls from this row's file, in a transient popup
    -- each entry reuses ``select_datablock`` so a name that DOES happen to
    also be loaded locally is still clickable."""

    bl_idname = "assetdoctor.show_linked_from"
    bl_label = "Show What's Linked From Here"
    bl_description = (
        "This library was never linked directly into the open file (only "
        "through another library), so it has no entry to select. Read the "
        "linking file and list what it actually pulls from here"
    )
    bl_options = {"INTERNAL"}

    parent: bpy.props.StringProperty()  # type: ignore[valid-type]
    basename: bpy.props.StringProperty()  # type: ignore[valid-type]

    def invoke(self, context, event):
        from ..core.datablock_links import datablocks_from_library

        # This is a real, BLOCKING disk read of the parent .blend (BAT block-
        # table scan) — up to ~1 min/file on this project's large production
        # files (see project memory) — with no other progress indication, so
        # a slow read was indistinguishable from "the click did nothing"
        # (docs/TODO.md Group 10 #39). A wait cursor is an OS-level cursor
        # swap, not dependent on a redraw, so it shows immediately even
        # though this whole call happens inside one blocking Python frame.
        context.window.cursor_modal_set("WAIT")
        try:
            self._items = datablocks_from_library(self.parent, self.basename)
        except Exception as exc:
            self.report({"ERROR"}, f"Could not read {os.path.basename(self.parent)}: {exc}")
            return {"CANCELLED"}
        finally:
            context.window.cursor_modal_restore()
        title = f"Linked from {self.basename} (via {os.path.basename(self.parent)})"
        context.window_manager.popup_menu(self._draw, title=title)
        return {"FINISHED"}

    def _draw(self, menu_self, context):
        from ..core.datablock_links import kind_ref

        layout = menu_self.layout
        if not self._items:
            layout.label(text="Nothing found")
            return
        for kind, name in self._items:
            ref = kind_ref(kind, name)
            op = layout.operator("assetdoctor.select_datablock", text=f"{kind}: {name}")
            op.type, op.name = ref["type"], ref["name"]


def _tree_to_text(nodes, title: str) -> str:
    """Fully-expanded indented text dump of a tree (for export/print)."""
    lines = [title, "=" * len(title), ""]
    for r in flatten_visible(nodes, all_keys(nodes)):
        prefix = "  " * r.indent
        detail = f"   [{r.detail}]" if r.detail else ""
        lines.append(f"{prefix}{r.label}{detail}")
    return "\n".join(lines) + "\n"


class ASSETDOCTOR_OT_export_report(FilePickerMixin, bpy.types.Operator):
    bl_idname = "assetdoctor.export_report"
    bl_label = "Export Report"
    bl_description = "Save the report to a text file (for printing or sharing)"

    source: bpy.props.EnumProperty(
        items=[("report", "Report", ""), ("resource", "Resource", "")],
        default="report",
    )  # type: ignore[valid-type]
    # Optional: export THIS feature's report instead of the active one (so an inline
    # section Export button targets its own report regardless of the selector).
    feature: bpy.props.StringProperty(default="")  # type: ignore[valid-type]
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore[valid-type]

    def invoke(self, context, event):
        wm = context.window_manager
        if self.source == "resource":
            label = "Resource Usage"
        else:
            feature = self.feature or active_feature(wm)
            label = dict(FEATURES).get(feature, feature)
        self.filepath = default_export_filename(label)
        return super().invoke(context, event)

    def execute(self, context):
        wm = context.window_manager
        if self.source == "resource":
            raw = wm.assetdoctor_resource_tree
            if not raw:
                self.report({"ERROR"}, "No resource analysis to export")
                return {"CANCELLED"}
            text = _tree_to_text(nodes_from_json(raw), "AssetDoctor — Resource Usage (estimate)")
        else:
            feature = self.feature or active_feature(wm)
            raw = getattr(wm, data_prop(feature), "") if feature else ""
            if not raw:
                self.report({"ERROR"}, "No report to export")
                return {"CANCELLED"}
            if feature in TREE_FEATURES:
                text = _tree_to_text(nodes_from_json(raw), f"AssetDoctor — {feature}")
            elif self.filepath.lower().endswith(".csv"):
                text = Report.from_json(raw).to_csv()
            else:
                report = Report.from_json(raw)
                text = _tree_to_text(report_to_tree(report), report.title)

        try:
            with open(bpy.path.abspath(self.filepath), "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            self.report({"ERROR"}, f"Could not write file: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported report to {self.filepath}")
        return {"FINISHED"}
