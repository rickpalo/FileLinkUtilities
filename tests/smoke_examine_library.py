"""Examine Library node-graph confidence, end-to-end in Blender:

    blender --background --factory-startup --python tests/smoke_examine_library.py

Links two materials from a throwaway source .blend into a session that already
has LOCAL materials of the same name — one with an IDENTICAL node graph (just a
different texture resolution, to also prove the comparison stays
resolution-agnostic), one with a genuinely DIFFERENT graph. Runs the real
Examine Library populate step (`ops.examine_library._populate_examine_rows`)
and checks each row's `graph_match` lands on "identical"/"differs" rather than
just trusting the name match.

Also reproduces the real bug found live 2026-07-09 on `human_bundle.blend`:
Mesh and NodeTree rows whose name is one of Blender's own generic auto-names
(`Plane.070`, `NT*_shader.001`) got auto-merged with an unrelated same-named
local datablock, because "exact name match" alone was trusted as identity.
The Mesh case here mirrors it exactly (two differently-sized "Plane" meshes);
the NodeTree case mirrors the shader node-group side of the same crash trace.
Both assert not just `graph_match == "differs"` but that Apply Selected's
auto-touch flags (`use_suggested` / `selected`) are OFF — the actual fix, not
just the label.
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
    mat.use_fake_user = True  # 0-user datablocks are silently dropped on save
    return mat


def _emission_mat(bpy, name):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    emit = tree.nodes.new("ShaderNodeEmission")
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])
    mat.use_fake_user = True  # 0-user datablocks are silently dropped on save
    return mat


def _plane_mesh(bpy, name, size):
    """A quad mesh named ``name`` (deliberately a Blender-generic name like
    'Plane.070' in the caller) with geometry scaled by ``size`` — two
    differently-sized planes are genuinely different content that should
    never auto-merge just because they share an auto-generated name."""
    mesh = bpy.data.meshes.new(name)
    verts = [(-size, -size, 0), (size, -size, 0), (size, size, 0), (-size, size, 0)]
    mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
    mesh.update()
    mesh.use_fake_user = True  # 0-user datablocks are silently dropped on save
    return mesh


def _group_tree(bpy, name, value):
    """A minimal shader node GROUP (Group Output driven by a Value node) —
    mirrors the real crash's `NT*`-prefixed node-group datablocks. Two trees
    with different ``value`` are genuinely different content."""
    tree = bpy.data.node_groups.new(name, "ShaderNodeTree")
    tree.interface.new_socket("Val", in_out="OUTPUT", socket_type="NodeSocketFloat")
    out = tree.nodes.new("NodeGroupOutput")
    val = tree.nodes.new("ShaderNodeValue")
    val.outputs[0].default_value = value
    tree.links.new(val.outputs[0], out.inputs[0])
    tree.use_fake_user = True  # 0-user datablocks are silently dropped on save
    return tree


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()
    examine = __import__(f"{PKG}.ops.examine_library", fromlist=["_populate_examine_rows"])

    checks = []
    try:
        with tempfile.TemporaryDirectory() as tmp:
            source_path = str(pathlib.Path(tmp) / "source.blend")

            # Build the SOURCE file: "Shared"/"Diff" materials, plus Mesh and
            # NodeTree datablocks under Blender's own GENERIC auto-names —
            # "Plane.070"/"Plane.099" and "NTutil.003"/"NTutil.007" — same
            # shape as the real human_bundle.blend bug.
            bpy.ops.wm.read_factory_settings(use_empty=True)
            img_1k = bpy.data.images.new("tex_1k", 1024, 1024)
            _textured_mat(bpy, "Shared", img_1k)
            _emission_mat(bpy, "Diff")
            _plane_mesh(bpy, "Plane.070", 1.0)   # will match local content
            _plane_mesh(bpy, "Plane.099", 1.0)   # will NOT match local content
            _group_tree(bpy, "NTutil.007", 1.0)  # will NOT match local content
            bpy.ops.wm.save_as_mainfile(filepath=source_path)

            # Fresh session with LOCAL datablocks of the same names: "Shared"
            # has an identical graph (different res texture); "Diff" has a
            # different graph (Principled BSDF instead of Emission);
            # "Plane.070" is the SAME size (genuinely identical mesh);
            # "Plane.099" is a DIFFERENT size (genuinely different mesh, same
            # generic name purely by coincidence); "NTutil.007" has a
            # DIFFERENT Value node output (genuinely different node graph).
            bpy.ops.wm.read_factory_settings(use_empty=True)
            img_2k = bpy.data.images.new("tex_2k", 2048, 2048)
            _textured_mat(bpy, "Shared", img_2k)
            _textured_mat(bpy, "Diff", img_2k)
            _plane_mesh(bpy, "Plane.070", 1.0)
            _plane_mesh(bpy, "Plane.099", 5.0)
            _group_tree(bpy, "NTutil.007", 9.0)

            with bpy.data.libraries.load(source_path, link=True) as (data_from, data_to):
                data_to.materials = list(data_from.materials)
                data_to.meshes = list(data_from.meshes)
                data_to.node_groups = list(data_from.node_groups)
            linked = [m for m in bpy.data.materials if m.library is not None]
            checks.append(("two materials linked", len(linked) == 2))
            library = linked[0].library if linked else None

            n = examine._populate_examine_rows(bpy.context, library)
            # 6, not 5: linking a textured Material with link=True also pulls
            # in its Image as an indirectly-linked dependency (tex_1k).
            checks.append(("six rows populated", n == 6))

            rows = {r.name: r for r in bpy.context.window_manager.filelink_examine_rows}
            shared, diff = rows.get("Shared"), rows.get("Diff")
            checks.append(("Shared row found", shared is not None))
            checks.append(("Diff row found", diff is not None))
            if shared is not None:
                checks.append(("Shared suggested local", shared.suggested_kind == "local"))
                checks.append(("Shared graph identical", shared.graph_match == "identical"))
                checks.append(("Shared auto-applies", shared.use_suggested and shared.selected))
            if diff is not None:
                checks.append(("Diff suggested local", diff.suggested_kind == "local"))
                checks.append(("Diff graph differs", diff.graph_match == "differs"))
                checks.append(("Diff NOT auto-applied",
                              not diff.use_suggested and not diff.selected))

            same_mesh, diff_mesh = rows.get("Plane.070"), rows.get("Plane.099")
            checks.append(("Plane.070 row found", same_mesh is not None))
            checks.append(("Plane.099 row found", diff_mesh is not None))
            if same_mesh is not None:
                checks.append(("Plane.070 graph identical", same_mesh.graph_match == "identical"))
                checks.append(("Plane.070 auto-applies",
                              same_mesh.use_suggested and same_mesh.selected))
            if diff_mesh is not None:
                # The real bug: same generic name, genuinely different mesh
                # content — must be flagged AND excluded from auto-apply.
                checks.append(("Plane.099 graph differs", diff_mesh.graph_match == "differs"))
                checks.append(("Plane.099 NOT auto-applied",
                              not diff_mesh.use_suggested and not diff_mesh.selected))

            diff_tree = rows.get("NTutil.007")
            checks.append(("NTutil.007 row found", diff_tree is not None))
            if diff_tree is not None:
                checks.append(("NTutil.007 graph differs", diff_tree.graph_match == "differs"))
                checks.append(("NTutil.007 NOT auto-applied",
                              not diff_tree.use_suggested and not diff_tree.selected))

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
