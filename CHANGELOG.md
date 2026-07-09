# Changelog

All notable changes to File & Link Utilities (renamed from AssetDoctor, see below). Versioning
is patch-only unless a change is flagged as major. From 0.2.x onward, entries below are grouped
by feature area rather than one per version bump (the project moved to much more frequent small
bumps) — see `docs/TODO.md` for the detailed session-by-session build history behind any entry.

Entries below [0.2.106] are kept as originally written, under the old "AssetDoctor" name and
`ASSETDOCTOR_*` identifiers, for historical accuracy — don't edit them to match the new naming.

## [0.2.117] — Fix: Examine Apply Selected's real "0 remapped" bug, plus a persistent results summary

### Fixed
- **Apply Selected could resolve the WRONG data-block and silently no-op, reporting "Made 0
  local, remapped 0" for every ticked row.** Root cause, confirmed via the v0.2.116 diagnostics
  against a real production file: `ops/examine_library.py`'s per-row apply loop looked up each
  row's target with a PLAIN-NAME lookup (`target_coll.get(row.name)`), which has no library
  disambiguation. In a heavily-merged file, a local data-block can coincidentally share the exact
  name of a linked one (Blender allows this across libraries — no forced rename), so the lookup
  had no guarantee of returning the specific linked block the row was populated from; every row
  looked "stale" even though nothing had changed since the scan. Fixed by switching to `bpy.data`'s
  `(name, filepath)` tuple lookup, which is library-qualified. Covered by a new regression test,
  `tests/smoke_examine_library_name_collision.py`, that reproduces the exact shape of the bug
  (linked + same-named local block, one Apply Selected call, asserts the linked one resolves).

### Added
- **Apply Selected's result now persists in the panel** instead of only flashing as a one-shot
  toast. Applying used to clear `filelink_examine_rows` and fall straight back to the pre-scan
  look, so a user who missed the toast (or scrolled away) had no way to tell whether anything had
  actually happened — new WindowManager string `filelink_examine_apply_summary` holds the same
  text the toast shows, drawn in the panel until the next Examine or Apply Selected call.

## [0.2.116] — Diagnostics: Examine Apply Selected's silent "0 remapped" now self-explains

### Changed
- **`Apply Selected`'s "Made X local, remapped Y" toast now reports WHY when rows were skipped**
  (`N stale, M unresolved — see console for details`), and prints a line per skipped row naming
  the exact reason (row already changed since scan vs. no resolvable target, with the row's
  suggestion fields). Found live, 2026-07-09: a second Apply Selected pass on `human_bundle.blend`
  reported "Made 0 local, remapped 0" for 46 rows that had all shown an in-memory match moments
  earlier, and there was no way to tell from the toast alone which of the two skip conditions in
  `ops/examine_library.py::FILELINK_OT_examine_apply_selected` every row hit, or why. Not a fix —
  the next occurrence's console output will point at the exact cause instead of requiring another
  live repro.

## [0.2.115] — Fix: Examine Library could suggest remapping onto ANOTHER broken library's placeholder

### Fixed
- **Examine Library's in-memory suggestion pool could offer a candidate that was itself a missing
  placeholder from a DIFFERENT broken library** — real bug found live on a production file with
  two libraries both unreadable on disk (`human_bundle.blend`, `Asset_bundle.blend`): each can
  independently hold a same-BASE-name missing block purely by coincidence of Blender's own
  `.NNN` dedup-suffix numbering (e.g. one wants `hanger.001`, an unrelated asset in the OTHER
  broken library separately wants `hanger.002` — the "numbered" match tier strips both to base
  `hanger` and calls it a match). Remapping one placeholder onto another placeholder doesn't fix
  anything — the link is still broken, just pointed at a different broken thing — and the apply
  silently "succeeds" with zero visible effect, which is how a user's staged Apply Selected could
  report success yet leave the data-block count completely unchanged after a reload.
  `ops/examine_library.py::_in_memory_pools` now skips any candidate that is itself
  `is_missing`. New end-to-end smoke test (`tests/smoke_examine_library_missing_collision.py`)
  reproduces the exact two-broken-library collision and confirms no suggestion is offered.
- **`core/imagematch.py::best_match`** now skips (and logs) a single candidate that raises
  during scoring instead of aborting the whole modal search — a real, never-reproduced TypeError
  surfaced live mid-scan against a multi-thousand-file library search and cost the user every
  match already staged. New pytest coverage.
- **`ops/orphans.py`'s Find Orphans** now prints the exact datablock name right before each risky
  fingerprint read — a real `EXCEPTION_ACCESS_VIOLATION` crash (2026-07-09, `PSM_Stage_v5.2`)
  turned out to be on a LOCAL mesh, a corruption class the existing `datablock_risk_reason`
  mitigation never covered (its `is_missing`/`override_library` checks only ever apply to linked
  IDs, but the fingerprinting branch that crashed only runs on local data). A native access
  violation can't be caught with try/except, so this is a breadcrumb, not a fix — the next
  occurrence's console output will end with the exact datablock name instead of an anonymous
  crash log.

## [0.2.114] — New: Check Armature Deformation (detection-only scan for the "weighted to the wrong bone" bug)

