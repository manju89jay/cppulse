"""Current policy evaluation never upgrades legacy unbound parse facts."""

from copy import deepcopy

import pytest

from cppulse.policy import evaluate_policy
from test_policy import NOW, analysis_documents, analysis_policy
from test_policy_extensions_runtime import metric_selected, metrics_bundle


@pytest.mark.parametrize("coherence", [None, "unverified", "mismatched", "verified"])
def test_metric_policy_requires_current_buffer_proof(coherence):
    bundle = metrics_bundle()
    row = bundle["analysis_inventory"]["items"][0]
    row["context_match"] = "matched"
    row.pop("buffer_coherence", None)
    if coherence is not None:
        row["buffer_coherence"] = coherence
    before = deepcopy(bundle)
    result = evaluate_policy(metric_selected(), bundle, generated_at=NOW)
    assert result["controls"][0]["status"] == (
        "passed" if coherence == "verified" else "unknown"
    )
    assert result["native_input_binding"] == "tu-buffer-coherence-v1"
    assert bundle == before


@pytest.mark.parametrize("coherence", [None, "unverified", "mismatched", "verified"])
def test_native_policy_predicates_require_current_buffer_proof(tmp_path, coherence):
    bundle, stamp = analysis_documents(tmp_path)
    for row in bundle["analysis_inventory"]["items"]:
        row["context_match"] = "matched"
        row.pop("buffer_coherence", None)
        if coherence is not None:
            # Explicit synthetic closed-fact test, not producer execution proof.
            row["buffer_coherence"] = coherence
    before = deepcopy(bundle)
    result = evaluate_policy(analysis_policy(), bundle, generated_at=stamp)
    assert [row["status"] for row in result["controls"]] == [
        "passed" if coherence == "verified" else "unknown"
    ] * 3
    assert result["native_input_binding"] == "tu-buffer-coherence-v1"
    assert bundle == before


@pytest.mark.parametrize("coherence", [None, "unverified", "mismatched"])
def test_unbound_numeric_breach_does_not_become_a_definite_failure(coherence):
    bundle = metrics_bundle((99,))
    row = bundle["analysis_inventory"]["items"][0]
    row["context_match"] = "matched"
    row.pop("buffer_coherence", None)
    if coherence is not None:
        row["buffer_coherence"] = coherence
    result = evaluate_policy(metric_selected(), bundle, generated_at=NOW)
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["incomplete"]


@pytest.mark.parametrize("coherence", [None, "unverified", "mismatched"])
def test_unbound_finding_does_not_become_a_definite_failure(tmp_path, coherence):
    from test_analysis_inventory import _finding

    bundle, stamp = analysis_documents(
        tmp_path, mutate=lambda report, root: _finding(report, root, partial=False)
    )
    for row in bundle["analysis_inventory"]["items"]:
        row["context_match"] = "matched"
        row.pop("buffer_coherence", None)
        if coherence is not None:
            row["buffer_coherence"] = coherence
    result = evaluate_policy(analysis_policy(), bundle, generated_at=stamp)
    assert result["controls"][0]["status"] == "unknown"
    assert result["controls"][0]["incomplete"]


def test_historical_metric_assessment_replays_without_upgrading_current_facts():
    from cppulse.contracts import validate_bundle
    from cppulse.errors import ContractError

    bundle = metrics_bundle()
    policy = metric_selected()
    historical = evaluate_policy(policy, bundle, generated_at=NOW)
    historical.pop("native_input_binding")
    bundle["analysis_inventory"]["items"][0].pop("buffer_coherence")
    before = deepcopy(bundle)
    validate_bundle({**bundle, "policy": policy, "assessment": historical})
    assert bundle == before
    fresh = evaluate_policy(policy, bundle, generated_at=NOW)
    assert fresh["controls"][0]["status"] == "unknown"
    forged = deepcopy(historical)
    forged["native_input_binding"] = "tu-buffer-coherence-v1"
    with pytest.raises(ContractError):
        validate_bundle({**bundle, "policy": policy, "assessment": forged})
