"""Regressions for unavailable model evaluation and safe heuristic fallback."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.model import BugPredictor
from tests.test_model import _make_features, _make_labels


@pytest.mark.parametrize("label", [0, 1])
def test_single_class_large_input_uses_unscored_heuristic(label: int) -> None:
    """A large file count does not make a single-class dataset trainable."""
    features = _make_features(60)
    predictor = BugPredictor()
    metrics = predictor.train(features, pd.Series([label] * len(features)))
    assert predictor.use_heuristic is True
    assert predictor.model is None
    assert metrics.f1 is None
    assert metrics.precision is None
    assert metrics.recall is None
    assert metrics.evaluation_status == "not_evaluated"
    assert metrics.fallback_reason == "insufficient_label_classes"
    scores = predictor.predict(features)
    assert len(scores) == len(features)
    assert np.isfinite(scores).all()
    assert ((scores >= 0) & (scores <= 1)).all()


def test_sparse_classes_do_not_report_zero_as_measured_f1() -> None:
    """A final model can train while evaluation remains explicitly unavailable."""
    features = _make_features(60)
    predictor = BugPredictor()
    labels = pd.Series([1] + [0] * 59)
    metrics = predictor.train(features, labels)
    assert predictor.use_heuristic is False
    assert predictor.model is not None
    assert metrics.f1 is None
    assert metrics.precision is None
    assert metrics.recall is None
    assert metrics.evaluation_status == "not_evaluated"
    assert metrics.evaluation_folds == 0
    assert len(predictor.predict(features)) == len(features)


def test_training_failure_falls_back_without_claiming_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A backend fit failure retains a usable explicitly heuristic result."""
    import src.model as model_module

    def fail_fit(*args: object, **kwargs: object) -> None:
        raise ValueError("synthetic XGBoost fit failure")

    monkeypatch.setattr(model_module.XGBClassifier, "fit", fail_fit)
    features = _make_features(60)
    predictor = BugPredictor()
    metrics = predictor.train(features, _make_labels(features))
    assert predictor.use_heuristic is True
    assert predictor.model is None
    assert metrics.evaluation_status == "not_evaluated"
    assert metrics.f1 is None
    assert metrics.fallback_reason == "training_failed"
    assert np.isfinite(predictor.predict(features)).all()


def test_retraining_small_input_clears_previous_model() -> None:
    """Heuristic retraining must not leave an obsolete model available."""
    predictor = BugPredictor()
    large = _make_features(60)
    predictor.train(large, _make_labels(large))
    assert predictor.model is not None
    small = _make_features(5)
    metrics = predictor.train(small, _make_labels(small))
    assert predictor.model is None
    assert predictor.use_heuristic is True
    assert metrics.evaluation_status == "not_evaluated"
    assert metrics.f1 is None
    assert metrics.fallback_reason == "insufficient_samples"


def test_prediction_failure_switches_to_explicit_heuristic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An inference backend error cannot leave a false trained-model result."""
    predictor = BugPredictor()
    features = _make_features(60)
    predictor.train(features, _make_labels(features))
    assert predictor.model is not None

    def fail_predict(*args: object, **kwargs: object) -> None:
        raise ValueError("synthetic XGBoost inference failure")

    monkeypatch.setattr(predictor.model, "predict_proba", fail_predict)
    scores = predictor.predict(features)
    assert np.isfinite(scores).all()
    assert predictor.use_heuristic is True
    assert predictor.model is None
    assert predictor.metrics.f1 is None
    assert predictor.metrics.evaluation_status == "not_evaluated"
    assert predictor.metrics.fallback_reason == "prediction_failed"


def test_shap_failure_uses_global_importance_without_losing_predictions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An optional explanation failure must not abort model predictions."""
    import src.model as model_module

    predictor = BugPredictor()
    features = _make_features(60)
    predictor.train(features, _make_labels(features))

    def fail_explainer(*args: object, **kwargs: object) -> None:
        raise RuntimeError("synthetic SHAP failure")

    monkeypatch.setattr(model_module, "_HAS_SHAP", True)
    monkeypatch.setattr(model_module.shap, "TreeExplainer", fail_explainer)
    explanations = predictor.explain(features)
    assert len(explanations) == len(features)
    assert all(item["top_factors"] for item in explanations)
    assert predictor.use_heuristic is False


@pytest.mark.parametrize("labels", [[0, 1], [0] * 59 + [2], [0] * 59 + [None]])
def test_invalid_training_labels_are_rejected(labels: list[int | None]) -> None:
    """Malformed labels are input errors, not a successful heuristic training run."""
    features = _make_features(60)
    with pytest.raises(ValueError, match="Label count|binary"):
        BugPredictor().train(features, pd.Series(labels))


def test_shap_not_installed_uses_global_importance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional explanation dependencies are unnecessary for model inference."""
    import src.model as model_module

    monkeypatch.setattr(model_module, "_HAS_SHAP", False)
    features = _make_features(60)
    predictor = BugPredictor()
    predictor.train(features, _make_labels(features))
    assert len(predictor.explain(features)) == len(features)
    assert np.isfinite(predictor.predict(features)).all()


@pytest.mark.parametrize("profile", ["default", "safety-critical"])
def test_heuristic_explanation_retains_history_factor_values(profile: str) -> None:
    """A scored heuristic-only feature keeps its actual per-file value."""
    from src.model import NUMERIC_FEATURES

    features = pd.DataFrame(
        [
            {**{name: 0.0 for name in NUMERIC_FEATURES}, "bug_fix_commits": count}
            for count in [0, 3, 1, 2]
        ],
        index=[17, 3, 92, 44],
    )
    predictor = BugPredictor(profile=profile)
    predictor.train(features, pd.Series([0, 0, 0, 0]))
    scores = predictor.predict(features)
    explanations = predictor.explain(features)
    assert scores[1] > scores[0]
    for row_position, count in enumerate([0, 3, 1, 2]):
        factors = {
            factor["feature"]: factor
            for factor in explanations[row_position]["top_factors"]
        }
        assert factors["bug_fix_commits"]["value"] == count
        assert factors["bug_fix_commits"]["importance"] > 0