### Added
- **New Analyze panel scan, "Check Armature Deformation"**, for a bug class found live on a real
  production file: a mesh vertex weighted (fully or partially) to the wrong bone — in the real
  case, Reallusion/CC facial `CTRL_*` control bones instead of a body `DEF_*` deform bone, most
  likely from an indiscriminate body→garment weight-paint transfer — looks completely normal in
  rest pose (nothing wrong in `mesh.vertices`) but gets dragged to that bone's posed position once
  the Armature modifier evaluates, sometimes thousands of units away. Invisible until posed, so it
  silently corrupts geometry that scan/export/render pipelines can't easily catch otherwise.
  Detection works by comparing each edge's REST length against its DEPSGRAPH-EVALUATED (posed)
  length — a healthy mesh keeps this ratio close to 1x (isometric-ish skin/cloth deformation);
  the real broken case measured ~84,000x against a default threshold of 20x. `core/deform_check.py`
  (bpy-free ratio math + `Report` building, 16 new pytest cases), `ops/deform_check.py` (modal
  chunked scan over every visible mesh with an enabled, vertex-group-bound Armature modifier,
  reusing one `evaluated_depsgraph_get()` across all objects), new `FILELINK_OT_scan_deform_issues`
  operator, new `FILELINK_PG_deform_row` / `FILELINK_UL_deform_rows` results list in
  `ui/panels.py` with a per-row checkbox for a future fix pass.
- **This release is detection/review only, by explicit design** — nothing is mutated. The results
  list exists so a future fix pass has something to select from, but no Apply/Fix action exists
  yet.
- **Linked objects/meshes are flagged but visibly tagged "linked — fix at source"** rather than
  silently scanned-and-ignored or mishandled — a fix would need to edit both the Object's vertex
  group definitions and the Mesh's per-vertex weight assignments, so either being linked blocks a
  local fix. `ObjectDeformSummary.is_locally_fixable` (`obj.library is None and mesh.library is
  None`) flows through to the report message and the UI row's icon/label.
- New end-to-end smoke test `tests/smoke_deform_check.py` (synthetic 2-bone armature + 2-vertex
  mesh, one bone posed 1000 units away vs. a healthy control pair posed a small amount) confirms
  the real operator flags the exploded object and not the healthy one, run against actual Blender
  5.1.

## [0.2.113] — Vendor catalog ID (Poliigon-style 4+ digit SKU) is now a primary match signal

### Changed
- **The fuzzy matcher now recognizes a bare 4+ digit token (Poliigon's own asset IDs — 7174,
  8819, 9322, ...) as a vendor catalog ID and weights it far more heavily than an ordinary
  descriptive word.** A shared catalog ID between the wanted and candidate name is now strong
  enough on its own to rescue a match whose descriptive words differ too much to pass the
  ordinary stem-similarity floor (e.g. a heavily vendor-abbreviated name), and pushes a
  same-channel, same-resolution match to "high" confidence. Conversely, **two DIFFERENT catalog
  IDs now hard-disqualify a match even if every other word is identical** — two different
  Poliigon products should never be treated as interchangeable just because their descriptive
  names happen to collide. Doesn't override a genuine channel conflict (a normal map still can't
  stand in for a roughness map just because the SKU matches) — `core/imagematch.py`'s
  `NameParts.catalog_id` / `_CATALOG_ID_RE`. New pytest coverage.

## [0.2.112] — Fix two real fuzzy-match misses found live (MemSaver cache hijack + dot-joined pseudo-extension)

### Fixed
- **A third-party RAM-saving addon (MemSaver) can silently rewrite an Image's stored `filepath`
  to point at its own hashed cache derivative instead of the original texture — if that cache
  entry later goes missing, the stored path has zero relation to the real texture name anymore,
  so neither exact nor fuzzy matching could ever bridge it, even though the image's own
  DATABLOCK NAME still preserved the real identity.** `ops/image_relink.py::_wanted_basename`
  now detects a `memSaver_cache` path and falls back to the datablock name in that case. Found
  live against a real missing texture (`FabricRope001_AO_1K_jpg.002`) that both "Search a
  Folder" and "Suggest Matches" came up empty on.
- **The pseudo-extension tokenizer only stripped an underscore-joined fake extension
  (`"..._jpg.001"`), not a dot-joined one (`"...1K.jpg.002"`)** — the latter is Blender's own
  ordinary dedup-on-collision naming when the requested datablock name already looked like it
  had a real extension baked in, leaving a stray `"jpg"` stem token that dragged an
  otherwise-perfect match from "high" confidence down to "low". `core/imagematch.py`'s
  `_PSEUDO_EXT_RE` now matches either separator.
- New pytest coverage for both in `tests/test_imagematch.py`.

## [0.2.111] — Confidence-floored bulk accept + Missing Textures categories

### Added
- **"Accept High Matches" / "Accept High/Med Matches" buttons** next to the existing "Accept
  All" in the Possible Matches (fuzzy Suggest Matches) results area — bulk-accept proposals at
  or above a confidence floor instead of an all-or-nothing choice. All three buttons share one
  operator (`filelink.accept_all_matches`, now taking a `min_confidence` property) rather than
  three near-duplicate operators; the ranking itself lives in a new
  `core.imagematch.meets_min_confidence` so the ops layer doesn't duplicate it.
- **Missing Textures now splits into three collapsible categories** — Missing Material Textures,
  Missing World Textures, Missing Other Textures — each with its own summary line ("N of M
  matched") and collapsed by default, same as every other section's group headers. World
  attribution is a new `core.imagematch`-style node-tree walk over `bpy.data.worlds` (mirroring
  the existing per-material walk); a texture that isn't found in any material's or world's node
  tree falls into Other. New `core.picker.CategorySpec` / `flatten_category_group_member_rows`
  generalize the existing single-level `GroupSpec` shell to a 3-level category → group → member
  shape (new pytest coverage in `tests/test_picker.py`); the per-group "point at folder" bulk
  action stays Material-category-only (a same-named World/Other group could otherwise pull in
  the wrong rows through the shared `item.material` lookup). Not yet live-verified in Blender.

## [0.2.110] — Fix Check Materials crash on large reports

### Fixed
- **Crash fixed: the Analyze panel's inline report disclosure (`_draw_report_detail` /
  `_feature_tree_nodes`, used by Check Materials and every other inline-disclosure section)
  re-parsed the ENTIRE stashed report from JSON and rebuilt its whole tree on every single panel
  redraw, unconditionally — even while collapsed. Fine for a small report; a real crash hit on a
  production file where Check Materials flagged ~1410 issues (many near-duplicate materials each
  with several broken image nodes), where a full JSON-parse + tree-rebuild on every redraw became
  a real perf/stability risk.** `_feature_tree_nodes` now caches its parsed result per feature,
  keyed on the exact raw JSON string last seen — a stashed report only changes when a scan
  actually re-runs (a fresh raw string), so this is an exact cache key with no staleness risk,
  it just skips redundant reparses of identical data between scans. NOT yet live-verified against
  the actual crash (see `docs/TODO.md` for the pending live-repro checklist).

