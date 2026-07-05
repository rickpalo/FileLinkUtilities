"""Find a material by name across every .blend file under a folder, offline
via Blender Asset Tracer (BAT) — no Blender launch, no library linking, reads
raw DNA the same way ``core.blendscan`` already does for the folder-wide link
map (docs/TODO.md #22).

bpy-free. BAT is imported lazily so the module imports even where BAT is
absent; tests put the bundled wheel on sys.path (see tests/conftest.py).
"""

from __future__ import annotations

import fnmatch
import pathlib


def make_matcher(pattern: str):
    """Case-insensitive matcher: glob (``* ? [``) if the phrase has wildcard
    characters, else a plain substring match. Ported from the dev-only
    ``tools/find_datablocks.py::_make_matcher`` (excluded from the packaged
    extension, see blender_manifest.toml) so the real add-on can use the same
    matching rule without shipping the CLI script itself."""
    needle = pattern.lower()
    if any(ch in pattern for ch in "*?["):
        return lambda name: fnmatch.fnmatchcase(name.lower(), needle)
    return lambda name: needle in name.lower()


def find_materials(path: pathlib.Path, pattern: str) -> list[str]:
    """Names of MATERIAL datablocks in ``path`` matching ``pattern`` (bare
    names, the ``MA`` DNA prefix stripped). Mirrors ``core.blendscan.
    scan_file``'s open/read/close shape exactly, just against ``MA`` blocks
    instead of ``LI`` ones. Raises ImportError if BAT is unavailable, and
    lets BAT's own exceptions propagate for unreadable/corrupt files
    (callers handle per-file errors, matching every other offline scan in
    this codebase)."""
    from blender_asset_tracer import blendfile  # lazy: see module docstring

    matches = make_matcher(pattern)
    hits: list[str] = []
    bfile = blendfile.BlendFile(pathlib.Path(path))
    try:
        for block in bfile.find_blocks_from_code(b"MA"):
            raw = block.get((b"id", b"name"), as_str=True, default="")
            name = raw[2:] if raw.startswith("MA") else raw
            if name and matches(name):
                hits.append(name)
    finally:
        bfile.close()
    return hits


__all__ = ["make_matcher", "find_materials"]
