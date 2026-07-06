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
import re
from typing import Iterable


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


def list_material_names(path: pathlib.Path) -> list[str]:
    """Bare names (``MA`` DNA prefix stripped) of every MATERIAL datablock in
    ``path``. Mirrors ``core.blendscan.scan_file``'s open/read/close shape
    exactly, just against ``MA`` blocks instead of ``LI`` ones. Raises
    ImportError if BAT is unavailable, and lets BAT's own exceptions
    propagate for unreadable/corrupt files (callers handle per-file errors,
    matching every other offline scan in this codebase)."""
    from blender_asset_tracer import blendfile  # lazy: see module docstring

    names: list[str] = []
    bfile = blendfile.BlendFile(pathlib.Path(path))
    try:
        for block in bfile.find_blocks_from_code(b"MA"):
            raw = block.get((b"id", b"name"), as_str=True, default="")
            name = raw[2:] if raw.startswith("MA") else raw
            if name:
                names.append(name)
    finally:
        bfile.close()
    return names


def find_materials(path: pathlib.Path, pattern: str) -> list[str]:
    """Names of MATERIAL datablocks in ``path`` matching ``pattern`` (glob if
    the phrase has wildcard characters, else a plain substring — see
    :func:`make_matcher`)."""
    matches = make_matcher(pattern)
    return [name for name in list_material_names(path) if matches(name)]


_NORM_RE = re.compile(r"[^a-z0-9]+")


def _normalize(name: str) -> str:
    return _NORM_RE.sub("", name.lower())


def score_material_name(wanted: str, candidate: str) -> float | None:
    """Bidirectional containment score (0..1) between two material names, or
    ``None`` if neither (lowercased, separator-stripped) name contains the
    other.

    Vendor material names are often long, concatenated compounds
    (``FabricFloralDuckeggJacquard001``) with no delimiter to tokenize on,
    that get manually shortened in a scene (``DuckEgg``) — token-overlap
    scoring (``core.imagematch``) doesn't apply: a short alias is SUPPOSED
    to share few tokens with the full name, which Jaccard would score as a
    poor match even though it's really a confident one. Plain containment
    handles both directions (a short scene alias finding a verbose vendor
    name, or vice versa for an older/differently-named library file); the
    ``shorter / longer`` length ratio scores a near-full match near 1.0 and
    a short generic alias low — so a weak, generic hit just naturally
    ranks below a fuller one instead of needing a hand-tuned minimum-length
    cutoff."""
    a, b = _normalize(wanted), _normalize(candidate)
    if not a or not b:
        return None
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b))
    return None


_CONFIDENCE_BANDS = ((0.9, "high"), (0.5, "medium"))


def material_name_confidence(score: float) -> str:
    """Bucket a :func:`score_material_name` score into "high"/"medium"/"low"
    — the same vocabulary ``core.imagematch.Match.confidence`` uses, so a
    material-name match and a texture-channel match read the same way."""
    for floor, label in _CONFIDENCE_BANDS:
        if score >= floor:
            return label
    return "low"


def best_material_match(
    wanted: str, files: Iterable[pathlib.Path], *, shortlist: int = 5,
) -> tuple[pathlib.Path, str, float] | None:
    """The best ``(file, material name, score)`` match for ``wanted`` across
    ``files``, or ``None``.

    Two-pass, so this stays cheap over a library of hundreds of files: first
    score every file by its OWN NAME (no I/O), then only open+parse the
    top ``shortlist`` candidates with BAT to confirm against the material
    name(s) actually inside — the file's name is usually the material's own
    name (this addon's "one material per file" convention), but isn't
    guaranteed (an older file might hold a differently-named or renamed
    material), so the shortlist is a cheap prefilter, not the final answer.
    A file whose real material name scores lower than its filename did (or
    that fails to open) is simply not a match from that file; unreadable
    files are skipped rather than raised, matching every other offline scan
    in this codebase."""
    by_filename = []
    for f in files:
        s = score_material_name(wanted, pathlib.Path(f).stem)
        if s is not None:
            by_filename.append((s, pathlib.Path(f)))
    by_filename.sort(key=lambda t: t[0], reverse=True)

    best: tuple[pathlib.Path, str, float] | None = None
    for _file_score, f in by_filename[:shortlist]:
        try:
            names = list_material_names(f)
        except Exception:
            continue
        for name in names:
            s = score_material_name(wanted, name)
            if s is not None and (best is None or s > best[2]):
                best = (f, name, s)
    return best


__all__ = [
    "make_matcher", "list_material_names", "find_materials",
    "score_material_name", "material_name_confidence", "best_material_match",
]
