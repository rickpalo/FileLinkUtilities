"""Phase 3a — the Analyze section's "Analyze All" sequencer + the smaller
"Find Duplicates" sequencer scoped to just the duplicate-detection checks
(item 3, 2026-06-25).

Runs a list of ``core.analyze_steps.AnalyzeStep``s in order via each one's real
operator id (``bpy.ops.<category>.<name>(**kwargs)``), one step per call, so
each step's own logic/report-stashing runs completely unchanged — this is a
dispatcher, not a reimplementation. A modal (not a tight Python loop) so the
panel can repaint a per-step status icon between steps and ESC still cancels;
``execute`` (the EXEC_DEFAULT / scripting / headless-test path) drains the same
generator synchronously via ``ModalProgressMixin``.

A step that raises (a bad file state, a cancelled sub-scan, …) is caught and
marked "error" — one bad step shouldn't stop the rest from running.
"""

from __future__ import annotations

import bpy

from ..core.analyze_steps import DUPLICATE_STEPS, STEPS
from .progress import ModalProgressMixin, set_result


def _call(opname: str, kwargs: dict):
    category, name = opname.split(".", 1)
    getattr(getattr(bpy.ops, category), name)(**kwargs)


class _AnalyzeSequencerMixin:
    """Shared dispatcher body for both sequencer operators below. Deliberately
    a PLAIN mixin (not a registered Operator) — subclassing one already-
    registered ``bpy.types.Operator`` from another corrupts Blender's RNA
    python-class binding for the FIRST one once the second is also
    registered (confirmed via an isolated repro: the parent's ``execute``
    silently stops running and ``bpy.ops`` calls return FINISHED having done
    nothing). That was the actual cause of "Analyze All no longer works"
    (docs/TODO.md Group 10 #34) — ``ASSETDOCTOR_OT_find_duplicates`` used to
    subclass ``ASSETDOCTOR_OT_analyze_all`` directly.

    Set per-operator via class attributes: ``_steps`` (which
    ``AnalyzeStep``s to run) and ``_run_label`` (feeds the closing message).
    """

    _steps = STEPS
    _run_label = "Analyze All"

    def run_steps(self, context):
        wm = context.window_manager
        coll = wm.assetdoctor_analyze_steps
        coll.clear()
        steps = self._steps
        for step in steps:
            row = coll.add()
            row.key = step.key
            row.label = step.label
            row.status = "pending"

        n = len(steps)
        errors = 0
        for i, step in enumerate(steps):
            coll[i].status = "running"
            yield i / n, f"Running {step.label}…"
            try:
                _call(step.opname, step.kwargs)
                coll[i].status = "done"
            except Exception as exc:  # one bad step shouldn't stop the rest
                coll[i].status = "error"
                errors += 1
                from ..log import get_logger

                get_logger().warning("%s: %s failed: %s", self._run_label, step.key, exc)
            yield (i + 1) / n, f"{step.label} done"

        msg = f"{self._run_label}: {n} check(s) done" + (f", {errors} failed" if errors else "")
        set_result(context, msg, ok=not errors)
        self.report({"WARNING"} if errors else {"INFO"}, msg)


class ASSETDOCTOR_OT_analyze_all(_AnalyzeSequencerMixin, ModalProgressMixin, bpy.types.Operator):
    bl_idname = "assetdoctor.analyze_all"
    bl_label = "Analyze All"
    bl_description = (
        "Run every Analyze check below in sequence against the CURRENT file, one "
        "click instead of N. Read-only — each step's own report/list is filled in "
        "exactly as if you'd clicked it yourself"
    )
    bl_options = {"REGISTER"}

    _steps = STEPS
    _run_label = "Analyze All"


class ASSETDOCTOR_OT_find_duplicates(_AnalyzeSequencerMixin, ModalProgressMixin, bpy.types.Operator):
    """Item 3, 2026-06-25 (user request): "Find Duplicate Materials/Geometry/
    Content" folded into ONE "Find Duplicates" trigger alongside Find
    Duplicate Data-blocks — same dispatcher as Analyze All, just scoped to the
    duplicate-detection subset; each scan's own existing report/list section
    is untouched, so the combined result reads as one summary followed by
    what each individual button would have shown. Resolution Variants is a
    DIFFERENT kind of analysis (multi-res footprint, not strict duplicates)
    and deliberately stays its own separate button."""

    bl_idname = "assetdoctor.find_duplicates"
    bl_label = "Find Duplicates"
    bl_description = (
        "Find duplicate data-blocks, materials, geometry, and image content in "
        "one click (was 4 separate buttons). Read-only — each one's own report/"
        "list below is filled in exactly as if you'd clicked it yourself"
    )
    bl_options = {"REGISTER"}

    _steps = DUPLICATE_STEPS
    _run_label = "Find Duplicates"
