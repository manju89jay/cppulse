"""Check full production scope and current evidence without declaring planned work done."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
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


def _source_items(path: Path) -> dict[str, str]:
    items: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or not re.fullmatch(
            r"(?:PR|UX|FR-[A-Z]+|NFR-[A-Z]+|REL|AC|M\d)-\d{2}", cells[0]
        ):
            continue
        if cells[0] in items:
            raise ValueError(f"Duplicate source ID: {cells[0]}")
        items[cells[0]] = " | ".join(cells[1:])
    return items


def _within(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(
        root.resolve()
    ):
        raise ValueError(f"Evidence path escapes checkout: {relative}")
    return path


def _proof(root: Path, relative: str) -> None:
    path = _within(root, relative)
    data = json.loads(path.read_bytes())
    if data.get("status") != "passed" or data.get("exit_code") != 0:
        raise ValueError(f"Non-passing evidence: {relative}")
    if not data.get("command") or not data.get("source_files"):
        raise ValueError(f"Evidence lacks command/source binding: {relative}")
    log = _within(root, data["log"])
    if hashlib.sha256(log.read_bytes()).hexdigest() != data.get("log_sha256"):
        raise ValueError(f"Changed verification log: {relative}")
    for name, expected in data["source_files"].items():
        source = _within(root, name)
        if (
            not source.is_file()
            or hashlib.sha256(source.read_bytes()).hexdigest() != expected
        ):
            raise ValueError(f"Stale source evidence: {name}")


def verify_ledger(root: Path, ledger: dict[str, Any]) -> dict[str, Any]:
    """Reject missing scope, unverifiable acceptance and stale execution evidence.

    This checks the evidence boundary. Independent review still decides whether
    a passing check actually satisfies the original product requirement.
    """
    folder = root / "docs/specs/production-platform"
    expected = {
        **_source_items(folder / "requirements.md"),
        **_source_items(folder / "tasks.md"),
    }
    if len(expected) != 178:
        raise ValueError("Original requirement/task inventory changed; review required")
    rows = ledger["items"]
    actual = {row["id"]: row for row in rows}
    ids = set(expected) | SUPPLEMENTAL
    if len(actual) != len(rows) or set(actual) != ids:
        raise ValueError(
            f"Missing {sorted(ids-set(actual))}; extra or duplicate {sorted(set(actual)-ids)}"
        )
    phases = {phase["id"] for phase in ledger["phases"]}
    if phases != {f"P{number}" for number in range(15)}:
        raise ValueError("Full P0–P14 phase inventory is required")
    for name, digest in ledger["source_hashes"].items():
        if hashlib.sha256((folder / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Changed accepted specification: {name}")
    for identity, row in actual.items():
        if identity in expected and row["requirement"] != expected[identity]:
            raise ValueError(f"Changed requirement text: {identity}")
        if not row.get("phases") or not set(row["phases"]) <= phases:
            raise ValueError(f"Missing/unknown delivery phase: {identity}")
        state = row["state"]
        if state not in {"open", "active", "blocked", "implemented", "verified"}:
            raise ValueError(f"Unsupported delivery state: {identity}: {state}")
        if identity.startswith(("M8-", "M9-")) and not row.get("original_optionality"):
            raise ValueError(f"Expansion classification lost: {identity}")
        if state == "blocked" and not row.get("blocker"):
            raise ValueError(f"Blocked work needs an explanation: {identity}")
        if state == "verified":
            review = row.get("review") or {}
            if (
                not row.get("evidence")
                or not review.get("accepted")
                or not review.get("reviewer")
                or not review.get("scope")
            ):
                raise ValueError(
                    f"Verified row requires evidence and independent review: {identity}"
                )
            for proof in row["evidence"]:
                _proof(root, proof)
    counts = dict(Counter(row["state"] for row in rows))
    return {
        "items": len(rows),
        "states": counts,
        "complete": all(row["state"] == "verified" for row in rows),
    }


def main(argv: list[str] | None = None) -> int:
    """Validate scope; optionally require fully accepted, current delivery."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ledger",
        type=Path,
        default=ROOT / "docs/plans/production-delivery-ledger.json",
    )
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        result = verify_ledger(ROOT, json.loads(args.ledger.read_bytes()))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 3 if args.require_complete and not result["complete"] else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "invalid", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
