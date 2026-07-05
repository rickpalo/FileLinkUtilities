"""End-to-end F6 Layer 3 (image content dedup) check in Blender:

    blender --background --factory-startup --python tests/smoke_image_dedup.py

Covers the real operator (filelink.scan_content_dups), not just the
bpy-free core logic (already covered by tests/test_imagededup.py): content-
identical images merge regardless of name, and a .NNN-name-family pair with
genuinely different content is reported "kept separate" (docs/TODO.md #16,
2026-06-27) -- with the dims-differ vs same-dims-different-hash distinction
that only matters for images, never for the generic/material/geometry tools.
"""

import glob
import pathlib
import sys
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
_bat = glob.glob(str(REPO_ROOT / "wheels" / "blender_asset_tracer-*.whl"))
if _bat:
    sys.path.insert(0, _bat[0])
PKG = REPO_ROOT.name


def _packed_image(bpy, name, size, fill):
    """A generated image with real, packed (non-empty) pixel data so
    ``ops.image_dedup._fingerprint`` can actually hash its content."""
    img = bpy.data.images.new(name, size, size)
    img.pixels = list(fill) * (size * size)
    img.pack()
    return img


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)

        # Content-identical images under different names -> one lossless merge.
        _packed_image(bpy, "Leather_a", 4, (0.2, 0.1, 0.05, 1.0))
        _packed_image(bpy, "Leather_b", 4, (0.2, 0.1, 0.05, 1.0))

        # .NNN-name-family pair, DIFFERENT dimensions -> "kept separate",
        # likely a resolution variant.
        _packed_image(bpy, "Wood", 4, (0.5, 0.3, 0.1, 1.0))
        _packed_image(bpy, "Wood.001", 8, (0.5, 0.3, 0.1, 1.0))

        # .NNN-name-family pair, SAME dimensions but different pixel content
        # -> "kept separate", the genuinely suspicious case.
        _packed_image(bpy, "Stone", 4, (0.6, 0.6, 0.6, 1.0))
        _packed_image(bpy, "Stone.001", 4, (0.1, 0.1, 0.1, 1.0))

        res = bpy.ops.filelink.scan_content_dups("EXEC_DEFAULT")
        wm = bpy.context.window_manager
        checks.append(("scan FINISHED", res == {"FINISHED"}))
        checks.append(("content-identical images merged into one group",
                       len(wm.filelink_dup_families) == 1))
        checks.append(("merge group covers Leather_a/Leather_b",
                       set(wm.filelink_dup_families[0].members.split("\n"))
                       == {"Leather_a", "Leather_b"}))
        checks.append(("2 name-family conflicts reported (Wood + Stone)",
                       wm.filelink_dup_conflicts == 2))
        text = wm.filelink_dup_conflicts_text
        checks.append(("Wood family: different dimensions",
                       "Wood —" in text and "different dimensions" in text))
        checks.append(("Stone family: same dimensions, different content",
                       "Stone —" in text and "same dimensions, different content" in text))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("IMAGE_DEDUP_SMOKE_OK" if ok else "IMAGE_DEDUP_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("IMAGE_DEDUP_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
