"""End-to-end Check Materials smoke test in Blender:

    blender --background --factory-startup --python tests/smoke_material_diagnostics.py

Builds a Principled BSDF material, an Emission material, a Mix Shader
material (both should classify as their own/"Mixed Shader" groups), a
material with an Image Texture node pointing at a file that doesn't exist on
disk, and an object with one filled + one empty material slot. Runs the real
``assetdoctor.check_materials`` operator and asserts the stashed report has
the expected shader-type groups, flags the missing-image node, and flags the
empty slot.

NOT covered here: a genuinely dangling/invalid NodeLink (Blender always
creates valid links via ``tree.links.new()`` between compatible sockets --
there's no simple Python-side way to fabricate the "socket type changed after
a version upgrade" case this checks for in real files). The report-building
side of that path is covered by ``tests/test_material_diagnostics.py``
instead (synthetic invalid_links tuples); only the bpy-side extraction is
untested against a real dangling link.
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


def main():
    import bpy

    addon = __import__(PKG)
    addon.register()

    checks = []
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)

        # Principled BSDF.
        wood = bpy.data.materials.new("Wood")
        wood.use_nodes = True
        tree = wood.node_tree
        tree.nodes.clear()
        bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
        out = tree.nodes.new("ShaderNodeOutputMaterial")
        tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

        # Emission.
        glow = bpy.data.materials.new("Glow")
        glow.use_nodes = True
        tree = glow.node_tree
        tree.nodes.clear()
        emit = tree.nodes.new("ShaderNodeEmission")
        out = tree.nodes.new("ShaderNodeOutputMaterial")
        tree.links.new(emit.outputs["Emission"], out.inputs["Surface"])

        # Mix Shader.
        mixed = bpy.data.materials.new("Mixed")
        mixed.use_nodes = True
        tree = mixed.node_tree
        tree.nodes.clear()
        b1 = tree.nodes.new("ShaderNodeBsdfDiffuse")
        b2 = tree.nodes.new("ShaderNodeBsdfGlossy")
        mix = tree.nodes.new("ShaderNodeMixShader")
        out = tree.nodes.new("ShaderNodeOutputMaterial")
        tree.links.new(b1.outputs[0], mix.inputs[1])
        tree.links.new(b2.outputs[0], mix.inputs[2])
        tree.links.new(mix.outputs["Shader"], out.inputs["Surface"])

        # Missing Image Texture node.
        rusty = bpy.data.materials.new("Rusty")
        rusty.use_nodes = True
        tree = rusty.node_tree
        tree.nodes.clear()
        img = bpy.data.images.new("rust_missing", 4, 4)
        img.source = "FILE"
        img.filepath = "//textures/definitely_does_not_exist_xyz123.png"
        tex = tree.nodes.new("ShaderNodeTexImage")
        tex.image = img
        bsdf2 = tree.nodes.new("ShaderNodeBsdfPrincipled")
        out = tree.nodes.new("ShaderNodeOutputMaterial")
        tree.links.new(tex.outputs["Color"], bsdf2.inputs["Base Color"])
        tree.links.new(bsdf2.outputs["BSDF"], out.inputs["Surface"])

        # Object with one filled + one empty material slot.
        mesh = bpy.data.meshes.new("CubeME")
        obj = bpy.data.objects.new("Cube", mesh)
        bpy.context.scene.collection.objects.link(obj)
        mesh.materials.append(wood)
        mesh.materials.append(None)

        res = bpy.ops.assetdoctor.check_materials("EXEC_DEFAULT")
        checks.append(("operator FINISHED", res == {"FINISHED"}))

        Report = __import__(f"{PKG}.core.report", fromlist=["Report"]).Report
        wm = bpy.context.window_manager
        report = Report.from_json(wm.assetdoctor_rep_matdiag)

        shader_findings = {f.message: f.items for f in report.findings if f.category == "shader_type"}
        checks.append(("Principled BSDF group has Wood",
                       any("Principled BSDF" in m and "Material/Wood" in items
                           for m, items in shader_findings.items())))
        checks.append(("Emission group has Glow",
                       any("Emission" in m and "Material/Glow" in items
                           for m, items in shader_findings.items())))
        checks.append(("Mixed Shader group has Mixed",
                       any("Mixed Shader" in m and "Material/Mixed" in items
                           for m, items in shader_findings.items())))

        link_findings = [f for f in report.findings if f.category == "node_link_issue"]
        checks.append(("missing image node flagged",
                       any("Rusty" in f.message and "rust_missing" in f.message
                           for f in link_findings)))

        slot_findings = [f for f in report.findings if f.category == "empty_slot"]
        checks.append(("empty slot flagged on Cube",
                       any("Cube" in f.message and f.items == ["Object/Cube"]
                           for f in slot_findings)))

        ok = all(p for _, p in checks)
        for label, p in checks:
            print(f"  [{'OK' if p else 'FAIL'}] {label}")
        print("MATDIAG_SMOKE_OK" if ok else "MATDIAG_SMOKE_FAIL")
        return 0 if ok else 1
    except Exception:
        traceback.print_exc()
        print("MATDIAG_SMOKE_FAIL")
        return 1
    finally:
        addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
