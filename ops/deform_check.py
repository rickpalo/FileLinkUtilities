"""Check Armature Deformation — scan for the "vertex weighted to a non-deform
bone gets dragged wildly out of place once posed" bug (Group 16, 2026-07-09;
see docs/TODO.md for the full live diagnosis on a real production file).
Detection only, per the user's explicit call — this never mutates a mesh or
its vertex groups; it just builds a reviewable, selectable list for a later
fix pass.

Walks every visible mesh object with an enabled Armature modifier bound via
vertex groups, compares each edge's REST length (base mesh.vertices) against
its DEFORMED length (the modifier-evaluated mesh, via the depsgraph) — a
healthy mesh keeps these close (skin/cloth deformation is locally close to
isometric); a vertex weighted to the wrong bone doesn't. One
``bpy.context.evaluated_depsgraph_get()`` call is reused across every object
(each `evaluated_get()` off it is cheap); the expensive part is each
object's own `to_mesh()` + edge-length pass, so this is chunked/modal like
every other whole-file scan in this addon.
"""

from __future__ import annotations

import bpy

from ..core.deform_check import (
    DEFAULT_RATIO_THRESHOLD,
    ObjectDeformSummary,
    build_deform_check_report,
    find_deform_outliers,
)
from .progress import ModalProgressMixin

_CHUNK = 8  # objects between progress yields -- each involves a full to_mesh() eval


def _deform_check_candidates(context):
    """Every mesh object with an ENABLED Armature modifier bound via vertex
    groups (bone envelopes deform differently and aren't this bug's shape;
    a disabled modifier isn't currently doing anything to flag)."""
    out = []
    for obj in context.view_layer.objects:
        if obj.type != 'MESH':
            continue
        for mod in obj.modifiers:
            if (mod.type == 'ARMATURE' and mod.show_viewport and mod.object is not None
                    and mod.use_vertex_groups):
                out.append((obj, mod.object))
                break
    return out


def _edge_lengths(mesh, world_matrix, vertex_coords=None):
    """(edges as (v1,v2) tuples, lengths) for ``mesh``'s edges. ``vertex_coords``
    lets the caller pass pre-computed WORLD-space coords (the evaluated/deformed
    case); without it, uses the mesh's own local ``vertices[i].co`` (the rest
    case — local space is fine there since we only ever compare a ratio between
    two lengths computed the same way, never an absolute cross-object distance)."""
    edges = []
    lengths = []
    coords = vertex_coords
    for e in mesh.edges:
        v1i, v2i = e.vertices[0], e.vertices[1]
        if coords is not None:
            v1, v2 = coords[v1i], coords[v2i]
        else:
            v1, v2 = mesh.vertices[v1i].co, mesh.vertices[v2i].co
        edges.append((v1i, v2i))
        lengths.append((v1 - v2).length)
    return edges, lengths


def _gather_steps(context, ratio_threshold: float):
    """Yields ``(fraction, status)``. Returns a list of ObjectDeformSummary,
    worst-ratio objects first, for objects with at least one flagged vertex."""
    candidates = _deform_check_candidates(context)
    total = len(candidates) or 1
    deps = context.evaluated_depsgraph_get()

    summaries: list[ObjectDeformSummary] = []
    for i, (obj, arm_obj) in enumerate(candidates):
        mesh = obj.data
        edges, rest_lengths = _edge_lengths(mesh, obj.matrix_world)

        obj_eval = obj.evaluated_get(deps)
        mesh_eval = obj_eval.to_mesh()
        try:
            world_coords = [obj.matrix_world @ v.co for v in mesh_eval.vertices]
            _, deformed_lengths = _edge_lengths(mesh_eval, obj.matrix_world, world_coords)
        finally:
            obj_eval.to_mesh_clear()

        # A topology change between rest and evaluated mesh (rare -- e.g. a
        # Boolean/Mask modifier stacked after the Armature one) means the edge
        # lists no longer line up 1:1; skip rather than compare mismatched data.
        if len(edges) == len(deformed_lengths):
            issues = find_deform_outliers(edges, rest_lengths, deformed_lengths,
                                          ratio_threshold=ratio_threshold)
            if issues:
                # Vertex-group WEIGHTS live on the Mesh (mesh.vertices[i].groups);
                # the group NAMES/definitions live on the Object (obj.vertex_groups)
                # -- a fix needs to edit both, so either being linked blocks it.
                locally_fixable = obj.library is None and mesh.library is None
                summaries.append(ObjectDeformSummary(
                    object_name=obj.name, mesh_name=mesh.name,
                    armature_name=arm_obj.name, issues=tuple(issues),
                    is_locally_fixable=locally_fixable))

        if (i + 1) % _CHUNK == 0 or i + 1 == total:
            yield (min(0.95, (i + 1) / total), f"Checking deformation {i + 1}/{total}…")

    return sorted(summaries, key=lambda s: -s.worst_ratio)


class FILELINK_OT_scan_deform_issues(ModalProgressMixin, bpy.types.Operator):
    """Scan every armature-deformed mesh for vertices weighted to a bone that
    drags them wildly out of place once posed — invisible in rest pose, only
    shows up in the deformed result. Detection/review only; nothing is changed."""

    bl_idname = "filelink.scan_deform_issues"
    bl_label = "Check Armature Deformation"
    bl_description = ("Compare each armature-deformed mesh's rest vs. posed edge "
                      "lengths to find vertices weighted to the wrong bone (they "
                      "look fine in rest pose but explode once posed). Read-only "
                      "— review the results and select which to investigate")
    bl_options = {"REGISTER"}

    def cancel_message(self) -> str:
        return "Armature deformation check cancelled"

    def run_steps(self, context):
        from .report_store import stash_report

        wm = context.window_manager
        summaries = yield from _gather_steps(context, DEFAULT_RATIO_THRESHOLD)

        yield (0.97, "Building report…")
        report = build_deform_check_report(summaries)
        stash_report(context, report, "deformcheck")

        coll = wm.filelink_deform_rows
        coll.clear()
        for s in summaries:
            item = coll.add()
            item.name = s.object_name
            item.mesh_name = s.mesh_name
            item.armature_name = s.armature_name
            item.vertex_count = s.count
            item.worst_ratio = s.worst_ratio
            item.vertex_ids = ",".join(str(i.vertex_id) for i in s.issues)
            item.is_locally_fixable = s.is_locally_fixable
        wm.filelink_deform_scanned = True
        wm.filelink_deform_index = 0

        if context.area:
            context.area.tag_redraw()
        yield (1.0, "Done")

        if summaries:
            total_verts = sum(s.count for s in summaries)
            self.report({"WARNING"}, f"{len(summaries)} object(s), {total_verts} "
                        "vertex(es) flagged for likely armature-deformation issues. "
                        "Review the list below.")
        else:
            self.report({"INFO"}, "No armature-deformation outliers found")
