"""Independent label-source and unavailable-evaluation regressions for batch 118.

Most inputs here are authored JSON contract cases, not analyzer receipts or
genuine defect ground truth. The cutoff case reuses the existing controlled
local Git history and runs its actual producer; SZZ remains an imperfect label.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from cppulse.git_miner import main as git_main
from cppulse.predictor import main, model
from cppulse.predictor.feature_engineer import FEATURE_COLUMNS
from cppulse.predictor.model import BugPredictor, ModelMetrics
from tests.test_szz_cutoff_history79 import cutoff_history  # noqa: F401


def _authored_inputs(
    counts: list[int | None],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create declared contract inputs with heuristics opposed to SZZ zeros."""
    files = [f"file-{index}.cpp" for index in range(len(counts))]
    findings = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/authored-label-contract",
            "analyzed_at": "2026-11-14T10:00:00Z",
            "file_count": len(files),
            "total_loc": 10 * len(files),
            "analysis": {
                "enabled_rules": ["CPP-MEM-001"],
                "files": [
                    {
                        "path": file,
                        "status": "analyzed",
                        "error_count": 0,
                        "compile_context": "inferred",
                    }
                    for file in files
                ],
            },
        },
        "findings": [
            {
                "file": file,
                "rule_id": "CPP-MEM-001",
                "category": "memory_safety",
                "severity": "warning",
                "line": 1,
                "message": "Authored input for label precedence, not a native receipt.",
            }
            for file in files
        ],
        "summary": {
            "total_findings": len(files),
            "by_category": {"memory_safety": len(files)},
            "by_severity": {"warning": len(files)},
        },
    }
    history = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/authored-label-contract",
            "analyzed_at": "2026-11-14T10:00:00Z",
            "commit_range": "authored contract input",
            "total_commits": 3,
            "history_status": "available",
            "limitations": [],
        },
        "file_metrics": [
            {
                "file": file,
                "change_frequency": 3,
                "unique_contributors": 2,
                "age_days": 30,
                "lines_of_code": 10,
                "bug_fix_commits": 3,
                **({"szz_bug_introductions": count} if count is not None else {}),
            }
            for file, count in zip(files, counts)
        ],
        "knowledge_silos": [],
    }
    return findings, history


def _run_inputs(
    tmp_path: Path,
    findings: dict[str, Any],
    history: dict[str, Any],
) -> dict[str, Any]:
    """Exercise actual compatibility run, validation and serialized output."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for name, document in [("findings", findings), ("git_metrics", history)]:
        (input_dir / f"{name}.json").write_text(json.dumps(document), encoding="utf-8")
    output_dir = tmp_path / "output"
    main.run(input_dir, output_dir)
    return json.loads((output_dir / "risk_scores.json").read_text(encoding="utf-8"))


def _observe_training(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[list[str], list[int]]]:
    """Observe the real training boundary without replacing its behavior."""
    observed: list[tuple[list[str], list[int]]] = []
    original = BugPredictor.train

    def train(
        self: BugPredictor,
        features: pd.DataFrame,
        labels: pd.Series,
    ) -> ModelMetrics:
        observed.append((features["file"].tolist(), labels.tolist()))
        return original(self, features, labels)

    monkeypatch.setattr(BugPredictor, "train", train)
    return observed


def test_szz_positive_and_observed_zero_override_opposed_heuristics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """SZZ positives and zeros keep their labels despite memory/fix signals."""
    frame = pd.DataFrame(
        {
            "szz_bug_introductions": [0, 2, 0],
            "memory_findings": [1, 0, 0],
            "bug_fix_commits": [0, 0, 3],
            "misra_findings": [0, 0, 1],
        },
        index=[91, 4, 37],
    )
    with caplog.at_level(logging.WARNING, logger=main.__name__):
        labels = main._derive_labels(frame, profile="safety-critical")
    assert labels.to_dict() == {91: 0, 4: 1, 37: 0}
    assert "falling back" not in caplog.text.lower()


@pytest.mark.parametrize("profile", ["default", "safety-critical"])
def test_all_observed_szz_zeros_are_not_absent_labels(
    profile: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An observed zero-label cohort must not become heuristic positives."""
    frame = pd.DataFrame(
        {
            "szz_bug_introductions": [0, 0, 0],
            "memory_findings": [1, 0, 0],
            "bug_fix_commits": [0, 3, 0],
            "misra_findings": [0, 0, 1],
        }
    )
    with caplog.at_level(logging.WARNING, logger=main.__name__):
        labels = main._derive_labels(frame, profile=profile)
    assert labels.tolist() == [0, 0, 0]
    assert "falling back" not in caplog.text.lower()


