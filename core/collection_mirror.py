"""Flatten v2's "Make Copy" collection-mirroring algorithm (docs/TODO.md
Group 11 #47) -- pure path math, bpy-free and unit-tested. The bpy-aware
caller (``ops/linkchain.py``) walks the real Scene Collection to build each
flattened object's PATH (a tuple of collection names from the scene's root
collection down to its immediate parent collection), calls
:func:`mirror_collection_paths` once for the whole batch, then realizes the
result into real ``bpy.types.Collection`` objects.

Every path must start with the same root element (the real scene's master
collection name, usually "Scene Collection" but user-renameable) -- a remote-
sourced character with no known local anchor (docs/TODO.md's 2026-06-27
scope decision) is represented as a path of JUST the root, i.e. ``(root,)``,
which this module already handles without any special-casing: its "lowest
common ancestor" with anything else just collapses toward the root, exactly
like the Scene-Collection-fallback rule the user originally described.
"""

from __future__ import annotations


def mirror_name(original: str) -> str:
    return f"{original}_flattened"


def lowest_common_path(paths: list[tuple[str, ...]]) -> tuple[str, ...]:
    """Longest common prefix across every path. Every path is expected to
    share the same first element (the scene root's name), so the result is
    never empty as long as ``paths`` is non-empty."""
    if not paths:
        return ()
    common = paths[0]
    for p in paths[1:]:
        n = 0
        while n < len(common) and n < len(p) and common[n] == p[n]:
            n += 1
        common = common[:n]
        if not common:
            break
    return common


def mirror_collection_paths(paths: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
    """Every distinct collection (as a full ORIGINAL-name path from the
    root) that needs a mirror collection created for it, shortest-first
    (parent before child; stable order otherwise) -- i.e. every unique
    prefix of every given path, from the lowest common ancestor down.

    The first entry is always the lowest common ancestor itself -- the
    caller creates ITS mirror as a sibling of the real ancestor (a new
    child of the ancestor's own parent), or as a new child of the scene
    root directly when the ancestor IS the root (no parent to be a sibling
    under). Every later entry's mirror is parented under the mirror of
    ``entry[:-1]`` (already created, since shorter prefixes sort first).
    An object's own leaf mirror collection is simply the mirror of its own
    full path -- guaranteed to be present in the result."""
    ancestor = lowest_common_path(paths)
    seen: set[tuple[str, ...]] = set()
    ordered: list[tuple[str, ...]] = []
    for p in paths:
        for n in range(len(ancestor), len(p) + 1):
            prefix = p[:n]
            if prefix not in seen:
                seen.add(prefix)
                ordered.append(prefix)
    ordered.sort(key=len)
    return ordered


__all__ = ["mirror_name", "lowest_common_path", "mirror_collection_paths"]
