"""bpy -> dict extractors feeding core.fingerprint.

This is the only fingerprint-related code that touches bpy. It walks materials,
meshes and images into the plain-dict shapes documented in core.fingerprint, so
all the hashing logic stays bpy-free and unit-tested.

Material extraction is resolution-agnostic: image references become their
resolution-stripped base name (see core.fingerprint.strip_resolution_tokens).
"""

from __future__ import annotations

import bpy

from ..core.fingerprint import fingerprint_mesh, strip_resolution_tokens

# Cosmetic/layout node attributes that must not affect the fingerprint.
_SKIP_NODE_PROPS = frozenset({
    "name", "label", "location", "location_absolute", "width", "height",
    "width_hidden", "dimensions", "color", "use_custom_color", "select",
    "hide", "show_options", "show_preview", "show_texture", "parent",
    "bl_idname", "bl_label", "bl_description", "bl_icon", "bl_static_type",
    "rna_type", "inputs", "outputs", "internal_links",
})


def _socket_value(socket):
    """JSON-able default_value of an input socket, or None if it has none."""
    val = getattr(socket, "default_value", None)
    if val is None:
        return None
    try:
        return list(val)  # color/vector arrays
    except TypeError:
        return val  # scalar float/int/bool/str


def _node_props(node, res_pattern: str | None) -> dict:
    props: dict = {}
    # Image reference, normalised to a resolution-agnostic base name.
    img = getattr(node, "image", None)
    if img is not None:
        base = img.name
        props["image_base"] = (
            strip_resolution_tokens(base, res_pattern) if res_pattern
            else strip_resolution_tokens(base)
        )
        cs = getattr(img, "colorspace_settings", None)
        if cs is not None:
            props["colorspace"] = cs.name

    for prop in node.bl_rna.properties:
        ident = prop.identifier
        if ident in _SKIP_NODE_PROPS or prop.is_readonly:
            continue
        if prop.type in {"POINTER", "COLLECTION"}:
            continue  # pointers (e.g. image) handled above; collections skipped
        try:
            value = getattr(node, ident)
        except AttributeError:
            continue
        if getattr(prop, "is_array", False):
            try:
                value = list(value)
            except TypeError:
                continue
        props[ident] = value
    return props


def _extract_tree(tree, res_pattern: str | None) -> dict:
    """Shared node-graph walk behind :func:`extract_material` and
    :func:`extract_node_tree`. Output-node detection tries a Material/World/
    Light output first (``get_output_node``, what materials use), then falls
    back to the active ``NodeGroupOutput`` (what a bare node GROUP's internal
    tree uses instead — ``get_output_node`` doesn't recognize it)."""
    out_node = tree.get_output_node("ALL") if hasattr(tree, "get_output_node") else None
    if out_node is None:
        group_outputs = [n for n in tree.nodes if n.bl_idname == "NodeGroupOutput"]
        out_node = next((n for n in group_outputs if getattr(n, "is_active_output", True)),
                        group_outputs[0] if group_outputs else None)
    nodes: dict = {}
    for node in tree.nodes:
        inputs: dict = {}
        for sock in node.inputs:
            if sock.is_linked and sock.links:
                link = sock.links[0]
                inputs[sock.identifier] = {
                    "from": link.from_node.name,
                    "from_socket": link.from_socket.identifier,
                    "value": None,
                }
            else:
                inputs[sock.identifier] = {
                    "from": None, "from_socket": None, "value": _socket_value(sock)
                }
        # A node's meaningful state can live on an OUTPUT socket's own
        # default_value rather than any input or bl_rna node property --
        # e.g. ShaderNodeValue/RGB have zero inputs, their single output IS
        # the node's entire content. Missed before 2026-07-09 (found live:
        # two differently-valued Value nodes hashed identically), which would
        # have silently undermined the Mesh/NodeTree content-verification
        # this same session added to Examine Library.
        outputs = {sock.identifier: _socket_value(sock) for sock in node.outputs}
        nodes[node.name] = {
            "idname": node.bl_idname,
            "props": _node_props(node, res_pattern),
            "inputs": inputs,
            "outputs": outputs,
        }
    return {
        "use_nodes": True,
        "output": out_node.name if out_node else None,
        "nodes": nodes,
    }


def extract_material(mat, res_pattern: str | None = None) -> dict:
    """Walk a bpy material into a core.fingerprint material_dict."""
    if not getattr(mat, "use_nodes", False) or mat.node_tree is None:
        return {
            "use_nodes": False,
            "flat": {"diffuse": list(getattr(mat, "diffuse_color", []))},
        }
    return _extract_tree(mat.node_tree, res_pattern)


def extract_node_tree(tree, res_pattern: str | None = None) -> dict:
    """Walk a STANDALONE bpy NodeTree (a shader/geometry node GROUP, not
    wrapped in a Material) into the same dict shape :func:`extract_material`
    produces, so :func:`core.fingerprint.fingerprint_node_tree` can hash it.

    Added 2026-07-09 for Examine Library's NodeTree-kind rows: a same-name
    match between two node groups is only a guess, same as for Materials (see
    ``ops.examine_library``'s docstring) — needed once real ``NT*``-prefixed
    shader node-group duplicates (Reallusion/CC utility groups,
    auto-numbered) were found merged this way in a heavily-merged production
    file."""
    return _extract_tree(tree, res_pattern)


