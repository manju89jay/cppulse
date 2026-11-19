"""Chronological evaluation rejects feature/label leakage and reports honest gaps."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from cppulse.errors import ContractError
from cppulse.predictor.evaluation import evaluate, validate_input


def dataset() -> dict:
    rows = []
    for n in range(12):
        day = "2026-01-01" if n < 8 else "2026-03-01"
        rows.append(
            {
                "id": f"sample-{n}",
                "project": "train-project" if n < 10 else "heldout-project",
                "prediction_at": day + "T00:00:00Z",
                "features_available_at": day + "T00:00:00Z",
                "label_available_at": ("2026-01-10" if n < 8 else "2026-03-10")
                + "T00:00:00Z",
                "label": n % 2,
                "features": {"churn": float(n % 2), "size": float(n + 1)},
            }
        )
    return {
        "version": "1.0.0",
        "label_definition": "Controlled authored future outcome; not real defects",
        "prediction_horizon_days": 7,
        "training_cutoff": "2026-02-01T00:00:00Z",
        "evaluation_cutoff": "2026-04-01T00:00:00Z",
        "feature_names": ["churn", "size"],
        "ranking_feature": "churn",
        "holdout_projects": ["heldout-project"],
        "observations": rows,
    }


def test_chronological_and_project_holdout_and_probability_metrics() -> None:
    report = evaluate(dataset())
    assert report["training"]["sample_ids"] == [f"sample-{n}" for n in range(8)]
    assert report["training"]["projects"] == ["train-project"]
    for partition in ["chronological", "project_holdout"]:
        result = report["partitions"][partition]
        assert result["sample_count"] == 2
        assert set(result["models"]) == {
            "zero",
            "training_base_rate",
            "feature_ranking",
            "logistic",
        }
        assert result["models"]["training_base_rate"]["brier_score"] == 0.25
        assert result["models"]["zero"]["recall"] == 0
        assert result["models"]["feature_ranking"]["brier_score"] is None
        assert result["models"]["feature_ranking"]["reliability"] is None
        assert result["models"]["feature_ranking"]["average_precision"] == 1
        assert result["models"]["logistic"]["status"] in ("evaluated", "unavailable")
    assert evaluate(dataset()) == report


def test_late_training_label_is_not_used_and_holdout_is_never_training() -> None:
    data = dataset()
    data["observations"][0]["label_available_at"] = "2026-03-10T00:00:00Z"
    data["observations"][1]["project"] = "heldout-project"
    report = evaluate(data)
    assert "sample-0" not in report["training"]["sample_ids"]
    assert "sample-1" not in report["training"]["sample_ids"]
    assert report["excluded"]["sample-0"] == "training_label_unavailable_at_cutoff"
    assert report["excluded"]["sample-1"] == "heldout_before_training_cutoff"


@pytest.mark.parametrize(
    "change",
    [
        "future_features",
        "duplicate_id",
        "missing_feature",
        "nan",
        "bool",
        "bad_time",
        "cutoff_order",
    ],
)
def test_rejects_invalid_or_leaking_inputs(change: str) -> None:
    data = dataset()
    row = data["observations"][0]
    if change == "future_features":
        row["features_available_at"] = "2026-02-01T00:00:00Z"
    if change == "duplicate_id":
        data["observations"][1]["id"] = row["id"]
    if change == "missing_feature":
        del row["features"]["size"]
    if change == "nan":
        row["features"]["churn"] = float("nan")
    if change == "bool":
        row["features"]["churn"] = True
    if change == "bad_time":
        row["prediction_at"] = "2026-01-01T00:00:00"
    if change == "cutoff_order":
        data["evaluation_cutoff"] = data["training_cutoff"]
    with pytest.raises(ContractError):
        validate_input(data)


def test_test_labels_unavailable_never_become_negative_examples() -> None:
    data = dataset()
    for row in data["observations"][8:]:
        row["label_available_at"] = None
        row["label"] = None
    report = evaluate(data)
    assert report["status"] == "not_evaluable"
    for partition in report["partitions"].values():
        assert partition["status"] == "unavailable"
        assert partition["sample_count"] == 0
        assert partition["models"] == {}


def test_single_class_training_and_test_preserve_unavailable_metrics() -> None:
    data = dataset()
    for row in data["observations"]:
        row["label"] = 0
    report = evaluate(data)
    for partition in report["partitions"].values():
        assert partition["models"]["logistic"]["status"] == "unavailable"
        assert (
            partition["models"]["logistic"]["reason"] == "single_class_training_labels"
        )
        assert partition["models"]["zero"]["roc_auc"] is None
        assert partition["models"]["zero"]["average_precision"] is None
        assert partition["models"]["zero"]["brier_score"] == 0


def test_future_evaluation_labels_and_post_evaluation_predictions_excluded() -> None:
    data = dataset()
    data["observations"][8]["label_available_at"] = "2026-05-01T00:00:00Z"
    data["observations"][9]["prediction_at"] = "2026-05-01T00:00:00Z"
    data["observations"][9]["label_available_at"] = "2026-05-10T00:00:00Z"
    result = evaluate(data)
    assert result["excluded"]["sample-8"] == "evaluation_label_unavailable_at_cutoff"
    assert result["excluded"]["sample-9"] == "prediction_after_evaluation_cutoff"


def test_module_cli_retains_validated_reproducible_report(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    output = tmp_path / "report.json"
    source.write_text(json.dumps(dataset()))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cppulse.predictor.evaluation",
            "--input",
            str(source),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_bytes()) == evaluate(dataset())
    source.write_text('{"version": NaN}')
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cppulse.predictor.evaluation",
            "--input",
            str(source),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2


def test_holdout_values_and_labels_do_not_change_chronological_model() -> None:
    original = evaluate(dataset())
    data = dataset()
    for row in data["observations"]:
        if row["project"] == "heldout-project":
            row["features"]["size"] = 1000000
            row["label"] = 1 - row["label"]
    changed = evaluate(data)
    assert changed["training"] == original["training"]
    assert (
        changed["partitions"]["chronological"]
        == original["partitions"]["chronological"]
    )


def test_ranking_ties_do_not_use_outcome_to_choose_top_k() -> None:
    data = dataset()
    for row in data["observations"]:
        row["features"]["churn"] = 0
    report = evaluate(data)
    metric = report["partitions"]["chronological"]["models"]["feature_ranking"]
    assert metric["precision_at_k"] == 0.5
    assert metric["roc_auc"] == 0.5
    assert metric["average_precision"] == 0.5


def test_report_contract_rejects_calibration_of_ranking() -> None:
    from cppulse.predictor.evaluation import validate_report

    report = evaluate(dataset())
    report["partitions"]["chronological"]["models"]["feature_ranking"][
        "brier_score"
    ] = 0.1
    with pytest.raises(ContractError):
        validate_report(report)


def test_no_training_labels_remains_unavailable_in_candidate() -> None:
    data = dataset()
    data["observations"] = data["observations"][8:]
    report = evaluate(data)
    assert report["training"]["sample_count"] == 0
    for partition in report["partitions"].values():
        assert partition["models"]["logistic"]["reason"] == "no_training_labels"
        assert partition["models"]["training_base_rate"]["status"] == "unavailable"


def test_optional_ml_dependency_absence_is_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import builtins

    original = builtins.__import__

    def block(name: str, *args, **kwargs):
        if name == "sklearn":
            raise ModuleNotFoundError("Deliberately unavailable optional backend")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block)
    report = evaluate(dataset())
    assert (
        report["partitions"]["chronological"]["models"]["logistic"]["reason"]
        == "optional_ml_backend_unavailable:ModuleNotFoundError"
    )
    assert (
        report["partitions"]["chronological"]["models"]["zero"]["status"] == "evaluated"
    )


def test_horizon_overflow_is_a_contract_error() -> None:
    data = dataset()
    data["observations"][0]["prediction_at"] = "9999-12-31T00:00:00Z"
    data["observations"][0]["label_available_at"] = "9999-12-31T00:00:00Z"
    with pytest.raises(ContractError):
        validate_input(data)


def test_cli_rejects_ambiguous_duplicate_json_keys(tmp_path: Path) -> None:
    source = tmp_path / "input.json"
    source.write_text('{"version":"1.0.0","version":"2.0.0"}')
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cppulse.predictor.evaluation",
            "--input",
            str(source),
            "--output",
            str(tmp_path / "out.json"),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert "Duplicate JSON keys" in result.stderr


def test_cli_refuses_nonregular_input_without_blocking(tmp_path: Path) -> None:
    import os

    source = tmp_path / "pipe"
    os.mkfifo(source)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cppulse.predictor.evaluation",
            "--input",
            str(source),
            "--output",
            str(tmp_path / "out.json"),
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 2
    assert "finite regular JSON" in result.stderr


def test_huge_integer_feature_fails_as_contract_error() -> None:
    data = dataset()
    data["observations"][0]["features"]["size"] = 10**1000
    with pytest.raises(ContractError):
        validate_input(data)
