"""Reject scope loss and stale or invented acceptance in the execution ledger."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts.verify_delivery import verify_ledger

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ledger() -> dict:
    return json.loads((ROOT / "docs/plans/production-delivery-ledger.json").read_text())


def test_complete_inventory_is_visible_but_open_work_is_not_complete(
    ledger: dict,
) -> None:
    result = verify_ledger(ROOT, ledger)
    assert result["items"] == 187
    assert result["complete"] is False


def test_a_single_dropped_expansion_requirement_is_rejected(ledger: dict) -> None:
    ledger["items"] = [row for row in ledger["items"] if row["id"] != "M9-05"]
    with pytest.raises(ValueError, match="Missing.*M9-05"):
        verify_ledger(ROOT, ledger)


def test_rewording_a_requirement_cannot_silently_narrow_scope(ledger: dict) -> None:
    ledger["items"][0]["requirement"] = "Only a small demo is required"
    with pytest.raises(ValueError, match="Changed requirement"):
        verify_ledger(ROOT, ledger)


def test_source_presence_cannot_mark_a_requirement_verified(ledger: dict) -> None:
    ledger["items"][0].update(state="verified", evidence=[], review={})
    with pytest.raises(ValueError, match="evidence and independent review"):
        verify_ledger(ROOT, ledger)


def test_stale_source_cannot_reuse_a_passing_check(
    ledger: dict, tmp_path: Path
) -> None:
    root = tmp_path / "checkout"
    root.mkdir()
    for relative in [
        "docs/specs/production-platform/requirements.md",
        "docs/specs/production-platform/design.md",
        "docs/specs/production-platform/tasks.md",
        "docs/plans/production-completion-traceability.json",
    ]:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    implementation = root / "module.py"
    implementation.write_text("revised source\n")
    proof = root / "proof.json"
    log = root / "proof.log"
    log.write_text("1 passed\n")
    proof.write_text(
        json.dumps(
            {
                "status": "passed",
                "exit_code": 0,
                "check_id": "observed-test",
                "command": ["python", "-m", "pytest"],
                "source_files": {
                    "module.py": hashlib.sha256(b"old source\n").hexdigest()
                },
                "log": "proof.log",
                "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(),
            }
        )
    )
    item = ledger["items"][0]
    item.update(
        state="verified",
        evidence=["proof.json"],
        review={
            "reviewer": "independent-agent",
            "accepted": True,
            "scope": "Original full requirement",
        },
    )
    with pytest.raises(ValueError, match="Stale source"):
        verify_ledger(root, ledger)


def test_an_implemented_row_cannot_hide_a_missing_phase_assignment(
    ledger: dict,
) -> None:
    ledger["items"][0]["state"] = "implemented"
    ledger["items"][0]["phases"] = []
    with pytest.raises(ValueError, match="phase"):
        verify_ledger(ROOT, ledger)
