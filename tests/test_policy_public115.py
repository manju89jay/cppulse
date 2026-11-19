"""Public framework arithmetic and genuine retained-producer consumption.

In-memory arithmetic/deviation records are explicitly authored QA declarations,
not actual executions or authenticated approvals. The separate CLI journey
uses unchanged genuine GCC/CTest/LCOV records supplied by the frozen driver.
"""

from copy import deepcopy
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import subprocess

import cppulse
import pytest
from cppulse.contracts import validate, validate_bundle, validate_evaluation_policy
from cppulse.errors import ContractError, UnsupportedVersion
from cppulse.policy import evaluate_policy
from cppulse.presentation import build_snapshot_view
from cppulse.run_store import RunStore
from cppulse.workflows import read_documents
from test_policy import NOW, add_result, approval, control, facts as synthetic_facts
from test_policy import policy as synthetic_policy


@pytest.fixture(autouse=True)
def installed_origin_if_requested():
    expected = os.environ.get("CPPULSE_POLICY_EXPECT_PREFIX115")
    if expected:
        root = Path(expected).resolve() / "cppulse"
        import cppulse.policy
        import cppulse.policy_extensions
        import cppulse.contracts.validation

        for module in (
            cppulse,
            cppulse.policy,
            cppulse.policy_extensions,
            cppulse.contracts.validation,
        ):
            assert Path(module.__file__).resolve().is_relative_to(root), module.__file__


def declared_arithmetic(profile):
    facts = synthetic_facts.__wrapped__()
    add_result(facts, "bad-result", status="failed")
    policy = synthetic_policy.__wrapped__()
    policy["evaluator_profile"] = profile
    policy["controls"] = [
        control("good", weight=4, required=False),
        control("bad", evidence_ids=["bad-result"], weight=2, required=True),
        control("missing", evidence_ids=["not-present"], weight=4, required=True),
        control("not-this-kind", weight=1000, required=True),
    ]
    policy["controls"][-1]["applicable_to"] = ["header-only"]
    policy["controls"][1]["allow_deviation"] = True
    policy["gates"] = {"minimum_readiness": 0, "minimum_completeness": 60}
    return facts, policy


