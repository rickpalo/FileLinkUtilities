"""Canonical content fingerprints for datablocks (shared by F3, F4, and the F1
cross-file duplication census).

Blender has no native "hash this datablock", so we build canonical, stable
serializers per type and hash them. All functions take plain dicts (extracted
from bpy by the ops layer in the documented shapes), so this module stays
bpy-free and unit-testable.

Material hashing is **resolution-agnostic**: an image reference inside a node is
normalised to its resolution-stripped base name (via ``strip_resolution_tokens``)
so a 1K and a 2K variant of the same material hash identically (the F3 rule).
Image *identity* hashing (``fingerprint_image``) is the opposite — it keeps
resolution, to find truly duplicate images for F4.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

# Default fragments; the live value comes from prefs.resolution_token_regex.
_DEFAULT_RES_TOKENS = r"[._-]?\d{1,2}k|[._-]\d{3,4}|\.\d{3}$"

# Float rounding for stable hashing (kills representation jitter).
_NDIGITS = 6


def strip_resolution_tokens(name: str, pattern: str = _DEFAULT_RES_TOKENS) -> str:
    """Reduce a texture/material name to its resolution-agnostic base.

    >>> strip_resolution_tokens("wood_2k")
    'wood'
    >>> strip_resolution_tokens("wood_1k")
    'wood'
    >>> strip_resolution_tokens("Bark-2048")
    'Bark'
    >>> strip_resolution_tokens("metal.001")
    'metal'
    """
    base = re.sub(pattern, "", name, flags=re.IGNORECASE)
    return base.strip(" ._-")


def _canon(obj: Any) -> str:
    """Deterministic JSON for hashing: sorted keys, rounded floats."""

    def default(o):
        if isinstance(o, float):
            return round(o, _NDIGITS)
        if isinstance(o, (tuple, set)):
            return list(o)
        if isinstance(o, bytes):
            return o.decode("utf-8", "replace")
        return str(o)

    # Pre-round floats nested in lists/dicts via a walk so json sees plain types.
    return json.dumps(_round(obj), sort_keys=True, default=default, separators=(",", ":"))


def _round(obj: Any) -> Any:
    if isinstance(obj, float):
        return round(obj, _NDIGITS)
    if isinstance(obj, dict):
        return {k: _round(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v) for v in obj]
    return obj


def _sha(obj: Any) -> str:
    return hashlib.sha1(_canon(obj).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Materials / node trees
# --------------------------------------------------------------------------- #
#
# material_dict contract (produced by the ops extractor):
#   {
#     "use_nodes": bool,
#     # when use_nodes is False:
#     "flat": { ... simple props like base color ... },
#     # when use_nodes is True:
#     "output": "<node key>" or None,
#     "nodes": {
#       "<key>": {
#         "idname": "ShaderNodeBsdfPrincipled",
#         "props": { ... resolution-agnostic params; for image nodes include
#                    "image_base": strip_resolution_tokens(name), "colorspace": .. },
#         "inputs": {
#           "<socket identifier>": {
#             "from": "<other node key>" or None,      # link source, if any
#             "from_socket": "<identifier>" or None,
#             "value": <jsonable> or None,             # default_value when unlinked
#           }, ...
#         },
#       }, ...
#     },
#   }
#
# Node *names/labels/positions* are intentionally NOT part of the hash.


def _node_hash(nodes: dict, key: str, memo: dict) -> str:
    state = memo.get(key)
    if state == "...":  # cycle guard (shouldn't happen in shader DAGs)
        return "<cycle>"
    if state is not None:
        return state
    memo[key] = "..."

    node = nodes[key]
    parts: list = [node.get("idname", ""), node.get("props", {})]
    for sid in sorted(node.get("inputs", {})):
        inp = node["inputs"][sid]
        if inp.get("from"):
            parts.append([sid, inp.get("from_socket"), "L", _node_hash(nodes, inp["from"], memo)])
        else:
            parts.append([sid, "V", inp.get("value")])
    # Output sockets carry a node's own state when it has no inputs at all
    # (ShaderNodeValue/RGB) -- see extract._extract_tree's 2026-07-09 note.
    for sid in sorted(node.get("outputs", {})):
        parts.append(["out", sid, node["outputs"][sid]])

    h = _sha(parts)
    memo[key] = h
    return h


def fingerprint_material(material_dict: dict) -> str:
    """Stable, resolution-agnostic hash of a material.

    Invariant to node naming/order; sensitive to graph topology, node params and
    unlinked socket default values. Driven from the Material Output node when
    present; otherwise falls back to the unordered multiset of node signatures.
    """
    if not material_dict.get("use_nodes"):
        return _sha(["flat", material_dict.get("flat", {})])

    nodes = material_dict.get("nodes", {})
    output = material_dict.get("output")
    if output and output in nodes:
        return _sha(["mat", _node_hash(nodes, output, {})])

    # Fallback: no identifiable output - hash the multiset of local node sigs.
    sigs = sorted(_sha([n.get("idname", ""), n.get("props", {}), n.get("outputs", {})])
                  for n in nodes.values())
    return _sha(["mat-no-output", sigs])


def fingerprint_node_tree(node_tree_dict: dict) -> str:
    """Stable hash of a STANDALONE NodeTree's graph (a shader/geometry node
    GROUP, not wrapped in a Material) — identical algorithm and dict shape as
    :func:`fingerprint_material`'s ``use_nodes=True`` path (which a bare node
    tree's extracted dict also uses), exposed under its own name for callers
    that aren't fingerprinting a Material (Examine Library's NodeTree-kind
    rows, added 2026-07-09)."""
    return fingerprint_material(node_tree_dict)


# --------------------------------------------------------------------------- #
# Meshes
# --------------------------------------------------------------------------- #
#
# mesh_dict contract:
#   { "vertices": [[x,y,z], ...], "polygons": [[i,j,k,...], ...], "edges": int }
# Order-sensitive: detects true duplicates/copies (which preserve order), not
# arbitrary geometric congruence.


def fingerprint_mesh(mesh_dict: dict) -> str:
    """Stable hash of mesh geometry (counts + rounded coords + face topology)."""
    verts = mesh_dict.get("vertices", [])
    polys = mesh_dict.get("polygons", [])
    payload = {
        "nv": len(verts),
        "np": len(polys),
        "ne": mesh_dict.get("edges", 0),
        "v": verts,  # _round handles float jitter
        "p": polys,
    }
    return _sha(["mesh", payload])


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #
#
# action_dict contract:
#   { "fcurves": [{"data_path": str, "array_index": int,
#                   "points": [[frame, value, interpolation], ...]}, ...] }
# Keyframe co (frame, value) + interpolation only — not handle positions/types.
# Detects byte-identical re-linked duplicates (the undisciplined-animator
# ".001"/".002" case), not arbitrary congruent animation curves.


def fingerprint_action(action_dict: dict) -> str:
    """Stable hash of an Action's F-curve keyframe data. Curves are sorted by
    ``(data_path, array_index)`` so fcurve ORDER doesn't matter, only identity."""
    curves = sorted(
        (c.get("data_path", ""), c.get("array_index", 0), c.get("points", []))
        for c in action_dict.get("fcurves", [])
    )
    return _sha(["action", curves])


