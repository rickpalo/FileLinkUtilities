"""Unit tests for core.fingerprint (bpy-free, hand-built dicts).

Locks the M2 guarantees: resolution-agnostic material hashing, node
naming/order invariance, topology/param sensitivity, mesh hashing with float
tolerance, and resolution-SENSITIVE image identity.
"""

import doctest

import pytest

from core import fingerprint
from core.fingerprint import (
    fingerprint_action,
    fingerprint_image,
    fingerprint_material,
    fingerprint_mesh,
    strip_resolution_tokens,
)


# --- strip_resolution_tokens -------------------------------------------------
@pytest.mark.parametrize(
    "name,expected",
    [
        ("wood_2k", "wood"),
        ("wood_1k", "wood"),
        ("Bark-2048", "Bark"),
        ("metal.001", "metal"),
        ("Wood_4K", "Wood"),
        ("plain", "plain"),
    ],
)
def test_strip_resolution_tokens(name, expected):
    assert strip_resolution_tokens(name) == expected


def test_fingerprint_doctests():
    assert doctest.testmod(fingerprint, verbose=False).failed == 0


# --- material hashing --------------------------------------------------------
def _mat_with_image(image_base, *, metallic=0.0, keyprefix="n"):
    """Output <- Principled (Base Color from an Image Texture)."""
    img = f"{keyprefix}_img"
    bsdf = f"{keyprefix}_bsdf"
    out = f"{keyprefix}_out"
    return {
        "use_nodes": True,
        "output": out,
        "nodes": {
            img: {
                "idname": "ShaderNodeTexImage",
                "props": {"image_base": image_base, "colorspace": "sRGB",
                          "interpolation": "Linear"},
                "inputs": {},
            },
            bsdf: {
                "idname": "ShaderNodeBsdfPrincipled",
                "props": {"distribution": "GGX"},
                "inputs": {
                    "Base Color": {"from": img, "from_socket": "Color", "value": None},
                    "Metallic": {"from": None, "from_socket": None, "value": metallic},
                },
            },
            out: {
                "idname": "ShaderNodeOutputMaterial",
                "props": {},
                "inputs": {"Surface": {"from": bsdf, "from_socket": "BSDF", "value": None}},
            },
        },
    }


def test_material_1k_2k_are_equal():
    m1 = _mat_with_image("wood")  # extractor already stripped to base
    m2 = _mat_with_image("wood")
    assert fingerprint_material(m1) == fingerprint_material(m2)


def test_material_node_key_naming_is_invariant():
    a = _mat_with_image("wood", keyprefix="alpha")
    b = _mat_with_image("wood", keyprefix="zeta")
    # Different internal node keys, same topology -> same fingerprint.
    assert fingerprint_material(a) == fingerprint_material(b)


def test_material_different_image_base_differs():
    assert fingerprint_material(_mat_with_image("wood")) != fingerprint_material(
        _mat_with_image("metal")
    )


def test_material_param_difference_differs():
    assert fingerprint_material(_mat_with_image("wood", metallic=0.0)) != fingerprint_material(
        _mat_with_image("wood", metallic=1.0)
    )


def test_material_topology_difference_differs():
    base = _mat_with_image("wood")
    # Remove the image link: Base Color becomes an unlinked default instead.
    rewired = _mat_with_image("wood")
    rewired["nodes"]["n_bsdf"]["inputs"]["Base Color"] = {
        "from": None, "from_socket": None, "value": [0.8, 0.8, 0.8, 1.0]
    }
    assert fingerprint_material(base) != fingerprint_material(rewired)


def test_material_non_nodes_uses_flat():
    m = {"use_nodes": False, "flat": {"diffuse": [0.1, 0.2, 0.3]}}
    same = {"use_nodes": False, "flat": {"diffuse": [0.1, 0.2, 0.3]}}
    diff = {"use_nodes": False, "flat": {"diffuse": [0.9, 0.0, 0.0]}}
    assert fingerprint_material(m) == fingerprint_material(same)
    assert fingerprint_material(m) != fingerprint_material(diff)


