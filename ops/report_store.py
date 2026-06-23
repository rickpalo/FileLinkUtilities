"""Persistent per-feature report registry + the operators driving the report UI.

Each feature keeps its OWN report (JSON) + expanded-keys on the WindowManager, so
a Materials report survives a later Geometry scan; the Report panel has a selector
to switch between whichever reports exist. Plus operators for expand/collapse,
select-the-datablock (with the agreed non-intrusive behaviour), row labels (which
carry the full text as a tooltip), clear, and export.
"""

import bpy

from ..core.report import Report
from ..core.tree import (
    all_keys,
    flatten_visible,
    nodes_from_json,
    nodes_to_json,
    report_to_tree,
    top_level_keys,
)

# (key, label) for each feature that produces a report. F5 resource is separate.
FEATURES = [
    ("f1", "Link Map"),
    ("f2", "Make Local"),
    ("f3", "Materials"),
    ("f4", "Orphans"),
    ("geo", "Geometry"),
    ("f7", "Dependencies"),
    ("f7live", "Overrides & Dups"),
    ("f7miss", "Missing Data-blocks"),
    ("f7rev", "Safe to Delete?"),
    ("f7links", "Broken Links"),
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
        item.guide = r.guide
        item.prop = prop
        if r.ref:
            item.ref_type = r.ref.get("type", "")
            item.ref_name = r.ref.get("name", "")


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
    """Rebuild whichever collection a toggle on ``prop`` affects."""
    if prop == RESOURCE_EXP_PROP:
        rebuild_resource_rows(wm)
    else:
        rebuild_report_rows(wm)


def _index_prop_for(prop: str) -> str:
    return "assetdoctor_resource_index" if prop == RESOURCE_EXP_PROP else "assetdoctor_report_index"


def focus_row(wm, prop: str, key: str) -> None:
    """Point the list's active index at the row identified by ``key`` (after a
    rebuild) so Blender's ``template_list`` scrolls to keep it visible. Without
    this, expanding/collapsing a row deep in a long report re-filled the whole
    collection from scratch with no active-index change, so the list appeared to
    jump back to the top instead of staying where you clicked (user, 2026-06-23)."""
    coll = wm.assetdoctor_resource_rows if prop == RESOURCE_EXP_PROP else wm.assetdoctor_report_rows
    for i, item in enumerate(coll):
        if item.key == key and item.prop == prop:
            setattr(wm, _index_prop_for(prop), i)
            return


class ASSETDOCTOR_OT_report_toggle(bpy.types.Operator):
    bl_idname = "assetdoctor.report_toggle"
    bl_label = "Expand/Collapse"
    bl_options = {"INTERNAL"}

    key: bpy.props.StringProperty()  # type: ignore[valid-type]
    prop: bpy.props.StringProperty()  # type: ignore[valid-type]

    def execute(self, context):
        wm = context.window_manager
        keys = get_expanded(wm, self.prop)
        keys.discard(self.key) if self.key in keys else keys.add(self.key)
        set_expanded(wm, keys, self.prop)
        rebuild_rows_for_prop(wm, self.prop)
        focus_row(wm, self.prop, self.key)
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ASSETDOCTOR_OT_report_expand_all(bpy.types.Operator):
    """Expand or collapse every node of the CURRENTLY SHOWN report at once (e.g.
    the F7 File Map can run many levels deep — drilling in one row at a time
    gets tedious)."""

    bl_idname = "assetdoctor.report_expand_all"
    bl_label = "Expand/Collapse All"
    bl_options = {"INTERNAL"}

    feature: bpy.props.StringProperty()  # type: ignore[valid-type]
    prop: bpy.props.StringProperty()  # type: ignore[valid-type]
    expand: bpy.props.BoolProperty(default=True)  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        return "Expand every row" if properties.expand else "Collapse every row"

    def execute(self, context):
        wm = context.window_manager
        raw = getattr(wm, data_prop(self.feature), "")
        if not raw:
            return {"CANCELLED"}
        try:
            if self.feature in TREE_FEATURES:
                nodes = nodes_from_json(raw)
            else:
                nodes = report_to_tree(Report.from_json(raw))
        except Exception:
            return {"CANCELLED"}
        set_expanded(wm, all_keys(nodes) if self.expand else set(), self.prop)
        rebuild_rows_for_prop(wm, self.prop)
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ASSETDOCTOR_OT_report_select(bpy.types.Operator):
    bl_idname = "assetdoctor.report_select"
    bl_label = "Show Report"
    bl_options = {"INTERNAL"}

    feature: bpy.props.StringProperty()  # type: ignore[valid-type]

    @classmethod
    def description(cls, context, properties):
        label = dict(FEATURES).get(properties.feature, properties.feature)
        return f"Show the {label} report"

    def execute(self, context):
        wm = context.window_manager
        wm.assetdoctor_active_report = self.feature
        rebuild_report_rows(wm)
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}


