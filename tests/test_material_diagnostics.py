"""Unit tests for core.material_diagnostics (bpy-free)."""

from core.material_diagnostics import (
    COMBINED_SENTINEL,
    NO_SURFACE,
    build_empty_slot_findings,
    build_material_diagnostics_report,
    build_node_link_findings,
    build_shader_type_findings,
    classify_shader_label,
    is_mix_idname,
)


def test_classify_known_bsdf():
    assert classify_shader_label("ShaderNodeBsdfPrincipled") == "Principled BSDF"
    assert classify_shader_label("ShaderNodeEmission") == "Emission"


def test_classify_mixed_shader():
    assert classify_shader_label("ShaderNodeMixShader") == "Mixed Shader"
    assert classify_shader_label("ShaderNodeAddShader") == "Mixed Shader"


def test_classify_node_group_names_the_tree():
    assert classify_shader_label("ShaderNodeGroup", "MyToonShader") == "Node Group: MyToonShader"
    assert classify_shader_label("ShaderNodeGroup", None) == "Node Group"


def test_classify_unknown_idname_falls_back_to_stripped_name():
    assert classify_shader_label("ShaderNodeCustomWeird") == "CustomWeird"


def test_classify_no_surface():
    assert classify_shader_label(None) == NO_SURFACE


def test_classify_combined_sentinel_is_its_own_bucket():
    """docs/TODO.md item 46b: a node GROUP that mixes shaders internally
    (e.g. Principled Hair + Glossy + Transparent) is a distinct bucket from
    both a plain Node Group AND a direct-at-the-surface Mixed Shader."""
    assert classify_shader_label(COMBINED_SENTINEL) == "Combined Shader"
    assert classify_shader_label(COMBINED_SENTINEL) != classify_shader_label("ShaderNodeMixShader")


def test_is_mix_idname():
    assert is_mix_idname("ShaderNodeMixShader")
    assert is_mix_idname("ShaderNodeAddShader")
    assert not is_mix_idname("ShaderNodeBsdfPrincipled")


def test_shader_type_findings_grouped_and_sorted():
    labels = {"Wood": "Principled BSDF", "Metal": "Principled BSDF", "Glow": "Emission"}
    findings = build_shader_type_findings(labels)
    assert all(f.category == "shader_type" for f in findings)
    by_message = {f.message: f.items for f in findings}
    assert "Emission (1 material(s))" in by_message
    assert by_message["Emission (1 material(s))"] == ["Material/Glow"]
    assert "Principled BSDF (2 material(s))" in by_message
    assert by_message["Principled BSDF (2 material(s))"] == ["Material/Metal", "Material/Wood"]


def test_node_link_findings_cover_both_kinds():
    findings = build_node_link_findings(
        invalid_links=[("Wood", "Mix.001", "Base Color")],
        missing_image_nodes=[("Metal", "Image Texture", "rust.png")],
    )
    assert len(findings) == 2
    assert all(f.category == "node_link_issue" for f in findings)
    assert findings[0].message == "Wood: broken link into 'Mix.001' → Base Color"
    assert findings[0].items == ["Material/Wood"]
    assert findings[1].message == "Metal: Image Texture node 'Image Texture' uses missing image 'rust.png'"
    assert findings[1].items == ["Material/Metal"]


def test_empty_slot_findings():
    findings = build_empty_slot_findings([("Cube", 1), ("Sphere", 0)])
    assert len(findings) == 2
    assert findings[0].category == "empty_slot"
    assert findings[0].message == "Cube: material slot 1 is empty"
    assert findings[0].items == ["Object/Cube"]


def test_full_report_nothing_found_is_clean():
    report = build_material_diagnostics_report({}, [], [], [])
    assert len(report.findings) == 1
    assert report.findings[0].category == "clean"


def test_full_report_combines_all_three_categories():
    report = build_material_diagnostics_report(
        {"Wood": "Principled BSDF"},
        [("Wood", "Mix.001", "Base Color")],
        [],
        [("Cube", 0)],
    )
    cats = {f.category for f in report.findings}
    assert cats == {"shader_type", "node_link_issue", "empty_slot"}
    assert report.feature == "MATDIAG"