## [0.2.109] — Material-name Tier 2 fuzzy relink + matcher precision fixes

### Added
- **Tier 2 material-name matching** for the fuzzy folder-search relink flow: a missing texture
  Tier 1 leaves unmatched (or only at medium/low confidence) now escalates to searching other
  `.blend` files under the same folder for a material of the same name — vendor names get
  manually shortened in-scene (`FabricFloralDuckeggJacquard001` → `DuckEgg`), so the new
  `core.material_search.score_material_name` matches bidirectionally by containment rather than
  token overlap. Once found, that file's own images are harvested and channel-matched against
  just its rows — a small, correct-source corpus instead of guessing across the whole library.
  A Tier 2 hit always replaces a Tier 1 medium/low (the right source beats a shakier name guess
  against the wrong one).
- Channel-alias vocabulary expanded from real texture-library naming: `REFL` (reflection),
  `DISP16`/`BUMP16`/`NRM16` (16-bit map suffix), `MicroN(Mask)`, `Cavity(Map)`/`GradAO`,
  `TransMap`/`Translucency`, plus new first-class channels `SSS`, `VertexColorMap`, `WeightMap`,
  and `ORM` (kept separate from AO/roughness/metallic — a packed ORM map isn't interchangeable
  with any single standalone channel map).

### Fixed
- The fuzzy folder-search candidate index no longer includes non-image files (a reorganized
  library that keeps a per-asset `.blend` alongside its textures was getting that `.blend`
  scored as a texture candidate itself, since name-matching strips extensions before scoring).
- `_wanted_basename` used `os.path.basename` on a bpy `//`-relative path — on Windows that's
  `ntpath`, which misreads a leading `//` as a UNC host\share marker and silently returns `''`
  for the single most common stored-path shape (`//folder/file.ext`), breaking fuzzy matching
  outright for those rows.
- The tokenizer didn't recognize `_png`/`_jpg`-style pseudo-extensions (some FBX/vendor export
  pipelines can't embed a literal `.` in an embedded texture name, so they substitute `_png` —
  Blender may then add its own real `.001` dedup suffix on top). That stray extra stem token
  was dragging otherwise-perfect matches down to "low"/"medium" confidence for no real reason.
- **Relink Selected** no longer aborts the entire ticked batch when one target file went missing
  between staging and relinking (e.g. a network-drive sync lag) — it relinks everything with a
  valid target and reports the rest, left ticked for a retry, instead of doing nothing at all.
- Accept / Accept All / Accept Material's Matches no longer auto-tick a proposal whose file
  doesn't actually exist — only a confirmed-present file gets ticked, so a stale proposal can't
  silently reach Relink Selected untested a second time.
- `imagematch.classify()` is now memoized — it's a pure function of the filename, so a large
  library's fuzzy match no longer re-tokenizes the same names millions of times over in one
  blocking modal step.

## [0.2.108] — Automated Cleanup (Scan/Review/Apply Selected) + Find Material Across Files

### Added
- **Automated Cleanup** panel: Scan every included cleanup function (Make Local / Duplicate
  Materials / Duplicate Geometry / Orphans), review and tick/untick individual results, then
  Apply Selected — one backup at the start, a before/after savings summary at the end. Make
  Local gained real per-datablock selection for the first time (previously all-or-nothing).
- **Find Material Across Files** (Utilities): recursively search every `.blend` under a folder
  for a material name, wildcard or substring, entirely offline (no Blender launch).

### Fixed
- Make Local's per-item selective apply now correctly leaves un-ticked linked datablocks (and
  their library) untouched, retries across multiple passes so a ticked child whose dependency
  only just went local still gets localized, and reports an accurate localized count instead of
  the attempted count.

## [0.2.107] — Multi-hop Link Chains display cleanup

### Changed
- **Find Flattenable Links'** multi-hop route rows no longer repeat the current file's own name
  on every line, and no longer inline the whole chain as one string — each hop in the route now
  shows as its own row with a link icon, matching the rest of this UI's tree rendering. (The
  "Link Directly" repoint action originally scoped alongside this was dropped — there's no real
  per-datablock action to take at the bpy level for a route that's also linked directly.)

## [0.2.106] — Phase R: renamed to File & Link Utilities

### Changed
- **Full rename**, package id `assetdoctor` → `file_link_utilities`, all `ASSETDOCTOR_*` class
  prefixes → `FILELINK_*`, `bpy.ops.assetdoctor.*` → `bpy.ops.filelink.*`, `assetdoctor_*`
  WM/Scene properties → `filelink_*`, `AssetDoctorPreferences` → `FileLinkPreferences`. GitHub
  repo and gh-pages URL renamed to `FileLinkUtilities`. See `docs/USER_GUIDE.md` and
  `README.md` for the one-time upgrade note (saved Preferences don't carry over; the gh-pages
  repository entry must be re-added under the new URL).

## [0.2.105] — Phase 2 live-verify fixes

