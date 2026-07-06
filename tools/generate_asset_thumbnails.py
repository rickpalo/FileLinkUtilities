"""Batch-render asset thumbnails for every Models/*.blend and materials/*.blend
file under a library root, fully headless (bpy.ops.render.render, NOT the
built-in Asset Browser "Generate Preview" -- that one crashes on some
machines when it has to background-load other files for a cross-file batch).

Two render pipelines:
  * Models:     find the file's asset-marked Collection, frame it with a
                bbox-driven camera + 3-light rig + transparent background,
                render, inject the render into the collection's own preview.
  * Materials:  append a user-supplied "material display studio" .blend
                (a Scene with a hero object + logo/text/floor dressing already
                lit), swap the candidate material onto the studio's swap-
                target objects, render, inject into the material's preview,
                then fully purge every appended studio datablock so nothing
                from the studio gets saved into the material file.

Known limitations (see docs/TODO or ask -- accepted tradeoffs, not bugs):
  * A single fixed camera angle for models means thin/frame-shaped objects
    (chair frames, sword blades) can render as a flat, low-detail silhouette.
  * Particle-only assets and collision-shape proxies have no real mesh
    bounding box / visible material, so their renders come out empty -- this
    script detects that (near-zero bbox radius, or a near-fully-transparent
    render) and skips injecting a preview rather than saving a blank one.
  * A material file can have MORE THAN ONE asset-marked material if it was
    split from a bundle carrying leftover staging-rig materials (commonly
    named Floor/Left_Light/R_Light/T_Light) -- this script picks correctly by
    matching the candidate material's name against the file's own basename,
    but the spurious extra asset-marks are a separate data-quality issue this
    script does NOT fix (see tools/find_multi_asset_materials.py).

Usage (run FROM Blender, not plain python -- needs bpy):
    blender -b --python tools/generate_asset_thumbnails.py -- \\
        --library "D:\\BlenderLibraries\\LocalLibrary" \\
        --studio "D:\\BlenderLibraries\\LocalLibrary\\materials\\MaterialDisplayStudio.blend" \\
        [--models-only] [--materials-only] [--limit N] [--dry-run] \\
        [--log "D:\\BlenderReorg_Audit\\thumbnail_batch_log.csv"]
"""
from __future__ import annotations

import argparse
import csv
import glob
import math
import os
import sys
import traceback

import bpy
from mathutils import Vector

SWAP_TARGETS = ("Base", "SolidModel", "floorModel")
_HELPER_MATERIAL_NAMES = {"floor", "left_light", "r_light", "t_light"}
_EMPTY_RENDER_ALPHA_FRACTION = 0.005  # below this, treat the render as empty


def _parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--library", required=True, help=r"Library root, e.g. D:\BlenderLibraries\LocalLibrary")
    p.add_argument("--studio", required=True, help="Path to the MaterialDisplayStudio.blend template")
    p.add_argument("--models-only", action="store_true")
    p.add_argument("--materials-only", action="store_true")
    p.add_argument("--limit", type=int, default=0, help="Process at most N files per pipeline (0 = no limit)")
    p.add_argument("--offset", type=int, default=0, help="Skip the first N files per pipeline (for chunked/resumed runs)")
    p.add_argument("--count", type=int, default=0, help="Process at most N files starting at --offset (0 = to the end)")
    p.add_argument("--dry-run", action="store_true", help="Render + report but never save any file")
    p.add_argument("--log", default=None, help="CSV path for the run log (default: <library>/thumbnail_batch_log.csv); appended to, not overwritten, so chunked runs accumulate one log")
    return p.parse_args(argv)


# ---------------------------------------------------------------- discovery

def find_model_files(library_root):
    return sorted(glob.glob(os.path.join(library_root, "Models", "**", "*.blend"), recursive=True))


