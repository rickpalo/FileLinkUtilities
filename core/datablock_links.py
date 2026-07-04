"""F7 — offline datablock-level link detail (bpy-free, via BAT).

For a ``.blend``, list every datablock that comes from a library (its ``id.lib``
is non-null) grouped by the source library's stored path. This is the primitive
behind the cycle "Detailed Analysis" (what crosses each direction), the safe
duplicate-library-block merge preview, and a Mesh→Material breakdown.

Heavy (it reads every ID block), so it is **on-demand** — run on one or two files
the user drills into, NOT across the whole dependency subtree during a scan.
"""

from __future__ import annotations

import pathlib
from collections import defaultdict


def basename(p: str) -> str:
    """Filename of a stored library path. Plain split (not ntpath, which misreads
    Blender's ``//`` prefix as a UNC root — ``os.path.basename("//Name.blend")``
    returns ``''`` on Windows, since ntpath treats a leading ``//`` as the start
    of a UNC share). Public (not module-private) because ``ui/panels.py`` reuses
    it too — the same disease was independently confirmed there (2026-07-04,
    "Fix at Source" showing blank library names)."""
    return p.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]

# DNA ID-block 2-char name prefix -> friendly kind (the prefix on id.name, e.g.
# "OBTree" -> Object "Tree"). Covers the datablocks that get linked; unknown
# prefixes fall back to the raw 2 chars.
_PREFIX_KINDS = {
    "OB": "Object", "ME": "Mesh", "MA": "Material", "IM": "Image",
    "NT": "Node Group", "AR": "Armature", "AC": "Action", "CU": "Curve",
    "GR": "Collection", "TE": "Texture", "LA": "Light", "CA": "Camera",
    "WO": "World", "SC": "Scene", "KE": "Shape Key", "PA": "Particle",
    "OB ": "Object",
}


# A few friendly kind labels above don't match the real bpy.types class name
# (used for click-to-select refs, which match on type(datablock).__name__) --
# everything else in _PREFIX_KINDS already is the real class name verbatim.
_KIND_TO_CLASS = {"Node Group": "NodeTree", "Shape Key": "Key", "Particle": "ParticleSettings"}


def kind_ref(kind: str, name: str) -> dict[str, str]:
    """A click-to-select ref for a ``(kind, name)`` pair from this module's
    functions (e.g. ``{"type": "NodeTree", "name": "Foo"}``)."""
    return {"type": _KIND_TO_CLASS.get(kind, kind), "name": name}


def linked_datablocks(blend_path) -> dict[str, list[tuple[str, str]]]:
    """``{library stored path: [(kind, name), …]}`` for every datablock in
    ``blend_path`` that comes from a library.

    Linked datablocks are written into the linking file as generic ``ID``
    placeholder blocks: a top-level ``name`` (with the 2-char type prefix) and a
    ``lib`` pointer to the source Library (``LI``) block. (Verified against the
    linkproj fixtures in Blender 5.1.)"""
    from blender_asset_tracer import blendfile

    grouped: dict[str, set[tuple[str, str]]] = defaultdict(set)
    bfile = blendfile.BlendFile(pathlib.Path(blend_path))
    try:
        for block in bfile.find_blocks_from_code(b"ID"):
            try:
                lib_block = block.get_pointer((b"lib",))
            except Exception:
                lib_block = None
            if lib_block is None:
                continue
            lib_path = lib_block.get(b"name", as_str=True, default="")
            raw = block.get(b"name", as_str=True, default="")
            kind = _PREFIX_KINDS.get(raw[:2], raw[:2] or "?")
            grouped[lib_path].add((kind, raw[2:]))
    finally:
        bfile.close()
    return {lib: sorted(items) for lib, items in grouped.items()}


def datablocks_from_library(blend_path, library_basename: str) -> list[tuple[str, str]]:
    """The datablocks ``blend_path`` links from the library whose *filename*
    matches ``library_basename`` (e.g. to ask "what does A link from B?")."""
    target = library_basename.lower()
    hits: list[tuple[str, str]] = []
    for lib_path, items in linked_datablocks(blend_path).items():
        if basename(lib_path).lower() == target:
            hits.extend(items)
    return hits


def link_counts(blend_path) -> list[tuple[str, int]]:
    """``(library stored path, #datablocks)`` linked from each, most first."""
    counts = [(lib, len(items)) for lib, items in linked_datablocks(blend_path).items()]
    counts.sort(key=lambda t: -t[1])
    return counts
