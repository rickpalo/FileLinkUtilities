# AssetDoctor — TODO / backlog

## TOP PRIORITY — separate "fix folders" from "fix paths/links"; per-link targeted fix (2026-06-21)

**STATUS: BUILT @ v0.2.5, VERIFIED IN BLENDER (user, 2026-06-21) — feature works end-to-end.** On the
user's real file: Find Broken Links listed the broken material library; the auto-match failed for one
lib so the user PICKED a file manually (pick-a-file path) — worked; Relink Selected fixed it; Normalize
worked. Feature done. The combined `Fix Paths` button is gone; the Scene panel now has two separate
sections: **Broken links** ("Find Broken Links" → per-link list with checkboxes, auto-found candidate
or "pick a file" per row, "Relink Selected (creates backup)") and **Path normalization** ("Check" /
"Normalize (creates backup)"). Ops in `ops/relink.py`: `scan_broken_links`, `relink_pick_file`,
`relink_selected`, `normalize_library_paths` (replaced `fix_library_paths`). `core.relink.relink_stored_path`
(bpy-free, tested). `ASSETDOCTOR_PG_broken_lib` + `ASSETDOCTOR_UL_broken_libs` + WM `assetdoctor_broken_libs`.

### Follow-ups from the 2026-06-21 verify session
- [x] **Caution when Scan Deps runs with unsaved changes (DONE @ v0.2.6, code).** User saw Scan Deps
  flag a "missing link" AFTER relinking but BEFORE saving, then clean after saving — because Scan Deps
  is the OFFLINE BAT scan that reads the file FROM DISK (last-saved state), not the in-memory fix.
  Added a red panel hint in `ASSETDOCTOR_PT_scene_deps.draw` above the Scan/Analyze row, shown when
  `bpy.data.is_dirty`: "Unsaved changes — save before Scan deps (it reads from disk)". UI-only.
