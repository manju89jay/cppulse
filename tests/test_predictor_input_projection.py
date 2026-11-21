"""Legacy feature inputs retain literal claims without keeping token subtrees."""

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from cppulse.errors import ContractError, IntegrityError
from cppulse.predictor.input_projection import open_predictor_inputs
from cppulse.native_projection_store import ProjectionStoreLimits
from tests.test_maintenance_metrics_contract import native_metric_report


def original(tmp_path: Path) -> tuple[Path, dict]:
    """Declared synthetic native shape; actual producer qualification is separate."""
    report = native_metric_report()
    report["metadata"]["analysis"]["native_metrics"]["files"][0][
        "source_content_sha256"
    ] = ("a" * 64)
    path = tmp_path / "findings.json"
    path.write_text(json.dumps(report))
    return path, report


def test_projection_keeps_metadata_and_literal_metrics_without_native_tokens(
    tmp_path: Path,
) -> None:
    path, report = original(tmp_path)
    raw = path.read_bytes()
    expected = deepcopy(report)
    del expected["metadata"]["analysis"]["native_metrics"]
    with open_predictor_inputs(path, directory=tmp_path / "spool") as inputs:
        assert inputs.findings == expected
        assert inputs.report_sha256 == hashlib.sha256(raw).hexdigest()
        assert inputs.measured_hotspot_metrics == {
            "a.cpp": {
                "physical_loc": 1,
                "complexity_score": 1,
                "metric_version": "cppulse-metrics-1",
                "metrics_source": "/metadata/analysis/native_metrics/files/0",
                "source_content_sha256": "a" * 64,
                "metric_provenance": "retained-native-report-claim",
            }
        }
    assert path.read_bytes() == raw


def test_legacy_without_native_claims_is_preserved_and_stays_unavailable(
    tmp_path: Path,
) -> None:
    path, report = original(tmp_path)
    del report["metadata"]["analysis"]
    path.write_text(json.dumps(report))
    with open_predictor_inputs(path, directory=tmp_path / "spool") as inputs:
        assert inputs.findings == report
        assert inputs.measured_hotspot_metrics == {}


def test_missing_content_identity_never_manufactures_available_metrics(
    tmp_path: Path,
) -> None:
    path, report = original(tmp_path)
    del report["metadata"]["analysis"]["native_metrics"]["files"][0][
        "source_content_sha256"
    ]
    path.write_text(json.dumps(report))
    with open_predictor_inputs(path, directory=tmp_path / "spool") as inputs:
        assert inputs.measured_hotspot_metrics == {}


def test_forged_json_validation_marker_cannot_hide_native_semantic_mismatch(
    tmp_path: Path,
) -> None:
    path, report = original(tmp_path)
    report["metadata"]["json_schema_checked"] = True
    report["metadata"]["analysis"]["native_metrics"]["files"][0]["function_count"] = 2
    path.write_text(json.dumps(report))
    with pytest.raises(ContractError):
        with open_predictor_inputs(path, directory=tmp_path / "spool"):
            pytest.fail("Invalid original semantic claims were admitted")


def test_late_original_change_refuses_projected_consumer_result(tmp_path: Path) -> None:
    path, _ = original(tmp_path)
    with pytest.raises(IntegrityError):
        with open_predictor_inputs(path, directory=tmp_path / "spool"):
            path.write_bytes(path.read_bytes() + b" ")


def test_symlink_is_not_an_original_regular_input(tmp_path: Path) -> None:
    path, _ = original(tmp_path)
    link = tmp_path / "alias.json"
    link.symlink_to(path)
    with pytest.raises(IntegrityError):
        with open_predictor_inputs(link, directory=tmp_path / "spool"):
            pytest.fail("Symlink input accepted")


def test_trailing_document_cannot_be_ignored_after_valid_report(tmp_path: Path) -> None:
    path, _ = original(tmp_path)
    path.write_bytes(path.read_bytes() + b"\n{}")
    with pytest.raises(ContractError):
        with open_predictor_inputs(path, directory=tmp_path / "spool"):
            pytest.fail("A second trailing JSON document was accepted")
    assert not any((tmp_path / "spool").iterdir())


def test_projection_capacity_failure_closes_spool_with_traceback_retained(
    tmp_path: Path,
) -> None:
    path, _ = original(tmp_path)
    with pytest.raises(ContractError) as failure:
        with open_predictor_inputs(
            path,
            directory=tmp_path / "spool",
            store_limits=ProjectionStoreLimits(max_records=1),
        ):
            pytest.fail("Projection record capacity did not constrain the consumer")
    assert failure.traceback is not None
    assert not any((tmp_path / "spool").iterdir())