def find_material_files(library_root, studio_path):
    studio_norm = os.path.normcase(os.path.abspath(studio_path))
    files = glob.glob(os.path.join(library_root, "materials", "**", "*.blend"), recursive=True)
    return sorted(f for f in files if os.path.normcase(os.path.abspath(f)) != studio_norm)


# ------------------------------------------------------------- asset lookup

def find_asset_collection():
    for c in bpy.data.collections:
        if getattr(c, "asset_data", None) is not None:
            return c
    return None


def find_asset_material(basename_hint):
    """Returns (material_or_None, other_asset_marked_names). Prefers an exact
    (case-insensitive) match against the file's own basename; falls back to
    excluding known staging-rig helper names (Floor/Left_Light/R_Light/
    T_Light) if exactly one non-helper candidate remains; otherwise picks the
    first candidate and reports the rest so the caller can log the ambiguity."""
    candidates = [m for m in bpy.data.materials if getattr(m, "asset_data", None) is not None]
    if not candidates:
        return None, []
    if len(candidates) == 1:
        return candidates[0], []
    target = basename_hint.strip().lower()
    for m in candidates:
        if m.name.strip().lower() == target:
            return m, [c.name for c in candidates if c is not m]
    non_helper = [m for m in candidates if m.name.strip().lower() not in _HELPER_MATERIAL_NAMES]
    if len(non_helper) == 1:
        return non_helper[0], [c.name for c in candidates if c is not non_helper[0]]
    return candidates[0], [c.name for c in candidates if c is not candidates[0]]


def world_bbox(objects):
    mn = Vector((math.inf, math.inf, math.inf))
    mx = Vector((-math.inf, -math.inf, -math.inf))
    any_pts = False
    for obj in objects:
        if not hasattr(obj, "bound_box"):
            continue
        for corner in obj.bound_box:
            p = obj.matrix_world @ Vector(corner)
            mn.x, mn.y, mn.z = min(mn.x, p.x), min(mn.y, p.y), min(mn.z, p.z)
            mx.x, mx.y, mx.z = max(mx.x, p.x), max(mx.y, p.y), max(mx.z, p.z)
            any_pts = True
    if not any_pts:
        return None
    return mn, mx


def _render_is_empty(png_path):
    img = bpy.data.images.load(png_path)
    try:
        pixels = img.pixels[:]
        if len(pixels) < 4:
            return True
        alphas = pixels[3::4]
        lit = sum(1 for a in alphas if a > 0.02)
        return (lit / len(alphas)) < _EMPTY_RENDER_ALPHA_FRACTION
    finally:
        bpy.data.images.remove(img)


# ------------------------------------------------------------------ models

