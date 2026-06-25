"""Phase 3a — the Analyze section's "Analyze All" sequencer.

Runs every step in ``core.analyze_steps.STEPS`` in order via its real operator
id (``bpy.ops.<category>.<name>(**kwargs)``), one step per call, so each step's
own logic/report-stashing runs completely unchanged — this is a dispatcher, not
a reimplementation. A modal (not a tight Python loop) so the panel can repaint a
per-step status icon between steps and ESC still cancels; ``execute`` (the
EXEC_DEFAULT / scripting / headless-test path) drains the same generator
synchronously via ``ModalProgressMixin``.

A step that raises (a bad file state, a cancelled sub-scan, …) is caught and
marked "error" — one bad step shouldn't stop the rest from running.
"""

from __future__ import annotations

import bpy

from ..core.analyze_steps import STEPS
from .progress import ModalProgressMixin, set_result


def _call(opname: str, kwargs: dict):
    category, name = opname.split(".", 1)
    getattr(getattr(bpy.ops, category), name)(**kwargs)


class ASSETDOCTOR_OT_analyze_all(ModalProgressMixin, bpy.types.Operator):
    bl_idname = "assetdoctor.analyze_all"
    bl_label = "Analyze All"
    bl_description = (
        "Run every Analyze check below in sequence against the CURRENT file, one "
        "click instead of N. Read-only — each step's own report/list is filled in "
        "exactly as if you'd clicked it yourself"
    )
    bl_options = {"REGISTER"}

    def run_steps(self, context):
        wm = context.window_manager
        coll = wm.assetdoctor_analyze_steps
        coll.clear()
        for step in STEPS:
            row = coll.add()
            row.key = step.key
            row.label = step.label
            row.status = "pending"

        n = len(STEPS)
        errors = 0
        for i, step in enumerate(STEPS):
            coll[i].status = "running"
            yield i / n, f"Running {step.label}…"
            try:
                _call(step.opname, step.kwargs)
                coll[i].status = "done"
            except Exception as exc:  # one bad step shouldn't stop the rest
                coll[i].status = "error"
                errors += 1
                from ..log import get_logger

                get_logger().warning("Analyze All: %s failed: %s", step.key, exc)
            yield (i + 1) / n, f"{step.label} done"

        msg = f"Analyze All: {n} check(s) done" + (f", {errors} failed" if errors else "")
        set_result(context, msg, ok=not errors)
        self.report({"WARNING"} if errors else {"INFO"}, msg)
