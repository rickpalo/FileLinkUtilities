# File & Link Utilities — TODO / backlog

## 🏷️ RENAMED (2026-07-05): AssetDoctor → File & Link Utilities, v0.2.106 (Phase R). Package
## id, class prefixes, operator category, WM/Scene props, GitHub repo, and gh-pages URL all
## changed — see CHANGELOG.md's [0.2.106] entry. Everything BELOW this note that predates the
## rename still uses the old `ASSETDOCTOR_*`/`assetdoctor.*` names as originally written — kept
## as historical record, not updated.

## ✅ CURRENT STATE (2026-07-04): v0.2.105 PUBLISHED. Group 12 (UI virtualization, all 4
## phases), the Phase 1/3 backlog batch, and the Phase 2 live-verify fixes (items 45/46 —
## see below for the full per-item digest) are all live-verified, committed, tagged, and
## on the gh-pages auto-update feed. Group 13's Analyze-All sequencer progress gap (#41
## below) remains logged but needs a design decision, not guesswork — not resumed unless
## asked. Flatten v2 is shipped but still imperfect — not the priority.
##
## ⏩ NEXT SESSION: **Phase R, the full addon rename** (see
## `C:\Users\Rick\.claude\plans\delightful-singing-tome.md` for the exact scope/sequence)
## — do this BEFORE any further new backlog work so it's written under the new name from
## the start.

## ✅ Duplicate Textures / Datablock Reconnect / Examine Library (v0.2.97/0.2.99/0.2.100)
## were all covered by the 2026-07-03 "Live verify looks good" confirmation above —
## their individual per-feature checklists are no longer needed.

## ✅ Resolution Variants — "Standardizing is LOSSY" note now conditional, v0.2.98
## (2026-07-03, user question same session). The warning used to show unconditionally,
## but the mechanic is direction-dependent: keeping a group's HIGHEST resolution isn't
## a quality loss (lower-res users just get re-pointed at the bigger file — wasteful,
## not lossy); only keeping a LOWER resolution than another available one actually
## discards data. New `core.imageres.selection_loses_resolution(groups)` (bpy-free, 6
## tests, suite 511) — true if any group's ticked member isn't that group's highest.
## `ui/panels.py::_draw_res_variants` now only shows the INFO line when this is true.
## Tooltips (`ASSETDOCTOR_OT_scan_res_variants`/`remove_excess_variants`'s static
## `bl_description`) deliberately left as-is — general disclaimers, not per-selection,
## out of scope for this ask. Manifest 0.2.98, NOT live-verified yet (needs a file with
## resolution variants, tick a LOW one, confirm the note appears; tick HIGH, confirm
## it disappears).

### Group 13 — 2026-07-03 live-test findings (Group 12 Phases 1-3 verification pass).
### All items here are logged, NOT investigated yet — the crashes especially need real
### evidence before touching code (this project's own hard-won lesson from the v0.2.94
### Find Duplicates crash: guessing at a native access-violation wastes time).

41. **Find Duplicates / Find All Duplicates has no interruptable progress on large
    files** (user, 2026-07-03). **Scoped + partially fixed 2026-07-04.** Of the 4
    dedup sub-scanners, 3 already chunk finely (`ops/material_dedup.py`/
    `ops/instance_dedup.py` both yield every 32 items via their own `_FP_CHUNK`;
    `ops/image_dedup.py::scan_content_dups` yields per-item). Only
    `ops/datablock_dup.py::_gather_steps` was coarse — it used to yield ONCE PER
    COLLECTION TYPE (e.g. once after finishing ALL Actions), so a single huge
    collection blocked the whole modal tick with no progress/ESC opportunity in
    between. **FIXED**: rewritten to pre-scan every collection's family membership
    first (cheap, just names) so the total item count is known up front, then
    fingerprint in one flat per-item loop yielding every `_FP_CHUNK=32` (matching
    the other 3 scanners' own pattern) regardless of which collection type it's in.
    **Separate, NOT YET FIXED architectural gap found while scoping**: when any of
    these 4 run THROUGH "Find All Duplicates"/"Analyze All" (not their own standalone
    button), `ops/analyze_all.py::_AnalyzeSequencerMixin._call` invokes the sub-
    operator via a plain `bpy.ops.category.name(**kwargs)` call — implicitly
    `EXEC_DEFAULT`, which runs `ModalProgressMixin.execute()` (`for _ in self.
    run_steps(context): pass`) — a tight Python loop that drains the ENTIRE nested
    generator with NO progress-bar update and NO ESC/cancel check at all, no matter
    how finely that sub-operator chunks internally. So even after this fix, running
    the big scan via "Find All Duplicates" specifically will still show no progress
    and can't be cancelled mid-step — only running each dedup tool via its OWN
    button (already fixed) gets the responsive progress bar. Fixing the sequencer
    itself would mean interleaving the sub-operator's own `run_steps` generator into
    the outer sequencer's yields (scaling its fraction into the current step's
    range) instead of a black-box `_call` — a real design decision (how much of the
    sub-step's progress to surface, whether ESC should cancel just that step or the
    whole sequence), not a pure mechanical fix. Flagged for a follow-up design pass,
    not attempted yet.

42. **Two crashes, same session (2026-07-03): during "Find All Duplicates" and during
    "Find Orphans."** Logs synced 2026-07-04 (`PSM_Stage_v5.2.crash.txt` /
    `PSM_Stage_v5.2.crash_orphans.txt`), both analyzed via their Python backtraces.
    **Crash A (Find All Duplicates):** `progress.py:137 modal → analyze_all.py:65
    run_steps → analyze_all.py:27 _call → progress.py:86 execute →
    datablock_dup.py:153 run_steps → _gather_steps:102 → _fingerprint_for:73 →
    extract.py extract_shape_key`. Same disease class as the v0.2.94 mitigation, but
    THIS shape key's owner mesh is neither missing nor a Library Override — the
    existing 2-condition `shape_key_risk_reason` filter is confirmed INCOMPLETE, a
    third risk pattern exists that it doesn't catch. Exact trigger unknown — no
    local-variable data survives in a Windows crash dump; needs a live diagnostic
    probe against the real file to identify which shape key/mesh it is before
    designing the broader filter. **Crash B (Find Orphans):** `progress.py:137 modal
    → orphans.py:138 run_steps → orphans.py:65 _gather_steps → orphans.py:50 <lambda>
    → fingerprint.py:169 fingerprint_mesh → _sha → _canon → _round` (4-deep
    recursion, matches the expected dict→list→list→float mesh-payload shape) — odd
    because this crashes INSIDE pure-Python recursion over data `extract_mesh` had
    already finished extracting, not while reading raw bpy data directly. Most likely:
    `ops/orphans.py::_gather_steps`'s mesh-fingerprint path has **zero risk
    filtering** (only checks `db.library is not None`, never missing/override —
    unlike the shape-key path), so a corrupted override mesh's geometry silently
    passes through and detonates later; alternative explanation is heap corruption
    from elsewhere manifesting late.
    **Crash B: FIXED 2026-07-04.** `ops/extract.py::shape_key_risk_reason` refactored
    into a shared `datablock_risk_reason(block)` (missing/override check on ANY
    datablock, not just a shape key's owner) + a thin shape-key-specific wrapper.
    Applied in `ops/orphans.py::_gather_steps` before ALL THREE fingerprint types
    (Material/Mesh/Image, not just Mesh) with a new "Skipped — unsafe to read" list
    (`assetdoctor_orphan_skipped_text`, reusing the existing `_draw_kept_separate`
    UI helper — no new widget). New `tests/smoke_orphans_skip.py` (real override-mesh
    round trip) — **ran for real against Blender 5.1, all 3 checks passed.**
    **Crash A: probed 2026-07-04, DID NOT REPRODUCE — CLOSED for now, documented not
    guessed.** Ran a clean single-pass probe against the real `PSM_Stage_v5.2.blend`
    (open file, iterate every shape key, print owner state, call `extract_shape_key`
    on any not already flagged). Result: **all 759 shape keys read successfully, zero
    crashed, zero were even flagged by the risk check.** So the crash is NOT a
    property of any specific shape key in isolation — a fresh background open+scan
    doesn't hit it. The real crash happened via the LIVE session after a specific
    sequence (Find Flattenable Links → toggle Make Local → Scan Broken Links → THEN
    the duplicate scan, per that session's own info log) — leading hypotheses:
    order/state-dependent corruction from that exact sequence, or something tied to
    viewport/depsgraph activity that `--background` mode never triggers at all (no
    viewport draws happen headlessly). **User's explicit call: do NOT guess a new
    `shape_key_risk_reason` condition without evidence — stop here, leave the filter
    as-is, revisit only if the crash recurs with a fresh crash log** (replicating the
    exact live sequence would be the next diagnostic step, ~20-30 min of headless
    Blender time, deferred).

43. ~~**Missing Textures — "Fix at Source" (the read-only Linked-missing-textures list)
    doesn't list a source file for some rows.**~~ **FIXED 2026-07-04.** ROOT-CAUSED via
    screenshot (`overviewAndFixAtSourceMissingSource.png`, synced 2026-07-04) + a direct
    test: `os.path.basename("//materialMaster.blend")` returns `''` on Windows — `ntpath`
    misreads Blender's leading `//` (same-folder-relative marker) as the start of a
    UNC path. Confirmed against the crash log's own library list: `materialMaster.blend`
    and `ThePiazzaSanMarco - People.blend` are linked as bare `//Name.blend` (breaks);
    `human_bundle.blend`/`Asset_bundle.blend` are linked via multi-hop
    `//..\..\..\libraries\Name.blend` (works fine) — matches exactly which groups
    showed blank vs. correct in the screenshot. Same lesson already fixed once in
    `core/datablock_links.py::_basename` (2026-06-16) — promoted from module-private
    to a public `basename()` and reused at both broken `ui/panels.py` call sites
    (`_draw_linked_missing_textures` and `_draw_examine_library`'s suggested-library
    display). +5 pytest (suite 520). NEEDS the user's live-Blender confirm (fold into
    the next live-verify pass).

44. ~~**NEW, 2026-07-04 (screenshot `FindFlatLinksUpperArrowNotResponsive.png`):
    the top-level toggle arrow on `_draw_report_detail`'s "2 multi-hop route(s) · …"
    row (Find Flattenable Links' f7chain inline disclosure) doesn't expand when
    clicked.**~~ **NOT REPRODUCIBLE, CLOSED (2026-07-04).** User re-tested the same
    addon version against a DIFFERENT file and the drill-down was responsive there —
    so this looks like a one-off/file-specific state on the original file, not a
    general code bug. Documented only, per the user's explicit call — no further
    investigation or fix planned.

45. **Crash A (item 42) REOPENED — fresh crash log, 2026-07-04 Phase 2 live-verify
    session, real file `ThePiazzaSanMarco - People.blend`.** Log synced as
    `ThePiazzaSanMarco - People.crash_FindDuplicates.txt`. Python backtrace:
    `progress.py:137 modal → analyze_all.py:65 run_steps → analyze_all.py:27 _call →
    progress.py:86 execute → datablock_dup.py:174 run_steps → datablock_dup.py:121
    _gather_steps → datablock_dup.py:73 _fingerprint_for → fingerprint.py:231
    fingerprint_shape_key → _sha → _canon → _round` (recursing through the
    dict→list→dict→list shape-key payload shape, not runaway/infinite — matches
    the expected nesting depth). **This satisfies item 42's own reopen condition**
    ("revisit only if the crash recurs with a fresh crash log") — the user's
    explicit call was not to guess a new `shape_key_risk_reason` condition without
    evidence, and now there's a second one. Confirmed BY READING THE CODE (not
    guessed): `datablock_dup.py::_fingerprint_for`'s shape_keys branch already
    calls `extract.shape_key_risk_reason(block)` and skips (with a listed reason)
    before ever calling `fingerprint_shape_key` — so the crash proves the existing
    2-condition check (`datablock_risk_reason`: `is_missing` / Library Override,
    checked against the shape key's OWNER MESH) let a genuinely risky shape key
    through. A third risk pattern exists that neither condition catches. Per the
    user's own established rule for this exact disease class: do NOT add a guessed
    third condition — needs a live diagnostic probe against this real file (open it,
    iterate every shape key, print owner/mesh state for ones NOT flagged by the
    current check, look for what's structurally different) before designing the
    fix.
    **Probed 2026-07-04, DID NOT REPRODUCE — same outcome as the first Crash A
    probe, this time against the ACTUAL file that crashed.** Throwaway script
    (mirrors `ops/datablock_dup.py::_gather_steps` exactly: local shape keys only,
    filtered to `.NNN`-family membership via `core.datablock_graph.duplicate_families`)
    opened `ThePiazzaSanMarco - People.blend` fresh, headless, and ran
    `shape_key_risk_reason` + `extract_shape_key` + `fingerprint_shape_key` on
    every one of the 807 local shape keys one at a time with output flushed after
    each, so a crash's last line would name the culprit. Result: **all 807
    fingerprinted successfully, 0 flagged by the existing risk check, 0
    vertex-count mismatches (key_block data length vs. owner mesh vertex count —
    the specific "third risk pattern" hypothesis this probe was built to catch),
    0 crashed.** Confirms the crash is NOT a property of any single shape key in
    isolation, even in the exact file where it happened — reinforcing item 42's
    standing hypothesis that it's order/state-dependent (something about the live
    session's sequence: Find Flattenable Links → Make Local → Scan Broken Links →
    THEN Find Duplicates) or tied to viewport/depsgraph activity that
    `--background` mode structurally never exercises. **Per the user's own rule:
    closing again without a guessed fix.** The only remaining diagnostic step
    would be scripting that exact multi-operator sequence in one headless probe to
    see if the STATE left behind by the earlier steps (not the file alone) is what
    triggers it — deferred, ~20-30 min of Blender time, needs the user's call on
    whether it's worth pursuing further or left as a known, rare, unreproducible
    crash (the per-type Find Duplicates buttons from item 46j already let the user
    route around it in practice).
    **User's call, 2026-07-04: close it again, move on to item 46** — not worth
    scripting the exact live sequence right now.

46. **2026-07-04 Phase 2 live-verify session — 13 items from clicking through the
    Group 12 Phase 4 UI + Phase 3 batch changes on the real `ThePiazzaSanMarco -
    People.blend` / `PSM_Stage_v5.2.blend` files.** ALL FIXED same session, `v0.2.105`
    (item i/45 handled separately — see that item above). Per-item outcome after the
    a-m list below:
    - **a/c FIXED — but the real bug was different from the guess.** Check Materials
      (`matdiag`) was ALREADY on `ASSETDOCTOR_UL_tree` at the time of this report
      (built same session as Check Materials itself, v0.2.104) — reading the code
      disproved the "not ported yet" theory. The REAL cause of (c)'s scroll-jump:
      `ops/report_store.py`'s `focus_row`/`rebuild_rows_for_prop` had a case for
      every OTHER virtualized prop family (Reports tab, Resource Usage, the 5
      pickers) but not for `assetdoctor_detail_expanded` — the ONE prop shared by
      every Group 12 Phase 4 inline disclosure (Check Materials, Check Link Chain,
      Make Local, …) — so NONE of them ever re-pointed their list's active index at
      the row you just clicked. Fixed by adding that missing case (+1 smoke check in
      `smoke_report.py`). Affects every inline-detail feature, not just Check
      Materials.
    - **b FIXED** exactly as scoped: `ops/material_diagnostics.py` now recurses into
      a Surface-linked node GROUP's own Group Output, and `core.material_diagnostics`
      gained a `COMBINED_SENTINEL`/`COMBINED_SHADER` bucket. +2 pytest, +3 smoke
      checks (a synthetic "hair shader" group mixing Principled Hair + Glossy +
      Transparent, matching the real `HG_Hair_V4.001` case).
    - **d FIXED — button renamed; the headline bug was also different from the
      guess.** Tracing `_report_headline`/`core.f2_makelocal.build_makelocal_report`
      showed the "Summary" node's real text was ALREADY the headline (the existing
      `summary.children[0].label` branch handled it) — the actual gap was that this
      ONE branch never set `skip`, so the inline body wasn't excluded and showed a
      redundant "Summary" row repeating the same text under a pointless arrow. Fixed
      by setting `skip=summary` there too (+2 smoke checks).
    - **e** no action needed (already confirmed working).
    - **f FIXED**: `f4` added to `INLINE_DETAIL_FEATURES`; `_draw_orphans`'s
      fake_only/identical sections now build a filtered sub-`Report` and draw it via
      the same `ASSETDOCTOR_UL_tree` machinery (the "orphan" checkbox list and
      "summary" headline stay bespoke, unchanged) — the real motivator was less
      "inconsistent styling" and more that a production file's 1093 identical-group
      findings were ALL instantiated as native rows regardless of scroll position
      before this. +3 smoke checks (two synthetic fake-user duplicate materials).
    - **g FIXED**: new `_path_normalization_clean(wm)`; the "Normalize" button's
      `draw_action` now also requires `not clean`.
    - **h DEFERRED, not fixed.** The underlying popup (`ASSETDOCTOR_OT_show_linked_from`)
      already has its own "Nothing found" branch — the gap, if real, is that the
      TRIGGER for it (a `popup_parent` on a File Map row) may not get wired up when a
      file has zero links, which needs tracing through `core/depscan.py`'s File Map
      construction to confirm — not done this session (lower confidence + the user's
      own note says they plan to re-test on a file that has links first).
    - **j FIXED** exactly as scoped: `_draw_duplicates` is now a `_draw_group_header`-
      driven collapsed section (key `"duplicates:all"`) whose header carries the
      relocated "Find All Duplicates" trigger + a live "N/4 scan(s) run" summary;
      expanding it shows the 4 individual buttons (`scan_datablock_dups`/
      `material_dedup`/`instance_geometry`/`scan_content_dups`), each immediately
      followed by its own already-existing results function (unchanged). +7 smoke
      checks.
    - **k (tooltip) FIXED**: `ASSETDOCTOR_OT_row_toggle` gained an explicit short
      `bl_description` instead of falling back to its class docstring.
    - **k (popup) not reproducible** — no code change, matches the original note.
    - **l FIXED**: the "no_user" outcome message in `ops/report_store.py` now leads
      with "exists, but has no object instance in the current view layer" instead of
      "no user found," which read the same as the separate "doesn't exist at all"
      case above it.
    - **m FIXED — two distinct triangles, two distinct causes.** (1) `f7chain`'s
      all-zero case adds BOTH an "overview" Finding (always) AND a "clean" Finding
      (`core.linkchain.build_chain_report`'s own fallback, kept for its existing test
      coverage) — only the overview node was ever skipped from the inline body, so
      `_f7chain_headline` now returns BOTH as `skip` (a list; `_draw_report_detail`
      generalized to accept either shape). (2) The `f7flatten` "No
      override_with_transform characters found" row: traced the code and this ALREADY
      renders as a plain non-expandable row today (a lone flat "clean" node in the
      generic `_report_headline` path already produces `remaining=[]`) — the
      screenshot most likely reflects a stale installed build, not current source; no
      change made here, flagged for the user to re-confirm live. +2 smoke checks for
      (1).
    
    Original 13-item list (kept for context):
    a. **Check Materials** doesn't use the shared results-tree UI (Group 12 Phase 4's
       `ASSETDOCTOR_UL_tree`) yet — left-align/indent/click-to-select needs porting
       in, same as the other inline-disclosure sections got.
    b. **Check Materials shader-type classification is shallow** — doesn't look
       inside node groups, so a node group wrapping multiple BSDFs (e.g.
       `HG_Hair_V4.001`, a Principled Hair + Glossy + Transparent mix) gets listed
       as its own "shader type" instead of being recognized as a combined shader.
       Decided fix (not built): any material whose graph combines shader types —
       including through a node group — lumps into one "Combined Shader" bucket.
    c. Clicking a material row **near the bottom of Check Materials' list jumps
       the view to the top** — same scroll-position bug the shared results-tree UI
       already solved elsewhere; folds into (a)'s port.
    d. **Make Local**: button label "Make Local Impact" is confusing in the Analyze
       section — rename to "Make Local". Its result's summary line is empty; the
       actual summary text is on the line below it — needs to follow the standard
       summary-on-the-headline-row convention used everywhere else ([[feedback_summary_propagation]]).
    e. Find Orphans' progress bar now updates live — confirmed working, no action.
    f. **Find Orphans results** need to move onto the shared results-tree UI too
       (same reasons as a/c).
    g. **Path Normalization**: when the result is already-clean (nothing to
       normalize), hide the "Normalize" button instead of showing a no-op action.
    h. **Check Link Chain** never showed a "what links from here" popup on this
       file because there genuinely were no links — but a negative case still needs
       its own visible popup/result ([[feedback_negative_output]]: every scan needs a
       visible "nothing found" result, not silence).
    i. **Find Duplicates crashed** — see item 45 above, needs the diagnostic probe
       before any fix.
    j. **Find Duplicates restructure**: replace the single "Find All Duplicates"
       button with a collapsed-by-default sub-section; expanding it reveals the
       individual per-type buttons (Duplicate Textures / Materials / Geometry /
       etc. — recover the original breakdown) each with its own icon, button, and
       its own results sub-sub-section. "Find All" then runs each in sequence,
       waiting for one's results/UI update before starting the next. Also lets the
       user avoid the specific crashing sub-scanner (item 45) by running the others
       individually meanwhile.
    k. Confirmed **not reproduced**: the Check Link Chain "What Links from Here"
       popup not appearing — likely cursor position, needs a re-test on a file that
       actually has links. Separately, the expand/collapse tooltip text (screenshot
       `assetdoctor_detail_expanded`'s docstring-as-tooltip) is too long/low-value —
       needs a short user-facing string instead of the implementation docstring.
    l. **Audit This File's dependency-loop click-to-select result is ambiguous** —
       doesn't make clear whether the reported problem is "object not in this view
       layer" vs. "object doesn't exist at all"; the outcome message needs to
       distinguish the two.
    m. **Find Flattenable Links**: expand/collapse triangles are drawn on rows with
       nothing to expand (the "2 multi-hop routes" and "no override_with_transform"
       rows) — should only show the triangle when there's actually a child list.

## ✅ Group 12 Phase 3 (1 of 4) — Missing Textures virtualized, v0.2.96 (2026-07-03,
## NOT committed, NOT live-verified). New shape-B (single-level group→member) picker,
## generalizing the Phase 2 primitives rather than duplicating them:
## - `core/picker.py`: originally shape-specific `TargetGroup`/`TargetMemberData`/
##   `flatten_target_picker_rows` (bpy-free, 9 new tests, suite 505) — the live-data
##   analogue of `flatten_picker_rows` for sections whose member rows are individually
##   interactive (checkbox + target + picker button) rather than group-checkbox.
##   `PickerRow` gained `ref_prop` (which WM collection `ref_index` points into — Flatten
##   only ever pointed at one collection so never needed this) and `has_action` (group
##   rows only). **Superseded same session by item 2's generic `GroupSpec`/`MemberRef`/
##   `flatten_group_member_rows`** — see that digest below for why.
## - `ASSETDOCTOR_PG_picker_row` (reused, not duplicated) gained the matching `ref_prop`
##   field. New `ASSETDOCTOR_UL_missing_tex_picker` (`ui/panels.py`): group rows draw the
##   pre-baked triangle+icon+label+count+optional "point at folder" button; member rows
##   fetch the REAL `wm.assetdoctor_broken_imgs` row live via `ref_prop`/`ref_index` and
##   draw checkbox+name+target-status+file-picker straight off it — ticking a checkbox or
##   picking a file needs no rebuild (same live-data approach as `ASSETDOCTOR_UL_broken_libs`).
## - `ops/image_relink.py`: new `rebuild_missing_tex_picker_rows(wm)`, called after every
##   op that changes group membership (scan / relink selected) or a row's `target`
##   (per-file pick, accept one/material/all matches, folder-search exact modes) — the
##   group header's "N of M matched" count would otherwise go stale since it's no longer
##   recomputed on every redraw like the old hand-drawn loop was. NOT called from the
##   fuzzy folder-search or the two "suggest from…" ops — those only stage `.proposal`
##   (Possible Matches, still hand-drawn), which doesn't change this list's counts.
## - `ops/report_store.py`: `rebuild_rows_for_prop`/`focus_row` gained an
##   `assetdoctor_tex_expanded` branch (shared harmlessly with Possible Matches/Linked-
##   missing's still-manual, namespaced-key sections).
## - `ui/panels.py::_draw_missing_textures`: the manual group/member loop (dict-build +
##   sort + `_draw_group_header` + per-file row) replaced by one `template_list` over
##   `wm.assetdoctor_missingtex_picker_rows`. Possible Matches and Linked-missing-textures
##   sub-sections are DELIBERATELY NOT virtualized this pass (different member widgets —
##   confidence+Accept vs read-only — left for a quick follow-up, not blocking).
## - Manifest bumped to 0.2.96. pytest 505 green (496 + 9 new). LIVE-VERIFIED clean
##   2026-07-03 (except the unrelated #43 "Fix at Source" bug in the OLD, untouched
##   Linked-missing-textures list — see Group 13).

## ✅ Group 12 Phase 3 item 2 — Duplicate Textures virtualized, v0.2.97 (2026-07-03,
## same session as item 1's live-verify, NOT committed, NOT live-verified). Harder than
## Missing Textures: a family's GROUP is keyed by `material_override` (an eyedropper
## `PointerProperty`), which the user can change via a bare `row.prop()` edit with no
## operator at all — unlike every other per-row edit in this addon, that has no natural
## place to hang a rebuild. Solved by giving `core/picker.py` ONE fully-generic
## single-level shape instead of writing a second near-duplicate flatten function:
## - `core/picker.py`: replaced item 1's shape-specific `TargetGroup`/`TargetMemberData`/
##   `flatten_target_picker_rows` with `GroupSpec`/`MemberRef`/`flatten_group_member_rows`
##   — the caller now supplies each group's FULLY-FORMED `label`/`icon`/`has_action`/
##   `alert` (moved the "(N of M matched)" text-building into
##   `ops.image_relink.rebuild_missing_tex_picker_rows`, mechanical, no behavior change);
##   the flatten helper's only job is order + expand-state + member `ref_index`/`ref_prop`
##   stamping, the truly-shared "shell." `PickerRow` gained `alert` (red group-label
##   styling). 9 of the original Target* tests renamed/kept (same coverage, generic API);
##   suite still 505 (no net new — same shape, less code).
## - `ops/image_dedup.py`: new shared `effective_material(row)`/`is_mismatch(row)` (moved
##   out of two pre-existing, independently-duplicated copies — `_draw_duplicate_textures`'s
##   closures AND `ASSETDOCTOR_OT_dup_material_keeper`'s inline computation — a real
##   duplication that predates this session, now one source of truth) + `_DUP_MISMATCH_AFFINITY`
##   (moved from `ui/panels.py`). New `rebuild_dup_tex_picker_rows(wm)`, wired into
##   `scan_content_dups` (after `_fill_families`) and `merge_dup_selected` (after clearing
##   families).
## - `ui/panels.py`: `ASSETDOCTOR_PG_dup_family.material_override` gained an `update=`
##   callback (`_dup_override_updated`) — THE piece that makes this safe: every eyedropper
##   edit now rebuilds the picker rows immediately, so a re-homed family shows under its
##   NEW group instantly, no rescan needed. New `ASSETDOCTOR_UL_dup_tex_picker` (the
##   "keeper dropdown" row family — checkbox + alert-styled label + conditional
##   material-override eyedropper + keeper `EnumProperty`, vs. Missing Textures' checkbox +
##   target-status + file-picker-button family); group rows draw the master-keeper
##   (DOWNARROW_HLT) action button + alert styling when the group has a mismatch.
##   `_draw_duplicate_textures`'s manual loop replaced by one `template_list` over
##   `wm.assetdoctor_duptex_picker_rows`.
## - `ops/report_store.py`: `rebuild_rows_for_prop`/`focus_row` gained an
##   `assetdoctor_dup_expanded` branch.
## - Manifest bumped to 0.2.97. pytest 505 green, full `py_compile` clean. NOT
##   live-verified yet — see the checklist at the top of this file.

## ✅ Group 12 Phase 3 item 3 — Datablock Reconnect virtualized, v0.2.99 (2026-07-03,
## same session, immediately after item 2; user explicitly chose to keep stacking
## unverified work rather than live-test first). NOT committed, NOT live-verified.
## Simpler than Duplicate Textures — same "no natural rebuild hook" risk class doesn't
## apply here (Reconnect's `target` is a plain dynamic-enum pick that never changes
## group membership or counts, unlike Duplicate Textures' `material_override`), but
## introduced one genuinely NEW piece to the shared shell: a per-group STATUS LINE
## (which source .blend is picked / not picked yet / library not found) that used to
## draw as a plain label between the group header and its members.
## - `core/picker.py`: `GroupSpec` gained `info`/`info_icon` (default `"INFO"`) and
##   `flatten_group_member_rows` now emits a `"rollup"` row right after an expanded
##   group's header when `info` is set — the SAME row kind Flattenable Overrides
##   already draws for its property-summary line, just generalized with a caller-
##   chosen icon instead of hardcoded `"INFO"`. +4 tests, suite 515.
## - `ops/datablock_reconnect.py`: new `_group_info_line(source, lib_found)` (the
##   3-way status text+icon, moved out of the old hand-drawn version verbatim) +
##   `rebuild_reconnect_picker_rows(wm)` — groups by library (sorted by size desc.
##   then name, same order as before), wired into `scan_reconnect_targets` (after
##   `_populate_missing_blocks`), `reconnect_pick_source` (after `_enumerate_group`
##   — both `source_blend` and confidence change here), and `reconnect_selected`
##   (after both `_populate_missing_blocks` AND the transitive/external re-flagging
##   loop, since that also changes group counts).
## - `ui/panels.py`: new `ASSETDOCTOR_UL_reconnect_picker` — a THIRD member-row
##   family (checkbox + label + confidence icon/label + a bare `target` enum
##   dropdown, no file-picker or keeper) reusing `_RECONNECT_CONF`. Group rows always
##   carry the "Pick Source .blend" action button (no "ungrouped" exemption like
##   Missing Textures had). `_draw_reconnect`'s manual loop replaced by one
##   `template_list` over `wm.assetdoctor_reconnect_picker_rows`.
## - `ops/report_store.py`: `rebuild_rows_for_prop`/`focus_row` gained an
##   `assetdoctor_missing_expanded` branch.
## - Manifest bumped to 0.2.99. pytest 515 green, full `py_compile` clean. NOT
##   live-verified — see the checklist at the top of this file.

## ✅ Group 12 Phase 3 item 4 — Examine Library virtualized, v0.2.100 (2026-07-03,
## same session, immediately after item 3) — **Phase 3 COMPLETE, all 4 sections done.**
## The simplest of the four: unlike Reconnect/Duplicate Textures, grouping (by `kind`)
## never changes without a rescan and NO group-header text depends on per-row state —
## so `rebuild_examine_picker_rows` only needs to fire after Examine/Apply Selected;
## every other per-row edit (`selected`/`make_local`/`target`, or a fresh
## `source_blend` from Pick a Specific Item/Search a Folder) draws live off the real
## row, same principle as the other three, just with an even smaller rebuild surface.
## - `ops/examine_library.py`: new `rebuild_examine_picker_rows(wm)`, wired into
##   `examine_library` (after `_populate_examine_rows`) and `examine_apply_selected`
##   (after clearing rows).
## - `ui/panels.py`: new `ASSETDOCTOR_UL_examine_picker` — a FOURTH member-row family
##   (checkbox + label + a conditional middle status reusing `_graph_match_suffix` +
##   a Make Local checkbox + 2 per-row file-pick buttons — the busiest row of the four
##   sections). `_draw_examine_library`'s manual loop replaced by one `template_list`
##   over `wm.assetdoctor_examine_picker_rows`; the top summary line (data-block
##   count/matches/staged) stays hand-drawn, unaffected.
## - `ops/report_store.py`: `rebuild_rows_for_prop`/`focus_row` gained an
##   `assetdoctor_examine_expanded` branch.
## - Manifest bumped to 0.2.100 (not 0.3.0 — [[feedback-versioning]]: patch-only unless
##   the user flags a major-version bump; completing an initiative isn't that on its
##   own). pytest still 515 (reused the existing generic flatten API, no new bpy-free
##   surface needed). NOT live-verified — see the checklist at the top of this file.
## **All four Phase 3 sections now share ONE `core/picker.py` shell — the thing Group
## 12 originally set out to prove was possible.** Phase 4 (retarget
## `_draw_report_detail`'s inline Analyze disclosure onto the existing
## `ASSETDOCTOR_UL_tree`/`rebuild_report_rows` mechanism, closing the THIRD independent
## tree-renderer) is next whenever picked up — not started, not scoped in detail yet.

## ✅ Datablock Reconnect "2 skipped" bug — ROOT-CAUSED + FIXED 2026-06-28 (uncommitted)

Real user report against `human_bundle.blend`: Reconnect Selected said "Reconnected 0
data-block(s) ... 2 skipped" for `Std_Tongue.026`/`Std_Upper_Teeth.026` even though Pick Source
had correctly auto-suggested `Std_Tongue`/`Std_Upper_Teeth` from `materialMaster.blend`.
Root-caused via a real headless probe against the production file (not guessed): this project's
real files routinely have a LOCAL data-block sharing the exact same literal name as a
linked-but-missing placeholder (here, a local `.026` from an unrelated local duplicate family,
colliding by sheer coincidence with the stale-named linked placeholder).
`ASSETDOCTOR_OT_reconnect_selected.execute()` looked the placeholder up via a bare
`target_coll.get(row.name)` — ambiguous in this situation, and Blender's plain-name `.get()`
silently returned the LOCAL (non-missing) one, so the code concluded "no longer a missing
placeholder" and skipped it, even though the real placeholder was untouched and still
resolvable. This is the SAME disease already documented in `env-blender-verification` memory
(2026-06-25, `bpy.data.user_map` vs name-lookup) recurring in a spot that hadn't been fixed yet.
**Fix:** use the documented `(name, library)` tuple form of `.get()` to disambiguate
(`ops/datablock_reconnect.py`). New regression test `tests/smoke_datablock_reconnect.py` builds
the exact collision via a real save/reopen round-trip and confirms reconnect now succeeds with
zero skips; confirmed it FAILS against the pre-fix code (`git stash` check). pytest still 475
green. **Committed together with the Find Duplicates crash fix below as v0.2.94.**

**Three side-note TODOs from the same conversation, explicitly deferred (not built yet):**
1. **Check Link Chain formatting:** the results-section titles are currently centered; should be
   left-aligned / indentation standardized like the rest of the tree rows. Fix "next time we
   modify Check Link Chain results."
2. **Analyze Memory/Disk default state:** Groups/Sub-Groups should default to COLLAPSED (they
   currently open expanded, screenshot showed the full Image (1389) breakdown open by default).
   Fix "next time we modify Analyze Memory results."
3. **Datablock Reconnect needs an explicit success/fail note IN the results section itself**, not
   just the shared top-of-panel sticky banner (`assetdoctor_last_result`) — by the time a user
   scrolls down to a specific sub-panel like Datablock Reconnect, the global banner up top is easy
   to miss or misattribute to a different action. Likely the same fix is worth considering for
   other sub-sections sharing the one sticky banner. Needs a design pass — see
   [[feedback-suggest-better-designs]].

## ✅ Find Duplicates CRASH root-caused + mitigated 2026-06-28 (v0.2.94)

Real crash report from the user's live session on `human_bundle.blend` (crash log they
retrieved from the networked machine: `human_bundle.crash2.txt`). Python backtrace (the
authoritative section, present in the actual crash dump) pins it exactly:
`ops/progress.py:137 modal` → `ops/analyze_all.py:65 run_steps` → `ops/analyze_all.py:27 _call`
(invoking the Find Duplicates sub-operator) → `ops/progress.py:86 execute` →
`ops/datablock_dup.py:135 run_steps` → `_gather_steps` → `_fingerprint_for` →
`ops/extract.py::extract_shape_key` — a genuine `EXCEPTION_ACCESS_VIOLATION` (read @ null)
inside CPython's own eval loop, i.e. a true native segfault, not a catchable Python exception
(`_fingerprint_for` already wraps the call in `try/except Exception`, which is why that
existing guard didn't help — a C-level access violation skips Python's exception machinery
entirely and takes the whole process down).

**Likely root cause (not yet proven with a minimal repro, but well-supported circumstantially):**
`_gather_steps` only fingerprints LOCAL `.NNN`-family shape keys (`b.library is None`), and
`extract_shape_key` reads `key.user` (owning Mesh) then iterates `kb.data` for every key block.
`human_bundle.blend` has ALREADY-documented override/dependency LOOPS involving exactly this
kind of data (this session's own Audit This File screenshot: `Dependency loop:
Mesh/CC_Base_Body → Material/Std_Skin_Head.001 → Object/CC_Base_Body`) — a shape key whose
owning mesh participates in one of these loops likely has a corrupted/dangling internal
pointer that reads as a hard NULL when touched.

**Why a try/except fix won't work:** access violations can't be caught in Python (same
documented constraint as the `_populate_missing_blocks` re-peek crash risk, see
[[env-blender-verification]]). The only real mitigation is AVOIDING the unsafe read in the
first place. **User chose the cheap pre-filter option (not the heavier subprocess-isolation
alternative — that's still on the table later if this doesn't fully solve it).**

**BUILT (v0.2.94):** `ops/extract.py` gained `shape_key_risk_reason(key) -> str` — returns a
human-readable reason ("owner mesh 'X' is a missing placeholder" / "... is a Library Override")
or `""` if safe; `extract_shape_key` calls it and bails (returns `{}`) before touching `kb.data`
when non-empty, reusing the EXACT signal `ops.datablock_inspect`'s Audit already trusts
(`shape_key_risks`), not a new heuristic. `ops/datablock_dup.py::_fingerprint_for` gained a
`skipped` out-param (mirrors `core.imagefamily.iter_resolve_group_in_dir`'s existing
ambiguous/skipped_dirs out-param pattern) so the caller learns WHICH shape keys were skipped
and why, instead of them silently vanishing into the generic "unverified" bucket — **user
feedback mid-session: "should be notified... by name so the user can investigate."** New WM
`assetdoctor_datablock_skipped_text` + a "Skipped — unsafe to read (N)" collapsible list in the
Duplicate Data-blocks section (`_draw_kept_separate` generalized with an optional `label`/`icon`
to render both that and the existing "kept separate" list); `scan_datablock_dups`'s closing
report escalates to WARNING and names the skip count when any occurred. Two new smoke tests:
`smoke_extract_shape_key.py` (the guard itself, via a REAL Library Override built through the
normal link + `override_create()` round trip — confirmed the override mesh's shape key stays
LOCAL even though its owner is an override, so it WOULD have reached the unsafe read pre-fix)
and `smoke_datablock_dup_skip.py` (end-to-end: the override shape key is named in
`assetdoctor_datablock_skipped_text` with "Override" in the reason, a sibling plain-local
shape key in the same `.NNN` family is NOT). Both confirmed to fail against the pre-fix code.
pytest 475 green throughout. **Residual risk, disclosed not hidden:** this targets the
specific documented disease (override/missing-owner), not every conceivable corruption mode —
if Find Duplicates ever crashes again on different data, the subprocess-isolation option is
still the fallback. [[feedback-suggest-better-designs]]

## ⚠ Real bloat pattern found 2026-06-28: orphaned LINKED datablock coexists with a LOCAL
## same-name "made local" copy (newspaper object in PSM_Stage_v5.2.blend) — same disease
## family as the Reconnect Selected bug above, one level up (objects, not just materials)

User noticed (Outliner "newspaper" search) that the View Layer only shows an UNLINKED
"newspaper", while the Blend File Outliner view shows a "newspaper" nested under
`ThePiazzaSanMarco - People1_v5.1.blend`. Confirmed via direct offline BAT read of
`PSM_Stage_v5.2.blend`'s raw block table: there is exactly ONE "OBnewspaper" block in the
file, and it is LOCAL (`lib=None`) — NOT a linked ID placeholder. The linked "newspaper" the
Outliner shows nested under People1 is content PSM_Stage pulls in transitively via linking
People1.blend's collections (confirmed `human_bundle.blend` IS directly + indirectly linked
into `PSM_Stage_v5.2.blend` — 101 datablocks direct, plus reachable again via the separate
direct 7-datablock People1 link — matches the already-recorded 2026-06-24 multi-path finding).
That linked "newspaper" (and its Mesh + Material + 4 textures: `Newspaper001_COL/GLOSS/NRM/
REFL_2K.jpg`) is most likely an ORPHAN — pulled in because it's part of a linked Collection,
but never actually placed into any of PSM_Stage's own scene collections (hence invisible in
the View Layer search) — while the scene's REAL, visible newspaper is the local copy (likely
created by an earlier Make Local pass on the original linked prop). **Real, measurable bloat:
a full duplicate Mesh+Material+4×2K-texture set sitting unused.** Likely NOT unique to
"newspaper" — probably a systemic pattern across this project's asset-prep history (anything
that got "made local" once while the original linked source remained reachable). **Candidate
new AssetDoctor feature: detect "local datablock whose name/identity shadows a linked-but-
unplaced-in-scene datablock of the same family" as a new bloat-finding category** — distinct
from the existing Duplicate Data-blocks tool (same name, but one side is LOCAL+visible, the
other LINKED+orphaned, not two same-type local family members). **NEEDS DESIGN — discuss with
the user before building** (how to detect "unplaced in scene" cheaply at scale; whether removing
the orphan is safe to automate or report-only).

## ✅ human_bundle "missing link from People1" — NOT a bug, scope/direction mismatch (2026-06-28)

User saw, in PSM_Stage's native Outliner Blend File view, `human_bundle.blend` apparently
nested with `ThePiazzaSanMarco - People1_v5.1.blend` nearby, and asked why AssetDoctor's Check
Link Chain (run with `human_bundle.blend` itself as the current file) didn't show this.
Confirmed via direct offline BAT read: `human_bundle.blend`'s OWN file genuinely links exactly
ONE library (`materialMaster.blend`, 97 datablocks) — it has ZERO reference to People1.
Already-recorded 2026-06-24 finding (this memory file) independently confirms `PSM_Stage`
links `human_bundle.blend` BOTH directly AND via `People1.blend` (a real verified 2-hop
diamond). Check Link Chain scoped to `human_bundle.blend` can only ever show what
human_bundle ITSELF links forward (materialMaster) — it structurally cannot show an INBOUND
link from People1, since that's the reverse direction from a different root. `core.depscan.
_build_file_map`'s recursion (keyed by each file's own `scan.refs`, not the lossy single-
parent BFS `scan.parents`) WOULD render human_bundle nested under People1 too, if Check Link
Chain is run with PSM_Stage (not human_bundle) as the scanned root.

**CONFIRMED with real data, same day.** Ran `core.depscan.scan_recursive` from
`PSM_Stage_v5.2.blend` for real (174-242s). PSM_Stage's own direct refs DO include
`//ThePiazzaSanMarco - People1_v5.1.blend`, and the tree correctly renders it as a `[missing]`
leaf — its resolved path simply doesn't exist on disk on this machine right now (same Synology
sync churn that evicted `PSM_Stage_v5.1.blend` mid-session almost certainly relocated/evicted
this file too). Since it's unreachable, the scan can't recurse into it, so the exact
"human_bundle via People1" path the user's live session showed (where the file presumably
still resolves) can't be reproduced offline here — but the underlying multi-path tree mechanism
IS confirmed working: human_bundle legitimately renders via 2 other real paths
(`/PSM_Stage_v5.2/Asset_bundle/human_bundle` and `/PSM_Stage_v5.2/human_bundle` directly).
**Not a Check Link Chain bug, full stop — closed.**

## ✅ Phase 4 Apply (Flatten Link) safety investigation — RESOLVED 2026-06-26 (v0.2.69)

`ops/linkchain.py::_flatten_rig` used to silently steal and corrupt another character's body/
eye/clothing object when flattening a different character sharing a reference in
`human_bundle.blend` (`override_hierarchy_create()`'s opaque hierarchy-matching would adopt an
already-in-use object instead of creating a fresh one). **Fixed by switching to per-member
`ID.override_create()`** (we already enumerate every member + its own reference via the chain
census, so Blender's hierarchy auto-discovery was never needed) **plus a before/after freshness
check** on the result (compare `bpy.data.objects` names before/after the call) — a member whose
result isn't verifiably fresh is BLOCKED (clear message, no property replay, no user remap)
instead of trusted. **Verified end-to-end against the real 712-character `People1_v5.1.blend`,
in the actual scan-then-apply flow: "Flattened 8/9 part(s)"** — only the one structurally
unfixable case (`Smock.002`, a reference nobody in the file has individually overridden yet,
still a bare shared plain link) is blocked, down from the original 3-of-9 corruption risk.

A `bpy.data.user_map`-based PRE-check (try to detect risk before calling `override_create()` at
all) was attempted and reverted — in this file, every heavily-shared template shows real
`user_map` users after the normal scan runs first (hundreds of legitimate characters reference
the same templates), so the pre-check blocked all 9 members, not just the unsafe one. The
post-call freshness check is the reliable signal; don't reintroduce a pre-check without solving
that false-positive problem first.

**One known residual issue, not yet root-caused, low severity:** even when correctly BLOCKED,
`Smock.002` itself still gets silently converted to an override in place (and loses its
collection membership) as a side effect of merely *calling* `override_create()` on it — confirmed
via probe regardless of `remap_local_usages` True/False. The blocked member never gets property
replay or a user-remap (the dangerous part), but the shared object's owner (`child_older`,
elsewhere in the file) likely loses it from its collection as an unwanted side effect. Tried:
renaming it out of the way first (dead end — linked object names are read-only); `do_fully_
editable=True` (no effect, ruled out); `remap_local_usages=True` (also mutates in place, no
improvement). Root cause of WHY Blender does this specifically for a never-before-overridden bare
link is still unknown (web research confirmed "library override creation fails silently" is a
known, acknowledged Blender bug class — [#102495](https://developer.blender.org/T102495) — but
the exact mechanism wasn't pinned down). **Not blocking further work** — pick up only if it
recurs/matters for a specific file, since it no longer risks cross-character corruption.

**Design note for the Flatten UI (queued, build later as its own UI pass):** each flattenable
character row needs a checkbox to its left so the user can select which ones to flatten (all
checked by default). Near the Flatten button, add a SEPARATE checkbox (unchecked by default) to
make the character local instead of flattening via direct link. Touches
`_draw_flatten_candidates`/`ASSETDOCTOR_OT_build_flatten_plan` in `ui/panels.py`/`ops/linkchain.py`.

**Third checkbox, added 2026-06-26 — "Create Copy (Hide Original)", enabled by default.** When
on, build an identical COLLECTION structure for the flattened result instead of leaving new
objects in whatever collection the old object was in: find the collection containing ALL of the
to-be-flattened objects (the lowest common collection in the hierarchy; if none exists, start at
the Scene Collection instead), create a mirror of it named `<original>-flattened`, then mirror
the existing sub-collection structure down to wherever the flattened characters actually live —
skipping any sub-collection that contains NONE of the flattened objects (don't duplicate empty
branches). The ORIGINAL collection structure/objects are hidden (not deleted), so before/after is
inspectable and reversible. This needs its own small algorithm (find lowest common ancestor
collection across a set of objects, then walk+mirror only the branches containing a target) —
not just a flag on the existing per-member loop; design the collection-mirroring logic before
wiring it to `_flatten_rig`'s existing per-member `coll.objects.link()` step.

**API version note (resolved):** the official Blender 5.1 docs bundle, live RNA introspection of
the installed 5.1.2 binary, and the UPBGE docs mirror all agree word-for-word on the
`override_create`/`override_hierarchy_create` signatures — the version-mismatch concern raised
mid-investigation was legitimate to check but didn't explain any of the above; ground truth was
never in question once verified three ways.

## 🗂️ CONSOLIDATED TASK LIST (single source, 2026-06-26) — supersedes the scattered
## Phase 1-5 / lettered-batch / ROADMAP / "queued feedback" notes throughout the rest of this
## file. Those sections are kept below for historical detail (don't delete), but THIS is where
## to look for "what's left," grouped for efficient batched work. Built from a full sweep of
## the plan file + this whole TODO.md + targeted code spot-checks (2026-06-26). Each item below
## links back to its original detailed writeup by line-area description, not duplicated in full.

### Group 1 — `core/depscan.py` + `core/datablock_links.py` cluster (do together: same two
### files, same reused primitive (`datablocks_from_library`/`linked_datablocks`), same report —
### Check Link Chain). All report-only, no mutation, no design ambiguity.
### **DONE @ v0.2.72 (2026-06-26), items 1-4 — see the SESSION DIGEST below for detail/tests.**
1. ~~Add `depths: dict[str,int]` to `DepScan`, label every Missing/Circular finding's linking
   file "direct" vs "indirect (N hops via X)" — answers "Outliner shows 9, report shows 15."~~
2. ~~"Show what's linked from here" action on indirect File Map rows (offline BAT read of the
   PARENT file via `datablocks_from_library`, since indirect libraries aren't real
   `bpy.data.libraries` entries and can't click-to-select today).~~ **Built, but live-tested
   2026-06-26 and found unreliable — see Group 10 item #39, re-open before trusting this.**
3. ~~Circular-reference findings: nest the actual datablocks crossing each direction of the loop
   (same primitive) instead of just repeating the file names — needs a `circular_link`-specific
   branch in `build_dependency_tree`'s `cat_node`.~~
4. ~~Cross-reference `linked_datablocks(blend)` to downgrade a library with ZERO real referencing
   placeholders from "missing/error" to "stale, not actually used" — closes the "is everything in
   the chain actually relevant" gap.~~
5. ~~**INVESTIGATED, does NOT share the fix — deferred as its own item.** `ops/relink.py::
   _gather_libs` is a flat one-level read...~~ **BUILT 2026-07-04.** New
   `ops/relink.py::_direct_libraries(libs)`: for each `Library`, walk `bpy.data.user_map(subset=
   <that library's own linked IDs>)` (restricts which IDs appear as dict KEYS but still scans the
   WHOLE file for their users — cheaper than a full-file map, same technique
   `ops.datablock_inspect` already uses for its own loop detection) and check whether any user is
   LOCAL (`id.library is None`) — if not, the library is only reachable transitively through
   ANOTHER linked library. Capped at 60000 linked datablocks (mirrors `ops.datablock_inspect.
   _LOOP_NODE_CAP`'s own "too heavy" guard — assumes direct rather than hang on a giant file).
   `core/relink.py::LibDesc` gained `is_direct: bool = True`; `_populate_broken_links` stores it in
   the existing generic `tag` field (unused for this list); `ASSETDOCTOR_UL_broken_libs` shows an
   "indirect" flag (INFO icon) only for the surprising case — direct is the expected default, no
   added noise. New `tests/smoke_relink_direct_indirect.py` (real 3-file link chain, root→libA→libB,
   where libB is only reachable through libA's own data) — closes the original "ThePiazzaSanMarco.
   blend not in Libraries" confusion from v0.2.27 item #8. NEEDS the user's live-Blender confirm.

### Group 2 — Duplicate data-blocks report shape (`core/datablock_graph.py` + `core/tree.py`)
6. **MOOT @ v0.2.76 (2026-06-26) — the category this referred to no longer exists.** Was: group
   the "Duplicate data-blocks (.NNN copies)" category by TYPE, collapsed by default. Resolved by
   REMOVAL instead (see item 7 below) — f7live's `.NNN`-family detection is gone entirely, so
   there's nothing left to group. "Find Duplicate Data-blocks" (`ops/datablock_dup.py`), the
   surviving home for this capability, already groups by type.
7. **RESOLVED @ v0.2.76 (2026-06-26) — see the full writeup at the "RESOLVED" entry further down
   this file (search "f7live's").** Was gated pending a fresh discussion; discussed as part of
   Group 10 item #38 (2026-06-26) — final call was REMOVE the `.NNN`-family detection from
   "Audit This File" (f7live) entirely rather than verify it deeper, since it's redundant with
   (and less careful than) "Find Duplicate Data-blocks," and Image — the one type where it's
   usually a real duplicate — already has its own content-hash-verified tool.

### Group 3 — Phase 3 panel restructuring (`ui/panels.py`) — **items 8-10 FULLY SCOPED 2026-06-26,
### see Group 11 below for the concrete phased plan; kept here only as the original index entries.**
8. **"Reporting & Recommendations" section** — see Group 11 Phase E.
9. **"Cleanup & Fixes" section** — see Group 11 Phases B/C/D.
10. **"Info & Utilities" section** — see Group 11 Phase A.
11. ~~Progress-bar position...~~ **RESOLVED 2026-06-27, no code.** User's pick of the 3 identified
    options: leave it where it is. `_draw_progress()` is already the first call in the parent
    panel's (`ASSETDOCTOR_PT_scene_deps`) own `draw()` — the highest point achievable given
    Blender can't inject parent content between sibling child panels. "Near the top" is correct as-is.
12. ~~UIList virtualization for Missing/Duplicate Textures, Datablock Reconnect, Examine
    Library...~~ **CLOSED 2026-06-27 via a design pivot — see Group 12 below.** Discussing this
    item, the user pointed at "Flattenable overrides" (Find Flattenable Links / Flatten v2) as a
    UI template that already works well and asked for a broader pass: audit EVERY results
    section in the addon and extract a small set of shared, reusable components (not just bolt a
    UIList onto these 4 sections individually) — while actually solving the blank-rows-past-a-
    point risk this item was originally about, not just copying Flattenable Overrides' look
    (which is itself still a manually-drawn, non-virtualized box). Superseded by Group 12.

### Group 12 — Generalize the "results section" UI across the whole addon (started 2026-06-27,
### full plan at `C:\Users\Rick\.claude\plans\graceful-wondering-steele.md`). Supersedes Group 3
### item #12. Each phase is its OWN session with its own live-Blender confirm before the next
### starts, per this project's established practice for multi-phase UI work.
**Audit (2026-06-27):** 3 sections already virtualized (`ASSETDOCTOR_UL_tree` for the Reports tab
+ Resource Usage breakdown; `ASSETDOCTOR_UL_broken_libs` for Find Broken Library Links — proof a
`UIList` can draw LIVE widgets straight onto a real `PropertyGroup` row, not just static labels).
~13 sections are NOT virtualized, hand-looped Python in `panel.draw()`, in 3 shapes: (A) two-level
group→member mostly-read-only (`_draw_report_detail` — the inline disclosure under EVERY Analyze
button, e.g. the "24 multi-hop route(s)…" line — is a THIRD independent reimplementation of
`core.tree.flatten_visible`, the same primitive the Reports tab already virtualizes; plus Orphans'
informational sub-lists, duplicate-library-paths, absolute-paths); (B) single-level group→member
interactive (Missing Textures, Duplicate Textures, Datablock Reconnect, Examine Library, Datablock/
Material/Geometry Dups, Resolution Variants — checkbox/radio + label + 1-2 extra widgets per
member); (C) two-level outer→group→member with a GROUP-level checkbox — "Flattenable overrides"
(`_draw_flatten_candidates`/`_draw_rig_group`), the liked template: shared control row above the
list, ready-first sort, per-group rollup, live counts kept in sync
([[feedback-summary-propagation]]) — same shape as B, just one more nesting level + group- not
member-level checkbox. Also found **8 near-identical toggle operator classes across 6 files**
doing the exact same "toggle a key in/out of a newline-joined WM string-set" logic (2 of the 8,
`report_toggle`/`flatten_category_toggle`, already generalized themselves with a `prop` param —
the pattern the other 6 should have used); `report_toggle` is the most complete (toggle + rebuild
+ focus-row + redraw). `get_expanded`/`set_expanded` already exist generically in
`ops/report_store.py` but most of `ui/panels.py`'s 15 inline expanded-set reads don't use them.

**Design:** (1) one generic toggle operator (key+prop+optional rebuild dispatch) replacing all 8;
(2) shared `_draw_group_header()` + member-row-prefix helpers replacing the hand-copied
dict-build/sort/triangle/icon/label block in every shape-B/C function (each section keeps its OWN
per-member extra-widget code — that's the real, kept flexibility); (3) the actual virtualization
layer — new `ASSETDOCTOR_PG_picker_row` (`kind` outer/group/member, `group_key`, `ref_prop`/
`ref_index` pointing back into the section's REAL collection so `draw_item` reads/writes live data
with no sync step, `indent`, `label`, `icon`, `count_text`, `checkbox_state`) + a bpy-free flatten
helper (likely `core/picker.py`, the live-data analogue of `flatten_visible`) + 2-3 `UIList`
classes (one per ROW-SHAPE family, shared across the sections that have that shape — not one per
section, not one mega-list).

**Phases:** 0 (done, this entry) → **1** mechanical de-dup, no behavior change (toggle-op
consolidation + group-header helper, across all ~13 sections; lowest risk, fast pytest-only
verify) → **2** build the virtualization primitives, PROVE ON FLATTENABLE OVERRIDES ITSELF (hardest
shape — 2-level + group checkbox + remote sub-grouping — proves the simpler sections are a subset;
also closes its own latent blank-row exposure) → **3** roll out to the single-level sections,
risk-ordered: Missing Textures (documented real risk on huge files) → Duplicate Textures →
Datablock Reconnect → Examine Library → the smaller ones → **4** retarget `_draw_report_detail`
onto the existing `ASSETDOCTOR_UL_tree`/`rebuild_report_rows` mechanism instead of its own manual
loop, closing the third duplicate tree-renderer.

**Phase 1 DONE @ v0.2.93 (2026-06-27, pytest 475 green, NOT live-verified — Blender was already
running a real user session, user chose to skip a headless smoke pass for now).**
(1) **Toggle-op consolidation**: new `ASSETDOCTOR_OT_row_toggle` (`ops/report_store.py`) replaces
all 8 — `report_toggle`, `toggle_inline_detail`, and the 6 bespoke per-section ones (deleted from
`ops/linkchain.py`/`datablock_reconnect.py`/`datablock_dup.py`/`examine_library.py`/
`image_relink.py`/`image_dedup.py`). Default `prop="assetdoctor_detail_expanded"` (the common
case — the 9 inline-disclosure call sites needed no change beyond the idname); every dedicated-prop
section now sets `.prop` explicitly at the call site. Adopted Flatten's area+region double-redraw
(the 2026-06-27 "drill-down arrows stop responding" defensive fix) for every section, not just
Flatten's. `rebuild_rows_for_prop`/`focus_row` hardened to no-op for any `prop` that isn't (yet) a
virtualized collection — was a blanket `else: rebuild_report_rows(wm)`, which would have been
WRONG once one op serves every section (it would silently rebuild/clobber the Reports tab's rows on
an unrelated section's toggle). Removed a genuinely-dead unreachable code fragment found along the
way in `report_store.py` (leftover from a prior deletion, sitting after an unconditional `return`).
(2) **Shared `_draw_group_header()` helper** (`ui/panels.py`, next to `_draw_kept_separate`, which
now also uses it): triangle + icon + label [+ optional `action(row)` callback for a trailing
button] + optional `indent_factor`. Applied to 10 of the ~13 audited sections — Duplicate
Data-blocks, Duplicate Textures (incl. its master-keeper button + alert styling), Missing Textures
categories + its Linked-companion list + Possible Matches, Datablock Reconnect, Examine Library,
Resolution Variants, Duplicate Library Paths, Absolute Paths, Orphans' fake-user/identical
sub-lists. **Deliberately NOT touched**: `_draw_rig_group`/`_draw_flatten_candidates` (Flatten
v2 — structurally different shape, IS Phase 2's prototype target, not worth reshaping twice) and
`_draw_report_detail`'s inline tree disclosure (Phase 4's retarget target) and
`_draw_material_dups`/`_draw_geo_dups` (flat lists, no grouping at all — never had this duplication).
Zero visual/behavioral change intended throughout — verified by pytest (475 passed, same as before
this phase) + a full-repo `py_compile` pass; **NEEDS a live-Blender registration + visual spot-check
before Phase 2 starts** (deferred this session per the user's call).

**Phase 2 DONE @ v0.2.95, Phase 3 (1 of 4, Missing Textures) DONE @ v0.2.96 — see the
"NEXT SESSION"/"Group 12 Phase 3" digest at the top of this file for current status and
what's still unverified; don't re-derive from scratch, read it first.**

### Group 4 — Phase 4 Flatten UI polish (`ui/panels.py` + `ops/linkchain.py`)
13. ~~Per-character checkboxes... "make local instead" checkbox...~~ **SUPERSEDED by Group 11
    item #47 "Flatten v2" (2026-06-27) — fully redesigned and scoped there, don't build from this
    older, vaguer version.**

### Group 5 — Quick standalone fixes (different files, but each trivial/self-contained, no
### design ambiguity, good filler between bigger groups)
14. ~~Export default filename should interpolate the active feature...~~ **DONE @ v0.2.88
    (2026-06-27)** — see the "Find Duplicates display unification" digest above.
15. ~~Resource Usage: column headers (RAM|VRAM|disk at top, not repeated per row) + sortable
    columns...~~ **DONE + LIVE-CONFIRMED @ v0.2.89 (2026-06-27)** — see the "Resource Usage real
    columns" digest above the "NEXT SESSION" marker.
16. ~~"Different content, kept separate" conflict rows should say WHY...~~ **DONE @ v0.2.88
    (2026-06-27), turned into a real redesign (Materials/Geometry had NO conflict reporting at all;
    Image Content's was dead code) — see the "Find Duplicates display unification" digest above.
    NEEDS the user's live-Blender confirm.**

### Group 6 — Make Local correctness/perf — confirmed against current code 2026-06-27, see the
### "Make Local: 3 findings" digest above the "NEXT SESSION" marker
17. ~~In-Place localize may not fully localize objects in hidden/excluded collections...~~ **NOT
    A BUG — confirmed empirically @ v0.2.91 (2026-06-27).** `bpy.ops.object.make_local(type='ALL')`
    is a file-wide mode (unlike `'SELECT_OBJECT'` etc.), proven via probe to localize everything
    regardless of selection/visibility/collection-exclusion; the per-ID fallback pass is also
    selection-independent. The recorded "lead" was based on a mistaken assumption.
18. ~~Progress bar reportedly invisible on huge files...~~ **DONE @ v0.2.91 (2026-06-27)** — root
    cause confirmed by reading the code (exactly as recorded) and fixed: `ops/make_local.py`'s
    gather + in-place backup-write now run AS the modal generator's own first steps instead of
    synchronously in `invoke()` before the timer starts.
19. ~~Guard against running In-Place localize on a file that's itself a shared library...~~ **DONE
    @ v0.2.91 (2026-06-27), narrower and more precise than the original ask** — investigation
    showed the real risk is rename-driven name collisions specifically, not "shared file" in
    general; built `core/f2_makelocal.py::find_rename_collisions`, surfaced in the F2 report and
    the final apply message. NEEDS the user's live-Blender confirm (modal/progress-bar timing is
    interactive-only).

### Group 7 — Small new features, self-contained, no major design ambiguity
20. ~~Examine Library: folder-wide search...~~ **DONE @ v0.2.92 (2026-06-27)** — see the
    "Examine Library folder-wide search" digest above the "NEXT SESSION" marker. This was the
    LAST item on the reprioritized Quick Fixes (Groups 5-7) list. NEEDS the user's live-Blender
    confirm.
21. ~~Global dedup preference: keep-local vs keep-linked, separate for materials and meshes...~~
    **DONE @ v0.2.90 (2026-06-27)** — see the "Geometry now clusters local+linked" digest above
    the "NEXT SESSION" marker. NEEDS the user's live-Blender confirm (the preference dropdown
    + behavior on a real file mixing local/linked materials or meshes).

### Group 8 — Bigger ROADMAP features (genuinely new work, several need a design discussion
### before any code; ordered roughly cheapest-to-scope first)
22. **Automated Cleanup pipeline** — unlike the others below, the FULL design is already locked
    (nested panels, run order, backup-once, savings metrics) — implementation-ready once the
    individual modal sections it depends on are live-verified, not a "needs discussion" item.
48. **NEW (2026-07-04) — Categorized file-load warnings.** User's ask: capture Blender's own
    load-time errors/warnings (missing library datablocks, silent node-link repairs, disabled
    embedded scripts, dependency-relation-build failures, etc.), categorize/prioritize them, and
    surface suggested fixes — an EXTENSIBLE parameter list, grown over time as new patterns are
    found. Feasibility researched same day: these messages have NO clean bpy API (raw console
    output from Blender's low-level file reader, not the operator-report system) — the right
    primitive is `core/remote_harvest.py`'s existing disposable-background-subprocess pattern
    (built for Flatten v2): open the target file in a throwaway subprocess, capture its console
    text, parse into structured findings. Real example patterns already gathered from
    `PSM_Stage_v5.2.blend`'s own load log this session: "LIB: <kind> 'X' missing from <lib>" (maps
    to existing Datablock Reconnect), missing-library warnings (maps to existing Broken Library
    Links), "Repairing invalid state in node link..." (informational, Blender already self-healed),
    "scripts disabled for..." (informational), "Failed to add relation X -> Y" / depsgraph
    `ComponentKey` errors (NEW territory, severity/fix not yet designed). User's explicit call:
    add to this roadmap group in priority order, do NOT jump the queue ahead of item 22.
23. Texture-channel synonym table + inverse-pairs (gloss↔roughness) — root-caused, needs a
    design decision on 3 sub-parts (editable prefs list; suggest-but-flag-inverted; an actual
    invert/convert action as separate future work).
24. Synology conflict-file diff/merge — scoping questions already identified (reuse
    `core.fingerprint` per-type + the Flatten Plan's `path_resolve` property-walk for the diff;
    the "pull one change in" mutation needs its own per-type apply logic) — needs full design
    discussion before any code.
25. Material override → real node-tree reassignment — today's eyedropper only re-groups the
    report, doesn't rewire the file; needs the user to decide exact semantics (move vs copy node,
    which socket, behavior with no matching target node) before any code.
26. Archive Project (BAT `pack` → zip) — unscoped, needs design from scratch.
27. Lazy-depth scan — unscoped, needs design from scratch.

### Group 9 — Verification / spot-checks (little to no new code unless something's found broken)
28. **The standing big one:** a full live-Blender verify sweep — almost everything since v0.2.5
    has shipped without ever being clicked through in the real UI. Named repeatedly across nearly
    every session digest as the single biggest backlog item.
29. Confirm the literal crash-stack names (`character1_cs.012`/`cs_grp.012`/`Mesh_006_001` etc.)
    were actually resolved by the broader Reconnect fixes, or reconnect them specifically.
30. ~~Confirm/re-confirm the F8 hierarchical-layout direction (leaf-at-top vs root-at-top)~~
    **RE-CONFIRMED + REVERTED 2026-07-04.** User's explicit answer: root-at-top, not
    leaf-at-top. `core/linkmap_html.py::assign_depths` now returns the mirror of its
    internal leaf-based longest-outgoing-chain computation (`max_depth - depth`) —
    same cycle-safe algorithm, just flipped top/bottom; the JS `applyTree()` comment
    ("roots at the top") was actually stale since the 2026-06-25 inversion and is now
    accurate again with no JS changes needed (it just renders whatever depth Python
    assigns). `tests/test_linkmap_html.py`'s depth-layering test updated to match.
    Suite still 520. NEEDS the user's live-Blender confirm (can't render the actual
    HTML graph headlessly).
31. Reproduce (or rule out) the Batch 2 relink/merge crash theory (Solid vs Material viewport
    shading) — mitigation code is in place but never proven necessary or sufficient.
32. ~~Confirm with the user whether "Remove Excess Variants" (already built) fully closes the old
    ROADMAP "footprint reduction — Layer 2 resolution-standardize" line, or whether a separate
    global/per-family auto-standardize mode is still wanted on top of per-group manual picking.~~
    **CLOSED 2026-07-05.** User's call: per-group manual picking is enough — no auto-standardize
    mode wanted. No code change.
33. **3 "Scene Debug"-style features (list materials by shader, missing node links, empty
    material slots) — confirmed nowhere else in the codebase, BUILT @ v0.2.104 (2026-07-04) as
    "Check Materials."** User's design decisions: fold into the existing Analyze tab (not a
    separate Properties-editor panel); "missing node links" scoped to dangling links only
    (`NodeLink.is_valid` False — real socket-type-mismatch breaks, not "artistically unlinked by
    choice") plus broken Image Texture nodes (image file missing on disk, same check as Find
    Missing Textures, deliberately overlapping); read-only, no bulk-fix action (removing a slot
    remaps polygon material indices — riskier to automate than it looks). New `core/
    material_diagnostics.py` (bpy-free, `classify_shader_label`/`build_*_findings`/
    `build_material_diagnostics_report`, 10 unit tests) + `ops/material_diagnostics.py`
    (`ASSETDOCTOR_OT_check_materials`, chunked scan of every material's node tree + every
    object's material_slots). Reuses the fully generic report/tree machinery end-to-end — new
    `"matdiag"` key in `report_store.FEATURES` + `INLINE_DETAIL_FEATURES`, 3 new categories in
    `core/tree.py::_CATEGORY_TITLES` (shader_type/node_link_issue/empty_slot) — no new
    PropertyGroup, UIList, or WM collection needed. Button placed in the Analyze tab right after
    Find Orphans. `tests/smoke_material_diagnostics.py` — real Blender 5.1 run, all 6 checks
    passed (Principled/Emission/Mixed-Shader grouping, missing-image-node flag, empty-slot flag).
    **NOT covered even by the smoke test:** a genuinely dangling/invalid `NodeLink` — Blender's
    Python API only ever creates valid links, so there's no simple way to fabricate the real
    "socket type changed after a version upgrade" case; that path's report-building logic is
    unit-tested with synthetic data instead, but the bpy-side extraction (`_material_node_issues`
    in `ops/material_diagnostics.py`) is unverified against a real invalid link. **NEEDS the
    user's live-Blender confirm** on a real production file if one happens to have this issue.

### Group 10 — v0.2.72 live-test feedback (2026-06-26, real production file; #34 FIXED @ v0.2.73,
### #35 FIXED @ v0.2.74, #39 PARTIALLY fixed @ v0.2.75, all below — #36 checked/not-a-bug, #37/#38/
### #40/#41 still NOT investigated/built (need a design discussion first) — documented per the
### user's explicit "don't begin work on any" instruction; READ THIS GROUP FIRST next session,
### ahead of Group 2).
34. ~~**REGRESSION, top priority — the "Analyze All" button no longer works.**~~ **ROOT-CAUSED AND
    FIXED @ v0.2.73 (2026-06-26).** Turned out NOT to need a live repro at all — `EXEC_DEFAULT`
    bypasses `invoke()`/the modal event loop entirely and calls `execute()` directly (no window
    needed), so it WAS exercisable headlessly; confirmed via the project's standard
    diagnostic-probe pattern ([[env-blender-verification]]). Root cause: `ops/analyze_all.py`'s
    `ASSETDOCTOR_OT_find_duplicates` (added 2026-06-25) subclassed the ALREADY-REGISTERED concrete
    `ASSETDOCTOR_OT_analyze_all` operator directly. Confirmed via an isolated repro (two toy
    operators, same pattern) that once Blender registers a SECOND `bpy.types.Operator` subclassing
    an already-registered concrete Operator, the RNA→python-class binding for the FIRST one breaks
    — `bpy.ops.assetdoctor.analyze_all(...)` kept returning `{'FINISHED'}` but silently ran ZERO of
    its own code (no steps populated, no report stashed), exactly matching the live symptom ("the
    per-step status icon never moves"). `bpy.rna` printed a console warning
    (`unable to get Python class for RNA struct 'ASSETDOCTOR_OT_analyze_all'`) — the actual tell,
    easy to miss in the noisy System Console. **Fix:** extracted the shared dispatcher body into a
    plain `_AnalyzeSequencerMixin` (NOT a registered Operator, same pattern as `ModalProgressMixin`
    itself) — both `ASSETDOCTOR_OT_analyze_all` and `ASSETDOCTOR_OT_find_duplicates` now inherit
    from `(_AnalyzeSequencerMixin, ModalProgressMixin, bpy.types.Operator)` independently instead
    of one subclassing the other. Re-verified with the same probe technique: both ops now run their
    real step count (13 and 4) and stash a result. Suite still 400 (no test changes needed — the
    bug was Blender-registration-level, invisible to bpy-free tests). **General lesson for this
    codebase: never subclass one concrete registered Operator from another — always factor shared
    logic into a plain mixin.**
35. ~~**Indentation/line-spacing bug in the INLINE Analyze disclosure — likely the SAME bug class
    fixed once already, but in a second, unfixed code path.**~~ **FIXED @ v0.2.74 (2026-06-26),
    NEEDS LIVE CONFIRM (UI draw can't be tested headless).** Hypothesis confirmed by re-reading the
    code: `ui/panels.py::_draw_report_detail` (the ONLY other call site building a `flatten_visible`
    arbitrary-depth tree, besides the already-fixed `ASSETDOCTOR_UL_tree.draw_item`) had
    `drow.separator(factor=2.8 + r.indent * 1.4)` — one separator scaled by depth, the exact pattern
    proven to break non-linearly past ~3 levels. Every OTHER `separator(factor=...)` call in
    `ui/panels.py` was checked and is a fixed constant for a shallow 1-2-level custom layout (Find
    Flattenable Characters' rig/member rows, Duplicate groups, etc.) — not built from
    `flatten_visible`, not in scope for this bug class, left alone. Fix: same shape as the v0.2.67
    UIList fix — `drow.separator(factor=2.8)` (unchanged base offset) followed by `for _ in
    range(r.indent): drow.separator(factor=1.4)` (N unit separators). Since `_draw_report_detail`
    is the SHARED renderer for every Analyze-section report (f7/f7live/f7chain/f7links/geo/f4/f2),
    this one change covers File Map, Circular references, Multi-hop link chains, Flattenable
    overrides, etc. all at once — matches the user's "recheck every report" ask without touching
    each individually. Suite still 400 (layout-only, no test impact, like every other panel change
    in this project). **NEEDS the user's live-Blender confirm** — re-check the same File Map
    (`LS`/`human_bundle`/`materialMaster`) and Circular-references screenshots that reported this.
36. **Progress-bar-over-current-file-data — CHECKED, not a bug.** User confirmed it's a transient
    artifact while the UI is frozen mid-heavy-scan; once unfrozen the layout is correct. No action.
37. **Click-to-select feedback is too easy to miss, and its message can mislead — FIXED @ v0.2.103
    (2026-07-04).** User's decision: an outcome icon on the row itself (found-and-selected /
    no live user / unresolved), not relying on a one-shot status message after the click.
    `ops/report_store.py` gained `SELECT_OUTCOME_ICON` (CHECKMARK/QUESTION/ERROR),
    `_load_select_outcomes`/`_save_select_outcome`/`get_select_outcome` (JSON dict, keyed
    `"Type/Name"`, persisted in the new WM `assetdoctor_select_outcomes` StringProperty so it
    survives redraws) and `ASSETDOCTOR_OT_select_datablock.execute()` now records an outcome +
    `tag_redraw()`s at every exit path (unresolved / no-user / found), checking "unresolved" FIRST
    (previously only the no-targets case was distinguished). Wired into
    `ASSETDOCTOR_UL_tree.draw_item` (covers every report row, Reports tab, Resource Usage, and
    every inline Analyze disclosure since Phase 4) and all 3 direct
    `assetdoctor.select_datablock` buttons in `_draw_orphans`. Did NOT touch the "check Orphan
    Data" wording sub-ask — the new icon replaces the need to parse that message at all, so it's
    now moot. **NEEDS the user's live-Blender confirm** — click a few rows of each outcome type
    and check the icon shows up and updates correctly.
38. **Audit ALL headings/sub-headings for a one-line summary — SWEPT @ 2026-07-04, closed, no
    fixes needed.** User asked for a dedicated sweep rather than closing this as done-by-osmosis.
    Result: every `_draw_group_header` call site (11 of them) already passes a live, data-derived
    label (counts, chosen-state, or a report finding's own message — none bare/static). Every
    top-level Analyze-tab feature (all ~18 buttons, including the 4 Find-Duplicates children)
    already shows a live headline via its own `_X_headline`/`_X_summary` helper or
    `_draw_report_detail`'s generic `_report_headline`, with a "✓ nothing found" fallback per
    [[feedback-negative-output]]. The only 4 spots with a static-looking title (Examine Library,
    Map a Folder, Safe-to-delete?, and the inner "Missing Textures" sub-header) all already carry
    their live count/status on a SEPARATE line directly below the title — the same established
    "static button + summary line below" shape used everywhere else in this UI (e.g. Analyze
    Memory/Disk) — so nothing there is actually missing a summary, just structured differently
    than the merged-into-heading style. No code changes made; item closed.
39. **Item 2's new "show what's linked from here" popup is unreliable in live use — do not trust
    it yet, contradicts the "DONE" mark above.** Couldn't get the popup to display reliably; not
    obvious what to click (the row looks like plain text — no visual cue that it's a button, unlike
    every OTHER clickable row's icon/affordance); a processing delay meant several clicks landed
    after the user had already moved on and clicked elsewhere, dismissing the popup the instant it
    appeared. **Leading hypothesis CONFIRMED by reading the code:** `ASSETDOCTOR_OT_show_linked_from.
    invoke()` (`ops/report_store.py`) does call `datablocks_from_library` SYNCHRONOUSLY on click — a
    real BAT disk read of the parent file, which this project's own notes elsewhere clock at up to ~1
    min/file on this user's large production files (`[[project-assetdoctor]]`, v0.2.4 digest) — with
    zero progress indication. **(b) PARTIALLY FIXED @ v0.2.75:** wrapped the blocking read in
    `context.window.cursor_modal_set("WAIT")` / `cursor_modal_restore()` — an OS-level cursor swap,
    shows immediately even mid-blocking-call, no redraw needed — so a slow read now visibly looks
    "busy," not "broken." Did NOT do the alternative half of (b) (a fast-path guard / moving the read
    off the click path) — the cursor fix is simpler and addresses the same symptom; revisit only if
    live-testing shows the busy cursor isn't enough. **(a) — the visible clickable-row affordance —
    deliberately NOT done.** Inventing a new icon convention is a real design choice this project has
    reversed multiple times already (severity icons removed 2026-06-16, category icons re-litigated
    repeatedly) — flagged for the user to decide rather than guessed at. **NEEDS the user's live
    re-test of the popup** (does it now feel responsive, was the busy cursor enough, is (a) still
    wanted) before relying on item 2 for anything.
40. ~~**Multi-hop Link Chains — redesign. DECIDED 2026-07-04, NOT built yet.**~~ **(a)/(b) BUILT
    2026-07-05, (c) DROPPED.** `core/linkchain.py::build_chain_report`'s `multihop_route` Finding
    used to read `"{root} reaches {target} via {N} hops: {chain}"`, repeating the root/current
    file's own name on every line. **(a) done:** message is now `"Reaches {target} via {N}
    hop(s)"` (+ the existing "(also linked directly)" suffix when `has_direct`), root name dropped.
    **(b) done:** `items` now holds one display-name entry per hop (`longest[1:]`, root excluded)
    instead of the old flat `" -> "`-joined chain string; `core/tree.py` gained
    `_HOP_ICON_CATEGORIES` so every `multihop_route` item child renders with a
    `LIBRARY_DATA_DIRECT` icon (no new UI code needed — `report_to_tree`'s existing
    `items`→children machinery + `FILELINK_UL_tree.draw_item`'s existing `item.icon` draw already
    plumb it through end-to-end). `routes_from_report` (used by Flatten v2's `build_flatten_plan`)
    updated to read the target path from `data["paths"][0][-1]` instead of `finding.items[1]`,
    since `items` is now display-only hop names, not raw paths — `data["paths"]` (unchanged, still
    raw) is the only thing downstream code should parse. +4 pytest (suite 535). **(c) DROPPED
    2026-07-05, user's call:** tracing the actual data model showed there's no real per-datablock
    "indirect reference" to repoint — `DepGraph` nodes are whole FILES (built by an offline
    dependency scan, not the open `bpy.data` session), so a `has_direct` route just means root's
    blend file has a SEPARATE direct edge to target for some unrelated datablock; target's actual
    data is one shared Library entry either way, nothing to remap at the bpy level. Revisit only if
    a concrete production case surfaces showing a real thing to fix.
41. ~~**Flattenable overrides — redesign, needs clarification of WHICH view this refers to before
    any code.**~~ **RESOLVED + BUILT @ v0.2.82 (2026-06-26).** Root cause of the original confusion:
    two near-identically-named buttons computing the SAME `OVERRIDE_WITH_TRANSFORM` data and
    showing it TWICE — "Find Flattenable Link Chains" (`assetdoctor.scan_link_chains`, feature
    `f7chain`) rendered a flat, ungrouped `posing_override`/`posing_modifier` list (this is what the
    user actually saw — exactly the "Flattenable overrides (Library Override + transform)" title
    quoted originally), while "Find Flattenable Characters" (`assetdoctor.scan_flatten_candidates`)
    re-read that SAME data grouped by rig — but only reachable as a SEPARATE second button that
    hard-required the first to have run already (`scan_flatten_candidates.execute()` errored "Run
    Find Flattenable Link Chains first" otherwise). User's call once this was traced out: merge the
    two into one **"Find Flattenable Links"** button (mirroring "Find Duplicates"'s existing
    multi-step-dispatcher pattern), not just fix the flat list in place.

    **Built:** new `core.analyze_steps.FLATTEN_STEPS` (`find_flattenable_chains` +
    new `find_flattenable_characters` step, in that order — the second needs the first's f7chain
    data already stashed) + new `ASSETDOCTOR_OT_find_flattenable_links`
    (`ops/analyze_all.py`, same `_AnalyzeSequencerMixin`/`ModalProgressMixin` shape as
    `ASSETDOCTOR_OT_find_duplicates` — see the Group 10 #34 mixin-not-subclass rule, followed
    correctly here, not re-violated). The new step also joined `STEPS` proper, so Analyze All now
    groups characters too (14 → 15 steps). The two old operators (`scan_link_chains`/
    `scan_flatten_candidates`) are UNCHANGED internally and still independently registered (Analyze
    All's own step list calls them individually) — only their `bl_description`s got a note that
    they're normally run together now; their old `bl_label`s ("Find Flattenable Link Chains"/
    "Find Flattenable Characters") only surface in internal step-status lists today, not as
    standalone buttons.

    **Display dedup:** rather than deleting the per-object `posing_override`/`posing_modifier`
    Findings from `build_chain_report` (`remote_posing_files` — the "found in another file, open it
    there" fallback for multi-hop-deep characters — genuinely reads them back out of the stashed
    Report, and several `test_linkchain.py` tests assert on them; deleting would have broken a
    load-bearing fallback for zero display benefit), `ui/panels.py::_feature_tree_nodes` now drops
    just those two category nodes from the RENDERED f7chain tree when `feature == "f7chain"` — the
    data stays fully intact in the Report/JSON, only the redundant flat display is hidden. The
    f7chain "overview" line (multi-hop/override+transform/modifier-driven counts) is unchanged and
    still always visible above the (now deduped) tree.

    **Grouped-picker improvements** (the 3 the user picked, out of the original #41(a)/(b)/(c)
    asks): (1) **sort ready-first** — `ui/panels.py::_flatten_group_sort_key` (new), 3-tier
    (fully-ready / partially-ready / fully-blocked), alphabetical only as the final tiebreak;
    (2) **distinguish real rigs from standalone overrides** — new `is_rig` bool on
    `ASSETDOCTOR_PG_flatten_candidate` (set in `ops/linkchain.py::scan_flatten_candidates` from
    whether `_resolve_rig()` found a real armature, vs falling back to the object's own name), real
    rigs sort before standalone AND draw with `ARMATURE_DATA` vs `OBJECT_DATA`; (3) **show WHY a
    member is blocked** — this data already existed (`m.status` holds the matching `FlattenPlan`'s
    `warnings` text whenever not ready — `read this back as already correct, not a gap`), the only
    real fix was the icon: blocked members drew `QUESTION` (reads as "unknown"), changed to `ERROR`
    ("blocked, here's why" — the warning text right next to it already explains it).

    Group/object-type grouping (the original #41(b), "group by object type") was NOT done — once
    rig-tier sorting + the is_rig split landed, the user's 3 picked improvements didn't include it;
    revisit only if a future file shows a real need (lots of standalone non-rig overrides of
    genuinely different types bunched together unhelpfully).

    New `tests/smoke_flatten_links.py` (the sort key + the tree-dedup-but-data-intact behavior, both
    pure-logic-in-a-bpy-importing-module, can't be pytest'd) + extended `tests/smoke_analyze_all.py`
    (the new operator joins the existing 2-sequencer RNA-corruption-class regression dance, now
    3-way) + `tests/test_analyze_steps.py` (`FLATTEN_STEPS`, `len(STEPS) == 15`). Suite 402 (+1 net
    pytest); `smoke_flatten_links`/`smoke_analyze_all`/`smoke_register`/`smoke_utils`/`smoke_report`
    all green. **NEEDS the user's live-Blender confirm** (panel `draw()`/real override objects can't
    be exercised headlessly) — particularly the sort order and icon distinction on a real
    multi-character file, and that the merged button's single status icon reads sensibly.

    **Follow-up fix @ v0.2.83 (2026-06-27), found via the user's live test on `PSM_Stage_v5.1.blend`
    (929 flattenable, 0 local).** The v0.2.82 dedup above was too broad: it hid the WHOLE
    `posing_override`/`posing_modifier` categories from the f7chain tree, but the grouped picker
    (`_draw_flatten_candidates`) only ever shows objects LOCAL to the open file — with zero local
    candidates, hiding the flat list too left no way to inspect ANY of the 929/4907 beyond a bare
    remote-filenames note. Fixed: new `core/linkchain.py::drop_local_posing_findings(report,
    current_file)` drops only the LOCAL rows (still duplicated by the picker); REMOTE rows (object
    several hops deep, in a file the picker can never see) are kept. Also fixed a latent bug this
    surfaced: the `posing_modifier` Finding never recorded `source_file` in `data` at all (only
    `posing_override` did), so a modifier-driven row could never be identified as local — added it.
    4 new pytest tests (`test_linkchain.py`) + rewrote `smoke_flatten_links.py` to assert
    local-hidden/remote-kept against a real saved-to-disk file (needed `bpy.data.filepath` to be a
    real path, not the empty unsaved-file case the first version used). Suite 406.

47. **Flatten v2 — design session 2026-06-27, supersedes the "Design note for the Flatten UI" at
    the very top of this file (kept above only for historical detail). Real motivating case: on
    `PSM_Stage_v5.1.blend` the user wants to find a character that's linked indirectly (current
    file → some intermediate → ultimate library), with changes made to it somewhere in that chain,
    and end up with a DIRECT link in the current file that's visually identical — without touching
    the donor file's existing override.** That's a genuinely different operation from today's
    "Flatten," which only ever re-routes an override that's already LOCAL to the open file — it
    never creates one from scratch, and never reads properties from a file that isn't open. Full
    design, decided step-by-step with the user this session:

    **Presentation** (`_draw_flatten_candidates`): standalone objects (no resolvable rig) group by
    `object.type` instead of one 1-member group per object (today: `row.rig = obj.name` fallback).
    Each row gets a per-row checkbox (default checked). The **Make Local**/**Make Copy**/
    **"Flatten Selected"** controls are NOT per-character — there is exactly ONE set, living on the
    "Flattenable overrides" subgroup's own title line, acting on whichever rows are checked.
    `Make Local` defaults OFF, `Make Copy` defaults ON.

    **Flatten Selected pipeline**, per checked row:
    1. **Harvest source properties.** If the override is already local, read it live (today's
       existing `read_live_override_properties`, unchanged). If it's REMOTE (per the census's
       `source_file`), the lookup is **scoped to that exact file — name + source_file, never an
       aggregate `bpy.data` search** (this project has a documented past bug from exactly that:
       multiple linked libraries can share a literal object name, see
       [[env-blender-verification]]). **PROBED 2026-06-27
       (`tests/probe_remote_override_link.py`, throwaway, not a regression test) — the
       temporary-link idea is dead, not just limited.** Built a real override in a donor file
       (linked object from a source file, `override_create()`'d, transform adjusted, saved), then
       tried `bpy.data.libraries.load(donor_path, link=True)` from a fresh session. Confirmed: the
       donor file's own `bpy.data.objects` genuinely has BOTH the override AND the original linked
       object, but `libraries.load()`'s `data_from.objects` enumeration showed **neither** — only a
       third, truly-plain local object (added as a sanity check) was listed. **Blender's linking
       API only exposes truly-local, non-override IDs; an override (or anything already reached
       through a link) is invisible to a file trying to link it a second time.** So there is no
       live-bpy way to harvest a remote override's properties at all — only an offline DNA read of
       the donor file could do it, and reading the FULL arbitrary `override_library.properties`
       list that way would need a generic offline RNA-path-to-value resolver (a much bigger,
       separate undertaking — not started, not assumed needed yet). **Scoped-down, achievable
       plan instead: reuse data the offline census ALREADY captures.** `ObjectPosingInfo` (built by
       the existing `read_object_posing`/BAT scan that already runs for Find Flattenable Links)
       already carries `loc`/`rot`/`quat`/`size` for every posing-classified object, local or
       remote, no new read needed. Remote-sourced replay is therefore **transform-only** (object
       loc/rot/quat/scale) — a real, explicit scope difference from local-sourced flattening, which
       still gets the full arbitrary-property replay (bones/actions/drivers/parenting/materials/
       modifiers) via the existing live-bpy path. Document this gap in the UI rather than silently
       under-deliver (e.g. the per-row status/outcome text should say "transform only" for a
       remote-sourced result, not imply full parity with a local one).
    2. **Link directly** from the resolved ultimate library; create a brand-new override (never
       mutates the donor's own override in its own file).
    3. **Replay** the harvested properties onto it (the "mimic").
    4. **If Make Copy is on:** build/reuse a mirrored collection tree. Algorithm, fully pinned down
       this session: find the lowest common collection across every object in THIS apply batch;
       mirror it named `<original-name>_flattened`, placed as a **sibling** of the real ancestor
       (a new child of the ancestor's own parent) — UNLESS the ancestor is the Scene Collection
       itself, which has no parent to be a sibling under, so the mirror becomes a new child of
       Scene Collection directly. Walk down from there mirroring ONLY branches that contain at
       least one flattened object (skip empty/irrelevant siblings, e.g. `Collection.005`/`.006` in
       the worked example below); a collection shared by two or more characters in the same batch
       is mirrored ONCE and reused, not duplicated per character. New objects (and their existing
       children — clothing, eyeballs, etc., same parenting preserved) are renamed
       `<original-name>_flattened`; the ORIGINAL structure is hidden, never deleted. **Moot/no-op
       for a remote-sourced character** — there's no pre-existing local object to hide in the first
       place, so the new direct link is simply the only thing that exists. If Make Copy is off:
       replaces in place (today's existing behavior).

       Worked example (user-provided, confirms the algorithm exactly):
       ```
       Before:                              After (Armature1 + Armature2 flattened, Make Copy on):
       Scene Collection                     Scene Collection
        Collection.001                       SceneCollection_flattened   <- new, sibling-of-root
        Collection.002                         Collection.002_flattened
          Armature1                              Armature1_flattened
            Clothing1                              Clothing1_flattened
          Collection.005 (empty)                Collection.004_flattened
          Collection.006 (empty)                  Armature2_flattened
        Collection.003                                Clothing2_flattened
        Collection.004                       Collection.001
          Armature2                          Collection.002
            Clothing2                          Armature1
                                                  Clothing1
                                                Collection.005
                                                Collection.006
                                              Collection.003
                                              Collection.004
                                                Armature2
                                                  Clothing2
       ```
       (Root is named after the true lowest common ancestor, `SceneCollection_flattened` here
       because Scene Collection happens to be it in this example — NOT a fixed literal name. If
       two flattened characters shared a deeper common collection, e.g. both under
       `Collection.002` but in different sub-collections, that shared collection is mirrored once
       and reused, not duplicated.)
    5. **If Make Local is on:** final step appended to the end of the pipeline (not an alternate
       branch) — `make_local()` the result and its children, fully detaching from the library.
    6. **Update outcome counts in every place they're shown**, per the new standing
       [[feedback-summary-propagation]] rule: the subgroup title becomes something like
       `"Flattenable overrides — XX original, YY flattened, ZZ failed"`; the top overview line's
       `"YY flattenable"` becomes `"AA of YY flattenable"` (AA = remaining, i.e. not yet
       flattened) — both read from the same persistent state, both update together after every
       apply, not just a one-shot operator message.

    **Open, deferred without guessing:** whether shape-key VALUES get captured as override
    properties at all (depends on whether the Key/Mesh sub-data participates in the override
    hierarchy — version/setup-dependent) — verify against a real character before trusting either
    way; if they're driver-driven from the rig instead of manually set, they likely need no replay
    at all since the driver lives in shared library data, not per-character.

    **Anchor-finding for a remote character's placement — real screenshot-driven correction,
    2026-06-27, then deliberately scoped down for v1.** Initial assumption was wrong: a
    remote-sourced character usually DOES have a real local anchor in the current file (e.g. a
    local Empty instancing a linked Collection several hops from the actual override — confirmed
    against a real Outliner screenshot of `PSM_Stage_v5.1`'s `People > Courtyard_people_left_near_a`
    structure) — `anchor.users_collection` gives its placement directly, no tree-walk (that part was
    never hard). The genuinely hard part is finding WHICH local anchor corresponds to a given remote
    character in the first place — tractable in principle (match the chain's first-hop library path
    against local Empties'/Objects' `instance_collection.library`/`.library`, disambiguating by
    instanced-collection name if more than one local anchor shares that library) but real new work,
    not built yet. **Scope decision: defer it.** For v1, every remote-sourced character is treated
    as "no anchor found," which the mirroring algorithm above ALREADY has a defined fallback for —
    Scene Collection. This composes for free with the rest of the algorithm: a batch mixing local
    and remote characters still works, since the lowest-common-ancestor of a real collection and
    "Scene Collection" is just Scene Collection. **In-place (Make Copy unchecked) is also deferred
    this round** — the checkbox stays in the UI defaulting on, but the operator runs the copy path
    regardless of its state for now (reporting that in-place isn't built yet if someone unchecks
    it), since the user expects the in-place case to be simpler to build once the copy path (and
    its mirroring/renaming logic) is proven.

    **BUILT @ v0.2.84 (2026-06-27), NEEDS LIVE-BLENDER CONFIRM (panel `draw()` and real override
    objects can't be exercised headlessly — verified instead via real synthetic .blend files this
    session, see below).** Two Blender-API facts discovered by hand while building/testing this,
    neither obvious going in and both load-bearing for the design: **(1)** `Object.library` always
    attributes to a datablock's TRUE owning file, even through several layers of indirection — a
    file that only reaches an object via ANOTHER file's collection never "owns" it. **(2)**
    `override_create()` only succeeds on an object whose `.library` is a DIRECT dependency of the
    CURRENT file — never one only reachable through another file's collection. Together these
    explain why the real `PSM_Stage_v5.1.blend` has 0 local candidates: it canNOT create its own
    override on anything it only reaches indirectly, same as the synthetic test files built to
    verify this.

    What shipped: `core/remote_harvest.py` (script/command builders + output parser, bpy-free,
    7 tests) + `core/collection_mirror.py` (the lowest-common-ancestor path math, bpy-free, 10
    tests, includes the exact user-provided worked example). `ops/linkchain.py` gained
    `_harvest_remote` (the disposable-subprocess lifecycle, mirrors `ops/dryrun_render.py` exactly),
    `_realize_mirror_plan`/`_resolve_real_collection` (real Collection creation from the path math —
    one real bug caught by the smoke test: the first mirror entry's parent isn't always the scene
    root, it can be arbitrarily deep when there's only one object in the batch), `_flatten_member`
    (the generalized per-member flatten — deliberately NOT a refactor of the existing
    production-validated `_flatten_rig`, kept untouched), and the new `ASSETDOCTOR_OT_flatten_selected`
    operator tying it together. `scan_flatten_candidates` now groups standalone (no-rig) LOCAL
    objects by `object.type` instead of one row each, and ALSO surfaces remote candidates (status
    "not yet checked" until harvested). `ui/panels.py`'s picker gained a per-group checkbox
    (tracked as DESELECTED keys, default all-checked) and the single shared Make Local/Make Copy/
    "Flatten Selected" control row living on the "Flattenable overrides" heading, per
    [[feedback-summary-propagation]] — both that heading's own outcome line ("XX original, YY
    flattened, ZZ failed") and the top f7chain overview line ("AA of YY flattenable", new
    `_f7chain_headline`) read from the same persistent `wm.assetdoctor_flatten_done`/`_failed` state
    and update together after every apply.

    Deliberately scoped down for this round (recorded above, not re-litigated): in-place (Make Copy
    unchecked) isn't built — the operator always copies regardless of the checkbox, reporting that
    in-place isn't built yet if unchecked; a remote character's collection-mirror anchor is always
    Scene Collection (the harder "find the real local anchor, e.g. a Collection-instance Empty"
    lookup is deferred); shape-key replay fidelity is unverified either way.

    Verified via 3 new real-Blender smoke tests (synthetic .blend files built and reopened for
    real, not mocked) since panel/override behavior can't be pytest'd: `smoke_flatten_selected.py`
    (a genuine local override end-to-end — ready-detection, flatten, collection mirroring, renaming,
    hide-original, Make Local, AND the live top-line count, across two differently-typed objects so
    group-selection logic is exercised too) and `smoke_remote_harvest.py` (the actual subprocess
    round-trip against a real donor file). `smoke_flatten_links.py` updated for the new `is_remote`
    field. Suite 424 pytest; all 7 relevant smoke tests green
    (`smoke_register`/`smoke_utils`/`smoke_report`/`smoke_analyze_all`/`smoke_flatten_links`/
    `smoke_flatten_selected`/`smoke_remote_harvest`).

    **One Blender-internal console message seen during the smoke test, not yet root-caused, low
    severity (same category as the already-documented "Smock.002" residual issue at the top of this
    file):** `lib.override ERROR Existing isolated override 'OBChar' has a non-null hierarchy root
    ('OBChar_flattened'), will be cleared` — appears after a successful flatten; Blender appears to
    self-correct it (every functional check still passed). Not investigated further this session —
    flag if it recurs or matters on a real file.

### Group 11 — Analyze/Utilities/Results panel consolidation — ALL 5 PHASES BUILT @ v0.2.77-0.2.81
### (2026-06-26), NEEDS ONE LIVE-BLENDER CONFIRM PASS (deliberately batched per the user's own
### request — "a live check will be most effective once everything is in place" — rather than
### per-phase). FULLY SCOPED 2026-06-26 (design session this session; supersedes Group 3 items
### 8-10 above and the now-stale "Phase 0-5" plan
### at `C:\Users\Rick\.claude\plans\declarative-booping-ripple.md`'s Phase 3 — that file is
### historical only, this is the current record). The Phase 3a redesign (2026-06-25) moved every
### scan TRIGGER into "Analyze This File," but left many results lists + action buttons behind in
### the old `ASSETDOCTOR_PT_results` holding pen (explicitly documented as "NOT a Phase 3b/3c
### design... a holding pen"). This finishes that deferred split. Decisions confirmed with the
### user before scoping: Path Normalization's fix actions (Normalize/Use Selected Paths/Make
### Selected Relative) are NOT redundant with Check Link Chain (which only reports the same
### issues, never fixes them) — relocate, don't delete; the "two blank Results sections" are
### `_draw_duplicate_library_paths`/`_draw_absolute_paths` (empty on THIS file, not dead code —
### move with Path Normalization); f9 (Dry-Run Render Warnings) and f7flatten (Flatten Plan
### preview) have no inline display anywhere today — give both one, THEN delete the generic
### Reports selector (everything else already shows inline); the Duplicates unification means
### unifying the DISPLAY (one container, grouped by type) not the underlying merge mechanism —
### each type's identity verification genuinely differs (node-graph fingerprint for materials,
### content-hash for images, name+per-type-fingerprint for generic blocks, mesh comparison for
### geometry) and should stay separate. Each phase below is independently shippable/testable —
### own version bump, own live-Blender verify, per [[env-blender-verification]] (panel `draw()`
### can't be exercised headlessly) — do NOT batch all 5 into one unreviewable change.
42. ~~**Phase A — Utilities relocations (pure UI move, lowest risk).**~~ **BUILT @ v0.2.77
    (2026-06-26), NEEDS LIVE-BLENDER CONFIRM (panel `draw()` can't be tested headless).** Moved
    (not duplicate) into
    `ASSETDOCTOR_PT_utilities.draw()`: "Run Dry-Run Render" trigger (was the `dry = layout.
    box()...` block in `ASSETDOCTOR_PT_results.draw()`); "Profile Render (Real RAM)" `_analyze_row`
    (was in `ASSETDOCTOR_PT_analyze.draw()`); Examine Library (`_draw_examine_library`, was called
    from `_results.draw()`, now a method on `ASSETDOCTOR_PT_utilities`) as its own always-visible
    box (picker + Examine button shown regardless of scan state, matching its original shape).
    Analyze Memory/Disk left in Analyze per the recommendation (it's one of the official
    `core.analyze_steps.STEPS`, included in Analyze All — unlike Dry-Run/Profile Render,
    deliberately excluded as "too slow/disruptive for the sequencer"). Suite still 398
    (UI-relocation only, no test impact); `smoke_register`/`smoke_utils` (panel-structure
    assertions) both still green.
43. ~~**Phase B — Path Normalization + Reconnect + Broken Library Links → Analyze.**~~ **BUILT @
    v0.2.78 (2026-06-26), NEEDS LIVE-BLENDER CONFIRM.** `_analyze_row` gained an optional
    `draw_action` callable param — draws one narrow extra operator on the right side of the
    summary row instead of a separate box below. New `_broken_links_headline(wm)` (mirrors
    `_reconnect_headline`) + new `_path_normalization_headline(wm)` (renames count from the f7fix
    report + duplicate-library/absolute-path GROUP counts from the interactive lists — skips
    drawing the read-only f7fix tree itself, same reasoning as Broken Links). New "Check Library
    Paths" Analyze trigger (Path Normalization had none before) added to `core.analyze_steps.
    STEPS` (now 14 steps, suite/`smoke_analyze_all.py` updated to match). `_draw_reconnect`/new
    `_draw_broken_links`/new `_draw_path_normalization` (folding in `_draw_duplicate_library_paths`/
    `_draw_absolute_paths`) converted from `ASSETDOCTOR_PT_results` methods to module-level
    functions, dropped their own restated headline/action button, now draw directly under their
    Analyze row. Removed the 3 corresponding blocks from `_results.draw()`. Suite 399 (+1 new
    test for the new step); `smoke_register`/`smoke_utils`/`smoke_analyze_all` all green
    (confirms the new step runs + the 14-vs-13 count update didn't break anything).
44. ~~**Phase C — Duplicates unification (the headline redesign).**~~ **BUILT @ v0.2.79
    (2026-06-26), NEEDS LIVE-BLENDER CONFIRM.** Turned out narrower than scoped once the code was
    actually read: 3 of 4 sections (Data-blocks/Materials/Geometry-once-built) already draw
    consecutively right after the ONE "Find Duplicates" trigger — only Geometry lacked an
    actionable UI (still the old read-only tree) and Duplicate Textures (Images) was still
    physically stuck in the old Results holding pen with its own separate headline. Built: new
    `ASSETDOCTOR_PG_geo_family` WM PropertyGroup (mirrors `ASSETDOCTOR_PG_datablock_family`, no
    keeper field — instancing always keeps the canonical mesh `choose_canonical` already picked,
    no ambiguity) + `core.geometry_dedup.removable_count` (2 new tests) + `ops.instance_dedup.
    _populate_geo_families` (called from the existing `instance_geometry` scan, mirrors
    `_populate_material_families`) + new `ASSETDOCTOR_OT_instance_geometry_selected` operator
    (mirrors `merge_material_selected` — cheap fresh id-to-mesh re-resolve, no re-fingerprinting).
    New `_draw_geo_dups`/`_geo_dups_headline` in `ui/panels.py`, wired into Analyze in place of the
    old `_draw_report_detail(layout, wm, "geo")` call. `_draw_duplicate_textures` (the Images
    section, ~115 lines) converted from an `ASSETDOCTOR_PT_results` method to a module-level
    function (dropped its `self._DUP_MISMATCH_AFFINITY` class attr → module constant; dropped its
    own `context.region`-based narrow calc in favor of taking `narrow` as a parameter, matching
    `_draw_duplicates_summary`'s existing shape) and moved into the same Analyze sequence, right
    after Geometry. Kept all 4 underlying scan/merge operators and data models completely separate
    (different identity verification per type is real) — only the DISPLAY consolidated, exactly as
    scoped. New regression test `tests/smoke_instance.py` extended with the selective-apply
    scenario (untick → CANCELLED no-op confirmed; tick → real merge confirmed) — proves "selective"
    is real, not a relabeled apply-everything. Suite 401 (+2 geometry, +0 net for the textures
    move); `smoke_register`/`smoke_utils`/`smoke_analyze_all`/`smoke_instance` all green.
45. ~~**Phase D — Orphans selective Purge UI.**~~ **BUILT @ v0.2.80 (2026-06-26), NEEDS
    LIVE-BLENDER CONFIRM.** Scoped down from the original "checkbox for orphan/fake_only/
    identical" wording once `ops/orphans.py`'s own module docstring was re-read: clearing fake
    users or merging identical datablocks "reflects intent, not just cleanup" was an EXISTING,
    deliberate design choice (the legacy bulk purge already only ever touches true orphans,
    users==0) — kept that scope rather than quietly expanding it. New `ASSETDOCTOR_PG_orphan_row`
    (checkbox only, no keeper — purging is binary) + `ops.orphans._populate_orphan_rows` (mirrors
    `_populate_material_families`) + new `ASSETDOCTOR_OT_purge_orphans_selected`. Verified via a
    headless probe that `bpy.data.batch_remove(ids=[...])` (Blender's own generic, mixed-type-safe
    removal primitive — same one the native orphan-purge button uses internally) is the right tool
    here, since selected orphans can span arbitrary datablock types and there's no per-type
    `.remove()` call to dispatch to without it. New `_draw_orphans`/`_orphans_headline` in
    `ui/panels.py` fully replace `_draw_report_detail(layout, wm, "f4")` — orphans get the
    checkbox+Purge-Selected treatment, fake-user-only/identical stay read-only/informational
    (click-to-select preserved, drawn straight from the report) in the SAME custom function, to
    avoid double-displaying orphans once actionable AND once in a generic tree. `tests/smoke_f4.py`
    extended with the selective-purge scenario (two fresh orphans, untick one, confirm Purge
    Selected removes only the ticked one — proves real per-row selectivity). Suite 401 throughout;
    `smoke_register`/`smoke_utils`/`smoke_analyze_all`/`smoke_f4` all green.
46. ~~**Phase E — Cleanup deletions.**~~ **BUILT @ v0.2.81 (2026-06-26), NEEDS LIVE-BLENDER
    CONFIRM.** Deleted `ASSETDOCTOR_PT_geometry` and `ASSETDOCTOR_PT_orphans` (both legacy panels
    that existed only to hold one blunt apply-everything button, now superseded by Phases C/D's
    selective UIs). Built minimal inline displays: Dry-Run Render Warnings (f9) under its Utilities
    button (`_draw_report_detail(dry, wm, "f9")`); Flatten Plan preview (f7flatten) at the end of
    `_draw_flatten_candidates` (one shared slot — whichever rig was last previewed/applied, not
    per-rig). **Scope grew once the code was actually read:** Missing Textures (`_draw_missing_
    textures` + 2 helper methods, ~210 lines) was ALSO still stuck in the old Results holding pen
    — never explicitly called out in the original phase breakdown — converted to module-level
    functions and relocated into Analyze (same treatment as Phase B/C's relocations) so Results
    could actually be deleted. f1 (Link Map)'s stashed report — flagged as "confirm before
    touching" — was given a minimal inline home (`_draw_report_detail`) next to its "Map Folder →
    Open Graph" button instead of asking the user to decide whether to abandon it: purely additive
    (no capability lost), resolves the flag without needing a decision. Deleted
    `ASSETDOCTOR_PT_results` entirely once everything it held had a home; also deleted
    `ASSETDOCTOR_OT_report_select`/`_report_clear`/`_report_expand_all` — the 3 operators that
    existed exclusively to power the now-gone generic selector (confirmed via grep: zero other call
    sites). **Deliberately did NOT delete** `rebuild_report_rows`/`assetdoctor_report_rows`/
    `active_feature`'s role in `stash_report` — these run unconditionally from the core stash
    pipeline every single scan operator calls, so even though nothing displays
    `assetdoctor_report_rows` anymore, removing them is a deeper refactor of `stash_report` itself,
    out of scope for this change — flagged as a known, harmless (just wasted recompute) follow-up
    cleanup, not silently left ambiguous. `ASSETDOCTOR_UL_tree`/`assetdoctor.report_toggle` both
    stay — still actively used by the Resource Analyzer's own tree. Updated `tests/smoke_report.py`
    (replaced the 2 deleted-operator calls with direct calls to the underlying still-alive
    functions they wrapped — `wm.assetdoctor_active_report` + `rebuild_report_rows`/
    `active_feature`/`data_prop`/`exp_prop`/`available_features` — preserving the same coverage)
    and `tests/smoke_utils.py` (sub-panel count 7→4, added the 3 newly-retired class names to the
    existing "retired N-panel classes are gone" check, dropped the dead `_SELECTOR_EXCLUDE`
    reference). **Verified the whole Group 11 pass didn't introduce any regressions** by diffing
    against a `git stash` of the pre-session code: 3 pre-existing, unrelated smoke-test failures
    (`smoke_idle_scan`, `smoke_examine_library`, `smoke_folder_search_diagnostics`) were confirmed
    to fail IDENTICALLY on the original code, ruling out this session as the cause — real, but not
    new, not investigated further here. Suite 401 throughout; every other smoke test green.

### Detail-on-demand for items #1-#4 above (the original "queued live-UI feedback" writeups,
### kept verbatim for the full reasoning/evidence trail — not separate open items)

- **DONE @ v0.2.67:** File Map indentation/row-height bug at depth 3+ — `ui/panels.py
  ::ASSETDOCTOR_UL_tree.draw_item` used ONE `row.separator(factor=item.indent * 1.4)`; a
  single large-factor separator inside an `align=True` row visibly breaks (both width and
  row height go non-linear past ~3 levels) — fixed to `for _ in range(item.indent):
  row.separator(factor=1.4)` (N unit separators instead of one scaled one). Needs the user's
  live-Blender confirm (panel changes can't be tested headlessly).
- **BUILT @ v0.2.72 (2026-06-26), but LIVE-TESTED AND FOUND UNRELIABLE same day — see Group 10
  item #39 above before touching this again.** "Show what's linked from here" for indirect File
  Map rows, built as a transient POPUP (not a permanent inline expand — agreed with the user, who
  also noted the dedicated Reports tab is expected to go away once the Phase 3 panel restructuring
  is done, but it's wired there too since it's still live today).** New `TreeNode.popup`/
  `Row.popup` field (`{"parent","basename"}`, JSON round-tripped); `core.depscan._filemap_popup`
  sets it on any File Map row with `depths[node] >= 2` (a library only reachable through another
  library — `depth is None` for a missing/never-visited target is explicitly NOT treated as
  direct). New `ASSETDOCTOR_OT_show_linked_from` operator (`ops/report_store.py`) calls
  `datablocks_from_library(parent, basename)` on click and lists the results in a
  `window_manager.popup_menu`, each row reusing the existing `select_datablock` operator. Wired
  into both the inline Analyze disclosure (`ui/panels.py::_draw_report_detail`) and the dedicated
  Reports tab (`ASSETDOCTOR_PG_tree_row.popup_parent/popup_basename` +
  `ASSETDOCTOR_OT_row_label`). Not live-Blender verified yet (UI/popups can't be headlessly
  tested) — Blender was occupied (likely a render) when this was built, so it still needs a
  click-through pass.
- **DONE @ v0.2.70 (2026-06-26) — Check Link Chain doesn't distinguish "actually used" from
  "stale link-table entry."** Confirmed via code: `core.depscan.scan_recursive_steps`/`scan_file`
  reads each file's FULL library (LI) link table and recurses into everything unconditionally —
  it never checks whether any LIVE datablock placeholder in that file still references the linked
  library. Blender doesn't auto-clean stale LI entries (same disease F4 Orphans targets, one
  level up), so a vestigial library reference with zero real users can still surface as a
  `missing_link`/`error` on par with a real break. Fixed: `build_dep_report` now takes an
  injectable `linked_datablocks_fn` (defaults to the real `core.datablock_links.
  linked_datablocks`), caches one offline read per linking file, and downgrades a MISSING finding
  to a new `STALE_LINK` info-severity category ("stale, not actually used") when that file holds
  zero live placeholders for the stored path. An unreadable file (the lookup itself raises) does
  NOT get downgraded — fails safe to the real MISSING finding rather than hiding a possible break.
- **DONE @ v0.2.70 (2026-06-26) — Missing/Circular findings don't distinguish DIRECT vs INDIRECT
  libraries**
  (2026-06-26 screenshot: Outliner shows 9 libraries, Check Link Chain reports 15 missing —
  user correctly guessed the gap is "libraries of libraries" but it isn't labeled). `core.
  depscan.DepScan` tracks BFS visit order but not each file's DEPTH from the root. Fix: add a
  `depths: dict[str, int]` field, fill it during `scan_recursive_steps` (the depth is already
  in the BFS queue tuple, just never stored), then have `build_dep_report` label each
  Finding's linking file as "direct" or "indirect (N hops via <intermediate>)" — this is the
  SAME conceptual gap as the older, still-unfixed v0.2.27 item #8 (`ops/relink.py::_gather_libs`
  not marking direct/indirect for the LIVE "Find Broken Library Links" tool) — checked
  2026-06-26: it does NOT share this fix (see Group 1 item #5's resolution above — `_gather_libs`
  has no recursion/BFS to draw a `depths` field from at all; a live direct/indirect signal for it
  needs its own `user_map`-based design, not started).
- **DONE @ v0.2.71 (2026-06-26) — Circular reference findings aren't actionable.** Screenshot:
  "Circular library reference: PSM_Stage_v5.1 -> People1_v5.1 -> PSM_Stage_v5.1" expanded to 3
  child rows that were just the SAME file names again (`core.depscan.build_dep_report`'s
  `circular_link` Finding used `items=list(cycle)`, i.e. the file-node list — zero new information
  over the message text). User wanted the actual DATABLOCKS crossing each direction of the loop,
  so they can judge which direction to break. Fixed: `build_dependency_tree` gained an injectable
  `datablocks_from_library_fn` (defaults to the real `core.datablock_links.datablocks_from_
  library`); its `cat_node` now special-cases `circular_link` (`_circular_pair_nodes`) — for each
  consecutive pair in the cycle, one node per direction holding the real (kind, name) datablocks
  as click-to-select leaves (`core.datablock_links.kind_ref` maps the few friendly kind labels
  that don't match their real `bpy.types` class name — Node Group→NodeTree, Shape Key→Key,
  Particle→ParticleSettings — everything else already matches verbatim).
- **NOT BUILT — "Duplicate data-blocks (.NNN copies — wasted memory)" should group by TYPE,
  collapsed by default.** Today `core.datablock_graph.build_live_report` adds every
  `duplicate_family` Finding into ONE flat category (sorted by type label then base name, but
  not actually grouped — a Material family and an Action family sit side by side in the same
  flat list). User wants real type sub-groups (Material/Action/Object/...), each collapsed by
  default, matching the established house style (Missing/Duplicate Textures' material-grouped
  collapsible sections). `core.tree.report_to_tree` is generic (category -> finding -> items, 3
  levels) — this needs either a 4th level special-cased for `duplicate_family` (mirroring the
  circular-reference fix above) or restructuring into one synthetic category per type. Decide
  which approach when this is picked up.
- **RESOLVED @ v0.2.76 (2026-06-26) — f7live's "Duplicate data-blocks (.NNN copies — wasted
  memory)" overclaimed for types with no real fingerprint.** Real user report (2026-06-26
  screenshot): "Collection: awning ×8" lists `awning`/`awning.001`/`.002`/... as if confirmed
  duplicates, but the user found the underlying meshes already differ (`Mesh.059` vs `Mesh.060` —
  diverged after a cloth sim bake). `core.datablock_graph.duplicate_families` is and always was
  purely NAME-based (`.NNN`-suffix stripping, zero content check) for every type except Action and
  Shape Key. Earlier attempt at a fix (reword the category/message to hedge "unverified") was
  explicitly rejected by the user — "I don't think a name change is the right approach." **Final
  resolution, decided 2026-06-26 (Group 10 #38 discussion):** don't verify deeper here — REMOVE the
  `.NNN`-family detection from "Audit This File" (f7live) entirely. Reasoning the user gave: it's
  not just types lacking a fingerprint that are unreliable — Blender appends `.NNN` constantly for
  objects that legitimately diverge after linking, across nearly every type; Image is the one type
  where `.NNN` families are commonly REAL duplicates, and that's already covered by a dedicated
  content-hash-verified tool (Duplicate Textures). Every OTHER type is already covered, with the
  SAME name-only-but-typed/fingerprint-where-possible care this report lacked, by "Find Duplicate
  Data-blocks" (`core.datablock_dedup`/`ops/datablock_dup.py`, which already fingerprints Action +
  Shape Key and flags the rest "unverified" rather than blindly claiming duplicates). So f7live's
  version was strictly redundant AND less careful than the dedicated tool — deleted rather than
  fixed. Removed `wasted_copies()`, the `duplicates` field on `LiveExtract`, the `duplicate_family`
  Finding loop in `build_live_report`, the matching `_COLLECTIONS` walk in `analyze_overrides`, and
  the now-dead `_CATEGORY_TITLES["duplicate_family"]` entry; renamed the now-inaccurate "Overrides &
  Dups"/"Analyze Overrides & Duplicates" labels to "Overrides"/"Analyze Overrides". 2 tests removed
  (tested the deleted behavior), suite 398 green.
  **Candidate deeper direction (not agreed, for discussion):** offer a "verify mesh identity" hint
  per family by walking each member object's `.data` through the ALREADY-EXISTING
  `core.fingerprint.fingerprint_mesh` (F5's tool) — meaningful for Object families, fuzzier for
  Collection families (a collection's "content" is its whole subtree, not one mesh).

## Find Duplicates display unification + item #16 — DONE 2026-06-27 (v0.2.85-v0.2.88), the "other
## backlog" the Flatten v2 pause (below) asked for. NOT the same thread as Flatten v2 — that is
## still ON HOLD, untouched by this work.

**Item #14 (export filename) — DONE.** `ops/report_store.py::ASSETDOCTOR_OT_export_report` always
offered the same hardcoded `AssetDoctorReport.txt`. New `core.report.default_export_filename(label)`
(bpy-free, tested) + an `invoke()` override that resolves the active feature's label (or "Resource
Usage") and sets `self.filepath` before the file browser opens — e.g. exporting f6dup now offers
`AssetDoctor_Duplicate_Textures.txt`. The dead `filename` property (declared, never read) was removed.

**Item #16 — turned into a real redesign once investigated, per the user's "force the combination
of the Find Duplicates function" direction.** Original ask ("kept separate" rows should say WHY)
traced to two asymmetric code paths: the generic Data-blocks conflict text was already real but
imprecise (a family with BOTH a content split AND unverified members only ever reported the first
fact — fixed, `core/datablock_dedup.py::plan_merges`, now reports both when both apply); the Image
Content conflicts box was dead code, `_fill_families(context, plans, [])` always passed an empty
list, so it could never show anything regardless of wording. Materials and Geometry had NO conflict
concept at all — silently dropped any name-alike-but-content-differs pair with zero feedback.

**Root design decision (confirmed with the user): the trigger-level merge done 2026-06-25 ("Find
Duplicates" running all 4 scans from one button) was never meant to unify the 4 detection
ALGORITHMS — each verifies "identical" differently (node-tree hash / mesh hash / dims+pixel hash /
generic content hash) for a real reason and stays separate. What WAS missing: the DISPLAY layer and
the "kept separate" reporting, which have no reason to differ by type.** Built:
- `core/datablock_dedup.py::plan_merges`'s name-family + fingerprint-conflict algorithm (already
  type-agnostic — just `(name, fingerprint, users)`) is now reused as a shared, INFORMATIONAL-ONLY
  layer for Materials (`ops/material_dedup.py::_populate_material_conflicts`) and Geometry
  (`ops/instance_dedup.py::_populate_geo_conflicts`) — new `assetdoctor_mat_conflicts(_text)` /
  `assetdoctor_geo_conflicts(_text)` WM props, reset on Merge/Instance Selected. Never changes what
  gets merged — content fingerprint alone still gates every actual apply.
- New `core/imagededup.py::find_image_conflicts` — same name-family algorithm, but with the
  image-specific split the original TODO item literally asked for: same family, fingerprint differs
  → check whether the DIMS portion differs ("different dimensions — likely a resolution variant")
  or only the trailing hash does ("same dimensions, different content — worth a closer look").
  Wired into `ops/image_dedup.py::scan_content_dups` (previously hardcoded `[]`). Deliberately does
  NOT revive the name-based ".NNN family" scan removed 2026-06-24 — this is read-only/informational,
  never a merge trigger; content identity alone still gates `plan_content_merges`.
- `ui/panels.py`: the 4 standalone boxes (`_draw_datablock_dups`/`_draw_material_dups`/
  `_draw_geo_dups`/`_draw_duplicate_textures`) plus the separate floating 4-line
  `_draw_duplicates_summary` headline block are gone, replaced by one `_draw_duplicates()` — a
  single outer box, each type as a section with its own consistent `"<Type> — ..."` headline
  (✓ none found / counts / "N kept separate"), its own existing actionable rows (keeper dropdowns
  where they already existed, untouched), and a new shared `_draw_kept_separate()` helper for the
  "kept separate" sub-list (reuses the existing generic `assetdoctor.toggle_inline_detail` /
  `assetdoctor_detail_expanded` mechanism already used elsewhere in this panel, instead of inventing
  a 5th per-feature toggle operator). Also fixes two known small bugs in this exact area for free:
  the stale "Materials/Meshes/Images have their own dedup tools" info note (always drawn, now
  removed — the new per-type headers already make the distinction obvious) and
  `_draw_duplicate_textures` creating its box unconditionally before checking `scanned` (now an
  early return like every other section).

**Tests:** `core/datablock_dedup.py` +1 pytest (combined differing-content+unverified case);
`core/imagededup.py` +5 pytest (`find_image_conflicts`: clean families ignored, dims-differ,
same-dims-different-hash, unverified, dims+unverified combined). New
`tests/smoke_image_dedup.py` (no prior coverage existed for `scan_content_dups` at all — covers
the real operator, packed synthetic images, both the merge path and both conflict-reason branches).
Extended `tests/smoke_f3.py` and `tests/smoke_instance.py` with a differing-content name-family
case each. All three run clean against Blender 5.1.2; full pytest suite green throughout.
**NEEDS the user's live-Blender confirm** — the panel restructuring (`_draw_duplicates`) can't be
exercised headlessly; check the combined results area reads sensibly on a real file with material/
geometry/image conflicts present (only Data-blocks conflicts have been seen live so far, per the
v0.2.86 screenshot that prompted this whole investigation).

**Live-confirmed 2026-06-27 (v0.2.88) — works.** One follow-up UI polish, EXPLICITLY DEFERRED by
the user to next time this area of the UI is touched (not now): each `_draw_kept_separate` member
line is currently one long flat string (`"{base} — {reason} ({', '.join(members)})"`), e.g. `"Node
Group: cc3iid_3_point_dist — 2 unverified (no fingerprint available) — not merged
(cc3iid_3_point_dist, cc3iid_3_point_dist.001)"` — too long. Wanted: the base name as its own row,
the reason text indented on its own row below that, then each member name indented on its own row
below that (3-4 rows per conflict instead of 1). Touches `_draw_kept_separate` (`ui/panels.py`) —
the `conflict_lines` strings would need to become structured data (base/reason/members) instead of
pre-joined text, since all 4 callers currently build the flat string themselves
(`ops/material_dedup.py`, `ops/instance_dedup.py`, `ops/image_dedup.py`'s `_fill_families`,
`ops/datablock_dup.py::_populate_datablock_families`).

## Resource Usage real columns — DONE 2026-06-27 (v0.2.89), item #15. Same "other backlog" thread
## as the Find Duplicates digest above — Flatten v2 (below) is still untouched/ON HOLD.

The Resource Usage list shared `ASSETDOCTOR_UL_tree` with the Report panel's tree, which only ever
drew one combined right-aligned `detail` string per row (`"12.3 MB RAM · 4.5 MB VRAM · 0 B disk ·
3u"`) — hence the repeated unit names on every row, and no way to align values under a header
since it was never more than one text blob. **User wanted real columns, confirmed worth the extra
files it touches (vs. a cheaper non-aligned label-only fix).**

Built: `core/tree.py`'s `TreeNode`/`Row` gained 3 new optional fields (`ram`/`vram`/`disk`, empty
string for every non-Resource tree — Report rows keep using `detail` exactly as before, verified by
the full pytest suite + `tests/smoke_report.py` staying green throughout). `core/resource_tree.py::
build_resource_tree` now fills those 3 fields with pre-formatted `human_bytes` text per row instead
of one joined string, and gained a `sort_by: "ram"|"vram"|"disk"` parameter that reorders the
TOP-LEVEL type groups only (each group's own children stay RAM-sorted — sorting individual
datablocks wasn't asked for and adds little value while a group is collapsed, which it is by
default). `ui/panels.py`: a new shared `_resource_columns()` helper (3 fixed-width
`ui_units_x`-sized sub-layouts) used by BOTH a new clickable column-header row (RAM/VRAM/Disk
buttons, the active one shown depressed) and `ASSETDOCTOR_UL_tree.draw_item`'s new branch (draws 3
real columns when `item.ram/vram/disk` are set, falls back to the old single-`detail` column
otherwise — so the Report tree's rendering is provably unchanged). New `ops/resource.py::
ASSETDOCTOR_OT_resource_sort_by`: clicking a header re-sorts CHEAPLY — the last scan's raw
per-datablock `items` are now cached as JSON (`assetdoctor_resource_items_json`) specifically so a
re-sort never re-walks `bpy.data` (the actually expensive part); the chosen sort persists
(`assetdoctor_resource_sort`) across re-scans too.

**Known, inherent limitation (not a bug, can't be fully solved):** the header row is drawn OUTSIDE
`template_list`, which has no API for a header that's actually part of the list widget — so columns
align cleanly until the list overflows its visible `rows=8` and Blender adds its own internal
scrollbar, at which point the last column drifts slightly relative to the (unaware) external
header. Accepted as the realistic ceiling for this UI toolkit; flagged to the user, not silently
shipped as if it were pixel-perfect.

**Tests:** `core/resource_tree.py`/`core/tree.py` — `tests/test_resource_tree.py` updated (label
now carries the `(Nu)` user-count suffix instead of `detail`, new tests for `sort_by="vram"`
reordering type groups, unknown `sort_by` falling back to "ram", disk column empty when zero) +
`tests/test_tree.py`/`test_report.py` unaffected (ran to confirm). `tests/smoke_resource.py`
extended: real RAM column present instead of a `detail` substring check, items get cached, a real
`resource_sort_by("EXEC_DEFAULT", metric="VRAM")` call re-sorts without losing any type node.
`smoke_register`/`smoke_report`/`smoke_analyze_all` re-run clean (shared-UIList regression risk
areas). All pytest + 5 relevant smoke tests green against Blender 5.1.2.
**Live-confirmed 2026-06-27 (v0.2.89) — works.** Columns aligned, Disk sort showed depressed/active,
user-count suffixes correct, "0 B" disk on the unsaved test file as expected.

## Geometry now clusters local+linked (item #21) — DONE 2026-06-27 (v0.2.90). Same "other backlog"
## thread as the two digests above — Flatten v2 (below) is still untouched/ON HOLD.

Investigating the literal ask ("keep-local vs keep-linked preference, separate for materials and
meshes") surfaced a real asymmetry: **Materials already mix local+linked in one duplicate cluster**
(`core/f3_materials.py`, no local-only filter) with a hardcoded "local wins" tie-break — a
preference there really is just a tie-break flip. **Geometry was structurally different**:
`core/geometry_dedup.py::build_instance_plan` explicitly filtered `if ... and not it["linked"]`
before clustering, so a linked mesh was never even a CANDIDATE — `choose_canonical`'s local-vs-
linked tie-break existed but was dead code in practice (nothing linked ever reached it). **User's
call when asked: do both** — relax Geometry's filter too, not just add an inert preference.

Built: `core/geometry_dedup.py::build_instance_plan` no longer excludes linked meshes from
clustering — a local mesh's users can now be repointed onto an already-linked-in identical mesh
(real footprint reduction), or vice versa. The linked datablock itself is never touched/removed
either way (only local IDs can be) — `removable_count`/the report message/the UI headline all now
track `linked_victims` separately from real removable victims, mirroring `core/f3_materials.py`'s
existing local/linked accounting exactly (new `assetdoctor_geo_linked` WM prop, parallel to
`assetdoctor_mat_linked`). Both `choose_canonical()`s gained a `prefer_linked: bool` parameter
(tie-break only — whitelist/blacklist still take precedence for Materials, unchanged). New
`AssetDoctorPreferences.material_keep_preference`/`geometry_keep_preference` enums (LOCAL/LINKED,
default LOCAL = today's behavior unchanged unless the user opts in), wired into
`ops/material_dedup.py`/`ops/instance_dedup.py::run_steps`.

**Tests:** `tests/test_f3_materials.py`/`test_geometry_dedup.py` +6 pytest (prefer_linked flips the
tie-break for both; whitelist still beats it; Geometry's old `test_linked_excluded` rewritten to
`test_local_and_linked_cluster_but_linked_never_removed` since that's no longer the real behavior).
New `tests/smoke_geo_linked.py` — a REAL linked mesh via `bpy.data.libraries.load(link=True)` (not
just synthetic dicts), confirming end-to-end through the actual registered operator: local+linked
cluster, the linked user gets repointed onto the local canonical, the linked datablock is never
removed/delocalized. **Could NOT smoke-test the LINKED preference itself** — every smoke test in
this project calls `register()` manually, which never populates
`bpy.context.preferences.addons[pkg]` (confirmed empirically: `tests/smoke_idle_scan.py` actually
FAILS on exactly this — `KeyError: 'AssetDoctor' not found` — a PRE-EXISTING, unrelated bug noticed
while investigating, not introduced this session, not yet fixed; flagged for the user, see
[[env-blender-verification]]). `ops.get_prefs()` always returns `None` in this harness, so
`prefer_linked` always resolves to the LOCAL default regardless — the actual flip is covered at the
core layer instead (prefs-free, the right layer for it anyway). All pytest + 4 relevant smoke tests
(`smoke_f3`/`smoke_instance`/`smoke_geo_linked`/`smoke_register`) green against Blender 5.1.2.
**NEEDS the user's live-Blender confirm** — the new Preferences dropdowns + real behavior on a file
that actually mixes local/linked materials or meshes.

## Make Local: 3 findings (items #17/18/19) — DONE 2026-06-27 (v0.2.91). Same "other backlog" thread
## as the three digests above — Flatten v2 (below) is still untouched/ON HOLD.

Per the original note's own "status uncertain, confirm against current code first" instruction —
all three turned out differently than recorded.

**#17 (hidden/excluded collections) — NOT A BUG.** Probed empirically (real linked objects via
`bpy.data.libraries.load(link=True)`, one selected, one not, one in a collection EXCLUDED from the
view layer): `bpy.ops.object.make_local(type='ALL')` localized all three regardless. Re-tested with
ZERO objects selected and no active object — still localized everything. Conclusion: `type='ALL'`
is a distinct, FILE-WIDE mode (unlike the `'SELECT_OBJECT'`/`'SELECT_OBDATA'`/
`'SELECT_OBDATA_MATERIAL'` options, which genuinely are selection-scoped) — it was never
selection/visibility-dependent, and the per-ID fallback pass (`_remaining_linked()`, walks raw
`bpy.data` directly) is independently immune to this too. The recorded "lead" (temporarily reveal
collections) was based on a mistaken assumption about how `type='ALL'` works; no code changed.

**#18 (progress bar invisible) — confirmed and fixed, exactly as recorded.** Reading
`ops/make_local.py::ASSETDOCTOR_OT_make_local.invoke()` confirmed `_prepare()` (gathers every
linked datablock) and `_setup_apply()` (for IN_PLACE: writes the full pre-mutation backup — can be
minutes on a huge file) ran synchronously before `RUNNING_MODAL` was ever returned, so the
progress bar/timer didn't exist yet during that window. Fixed: both now run as the first steps of
a new `_apply_steps()` generator that IS the modal's `_gen` from the start — `invoke()` just starts
the timer/modal_handler immediately, with status text ("Scanning linked data…", "Backing up…")
updating before `localize_steps()`'s own granular per-chunk progress takes over. Early-exit cases
(nothing linked; `_setup_apply` returns an error, e.g. unsaved file in NEW_FILE mode) are now
discovered mid-modal via a new `self._aborted` flag instead of short-circuiting before the modal
starts, and `modal()` reports/finishes correctly either way. `execute()` (EXEC_DEFAULT/scripting/
tests) is unchanged — it was already fully synchronous by design, never needed this.

**#19 (shared-library guard) — built narrower and more precise than the literal ask, per the
user's explicit choice ("detect actual collision risk," not a blanket "this file is shared"
warning).** Working through the actual mechanics: In-Place Make Local doesn't rename/break what
another file links FROM this one in general — Blender resolves a link by name at load time
regardless of whether the target became local via Make Local or was always local. The REAL risk is
narrower: Blender enforces datablock name uniqueness only WITHIN one library (local counts as its
own), so two items can share a bare name today purely because they're in different libraries; once
Make Local converts everything to local, every name after the first gets a `.001`-style
auto-suffix — and THAT can silently break a same-named link from another file. Built
`core/f2_makelocal.py::find_rename_collisions(all_names)` (bpy-free, groups by (type, name) across
ALL existing datablocks — local included — flagging any name held by 2+ sources) + a new
`ops/make_local.py::_gather_all_names()` (existing `_gather_linked()` only covered linked items,
not local ones, which the collision check also needs). Surfaced as a new `rename_risk` Finding in
the F2 report (visible on every dry-run, before the user ever clicks Apply — report-first, this
project's standing safety pattern) AND restated in the final apply-message
(`self._n_collisions`, computed pre-mutation in `_prepare()`) since that's the moment a downstream
break would actually matter. Deliberately did NOT add a blocking confirmation dialog — no
precedent for that pattern anywhere in this codebase; the auto-backup remains the established
safety net for every mutating op here (see `[[feedback-modal-undo]]`). Deliberately did NOT cross-
reference this with the existing "Safe to Delete?" (f7rev) reverse-dependency graph — that needs a
folder-wide scan as a prerequisite and knowing exactly which names each dependent file imports,
which would mean re-scanning every dependent file too; scoped out as a separate, bigger follow-up
rather than conflated with this fix.

**Tests:** `core/f2_makelocal.py` +6 pytest (`find_rename_collisions`: unique names ignored,
local+linked collision, two-different-libraries collision, different types with the same name
don't collide; `build_makelocal_report` wires collisions through) + 2 existing tests updated for
the new `"collisions"` summary-data key. `tests/smoke_f2.py` extended: a real local object sharing
a name with a linked one, dry-run, confirms the F2 report names it
(`"Object/Tree — shared by 2 sources (//libA.blend, local); Make Local will rename all but one"`).
All pytest + smoke_f2/smoke_register green against Blender 5.1.2.
**Side finding, unrelated to this work, flagged not fixed:** `tests/smoke_idle_scan.py` is
currently BROKEN (`KeyError: 'AssetDoctor' not found` — manually calling `register()`, the pattern
every smoke test in this project uses, never populates `bpy.context.preferences.addons[pkg]`; that
test indexes it directly instead of using `.get()`). Noticed while investigating why
`ops.get_prefs()` returns `None` in this harness (relevant to item #21's digest above too) — not
this session's regression, not yet fixed.
**NEEDS the user's live-Blender confirm** — #18's progressive modal timing and #19's report/
apply-message wording are both interactive-only, can't be verified headless.

## Examine Library folder-wide search (item #20) — DONE 2026-06-27 (v0.2.92). Last item on the
## reprioritized Quick Fixes (Groups 5-7) list — same "other backlog" thread as the four digests
## above. Flatten v2 (below) is still untouched/ON HOLD.

The existing "Pick a Specific Item" button already let the user pick ONE .blend and see ranked
name candidates within it — but required already knowing which file in a folder held a
replacement. New **"Search a Folder"** button right next to it: walks every `.blend` under a
chosen folder (`core.blendscan.iter_blend_files`, the same folder-walk Map a Folder already uses),
peeks each one's matching collection, and picks the single best match across the whole folder.

Built: `core/reconnect.py::find_best_file_match(wanted, names_by_file)` (bpy-free) — an exact/
numbered match in ANY file wins outright over a fuzzy one in another (never settle for a guess
when a clean match exists elsewhere); ties keep whichever file was checked first (the folder
walk's own alphabetical order is the deterministic tiebreak). `ops/examine_library.py`: factored
the existing single-file peek (`with bpy.data.libraries.load(path, link=True) as ...`) out of
`ASSETDOCTOR_OT_examine_pick_source` into a shared `_peek_names(path, attr)` (no behavior change,
just de-duplicated — both operators need the identical peek-without-loading pattern) + new
`ASSETDOCTOR_OT_examine_search_folder`. Sets the SAME `row.source_blend`/`row.candidates` fields
the single-file picker already sets, so the existing dropdown/Apply Selected logic needed zero
changes.

**Safety carry-over from a DIFFERENT, already-documented crash class:** `ops/datablock_reconnect.
py::_populate_missing_blocks`'s docstring records a real, uncatchable
`EXCEPTION_ACCESS_VIOLATION` from re-peeking a library the session had just REALLY linked from
moments earlier. A folder-wide walk would otherwise peek exactly that kind of file constantly (the
examined library itself, or any other already-loaded one sitting in the same folder) — the new
operator builds the set of already-loaded library paths up front and skips any matching file
entirely, both for safety and because such a file's names are already in the in-memory pool
`_populate_examine_rows` checks first anyway (searching it again would be redundant even if it
were safe).

**Tests:** `core/reconnect.py` +5 pytest (`find_best_file_match`: exact beats fuzzy in another
file, first-file-wins on a same-confidence tie, falls back to fuzzy when nothing better exists,
nothing-qualifies and empty-input cases). New `tests/smoke_examine_folder_search.py` — 3 real
.blend files in a temp folder (one fuzzy-named decoy, one exact match, one that's also already
linked into the session with an identical exact-match name) plus a real Examine Library scan via
the actual registered operators; confirms the exact match wins over both the fuzzy file AND the
already-loaded one (which sits alphabetically earlier and ties on confidence — would have won the
tiebreak if the skip-logic weren't working), and that an empty folder cleanly CANCELs.
**Side finding, unrelated to this work, flagged not fixed:** `tests/smoke_examine_library.py`
(pre-existing, untouched by this session) is currently BROKEN — confirmed via `git stash` that it
fails identically with none of this session's changes applied. Root cause not investigated (out of
scope here); likely related to the orphan/zero-real-user test materials it creates before saving —
not the same root cause as the `smoke_idle_scan.py` finding noted in item #19's digest, just
another pre-existing gap noticed along the way.
**NEEDS the user's live-Blender confirm** — the new button's placement/icon and real-world folder
search timing (peeking many real files can be slow) are best judged interactively.

## Flatten v2 — paused mid live-test, items 10-13 still open (historical detail below)

**STATUS: COMMITTED @ v0.2.92 (`03a3248`, 2026-06-27) along with the same session's Quick Fixes
batch — the user explicitly accepted shipping it in this state ("doesn't work as desired, but is
better than it has been... don't need to keep anything in Flatten V1"). Still has the same open
gaps recorded below (items 10-13); not a "do not touch" hold anymore, just not the next priority —
the user's own next-session pick is Group 3 leftovers (see the top of this file).**

**Resume checklist, in priority order, when this DOES get picked back up again:**
1. User was about to try making the People collections local (Blender's native Make Local, native
   = no auto-backup, a copy of the file first was recommended) specifically to route around item
   11's cross-file-template problem — check whether they did this and what Find Flattenable Links
   found afterward before doing anything else.
2. Item 11 (cross-file bare-link rig resolution) is the biggest real open gap — only fix it if the
   Make Local route above didn't already make it moot for this file.
3. Item 10/the drill-down-arrow bug is still NOT root-caused — last data point was that it
   reproduces in a SECOND, unrelated code path (Audit This File's generic tree, not just the
   Flatten picker), shifting suspicion toward general redraw/memory-pressure rather than a bug in
   this session's new code. Get the System Console traceback check and the resource-pressure check
   (item 13's cross-cutting note) before touching code again.
4. Item 12 (debug log) needs a fresh Evaluate/Flatten Selected run on a failing group (toggle is
   confirmed on, but the log was stale at last check) to actually capture the real
   `override_create()` RuntimeError text.
5. Items 5/6/13 are pure documentation (stale info note + an empty-box UI bug elsewhere, the Audit
   This File feedback) — small, safe, no dependencies on 1-4 above; fine to batch into a cleanup
   pass whenever convenient, including the "other backlog" the user mentioned wanting to clean up
   next session.

**SESSION DIGEST — 2026-06-27, v0.2.87 (uncommitted) — live-test of "Find Flattenable Links"
against a real collection-with-multiple-characters file (`PSM_Stage_v5.1.blend` /
`ThePiazzaSanMarco - People1_v5.1.blend`), across multiple real-Blender test rounds. Items 1-4
found/agreed in round 1, then BUILT (item 2's census redesign + item 4's decisions). Round 2 (a
real run against the actual file) surfaced items 5-6 (UI polish, documented not fixed), item 7 (a
real root cause for "most characters missing" — found AND fixed), item 8 (two more UI fixes), item
9 (two things investigated and confirmed NOT bugs), and item 10 (two things still open, need more
repro info before guessing further). Round 3 found item 11 (the type-detection fix only partially
worked — a deeper cross-file template-resolution gap remains, not yet built), item 12 (the debug
log is stale, no new info yet), and item 13 (new Audit This File feedback, explicitly held).
Session paused here at the user's request — see the STATUS/resume checklist above this digest.**

1. **BUG, low priority, not yet fixed: progress bar shows "Starting…" for the entire ~5.5-minute
   scan**, never updating to per-file status even though `ASSETDOCTOR_OT_scan_link_chains`
   (`ops/linkchain.py`) yields per-file progress throughout. **Root cause:** the combined "Find
   Flattenable Links" button (`ASSETDOCTOR_OT_find_flattenable_links`, `ops/analyze_all.py:117`)
   is a `_AnalyzeSequencerMixin` that runs each of its 2 sub-steps via ONE synchronous
   `bpy.ops.assetdoctor.<step>()` call (`ops/analyze_all.py::_call`) — with no execution-context
   override this invokes the sub-operator's plain `execute()` (`ModalProgressMixin.execute`,
   `ops/progress.py:85-88`), which drains that sub-operator's WHOLE `run_steps()` generator in one
   tight loop, never touching the shared WM progress props per sub-step. The outer sequencer's own
   modal tick (`ModalProgressMixin.modal`, `ops/progress.py:104-148`) compounds it: its time-budget
   loop calls `next(self._gen)` repeatedly until `_PROGRESS_BUDGET` (default 0.04s) elapses: the
   FIRST yield (`"Running Find Flattenable Link Chains…"`) returns almost instantly, so the loop
   immediately calls `next()` again — which now blocks for the entire sub-scan — and only exits
   (calling `set_progress()` for the first time) once that blocking call finally returns. Net
   effect: the "Running…" status is computed but never painted before the multi-minute block
   begins, so the panel keeps showing whatever `invoke()` last painted ("Starting…") until the
   whole step finishes. **Same mechanism likely affects "Analyze All" and "Find Duplicates"**
   (same `_AnalyzeSequencerMixin`) for any sub-step slow enough to notice — not confirmed live, but
   the code path is identical. **Fix (not yet built):** have the sequencer interleave each
   sub-step's own `run_steps()` generator into its own loop instead of calling it via `bpy.ops`, or
   otherwise pass progress through from sub-step to outer sequencer.

2. **Items 2-6 (remote-group ordering, the FILE_TEXT "Build Flatten Plan" icon being a dead end on
   all-remote groups, and the stale "Run Find Flattenable Link Chains" message) all trace back to
   ONE root design gap, found discussing them with the user: the picker's remote-candidate path
   has no hierarchy data at all.** `ASSETDOCTOR_OT_scan_flatten_candidates` only ever surfaces a
   remote row from `chain_report` findings already filtered to `category == "posing_override"`
   (`ops/linkchain.py:268-286`) — and `build_chain_report` (`core/linkchain.py:355-382`) only emits
   a `Finding` for objects classified `OVERRIDE_WITH_TRANSFORM`/`MODIFIER_DRIVEN` in the first
   place; anything `UNCLASSIFIED` (a plain mesh child with no override, **or an Armature whose own
   object-transform is untouched because it's posed via bones, not the object's own loc/rot/
   scale** — the common case) never survives into the stashed report at all. Remote rows are then
   grouped only by source FILE (`row.rig = f"Remote: {_display_file_name(source_file)}"`,
   `ops/linkchain.py:279`), never by rig — `_resolve_rig`'s parent/modifier walk only ever runs
   against LIVE `bpy.data.objects`, and `ObjectPosingInfo` (the offline census record) never reads
   `parent`/modifier-target/object-type at all. The FILE_TEXT preview button only has cached plans
   for LOCAL objects (built during the live scan), so it's a guaranteed no-op on an all-remote
   group — which is what made it look like "nothing happened" and produced the stale
   pre-merge-button-name message as its only (misleading) output.
   **User's real need (this session, testing a file with zero local overrides — everything is
   remote): see ALL objects in the donor file's hierarchy, not just override-with-transform ones,
   so Armatures can roll up everything attached to them (true parent, Armature-deform modifier, OR
   anything else that attaches to a bone) and the rest group sensibly.**
   **Plan agreed: widen the existing offline per-file BAT census (the one pass already paid for
   during "Find Flattenable Links") instead of a new harvest/subprocess** — add object-type (via
   the data-block-name 2-char-prefix trick, reusing the already-proven `_PREFIX_KINDS` map),
   `parent` name, and Armature/Hook-modifier target+subtarget to `ObjectPosingInfo`, and stop
   dropping `UNCLASSIFIED` objects before the report is stashed (cache the full per-file object
   census separately, the same way `flatten_plan_to_dict` already round-trips structured data,
   rather than forcing it through the prose-oriented Report/Finding model). Then build an offline
   equivalent of `_resolve_rig` over that per-file map.
   **User pushed back, correctly: "are you determining that by checking for modifiers?"** — raised
   that parenting + Armature modifiers don't cover every way an object attaches to a rig (props/
   accessories are commonly attached via a BONE CONSTRAINT or a Hook modifier, with no parent
   relationship and no Armature-deform modifier at all). Confirmed via a real headless probe
   (synthetic fixture covering all 4 mechanisms + a live-RNA-vs-BAT cross-check, since Blender
   closed for the session — see `[[env-blender-verification]]`'s diagnostic-probe pattern) that
   **all of these ARE readable from the same offline BAT pass**, with two real path subtleties
   worth recording before this gets built (verified 2026-06-27, synthetic fixture, Blender 5.1):
   - **Modifier blocks are concretely typed per modifier** (block's own `dna_type.dna_type_id` is
     e.g. `b"ArmatureModifierData"`/`b"HookModifierData"`, not generic `ModifierData`) — `object`/
     `subtarget` are DIRECT top-level fields on the concrete struct, but `type` is NOT (it lives on
     the embedded base `ModifierData modifier;` substruct all modifier structs start with) — read
     it via the nested path `(b"modifier", b"type")`, same embedded-substruct pattern as `(b"id",
     b"override_library")`. Confirmed values match live `bpy.types.Modifier.bl_rna.properties
     ["type"].enum_items[...].value` exactly: `ARMATURE=8`, `HOOK=9` (read from live RNA, not
     hardcoded — don't hardcode these elsewhere either, re-derive the same way if needed again).
   - **`bConstraint.type` IS a direct top-level field** (`CHILD_OF=1`, also confirmed against live
     RNA) but the target is NOT on `bConstraint` itself — `data` is a `void*` to a type-specific
     struct (e.g. `bChildOfConstraint`), and BAT's block header already records the CONCRETE
     struct for whatever got allocated there (no explicit `refine_type()` call needed — confirmed
     the dereferenced block already reports `dna_type.dna_type_id == b"bChildOfConstraint"`). Read
     it as **two separate sequential `get_pointer`/`get` calls** — `data_block =
     con.get_pointer((b"data",))` then `data_block.get_pointer((b"tar",))` /
     `data_block.get((b"subtarget",), as_str=True)` — never one combined path tuple, same lesson
     as the override-reference 2-hop case (`core/linkchain.py`'s module docstring). Other
     target+subtarget constraint types (Copy Location/Rotation/Transforms, Damped Track, Track
     To, …) follow the identical two-hop mechanism, just with their own struct name in place of
     `bChildOfConstraint` — not individually re-verified yet, only `CHILD_OF` was probed.
   **BUILT (v0.2.85).** `ObjectPosingInfo` gained `obj_kind`/`parent_name`/`attach_target`/
   `attach_subtarget`; `read_object_posing` reads all four unconditionally (`core/linkchain.py`).
   New pure functions: `read_attach_target` (the modifier/constraint walk above),
   `build_offline_rig_index` (the offline `_resolve_rig` equivalent — keyed by `(source_file,
   name)`, NOT bare name, since object names are only unique WITHIN one .blend and two unrelated
   donor files can easily both have e.g. a "Rig"), `posing_list_to_dict`/`from_dict` (cache
   round-trip). `ASSETDOCTOR_OT_scan_link_chains.run_steps` now also caches the full `posing` list
   as JSON (`wm.assetdoctor_flatten_hierarchy_json`) — previously computed, then discarded once
   the generator returned. The live `ops.linkchain._resolve_rig` got the same Hook-modifier/
   Child-Of-constraint checks added for parity with the offline walk.

3. **RESOLVED — "local override" confusion, raised by the user multiple times this session; this
   is the permanent answer, don't re-litigate it.** "Local" is used for TWO different things in
   this codebase and they got conflated in conversation:
   - **Local vs. remote CANDIDATE** (`row.is_remote` in the picker): does the override-with-changes
     live in the file currently open in the session (local), or in some OTHER file only reached by
     following the link chain (remote)? **This was never local-only** — the offline census was
     already extended (2026-06-25) to walk every file the scan visits, specifically because real
     production root files (e.g. `PSM_Stage_v5.1.blend`) have ZERO local overrides of their own;
     every actual character lives several hops deep. Remote detection is the whole reason the
     "Remote: …" groups in the user's screenshot exist at all.
   - **Local-only CACHE** (`wm.assetdoctor_flatten_plans_json`, built in
     `ASSETDOCTOR_OT_scan_flatten_candidates`): the FILE_TEXT "Build Flatten Plan (preview)" button
     only has pre-built plan data for objects read live from `bpy.data.objects` during the scan —
     remote objects never get an entry, since building their plan needs to open the donor file
     (harvest), which today only happens inside "Flatten Selected." **This is the real, narrow gap**
     — not a fundamental local-only limitation, just a preview button with no remote-aware path.
     **Decision: remove this button** (see item 4 below) rather than fix it in place.
   Separately, the OTHER reason real characters could go missing even from the remote census: the
   offline classifier only ever flagged `OVERRIDE_WITH_TRANSFORM` (object-level loc/rot/scale
   differs from identity) as worth keeping — a character posed entirely via BONES, with its
   Armature's own object-transform untouched, was silently dropped as `UNCLASSIFIED` before the
   report was even stashed (see item 2 above). The widened census (item 2) fixes this by keeping
   every local object regardless of classification, not just the ones that already passed the old
   transform gate.

4. **Design decisions agreed this session, to land together with item 2's census widening:**
   - **Filter out direct-linked overrides from the candidate list entirely, don't show them as
     "blocked."** User's framing: if an override's reference is reachable from the root ONLY
     directly (no multi-hop route exists to that target at all), flattening it is a no-op — it's
     already linked from exactly where flattening would re-link it. `build_flatten_plan` already
     detects this case (`"linked directly, no multi-hop chain to flatten — nothing to collapse"`)
     but currently surfaces it as a blocked row anyway; switch this to an exclusion filter at
     candidate-build time instead of a per-row warning.
   - **Selection granularity: per-character/rig, not per-donor-file.** Today an all-remote group is
     keyed by source file (`"Remote: ThePiazzaSanMarco - People1_v5.1"`), so its single checkbox
     selects/deselects ALL ~762 characters in that file together — the user needs to pick Character
     A without Character B. Falls out of item 2's redesign for free once remote rows group by
     resolved rig instead of source file — **plus a new outer "select all" toggle at the donor-file
     level**, above its per-character groups (a small nesting change to `_draw_flatten_candidates`:
     today's group list is flat, this needs one more level — file → character — not built yet).
   - **Remove the FILE_TEXT "Build Flatten Plan (preview)" icon entirely** (`ops/linkchain.py:1150`
     in `_draw_flatten_candidates`, operator `ASSETDOCTOR_OT_build_flatten_plan`) — confirmed
     useless for the user's actual files (item 3 above).
   - **Add a new "Evaluate Selected" button**, next to "Flatten Selected" on the outer
     "Flattenable overrides" row: harvests whatever's CHECKED (same harvest mechanism
     `_harvest_remote`/`remote_harvest.py` already built for Flatten Selected — opens each donor
     file once in a disposable background process), builds each one's `FlattenPlan`, and updates
     `ready`/`status` on every row + stashes the f7flatten report — **but does not apply anything**.
     Gives the user a real preview-after-harvest checkpoint before committing, which doesn't exist
     today (today harvest+apply are fused into one click). Open question for whoever builds this:
     should "Flatten Selected" skip re-harvesting anything "Evaluate Selected" already harvested in
     the same session, or always harvest fresh? **Resolved while building:** yes — both operators
     now go through one shared generator (`ops.linkchain._harvest_and_build_plans`), and a member
     already present in the cached-plans dict (whether cached by the original LOCAL scan or by an
     earlier Evaluate Selected run) is reused as-is, never re-harvested.
   **BUILT (v0.2.85).** `core.linkchain.is_direct_link_only` (the exclusion-filter predicate,
   +4 tests) is applied in BOTH the local and remote loops of `scan_flatten_candidates`. Remote
   candidates are now sourced directly from the `assetdoctor_flatten_hierarchy_json` cache (every
   local object regardless of override-with-transform classification) instead of the
   already-filtered `posing_override` findings, grouped via `build_offline_rig_index` into
   `row.group_parent` ("Remote: <file>") + `row.rig` ("<file> :: <character>", kept globally
   unique by the file prefix so two donor files with a same-named "Rig" never merge). UI
   (`ui/panels.py::_draw_flatten_candidates`, factored into a new `_draw_rig_group` helper reused
   at both nesting levels) draws a two-level tree: each donor file is its own collapsible header
   with a "select all in this library" toggle (new operator
   `assetdoctor.flatten_group_select_all`), and each character underneath gets its own independent
   checkbox. The FILE_TEXT "Build Flatten Plan (preview)" button/operator
   (`ASSETDOCTOR_OT_build_flatten_plan`) is REMOVED entirely, along with the now-dead
   `_flatten_rig` it was the only caller of (superseded by `_flatten_member`, which already covers
   everything it did plus more — see the module comment in `ops/linkchain.py`). New
   `assetdoctor.evaluate_selected` operator (bl_label "Evaluate Selected") harvests + builds a real
   plan for whatever's checked, local or remote, updates each row's ready/status, stashes the
   f7flatten preview report, and caches every newly-built plan — applies nothing.
   **Verified:** full pytest suite (470, was 401 — `core/linkchain.py` pure-logic additions all
   covered) + `tests/smoke_register.py`, `smoke_flatten_links.py`, `smoke_analyze_all.py`,
   `smoke_remote_harvest.py`, `smoke_flatten_selected.py` (covers the LOCAL apply path through the
   refactored shared harvest/plan helper) all still pass. Two NEW smoke tests added this session:
   `smoke_flatten_hierarchy.py` (crafts a 2-character-one-donor-file census + a bone-only-posed
   Armature with identity object-transform — directly proves both the original bug reports: the
   Armature now survives as a candidate, and the two characters land in separate, independently
   selectable groups under one outer donor-file header) and `smoke_evaluate_selected.py` (confirms
   Evaluate Selected builds a ready plan and caches it WITHOUT creating/hiding/mutating any
   object). **NEEDS A LIVE-BLENDER CONFIRM** against the user's real multi-character collection
   file before this is considered done — none of the above touches a real multi-GB production
   file or the actual N-panel UI interactively.

5. **Stale info note, flagged by the user (2026-06-27), NOT fixed yet (explicitly told to just
   document it).** `_draw_datablock_dups` (`ui/panels.py:1626-1627`) unconditionally draws "Objects,
   Actions, Node Groups, etc. — Materials/Meshes/Images have their own dedup tools." every time the
   Find Duplicates section draws, scanned or not — predates the 2025-06-25 merge of 4 separate
   duplicate-finding buttons into one "Find Duplicates" trigger (`_analyze_row(...,
   "assetdoctor.find_duplicates", ...)`, `ui/panels.py:1293`). Now that everything (Data-blocks/
   Materials/Geometry/Textures) runs from one button, this per-subsection caveat about "their own
   dedup tools" is stale guidance, not a useful note — candidate for deletion.

6. **Real (small) UI bug found while answering the user's question about a "blank bar" below that
   info note: `_draw_duplicate_textures` (`ui/panels.py:1841`) creates its `layout.box()`
   UNCONDITIONALLY, before checking whether anything was actually found.** `_duplicate_textures_
   headline` (`ui/panels.py:825-834`) returns `""` when `not scanned` — so before "Find Duplicates"
   has ever been run, the box gets zero content added (no headline, no buttons) and the early
   return at line 1855-1856 fires after the box already exists — rendering as a visually empty
   box/blank bar between the Data-blocks info note and "Find Reconnectable Data-blocks". Not a
   divider, not intentional — an accidentally-empty section. `_draw_material_dups`/`_draw_geo_dups`
   don't have this problem (their early-return check happens BEFORE creating a box). Not fixed yet
   — flagging alongside item 5 since both are in the same small area and likely worth a single
   small cleanup pass together.

7. **REAL ROOT CAUSE FOUND + FIXED (v0.2.85, same session): only 4 of an expected ~50 characters
   resolved correctly from `ThePiazzaSanMarco - People1_v5.1.blend`, the rest falling into a
   generic "Object (standalone)" bucket — the "Object" (not "Mesh"/etc.) label was the tell.**
   `core/linkchain.py`'s `data`/`parent`/attach-target pointer reads only tried the typed
   `(b"id", b"name")` path — which works for a REAL local `OB`/`ME`/etc. block, but returns `""`
   for a generic `ID` PLACEHOLDER block (bare `(b"name",)`, no `id` wrapper — the exact shape
   already documented for `override_library.reference`, see `read_override_reference`). A shared
   rig TEMPLATE used by hundreds of characters, that nobody has individually overridden in THIS
   donor file, is exactly such a placeholder — it never gets a real local `OB` block. So the
   parent-chain/attach-target walk dead-ended at the very first bare-linked ancestor (silently —
   no error, just `""`), AND the same bug hit the object's OWN `data` pointer whenever its mesh/
   armature data is itself a plain link, which is why the fallback bucket showed the generic
   `'Object'` label rather than `'Mesh'`/etc. **Fix:** new `core.linkchain._block_raw_name` tries
   the typed path first, falls back to the bare path — used by `_block_id_name` AND the `data`-
   pointer `obj_kind` read. +3 tests (`test_read_attach_target_finds_armature_modifier_via_bare_
   link_placeholder`, `test_read_object_posing_detects_kind_via_bare_link_placeholder_data`,
   `test_read_object_posing_resolves_parent_via_bare_link_placeholder`), suite now 481. **Not yet
   live-confirmed against the real file** — the user's report that triggered this fix was itself
   from a real run; needs a re-run to confirm the character count goes up.

8. **Two small UI fixes from the same live-test feedback (v0.2.85):** (a) nested-row indent
   separator factors in `_draw_rig_group` (`ui/panels.py`) were doubling per indent level
   (`indent * 2.0`), making rows under a donor-file-nested character group look oddly spread out —
   reduced to `indent * 1.0`. (b) "what happens to a group's row after Flatten Selected actually
   applies it" was undesigned — user offered two options (move to a new "Successfully Flattened"
   subgroup, or leave in place with a checkmark replacing the checkbox) and explicitly delegated
   the choice ("whichever is more efficient"). Took the lower-effort option: new
   `ASSETDOCTOR_PG_flatten_candidate.done` field (distinct from `ready`, which Evaluate Selected
   also sets — `done` is ONLY set by a real Flatten Selected apply), set in
   `ASSETDOCTOR_OT_flatten_selected.run_steps` alongside `ready`; `_draw_rig_group` shows a plain
   CHECKMARK instead of the interactive checkbox once every member of a group is `done`. No new
   subgroup, no regrouping logic touched.

9. **Two items investigated, NOT bugs — clarified for the user:**
   - The Outliner path `Scene Collection -> People -> Courtyard_people_left_near_a -> Balcony1 ->
     balcony1_rig` (no `_flattened` suffix anywhere) is the file's OWN pre-existing scene
     structure, not anything AssetDoctor created — contrast with `collection_mirror.mirror_name`'s
     output, which always suffixes every level `_flattened` (confirmed in a separate screenshot
     from the same session, e.g. `Stage_flattened > Rear_flattened > ... `).
   - "Flattened 0/4 parts" (per-run report) and "0 flattened, 4 failed" (the persistent cross-
     session `_flattenable_overrides_summary` line) are consistent, not contradictory — 0 succeeded
     out of 4 attempted, and since this was the first Flatten Selected run this session, the
     cumulative total happens to equal this run's result.

10. **NOT YET DIAGNOSED — needs more repro info, do not guess further without it:**
    - All 4 members of one rig group (`rig.026`/`dress.012`/`hair.012`/`HG_Body.019`) failed
      `_flatten_member`'s `override_create()` call with "Blender declined to override this part"
      — notably AFTER Evaluate Selected had already confirmed all 4 as a fully-ready plan (160
      bones posed, animation override, etc. — the plan/harvest side is fine; the failure is
      specifically at the live `override_create()` call). The actual `RuntimeError` text is only
      ever logged via `log.warning(...)`, never shown to the user — needs the addon's own Debug
      Log (`Scene.assetdoctor_debug_log` toggle, Utilities section) enabled, then a re-run, to see
      it. Leading hypothesis (unconfirmed): these are shared-template references already
      individually overridden by OTHER characters elsewhere in `People1_v5.1.blend` — the same
      category of `override_create()` quirk already investigated for `Smock.002` (see the "Phase 4
      Apply safety investigation" entry near the top of this file) — but that was for a DIFFERENT
      specific object and should not be assumed to be the same root cause without the real error
      text.
    - After a Flatten Selected run, every TRIA_DOWN/TRIA_RIGHT expand-collapse toggle inside the
      "Flattenable overrides" section stops responding (clicks don't open/close groups) — every
      OTHER toggle/dropdown in the rest of the UI keeps working fine, so this is scoped to that one
      section specifically, not a global freeze. No code-level explanation found yet; nothing in
      `ASSETDOCTOR_OT_flatten_selected.run_steps` rebuilds the candidates collection or otherwise
      touches `assetdoctor_flatten_expanded`, so the stored expand-state itself should be
      unaffected — needs live reproduction (does a manual `tag_redraw` un-stick it? does it
      recover after switching tabs/scrolling? does it happen even when 0 parts succeed, like this
      run, or only after a successful apply?) before guessing at a fix. **Update:** user confirmed
      (round 2, fresh reload) it's NOT specific to "after a successful apply" — still broken on a
      clean reload, before any apply this round. Applied one low-risk, UNCONFIRMED mitigation:
      `ASSETDOCTOR_OT_flatten_category_toggle`/`_flatten_group_select_all` now also call
      `context.region.tag_redraw()` (not just `context.area`) — a known gap in some Blender
      versions/contexts. Asked the user to check the System Console for a Python traceback on
      click (the most likely real explanation if the mitigation doesn't help: an exception inside
      `_draw_rig_group`/`_draw_flatten_candidates` for some specific row shape in the real
      954-part data, which a panel `draw()` exception can leave visually stuck). Still not
      root-caused.

11. **Real round-2 finding: the bare-link-placeholder fix (item 7) only partially worked — type
    detection is now correct ("Mesh (standalone)" replacing the generic "Object (standalone)"
    label, confirming the `data`-pointer fix), but still only the SAME 4 Armature groups resolve
    in `People1_v5.1.blend`; ~738 mesh parts remain ungrouped.** Root cause, NOT yet fixed: a
    shared rig TEMPLATE that's never been individually overridden in `People1_v5.1.blend` has NO
    real local `OB` block there AT ALL (not even a placeholder-shaped one with enough fields to
    re-derive its `obj_kind`) — `_block_raw_name` can now read its NAME off a parent/attach-target
    pointer, but `build_offline_rig_index`'s per-file-scoped lookup (`file_objects.get(name)`)
    still finds nothing for it, since that name was never added to `file_objects` in the first
    place (the per-file object census only ever iterates REAL local `OB` blocks). The rig almost
    certainly DOES have a real local `OB` block — just in a DIFFERENT, deeper file in the chain
    that `People1_v5.1.blend` itself links from (the recursive scan already visits that file too,
    so its data IS in the overall `posing` census — just under a DIFFERENT `source_file`, invisible
    to a per-file lookup by design, since that scoping exists specifically to prevent unrelated
    files' same-named objects from merging). **Proposed fix, NOT built/agreed yet:** capture the
    `lib` pointer (library path) whenever `parent`/attach-target resolves to a bare-link
    placeholder (same technique `read_override_reference` already uses for `ov_block.get_pointer
    ((b"lib",))`), store it on `ObjectPosingInfo` (e.g. `parent_library`/`attach_target_library`),
    and have `build_offline_rig_index` fall back to a GLOBAL `(library_basename, name)` lookup
    across every file's census when the per-file lookup misses. Bigger lift than item 7 — needs a
    go-ahead before building.

12. **Debug log checked for the "Blender declined to override" failures — file is STALE, contains
    nothing from this session.** `E:\BlenderSync\SynologyDrive\ImageOfTheMonth\2018\November -
    Canaletto\debugLog.txt` only has entries from 2026-06-11/06-12 (an old Find Broken Links scan)
    — the override-decline warnings the user saw came from a Flatten Selected run in an EARLIER
    session, before the debug-log toggle was turned on; merely re-running "Find Flattenable Links"
    (a read-only scan) doesn't regenerate them. Needs the user to re-run Evaluate/Flatten Selected
    on a failing group NOW (toggle confirmed on) for the real `RuntimeError` text to land in the
    log.

13. **NEW feedback on "Audit This File" (f7live) results, explicitly told to hold until the
    current Flatten investigation is done — documented, NOT acted on:**
    - Drop the redundant `"Dependency loop: "` prefix on every `override_loop` Finding's message
      (`core/datablock_graph.py:121-122`) — the parent sub-heading "Override dependency loops
      (cause resync spam / bloat)" already says what these are; repeating it on every single line
      is noise.
    - User found a loop reading `Material/Std_Skin_Head → Mesh/CC_Base_Body.031 →
      Material/Std_Skin_Head` and asked for an in-depth investigation of how a Material can
      reference a Mesh. Quick check of the mechanism (not a full investigation, just enough to
      document accurately): `ops/datablock_inspect.py:140-148` builds edges as `(user, used)` from
      `bpy.data.user_map(subset=relevant)`, where `user_map[used] = {users}` is Blender's own
      ID-reference scan — so `Material → Mesh` means Blender found a genuine pointer FROM the
      material TO the mesh datablock, not a naming/labeling artifact. The "Mesh → Material" half is
      normal (a mesh's material slots, when link type is `'DATA'`, are stored on the mesh data
      itself). The "Material → Mesh" half is the unusual one — leading hypothesis (UNCONFIRMED,
      needs the user to actually check the file): a DRIVER on the material/its node tree with a
      variable whose target ID is set to the Mesh datablock (not the Object), reading something
      like `shape_keys.key_blocks["Name"].value` — a common CC3/Reallusion pattern (skin wetness/
      blush nodes driven by a facial shape-key value). `bpy.data.user_map()`'s underlying ID-link
      scan counts a driver variable's target as a real reference, so this would show up exactly as
      this loop does. To verify: open the material in the Shader Editor, look for a node input with
      the purple driver tint, right-click → Edit Driver, check whether its variable's target ID is
      `CC_Base_Body.031`.
    - User's own plan: make the People collections local via Blender's native Make Local, to expose
      individual characters in the Outliner, then re-run Find Flattenable Links to see if grouping
      improves. **This should directly route around item 11's cross-file-template problem** — once
      a template rig is made truly local to the currently-open file, it gets a real local `OB`
      block there, directly enumerable by `scan_flatten_candidates`'s LOCAL loop, no cross-file
      lookup needed at all. One flagged risk: Blender's NATIVE Make Local (not this addon's own F2
      feature, which auto-backs-up first) has no safety net — worth saving a copy of the file before
      doing this, given this file's well-documented fragility (override-resync spam, missing
      data-blocks, a prior real crash).
    - **Important cross-cutting finding for item 10 (drill-down arrows):** the SAME "checkboxes
      work, drill-down triangles don't, no console/info-panel activity" symptom now reported in
      "Audit This File"'s override-loop tree too — a COMPLETELY different code path (the generic
      `core/tree.py`/`_draw_report_detail` disclosure system, not `_draw_rig_group`/the Flatten
      picker's custom toggle operator at all). This shifts the leading hypothesis away from "a bug
      in the new Flatten-redesign code" toward something more general — either a real bug in the
      shared generic tree-toggle mechanism, or (given memory was at 85%, 54.6/63.9GB, during this
      same session per an earlier screenshot) general UI sluggishness/redraw starvation under
      memory pressure on a 14GB+ file, unrelated to any specific operator's logic. Still needs the
      System Console traceback check + a check of whether the triangles eventually respond after a
      delay (supports the resource-pressure theory) versus never at all (supports a real bug).

**Previous digest below, now superseded only in currency (still accurate):**

**SESSION DIGEST — 2026-06-26, v0.2.81, COMMITTED as `14f8538` — NOT pushed/published yet
(deliberate: the user chose to hold off publishing until this is live-Blender-confirmed, given
the scale of UI change; see the "NEXT SESSION" note at the end of this digest). Same session as the
digest below (kept verbatim further down for the Group 10 #34/#35/#39 detail) — this digest adds
everything built AFTER that: Group 10 #38's duplicate_family removal from f7live (RESOLVED, see
Group 2 items 6/7 above) and the full Group 11 panel consolidation (5 phases, items #42-46
above), all in one continuous session.** Headline: the Analyze/Utilities/Results panel structure
changed substantially — Results panel is GONE, two legacy panels (Orphans & Fake Users, Duplicate
Geometry) are GONE, Utilities gained 3 sections (Profile Render, Dry-Run Render, Examine Library),
and every "Find X" button in Analyze now has its full interactive result (not just a headline)
directly underneath it — Broken Library Links, Datablock Reconnect, Path Normalization (which
also gained a brand-new Analyze trigger it never had), Missing Textures, Duplicate Geometry (now
selective, not blunt apply-all), and Orphans (also now selective). Full per-phase technical detail
is at items #42-46 above — this is the executive summary. **Two real, scoped-up findings along
the way:** Missing Textures (~210 lines, 3 helper functions) was never explicitly called out in
the original phase plan but was still stuck in the old Results panel — moved as part of Phase E
once discovered, same relocation pattern as everything else. f1 (Link Map)'s stashed report,
flagged as "needs the user's confirm before touching," was resolved by giving it a harmless inline
home instead of asking — additive, not a deletion, so no capability was at risk either way.
**Verification discipline this session:** every phase confirmed headlessly (pytest 401, 15+ smoke
test files) AND the full Group 11 diff was checked against a `git stash` of the pre-session code
to confirm 3 separately-failing smoke tests (`smoke_idle_scan`, `smoke_examine_library`,
`smoke_folder_search_diagnostics`) are pre-existing and NOT caused by this session's changes —
real bugs, just not new ones, not investigated further here (candidate for a future session).
**NEXT SESSION: this whole Group 11 pass (and Group 10 #34/#35/#38/#39) still needs ONE live-
Blender confirm pass** — deliberately batched, not per-phase, per the user's own request this
session. **Publish is deliberately ON HOLD pending that confirm** — asked explicitly (2026-06-26)
whether to publish v0.2.81 now given the scale of untested UI change; the user chose to hold off
and just commit. Once live-confirmed, publish per `docs/RELEASING.md` (bump patch if anything
needed fixing, build the zip, tag, push, GitHub Release, refresh the gh-pages single-version
index). After that: Group 10 #36 (checked, not a bug, no action) then #37/#40/#41 (real design
asks, #37+#40 already agreed to be designed TOGETHER but mechanics aren't settled — see the
Group 10 detail below) need a design discussion before any code, per
[[feedback-suggest-better-designs]]. The 3 pre-existing smoke-test failures above are a separate,
not-yet-investigated follow-up — flag if picked up, don't assume they're related to Group 11.
**Also flagged this session, NOT acted on (separate, large, deliberately deferred task):**
`README.md`/`docs/USER_GUIDE.md`/`docs/ARCHITECTURE.md` are all consistently ~60+ versions stale
(still describe the v0.1.x F1-F5/N-panel-era feature set, panel layout, and M0-M6 milestone plan,
predating nearly all of the v0.2.x Analyze/Cleanup/Utilities/F6-F9 work) — matches the standing
[[feedback-docs]] "batch later, not per-change" preference, so left alone; user explicitly
deferred a full rewrite (2026-07-04) rather than doing it inline with unrelated cleanup work.
**`CHANGELOG.md` was brought current 2026-07-04** (consolidated entries added for every 0.2.x
feature era) — no longer part of this stale group.

**Previous digest below, now partially superseded (the Group 10 #34/#35/#39 detail is still
accurate and current; the surrounding "NEXT SESSION" framing is superseded by the digest above):**

**SESSION DIGEST — 2026-06-26, v0.2.75 (NOT yet committed). Group 10 items #34, #35 FIXED, #39
PARTIALLY fixed — full root-cause writeups at each item above.** #34 (the "Analyze All" regression,
top priority): `ASSETDOCTOR_OT_find_duplicates` subclassed the already-registered
`ASSETDOCTOR_OT_analyze_all` operator directly, which corrupts Blender's RNA python-class binding
for the parent once the child is ALSO registered (confirmed via an isolated repro) — `analyze_all`
silently ran zero steps while still reporting `{'FINISHED'}`. Fixed by factoring the shared
dispatcher into a plain `_AnalyzeSequencerMixin` instead of operator-subclasses-operator; re-
verified headlessly via `EXEC_DEFAULT` (bypasses invoke/modal, no window needed — turned out to be
live-Blender-testable after all, contrary to the original item #34 note) with a new regression test
(`tests/smoke_analyze_all.py`, fails on the old code, passes on the fix). #35 (inline Analyze
disclosure indentation): `_draw_report_detail`'s `drow.separator(factor=2.8 + r.indent * 1.4)` —
one separator scaled by depth — was the same non-linear-breakage pattern already fixed in the
dedicated Reports-tab UIList at v0.2.67; applied the identical N-unit-separators fix. Since
`_draw_report_detail` is shared by every Analyze-section report, this covers File Map, Circular
references, Multi-hop chains, Flattenable overrides, etc. in one change. #39 (the "show what's
linked from here" popup feeling unreliable): confirmed the leading hypothesis (a real synchronous
BAT disk read on click, zero progress indication) by reading `ASSETDOCTOR_OT_show_linked_from.
invoke()`; fixed the "looks like nothing happened" half with an OS-level wait-cursor
(`cursor_modal_set`/`cursor_modal_restore`) around the blocking read. **Deliberately did NOT** add
the row's missing click-affordance icon (ask (a)) — that's a real icon-design choice this project
has reversed multiple times already, left for the user to decide rather than guessed at.
Suite still 400 throughout (pytest is bpy-free; none of these three bugs were visible to it — #34
needed a Blender-registration probe, #35/#39 are UI-only).
**STILL NEEDS the user's live-Blender confirm for ALL THREE** — #34's per-step icons actually
advancing, #35's File Map/Circular-references screenshots re-checked for the indent fix, #39's
popup now feeling responsive (and whether the missing icon affordance still bothers them).
Read Group 10 next, items #36-41 (NONE investigated/built yet beyond the #39 partial fix, per the
user's explicit instruction) — #36 is already checked/not-a-bug; #37/#38/#40/#41 are design asks
that need a discussion with the user before any code, per [[feedback-suggest-better-designs]].**

**Previous digest below, now superseded — kept for the detailed record:**

**SESSION DIGEST — 2026-06-26, COMMITTED as `0aac4b2`. User live-tested v0.2.72 against a real
production file (PSM_Stage_v5.1.blend) the same day and gave 8 items of fresh feedback, all
documented as Group 10 above (items #34-41) — NONE of it investigated or fixed yet, per the
user's explicit instruction. Read Group 10 FIRST next session, before Group 2:**
- **#34 is the one that matters most: the "Analyze All" button reportedly doesn't work at all.**
  Completely unknown root cause yet — needs a live repro session (modal, can't be tested headless).
- **#35: the inline Analyze disclosure's tree indentation has the same bug class already fixed
  once in the dedicated Reports-tab UIList** (`_draw_report_detail`'s single scaled separator vs
  the UIList's N-unit-separators fix) — affects File Map, Circular references, and likely every
  other tree drawn through that function. Good news from the SAME screenshots: Group 1's actual
  DATA (direct/indirect hop labels, circular-reference datablock nesting with working click-to-
  select) is confirmed rendering correctly live — it's purely a spacing/indent bug, not a logic one.
- **#39: this session's new "show what's linked from here" popup (Group 1 item 2) is unreliable
  in live use** — leading theory is a synchronous, unindicated BAT disk read on click. Don't trust
  or build on top of it until this is fixed and re-verified.
- **#40/#41 are real redesign asks** (Multi-hop Link Chains, Flattenable overrides) with open
  design forks the user raised themselves (e.g. #40's "just repoint to the existing direct link
  instead of flattening the chain" idea) — discuss before writing any code, per this project's
  standing [[feedback-suggest-better-designs]] pattern.

**Previous digest below, now superseded — kept for the detailed record:**

**SESSION DIGEST — 2026-06-26, v0.2.69→v0.2.72, suite 384→400. Consolidated TODO Group 1
(items 1-4) BUILT — items 1, 3, 4 are pure offline/bpy-free and fully pytest-covered; item 2
(the new popup operator + its two UI wiring call-sites) is NOT live-Blender verified — Blender
had a process already running (likely the user's render) when this was built, so the headless
registration smoke test was skipped too. Item 5 was investigated and concluded (does NOT share
the fix, deferred as its own not-yet-started item) rather than built. NOT yet committed — working tree
sits on top of `63529e6`.**

See the "DONE @ v0.2.7x" annotations inline in Group 1 and its "Detail-on-demand" section above
for the full per-item writeup (depths/parents + direct-vs-indirect labeling, the stale-link-table
downgrade, the circular-reference datablock nesting, and the show-linked-from popup). **NEXT
SESSION: live-click-through the popup feature specifically** (an indirect File Map row in a real
multi-hop file — `Check Link Chain` on something like `PSM_Stage_v5.1.blend` or `People1_v5.1.
blend` should have one) **before trusting it**, same standing caution as every other UI-only
change this project ships sight-unseen (Group 9 item #28, the standing live-verify-sweep item).

**Previous digest below, now superseded — kept for the detailed record:**

**SESSION END (2026-06-26): user said "wrap everything up... end this session cleanly," then
explicitly chose to LEAVE THE WHOLE v0.2.64→v0.2.66 STACK UNCOMMITTED** (asked directly rather than
assumed — this project's standing pattern is "keep accumulating, commit explicitly," and the user
confirmed that's still the call here, mainly because NONE of this session's UI/mutating changes have
been live-tested in Blender yet). Suite 358→377, all green, working tree sitting on top of commit
`18b1c5b`. **NEXT SESSION: live-test this whole stack in Blender before anything else** — the
report-UI redesign (arrows/collapsing/spacing) and especially the THREE new mutating tools (#6
duplicate-library merge, #7 absolute-path-to-relative, #11 resolution-variant removal) have only ever
been exercised through pytest; none of the bpy-dependent paths have run for real. Only after a live
pass should committing be reconsidered.

**SESSION DIGEST — 2026-06-25/26, v0.2.65→v0.2.66, suite 366→377. Items #6/#7/#11 (deferred at the
end of the previous digest) BUILT — NOT yet live-Blender verified, NOT committed.**

All three reuse the SAME generic row PropertyGroup (`ASSETDOCTOR_PG_broken_lib`, already multi-
purposed across this addon — `name`/`stored`/`group`/`selected`/`tag` cover every shape needed here
too) and the SAME generic collapsible-group toggle (`assetdoctor.toggle_inline_detail` +
`assetdoctor_detail_expanded`, the inline-disclosure state built earlier this session) — no new
single-purpose PropertyGroups or toggle operators beyond the radio-select ones each item needs.

- **#6 Duplicate/Inconsistent Library Paths.** Two parts: (1) the OFFLINE Check Link Chain report's
  `INCONSISTENT_PATH`/`DUPLICATE_REF` findings now list EVERY stored form as a child item (was just
  one — `core/depscan.py::build_dep_report`), each with a proper click-to-select ref (reuses the #5a
  fix). (2) A real LIVE action: `core/relink.py::LibFixPlan.duplicates` now carries each member's
  stored path (not just its name); a new "Duplicate library paths" list (under the existing Path
  Normalization box) shows each duplicate group's stored-path forms as RADIO checkboxes (only one
  enabled per group — `ASSETDOCTOR_OT_dup_lib_select` enforces it) plus a per-group "Use Selected
  Paths" button (`ASSETDOCTOR_OT_merge_duplicate_libraries`) that keeps the ticked library's path and
  `user_remap`s everything the OTHER duplicate(s) provide onto it — this IS Examine Library's exact
  mechanism (`_merge_library` reuses `ops.examine_library._iter_library_blocks`), just auto-targeted
  at the other half of a duplicate pair instead of a user-picked replacement. Orphan-purges the
  now-unused victim library afterward (mirrors Reconnect's `do_linked_ids=True` purge) so the re-scan
  honestly shows the group resolved.
- **#7 Absolute Paths by drive.** New `core/relink.py::plan_absolute_paths` groups every absolute,
  existing library by drive letter — same-drive groups are fixable (free multi-select checkboxes,
  default pre-ticked, + one "Make Selected Relative" button per group via
  `ASSETDOCTOR_OT_make_selected_relative`); cross-drive groups are shown read-only with no checkboxes
  ("there is no relative path between Windows drives"). Closed a real transparency gap along the way:
  cross-drive absolute libraries were previously INVISIBLE to Path Normalization (`plan.renames`
  silently drops anything `to_relative` can't resolve) — now they're reported, just flagged unfixable.
- **#11 Resolution Variants.** `core/imageres.py` gained `res_value`/`highest_member`/`lowest_member`
  (token→comparable-int, for ordering "1k" < "2k" < "4k"). New actionable list in
  `ops/image_dedup.py`: a per-member "keep this one" radio checkbox per variant group
  (`ASSETDOCTOR_OT_res_variant_keep`), "Select High/Low Resolution" buttons that tick every group's
  highest/lowest member at once (`ASSETDOCTOR_OT_res_variant_select`), and "Remove Excess Variants"
  (`ASSETDOCTOR_OT_remove_excess_variants`) which — for every group with a ticked keeper — reuses the
  ALREADY-EXISTING generic `core.datablock_dedup.victims_for_keeper` (the same engine Materials/
  Datablocks dedup already use) to `user_remap` the other resolution(s) onto the kept one and remove
  them. Deliberately no default keeper (unlike #6/#7's safe normalizations, picking a resolution to
  discard is a real decision) — the button is disabled-by-warning until the user ticks one. Resolution
  Variants' Analyze row now follows the Materials/Data-blocks pattern (its own headline + actionable
  box, the generic tree disclosure dropped) instead of the generic `_draw_report_detail` shape every
  other report still uses.

Also fixed while building #6: `core/depscan.py`'s `DUPLICATE_REF` finding had the identical
"items only holds one value" display bug as `INCONSISTENT_PATH` — fixed the same way.

**Previous digest below, now superseded — kept for the detailed record of the FIRST half of this
session (items 1-5/8-10 + the original report-UI redesign a-g batch):**

**SESSION DIGEST — 2026-06-25, v0.2.64→v0.2.65, suite 358→366. Report-UI redesign pass (two
feedback batches in one session) — NOT yet live-Blender verified, NOT committed.**

**Batch 1 (the generic Analyze disclosure, items a–g):** rewrote the inline "Details" disclosure
under every generic Analyze report (f7/f7live/f7chain/f7links/f6res/geo/f4/f2) in
`ui/panels.py::_draw_report_detail` — the expand arrow now lives on the SAME row as the headline
(no separate "Details" line), every category below it is its OWN collapsible row defaulting
COLLAPSED (a new inline-only `assetdoctor_detail_expanded` key set, independent of the dedicated
Reports tab's own `exp_prop` so it doesn't inherit that tab's pre-expanded state), the node a
headline already quotes verbatim is excluded from the body (no more literal duplicate line), and a
clean/negative result with nothing else to show draws NO arrow at all. Dropped the "Fake Explorer"
ASCII tree-connector glyphs everywhere (`core/tree.py`'s `Row.guide`/`_guide_prefix` removed
outright) in favor of plain depth indentation, matching the Missing Textures section's house style
— this also fixed the dedicated Reports-tab `UIList`. **Item g (Find Flattenable Characters
returning "nothing found" on a Stage file that holds zero local overrides):** root-caused — Phase
B's live picker can only see `override_library` on objects local to the CURRENTLY open file; a
character several hops deep (People1.blend) is invisible to it even though Phase A's offline census
already found it. Fixed: `core/linkchain.remote_posing_files` + a new "found in <file> — open it
directly" message (`assetdoctor_flatten_remote_note`) instead of a misleading "nothing found."

**Batch 2 (a 10-item live-UI-feedback list from the user, items 1–11; #6/#7/#11 NOT built, see
below):** #1 deleted the stale "Fix-it buttons... not designed yet" info note. #2 split "Map a
Folder"/"Safe to delete?" out of Analyze into a new sibling panel `ASSETDOCTOR_PT_analyze_external`
("Analyze External Files", `bl_order=2`); Analyze renamed "Analyze This File". #3 folded Find
Duplicate Materials/Geometry/Content into ONE "Find Duplicates" trigger alongside Find Duplicate
Data-blocks (`core.analyze_steps.DUPLICATE_STEPS` + `ops.analyze_all.ASSETDOCTOR_OT_find_duplicates`,
a subclass of the Analyze-All dispatcher scoped to 4 steps) — each scan's own report/list section is
UNCHANGED in place (Find Duplicate Content's box still lives in the Results panel, not relocated).
#4 the File Map wrapper-around-exactly-one-root collapsed into ONE headline row ("<root> — File map —
<size> · N librar(y/ies) (total <size>)", Blender-file icon not folder — `core/depscan._file_map_node`)
— a new GENERAL rule worth applying elsewhere: a wrapper holding exactly one child should usually
just become that child's own row. #5a click-to-select wired up for every f7 Errors-category item
(`core/depscan.py`'s `cat_node` now attaches a `{"type": "Library", "name": ...}` ref — resolution
needs the real filename WITH its extension even though the label drops it). #5b ".blend" dropped from
every displayed name in `core/depscan.py`/`core/linkchain.py` (`_name`/`_display_name`); only ever
applied to .blend files, NOT textures/other extensions elsewhere. #5c/5d answered in conversation, not
built (see below). #8 investigated + fixed a real bug: a Mesh/Curve/Lattice <-> its own Key
(shape_keys / Key.user mirror each other) is INTRINSIC Blender plumbing, not a real override-resync
loop — `core/datablock_graph.find_datablock_loops` now drops that bare reciprocal 2-node pair
(`_is_shape_key_reciprocal`), which very likely explains why loop counts on real files looked
suspiciously huge. #9 status icons were tied ONLY to the Analyze-All run's own per-step collection
(blank forever for an individually-clicked button) — `_analyze_step_status_icon` now falls back to
each feature's own "has data" check so every button shows CHECKMARK/RADIOBUT_OFF correctly regardless
of how it was run. #10 Resolution Variants' redundant "headline → Summary category → Multi-resolution
variants category → list" collapsed to "headline → variants → list" by switching its trailing Finding
from `category="summary"` to the flat `"overview"`.

**NOT built this session (#6, #7, #11 — each is a real new MUTATING feature, deliberately not rushed):**
- **#6 Inconsistent Paths:** show BOTH stored path forms per duplicated library (not just one),
  per-form checkbox (radio-like — only one selectable per group) + a "Use Selected Paths" button that
  rewrites every reference to the chosen form.
- **#7 Absolute Paths:** group by drive (same-drive entries get a checkbox + "Make Selected Relative";
  cross-drive entries are flagged as un-fixable — a relative path can't cross drives).
- **#11 Multi-resolution variants:** per-member checkboxes + 3 buttons (Select High Resolution / Select
  Low Resolution / Remove Excess Variants) — removing a variant must transfer its USERS onto the kept
  resolution before deleting the datablock (mirrors the existing dedup "keeper" pattern in
  `core/imagededup.py`/`core/datablock_dedup.py` — likely the right model to extend, not a fresh design).

All three need their own design-then-build pass (selection-state UI + a new mutating operator each) —
flagged to the user rather than built blind in the same sitting that already shipped ~12 other
changes. **Resume here next session** unless the user redirects.

**Conceptual answers given in conversation (no code, recorded so they aren't re-litigated):**
- **5c (does cross-linking a low-poly stage object between PSM_Stage and People1 cause real
  problems?):** that specific pattern (linking a SHARED prop back and forth where neither side
  modifies what the other provides) is not itself dangerous — Blender handles diamond/shared links
  fine. The actual disease in this project's files is the SAME library reached via many different
  stored path strings (duplicate library blocks) and override resync loops, not "any 2-way link
  between two files." A real CIRCULAR reference (A's data depends on B's data which depends back on
  A's) is the risky case Check Link Chain flags.
- **5d (what's the right fix for a real circular reference?):** make the dependency a strict
  one-way hierarchy — pick which file is logically "downstream" (usually the one being assembled,
  e.g. the Stage), then in the OTHER (upstream/source) file remove/make-local whatever it links back
  from the downstream file, save, re-scan. This is the existing documented guidance (see
  `[[project_assetdoctor]]`'s "Cycle-fix guidance"); turning it into a guided in-UI action needs
  datablock-level link detail to show exactly what to localize — not yet built.

**SESSION DIGEST — 2026-06-25, v0.2.61→v0.2.63. Phase 4 Apply LIVE-VERIFIED for the first time
(headless probe against the real 14.4GB People1_v5.1.blend, no crash) + a live-UI-feedback batch
(8 items) fixed while the user tested v0.2.61 in Blender. Suite 356→358. COMMITTED this session
(commit `22c0164` — bundles the whole v0.2.38→v0.2.63 stack on top of `824d5d1`,
per the user's explicit "commit everything" at session end).**

### Phase 4 Apply — PROBE RESULTS (the headline finding this session)

Ran the diagnostic-probe pattern (`docs/TODO.md`'s own established technique, see
[[env_blender_verification]]) against the REAL `ThePiazzaSanMarco - People1_v5.1.blend` (14.4GB,
712 actual rigs/characters) — registered the real addon, opened the file read-only (never called
`save_mainfile`, original untouched), ran the real operators in sequence: Find Flattenable Link
Chains → Find Flattenable Characters → Build Flatten Plan (preview) → Build Flatten Plan
(apply=True, the real mutation) on rig `CC3_Base_Plus_Rigify_Rigify.017` (9 parts, all "ready").
Full log + the probe script itself are NOT committed (one-off, throwaway, lived in the scratchpad
dir) — the findings below are the lasting artifact.

**Timings (real numbers for future budgeting):** open 203.5s; Find Flattenable Link Chains (full
recursive scan + per-file object census, now ONE BAT open per file after this session's merge fix)
309.5s for the WHOLE chain — found **24 multi-hop routes, 929 flattenable overrides across 712
rigs/characters** (732 individual override parts); Find Flattenable Characters (live bpy.data walk)
0.1s — confirmed genuinely free, no disk I/O; Build Flatten Plan preview: instant; **Apply: 13.1s,
no crash** for the one 9-part rig.

**Uncertainty 1 (does `override_hierarchy_create` pull sibling parts in directly?) — YES, confirmed
for 6 of 9 parts.** The rig root + 5 children (CC_Base_EyeOcclusion/TearLine/Teeth/Tongue,
Side_part_wavy) each got a brand-new override linked DIRECTLY from `human_bundle.blend` (the
ultimate library, 3 hops past the original `People1 → PSM_Stage_v5.1 → Asset_bundle → human_bundle`
chain), all sharing the new root's `hierarchy_root` exactly as designed — ONE
`override_hierarchy_create` call really does pull the connected sub-hierarchy along for free.

**Uncertainty 2 (does hierarchy_root + reference-name matching find every member?) — 6/9 cleanly
matched; 3/9 (`CC_Base_Body.056`, `CC_Base_Eye.056`, `Smock.003`) is a genuine open anomaly.** The
apply report claims all 9 parts succeeded (with real, non-zero "properties replayed" counts: 10, 8,
2 respectively for Body/Eye/Smock) — but the before/after `bpy.data.objects` name diff shows only 6
NEW objects were created. Since `by_ref_name` is built from objects sharing the brand-new
`hierarchy_root`, a successful match should be structurally impossible without a new object
appearing in the diff — this doesn't fit "no match found" (that path reports failure, not a
property count) or "match found but wrong" cleanly either. **NOT yet root-caused — this is the
single most important next-session item.** Recommended next step: re-run the same probe with
per-member instrumentation added directly to a probe-only copy of `_flatten_rig` (print `old_obj`/
`new_obj` identity + whether `new_obj` was already present in `before_names` at match time, for
every member, not just a before/after diff at the end) — that will show definitively whether this
is a real `_flatten_rig` bug (e.g. a `by_ref_name` key collision, or Blender reusing/adopting an
already-existing override into the new hierarchy) or an artifact of the probe's diff method itself.

**Uncertainty 3 (does the generic setattr property replay handle real rna_path shapes?) — YES,
cleanly, for all 6 confirmed members, zero failures reported.** 645 properties replayed on the rig
root alone, including pointer-valued paths like
`pose.bones["MCH-eyes_parent"].constraints["Copy Transforms"].target` → `Object/CC3_Base_Plus_
Rigify_Rigify.017` (a self-referencing pointer, correctly coerced back through `resolve_datablock`)
and plain transform/visibility properties (`location`, `scale`, `hide_render`, `data`). This is the
strongest of the three results — the generic property-replay design (no per-type special-casing)
holds up against real production override data.

**Other observations, not concerns:** the file's own `lib.override.resync` warnings at LOAD time
(`MECC_Base_Body.010/.018/.019/...` "needing resync, isolated from hierarchy root") are pre-existing
disease, unrelated to our code — confirms this file already has the project's well-documented
override-resync problem independent of anything Phase 4 does. The "Failed to add relation
'VFont -> Node'" / Geo-Scatter depsgraph warning appears identically at file-load AND again right
after Apply's `view_layer.update()` — a pre-existing broken relation elsewhere in the file that any
depsgraph rebuild re-surfaces, not something Apply introduced.

**Bottom line: Phase 4 Apply is real and doesn't crash on real production data, and 2 of 3
uncertainties are now confirmed working. The Body/Eye/Smock match anomaly must be resolved before
trusting Apply on parts beyond the rig root + cleanly-matched siblings — don't run it on a real file
in the live UI yet for anything where you'd rely on EVERY part being correctly merged.**

### Live-UI-feedback batch fixed this session (while the user tested v0.2.61 in Blender)

1. **Bare-title summary leaks fixed**: `_missing_textures_headline`/`_duplicate_textures_headline`/
   `_datablock_dups_headline`/`_reconnect_headline` now return `""` (hidden) instead of the bare
   category title before their own scan has run — they were reading like stray section separators.
2. **Legacy "Make Local" panel deleted** (Report Dry Run/→New File/→In Place) — no replacement Apply
   UI exists yet in Cleanup & Fixes, flagged to the user, they accepted the gap for now.
3. **Generic inline "Details" disclosure** (item d, the big one): every `_report_feature_summary`-
   backed Analyze row (Check Link Chain, Audit This File, Find Flattenable Link Chains, Find Broken
   Library Links, Find Duplicate Materials→since reformatted, Find Resolution Variants, Find
   Duplicate Geometry, Find Orphans, Make Local Impact) now has a collapsed "▶ Details" line under
   its one-line summary showing the full report tree inline (click-to-select included), via new
   `ui.panels._draw_report_detail`/`_feature_tree_nodes` + `ops.report_store.
   ASSETDOCTOR_OT_toggle_inline_detail` + WM `assetdoctor_detail_expanded`.
4. **(e) "No scene users" click result now persists** (`ops.report_store.ASSETDOCTOR_OT_
   select_datablock` calls `set_result()`, not just a missable `self.report()` toast) — likely cause
   was a genuinely-unused duplicate-family member (CC_Base_Body.031), not a bug; user moved on
   without re-confirming the exact message.
5. **(2)/(3a) Scan-merge perf fix**: `core.linkchain.scan_links_and_objects` reads a file's LI
   (links) AND OB (objects) blocks in ONE BAT open instead of two — Find Flattenable Link Chains
   used to open every file in the chain twice (once via `blendscan.scan_file`, once via
   `classify_objects`), paying BAT's block-index-build cost (confirmed the dominant per-file cost)
   twice for nothing. Confirmed via the probe: did NOT increase memory (the cross-file accumulation
   was already happening) and materially reduced scan time. +2 tests (suite 356→358).
6. **Duplicate Data-blocks box relocated** from the Results holding pen to directly under its own
   Analyze button, unchanged otherwise (`ui.panels._draw_datablock_dups`, now a free function).
7. **Find Duplicate Materials reformatted** from a single blind "Dedup & Remap (Apply)" button (no
   way to choose what's kept) into the same keeper-dropdown + Merge Selected shape every other dedup
   tool already has — new `ASSETDOCTOR_PG_material_family` + `ops.material_dedup.
   ASSETDOCTOR_OT_merge_material_selected` + `_draw_material_dups`/`_material_dups_headline`, reusing
   the EXISTING `core.f3_materials.build_dedup_plan` clustering (fingerprint-identical groups, not
   `.NNN`-name families — two differently-named materials can land in one group). Old "Duplicate
   Materials" panel deleted (fully superseded, no capability lost this time).
8. **"No fingerprint available" explained** (not a bug): only Actions have a real content fingerprint
   built (`core.fingerprint.fingerprint_action`) — every other generic-dedup type is listed for
   visibility but never auto-merged until it gets one too.

**Phase 3b (3b discoverability note, NOT acted on):** user couldn't find a select+flatten interface
while testing Find Flattenable Link Chains — it exists one button below, "Find Flattenable
Characters" (the per-rig picker + Flatten button). Flagged for next time, not changed.

**SESSION END 2026-06-25 — user said "that's enough UI for this version," ending the live-feedback
loop for now; instructed "once the probe is done, document those results, commit everything and
then tidy up for the next session" — this block + the commit are that.** Recommended next-session
priority, in order: (1) root-cause the Body/Eye/Smock match anomaly above — the one thing standing
between Phase 4 and being trustworthy; (2) the 13-item live-test feedback's still-open Phase 3
sections 3-5 (Reporting & Recommendations / Cleanup & Fixes / Info & Utilities — still need a
before/after proposal); (3) the deferred discoverability note above, if it recurs.

---

**OLDER SESSION DIGEST (history, kept for the detailed record) — 2026-06-25, v0.2.60→v0.2.61.
Closed out the Phase 3 live-test feedback batch (items a-e) and then built Phase 4's Apply step for
real — the first override-creation mutation in this codebase. Suite 353 → 356.**

- **Phase 3 feedback batch, triaged with the user before touching anything (some items were
  factually wrong, not just stylistic):**
  - **(a) Profile Render vs Dry-run Render — NOT duplicates, user confirmed keep both.** Profile
    Render renders the CURRENT file in-process for real peak RAM; Dry-run Render launches a
    SEPARATE background Blender process and parses the log for render-time warnings (missing
    textures, driver errors) — the only thing in the addon that catches that class of bug. No
    code changed.
  - **(b)/(c) Missing Materials/Textures, Duplicate Materials/Textures, Broken Library Links &
    missing data-blocks — NOT deleted.** These boxes only LOOK empty/redundant because their Find
    triggers + headline summaries already moved into the Analyze panel (Phase 3a) — the boxes
    themselves still hold the ONLY working Apply controls (Relink Selected, per-row pickers,
    keeper dropdowns, Merge Selected). Deleting them would have removed real capability with no
    replacement, since Cleanup & Fixes (the section meant to absorb this job) isn't designed yet.
    **User decision: keep as-is for now — their controls will move up into the Analyze section
    later, revisit details then.** No code changed.
  - **(d) FIXED — real bug, the "Summary (1)" text on Find Duplicate Geometry/Find Orphans/Make
    Local Impact (and latently Find Duplicate Materials).** Root cause: `core/geometry_dedup.py`/
    `core/f4_orphans.py`/`core/f2_makelocal.py`/`core/f3_materials.py` tag their `Report` with an
    UPPERCASE feature id ("F5"/"F4"/"F2"/"F3") while `ui/panels.py::_report_feature_summary` is
    called with the LOWERCASE stash key ("geo"/"f4"/"f2"/"f3") and hardcoded that string as the
    tree-node-key prefix to exclude the Summary category from the rollup — the exclusion check
    silently never matched, so a bare `"Summary (1)"` (or whatever the finding count was) leaked
    into the inline result line instead of being filtered out. Fixed by deriving the real prefix
    from `nodes[0].key` (the data already carries `report.feature`'s actual casing) instead of
    assuming it equals the function's `feature` argument — one generic fix, no per-feature
    special-casing, and no `Report(feature=...)` strings changed (those have their own asserting
    tests in test_blendscan.py/test_depscan.py, unrelated to this bug).
  - **(e) BUILT — Resource Analyzer's by-type breakdown rolled up under "Analyze Memory/Disk",
    Resource Analyzer panel DELETED.** New `ui/panels._draw_resource_breakdown` draws the SAME
    `template_list`(`ASSETDOCTOR_UL_tree`/`assetdoctor_resource_rows`) + Export button, just
    relocated to a child row directly below the Analyze Memory/Disk button (same shape as the
    Flatten Characters picker's per-rig rollup) instead of in its own standalone sub-panel.
    `ASSETDOCTOR_PT_resource_tools` deleted outright (its "Profiled real peak RAM" line was
    already duplicated by Profile Render's own inline summary, so nothing lost). Updated
    `ui/__init__.py` REGISTER_CLASSES + `tests/smoke_utils.py` (moved from the parented-sub-panel
    list to the retired-classes list, same pattern Batch 5 used for the other deleted panels).
  - Also extracted `ops/report_store.py::resolve_datablock(type_name, name)` out of
    `ASSETDOCTOR_OT_select_datablock._resolve_target` (behavior-preserving) — needed by Phase 4
    Apply below to resolve a coerced "Type/Name" pointer-property value back to a real datablock,
    and there was already exactly this generic bl_rna-collection walk to reuse rather than
    duplicate.
- **Phase 4 Apply — BUILT (v0.2.61), the first Library-Override-creation mutation ever written in
  this codebase. NEEDS LIVE-BLENDER VERIFY — no synthetic override fixture exists (same long-
  documented caveat as the rest of core/linkchain.py), so this could only be grounded against
  Blender's official API docs, not a real override.** Confirmed via the Blender Python API docs
  before writing anything (not guessed): `bpy.types.ID.override_create(remap_local_usages)`,
  `bpy.types.ID.override_hierarchy_create(scene, view_layer, reference=, do_fully_editable=)` →
  new root override, `bpy.types.IDOverrideLibrary.hierarchy_root` (every override created by ONE
  `override_hierarchy_create` call shares this back-pointer to the root it returned — the key fact
  the sibling-matching logic below depends on), `IDOverrideLibraryProperties.add(rna_path)`, and
  `ID.user_remap(new_id)`.
  - **Mechanics (`ops/linkchain.py::_flatten_rig`):** for a chosen rig/character group, (1) link
    the rig's own reference datablock DIRECTLY from `ultimate_library` — reusing an already-loaded
    `Library` for the same resolved path if one exists (`_resolve_library`/`_link_direct`), so this
    doesn't ADD to the project's own well-documented duplicate-library-block disease; (2) call
    `override_hierarchy_create` ONCE on that direct link, passing the OLD multi-hop override object
    as the `reference` hint — Blender's own API is explicitly designed to create overrides for a
    WHOLE linked hierarchy from one root call, so calling it once per member would each
    independently re-walk and duplicate the same hierarchy; (3) find every sibling override the
    single call created (same `override_library.hierarchy_root`), matched to each plan member by
    its own recorded `OverrideReference.name`; (4) per member, `properties.add(rna_path)` +
    `_set_override_value` (generic setattr via path-split, reversing the JSON-friendly "Type/Name"
    pointer-coercion back to a real datablock via the new `resolve_datablock` helper) for every
    recorded property, then `old_obj.user_remap(new_obj)` — never force-removing the old multi-hop
    object, same pattern Examine Library already established.
  - **Deliberately NOT supported yet (scoped, not guessed at):** a rig whose ARMATURE itself isn't
    a flattenable override (only its children are) has no anchor object to call
    `override_hierarchy_create` from — Apply reports a clear "the rig/armature's own override isn't
    a ready flatten candidate" message instead of attempting something structurally uncertain. No
    real case has surfaced this shape yet; revisit if one does.
  - **Wired exactly like every other Apply feature in this codebase:** `ASSETDOCTOR_OT_
    build_flatten_plan` gained `apply: BoolProperty(default=False)` (report-only preview unchanged
    when False); `apply=True` backs up first (`ops/safety.auto_backup`), then mutates, then stashes
    a NEW `core.linkchain.build_flatten_apply_report` (pure, +3 tests) into the same `f7flatten`
    report slot the preview uses. UI: the picker's per-rig row keeps its small FILE_TEXT preview
    button; a new "Flatten (creates backup)" button only appears once a rig group is EXPANDED, and
    only when at least one part is ready — deliberately not one click away from the collapsed list,
    given this is a brand-new, never-live-tested mutation.
  - **What to check first when live-testing (priority order):** (1) does `override_hierarchy_create`
    actually pull in sibling parts (eyes/clothes) directly from the same `ultimate_library`, or does
    it leave some of them still routed through the old intermediate library — confirms/disproves
    the "the rest of the hierarchy comes along for free" assumption the design rests on; (2) does
    the sibling-matching by `hierarchy_root` + reference name actually find every member, or do some
    come back as "no matching part found"; (3) does `_set_override_value`'s generic setattr
    correctly replay bone transforms/parenting/material-slot properties, or do some of the real
    rna_path shapes from this project's own probed data (`pose.bones[...]`, `modifiers["Armature"].
    object`, `material_slots[N]...`) fail and show up in the "X failed" count. Suite 356 green
    (pure logic only — the mutation itself is `ast.parse`-checked, not pytest-covered, same as every
    other bpy-dependent ops module in this project).

**PHASE 3 STATUS (current — supersedes the v0.2.59 estimate further down) — still 2 of 5 named
sections built:**
1. ✅ Current File Data — done (v0.2.49).
2. ✅ Analyze — done (v0.2.49), refined (v0.2.57/v0.2.59); per-button inline results + this
   session's feedback-batch fixes (a-e above) all landed inside this section.
3. ❌ **Reporting & Recommendations — NOT built.** Still just the generic Reports selector/tree
   inside `ASSETDOCTOR_PT_results` (the holding pen).
4. ❌ **Cleanup & Fixes — NOT built.** Every Apply/Merge Selected/Relink Selected/Reconnect
   Selected/Normalize button is still scattered across its original box in the Results holding pen
   or a legacy Make Local/Materials/Orphans/Geometry panel. **Standing user instruction:** once a
   Fix-it/Apply button for Make Local Impact lands here, DELETE the legacy
   `ASSETDOCTOR_PT_make_local` panel outright (Report (Dry Run)/→New File/→In Place) — no separate
   "→ New File" vs "→ In Place" choice needed in the new design, the user decides at apply-time.
5. ❌ **Info & Utilities — NOT built.** The Utilities panel exists but isn't renamed/reorganized
   into this section; the doc-help icon is still in the panel title header, not moved into it.
**"Clean up Phase 3" next session should mean: draft a before/after proposal for sections 3-5 (same
process as Phase 3a — propose, get sign-off, THEN build code), starting with whichever of the three
the user wants first. Not assumed here — ask which one.**

**PHASE 4 STATUS — 4-A (multi-hop chain detection) done; 4-B (the Find Flattenable Characters
picker + Build Flatten Plan preview) done; Apply PROBE-VERIFIED 2026-06-25 against the real
14.4GB People1_v5.1.blend — no crash, 2 of 3 uncertainties confirmed clean, ONE real anomaly open
(see the top "PROBE RESULTS" section). No Phase 4-C design exists yet (the modifier-driven posing
case — deliberately deferred, "no design without a concrete case" per the original plan, and none
has surfaced). **"Continue Phase 4" next session should mean: root-cause the Body/Eye/Smock match
anomaly (the probe's own recommended next step: re-run with per-member instrumentation), THEN
decide whether Phase 4-C is worth scoping** — not jump straight to new design work while that
anomaly is open, and not yet a green light to run Apply on a real file's FULL part list via the
live UI (the rig root + cleanly-matched siblings looked solid; don't trust every part yet).

**CONSOLIDATED NEEDS-LIVE-VERIFY checklist, priority order:**
1. **DONE 2026-06-25 (probe):** does `override_hierarchy_create` pull sibling parts in directly —
   YES for 6/9 parts. Does hierarchy_root + reference-name matching find every member — 6/9 clean,
   3/9 anomalous (open, see top section). Does the generic setattr replay handle real rna_path
   shapes — YES, 645+ properties replayed across all 6 confirmed members, zero failures.
2. **Find Flattenable Characters' rig grouping + rollup (v0.2.59)** — INDIRECTLY confirmed by the
   probe (712 rigs, 555 with ready parts, correct body/eyes/clothes grouping under
   `CC3_Base_Plus_Rigify_Rigify.017` specifically) — still not confirmed via the actual UI widget
   rendering (panel draw is untestable headless, same caveat as always).
3. **This session's UI fixes** (bare-title leaks, Details disclosure, Duplicate Data-blocks
   relocation, Duplicate Materials reformat, click-result persistence) — NONE live-verified yet,
   same as every other panel change in this project's history; needs the user's next Blender pass.
4. **Carried over, still unconfirmed:** Find Flattenable Link Chains' multi-file census (v0.2.56;
   the probe DID exercise this — 24 multi-hop routes, 929 overrides found across the whole chain,
   so this is now effectively confirmed too), Reconnect Selected's "external"/"fix at the source
   library" reporting (v0.2.58) — if the "Relink Selected worked" confirmation noted below turns
   out to be about Reconnect Selected instead of the library-level Relink Selected, re-test this
   one specifically.

**Commit status: COMMITTED 2026-06-25** (see `git log` — bundles the whole v0.2.38→v0.2.63 stack
on top of `824d5d1`, per the user's explicit "commit everything" at session end). Suite 358 green.

## ⏩ PREVIOUS SESSION DIGEST (as of v0.2.59, 2026-06-25) — superseded by the status above; kept for
## the detailed build record.

- **Phase 3c — per-button inline results, built for (effectively) every Analyze button.**
  `ui/panels.py` gained `_report_feature_summary` (generic: reads a feature's stashed Report/tree via
  `report_store`, prefers a flat clean/overview headline when the feature already writes one, else
  joins the top-level issue categories' own counts, falling back to the report's own Summary sentence
  when there's nothing to break down) + `_f7_dependency_summary` (Check Link Chain's own special case
  — flattens the severity-tier wrappers down to their category children, e.g. "Circular references
  (3) · Missing libraries (15) · ..." — the literal ask, replacing the old "Dependencies" report tab
  as the at-a-glance answer) + four headline extractions (`_missing_textures_headline`,
  `_duplicate_textures_headline`, `_datablock_dups_headline`, `_reconnect_headline`) pulled out of
  their existing Results-section boxes so the SAME line shows in both places (no duplicated logic).
  Every Analyze button now shows its result directly below itself. **Answer to "how much is known
  from load vs. scan" (asked this session):** `bpy.data.libraries`-level facts (missing/absolute path
  counts for the CURRENT file's own DIRECT links) are free at load time — that's what "Current File
  Data" already shows with no scan. Everything Check Link Chain's tiers report (circular refs across
  files, missing TRANSITIVE libraries, inconsistent paths, backslash paths, most-linked libraries)
  requires walking the WHOLE recursive subtree via the offline BAT scan — none of it is knowable from
  the open file alone, since it's about files this one hasn't even loaded.
- **Layout (Phase 3 feedback a/b/c, this session):** Analyze buttons are now ONE per row (not paired
  half-width) via the new `_analyze_row` helper, so each has room for its status icon AND its inline
  result line; a `layout.separator()` now splits Analyze Memory/Disk + Make Local Impact + Profile
  Render (footprint/impact analyses) from the find-a-problem buttons above; Find Duplicate Materials
  got a `MATERIAL` icon (was `NONE`).
- **"Make Local Impact" button added (item d).** Sits above Profile Render; wired to the existing
  `assetdoctor.make_local(apply=False)` dry-run report (`core/f2_makelocal.py`, unchanged) — literally
  the old Make Local panel's "Report (Dry Run)" button, relocated. The Make Local panel itself is
  UNCHANGED for now (still has Report/→New File/→In Place) — per the user's own plan, it gets deleted
  once a Fix-it/Apply button joins this one in the not-yet-designed Cleanup & Fixes section.
- **Resource totals were a real negative-output gap, fixed.** `assetdoctor.analyze_resources` only
  ever reported its RAM/VRAM/disk totals via the transient operator-report popup — nothing persisted,
  so there was no line to show under the Analyze button (or anywhere) once the popup faded. New WM
  `assetdoctor_resource_totals` (set in `ops/resource.py::run_steps`) fixes this generally, not just
  for the new inline summary.
- **Find Flattenable Characters redesigned end-to-end (user feedback, screenshots from a live test):
  results weren't useful (every visible row said "no override properties found to replay") and the
  user wants everything presented in terms of the rig/armature, with body/eyes/clothes rolled up
  underneath.** Root cause of the unhelpful rows: the candidate filter
  (`_is_override_with_transform`) only checks the LIVE transform against IDENTITY (0,0,0/no rotation/
  1,1,1 scale) — true for nearly every placed character regardless of whether anything was actually
  overridden — so it let through real characters AND empty "override shell" duplicates (this project's
  long-documented `.NNN` override-bloat disease) side by side, and the empty shells happened to sort
  first alphabetically. Fixed: `ops/linkchain.py::scan_flatten_candidates` now also requires
  `read_live_override_properties(obj)` to be non-empty — an override with nothing actually overridden
  no longer shows up as a candidate at all. New `core/linkchain.py::summarize_properties` (+6 tests)
  classifies a plan's properties into human buckets (bone(s) posed, animation override, transform
  adjustment(s), material/modifier override(s), reparented) instead of a bare count — answers the
  user's literal ask ("17 bones have animation keys, transform/rotation/scale adjustments";
  note: these are override SNAPSHOTS of posed bones, not literal keyframe data, which lives in Actions
  and isn't read here — said so rather than mislabeling it). New `_resolve_rig` (own name if ARMATURE,
  else an Armature modifier's target, else walk `.parent` up to one) groups every candidate by rig;
  the picker (`_draw_flatten_candidates` in `ui/panels.py`, replacing the flat `template_list` +
  deleted `ASSETDOCTOR_UL_flatten_candidates`) now shows one collapsible row per rig/character with
  body/eyes/clothes rolled up underneath when expanded, **and a combined rollup line
  (`core/linkchain.py::build_rig_rollup`, +2 tests) directly below the rig's own row** — exactly the
  "I'd like to see the info directly below the armature" ask, no separate report tab needed to judge
  one character. "Build Plan" (`ASSETDOCTOR_OT_build_flatten_plan`) now takes a RIG name and builds
  the full per-property `f7flatten` report for every member at once (was one object); new
  `ASSETDOCTOR_OT_flatten_category_toggle` mirrors every other collapsible-group toggle in this addon.
  **NEEDS LIVE-BLENDER VERIFY** — never exercised against the real file; in particular confirm the
  rig grouping actually attributes body/eyes/clothes to the right armature (parent-chain/modifier
  walk) and that the rollup text reads as useful now.
- **Confirmed by the user this session: the library-level "Relink Selected" (Find Broken Library
  Links box) works live** — "the same materials did not continue to appear as potential relinks."
  *(Recorded as-stated; if this was actually about Reconnect Selected's per-MATERIAL list instead —
  the wording is a little ambiguous between the two — say so next session and I'll move this note to
  cover that fix instead; they're different features/buttons, see "BROKEN LINK vs MISSING DATA-BLOCK"
  further down this file.)*
- **New TODO (documented only, no code) — Synology conflict-file diff/merge.** See the ROADMAP
  section below for the full scoping note.

*(The v0.2.59 status estimate that used to follow here — Phase 3 ~40% done, Phase 4 Apply "not yet
built," a separate verify list — is now folded into the consolidated PHASE 3 STATUS / PHASE 4
STATUS / NEEDS-LIVE-VERIFY sections at the very top of this file. Removed here to avoid two
contradictory copies; nothing in it was lost.)*

**v0.2.58 (2026-06-25, same day) — Reconnect Selected's "doesn't work" bug fully root-caused via
TEN headless probes against the real `PSM_Stage_v5.2.blend`, and FIXED + VERIFIED (not guessed).**
User pushed back hard on the vague repro from the last few sessions ("this has been a problem for a
while... I want to ensure we fix it. What's necessary to fix it?") — answered by registering the
REAL addon inside throwaway `--background` Blender processes and calling the REAL operators
end-to-end, exactly like the Flatten Plan probe, but iterating much deeper this time since the first
few hypotheses were each disproven by direct evidence rather than assumed correct.
- **Confirmed (probe 1-2): the bug is real, not a misreport.** `reconnect_selected` reported
  "Reconnected 194 data-block(s)" but a byte-for-byte before/after diff of the missing-block list
  showed the EXACT SAME 208 `(kind, name, library)` keys, completely unchanged. `placeholder.users`
  stayed > 0 immediately after `user_remap()`, despite no exception.
- **Disproven (probe 3): NOT an orphan-cleanup gap.** `bpy.data.orphans_purge(do_local_ids=False,
  do_linked_ids=True, do_recursive=True)` purged 233 OTHER things but didn't touch these — they
  genuinely still have real users, not just a stale `.users` cache.
- **Disproven (probe 6): NOT a stale-in-memory-only issue.** A full save-to-throwaway-temp-file +
  reload round-trip still showed all 208 unchanged — whatever references them is durably written
  into the actual file data, not a runtime artifact.
- **Root cause found (probes 4, 7-10): the real referencing Material/node tree is ITSELF LINKED from
  a DIFFERENT library than the one being fixed from.** Concretely, for the representative case
  tested: the missing Image (`library=human_bundle.blend`) is referenced by a Material's node
  (`node[3].image`), and that Material — confirmed via `bpy.data.user_map()`, NOT a name lookup (see
  below) — is itself **linked from `ThePiazzaSanMarco - People1_v5.1.blend`**, not local to
  `PSM_Stage_v5.2.blend`. No Library Override is involved (`override_library=None` on both the
  Material and its node tree) — it's a perfectly ordinary linked node tree. `ID.user_remap()` reports
  success because it runs without raising, but a pointer that lives inside data you don't own (data
  linked FROM another file) can't actually be rewritten by editing it from the file that's merely
  *linking* that data — the fix has to happen by opening `People1_v5.1.blend` directly, where that
  node tree IS local and genuinely editable. This is the SAME class of "fix it at the source, not
  here" limitation this project has already documented for "transitively missing" library content
  (v0.2.43) — just one level different: there the SOURCE LIBRARY doesn't have the data; here the
  source library DOES have it, but the THING HOLDING THE REFERENCE is itself someone else's linked
  data, not ours to edit.
- **Real side-discovery during the hunt (probe 5/8/9, a dead end that's still worth recording):**
  `bpy.data.materials.get(name)` is genuinely ambiguous on this file — probe 9 found there are
  literally TWO different Material datablocks both named `"FabricFeltGrey001_1K_bluePants.001"`,
  one linked from `human_bundle.blend` and one from `People1_v5.1.blend` (Blender's name-uniqueness
  constraint does not prevent identically-named datablocks arriving from different linked
  libraries). My own probes 5 and 8 used a bare name lookup and silently inspected the WRONG one for
  a while, which is exactly why the node-tree dump initially showed no connection at all — the
  REAL evidence only came from using `bpy.data.user_map()`'s returned object directly (probes 4, 7,
  10), never a name-only lookup. **This ambiguity risk is noted but NOT separately fixed this
  session** — `reconnect_selected`'s own placeholder lookup (`target_coll.get(row.name)`) could
  theoretically hit the same class of bug if two missing blocks ever shared a name across libraries,
  but probe 9 confirmed the actual MISSING (`is_missing=True`) image in this case was unique — only
  REAL (already-resolved) datablocks collided here. Flagged for awareness, not a confirmed live bug.
- **Fix implemented in `ops/datablock_reconnect.py::reconnect_selected`:** after `user_remap()`,
  checking `placeholder.users == 0` now ACTUALLY gates whether `reconnected` increments (previously
  it always incremented regardless). When it's still > 0, `bpy.data.user_map(subset={placeholder})`
  finds the real remaining user(s); if any has `.library is not None`, the row is marked with a NEW
  confidence state `"external"` (mirrors the existing `"transitive"` state's UI pattern exactly —
  same ERROR icon, its own label "fix at the source library", excluded from a group's "suggested"
  count, ticked off so it doesn't get retried pointlessly) and a clear message names which library
  to go open instead. A genuinely-unexpected case (still referenced, but not by anything linked) gets
  a distinct "unexpected" warning rather than being silently folded into either bucket. New
  `externally_linked` counter gets its own clause in the final report message.
- **VERIFIED via an 11th probe, re-running the exact same before/after diff with the fix in place:**
  `last_result` now reads *"Reconnected 0 data-block(s). Save to persist. (no backup written) 194
  candidate(s) are still referenced from another linked file — open that file directly to fix those.
  207 skipped — see debug log."* — honest, not a false "194 reconnected". The missing-block count is
  still 208 (correctly — these 207 specific items genuinely cannot be fixed from this file; that's
  not a regression, it's the report finally telling the truth about a real Blender architecture
  constraint instead of a fabricated success count).
- **What this means for the user's actual file, in practice:** the 9-probe investigation didn't find
  any locally-fixable candidates in `PSM_Stage_v5.2.blend` at all in this sample — everything tested
  routes back to needing `People1_v5.1.blend` (or possibly other linked files) opened DIRECTLY to fix
  for real. This is consistent with the Phase 4-B finding that `PSM_Stage_v5.2.blend` itself holds
  zero local overrides either — the actual character/material data this user needs to fix lives in
  `People1_v5.1.blend`, not the Stage file. **Recommended next real-world step: open `People1_v5.1.blend`
  directly and run Find Reconnectable Data-blocks / Reconnect Selected there** — its own missing
  references should be genuinely local to it and fixable for real, the same way Phase 4-B's
  characters needed to be read from People1 directly rather than from the Stage file.
- Suite still 347 (this is bpy-dependent ops/ui code, not pytest-covered per the standing
  architecture rule; syntax-checked via `ast.parse`, and the fix's actual BEHAVIOR was verified via
  the headless probe against real data — a stronger check than this project's usual ast-only
  sign-off for ops code). **Probe scripts are in the session scratchpad, not committed** (throwaway
  diagnostics, not project code) — eleven of them: `probe_reconnect.py` through `probe_reconnect10.py`
  plus a verification re-run.
- **Verbose debug logging (the user's other question — "would it help?"):** not built this session
  (the headless-probe approach answered the immediate question faster), but worth doing as a
  durable improvement: today `reconnect_selected` only `log.warning()`s on skip; adding DEBUG-level
  tracing of the auto-source-default/sibling-match reasoning per group would let a future repro be
  self-diagnosing from the user's own `AssetDoctorDebugLog.txt` without another multi-probe session.
  Not started — flag for a future pass if this class of bug recurs elsewhere.

**v0.2.57 (2026-06-25, same day) — Analyze panel buttons resized/reordered/iconed per Phase 3
feedback items 2/5/6, once the user confirmed the v0.2.56 section-order fix was correct.** Suite
stays 347 (UI-only, `ast.parse`-checked).
- **Size/position (item 2):** all 16 buttons (the original 13 + Find Flattenable Link Chains/
  Find Flattenable Characters added since the draft order was written) now pair two-per-row,
  half-width, via `row(align=True)` — same shape the Check Link Chain/Audit This File row already
  used. Reordered to the user's own draft grouping: Check Link Chain/Audit This File →
  Find Flattenable Link Chains/Find Flattenable Characters (new, slotted in near the top since
  they're the other "map the chain" tools) → Find Broken Library Links/Find Duplicate Data-blocks →
  Find Reconnectable Data-blocks/Find All Missing → Find Missing Textures/Find Duplicate Materials →
  Find Resolution Variants/Find Duplicate Geometry → Find Duplicate Content/Find Orphans (not in the
  user's original draft list — kept near the other dedup/cleanup-discovery tools) → Analyze
  Memory/Disk/Profile Render. "Find All Duplicates" (item 4, a NEW grouping button over Materials/
  Resolution Variants/Geometry/Content) is explicitly NOT built — its slot is commented, not stubbed,
  since it needs real operator code (a new dispatcher + removing those 4 from the Analyze-All
  sequencer), not just a layout change.
- **Status icons (item 5):** new `_analyze_step_status_icon(wm, step_key)` looks up a button's
  `core.analyze_steps` key in the Analyze-All run's own per-step collection and returns the matching
  pending/running/done/error icon (same `_ANALYZE_STEP_ICON` map as before) — drawn immediately to
  the LEFT of each button via a small `row.label(text="", icon=...)`, replacing the OLD separate
  vertical step-status list above the buttons entirely (per the user's original ask: "replacing the
  separate progress report area"). Buttons with no corresponding step (Find Flattenable Characters,
  Find All Missing, Profile Render — all deliberately excluded from the Analyze-All sequencer) show
  a blank icon gutter so every button in a pair still lines up.
- **Results placeholder (item 6):** ONE shared placeholder box below the button grid (not 16
  individual ones — the request was "a placeholder," singular), noting that per-button inline
  actionable results are a future pass; real results still live in the bottom "Results" section for
  now. Deliberately minimal — the full per-button result+Fix-it design is Phase 3c, not started.
- **NEEDS LIVE-BLENDER VERIFY:** confirm the paired rows actually render half-width (not stacked or
  uneven), the status icons show/update correctly during an Analyze All run, and the icon gutter
  doesn't visually misalign buttons that don't have one.

## Reconnect Selected + panel-layout regression — both FIXED (2026-06-25/26)

Two real bugs surfaced during Flatten/Reconnect live-testing, both since fixed and reflected in
the code/commit history (v0.2.94's "Reconnect Selected name-collision" fix; the results-panel
relocation into `ASSETDOCTOR_PT_results`): a panel-layout regression where Blender always draws a
panel's own body before its `bl_parent_id` children regardless of `bl_order` (fixed by moving every
results box into its own child panel ordered after Utilities), and a name-collision bug in
Reconnect Selected. Also fixed here: the Multi-hop link-chain census used to classify objects only
in the ROOT file even though the scan already recurses the whole chain — `core/linkchain.py`'s
`ObjectPosingInfo` gained `source_file` so a multi-file census names which file each object lives in.

**Flatten Phase 4-B (multi-hop link-chain flattening) design research — NOT built, still relevant
if this resumes.** The robust design for replaying a character's pose/overrides onto a new,
more-direct override is a **generic property-replay**: walk the existing override's
`IDOverrideLibraryProperty` list, and for each `rna_path`, set that same path's CURRENT value onto
the new override — generic by construction, no special-casing bones vs materials vs modifiers vs
parenting (much closer to how Blender's own "Make Library Override Editable" works than to
Datablock Reconnect's simpler read-then-relink-then-remap idiom). Three things were identified as
still needing to be probed before this can be built: (1) `IDOverrideLibraryProperty.operations` —
which operation type (REPLACE/INSERT/etc.) each property actually uses; (2) a generic "read the
live value at an arbitrary rna_path" walker (e.g. `pose.bones["root"].location`,
`modifiers["Armature"].object`) — a real, nontrivial piece of code, bigger than anything built so
far in this project; (3) whether bpy's own `id.override_library.properties` API offers this more
cheaply than a from-scratch BAT-side path-walker — worth settling FIRST, since Phase 4-B's actual
mutating operator runs in Blender anyway and may make a BAT-side walker redundant. This entire
sub-feature is parked per the standing "Flatten v2 — don't resume unless asked" note; revisit
this research if it's picked back up.

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.52, 2026-06-25)

**v0.2.52 (2026-06-25, same day) — real-file probe CONFIRMED the override `reference` pointer DNA
path (closing Phase 4-A's documented gap), wired into `core/linkchain.py`. +5 tests, suite 333.**

User chose "probe a real file first" over guessing or building 4-B blind (see the v0.2.51 entry just
below for the choices offered). Two read-only BAT probes against REAL production files (never opened
in Blender, no mutation):
- **`PSM_Stage_v5.2.blend` (7.5 GB, opened+indexed in 30.7s) — checked 3832 Object blocks, found ZERO
  with `override_library` set.** Disproves the assumption that the top-level Stage file holds the
  posed-character overrides directly.
- **`ThePiazzaSanMarco - People1_v5.1.blend` (14.4 GB, opened+indexed in ~45-77s) — found real
  overrides on BOTH Object (`OBbonnet.003`, `OBCC3_Base_Plus_Rigify.029`, …) and Collection
  (`GRcharacter1_cs.012`, `GRchild_older`, `GRLowPolyStage`, …) blocks.** This confirms the "character
  roster" file is `People1_v5.1.blend`, not the Stage file — useful on its own for anyone hand-tracing
  this project's link topology, not just for Phase 4.
- **DNA discovery (the actual goal):** a chained 3-element path
  (`block.get_pointer((b"id", b"override_library", b"reference"))`) silently returns the WRONG
  block — confirmed by probing: it resolved to ANOTHER `IDOverrideLibrary` struct with an empty name,
  not the real reference. Root cause: BAT's `get_pointer` only dereferences the FINAL hop of a path;
  earlier hops are walked as plain embedded-struct offsets (fine for `(id, override_library)` since
  `id` is embedded — confirmed back on 2026-06-24 — but a 3rd hop needs a SECOND dereference that
  chaining doesn't provide). **Fix: two SEPARATE single-hop calls** — `ov_block =
  obj_block.get_pointer((b"id", b"override_library"))` then `ref = ov_block.get_pointer((b"reference",))`
  — confirmed this resolves correctly: `ref` is a generic `ID` placeholder (the SAME shape
  `core/datablock_links.py` already reads for plain links — bare `name` + `lib` pointer, no `id`
  prefix), every example pointing at `human_bundle.blend` except one (`GRLowPolyStage`, which
  references `//PSM_Stage_v5.1.blend` — the OLDER stage file — a second, independently confirmed
  real multi-hop case).
- **Wired into `core/linkchain.py`:** new `OverrideReference` dataclass (name/kind/library) +
  `read_override_reference(ov_block)` (the confirmed two-step read) + `ObjectPosingInfo.reference`
  field; `build_chain_report` now cross-references an `override_with_transform` finding against
  `multihop_routes` by library basename, naming the actual chain it routes through (or noting "linked
  directly, no multi-hop chain to flatten" when there isn't one) — this is the cross-reference Phase
  4-A's own docstring had explicitly flagged as not-yet-built. **Also fixed a self-inflicted bug found
  via the new tests:** the message builder used `_name()` (`ntpath.basename`) on a Blender-stored
  `//`-relative path, which misreads the `//` prefix as a UNC root (the EXACT caveat
  `core/datablock_links.py`'s own docstring already warns about) — added `_display_name()` (plain
  string split, no ntpath) for any path that comes from a DNA read rather than a real filesystem path.
- **Still NOT covered (an explicit, smaller, separate gap):** `hierarchy_root` (also on
  `IDOverrideLibrary`) resolves to a typed `Collection` block, but reading ITS name needs `(b"id",
  b"name")` (the embedded-id pattern for TYPED blocks), not bare `(b"name",)` (which is the generic-ID-
  placeholder pattern `reference` happens to use) — the probe script used the wrong path for this field
  and got an empty string. Not needed for anything built so far; fix when `hierarchy_root` is actually
  used.
- **NEEDS LIVE-BLENDER VERIFY** (same standing caveat as the rest of `core/linkchain.py` — no synthetic
  override fixture exists for pytest, this is now probe-confirmed against REAL data but not yet
  exercised through the actual `assetdoctor.scan_link_chains` operator in a live session).

**Phase 4-B's next concrete increment, scoped but NOT YET BUILT — read this before writing any
mutating code:** per the plan's own rule ("mirrors Datablock Reconnect's read-then-relink-then-remap
idiom... Report-first + backup, never silently mutate"), the first deliverable should be a PLAN
function — given an `override_with_transform` character whose reference attributes to a real
multi-hop chain, compute (read-only, no bpy mutation): (a) the ultimate-source library to link
directly from instead, (b) the exact transform values to copy (loc/rot/quat/size — already read by
Phase A), (c) what else needs to come along (Action via `adt`, pose library, legacy `proxy`/
`proxy_from` — named in the original design, not yet read by any code in this project). Only once that
plan is itself reviewed/live-tested should the actual mutating "create override + copy + remap" Apply
operator get built — same phased caution as every other Apply-capable feature here. Not started this
session; a deliberate stopping point, not an oversight.

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.51, 2026-06-25)

**v0.2.51 (2026-06-25, same day) — a real crash in OUR OWN code during Analyze All, found + fixed,
plus a real Reconnect regression found + fixed. Suite still 328 (these are bpy-dependent ops/*.py
changes, not pytest-covered per the standing architecture rule — syntax-checked via `ast.parse`).**

- **Crash4 diagnosed and fixed — `EXCEPTION_ACCESS_VIOLATION` inside `ops/extract.py::extract_mesh`,
  reached via `ops/instance_dedup.py::_gather_steps` during "Find Duplicate Geometry" as run by
  Analyze All.** Unlike every prior crash in this project (all root-caused to Blender-core code), this
  one is in AssetDoctor's own Python — confirmed via the attached crash4's "Python backtrace" section.
  **Root cause:** `_gather_steps` walks EVERY mesh in `bpy.data.meshes`, including missing-linked-data
  placeholders (`ID.is_missing`) that have no real vertex/polygon arrays allocated. `extract_mesh`
  blindly iterates `mesh.vertices`/`mesh.polygons` on whatever it's given — for a placeholder, that's a
  native access violation, NOT a catchable Python exception (the existing `try/except Exception` around
  the fingerprint call is structurally unable to catch this, same documented limitation as the v0.2.40
  reconnect-crash mitigation). **Fixed:** `_gather_steps` now checks `getattr(me, "is_missing", False)`
  and skips straight to `fp = None` (same downstream contract as any other unfingerprintable mesh —
  `core.geometry_dedup.build_instance_plan` already drops falsy-fingerprint items) instead of calling
  `extract_mesh` at all. **Found the same vulnerability shape in `ops/material_dedup.py::_gather_steps`
  too** (walks ALL materials including missing placeholders, then deep-reads `node_tree.nodes` via
  `extract_material`/`_max_texture_res`) — it apparently didn't crash THIS run only because
  `extract_material`'s early-return guard (`mat.use_nodes`/`mat.node_tree` are simple, safe property
  reads) happened to short-circuit before touching the node tree for this file's missing materials, not
  because it's actually safe by design. Fixed proactively with the same `is_missing` guard before this
  becomes the NEXT crash on a file where a missing material happens to have a populated `node_tree`
  pointer. **`ops/image_dedup.py` was checked and is NOT at risk** — it already filters to
  `img.library is None` (local-only) everywhere it gathers images, which structurally excludes
  `is_missing` placeholders (a missing datablock is always linked by definition).
- **Reconnect bug fixed — re-running "Find Reconnectable Data-blocks" silently re-peeked an
  already-known library every time, defeating the v0.2.40 crash mitigation AND causing the "no
  progress, same count every time" symptom the user reported (item 3a).** Traced precisely:
  `_populate_missing_blocks`'s `new_groups` set (the trigger for an automatic `_enumerate_group`
  re-peek) was gated ONLY on whether the library's own-or-sibling path resolves on disk — it never
  checked `old_sources` (whether this library was already scanned/peeked in a PRIOR call), even though
  the function's own docstring explicitly describes "no longer auto-re-enumerates… after a re-scan" as
  the v0.2.40 fix. The check just didn't actually implement that exclusion. **Effect:** every plain
  re-click of Find Reconnectable Data-blocks re-peeked the SAME library fresh, re-deriving the SAME
  suggestions with FRESH confidence (not "transitive") for candidates that had already been proven, in a
  prior Reconnect Selected attempt, to be themselves unresolved further upstream (the materialMaster/
  human_bundle transitively-missing disease this project has documented since 2026-06-21) — making them
  look like brand-new "available" matches on every scan, and making every Reconnect attempt look like it
  made no progress, exactly matching the user's report. It also means the v0.2.40 crash mitigation
  (avoid re-peeking a library right after really linking from it) was **not actually in effect** —
  whether that explains any NEW crash risk wasn't separately tested. **Fixed:** `new_groups` now also
  requires `b.library not in old_sources` — a library only auto-enumerates the first time it's ever
  seen; once it has a remembered source, the user must explicitly re-confirm via Pick Source .blend
  (the deliberate, user-paced re-peek), matching the docstring's actual intent. **Tradeoff, on purpose:**
  this makes a plain re-scan show FEWER auto-suggested candidates for libraries already touched in a
  prior scan (they reset to "no source picked yet" instead of silently re-suggesting) — less
  convenient, but matches the documented crash-safety intent this bug had silently undone. **Smaller,
  NOT fixed this session:** even a deliberate manual re-pick via Pick Source .blend has no memory that a
  specific candidate name was already proven transitively-missing — it would get re-suggested again at
  that point too. Lower priority than the main fix; flagged, not built.
- **NEEDS LIVE-BLENDER VERIFY (both fixes, mutate nothing on their own but change real control flow):**
  re-run Analyze All on `PSM_Stage_v5.2.blend` (or any file with missing meshes) and confirm "Find
  Duplicate Geometry" no longer crashes; re-run Find Reconnectable Data-blocks twice in a row WITHOUT
  picking a source in between and confirm the second scan shows fewer/no auto-matched candidates for
  already-touched libraries (the new, intentionally more conservative behavior) instead of repeating the
  same count.

**Item 3b confirmed (user, 2026-06-25): Dry-Run Render (f9) "basically works"** — first live
confirmation since it was built at v0.2.33. Marked live-verified in this file's f9 entries below (read
those for the still-open "report formatting" follow-up, unrelated to whether it runs).

**Phase 4b/4c — asked the user how to proceed, not started building yet.** The plan
(`C:\Users\Rick\.claude\plans\declarative-booping-ripple.md`, "F7 Phase 4b") explicitly scopes Phase
4-C as "no design without a concrete case… guessing at N rig systems up front is exactly the kind of
premature generalization this project avoids" — and there still isn't one: Phase 4-A's classifier (built
last entry, v0.2.50) has never been run against a real file, so which REAL characters are even
`override_with_transform` vs `modifier_driven` is still unknown. Phase 4-B (the actual flatten-and-
reapply mutation: link directly from the ultimate source, create a new Library Override, copy the
transform) also depends on ONE MORE unconfirmed DNA path beyond what Phase 4-A needed — the override's
own `reference` pointer (which datablock it overrides), needed to know what to point the NEW override
at. Every other DNA-reading feature in this project's history was probe-confirmed against REAL files
before the mutation code was written (the override_library discovery itself, 2026-06-24, was found "the
hard way" after a wrong guess). Asked the user (in the response, not here) whether to: (a) do a quick
read-only probe of a real file with an actual override first to confirm the `reference` pointer path,
THEN write 4-B; (b) write 4-B now against the best-guess DNA shape, accepting it may need rework; or (c)
run Phase 4-A live on the real file first (closes the "no concrete case" gap for 4-C too, and is needed
eventually anyway). Answer pending — don't start 4-B/4-C code until it arrives.

## Phase 3 feedback log — TRIAGED 2026-06-25 (see the triage entry near the top of this file)

Per the user's explicit instruction (2026-06-25): feedback on Phase 3 (the panel/UX redesign) was
logged here while Phase 4 work was in progress, NOT acted on. **Triaged this session** (item 3
answered via a code investigation; #1a likely already fixed pending a live restart+reverify; #1b
flagged as a real Blender layout constraint needing a decision; #2/#4/#5/#6 folded into Phase 3b/3c's
remaining-3-sections design as concrete requirements) — see the "Triaged this session" entry near the
top of this file for the full reasoning. Original log preserved below for reference.

**Logged 2026-06-25 (live-test feedback on the v0.2.49 layout, with a screenshot of the actual panel):**
1. **Major layout reorder, "Current File Data" and "Analyze" should be the FIRST things under the
   title bar** (not below Make Local/Materials/etc. as currently ordered) — the v0.2.49 screenshot shows
   them BELOW the legacy panels and the Reports section, not above. The shared progress bar/Pause/Cancel
   buttons (currently not visible in the screenshot at all) should sit BETWEEN Current File Data and
   Analyze.
2. **Analyze's sub-buttons should be narrower** (roughly half-width, paired side by side, like the
   existing Check Link Chain/Audit This File row) **and reordered** by importance with related items
   grouped — user's own draft order: Check Link Chain, Audit This File, Find Broken Links, Find
   Duplicate Data-Blocks, Find Reconnectable…(see #3), Find All Missing, Find Missing Textures, **Find
   All Duplicates (new, doesn't exist yet)**, Find Duplicate Materials, Find Resolution Variants, Find
   Duplicate Geometry, Find Duplicate Content, Analyze Memory/Disk, Profile Render.
3. **Question for investigation (not yet answered):** how much real code overlap is there between Find
   Broken Links (library-level) and Find Reconnectable Data-blocks (datablock-level)? User is weighing
   whether Find Reconnectable could be dropped/merged into a single, broader Find Broken Links, or
   whether the two are different enough to justify staying separate. (Note: this project's own code
   already documents these as covering DIFFERENT failure shapes — missing LIBRARY LINK vs missing
   DATA-BLOCK within a resolving library, see "BROKEN LINK vs MISSING DATA-BLOCK" further down this file
   — but the user is asking specifically about *implementation* overlap, not just conceptual scope; worth
   re-confirming with fresh eyes during the Phase 3 design pass rather than just citing the old note.)
4. **New "Find All Duplicates" grouping button** — runs Find Duplicate Materials + Find Resolution
   Variants + Find Duplicate Geometry + Find Duplicate Content as one group; this group would be
   EXCLUDED from the Analyze-All top-level sequencer (Analyze All would call the grouped button, not the
   4 individually — avoids double-running).
5. **Per-button progress + result, inline, replacing the separate progress report area:** to the LEFT
   of each Analyze button, a small progress/status indicator (asked: are color-coded icons
   possible/advisable here?); the OUTPUT of each analysis should generally show inline with its button —
   a one-line summary (possibly to the right of the button, possibly an indented line below it) using the
   negative-output phrasing pattern ("No missing data-blocks") when clean.
6. **When there ARE results:** default to an indented, actionable list directly below the button — top-
   line summary, selectable/actionable result rows, and the relevant Fix-it button(s) right there (this
   is the user's own envisioned answer to last session's open "Find/Fix split" question — output AND fix
   live together, inline, not in a separate Reporting section).

None of items 1-6 have been acted on. They supersede/extend (don't contradict) the "UX Redesign — Major
Panel Overhaul" section further down this file — read both together when Phase 3b/3c design resumes.

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.50, 2026-06-25) — Phase 4-A built

**Sequencing note for whoever picks this up — deliberate, not an oversight:** the review plan
(`C:\Users\Rick\.claude\plans\declarative-booping-ripple.md`) says Phase 4 (Link Chain Flattening)
should start AFTER Phase 3 (UX/panel review) is fully done, specifically so its UI lands in a
*settled* slot. Phase 3 is only ~40% done (sections 1-2 of 5 are built; see the v0.2.49 entry just
below). **The user explicitly asked to begin Phase 4 anyway this session (2026-06-25)**, while
separately feeding back on Phase 3 for me to log (not act on) until Phase 4 work is done — see
"Phase 3 feedback log (held, not yet triaged)" below. Don't re-close this gap on your own initiative;
follow whatever the user says next.

**v0.2.50 — Phase 4-A built (F7 Phase 4b's read-only classification step — "Find Flattenable Link
Chains"). Suite 328 green (+19 new tests). NEEDS LIVE-BLENDER VERIFY, and one DNA read-path is
genuinely unconfirmed (see below) — treat this as a first draft, not trusted output yet.**
- **New `core/linkchain.py`** (bpy-free where possible, split read/classify per the project's
  standing pattern): (1) **pure graph layer** — `find_chains`/`multihop_routes` over the EXISTING
  `core.depscan.DepGraph` (no new scanning infrastructure, just a new query over what Check Link
  Chain already builds) — finds every file a root reaches via 2+ hops, keeping a same-target direct
  path alongside it when one also exists (the real PSM_Stage→human_bundle-directly-AND-via-People1
  case). (2) **posing-mechanism census** — `read_object_posing` (BAT, on-demand, reads the CURRENT
  file's own local Object blocks a second time — cheap, it's the 227 MB root file, not the 60 GB
  closure) + pure `classify_posing` → `override_with_transform` / `modifier_driven` / `unclassified`,
  per the plan's own 3-bucket design. `build_chain_report` combines both into one new report,
  feature key `"f7chain"` ("Link Chain Analysis").
- **DNA paths used:** `(b"id", b"override_library")` (Library Override pointer — already confirmed
  against REAL production files in the 2026-06-24 design session, per that session's notes further
  down this file) and `(b"modifiers", b"first")` (presence-only, deliberately not modifier-TYPE-
  specific — Phase A only needs the 3-way bucket, not which modifier). Both paths were re-confirmed
  this session to resolve without exception against the `tests/fixtures/linkproj` fixture (an object
  with neither signal) — but **no fixture exists with an ACTUAL override or modifier**, so the
  override/modifier-PRESENT branch of `read_object_posing` is structurally sound but has never been
  exercised against real data with this exact code. `classify_posing` itself (the pure decision
  logic) IS fully unit-tested with crafted inputs — only the BAT *read* side carries this caveat.
- **Known, deliberate gap, not guessed at:** a flagged override is NOT yet attributed back to WHICH
  library in a multi-hop chain it overrides (that needs the override's `reference` pointer — an
  unconfirmed DNA path). So this session's report shows two PARALLEL findings (the chains, and the
  overridden-objects census) side by side, not yet cross-referenced into "object X is flattenable
  BECAUSE it routes through chain Y." That cross-reference is the natural next increment, not built
  this session.
- **Wired:** `ops/linkchain.py::ASSETDOCTOR_OT_scan_link_chains` (`ModalProgressMixin`, reuses
  `depscan.scan_recursive_steps` then runs `classify_objects` on the root) → registered in
  `ops/__init__.py`; `"f7chain"` added to `report_store.FEATURES`; 3 new category titles in
  `core/tree._CATEGORY_TITLES` (`multihop_route`/`posing_override`/`posing_modifier`); new button
  "Find Flattenable Link Chains" in the Analyze panel (`ui/panels.py`, icon `"LINKED"` — reused an
  icon already drawn elsewhere in this file rather than guessing a new enum, since a bad icon string
  throws at draw time and kills the whole panel); new step in `core/analyze_steps.STEPS` (now 13
  entries, `tests/test_analyze_steps.py`'s count assertion updated to match) so "Analyze All" runs it
  too.
- **NEEDS LIVE-BLENDER VERIFY:** run "Find Flattenable Link Chains" on a real multi-hop file
  (`PSM_Stage_v5.2.blend` is the known real case — reaches `human_bundle.blend` both directly and via
  `People1_v5.1.blend`) and confirm: the multi-hop route shows up with both paths noted; the button
  doesn't error; and — most important, since it's unverified — confirm at least one ACTUAL Library
  Override object on that file gets read without a Python exception (an override read going wrong
  would likely surface as an `AttributeError`/`KeyError` in the Info log, not a crash, since this is
  plain BAT field access, not bpy mutation — but it's never been tried against real override data).
- **Not yet committed** — stacks on top of the still-uncommitted v0.2.38→0.2.49 diff (commit decision
  unchanged: one commit, after Phase 5 docs review, per the standing plan).

## Phase 3 feedback log — superseded by the entry further up this file (TRIAGED 2026-06-25)

This was the original placeholder stub, written before any feedback had arrived this session — see
the (now-triaged) log near the top of the file for the actual items and their disposition.

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.49, 2026-06-25) — Phase 3a sign-off + 3b/3c scope-cut

**Phase 3a got the user's actual sign-off this session (2026-06-25, 4 concrete decisions via
AskUserQuestion — not just my own recommendation), and Phase 3b/3c were immediately built for the
first 2 of the 5 named sections ONLY, by explicit user request** ("I would like to get the Title,
Current File Data and Analyze sections roughed in, so I can see what's left, and propose an overall
design for the remaining"). Don't re-litigate any of this — pick up from here:
1. **Live-verify v0.2.49 first** (see that version's entry below for the full checklist) — this
   touched almost every box in the main panel (stripped a trigger button out of each), so it's the
   riskiest change since Batch 5's N-panel retirement.
2. **Then design the remaining 3 sections** — Reporting & Recommendations (today's generic Reports
   selector/tree, formalized as its own section), Cleanup & Fixes (every "Apply"/"Merge
   Selected"/"Relink Selected" button now left stranded in its old box once Find moved to Analyze —
   the user's own framing: "I suspect that each of the Find buttons will create an output with
   actionable data. The 'Fix' buttons will then be part of that output"), Info & Utilities (today's
   Utilities child panel + the doc-help icon currently stuck in the title header). **Cleanup & Fixes
   ordering: user chose risk-grouped** (cheap/reversible/well-backed-up fixes first — Relink
   Selected, Reconnect Selected, Normalize; bulk/structural ones last — Make Local, Dedup & Remap,
   Instance & Merge, Scan + Purge Orphans) **over mirroring Analyze's order 1:1** — and noted "some
   of the analysis information will turn into background information, but we can move that around as
   the design matures," i.e. treat this as a draft to iterate on, not a final layout.
3. **Still-open from Phase 1, deliberately deferred, not forgotten:** the literal crash-stack names
   (`character1_cs.012`/`cs_grp.012`/`Mesh_006_001`/the crash3 `ParticleSettings` names) still
   haven't been specifically reconnected on the real file.
4. **Commit decision unchanged:** keep accumulating uncommitted, commit as ONE commit only once
   Phase 5 (documentation review) is also done.

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.49, 2026-06-25) — read this first

**v0.2.49 — Phase 3a signed off (4 real user decisions, not just my recommendations) + Phase 3b/3c
built for Current File Data + Analyze ONLY, by explicit user scope-cut. Suite 309 green (net zero:
−4 removed `test_missingdata.py` tests, +4 new `test_analyze_steps.py` tests).**

**The 4 sign-off decisions (AskUserQuestion, 2026-06-25):**
1. Scan Deps / Analyze / Project Link Map naming → **rename to scope-revealing names** (not add
   captions, not leave as-is).
2. Find/Apply split-box traceability → **deferred** — user wants Current File Data + Analyze roughed
   in FIRST so they can see what's left before designing how Cleanup & Fixes echoes back to Analyze.
   Their own words: "I suspect that each of the Find buttons will create an output with actionable
   data. The 'Fix' buttons will then be part of that output."
3. The redundant "Find Missing Data-blocks" vs "Find Reconnectable Data-blocks" → **delete it, fold
   into Reconnect** (not keep-as-summary, not keep-both).
4. Cleanup & Fixes button ordering → **risk-grouped** (not mirror-Analyze's-order) — but flagged as a
   draft, not final ("we can move that around as the design matures").

**Built this session (Phase 3b/3c, scoped to decisions 1+3 plus the two sections the user asked to
see roughed in):**
- **Deleted the redundant "Find Missing Data-blocks" end-to-end** (decision 3): removed
  `ASSETDOCTOR_OT_scan_missing_datablocks` (`ops/datablock_inspect.py`); `core/missingdata.py` now
  keeps only the `MissingBlock` dataclass (still used by `ops/datablock_reconnect.py`) — deleted
  `group_by_library` + `build_missing_datablocks_report`; deleted `tests/test_missingdata.py` (4
  tests, all for the removed functions); removed `("f7miss", "Missing Data-blocks")` from
  `ops/report_store.FEATURES` and the now-orphaned `"missing_datablock"` category title from
  `core/tree._CATEGORY_TITLES`. `ASSETDOCTOR_OT_scan_all_missing` ("Find All Missing") now calls
  `scan_reconnect_targets` instead of the deleted operator — same two-checks-at-once convenience,
  just pointed at the surviving (actionable) scan.
- **New `core/analyze_steps.py`** (bpy-free, +4 tests, suite 309): `AnalyzeStep` + the ordered
  `STEPS` tuple (12 entries: Check Link Chain, Audit This File, Find Duplicate Data-blocks, Find
  Broken Links, Find Reconnectable Data-blocks, Find Missing Textures, Find Duplicate Materials,
  Find Duplicate Geometry, Find Orphans, Find Duplicate Content, Find Resolution Variants, Analyze
  Memory/Disk) + `step_by_key`. Deliberately excludes Project Link Map/Safe to Delete (need a
  user-supplied path first) and Profile Render (an actual render — too slow/disruptive to fire
  unattended; stays a manual-only button in the Analyze panel).
- **New `ops/analyze_all.py`** — `ASSETDOCTOR_OT_analyze_all` (`ModalProgressMixin`, the "Analyze
  All" sequencer): dispatches each `STEPS` entry via `getattr(bpy.ops, category)` + `getattr(...,
  name)(**kwargs)` (a pure dispatcher — every step's own report-stashing/UI-state logic runs
  unchanged, exactly as if its own button had been clicked), rebuilding a WM `assetdoctor_analyze_
  steps` collection (`pending`→`running`→`done`/`error` per step) the panel reads for per-step icons.
  A step that raises is caught + logged (`error` status) so one bad step doesn't stop the rest.
- **New `ASSETDOCTOR_PG_analyze_step`** PropertyGroup (`ui/panels.py`) + WM `assetdoctor_analyze_
  steps`/`_index` (registered in `__init__.py`, alongside every other WM collection).
- **Two new native collapsible sub-panels** (`bl_parent_id=ASSETDOCTOR_PT_scene_deps`, same pattern
  as the Batch-5 legacy panels), inserted at `bl_order` 0/1 — every legacy panel's `bl_order` shifted
  +2 to make room (Make Local 0→2, Materials 1→3, Orphans 2→4, Geometry 3→5, Resource Analyzer
  4→6, Utilities 5→7):
  - **`ASSETDOCTOR_PT_current_file_data`** ("Current File Data") — the file name + dirty-warning +
    libraries-at-a-glance line, moved verbatim out of the parent panel's `draw()` into its own
    collapsible section (content unchanged; just promoted per the user's "all 5 sections must be
    collapsible" requirement). Expanding it with face/vert/texture-size counts stays deferred.
  - **`ASSETDOCTOR_PT_analyze`** ("Analyze") — the "Analyze All" button + per-step status icons,
    then every "look for problems in the CURRENT file" trigger in one place: **Check Link Chain**
    (was "Scan Deps") / **Audit This File** (was bare "Analyze") — decision 1's scope-revealing
    rename — Find Duplicate Data-blocks, Find Broken Links, Find Reconnectable Data-blocks, Find All
    Missing, Find Missing Textures, Find Duplicate Materials, Find Duplicate Geometry, Find Orphans,
    Find Duplicate Content, Find Resolution Variants, Analyze Memory/Disk, Profile Render (manual
    only, excluded from the sequencer). **Map a Folder** (was "Project link map") + Safe to Delete
    moved to the bottom of this section per the user's original ask (different scope — an arbitrary
    folder, not the current file).
- **Every box that used to mix a Find trigger with its results+Apply UI lost ONLY the trigger** —
  the populated list/report still draws exactly where it always has, since all this state lives on
  shared WM/Scene properties regardless of which button fired the operator: Overrides & Dups (`_draw_
  datablock_dups`), Broken links & missing data-blocks box, Datablock Reconnect (`_draw_reconnect`),
  Missing Textures (`_draw_missing_textures`), Duplicate Materials/Textures (`_draw_duplicate_
  textures`), and the legacy Materials/Orphans/Geometry/Resource Analyzer child panels (each now
  keeps only its Apply-side button: Dedup & Remap, Scan + Purge Orphans, Instance & Merge — Resource
  Analyzer keeps only its results display, both its buttons moved to Analyze). **Examine Library and
  Path Normalization are UNTOUCHED** — neither was in the user's original Analyze-All list, so
  neither moved; they stay exactly where they were, full Find+Apply box intact, for the Cleanup &
  Fixes design pass to redistribute later.
- All edits syntax-checked via `ast.parse` (ops/ui code isn't pytest-covered per the standing
  architecture rule); `tests/smoke_utils.py`'s sub-panel `bl_parent_id` check extended to include
  the two new panel ids. Manifest bumped to 0.2.49.

**NEEDS LIVE-BLENDER VERIFY (the riskiest change since Batch 5's N-panel retirement — RESTART
Blender, don't Reload Scripts, per the standing structural-change rule):**
- "Current File Data" and "Analyze" appear as the FIRST two collapsible sub-panels under AssetDoctor
  (above Make Local), each with a native collapse triangle.
- Every renamed button still does what its old name implied: Check Link Chain = old Scan Deps; Audit
  This File = old bare Analyze.
- Clicking each Find-* button in Analyze still populates the SAME box/list it used to (e.g. Find
  Broken Links in Analyze → the "Broken links & missing data-blocks" box below still fills in).
- "Analyze All" runs all 12 steps in order, shows a per-step icon (pending→running→done, or error if
  a step's own operator reports a problem), and ESC/Pause work mid-run (inherited from
  `ModalProgressMixin` — never exercised by a 12-step chained dispatch before).
- The legacy Materials/Orphans/Geometry/Resource Analyzer panels now show ONLY their Apply button (no
  more "(Report)" sibling) — confirm that doesn't read as "missing a button," just relocated.
- "Find All Missing" (now Broken Links + Reconnectable Data-blocks) still reports a sane combined
  message.

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.48, 2026-06-25)

**v0.2.48 — three real bugs from live-testing v0.2.44's reconnect/click-to-select fixes, fixed;
PHASE 2 NOW FULLY COMPLETE (user: "Work on anything still to do in Phase 2a, then start Phase 2b
immediately"). Suite 309 green.**

**Bug 1 — click-to-select STILL didn't focus the material for a missing-texture row.** The v0.2.44
fix (set `active_material_index` + `outliner.show_active()`) was insufficient — confirmed live, not
just theorized. Root cause confirmed: `show_active()` is fundamentally tied to the ACTIVE OBJECT;
Blender has no public API to scroll-to/highlight an arbitrary non-object ID in ANY display mode.
**Fix:** `ops/report_store._reveal_in_outliner` now ALSO sets `SpaceOutliner.filter_text` (the
Outliner's own name-search box) to the connecting material's name (or the clicked target's own name
if no material was found) on every open Outliner, for any click that isn't a direct Object pick —
this narrows the visible rows to matches regardless of display mode, the only mechanism that
actually works mode-independently. **This mutates persistent Outliner UI state** (the filter stays
set until cleared) — the operator's status message now says "Outliner filtered to 'X'" so it's never
a silent surprise.

**Bug 2 — Find Reconnectable Data-blocks "did not autoselect most of the materials."** Root cause:
this project's own long-documented disease — the SAME library (e.g. materialMaster.blend) gets
linked into this file via MULTIPLE different path strings (absolute vs `//`-relative, slash
direction, a since-moved folder), and Blender treats each as a separate `Library` datablock. The
v0.2.42 auto-default only checked a missing block's OWN stored library path — if that particular
copy's path string was a STALE duplicate (even though the SAME file resolves fine via a DIFFERENT
library entry elsewhere in the very same file), auto-matching silently didn't fire for it. **Fix:**
new `core.reconnect.find_sibling_library(missing_path, resolving_paths)` (+5 tests) — when a group's
own path doesn't resolve, look for exactly one OTHER already-loaded library (any that resolves) with
the SAME basename and use it instead; ambiguous (2+) or no match → still falls back to a manual pick
(never guessed). Wired into `ops/datablock_reconnect._populate_missing_blocks` (also fixed a real bug
caught before it shipped: the original draft only applied the per-library auto-source computation to
the FIRST block of each group, leaving every other member of the same group unset — caching the
computed source per-library, not just the "found" flag, fixes this).

**Bug 3 (not really a bug — a missing differentiation) — "after reconnecting they still showed
missing. It did not differentiate between data-blocks that were missing in linked libraries."**
This is the v0.2.43 transitively-missing safety check working AS INTENDED (refusing to fake-fix a
candidate that's itself unresolved further upstream) — but the Reconnect list gave no VISIBLE,
persistent signal of WHY, so it looked indistinguishable from "just hasn't been matched yet" or a
plain bug. Two real UI/state gaps fixed:
- `ASSETDOCTOR_PG_missing_block` gained `library_found` (set at scan time: does this group's own
  library path resolve ANYWHERE in this session — own path or a sibling match) and a new `confidence
  = "transitive"` value (set by `reconnect_selected` AFTER an apply attempt catches a transitively-
  missing candidate; survives the post-apply list rebuild via a `(collection, name)` replay, since
  the rebuild normally resets every row's confidence to "none").
- `ui/panels._draw_reconnect`: a group whose library is found NOWHERE in this session (not even via
  sibling-match) now shows an ERROR icon + "library not found anywhere in this session — pick a
  source .blend manually" instead of the generic "no source picked yet" — distinct from the normal
  case. A row stuck in the "transitive" state shows "⚠ missing upstream too" instead of going blank.
  Group header now reports "{matched} suggested" and "{stuck} stuck (missing upstream too)"
  separately instead of lumping them into one "suggested" count.
- **Real implication unchanged from v0.2.43:** rows that land in "transitive"/stuck genuinely can't
  be fixed via Reconnect — the source library itself doesn't have valid data for them either; the
  real fix is finding/relinking whatever further-upstream library it's missing (Scan Deps / Find
  Broken Links on THAT library directly).

**PHASE 2 — NOW FULLY COMPLETE.** 2a (shared file-picker helper): besides the two files done last
session (`ops/relink.py`, `ops/datablock_reconnect.py`), converted the rest this session —
`ops/image_relink.py` (4 of 5: `search_textures_folder`, `suggest_fuzzy_matches`,
`suggest_from_blend` + `resolve_existing_file`, `point_group_at_folder`; `relink_pick_texture`
deliberately LEFT UNCONVERTED — it has a genuinely custom `invoke()` that pre-fills the browser path
from an existing target, so the mixin wouldn't save anything), `ops/examine_library.py`
(`examine_pick_source` + `resolve_existing_file`), and two MORE instances the original plan's file
list didn't name but matched the exact same boilerplate shape: `ops/report_store.py`
(`export_report`) — `ops/scan_folder.py`'s `invoke()` was checked and correctly left alone (its
file-picker fallback is conditional on no folder being pre-set already, a genuinely different shape,
not pure duplication). **2b** (consolidate the generic `bpy.data` walk): new `ops.datablock_inspect.
_iter_all_blocks()` (the shared `(attr, block)` walk with no predicate); `_iter_missing_blocks` now
filters it for `is_missing`, and `ops.examine_library._iter_library_blocks` (imports across files,
no circularity) filters it for `block.library is library` — same walk, two predicates, zero
duplication. **2c** was already done at v0.2.39. All three confirmed behavior-preserving (suite 309,
exactly +5 from the new `find_sibling_library` tests; ops/ui changes verified via `ast.parse`, not
pytest-covered per the standing architecture rule). **NEEDS live-Blender verify** on all of the
above — every change this session touches code the user is actively testing.

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.47, 2026-06-24) — read this first

**v0.2.47 — "Find .NNN" DELETED (user confirmed after the redundancy investigation below: "Delete
it").** Removed end-to-end, not just the button:
- `core/imagededup.py`: deleted `plan_dup_merges` (kept `plan_content_merges`, `ImgInfo`,
  `MergePlan`/`FamilyConflict`, `build_dedup_report`, `removable_count`, `victims_for_keeper` — all
  still needed by Find Content Dups); updated the module docstring + the `clean` Finding's message
  ("✓ No duplicate image datablocks" — dropped the now-inaccurate ".NNN" qualifier).
- `tests/test_imagededup.py`: removed the 6 tests that only covered `plan_dup_merges`; kept/adjusted
  the content-merge + `removable_count`/`build_dedup_report`/`victims_for_keeper` tests. Suite
  **310 → 304** (exactly the 6 removed, same verification pattern as the Phase 0 dead-code pass).
- `ops/image_dedup.py`: deleted `_family_member_infos`, `_populate_dup_families`, and the
  `ASSETDOCTOR_OT_scan_dup_textures` operator entirely. `ASSETDOCTOR_OT_merge_dup_selected` no
  longer branches on a scan "mode" (there's only one scan now) — always clears the list and prompts
  "Re-run Find Content Dups" after a merge, which is what the CONTENT branch already did.
- `assetdoctor_dup_scan_mode` WM prop removed (`__init__.py` registration + unregister list) — it
  had become write-only (no remaining reads) the moment the mode branch collapsed to one path.
- `ops/__init__.py`: removed the import + `REGISTER_CLASSES` entry for the deleted operator.
- `ui/panels.py`: removed the "Find .NNN" button from the Duplicate Materials/Textures box (Find
  Content Dups is now the row's only button) + updated the section's docstring.
- All deletions verified via `ast.parse` (ops/ui code isn't pytest-covered) + the full suite green
  at 304. **NEEDS live-Blender verify**: the Duplicate Materials/Textures box should show only
  "Find Content Dups" now; running it + Merge Selected should behave exactly as before (same
  underlying content-merge logic, just no more separate fast-path button).

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.46, 2026-06-24) — read this first

**Phase 1 item (b) CONFIRMED DONE (2026-06-24, user live-test):** Scan Deps run against the real
multi-file chain (PSM_Stage_v5.2/People1/human_bundle/materialMaster) "works fine, except for the
look of the report" — the formatting gap is ALREADY tracked (the report-formatting pass, LIVE-TEST
FEEDBACK BATCH 2 item #2/#10, further down this file — now also covering f9's missing Summary line
from v0.2.45). No new work needed for this item; Phase 1's classifiers (duplicate-ref/inconsistent-
path/cycle detection) are confirmed correct on real production data. **Phase 1's only remaining
named item:** reconnect the literal crash-stack names (`character1_cs.012`/`cs_grp.012`/
`Mesh_006_001` from crash.txt; the `ParticleSettings` names from crash3 —
`Eyebrows_`/`Eyelashes_…V2`/`fh_sideburns_low`/`hair_side_fade_new`/`HG_Side_Lines`) — not yet
confirmed. Everything else fixed this session (crash3 diagnosis, dry-run-crash-detection,
auto-suggest-library, transitively-missing-reconnect bug, click-to-select-material,
linked-missing-textures visibility) already counts as Phase 1 triage work, done.

**v0.2.46 — Phase 2 STARTED (user: "Start Phase 2").** Phase 2a (shared file-picker/proposal-
staging helper) begun per the plan's own incremental rule — convert one file, verify, spot-check,
then continue: new `ops/pickers.py` (`FilePickerMixin` — the identical `invoke()` body every
Pick-a-file operator in this addon repeats; `resolve_existing_file(filepath)` — the identical
"normalize + check exists" validation several of them repeat). Converted so far: `ops/relink.py`'s
`ASSETDOCTOR_OT_relink_pick_file` (mixin only — this one stages a target even when it doesn't yet
exist, via its own `has_candidate` flag, so it deliberately does NOT use `resolve_existing_file`'s
reject-if-missing contract) and `ops/datablock_reconnect.py`'s `ASSETDOCTOR_OT_reconnect_pick_
source` (mixin + `resolve_existing_file`, exact behavior-preserving substitution). Both are
zero-behavior-change extractions (same `invoke()` body, same validation logic, just shared instead
of repeated) — suite still 310 (ops/*.py isn't pytest-covered per the standing architecture rule;
syntax-checked via `ast.parse`). **STILL TO DO in 2a:** `ops/image_relink.py` (5 separate
file/folder-picker operators — the biggest remaining chunk) and `ops/examine_library.py`'s per-row
picker, then **2b** (consolidate `_iter_missing_blocks`/`_iter_library_blocks`). **NEEDS a live-
Blender spot-check on the two converted features before continuing** (Find Broken Links → Pick
Library File; Find Reconnectable Data-blocks → Pick Source .blend) — per the plan's own rule, not
skipped just because the diff is small.

**Investigated (2026-06-24, user question): is "Find .NNN" redundant with "Find Content Dups"?**
Confirmed via code, not guessed — both are in `ops/image_dedup.py` and call the EXACT SAME
`_fingerprint(img)` function (dimensions + file/packed-data hash), and both populate the SAME
`wm.assetdoctor_dup_families` list + the same `f6dup` report. The only real difference: **"Find
.NNN"** (`scan_dup_textures` → `core.imagededup.plan_dup_merges`) only ever hashes images that
ALREADY share a `.NNN` name-family (`_family_member_infos` pre-filters via
`datablock_graph.duplicate_families` before fingerprinting anything) — cheap, synchronous,
no-modal. **"Find Content Dups"** (`scan_content_dups` → `plan_content_merges`) hashes EVERY local
file-backed image regardless of name — slower (it's the one with the progress-bar modal), but
since it uses the IDENTICAL fingerprint function over a strict superset of images, **any group
"Find .NNN" finds, "Find Content Dups" finds too** — confirmed, not assumed (same hash, broader
search space, same merge-grouping logic underneath via `core.datablock_dedup.plan_merges`). So the
user's hypothesis holds: **"Find .NNN" is functionally redundant** — its output is always a subset
of what "Find Content Dups" already produces. **The one tradeoff worth knowing before deleting:**
"Find .NNN" is the FAST, synchronous, no-progress-bar path (cheap because it skips hashing most of
the file's images); "Find Content Dups" must hash every local image, which on this project's
multi-GB files is the reason it has a `ModalProgressMixin` progress/pause/ESC UI at all — deleting
"Find .NNN" means there's no more fast path for the common ".001/.002 litter" case, only the
heavier always-hash-everything scan. Asked the user to decide given that tradeoff before deleting
(removing an operator + its UI box + report wiring is not easily reversible).

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.45, 2026-06-24) — read this first

**v0.2.45 — real undercounting bug found via live testing: "List Missing Textures" found 9 missing,
but the same file's Dry-Run Render found 144 missing images at render time.** User correctly
suspected linked images were the gap and asked that they be surfaced even though nothing can be
done about them in the current file. Confirmed by code: `ops/image_relink.py::_gather_images`
deliberately skips every `img.library is not None` Image (the existing docstring: "linked image ->
fix in its source file, not here") — so "List Missing Textures" was ONLY ever counting LOCAL
images, while a real render evaluates every image regardless of who owns it. **Built — a new
READ-ONLY companion list, not a fix-it action (these can't be relinked from this file; the source
library owns that path):**
- `ops/image_relink.py::_gather_linked_missing_images()` — walks linked Images, resolves each via
  `bpy.path.abspath(stored, library=img.library)` (relative paths on a linked Image are relative to
  ITS OWN library file, not the current one — using plain `bpy.path.abspath` here would have
  silently mis-flagged valid paths), reports ones that don't resolve.
  `_populate_broken_images` now ALSO fills a new `assetdoctor_linked_missing_imgs` WM collection
  from it (existing local-only counts/contract unchanged).
- `ui/panels.py`: `ASSETDOCTOR_PG_broken_lib` gained a `library` field (used only by these new rows;
  every existing consumer of this shared PG is unaffected). The Missing Materials/Textures header
  now also shows "N linked" when present; a new collapsible **"Linked — fix at the source library"**
  sub-section (grouped by library, mirrors the existing Possible Matches shape) lists each name +
  its material, with NO checkbox/target/file-picker — visibility only, by design.
- `ASSETDOCTOR_OT_scan_broken_textures`'s report message now mentions the linked count too.
- Suite still 310 (this is bpy-dependent ops/ui code — per the standing architecture rule it can't
  be pytest-covered; syntax-checked via `ast.parse`). **NEEDS live-Blender verify**: re-run List
  Missing Textures on the same file — header should show both counts, and the new collapsible
  section should list the ~135 linked-but-missing textures grouped by library, read-only.

**Phase status, answering the user's direct question (2026-06-24) — from the actual plan at
`C:\Users\Rick\.claude\plans\declarative-booping-ripple.md`:** 5 phases total. **Phase 0 (dead-code
removal) is the only one FULLY complete** (v0.2.37, committed `9cef3a4`). **We are still inside
Phase 1** ("wait for live-test feedback, then triage" — explicitly NOT new feature work, just
fixing what the user's live testing surfaces) — everything from crash3's diagnosis through this
v0.2.45 fix IS Phase 1 work, exactly as scoped. Phase 1's own two NAMED concrete items are **not yet
done**: (a) running Find Missing Data-blocks + Datablock Reconnect against the real file
prioritizing the crash-stack names (`character1_cs.012`/`cs_grp.012`/`Mesh_006_001` from crash.txt,
plus the `ParticleSettings` names from crash3); (b) running Scan Deps against the real
PSM_Stage/People1/human_bundle multi-file chain. Phases 2 (code-review cleanup), 3 (UX/panel
review), 4 (Link Chain Flattening), and 5 (docs) have **not started** (one small Phase-2 sub-item,
2c, was done early/opportunistically back at v0.2.39 — generalized click-to-select — but that's the
only exception). The plan's own exit rule for Phase 1 is explicit: "**Resume the plan at Phase 2
once the user signals this pass is done**" — that's the user's call to make, not mine to assume.

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.44, 2026-06-24) — read this first

**v0.2.44 — click-to-select gap fixed: a missing-texture row now highlights the Material that uses
it, not just the object.** User report (live-testing Find Missing Data-blocks): clicking an Object
row already worked (selects + reveals its container in the Outliner), but clicking a missing
TEXTURE (Image) row, with the Outliner in **Blend File** display mode, did not highlight the
Material it came from. Root cause: `ASSETDOCTOR_OT_select_datablock._find_objects` walked
`bpy.data.user_map()` all the way up to the using OBJECTS (to select them) but threw away any
Material it passed through along the way — the existing "highlight the active material slot" logic
only ever fired for a DIRECT Material-type click, never for something deeper like an Image two
hops below it. **Fixed:** `_find_objects` now returns `(objects, materials)` — any Material
encountered during the walk is collected alongside the objects, so `execute()`'s slot-highlighting
now fires for ANY target that resolves through a Material (Image, Texture, etc.), not just a literal
Material click. **Honest caveat on the Blend File-mode half of the report:** `bpy.ops.outliner.
show_active()` (the actual "reveal" call) is fundamentally tied to the ACTIVE OBJECT — Blender has
no public API to scroll-to/highlight an arbitrary non-object ID (a Material or Image) directly in
Blend File / Orphan Data mode, which lists all datablocks flat by type, independent of any object.
Setting the active material slot (this fix) should help if Outliner **Sync Selection** is enabled
(global active-material state, not view-layer-scoped) — but whether Blend File mode actually shows
that highlight is genuinely uncertain without live-testing (can't be checked headlessly, same
caveat as every other Outliner-behavior question in this project). **If Sync Selection doesn't pick
it up either, the next lever is `SpaceOutliner.filter_text`** (the Outliner's name-filter field,
works in every display mode including Blend File) — but that mutates persistent Outliner UI state
(narrows what's visible until cleared), which is a real intrusiveness trade-off NOT made without
the user's go-ahead first ([[feedback-suggest-better-designs]]) — flagged here, not built. **NEEDS
live-Blender verify**: click a missing-texture row again with Outliner Sync Selection ON, in both
View Layer and Blend File display modes, and report whether the material highlight now shows.

**Documented, not built — Dry-Run Render (f9) is missing a top Summary line.** User ran the real
Dry-Run Render to completion (~9 minutes, no crash this time): 45,016 render warnings, 11,542 render
errors, 144 missing images (render-time), each its own collapsible category row but no aggregate
line above them. Folded into the ALREADY-PLANNED "report formatting" pass (LIVE-TEST FEEDBACK BATCH
2, item #2/#10, further down this file) with this as the concrete example — see that section for
the implementation note. Not built this session (deliberately deferred to whenever that pass is
picked up, per the user's own framing).

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.43, 2026-06-24) — read this first

**v0.2.43 — a REAL Reconnect bug found via live testing immediately after v0.2.42 shipped (same
session): "successfully reconnected" data-blocks reappeared as missing right after Save +
requery.** User's exact repro: Find Reconnectable Data-Blocks → pick source .blend → Reconnect
Selected (reported success) → Save .blend → Find Reconnectable Data-Blocks again → (almost) all of
the just-"reconnected" rows are missing again. **Root-caused from code + this project's own prior
findings, not guessed:** `core/datablock_links.py`'s 2026-06-24 DNA discovery already documented
that a linking file stores what it links as a generic `ID` placeholder stub — so when a SOURCE
.blend (e.g. `materialMaster.blend`) is itself a few hops downstream of ANOTHER library for some of
its own content, and THAT further-upstream library isn't available either, materialMaster.blend's
OWN on-disk copy of that name is just another unresolved placeholder, not real data. This project's
memory already flagged this exact disease on this exact library ("materialMaster linked 11×, ~18
missing botaniq libs" — see the "MAGENTA = MISSING TEXTURES" investigation further down this
file). `reconnect_selected` (`ops/datablock_reconnect.py`) never checked whether the candidate it
just linked via `bpy.data.libraries.load(source, link=True)` was ITSELF `is_missing` before
remapping onto it — it would happily `user_remap` the broken placeholder onto ANOTHER, equally
broken placeholder, increment `reconnected`, and report success. The data didn't get fixed; it just
changed which broken name it was pointing at, with no difference in `is_missing` status — so the
very next scan (or, per the user's repro, after a Save) finds the same is_missing condition and
reports it again. (Save itself isn't implicated — the underlying placeholder state was never
actually resolved in the first place; the user's repro just happened to interleave a Save before
noticing.) **Fix:** after linking, check `getattr(linked, "is_missing", False)`; if true, DON'T
remap (that would trade one missing name for another and falsely report success) — skip with a
clear "is itself unresolved (missing further upstream) — not actually fixed" warning, and remove
the now-orphaned still-missing block we just linked (avoids it cluttering `bpy.data` on every
retry). New `transitively_missing` counter surfaced in the operator's result message ("N
candidate(s) were themselves unresolved in the source .blend... that library doesn't actually have
this data either"), distinguishing "we didn't fix these, and here's why" from a silent false
"reconnected" count. **This explains "(almost) all" reappearing** (most of materialMaster.blend's
texture names ARE transitively missing from botaniq) **and the ~1% that stuck** (the few names
materialMaster.blend genuinely owns locally). **Real implication for the user's actual file:** the
true fix for these textures isn't Datablock Reconnect at all — it's finding/relinking whatever
further-upstream library (likely a botaniq-adjacent texture library) materialMaster.blend itself is
missing, via Scan Deps / Find Broken Links on materialMaster.blend directly. **NEEDS live-Blender
verify**: re-run the exact same repro — Reconnect Selected's message should now show some
candidates flagged "themselves unresolved" instead of silently reporting full success, and ONLY
the genuinely-fixed ones should survive a Save + requery.
- **Documentation icon — confirmed fine, no action.** User confirmed the doc/help icon (reverted to
  the plain right-aligned placement in v0.2.40 after the v0.2.38/39 edge-pin attempt overlapped the
  title) now reads correctly and asked to leave it as-is. Nothing to change.

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.42, 2026-06-24)

**User real-world feedback this session (live testing on the actual `PSM_Stage_v5.2.blend`):**
(1) the v0.2.41 30-minute Dry-Run Render timeout fix worked — the render ran past the old 300s
limit. (2) Reconnect/select/reconnect workflow tested successfully WHILE the dry-run render ran in
its background subprocess. (3) **A THIRD crash**, user attached `PSM_Stage_v5.2.crash3.txt` —
diagnosed below. Also a concrete feature request: "Find Reconnectable Data-blocks" should
automatically check the original (broken-block's-stored) library for a match, not require a manual
Pick-Source round-trip when that library is sitting right there.

**v0.2.42 — crash3 diagnosed (a FOURTH distinct Blender-core code path, same root disease) +
two fixes: dry-run-render crash detection (real bug, was silently masking a crash as "no warnings")
and auto-suggest-from-original-library (the user's feature request). Suite 310 green.**
- **Crash3 diagnosis — Blender core, NOT AssetDoctor, but in a NEW subsystem this time.** The
  attached backtrace is from the headless **Dry-Run Render subprocess** (main thread:
  `BPY_run_filepath` → `python_script_exec` → `screen_render_exec` → `RE_RenderFrame` →
  `BKE_scene_graph_update_for_newframe_ex` → depsgraph eval → `mesh_calc_modifiers` →
  `subdiv_to_mesh` → `bke::subdiv::eval_begin` → **OpenSubdiv's
  `StencilBuilder<float>::Index::AddWithWeight`**, `EXCEPTION_ACCESS_VIOLATION` reading address
  `0x7`) — a Subdivision Surface modifier evaluation crashing deep inside OpenSubdiv on a mesh with
  corrupt/degenerate topology. The file load logged the same disease as crash.txt and crash2.txt:
  **224 missing linked data-blocks**, prominently many `ParticleSettings` (`Eyebrows_`,
  `Eyelashes_…V2`, `fh_sideburns_low`, `hair_side_fade_new`, `HG_Side_Lines` — all from
  `human_bundle.blend`) plus dozens of missing skin/hair/teeth Images. A character whose hair/
  eyebrow particle systems reference missing `ParticleSettings` placeholders, combined with a
  Subsurf modifier somewhere in its modifier stack, is consistent with OpenSubdiv choking on
  degenerate/placeholder geometry it isn't null-safe against — Blender core not validating against
  missing-linked-data again, THIRD code path now (depsgraph relation builder in crash.txt → none,
  in crash2.txt the suspect was our own re-peek timing, since mitigated → OpenSubdiv subsurf eval
  here). **Same fix as before: this is data, not code** — running Find Missing Data-blocks +
  Datablock Reconnect against the real file (still the outstanding Phase-1 task, see further down)
  is what actually closes this, not a code change to OpenSubdiv. Importantly: this crash happened in
  the SEPARATE background Dry-Run Render subprocess, not the interactive session the user was using
  for Reconnect — the two crashed independently of each other, confirming the subprocess isolation
  is doing its job (the interactive session survived; only the throwaway render process died).
- **Real bug found BECAUSE of crash3: Dry-Run Render had NO way to detect its own subprocess
  crashing — would have silently reported "✓ no warnings found".** `ops/dryrun_render.py` polled
  `proc.poll()` until the subprocess exited but never checked `proc.returncode` — a crashed process
  still exits (with a crash-signaling exit code), so the while-loop ended normally and the code
  went straight to parsing whatever text made it into the log. The crash backtrace text doesn't
  reliably contain a recognizable "error"/"warning"/"missing image" line (Blender's crash handler
  writes the real backtrace to a separate `<filename>.crashN.txt` file, not necessarily stdout) —
  so a crashed render could read as completely clean. This directly violates the project's
  negative-output principle ([[feedback-negative-output]]) in the worst way: not "no visible
  result" but an ACTIVELY WRONG one. **Fixed:** `core/dryrun.parse_render_log` gained a
  `returncode: int | None = None` param — any non-`None`, non-zero code now adds a top
  `process_crash` Finding (severity error) pointing at the `<filename>.crashN.txt` Blender writes
  and naming missing-linked-data as this project's known cause, regardless of what the line-scan
  found (kept alongside other real findings, doesn't replace them). `ops/dryrun_render.py` now
  captures `proc.returncode` and passes it through, and its final status message says "crashed
  (exit code N)" instead of a generic warning count when nonzero. +5 tests, suite 310.
- **Built: auto-suggest from the original library (user's explicit ask).** Today, the FIRST time a
  missing-data-block group is scanned, the user had to click Pick Source .blend and browse to a
  file even when the answer was the group's own already-known (and already-resolving-on-disk)
  library path — the common "same library, block renamed/numbered at the source" case (e.g. wants
  `GeometricStichDesign`, library now has `GeometricStichDesign.001`). `ops/datablock_reconnect.py::
  _populate_missing_blocks` now auto-defaults a BRAND-NEW group's `source_blend` to its own stored
  library path (resolved via `bpy.path.abspath`) when that path exists on disk, and immediately
  calls `_enumerate_group` on it — so suggestions appear with zero clicks for that case. **Carefully
  scoped to not reopen the v0.2.40 crash-mitigation gap:** the auto-peek only fires for a group with
  NO remembered `source_blend` from a prior scan (a genuinely first-time peek) — a group that
  already has one (meaning it was likely already linked from for real) is untouched, same as before
  the v0.2.40 fix; re-peeking a just-really-linked-from library is the one scenario diagnosed as
  crash-risky, not a first peek (which succeeded twice for real, 54 then 207 reconnects, before the
  crash that prompted that mitigation). The manual Pick Source .blend flow (which already
  auto-suggests once a file is chosen) is untouched — covers the "I pick it myself" half of the
  ask, which already worked. `scan_reconnect_targets`'s report message now says "N auto-matched
  from their original library; pick a source for the rest" when applicable. **NEEDS live-Blender
  verify** (same caution as every Reconnect change — mutates nothing on its own, only auto-fills a
  picker + peeks, but exercises `_enumerate_group` automatically now where it previously didn't).
- **Not yet committed** — this is now FIVE sessions of uncommitted work stacked up (v0.2.38→0.2.42).
  Consider committing soon; ask the user how they want it split (or as one commit) before doing so.

**⏩ NEXT SESSION — start here.** Priority-ordered:
1. **Live-verify v0.2.42's two fixes** on the real file: re-run Dry-Run Render and confirm a
   crashed subprocess now reports "crashed (exit code N)" with a `process_crash` finding instead of
   looking clean; re-run Find Reconnectable Data-blocks on a file with missing data-blocks and
   confirm matches against the original library appear immediately, with no Pick Source click.
2. **Still the single highest-value outstanding task, unchanged across several sessions now:**
   run Find Missing Data-blocks + Datablock Reconnect against the real `PSM_Stage_v5.2.blend`,
   prioritizing `character1_cs.012`/`cs_grp.012`/`Mesh_006_001` (crash.txt's stack) AND the
   `ParticleSettings` names from crash3 (`Eyebrows_`, `Eyelashes_…V2`, `fh_sideburns_low`,
   `hair_side_fade_new`, `HG_Side_Lines`) — fixing these is what actually stops the crashes (three
   so far, three different Blender-core code paths, same root cause).
3. Everything else from the v0.2.41 punch list below still applies unchanged (Phase 3a UX proposal,
   commit decision, side quests) — not re-listed here, see immediately below.

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.41, 2026-06-24)

**v0.2.41 — Dry-Run Render's 300s timeout (Batch D, v0.2.33) was real-world too short for this
project's multi-GB, multi-library files; user hit it live.** `ops/dryrun_render._TIMEOUT_SECONDS`
300 → **1800 (30 min)**, matching this project's own documented load times for files this size
(People1 at 15GB took ~10+ min just to open+walk its block table in an earlier offline BAT probe —
this subprocess's wall-clock covers loading/resolving ALL linked libraries AND decoding their
textures on first access, not just the actual low-res/1-sample render call, which is fast once the
scene is in memory). **User asked: would Simplify + a texture-size limit help, or mask real
problems?** Analysis: NEITHER risks masking what this report tracks — a genuinely missing texture
file still fails to load (and still gets reported) regardless of any resolution clamp, since the
clamp only applies to images that load successfully; a lower particle-child render count changes
how many hair strands draw, not whether a broken particle-system reference errors. Given this
exact file's crash logs show dense human-character particle systems (Eyebrows_/Eyelashes_/
sideburns/hair particle settings), Simplify's child-particle reduction is a real, relevant lever,
not just a guess. **Built, default ON:** `core/dryrun.build_dryrun_script` gained a `simplify: bool
= True` param — sets `scene.render.use_simplify` + `simplify_child_particles_render = 0.0`, and
(Cycles only) `scene.cycles.texture_limit_render = '1024'`, each wrapped in `try/except` **inside
the generated subprocess script** (not here) since exact property names can drift across Blender
versions/engines — a wrong guess should no-op, not break the dry-run itself. Also added
`core.dryrun.format_elapsed` (e.g. `"14m07s"` past a minute — `"847s"` was unreadable once the
timeout grew) and used it for both the running-status line and the timeout error message. 4 new
tests, suite 306. **VERIFY:** re-run Dry-run Render on the real file — should no longer time out
at 5 minutes; if it's STILL too slow even at 30 minutes, the next lever is investigating whether
the bottleneck is genuinely render-side (textures) vs. load-side (multi-GB library resolution,
which Simplify/texture-limit can't touch since the script only runs after the file is already
open) — tell me which it looks like (Blender's own background console window, if visible, or the
elapsed-time curve, hints at this) and we'll dig further.

**⏩ NEXT SESSION — start here.** This pass (v0.2.37 → v0.2.41) is feature-complete and documented;
nothing left mid-edit. **Not yet committed to git** — `git status` shows the full v0.2.38–0.2.41
diff still uncommitted (manifest version, `ui/panels.py`, `ops/{datablock_reconnect,
dryrun_render,progress}.py`, `core/{datablock_graph,dryrun,missingdata}.py`, `__init__.py`, 3 test
files) — say the word when you want it committed (and whether as one commit or split).
Priority-ordered punch list for next session:
1. **Live-verify v0.2.38–0.2.41 first** (header fix, sticky result line, the Reconnect crash
   mitigation, the Dry-run timeout/Simplify change) — these are the freshest, least-trusted changes.
2. **Confirm or rule out the Reconnect crash mitigation specifically** — re-scan after an Apply and
   watch whether it still happens; that's the single highest-value data point right now.
3. **Resume Phase 1 of the review plan** (the original ask, still not done): run Find Missing
   Data-blocks + Reconnect against `PSM_Stage_v5.2.blend` prioritizing the 3 names literally in the
   FIRST crash's stack (`character1_cs.012`/`cs_grp.012`/`Mesh_006_001`) — fixing those resolves
   that crash and is the production-data proof for these tools.
4. **Phase 3a proposal — still NOT drafted, now has a much bigger input set to work from:** the 5
   named sections (Current File Data/Analyze/Reporting & Recommendations/Cleanup & Fixes/Info &
   Utilities), the Item 2 "Current File Data" content list (file size, texture size, object/face/
   vert/edge counts — resolved above), the Analyze-All step list with its one confirmed duplicate
   (Missing vs. Reconnectable Data-blocks) and two confirmed NON-duplicates (Duplicate Materials,
   Duplicate Geometry — don't delete those), the grouped-box-over-tree visual preference (Item 4),
   the LS.blend label-clarity + file-map click-to-select design gap, and the auto-reconnect-for-
   high-confidence proposal (Item 3b) awaiting a scope decision. All of it lives in this file under
   "UX Redesign — Major Panel Overhaul" + its "Item 2"/"Item 3"/Item-2-follow-up subsections —
   read those three before drafting 3a, the groundwork is done, just not yet turned into a single
   before/after layout proposal.
5. Still-open side quests, lower priority: Examine Library's deferred folder-wide search, the
   KEKey/shape-key half of duplicate-datablock merging, extending `set_result` (the new sticky
   feedback line) to the other plain-`execute()` mutating operators.

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.40, 2026-06-24) — read this first

**v0.2.40 — a REAL crash in OUR OWN code (not Blender-core, unlike the two earlier crash
diagnoses), a header-layout regression reverted, and a new sticky-result feedback line.**
User attached `PSM_Stage_v5.2.crash2.txt` from continued live testing (after successfully
reconnecting 54 then 207 data-blocks against `materialMaster.blend`/`human_bundle.blend`) — this
time the Python backtrace points straight at our code: `core/imagematch.py:64 (tokenize)` ←
`name_affinity:124` ← `core/reconnect.py:69 (suggest_reconnect)` ← `ops/datablock_reconnect.py:83
(_enumerate_group)` ← `:53 (_populate_missing_blocks)` ← `:101 (execute)`. **Root-cause analysis
(can't fully prove without live Blender — documented honestly):** read every line in that call
chain — `tokenize`/`name_affinity` are pure-Python string ops (lowercase, regex split, Jaccard) on
plain `str` values (Blender `StringProperty` always returns an independent copy, and the
peeked library names are plain strings from a `with bpy.data.libraries.load(...) as (data_from,
_data_to)` block that never assigns `data_to`) — nothing in that logic touches a dangling/freed
Blender ID, so a deterministic pure-Python bug looks unlikely. The more likely explanation: the
SAME exact call path had ALREADY run once successfully (the auto-refresh built into
`reconnect_selected`, line ~243) moments earlier; the crash hit on an immediate, manual re-click
of "Find Reconnectable Data-blocks" with no `bpy.data` changes in between. The one thing that WAS
different: `_enumerate_group` re-opens (`bpy.data.libraries.load(source, link=True)`, peek-only)
the EXACT library that `reconnect_selected` had, instants earlier, REALLY linked real data-blocks
from — on a file independently known (from the FIRST `PSM_Stage_v5.2.crash.txt` diagnosis,
documented in this file already) to have Blender-core fragility around its (now-shrinking, but
still present) population of missing/override-corrupted linked data. Re-peeking a library you just
really linked from, on an already-fragile file, is the prime suspect. **An access violation cannot
be caught by Python `try`/`except`** — there is no defensive code that "catches and recovers" from
this, so the only honest mitigation is to stop TRIGGERING the suspicious re-peek automatically.
**Fix:** `ops/datablock_reconnect.py::_populate_missing_blocks` no longer auto-re-enumerates a
library group's candidates after a re-scan (removed the `remaining_libs`/`old_sources` re-peek
loop) — a group's picked `source_blend` is still remembered across a re-scan, but its
candidates/confidence reset to "none" until the user explicitly re-confirms via **Pick Source
.blend** (the file-browser flow), which is the same underlying peek but now a deliberate,
user-paced action instead of a silent automatic one on every list refresh. `ui/panels.py`'s
`_reconnect_target_items` placeholder text covers both "never picked" and "picked but needs a
re-pick" cases. **This is a mitigation based on careful code-reading, NOT a proven fix** — I
cannot reproduce or verify it without live Blender; treat the next Reconnect session on a real
file with extra caution (save often) until it's been exercised live without a repeat crash.
- **Header regression reverted.** The v0.2.39→38 attempt to pin the doc/help icon to the panel's
  true far-right edge via `layout.separator_spacer()` made things WORSE per a live screenshot — it
  overlapped the icon onto the `bl_label` text ("AssetDoctor") instead of pushing it right, in this
  narrow header region. Reverted to the plain right-aligned sub-row (icon sits right after the
  version text, not edge-pinned) — the same as the original complaint, but at least not broken.
  Genuine far-right pinning in this constrained header needs a different approach + a live trial
  before trying again; not re-attempted blind this session.
- **New: sticky "last result" line (`assetdoctor_last_result`/`_ok` WM props,
  `ops/progress.set_result`).** User report: clicking **Reconnect Selected** (a plain operator, not
  a `ModalProgressMixin`) left NO trace in the panel — only a transient toast and the Info editor
  (which then says "see debug log" for the skip count, a 3-hop trail just to learn 5 items were
  skipped). `reconnect_selected` now also calls `set_result(context, msg, ok=not warnings)`; the
  Scene panel shows this as a persistent row (CHECKMARK/ERROR icon, red `alert` on warnings) right
  under the progress bar, until the NEXT action overwrites it. **Deliberately minimal (one line,
  same position as today's layout)** — the user separately proposed a bigger always-visible
  multi-line feedback area beside Current File Data (their own words: "goes against the Blender
  way... not 100% convinced... but I want to try") — that's a real Phase 3 design question, not
  decided yet, see "UX Redesign" section below. Only wired into `reconnect_selected` so far (the
  operator that prompted this) — extending `set_result` to the OTHER plain-`execute()` mutating
  operators (Examine Library's Apply Selected, Duplicate Data-blocks' Merge Selected, etc.) is a
  natural follow-up once the bigger layout question is settled, not done blanket-wide this session.
Suite 302 (no new tests — `ops/*.py` changes need bpy, can't be pytest-covered per the standing
architecture rule; `ui/panels.py`/`__init__.py` changes are layout/registration only).

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.39, 2026-06-24) — read this first

**v0.2.39 — click-to-select extended to two more report types (item 2b of the feedback batch —
the user has now asked for this "several times," flagged as a standing priority).** Investigated
before building anything: the generic click-to-select pipeline (`TreeNode.ref` →
`Row.ref`/`flatten_visible` → `ASSETDOCTOR_PG_tree_row.ref_type`/`ref_name` →
`ASSETDOCTOR_OT_row_label` → `assetdoctor.select_datablock`) was already fully built and
**already auto-wires itself** for any Report-based tree, via `core/tree.py::_parse_ref` — it
recognizes a `Finding.items` entry formatted exactly `"Type/Name"` (e.g. `"Object/Cube.001"`) as a
real datablock reference. `override_loop` (Analyze) already used that format and already worked.
Two others were ONE STRING-FORMAT AWAY from working and didn't need any new design:
- **Missing Data-blocks (f7miss)** used `"Type: Name"` (colon) — `_parse_ref` requires a literal
  `"/"`, so it never matched. `core/missingdata.py` now emits `"Type/Name"`.
- **Analyze's duplicate_family (f7live)** passed bare names (`"Cube.001"`, no type at all) into
  `core.datablock_graph.duplicate_families`. `ops/datablock_inspect.py` now feeds
  `_node_id(b)`-formatted names (`"Mesh/Cube.001"`) instead; `core/datablock_graph.build_live_report`
  strips the prefix back off for the human-readable message/base (`"Mesh: Cube ×3"`, not
  `"Mesh: Mesh/Cube ×3"`) while the row's `items` keep the full ref for selection.
Suite 302 (+1 test, `test_build_live_report_strips_type_prefix_for_display`).
**Still NOT covered** (harder, needs a design decision, not a quick fix — see below): File Map /
Scan Deps (f7) findings describe OTHER FILES, most of which were never opened by the live session
(offline BAT scan) — there is no live datablock to select for those, so this needs its own
graceful-fallback design, not just a string-format fix. Folded into the UX Redesign section below
along with items 1 and 3 of the same feedback batch (wasted tree-row space, the confusing
LS.blend missing-library label, and 4 legacy-N-panel-section redundancy questions).

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.38, 2026-06-24) — read this first

**v0.2.38 — two trivial title-bar fixes (item 1a of a new live-test feedback batch) + the
big remaining ask folded into Phase 3 of the review plan.** User started a new feedback batch
("This prompt is getting too long, so start on that and we'll build on what you come up with" —
more items still incoming) opening with "the UI needs a major overhaul." Two sub-items were
small/unambiguous enough to fix immediately rather than wait for a full proposal:
- **bl_label dropped "— Dependencies".** `ASSETDOCTOR_PT_scene_deps.bl_label` is now just
  `"AssetDoctor"` — the panel hosts the whole add-on now (Batch 5), not just dependency tools, and
  the user couldn't see what either word was telling them.
- **Doc icon now genuinely pinned to the panel's far-right edge.** `draw_header` previously put
  the help/doc operator in a `row.alignment = "RIGHT"` sub-row with no spacer before it — a
  right-aligned sub-row only right-aligns *within its own width*, so with nothing forcing that
  sub-row wide, the icon just sat immediately after the version label, not at the panel edge.
  Real (if cosmetic) layout bug, not just a preference. Fixed with `layout.separator_spacer()`
  (the flexible-width spacer Blender's own headers use for this exact purpose) between the
  version label and the icon. Suite still 301 (UI-only, no test impact).

**Everything else in this feedback batch is a structural/IA redesign, not a quick fix — folded
into Phase 3 of the 3-part-review plan (`C:\Users\Rick\.claude\plans\declarative-booping-ripple.md`)
as the concrete basis for that phase's "present a proposal first" step (3a), since Phase 3 is
already exactly "UX/panel review."** Full ask + my answers to the two open questions the user
asked directly are in the new "UX Redesign — Major Panel Overhaul" section right below.
**NEXT: wait for the rest of this feedback batch (user signaled more is coming) before drafting
the actual before/after section layout for 3a sign-off** — drafting now risks redoing it once
items 2/3/... arrive.

## UX Redesign — Major Panel Overhaul (folds into Phase 3a, live-test feedback batch started 2026-06-24)

**The ask (user, item 1 of a feedback batch — verbatim structure, lightly organized):**
- **(a) DONE @ v0.2.38** — title-bar fixes above.
- **(b) Five rough top-level sections, evolving:** Current File Data, Analyze,
  Reporting/Recommendations, Cleanup/Fixes, Info & Utilities. These will also shape the planned
  automated-fix functionality (a Cleanup/Fixes section needs to know which Analyze finding feeds
  which fix). **All sections (not just Analyze) must be collapsible.**
- **(c) "Current File Data" = the current file-plan + linked-library info that already exists**
  (the instant `_libraries_at_a_glance()` line + the file map). Stays AS-IS for now; will likely
  expand to host reporting output from the other sections once those are scoped — open question,
  don't design it yet.
- **(d) "Analyze" section spec:** an **Analyze All** button that steps through every analysis
  function in sequence, with a per-step icon showing active/complete state. Sub-buttons as the
  user listed them: Scan Deps, Analyze, Find Duplicates, Find Broken Links, Find Missing Data
  Blocks, Find Reconnectable Data Blocks, Find Missing Materials/Textures, Find Duplicate
  Materials/Textures, Find Duplicate Content, Find Resolution Variations. **Project Link Map** and
  **Safe to Delete** stay in this section but move to the bottom. User flagged the list itself as
  probably redundant ("as I typed that list, it seems like there is overlap and redundancy that
  could be improved") — see findings below. Open question from the user: which results belong in
  Current File Data vs. this section's own reporting — explicitly unresolved, needs (c) scoped
  first. The current Dependencies report layout was called out as "not usable" — needs a redesign,
  not just a rename.
- **Mini-outliner question (user, verbatim):** "Is it possible to get the outliner template and
  make the Current File Data section into a mini-outliner that is filtered?"

**ANSWERED — outliner embedding is not possible via the public API.** The Outliner is its own
`SpaceType`/editor (`bpy.types.SpaceOutliner`), not a `UILayout` template — there is no
`template_outliner()` or equivalent that draws a live, filtered Outliner tree inside an arbitrary
Panel the way `template_list`/`template_ID` do. You cannot embed it inside a Properties-tab panel;
the only way to get a real Outliner widget on screen is a full editor *area* (a different part of
the screen layout), which isn't something a Scene-properties panel can host. **The practical
equivalent already exists in this codebase**: `ASSETDOCTOR_UL_tree` (icons + sibling-aware
`"│  ├─ "` indent guides, built in Batch B @ v0.2.29 specifically to look like the Outliner/
Explorer) is a custom-drawn tree over a flattened `CollectionProperty` — that's the actual
mechanism to extend into a filtered "mini-outliner" for Current File Data (e.g. a tree scoped to
this file's linked libraries + their datablock counts), not a real embed. Worth being upfront with
the user that "mini-outliner" will mean "more of what File Map already does," not a literal
Outliner widget.

**FOUND — a real, concrete redundancy while mapping the user's 10-item Analyze list onto actual
code (not hypothetical, confirmed by grep):** "Find Missing Data Blocks" and "Find Reconnectable
Data Blocks" are very likely the SAME two buttons already in the panel today
(`assetdoctor.scan_missing_datablocks` → f7miss report, and `datablock_reconnect.scan_reconnect_
targets` → the Datablock Reconnect list) — and both call the exact same underlying walk,
`ops/datablock_inspect.py::_iter_missing_blocks()` (`datablock_reconnect.py:25,38` imports and
calls it directly). Today this is two separate scans of identical data feeding two separate UI
surfaces. **Candidate fix for 3a:** one "Find Missing Data-blocks" scan populates BOTH the
plain-report view (for Reporting/Recommendations) and the Reconnect list's editable rows (for
Cleanup/Fixes) — drop the second button entirely rather than re-scanning. This is the same
"verb soup" problem the plan already flagged (Scan/Find/List/Search/Analyze used interchangeably
across ~12 buttons) — the user re-discovered it independently by listing the functions out loud,
which is a good sign the existing Phase-3 finding was correctly scoped, just not yet visible to
the user since nothing's been renamed/merged yet.

**Other naming confusion worth fixing in the same pass (not yet asked about, flagging for 3a):**
"Scan Deps" (`f7`, offline BAT, recursively walks the CURRENT file's whole link chain across
multiple .blend files), "Analyze" (`f7live`, LIVE in-memory census of the CURRENT file only — no
disk read, no other files), and "Project Link Map" (scans an entire FOLDER of possibly-unrelated
.blend files, broadest scope of the three) sound like three flavors of the same thing but differ
in scope (current file's chain / current file only / arbitrary folder) — exactly the kind of thing
the user asked for "more descriptive names" on.

### Item 2 (2026-06-24 batch) — wasted space, the LS.blend label confusion, click-to-select priority

**(1) "A lot of wasted space" in tree rows (user, with a File Map screenshot).** Investigated
`ASSETDOCTOR_UL_tree.draw_item` (`ui/panels.py:66-111`): the row's label is drawn via
`row.operator("assetdoctor.row_label", text=display, emboss=False, ...)` with no width
constraint, so it (a real button, just invisible since `emboss=False`) likely expands to fill all
remaining row width by default — that gives a big, deliberately-clickable hover target, but reads
as a big empty gap once the (often short) text ends and before the right-aligned `detail` column
(or nothing, on rows with no detail). **Not fixed yet — this is a real layout effect I can name in
code, but I can't see how it actually renders without a live Properties panel at real width**
(per [[env-blender-verification]], same constraint as every other panel-layout question in this
project). Candidate ideas for the live pass: give every row a detail value (not just sized ones —
e.g. a child-count for category rows) so the right column is consistently used, or revisit whether
the full-row click target is worth the visual gap it creates. Needs to be tried live, not guessed.

**(2) The "LS.blend links missing library …Grass_Wild_A_spring-summer.blend" row "doesn't make
sense as presented."** Traced the exact code: `core/depscan.py:253`,
`message=f"{_name(fkey)} links missing library {ref.stored_path}"` — `fkey` is the file being
scanned (here, LS.blend) and `ref.stored_path` is a library path *it* stores that doesn't resolve
on this machine. **The classification is self-consistent and correct** (verified against
`items=[fkey, ref.resolved_path or ref.stored_path]`, which matches the two nested lines in the
screenshot) — LS.blend really does store a now-broken link to that Grass_Wild path. The confusion
is a **presentation problem, not a logic bug**: the phrasing doesn't make the FROM→TO direction
visually unambiguous, and the missing target obviously can't be opened/inspected to confirm it
(it's the broken one) — comparing it against an unrelated-but-similarly-named file you happened to
have on hand (the second screenshot, a different botaniq vine file) won't ever reconcile, since
that's a different file. **Candidate fix for 3a:** restructure the row so source and missing
target are visually distinct (e.g. "LS.blend → ⚠ missing: Grass_Wild_A_spring-summer.blend" with
an explicit arrow/icon, not two plain nested lines that read like a parent-child "contains").
Ties directly into (3) below — once a row like this is click-to-select-able, the user can jump
straight to LS.blend (if it's actually loaded in the session) instead of parsing text at all.

**(3) Click-to-select-and-focus, "I've asked several times… want to make it a priority."** Investigated
before changing anything: the mechanism is real and already proven — `TreeNode.ref` →
`core.tree._parse_ref` (recognizes a `Finding.items` entry formatted exactly `"Type/Name"`) →
`Row.ref` → `ASSETDOCTOR_PG_tree_row.ref_type`/`ref_name` → `ASSETDOCTOR_OT_row_label` →
`assetdoctor.select_datablock` (selects + calls `outliner.show_active()` in any open Outliner).
Before this session it was exercised by exactly ONE tree (Resource Analyzer, `core/resource_tree.py`)
and `override_loop` (Analyze) — every other report's `Finding.items` just weren't formatted as a
ref, so nothing broke, it simply never tried. **Fixed @ v0.2.39** for Missing Data-blocks (f7miss)
and Analyze's duplicate_family — see the SESSION RESUME note at the top of this file. **Still open,
and genuinely harder (needs a 3a design decision, not a string fix):** File Map / Scan Deps (f7)
findings are about OTHER FILES on disk, most of which the live session never opened (it's an
offline BAT scan) — there is no datablock to select for those. The only case where a real
selection is possible is when the referenced library happens to ALSO be loaded in the current
session (`bpy.data.libraries` has a matching entry) — e.g. the LS.blend example above, since
LS.blend is presumably linked into the file actually being scanned. Proposal for 3a: when a
File-Map row's file resolves to a loaded `Library` datablock, offer select/reveal for that;
otherwise fall back to today's no-op-with-a-message pattern (already used when a target has no
scene users) rather than pretending every row is clickable.

### Item 3 (2026-06-24 batch) — legacy N-panel sections vs. the new Analyze section

User asked whether 4 legacy (now Properties > Scene child-panel) sections are redundant with the
planned Analyze section, in old-N-panel order. **Checked each against the actual code before
agreeing to delete anything — two of the four "redundant, delete" guesses don't hold up:**
- **(a) "Find Duplicates" (the *Duplicate Materials* panel's button, `ops/material_dedup.py` via
  F3) — NOT redundant, recommend keeping.** This merges actual duplicate **Material** datablocks
  using a node-graph content fingerprint (works across ANY name, e.g. an unrelated-but-identical
  shader). It is completely different from the inline "Duplicate Materials/Textures" section
  (f6dup), which never merges Material datablocks at all — it dedupes **textures**, grouped by
  the material that uses them. The likely source of the "redundant" read: Analyze's own
  `duplicate_family` census *also* counts `.NNN`-named Material families (alongside every other
  audited type) as part of its passive overview — but that's a bare NAME-pattern count with no
  content verification, not a competing merge tool. Recommend: move the panel's two buttons
  ("Find Duplicates (Report)" → Analyze, "Dedup & Remap (Apply)" → Cleanup/Fixes) rather than
  delete, and have Analyze's overview point AT this tool for the Material slice of its count
  instead of just stating a number that looks like a dead end.
- **(b) "Orphans & Fake Users" → move into Analyze.** Pure relocation, no redundancy question —
  its scan button ("Scan (Report)") → Analyze, its mutating button ("Scan + Purge Orphans") →
  Cleanup/Fixes, per the user's own Analyze-finds/Cleanup-fixes split.
- **(c) "Duplicate Geometry" — NOT redundant, recommend keeping (same shape as (a)).**
  `ops/instance_dedup.py` fingerprints mesh **content** (`core/fingerprint.fingerprint_mesh`) to
  find geometrically-identical meshes regardless of name — strictly more capable than Analyze's
  bare `.NNN`-name census for Mesh, not a duplicate of it. Same recommendation as (a): relocate
  the two buttons (report → Analyze, "Instance & Merge (Apply)" → Cleanup/Fixes), don't delete.
- **(d) "Resource Analyzer" → move "Analyze Memory/Disk" and "Profile Render (Real RAM)" into
  Analyze, as the user asked — and the "overlap" hunch is real but not where it was aimed.** The
  two ARE complementary, not duplicates of each other (estimated RAM/VRAM/disk vs. one real
  render to measure actual peak RAM — the UI already labels this, just not prominently). The
  genuine naming collision is with the SEPARATE "Dry-run render" feature (f9, Batch D): "Profile
  Render" (in-process, measures RAM) and "Dry-run render" (a background subprocess, catches
  missing-texture/driver warnings) sound like variants of the same idea but do unrelated jobs —
  another candidate for the verb-soup naming pass.

**Net effect on the Analyze-All list:** of the user's original 10 items, this session's
investigation found ONE real duplicate (Missing Data-blocks / Reconnectable Data-blocks, same
underlying scan, item 1d above) and confirmed TWO suspected-but-not-actual duplicates (Find
Duplicates / Duplicate Geometry vs. Analyze's passive census) — net of this batch, the
recommended Analyze-All step list is trending toward *fewer, better-named* steps plus explicit
links from the census down to each dedicated dedup tool, not a flat re-list of every existing
button.

**What to live-test right now (user asked directly):** nothing above is built yet except the
v0.2.38/v0.2.39 fixes (title bar, far-right doc icon, click-to-select on Analyze/Missing
Data-blocks rows) — confirm those three first since they're real, shipped, and quick to eyeball.
Past that, the single highest-priority item still outstanding from BEFORE this feedback batch is
**Phase 1 of the review plan, not yet done**: run Find Missing Data-blocks + Datablock Reconnect
against the real `PSM_Stage_v5.2.blend`, prioritizing `character1_cs.012`/`cs_grp.012`/
`Mesh_006_001` (literally in the crash stack) — fixing those both resolves the real
`EXCEPTION_ACCESS_VIOLATION` crash AND is the first production-data exercise of those two tools.
Also still sitting in the "needs live-Blender verify, never confirmed" backlog from earlier
sessions: Datablock Reconnect and Examine Library (both mutate links), Dry-run Render (f9),
the idle-scan prototype, and Examine Library's node-graph-confidence labels — all listed with
exact repro steps under their version entries further down this file if you want the full list
rather than re-deriving it.

[[feedback-suggest-better-designs]] [[feedback-versioning]] [[feedback-testing]]

### Item 2 follow-up, real PSM_Stage_v5.2 Reconnect run (2026-06-24, second feedback batch)

User ran the real Phase-1 triage this session (Find Missing Data-blocks, then Datablock Reconnect,
against the real file) — first real production exercise of both tools. Results + questions:

- **"Find Missing Data-blocks gave a report that wasn't clickable... I think it can be deleted."**
  Partially superseded by this session's own work: as of v0.2.39 (above), its rows ARE
  click-to-select-able now (the `"Type/Name"` item-format fix). But the user's deeper point stands
  even with that fixed: **Datablock Reconnect's list IS a strict superset** — same underlying scan
  (`_iter_missing_blocks()`, confirmed by grep, see "Item 1d" above), grouped, AND actionable (pick
  source → suggest → apply), where the plain report is read-only. Recommend: fold the plain
  Missing-Data-blocks report into Reporting/Recommendations as a SUMMARY ONLY (counts, no separate
  scan button) that's just a read of the SAME data Reconnect already populates, rather than two
  things to click. Matches "Item 1d"'s candidate fix exactly — this real test confirms it's the
  right call, not just a hunch from reading code.
- **3a — "I don't understand how they were missing. Is it just because the added suffix?" YES,
  exactly.** The screenshot's rows (`Image: FabricFauxLeather010_AO_2K_METALNESS_png.005`, etc.)
  show Blender appended a `.NNN` suffix to the LOCAL placeholder name at some point (this happens
  when the same base name was already taken locally — e.g. the SAME `materialMaster.blend` was
  linked/re-linked or partially merged more than once over this file's history), but
  `materialMaster.blend` itself only has the bare, un-suffixed name. So the placeholder's name
  (`…png.005`) no longer matches anything in the library (`…png`) — not a content problem, a pure
  naming mismatch, which is exactly what `core.reconnect.suggest_reconnect`'s `.NNN`-strip tier is
  built to catch (and did — 59 of 60 suggested automatically).
- **3b — "This seems like something that should be corrected automatically."** Reasonable, but
  scoping it needs a decision before building (mutates links, the standing project rule): an
  auto-apply tier for HIGH-CONFIDENCE-ONLY matches (exact name or `.NNN`-strip, never the fuzzy
  tier) would have closed 59 of these 60 with zero clicks. Open questions for the user: (i) opt-in
  toggle or always-on for exact/`.NNN` matches specifically (fuzzy/affinity matches should very
  likely stay manual-confirm — same reasoning as Examine Library's `allow_fuzzy=False` default for
  in-memory suggestions, a wrong fuzzy auto-apply would silently mis-wire something); (ii) does
  "automatic" mean auto-TICKED-but-still-requires-clicking-Reconnect-Selected (safer, still one
  button, still backed up) vs. fully unattended (riskier, no real precedent elsewhere in this
  add-on — everything is report-first + an explicit Apply click). Recommend (i) high-confidence-
  only and (ii) auto-ticked-not-unattended, matching every other "safe default" decision already
  made in this project — but this is the user's call, not mine to decide alone.
- **3c — no in-panel feedback after Reconnect Selected — FIXED this session, see "SESSION RESUME"
  above.** The "remove what was relinked from the list" half was ALREADY happening automatically
  (`reconnect_selected` calls `_populate_missing_blocks` itself) — the user just couldn't tell,
  because of the missing-feedback bug they're also reporting here, so they (reasonably) assumed
  nothing had refreshed and re-triggered it manually, which is what hit the crash documented above.
  Telling the user this directly: **you likely don't need to manually re-run Find Reconnectable
  Data-blocks after a Reconnect** — it already refreshes; the new sticky result line should make
  that visible going forward.
- **Item 4 — "I like the look of Find Reconnectable Data-blocks better than the Explorer/
  Outliner-type attempted before."** Direct, useful input for the Current File Data /
  mini-outliner design question (Item 1d above): the grouped-box-with-dropdowns shape (collapsible
  group header + per-row checkbox/confidence/picker, the same shape Duplicate Materials/Textures
  and Examine Library use) is the user's preferred visual pattern, NOT the Outliner-style indented
  tree (`ASSETDOCTOR_UL_tree`, used by File Map/Scan Deps/Analyze). Recorded for Phase 3a — leans
  the "mini-outliner" direction toward "more grouped boxes like Reconnect," not "more tree-with-
  guides like File Map," which also makes the click-to-select/file-map-clarity work (Item 2 above)
  lower-priority relative to extending the grouped-box pattern to more sections.
- **Item 2 — RESOLVED (2026-06-24, follow-up message).** User restated the list: **total file
  size, total texture size, object count, face/vertex/edge counts** — explicitly a LIVING list
  ("will get refined as we progress"), not a final spec. Recorded as the current working answer to
  the open "what does Current File Data show beyond links/paths" question from Item 1c/1d above.
  **Reuse opportunity, not a from-scratch build:** most of this is ALREADY computed elsewhere —
  `ops/resource.py::_gather_steps` (F5 Resource Analyzer) already walks every Mesh for
  `verts`/`edges`/`loops`/`polys` and every Image for on-disk size (`_image_disk`); object count is
  a trivial `len(bpy.data.objects)`; the CURRENT file's own disk size is already captured by
  `core/depscan.py` during a Scan Deps run (the same `path.stat()` capture used for every node in
  the File Map). Building this into Current File Data is therefore mostly **surfacing an instant
  summary** (own light walk, or a cached read of F5's last scan if one exists) rather than new
  heavy analysis — keep that framing when 3a's concrete proposal gets drafted, since it changes the
  performance question from "is this safe to run on file open" (no, F5's full walk is a modal scan
  for a reason) to "what's the CHEAPEST instant subset" (object count + an instant aggregate is
  free; full per-mesh vert/face/texture-size totals likely still want a short scan, even if fast).
- **Item 6 — Dry-run Render in progress, feedback pending** — no action needed, will fold into
  the next pass once the user reports back.

**What to live-test right now (updated):** the v0.2.40 fixes specifically — (1) the header no
longer overlaps (confirm the doc icon sits cleanly after the version text, even if not edge-pinned
yet); (2) Reconnect Selected now shows a sticky CHECKMARK/ERROR line in the panel after running;
(3) **treat the next Datablock Reconnect re-scan with caution** — the crash mitigation above is
analysis-based, not proven; save before re-scanning, and report back whether re-running "Find
Reconnectable Data-blocks" after an Apply still crashes (it shouldn't need to — see 3c above — but
if you click it anyway, that's exactly the repro to confirm or rule out). Still outstanding from
before: the rest of Phase 1 (the 3 crash-stack names specifically:
`character1_cs.012`/`cs_grp.012`/`Mesh_006_001`), and the long-standing live-verify backlog
(Examine Library, Dry-run Render, idle-scan, node-graph-confidence labels).

[[feedback-suggest-better-designs]] [[feedback-versioning]] [[feedback-modal-undo]]

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.37, 2026-06-24) — read this first

**v0.2.37 — Phase 0 of the 3-part review (code review / N-panel dedup / UX review, plan at
`C:\Users\Rick\.claude\plans\declarative-booping-ripple.md`): dead-code removal only, zero
behavior change, while the user live-tests v0.2.34-0.2.36 separately.** Removed: the unused
`ASSETDOCTOR_UL_broken_imgs` UIList class (`ui/panels.py`, never drawn via `template_list`
since the Missing-Textures section switched to custom rows in v0.2.12) + its registration;
`core/imagepaths.diff_found`, `build_find_missing_report`, `build_image_report`, and the
`FindMissingResult` dataclass (none called from any `ops/*.py` — verified by grep, not just
inherited from notes) + the now-orphaned `Finding`/`Report` import and 6 tests covering them.
Suite dropped from 307 → **301 green** (exactly the 6 removed tests). **Next: wait for the
user's live-test bug list from this Blender session, fix those in place, THEN do the bigger
Phase 2 refactor** (a shared file-picker/proposal-staging helper across `ops/relink.py`,
`ops/image_relink.py`, `ops/datablock_reconnect.py`, `ops/examine_library.py` — deliberately
held back since those are the exact files under live test right now) — see the plan file for
the full **5-phase** breakdown (code cleanup → panel-dedup/UX review combined → **F7 Phase 4b:
Link Chain Flattening (NEW 2026-06-24)** → documentation review last, separately).

**2026-06-24 — a real crash + a new feature request folded into the plan (plan file now 5
phases; see "F7 Phase 4b — Link Chain Flattening" immediately below for the full design).** User
attached a real `PSM_Stage_v5.2.crash.txt` and separately asked for a multi-hop "link chain
flattening" feature in the same session — both are now part of the plan instead of separate
threads.
- **Crash diagnosed — Blender core, not AssetDoctor.** Backtrace is 100% Blender C++
  (`DepsgraphRelationBuilder::build_rig → build_object_data → build_object_data_geometry →
  add_relation`, access violation reading near-null @ +0x30), fired from the engine's own
  background depsgraph refresh (`wm_event_do_notifiers`), not from any add-on action. Root cause:
  the file load logged **224 missing linked data-blocks**, including `Collection
  'character1_cs.012'`, `Object 'cs_grp.012'`, `Mesh 'Mesh_006_001'` (all from
  `human_bundle.blend`) — exactly the kind of object `build_rig`/`build_object_data_geometry`
  walks; Blender's relation builder isn't null-safe against a missing/placeholder linked ID in
  that position. Same disease as the 2026-06-16 crash diagnosis further down this file (dangling
  pointer from missing library data crashing Blender core code), different code path (depsgraph
  builder vs. an add-on timer).
- **Real link topology confirmed** via a one-off offline BAT probe of the ACTUAL files (not
  fixtures): `PSM_Stage_v5.2.blend` links `human_bundle.blend` BOTH directly AND via
  `ThePiazzaSanMarco - People1_v5.1.blend` — a real, live 2-hop chain, not hypothetical.
  `People1_v5.1.blend` ALSO links back to `//PSM_Stage_v5.1.blend` (the older stage file) plus
  `laFamiglia.blend` and `Dodo_ARP_Convert.blend` — an intermediate "character library" reaching
  back into a stage-level file. `materialMaster.blend` is reachable via at least 4 distinct paths
  (direct from PSM_Stage, via human_bundle, via People1, via People1→human_bundle) — textbook
  "same library via different paths."
- **Action folded into Phase 1 (not new code, just real-data verification):** (a) run Find
  Missing Data-blocks (f7miss) + Datablock Reconnect against the real `PSM_Stage_v5.2.blend`,
  prioritizing `character1_cs.012`/`cs_grp.012`/`Mesh_006_001` first since they're literally in
  the crash stack — fixing them resolves the crash AND is the first real production-data exercise
  of f7miss/Reconnect (everything before this was fixture/screenshot-verified only); (b) run Scan
  Deps against the real PSM_Stage/People1/human_bundle files — first real exercise of the
  duplicate-ref/inconsistent-path/cycle classifiers on production data.
- **NEW FEATURE folded in as F7 Phase 4b — Link Chain Flattening.** Completes the ORIGINAL F7
  Phase 4 ask from the 2026-06-16 design session ("repoint to a more direct library, collapse
  multi-hop chains") — Phase 4a (single-hop repoint) already shipped as Datablock Reconnect +
  Examine Library; Phase 4b (collapse a multi-hop chain while preserving what an intermediate hop
  adds) was never built. Full design in the dedicated section right below. **Sequencing decision:
  build Phase 4b AFTER Phase 2 (shared file-picker helper) and Phase 3 (UX/panel review)** — its
  UI needs the Phase-2 helper and a settled slot in the Phase-3-regrouped tool cluster, so building
  it earlier means writing or placing it twice. [[feedback-suggest-better-designs]]

## F7 Phase 4b — Link Chain Flattening (NEW, folded in 2026-06-24)

**Completes the original F7 Phase 4 ask (design session 2026-06-16): "repoint to a more direct
library (collapse multi-hop chains, e.g. material → link directly from materialMaster)."** Phase
4a (single-hop repoint, including to a DIFFERENT source) is done — Datablock Reconnect (Batch C
#2, v0.2.30) fixes broken placeholders; Examine Library (v0.2.32) repoints a working-but-unwanted
library. Neither collapses a *chain* while preserving what an intermediate hop adds — that's 4b.

**Real motivating case (confirmed via direct file analysis, 2026-06-24, not hypothetical):**
`PSM_Stage_v5.2.blend` links characters from `human_bundle.blend` via
`ThePiazzaSanMarco - People1_v5.1.blend`, which gives each character a transform + a pose on top
of the bare linked rig — exactly the "char/people files" hop named in the 2026-06-16 design note's
`materialMaster → char/people files → PSM_Stage → SoundStage` chain.

**Why this needs a phased design, not a generic "diff and reapply" tool (user, 2026-06-24):** the
posing mechanism is HETEROGENEOUS across characters in the same file — some are a **Library
Override** of the human_bundle object with an adjusted rig Location/Rotation/Scale; some are
animated via a **Modifier (Path or other)**; rigs come from **HumanGen**, **Character Creator**,
**AutoRig Pro**, **Rigify**, and **MetaRig**. A single mechanism would either miss cases or
mis-pose a character by guessing wrong. So: detect-and-classify first (report-only), build the
mutating action only for the mechanically-tractable case, leave the rest flagged-but-manual.

**Confirmed buildable (direct file-analysis findings, 2026-06-24):**
- Reading override/transform data offline (no Blender launch) IS structurally possible: a Library
  Override's `override_library` field lives under the embedded `id` sub-struct, not directly on
  `Object` — read via `block.get_pointer((b"id", b"override_library"))`, NOT
  `block.get_pointer((b"override_library",))` (the latter raises — confirmed the hard way; the
  error dump listed every valid `Object` DNA field for this Blender version). The relevant Object
  fields all exist in this Blender 5.1 file's DNA: `loc`/`rot`/`quat`/`rotAxis`/`rotAngle`/`size`
  (transform), `adt` (assigned Action), `pose`/`poselib`, and even legacy `proxy`/`proxy_from`/
  `proxy_group` (still in the format from the pre-2.80 proxy era — relevant since the user's
  workflow predates Library Overrides for some characters: "I appended a character... froze frame
  250 location/rotation/scale and rig pose").
- `core/depscan.py` already builds the exact multi-hop tree needed to find chains ≥2 deep;
  `core/datablock_links.py` already answers "what does file A link from file B" at the datablock
  level — finding the chains is assembling existing primitives, not new infrastructure. **Caveat:**
  `datablock_links.linked_datablocks` only sees PLAIN links via the generic `ID` placeholder block
  (`id.lib` non-null, block code `ID`) — it will NOT see Library Overrides, which are typed local
  blocks (`id.lib == NULL`, `id.override_library != NULL`). The override detector above is new
  code, not an extension of that module's existing query.

**Phased build plan:**
- **Phase A — read-only classification, no mutation.** Extend the multi-hop chain finder with a
  per-character posing-mechanism classifier: `override-with-transform` (`id.override_library` set
  + read loc/rot/quat/size) / `modifier-driven` (has a Path or other modifier, no override) /
  `unclassified` (anything else — HumanGen/CC4/AutoRig Pro/Rigify/MetaRig specifics not yet
  modeled). Ships as a new report only — answers "how many characters route through People1, and
  which ones could even theoretically be flattened" before any mutation is designed.
- **Phase B — the actual flatten-and-reapply action, override-with-transform case ONLY.** For a
  character classified `override-with-transform`: link the character directly from the ultimate
  source (human_bundle), create a new Library Override there, copy the captured loc/rot/quat/size
  across, re-point whatever holds the pose (Action via `adt`, or pose library) — mirrors Datablock
  Reconnect's read-then-relink-then-remap idiom and Phase 2's shared file-picker/proposal-staging
  helper (build Phase B AFTER Phase 2 lands so it's written once, against the clean abstraction).
  Report-first + backup, never silently mutate (the standing project rule).
- **Phase C — explicitly deferred, no design without a concrete case.** Modifier-driven and
  rig-specific (HumanGen/CC4/AutoRig Pro/Rigify/MetaRig) cases stay flagged-but-manual in Phase A's
  report until there's a real example of each to design against — guessing at N rig systems up
  front is exactly the kind of premature generalization this project avoids.

**Separate, smaller finding worth its own pass (not Phase 4b, but surfaced by the same file
analysis):** `People1_v5.1.blend` linking back to `//PSM_Stage_v5.1.blend` plus the 4-path
`materialMaster.blend` reachability — both are real, fresh inputs for the EXISTING
duplicate-ref/inconsistent-path/cycle detection (Scan Deps), not new code. Run Scan Deps on the
real files (folded into Phase 1 above) and confirm these surface correctly before Phase 4b design
goes further — Phase A's chain-finder will want a clean picture of the real graph to walk.

[[feedback-suggest-better-designs]] [[feedback-testing]] [[feedback-versioning]]

## ⏩ PREVIOUS SESSION RESUME (as of v0.2.36, 2026-06-24)

**State:** local dev **v0.2.36** (published channel still 0.1.9). Suite **307 green**. **Lettered
Batches A–E are ALL COMPLETE**, and so is the numbered **5-batch consolidated plan (1–5)** — confirmed
2026-06-24 by checking the working tree directly: Batch 4's three "remaining" items (datablock reconnect,
node-graph substitute confidence, idle-scan feasibility) were genuinely built, just shipped under the
Batch C / Batch E labels instead of literal "Batch 4" commits — the numbered-Batch-4 status line was
just stale bookkeeping, now fixed (see "Where we are in the 5-batch push" further down). **Nothing new
was built this pass.** Plus a **user-reported bug fixed** in v0.2.36: "Search a Folder (Recursive)"
silently missing textures at drive-level scope. All of this work (everything since v0.2.5) still needs
the live-Blender verify sweep (structural panel changes especially — RESTART Blender, don't rely on
Reload Scripts) — that is the actual next step, not new feature work, unless the user redirects.

- **v0.2.36 — fixed: drive-level "Search a Folder (Recursive)" silently misses textures a narrower
  search finds.** User report: selecting a whole drive as the search root missed some textures that a
  more specific folder found. Root cause is NOT a recursion-depth limit (`os.walk` has none) — it's two
  silent-skip behaviors that both produce exactly this symptom: (1) **ambiguous-match skip by design** —
  the exact-name search only relinks a texture when its filename matches EXACTLY ONE file anywhere in the
  scanned tree (`core/imagepaths.find_image_target`); a common filename (e.g. `diffuse.jpg`) easily exists
  in 2+ unrelated project folders at drive scope, so the match becomes ambiguous and is skipped with NO
  feedback — narrow the search to one project and the ambiguity disappears. (2) **`os.walk`'s default
  `onerror=None`** silently drops any subfolder it can't list (permission denied, or a path exceeding
  Windows' 260-char MAX_PATH) — common given how deep this user's project paths nest from a drive root.
  **Fix — make both failure modes VISIBLE instead of indistinguishable from "not found":**
  `core/imagepaths.py` gained `ambiguous_matches(index, basenames)` (which wanted basenames matched 2+
  paths) and `iter_walk_dirs` gained an optional `skipped: list[str]` out-param wired through a custom
  `os.walk(..., onerror=...)` callback (+4 tests). `core/imagefamily.iter_resolve_group_in_dir` gained
  optional `ambiguous`/`skipped_dirs` out-params (mutated in place, NOT part of the return value — kept
  the existing `found`-dict contract so `resolve_group_in_dir`-equivalence tests didn't need touching;
  +3 tests). `ops/image_relink.py`: `_run_exact` (powers both "Search a Folder (Recursive)" and "Point
  group at folder") now sets a new `ASSETDOCTOR_PG_broken_lib.ambiguous_count` per row instead of leaving
  a silently-skipped row looking identical to a genuinely-unmatched one; new `_diagnostics_tail()` helper
  appends a short "⚠ N skipped (same filename in 2+ places); M folder(s) could not be scanned" suffix to
  the operator's status message (both `_run_exact` and `_run_fuzzy`, since the skipped-folder risk applies
  to fuzzy matching too). UI: `ui/panels._draw_missing_textures`'s per-row "no match" label becomes
  "N found elsewhere — pick one" (ERROR icon) when `ambiguous_count > 1`, so the row itself explains why,
  not just the transient status bar. **Deliberately scoped to the explicit folder-search operators** (what
  the user is actually using) — the initial auto-scan on "List Missing Textures"
  (`_populate_broken_images`/`find_relink_targets`) was left untouched (much narrower search_dirs, so
  ambiguity there is rare, and touching it risked an unrelated regression for no reported problem). New
  `tests/smoke_folder_search_diagnostics.py` (two same-named files in different subfolders → no target +
  `ambiguous_count == 2`; one uniquely-named file → resolves normally + `ambiguous_count == 0`). Suite 307.
  **VERIFY:** run "Search a Folder (Recursive)" at a broad scope containing a deliberately duplicate
  filename — the row should show "N found elsewhere — pick one" instead of a plain "no match"; the status
  message should mention the skip counts.

- **Batch E part 3 @ v0.2.35 — Batch 5: N-panel retired, everything now lives under Properties > Scene,
  BUILT, needs live-Blender verify.** User chose (2026-06-23): delete the VIEW_3D N-panel in the same
  pass (no parity-check period), native `bl_parent_id` child panels (not inline boxes) appended after the
  Reports selector in `ASSETDOCTOR_PT_scene_deps`, UIList virtualization of the Missing/Duplicate lists
  split off as its own follow-up. `ui/panels.py`: `_FeaturePanel` (VIEW_3D mixin) → `_SceneFeaturePanel`
  (`PROPERTIES`/`WINDOW`/`scene`, `bl_parent_id="ASSETDOCTOR_PT_scene_deps"`); `ASSETDOCTOR_PT_make_local`/
  `_materials`/`_orphans`/`_geometry`/`_resource_tools`/`_utilities` re-parented in place (same class
  names/operators/bl_idname, just re-homed + renumbered `bl_order` 0-5). **Deleted outright** (no
  replacement needed — already redundant): `ASSETDOCTOR_PT_main` (its progress bar + header were already
  duplicated by `scene_deps`; the help-doc button moved into `scene_deps.draw_header`), `ASSETDOCTOR_PT_
  project` (its one button was already in `scene_deps`'s "Project link map" box), `ASSETDOCTOR_PT_report`
  (its report selector was already duplicated by `scene_deps`'s own Reports section). **Folded in**
  (content merged into the new Resource Analyzer sub-panel, not just deleted): `ASSETDOCTOR_PT_resources`
  — its profiled-RAM line + Export + resource `template_list` now draw inline in `ASSETDOCTOR_PT_
  resource_tools` once a scan has run, instead of needing a second collapsible panel for the same result.
  **Regression caught + fixed before it shipped:** `scene_deps`'s OWN report selector only ever showed the
  curated F7/F6/F9 `_F7_FEATURES` subset — deleting `ASSETDOCTOR_PT_report` outright would have made F1
  (Link Map)/F2 (Make Local)/F3 (Materials)/F4 (Orphans)/Geometry dry-run reports unviewable (they have no
  other UI surface). Replaced `_F7_FEATURES` with `ops.report_store.available_features(wm)` (the same
  generic "all features with data" helper the old Report panel used) minus a small explicit `_SELECTOR_
  EXCLUDE = {"f6dup"}` (preserves the 2026-06-22 #9 fix — f6dup's report is Export-only, the Duplicate
  Materials/Textures section already shows it inline, so it deliberately doesn't get a selector tab). Also
  added the report-selector's missing "Clear" (X) button, carried over from the deleted panel's header.
  `ui/__init__.py`: `REGISTER_CLASSES` reordered so `ASSETDOCTOR_PT_scene_deps` registers BEFORE its new
  children (Blender errors if a `bl_parent_id` target isn't registered yet) — registering it LAST never
  mattered before since it had no children. `tests/smoke_utils.py` updated: sub-panel parent check now
  targets `scene_deps` (was `_main`, now gone), a new check confirms the 4 retired class names are gone
  from `bpy.types`, and a new check confirms `f3` (Materials) surfaces through the generalized selector.
  **bl_label "AssetDoctor — Dependencies" intentionally left AS-IS** (the panel now hosts the whole add-on,
  not just dependency tools, but renaming it was already a separate, deferred decision — see "DEFERRED UI
  BATCH (a)" further down — not reopened here). **VERIFY (this is the riskiest change this session —
  RESTART Blender, don't Reload Scripts):** every legacy feature (Make Local/Duplicate Materials/Orphans/
  Geometry/Resource Analyzer/Utilities) appears as a native collapsible sub-panel under Properties > Scene
  > AssetDoctor, in that order, after the Reports selector; the VIEW_3D "AssetDoctor" N-panel tab is GONE
  from the 3D viewport sidebar entirely; running Make Local/F3/F4/Geometry's "Report (Dry Run)" buttons
  makes their report appear as a new tab in the Reports selector; Resource Analyzer's Analyze/Profile
  buttons populate its own inline tree (no second panel needed); the idle-scan status line (if enabled)
  still shows under Utilities.

- **Batch E parts 1-2 @ v0.2.34 — node-graph substitute-material confidence + idle-scan prototype, BUILT,
  needs live-Blender verify.** (1) **Examine Library now compares node graphs, not just names.**
  `ops/examine_library._material_graph_match` reuses the F3 fingerprinter
  (`core.fingerprint.fingerprint_material` + `ops.extract.extract_material`, resolution-agnostic) to
  compare a Material row's examined block against its auto-suggested local/library replacement (both are
  already loaded in memory — unlike a missing image file, nothing here is unrecoverable) and tags the row
  `graph_match = "identical" | "differs" | ""`. `ASSETDOCTOR_PG_examine_row` gained the field;
  `ui/panels._graph_match_suffix` + `_draw_examine_library` append "(identical)"/CHECKMARK or "(graph
  differs)"/ERROR to the suggestion line. Per-node diff for the "differs" case is still Phase 2, deferred.
  New `tests/smoke_examine_library.py` (links a same-named "Shared" + "Diff" material pair from a
  throwaway source .blend into a session that already has local materials of the same names — one
  identical graph at a different texture resolution, one genuinely different — and checks the populated
  rows land on "identical"/"differs"). (2) **Idle-scan feasibility prototype.** `core/idle.py` (bpy-free,
  5 tests): `seconds_since_input()` via `ctypes`/`GetLastInputInfo` on Windows (`None` elsewhere — never
  treated as idle) + `is_idle(seconds, threshold)`. `ops/idle_scan.py`: the **first app timer this add-on
  has ever registered** (`bpy.app.timers`, 5s tick, `persistent=True`), gated behind a new, default-OFF
  `AssetDoctorPreferences.idle_scan_enabled` (+`idle_scan_threshold`, default 120s) — while enabled and no
  AssetDoctor modal is running, it sets `WindowManager.assetdoctor_idle_seconds`/`assetdoctor_idle_detected`
  for a status line under the (now Scene-panel) Utilities section. **It does not trigger any scan** — this
  only proves the OS poll is safe to run from inside Blender (doesn't freeze/crash on file load —
  `register_idle_timer`/`unregister_idle_timer` are wired into add-on register()/unregister() so nothing
  survives a disable/reload). `tests/smoke_idle_scan.py` exercises register → disabled-tick-is-noop →
  enabled-tick-sets-seconds → skipped-while-a-modal-is-active → unregister. Wiring a REAL idle-triggered
  scan (chunked/modal, never during a render) is still future work, same caveats as the original TODO item.
  **VERIFY:** enable the prototype in Preferences, watch the Utilities status line tick up while idle and
  reset on input; confirm Examine Library's graph-match labels on a real same-named-but-different Material
  pair.

**Still open (not part of Batch E, do whenever convenient):** UIList virtualization of the Missing/
Duplicate/Examine Library/Datablock Reconnect custom-drawn lists (split off this session, see "BATCH 5"
below); KEKey/shape-key half of Batch C #3; Examine Library's deferred folder-wide search; the rest of
"LIVE-TEST FEEDBACK BATCH 2" (#1 synonym-table+inverse-pairs design, #2/#10 report-formatting pass, #4
auto-suggest feasibility).
**Previously, Batch D @ v0.2.33 — headless dry-run render for warnings (#12), BUILT — LIVE-VERIFIED
2026-06-25 (user: "basically works"). Report-formatting follow-up still open, unrelated to whether it runs.**
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
  `"f9"` added to `report_store.FEATURES` + `core/tree._CATEGORY_TITLES` (the panel's old curated
  `_F7_FEATURES` selector subset was replaced by the generic `available_features()` in Batch E part 3 —
  see above). Distinct from F5's in-process Profile Render (`ops/resource.py`) — this never touches the
  live session. **VERIFY:** run it on a file with a missing texture or a broken driver → report lists
  them; a clean file → ✓ no warnings; Cancel/ESC kills the subprocess cleanly.

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
  **Concrete case confirmed 2026-06-24 (real numbers, from a live Dry-Run Render on the actual crash
  file):** `f9` (Dry-Run Render Warnings, `core/dryrun.parse_render_log`) has NO top summary line —
  the report opens straight into per-category collapsible rows ("Render warnings" 45,016 / "Render
  errors" 11,542 / "Missing images (render-time)" 144, in the user's screenshot) with no aggregate
  line above them. Wants the same flat `overview` headline pattern other reports already have, e.g.
  "Summary — 45,016 warnings, 11,542 errors, 144 missing images". Add `f9` to the report-formatting
  pass's scope when it's picked up — `core/dryrun.parse_render_log` would need a leading `overview`
  Finding combining the existing per-category counts (`missing_image`/`driver_error`/`render_error`/
  `render_warning`, already each their own collapsible row) into one line, same shape as every other
  `overview`-having report (e.g. `build_missing_datablocks_report`'s headline) — decide at build time
  whether the line groups by raw severity (Warnings/Errors) or keeps the existing per-category split
  (the user's example phrasing — "45,016 Warnings, 11,542 Errors, 144 Missing Images" — happens to
  match the THREE category rows already shown 1:1 in this run, so category-level wording is the
  closer match to what was actually asked for).
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

### BATCH D — headless dry-run render warnings (#12) — BUILT @ v0.2.33, LIVE-VERIFIED 2026-06-25
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
- **Node-graph substitute-material confidence — DONE @ v0.2.34, needs live-Blender verify.** Reused
  `core/fingerprint.fingerprint_material` via `ops/examine_library._material_graph_match`; see the
  "SESSION RESUME" entry at the top of this file for the full build note + verify steps.
- **Idle-scan feasibility prototype — DONE @ v0.2.34, needs live-Blender verify.** `core/idle.py`
  (Windows `GetLastInputInfo`, gated behind a default-off preference) + `ops/idle_scan.py`'s app timer;
  see the "SESSION RESUME" entry at the top for the full build note + verify steps. Does NOT trigger any
  scan yet — that's still its own follow-up (chunked/modal, never during a render).
- **Batch 5 — DONE @ v0.2.35, needs live-Blender verify (the riskiest change this session).** N-panel →
  Properties migration. User's scope decisions (2026-06-23): delete the VIEW_3D N-panel in the same pass
  (no parity period); native `bl_parent_id` child panels (not inline boxes), appended after the Reports
  selector, same order as the old N-panel; **UIList virtualization of the Missing/Duplicate lists split
  off as its own follow-up** (not done — still future work, see "SCHEDULED" under SESSION 4 below). Full
  build note + verify checklist in the "SESSION RESUME" entry at the top of this file.

(The stale "NEXT BUILD: DATABLOCK RECONNECT" note that used to live here was leftover from before Batch C
#2 shipped it back in v0.2.30 — removed.)

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
- **Batch 4 — DONE** (v0.2.24–0.2.26, remaining items closed out under other batch labels by v0.2.34):
  **material eyedropper** (v0.2.24) + v0.2.25 live-test fixes + **search-another-.blend for TEXTURES**
  (v0.2.26, `harvest_image_paths` + `suggest_from_blend`); **datablock RECONNECT** shipped as Batch C #2
  @ v0.2.30 (`core/reconnect.py` + `ops/datablock_reconnect.py`); **node-graph substitute confidence** +
  **idle-scan feasibility** shipped as Batch E parts 1–2 @ v0.2.34 (`ops/examine_library._material_graph_
  match`, `core/idle.py` + `ops/idle_scan.py`). All three "remaining" items were genuinely built, just under
  the lettered-batch names — confirmed present in the working tree + suite 307 green (2026-06-24).
- **Batch 5 — DONE @ v0.2.35** (N-panel→Properties migration; shipped as Batch E part 3 — see "BATCH E"
  above). **UIList virtualization** of the Missing/Duplicate lists (scheduled here from B1) split off as
  its own follow-up, NOT done.

**Immediate next actions next session:** all 5 numbered batches + the lettered A–E batches are now code-
complete. What's left, by priority: (1) the live-Blender verify sweep across this entire local-dev range
(v0.2.5→v0.2.36 — nothing has been exercised in the actual Blender UI beyond a few early screenshots);
(2) the still-open side quests independent of the batches — Batch 2's relink/merge **crash repro** (Solid
vs Material shading, needs USER repro), Batch 5's **UIList virtualization** follow-up, the **KEKey/shape-
key half of Batch C #3**, Examine Library's deferred folder-wide search, and the rest of "LIVE-TEST
FEEDBACK BATCH 2" (#1 synonym-table+inverse-pairs design, #2/#10 report-formatting pass, #4 auto-suggest
feasibility); (3) the ROADMAP items (Automated Cleanup pipeline, Archive Project, material-override→
real node-tree reassignment).

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
- **BATCH 4 — Possible Matches power-ups + idle-scan feasibility. DONE (v0.2.24–v0.2.34; the last three
  items below shipped under Batch C #2 / Batch E rather than as literal "Batch 4" commits — cross-
  referenced where each landed).**
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
  - **DATABLOCK RECONNECT (missing data-blocks) — DONE, shipped as Batch C #2 @ v0.2.30.** Design matched
    what's below exactly: `core/reconnect.py` (`suggest_reconnect`/`ranked_candidates`/`plan_reconnects`) +
    `ops/datablock_reconnect.py` (`scan_reconnect_targets`/`reconnect_pick_source`/`reconnect_selected`) +
    "Datablock Reconnect" box. See "★ BATCH C" #2 above for the full build note + verify steps.
  - **Node-graph introspection for substitute-material confidence — DONE, shipped as Batch E part 1
    @ v0.2.34.** `ops/examine_library._material_graph_match` reuses `core/fingerprint.fingerprint_material`.
    See "BATCH E" above.
  - **Idle-scan feasibility prototype — DONE, shipped as Batch E part 2 @ v0.2.34.** `core/idle.py`
    (Windows `GetLastInputInfo`) + `ops/idle_scan.py`'s app timer, gated behind a default-off preference.
    See "BATCH E" above.
- **BATCH 5 — N-panel → Properties migration + cleanup — DONE @ v0.2.35 (shipped as Batch E part 3).**
  - Done: each feature re-homed as a native Scene sub-panel under `ASSETDOCTOR_PT_scene_deps` (which
    already hosted the shared progress + report lists, so no separate new parent panel was needed); the
    redundant Project/Resource/Report N-panel sections deleted (Resource's tree folded into the new
    Resource Analyzer sub-panel instead of just deleted); the VIEW_3D panels retired entirely. Still
    needs the live-verify sweep (v0.2.7–current, plus this change itself).
  - **Virtualize the Missing + Duplicate lists to scrollable UILists** (user-scheduled @ v0.2.18) —
    fixed-height + scrollbar via `template_list`; flatten each hierarchy into one heterogeneous row
    collection drawn by a custom `draw_item` that still hosts checkbox / keeper dropdown / pickers.
    **Deliberately split off as its OWN follow-up (user, 2026-06-23)** — NOT done, still future work.

**ROADMAP — separate NEW FEATURES, NOT part of "finish-up" (schedule after the 5 batches):**
Automated Cleanup pipeline; Archive Project (BAT `pack`→zip); footprint reduction (Layer 2
resolution-standardize LOSSY + Layer 3 content-overlap hash dedup); reverse-dependency "safe to
delete?" check; lazy-depth scan; older Make-Local perf / In-Place-localize / shared-library-guard
bugs. Pull any into a batch on request.
- **Synology conflict-file diff/merge (user request, 2026-06-25, documentation only — no work
  started).** Synology Drive sometimes creates a `"... (conflicted copy ...)"` sibling file when the
  same .blend is edited on two computers and both saves land near-simultaneously. Wanted: open one of
  the files, pick the conflict sibling, AssetDoctor diffs the two and shows what's different, then
  lets the user selectively pull individual changes from the conflict copy into the currently open
  file. Scoping questions for whenever this gets picked up: diffing two arbitrary .blend files needs a
  datablock-level comparison (reuse `core.fingerprint`'s per-type fingerprinters — already proven for
  materials/actions — extended to whatever types matter most: objects/meshes/textures?) plus a way to
  show WHICH properties differ (the override `path_resolve` property-walk built for Phase 4-B's Flatten
  Plan is the closest existing primitive for "list every differing property between two like-named
  datablocks"); the "pull this one change in" mutation needs its own per-type apply logic, scoped with
  the user before building, same as every other mutating feature here.

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
- **DONE @ v0.2.35 (Batch E part 3) — N-panel → Properties migration plan (#7).** Shipped close to plan,
  with one simplification: skipped the separate `ASSETDOCTOR_PT_scene_root` step (1) since
  `ASSETDOCTOR_PT_scene_deps` already hosted the shared progress bar + Report UIList, so it could be the
  parent directly. Did: (2) re-homed Make Local/Materials/Orphans/Geometry/Resource Analyzer/Utilities as
  Scene sub-panels via `bl_parent_id`; (3) deleted the duplicate Project/Report N-panel sections outright,
  folded Resource's tree into Resource Analyzer instead of just deleting it; (4) dropped the VIEW_3D
  panels in the SAME pass (user chose no parity-check period, see "SESSION RESUME" / "BATCH E" for the
  full note). Still needs the live-Blender verify (registration is fragile — RESTART Blender, don't rely
  on Reload Scripts).

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
- **Cleanup later — DONE @ v0.2.37 (2026-06-24).** `ASSETDOCTOR_UL_broken_imgs` UIList,
  `core/imagepaths.diff_found`/`build_find_missing_report`/`build_image_report`/`FindMissingResult`,
  and their tests all removed (Phase 0 of the code-review/panel-dedup/UX-review plan).
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

## F7 origin story (2026-06-16, condensed)

F7 (Link & Dependency Doctor) exists because two real production files
(`PSM_Stage_v5.1.blend` + `v2.0_PSM_Final_SoundStage.blend`) crashed on load with thousands of
`lib.override.resync` dependency-loop warnings, traced to the same library referenced via
multiple different paths (duplicate library blocks) plus several genuine multi-hop indirect-
link chains and file-level circular library links. That investigation is what launched F7's
phased plan, the "footprint reduction = analyze-only for now" pillar, and the "Scene Debug"-
style inspector UI (count badges, per-row checkboxes, type-dropdown + datablock-picker) that's
shaped every panel built since — including this session's Check Materials feature. Full offline
scan output: `tools/scan_recursive.py` / `tools/_scan_soundstage.txt`.

**F7 phased plan status:** Phase 1 (recursive dependency scan) ✅, Phase 2 (live datablock link
map) ✅, Phase 3 (path normalization/remap) ✅, **Phase 4a (single-hop link retargeting) ✅ DONE**
— shipped as Datablock Reconnect + Examine Library. Still open:
- [ ] **Phase 4b — multi-hop link-chain flattening** (collapse a chain like material → char file
  → stage into a direct link, while preserving whatever an intermediate hop adds). See the
  dedicated "F7 Phase 4b — Link Chain Flattening" section near the top of this file for the full
  design (A: classify, B: build the override-with-transform action, C: defer modifier-driven/
  rig-specific cases).
- [ ] **Phase 5 — before/after diff** (snapshot library/datablock/duplicate-family counts + est.
  RAM + resync-warning count before and after a cleanup pass, diff the two). Generalizes the
  Automated Cleanup savings summary below.

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

## Still-open safety idea from early testing (2026-06-15)
- [ ] **Guard against running Make Local "In Place" on a shared LIBRARY file.** A file other
  scenes link thousands of datablocks from can have its datablocks renamed/removed by an
  in-place make-local+purge, breaking links from dependent files (and downstream library
  overrides — e.g. posed characters reverting to rest pose). Idea: detect "this file is likely a
  linked library / asset source" and warn before In-Place mutation (or steer to New File), BUT
  suppress the warning if the user has recently scanned the project (F1 link map) and is clearly
  working top-down in dependency order (they already know the impact). Never built — no such
  guard currently exists in `ops/make_local.py`.

## Progress & responsiveness — ALL actions
- [x] **Progress bar + status text for every action**, via `ops/progress.ModalProgressMixin`
  (subclass yields `(fraction, status)`, chunked per-datablock loops, ESC-to-cancel). Only
  Profile Render stays synchronous (a single render call can't be chunked).
- [x] **F2 (Make Local) performance on complex files** — fixed v0.1.7, one bulk
  `bpy.ops.object.make_local(type='ALL')` + bounded per-ID mop-up passes, instead of per-id
  passes over thousands of datablocks taking hours.

## Report UI v2 (from real-project testing)

The N-panel didn't virtualize manually-drawn rows, so a large report (hundreds of findings)
left rows blank past a point — fixed for good in v0.1.10 (`ASSETDOCTOR_UL_tree` over a real
`UIList`) and reused/extended by every later report/picker (Group 12). Click-to-select and
Outliner-focus-on-select are both built (`ops/report_store.py`).

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

Auto-updates (self-hosted gh-pages extension repository) and per-step version bumping were
both open questions early on — both long since standard practice (repo live at
rickpalo.github.io/AssetDoctor, [[feedback_versioning]] governs bump cadence).

## Future / deferred
- [ ] **M6 — F1 cross-file duplication census** (deferred by user; may be re-scoped after
  testing). Largely folded into M7 step 2's geometry-dedup engine; the cross-*file* count
  still needs an offline fingerprint path (headless-Blender pass per file, or a BAT-level
  signature).
