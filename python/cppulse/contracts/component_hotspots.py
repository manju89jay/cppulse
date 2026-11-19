"""Scope checks for component sums of measured file hotspot priorities."""

from __future__ import annotations

import math
from typing import Any


def validate_component_hotspots(document: dict[str, Any]) -> None:
    """Reject incomplete or inconsistent component claims in risk output."""
    from .validation import _fail, _safe_path, _unique

    value = document["component_hotspots"]
    declared = {
        row["file"]
        for row in document["file_risks"] + document.get("unranked_files", [])
    }
    excluded = set(value.get("excluded_files", []))
    for path in excluded:
        _safe_path(path, "/component_hotspots/excluded_files")
    if excluded & declared:
        _fail("Excluded component members cannot enter attempted ranking scope", "/component_hotspots/excluded_files")
    scope = declared | excluded
    _unique(value["components"], "id", "/component_hotspots/components")
    assigned: set[str] = set()
    for index, row in enumerate(value["components"]):
        pointer = f"/component_hotspots/components/{index}"
        members = set(row["files"])
        for path in members:
            _safe_path(path, pointer + "/files")
        measured = _unique(row["measured_files"], "file", pointer + "/measured_files")
        missing = set(row["unavailable_files"])
        if members & assigned or not members <= scope:
            _fail("Component members overlap or leave the declared file scope", pointer)
        assigned.update(members)
        if set(measured) & missing or set(measured) | missing != members:
            _fail("Measured and unavailable members must partition the component", pointer)
        if set(measured) & excluded:
            _fail("Excluded component members cannot supply measured priorities", pointer)
        history = value["history_status"]
        if history == "unavailable" and measured:
            _fail("Unavailable history cannot supply measured hotspot priorities", pointer)
        try:
            observed = (
                math.fsum(item["score"] for item in row["measured_files"])
                if measured else None
            )
        except OverflowError:
            _fail("Component member sum exceeds finite evidence bounds", pointer)
        if observed is not None and not math.isfinite(observed):
            _fail("Component member sum must remain finite", pointer)
        availability = (
            "unavailable" if observed is None
            else "partial" if missing or history != "available"
            else "available"
        )
        if row["availability"] != availability:
            _fail("Component availability disagrees with measured scope/history", pointer)
        for key, expected in [
            ("observed_score", observed),
            ("score", observed if availability == "available" else None),
        ]:
            actual = row[key]
            if (actual is None) != (expected is None) or (
                actual is not None
                and not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=0)
            ):
                _fail("Component score disagrees with its measured member sum", pointer + "/" + key)
    if assigned != scope:
        _fail("Component mapping must cover the declared file scope", "/component_hotspots/components")
