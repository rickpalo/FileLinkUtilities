"""Unit tests for core.resource estimation + formatting."""

from core.resource import (
    human_bytes,
    image_estimate,
    mesh_estimate,
    peak_process_ram_bytes,
)


def test_image_estimate_8bit_rgba():
    # 1024x1024, 32 bits/px (8-bit RGBA) = 4 MiB RAM, ~5.33 MiB VRAM.
    est = image_estimate({"width": 1024, "height": 1024, "depth": 32})
    assert est["ram"] == 1024 * 1024 * 4
    assert est["vram"] == int(est["ram"] * 4 / 3)


def test_image_estimate_float_is_larger():
    rgba8 = image_estimate({"width": 512, "height": 512, "depth": 32})
    rgba32f = image_estimate({"width": 512, "height": 512, "depth": 128})
    assert rgba32f["ram"] == rgba8["ram"] * 4


def test_image_estimate_empty():
    assert image_estimate({"width": 0, "height": 0, "depth": 0}) == {"ram": 0, "vram": 0}


def test_mesh_estimate_scales_with_counts():
    small = mesh_estimate({"verts": 10, "edges": 10, "loops": 10, "polys": 5})
    big = mesh_estimate({"verts": 1000, "edges": 1000, "loops": 1000, "polys": 500})
    assert big["ram"] > small["ram"] > 0
    assert big["vram"] == 1000 * 32


def test_peak_process_ram_is_positive():
    # This process is using memory, so the OS query should return a positive value
    # on supported platforms (Windows/Linux/macOS).
    assert peak_process_ram_bytes() > 0


def test_human_bytes():
    assert human_bytes(0) == "0 B"
    assert human_bytes(512) == "512 B"
    assert human_bytes(1536) == "1.5 KB"
    assert human_bytes(5 * 1024 * 1024) == "5.0 MB"
    assert human_bytes(3 * 1024 ** 3) == "3.0 GB"