# --------------------------------------------------------------------------- #
# Images (identity, resolution-SENSITIVE)
# --------------------------------------------------------------------------- #
#
# image_dict contract:
#   { "filepath": str, "size": [w, h], "depth": int, "source": str,
#     "colorspace": str, "pixels_digest": str (optional) }


# --------------------------------------------------------------------------- #
# Shape keys (Key datablocks)
# --------------------------------------------------------------------------- #
#
# shape_key_dict contract:
#   { "mesh_fingerprint": str,  # fingerprint_mesh() of the OWNING mesh's geometry
#     "blocks": [{"name": str, "co": [[x,y,z], ...]}, ...] }  # key_blocks, in order
#
# A Key's own relative-key vertex data means nothing on its own — the same
# delta values deform a different mesh into a different shape. Folding the
# owning mesh's fingerprint into the hash means two Keys only ever compare
# equal when BOTH the mesh they deform AND every key block's data match.


def fingerprint_shape_key(shape_key_dict: dict) -> str:
    """Stable hash of a shape-key (Key) datablock, keyed to its owning mesh.

    Order-sensitive (like ``fingerprint_mesh``): detects byte-identical
    re-linked duplicates, not arbitrary shapes that happen to deform the same
    way. Empty/unverifiable input (e.g. the owner isn't a Mesh) hashes to ""
    so it never collides with a real fingerprint."""
    if not shape_key_dict:
        return ""
    payload = {
        "mesh": shape_key_dict.get("mesh_fingerprint", ""),
        "blocks": [{"name": b.get("name", ""), "co": b.get("co", [])}
                   for b in shape_key_dict.get("blocks", [])],
    }
    return _sha(["shape_key", payload])


def fingerprint_image(image_dict: dict) -> str:
    """Identity hash of an image datablock (keeps resolution; for F4 dedup)."""
    payload = {
        "filepath": image_dict.get("filepath", ""),
        "size": list(image_dict.get("size", [])),
        "depth": image_dict.get("depth", 0),
        "source": image_dict.get("source", ""),
        "colorspace": image_dict.get("colorspace", ""),
        "pixels_digest": image_dict.get("pixels_digest", ""),
    }
    return _sha(["image", payload])
