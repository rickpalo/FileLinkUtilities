# File & Link Utilities — Architecture & Roadmap

## Why this exists

A multi-file Blender project accumulates asset-management debt: tangled link graphs,
near-duplicate materials at different resolutions, and data kept alive only by Fake
Users. File & Link Utilities (formerly AssetDoctor) maps, diagnoses, and cleans this for Blender 5+.

## Locked decisions

- **Engine:** BAT + bpy **hybrid**. Blender Asset Tracer parses `.blend` files offline for
  the folder-wide work (F1); live `bpy` performs in-session mutation (F2–F4).
- **Material similarity:** node-graph fingerprint (resolution- and position-agnostic) +
  image **base-name** matching after stripping resolution tokens.
- **Packaging:** standalone repo, Blender 5+ **Extension** (`blender_manifest.toml`).
- **Safety:** every mutating op is **report-first → explicit Apply**, with a timestamped
  `.blend` auto-backup before any change.

## The one fact that drives the design

**F1 is an offline batch job over many files; F2–F4 mutate the single open file.** Two
different execution worlds. So:

- `core/` is **bpy-free** and unit-testable with plain pytest. It holds the graph model,
  content fingerprinting, report serialization, and the BAT wrapper.
- `ops/` is the **only** place (besides `ui/`, `prefs.py`, top-level `__init__.py`) that
  imports `bpy`. Operators are thin: gather bpy data → hand to `core` → present a report →
  on Apply, mutate after an auto-backup.
- **Import rule:** `core` modules import each other with *relative* imports, so they
  resolve both inside Blender (as `filelink.core`) and in pytest (as top-level `core`;
  see `conftest.py`).

## Layout

```
file_link_utilities/ (dev folder: FileLinkUtilities)
├─ blender_manifest.toml   Extension manifest (blender_version_min = 5.0)
├─ __init__.py             register/unregister (thin)
├─ prefs.py                backup dir, auto-backup toggle, resolution-token regex
├─ core/                   bpy-FREE
│  ├─ report.py            Finding/Report -> JSON/CSV          [done M0]
│  ├─ graph.py             DepGraph: roots/leaves/cycles       [done M0]
│  ├─ fingerprint.py       canonical hashing; strip_resolution_tokens done; hashers M2
│  └─ blendscan.py         BAT wrapper (offline .blend reads)  [stub -> M1]
├─ ops/                    bpy operators (scaffold stubs -> per-milestone)
├─ ui/                     N-panel
└─ tests/                  pytest over core/
```

## Bundling BAT (resolved)

We bundle the **pure-Python** `blender-asset-tracer==1.20` wheel via the manifest `wheels`
list. Verified under **Blender 5.1**: `blender_asset_tracer.blendfile` and `.trace` (all we
use for dependency mapping) import even with `requests` blocked
(`tests/probe_bat_imports.py`). So we deliberately **do not** bundle BAT's `requests`
dependency chain (which would drag in a compiled, platform-specific `charset_normalizer`
wheel and break cross-platform distribution); `requests` is only for BAT's upload/pack
features we don't use, and Blender bundles it anyway if we ever do.
⚠️ A newer "BAT v2" is reportedly a standalone **Rust binary**; we stay on the pure-Python
1.x line. Fallback if a future Blender drops compatibility: the Kaitai `.blend` parser, or a
thin in-house reader for just the library (LI) blocks.

Build/validate the extension with:
`blender --command extension validate <dir>` and `blender --command extension build --source-dir <dir> --output-dir dist`.

## Feature notes

- **F1** — glob `*.blend`, read each file's links via BAT (no Blender open), build a
  `DepGraph`. Detect broken/missing links, cycles, absolute-vs-relative paths, hub vs leaf
  files. Plus a **cross-file duplication census**: fingerprint appendable datablocks
  (objects/meshes/materials) across all files and count how many are duplicated by
  characteristics. (This is about *how many copies of the same thing exist*, not about
  proving they share an append origin — origin metadata does not survive an append.)
  Export JSON / CSV / Graphviz DOT.
- **F2** — dry-run lists linked IDs + library overrides; on Apply one bulk
  `bpy.ops.object.make_local(type='ALL')` does most of the work, then per-ID
  `ID.make_local(clear_liboverride=True)` passes mop up the rest (collections / node groups /
  overrides), iterating until none remain; offer purge. Runs **modal** (progress + ESC) via the
  `localize_steps` generator. Watch: multi-user linked data, partial overrides, packed vs external.
- **F3** — fingerprint every material (local + linked), cluster by fingerprint + image
  base-name (the 1K/2K rule), pick a canonical per white/black list, `user_remap` victims,
  purge. Linked materials can be remapped *away from* but not deleted from their library —
  reported as such.
- **F4** — classify each datablock: orphan (`users == 0`) vs fake-user-only
  (`use_fake_user` with no real users). ⚠️ exact `users`-vs-fake-user semantics in Blender 5
  must be pinned by a fixture test, not memory. Group identical datablocks via
  `fingerprint`. Read-only by default; optional purge on Apply.

## Known risks (carry forward)

1. Appended-origin metadata is unrecoverable → F1 census is by characteristics, with a
   confidence note, never a guarantee of shared origin.
2. BAT distribution flux (pure-Python vs Rust v2) → pin & validate early; fallback exists.
3. Fake-user detection nuance → fixture test required.
4. Library overrides complicate make-local → resolve before localizing.
5. Purge/remap hard to fully undo → report-first + auto-backup + confirm gate.
6. Performance on big folders/textures → BAT keeps F1 fast; perceptual hashing opt-in.
7. Fingerprint stability across Blender versions → guarded by pytest fixtures.

## Milestone roadmap

- **M0 – Scaffold** ✅ repo, manifest, register/unregister, prefs, N-panel, `core.report`
  + `core.graph` implemented & tested, pytest harness.
- **M1 – F1 read-only mapping** ✅ BAT-backed `blendscan` + `DepGraph` + `f1_linkmap`
  report (broken/absolute/circular/unreadable + summary) + JSON/CSV/DOT export + operator;
  fixtures + 7 tests; verified in Blender 5.1.
- **M2 – `core/fingerprint`** ✅ material (resolution-agnostic, output-rooted recursive
  hash), mesh, image-identity hashers + `ops/extract.py` (bpy→dict) + `core/cluster.py`;
  verified in Blender 5.1 (1K==2K hash equal end-to-end). 44 tests.
- **M3 – F4** ✅ `f4_orphans` classify (verified Blender 5.1 users/fake semantics) +
  identity clusters; `ops/orphans` read-only report + optional safe purge; `ops/safety`
  auto-backup. Verified in 5.1. 50 tests.
- **M4 – F3** ✅ `f3_materials` fingerprint clusters + canonical selection (white/black list,
  local-over-linked + highest-res tie-break) + `ops/material_dedup` `user_remap`/purge Apply;
  prefs lists. Verified in 5.1 (1K/2K → 2K, slot repointed). 60 tests.
- **M5 – F2** ✅ `f2_makelocal` report + `ops/make_local` iterative
  `make_local(clear_liboverride=True)` + library purge; New File (copy+revert, default) and
  In Place modes. Discovered & worked around phantom `Library.users` (trust `user_map()`).
  Verified in 5.1. 63 tests.
- **M6 – F1** cross-file duplication census (reuses M2 hashing) + polish/exports.

## Testing philosophy

Every function gets a test. Any bug found later gets a regression test added in the same
commit. `core/` is tested outside Blender with pytest; in-session operators are tested via
headless `blender --background --python` against fixture `.blend` files (added from M1/M2).
