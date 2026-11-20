"""Synthetic raw-contract compatibility and include-buffer claim boundaries."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from cppulse.contracts import validate
from cppulse.errors import ContractError
from tests.test_maintenance_metrics_contract import native_metric_report


def report_with_edge(
    identity: dict[str, Any] | None = None, *, kind: str = "project"
) -> dict[str, Any]:
    """Build a labeled synthetic edge, without claiming producer execution."""
    report = native_metric_report()
    edge = {"source": "a.cpp", "target": "a.hpp", "target_kind": kind, "direct": True}
    if identity is not None:
        edge["content_identity"] = deepcopy(identity)
    report["metadata"]["analysis"]["native_metrics"]["files"][0]["includes"] = [edge]
    return report


def available() -> dict[str, Any]:
    """Return a synthetic well-shaped buffer observation for contract testing."""
    return {
        "method": "libclang-tu-buffer-sha256-v1",
        "status": "available",
        "sha256": "a" * 64,
        "size_bytes": 17,
    }


def test_path_only_legacy_include_remains_a_valid_unproven_observation() -> None:
    validate("findings", report_with_edge(), version="prototype_v1")


def test_observed_buffer_and_explicit_unavailable_identity_are_additive() -> None:
    validate("findings", report_with_edge(available()), version="prototype_v1")
    identity = {
        "method": "libclang-tu-buffer-sha256-v1",
        "status": "unavailable",
        "sha256": None,
        "size_bytes": None,
    }
    validate(
        "findings",
        report_with_edge(identity, kind="unresolved"),
        version="prototype_v1",
    )


@pytest.mark.parametrize(
    "mutation",
    [
        {"sha256": None},
        {"size_bytes": None},
        {"size_bytes": -1},
        {"size_bytes": True},
        {"sha256": "not-a-digest"},
        {"method": "fresh-filesystem-reread"},
        {"status": "unavailable"},
    ],
)
def test_inconsistent_or_unknown_byte_identity_is_rejected(
    mutation: dict[str, Any],
) -> None:
    identity = available()
    identity.update(mutation)
    with pytest.raises(ContractError):
        validate("findings", report_with_edge(identity), version="prototype_v1")


def test_unresolved_header_cannot_claim_an_observed_buffer() -> None:
    with pytest.raises(ContractError):
        validate(
            "findings",
            report_with_edge(available(), kind="unresolved"),
            version="prototype_v1",
        )
