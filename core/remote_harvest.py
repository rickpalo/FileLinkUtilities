"""Flatten v2 -- harvesting a REMOTE override's properties without touching
the live session (docs/TODO.md Group 11 #47).

Confirmed via a throwaway probe (2026-06-27, ``tests/probe_remote_override_link.py``):
``bpy.data.libraries.load()`` never exposes a Library Override object (or
anything already reached through a link) -- only truly-local IDs are listed.
So the only way to read a remote override's full property list is to
actually open the file that owns it -- in a SEPARATE background Blender
process, never the live session, the same technique ``core.dryrun`` already
uses for render warnings.

Kept bpy-free and unit-tested. The generated script text is plain bpy calls
with zero dependency on the AssetDoctor package, so it runs standalone in the
subprocess regardless of how AssetDoctor itself happens to be installed
there. It re-derives the same property list + reference a LOCAL flatten
already gets via ``ops.linkchain.read_live_override_properties``/
``_live_override_reference`` -- duplicated here deliberately (those live in
a bpy-importing ops module, not embeddable as generated script text) rather
than introducing a fragile sys.path/import dance into the subprocess.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .linkchain import OverrideProperty, OverrideReference


@dataclass(frozen=True)
class HarvestResult:
    """One donor object's harvested override state, or ``found=False`` when
    it wasn't there at all (renamed/deleted since the census ran) or wasn't
    actually an override (shouldn't happen given the census already
    classified it, but fail safe rather than crash the batch)."""

    name: str
    found: bool
    reference: OverrideReference | None = None
    properties: tuple[OverrideProperty, ...] = ()


def group_by_source_file(items: list[tuple[str, str]]) -> dict[str, list[str]]:
    """``[(name, source_file), ...] -> {source_file: [name, ...]}`` so the
    caller opens each donor file exactly ONCE per batch, regardless of how
    many remote characters in this apply happen to live in it -- the same
    "one open does both" cost-saving the offline census itself already
    applies (``ops.linkchain.scan_and_classify``). Order-preserving and
    de-duplicating within each file."""
    out: dict[str, list[str]] = {}
    for name, source_file in items:
        bucket = out.setdefault(source_file, [])
        if name not in bucket:
            bucket.append(name)
    return out


def build_harvest_script(names: list[str], out_path: str) -> str:
    """Python source for the subprocess: for each NAME already known to be
    local to whichever .blend is passed as this process's startup file (the
    donor), read its override reference + every override property the SAME
    way ``ops.linkchain.read_live_override_properties``/
    ``_live_override_reference`` do for a LOCAL flatten -- so a remote-
    sourced flatten gets the same property fidelity, just sourced from a
    disposable background process instead of the open session."""
    return (
        "import bpy\n"
        "import json\n"
        f"NAMES = {names!r}\n"
        "\n"
        "def _coerce(value):\n"
        "    if isinstance(value, bpy.types.ID):\n"
        "        return f'{type(value).__name__}/{value.name}'\n"
        "    if isinstance(value, (str, int, float, bool)) or value is None:\n"
        "        return value\n"
        "    try:\n"
        "        return list(value)\n"
        "    except TypeError:\n"
        "        return str(value)\n"
        "\n"
        "results = {}\n"
        "for name in NAMES:\n"
        "    obj = bpy.data.objects.get(name)\n"
        "    if obj is None or obj.override_library is None:\n"
        "        results[name] = {'found': False}\n"
        "        continue\n"
        "    props = []\n"
        "    for prop in obj.override_library.properties:\n"
        "        try:\n"
        "            value = obj.path_resolve(prop.rna_path)\n"
        "        except (ValueError, AttributeError):\n"
        "            continue\n"
        "        props.append({'rna_path': prop.rna_path, 'value': _coerce(value)})\n"
        "    ref = obj.override_library.reference\n"
        "    reference = None\n"
        "    if ref is not None:\n"
        "        lib_path = ref.library.filepath if ref.library else ''\n"
        "        reference = {'name': ref.name, 'kind': type(ref).__name__, 'library': lib_path}\n"
        "    results[name] = {'found': True, 'properties': props, 'reference': reference}\n"
        "\n"
        f"with open({out_path!r}, 'w', encoding='utf-8') as fh:\n"
        "    json.dump(results, fh)\n"
    )


def build_harvest_command(blender_exe: str, blend_path: str, script_path: str) -> list[str]:
    """Argv to launch the harvest subprocess. ``--factory-startup`` for the
    same reason Dry-Run Render uses it: this only reads property values
    already saved in the file's own data, no add-on needs to be enabled to
    read them, and skipping the user's other add-ons avoids unrelated
    startup noise/slowness."""
    return [blender_exe, "--background", "--factory-startup", blend_path,
            "--python", script_path]


def parse_harvest_output(json_text: str) -> dict[str, HarvestResult]:
    """Inverse of what ``build_harvest_script`` writes."""
    raw = json.loads(json_text)
    out: dict[str, HarvestResult] = {}
    for name, entry in raw.items():
        if not entry.get("found"):
            out[name] = HarvestResult(name=name, found=False)
            continue
        ref_d = entry.get("reference")
        reference = OverrideReference(**ref_d) if ref_d else None
        properties = tuple(
            OverrideProperty(rna_path=p["rna_path"], value=p["value"])
            for p in entry.get("properties", [])
        )
        out[name] = HarvestResult(name=name, found=True, reference=reference,
                                   properties=properties)
    return out


__all__ = [
    "HarvestResult", "group_by_source_file",
    "build_harvest_script", "build_harvest_command", "parse_harvest_output",
]
