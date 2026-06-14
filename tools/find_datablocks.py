"""Find datablocks across .blend files by name, offline.

Scans every ``*.blend`` under a directory (newest first), reading each one
OFFLINE via Blender Asset Tracer (BAT) -- no Blender launch needed. Searches one
datablock KIND (objects, actions, materials, meshes, images, ...) by name; for
objects you can further narrow by object type (mesh, camera, ...).

Matching:
  * a plain phrase matches as a case-insensitive SUBSTRING ("walk" -> "WalkCycle");
  * a phrase with wildcards (* ? [ ]) matches as a case-insensitive GLOB.

--kind  datablock kind to search, case-insensitive (default: object): object,
        action, material, mesh, image, world, collection, scene, texture,
        node_group, armature, curve, camera, light/lamp, speaker, lattice,
        metaball, sound.
--type  object SUB-type filter, only with --kind object (default: any): empty,
        mesh, curve, surface, text, metaball, lamp/light, camera, speaker,
        lightprobe, lattice, armature, grease_pencil, curves/hair, pointcloud,
        volume.

Examples:
    python tools/find_datablocks.py "E:/proj" walk --kind action
    python tools/find_datablocks.py "E:/proj" "wood*" --kind material
    python tools/find_datablocks.py "E:/proj" "tree*" --type mesh
    python tools/find_datablocks.py "E:/proj" "*cam*" --type camera --first
"""

from __future__ import annotations

import argparse
import fnmatch
import glob
import pathlib
import sys

# Friendly datablock-kind name -> Blender DNA ID block code (DNA_ID.h ID_* codes).
KIND_CODES = {
    "object": b"OB", "action": b"AC", "material": b"MA", "mesh": b"ME",
    "image": b"IM", "world": b"WO", "collection": b"GR", "scene": b"SC",
    "texture": b"TE", "node_group": b"NT", "armature": b"AR", "curve": b"CU",
    "camera": b"CA", "light": b"LA", "lamp": b"LA", "speaker": b"SK",
    "lattice": b"LT", "metaball": b"MB", "sound": b"SO",
}

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
    """Resolve a friendly object-type name to its DNA code, or None for 'any'."""
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


def _find_by_code(blend: pathlib.Path, pattern: str, code: bytes) -> list[str]:
    """Names of datablocks of DNA ``code`` in ``blend`` matching ``pattern``.
    The 2-char ID code prefix (e.g. 'AC', 'MA') is stripped from each name."""
    from blender_asset_tracer import blendfile

    matches = _make_matcher(pattern)
    prefix = code.decode("ascii")
    hits: list[str] = []
    bfile = blendfile.BlendFile(blend)
    try:
        for block in bfile.find_blocks_from_code(code):
            raw = block.get((b"id", b"name"), as_str=True, default="")
            name = raw[len(prefix):] if raw.startswith(prefix) else raw
            if matches(name):
                hits.append(name)
    finally:
        bfile.close()
    return hits


def find_objects(blend: pathlib.Path, pattern: str, obj_type: str | None = None) -> list[str]:
    """Names of OBJECTS in ``blend`` matching ``pattern`` (and ``obj_type`` if
    given). Object-specific because it can filter on the OB 'type' field."""
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


def find_in_blend(blend: pathlib.Path, pattern: str, kind: str = "object",
                  obj_type: str | None = None) -> list[str]:
    """Dispatch: objects (with optional sub-type) or any other datablock KIND."""
    if kind == "object":
        return find_objects(blend, pattern, obj_type)
    try:
        code = KIND_CODES[kind]
    except KeyError:
        raise ValueError(f"unknown datablock kind {kind!r}; known: {', '.join(sorted(KIND_CODES))}")
    return _find_by_code(blend, pattern, code)


def _kind_arg(value: str) -> str:
    """argparse `type` for --kind: case-insensitive, validated datablock kind."""
    v = value.strip().lower()
    if v in KIND_CODES:
        return v
    valid = ", ".join(sorted(set(KIND_CODES)))
    raise argparse.ArgumentTypeError(
        f"'{value}' is not a searchable datablock kind.\n  Valid kinds: {valid}."
    )


def _object_type_arg(value: str) -> str:
    """argparse `type` for --type: case-insensitive, validated object sub-type."""
    v = value.strip().lower()
    if v in _ANY_TYPE or v in TYPE_CODES:
        return v
    valid = ", ".join(sorted(set(TYPE_CODES) | {"any"}))
    raise argparse.ArgumentTypeError(
        f"'{value}' is not a Blender object sub-type.\n"
        f"  Valid object types: {valid}.\n"
        "  (To search non-objects like actions or materials, use --kind instead.)"
    )


def build_parser() -> argparse.ArgumentParser:
    """The argparse CLI parser (also gives `-h/--help` for free)."""
    parser = argparse.ArgumentParser(
        prog="find_datablocks.py",
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
        "--kind", "-k", dest="kind", metavar="KIND", default="object",
        type=_kind_arg,
        help="datablock kind to search, case-insensitive (default: object). "
        "e.g. object, action, material, mesh, image, ...",
    )
    parser.add_argument(
        "--type", "-t", dest="obj_type", metavar="TYPE", default=None,
        type=_object_type_arg,
        help="object SUB-type filter, only with --kind object (default: any)",
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
    kind = args.kind
    obj_type = args.obj_type
    stop_first = args.first

    if not root.is_dir():
        print(f"Not a directory: {root}")
        return 2
    if kind != "object" and obj_type:
        print(f"Note: --type {obj_type!r} only applies to --kind object; ignoring it.\n")
        obj_type = None

    _ensure_bat_importable()
    if not _zstandard_available():
        print(
            "WARNING: the `zstandard` module is not installed.\n"
            "    Compressed .blend files (the default since Blender 3.0) cannot be\n"
            "    read and would be silently skipped. " + ZSTD_HINT
        )

    type_label = f" of type {obj_type}" if obj_type and obj_type.lower() not in _ANY_TYPE else ""
    print(f"Searching for {kind} datablocks{type_label} matching {phrase!r} ...\n")

    total_files = matched_files = 0
    for blend in iter_blend_files_newest_first(root):
        total_files += 1
        try:
            hits = find_in_blend(blend, phrase, kind, obj_type)
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
        f"\nScanned {total_files} .blend file(s); matched {phrase!r} "
        f"({kind}{type_label}) in {matched_files}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
