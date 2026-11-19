"""Mocked provider precision and contradictory-state contract regressions."""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from cppulse.errors import ContractError
from cppulse.issue_tracker import collect, validate_report


def request() -> dict:
    """Use an explicit finite public scope; every response is supplied in memory."""
    return {
        "version": "1.0.0",
        "provider": "github-rest-2022-11-28",
        "repository": "fixture/project",
        "window": {"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"},
        "limits": {"pages": 2, "page_bytes": 65536, "wall_seconds": 10},
        "cost_inputs": [],
    }


def issue(number: int = 1) -> dict:
    """Return one coherent observed issue, with no historical-state inference."""
    return {
        "number": number,
        "title": "Synthetic provider record",
        "state": "closed",
        "created_at": "2026-01-02T00:00:00Z",
        "updated_at": "2026-01-04T00:00:00Z",
        "closed_at": "2026-01-03T00:00:00Z",
        "html_url": f"https://github.com/fixture/project/issues/{number}",
    }


@pytest.mark.parametrize("field", ["start", "end", "recorded_at"])
def test_unsupported_request_precision_rejects_before_output_or_transport(
    tmp_path: Path, field: str
) -> None:
    cfg = request()
    if field == "recorded_at":
        cfg["cost_inputs"] = [
            {
                "id": "future-claim",
                "issue": 1,
                "kind": "cost",
                "basis": "estimated",
                "currency": "USD",
                "amount": 10,
                "recorded_at": "2026-02-01T00:00:00.0000001Z",
                "description": "Claim",
            }
        ]
    else:
        cfg["window"][field] = cfg["window"][field].replace("Z", ".0000001Z")
    called = []

    def get(url: str, timeout: float) -> tuple[int, dict, bytes]:
        called.append(url)
        return 200, {}, json.dumps([issue()]).encode()

    with pytest.raises(ContractError, match="timestamp"):
        collect(cfg, tmp_path / "output", transport=get)
    assert called == []
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("field", ["created_at", "updated_at", "closed_at"])
def test_provider_precision_is_not_silently_normalized(
    tmp_path: Path, field: str
) -> None:
    row = issue()
    row[field] = row[field].replace("Z", ".0000001Z")
    body = json.dumps([row]).encode()
    cfg = request()
    output = tmp_path / "output"
    result = collect(cfg, output, transport=lambda *_: (200, {}, body))
    assert result["status"] == "unavailable"
    assert result["issue_count"] is None
    assert result["issues"] == []
    assert (output / "page-001.body").read_bytes() == body
    validate_report(result, expected_request=cfg, output=output)


@pytest.mark.parametrize(
    "mutation", ["closed_after_update", "open_with_closure", "closed_without_closure"]
)
def test_contradictory_provider_state_does_not_qualify_complete_issue_scope(
    tmp_path: Path, mutation: str
) -> None:
    row = issue()
    if mutation == "closed_after_update":
        row["closed_at"] = "2026-01-05T00:00:00Z"
    elif mutation == "open_with_closure":
        row["state"] = "open"
    else:
        row["closed_at"] = None
    result = collect(
        request(),
        tmp_path / "output",
        transport=lambda *_: (200, {}, json.dumps([row]).encode()),
    )
    assert result["status"] == "unavailable"
    assert result["issue_count"] is None
    assert result["issues"] == []


@pytest.mark.parametrize("state", ["open", "closed"])
def test_coherent_open_or_closed_state_preserves_observation_without_history(
    tmp_path: Path, state: str
) -> None:
    row = issue()
    row.update(state=state, closed_at=None if state == "open" else row["updated_at"])
    row["created_at"] = "2026-01-02t00:00:00.123456z"
    result = collect(
        request(),
        tmp_path / "output",
        transport=lambda *_: (200, {}, json.dumps([row]).encode()),
    )
    assert result["status"] == "complete"
    assert result["issue_count"] == 1
    assert result["issues"][0]["state_observed"] == state
    assert result["issues"][0]["historical_state"] == "unknown"
    assert result["issues"][0]["created_at"] == "2026-01-02T00:00:00.123456+00:00"


def test_exact_microsecond_window_and_cost_availability_boundaries(
    tmp_path: Path,
) -> None:
    cfg = request()
    cfg["window"] = {
        "start": "2026-01-02T00:00:00.000001Z",
        "end": "2026-01-02T00:00:00.000002Z",
    }
    cfg["cost_inputs"] = [
        {
            "id": label,
            "issue": 1,
            "kind": "cost",
            "basis": "estimated",
            "currency": "USD",
            "amount": amount,
            "recorded_at": at,
            "description": "Finite cutoff control",
        }
        for label, amount, at in [
            ("at-cutoff", 10, "2026-01-02T00:00:00.000002Z"),
            ("after-cutoff", 1000, "2026-01-02T00:00:00.000003Z"),
        ]
    ]
    rows = [issue(1), issue(2)]
    rows[0]["created_at"] = cfg["window"]["start"]
    rows[1]["created_at"] = cfg["window"]["end"]
    result = collect(
        cfg,
        tmp_path / "output",
        transport=lambda *_: (200, {}, json.dumps(rows).encode()),
    )
    assert result["status"] == "complete"
    assert [row["number"] for row in result["issues"]] == [1]
    assert result["excluded"]["outside_created_window"] == 1
    assert result["excluded"]["future_cost_inputs"] == 1
    assert result["costs"][0]["cost"] == "10"
    assert result["costs"][0]["input_ids"] == ["at-cutoff"]


def test_bad_later_page_retains_prior_facts_without_inventing_total(
    tmp_path: Path,
) -> None:
    bodies = [json.dumps([issue(1)]).encode()]
    invalid = issue(2)
    invalid["closed_at"] = "2026-01-05T00:00:00Z"
    bodies.append(json.dumps([invalid]).encode())
    calls = []

    def get(url: str, timeout: float) -> tuple[int, dict, bytes]:
        index = len(calls)
        calls.append(url)
        headers = (
            {
                "Link": '<https://api.github.com/repos/fixture/project/issues?page=2>; rel="next"'
            }
            if index == 0
            else {}
        )
        return 200, headers, bodies[index]

    cfg, output = request(), tmp_path / "output"
    result = collect(cfg, output, transport=get)
    assert result["status"] == "partial"
    assert result["issue_count"] is None
    assert [row["number"] for row in result["issues"]] == [1]
    assert len(calls) == 2
    assert [page["parse_status"] for page in result["pages"]] == [
        "complete",
        "attempted",
    ]
    assert (output / "page-002.body").read_bytes() == bodies[1]
    validate_report(result, expected_request=cfg, output=output)