@pytest.mark.parametrize("profile", ["1.0.0", "1.1.0", "1.2.0"])
def test_public_hand_calculation_four_outcomes_and_blocking_precedence(
    profile, tmp_path
):
    facts, policy = declared_arithmetic(profile)
    before = deepcopy((facts, policy))
    assessment = evaluate_policy(policy, facts, generated_at=NOW)
    assert {r["id"]: r["status"] for r in assessment["controls"]} == {
        "good": "passed",
        "bad": "failed",
        "missing": "unknown",
        "not-this-kind": "not_applicable",
    }
    assert assessment["weights"] == {"passed": 4, "failed": 2, "unknown": 4}
    assert assessment["scores"] == {
        "readiness": 40,
        "evidence_completeness": 60,
        "observed_satisfaction": 100 * 4 / 6,
        "maximum_possible_readiness": 80,
    }
    assert assessment["gate"] == "failed"
    assert assessment["evaluator"]["version"] == profile
    validate_bundle({**facts, "policy": policy, "assessment": assessment})
    assert (facts, policy) == before
    (tmp_path / "AUTHORED-arithmetic-example.json").write_text(
        json.dumps(
            {
                "provenance": "Synthetic closed QA facts; no producer execution/authentication claim.",
                "facts": facts,
                "policy": policy,
                "actual_evaluation": assessment,
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize(
    "case",
    [
        "active",
        "unknown_required",
        "expired",
        "future",
        "wrong_source",
        "wrong_context",
        "denied",
    ],
)
def test_public_declared_deviations_never_rewrite_raw_scores_or_unknowns(
    case, tmp_path
):
    facts, policy = declared_arithmetic("1.0.0")
    policy["controls"][2]["required"] = case == "unknown_required"
    request = approval(
        facts,
        control_id="bad",
        reason="Consumer-authored QA approval; identity is not authenticated.",
    )
    if case == "expired":
        request["expires_at"] = NOW
    elif case == "future":
        request["approved_at"] = "2026-11-13T13:00:00Z"
        request["expires_at"] = "2026-11-14T13:00:00Z"
    elif case == "wrong_source":
        request["source_digest"] = "f" * 64
    elif case == "wrong_context":
        request["context_ids"] = ["other-job"]
    elif case == "denied":
        policy["controls"][1]["allow_deviation"] = False
    before = deepcopy((facts, policy, request))
    result = evaluate_policy(policy, facts, generated_at=NOW, deviations=[request])
    assert result["controls"][1]["status"] == "failed"
    assert result["controls"][2]["status"] == "unknown"
    assert (
        result["scores"]["readiness"] == 40
        and result["scores"]["evidence_completeness"] == 60
    )
    if case in {"active", "unknown_required"}:
        assert result["deviations"][0]["active"] is True
        assert result["gate"] == (
            "passed" if case == "active" else "insufficient_evidence"
        )
    else:
        assert result["deviations"][0]["active"] is False and result["gate"] == "failed"
    assert (facts, policy, request) == before
    (tmp_path / ("AUTHORED-deviation-" + case + ".json")).write_text(
        json.dumps(
            {
                "provenance": "Consumer-authored approval declarations; no real reviewer authentication.",
                "request": request,
                "actual_evaluation": result,
            },
            indent=2,
        )
        + "\n"
    )


@pytest.mark.parametrize(
    "case",
    [
        "duplicate",
        "cycle",
        "unknown_dependency",
        "unsupported_profile",
        "mismatched_source",
        "unsupported_option",
    ],
)
def test_public_contracts_reject_invalid_pack_and_actual_reference_claims(
    case, tmp_path
):
    facts, policy = declared_arithmetic("1.0.0")
    if case == "duplicate":
        policy["controls"].append(deepcopy(policy["controls"][0]))
    elif case == "cycle":
        policy["controls"][0]["depends_on"] = ["bad"]
        policy["controls"][1]["depends_on"] = ["good"]
    elif case == "unknown_dependency":
        policy["controls"][0]["depends_on"] = ["missing-control"]
    elif case == "unsupported_profile":
        policy["evaluator_profile"] = "999.0.0"
    elif case == "mismatched_source":
        facts["execution_receipt"][0]["source_digest"] = "f" * 64
    elif case == "unsupported_option":
        policy["invented_clean_result"] = True
    (tmp_path / ("AUTHORED-invalid-" + case + ".json")).write_text(
        json.dumps({"policy": policy, "facts": facts}, indent=2) + "\n"
    )
    with pytest.raises((ContractError, UnsupportedVersion)):
        evaluate_policy(policy, facts, generated_at=NOW)


def _call(output, name, argv, expected):
    result = subprocess.run(
        [str(a) for a in argv],
        cwd=output,
        env=dict(os.environ),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    (output / (name + ".stdout")).write_text(result.stdout)
    (output / (name + ".stderr")).write_text(result.stderr)
    record = {
        "argv": [str(a) for a in argv],
        "cwd": str(output),
        "exit_status": result.returncode,
    }
    (output / (name + "-command.json")).write_text(json.dumps(record, indent=2) + "\n")
    assert result.returncode in expected, (
        name,
        result.returncode,
        result.stdout[-1800:],
        result.stderr[-3000:],
    )
    return json.loads(result.stdout) if result.stdout.lstrip().startswith("{") else None


def test_genuine_retained_lcov_public_assess_check_report_and_deviation(tmp_path):
    descriptor = os.environ.get("CPPULSE_POLICY115_INPUTS")
    assert (
        descriptor
    ), "Genuine producer input descriptor required; pure component stage selects the other tests explicitly."
    inputs = json.loads(Path(descriptor).read_bytes())
    store, workspace = Path(inputs["store"]), Path(inputs["workspace"])
    source = RunStore.open_existing(store).open_run(
        inputs["run_id"], manifest_sha256=inputs["manifest_sha256"]
    )
    source.verify()
    documents = read_documents(source)
    documents["run_manifest"] = source.manifest
    facts = documents["coverage_facts"]
    facts = facts if isinstance(facts, list) else [facts]
    (fact,) = [row for row in facts if row["adapter"]["name"] == "lcov"]
    measured = {m["kind"]: m for f in fact["files"] for m in f["measurements"]}
    assert {k: (m["covered"], m["total"]) for k, m in measured.items()} == {
        "line": (5, 8),
        "branch": (1, 2),
        "function": (2, 3),
    }
    assert fact["origin"] == "execution" and fact["usability"] == "usable"
    assert "mcdc" not in measured and "decision" not in measured
    context = fact["context_id"]

    def coverage(identifier, kind, weight, required):
        return {
            "id": identifier,
            "title": identifier,
            "kind": "minimum_coverage",
            "weight": weight,
            "required": required,
            "parameters": {
                "fact_ids": [fact["id"]],
                "measurement_kind": kind,
                "method": measured[kind]["method"],
                "minimum": 60,
                "contexts": [context],
            },
            "depends_on": [],
        }

    policy = {
        "version": "2.0.0",
        "id": "genuine-policy115",
        "policy_version": "1.0.0",
        "evaluator_profile": "1.1.0",
        "standards": [],
        "scope": {"include": ["main.cpp"], "exclude": []},
        "contexts": [context],
        "gates": {"minimum_readiness": 0, "minimum_completeness": 60},
        "controls": [
            coverage("line", "line", 4, False),
            coverage("branch", "branch", 2, True),
            {
                "id": "missing",
                "title": "Missing named executed result",
                "kind": "test_outcomes",
                "weight": 4,
                "required": True,
                "parameters": {
                    "evidence_ids": ["not-present-policy115"],
                    "contexts": [context],
                },
                "depends_on": [],
            },
            {
                **coverage("not-this-kind", "line", 1000, True),
                "applicable_to": ["header-only"],
            },
        ],
    }
    policy["controls"][1]["allow_deviation"] = True
    validate_evaluation_policy(policy)
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(policy, indent=2) + "\n")
    common = [
        "--store",
        store,
        "--workspace",
        workspace,
        "--run-id",
        source.run_id,
        "--manifest-sha256",
        source.manifest_sha256,
        "--policy",
        policy_path,
    ]
    result = _call(tmp_path, "assess", [inputs["console"], "assess", *common], (1,))
    validate("workflow_result", result)
    assessed = RunStore.open_existing(store).open_run(
        result["final_run"]["run_id"],
        manifest_sha256=result["final_run"]["manifest_sha256"],
    )
    assessed.verify()
    assessed_documents = read_documents(assessed)
    assessments = assessed_documents["assessment"]
    actual = assessments[-1] if isinstance(assessments, list) else assessments
    prospective = deepcopy(documents)
    prospective["run_manifest"]["run_id"] = assessed.run_id
    expected = evaluate_policy(policy, prospective, generated_at=actual["generated_at"])
    assert actual == expected
    assert actual["gate"] == "failed"
    assert {row["id"]: row["status"] for row in actual["controls"]} == {
        "line": "passed",
        "branch": "failed",
        "missing": "unknown",
        "not-this-kind": "not_applicable",
    }
    assert actual["weights"] == {"passed": 4, "failed": 2, "unknown": 4}
    assert actual["scores"] == {
        "readiness": 40,
        "evidence_completeness": 60,
        "observed_satisfaction": 100 * 4 / 6,
        "maximum_possible_readiness": 80,
    }
    for kind, counts in {"line": "5/8", "branch": "1/2"}.items():
        assert counts in next(
            row["reason"] for row in actual["controls"] if row["id"] == kind
        )
    checked = _call(tmp_path, "check", [inputs["console"], "check", *common], (1,))
    validate("check_result", checked)
    assert checked["status"] == "failed"
    checked_snapshot = RunStore.open_existing(store).open_run(
        checked["run"]["run_id"], manifest_sha256=checked["run"]["manifest_sha256"]
    )
    checked_assessments = read_documents(checked_snapshot)["assessment"]
    assert checked_assessments[-1]["gate"] == "failed"
    expected_view = build_snapshot_view(assessed)
    for format in ("json", "html"):
        output = tmp_path / ("report." + format)
        _call(
            tmp_path,
            "report-" + format,
            [
                inputs["console"],
                "report",
                "--input",
                store,
                "--format",
                format,
                "--output",
                output,
                "--evidence",
                "--run-id",
                assessed.run_id,
                "--manifest-sha256",
                assessed.manifest_sha256,
            ],
            (0,),
        )
        if format == "json":
            view = json.loads(output.read_bytes())
            validate("snapshot_view", view)
            assert view == expected_view
        else:
            assert (
                assessed.run_id in output.read_text() and "failed" in output.read_text()
            )
    # This is declared approval data over genuine failed coverage, not a real
    # human approval. It cannot rewrite the observed branch1/2 or missing proof.
    relaxed = deepcopy(policy)
    relaxed["controls"][2]["required"] = False
    time = datetime.fromisoformat(actual["generated_at"].replace("Z", "+00:00"))
    deviation = {
        "id": "declared-qa115",
        "control_id": "branch",
        "source_digest": source.manifest["source"]["digest"],
        "context_ids": [context],
        "reason": "Consumer-authored QA declaration, not authenticated approval.",
        "owner": "qa-declared-owner",
        "reviewer": "qa-declared-reviewer",
        "gate": "required_controls",
        "approved_at": (time - timedelta(hours=1)).isoformat(),
        "expires_at": (time + timedelta(hours=1)).isoformat(),
    }
    unchanged = deepcopy((documents, relaxed, deviation))
    excepted = evaluate_policy(
        relaxed, documents, generated_at=actual["generated_at"], deviations=[deviation]
    )
    assert excepted["gate"] == "passed" and excepted["deviations"][0]["active"] is True
    assert (
        excepted["scores"] == actual["scores"]
        and excepted["controls"][1]["status"] == "failed"
    )
    assert (documents, relaxed, deviation) == unchanged
    (tmp_path / "CONSUMER-AUTHORED-deviation-on-genuine-facts.json").write_text(
        json.dumps(excepted, indent=2) + "\n"
    )
    source.verify()
    (tmp_path / "genuine-policy115-result.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "original_run_id": source.run_id,
                "original_manifest_sha256": source.manifest_sha256,
                "assessment_run_id": assessed.run_id,
                "assessment_manifest_sha256": assessed.manifest_sha256,
                "literal_measurements": {
                    k: [m["covered"], m["total"]] for k, m in measured.items()
                },
                "four_outcomes": {r["id"]: r["status"] for r in actual["controls"]},
                "scores": actual["scores"],
                "declared_deviation_does_not_authenticate_reviewer": True,
            },
            indent=2,
        )
        + "\n"
    )
