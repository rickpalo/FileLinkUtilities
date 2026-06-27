"""Unit tests for core.remote_harvest (bpy-free; the generated script text
only ever runs inside the background subprocess, never here)."""

import json

from core.remote_harvest import (
    HarvestResult,
    build_harvest_command,
    build_harvest_script,
    group_by_source_file,
    parse_harvest_output,
)


def test_group_by_source_file_buckets_and_dedupes():
    items = [("CharA", "/proj/people1.blend"), ("CharB", "/proj/people1.blend"),
             ("CharC", "/proj/asset_bundle.blend"), ("CharA", "/proj/people1.blend")]
    grouped = group_by_source_file(items)
    assert grouped == {
        "/proj/people1.blend": ["CharA", "CharB"],
        "/proj/asset_bundle.blend": ["CharC"],
    }


def test_group_by_source_file_preserves_order():
    items = [("Z", "/f.blend"), ("A", "/f.blend"), ("M", "/f.blend")]
    assert group_by_source_file(items)["/f.blend"] == ["Z", "A", "M"]


def test_build_harvest_command_shape():
    cmd = build_harvest_command("/path/to/blender", "/proj/people1.blend", "/tmp/script.py")
    assert cmd == ["/path/to/blender", "--background", "--factory-startup",
                    "/proj/people1.blend", "--python", "/tmp/script.py"]


def test_build_harvest_script_embeds_names_and_out_path_as_literals():
    script = build_harvest_script(["CharA", "CharB"], "/tmp/out.json")
    assert "NAMES = ['CharA', 'CharB']" in script
    assert "open('/tmp/out.json'" in script
    # Sanity: it's plain bpy calls, never imports the addon package.
    assert "assetdoctor" not in script.lower()


def test_build_harvest_script_is_syntactically_valid_python():
    """The generated text only ever runs inside a Blender subprocess, but it
    should at least compile here -- catches a malformed template before it
    ever reaches a real (slow) subprocess launch."""
    script = build_harvest_script(["CharA"], "/tmp/out.json")
    compile(script, "<harvest_script>", "exec")


def test_parse_harvest_output_found_with_properties_and_reference():
    raw = json.dumps({
        "CharA": {
            "found": True,
            "properties": [{"rna_path": "location", "value": [1.0, 2.0, 3.0]}],
            "reference": {"name": "CharA", "kind": "Object", "library": "//human_bundle.blend"},
        }
    })
    results = parse_harvest_output(raw)
    r = results["CharA"]
    assert isinstance(r, HarvestResult)
    assert r.found is True
    assert r.reference.library == "//human_bundle.blend"
    assert r.properties[0].rna_path == "location"
    assert r.properties[0].value == [1.0, 2.0, 3.0]


def test_parse_harvest_output_not_found():
    raw = json.dumps({"GoneChar": {"found": False}})
    results = parse_harvest_output(raw)
    assert results["GoneChar"].found is False
    assert results["GoneChar"].reference is None
    assert results["GoneChar"].properties == ()


def test_parse_harvest_output_found_but_no_reference():
    raw = json.dumps({"OrphanOverride": {"found": True, "properties": [], "reference": None}})
    results = parse_harvest_output(raw)
    assert results["OrphanOverride"].found is True
    assert results["OrphanOverride"].reference is None
