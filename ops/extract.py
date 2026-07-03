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


def extract_material(mat, res_pattern: str | None = None) -> dict:
    """Walk a bpy material into a core.fingerprint material_dict."""
    if not getattr(mat, "use_nodes", False) or mat.node_tree is None:
        return {
            "use_nodes": False,
            "flat": {"diffuse": list(getattr(mat, "diffuse_color", []))},
        }

    tree = mat.node_tree
    out_node = tree.get_output_node("ALL")
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
        nodes[node.name] = {
            "idname": node.bl_idname,
            "props": _node_props(node, res_pattern),
            "inputs": inputs,
        }
    return {
        "use_nodes": True,
        "output": out_node.name if out_node else None,
        "nodes": nodes,
    }


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


def shape_key_risk_reason(key) -> str:
    """Why :func:`extract_shape_key` would refuse to read ``key``'s per-vertex
    data, or ``""`` if there's no known risk. A missing or Library-Override
    owner is the documented "KEKey... not linkable, flagged as directly
    linked" disease (a shape key can never be its own override, only
    inherited via its owner) — `ops.datablock_inspect`'s Audit already flags
    exactly this combination as `shape_key_risks` without ever reading
    `kb.data` on it. Real crash (EXCEPTION_ACCESS_VIOLATION, 2026-06-28,
    human_bundle.blend via Find Duplicates) traced to `extract_shape_key`
    reading shape-key vertex data on a file with known override/dependency
    loops touching shape-keyed meshes; a native access violation can't be
    caught with try/except, so the only real mitigation is never touching
    the risky data in the first place. Split out from `extract_shape_key`
    itself so callers can report WHICH shape keys got skipped and why,
    instead of silently dropping them (user 2026-06-28: needs to be visible
    by name so they can investigate the underlying file corruption)."""
    owner = key.user
    if not isinstance(owner, bpy.types.Mesh):
        return ""
    if getattr(owner, "is_missing", False):
        return f"owner mesh {owner.name!r} is a missing placeholder"
    if getattr(owner, "override_library", None) is not None:
        return f"owner mesh {owner.name!r} is a Library Override"
    return ""


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