### Changed
- **Find Orphans'** fake-user-only and identical-datablock sections now share the same
  virtualized `ASSETDOCTOR_UL_tree` every other diagnostic uses, instead of hand-rolled,
  unindented row loops — matters most on a real production file (1000+ identical-datablock
  groups instantiated every row regardless of scroll position before this).
- **Find Duplicates** is now a collapsed-by-default sub-section: expanding it reveals the 4
  individual scan buttons (Data-blocks / Materials / Geometry / Textures) each with their own
  results area, so one problematic scanner doesn't block running the other 3. "Find All
  Duplicates" still runs all 4 in sequence from the section's own header.
- **Check Materials** now looks inside node GROUPS: a group that internally mixes shaders
  (e.g. a "hair shader" convenience group wrapping Principled Hair + Glossy + Transparent) is
  classified as "Combined Shader" instead of being lumped under its group's own name as if it
  were one single shader type.
- "Make Local Impact" renamed to "Make Local" (the Analyze section already names the analysis,
  not its effect).
- Path Normalization's "Normalize" button now hides once the result is clean instead of
  offering a no-op.

### Fixed
- Every inline Analyze-button disclosure (Check Materials, Check Link Chain, Make Local, …)
  could jump back to the top of its list on any click — the shared expand-state prop these
  sections all share was never wired into the existing scroll-position-preservation logic.
- Make Local's own result line showed a generic "nothing found" instead of the real linked/
  library count when nothing needed making local, with the real text only visible one row
  down inside a pointless expand arrow.
- Find Flattenable Links' summary line kept an expand arrow with nothing real behind it when
  no flattenable characters were found.
- The Audit This File dependency-loop "no user found" message could read as "this datablock
  doesn't exist" when it actually meant "exists, but has no object instance in the current
  view layer."
- The expand/collapse triangle's tooltip was a multi-paragraph developer docstring instead of
  a short user-facing hint.

## [0.2.90 – 0.2.104] — UI virtualization + backlog cleanup

### Changed
- **Every report/picker list now virtualizes.** Reports tab, Resource Usage, every inline
  Analyze-button disclosure, and the Missing Textures / Duplicate Textures / Datablock
  Reconnect / Examine Library pickers all draw through the same `UIList`-backed renderer —
  closes out the last few manually-drawn row lists, which could show blank rows once
  deeply expanded on a large result.
- **Click-to-select now leaves a sticky per-row icon** (found / no live user / unresolved)
  instead of a one-shot status message that was easy to miss.
- F8's hierarchical link-map layout is root-at-top (the file that pulls everything in sits
  at the top; pure assets sink to the bottom).

### Added
- **Check Materials** — a new read-only diagnostic: lists materials grouped by shader type,
  flags dangling node links and Image Texture nodes pointing at a missing file, and flags
  empty material slots.
- Broken Library Links rows flag whether a library is linked *directly* or only reachable
  through another linked library.

### Fixed
- A blank library name could appear in "Fix at Source" / Examine Library suggestions on
  Windows (a same-folder `//Name.blend` path was misread as a UNC path).
- Find Orphans could crash scanning a mesh belonging to a Library Override or missing
  placeholder; the same missing/override safety check Find Duplicates already used for
  shape keys now applies to every fingerprinted datablock type.
- Find Duplicate Data-blocks showed no progress/couldn't be cancelled on a file with one
  very large collection (e.g. hundreds of Actions) — now chunks per-item like the other
  duplicate scanners.

## [0.2.29 – 0.2.89] — Properties-editor migration, Flatten, fuzzy texture matching

### Changed
- Migrated from the 3D-viewport N-panel to **Properties → Scene**, restructured into
  **Analyze / Cleanup & Fixes / Utilities** panels as the feature set grew well past the
  original 6.
- Duplicate Textures redesigned around per-family keeper dropdowns + a material-mismatch
  eyedropper override.

### Added
- **Flatten** — detect Library-Override-with-transform "posing" setups (e.g. posed
  characters linked from a rig library) and flatten them to real local data, including a
  grouped "Flattenable Links" view and a background-subprocess-based cross-file resolver
  for more complex cases.
- **Datablock Reconnect** — for a missing linked datablock, pick a source `.blend`,
  auto-suggest the closest-matching name (exact / renamed / fuzzy), and relink + remap in
  one step, grouped by source library.
- Fuzzy texture-name matching (`core/imagematch.py`) with a confidence score and a
  channel-synonym table, wired into Possible Matches; substitute-from-material and
  substitute-from-another-`.blend` corpora.
- Resolution Variants (multi-resolution texture footprint report, opt-in standardize).

## [0.2.11 – 0.2.28] — F8 link-map graph, missing data-blocks, safe-to-delete

### Added
- **F8** — a self-contained interactive HTML dependency graph (force-directed, zoom/pan/
  search, no external resources) as an alternative to the flat F1 report.
- Missing **data-block** detection (`id.is_missing`, distinct from a missing *library*),
  grouped by source library.
- **Safe to delete?** — reverse-dependency check: given a file, list what would break if it
  were removed, before you remove it.

## [0.2.5 – 0.2.10] — F6 texture relink & dedup suite

### Added
- Missing-texture relink: doubled-path-prefix fix, cross-drive remap, folder search by
  filename, and a group-by-directory-or-material "point group at folder" bulk action.
- Duplicate-texture cleanup: `.NNN`-family lossless merge (content-verified first) and a
  content-hash dedup pass across the whole file regardless of naming.

## [0.2.0 – 0.2.4] — F7 Link & Dependency Doctor

### Added
- Recursive, offline (BAT-based) folder dependency scan: broken/absolute/circular links,
  duplicate library blocks, inconsistent paths, most-linked libraries.
