"""Planning cannot silently lose the ninth retained Docker obligation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_verifier() -> ModuleType:
    """Import the actual guard without executing its command entry point."""
    spec = importlib.util.spec_from_file_location(
        "production_plan_guard", ROOT / "docs/plans/verify_production_plan.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_planning_and_execution_retain_all_nine_obligations() -> None:
    module = load_verifier()
    result = module.verify()
    ledger = json.loads(
        (ROOT / "docs/plans/production-delivery-ledger.json").read_text()
    )
    assert result["supplemental_obligations"] == 9
    assert result["numbered_requirements"] == 118
    assert result["milestone_tasks"] == 60
    assert module.SUPPLEMENTAL <= {row["id"] for row in ledger["items"]}
    assert len(ledger["items"]) == 187


def test_dropping_docker_from_planning_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_verifier()
    tracker = json.loads(
        (ROOT / "docs/plans/production-completion-traceability.json").read_text()
    )
    tracker["supplemental_obligations"] = [
        row
        for row in tracker["supplemental_obligations"]
        if row["id"] != "ENV-DOCKER-COMPOSE"
    ]
    monkeypatch.setattr(module.json, "loads", lambda _: tracker)
    with pytest.raises(ValueError, match="Supplemental"):
        module.verify()
