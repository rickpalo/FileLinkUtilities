"""Find objects across .blend files by name phrase, optional type, offline.

Scans every ``*.blend`` under a directory, newest file first, reading each one
OFFLINE via Blender Asset Tracer (BAT) -- no Blender launch needed. Objects live
in the DNA as ``OB`` blocks; the name is ``id.name`` (with a 2-char "OB" prefix)
and the ``type`` field encodes the object kind (mesh, curve, camera, ...).

Matching:
  * a plain phrase matches as a case-insensitive SUBSTRING ("tree" -> "Treetop");
  * a phrase containing wildcards (* ? [ ]) matches as a case-insensitive GLOB
    ("tree*", "*billboard*", "chair_??").

Object types for --type: empty, mesh, curve, surface, text, metaball, lamp/light,
camera, speaker, lightprobe, lattice, armature, grease_pencil, curves/hair,
pointcloud, volume (default: any).

Examples:
    python tools/find_objects.py "E:/BlenderSync" billboard
    python tools/find_objects.py "E:/assets" "tree*" --type mesh
    python tools/find_objects.py "E:/assets" "*cam*" --type camera --first
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import pathlib
import sys

# Friendly object-type name -> Blender DNA object 'type' code (DNA_object_types.h).
TYPE_CODES = {
    "empty": 0, "mesh": 1, "curve": 2, "surface": 3, "text": 4, "metaball": 5,
    "lamp": 10, "light": 10, "camera": 11, "speaker": 12, "lightprobe": 13,
    "lattice": 22, "armature": 25, "grease_pencil": 26, "curves": 27, "hair": 27,
    "pointcloud": 28, "volume": 29,
}
_ANY_TYPE = {"", "any", "all", "*"}

ZSTD_HINT = (
    "Blender 3.0+ saves compressed .blend files with ZStandard, which needs the\n"
    "    `zstandard` Python module. Install it with:\n\n"
    "        pip install zstandard\n"
)


def _ensure_bat_importable() -> None:
    """Put the bundled BAT wheel on sys.path if BAT isn't already importable."""
    try:
        import blender_asset_tracer.blendfile  # noqa: F401

        return
    except Exception:
        pass
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    for whl in glob.glob(str(repo_root / "wheels" / "blender_asset_tracer-*.whl")):
        sys.path.insert(0, whl)
        return


def _zstandard_available() -> bool:
    try:
        import zstandard  # noqa: F401

        return True
    except Exception:
        return False


def _is_zstd_error(exc: Exception) -> bool:
    """True when a per-file read failed only because zstandard is missing."""
    return "zstandard" in str(exc).lower()


def type_code_for(obj_type: str | None) -> int | None:
    """Resolve a friendly type name to its DNA code, or None for 'any'."""
    if obj_type is None or obj_type.lower() in _ANY_TYPE:
        return None
    try:
        return TYPE_CODES[obj_type.lower()]
    except KeyError:
        raise ValueError(
            f"unknown object type {obj_type!r}; known: {', '.join(sorted(TYPE_CODES))}"
        )


def _make_matcher(pattern: str):
    """Case-insensitive matcher: glob if the phrase has wildcards, else substring."""
    needle = pattern.lower()
    if any(ch in pattern for ch in "*?["):
        return lambda name: fnmatch.fnmatchcase(name.lower(), needle)
    return lambda name: needle in name.lower()


def iter_blend_files_newest_first(root: pathlib.Path):
    """Yield ``*.blend`` under ``root`` sorted by modification time, newest first."""
    ignore = {".git", "__pycache__", "blender_backups", "dist"}
    files = [
        p
        for p in root.rglob("*.blend")
        if not any(part in ignore for part in p.parts)
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def find_objects(blend: pathlib.Path, pattern: str, obj_type: str | None = None) -> list[str]:
    """Return names of objects in ``blend`` matching ``pattern`` (and ``obj_type``
    if given). Reads the file offline via BAT."""
    from blender_asset_tracer import blendfile

    type_code = type_code_for(obj_type)
    matches = _make_matcher(pattern)
    hits: list[str] = []
    bfile = blendfile.BlendFile(blend)
    try:
        for block in bfile.find_blocks_from_code(b"OB"):
            if type_code is not None and block.get(b"type") != type_code:
                continue
            raw = block.get((b"id", b"name"), as_str=True, default="")
            name = raw[2:] if raw[:2] == "OB" else raw  # strip the "OB" id prefix
            if matches(name):
                hits.append(name)
    finally:
        bfile.close()
    return hits


def find_mesh_objects(blend: pathlib.Path, keyword: str) -> list[str]:
    """Backwards-compatible helper: mesh objects whose name matches ``keyword``."""
    return find_objects(blend, keyword, obj_type="mesh")


def _object_type_arg(value: str) -> str:
    """argparse `type` for --type: case-insensitive, validated against Blender's
    object types, with a helpful message for non-object terms (action, NLA, …)."""
    v = value.strip().lower()
    if v in _ANY_TYPE or v in TYPE_CODES:
        return v
    valid = ", ".join(sorted(set(TYPE_CODES) | {"any"}))
    raise argparse.ArgumentTypeError(
        f"'{value}' is not a Blender object type.\n"
        f"  Valid object types: {valid}.\n"
        "  (Note: 'action'/'NLA' are animation data, and materials/images are other "
        "datablock kinds, not object types, so they can't be filtered here.)"
    )


def build_parser() -> argparse.ArgumentParser:
    """The argparse CLI parser (also gives `-h/--help` for free)."""
    parser = argparse.ArgumentParser(
        prog="find_objects.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("directory", help="folder to scan recursively for .blend files")
    parser.add_argument(
        "phrase",
        help="name to search for; plain text = case-insensitive substring, "
        "or use wildcards (* ? [ ]) for a glob match",
    )
    parser.add_argument(
        "--type", "-t", dest="obj_type", metavar="TYPE", default=None,
        type=_object_type_arg,
        help="restrict to an object type, case-insensitive (default: any)",
    )
    parser.add_argument(
        "--first", "-1", action="store_true",
        help="stop at the first (newest) match instead of listing all",
    )
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)  # handles -h/--help and bad input
    root = pathlib.Path(args.directory)
    phrase = args.phrase
    obj_type = args.obj_type
    stop_first = args.first

    if not root.is_dir():
        print(f"Not a directory: {root}")
        return 2

    _ensure_bat_importable()
    if not _zstandard_available():
        print(
            "WARNING: the `zstandard` module is not installed.\n"
            "    Compressed .blend files (the default since Blender 3.0) cannot be\n"
            "    read and would be silently skipped. " + ZSTD_HINT
        )

    type_label = f" of type {obj_type}" if obj_type and obj_type.lower() not in _ANY_TYPE else ""
    print(f"Searching for objects{type_label} matching {phrase!r} ...\n")

    total_files = matched_files = 0
    for blend in iter_blend_files_newest_first(root):
        total_files += 1
        try:
            hits = find_objects(blend, phrase, obj_type)
        except Exception as exc:  # corrupt/unreadable -> note and keep going
            if _is_zstd_error(exc):
                print(f"\nERROR reading {blend}\n    {ZSTD_HINT}")
                return 3
            print(f"  ! {blend}  ({type(exc).__name__}: {exc})")
            continue
        if hits:
            matched_files += 1
            print(f"{blend}")
            for name in hits:
                print(f"    {name}")
            if stop_first:
                print("\nStopped at first match (--first).")
                return 0

    print(
        f"\nScanned {total_files} .blend file(s); "
        f"{matched_files} contained an object matching {phrase!r}{type_label}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
