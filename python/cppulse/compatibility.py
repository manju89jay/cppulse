"""Explicit readers for legacy risk output and semantically honest v2 conversion."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from cppulse.contracts import validate
from cppulse.errors import CompatibilityError, UnsupportedVersion


def read_prototype_document(kind: str, document: dict[str, Any]) -> dict[str, Any]:
    """Read the known unreleased v1-shaped prototype contract explicitly.

    This validates existing native pipeline output without claiming it is a
    released v2 contract or inventing execution/completeness provenance.
    """
    validate(kind, document, version="prototype_v1")
    return deepcopy(document)


def read_risk_scores(
    document: dict[str, Any], *, allow_prototype_v1: bool = False
) -> dict[str, Any]:
    """Normalize supported risk documents without inventing probability claims.

    Args:
        document: Original legacy, explicit prototype-v1 or v2 risk object.
        allow_prototype_v1: Opt into the unreleased v1-shaped extension. The
            original frozen v1 schema is otherwise used for version 1.0.0.

    Returns:
        A validated v2 document. Legacy observed health is retained separately
        while full-scope health and unverifiable evaluation remain unavailable.

    Raises:
        ContractError: If input violates its selected contract.
        UnsupportedVersion: If the major/format is unsupported.
    """
    version = document.get("version")
    if version == "2.0.0":
        validate("risk_scores", document)
        return deepcopy(document)
    if version != "1.0.0":
        raise UnsupportedVersion(f"Cannot read risk_scores version {version!r}")
    validate(
        "risk_scores",
        document,
        version="prototype_v1" if allow_prototype_v1 else "1.0.0",
    )
    metadata = document["metadata"]
    old_health = document["health_score"]
    limitations = list(metadata.get("limitations", []))
    limitations.append(
        "Legacy model/evaluation metadata is an unverified producer claim; rank values are not calibrated defect probabilities."
    )
    limitations.append(
        "Legacy risk output alone does not establish source-scope completeness; original observed health is retained separately."
    )
    active_features = metadata.get("active_features")
    method = metadata["model_type"] if allow_prototype_v1 else "legacy_claim_unverified"
    if active_features is None:
        feature_count = None
    else:
        feature_count = len(active_features)
    status = old_health.get("status")
    availability = status if status in {"partial", "no_data"} else "unverified"
    result: dict[str, Any] = {
        "version": "2.0.0",
        "metadata": {
            "generated_at": metadata["generated_at"],
            "method": method,
            "score_kind": "heuristic_rank" if method == "heuristic" else "model_rank",
            "experimental": True,
            "feature_count": feature_count,
            "active_features": active_features,
            "training_samples": metadata.get("training_samples", 0),
            "label_source": metadata.get("label_source", "legacy_unverified"),
            "evaluation_status": "not_evaluated",
            "f1_score": None,
            "limitations": limitations,
        },
        "health_score": {
            "overall": None,
            "by_category": {key: None for key in old_health["by_category"]},
            "availability": availability,
            "scorer_version": metadata.get("score_model", "legacy_unverified"),
            "denominator": 0,
            "limitations": [
                "No source inventory is established by this legacy document."
            ],
        },
        "file_risks": [
            {
                "file": entry["file"],
                "score": entry["bug_probability"],
                "risk_level": entry["risk_level"],
                "top_factors": deepcopy(entry["top_factors"]),
                "explanation_kind": "legacy_unverified",
            }
            for entry in document["file_risks"]
        ],
        "hotspots": [
            {
                "file": entry["file"],
                "score": entry["hotspot_score"],
                "method": metadata.get("hotspot_formula", "legacy_proxy_unverified"),
                "finding_count": entry.get("finding_count", 0),
            }
            for entry in document["hotspots"]
            if entry["hotspot_score"] > 0
        ],
        "legacy_observed_health": old_health["overall"],
    }
    if "feature_count" in metadata:
        result["metadata"]["legacy_reported_feature_count"] = metadata["feature_count"]
    validate("risk_scores", result)
    return result


def export_legacy_risk_scores(document: dict[str, Any]) -> dict[str, Any]:
    """Round-trip original v1 input; refuse invented v2-to-v1 semantics.

    New ranking/availability semantics have no generally safe representation
    in the original v1 probability/numeric-health contract. Callers can keep
    an original valid v1 object unchanged, but cannot silently downgrade v2.
    """
    if document.get("version") == "1.0.0":
        validate("risk_scores", document, version="1.0.0")
        return deepcopy(document)
    raise CompatibilityError(
        "Risk v2 cannot be exported as original v1 without losing method, unavailable-health and ranking semantics.",
        code="LEGACY_EXPORT_NOT_REPRESENTABLE",
    )
