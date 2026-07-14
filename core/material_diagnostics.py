"""Material Diagnostics — list materials by shader type, flag broken node
links, and flag empty material slots (docs/TODO.md Group 9 #33, scoped
2026-07-04). bpy-free and unit-tested; ``ops/material_diagnostics.py`` does
the bpy-side node/object walk and hands this module plain data.

All 3 checks are read-only/informational (user's explicit call: no bulk-fix
action, unlike Find Orphans/Find Duplicates) — this module only ever builds a
:class:`~core.report.Report`, nothing mutates.
"""

from __future__ import annotations

from .report import Finding, Report

# bl_idname -> friendly label for the node feeding a material's Surface input.
_FRIENDLY_SHADER = {
    "ShaderNodeBsdfPrincipled": "Principled BSDF",
    "ShaderNodeBsdfHairPrincipled": "Principled Hair BSDF",
    "ShaderNodeVolumePrincipled": "Principled Volume",
    "ShaderNodeEmission": "Emission",
    "ShaderNodeBsdfDiffuse": "Diffuse BSDF",
    "ShaderNodeBsdfGlossy": "Glossy BSDF",
    "ShaderNodeBsdfTransparent": "Transparent BSDF",
    "ShaderNodeBsdfGlass": "Glass BSDF",
    "ShaderNodeBsdfTranslucent": "Translucent BSDF",
    "ShaderNodeBsdfRefraction": "Refraction BSDF",
    "ShaderNodeBsdfToon": "Toon BSDF",
    "ShaderNodeBsdfVelvet": "Velvet BSDF",
    "ShaderNodeBsdfSheen": "Sheen BSDF",
    "ShaderNodeSubsurfaceScattering": "Subsurface Scattering",
    "ShaderNodeHoldout": "Holdout",
    "ShaderNodeEeveeSpecular": "Specular BSDF",
    "ShaderNodeBackground": "Background",
}
_MIX_IDNAMES = {"ShaderNodeMixShader", "ShaderNodeAddShader"}

NO_NODES = "No Nodes (legacy)"
NO_OUTPUT = "No Output Node"
NO_SURFACE = "No Surface Shader"
MIXED_SHADER = "Mixed Shader"
COMBINED_SHADER = "Combined Shader"

# Sentinel ``surface_idname`` the ops layer returns when a node GROUP's own
# internal graph mixes multiple shaders (docs/TODO.md item 46b, 2026-07-04) --
# distinct from ``MIXED_SHADER`` (a Mix/Add Shader wired directly at the
# material's own surface) so the two discovery paths stay tellable apart if
# that's ever useful, per the user's own naming for this new case.
COMBINED_SENTINEL = "__COMBINED__"


def is_mix_idname(idname: str) -> bool:
    """Whether ``idname`` is a Mix/Add Shader node -- exposed so the ops
    layer's node-group traversal (docs/TODO.md item 46b) can recognise a
    combining node without reaching into this module's private set."""
    return idname in _MIX_IDNAMES


def classify_shader_label(surface_idname: str | None, group_tree_name: str | None = None) -> str:
    """Friendly group label for the node connected to a material's Surface
    input. ``surface_idname=None`` means the Surface socket itself is
    unlinked (caller has already ruled out the no-nodes/no-output cases)."""
    if surface_idname is None:
        return NO_SURFACE
    if surface_idname == COMBINED_SENTINEL:
        return COMBINED_SHADER
    if surface_idname in _MIX_IDNAMES:
        return MIXED_SHADER
    if surface_idname == "ShaderNodeGroup":
        return f"Node Group: {group_tree_name}" if group_tree_name else "Node Group"
    return _FRIENDLY_SHADER.get(surface_idname, surface_idname.replace("ShaderNode", ""))


def build_shader_type_findings(mat_labels: dict[str, str]) -> list[Finding]:
    """One Finding per shader-type group, sorted by label; items are
    ``"Material/<name>"`` click-to-select refs (core.tree's convention)."""
    groups: dict[str, list[str]] = {}
    for name, label in mat_labels.items():
        groups.setdefault(label, []).append(name)
    findings = []
    for label in sorted(groups):
        names = sorted(groups[label])
        findings.append(Finding(
            category="shader_type", severity="info",
            message=f"{label} ({len(names)} material(s))",
            items=[f"Material/{n}" for n in names],
        ))
    return findings


def build_node_link_findings(invalid_links: list[tuple[str, str, str]],
                              missing_image_nodes: list[tuple[str, str, str]]) -> list[Finding]:
    """``invalid_links``: (material, node, socket) triples where the link
    into that socket is dangling (``NodeLink.is_valid`` False — e.g. a
    version-upgrade socket-type mismatch). ``missing_image_nodes``:
    (material, node, image_name) triples where an Image Texture node's image
    file can't be found on disk. One Finding per issue (not per material) so
    each keeps its own description; the single click-to-select item still
    jumps to the material."""
    findings = []
    for mat, node, sock in invalid_links:
        findings.append(Finding(
            category="node_link_issue", severity="warning",
            message=f"{mat}: broken link into '{node}' → {sock}",
            items=[f"Material/{mat}"],
        ))
    for mat, node, img in missing_image_nodes:
        findings.append(Finding(
            category="node_link_issue", severity="warning",
            message=f"{mat}: Image Texture node '{node}' uses missing image '{img}'",
            items=[f"Material/{mat}"],
        ))
    return findings


def build_empty_slot_findings(empty_slots: list[tuple[str, int]]) -> list[Finding]:
    """``empty_slots``: (object_name, slot_index) pairs where
    ``material_slots[index].material is None``. ``data`` carries the pair
    STRUCTURALLY (2026-07-14 — it used to live only in the message text) so
    ``FILELINK_OT_delete_empty_material_slots`` can target the exact slot
    without re-parsing a human-readable string."""
    return [
        Finding(category="empty_slot", severity="info",
                message=f"{obj}: material slot {idx} is empty",
                items=[f"Object/{obj}"],
                data={"object": obj, "slot_index": idx})
        for obj, idx in empty_slots
    ]


def build_material_diagnostics_report(
    mat_labels: dict[str, str],
    invalid_links: list[tuple[str, str, str]],
    missing_image_nodes: list[tuple[str, str, str]],
    empty_slots: list[tuple[str, int]],
) -> Report:
    findings: list[Finding] = []
    findings += build_shader_type_findings(mat_labels)
    findings += build_node_link_findings(invalid_links, missing_image_nodes)
    findings += build_empty_slot_findings(empty_slots)
    if not findings:
        findings = [Finding(category="clean", severity="info",
                            message="✓ no materials, node-link issues, or empty material slots found")]
    return Report(title="Material Diagnostics", feature="MATDIAG", findings=findings)