class ASSETDOCTOR_OT_report_clear(bpy.types.Operator):
    bl_idname = "assetdoctor.report_clear"
    bl_label = "Clear Report"
    bl_description = "Clear the report currently shown"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        wm = context.window_manager
        active = active_feature(wm)
        if active:
            setattr(wm, data_prop(active), "")
            setattr(wm, exp_prop(active), "")
        remaining = available_features(wm)
        wm.assetdoctor_active_report = remaining[0][0] if remaining else ""
        rebuild_report_rows(wm)
        if context.area:
            context.area.tag_redraw()
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
        elif self.ref_type:
            bpy.ops.assetdoctor.select_datablock(type=self.ref_type, name=self.ref_name)
        return {"FINISHED"}


def _reveal_in_outliner(context) -> None:
    """Best-effort: frame + expand the active object's hierarchy in an open
    Outliner, the same as typing its name there. ``outliner.show_active`` needs
    an Outliner area/region in the override context, which this panel's own
    Properties-editor context doesn't have — find one if the user has it open."""
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
            return


class ASSETDOCTOR_OT_select_datablock(bpy.types.Operator):
    bl_idname = "assetdoctor.select_datablock"
    bl_label = "Select"
    bl_description = "Select the object(s) this finding refers to (the Outliner follows the active object)"
    bl_options = {"INTERNAL"}

    type: bpy.props.StringProperty()  # type: ignore[valid-type]
    name: bpy.props.StringProperty()  # type: ignore[valid-type]

    def execute(self, context):
        targets = self._find_objects(context)
        if not targets:
            # Non-intrusive: don't open/rearrange editors; hint where to look.
            self.report(
                {"INFO"},
                f"{self.type}/{self.name} has no users in the scene — view it via "
                "Outliner → Display Mode → Blender File / Orphan Data",
            )
            return {"CANCELLED"}

        for obj in context.view_layer.objects:
            obj.select_set(False)
        for obj in targets:
            obj.select_set(True)
        context.view_layer.objects.active = targets[0]

        # For a material, also highlight its slot on the active object.
        if self.type == "Material":
            mat = bpy.data.materials.get(self.name)
            for i, slot in enumerate(targets[0].material_slots):
                if slot.material == mat:
                    targets[0].active_material_index = i
                    break

        _reveal_in_outliner(context)
        self.report({"INFO"}, f"Selected {len(targets)} object(s) using {self.name}")
        return {"FINISHED"}

    def _resolve_target(self):
        """Find the ID datablock matching this finding's type-name + name."""
        for prop in bpy.data.bl_rna.properties:
            if prop.type != "COLLECTION":
                continue
            coll = getattr(bpy.data, prop.identifier, None)
            if coll is None:
                continue
            try:
                cand = coll.get(self.name)
            except (TypeError, AttributeError):
                continue
            if cand is not None and type(cand).__name__ == self.type:
                return cand
        return None

    def _find_objects(self, context):
        """Scene objects that use the datablock, directly or transitively.

        e.g. an Image used by a Material used by a Mesh used by an Object resolves
        to that Object. ``bpy.data.user_map()`` maps each id -> the set of ids that
        USE it, so we walk it forward from the target up to the using objects."""
        scene_objs = set(context.view_layer.objects)
        target = self._resolve_target()
        if target is None:
            return []
        if isinstance(target, bpy.types.Object):
            return [target] if target in scene_objs else []

        user_map = bpy.data.user_map()
        found, seen, stack = [], set(), [target]
        while stack:
            cur = stack.pop()
            for user in user_map.get(cur, ()):
                if user in seen:
                    continue
                seen.add(user)
                if isinstance(user, bpy.types.Object):
                    if user in scene_objs and user not in found:
                        found.append(user)
                else:
                    stack.append(user)
        return found


def _tree_to_text(nodes, title: str) -> str:
    """Fully-expanded indented text dump of a tree (for export/print)."""
    lines = [title, "=" * len(title), ""]
    for r in flatten_visible(nodes, all_keys(nodes)):
        prefix = "  " * r.indent
        detail = f"   [{r.detail}]" if r.detail else ""
        lines.append(f"{prefix}{r.label}{detail}")
    return "\n".join(lines) + "\n"


class ASSETDOCTOR_OT_export_report(bpy.types.Operator):
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
    filename: bpy.props.StringProperty(default="AssetDoctorReport.txt")  # type: ignore[valid-type]

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

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
