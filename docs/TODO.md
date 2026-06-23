# AssetDoctor — TODO / backlog

## ⏩ SESSION RESUME (as of v0.2.33, 2026-06-23) — read this first

**State:** local dev **v0.2.33** (published channel still 0.1.9). Suite **295 green**. **BATCH D BUILT**
(see "BATCH D" below) — **RESUME WITH BATCH E next session.**

- **Batch D @ v0.2.33 — headless dry-run render for warnings (#12), BUILT, needs live-Blender verify.**
  `core/dryrun.py` (bpy-free, 11 tests): `build_dryrun_script`/`build_dryrun_command` build a throwaway
  low-res (10%, 1 sample), `write_still=False` render script + the subprocess argv (`--background
  --factory-startup <blend> --python <script>` — factory-startup deliberately keeps unrelated add-on
  startup noise out of the captured log); `classify_line`/`parse_render_log` turn the captured stdout/
  stderr into a `Report` (categories `missing_image`/`driver_error`/`render_error`/`render_warning`,
  deduped with "(xN)", ✓-clean when nothing found). `ops/dryrun_render.py::ASSETDOCTOR_OT_dryrun_render`
  (`ModalProgressMixin`) launches a SEPARATE `bpy.app.binary_path` process against the file ON DISK (save-
  first guard, same idiom as Scan Deps), polls non-blockingly (small sleep avoids busy-spin in both modal
  and synchronous-drain paths) with a 5-minute timeout, parses the log, stashes report `"f9"`. New "Dry-run
  render" box in `ASSETDOCTOR_PT_scene_deps` (after Duplicate Textures, before the Reports selector);
  `"f9"` added to `report_store.FEATURES` + the panel's `_F7_FEATURES` + `core/tree._CATEGORY_TITLES`.
  Distinct from F5's in-process Profile Render (`ops/resource.py`) — this never touches the live session.
  **VERIFY:** run it on a file with a missing texture or a broken driver → report lists them; a clean file
  → ✓ no warnings; Cancel/ESC kills the subprocess cleanly.

**Previously, Batch C @ v0.2.30–0.2.32** (all BUILT + WIRED, still needs live-Blender verify — mutates
links/datablocks, see "★ BATCH C" below for exact test steps per feature): **#2** missing-data-block
reconnect (`core/reconnect.py`, `ops/datablock_reconnect.py`, "Datablock Reconnect" box) — only triggers
on BROKEN placeholders. **#3 generic half** Duplicate Data-blocks merge (`core/datablock_dedup.py` —
extracted the type-agnostic algorithm out of `core.imagededup`, now a thin wrapper over it —
`core.fingerprint.fingerprint_action`, `ops/datablock_dup.py`, "Duplicate Data-blocks" box; excludes
Materials/Meshes/Images, which already have F3/F5/F6). **#2b "Examine Library"**
(`ops/examine_library.py`, "Examine Library" box) — for a chosen WORKING library, list everything it
provides and retarget away from it (local match → other-library match → Make Local or a manual per-row
file+item pick), even though nothing is broken. Real case: `Asset_bundle.blend` causes circular
references, user wants to stop depending on it.

Also still open from a live-test feedback batch (NOT yet built): the KEKey/shape-key half of Batch C's
#3 (needs its own fingerprinter — shape keys must match their owning mesh), the deferred folder-wide
search for Examine Library, and the rest of "★★ LIVE-TEST FEEDBACK BATCH 2" (#1 synonym-table+inverse-
pairs design, #2/#10 report-formatting pass, #4 auto-suggest feasibility). **NEXT SESSION: Batch E**
(node-graph substitute-material confidence, idle-scan feasibility prototype, then Batch 5's N-panel→
Properties migration + UIList virtualization — see "BATCH E" below) — pick up the live-test-feedback
leftovers above whenever convenient, they're independent of Batch E.

## ★★ LIVE-TEST FEEDBACK BATCH 2 (user, 2026-06-23 — 10 items, screenshots from a real PSM_Stage file) ★★

**DONE this session (quick, high-confidence, no design ambiguity):**
- **#3 fixed — "(no material)" triangle never stayed expanded.** Root cause: `_draw_missing_textures`
  used `UNGROUPED = "\x00"` as the sentinel key for the ungrouped category. Blender's `StringProperty`
  round-trips through a C string, which truncates at the first NUL byte — so writing a lone `"\x00"` into
  `assetdoctor_tex_expanded` read back as `""` on the next redraw, and the triangle could never register
  as expanded. Changed the sentinel to `"\x02"` (a control byte, but not NUL).
- **#6 fixed — redundant "Summary" line under Overrides & Dups.** `core.datablock_graph.build_live_report`
  emitted BOTH the flat `"overview"` headline (Batch A, v0.2.28) AND a trailing `"summary"` Finding
  restating the same counts in different words. Dropped the `"summary"` Finding from this report only
  (every OTHER report's `"summary"` category is untouched — they don't have an `overview` substitute, so
  it's still their only top-line total). `test_build_live_report` updated to assert `"summary"` is gone.
- **#8 fixed (needs live verify) — drill-down "jumps to the top".** Expanding/collapsing a report row
  cleared and refilled the ENTIRE flattened-rows `CollectionProperty` from scratch
  (`report_store._fill_rows`) with no change to the `template_list` active index, so Blender's list view
  had no anchor and appeared to jump away from where you clicked on a long report. New
  `report_store.focus_row(wm, prop, key)` finds the toggled row's new position after the rebuild and sets
  the matching active-index WM prop (`assetdoctor_report_index` / `assetdoctor_resource_index`) — Blender's
  `template_list` auto-scrolls to keep the active index visible. Wired into both `ASSETDOCTOR_OT_
  report_toggle` and `ASSETDOCTOR_OT_row_label`'s toggle branch. **Confidence is high but unverified
  headless** (template_list scroll behavior can't be tested without a real UI).

**ROOT-CAUSED, NOT YET FIXED (need a design decision before coding):**
- **#1 — texture-channel synonyms should be user-configurable; gloss/roughness need an "inverse" concept.**
  `core/imagematch._CHANNEL_ALIASES` already maps `"nrm"` → `"normal"`, so the reported Normal-texture
  miss is NOT explained by a missing alias — most likely "Suggest Matches" (the fuzzy fallback) simply
  hadn't been run yet for that material (the screenshot only shows the plain exact-match list, which never
  does fuzzy/synonym matching — see #4 below). The ROUGHNESS-vs-GLOSS case IS a confirmed code gap, though:
  `score_match` HARD-DISQUALIFIES a candidate whose channel differs from the wanted file's
  (`if w.channel and c.channel and w.channel != c.channel: return None`), and `"gloss"` and `"roughness"`
  are currently two separate, non-aliased canonical channels — so a GLOSS candidate can never be offered
  for a missing ROUGHNESS file. Don't just merge them as plain synonyms (gloss is often the visual inverse
  of roughness — relinking one as the other without inverting pixel values would look wrong). Proposed
  design: (a) move the synonym table to an editable list in Add-on Preferences (comma-separated aliases per
  canonical channel, user can add/remove); (b) add a separate "known inverse pairs" table (gloss↔roughness
  to start) so the matcher can still SUGGEST a gloss candidate for a missing roughness file, but flagged
  "inverted — needs an invert to use correctly" instead of either hard-blocking or silently substituting;
  (c) a real "convert/invert" action is a follow-up, separate piece of work (would need to write a NEW
  image file with inverted pixel data, not just relink — not a quick add). Needs scoping with the user.
- **#5 — clarified, not (yet) a confirmed bug.** "Different content — kept separate" means: within a
  `.NNN` name-family, members are grouped by content fingerprint; any fingerprint-group of 2+ becomes a
  lossless merge plan, and if MORE THAN ONE distinct fingerprint exists in the family (or some members are
  unhashable), the whole family is ALSO listed under "kept separate" so the user can see what didn't merge
  — even if part of it already did. So two same-resolution images NOT merging means their content
  fingerprints (dimensions + a file hash) genuinely differ — which can legitimately happen if the same
  texture was re-exported/recompressed at different times (different bytes, same visual result). This is
  plausible, not obviously a bug — but the report doesn't currently say WHY they differ (different
  dimensions vs. same dimensions but different hash), which would help the user judge. Candidate follow-up:
  surface the specific mismatch reason per conflict instead of just "differing content".

**DONE — folded into Batch C @ v0.2.31 (see "★ BATCH C" below for the full build notes):**
- **#7 + #9 — a generic "Duplicate Data-blocks" merge UI + Action-aware fingerprinting.** The Overrides &
  Dups report's 3487 `duplicate_family` findings were mostly `Action` datablocks from undisciplined
  animating (`ObjectName.PoseName`, then `.001`, `.002`, …) — #7 asked whether real content identity could
  be verified before treating them as redundant, and #9 asked for a way to actually ACT on a drill-down.
  Built as Batch C's #3 (generic half): `core/datablock_dedup.py` + `core.fingerprint.fingerprint_action` +
  `ops/datablock_dup.py` + a "Duplicate Data-blocks" box. Actions now get a real content fingerprint (so #7
  is answered: verified, not just excluded); every type in the box gets a keeper-dropdown + Merge Selected
  (so #9 is answered). Materials/Meshes/Images stayed out of scope (existing F3/F5/F6 already own those).
- **#2 — Outliner-style tree formatting + better summary lines, generalized.** Same ask as the existing
  "File Map like the Outliner/Explorer" work (Batch B, #6) and the resolution-variants ask in #10: tighten
  left-margin/indentation across report trees and make every report's TOP line carry real counts (the
  `overview`-headline pattern from #6/Batch A, generalized to reports that don't have one yet, e.g.
  Resolution Variants). Bundle with #10 as one "report formatting" pass — needs the user to point at
  specific screenshots/reports since this touches the SHARED `ASSETDOCTOR_UL_tree` used by every report.
- **#4 — auto-suggest matches without a folder pick.** Today, exact relink is automatic on "List Missing
  Textures" (e.g. doubled-prefix auto-match), but FUZZY suggestions ("Suggest Matches…") need an explicit
  folder (or material/another-.blend) as the candidate pool — there's no "compare every missing texture
  against every OTHER local image already in this file" step that needs zero picking. That's feasible and
  fast (no disk I/O, just name-token scoring over typically hundreds of names) and could run automatically
  right after "List Missing Textures", though for very large texture counts it could still cause a
  noticeable pause — wrap it in the existing modal/progress pattern (`ops.progress.ModalProgressMixin`,
  already used for the folder-search ops) rather than assuming it's always instant.
- **#10 — Resolution Variants needs a real summary line + Outliner formatting + an action.** Currently
  report-only (`core/imageres.py`, intentionally no Apply — standardizing resolution is lossy). Bundle the
  formatting half with #2 above; the "let me act on it" half is a deliberate, separate decision (an opt-in
  lossy standardize-to-one-resolution op) that still needs the user to choose semantics (which resolution
  wins, per-family or global) before building — tracked since Batch 1b, still deferred on purpose.

## ★★ LIVE-TEST FEEDBACK BATCH (user, 2026-06-23 — 13 items on the real PSM/People files) ★★
Worked the quick UI items into **v0.2.27**; the rest is planned into batches below. **Do these batches in
order next sessions.** (Item numbers = the user's original numbering.)

**DONE @ v0.2.27 (UI polish that landed this session):**
- **#1 F8 labels:** reverted always-on-in-tree-mode — labels now reveal on zoom (`scale > 0.5`), so zooming
  in shows names (the user only wanted them to APPEAR on zoom, not always). NOTE: kept the **leaf-at-top**
  hierarchy direction (v0.2.25) — user's screenshot seems to confirm assets-at-top; CONFIRM if still wrong.
- **#4 progress to top:** `_draw_progress` now drawn right under the file/link/unsaved-warning header (was at
  the bottom); removed the early-return so the panel stays visible during a scan. Filename line no longer
  repeats the version (`v…` lives only in the panel header, right of the name — already there via draw_header).
- **#5 Reports header:** the bottom report area always gets a "Reports" header now (a lone report was confusing).
- **#10 Title Case:** button labels title-cased (Scan Deps, Search a Folder (Recursive)…, Suggest Matches…,
  Find Content Dups, Merge Selected (Backup), Resolution Variants (Footprint, Report)…, etc.). Audit the rest.

