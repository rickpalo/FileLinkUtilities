"""Check Materials — list materials by shader type, flag broken node links
(dangling links + Image Texture nodes pointing at a missing file), and flag
empty material slots (docs/TODO.md Group 9 #33). Read-only/informational —
no bulk-fix action, per the user's explicit call (2026-07-04): these are
diagnostics, not a cleanup step.

Modal: walking every material's node tree + every object's material_slots is
the heavy part, chunked through :func:`_gather_steps` (progress bar + ESC).
``_gather`` keeps a synchronous path for tests/scripting.
"""

import os

import bpy

from ..core.material_diagnostics import (
    COMBINED_SENTINEL,
    build_material_diagnostics_report,
    classify_shader_label,
    is_mix_idname,
)
from .progress import ModalProgressMixin

_CHUNK = 64  # materials+objects processed between progress yields
_FILE_SOURCES = {"FILE", "SEQUENCE", "MOVIE", "TILED"}


def _group_output_surface_node(node_tree):
    """The node feeding a node GROUP's own Group Output "Shader" socket, or
    ``None`` if there's no output node or no linked shader socket."""
    out = next((n for n in node_tree.nodes if n.type == "GROUP_OUTPUT"), None)
    if out is None:
        return None
    for sock in out.inputs:
        if sock.type == "SHADER" and sock.is_linked:
            return sock.links[0].from_node
    return None


def _group_combines_shaders(node_tree, visited: set) -> bool:
    """Whether ``node_tree`` (a node GROUP's own internal graph) ultimately
    feeds its Group Output from a Mix/Add Shader -- descending through any
    further-nested groups too (docs/TODO.md item 46b, 2026-07-04: a
    convenience group like "HG_Hair_V4.001" can wrap a Principled Hair +
    Glossy + Transparent mix, which used to be lumped under its own group
    name as if it were one single shader type). ``visited`` guards against a
    group that contains itself, directly or via nesting."""
    if node_tree is None or node_tree.name in visited:
        return False
    visited.add(node_tree.name)
    node = _group_output_surface_node(node_tree)
    if node is None:
        return False
    if is_mix_idname(node.bl_idname):
        return True
    if node.bl_idname == "ShaderNodeGroup":
        return _group_combines_shaders(node.node_tree, visited)
    return False


def _surface_shader_idname(mat):
    """``(idname, group_tree_name)`` for the node feeding Surface, or
    ``(None, None)`` if there's no linked Surface shader to trace (no nodes,
    no output node, or the Surface socket itself is unlinked). ``idname`` is
    ``core.material_diagnostics.COMBINED_SENTINEL`` when a Surface-linked
    node GROUP mixes multiple shaders internally (item 46b above)."""
    if not getattr(mat, "use_nodes", False) or mat.node_tree is None:
        return None, None
    out = mat.node_tree.get_output_node("ALL")
    if out is None:
        return None, None
    surface = None
    for sock in out.inputs:
        if sock.identifier == "Surface":
            surface = sock
            break
    if surface is None or not surface.is_linked:
        return None, None
    node = surface.links[0].from_node
    if node.bl_idname == "ShaderNodeGroup":
        if node.node_tree and _group_combines_shaders(node.node_tree, set()):
            return COMBINED_SENTINEL, None
        return node.bl_idname, (node.node_tree.name if node.node_tree else None)
    return node.bl_idname, None


def _material_node_issues(mat):
    """``(invalid_links, missing_image_nodes)`` for one material — triples
    matching ``core.material_diagnostics.build_node_link_findings``'s
    expected shape."""
    invalid_links: list[tuple[str, str, str]] = []
    missing_image_nodes: list[tuple[str, str, str]] = []
    if not getattr(mat, "use_nodes", False) or mat.node_tree is None:
        return invalid_links, missing_image_nodes
    tree = mat.node_tree
    for link in tree.links:
        if not link.is_valid:
            invalid_links.append((mat.name, link.to_node.name, link.to_socket.name))
    for node in tree.nodes:
        if node.type != "TEX_IMAGE" or node.image is None:
            continue
        img = node.image
        if img.source not in _FILE_SOURCES or img.packed_file is not None or not img.filepath:
            continue  # generated/viewer/packed -> no external file to go missing
        if not os.path.isfile(os.path.normpath(bpy.path.abspath(img.filepath))):
            missing_image_nodes.append((mat.name, node.name, img.name))
    return invalid_links, missing_image_nodes


def _empty_slots(obj):
    return [idx for idx, slot in enumerate(obj.material_slots) if slot.material is None]


def _gather_steps(context):
    """Yields ``(fraction, status)`` every ``_CHUNK`` materials/objects.
    Returns ``(mat_labels, invalid_links, missing_image_nodes, empty_slots)``."""
    materials = list(bpy.data.materials)
    objects = list(bpy.data.objects)
    total = (len(materials) + len(objects)) or 1

    mat_labels: dict[str, str] = {}
    invalid_links: list[tuple[str, str, str]] = []
    missing_image_nodes: list[tuple[str, str, str]] = []
    empty_slots: list[tuple[str, int]] = []
    done = 0

    for mat in materials:
        idname, group_name = _surface_shader_idname(mat)
        mat_labels[mat.name] = classify_shader_label(idname, group_name)
        links, imgs = _material_node_issues(mat)
        invalid_links.extend(links)
        missing_image_nodes.extend(imgs)
        done += 1
        if done % _CHUNK == 0:
            yield (0.85 * done / total, f"Checking materials {done}/{total}…")

    for obj in objects:
        for idx in _empty_slots(obj):
            empty_slots.append((obj.name, idx))
        done += 1
        if done % _CHUNK == 0:
            yield (0.85 * done / total, f"Checking objects {done - len(materials)}/{len(objects)}…")

    return mat_labels, invalid_links, missing_image_nodes, empty_slots


def _gather(context):
    """Synchronous gather (drains :func:`_gather_steps`). Kept for tests/scripting."""
    gen = _gather_steps(context)
    try:
        while True:
            next(gen)
    except StopIteration as done:
        return done.value


class ASSETDOCTOR_OT_check_materials(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "assetdoctor.check_materials"
    bl_label = "Check Materials"
    bl_description = ("List materials grouped by shader type, flag broken node links "
                       "and Image Texture nodes with a missing file, and flag empty "
                       "material slots (read-only, no changes)")
    bl_options = {"REGISTER"}

    def cancel_message(self):
        return "Material check cancelled"

    def run_steps(self, context):
        from ..log import get_logger
        from .report_store import stash_report

        log = get_logger()
        mat_labels, invalid_links, missing_image_nodes, empty_slots = yield from _gather_steps(context)

        yield (0.9, "Building report…")
        report = build_material_diagnostics_report(
            mat_labels, invalid_links, missing_image_nodes, empty_slots)
        stash_report(context, report, "matdiag")
        for f in report.findings:
            log.info("MATDIAG [%s] %s: %s", f.severity, f.category, f.message)

        issues = len(invalid_links) + len(missing_image_nodes) + len(empty_slots)
        msg = (f"{len(mat_labels)} material(s) classified, {issues} issue(s) flagged"
               if mat_labels or issues else "No materials or objects to check")
        level = "WARNING" if report.count("warning") else "INFO"
        self.report({level}, msg)
