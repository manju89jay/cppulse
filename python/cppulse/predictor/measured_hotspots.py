"""Extract measured hotspot prerequisites without treating severity as complexity."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from cppulse.contracts import validate
from cppulse.contracts.maintenance import METRIC_VERSION
from .feature_engineer import relative_identity


def native_hotspot_metrics(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Read only complete producer-reported CC/LOC; absence remains unavailable.

    This does not authenticate the producer, verify current source or borrow
    execution evidence. The enclosing snapshot retains those distinct limits.
    """
    raw = report.get("metadata", {}).get("analysis", {}).get("native_metrics")
    if raw is None:
        return {}
    validate("findings", report, version="prototype_v1")
    return _reported_hotspot_claims(report, raw["files"], raw["metric_version"])


def _reported_hotspot_claims(
    report: dict[str, Any], files: Iterable[dict[str, Any]], metric_version: str | None
) -> dict[str, dict[str, Any]]:
    """Extract literal claims only after the caller validates original semantics.

    This private boundary carries no execution/source/cache assurance. The
    ordinary JSON caller above validates the full report; the streaming caller
    validates schema and the original complete native frame census first.
    """
    if metric_version != METRIC_VERSION:
        return {}
    result = {}
    for index, file in enumerate(files):
        functions = file["functions"]
        if (
            not file.get("source_content_sha256")
            or not file["measurement_complete"]
            or file["status"] != "analyzed"
            or file["error_count"]
            or not file["physical_loc"]
            or not functions
            or len(functions) != file["function_count"]
            or any(
                row["availability"] != "measured"
                or row["cyclomatic_complexity"] is None
                for row in functions
            )
        ):
            continue
        result[relative_identity(file["path"], report)] = {
            "physical_loc": file["physical_loc"],
            "complexity_score": max(row["cyclomatic_complexity"] for row in functions),
            "metric_version": metric_version,
            "metrics_source": f"/metadata/analysis/native_metrics/files/{index}",
            "source_content_sha256": file["source_content_sha256"],
            "metric_provenance": "retained-native-report-claim",
        }
    return result