**INVESTIGATED (root-caused, fix planned):**
- **#8 "ThePiazzaSanMarco.blend broken but not in Libraries":** `ops/relink._gather_libs` walks ALL of
  `bpy.data.libraries`, which includes **indirect** libraries (linked by your linked files), so a
  transitively-missing lib shows as broken though it's not a DIRECT library. FIX = mark direct vs indirect in
  the broken-links list + show who references it (ties into #2). Not a bug per se, but confusing.
- **#9 "Find Content Dups → Dependencies tab highlighted, Duplicate content shown":** `scan_content_dups`
  calls `stash_report(..., "f6dup")`; `stash_report` sets f6dup ACTIVE + rebuilds rows, but f6dup isn't in the
  selector (`_F7_FEATURES`) → selector falls back to highlighting "Dependencies" while showing f6dup rows. The
  real de-dup UI is the INLINE Duplicate Materials/Textures section (keeper dropdown + Merge Selected).
  **FIXED @ v0.2.28** (Batch A, below).

### BATCH A — small UI/report polish — DONE @ v0.2.28, needs live-Blender verify
- **#7 Overrides & Dups summary — DONE.** `core/datablock_graph.build_live_report` now emits a flat
  **`"overview"`** headline Finding first: "N override loop(s) · M duplicate data-block(s) · K library/-ies ·
  J override(s)" (severity escalates to error/warning when loops/waste are present). The redundant
  `override_summary` Finding is gone (its one fact — the override count — now lives in the overview line).
  `core/tree._CATEGORY_TITLES` gained informative titles: `override_loop`→"Override dependency loops (cause
  resync spam / bloat)", `duplicate_family`→"Duplicate data-blocks (.NNN copies — wasted memory)",
  `library_block`→"Linked data-blocks per library". `tree.report_to_tree`'s ordering now hoists `overview`
  ABOVE the collapsible `Summary` category too (generic — only matters when a report has both; no other
  report does yet). Tests updated (`test_build_live_report`, +`test_overview_renders_before_summary`).
- **#13 Safe to Delete verdict — DONE.** `ops/reversedep.check_dependents` now sets two small WM strings
  after building the report — `assetdoctor_dep_verdict` (`"safe"`/`"unsafe"`/`"not_scanned"`/`""`) +
  `assetdoctor_dep_verdict_text` — instead of making the panel re-parse the stashed `f7rev` JSON every
  redraw. `ui/panels.ASSETDOCTOR_PT_scene_deps.draw` shows a color-coded line under "Check What Links This
  File": red `row.alert=True` "⚠ Do Not Delete — N file(s) link X directly[, M more transitively]" when
  unsafe, green-ish CHECKMARK "No Links Detected — Safe to Delete" when clean, red warning when the target
  wasn't in the scanned folder.
- **#9 fix — DONE.** `ops/report_store.stash_report` gained `set_active: bool = True`; all three `"f6dup"`
  call sites in `ops/image_dedup.py` (`scan_dup_textures`, `merge_dup_selected`, `scan_content_dups`) now pass
  `set_active=False` so stashing f6dup (for the inline Export button) no longer hijacks the report selector —
  the Dependencies tab no longer falsely highlights after Find Content Dups.
- **#5/#10 follow-ups — DONE.** Title-cased the remaining legacy N-panel (VIEW_3D) button labels: "Report (Dry
  Run)", "Find Duplicates (Report)" ×2, "Dedup & Remap (Apply)", "Scan (Report)", "Instance & Merge (Apply)",
  "Profile Render (Real RAM)". Audited the Scene panel + the rest of the N-panel too — already consistent
  (small-word lowercase like "a"/"from" intentional, matching the existing style).
- **#11 click → reveal in Outliner — DONE.** `ops/report_store._reveal_in_outliner` (new) — after a
  click-to-select sets the active object, it now also looks across every window/area for an open Outliner and
  calls `bpy.ops.outliner.show_active()` with a `context.temp_override` targeting it (frame + expand the
  hierarchy, like typing the name there). Best-effort/bounded: no-op (silently) when no Outliner is open;
  wrapped in try/except since `show_active` can refuse depending on Outliner display mode.

