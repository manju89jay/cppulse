"""Developer verification cannot present planned or blocked work as complete."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def schema() -> dict[str, object]:
    """Load the developer operation contract before its orchestration exists."""
    return json.loads(
        (ROOT / "tools/contracts/development-result.schema.json").read_text()
    )


@pytest.fixture
def planned() -> dict[str, object]:
    """Represent a reviewed execution plan with no claim that it ran."""
    return {
        "version": "1.0.0",
        "operation": "verify",
        "scope": "full",
        "status": "planned",
        "exit_status": None,
        "started_at": "2026-11-14T00:00:00Z",
        "finished_at": "2026-11-14T00:00:00Z",
        "source": {},
        "checks": [{"name": "source-checks", "status": "planned"}],
        "limitations": ["A plan is not execution or product qualification."],
    }


def test_development_contract_is_valid_draft7(schema: dict[str, object]) -> None:
    jsonschema.Draft7Validator.check_schema(schema)


def test_plan_never_has_a_successful_execution_exit(
    schema: dict[str, object], planned: dict[str, object]
) -> None:
    jsonschema.validate(planned, schema)
    planned["exit_status"] = 0
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(planned, schema)


@pytest.mark.parametrize("unexecuted", ["planned", "blocked", "failed", "interrupted"])
def test_passing_verification_cannot_hide_unexecuted_or_failed_work(
    schema: dict[str, object], planned: dict[str, object], unexecuted: str
) -> None:
    document = copy.deepcopy(planned)
    document.update(status="passed", exit_status=0)
    document["checks"][0]["status"] = unexecuted
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, schema)


def test_full_success_requires_all_actual_stages_and_candidate_binding(
    schema: dict[str, object], planned: dict[str, object]
) -> None:
    document = copy.deepcopy(planned)
    document.update(status="passed", exit_status=0)
    document["checks"] = [{"name": "root-tests", "status": "passed"}]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(document, schema)
    document["candidate"] = {"manifest_sha256": "example-identity"}
    document["checks"] = [
        {"name": name, "status": "passed"} for name in schema["x-required-full-checks"]
    ]
    jsonschema.validate(document, schema)
