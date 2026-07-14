"""The reusable "Select by confidence tier" operator behind the toolbar
(v0.3.x) — ticks/unticks the rows of any confidence-graded WM collection by
tier (High / High+Med / All / None). Generic on the collection name so every
graded list (reconnect today, others later) shares one operator; each row just
needs a ``confidence`` string and a ``selected`` bool. See core.confidence for
the shared ladder that makes one control mean the same thing everywhere.
"""

from __future__ import annotations

import bpy

from ..core.confidence import TIERS, selected_by_tier


class FILELINK_OT_select_by_confidence(bpy.types.Operator):
    bl_idname = "filelink.select_by_confidence"
    bl_label = "Select by Confidence"
    bl_description = ("Tick the rows at this confidence tier (and untick the rest): "
                      "High = exact/near-exact, High + Med adds fuzzy matches, All includes "
                      "weak guesses, None clears the selection")
    bl_options = {"INTERNAL"}

    collection: bpy.props.StringProperty()  # type: ignore[valid-type]
    tier: bpy.props.EnumProperty(  # type: ignore[valid-type]
        items=[(t, label, "") for t, label in TIERS], default="HIGH")

    def execute(self, context):
        wm = context.window_manager
        coll = getattr(wm, self.collection, None)
        if coll is None:
            self.report({"WARNING"}, f"No such list: {self.collection}")
            return {"CANCELLED"}
        n = 0
        for row in coll:
            want = selected_by_tier(getattr(row, "confidence", "none"), self.tier)
            if row.selected != want:
                row.selected = want
                n += 1
        # The reconnect picker draws `selected` live off these rows, so no
        # picker rebuild is needed — just repaint.
        if context.area:
            context.area.tag_redraw()
        return {"FINISHED"}