### BATCH B — File Map / graph presentation (#1 confirm, #6)
- **#6 File Map like the Outliner/Explorer — DONE @ v0.2.29, needs live-Blender verify.** `TreeNode`/`Row`
  gained an optional **`icon`** field (threaded through `node_to_dict`/`from_dict`, `flatten_visible`,
  `ASSETDOCTOR_PG_tree_row`, `_fill_rows`); `core.depscan._build_file_map` sets it per file-map node —
  `ICON_BLEND` ("FILE_BLEND") for a clean in-tree relative link or the root, `ICON_MISSING`
  ("LIBRARY_DATA_BROKEN") for a missing link (wins over absolute, same precedence as `link_issues`), and
  `ICON_EXTERNAL` ("FILE_FOLDER") for a link resolved via an absolute path ("external" to the relative
  project tree); the "File map" wrapper node itself gets a folder icon. Other trees (Missing/Duplicate/
  Resource/etc.) don't set an icon, so they keep today's icon-free look. **Clearer indent guides:**
  `flatten_visible` now also computes a precomputed `"│  ├─ "`-style Explorer connector prefix per row
  (`Row.guide`/`_guide_prefix`, sibling-aware via an `is_last_chain` walked alongside depth) — this is
  universal (every tree benefits, not just the File Map), replacing the old blank `row.separator`
  indentation in `ASSETDOCTOR_UL_tree.draw_item`; depth-0 rows stay unprefixed (today's look). Sizes were
  already right-aligned — no change needed. **Expand All / Collapse All** added too: new
  `ASSETDOCTOR_OT_report_expand_all` op (`feature`/`prop`/`expand` props, reuses `all_keys`) + two
  ZOOM_IN/ZOOM_OUT buttons next to the Reports title row in `ASSETDOCTOR_PT_scene_deps` (works for
  whichever report is active, not just the File Map). "Group by folder" (the "possibly" stretch item) NOT
  done — lower priority, skipped for now. 6 new tests (`test_tree.py` icon/guide, `test_depscan.py`
  file-map icons + circular-node icon); suite 261.
- **#1 confirm** the hierarchical direction with the user (leaf-at-top vs root-at-top) on a real file —
  STILL PENDING, needs a live-Blender look (not a code change).

### BATCH C — ★ THE HEADLINE: datablock-level relink / retarget tool (#2 + #3 + reconnect) ★
This is the user's biggest ask (and the original F7 Phase-4 goal). It SUPERSEDES the earlier "datablock
reconnect" plan — build them together.
- **#2 Relink tool — BUILT @ v0.2.30 (2026-06-23), NEEDS LIVE-BLENDER VERIFY (mutates links).**
  `core/reconnect.py` (bpy-free, 11 tests, suite 272): `suggest_reconnect(wanted, candidates)` → exact name →
  `.NNN` same-base match (`datablock_graph.strip_dup_suffix`) → fuzzy token affinity
  (`imagematch.name_affinity`, floor 0.5) → `Suggestion(target, confidence)`; `ranked_candidates` reorders a
  candidate list so the suggestion sorts first (the safe way to default a dynamic-enum dropdown — explicit
  assignment is fragile, per the keeper-dropdown lesson); `plan_reconnects` batches it per `MissingBlock`.
  `core.missingdata.MissingBlock` gained a `collection` field (the bpy.data attribute, e.g. `"materials"`,
  captured during the scan in `ops/datablock_inspect._iter_missing_blocks`) so reconnect knows exactly what
  to read from a chosen source .blend — no guessing from `kind` (a Python class name that doesn't always
  match the bpy.data attribute, e.g. shape keys are `"Key"` → `"shape_keys"`).
  New `ops/datablock_reconnect.py`: `scan_reconnect_targets` (fills an EDITABLE list, `assetdoctor_missing_
  blocks`, grouped by library — re-scanning preserves each group's already-picked source); `reconnect_pick_
  source` (per-LIBRARY-GROUP file browser — picks ONE source .blend for the whole group, since a broken/
  renamed library's blocks usually all need the same fix) → peeks `bpy.data.libraries.load(path, link=True)`
  WITHOUT assigning `data_to` (so nothing loads yet) to list each needed collection's names, then suggests
  per row; `reconnect_selected` (Apply: backup → batches ticked rows by source_blend → ONE real
  `libraries.load(..., link=True)` per source with `data_to.<attr> = [chosen names]` → `placeholder.
  user_remap(linked)` → remove the placeholder if now unused → re-scan). UI: new `ASSETDOCTOR_PG_missing_
  block` + a "Datablock Reconnect" box in the Scene panel (grouped-collapsible, mirrors the Duplicate
  Materials/Textures shape — group header with a file-picker icon, per-row checkbox + confidence badge +
  target dropdown). **VERIFY:** Find Reconnectable Data-blocks lists missing placeholders grouped by
  library; picking a source .blend per group suggests names (try an exact-name case and a renamed/`.NNN`
  case); Reconnect Selected links + remaps + removes the placeholder, and re-running the scan drops resolved
  rows while groups still missing something keep their picked source.
- **#3 generic duplicate-merge half — BUILT @ v0.2.31 (2026-06-23), NEEDS LIVE-BLENDER VERIFY** (folds in
  the 2026-06-23 live-test feedback #7+#9). `core/datablock_dedup.py` (bpy-free, 7 tests): extracted the
  ALREADY type-agnostic `.NNN` merge-planning algorithm out of `core.imagededup` (which is now a thin
  image-flavored wrapper over it — `tests/test_imagededup.py` unchanged, still green) — `MemberInfo`/
  `MergePlan`/`FamilyConflict`/`plan_merges`/`removable_count`/`victims_for_keeper`, reusable for ANY
  datablock type via `ID.user_remap()` (which is generic). `core/fingerprint.fingerprint_action` added
  (hashes F-curve keyframe co+interpolation per `(data_path, array_index)`, 5 tests) + `ops/extract.
  extract_action`. **Scoped to EXCLUDE Materials/Meshes/Images** — they already have dedicated, more mature
  tools (F3/F5/F6) with their own verified fingerprints; duplicating that path here would just be a second,
  weaker way to do the same job. New `ops/datablock_dup.py`: modal `scan_datablock_dups` walks the OTHER
  audited collections (Object/Node Group/Armature/Action/Texture/Curve/Light/Collection/World/Shape Key/
  Particle — reusing `ops.datablock_inspect._COLLECTIONS`), fingerprints `.NNN`-family members (real content
  hash for Actions only so far; everything else reports "unverified" — never silently merged, per the
  standing safety rule) via one `plan_merges` call (an `"{attr}:{name}"` prefix keeps each type's families
  separate without per-type calls); `merge_datablock_selected` applies via `user_remap`+`remove`, backup
  first. UI: new `ASSETDOCTOR_PG_datablock_family` + a "Duplicate Data-blocks" box (grouped by KIND, keeper
  dropdown per family, mirrors the Duplicate Materials/Textures shape) right under Scan Deps/Analyze. Real
  motivating case (#7): 3487 duplicates on a test file, MOST of them `Action`s from undisciplined animating
  (`ObjectName.PoseName`, then `.001`, `.002`, …) — now both VISIBLE-with-reason for every type AND
  MERGEABLE for Actions specifically. **VERIFY:** Find Duplicates lists Action families (and others,
  unverified); a real duplicate Action family offers a merge; Merge Selected remaps+removes; re-running
  drops merged rows. Add a fingerprinter to `ops.datablock_dup._fingerprint_for` to light up another type.
- **#3 KEKey/shape-key half — STILL OPEN.** The `KEKey.NNN … not linkable but flagged as directly linked`
  write errors come from the broken override/shape-key hierarchy (the override LOOPS the f7live Analyze
  already counts — 202 here). DIAGNOSE + EXPLAIN per block: which datablock is flagged directly-linked but
  can't be (usually a shape Key whose owner is an override). Shape keys ("Key" datablocks, `bpy.data.
  shape_keys`) specifically must match their OWNING MESH before merging — a generic content fingerprint
  isn't enough identity check on its own; needs its own fingerprinter (hash the key block's relative-key
  values keyed to its mesh) before they can be added to `_fingerprint_for` safely. Surface a "why this is a
  problem" per category and a safe-merge path once that's built.
- **#2b "Examine Library" — BUILT @ v0.2.32 (2026-06-23, user request, real Asset_bundle.blend circular-
  reference case), NEEDS LIVE-BLENDER VERIFY (mutates links).** Distinct from #2's reconnect box (which only
  triggers on BROKEN placeholders): a library can resolve perfectly fine and still be worth dropping — e.g. a
  shared `Asset_bundle.blend` causing circular references — so the user wants everything it currently
  provides re-sourced from the local file or another already-loaded library FIRST, falling back to a manual
  pick only when nothing already in memory matches. `core.reconnect.suggest_reconnect` gained an
  `allow_fuzzy=True` kwarg (default unchanged; `allow_fuzzy=False` stops after the exact/numbered tiers — a
  wrong FUZZY guess here would silently repoint a WORKING link at an unrelated datablock, so in-memory
  suggestions are exact-only by design choice, confirmed with the user). New `ops/examine_library.py`: pick a
  library (`bpy.types.WindowManager.assetdoctor_examine_library_pick`, a `prop_search` over `bpy.data.
  libraries` — no dynamic-enum GC-pin needed) → `examine_library` walks ALL of `bpy.data` (the same generic
  per-ID-collection walk `_iter_missing_blocks` uses) for `block.library is library` → for each, tries an
  EXACT/numbered match first among LOCAL datablocks of that type, then among datablocks from OTHER already-
  loaded libraries → stages the result. Per row, THREE mutually-exclusive actions (user's exact spec): (1)
  accept the in-memory suggestion (`use_suggested`, pre-ticked when found); (2) **Make Local** checkbox
  (`block.make_local()` — Blender's own generic per-ID method, no per-type code needed); (3) **Pick a
  Specific Item** (`examine_pick_source`, per-ROW file browser — peeks the chosen .blend's matching
  collection and lets the user pick literally ANY name there, e.g. relinking a Cube to a Sphere from another
  file on purpose — not constrained to a name-based guess). `examine_apply_selected` applies in that
  priority order, backup first; mirrors F3's pattern of NOT removing the old linked copy (`user_remap` only —
  Blender drops an unused linked datablock from the file on its own on save/reload). UI: `ASSETDOCTOR_PG_
  examine_row` + an "Examine Library" box (grouped by kind) right after the Datablock Reconnect box.
  **DEFERRED (flagged, not built):** a FOLDER-wide search (walk every .blend in a chosen folder, peek each
  for a name match) — the per-row manual pick already covers the same need when the user knows roughly which
  file to check; the folder-search is a "let the computer find it across many files" convenience layer on
  top, scoped out of v1 for time. **VERIFY:** Examine Asset_bundle.blend lists its Objects/Materials/Meshes/
  etc.; an item with a same-named local datablock pre-suggests "local: X"; Pick a Specific Item opens a
  browser and the dropdown lists every name in the chosen file (try picking an UNRELATED name); Make Local
  works; Apply Selected remaps/localizes only ticked rows and the old Asset_bundle copies aren't force-
  removed (just unreferenced).

### BATCH D — headless dry-run render warnings (#12) — BUILT @ v0.2.33, needs live-Blender verify
- **#12 Dry-run render for warnings — DONE.** Runs a low-res (10%, 1 sample), `write_still=False` render in
  a SEPARATE background Blender subprocess (`bpy.app.binary_path`, `--factory-startup` to keep add-on
  startup noise out of the log) against the file ON DISK, so it never touches the live UI/session. Captures
  combined stdout/stderr to a temp log file (read after the process exits — no pipe-deadlock risk), parses
  it for missing-image/driver-error/generic-error/-warning lines (deduped with "(xN)") into report `"f9"`.
  `core/dryrun.py` (bpy-free, 11 tests) + `ops/dryrun_render.py::ASSETDOCTOR_OT_dryrun_render`
  (`ModalProgressMixin`, non-blocking poll with a 5-min timeout) + "Dry-run render" box in
  `ASSETDOCTOR_PT_scene_deps`. Distinct from the in-process Profile Render (F5). See the "BATCH D" entry
  at the top of this file (SESSION RESUME) for full build notes + the live-verify checklist.

### BATCH E — finish Batch 4 leftovers + Batch 5
- Node-graph substitute-material confidence (reuse `core/fingerprint.fingerprint_material`).
- Idle-scan feasibility prototype (Windows `GetLastInputInfo`, gated).
- **Batch 5:** N-panel → Properties migration + **UIList virtualization** of the Missing/Duplicate lists.

**NEXT BUILD (agreed 2026-06-23): DATABLOCK RECONNECT** for missing data-blocks — see Batch 4. Auto-suggest
closest name + user override; link via `bpy.data.libraries.load` + `user_remap` the placeholder; needs an
editable missing-data-blocks list (mirror broken-libs). Mutates links → live-verify WITH the user.

**v0.2.25 — live-test feedback fixes (user, 2026-06-23):** (1) F8 **Hierarchical layout INVERTED** —
`assign_depths` now measures from the LEAVES so pure assets (linked-by-others, link nothing) sit at the top
and the consuming scene sinks to the bottom; labels always shown in tree mode. (2) Missing-data-blocks report
gets a flat **"Summary" overview row** ("N file(s) with M missing data-block(s)") via a new flat `overview`
category in `core/tree`. (3) **"Missing" button moved** out of the deps row into the **Broken links & missing
data-blocks** box, renamed; three buttons now: **Find Broken Links / Find Missing Data-blocks / Find All
Missing** (new combined `ASSETDOCTOR_OT_scan_all_missing` runs both). (4) reconnection = the library relinker
(see below — design recorded). (5) texture **eyedropper** kept in the Missing-Textures Suggest area with a
clear "Substitute from a material's textures:" label (it only draws after *List Missing Textures* finds
missing TEXTURES — the user was on the Data-blocks view).

**BROKEN LINK vs MISSING DATA-BLOCK (clarified for the user):** a broken/missing LINK = a whole library
`.blend` that can't be found on disk (`library.filepath` resolves to nothing) — fix via Broken Links → Relink
(reloads ALL its datablocks at once). A missing DATA-BLOCK = one linked id flagged `is_missing` — caused
EITHER by a missing library (above) OR by a present library that no longer holds that block (renamed/deleted,
e.g. the link wants `GeometricStichDesign` but materialMaster.blend now has `GeometricStichDesign.001`).

**RECONNECTION DESIGN (item 4, agreed approach — deep part NOT built yet):** missing-library case is already
handled by the library relinker. The same-library NAME-MISMATCH case needs a NEW datablock-level remap (point
the missing id at an existing differently-named block in the same library, or re-link the correct name +
`user_remap` the placeholder's users onto it, backup-first). Scope WITH the user before building (mutates
links). Candidate next increment.

**v0.2.20 LIVE-VERIFIED (user, 2026-06-23):** the folder-ops progress bar + ESC work. **Known BENIGN console
noise (NOT a bug):** running the Duplicate **Find .NNN** (and content) scan prints libjpeg decoder warnings —
`Using code not yet in table` / `Corrupt JPEG data: premature end of data segment` — for any slightly-truncated
JPEG in the user's textures. Source: `_fingerprint` reads `img.size`/`channels`/`depth`
(`ops/image_dedup.py`), which forces Blender's C JPEG decoder to load the file; the decoder logs to stderr.
The content hash is over RAW bytes (no decode), so dedup is unaffected and everything still populates. Two
corrupt-but-byte-identical files still merge. Nothing to fix; could optionally suppress/relabel later.

**Where we are in the 5-batch push (go 1→5 in order):**
- **Batch 1 — DONE** (v0.2.16–0.2.18): Missing/Duplicate renamed; Duplicate section redesigned (collapsible
  material groups, keeper dropdown, master keeper, mismatch highlight + eyedropper override); name-affinity
  material attribution; Layer-2 resolution-variants report (f6res).
- **Batch 2 — code-complete** (v0.2.19–0.2.20): **Layer-3 content-overlap dedup DONE** (modal
  `scan_content_dups`, "Find content dups" button, reuses keeper/merge). **"Working…" modal for the FOLDER
  ops DONE @ v0.2.20** (two-op picker→worker split, shared `ASSETDOCTOR_OT_relink_folder_search`). Defensive
  crash settle added (UNVERIFIED). **REMAINING (USER):** the relink/merge **CRASH still needs USER repro**
  (relink/merge alone, Solid vs Material shading) + live-verify the new modal folder search.
- **Batch 3 — DONE** (v0.2.21–0.2.23): missing DATA-BLOCKS via `id.is_missing` (`core/missingdata.py`, op
  `scan_missing_datablocks`, feature `f7miss`); F8 graph zoom/hierarchy (+/−/Fit, Ctrl-gated wheel,
  Hierarchical via `assign_depths`); reverse-dependency "safe to delete?" (`core/reversedep.py` +
  `ops/reversedep.py`, feature `f7rev`, "Safe to delete?" box).
- **Batch 4 — IN PROGRESS** (v0.2.24–0.2.26): **material eyedropper** (v0.2.24) + v0.2.25 live-test fixes +
  **search-another-.blend for TEXTURES DONE** (v0.2.26, `harvest_image_paths` + `suggest_from_blend`).
  **REMAINING:** **datablock RECONNECT** (design agreed, auto-suggest+override; next increment — editable
  missing-data-blocks list + link/`user_remap` op), node-graph substitute confidence, idle-scan feasibility.
- **Batch 5 — NOT STARTED.** N-panel→Properties migration + **UIList virtualization** of the Missing/Duplicate
  lists (scheduled here from B1).

**Immediate next actions next session:** (1) user live-verifies Batch 3 (v0.2.21–0.2.23: Missing button, F8
graph controls, Safe-to-delete) + the new **B4 material eyedropper** (v0.2.24: eyedrop a good material →
Suggest → Possible Matches) — plus the still-pending **Find content dups** / **modal folder search** /
**crash repro** (Solid vs Material). (2) Continue **Batch 4**: search-another-.blend corpus (reuses
`propose_from_paths`), node-graph substitute confidence, idle-scan feasibility.

**Big pending live-verify backlog (none of v0.2.7–v0.2.19 confirmed beyond the keeper dropdown + the
material-attribution screenshots):** see the per-version notes below.

**After the 5-batch push:** scope the material-override → real node-tree reassignment (see ROADMAP).

## ★ CONSOLIDATED BATCH PLAN (agreed 2026-06-22) — finish the open backlog in 5 batches

Goal: close out all the active polish/redesign/feasibility TODOs. Ordered so panel-touching work
settles BEFORE the panel migration (Batch 5), and each batch ends with a live-Blender verify.
Detailed specs for every line live in the sections further down this file.

- **BATCH 1 — Texture-section finalization + footprint reduction.** Biggest chunk; do in two passes.
  - **1a — DONE @ v0.2.16 (2026-06-22), needs live-Blender verify.** Missing section title →
    **"Missing Materials/Textures"** (width-aware). Duplicate section fully REDESIGNED to mirror the
    Missing section: inline summary header ("Duplicate Materials/Textures — N material(s), M texture(s)
    redundant, K differing"), top **Find / Merge Selected / Export** buttons, collapsible **material
    groups** whose rows are the `.NNN` families — each with an **include checkbox + a keeper dropdown**
    (`ASSETDOCTOR_PG_dup_family.keeper`, a dynamic EnumProperty over the family members so the user
    repoints which datablock survives) + a "Different content — kept separate" collapsible. New WM coll
    `assetdoctor_dup_families` + state; ops `scan_dup_textures` / `merge_dup_selected` (keeper-based via
    `imagededup.victims_for_keeper`, +1 test) / `dup_category_toggle` replace the old apply-bool
    `dedup_textures` op. f6dup dropped from the report selector (`_F7_FEATURES`) but still stashed for the
    inline Export (`export_report` gained an optional `feature` override). Suite 217. **VERIFY (watch the
    dynamic keeper EnumProperty — untestable headless, crash-class if items GC'd; pinned via
    `_KEEPER_ITEMS_CACHE`):** Find lists families under their material; the keeper dropdown lists members
    and defaults to the canonical; pick a different keeper → Merge keeps it; Export writes the report.
  - **1a-followups — DONE @ v0.2.17 (from the keeper-dropdown live test).** (i) **Material-attribution
    BUG fixed:** `_image_material_map` now picks the representative material by NAME AFFINITY
    (`core/imagematch.name_affinity` = token Jaccard; +1 test) among the materials that use an image,
    so a `…_lightBlue_…` texture groups under a lightBlue material instead of whichever was found first
    (the FabricWool-under-FloralLace mis-grouping). Helps BOTH the Missing and Duplicate sections.
    (ii) **Master keeper control:** `ASSETDOCTOR_OT_dup_material_keeper` (DOWNARROW_HLT on each material
    row) → a popup to set every family's keeper at once by policy (Recommended / Un-suffixed base);
    per-family dropdowns still override.
  - **1b — Layer 2 resolution-variants DONE @ v0.2.17 (report-only, LOSSY-aware).** `core/imageres.py`
    (bpy-free, 6 tests, suite 224): `plan_res_variants` groups local image names by (stems, channel)
    via `imagematch.classify` (`.NNN` stripped first) and flags any set present at 2+ resolution tokens;
    `build_res_report` → feature `"f6res"`. Op `ASSETDOCTOR_OT_scan_res_variants` (never mutates) +
    "Resolution variants (footprint, report)…" button in the Duplicate section + `f6res` in
    FEATURES/_F7_FEATURES + `core/tree._CATEGORY_TITLES`. **APPLY (standardize-to-res) deferred** — lossy,
    needs the footprint-savings UI; report surfaces candidates first.
  - **1b — Layer 3 content-overlap (DEFERRED to Batch 2's modal infra):** fingerprint ALL local images by
    CONTENT (not name) and collapse exact-content duplicates across folders (the real bloat-killer; same
    CC4 textures across ~15 import folders). LOSSLESS but HEAVY (hashes everything) → must run under the
    modal progress+pause scan from Batch 2, not synchronously (would freeze). Build its bpy-free core
    (`plan_content_merges`) + the modal op when B2 lands. Feeds the F5 before/after savings diff.
- **BATCH 2 — Responsiveness + the relink CRASH + Layer-3 content-overlap.**
  - **Layer-3 content-overlap dedup — DONE @ v0.2.19 (the real bloat-killer).** `imagededup.plan_content_merges`
    (group ALL images by content fingerprint regardless of name → lossless merge across folders; +3 tests,
    suite 227). Modal op `ASSETDOCTOR_OT_scan_content_dups` (ModalProgressMixin: hashes every local image,
    progress + pause/ESC) populates the SAME Duplicate list (keeper dropdown + Merge Selected apply reused via
    `_fill_families`). New button "Find content dups". Merge is now mode-aware (`assetdoctor_dup_scan_mode`):
    after a CONTENT merge it clears + prompts re-scan (a deep rescan is too heavy to auto-run). **VERIFY on
    human_bundle — this is where the real CC4 cross-folder duplication is.**
  - **Crash mitigation — defensive only @ v0.2.19 (NOT a verified fix).** Added `context.view_layer.update()`
    after bulk image removal (merge) and filepath/reload (relink) to settle the depsgraph before the next
    viewport draw. **STILL NEEDS USER REPRO** (relink/merge alone; Solid vs Material shading) to confirm the
    cause + whether this helps. Content merge can remove MANY images → higher crash exposure; recommend Solid
    shading during bulk merges until confirmed.
  - **"Working…" modal for the FOLDER ops — DONE @ v0.2.20.** Suggest Matches / Search a folder / Point
    group at folder are now the **two-op split**: each picker op keeps the file browser but its `execute`
    just launches one shared `ModalProgressMixin` worker (`ASSETDOCTOR_OT_relink_folder_search`,
    mode = EXACT_ALL | EXACT_GROUP | FUZZY) via INVOKE_DEFAULT, so a big import tree no longer freezes the
    UI (progress bar + ESC/pause). Core got the incremental primitives it needs (bpy-free, +7 tests, suite
    234): `imagepaths.iter_walk_dirs` + `_scan_dir_into` (factored out of `_index_dirs`) and
    `imagefamily.iter_resolve_group_in_dir` (generator form of `resolve_group_in_dir`, proven equivalent by
    test). UI unchanged (pickers still own the buttons). **VERIFY live:** run each folder action on a big
    tree — progress bar advances, ESC cancels cleanly, matches still stage exactly as before. The native
    Find-Missing-Files wrapper was never wired to an op, so it's out of scope here.
- **BATCH 3 — Diagnostics: missing data-blocks + F8 graph. IN PROGRESS (v0.2.21).**
  - **Identify missing DATA-BLOCKS via `id.is_missing` — DONE @ v0.2.21.** `core/missingdata.py` (bpy-free,
    +4 tests, suite 238): `MissingBlock` + `group_by_library` + `build_missing_datablocks_report` (feature
    `"f7miss"`, groups by the broken source library most-missing-first, ✓-status when none). Op
    `ASSETDOCTOR_OT_scan_missing_datablocks` (`ops/datablock_inspect.py`) — generic walk over ALL of
    `bpy.data`'s ID collections (`_iter_missing_blocks`, so ANY linked type counts, not just the dup-census
    set), plain/instant (just reads the in-memory placeholder flags, no disk/user_map). Wired: `"f7miss"` in
    `report_store.FEATURES` + panel `_F7_FEATURES` + `tree._CATEGORY_TITLES["missing_datablock"]`; new
    **"Missing"** button in the Scene panel's Scan-deps/Analyze row. **VERIFY live on human_bundle** (the "3
    linked data-blocks missing" case) — should list them grouped under the missing library; ✓ when clean.
  - **F8 HTML graph zoom/hierarchy — DONE @ v0.2.22.** `core/linkmap_html.py`: on-page **+ / − / Fit**
    buttons (`#controls`), wheel is now **Ctrl/⌘-gated** (plain wheel pans, Ctrl+wheel zooms, softened
    1.08), and a **Hierarchical** toggle lays files out in dependency rows. Layer index per node = new
    bpy-free `assign_depths` (roots = depth 0, each target one row below its deepest user; cycle-safe via
    bounded relaxation; +3 tests, suite 241) embedded as `node.depth`; tree mode pins nodes by layer +
    Fit, force mode resumes on toggle-off. **VERIFY live:** Scan Folder → graph opens → +/−/Fit work,
    plain scroll pans, Ctrl+scroll zooms, Hierarchical lays out in layers + back.
  - **Reverse-dependency "safe to delete?" check — DONE @ v0.2.23.** `core/reversedep.py` (bpy-free, +9
    tests, suite 250): `dependents(edge_pairs, nodes, target)` inverts the F1 file→file graph and reverse-
    reaches from the target (cycle-safe BFS) → (direct, indirect, canonical); `build_reverse_dep_report`
    (feature `"f7rev"`) — three visible outcomes: not-in-scan (warning, wrong folder), ✓ nothing-links-it
    (safe), or the dependents that would break. Op `ASSETDOCTOR_OT_check_dependents`
    (`ops/reversedep.py`, ModalProgressMixin) reuses `blendscan` to scan the Project Folder offline, then
    reports who links the chosen file. New Scene prop `assetdoctor_dep_target` (FILE_PATH) + a "Safe to
    delete? (who links this file)" box under the Project link map; `f7rev` in FEATURES + `_F7_FEATURES` +
    `tree._CATEGORY_TITLES` (direct_dependent / indirect_dependent). Closes the deleted-19GB-
    ThePiazzaSanMarco incident. **VERIFY live:** set Project Folder + pick a linked file → lists its
    dependents; pick a root scene → ✓ safe. **BATCH 3 COMPLETE.**
- **BATCH 4 — Possible Matches power-ups + idle-scan feasibility. IN PROGRESS (v0.2.24).**
  - **Eyedropper/material datablock-picker — DONE @ v0.2.24, relabeled @ v0.2.25.** WM
    `assetdoctor_tex_source_material` (PointerProperty→Material) + op `ASSETDOCTOR_OT_suggest_from_material`
    (`ops/image_relink.py`): harvest the picked material's on-disk textures (recursing node groups via
    `_walk_image_nodes`) → candidate corpus → match by name against every still-unplaced missing row → stage
    Possible Matches (reuses the existing Accept UI; nothing written). All-local/instant (no folder walk). New
    bpy-free core `imagematch.propose_from_paths(wanted, candidate_paths)` → `{wanted: (path, Match)}`
    (resolves the chosen candidate basename back to a real path; first-path-wins on duplicate basename; +3
    tests, suite 253) — the shared corpus→proposals primitive for material/another-.blend/folder. UI: now a
    labeled "Substitute from a material's textures:" row in the Missing-Textures section (shows after *List
    Missing Textures* finds missing textures). **VERIFY live:** eyedrop a good material → Suggest → its
    textures appear as Possible Matches. **Possible follow-up:** per-material-group eyedroppers (fill just one
    group's rows) — global picker for now.
  - **Search ANOTHER .blend (TEXTURES) — DONE @ v0.2.26.** `core/blendscan.harvest_image_paths(path)` harvests
    the image file paths another .blend references, offline, by delegating to BAT's own `IM`-block handler
    (`trace.blocks2assets.image`; skips packed, resolves relative paths; +1 smoke test on real fixtures, suite
    254). Op `ASSETDOCTOR_OT_suggest_from_blend` (`ops/image_relink.py`): pick a .blend → harvest its on-disk
    image paths → `imagematch.propose_from_paths` against unplaced missing rows → Possible Matches (shared
    `_stage_proposals` tail, also now used by the material eyedropper). UI: "Substitute from another .blend…"
    button under the material eyedropper. Images are file-backed, so this just finds the right FILE — no
    Blender linking. **VERIFY live:** pick a .blend whose textures exist → its files appear as Possible
    Matches. **Materials-as-substitution-source (linking a specific datablock) = the DATABLOCK RECONNECT
    feature below, separate from textures.**
  - **DATABLOCK RECONNECT (missing data-blocks) — DESIGN AGREED @ 2026-06-23, NOT built (next increment).**
    The parallel "search another .blend" for missing DATA-BLOCKS (materials/objects), which unlike textures
    must actually LINK. Mechanics: pick a source .blend (default = the library the block should come from) →
    enumerate its datablocks of the matching type via `with bpy.data.libraries.load(path, link=True) as
    (data_from, data_to): data_from.materials` (names only, no load) → **auto-suggest the closest name**
    (exact → `.NNN` copy of the same base e.g. GeometricStichDesign→GeometricStichDesign.001 → fuzzy affinity;
    user can OVERRIDE by picking another) → on Apply (backup first): `data_to.<coll> = [chosen]` to LINK it,
    then `placeholder.user_remap(linked)` + remove the placeholder. Needs: make the missing-data-blocks output
    an EDITABLE list (mirror the broken-libs PG/UIList pattern: kind, name, library, source_blend picker,
    auto-suggested target + override, Apply Selected). Build core (`suggest_reconnect`/`plan_reconnects`,
    bpy-free + tested) + the editable list + the mutating link/remap op together; live-verify WITH the user
    (mutates links).
  - **Node-graph introspection** (reuse `core/fingerprint.fingerprint_material`) for substitute-
    material confidence.
  - **Idle-scan feasibility prototype** (Windows `GetLastInputInfo` via an app timer; gated,
    Windows-only, prototype).
- **BATCH 5 — N-panel → Properties migration + cleanup (LAST, after panels settle).**
  - Parent Scene panel hosting the shared progress + report lists once; re-home each feature as a
    Scene sub-panel; delete the redundant Project/Resource N-panel sections; final live-verify
    sweep (v0.2.7–current); retire the VIEW_3D panels.
  - **Virtualize the Missing + Duplicate lists to scrollable UILists** (user-scheduled @ v0.2.18) —
    fixed-height + scrollbar via `template_list`; flatten each hierarchy into one heterogeneous row
    collection drawn by a custom `draw_item` that still hosts checkbox / keeper dropdown / pickers.

**ROADMAP — separate NEW FEATURES, NOT part of "finish-up" (schedule after the 5 batches):**
Automated Cleanup pipeline; Archive Project (BAT `pack`→zip); footprint reduction (Layer 2
resolution-standardize LOSSY + Layer 3 content-overlap hash dedup); reverse-dependency "safe to
delete?" check; lazy-depth scan; older Make-Local perf / In-Place-localize / shared-library-guard
bugs. Pull any into a batch on request.

**AFTER THE 5-BATCH PUSH (user-scheduled 2026-06-22):**
- **Material override → real node-tree reassignment.** Today the Duplicate section's eyedropper
  (`material_override`, v0.2.18) only RE-GROUPS our list — it does NOT change the file. Scope a follow-up
  that actually fixes the mis-assignment: when the user repoints a texture's family at the correct material,
  optionally **rewire** that image into the chosen material's node tree (and/or out of the wrong one) —
  report-first + backup, opt-in (it mutates shading). Decide exact semantics (move vs copy the texture node;
  which channel/socket; behavior when the target material has no matching node) WITH the user before building.

---

## SESSION 4 — live test of v0.2.17 keeper dropdown (user, 2026-06-22)

Keeper dropdowns confirmed working. Feedback + decisions:
- **Material grouping: KEEP by material, but HIGHLIGHT mismatches (user decision).** The user realized the
  brown-material-uses-lightBlue-textures is an ERROR IN THEIR FILE's material assignment, not our bug.
  **DONE @ v0.2.18:** the Duplicate section now flags an "apparent mismatch" — when a family's (effective)
  material name barely overlaps the texture name (`core/imagematch.name_affinity < 0.5`), the material header
  + the texture row turn red (ERROR icon, "⚠N mismatch" on the header). Each flagged row gets an **alternate
  material picker (eyedropper)** — `ASSETDOCTOR_PG_dup_family.material_override` (PointerProperty→Material) —
  to re-home the family under the correct material; grouping + the master-keeper op use the override. This
  also **exercises the datablock eyedropper UI ahead of Batch 4.** CAVEAT (told user): the override is
  ORGANIZATIONAL (re-groups our list) — it does NOT rewire the material's node tree (fixing the actual
  assignment in the file is a deeper, separate job; offer it if the user wants it).
