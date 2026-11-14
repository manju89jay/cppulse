"""Hand-calculated contracts for measured maintenance facts and context health.

These are synthetic interface cases, not producer execution or accuracy claims.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from cppulse.contracts import validate, validate_bundle
from cppulse.errors import ContractError
from cppulse.identities import digest_json
from tests.test_analysis_inventory_contract import analysis_bundle as native_bundle
from tests.test_contracts_v2 import risk_document


def scorer() -> dict[str, Any]:
    """Define the initial published physical-KLOC calibration choices."""
    rules = [
        f"CPP-{family}-{number:03d}"
        for family, count in [("MEM", 3), ("CX", 3), ("MOD", 9)]
        for number in range(1, count + 1)
    ]
    result = {
        "id": "analyzed-kloc-context-v3",
        "version": "3.0.0",
        "profile": "default",
        "loc_metric": "physical_loc",
        "metric_version": "cppulse-metrics-1",
        "allow_inferred_parse": False,
        "required_rule_ids": rules,
        "required_rule_versions": {
            rule: (
                "prototype-2"
                if rule.startswith("CPP-CX-") or rule == "CPP-MOD-005"
                else "prototype-1"
            )
            for rule in rules
        },
        "categories": [
            {"category": "memory_safety", "weight": 3.0, "density_cap": 5.0},
            {"category": "complexity", "weight": 1.5, "density_cap": 10.0},
            {"category": "modernization", "weight": 1.0, "density_cap": 50.0},
        ],
    }
    result["configuration_digest"] = digest_json(result)
    return result


def health_context(identifier: str = "native") -> dict[str, Any]:
    """Hand calculation: weighted penalties total1; weights5.5; overall81.818…."""
    return {
        "job_context_id": identifier,
        "availability": "scored",
        "analysis_inventory_ids": ["native-inventory"],
        "metric_ids": ["loc-main", "code-main", "functions-main"],
        "declared_files": 1,
        "analyzed_files": 1,
        "excluded_files": 0,
        "physical_loc": 1000,
        "code_loc": 600,
        "parse_context_counts": {
            "database": 1,
            "inferred": 0,
            "fallback": 0,
            "none": 0,
        },
        "finding_counts": {"memory_safety": 1, "complexity": 2, "modernization": 5},
        "category_calculations": [
            {
                "category": "memory_safety",
                "count": 1,
                "density": 1.0,
                "penalty": 0.2,
                "score": 80.0,
            },
            {
                "category": "complexity",
                "count": 2,
                "density": 2.0,
                "penalty": 0.2,
                "score": 80.0,
            },
            {
                "category": "modernization",
                "count": 5,
                "density": 5.0,
                "penalty": 0.1,
                "score": 90.0,
            },
        ],
        "weighted_penalty": 1.0,
        "weight_sum": 5.5,
        "overall": 81.81818181818181,
        "limitations": [],
    }


def health_document() -> dict[str, Any]:
    """Return a synthetic authoritative result for one required job."""
    return {
        "version": "2.0.0",
        "id": "maintenance-health",
        "source_digest": "a" * 64,
        "scorer": scorer(),
        "consumer_assurance": "not_assessed",
        "required_context_ids": ["native"],
        "optional_context_ids": [],
        "contexts": [health_context()],
        "aggregate": {
            "availability": "scored",
            "overall": 81.81818181818181,
            "by_category": {
                "memory_safety": 80.0,
                "complexity": 80.0,
                "modernization": 90.0,
            },
            "worst_context_id": "native",
            "incomplete_required_context_ids": [],
            "limitations": [],
        },
        "limitations": ["Calibration constants are not empirically validated."],
    }


def metric_document() -> dict[str, Any]:
    """Declare normalized physical/code/function-count measurements."""
    return {
        "version": "2.0.0",
        "source_digest": "a" * 64,
        "analysis_inventory_id": "native-inventory",
        "job_context_id": "native",
        "items": [
            {
                "id": identifier,
                "file": "src/main.cpp",
                "symbol": None,
                "context_id": "parse-main",
                "metric": name,
                "metric_version": "cppulse-metrics-1",
                "value": value,
                "units": units,
                "availability": "available",
                "limitations": [],
            }
            for identifier, name, value, units in [
                ("loc-main", "physical_loc", 1, "lines"),
                ("code-main", "code_loc", 1, "lines"),
                ("functions-main", "function_count", 0, "functions"),
            ]
        ],
    }


def unavailable(
    context: dict[str, Any], reason: str = "Missing required measurement."
) -> None:
    """Retain observed counts but remove incomplete derived-score claims."""
    context["availability"] = "partial"
    context["overall"] = None
    context["weighted_penalty"] = None
    for calculation in context["category_calculations"]:
        calculation.update(density=None, penalty=None, score=None)
    context["limitations"] = [reason]


def incomplete_aggregate(result: dict[str, Any], missing: list[str]) -> None:
    """Represent a known required-context gap without a perfect or partial score."""
    result["aggregate"] = {
        "availability": "partial",
        "overall": None,
        "by_category": {
            category: None for category in result["contexts"][0]["finding_counts"]
        },
        "worst_context_id": None,
        "incomplete_required_context_ids": missing,
        "limitations": ["Required context evidence is incomplete."],
    }


def test_hand_calculated_density_context_is_a_valid_contract() -> None:
    result = health_document()
    validate("maintenance_health", result)
    assert result["aggregate"]["overall"] == pytest.approx(81.81818181818181)


def test_zero_violations_with_observed_nonzero_scope_can_score_100() -> None:
    result = health_document()
    context = result["contexts"][0]
    context["finding_counts"] = {name: 0 for name in context["finding_counts"]}
    for calculation in context["category_calculations"]:
        calculation.update(count=0, density=0.0, penalty=0.0, score=100.0)
    context.update(weighted_penalty=0.0, overall=100.0)
    result["aggregate"].update(
        overall=100.0, by_category={name: 100.0 for name in context["finding_counts"]}
    )
    validate("maintenance_health", result)


@pytest.mark.parametrize(
    "mutation",
    [
        "zero_loc",
        "wrong_density",
        "wrong_penalty",
        "wrong_category",
        "wrong_overall",
        "wrong_counts",
        "fake_context",
        "negative_weight",
        "duplicate_category",
        "inferred_without_optin",
        "fallback",
        "unknown_context_count",
        "fake_assurance",
        "method_changed_without_digest",
    ],
)
def test_complete_health_rejects_missing_or_inconsistent_prerequisites(
    mutation: str,
) -> None:
    result = health_document()
    context = result["contexts"][0]
    if mutation == "zero_loc":
        context["physical_loc"] = 0
    elif mutation == "wrong_density":
        context["category_calculations"][0]["density"] = 0.01
    elif mutation == "wrong_penalty":
        context["category_calculations"][0]["penalty"] = 0.0
    elif mutation == "wrong_category":
        context["category_calculations"][0]["score"] = 100.0
    elif mutation == "wrong_overall":
        context["overall"] = 99.0
    elif mutation == "wrong_counts":
        context["analyzed_files"] = 0
    elif mutation == "fake_context":
        context["job_context_id"] = "unselected-build"
    elif mutation == "negative_weight":
        result["scorer"]["categories"][0]["weight"] = -1
    elif mutation == "duplicate_category":
        result["scorer"]["categories"].append(
            deepcopy(result["scorer"]["categories"][0])
        )
    elif mutation == "inferred_without_optin":
        context["parse_context_counts"].update(database=0, inferred=1)
    elif mutation == "fallback":
        context["parse_context_counts"].update(database=0, fallback=1)
    elif mutation == "unknown_context_count":
        context["parse_context_counts"]["none"] = 1
    elif mutation == "fake_assurance":
        result["consumer_assurance"] = "passed"
    else:
        result["scorer"]["allow_inferred_parse"] = True
    with pytest.raises(ContractError):
        validate("maintenance_health", result)


def test_missing_required_context_is_visible_and_never_overridden_by_optional_score() -> (
    None
):
    result = health_document()
    result["required_context_ids"].append("windows-msvc")
    result["optional_context_ids"] = ["optional-linux"]
    result["contexts"].append(health_context("optional-linux"))
    incomplete_aggregate(result, ["windows-msvc"])
    validate("maintenance_health", result)
    result["aggregate"]["overall"] = 81.81818181818181
    with pytest.raises(ContractError):
        validate("maintenance_health", result)


def test_partial_context_retains_raw_counts_without_full_health() -> None:
    result = health_document()
    unavailable(result["contexts"][0])
    incomplete_aggregate(result, ["native"])
    validate("maintenance_health", result)
    result["contexts"][0]["category_calculations"][0]["score"] = 100
    with pytest.raises(ContractError):
        validate("maintenance_health", result)


def test_explicit_inferred_maintenance_optin_does_not_grant_consumer_assurance() -> (
    None
):
    result = health_document()
    config = result["scorer"]
    config["allow_inferred_parse"] = True
    config["configuration_digest"] = digest_json(
        {k: v for k, v in config.items() if k != "configuration_digest"}
    )
    context = result["contexts"][0]
    context["parse_context_counts"].update(database=0, inferred=1)
    context["limitations"] = [
        "Inferred parse arguments support maintenance only; consumer evidence remains unverified."
    ]
    validate("maintenance_health", result)
    assert result["consumer_assurance"] == "not_assessed"


def test_worst_context_selection_is_deterministic_and_category_values_are_not_mixed() -> (
    None
):
    result = health_document()
    result["required_context_ids"] = ["zulu", "alpha"]
    result["contexts"] = [health_context("zulu"), health_context("alpha")]
    result["aggregate"]["worst_context_id"] = "alpha"
    validate("maintenance_health", result)
    result["aggregate"]["worst_context_id"] = "zulu"
    with pytest.raises(ContractError):
        validate("maintenance_health", result)


def test_metric_profile_binds_job_separately_from_actual_parse_context() -> None:
    validate("analysis_metrics", metric_document())


@pytest.mark.parametrize(
    "mutation",
    [
        "negative",
        "fractional",
        "wrong_units",
        "code_above_physical",
        "duplicate_cell",
        "missing_job",
        "missing_inventory",
        "unavailable_zero",
        "unavailable_no_reason",
        "function_without_symbol",
        "reversed_location",
    ],
)
def test_named_metrics_are_measurements_with_explicit_missingness(
    mutation: str,
) -> None:
    result = metric_document()
    entry = result["items"][0]
    if mutation == "negative":
        entry["value"] = -1
    elif mutation == "fractional":
        entry["value"] = 1.5
    elif mutation == "wrong_units":
        entry["units"] = "percent"
    elif mutation == "code_above_physical":
        result["items"][1]["value"] = 2
    elif mutation == "duplicate_cell":
        duplicate = deepcopy(entry)
        duplicate["id"] = "different-id-same-cell"
        result["items"].append(duplicate)
    elif mutation == "missing_job":
        del result["job_context_id"]
    elif mutation == "missing_inventory":
        del result["analysis_inventory_id"]
    elif mutation == "unavailable_zero":
        entry["availability"] = "unavailable"
        entry["limitations"] = ["Measurement was not available."]
    elif mutation == "unavailable_no_reason":
        entry.update(availability="unavailable", value=None)
    elif mutation == "function_without_symbol":
        entry.update(
            metric="function_length",
            location={"line": 1, "column": 1, "end_line": 1, "end_column": 2},
        )
    else:
        entry.update(
            metric="function_length",
            symbol="usr:example",
            location={"line": 2, "column": 1, "end_line": 1, "end_column": 2},
        )
    with pytest.raises(ContractError):
        validate("analysis_metrics", result)


def test_old_generic_metric_contract_remains_supported() -> None:
    result = metric_document()
    result.pop("analysis_inventory_id")
    result.pop("job_context_id")
    for entry in result["items"]:
        entry["metric_version"] = "third-party-legacy-1"
    validate("analysis_metrics", result)


def bound_metric_bundle() -> dict[str, Any]:
    """Use existing synthetic receipt/inventory fixtures, not fabricated execution."""
    result = native_bundle.__wrapped__()
    metrics = metric_document()
    metrics["source_digest"] = result["run_manifest"]["source"]["digest"]
    result["analysis_metrics"] = metrics
    return result


def test_measured_metrics_reuse_the_existing_closed_native_lineage() -> None:
    validate_bundle(bound_metric_bundle())


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_job",
        "wrong_parse",
        "wrong_inventory",
        "partial_parse_positive",
        "wrong_source",
        "impossible_loc",
    ],
)
def test_metric_facts_cannot_outgrow_the_observed_native_subject(mutation: str) -> None:
    result = bound_metric_bundle()
    metrics = result["analysis_metrics"]
    if mutation == "wrong_job":
        metrics["job_context_id"] = "gcc17"
    elif mutation == "wrong_parse":
        metrics["items"][0]["context_id"] = "native"
    elif mutation == "wrong_inventory":
        metrics["analysis_inventory_id"] = "not-observed"
    elif mutation == "partial_parse_positive":
        result["analysis_inventory"]["items"][0].update(status="partial", error_count=1)
    elif mutation == "wrong_source":
        metrics["source_digest"] = "b" * 64
    else:
        metrics["items"][0]["value"] = 1000
    with pytest.raises(ContractError):
        validate_bundle(result)


def native_metric_report() -> dict[str, Any]:
    """Build a synthetic raw shape, not an assertion of executed source analysis."""
    return {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/repo",
            "analyzed_at": "2026-11-14T10:00:00Z",
            "file_count": 1,
            "total_loc": 1,
            "analysis": {
                "enabled_rules": ["CPP-MOD-001"],
                "files": [
                    {
                        "path": "/repo/a.cpp",
                        "status": "analyzed",
                        "compile_context": "database",
                        "error_count": 0,
                    }
                ],
                "native_metrics": {
                    "version": "1.0.0",
                    "metric_version": "cppulse-metrics-1",
                    "max_token_records": 100000,
                    "definitions": {
                        "physical_loc": "Physical lines including blanks/comments; terminal newline adds no extra line."
                    },
                    "files": [
                        {
                            "path": "/repo/a.cpp",
                            "status": "analyzed",
                            "error_count": 0,
                            "measurement_complete": True,
                            "physical_loc": 1,
                            "code_loc": 1,
                            "function_count": 1,
                            "functions": [
                                {
                                    "symbol": "c:@F@a#",
                                    "identity_kind": "usr",
                                    "name": "a",
                                    "kind": "function",
                                    "line": 1,
                                    "column": 1,
                                    "end_line": 1,
                                    "end_column": 12,
                                    "function_length": 1,
                                    "cyclomatic_complexity": 1,
                                    "nesting_depth": 0,
                                    "parameter_count": 0,
                                    "availability": "measured",
                                    "limitations": [],
                                }
                            ],
                            "token_stream": {
                                "method": "cppulse-spelled-tokens-1",
                                "availability": "measured",
                                "record_limit": 100000,
                                "complete": True,
                                "total_tokens": 1,
                                "retained_tokens": 1,
                                "records": [
                                    {
                                        "kind": "keyword",
                                        "spelling": "int",
                                        "line": 1,
                                        "column": 1,
                                        "end_line": 1,
                                        "end_column": 4,
                                    }
                                ],
                                "limitations": [],
                            },
                            "includes": [],
                            "limitations": [],
                        }
                    ],
                    "limitations": [
                        "Shape-only synthetic fixture; token inventory is not measured execution."
                    ],
                },
            },
        },
        "findings": [],
        "summary": {"total_findings": 0, "by_category": {}, "by_severity": {}},
    }


def test_native_metric_shape_is_additive_and_explicitly_versioned() -> None:
    validate("findings", native_metric_report(), version="prototype_v1")


@pytest.mark.parametrize(
    "mutation",
    [
        "wrong_status",
        "wrong_function_count",
        "hidden_missing_function",
        "unavailable_zero",
        "wrong_token_count",
        "hidden_truncation",
        "over_budget",
        "wrong_declared_budget",
        "missing_end",
        "no_truncation_reason",
        "outside_include",
    ],
)
def test_raw_native_metrics_cannot_claim_unobserved_or_truncated_completeness(
    mutation: str,
) -> None:
    result = native_metric_report()
    raw = result["metadata"]["analysis"]["native_metrics"]
    file = raw["files"][0]
    stream = file["token_stream"]
    if mutation == "wrong_status":
        file["status"] = "partial"
    elif mutation == "wrong_function_count":
        file["function_count"] = 0
    elif mutation == "hidden_missing_function":
        file["functions"][0]["cyclomatic_complexity"] = None
    elif mutation == "unavailable_zero":
        file["functions"][0]["availability"] = "unavailable"
        file["functions"][0]["limitations"] = ["Measurement unavailable."]
    elif mutation == "wrong_token_count":
        stream["retained_tokens"] = 0
    elif mutation == "hidden_truncation":
        stream["total_tokens"] = 2
    elif mutation == "over_budget":
        raw["max_token_records"] = stream["record_limit"] = 1
        stream["records"] *= 2
        stream["total_tokens"] = stream["retained_tokens"] = 2
    elif mutation == "wrong_declared_budget":
        stream["record_limit"] = 999
    elif mutation == "missing_end":
        del stream["records"][0]["end_line"]
    elif mutation == "no_truncation_reason":
        stream.update(availability="partial", complete=False, total_tokens=2)
    else:
        file["includes"] = [
            {
                "source": "a.cpp",
                "target": "../outside.hpp",
                "target_kind": "project",
                "direct": True,
            }
        ]
    with pytest.raises(ContractError):
        validate("findings", result, version="prototype_v1")


def test_truncated_tokens_preserve_separate_observed_ast_measurements() -> None:
    result = native_metric_report()
    raw = result["metadata"]["analysis"]["native_metrics"]
    raw["max_token_records"] = 1
    raw["files"][0]["token_stream"].update(
        record_limit=1,
        availability="partial",
        complete=False,
        total_tokens=2,
        limitations=[
            "Configured token record budget exhausted; duplication remains unavailable."
        ],
    )
    validate("findings", result, version="prototype_v1")
    assert raw["files"][0]["function_count"] == 1


def bound_health_bundle() -> dict[str, Any]:
    """Bind a narrow custom profile to one synthetic observed modernization rule."""
    import hashlib
    import json

    result = bound_metric_bundle()
    health = health_document()
    health["source_digest"] = result["run_manifest"]["source"]["digest"]
    config = health["scorer"]
    config.update(
        profile="custom",
        required_rule_ids=["CPP-MOD-001"],
        required_rule_versions={"CPP-MOD-001": "prototype-1"},
        categories=[{"category": "modernization", "weight": 1.0, "density_cap": 50.0}],
    )
    config["configuration_digest"] = digest_json(
        {key: value for key, value in config.items() if key != "configuration_digest"}
    )
    context = health["contexts"][0]
    context.update(
        physical_loc=1,
        code_loc=1,
        finding_counts={"modernization": 1},
        category_calculations=[
            {
                "category": "modernization",
                "count": 1,
                "density": 1000.0,
                "penalty": 1.0,
                "score": 0.0,
            }
        ],
        overall=0.0,
        weighted_penalty=1.0,
        weight_sum=1.0,
    )
    health["aggregate"].update(overall=0.0, by_category={"modernization": 0.0})
    result["maintenance_health"] = health
    content = (json.dumps(health, indent=2) + "\n").encode()
    result["run_manifest"]["artifacts"].append(
        {
            "id": health["id"],
            "path": "documents/maintenance-health.json",
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "media_type": "application/json",
            "contract": {"kind": "maintenance_health", "version": "2.0.0"},
        }
    )
    risk = risk_document()
    risk["maintenance_health_artifact_id"] = health["id"]
    risk["health_score"].update(
        overall=0.0,
        by_category={"modernization": 0.0},
        scorer_version="analyzed-kloc-context-v3",
    )
    result["risk_scores"] = risk
    return result


def test_health_and_risk_refer_to_one_authoritative_bound_calculation() -> None:
    validate_bundle(bound_health_bundle())


@pytest.mark.parametrize(
    "mutation",
    [
        "invented_loc",
        "invented_finding_count",
        "missing_metric",
        "disabled_rule",
        "wrong_rule_version",
        "omitted_rule",
        "fake_metric_job",
        "missing_health_artifact",
        "wrong_health_contract",
        "risk_recomputed_score",
    ],
)
def test_authoritative_health_must_reproduce_bound_native_inputs(mutation: str) -> None:
    result = bound_health_bundle()
    health = result["maintenance_health"]
    context = health["contexts"][0]
    if mutation == "invented_loc":
        context["physical_loc"] = 2
        calculation = context["category_calculations"][0]
        calculation["density"] = 500.0
    elif mutation == "invented_finding_count":
        context["finding_counts"]["modernization"] = 2
        context["category_calculations"][0].update(count=2, density=2000.0)
    elif mutation == "missing_metric":
        context["metric_ids"].remove("code-main")
    elif mutation == "disabled_rule":
        result["analysis_inventory"]["enabled_rules"] = []
    elif mutation == "wrong_rule_version":
        health["scorer"]["required_rule_versions"][
            "CPP-MOD-001"
        ] = "not-executed-version"
        health["scorer"]["configuration_digest"] = digest_json(
            {
                key: value
                for key, value in health["scorer"].items()
                if key != "configuration_digest"
            }
        )
    elif mutation == "omitted_rule":
        health["scorer"]["required_rule_ids"] = []
        health["scorer"]["required_rule_versions"] = {}
    elif mutation == "fake_metric_job":
        result["analysis_metrics"]["job_context_id"] = "parse-main"
    elif mutation == "missing_health_artifact":
        result["run_manifest"]["artifacts"] = [
            row
            for row in result["run_manifest"]["artifacts"]
            if row["id"] != health["id"]
        ]
    elif mutation == "wrong_health_contract":
        next(
            row
            for row in result["run_manifest"]["artifacts"]
            if row["id"] == health["id"]
        )["contract"]["kind"] = "analysis_metrics"
    else:
        result["risk_scores"]["health_score"]["overall"] = 100
    with pytest.raises(ContractError):
        validate_bundle(result)
