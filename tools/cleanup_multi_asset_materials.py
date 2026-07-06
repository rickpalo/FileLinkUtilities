"""Clean up the multi_asset issue found by find_multi_asset_materials.py:
files where a real material sits alongside leftover staging-rig materials
(Floor/Left_Light/R_Light/T_Light) that got asset-marked too, cluttering the
Materials catalog in the Asset Browser with spurious extra tiles.

For each flagged file:
  1. Open it.
  2. For every material named Floor/Left_Light/R_Light/T_Light (case-
     insensitive) that is asset-marked: clear its asset mark AND its fake
     user (asset_clear() + use_fake_user = False).
  3. Purge any of those that are now true orphans (0 users) -- removes the
     leftover data entirely rather than just hiding it from the browser.
  4. Leaves the real (non-helper) material's own asset mark untouched.
  5. Saves the file in place.

Never touches a file that ISN'T in the input CSV's multi_asset rows, and
never touches a material that isn't one of the four known helper names --
does not guess at anything else.

Usage:
    blender -b --python tools/cleanup_multi_asset_materials.py -- \\
        --csv "D:\\BlenderReorg_Audit\\multi_asset_materials.csv" \\
        --log "D:\\BlenderReorg_Audit\\cleanup_multi_asset_materials_log.csv" \\
        [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import sys

import bpy

_HELPER_NAMES = {"floor", "left_light", "r_light", "t_light"}


def _parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", required=True, help="find_multi_asset_materials.py's output CSV")
    p.add_argument("--log", required=True)
    p.add_argument("--dry-run", action="store_true", help="Report what would change but never save")
    return p.parse_args(argv)


def load_multi_asset_files(csv_path):
    files = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        next(r)
        for row in r:
            path, issue, detail = row
            if issue == "multi_asset":
                files.append(path)
    return files


def clean_one(path, dry_run):
    bpy.ops.wm.open_mainfile(filepath=path)
    unmarked = []
    removed = []
    for m in list(bpy.data.materials):
        if m.name.strip().lower() not in _HELPER_NAMES:
            continue
        if getattr(m, "asset_data", None) is None:
            continue
        m.asset_clear()
        m.use_fake_user = False
        unmarked.append(m.name)

    # re-check users AFTER clearing fake_user -- true orphans can be purged
    for name in unmarked:
        m = bpy.data.materials.get(name)
        if m is not None and m.users == 0:
            bpy.data.materials.remove(m)
            removed.append(name)

    if unmarked and not dry_run:
        bpy.ops.wm.save_mainfile()

    return unmarked, removed


def main():
    args = _parse_args()
    files = load_multi_asset_files(args.csv)
    print(f"{len(files)} files to clean" + (" (DRY RUN)" if args.dry_run else ""))

    rows = []
    for i, path in enumerate(files, 1):
        try:
            unmarked, removed = clean_one(path, args.dry_run)
            status = "ok" if unmarked else "no_match"
            detail = f"unmarked={unmarked} removed={removed}"
            rows.append((path, status, detail))
            print(f"  [{status}] {path} -- {detail}")
        except Exception as exc:
            rows.append((path, "fail", str(exc)))
            print(f"  [fail] {path} -- {exc}")
        if i % 50 == 0:
            print(f"  ...{i}/{len(files)}")

    with open(args.log, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["path", "status", "detail"])
        w.writerows(rows)

    n_ok = sum(1 for r in rows if r[1] == "ok")
    n_nomatch = sum(1 for r in rows if r[1] == "no_match")
    n_fail = sum(1 for r in rows if r[1] == "fail")
    print(f"\nLog written: {args.log}")
    print(f"ok={n_ok}  no_match={n_nomatch}  fail={n_fail}")


main()