- [~] **Magenta materials after a successful library relink → likely MISSING TEXTURES, not libraries.**
  **LAYER 1 (relink) BUILT @ v0.2.7 (2026-06-21), needs live-Blender verify.** `core/imagepaths.py`
  (bpy-free: `dedup_path` collapses doubled `BlenderSync\BlenderSync\` segments, `apply_prefix_remap`
  cross-drive, `find_relink_targets` folder-search-by-basename; 13 tests, suite 175 green) +
  `ops/image_relink.py` (`scan_broken_textures`, `relink_pick_texture`, `relink_textures_selected` —
  LOCAL images only, per-texture checkboxes + pick-a-file, backup→set `image.filepath`→`reload`). UI:
  `ASSETDOCTOR_UL_broken_imgs` + "Missing textures" box in the Scene panel + WM `assetdoctor_broken_imgs`
  (reuses `ASSETDOCTOR_PG_broken_lib`). **Verify:** Find Missing Textures lists the magenta images,
  doubled-prefix ones auto-match, pick-a-file works, Relink Selected fixes only ticked. Layers 2
  (name-family consolidation) + 3 (content-overlap deep dive) still TODO.
  - **UI LIVE-CONFIRMED @ v0.2.7 (user screenshot, 2026-06-21):** the "Missing textures" box draws,
    lists the CC4/Beard/Brows textures (mostly "no match — pick a file" since they're absent locally).
    Two NEW follow-ups from that test:
  - **DESIGN AGREED (user, 2026-06-21) — A + B + Layer 2 designed together. Build NOT started.**

    **Unifying model (the "better design" — build ONCE, reuse across B + Layer 2).** A, B, and
    Layer 2 all operate on FAMILIES/GROUPS of images, and a missing `Leather_2k` whose `Leather_1k`
    exists is BOTH a relink candidate AND a consolidation candidate (surface both). So build a single
    bpy-free `core/imagefamily.py`: `family_key(name)` (strip `.NNN` → strip res tokens
    `_1k`/`_2k`/`_4k`/`_1024`/`LowRes`/`HighRes`); `group_images(descs)` →
    `{family_key: [members]}` where members carry name/stored/resolved/exists/dims/content-hash/users;
    `classify_family(members)` → IDENTICAL | RES_VARIANT | DISTINCT (needs dims+hash). The bpy op stays
    a thin extractor (like `_gather_images`); all logic unit-tested. Matches the cross-cutting
    "build the selection model once and reuse" requirement.

  - [~] **F6 follow-up A — BUILT @ v0.2.8 (2026-06-21), needs live-Blender verify.**
    `core/imagepaths.py`: `diff_found(before_missing, after_by_name)` → `FindMissingResult`
    (found / still_missing) + `build_find_missing_report` (feature `"f6tex"`; 4 new tests, suite 179).
    `ops/image_relink.py::ASSETDOCTOR_OT_find_missing_files_folder` — dir picker → snapshot missing →
    `auto_backup` → `bpy.ops.file.find_missing_files(directory=)` → re-snapshot → diff → stash f6tex
    report + re-populate the broken-imgs list. UI: "Find Missing Files (folder)…" button in the
    Missing-textures box; `"f6tex"` ("Missing Textures") added to `report_store.FEATURES` +
    panel `_F7_FEATURES` + `core/tree._CATEGORY_TITLES` (found_texture/unresolved_texture/relink_texture).
    **VERIFY:** pick a folder containing the missing textures → found ones drop off the list + appear in
    the Missing Textures report; still-missing remain; backup written.
    Our Layer-1 search is single-level `os.scandir`; `bpy.ops.file.find_missing_files(directory=X)` is
    **recursive by filename** but **silent**. New **"Find Missing Files (folder)…"** button in the
    Missing-textures box → dir picker. Flow: snapshot each LOCAL image's `exists` → `auto_backup` → run
    native op → re-snapshot → **diff** → report **found** vs **still-missing** (the report Blender
    omits); also surface `file.report_missing_files`. **Accepted caveat:** the native op affects ALL
    external files (libraries/caches too), recurses the whole tree, and on duplicate basenames picks
    one — less safe than our unique-match rule; mitigation = backup + the before/after report so the
    user inspects what moved (label it "searches recursively, affects all external files"). Complements
    Layer 1 (ours = precise/unique; native = broad/recursive).
  - [ ] **F6 follow-up B1 — directory-level relink (LOSSLESS, build now).** Keep the flat virtualized
    UIList as source of truth; add a compact **Groups** strip above it. **Group by ORIGINAL containing
    directory** (decided — files that lived together likely still do; material shown as secondary
    info). Each group row → **"Point group at folder…"** → dir picker → fill `target` for every member
    found there by basename → existing **Relink Selected** applies. **Material is the FALLBACK
    targeting dimension (user, 2026-06-21):** when a group's original directory is gone, let the user
    pick a directory and resolve **all of ONE material's** missing textures within it (group-by-material
    targeting mode for that case). Minimal new state; reuses the working apply path.
  - [ ] **F6 follow-up B2 — fuzzy substitution (LOSSY/render-changing, build WITH Layer 2, gate hard).**
    Substituting `Beard18→Beard1` deliberately changes the render. Separate, explicitly-labeled
    **"Substitute equivalent…"** per-group action, **default OFF**, candidate shown for confirmation.
    Needs a DIFFERENT strip than `.NNN` — an embedded trailing index in a name segment (`BeardNN`) —
    which overlaps Layer 2's family logic, so build it together with Layer 2, not with B1.

### F6 Layer 2 — name-family consolidation (DEDUP datablocks, not relink) — design agreed 2026-06-21
  Different operation from A/B (which fix MISSING files): merge duplicate image DATABLOCKS. Two cases,
  treated differently (mixing them corrupts the render):
  - **`.NNN` families (Leather vs Leather.001) → LOSSLESS merge** when identity-verified. Image analogue
    of F3 material dedup: pick canonical, `old.user_remap(new)`, purge rest. Reuse
    `datablock_graph.strip_dup_suffix`/`duplicate_families`.
  - **Resolution variants (`_1k` vs `_2k`) → DIFFERENT files → NOT a merge.** "Combine" = standardize
    to a CHOSEN resolution = **LOSSY → footprint pillar, opt-in, REPORT-ONLY for now.**
  - **SAFETY RULE:** name similarity finds CANDIDATES only; verify **dimensions + content hash** before
    offering merge. Same family + same content → lossless; same family + different content → standardize
    (flagged lossy). Show which objects/materials use each (usage graph).
  - First cut: **current-file images only**, hash on demand, **cache by (path,size,mtime)**, packed
    images hashed from packed data. New `core/imagededup.py` (bpy-free) + report feature key `"f6dup"`
    (categories `merge_lossless` info, `standardize_lossy` warning/opt-in).

### F6 A/B/Layer-2 — recommended build order (lossless-now vs lossy-deferred)
  1. **Follow-up A** — self-contained, immediate value.
  2. **`core/imagefamily.py` + B1** — shared model + directory-level relink (lossless).
  3. **Layer 2 `.NNN` lossless merge** — safe, high-value dedup (new core + tests).
  4. **B2 fuzzy substitute + Layer 2 resolution-standardize** — both lossy/opt-in, designed & built
     together under the footprint pillar.
  Keeps the lossless/lossy split clean; never collapses a 1k+2k pair by accident.
  User relinked the material library OK but some materials still render pink/purple = likely missing
  IMAGE files inside that library. AssetDoctor's relinker currently fixes LIBRARY (.blend) links only,
  NOT image/texture paths. (User CAN use Blender's File→External Data→Report Missing Files to confirm —
  they were just thinking add-on-first; not a gap in Blender.) Still worth folding into AssetDoctor as
  a one-stop **missing-file detection + relink for images/textures** (the F6 smart relinker, below) so
  the user doesn't bounce between tools. Detect missing `image.filepath` (+ other external files),
  report, and relink (folder remap / pick / fuzzy). Pairs with the existing library relinker. NOTE: fix
  the SOURCE library top-down (e.g. human_bundle), not the linking file — but human_bundle is a SHARED
  library, so relink/normalize + save there; do NOT make-local/purge in it.
  - **CONFIRMED via render log (user, 2026-06-21): the magenta = MISSING IMAGE TEXTURES.** Concrete
    patterns from the real files (these define the F6 relinker's required transforms):
    1. **Doubled prefix `E:\BlenderSync\BlenderSync\SynologyDrive\...`** (should be `E:\BlenderSync\
       SynologyDrive\...`) — the biggest, fixed by a single prefix find/replace `E:\BlenderSync\
       BlenderSync\` → `E:\BlenderSync\`. ← headline F6 case.
    2. **Cross-drive `D:\CharacterCreator\...`** — machine-specific; needs drive/root remap or absent.
    3. **Temp `C:\Users\Rick\AppData\Local\Temp\tmp…\...`** — deleted; must re-point to real source.
    4. **`E:\Addons\HumGenV4\...` (dot-prefixed)** — Human Generator addon-internal; addon-managed.
    5. Genuinely-missing files under valid CC_DataLink/imports roots (CC4 re-imports cleaned up).
    So F6 = detect missing `image.filepath` + **prefix find/replace remap** + folder-search-by-
    filename + cross-drive (D:→E:) remap, report-first + backup. Stopgap now: Blender File→External
    Data→**Find Missing Files** pointed at `E:\BlenderSync\SynologyDrive` catches the doubled-prefix +
    many others by filename.
  - **F6 ALSO: consolidate similar-named image datablocks (user, 2026-06-21).** Beyond relink, detect
    similar names and offer to combine — but TWO distinct cases, treated differently (mixing them
    would corrupt the render):
    - **`.NNN` suffix families ("Leather" vs "Leather.001") → usually IDENTICAL → LOSSLESS merge.**
      The image analogue of F3 material dedup: pick canonical, remap users, purge rest. Reuse
      `core/datablock_graph.py` `strip_dup_suffix`/`duplicate_families`.
    - **Resolution variants ("Leather_2k" vs "Leather_1k", "LowRes"/"HighRes") → DIFFERENT files →
      NOT a merge.** "Combining" = standardize to a CHOSEN resolution; LOSSY, changes the render →
      belongs with the **footprint-reduction pillar**, opt-in per family, user picks target res, never
      automatic.
    - **SAFETY RULE: name similarity only finds CANDIDATES; verify identity (dimensions + file hash /
      datablock fingerprint) before offering "combine."** Same family + same content → lossless merge;
      same family + different content (1k/2k) → standardize-to-resolution (flagged lossy), show which
      objects use each.
    - **Family detection:** strip `.NNN` → strip res tokens (`_1k`/`_2k`/`_4k`/`_8k`, `_1024`/`_2048`,
      `LowRes`/`HighRes`) → group. Real cases in the render log (`…\LowRes\…`, `Std_Skin_Head_*`
      families across CC4 re-imports). Pairs with the relinker: a missing `Leather_2k` whose
      `Leather_1k` exists is BOTH a relink candidate AND a consolidation candidate — surface both.
  - **F6 DEEP DIVE: content-based texture-overlap analysis (user, 2026-06-21) — the real bloat-killer.**
    Render log shows the SAME texture names repeated across ~15+ CC4 import folders (`CC3_Base_Plus`,
    `_2`, `_4`, `_20`, `fullyClothed`, `HD Aaron`, …) → likely dozens of content-identical copies.
    - **Detect overlap by CONTENT, not name:** fingerprint each image = file-bytes hash (or
      packed-file/pixel data) + dimensions. Name-matching misses this and risks false merges; hashing
      is the backbone.
    - **Three signals:** (a) **exact-content duplicates** (same hash, different datablocks/paths) →
      LOSSLESS collapse to one shared image, remap users, purge rest (biggest win); (b) **already-
      shared many-user** images → report (so F5 counts once); (c) **partial material overlap**
      (materials sharing most of their texture set) → near-dup material clusters, ties to F3 node-graph
      fingerprint.
    - **Build a texture→materials→objects usage graph** so blast radius is visible before merging.
    - **Hard constraints:** hashing a 60GB closure is slow → modal scan w/ progress+pause (like
      dep-scan) + **cache by (path,size,mtime)**; offline-capable (BAT reads refs, hash on-disk files,
      no Blender load = crash-safe); scope = current file first, recurse on request (this is the
      deferred **M6 cross-file census** re-scoped to textures). Packed images hash from packed data.
    - **Feeds F5:** overlap quantifies savings ("47 copies → 1, −X GB disk, −Y GB est RAM") = the
      before/after diff.
    - **F6 = 3 layers:** relink (fix missing) → name-family consolidation (identity-verified) →
      content-overlap analysis (hash-based deep dive).
  - **SEPARATE (not textures):** the huge `KEKey … not linkable, but is flagged as directly linked`
    blend.writefile errors = broken shape-key/override hierarchy from the dependency loops (the
    Asset_bundle/human_bundle/People1_v5.1/materialMaster cycle). Untangle via break-circular work;
    not the magenta.

**Requirement change (user, 2026-06-21):** today the **"Fix Paths"** button
(`ops/relink.py::ASSETDOCTOR_OT_fix_library_paths`, apply=True) does **two distinct jobs in one
all-or-nothing click**:
1. **Relink missing libraries** — search folders for a same-named `.blend` and repoint the broken
   library link (the "fix folders" / find-the-file job; Phase 3b, `relink.find_relink_candidates`).
2. **Normalize paths** — absolute→`//`-relative + backslash→forward-slash on the libraries that
   already resolve (the "fix paths/links" job; Phase 3a, `relink.plan_library_fixes`).

**These must be separated, AND the relink job must be targetable per-link.** Real case: a file with a
**single broken link to a materials library** — the user wants to fix **that one link specifically**,
not run a bulk pass over every library.

Design to flesh out (report-first + backup stays):
- **Split the UI into two independent actions** — one for relinking missing/broken libraries, one for
  path normalization. Don't force both.
- **Per-link selection** for the relink action: list each broken/missing library link as its own row
  (with the candidate match found, if any) and let the user fix **just the selected one(s)** — likely
  checkboxes + a single "Fix selected" button (matches the user's stated checkbox-over-per-row-button
  preference in the deferred UI batch, items (i)/(j)).
- Also allow **pointing a broken link at a file the user picks** (manual relink target), not only the
  auto-found same-name candidate — needed when the materials lib lives somewhere the folder search
  doesn't cover or the name differs.
- Keep `core/relink.py` bpy-free + add tests for the per-link plan (one selected link → only that
  `lib.filepath` changes; others untouched).

## Scope/design expansion — DISCUSS 2026-06-16
- [ ] **Expand the add-on's design & purpose** — user wants a broader conversation about where
  AssetDoctor is headed (next session). Capture goals before building.
- [ ] **UI placement: Properties editor vs N-panel.** User likes the layout of a "Scene Debug"
  panel that lives in the **Properties editor > Scene tab** (image-blocks count, list materials by
  shader, missing node links, empty material slots, list users for a datablock). Feasible: a panel
  moves to the Properties editor by setting `bl_space_type="PROPERTIES"`, `bl_region_type="WINDOW"`,
  and `bl_context` (e.g. "scene"/"object"/"render"/"material"); `bl_category` (N-panel tab) no
  longer applies there. Parent/child collapsible sub-panels still work via `bl_parent_id`. Decide:
  move entirely, or offer both locations (a prefs toggle re-registering the panels' parent), and
  which Properties tab. Some of that "Scene Debug" functionality (list users for a datablock, empty
  material slots, materials-by-shader) overlaps AssetDoctor's diagnostics — fold into the roadmap.

## Design session outcome (2026-06-16) — three pillars + F7 is the new lead

Driven by a real problem: `PSM_Stage_v5.1.blend` + `v2.0_PSM_Final_SoundStage.blend` in
`…\2018\November - Canaletto` use too much memory and crash on load with thousands of
`lib.override.resync | WARNING Levels of indirect usages of libraries is suspiciously too high,
there are most likely dependency loops` (KEKey.553 in People1_v5.1 ↔ MECC_Base_Body.008 in
human_bundle).

**Offline recursive scan (BAT, via `tools/scan_recursive.py`) of the SoundStage file found:**
- 227 MB file with a **60 GB+ dependency closure** — the "low-poly stage" link transitively drags
  in the full `ThePiazzaSanMarco.blend` (19 GB) + `People1_v5.1` (15 GB).
- **Same library referenced via different paths** → duplicate library blocks → the indirect-usage
  explosion. human_bundle linked both `//..\..\..\libraries\human_bundle.blend` and absolute
  `E:\…\libraries\human_bundle.blend`; **People1_v5.1 references materialMaster two ways in one
  file** (`//materialMaster.blend` ✅ and `//..\..\..\materialMaster.blend` ❌ MISSING); botaniq libs
  via **three** roots (dead `D:\BlenderLibraries\…`, two Geo-Scatter paths).
- **6 file-level circular library links** (already caught by `core/graph.find_cycles()`):
  PSM_Stage⇄ThePiazzaSanMarco, asset_bundle⇄LS, Structure⇄People, Structure⇄People1,
  ThePiazzaSanMarco⇄PSM_Awnings, asset_bundle→LS→ladyShallott_human→asset_bundle.
- Link-count census: materialMaster 11×, human_bundle 9×, bq_Library_Materials 9×, asset_bundle 7×;
  + a missing materialMaster and ~18 missing botaniq plant libs; mixed slashes nearly everywhere.

**Project structure (user):** stage = buildings; ~50 background people/animals (being merged into
stage); main characters in a library; a low-poly stage is linked into the SoundStage file, main
characters appended + animated there; background chars from a library; a material library was linked
to both char files then onward — i.e. a **multi-hop indirect-link chain**
(`materialMaster → char/people files → PSM_Stage → SoundStage`) that inflates indirect-usage levels.

**Three pillars (reprioritized):**
1. **Link & Dependency Doctor (F7) — THE LEAD** (the actual crash/loop/bloat fire). Below.
2. **Footprint reduction** (memsaver-like) — **ANALYZE-ONLY for now** (user, 2026-06-16): identify
   oversized-texture downscale candidates + high-poly mesh-decimate candidates (background-first).
   No lossy mutation yet; user may later have us review memsaver's code to decide build-vs-handoff.
   Keep clearly separated from lossless cleanups (it changes the render).
3. **Before/after diff** — cross-cutting; the "see the difference" requirement (Phase 5 below).

**Cross-cutting requirements (apply to all of F7 and retrofit to F2/F3):**
- **Tailorable make-local & dedup**: selectable by **type** (all materials), by **scope** (one
  collection), and by **individual item** — not all-or-nothing.
- **Inspector UI** modeled on the "Scene Debug"-style panels the user likes (image 2 = gold
  standard): count badges (`[2]`), `[L]` linked markers, `[Not in Scene]` flags, per-row checkboxes,
  type-dropdown + datablock-picker; group + group/individual selection, varying by function.
  Build the selection model **once** and reuse (pairs with the check-registry idea).
- **UI/UX performance is a hard constraint** — Blender's built-in path editor is too heavy and
  crashes these files. Virtualized `UIList` (v0.1.10) is the right direction; keep it light.
- **Progress + status + PAUSE for BOTH offline and live diagnosis** (user, 2026-06-16). Not just a
  progress bar + ESC-cancel — the modal must support **pause/resume** (recursive scans over multi-GB
  files take minutes). Design: `core/depscan` exposes a **step-generator** so the modal drives it,
  shows per-file status, and can hold between steps. Extend `ops/progress.ModalProgressMixin` with a
  PAUSE state (a WM `assetdoctor_op_paused` bool + a Pause/Resume button beside the ESC hint; while
  paused the timer tick yields without advancing the generator).
- **Project *folder* scan is dropped** — the need is **single-file + recursive link-following**
  (default = current file). Supersedes the old Link Map v2 folder mode.
- **UI placement DECIDED (user, 2026-06-16): the MAJORITY lives in the Properties editor > Scene
  tab**, not the N-panel — this is scene-data hygiene, not a 3D/render/texture activity. Some
  aspects may stay in the N-panel (TBD as we build). Tech: Scene-tab panels set
  `bl_space_type="PROPERTIES"`, `bl_region_type="WINDOW"`, `bl_context="scene"` (no `bl_category`);
  sub-panels nest via `bl_parent_id`. **Implications to handle:** the shared modal progress bar (now
  drawn on the N-panel parent `ASSETDOCTOR_PT_main`) and the Report/Resource `UIList`s must render in
  the Scene-properties parent too — likely a new `ASSETDOCTOR_PT_scene_root` (Properties/WINDOW/scene)
  hosting the progress bar + F7 inspectors + reports, with the N-panel kept only for whatever we
  explicitly decide belongs there. Revisit the v0.1.x panel registration accordingly.

### F7 — Link & Dependency Doctor — phased plan
Two analysis engines: **offline file-graph** (BAT — works on any file unopened; prototyped in
`tools/scan_recursive.py`, reuses `core/blendscan` + `core/graph`) and **live datablock graph**
(bpy `user_map()` on the current file, for per-datablock users/overrides/retargeting).

- [ ] **Phase 1 — Diagnose: recursive dependency scan (offline, read-only).** Productionize the
  prototype into `core/depscan.py`: recursive single-file walk; per-link classification (missing,
  absolute, mixed-slash, outside-root, **drive-root mismatch**, **duplicate ref to same resolved
  lib**, **same lib via different paths** across files); file-level cycles (have it); library
  link-count census. UI: single-file picker (default = current file) + "Scan Dependencies" → the
  inspector tree grouped by issue/file with badges + severity + `[L]`/missing flags. Unit-test
  classification + cycles on fixtures. **Shippable alone; helps the two files immediately, no render
  risk.**
- [ ] **Phase 2 — Diagnose: live datablock link map (current file).** Walk `bpy.data` via
  `user_map()`: per-datablock library source + users (which meshes/objects) + override status.
  **Override dependency-loop detection** (datablock-level cycle search — the KEKey↔MECC case).
  **Duplicate-datablock census** (the `.NNN` families). UI: "List Users for Datablock" inspector
  (type dropdown + datablock picker + users list), per the screenshot.
- [ ] **Phase 3 — Treat: path normalization & remap (lossless, batch, tailorable).** Make-relative,
  fix mixed slashes, **drive-root prefix remap** (D:\→E:\ rules), **dedupe duplicate library blocks**
  (merge two LIs → same resolved file). Report-first + backup; in-session `library.filepath` +
  reload, or offline BAT rewrite. Select which libs/rules apply. Pairs with the F6 relinker item.
- [ ] **Phase 4 — Treat: datablock link retargeting (HEADLINE — user's explicit ask).** Per
  datablock/selection: **make local** OR **repoint to a more direct library** (collapse multi-hop
  chains, e.g. material → link directly from materialMaster). Granular make-local by
  type/collection/item (the tailorable requirement; retrofit F2). Break override loops by localizing
  the offending override. Report-first + backup + before/after.
- [ ] **Phase 5 — Before/after diff (cross-cutting).** Snapshot library count, per-type datablock
  counts, duplicate-family counts, est. RAM, resync-warning count → apply → re-snapshot → diff
  report. Generalizes the Automated Cleanup savings summary.

(Prototype + raw scan output live in `tools/scan_recursive.py` / `tools/_scan_soundstage.txt`.)

## Automated Cleanup (was NEXT major feature — requested 2026-06-15; now behind F7)

Goal: a one-click pipeline that runs the chosen cleanups together, with a combined report and a
before/after/savings summary. Gated on the individual modal sections being verified in the UI.

**UI restructure (nested collapsible sub-panels):**
- **Automated Cleanup** — new sub-panel at the **very top** (`bl_order` negative), default **open**.
  - An **include checkbox per function** (Scene BoolProps, persisted in the file).
  - **Report Only** button → runs each included function's *report* path and shows one **combined
    report** (a section per function).
  - **Apply & Report** button → applies each included function and produces a
    **before / after / savings** report.
- **Manual Cleanup** — new sub-panel, default **collapsed**, that **parents the existing per-
  function sub-panels** (Make Local, Duplicate Materials, Orphans, Duplicate Geometry) as nested
  children. (Project link-map + Resource Analyzer are analysis, not cleanup — leave them as their
  own sections; Utilities stays last.) Blender supports nesting `bl_parent_id` chains.

**Proposed design / decisions (confirm before building):**
- **In-scope cleanups + run order** (order matters — later steps clean up what earlier ones
  orphan): 1) Make Local *(optional — see below)* → 2) Duplicate Materials dedup → 3) Duplicate
  Geometry instance → 4) Orphans purge **last**. Resource Analyzer is **not** a toggle; it's the
  before/after *measurement*.