@pytest.mark.parametrize(
    "profile, expected",
    [
        ("default", [1, 1, 0, 0]),
        ("safety-critical", [1, 1, 1, 0]),
    ],
)
def test_absent_szz_uses_disclosed_profile_specific_heuristic(
    profile: str,
    expected: list[int],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Legacy absent SZZ is a warned feature-derived label, not SZZ zero."""
    frame = pd.DataFrame(
        {
            "memory_findings": [1, 0, 0, 0],
            "bug_fix_commits": [0, 3, 0, 0],
            "misra_findings": [0, 0, 1, 0],
        }
    )
    with caplog.at_level(logging.WARNING, logger=main.__name__):
        labels = main._derive_labels(frame, profile=profile)
    assert labels.tolist() == expected
    assert "heuristic" in caplog.text.lower()
    assert "optimistic" in caplog.text.lower()


@pytest.mark.parametrize(
    "counts, source, labels",
    [
        ([0, 1], "szz", [0, 1]),
        ([0, 0], "szz", [0, 0]),
        ([None, None], "feature_derived_heuristic", [1, 1]),
    ],
)
def test_run_serializes_actual_label_source_and_unevaluated_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    counts: list[int | None],
    source: str,
    labels: list[int],
) -> None:
    """The public compatibility path preserves zero/absent label distinction."""
    observed = _observe_training(monkeypatch)
    result = _run_inputs(tmp_path, *_authored_inputs(counts))
    assert observed == [(["file-0.cpp", "file-1.cpp"], labels)]
    metadata = result["metadata"]
    assert metadata["label_source"] == source
    assert metadata["model_type"] == "heuristic"
    assert metadata["experimental"] is True
    assert metadata["profile"] == "default"
    assert metadata["training_samples"] == 2
    assert metadata["evaluation_status"] == "not_evaluated"
    assert metadata["evaluation_folds"] == 0
    assert metadata["fallback_reason"] in {
        "insufficient_samples",
        "backend_unavailable",
    }
    assert metadata["f1_score"] is None
    assert "memory_findings" in metadata["active_features"]
    warning = " ".join(metadata["limitations"]).lower()
    assert ("not evidence of future-defect predictive accuracy" in warning) == (
        source == "feature_derived_heuristic"
    )
    assert result["health_score"]["overall"] is None


def test_run_excludes_partial_and_missing_history_from_labels_and_training(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ineligible SZZ positive cannot supply training or hide missing data."""
    findings, history = _authored_inputs([0, 9, 9])
    findings["metadata"]["analysis"]["files"][1].update(
        status="partial",
        error_count=1,
    )
    history["file_metrics"] = history["file_metrics"][:2]
    observed = _observe_training(monkeypatch)
    result = _run_inputs(tmp_path, findings, history)
    assert observed == [(["file-0.cpp"], [0])]
    assert result["metadata"]["label_source"] == "szz"
    assert result["metadata"]["training_samples"] == 1
    assert [row["file"] for row in result["file_risks"]] == ["file-0.cpp"]
    unranked = {row["file"]: row for row in result["unranked_files"]}
    assert set(unranked) == {"file-1.cpp", "file-2.cpp"}
    assert "partial_analysis" in unranked["file-1.cpp"]["reason_codes"]
    assert "missing_file_history" in unranked["file-2.cpp"]["reason_codes"]
    assert all(
        "bug_probability" not in row and "risk_level" not in row
        for row in unranked.values()
    )
    assert result["health_score"]["overall"] is None
    assert result["metadata"]["ranking_scope"] == {
        "version": "file-eligibility-1",
        "declared_files": 3,
        "ranked_files": 1,
        "unranked_files": 2,
    }


@pytest.mark.parametrize("history_status", [None, "partial", "unavailable"])
def test_unverified_or_unavailable_history_never_enters_training(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    history_status: str | None,
) -> None:
    """History gaps are excluded rather than converted into clean examples."""
    findings, history = _authored_inputs([1, 0])
    if history_status is None:
        del history["metadata"]["history_status"]
    else:
        history["metadata"]["history_status"] = history_status
    observed = _observe_training(monkeypatch)
    result = _run_inputs(tmp_path, findings, history)
    assert observed == [([], [])]
    assert result["metadata"]["training_samples"] == 0
    assert result["file_risks"] == []
    assert len(result["unranked_files"]) == 2
    assert all(
        "bug_probability" not in row and "risk_level" not in row
        for row in result["unranked_files"]
    )
    assert result["health_score"]["overall"] is None


@pytest.mark.parametrize(
    "case, reason",
    [
        ("small", "insufficient_samples"),
        ("single_class", "insufficient_label_classes"),
        ("fit_failure", "training_failed"),
    ],
)
def test_fallback_clears_stale_empirical_metrics(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    reason: str,
) -> None:
    """Fault injection exercises fallback metadata without training a backend."""

    class FailingBackend:
        """Explicit test double that must never produce a trained model."""

        def __init__(self, **kwargs: Any) -> None:
            pass

        def fit(self, features: pd.DataFrame, labels: pd.Series) -> None:
            if case != "fit_failure":
                pytest.fail("A prerequisite fallback attempted backend training")
            raise ValueError("Authored backend failure for fallback metadata")

    monkeypatch.setattr(model, "_HAS_ML", True)
    monkeypatch.setattr(model, "XGBClassifier", FailingBackend)
    size = 2 if case == "small" else 50
    features = pd.DataFrame(
        [
            {column: 0 for column in FEATURE_COLUMNS if column != "file"}
            for _ in range(size)
        ]
    )
    labels = pd.Series([1] + [0] * (size - 1) if case == "fit_failure" else [0] * size)
    predictor = BugPredictor(profile="safety-critical")
    predictor.metrics = ModelMetrics(
        f1=0.9,
        precision=0.8,
        recall=0.7,
        evaluation_status="cross_validated",
        evaluation_folds=5,
    )
    metrics = predictor.train(features, labels)
    assert predictor.model is None
    assert predictor.use_heuristic is True
    assert metrics.fallback_reason == reason
    assert metrics.training_samples == size
    assert metrics.evaluation_status == "not_evaluated"
    assert metrics.evaluation_folds == 0
    assert (metrics.f1, metrics.precision, metrics.recall) == (None, None, None)


def test_actual_producer_cutoff_and_imperfect_label_provenance_survive_run(
    cutoff_history: Any,  # noqa: F811 -- imported pytest fixture
    tmp_path: Path,
) -> None:
    """Reuse the exact existing producer case; do not equate SZZ with truth."""
    producer_dir = tmp_path / "producer"
    repo_root = Path(cutoff_history.working_tree_dir)
    assert (
        git_main.run(
            repo_root,
            producer_dir,
            szz_cutoff="2020-01-05T00:00:00Z",
        )
        == 0
    )
    history = json.loads(
        (producer_dir / "git_metrics.json").read_text(encoding="utf-8")
    )
    provenance = history["metadata"]["szz"]
    assert provenance["analysis_cutoff"] == "2020-01-05T00:00:00Z"
    assert provenance["cutoff_source"] == "explicit"
    assert provenance["label_kind"] == "imperfect_candidate"
    assert provenance["feature_history_scope"] == "retained_history_not_cutoff_filtered"
    counts = {
        row["file"]: row["szz_bug_introductions"] for row in history["file_metrics"]
    }
    assert counts == {"old.cpp": 1, "new.cpp": 0}
    findings, _ = _authored_inputs([None, None])
    findings["metadata"]["repo_path"] = str(repo_root)
    for index, file in enumerate(["old.cpp", "new.cpp"]):
        findings["metadata"]["analysis"]["files"][index]["path"] = file
        findings["findings"][index]["file"] = file
    result = _run_inputs(tmp_path, findings, history)
    assert result["metadata"]["label_source"] == "szz"
    assert result["metadata"]["szz"] == provenance
    assert all(
        note in result["metadata"]["limitations"]
        for note in history["metadata"]["limitations"]
    )
    assert result["metadata"]["experimental"] is True