- Live in-file analysis: `.NNN` duplicate-datablock census, override/dependency loops.
- Library path fixes (normalize + relink missing) and datablock-level link inspection
  (what one file links from another, in either direction — the basis for later cycle-
  breaking and reconnect work).

## [0.1.10] — Report/Resource panels: virtualized UIList (fixes blank rows)

### Fixed
- **Blank rows in large reports.** The Report and Resource trees were drawn as manually-built
  rows, which the N-panel doesn't virtualize — so expanding a big category (e.g. an F1 link map
  with dozens of broken-link findings) left every row past ~13 blank (only the expand triangle
  drew). Both panels now use a real **`UIList`** (`template_list`), which virtualizes and scrolls,
  rendering correctly for any size. The 200-row draw cap and its "+N more — use Export…" hint are
  gone (no longer needed).

### Changed
- The flattened tree rows (`core.tree.flatten_visible`) are now materialised into a
  `WindowManager` `CollectionProperty` (`ASSETDOCTOR_PG_tree_row`) that the new `ASSETDOCTOR_UL_tree`
  draws; `ops.report_store` rebuilds it whenever the shown report, the selected feature, or its
  expansion changes. The report JSON stays the source of truth (export/title unchanged).

## [0.1.9] — Duplicate Materials report (local/linked)

### Changed
- **Duplicate Materials report restructured.** The top row now shows the headline
  **`XX (YY Local & ZZ Linked)`** (total removable duplicates, split by local vs linked), with two
  child rows **Local** / **Linked** that expand to the actual material lists. The redundant
  bottom "Summary" row was removed. Apply behaviour is unchanged (the remap plan is the same).
- Generic report model gained an optional **`Finding.detail`** (right-aligned per-row value) and
  **`Report.category_details`** (per-category header override) — both serialized; used by F3 and
  available to any feature. `report_to_tree` renders them.

## [0.1.8] — progress bars for every scan/apply

