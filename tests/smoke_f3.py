"""End-to-end F3 check in Blender:

    blender --background --factory-startup --python tests/smoke_f3.py

Builds a 1K and a 2K variant of the same material (identical graph, different
texture resolution), each used by an object. Asserts they cluster, the 2K wins
the canonical (highest res), and after Apply the 1K material is gone and its
object's slot now points at the 2K material. Also checks a whitelist override.
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


def _wood_mat(bpy, name, image):
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


def _obj_with(bpy, name, mat):
    obj = bpy.data.objects.new(name, bpy.data.meshes.new(name + "ME"))
    obj.data.materials.append(mat)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()
    f3 = __import__(f"{PKG}.core.f3_materials", fromlist=["build_dedup_plan"])
    gather = __import__(f"{PKG}.ops.material_dedup", fromlist=["_gather"])._gather

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        img1 = bpy.data.images.new("wood_1k", 1024, 1024)
        img2 = bpy.data.images.new("wood_2k", 2048, 2048)
        m1 = _wood_mat(bpy, "Wood1K", img1)
        m2 = _wood_mat(bpy, "Wood2K", img2)
        o1 = _obj_with(bpy, "A", m1)
        _obj_with(bpy, "B", m2)

        items, _ = gather(bpy.context)
        report, plan = f3.build_dedup_plan(items)
        checks.append(("one duplicate group", len(plan) == 1))
        if plan:
            checks.append(("canonical is the 2K material", plan[0]["canonical"] == "Wood2K"))
            checks.append(("victim is the 1K material", plan[0]["victims"] == ["Wood1K"]))

        # Whitelist override flows through choose_canonical.
        _r, wplan = f3.build_dedup_plan(items, whitelist=["Wood1K"])
        checks.append(("whitelist forces 1K canonical", wplan[0]["canonical"] == "Wood1K"))

        # Apply the default plan via the operator.
        res = bpy.ops.assetdoctor.material_dedup("EXEC_DEFAULT", apply=True)
        names = set(bpy.data.materials.keys())
        checks.append(("apply FINISHED", res == {"FINISHED"}))
        checks.append(("Wood1K removed", "Wood1K" not in names))
        checks.append(("Wood2K kept", "Wood2K" in names))
        checks.append(("object A repointed to Wood2K",
                       o1.data.materials[0] is not None and o1.data.materials[0].name == "Wood2K"))

        # docs/TODO.md #16 (2026-06-27): a .NNN-name-family pair with genuinely
        # DIFFERENT content (different images -> different fingerprints) should
        # be reported "kept separate," not silently dropped.
        img3 = bpy.data.images.new("rock_a", 64, 64)
        img4 = bpy.data.images.new("rock_b", 64, 64)
        m3 = _wood_mat(bpy, "Stone", img3)
        m4 = _wood_mat(bpy, "Stone.001", img4)
        _obj_with(bpy, "S1", m3)
        _obj_with(bpy, "S2", m4)

        res_conflict = bpy.ops.assetdoctor.material_dedup("EXEC_DEFAULT", apply=False)
        wm = bpy.context.window_manager
        checks.append(("conflict scan FINISHED", res_conflict == {"FINISHED"}))
        checks.append(("differing-content name-family flagged as kept separate",
                       wm.assetdoctor_mat_conflicts >= 1 and "Stone" in wm.assetdoctor_mat_conflicts_text
                       and "differing content" in wm.assetdoctor_mat_conflicts_text))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("F3_SMOKE_OK" if ok else "F3_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("F3_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
