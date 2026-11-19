"""Check full-spec plan coverage; this does not verify product implementation."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
NUMBERED = re.compile(r"^(?:PR|UX|FR-[A-Z]+|NFR-[A-Z]+|REL|AC)-\d+$")
TASK = re.compile(r"^M\d+-\d+$")
SUPPLEMENTAL = {
    "DESIGN-SCORER",
    "DESIGN-FINGERPRINT",
    "DESIGN-DEV-FACADE",
    "DESIGN-CPACK",
    "DESIGN-SIX-CORPUS",
    "ENV-MATRIX",
    "ENV-CMAKE",
    "HUMAN-USEFULNESS",
    "ENV-DOCKER-COMPOSE",
}


def source_items(path: Path, pattern: re.Pattern[str]) -> dict[str, list[str]]:
    """Read exact numbered table cells from an authoritative specification."""
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [part.strip() for part in line.strip().strip("|").split("|")]
        if pattern.fullmatch(cells[0]):
            if cells[0] in result:
                raise ValueError(f"Duplicate source ID: {cells[0]}")
            result[cells[0]] = cells[1:]
    return result


def verify() -> dict[str, object]:
    """Reject omitted IDs, changed source text, stale hashes and unassigned work."""
    folder = ROOT / "docs/plans"
    tracker = json.loads(
        (folder / "production-completion-traceability.json").read_bytes()
    )
    requirements = source_items(
        ROOT / "docs/specs/production-platform/requirements.md", NUMBERED
    )
    tasks = source_items(ROOT / "docs/specs/production-platform/tasks.md", TASK)
    expected = {**requirements, **tasks}
    rows = tracker["items"]
    actual = {row["id"]: row for row in rows}
    if len(actual) != len(rows) or set(actual) != set(expected):
        raise ValueError("Missing, extra or duplicate requirement/task IDs")
    if len(requirements) != 118 or len(tasks) != 60:
        raise ValueError("Specification inventory changed; explicit review is required")
    phases = {row["id"] for row in tracker["phases"]}
    plan = (folder / "cppulse-production-completion-plan.md").read_text()
    declared = set(re.findall(r"^\| (P\d+) \|", plan, re.MULTILINE))
    if phases != declared:
        raise ValueError("Plan/tracker delivery phases differ")
    for identity, row in actual.items():
        if row["original_source_cells"] != expected[identity]:
            raise ValueError(f"Changed or narrowed source text: {identity}")
        assigned = row["delivery_phases"]
        if not assigned or not set(assigned) <= phases:
            raise ValueError(f"Unassigned/unknown delivery phase: {identity}")
        if row["owner_phase"] not in assigned:
            raise ValueError(f"Missing owner phase: {identity}")
        if row["review_gates"] != ["R" + phase[1:] for phase in assigned]:
            raise ValueError(f"Review gates differ from assigned phases: {identity}")
        if not row["user_scope_change_required_to_remove"]:
            raise ValueError(f"Missing change-control boundary: {identity}")
        if identity.startswith(("M8-", "M9-")) and not row.get("original_optionality"):
            raise ValueError(f"Expansion optionality was lost: {identity}")
        for evidence in row["current_evidence"]:
            if not (ROOT / evidence).exists():
                raise ValueError(f"Missing baseline evidence: {identity}: {evidence}")
    supplemental = tracker["supplemental_obligations"]
    if {row["id"] for row in supplemental} != SUPPLEMENTAL:
        raise ValueError("Supplemental design/environment obligations differ")
    for row in supplemental:
        if not row["delivery_phases"] or not set(row["delivery_phases"]) <= phases:
            raise ValueError(f"Unassigned supplemental obligation: {row['id']}")
    for name, expected_sha in tracker["input_source_sha256"].items():
        path = ROOT / "docs/specs/production-platform" / name
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha:
            raise ValueError(f"Input specification changed without review: {name}")
    plan_path = folder / "cppulse-production-completion-plan.md"
    if hashlib.sha256(plan_path.read_bytes()).hexdigest() != tracker["plan_sha256"]:
        raise ValueError("Plan changed without regenerating its reviewed tracker")
    with (folder / "production-completion-traceability.csv").open(newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    csv_ids = [row["id"] for row in csv_rows]
    if (
        len(csv_ids) != len(set(csv_ids))
        or set(csv_ids) != set(expected) | SUPPLEMENTAL
    ):
        raise ValueError("CSV and JSON inventories differ")
    return {
        "status": "passed",
        "numbered_requirements": len(requirements),
        "milestone_tasks": len(tasks),
        "supplemental_obligations": len(supplemental),
        "unassigned_or_missing": 0,
        "scope": "Planning traceability only; not product completion or new test results",
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