- **Make Local in the pipeline?** It's a transformation with modes (New File / In Place), more
  destructive than the others. Recommend: offer it **off by default**, **In Place only** when
  ticked (New File's copy+revert doesn't compose with a combined apply).
- **One backup** at the start of Apply (single restore point), not one per function.
- **Savings metrics:** snapshot `core.resource` totals (est. RAM / VRAM) + datablock counts
  (materials, meshes, images, libraries, orphans) **before and after**; report deltas. True **disk**
  savings needs a save (note it, or offer "save after"). Per-function counts (remapped/removed/
  purged/localized) come from each step.
- **Combined report:** new feature key (e.g. `auto`) in `report_store`; one report with a section
  per function + a top **savings summary**.

**Implementation:** reuse `ops/progress.ModalProgressMixin` — the automated op's `run_steps`
`yield from` each included function's steps in sequence (weighted progress across steps, ESC
cancels between steps; cancel after the single start-of-run backup is safe). To avoid duplicating
logic, refactor each function's core work into shared helpers returning `(report, apply-counts)`
that both the manual op and the automated op call.

**Decisions (locked 2026-06-15):**
- (a) **Make Local IS offered** in the pipeline but **off by default**, and runs **In Place only**
  when ticked (per recommendation).
- (b) **Apply & Report offers to save the file afterwards** so disk savings are real (prompt/option).
- (c) **Automated open by default, Manual collapsed by default** — confirmed.

