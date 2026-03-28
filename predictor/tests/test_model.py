"""Tests for src/model.py — BugPredictor."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.model import MIN_SAMPLES_FOR_ML, NUMERIC_FEATURES, BugPredictor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_features(n: int, seed: int = 42) -> pd.DataFrame:
    """Generate a synthetic feature DataFrame with n rows.

    Args:
        n: Number of rows to generate.
        seed: NumPy random seed for reproducibility.

    Returns:
        DataFrame with all NUMERIC_FEATURES columns plus a 'file' column.
    """
    rng = np.random.default_rng(seed)
    data = {
        feat: rng.integers(0, 10, size=n).astype(float) for feat in NUMERIC_FEATURES
    }
    data["churn_rate"] = rng.uniform(0, 5, size=n)
    data["file"] = [f"src/file_{i}.cpp" for i in range(n)]
    return pd.DataFrame(data)


def _make_labels(features_df: pd.DataFrame, positive_ratio: float = 0.4) -> pd.Series:
    """Generate synthetic binary labels.

    Args:
        features_df: Feature DataFrame.
        positive_ratio: Proportion of positive (buggy) labels.

    Returns:
        Integer Series of 0/1 labels.
    """
    n = len(features_df)
    labels = np.zeros(n, dtype=int)
    n_positive = max(1, int(n * positive_ratio))
    labels[:n_positive] = 1
    rng = np.random.default_rng(0)
    rng.shuffle(labels)
    return pd.Series(labels)


# ---------------------------------------------------------------------------
# Heuristic fallback tests (< 50 samples)
# ---------------------------------------------------------------------------


class TestHeuristicFallback:
    """Tests for the heuristic scoring path (fewer than 50 samples)."""

    def test_uses_heuristic_when_below_threshold(self) -> None:
        """With 10 samples, use_heuristic must be True after train()."""
        predictor = BugPredictor()
        df = _make_features(10)
        labels = _make_labels(df)
        predictor.train(df, labels)
        assert predictor.use_heuristic is True
        assert predictor.model is None

    def test_uses_heuristic_at_exactly_49_samples(self) -> None:
        """With exactly 49 samples, heuristic should still be used."""
        predictor = BugPredictor()
        df = _make_features(MIN_SAMPLES_FOR_ML - 1)
        labels = _make_labels(df)
        predictor.train(df, labels)
        assert predictor.use_heuristic is True

    def test_heuristic_probabilities_in_unit_interval(self) -> None:
        """Heuristic scores must all be in [0.0, 1.0]."""
        predictor = BugPredictor()
        df = _make_features(5)
        labels = _make_labels(df)
        predictor.train(df, labels)
        probs = predictor.predict(df)
        assert probs.min() >= 0.0
        assert probs.max() <= 1.0

    def test_heuristic_returns_one_value_per_row(self) -> None:
        """Returned array length must equal number of input rows."""
        predictor = BugPredictor()
        df = _make_features(7)
        labels = _make_labels(df)
        predictor.train(df, labels)
        probs = predictor.predict(df)
        assert len(probs) == 7

    def test_heuristic_high_risk_file_scores_higher(self) -> None:
        """File with many memory/MISRA findings should score higher than clean file."""
        predictor = BugPredictor()
        df = _make_features(5)
        labels = _make_labels(df)
        predictor.train(df, labels)

        risky = pd.DataFrame(
            [
                {
                    **{f: 0 for f in NUMERIC_FEATURES},
                    "memory_findings": 10,
                    "misra_findings": 8,
                    "churn_rate": 5.0,
                    "bug_fix_commits": 10,
                }
            ]
        )
        clean = pd.DataFrame([{**{f: 0 for f in NUMERIC_FEATURES}}])
        risky_score = predictor.predict(risky)[0]
        clean_score = predictor.predict(clean)[0]
        assert risky_score > clean_score

    def test_metrics_training_samples_recorded(self) -> None:
        """ModelMetrics.training_samples must match the input size."""
        predictor = BugPredictor()
        df = _make_features(12)
        labels = _make_labels(df)
        metrics = predictor.train(df, labels)
        assert metrics.training_samples == 12


# ---------------------------------------------------------------------------
# XGBoost model tests (>= 50 samples)
# ---------------------------------------------------------------------------


class TestXGBoostModel:
    """Tests for the XGBoost ML path (50 or more samples)."""

    def test_uses_ml_when_above_threshold(self) -> None:
        """With 50+ samples, use_heuristic must be False after train()."""
        predictor = BugPredictor()
        df = _make_features(60)
        labels = _make_labels(df)
        predictor.train(df, labels)
        assert predictor.use_heuristic is False
        assert predictor.model is not None

    def test_predict_probabilities_in_unit_interval(self) -> None:
        """XGBoost predict must return values in [0.0, 1.0]."""
        predictor = BugPredictor()
        df = _make_features(60)
        labels = _make_labels(df)
        predictor.train(df, labels)
        probs = predictor.predict(df)
        assert probs.min() >= 0.0
        assert probs.max() <= 1.0

    def test_predict_length_matches_input(self) -> None:
        """Array length must equal number of rows."""
        predictor = BugPredictor()
        df = _make_features(60)
        labels = _make_labels(df)
        predictor.train(df, labels)
        probs = predictor.predict(df)
        assert len(probs) == 60

    def test_metrics_contain_f1(self) -> None:
        """ModelMetrics.f1 must be a float in [0, 1] after XGBoost training."""
        predictor = BugPredictor()
        df = _make_features(60)
        labels = _make_labels(df)
        metrics = predictor.train(df, labels)
        assert 0.0 <= metrics.f1 <= 1.0

    def test_training_samples_recorded(self) -> None:
        """ModelMetrics.training_samples must match the input count."""
        predictor = BugPredictor()
        df = _make_features(55)
        labels = _make_labels(df)
        metrics = predictor.train(df, labels)
        assert metrics.training_samples == 55

    def test_predict_on_new_data(self) -> None:
        """Model trained on one set should predict on an unseen set without error."""
        predictor = BugPredictor()
        train_df = _make_features(60)
        labels = _make_labels(train_df)
        predictor.train(train_df, labels)

        test_df = _make_features(10, seed=99)
        probs = predictor.predict(test_df)
        assert len(probs) == 10
        assert probs.min() >= 0.0
        assert probs.max() <= 1.0


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Edge-case and boundary tests for BugPredictor."""

    def test_predict_empty_dataframe_returns_empty_array(self) -> None:
        """predict() on an empty DataFrame must return an empty array."""
        predictor = BugPredictor()
        df = pd.DataFrame(columns=NUMERIC_FEATURES)
        result = predictor.predict(df)
        assert len(result) == 0
        assert isinstance(result, np.ndarray)

    def test_predict_without_train_uses_heuristic(self) -> None:
        """predict() before train() must fall back to heuristic safely."""
        predictor = BugPredictor()
        df = _make_features(5)
        probs = predictor.predict(df)
        assert len(probs) == 5
        assert probs.min() >= 0.0
        assert probs.max() <= 1.0

    def test_all_zero_features_give_zero_heuristic(self) -> None:
        """All-zero features should produce a heuristic score of 0.0."""
        predictor = BugPredictor()
        small_df = pd.DataFrame([{f: 0 for f in NUMERIC_FEATURES}] * 5)
        labels = pd.Series([0] * 5)
        predictor.train(small_df, labels)

        zero_df = pd.DataFrame([{f: 0 for f in NUMERIC_FEATURES}])
        probs = predictor.predict(zero_df)
        assert probs[0] == pytest.approx(0.0)

    def test_return_type_is_numpy_array(self) -> None:
        """predict() must always return a numpy ndarray."""
        predictor = BugPredictor()
        df = _make_features(5)
        labels = _make_labels(df)
        predictor.train(df, labels)
        result = predictor.predict(df)
        assert isinstance(result, np.ndarray)