def test_public_predictor_preserves_frozen_legacy_results_without_eager_native_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.predictor.main as current

    path, report = original(tmp_path)
    report["findings"] = [
        {
            "file": "a.cpp",
            "rule_id": "CPP-MOD-001",
            "category": "modernization",
            "severity": "warning",
            "line": 1,
            "message": "Declared fixture",
        }
    ]
    report["summary"] = {
        "total_findings": 1,
        "by_category": {"modernization": 1},
        "by_severity": {"warning": 1},
    }
    path.write_text(json.dumps(report))
    history = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/repo",
            "analyzed_at": "2026-11-14T10:00:00Z",
            "commit_range": "a..b",
            "total_commits": 2,
            "history_status": "available",
        },
        "file_metrics": [
            {
                "file": "a.cpp",
                "change_frequency": 2,
                "unique_contributors": 1,
                "age_days": 1,
                "lines_of_code": 99,
                "churn_rate": 0,
                "bug_fix_commits": 0,
            }
        ],
        "knowledge_silos": [],
    }
    (tmp_path / "git_metrics.json").write_text(json.dumps(history))
    root = Path(__file__).resolve().parents[1]
    candidate_path = root / "work/installed-sdk-component69/candidate.json"
    if not candidate_path.exists():
        pytest.skip(
            "Frozen candidate69 parity oracle is a retained Cloud qualification"
        )
    candidate = json.loads(candidate_path.read_bytes())
    baseline = tmp_path / "baseline"
    # Compare code epochs with the same interpreter/backend availability. The
    # separate installed journey qualifies the retained minimal core venv.
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": candidate["installed_target"],
    }
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; from cppulse.predictor.main import run; import sys; run(Path(sys.argv[1]),Path(sys.argv[2]))",
            str(tmp_path),
            str(baseline),
        ],
        env=env,
        capture_output=True,
        timeout=60,
    )
    assert process.returncode == 0, process.stderr.decode(errors="replace")
    original_load = current._load_json

    def no_eager_native(candidate_input: Path) -> dict:
        assert (
            candidate_input != path
        ), "Public predictor eagerly materialized native input"
        return original_load(candidate_input)

    monkeypatch.setattr(current, "_load_json", no_eager_native)
    output = tmp_path / "current"
    current.run(tmp_path, output)
    for name in ["risk_scores.json", "roadmap.json"]:
        before = json.loads((baseline / name).read_bytes())
        after = json.loads((output / name).read_bytes())
        if name == "risk_scores.json":
            before["metadata"].pop("generated_at")
            after["metadata"].pop("generated_at")
            # The old oracle treated authored raw scope as qualified health.
            # Preserve its numerical calibration, while requiring the public
            # result to disclose the newly enforced missing prerequisites.
            from cppulse.predictor.feature_engineer import FeatureEngineer
            from cppulse.predictor.health_scorer import HealthScorer

            expected_health = before.pop("health_score")
            unavailable_health = after.pop("health_score")
            assert expected_health["status"] == "scored"
            assert expected_health["overall"] == 99.0
            assert unavailable_health["status"] == "partial"
            assert unavailable_health["overall"] is None
            assert set(unavailable_health["by_category"]) == set(
                expected_health["by_category"]
            )
            assert all(
                value is None for value in unavailable_health["by_category"].values()
            )
            calibration = FeatureEngineer().build_features(report, history)
            calibration.attrs.clear()  # Calculation-only API, not scope proof.
            calculated = HealthScorer().compute(calibration)
            assert calculated.overall == expected_health["overall"]
            assert calculated.by_category == expected_health["by_category"]
            limitations = after["metadata"]["limitations"]
            assert any(
                item.startswith("Full-scope health unavailable:")
                for item in limitations
            )
            after["metadata"]["limitations"] = [
                item
                for item in limitations
                if not item.startswith("Full-scope health unavailable:")
            ]
            # Explicit disclosures introduced by the accepted health/proxy-label
            # repairs are additional to the old69 oracle. Check their full
            # meaning, then retain strict parity for every other original field.
            assert "training_label_provenance" not in before["metadata"]
            assert after["metadata"].pop("training_label_provenance") == {
                "kind": "declared_experimental_proxy_labels",
                "training_files": ["a.cpp"],
                "szz_files": [],
                "feature_derived_files": ["a.cpp"],
            }
            assert "health_calculation" not in before["metadata"]
            assert after["metadata"].pop("health_calculation") == {
                "method": "weighted-findings-per-attempted-file-v2",
                "version": "2",
                "formula": "clamp(100 - sum(category_weight * finding_count) / denominator_files, 0, 100)",
                "profile": "default",
                "weights": {
                    "memory_findings": 3.0,
                    "complexity_findings": 1.5,
                    "modernization_findings": 1.0,
                },
                "category_scales": {
                    "memory_safety": 15.0,
                    "modernization": 5.0,
                    "complexity": 10.0,
                },
                "denominator_files": 1,
                "declared_files": 1,
                "availability": "partial",
            }
        assert before == after


def test_public_predictor_does_not_publish_after_late_original_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.predictor.main as current

    path, _ = original(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    for name in ["risk_scores.json", "roadmap.json"]:
        (output / name).write_bytes(b"prior retained output\n")

    def changed_original(input_dir, staged_output, profile, findings, claims):
        staged_output.mkdir(parents=True, exist_ok=True)
        for name in ["risk_scores.json", "roadmap.json"]:
            (staged_output / name).write_text("{}")
        path.write_bytes(path.read_bytes() + b" ")

    monkeypatch.setattr(current, "_run_projected", changed_original)
    with pytest.raises(IntegrityError):
        current.run(tmp_path, output)
    for name in ["risk_scores.json", "roadmap.json"]:
        assert (output / name).read_bytes() == b"prior retained output\n"
