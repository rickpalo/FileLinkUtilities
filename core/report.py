"""Serializable report objects shared by all features (F1-F4).

A :class:`Report` is a flat list of :class:`Finding` rows plus some metadata.
Every feature emits one, so the UI, JSON export and CSV export are all generic.
This module is bpy-free and fully unit-tested.

Severity ordering (low -> high): ``info`` < ``warning`` < ``error``.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict, dataclass, field
from typing import Any

SEVERITIES = ("info", "warning", "error")


@dataclass
class Finding:
    """One row in a report.

    Attributes:
        category: Machine-readable group, e.g. "broken_link", "duplicate_material".
        message: Human-readable description.
        severity: One of :data:`SEVERITIES`.
        items: Names/paths this finding concerns (the affected datablocks/files).
        data: Arbitrary extra structured payload for the UI / Apply step.
        detail: Optional short right-aligned value shown on the finding's row
            (e.g. a count); purely cosmetic.
    """

    category: str
    message: str
    severity: str = "info"
    items: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    detail: str = ""

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError(
                f"severity must be one of {SEVERITIES!r}, got {self.severity!r}"
            )


@dataclass
class Report:
    """A titled collection of findings produced by one feature run."""

    title: str
    feature: str  # "F1".."F4"
    findings: list[Finding] = field(default_factory=list)
    # Optional per-category right-aligned detail string for the category header row
    # (overrides the default finding-count). Keyed by Finding.category.
    category_details: dict[str, str] = field(default_factory=dict)

    def add(self, finding: Finding) -> Finding:
        self.findings.append(finding)
        return finding

    def count(self, severity: str | None = None) -> int:
        if severity is None:
            return len(self.findings)
        if severity not in SEVERITIES:
            raise ValueError(f"unknown severity {severity!r}")
        return sum(1 for f in self.findings if f.severity == severity)

    @property
    def max_severity(self) -> str:
        """Highest severity present, or "info" when empty."""
        present = {f.severity for f in self.findings}
        for sev in reversed(SEVERITIES):
            if sev in present:
                return sev
        return "info"

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "feature": self.feature,
            "findings": [asdict(f) for f in self.findings],
            "category_details": dict(self.category_details),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Report":
        report = cls(title=d.get("title", ""), feature=d.get("feature", ""))
        report.category_details = dict(d.get("category_details", {}))
        for f in d.get("findings", []):
            report.findings.append(
                Finding(
                    category=f["category"],
                    message=f["message"],
                    severity=f.get("severity", "info"),
                    items=list(f.get("items", [])),
                    data=dict(f.get("data", {})),
                    detail=f.get("detail", ""),
                )
            )
        return report

    @classmethod
    def from_json(cls, text: str) -> "Report":
        return cls.from_dict(json.loads(text))

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def to_csv(self) -> str:
        """One row per finding; ``items`` joined with ';', ``data`` as JSON."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["category", "severity", "message", "items", "data"])
        for f in self.findings:
            writer.writerow(
                [
                    f.category,
                    f.severity,
                    f.message,
                    ";".join(f.items),
                    json.dumps(f.data, sort_keys=True) if f.data else "",
                ]
            )
        return buf.getvalue()


def default_export_filename(label: str) -> str:
    """``"Duplicate Textures"`` -> ``"FileLink_Duplicate_Textures.txt"`` —
    the file-browser default name for Export, so saving reports from
    different features doesn't always offer to overwrite the same generic
    ``FileLinkReport.txt``."""
    slug = "_".join(label.split())
    return f"FileLink_{slug}.txt" if slug else "FileLinkReport.txt"