def test_material_no_output_fallback_is_stable():
    m = {"use_nodes": True, "output": None, "nodes": {
        "a": {"idname": "ShaderNodeValue", "props": {}, "inputs": {}}}}
    assert fingerprint_material(m) == fingerprint_material(dict(m))


# --- mesh hashing ------------------------------------------------------------
def test_mesh_identical_match():
    m = {"vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "polygons": [[0, 1, 2]], "edges": 3}
    assert fingerprint_mesh(m) == fingerprint_mesh(dict(m))


def test_mesh_moved_vertex_differs():
    a = {"vertices": [[0, 0, 0], [1, 0, 0], [0, 1, 0]], "polygons": [[0, 1, 2]], "edges": 3}
    b = {"vertices": [[0, 0, 0], [1, 0, 0], [0, 2, 0]], "polygons": [[0, 1, 2]], "edges": 3}
    assert fingerprint_mesh(a) != fingerprint_mesh(b)


def test_mesh_float_jitter_within_tolerance_matches():
    a = {"vertices": [[0.0, 0.0, 0.0]], "polygons": [], "edges": 0}
    b = {"vertices": [[0.0000000001, 0.0, 0.0]], "polygons": [], "edges": 0}
    assert fingerprint_mesh(a) == fingerprint_mesh(b)


# --- action hashing -----------------------------------------------------------
def test_action_identical_match():
    a = {"fcurves": [{"data_path": "location", "array_index": 0,
                      "points": [[1, 0.0, "LINEAR"], [10, 2.0, "LINEAR"]]}]}
    assert fingerprint_action(a) == fingerprint_action(dict(a))


def test_action_curve_order_is_invariant():
    a = {"fcurves": [{"data_path": "location", "array_index": 0, "points": [[1, 0.0, "LINEAR"]]},
                     {"data_path": "location", "array_index": 1, "points": [[1, 1.0, "LINEAR"]]}]}
    b = {"fcurves": [{"data_path": "location", "array_index": 1, "points": [[1, 1.0, "LINEAR"]]},
                     {"data_path": "location", "array_index": 0, "points": [[1, 0.0, "LINEAR"]]}]}
    assert fingerprint_action(a) == fingerprint_action(b)


def test_action_different_keyframe_value_differs():
    a = {"fcurves": [{"data_path": "location", "array_index": 0, "points": [[1, 0.0, "LINEAR"]]}]}
    b = {"fcurves": [{"data_path": "location", "array_index": 0, "points": [[1, 5.0, "LINEAR"]]}]}
    assert fingerprint_action(a) != fingerprint_action(b)


def test_action_different_interpolation_differs():
    a = {"fcurves": [{"data_path": "location", "array_index": 0, "points": [[1, 0.0, "LINEAR"]]}]}
    b = {"fcurves": [{"data_path": "location", "array_index": 0, "points": [[1, 0.0, "BEZIER"]]}]}
    assert fingerprint_action(a) != fingerprint_action(b)


def test_action_float_jitter_within_tolerance_matches():
    a = {"fcurves": [{"data_path": "location", "array_index": 0, "points": [[1, 0.0, "LINEAR"]]}]}
    b = {"fcurves": [{"data_path": "location", "array_index": 0,
                      "points": [[1, 0.0000000001, "LINEAR"]]}]}
    assert fingerprint_action(a) == fingerprint_action(b)


# --- image identity (resolution-sensitive) -----------------------------------
def test_image_identity_same():
    img = {"filepath": "//wood.png", "size": [2048, 2048], "depth": 32,
           "source": "FILE", "colorspace": "sRGB"}
    assert fingerprint_image(img) == fingerprint_image(dict(img))


def test_image_identity_resolution_matters():
    a = {"filepath": "//wood.png", "size": [1024, 1024], "colorspace": "sRGB"}
    b = {"filepath": "//wood.png", "size": [2048, 2048], "colorspace": "sRGB"}
    assert fingerprint_image(a) != fingerprint_image(b)
