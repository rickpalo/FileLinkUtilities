"""Examine Library node-graph confidence, end-to-end in Blender:

    blender --background --factory-startup --python tests/smoke_examine_library.py

Links two materials from a throwaway source .blend into a session that already
has LOCAL materials of the same name — one with an IDENTICAL node graph (just a
different texture resolution, to also prove the comparison stays
resolution-agnostic), one with a genuinely DIFFERENT graph. Runs the real
Examine Library populate step (`ops.examine_library._populate_examine_rows`)
and checks each row's `graph_match` lands on "identical"/"differs" rather than
just trusting the name match.
"""

import glob
import pathlib
import sys
import tempfile
import traceback

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))
_bat = glob.glob(str(REPO_ROOT / "wheels" / "blender_asset_tracer-*.whl"))
if _bat:
    sys.path.insert(0, _bat[0])
PKG = REPO_ROOT.name


def _textured_mat(bpy, name, image):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    tex = tree.nodes.new("ShaderNodeTexImage")
    tex.image = image
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _emission_mat(bpy, name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    emit = tree.nodes.new("ShaderNodeEmission")
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    return mat


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()
    examine = __import__(f"{PKG}.ops.examine_library", fromlist=["_populate_examine_rows"])

    checks = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = str(pathlib.Path(tmp) / "source.blend")

            # Build the SOURCE file: "Shared" (textured) and "Diff" (emission).
            bpy.ops.wm.read_factory_settings(use_empty=True)
            img_1k = bpy.data.images.new("tex_1k", 1024, 1024)
            _textured_mat(bpy, "Shared", img_1k)
            _emission_mat(bpy, "Diff")
            bpy.ops.wm.save_as_mainfile(filepath=source_path)

            # Fresh session with LOCAL materials of the same names: "Shared" has
            # an identical graph (different res texture); "Diff" has a different
            # graph (Principled BSDF instead of Emission).
            bpy.ops.wm.read_factory_settings(use_empty=True)
            img_2k = bpy.data.images.new("tex_2k", 2048, 2048)
            _textured_mat(bpy, "Shared", img_2k)
            _textured_mat(bpy, "Diff", img_2k)

            with bpy.data.libraries.load(source_path, link=True) as (data_from, data_to):
                data_to.materials = list(data_from.materials)
            linked = [m for m in bpy.data.materials if m.library is not None]
            checks.append(("two materials linked", len(linked) == 2))
            library = linked[0].library if linked else None

            n = examine._populate_examine_rows(bpy.context, library)
            checks.append(("two rows populated", n == 2))

            rows = {r.name: r for r in bpy.context.window_manager.filelink_examine_rows}
            shared, diff = rows.get("Shared"), rows.get("Diff")
            checks.append(("Shared row found", shared is not None))
            checks.append(("Diff row found", diff is not None))
            if shared is not None:
                checks.append(("Shared suggested local", shared.suggested_kind == "local"))
                checks.append(("Shared graph identical", shared.graph_match == "identical"))
            if diff is not None:
                checks.append(("Diff suggested local", diff.suggested_kind == "local"))
                checks.append(("Diff graph differs", diff.graph_match == "differs"))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("EXAMINE_SMOKE_OK" if ok else "EXAMINE_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("EXAMINE_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
