"""Offline .blend inspection via Blender Asset Tracer (BAT).

Reads a file's linked libraries WITHOUT opening Blender (BAT handles compressed
files and the raw DNA). The file->file link graph (F1) is built from each
file's ``LI`` (Library) blocks; in Blender 5.x the library path lives in the
block's ``name`` field, where a leading ``//`` means "relative to this .blend's
directory" (verified against fixtures in Blender 5.1).

bpy-free. BAT is imported lazily so the module imports even where BAT is absent;
tests put the bundled wheel on sys.path (see tests/conftest.py).
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Iterator

from .graph import DepGraph

# Folders we never descend into when globbing a project.
DEFAULT_IGNORE_DIRS = frozenset({".git", "__pycache__", "blender_backups", "dist"})


@dataclass(frozen=True)
class LinkRef:
    """A single library link a .blend file makes."""

    stored_path: str  # exactly as stored, e.g. "//libA.blend" or "C:/abs/lib.blend"
    resolved_path: str  # absolute, normalized; "" if it could not be resolved
    is_relative: bool  # True when stored as a "//"-relative path (the good case)
    exists: bool  # whether resolved_path is present on disk


@dataclass
class ScanResult:
    """Outcome of scanning a folder of .blend files."""

    graph: DepGraph
    refs: dict[str, list[LinkRef]]  # blend file (resolved str) -> its library links
    errors: dict[str, str]  # blend file -> error message (could not be read)


def resolve_blend_relative(stored: str, blend_path: pathlib.Path) -> tuple[str, bool]:
    """Resolve a stored library path against the containing .blend.

    Returns (absolute_path_str, is_relative). A leading "//" marks a path
    relative to the .blend's directory (Blender's convention).
    """
    if stored.startswith("//"):
        rel = stored[2:]
        resolved = (blend_path.parent / rel).resolve()
        return str(resolved), True
    p = pathlib.Path(stored)
    if not p.is_absolute():
        p = blend_path.parent / p
    return str(p.resolve()), False


def scan_file(path: pathlib.Path) -> list[LinkRef]:
    """Return the libraries ``path`` links, read offline via BAT.

    Raises ImportError if BAT is unavailable, and lets BAT's own exceptions
    propagate for unreadable files (callers handle per-file errors).
    """
    from blender_asset_tracer import blendfile  # lazy: see module docstring

    path = pathlib.Path(path)
    bfile = blendfile.BlendFile(path)
    try:
        refs: list[LinkRef] = []
        for block in bfile.find_blocks_from_code(b"LI"):
            stored = block.get(b"name", as_str=True, default="")
            if not stored:
                continue
            resolved, is_rel = resolve_blend_relative(stored, path)
            refs.append(
                LinkRef(
                    stored_path=stored,
                    resolved_path=resolved,
                    is_relative=is_rel,
                    exists=pathlib.Path(resolved).is_file() if resolved else False,
                )
            )
        return refs
    finally:
        bfile.close()


def harvest_image_paths(path: pathlib.Path) -> list[str]:
    """Absolute on-disk paths of the external IMAGES referenced by ``path`` (offline,
    via BAT). The candidate corpus for relinking missing textures from ANOTHER .blend
    — we want the files that .blend points its textures at, wherever they live.

    Delegates to BAT's own ``IM``-block handler (skips packed/generated images and
    resolves each path relative to the file), so it tracks Blender's DNA across
    versions exactly as the rest of the offline scan does. Raises ImportError if BAT
    is unavailable; lets BAT's exceptions propagate for unreadable files."""
    from blender_asset_tracer import blendfile  # lazy: see module docstring
    from blender_asset_tracer.trace import blocks2assets

    path = pathlib.Path(path)
    bfile = blendfile.BlendFile(path)
    out: list[str] = []
    seen: set[str] = set()
    try:
        for block in bfile.find_blocks_from_code(b"IM"):
            for usage in blocks2assets.image(block):
                try:
                    p = str(usage.abspath)
                except Exception:
                    continue  # unresolvable path -> skip
                if p and p not in seen:
                    seen.add(p)
                    out.append(p)
        return out
    finally:
        bfile.close()


def iter_blend_files(
    root: pathlib.Path, ignore_dirs: frozenset[str] = DEFAULT_IGNORE_DIRS
) -> Iterator[pathlib.Path]:
    """Yield every ``*.blend`` under ``root``, skipping ignored directories."""
    root = pathlib.Path(root)
    for p in sorted(root.rglob("*.blend")):
        if any(part in ignore_dirs for part in p.parts):
            continue
        yield p


def bat_available() -> bool:
    """Whether Blender Asset Tracer can be imported (bundled at runtime)."""
    try:
        import blender_asset_tracer.blendfile  # noqa: F401

        return True
    except Exception:
        return False


def new_scan_result() -> ScanResult:
    return ScanResult(graph=DepGraph(), refs={}, errors={})


def scan_into(result: ScanResult, blend: pathlib.Path) -> None:
    """Scan one .blend into an existing result (used by both the sync and the
    incremental/modal drivers)."""
    blend = pathlib.Path(blend)
    key = str(blend.resolve())
    result.graph.add_node(key)
    try:
        file_refs = scan_file(blend)
    except Exception as exc:  # unreadable/corrupt file - record, keep going
        result.errors[key] = f"{type(exc).__name__}: {exc}"
        return
    result.refs[key] = file_refs
    for ref in file_refs:
        # Edge source -> target even if target is missing, so broken links
        # still show up as nodes/edges in the graph.
        result.graph.add_edge(key, ref.resolved_path or ref.stored_path)


def map_folder(
    root: pathlib.Path, ignore_dirs: frozenset[str] = DEFAULT_IGNORE_DIRS
) -> ScanResult:
    """Scan a folder and build the file->file link graph (F1 core)."""
    result = new_scan_result()
    for blend in iter_blend_files(root, ignore_dirs):
        scan_into(result, blend)
    return result