def render_model(path, log_row):
    bpy.ops.wm.open_mainfile(filepath=path)
    bpy.context.view_layer.update()  # matrix_world reads stale (identity) right after open

    coll = find_asset_collection()
    if coll is None:
        log_row(path, "skip", "no asset-marked collection")
        return
    objs = [o for o in coll.all_objects]
    bb = world_bbox(objs)
    if bb is None:
        log_row(path, "skip", "no bound_box data (e.g. particles/empties only)")
        return
    mn, mx = bb
    center = (mn + mx) / 2
    size = mx - mn
    radius = max(size.length / 2, 0.01)
    if radius < 0.02:
        log_row(path, "skip", f"bbox radius too small ({radius:.4f}) -- likely a proxy/helper mesh")
        return

    scene = bpy.data.scenes.new("ThumbRenderScene")
    for o in objs:
        scene.collection.objects.link(o)

    world = bpy.data.worlds.new("ThumbWorld")
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.6, 0.6, 0.65, 1.0)
    bg.inputs[1].default_value = 0.8
    scene.world = world
    scene.render.film_transparent = True

    cam_data = bpy.data.cameras.new("ThumbCam")
    cam_data.lens = 50
    cam_obj = bpy.data.objects.new("ThumbCam", cam_data)
    scene.collection.objects.link(cam_obj)
    direction = Vector((1, -1.4, 0.9)).normalized()
    fov = 2 * math.atan(18 / cam_data.lens)
    distance = radius / math.sin(fov / 2) * 1.35
    cam_obj.location = center + direction * distance
    look_dir = (center - cam_obj.location).normalized()
    cam_obj.rotation_euler = look_dir.to_track_quat('-Z', 'Y').to_euler()
    scene.camera = cam_obj

    sun_data = bpy.data.lights.new("ThumbSun", type='SUN')
    sun_data.energy = 3.0
    sun_obj = bpy.data.objects.new("ThumbSun", sun_data)
    sun_obj.rotation_euler = (math.radians(55), 0, math.radians(35))
    scene.collection.objects.link(sun_obj)

    fill_data = bpy.data.lights.new("ThumbFill", type='SUN')
    fill_data.energy = 1.0
    fill_obj = bpy.data.objects.new("ThumbFill", fill_data)
    fill_obj.rotation_euler = (math.radians(60), 0, math.radians(-140))
    scene.collection.objects.link(fill_obj)

    rim_data = bpy.data.lights.new("ThumbRim", type='SUN')
    rim_data.energy = 1.5
    rim_obj = bpy.data.objects.new("ThumbRim", rim_data)
    rim_obj.rotation_euler = (math.radians(110), 0, math.radians(35))
    scene.collection.objects.link(rim_obj)

    scene.render.resolution_x = 256
    scene.render.resolution_y = 256
    try:
        scene.render.engine = 'BLENDER_EEVEE_NEXT'
    except TypeError:
        scene.render.engine = 'BLENDER_EEVEE'

    tmp_png = os.path.join(bpy.app.tempdir or ".", "_thumb_render.png")
    scene.render.filepath = tmp_png
    scene.render.image_settings.file_format = 'PNG'
    bpy.ops.render.render(write_still=True, scene=scene.name)

    empty = _render_is_empty(tmp_png)
    if not empty:
        img = bpy.data.images.load(tmp_png)
        coll.preview_ensure()
        coll.preview.image_size = (img.size[0], img.size[1])
        coll.preview.image_pixels_float[:] = img.pixels[:]
        bpy.data.images.remove(img)

    bpy.data.scenes.remove(scene)
    bpy.data.objects.remove(cam_obj)
    bpy.data.objects.remove(sun_obj)
    bpy.data.objects.remove(fill_obj)
    bpy.data.objects.remove(rim_obj)
    bpy.data.cameras.remove(cam_data)
    bpy.data.lights.remove(sun_data)
    bpy.data.lights.remove(fill_data)
    bpy.data.lights.remove(rim_data)
    bpy.data.worlds.remove(world)
    try:
        os.remove(tmp_png)
    except OSError:
        pass

    if empty:
        log_row(path, "skip", f"render came out empty (collection='{coll.name}', radius={radius:.3f})")
        return

    return coll.name, radius


# ---------------------------------------------------------------- materials

