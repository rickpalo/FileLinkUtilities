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
    report_to_tree,
)

# (key, label) for each feature that produces a report. F5 resource is separate.
FEATURES = [
    ("f1", "Link Map"),
    ("f2", "Make Local"),
    ("f3", "Materials"),
    ("f4", "Orphans"),
    ("geo", "Geometry"),
]


def data_prop(feature: str) -> str:
    return f"assetdoctor_rep_{feature}"


def exp_prop(feature: str) -> str:
    return f"assetdoctor_repx_{feature}"


def stash_report(context, report, feature: str) -> None:
    """Persist a feature's report. Categories start COLLAPSED so a large report
    (hundreds of findings) doesn't draw as one giant column — the N-panel doesn't
    virtualize manual rows, which can leave rows blank. The user expands one
    category at a time."""
    wm = context.window_manager
    setattr(wm, data_prop(feature), report.to_json())
    setattr(wm, exp_prop(feature), "")  # collapsed
    wm.assetdoctor_active_report = feature


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
        context.window_manager.assetdoctor_active_report = self.feature
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
            if context.area:
                context.area.tag_redraw()
        elif self.ref_type:
            bpy.ops.assetdoctor.select_datablock(type=self.ref_type, name=self.ref_name)
        return {"FINISHED"}


# Datablock type -> bpy.data collection, for select-in-Outliner.
_DATA_COLLECTIONS = {
    "Object": "objects", "Mesh": "meshes", "Curve": "curves",
    "Material": "materials", "Image": "images", "NodeGroup": "node_groups",
    "Armature": "armatures",
}


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

        self.report({"INFO"}, f"Selected {len(targets)} object(s) using {self.name}")
        return {"FINISHED"}

    def _find_objects(self, context):
        scene_objs = list(context.view_layer.objects)
        if self.type == "Object":
            o = bpy.data.objects.get(self.name)
            return [o] if o is not None and o in scene_objs else []
        if self.type == "Material":
            mat = bpy.data.materials.get(self.name)
            if mat is None:
                return []
            return [o for o in scene_objs
                    if any(s.material == mat for s in o.material_slots)]
        coll = _DATA_COLLECTIONS.get(self.type)
        if coll and coll != "objects":
            db = getattr(bpy.data, coll, {}).get(self.name)
            if db is not None:
                return [o for o in scene_objs if o.data == db]
        return []


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
            feature = active_feature(wm)
            raw = getattr(wm, data_prop(feature), "") if feature else ""
            if not raw:
                self.report({"ERROR"}, "No report to export")
                return {"CANCELLED"}
            report = Report.from_json(raw)
            if self.filepath.lower().endswith(".csv"):
                text = report.to_csv()
            else:
                text = _tree_to_text(report_to_tree(report), report.title)

        try:
            with open(bpy.path.abspath(self.filepath), "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            self.report({"ERROR"}, f"Could not write file: {exc}")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported report to {self.filepath}")
        return {"FINISHED"}