- **Keeper master dropdown labels (TODO 1):** left as the policy popup (Recommended / Un-suffixed base) — once
  the user understood families are `.NNN` copies of ONE variant (color variants are different content, never
  merged), the "show variant names" request was moot (no cross-variant choice exists within a family).
- **Resolution-variants report (v0.2.17):** ran fine on human_bundle but found **none** (negative-output case
  working). The real texture bloat there is content-overlap (Layer 3), not resolution variants — so Layer-3 is
  the higher-value footprint win (still deferred to Batch 2's modal).
- **SCHEDULED (user: "leave as-is for now, schedule for later") — convert Missing + Duplicate custom-drawn
  hierarchies to VIRTUALIZED UILISTS** so the boxes are fixed-height + scrollable (Blender only scrolls via
  `template_list`). Plan: flatten each hierarchy into one heterogeneous row collection (kind = category /
  texture / keeper) drawn by a custom `UIList.draw_item` that branches on kind and still hosts the checkbox /
  keeper EnumProperty / pickers per row (the F7 report's flatten-to-UIList pattern, extended for interactive
  rows). Sizable; its own task. Until then the lists stay collapsible-but-unbounded.

## SESSION 3 — live test of v0.2.14 on human_bundle.blend (user, 2026-06-22)

First real run of the Possible Matches section on the CC4/human_bundle file (407 missing
textures). It worked. Feedback batch + a crash:

- **DONE @ v0.2.15 — Possible Matches: collapsible + ordered + material-accept.**
  - **Collapsible categories, collapsed by default** (`_draw_possible_matches` now mirrors the
    Missing list's triangle-toggle pattern; keys namespaced with `"\x01"` in the shared
    `assetdoctor_tex_expanded`). Fixes "the list was so long I didn't see the suggestions" — a long
    Suggest-Matches result is now short collapsed headers.
  - **Ordered by confidence** (material's rank = its best texture; high→low, then name). Within a
    material, rows sorted high→low too.
  - **Material-level Accept** (`ASSETDOCTOR_OT_accept_material_matches`, CHECKMARK icon on the
    category row — distinct from the single-row IMPORT icon) accepts all rolled-up textures at once.
  - **"(no material)" reduced:** `_image_material_map` now recurses node GROUPS
    (`_walk_image_nodes`), so a texture buried in a ShaderNodeGroup is attributed to its material
    instead of falling into "(no material)". (Some images genuinely have no material — world env,
    brush, unused — those correctly stay "(no material)".)
- **DONE @ v0.2.15 — header reflects matched count.** "Missing Textures — N missing, M matched[,
  K relinked]" (`matched` = still-missing rows that already have a staged target). Category labels
  "(X of Y found)" → "(X of Y matched)". Title cased "Missing Textures".
- **TODO — "Working…" indicator on long ops (#1).** The folder ops (Suggest Matches, Search a
  folder, Point group, Find Missing Files) run SYNCHRONOUSLY in `execute()`, which BLOCKS the UI —
  so a spinner can't animate (Blender is frozen until the op returns; the result then shows in the
  status bar). A real busy indicator requires converting these to MODAL ops that chunk the
  `os.walk`/match work and yield (reuse `ops/progress.ModalProgressMixin` + `_draw_progress`, which
  already power the scan ops). PLAN: make `suggest_fuzzy_matches` (and the other folder ops) modal,
  driving a "Searching {dir}…" status + the existing progress bar; the panel title/button can show
  a spinning icon while `wm.assetdoctor_op_active`. Deferred — moderate, isolated; do next.