## Bugs found in v0.1.8 testing (2026-06-15)
- [ ] **F2 progress bar not visible for Make Local (report + apply In Place).** On a huge file
  (human_bundle.blend, ~8 GB) the user saw no progress bar. Causes: (1) the **report/dry-run path
  has no modal** (invoke→execute) by design — add one; (2) for **apply**, the heavy phases run
  *synchronously in `invoke()` before the modal starts* — `_prepare` (gather all linked) and
  `auto_backup` (saving an **8 GB** copy = the long freeze) — and then the bulk
  `make_local(type='ALL')` is one blocking call. So the bar only animates during the minor per-ID
  passes. Fix: move gather + backup into the generator/`run_steps` so a "Backing up…/Making all
  local…" status shows first; force a redraw before each big blocking step. (Consider migrating F2
  to `ModalProgressMixin`.)
- [ ] **Make Local "In Place" does NOT fully localize a complex file.** Forensic diff of
  human_bundle.blend before/after (offline BAT): it purged ~100k datablocks (MA 609→312, IM
  1903→1315, NT 796→678, ~99k DATA) — good cleanup — **but left `materialMaster.blend` still
  linked** (1 LI block remains; the lib exists and is resolvable, path just re-stored relative to
  the new file location). Objects/meshes unchanged (OB 6371, ME 5832 — identical). So the localize
  loop stops before removing the last library (likely the no-progress safety break or a remaining
  user/override). Needs investigation: why does one library survive, and should In Place guarantee
  zero libraries or report what it couldn't localize.
  - **Strong lead (2026-06-15):** re-running on the same file **after making everything visible**
    fully localized (0 libraries). `bpy.ops.object.make_local(type='ALL')` works on the **view
    layer**, so objects in **hidden/excluded collections** are likely skipped, leaving their data +
    library linked. Fix: before the bulk pass, temporarily un-exclude/reveal all collections (or
    don't rely on the operator for completeness — the per-ID passes already iterate `bpy.data`
    directly, so make sure they aren't stopped early by the no-progress break on this case).
    Restore the original visibility/exclusion afterward so we don't perturb the user's scene.
- [ ] **Guard against running mutate-in-place on a shared LIBRARY file.** human_bundle.blend is a
  library other scenes link thousands of datablocks from; make-local+purge renamed/removed its
  datablocks, which can break links from dependent files (and downstream library overrides — e.g.
  posed characters reverting to rest pose). Consider detecting "this file is likely a linked library
  / asset source" and warning before In-Place mutation (or steering to New File).
  - **Warning-gating (user, 2026-06-15):** the warning should fire **unless** the user has **scanned
    the project folder (F1 link map) to identify all links and is working top-down** (cleaning the
    leaf/source files in dependency order). If they've mapped the project and are working top-down,
    suppress it — they know the impact. So the guard is tied to the link-map workflow: a recent F1
    scan of the containing project + a notion of "this file's place in the dependency order". Flesh
    out the design when this item reaches the queue (pairs with Link Map v2).

## Link Map v2 — single-file scan + visual report (requested 2026-06-15)
- [ ] **Scan mode: whole folder OR a single file.** Today F1 (`scan_folder`) only takes a
  directory. Add a **single-file** mode that scans one `.blend` (the current file or a picked one),
  identifies its links and their **status**, and **recursively follows dependent files** to build
  that file's dependency tree. Reuse `core.blendscan.scan_file` (already exists) + a recursive
  walk; the folder mode stays as-is. UI: a mode toggle (Folder / Single File) + a file field
  (default = current file) in the Project section.
- [ ] **Visual link/status report.** Show the dependency graph **visually** with per-link status
  (OK / missing / absolute-path / outside-root, etc.). Options to weigh:
  - **In-panel:** reuse the expandable tree widget with severity icons/colors (cheap, no deps).
  - **Graphviz DOT → SVG/PNG:** already export `.dot`; enhance it with **status colors** (red =
    missing, amber = absolute, green = OK) and node labels, render to SVG for a real graph.
  - **Standalone HTML report:** self-contained interactive graph (e.g. embedded vis/d3) written
    next to the file — best "visual" but heaviest. Decide rendering target with the user.

## Progress & responsiveness — ALL actions
- [x] **Progress bar + status text for every action** — DONE for **F1, F2, F3, F4, Geometry, and
  Resource Analyzer**. `ops/progress.ModalProgressMixin` packages the pattern (subclass supplies a
  `run_steps(context)` generator yielding `(fraction, status)`; `execute` drains it, the modal
  steps it under a per-tick time budget with ESC-to-cancel). The heavy per-datablock loops are
  chunked via `_gather_steps`. **Only Profile Render** stays synchronous (a single render call
  can't be chunked) — left intentionally.
- [x] **F2 (Make Local) performance on complex files.** Was: per-id
  `make_local(clear_liboverride=True)` over thousands of override/indirect datablocks × multiple
  passes ran **~hours** and stopped logging. **Fixed (v0.1.7):** one bulk
  `bpy.ops.object.make_local(type='ALL')` (internally batched) does most of the work, then bounded
  per-ID passes only mop up what it can't reach (linked collections, node groups, un-resolved
  overrides). Bulk pass is `poll()`-guarded and falls back to per-ID on RuntimeError. Plus the
  earlier observability/safety work: per-pass + per-100 heartbeat logging, `log.debug` of each
  datablock (debug log's last line = the hanging call), no-progress safety break, bounded purge,
  and the reversed library-purge user-check fixed. Now **modal** with a progress bar + ESC.
  Verified by `smoke_f2` (both modes still end fully local). **Remaining:** confirm on the real
  botaniq/engon file (user to re-run with the new build).

## New requirement — smart missing-file relinker (F6)
- [ ] **Follow the dependency chain and find/replace missing files.** Beyond F1's *detection* of
  broken links / absolute paths, add an intelligent **resolve** step that walks
  object → material → texture image (and library → datablock) chains and, for each missing file:
  - **suggest** likely matches — search sibling/known asset dirs, apply drive/root remaps
    (e.g. `D:\…` → `E:\…`, the `WindowsApps` Blender-bundle path → the installed datafiles),
    fuzzy-match by filename/basename;
  - offer **apply**: relink single, or **batch** "remap all under root X to root Y" /
    "replace path prefix A→B", with a **dry-run preview** first (report-first + backup).
  BAT can rewrite paths offline; in-session we can also set `image.filepath` / `library.filepath`
  and reload. Pairs with F1 (which already finds the problems). Real-project data shows common
  patterns: same file under different drive roots, and absolute paths into per-machine library
  folders — good candidates for prefix-remap rules.

## Report UI v2 (from real-project testing)

**Root cause noted:** the N-panel doesn't virtualize manually-drawn rows, so a large report
(hundreds of findings) leaves rows blank past a point. **Mitigated** (v0.1.6) by collapsing
categories by default + a 200-row draw cap + Export hint. **FIXED (v0.1.10):** Report and Resource
panels now use a real `UIList` (`ASSETDOCTOR_UL_tree` over a `CollectionProperty` rebuilt from
`flatten_visible`) — virtualized + scrollable, so rows render for any size; the 200-cap/hint were
removed. Data path verified by `smoke_report`; **UIList draw still needs interactive UI confirm.**
See docs/images/BUG-blank-report-lines.png for the pre-fix bug.

- [ ] **Focus the Outliner on a clicked finding** (requested 2026-06-15). Clicking a finding
  already selects + activates the object, but the Outliner doesn't scroll to it. Feasible & small:
  after setting `view_layer.objects.active`, loop open Outliner areas and call
  `bpy.ops.outliner.show_active()` under `context.temp_override(area=outliner, region=WINDOW)`
  (expands parents + scrolls to the active object). No-op if no Outliner is open; wrap in
  try/except. Add a `_focus_outliner(context)` helper in `ops/report_store.py`, called from
  `ASSETDOCTOR_OT_select_datablock.execute`. UI-only → verify interactively.
- [x] **UIList rework** for Report + Resource panels (fixes blank rows definitively for any size).
  **DONE (v0.1.10)** — `ASSETDOCTOR_UL_tree` + `ASSETDOCTOR_PG_tree_row`; pending live-UI confirm.
- [ ] **Collapsible "Report" master heading** with a **section per report**, and a *"run a
  scan above"* hint when none has been run.
- [ ] **Report selector → toggle**: the per-report button should toggle the report contents
  visible/hidden.
- [ ] **Resource Usage:** default the Image/Mesh type groups **collapsed**; put **column
  headers at the top** (RAM | VRAM | disk) instead of repeating units on every row; make the
  **columns sortable** by clicking the header.
- [ ] **Duplicate Materials report:**
  - summary line (e.g. "50 duplicated materials; est. ~X savings" — file-size savings is
    cheap/accurate from datablock sizes; live-memory savings is an estimate).
  - **interactive include/omit + choose-which-to-keep** without busy per-row checkboxes.
    Options to weigh: a UIList with a single **"keep" radio/icon column** per group + an
    **include** toggle; or set the canonical by clicking a row; or drive it from the existing
    white/black-list prefs (name-based) surfaced in the panel. (`title` capitalized in v0.1.6.)
- [ ] **Export filename:** suggest a sensible name **with extension** (currently pre-fills the
  `.blend` name including its `.blend` extension); default to e.g. `AssetDoctor_<feature>.txt`.
- [x] **Click-to-select in Outliner** — already implemented (click a finding → selects the user
  object(s); Outliner follows the active object). Note: F1 link-map items are **file paths**, not
  datablocks, so those aren't selectable (expected); F3/F4 datablock findings are.

## Dedup preferences (global)
- [ ] **Keep-local vs keep-linked preference**, in **Add-on Preferences** (global options),
  **separate for materials and for meshes** (e.g. two enums: Materials → {prefer local, prefer
  linked}; Meshes → {prefer local, prefer linked}). These set the canonical tie-break for F3
  (materials) and the geometry-instancing dedup; the white/black lists still override. Today
  both hardcode "prefer local" — this makes it configurable per data type.

## Decided — to implement (batch)
- [x] **Debug log: fresh per file-open** — DONE (v0.1.7): handler opens in `mode="w"`, and a
  `load_post` handler re-arms a fresh log when a file opens with the toggle on.
- [ ] ~~(original note)~~ **Debug log: fresh per file-open** (decision made; not a continuous append). The log
  captures one reproduction to send for diagnosis, so each session should be a clean,
  single-session file. Implementation:
  - open the handler in `mode="w"` (truncate) so enabling starts a fresh log;
  - add a `bpy.app.handlers.load_post` handler that re-arms/truncates the log when a file opens
    with the toggle on — fixes the current gap where the per-file `Scene.assetdoctor_debug_log`
    `update` callback doesn't fire on load, so an "on" toggle doesn't reactivate after open.
  - (If cross-session history is ever wanted instead, switch to a size-capped
    `RotatingFileHandler` rather than plain append.)

## Done
- [x] **Collapsible panel sections** — each feature is a native child panel of the main panel
  (own collapse triangle + Blender-persisted open/closed state); Utilities defaults closed.
- [x] **Clickable Add-on Preferences** — the static "Lists/backups" hint became an
  `assetdoctor.open_preferences` button inside Utilities that opens Preferences with the add-on
  expanded (`preferences.addon_show`, with a userpref-show fallback).
- [x] **(5) Split Project section** into a folder path field (`Scene.assetdoctor_scan_dir`)
  + a separate **Scan Link Map** button. Picking a folder no longer auto-runs.
- [x] **(1) Tooltips** — every operator has a `bl_description`; the multi-variant buttons
  (Make Local New File/In Place/report, dedup apply/report, orphans purge/report) use a
  `description(cls, context, properties)` classmethod for accurate per-button tooltips.
  Scene props carry descriptions too.
- [x] **(2) Utilities section + Enable Debug Log** — `Scene.assetdoctor_debug_log` toggle in a
  new Utilities box. Enabling attaches a DEBUG file handler writing `debugLog.txt` next to the
  .blend (or Blender's temp dir if unsaved). All operators log via the `assetdoctor` logger
  (`log.py`): INFO findings go to console + file; DEBUG detail (per-file scan, per-remap,
  localize passes) goes to the file only. Suitable for a remote user to send back.

## Done (cont.)
- [x] **(4) Progress / responsiveness.** Folder scan is now a **modal operator**: a
  time-bounded batch of files per `wm.event_timer` tick, ESC to cancel, live progress via
  WindowManager props (`assetdoctor_scan_active/_progress/_status`) shown as a `layout.progress`
  bar in the panel, plus the wait cursor and status-bar text. `core.blendscan` split into
  `new_scan_result`/`scan_into`/`map_folder` and `f1_linkmap.report_from_scan` so the modal
  and synchronous paths share logic. Synchronous `execute` retained for scripting/tests.
  Core verified by pytest (incremental == synchronous); modal/progress is interactive-only
  (can't run headless) — verify by running the scan in the UI.
- [x] **(doc link)** Documentation icon (HELP) right-aligned on the panel header via
  `draw_header`, opens `DOC_URL` (placeholder GitHub URL — update on push). `website` also
  added to the manifest.

## Planned — milestone "M7: Reporting + Resource Analyzer (F5)"

Decided sequencing (user): build the **shared tree/report widget** and the **geometry-dedup
engine** first, so the report viewer (#3), the instance-savings detector, and F5 all reuse
them instead of duplicating work. Proposed build order:

1. **Shared tree/report widget.** ✅ DONE. `core/tree.py` (TreeNode/Row, `report_to_tree`,
   `flatten_visible`) + `ops/report_store.py` (stash + toggle/clear/select) + the **Report**
   panel rendering an expandable tree with severity icons and click-to-select. Serves **(3)
   the report viewer** and will back F5's outliner display. Verified by `test_tree.py` +
   `smoke_report.py`.
2. **Geometry dedup engine.** Extend fingerprinting (mesh done; add curve/other geometry) to
   find identical-but-separate datablocks used by different objects → "instanceable"
   candidates. Apply = repoint `object.data` to one shared datablock (the geometry analogue of
   F3's material remap). This also subsumes the instance-savings part of F5 and overlaps M6.
3. **(F5) Resource Analyzer.** Analyze button → the tree from step 1, rows showing rolled-up
   **estimated RAM / estimated texture-VRAM / accurate disk**, biggest-first; shared/multi-user
   data counted once and flagged (surfaces "N copies → could be 1"). Feasibility:
   - Disk: accurate (`.blend` size + external dep sizes via BAT; per-block sizes offline).
   - System RAM: ESTIMATE from a documented model (mesh counts; image `size×channels×depth`
     or `packed_file.size`). No per-ID byte API in Blender.
   - Texture VRAM: ESTIMATE only (`res×channels×~1.33` mipmaps); no per-datablock VRAM API.
   Label estimates clearly; granularity toggle for the GPU column.
4. **(F5) "Profile Render" button** ✅ DONE (v0.1.5). Renders the current frame and reports
   real **peak process RAM** (OS-level). Real VRAM not attempted (no Python API); F5 estimates
   cover VRAM. `core.resource.peak_process_ram_bytes` + `smoke_profile.py`.

Note: the duplicate→instance detection is fully available from the **loaded** file (no
load-time profiling) — it's the existing fingerprint engine plus `data.users` sharing checks.
Only step 4 (real peak memory) needs a live render.

## Done — milestone "M8: Report system v2" (v0.1.4)
- [x] **Persistent per-type reports** — per-feature registry + selector; clear removes only the
  shown report. F5 resource separate.
- [x] **Per-line tooltips** — row labels are tooltip-bearing buttons (full text on hover);
  clicking does the row's natural action.
- [x] **Print/export** — Export… on Report + Resource panels → `.txt` (indented) or `.csv`.
- [x] **Select-in-Outliner** — non-intrusive select+activate (Outliner follows active);
  material slot highlighted; orphan/no-user → hint to Blender File / Orphan Data view.

### (original M8 notes for reference)
- [x] **Persistent per-type reports.** Today one slot (`assetdoctor_last_report`) is overwritten
  by each scan. Change to a **per-feature registry** (F1/F2/F3/F4/Geo each keep their own report
  + expanded state, persisting until that scan is re-run). Report panel gets a small selector
  (row of toggle buttons or enum) to choose which to view. F5 resource is already its own slot.
- [ ] **Per-line tooltips (full text).** The N-panel is narrow and lines truncate. Render each
  tree row's label as a no-emboss operator whose dynamic `description()` returns the full text
  (e.g. the full broken-link path), so hovering shows everything. Bonus: the whole row becomes
  clickable (parents toggle, leaves select).
- [ ] **Print / export report.** "Print" = save the current report to a formatted `.txt` (and/or
  CSV) via a file browser, for printing/sharing. Add an Export button to the Report and Resource
  panels (F1 already writes JSON/CSV/DOT; generalize to all).
- [ ] **Select-in-Outliner (needs your feedback — see chat).** Selecting a finding should also
  reflect in the Outliner. Recommendation: set active + select the user objects (Outliner follows
  active) **without** force-opening/rearranging editors; for a multi-use material, select all
  user objects + set the active object's material slot; for orphan/unused datablocks (no object
  users) or when no Outliner is open, show a status hint to view via Outliner → Blender File /
  Orphan Data (the API can't reliably select there).

## New requirement — auto-updates
- [ ] **Auto-updates.** Blender's extension system updates automatically only for extensions
  installed from a **repository URL**, not from a disk `.zip`. Recommended approach: publish a
  **self-hosted extension repository** (generate `index.json` + host the zips on GitHub
  Releases/Pages), which the user adds once in Preferences → Get Extensions → Repositories;
  Blender then checks/updates natively. No custom updater code needed. (A legacy in-addon
  GitHub-release updater is the fallback if we never host a repo.) Blocked on the GitHub repo
  existing — pairs with the first push. Also: keep `version` bumped (3rd digit per step) so the
  repo index advertises new versions.
  - **Effort: low.** No in-addon updater code. One-time: a publish step (build zip +
    `blender --command extension server-generate` → `index.json`, host on GitHub Pages/Releases)
    + user adds the repo URL once. Per release: re-run publish (script/GH Action). Local disk
    installs stay manual by design. Blocked only on the repo existing.

## Versioning
- [x] **Per-step patch bump + visible version.** Manifest `version` is bumped on each completed
  step; the N-panel header shows `vX.Y.Z` (read from the manifest) so the installed build is
  verifiable at a glance.

## Future / deferred
- [ ] **M6 — F1 cross-file duplication census** (deferred by user; may be re-scoped after
  testing). Largely folded into M7 step 2's geometry-dedup engine; the cross-*file* count
  still needs an offline fingerprint path (headless-Blender pass per file, or a BAT-level
  signature).
- [ ] First git commit once the tested baseline is accepted.