### Added
- **Modal progress bar + ESC for F3, F4, Geometry, and Resource Analyzer.** Find Duplicate
  Materials, Scan Orphans (+ Purge), Instance Duplicate Geometry, and Analyze Resource Usage now
  run as modal operators with the shared progress bar/status and ESC-to-cancel — the heavy
  per-datablock fingerprinting/estimation is chunked through a `_gather_steps` generator, so big
  files no longer freeze the UI while they "look hung". Only **Profile Render** stays synchronous
  (a single render can't be chunked).
- **`ModalProgressMixin`** (`ops/progress.py`) — packages the modal/timer/ESC/progress-bar
  pattern with a per-tick time budget, so an operator only supplies a `run_steps(context)`
  generator that yields `(fraction, status)`. `execute` drains it for EXEC_DEFAULT/scripting/tests.

### Changed
- F3 (materials) and Geometry instancing apply paths **no longer push a native Undo step** (modal
  operators); they continue to take a timestamped **auto-backup before mutating** (same safety
  model as F2). Restore from the backup to revert.

## [0.1.0] — M0 Scaffold — unreleased

### Added
- Repo scaffold: `blender_manifest.toml` (Extension, Blender 5.0+), thin
  `register`/`unregister`, `AssetDoctorPreferences` (backup dir, auto-backup toggle,
  resolution-token regex).
- `core/` bpy-free package:
  - `report.py` — `Finding`/`Report` with JSON + CSV export. **Tested.**
  - `graph.py` — `DepGraph` with roots/leaves/cycle detection. **Tested.**
  - `fingerprint.py` — `strip_resolution_tokens` implemented & tested; node/mesh hashers
    stubbed for M2.
  - `blendscan.py` — BAT wrapper stub for M1.
- `ops/` scaffold operators (F1–F4) that register and report "implemented in M#".
- `ui/panels.py` — AssetDoctor N-panel with one button per feature.
- pytest harness (`conftest.py`, `pyproject.toml`) running the bpy-free core tests outside
  Blender; tests for report, graph, and `strip_resolution_tokens` (incl. doctests).
- `README.md`, `docs/ARCHITECTURE.md` (design + risks + milestone roadmap), `.gitignore`.

### Added (BAT bundling — TODO #2 resolved)
- Bundled `blender_asset_tracer==1.20` (pure-Python wheel) via `blender_manifest.toml`
  `wheels`. Confirmed `requests` is NOT required for dependency tracing (probe with
  requests blocked under Blender 5.1), so the requests/charset_normalizer chain is
  intentionally excluded to keep the extension cross-platform.
- `tests/smoke_register.py` (headless register/unregister + BAT-presence check) and
  `tests/probe_bat_imports.py` (confirms blendfile/trace import without requests).
- `[build] paths_exclude_pattern` so dev-only dirs stay out of the release zip.
- Verified: manifest parses, extension builds (`assetdoctor-0.1.0.zip`), and the addon
  registers/unregisters in Blender 5.1.

## [0.1.0] — M1: F1 folder link map — unreleased

### Added
- `core/blendscan.py` — BAT-backed offline reader: `scan_file` (reads `LI` Library
  blocks; Blender 5.x stores the path in the block's `name`, `//` = relative),
  `resolve_blend_relative`, `iter_blend_files`, and `map_folder` building the `DepGraph`.
- `core/graph.py` — added `to_dot()` Graphviz export.
- `core/f1_linkmap.py` — `build_link_report` flags broken links, absolute (non-portable)
  paths, circular references, unreadable files, plus a summary.
- `ops/scan_folder.py` — folder picker → report → writes `<root>/.assetdoctor/linkmap_*.{json,csv,dot}`.
- Fixtures: `tests/fixtures/build_linkproj.py` generates `linkproj/` (scene → libA → libB,
  relative links) — committed so pytest runs bpy-free. `tests/conftest.py` puts the BAT
  wheel on sys.path.
- Tests: `tests/test_blendscan.py` (7) — direct link, leaf, path resolution, transitive
  graph, clean-project report, broken-link detection, DOT smoke. `tests/smoke_f1.py`
  runs the operator end-to-end in Blender.

### Verified
- 28 pytest tests pass; F1 operator runs in Blender 5.1 (scene→libA→libB, exports written).

## [0.1.0] — M2: content fingerprinting — unreleased

### Added
- `core/fingerprint.py` — `fingerprint_material` (recursive hash from the Material Output,
  invariant to node naming/order, **resolution-agnostic** via image base-name),
  `fingerprint_mesh` (counts + rounded coords + topology, float-jitter tolerant),
  `fingerprint_image` (identity, resolution-SENSITIVE). Canonical JSON + SHA1 with float
  rounding.
- `ops/extract.py` — bpy→dict extractors (materials/meshes/images) feeding the hashers;
  generic node-prop extraction that skips cosmetic/layout attrs and normalises image refs.
- `core/cluster.py` — `group_identical` (fingerprint → duplicate groups), used by F3/F4/M6.
- Tests: `tests/test_fingerprint.py` (1K==2K equality, naming/order invariance,
  topology/param sensitivity, mesh tolerance, image res-sensitivity), `tests/test_cluster.py`,
  and `tests/smoke_fingerprint.py` validating the contract against real Blender 5.1 data.

### Verified
- 44 pytest tests pass. In Blender 5.1: a 1K and 2K material hash identically end-to-end;
  wood≠metal; mesh identity works; image identity stays resolution-sensitive.

## [0.1.0] — M3: F4 orphans, fake users & duplicates — unreleased

### Added
- `core/f4_orphans.py` — `classify` (orphan / fake_only / in_use / linked, per verified
  Blender 5.1 semantics: orphan=users0, fake_only=fake&users1) and `build_orphan_report`
  (orphan + fake-only lists, identity clusters via `group_identical` with per-member status,
  summary).
- `ops/orphans.py` — gathers datablocks across the common collections (materials/meshes/
  images fingerprinted), builds the report, and offers an optional `purge_orphans`
  (`bpy.data.orphans_purge`) behind the report-first/auto-backup safety model.
- `ops/safety.py` — `auto_backup` writes a timestamped `.blend` copy (save_as_mainfile
  copy=True) before any mutation, honouring the prefs backup dir / toggle.
- Tests: `tests/test_f4_orphans.py` (classification, orphan/fake lists, identity clusters,
  type isolation, linked exclusion, summary) + `tests/smoke_f4.py` end-to-end.

### Verified
- 50 pytest tests pass. In Blender 5.1: orphan/fake-only/identical classification correct;
  purge removes orphans while fake-user and in-use data survive.

## [0.1.0] — M4: F3 material dedup — unreleased

### Added
- `core/f3_materials.py` — `parse_name_list`, `choose_canonical` (whitelist > non-blacklisted
  > forced; tie-break local-over-linked then highest resolution), `build_dedup_plan`
  (fingerprint clusters → plan + report, flags linked victims).
- `ops/material_dedup.py` — gathers materials (fingerprint + max texture res + unique id that
  disambiguates local/linked same-name), report-first dry run; on Apply (after auto-backup)
  `user_remap`s duplicates onto the canonical and removes local victims. `REGISTER`+`UNDO`.
- `prefs.py` — `material_whitelist` / `material_blacklist` (comma/newline, glob-aware).
- Tests: `tests/test_f3_materials.py` (list parsing, all canonical-selection rules, plan +
  summary, linked-victim flagging) + `tests/smoke_f3.py` end-to-end.

### Verified
- 60 pytest tests pass. In Blender 5.1: a 1K+2K material pair clusters, the 2K wins canonical,
  Apply removes the 1K and repoints its object's slot to the 2K; whitelist override works.

## [0.1.7] — Make Local speed + collapsible panels

### Fixed
- **Select-in-Outliner for all report findings.** Clicking a finding now selects the object(s)
  that use the datablock, even for non-object kinds (materials, meshes, images, node groups) —
  it walks `user_map()` from the datablock up to the using objects. Previously only a few types
  resolved, so Make Local report items appeared to do nothing.
- **Make Local on complex files: observability + safety.** Added per-pass and per-100-datablock
  **heartbeat logging**, `log.debug` of each datablock before make-local (the debug log's last
  line pinpoints a hanging call), a **no-progress safety break**, and **bounded** purge loops —
  so a long run is visible (it stopped logging mid-run before) and can't grind indefinitely.
  Also fixed a latent **library-purge** bug (the user check was reversed and could force-remove
  still-used libraries).

### Changed
- **Make Local performance.** The apply path now does one **bulk**
  `bpy.ops.object.make_local(type='ALL')` call (internally batched) before the per-ID passes,
  instead of localizing thousands of datablocks one at a time. The per-ID passes only mop up
  what the bulk op can't reach (linked collections, node groups, un-resolved overrides), so the
  pathological ~hours run on complex files (botaniq/engon, circular links + overrides) collapses
  to seconds/minutes. Bulk pass is guarded by `poll()` + RuntimeError and degrades gracefully to
  the pure per-ID path. Verified by `smoke_f2` (New File + In Place still fully local).

### Added
- **Collapsible panel sections.** Each feature (Project, Make Local, Duplicate Materials, Orphans,
  Duplicate Geometry, Resource Analyzer, Utilities) is now a native child panel of the main
  AssetDoctor panel, so each has its own collapse triangle and Blender remembers its open/closed
  state. Utilities defaults closed.
- **Clickable "Add-on Preferences" in Utilities.** The old static "Lists/backups: Add-on
  Preferences" hint is now a button (`assetdoctor.open_preferences`) inside the Utilities section
  that opens Preferences with AssetDoctor expanded (`preferences.addon_show`, with a fallback).
- **Make Local progress bar + cancel.** Apply now runs as a **modal** operator with a live
  progress bar and status text in the panel (and the OS task-bar), and **ESC to cancel** —
  mirroring the F1 folder scan. New File reverts cleanly on cancel; In Place reports it's
  partially localized and points at the backup. Core work is a `localize_steps` generator that
  `execute` (scripting/tests) drains synchronously and the modal steps one chunk per timer tick.
- **Shared progress widget.** The folder-scan's progress props were generalized to one
  `assetdoctor_op_*` WindowManager trio + `ops/progress.py` helpers, drawn once at the top of
  the panel, so every modal action reuses a single progress bar.
- **Debug log starts fresh** on each enable and on each **file open** (`load_post` handler;
  the Scene-prop update didn't fire on load before). File is `AssetDoctorDebugLog.txt`.

## [0.1.6] — report drawing fix

### Fixed
- **Reports no longer show blank rows** on large projects. The N-panel doesn't virtualize
  manually-drawn rows, so a report with hundreds of findings left rows blank past a point
  (data was fine — the Export was complete). Now: **categories start collapsed**, each shows a
  **count**, and the tree draw is **capped (200 rows)** with an "use Export… for the full list"
  hint. Affects every report (Link Map, Materials, etc.). The full fix (a virtualized `UIList`)
  is tracked in docs/TODO.md "Report UI v2".

### Changed
- Duplicate-materials report category title capitalized ("Duplicate Materials").

## Unreleased — auto-update repository

- Published a self-hosted **extension repository** so Blender auto-updates: `gh-pages` branch
  serves `index.json` (from `extension server-generate`) + the version zips via GitHub Pages at
  **https://rickpalo.github.io/AssetDoctor/index.json**. Users add that URL once
  (Preferences → Get Extensions → Repositories). See `docs/RELEASING.md`.

## [0.1.5] — M7 step 4: Profile Render (real peak RAM)

### Added
- **Profile Render** button (Resource Analyzer): renders the current frame and reports
  Blender's **real peak system RAM** (whole process, via OS — Windows `GetProcessMemoryInfo`
  / Unix `getrusage`), shown in the Resource panel to complement the estimates.
  Real VRAM is intentionally not attempted (not exposed by Blender's Python API); F5's
  VRAM estimate covers that side.
- `core.resource.peak_process_ram_bytes()` (bpy-free) + test; `tests/smoke_profile.py`.

This completes **F5 / M7**.

## [0.1.4] — M8: Report system v2

### Added / changed (TODOs)
- **Persistent per-feature reports.** Each scan (Link Map / Make Local / Materials / Orphans /
  Geometry) keeps its OWN report — a Materials report survives a later Geometry scan. The
  Report panel gets a selector row to switch between whichever reports exist; clear removes
  only the shown one. (Replaces the single overwritten slot; F5 resource stays separate.)
- **Per-line tooltips.** Tree row labels are now tooltip-bearing buttons whose hover text is
  the FULL line (full broken-link path, full message + size) — readable despite the narrow
  panel. Clicking a row does its natural action (expand/collapse a parent, select a leaf).
- **Export/print.** "Export…" on the Report and Resource panels writes the current view to a
  `.txt` (indented tree) or `.csv` (reports) for printing/sharing.
- **Select-in-Outliner** (per chosen behaviour): selecting a finding selects + activates the
  user object(s) (Outliner follows the active object) without rearranging editors; a material
  also gets its slot highlighted; orphan/unused data shows a hint to use Outliner → Blender
  File / Orphan Data.
- Tests: `core/tree.all_keys` + updated `smoke_report.py` (persistence, selector, toggle,
  export, select, clear — 9/9).

## [0.1.3] — M7 step 3: F5 Resource Analyzer

### Added
- **Resource Analyzer (F5).** "Analyze Memory/Disk" estimates usage by **datablock type**
  (Images, Meshes, …), each datablock counted once, biggest-first, with est. RAM / est. VRAM /
  accurate disk + user count, shown in a new **Resource Usage** panel (reuses the tree widget).
  Chosen over a scene→object hierarchy to avoid double-counting shared data.
- `core/resource.py` (image/mesh byte estimates + `human_bytes`), `core/resource_tree.py`
  (by-type tree + totals), tree `detail` column + JSON (de)serialization, generalized expand
  toggle (works for both the report and resource trees).
- Tests: `test_resource.py`, `test_resource_tree.py` (+ tree round-trip) and `smoke_resource.py`.

### Changed (TODOs)
- Documentation icon pinned **far right** in the panel header (title · version · ⟶ icon).
- Debug log renamed **`AssetDoctorDebugLog.txt`** (was debugLog.txt).

## [0.1.2] — M7 step 2: instance duplicate geometry

### Added
- **Geometry dedup / instancing.** `core/geometry_dedup.py` (`build_instance_plan`,
  `choose_canonical`) finds identical-but-separate mesh datablocks used by different objects
  and plans to collapse them onto one shared datablock (turning wasteful copies into
  instances). Kind-agnostic engine; covers meshes now (curves/others extend via a fingerprint).
- `ops/instance_dedup.py` — report-first dry run; on Apply (after auto-backup) `user_remap`s
  duplicate meshes onto the canonical (most-used local one) and removes the copies. Panel:
  "Duplicate Geometry" box (report / apply). Report flows into the M7-step-1 viewer.
- Tests: `tests/test_geometry_dedup.py` + `tests/smoke_instance.py` (two identical separate
  meshes → instanced onto one; duplicate removed; distinct geometry untouched).

### Versioning
- **3rd-digit bump per completed step**; the N-panel header shows `vX.Y.Z` (from the manifest)
  so the installed build is verifiable. The built zip is named `assetdoctor-<version>.zip`.

## [0.1.1] — M7 step 1: report viewer (shared tree widget)

### Added
- **In-Blender report viewer.** Every feature now stashes its `Report` on the WindowManager
  and a collapsible **Report** panel renders it as an expandable tree (category → finding →
  item) with severity icons, expand/collapse toggles, and **click-to-select** the datablock a
  finding refers to (objects directly; materials/mesh-data via the objects that use them).
- `core/tree.py` (bpy-free): `TreeNode`/`Row`, `report_to_tree` (rolls up severity, parses
  `Type/Name` refs but not file paths), `flatten_visible` (tree + expanded keys → indented
  rows). `Report.from_dict`/`from_json` round-trip.
- `ops/report_store.py`: `stash_report` + toggle/clear/select operators.
- Tests: `tests/test_tree.py` (tree build, ref parsing, flatten/expand) + `tests/smoke_report.py`
  (operator → stash → reconstruct → toggle → select → clear, in Blender). Report round-trip test.

### Notes
- This is the shared widget the F5 Resource Analyzer (M7 step 3) will reuse. Panel *draw* is
  interactive; the data pipeline behind it is covered by tests.

## [0.1.0] — Build hygiene + compressed-file support — unreleased

### Fixed / clarified
- **Compressed .blend support confirmed.** Blender 5.x bundles `zstandard` (0.25.0 in 5.1)
  in its own Python, so BAT reads zstd-compressed files (Blender's default since 3.0) with
  nothing extra bundled. Locked by `tests/smoke_compressed.py`. (Our committed fixtures are
  uncompressed, which had hidden this.)
- **Removed a stray bundled `zstandard` wheel** from `wheels`/manifest and the
  **Windows-only `platforms` pin** that came with it — both unnecessary given the above, and
  the pin would have made the extension Windows-only. Package is platform-independent again
  and back to ~135 KB (was ~645 KB).
- **Excluded `tools/` from the shipped extension** (kept in the repo as a dev utility).
  `tools/find_datablocks.py` (originally find_billboards.py) is a host-Python offline search; on host Python it
  needs `pip install zstandard` for compressed files (Blender's bundle doesn't apply there).

## [0.1.0] — Responsive scan + doc link (TODO 4 + doc icon) — unreleased

### Added
- **Modal folder scan** (TODO 4): the F1 scan runs as a modal operator — time-bounded batch
  per timer tick, **ESC to cancel**, live progress bar in the panel (WindowManager props),
  wait cursor and status-bar text. `core.blendscan` refactored into
  `new_scan_result`/`scan_into`/`map_folder`; `f1_linkmap.report_from_scan` shares report
  building between the modal and synchronous (`execute`) paths.
- **Documentation icon**: right-aligned HELP button on the panel header (`draw_header`) opening
  the repo docs; `website` added to `blender_manifest.toml`. (URL is a placeholder pending push.)
- Tests: incremental-vs-synchronous scan equivalence + `report_from_scan` + `bat_available`.

### Verified / pending
- 69 pytest tests pass (core of the modal scan verified: incremental == synchronous).
- Blender-side checks (register smoke, zip rebuild) and the interactive modal/progress + doc
  icon are pending — deferred to avoid competing with an active render.

## [0.1.0] — UX batch (TODO 1/2/5) — unreleased

### Added
- **Project folder field + Scan button** (TODO 5): `Scene.assetdoctor_scan_dir` path picker;
  the scan operator runs the stored folder (only opens the browser when none is set).
- **Tooltips** (TODO 1): per-variant `description()` classmethods on the make-local / dedup /
  orphans operators; descriptions on the new Scene props.
- **Utilities section + Enable Debug Log** (TODO 2): `Scene.assetdoctor_debug_log` toggle and
  `log.py` (an `assetdoctor` logger). INFO findings → console + file; DEBUG detail → file.
  `debugLog.txt` is written next to the .blend (or Blender temp if unsaved). All four
  operators now log instead of bare `print`.
- Tests: `tests/test_log.py` + `tests/smoke_utils.py`.

### Notes
- Deferred to a planned "M7: UX & feedback" milestone — report viewer (TODO 3) and
  progress/responsiveness via a modal folder-scan operator (TODO 4). See docs/TODO.md.

## [0.1.0] — M5: F2 recursive make-local — unreleased

### Added
- `core/f2_makelocal.py` — `build_makelocal_report` groups linked datablocks by source
  library, counts indirect (transitively-linked) ones, summary.
- `ops/make_local.py` — dry-run report; on Apply iterates `make_local(clear_liboverride=True)`
  over all ID collections until nothing is linked, then purges emptied libraries.
  - **New File** mode (default): writes a fully-local copy (`save_as_mainfile copy=True`) then
    `revert_mainfile()` so the working file's linked setup is untouched. Requires a saved file.
  - **In Place** mode: flattens the current file after an auto-backup.
- Tests: `tests/test_f2_makelocal.py` + `tests/smoke_f2.py` (New File output BAT-verified to
  have zero library links; In Place leaves no linked data and no libraries).

### Fixed / discovered
- After `make_local`, `Library.users` can report a phantom count even when `user_map()` shows
  no real users. `_purge_libraries` now trusts `user_map()` to remove stale libraries.
  Regression covered by `smoke_f2.py` ("no libraries remain").

### Verified
- 63 pytest tests pass. In Blender 5.1: both F2 modes correct on the scene→libA→libB fixture.

### Notes
- Next: M6 — F1 cross-file object-duplication census (reuses M2 fingerprints) + polish.