- **CRASH on relink (EXCEPTION_ACCESS_VIOLATION) — see human_bundle.crash.** Backtrace top:
  `image_acquire_ibuf` ← `BKE_image_acquire_ibuf` ← EEVEE `Instance::end_sync` ← `DRW_draw_view`
  ← `view3d_main_region_draw` (NULL read @ +0x28). i.e. a **Blender C-level crash during the EEVEE
  VIEWPORT DRAW**, when the engine acquired an image buffer for a material — NOT in our Python.
  Timeline in the log: `dedup_textures(apply=True)` removed **1150** image datablocks, then the user
  tried to relink → next viewport redraw crashed. Prime cause: mutating many image datablocks
  (remove via dedup, then `filepath`+`reload` via relink) while the viewport is in **Material/
  Rendered** shading and we force `area.tag_redraw()` → EEVEE re-acquires an ibuf for an image in a
  transient/invalid state → NULL deref. Our dedup uses the safe `user_remap`→`remove` pattern and
  relink wraps `reload()` in try/except, so there's no obvious Python bug; this is Blender
  fragility on a file with hundreds of broken textures.
  - **WORKAROUND for the user (next run):** switch the 3D viewport to **Solid** shading before bulk
    relink/dedup (so EEVEE doesn't acquire image buffers mid-mutation), apply, **save**, then switch
    back to Material. Do dedup and relink as SEPARATE steps with a save between.
  - **TO ISOLATE next session:** reproduce relink alone (no prior dedup) in Solid vs Material
    shading; if Solid avoids it, confirms the draw-time ibuf-acquire theory. POSSIBLE mitigations to
    evaluate: defer the forced `tag_redraw` after bulk image mutation; call a depsgraph/view-layer
    update + `image.gpu_flush`/`buffers_free` before returning; or relink with an explicit "engine
    quiet" step. None proven yet — do not claim a fix until reproduced.
- **TODO — N-panel → Properties migration plan (#7).** Goal: consolidate everything into
  **Properties › Scene** (the `ASSETDOCTOR_PT_scene_deps` hub), retire the VIEW_3D/N-panel, delete
  redundancies. Current split:
  - **N-panel (VIEW_3D/UI/"AssetDoctor"):** `ASSETDOCTOR_PT_main` (header + shared progress bar) →
    children `_project`, `_make_local`, `_materials`, `_orphans`, `_geometry`, `_resource_tools`,
    `_utilities`; plus `ASSETDOCTOR_PT_report` and `ASSETDOCTOR_PT_resources`.
  - **Properties › Scene:** `ASSETDOCTOR_PT_scene_deps` (F7/F6 hub — deps scan, broken links, path
    norm, missing textures, possible matches, dup textures, report selector).
  - **Redundancies to delete:** the N-panel **Project link map** (folder→graph) is already in
    scene_deps; **Resource analysis** appears in both `_resource_tools` and `_resources`; the shared
    **progress bar**/Report UIList are drawn in BOTH panel roots.
  - **PLAN (phased, low-risk):** (1) add a parent Scene panel `ASSETDOCTOR_PT_scene_root`
    (PROPERTIES/WINDOW/scene) that hosts the shared progress bar + Report/Resource UILists once;
    (2) re-home each feature box as a Scene sub-panel via `bl_parent_id` (Make Local, Materials,
    Orphans, Geometry, Resource Analyzer, Utilities), default-collapsed; (3) delete the duplicate
    Project + Resource N-panel sections; (4) drop the VIEW_3D panels once parity is confirmed live.
    Keep one change per version + live-verify each (registration is fragile — RESTART Blender).
    **Needs user sign-off on ordering + which N-panel items (if any) stay in the 3D view.**

## NEW BACKLOG — session 2, 2026-06-22 (documented, NOT built; resume here next session)

1. **Rename "Missing textures" → "Missing Materials/Textures"** (section title + the header-summary base
   string in `ui/panels._draw_missing_textures`). Width-aware brief form too.
2. **Rename "Duplicate textures (.NNN)" → "Duplicate Materials/Textures"** (section title).
3. **Richer Duplicate-Textures summary line** (concise version by width): e.g. "Summary — 230 merge
   group(s) (~954 redundant datablocks removeable) — 65 similar name (different content)". Built in
   `core/imagededup.build_dedup_report` (the summary Finding) + the width trim already in
   `ASSETDOCTOR_UL_tree` (extend it for this line). Brief form e.g. "230 groups · ~954 removeable · 65 diff".
4. **Duplicate Materials/Textures section REDESIGN (mirror the Missing Materials section; kill the f6dup
   report):** after scan, title → "Duplicate Materials/Textures — XX Materials / YY Textures Redundant".
   List a Material → its textures rolled up beneath; separator; a **right column = the item to KEEP, as a
   dropdown** (user can pick a different keeper); left **checkbox**, default-checked for anything with a
   recommended merge. **Find + Merge buttons at the top under the title, plus an inline Export Report
   button** there; remove the now-redundant separate export button. Reuse the v0.2.12 collapsible-category
   custom-draw pattern from `_draw_missing_textures`. Same "summarize inline, drop the separate report"
   move as the Missing section. (Keeps `f6dup` core/plan; just changes presentation + adds keeper-dropdown.)
5. **HTML folder-graph (F8) tweaks:** (a) mouse-wheel zoom too sensitive — add on-page **zoom +/− and
   reset buttons** and soften the wheel factor (or require Ctrl+wheel). (b) **Hierarchical layout option**
   — feasible: assign each node a depth/layer by BFS from roots and lay out in columns by layer
   (Sugiyama-ish), with a toggle between force-directed and hierarchy. Edit `core/linkmap_html.py` JS.
6. **Idle-triggered scans — feasibility (user considering):** Blender has NO direct "idle" event. OS-level
   IS reliable on Windows: poll `GetLastInputInfo` via `ctypes` (ms since last keyboard/mouse input
   system-wide) from a lightweight `bpy.app.timers` callback; when idle > threshold AND no AssetDoctor
   modal running AND not rendering, kick a scan. CAVEATS: (i) AssetDoctor currently registers ZERO app
   timers (see crash-diagnosis note) — this would be the first; keep it tiny, remove on unregister;
   (ii) offline BAT scans block the MAIN thread, so an idle scan must be CHUNKED/modal or it freezes when
   the user returns; (iii) never start while a render is running. Prototype Windows-only first.
7. **Identify missing DATA-BLOCKS, not just missing links (human_bundle: "0 libraries and 3 linked
   data-blocks are missing").** Today we detect missing library FILES (broken links) + missing IMAGE
   files — NOT individual missing linked IDs (library present, but a specific Object/Material/etc. no
   longer exists in it, usually renamed/removed at source). **Feasible to IDENTIFY:** walk `bpy.data.*`
   for `id.library is not None and id.is_missing` (Blender's placeholder flag) and report type+name+source
   library — a LIVE scan. Fits the F7 "Analyze" / a new "Missing datablocks" report. FIXING is harder
   (the ID was renamed/removed in source → needs a fuzzy datablock-name remap like the texture matcher,
   or accept the loss); identification is the immediate win.



## F8 — Project folder link map (graphical), reborn (2026-06-22)

**STATUS: BUILT @ v0.2.11 (local; needs live-Blender verify).** Brings back the folder-wide F1 scan
the user previously had me remove, but with a **graphical, interactive output** instead of a text
report. The scan engine never actually left — `core/blendscan.map_folder` + `core/graph.DepGraph` +
the `ASSETDOCTOR_OT_scan_folder` modal op were all still present; only the button had been dropped.

- **New core:** `core/linkmap_html.py` (bpy-free, 8 tests) — `classify_nodes` (root / leaf / intermediate
  / external / missing / isolated, derived from scan data, no disk access), `aggregate_edges` (collapse
  multigraph → (src,tgt,count)), `cycle_edges`, `build_graph_data`, `build_link_map_html` → ONE
  self-contained `.html` with the graph JSON inlined + a dependency-free vanilla-JS force-directed
  canvas renderer (drag / zoom / pan / click-to-focus / search). No CDN, opens offline.
- **Op:** `ops/scan_folder.py` `_emit` now also writes `linkmap_<stamp>.html` into `<root>/.assetdoctor/`
  and opens it in the browser (still writes the JSON/CSV/DOT exports + stashes the f1 report). Label →
  "Scan Folder → Link Graph". Recursive, backups (`.blend1/2/…`) skipped for free (`rglob("*.blend")`).
- **UI:** new "Project link map (folder → graph)" box in the Scene panel (dir field + Scan button).
- **Scope decided (user, 2026-06-22):** interactive HTML during development, recurse subfolders.
  Datablock-level edge detail ("A links a Camera + Object to B") deferred — the edge already carries a
  link `count`; wire `core/datablock_links` in later for the per-datablock breakdown as edge tooltips.
- **↩ REVISIT (user, 2026-06-22):** once the link-map requirements are solid, evaluate whether a **native
  Blender node-editor** rendering (custom NodeTree: file = node, link = wire) is worth building as the
  end-state output. The user likes it conceptually; HTML chosen first to iterate fast and dodge the
  project's recurring Blender-UI/registration fragility. Compare effort vs payoff then.

## Missing Textures section REDESIGN @ v0.2.12 (user, 2026-06-22) — needs live verify

Unified the three texture-relink paths into one hierarchical, self-contained section (no separate
report). `ui/panels.ASSETDOCTOR_PT_scene_deps._draw_missing_textures`:
- **Header summary** (the visible result, satisfies the negative-output rule): before a scan "Missing
  textures"; after, "— N missing[, M found]"; on a narrow panel "Missing — N✗ M✓". State: WM
  `assetdoctor_tex_scanned` + `assetdoctor_tex_initial_missing` (found = initial − still-missing).
- **"Find Missing Textures" → "List Missing Textures"** (`scan_broken_textures`, sets the scan state).
- **"Search a folder (recursive)…"** = new `ASSETDOCTOR_OT_search_textures_folder`: OUR recursive
  basename search over ALL missing textures, **stages** targets (sets target + ticks), never writes —
  user reviews then Relink Selected. **Replaces the native `find_missing_files_folder` op (REMOVED)**
  (user chose staged-&-reviewable over native immediate-apply; libraries have their own Broken Links
  section). The old before/after **f6tex report is gone** (dropped from `_F7_FEATURES`).
- **Heading "Missing Textures" + "Relink Selected"** on one row.
- **Collapsible categories** (group-by **Material** default, or Folder — `assetdoctor_tex_group_by`):
  triangle toggle (`ASSETDOCTOR_OT_tex_category_toggle` + WM `assetdoctor_tex_expanded`), label
  "{name} ({M} of {N} found)" + ✓ when all matched, a category **folder button** (reuses
  `point_group_at_folder`). Expanded → per-file rows: checkbox (`item.selected`) + name + staged target
  + per-file **file picker** (`relink_pick_texture`). Ungrouped items (`\x00` sentinel) get no folder button.
- **CAVEAT:** these category/file rows are manually drawn (not a UIList) → no virtualization; a single
  category with hundreds of expanded files could blank rows past ~the panel height (the known N-panel
  limitation). Categories are collapsed by default to mitigate; watch on the real CC4 file.
- **Cleanup later:** `ASSETDOCTOR_UL_broken_imgs` UIList is now unused (replaced by custom rows) but
  still registered — harmless; remove on a later pass. `core/imagepaths.diff_found`/`build_find_missing_report`
  also now unused by ops (kept, still tested).
- **DEFERRED UI tweaks (user, 2026-06-22 — do on the NEXT Missing-Textures UI change, not standalone):**
  (a) category label "(X of Y found)" → **"(X of Y matched)"** (more accurate — these are staged, not
  applied); (b) put the ticked count on the apply button: **"Relink YY Selected (creates backup)"**
  (count = items with `selected` and a `target`).

## Request 1 DONE @ v0.2.12 — clean status on the summary line, width-aware (user, 2026-06-22)

`core/tree.report_to_tree` now hoists the `clean` category to a flat top-level row (`_FLAT_CATEGORIES`)
so an all-clear ("✓ All library paths are clean") shows on the summary line — no drilling into a
"Status" category (+ test). `summary` intentionally stays a category (tests depend on it). The report
UIList (`ASSETDOCTOR_UL_tree`) drops a row's " — …" tail on a narrow panel (region.width < 320) for
top-level info rows, keeping the full text in the tooltip.

## BUGFIX @ v0.2.11 — B1 "Point at folder…" gave no group-level feedback (user, 2026-06-22)

Pointing a missing-texture GROUP at a folder set each member's target (the per-texture rows above DO
update with the filename + checkmark) and the matching logic worked — but the **group strip itself
showed nothing**: its button is a static "Point at folder…" and the row count didn't change, so on a
partial/zero match it looked like nothing happened. The user read the operator-redo panel (which only
confirms the op was *invoked* with that directory) and saw the unchanged button. **Fix:** the group row
now shows "M/N matched" + a ✓ when all resolved, the button flips to "Re-point…", and a muted line
shows the resolved folder path. The op reports a WARNING naming the folder when zero matched (so it's
clear nothing was found there). UI-only (presentational) — `resolve_group_in_dir` was already tested.

## PRINCIPLE — every analysis must produce a visible result, even a negative one (user, 2026-06-22)

Any scan/analysis must leave a persistent, visible output even when it finds nothing — never just a
transient header toast that vanishes. A clean result is itself information ("✓ nothing wrong"). Pattern:
stash a report whose empty case is a ✓ `clean`/"Status" finding (as `build_libfix_report` already did).
- **DONE for Find Broken Links (v0.2.11):** `core/relink.build_broken_links_report` always emits a
  finding; empty → "✓ No broken links found — every linked library resolves on disk". New feature key
  `f7links` ("Broken Links") in FEATURES + the Scene panel report selector; `scan_broken_links` and the
  post-relink refresh both stash it (2 tests).
- **TODO — audit the others for the same:** `scan_broken_textures` (f6tex), `analyze_overrides` (f7live),
  `dedup_textures` (f6dup), Find Missing Files, etc. — make each show an explicit "nothing found" result.

## ⚑ LIVE-BLENDER VERIFY CHECKLIST — tonight's builds v0.2.5–v0.2.10 (2026-06-21)

Everything below is BUILT + unit-tested (suite 194 green) but **never exercised in Blender** beyond the
v0.2.7 panel draw. Modal pickers, native ops, node-tree walks, and datablock mutation can't be
headless-tested, so this is the first real run. **Test on a COPY of the real file.** All mutating ops
auto-backup; you must **save** to persist. **Install the new build and RESTART Blender** (registration
changed — new ops/props/panels; F3 "Reload Scripts" is unreliable for structural changes). Work the list
**top-down (lossless/report paths first, apply last).** All controls live in **Properties › Scene ›
AssetDoctor** (the dependency panel) unless noted.

1. **Library relink + normalize (v0.2.5).** *Broken links* box → **Find Broken Links** lists missing
   library links (per-row checkbox; auto-found candidate or "pick a file"); tick → **Relink Selected
   (backup)** fixes only ticked, leaves others. *Path normalization* box → **Check** (report) then
   **Normalize (backup)** — normalize must NOT relink.
2. **Unsaved-changes caution (v0.2.6).** With unsaved edits, a red hint shows above **Scan deps**
   ("save before Scan deps — it reads from disk"); it clears after saving.
3. **Missing-texture relink — Layer 1 (v0.2.7).** *Missing textures* box → **Find Missing Textures**
   lists magenta/missing LOCAL images; doubled-prefix ones auto-match (`CHECKMARK`); **pick a file**
   works; **Relink Selected (backup)** fixes only ticked → magenta resolves on reload. *(Relink ACTION
   never run before — watch this one.)*
4. **Find Missing Files / native recursive (v0.2.8).** **Find Missing Files (folder)…** → pick a folder
   (e.g. `E:\BlenderSync\SynologyDrive`) → found textures drop off the list AND appear in the **Missing
   Textures** report; still-missing remain; backup written. **Caveat to confirm:** native op is
   recursive and relocates ALL external files (libraries too), picking one on duplicate basenames.
5. **Group targeting — B1 (v0.2.9).** *Fix a group at once* box: **Folder/Material** toggle; groups
   list by original folder; **Point at folder…** fills targets for the whole group (recursive, unique
   match) → then **Relink Selected**. Switch to **Material** when a group's original folder is gone and
   point one material's textures at a chosen dir.
6. **Duplicate-texture dedup — Layer 2 (v0.2.10).** *Duplicate textures (.NNN)* box → **Find (report)**
   lists content-identical `.NNN` sets (verified by dims+hash); a same-name family with DIFFERING
   content is flagged "content differs — not merged". **Merge (backup)** keeps one canonical, remaps
   users, removes the copies → re-check shows clean.

Report any failures back here; the **next build step is step 4 (B2 fuzzy substitute + Layer 2
resolution-standardize — LOSSY/opt-in)**, which should wait until these lossless layers verify.

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
  - [~] **F6 follow-up B1 — BUILT @ v0.2.9 (2026-06-21), needs live-Blender verify.**
    `core/imagefamily.py` (bpy-free, 7 tests, suite 186): `group_by_directory`, `group_by_key` (material
    fallback), `resolve_group_in_dir(members, dir, recursive)` (unique basename match, never a
    non-existent path; reuses Layer-1 `find_relink_targets`). Name-family detection deferred to step 3.
    `ASSETDOCTOR_PG_broken_lib` gained `group`+`material`; `_populate_broken_images` fills them
    (`_image_material_map` walks material node trees for a representative material). New op
    `ASSETDOCTOR_OT_point_group_at_folder` (group_key, by=DIR|MATERIAL, recursive dir picker → fills
    targets on the group's rows → user Relinks Selected). UI: a "Fix a group at once" box in the
    Missing-textures section with a Folder/Material toggle (`WM.assetdoctor_tex_group_by`) + a
    "Point at folder…" button per group. **VERIFY:** groups list by folder; pick a folder → members
    matched/ticked; Material toggle groups by material when the original folder is gone; Relink Selected
    applies. Name-family/`.001` overlap stays for Layer 2.
  - [ ] **F6 follow-up B2 — fuzzy / synonym matching (NEXT BUILD STEP; refined by the Woodplanks case
    2026-06-22).** Two cases, ONE matcher, differing only by confidence shown to the user:
    - **(i) Renamed-same-texture (LOSSLESS intent, high value).** Vendor changed the naming convention;
      the .blend's wanted file is gone but the SAME texture sits in the folder under a different name.
      Real example — wanted `WoodplanksNaturalStained007_2K_ao.png` / `..._2K_metallic.png` /
      `..._2K_roughness.png`; on disk `WoodplanksNaturalStained007_AO_2K_METALNESS.png` /
      `..._METALNESS_2K_METALNESS.png` / `..._ROUGHNESS_2K_METALNESS.png`. Exact-basename match (Layer 1
      / B1) CANNOT find these → they show "no match".
    - **(ii) Substitute-equivalent (LOSSY, `Beard18→Beard1`).** Different texture, deliberately changes
      the render. Same engine, lower confidence, **default OFF**, explicit confirm.
    - **MATCHER DESIGN (token-set scoring, NOT just index-strip):** split each name into tokens; score a
      candidate by shared **stem** (material id, e.g. `WoodplanksNaturalStained007`) + shared
      **resolution token** (`2K`/`1K`/`4K`) + **PBR channel synonym** match via a synonym table
      (`ao≈AO≈ambientocclusion`, `metallic≈metalness≈METALNESS`, `roughness≈ROUGH`, `col≈diffuse≈basecolor≈albedo`,
      `nrm≈normal≈nor`, `disp≈height≈displacement`, `emit≈emission`, `opacity≈alpha`). Case-insensitive,
      **order-independent** (`_2K_ao` vs `_AO_2K_…` reorder tokens). Per missing texture, offer the
      best-scoring candidate in the chosen folder as a staged target with a confidence indicator;
      user reviews + ticks, then the existing **Relink Selected** applies (fits the v0.2.12 staged model).
    - Build as a FALLBACK in the folder-search / point-group flow: when exact basename fails, try fuzzy.
      bpy-free in `core/imagefamily.py` (or new `core/imagematch.py`) + tests using these real names.
    - **Layer 3 (content-hash) does NOT cover this** — the wanted file is missing, nothing to hash.
      Index-strip (`BeardNN`) is a SUBSET of this richer token matcher; supersedes the old narrow design.
    - **MATCHER CORE BUILT @ v0.2.13 (2026-06-22): `core/imagematch.py` (bpy-free, 9 tests, suite 214).**
      `classify(name)`→`NameParts(stems, channel, res)` (split on `_.-`; FIRST channel token wins so a
      trailing `_METALNESS` workflow suffix on a COLOR map doesn't read as metallic; `_CHANNEL_ALIASES`
      synonym table incl. DISP=DISPLACEMENT, AO=AmbientOcclusion, COL=COLOR=COLOR1=DIFFUSE=ALBEDO=…;
      "transparency" deliberately a STEM token, not a channel). `score_match`/`best_match` →
      `Match(candidate, score, confidence high|med|low, res_mismatch, channel_ok)`. **`_numbered_conflict`
      = the key rule: same word + different trailing number (Beard18 vs Beard19, Base1/Base2/Base12) is a
      hard DISQUALIFY** — directly fixes the user's #2 concern. Wrong channel disqualifies; res mismatch
      flagged (lower confidence), not blocked. Tested on the real Woodplanks + Beard names. NOT yet wired
      to UI (feeds the Possible Matches section, below).

### F6 step 4 — "Possible Matches" UI + plan (user design 2026-06-22; matcher core done, UI TODO)
  - **#1 DONE @ v0.2.13:** dropped the Folder grouping toggle — Missing Textures groups by **Material**
    only (`_draw_missing_textures` hardcodes mode=MATERIAL; `assetdoctor_tex_group_by` prop kept, unused).
  - **#2 NOT a name-matching bug:** grouping does NO name combining. Material view groups by the material
    that USES each image (`_image_material_map` = first material referencing it). Beard18- and Beard19-
    named textures show under one material (`Beard19_Transparency.001`) because that ONE (merged/`.001`)
    material datablock genuinely references all of them — the file's real state, not our code. Folder view
    counted by original directory, hence different counts. POSSIBLE improvement if it bugs the user:
    choose the representative material by NAME AFFINITY (token overlap with the image name) so a Beard18
    image prefers a Beard18 material when one still exists; and/or list an image under EVERY using material.
  - **Folder-icon TODO DONE @ v0.2.13:** the per-texture file picker (`relink_pick_texture`) now opens AT
    the match's folder (sets `self.filepath` from the item's target in invoke), not the last-used dir.
  - **#3 Possible Matches section — BUILT @ v0.2.14 (2026-06-22), needs live-Blender verify.** The fuzzy
    matcher core is now wired to the UI. `core/imagematch.propose_matches(wanted, candidates, min_confidence)`
    → `{wanted basename: Match}` (best fuzzy candidate per name at/above a confidence floor; +2 tests, suite
    216). New ops in `ops/image_relink.py`: `ASSETDOCTOR_OT_suggest_fuzzy_matches` (folder picker → recursive
    `_index_dirs` walk → `propose_matches` over the textures with NO exact target → STAGE each as a
    `proposal` on its row, never writes); `ASSETDOCTOR_OT_accept_match` (index → copy proposal into `target`,
    tick, clear proposal); `ASSETDOCTOR_OT_accept_all_matches`. `ASSETDOCTOR_PG_broken_lib` gained
    `proposal`/`proposal_confidence`/`proposal_res_mismatch`. UI: a **"Suggest matches…"** button beside
    "Search a folder (recursive)…", and a new **"Possible Matches — N"** sub-section (`_draw_possible_matches`)
    below the main list — grouped by material, each row = missing | proposed basename + confidence band
    (+ "diff res" when `res_mismatch`) | **Accept**; a top **Accept All**. Accept moves the proposal into the
    Missing Textures list above (ticked) → existing Relink Selected applies. UI filter = `proposal and not
    target`, so accepting (or an exact match) removes a row from this list. **VERIFY:** Suggest matches on the
    Woodplanks/Beard folder stages renamed-channel guesses with the right confidence; Accept/Accept All move
    them up ticked; Relink Selected writes them. **NOT YET BUILT (deferred):** the eyedropper/material datablock
    picker (pick a MATERIAL → fill its texture rows) and "search ANOTHER .blend" as a candidate corpus — the
    folder-based fuzzy fallback ships first; revisit the picker if the user wants per-material substitution.
    **DnD REALITY (still true):** no drag-from-Outliner; use a datablock picker + eyedropper
    (`template_ID`/`prop_search` on a PointerProperty) when that lands.
  - **#4 node-graph introspection (feasible, reuse F3):** `core/fingerprint.fingerprint_material` already
    hashes a material's node graph **resolution-agnostically** (invariant to node naming/order). Use it to
    compare a PROPOSED substitute material vs the broken one: identical hash → "same material, renamed"
    (high confidence); differing → Phase-2 per-node diff to report "differs by an RGB Curves / Transform
    node". CANNOT recover a MISSING image's content (nothing to hash) — that stays name-based.
  - **Search ANOTHER .blend (user Q, feasible):** (a) TEXTURE files — read another .blend OFFLINE via BAT,
    harvest its image filepaths, feed their folders/basenames to the matcher as the candidate corpus;
    (b) MATERIALS — `bpy.data.libraries.load` to link/append materials from another .blend as substitution
    sources + node-graph compare. Pairs with the eyedropper (pick from current file OR a chosen library).

### F6 Layer 2 — name-family consolidation (DEDUP datablocks, not relink) — design agreed 2026-06-21
  Different operation from A/B (which fix MISSING files): merge duplicate image DATABLOCKS. Two cases,
  treated differently (mixing them corrupts the render):
  - [~] **`.NNN` families (Leather vs Leather.001) → LOSSLESS merge — BUILT @ v0.2.10 (2026-06-21),
    needs live-Blender verify.** `core/imagededup.py` (bpy-free, 8 tests, suite 194):
    `plan_dup_merges(images)` → `([MergePlan], [FamilyConflict])` — groups local images into `.NNN`
    families via `datablock_graph.duplicate_families`, partitions each by the operator-supplied
    fingerprint, emits a lossless plan per identical 2+ subset (canonical = un-suffixed base, else
    most-users); families with differing/unverifiable content become conflicts (reported, NOT merged).
    `build_dedup_report` (feature `"f6dup"`). `ops/image_dedup.py::ASSETDOCTOR_OT_dedup_textures`
    (apply bool): fingerprints ONLY family members (`WxH:channels:depth:hash`; packed→packed data,
    else file hash cached by path/size/mtime); apply = `auto_backup` → `victim.user_remap(canonical)`
    → `images.remove` when users==0 → re-report. UI "Duplicate textures (.NNN)" box (Find/Merge) in
    the Scene panel; `"f6dup"` in FEATURES/_F7_FEATURES + category titles (merge_lossless/
    family_conflict). **VERIFY:** Find lists identical `.NNN` sets; Merge keeps one + removes copies +
    backup; a mixed-content family is flagged not merged. Reuse `datablock_graph.strip_dup_suffix`/
    `duplicate_families` (done).
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