def render_material(path, studio_path, log_row):
    bpy.ops.wm.open_mainfile(filepath=path)
    basename_hint = os.path.splitext(os.path.basename(path))[0]
    mat, others = find_asset_material(basename_hint)
    if mat is None:
        log_row(path, "skip", "no asset-marked material")
        return
    if others:
        log_row(path, "note", f"multiple asset-marked materials, chose '{mat.name}', "
                               f"also present: {others}")

    before = {
        "scenes": set(bpy.data.scenes.keys()),
        "objects": set(bpy.data.objects.keys()),
        "meshes": set(bpy.data.meshes.keys()),
        "materials": set(bpy.data.materials.keys()),
        "lights": set(bpy.data.lights.keys()),
        "cameras": set(bpy.data.cameras.keys()),
        "worlds": set(bpy.data.worlds.keys()),
        "images": set(bpy.data.images.keys()),
    }

    with bpy.data.libraries.load(studio_path, link=False) as (data_from, data_to):
        data_to.scenes = ["Scene"]
    scene = data_to.scenes[0]

    swapped = []
    for name in SWAP_TARGETS:
        obj = scene.objects.get(name)
        if obj is not None and hasattr(obj.data, "materials") and len(obj.data.materials) > 0:
            obj.data.materials[0] = mat
            swapped.append(name)

    tmp_png = os.path.join(bpy.app.tempdir or ".", "_thumb_render.png")
    scene.render.filepath = tmp_png
    scene.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True, scene=scene.name)

    img = bpy.data.images.load(tmp_png)
    mat.preview_ensure()
    mat.preview.image_size = (img.size[0], img.size[1])
    mat.preview.image_pixels_float[:] = img.pixels[:]
    bpy.data.images.remove(img)
    try:
        os.remove(tmp_png)
    except OSError:
        pass

    def _purge(coll, before_keys):
        for name in list(coll.keys()):
            if name not in before_keys:
                coll.remove(coll[name])

    _purge(bpy.data.scenes, before["scenes"])
    _purge(bpy.data.objects, before["objects"])
    _purge(bpy.data.meshes, before["meshes"])
    _purge(bpy.data.materials, before["materials"])
    _purge(bpy.data.lights, before["lights"])
    _purge(bpy.data.cameras, before["cameras"])
    _purge(bpy.data.worlds, before["worlds"])
    _purge(bpy.data.images, before["images"])

    return mat.name, swapped


# --------------------------------------------------------------------- main

def _slice_files(files, args):
    if args.offset:
        files = files[args.offset:]
    if args.count:
        files = files[:args.count]
    elif args.limit:
        files = files[:args.limit]
    return files


def main():
    args = _parse_args()
    log_path = args.log or os.path.join(args.library, "thumbnail_batch_log.csv")
    is_new_log = not os.path.exists(log_path)
    counts = {"ok": 0, "skip": 0, "fail": 0, "note": 0}

    log_file = open(log_path, "a", newline="", encoding="utf-8")
    csv_writer = csv.writer(log_file)
    if is_new_log:
        csv_writer.writerow(["path", "status", "detail"])
        log_file.flush()

    def log_row(path, status, detail):
        counts[status] = counts.get(status, 0) + 1
        print(f"  [{status}] {path}  -- {detail}")
        csv_writer.writerow([path, status, detail])
        log_file.flush()

    do_models = not args.materials_only
    do_materials = not args.models_only

    if do_models:
        files = _slice_files(find_model_files(args.library), args)
        print(f"=== MODELS ({len(files)}) ===")
        for path in files:
            try:
                result = render_model(path, log_row)
                if result is None:
                    continue
                coll_name, radius = result
                if not args.dry_run:
                    bpy.ops.wm.save_mainfile()
                log_row(path, "ok", f"collection='{coll_name}' radius={radius:.3f}"
                                     + (" (dry-run, not saved)" if args.dry_run else ""))
            except Exception:
                log_row(path, "fail", traceback.format_exc(limit=3).replace("\n", " | "))

    if do_materials:
        files = _slice_files(find_material_files(args.library, args.studio), args)
        print(f"=== MATERIALS ({len(files)}) ===")
        for path in files:
            try:
                result = render_material(path, args.studio, log_row)
                if result is None:
                    continue
                mat_name, swapped = result
                if not args.dry_run:
                    bpy.ops.wm.save_mainfile()
                log_row(path, "ok", f"material='{mat_name}' swapped={swapped}"
                                     + (" (dry-run, not saved)" if args.dry_run else ""))
            except Exception:
                log_row(path, "fail", traceback.format_exc(limit=3).replace("\n", " | "))

    log_file.close()
    print(f"\nLog appended: {log_path}")
    print(f"this run: ok={counts['ok']}  skip={counts['skip']}  fail={counts['fail']}  note={counts['note']}")


main()
