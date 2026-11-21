"""Architectural sums of measured file priorities, with incomplete scope visible."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import islice
import math
from typing import Any

from cppulse.errors import ContractError
from cppulse.git_miner.behavior import validate_behavior_report
from cppulse.maintenance import measured_hotspot_calculation


def _number(value: Any, name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"Measured hotspot {name} must be a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError as error:
        raise ContractError(f"Measured hotspot {name} must be finite") from error
    if not finite or value < 0:
        raise ContractError(f"Measured hotspot {name} must be finite and nonnegative")
    return value


def _inventory(paths: Iterable[str], name: str) -> set[str]:
    if isinstance(paths, (str, bytes)):
        raise ContractError(f"{name} hotspot scope must be a file inventory")
    try:
        files = list(islice(paths, 100001))
    except TypeError as error:
        raise ContractError(f"{name} hotspot scope must be a file inventory") from error
    if (
        len(files) > 100000
        or any(not isinstance(path, str) for path in files)
        or len(set(files)) != len(files)
    ):
        raise ContractError(f"{name} hotspot scope is duplicate, invalid or too large")
    return set(files)


def aggregate_component_hotspots(
    *,
    behavior: dict[str, Any],
    declared_files: Iterable[str],
    hotspot_scores: list[dict[str, Any]],
    excluded_files: Iterable[str] = (),
) -> dict[str, Any]:
    """Sum all measured member priorities without turning missing evidence into zero.

    Args:
        behavior: Validated historical report declaring component membership.
        declared_files: Complete ranked and unranked file scope, before display limits.
        hotspot_scores: All measured file calculations, including genuine zeros.
        excluded_files: Explicit excluded architectural members outside attempted
            ranking scope; they have no measured priority.

    Returns:
        Versioned component priorities and explicit observed/unavailable members.

    Raises:
        ContractError: Scope, mapping or supplied measured calculations disagree.
    """
    validate_behavior_report(behavior)
    scope = _inventory(declared_files, "Declared")
    excluded = _inventory(excluded_files, "Excluded")
    if scope & excluded or len(scope | excluded) > 100000:
        raise ContractError(
            "Excluded component members must be outside attempted scope"
        )
    if scope | excluded != {row["file"] for row in behavior["files"]}:
        raise ContractError(
            "Component mapping must exactly cover declared hotspot scope"
        )
    if not isinstance(hotspot_scores, list):
        raise ContractError("Measured hotspots must be a list of file calculations")
    measured: dict[str, int | float] = {}
    for row in hotspot_scores:
        if not isinstance(row, dict) or not isinstance(row.get("file"), str):
            raise ContractError("Measured hotspot requires a file identity")
        path = row["file"]
        if path not in scope or path in measured:
            raise ContractError(
                "Measured hotspot is duplicate or outside declared scope"
            )
        required = {
            "change_frequency",
            "complexity_score",
            "finding_count",
            "physical_loc",
            "hotspot_score",
            "debt_density",
        }
        if not required <= row.keys():
            raise ContractError("Measured hotspot is missing calculation inputs")
        expected = measured_hotspot_calculation(
            change_frequency=row["change_frequency"],
            complexity=row["complexity_score"],
            finding_count=row["finding_count"],
            physical_loc=row["physical_loc"],
        )
        for name in ("hotspot_score", "debt_density"):
            actual = _number(row[name], name)
            if not math.isclose(actual, expected[name], rel_tol=1e-12, abs_tol=0.0):
                raise ContractError(
                    "Measured hotspot calculation disagrees with inputs"
                )
        measured[path] = row["hotspot_score"]

    # A valid legacy calculation cannot qualify absent behavioral history. Still
    # validate every supplied row above so unavailable scope cannot hide corruption.
    history = behavior["history_status"]
    if history == "unavailable":
        measured = {}
    components = []
    for component in sorted(behavior["components"], key=lambda row: row["id"]):
        members = sorted(component["files"])
        known = [
            {"file": path, "score": measured[path]}
            for path in members
            if path in measured
        ]
        missing = [path for path in members if path not in measured]
        observed = math.fsum(row["score"] for row in known) if known else None
        availability = (
            "unavailable"
            if observed is None
            else "partial" if missing or history != "available" else "available"
        )
        components.append(
            {
                "id": component["id"],
                "files": members,
                "measured_files": known,
                "unavailable_files": missing,
                "availability": availability,
                "score": observed if availability == "available" else None,
                "observed_score": observed,
            }
        )
    return {
        "version": "1.0.0",
        "method": "sum-measured-file-hotspots-v1",
        "file_method": "measured-cc-physical-kloc-v1",
        "behavior_configuration_digest": behavior["configuration_digest"],
        "behavior_input_digest": behavior["input_digest"],
        "history_status": history,
        "excluded_files": sorted(excluded),
        "components": components,
        "limitations": [
            "Hotspot priority is heuristic, not a calibrated defect probability.",
            "Hotspot activity uses retained legacy history; behavioral lookback and exclusions apply to ownership/coupling only.",
            "Historical co-change is separate from static include/call dependencies.",
            "Hashes pin declared configuration/input integrity, not producer authentication.",
            "Incomplete components expose only a labelled observed subset sum.",
            "Excluded architectural members stay outside ranking and health denominators and have no measured hotspot priority.",
        ],
    }
