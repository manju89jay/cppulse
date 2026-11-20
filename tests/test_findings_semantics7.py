"""Suppression timing regressions over labeled synthetic retained native facts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cppulse.errors import ContractError
from cppulse.findings import compare_findings, create_finding_baseline
from test_findings import SCOPE, baseline, compare, normalized, now


def finer_than_microseconds(value: str) -> str:
    """Place an instant strictly after an exact microsecond without changing it."""
    instant = datetime.fromisoformat(value)
    return instant.isoformat(timespec="microseconds").replace("+00:00", "1+00:00")


@pytest.fixture
def comparison_inputs(tmp_path: Path) -> tuple:
    old, _ = baseline(tmp_path, count=0)
    current = normalized(tmp_path, count=1)
    initial = compare(current, old).document
    metadata = create_finding_baseline(
        current,
        baseline_id="timing-inspection",
        reason="Synthetic timing scope",
        created_at=now(),
        **SCOPE,
    ).document
    instant = datetime.now(timezone.utc) + timedelta(seconds=1)
    request = {
        "id": "reviewed-timing",
        "gate": "finding_regression",
        "baseline_sha256": initial["baseline_sha256"],
        "fingerprint_version": "native-line-anchor-1",
        "fingerprint": initial["groups"][0]["fingerprint"],
        "file": "main.cpp",
        "context_id": "native",
        "parse_context_digest": metadata["cells"][0]["parse_context_digest"],
        "rule_id": "CPP-MOD-001",
        "rule_version": metadata["findings"][0]["rule_version"],
        "max_count": 1,
        "reason": "Explicit synthetic bounded review",
        "owner": "fixture-owner",
        "approved_at": (instant - timedelta(seconds=1)).isoformat(),
        "expires_at": (instant + timedelta(days=1)).isoformat(),
    }
    return current, old, instant, request


@pytest.mark.parametrize("field", ["approved_at", "expires_at", "generated_at"])
def test_unsupported_precision_cannot_authorize_or_retime_suppression(
    comparison_inputs: tuple, field: str
) -> None:
    current, old, instant, request = comparison_inputs
    generated = instant.isoformat()
    if field == "generated_at":
        generated = finer_than_microseconds(generated)
    elif field == "approved_at":
        # Original parser truncated this future approval to generated_at,
        # suppressing a new occurrence before approval actually became effective.
        request[field] = finer_than_microseconds(generated)
    else:
        request[field] = finer_than_microseconds(request[field])
    with pytest.raises(ContractError, match="precision"):
        compare_findings(
            current,
            old,
            baseline_artifact_id="baseline",
            generated_at=generated,
            suppressions=[request],
            **SCOPE,
        )


def test_baseline_creation_does_not_silently_truncate_requested_time(
    tmp_path: Path,
) -> None:
    current = normalized(tmp_path)
    with pytest.raises(ContractError, match="precision"):
        create_finding_baseline(
            current,
            baseline_id="precision-baseline",
            reason="Explicit timestamp",
            created_at=finer_than_microseconds(now()),
            **SCOPE,
        )


@pytest.mark.parametrize(
    "approved_delta,expiry_delta,active",
    [(0, 1, True), (1, 2, False), (-1, 0, False), (-1, 1, True)],
)
def test_exact_microsecond_suppression_boundaries_preserve_raw_occurrences(
    comparison_inputs: tuple, approved_delta: int, expiry_delta: int, active: bool
) -> None:
    current, old, instant, request = comparison_inputs
    request.update(
        approved_at=(instant + timedelta(microseconds=approved_delta)).isoformat(),
        expires_at=(instant + timedelta(microseconds=expiry_delta)).isoformat(),
    )
    original = current.manifest
    result = compare_findings(
        current,
        old,
        baseline_artifact_id="baseline",
        generated_at=instant.isoformat(),
        suppressions=[request],
        **SCOPE,
    ).document
    assert result["counts"]["new"] == result["counts"]["current"] == 1
    assert result["counts"]["suppressed_new"] == int(active)
    assert result["counts"]["unsuppressed_new"] == int(not active)
    assert result["suppressions"][0]["active"] is active
    assert result["gate"] == ("passed" if active else "failed")
    assert current.manifest == original
