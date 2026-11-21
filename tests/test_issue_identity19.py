"""Canonical caller/provider identities over mocked transport only."""

from pathlib import Path
import json

import pytest

from cppulse import issue_tracker as candidate
from cppulse.errors import ContractError


def test_module_origin():
    here = Path(__file__).resolve()
    expected = (
        here.parent.parent / "python/cppulse/issue_tracker.py"
        if here.parent.name == "tests"
        else here.with_name("issue_tracker.py")
    )
    assert Path(candidate.__file__).resolve() == expected


def request():
    return {
        "version": "1.0.0",
        "provider": "github-rest-2022-11-28",
        "repository": "fixture/project",
        "window": {"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"},
        "limits": {"pages": 2, "page_bytes": 65536, "wall_seconds": 10},
        "cost_inputs": [],
    }


def cost():
    return {
        "id": "cost",
        "issue": 1,
        "kind": "cost",
        "basis": "estimated",
        "currency": "USD",
        "amount": 12.5,
        "recorded_at": "2026-01-05T00:00:00Z",
        "description": "caller declared",
    }


def issue():
    return {
        "number": 1,
        "title": "Mocked issue",
        "state": "open",
        "created_at": "2026-01-02T00:00:00Z",
        "updated_at": "2026-01-03T00:00:00Z",
        "closed_at": None,
        "html_url": "https://github.com/fixture/project/issues/1",
    }


@pytest.mark.parametrize("field,value", [("pages", 1.0), ("page_bytes", 65536.0)])
def test_count_limits_reject_integral_float_before_output_and_transport(
    tmp_path, field, value
):
    config = request()
    config["limits"][field] = value

    def forbidden(*args):
        pytest.fail("invalid request reached provider")

    output = tmp_path / "output"
    with pytest.raises(ContractError):
        candidate.collect(config, output, transport=forbidden)
    assert not output.exists()


def test_cost_foreign_key_is_an_exact_issue_integer(tmp_path):
    config = request()
    row = cost()
    row["issue"] = 1.0
    config["cost_inputs"] = [row]
    with pytest.raises(ContractError):
        candidate.validate_request(config)


@pytest.mark.parametrize("field", ["repository", "currency", "evidence_sha256"])
def test_final_newline_cannot_alias_canonical_scope_currency_or_digest(field):
    config = request()
    if field == "repository":
        config["repository"] += "\n"
    else:
        row = cost()
        config["cost_inputs"] = [row]
        if field == "currency":
            row[field] = "USD\n"
        else:
            row.update(basis="observed", evidence_sha256="a" * 64 + "\n")
    with pytest.raises(ContractError):
        candidate.validate_request(config)


def test_http_status_integral_float_never_qualifies_complete_response(tmp_path):
    report = candidate.collect(
        request(),
        tmp_path / "output",
        transport=lambda *_: (200.0, {}, json.dumps([issue()]).encode()),
    )
    assert report["status"] == "unavailable" and report["issue_count"] is None
    assert report["pages"] == [] and report["issues"] == []


def test_replay_counts_are_exact_integers(tmp_path):
    config = request()
    output = tmp_path / "output"
    report = candidate.collect(
        config, output, transport=lambda *_: (200, {}, json.dumps([issue()]).encode())
    )
    report["issue_count"] = 1.0
    with pytest.raises(ContractError):
        candidate.validate_report(report, expected_request=config, output=output)


def test_monetary_floats_and_fractional_wall_budget_remain_numbers(tmp_path):
    config = request()
    config["limits"]["wall_seconds"] = 1.25
    first = cost()
    second = {**cost(), "id": "benefit", "kind": "benefit", "amount": 18.75}
    config["cost_inputs"] = [first, second]
    report = candidate.collect(
        config,
        tmp_path / "output",
        transport=lambda *_: (200, {}, json.dumps([issue()]).encode()),
    )
    assert report["status"] == "complete" and report["issue_count"] == 1
    assert (
        report["costs"][0]["issue"] == 1
        and type(report["costs"][0]["issue"]) is int  # noqa: E721 -- exact ID type
    )
    assert report["costs"][0]["roi_ratio"] == "0.5"
    assert report["costs"][0]["currency"] == "USD"


@pytest.mark.parametrize("status", [None, True, "200", 99, 600])
def test_unusable_transport_status_retains_unknown_total(tmp_path, status):
    report = candidate.collect(
        request(), tmp_path / "output", transport=lambda *_: (status, {}, b"[]")
    )
    assert report["status"] == "unavailable" and report["issue_count"] is None
    assert not report["pages"] and not report["issues"]
    assert any("HTTP status" in limitation for limitation in report["limitations"])


@pytest.mark.parametrize(
    "field", ["http_status", "size_bytes", "outside_created_window", "pull_requests"]
)
def test_replay_receipt_and_exclusion_counts_are_exact(tmp_path, field):
    config = request()
    output = tmp_path / "output"
    report = candidate.collect(
        config, output, transport=lambda *_: (200, {}, json.dumps([issue()]).encode())
    )
    row = (
        report["pages"][0]
        if field in ("http_status", "size_bytes")
        else report["excluded"]
    )
    row[field] = float(row[field])
    with pytest.raises(ContractError):
        candidate.validate_report(report, expected_request=config, output=output)


def test_valid_observed_cost_hash_retains_caller_claim_scope(tmp_path):
    config = request()
    row = cost()
    row.update(basis="observed", evidence_sha256="a" * 64)
    config["cost_inputs"] = [row]
    report = candidate.collect(
        config,
        tmp_path / "output",
        transport=lambda *_: (200, {}, json.dumps([issue()]).encode()),
    )
    assert (
        report["status"] == "complete"
        and report["costs"][0]["status"] == "missing_benefit"
    )
    assert report["costs"][0]["evidence_status"] == "caller_claim_unverified"