def extract_mesh(mesh) -> dict:
    return {
        "vertices": [list(v.co) for v in mesh.vertices],
        "polygons": [list(p.vertices) for p in mesh.polygons],
        "edges": len(mesh.edges),
    }


def extract_action(action) -> dict:
    """Walk a bpy Action into a core.fingerprint action_dict (keyframe co +
    interpolation only — not handle positions/types, same scope tradeoff as
    extract_mesh keeping verts+polys but not normals/UVs)."""
    fcurves = []
    for fc in action.fcurves:
        points = [[kp.co[0], kp.co[1], kp.interpolation] for kp in fc.keyframe_points]
        fcurves.append({"data_path": fc.data_path, "array_index": fc.array_index,
                        "points": points})
    return {"fcurves": fcurves}


def datablock_risk_reason(block) -> str:
    """Why reading ``block``'s heavy per-element data (mesh geometry,
    shape-key vertex deltas, ...) risks a native crash, or ``""`` if there's
    no known risk. A missing placeholder or Library Override ID is the
    documented disease class: a file with known override/dependency loops can
    leave this kind of data incomplete or dangling, and a native access
    violation reading it can't be caught with try/except — the only real
    mitigation is never touching the risky data in the first place.

    Originally shape-key-specific (`shape_key_risk_reason`, the v0.2.94
    `extract_shape_key` mitigation); generalized 2026-07-04 after the SAME
    disease crashed `ops.orphans`' mesh fingerprinting too (a mesh datablock
    can itself be missing or an override, not just a shape key's owner) —
    one shared check instead of two independent copies."""
    if getattr(block, "is_missing", False):
        return f"{block.name!r} is a missing placeholder"
    if getattr(block, "override_library", None) is not None:
        return f"{block.name!r} is a Library Override"
    # 2026-07-14 (PSM_Stage crashes v0.3.4/v0.3.5): a datablock linked from a
    # library whose FILE is missing can itself be flagged neither is_missing nor
    # override, yet its heavy data is dangling — reading it (extract_mesh /
    # shape-key co) is a native null read no try/except can catch. The owning
    # Library's own is_missing IS set, so gate on that. This one shared check
    # covers every geometry-reading path (shape keys, Find Duplicate Geometry,
    # Orphans, ...), not just the one that happened to crash first.
    lib = getattr(block, "library", None)
    if lib is not None and getattr(lib, "is_missing", False):
        return f"{block.name!r} is linked from a missing library"
    return ""


def shape_key_risk_reason(key) -> str:
    """Why :func:`extract_shape_key` would refuse to read ``key``'s per-vertex
    data, or ``""`` if there's no known risk — :func:`datablock_risk_reason`
    applied to the shape key's OWNER mesh (a shape key can never be its own
    override, only inherited via its owner; `ops.datablock_inspect`'s Audit
    already flags exactly this combination as `shape_key_risks` without ever
    reading `kb.data` on it). Split out from `extract_shape_key` itself so
    callers can report WHICH shape keys got skipped and why, instead of
    silently dropping them (user 2026-06-28: needs to be visible by name so
    they can investigate the underlying file corruption)."""
    owner = key.user
    if not isinstance(owner, bpy.types.Mesh):
        return ""
    reason = datablock_risk_reason(owner)
    return f"owner mesh {reason}" if reason else ""


def extract_shape_key(key) -> dict:
    """Walk a bpy Key (shape-key) datablock into a core.fingerprint
    shape_key_dict. Returns ``{}`` ('unverified', no safe identity check
    possible) when the owner isn't a Mesh (Curve/Lattice shape keys are rarer
    in practice and not yet covered) or :func:`shape_key_risk_reason` flags it
    as unsafe to read."""
    owner = key.user
    if not isinstance(owner, bpy.types.Mesh):
        return {}
    if shape_key_risk_reason(key):
        return {}
    # A LINKED owner mesh is never a local merge candidate (you can't merge a
    # datablock a library owns), so its geometry fingerprint has no use — and
    # reading that geometry can crash `extract_mesh` with an uncatchable native
    # null read on a file with missing libraries / override loops, even when the
    # mesh is flagged NEITHER missing nor override (PSM_Stage crash, v0.3.4:
    # the owner was linked from one of 3 missing libraries). Nothing to gain,
    # real risk — skip to "unverified".
    if owner.library is not None:
        return {}
    blocks = [{"name": kb.name, "co": [list(p.co) for p in kb.data]}
              for kb in key.key_blocks]
    return {"mesh_fingerprint": fingerprint_mesh(extract_mesh(owner)), "blocks": blocks}


def extract_image(image) -> dict:
    cs = getattr(image, "colorspace_settings", None)
    return {
        "filepath": image.filepath,
        "size": list(image.size),
        "depth": image.depth,
        "source": image.source,
        "colorspace": cs.name if cs else "",
    }
