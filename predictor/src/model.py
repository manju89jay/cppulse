"""Bug prediction model for cppulse predictor.

Provides XGBClassifier-based prediction with a heuristic fallback
when fewer than 50 training samples are available.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score
from xgboost import XGBClassifier

logger = logging.getLogger(__name__)

NUMERIC_FEATURES: list[str] = [
    "finding_count",
    "memory_findings",
    "modernization_findings",
    "complexity_findings",
    "misra_findings",
    "max_severity",
    "change_frequency",
    "unique_contributors",
    "churn_rate",
    "bug_fix_commits",
    "age_days",
    "is_knowledge_silo",
]

HEURISTIC_WEIGHTS: dict[str, float] = {
    "memory_findings": 3.0,
    "misra_findings": 2.5,
    "complexity_findings": 1.5,
    "modernization_findings": 1.0,
    "churn_rate": 2.0,
    "bug_fix_commits": 1.5,
}

MIN_SAMPLES_FOR_ML: int = 50


@dataclass
class ModelMetrics:
    """Training metrics for the bug predictor.

    Attributes:
        f1: F1 score on training data.
        precision: Precision score on training data.
        recall: Recall score on training data.
        training_samples: Number of samples used for training.
    """

    f1: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    training_samples: int = 0


class BugPredictor:
    """Predicts bug probability per file using XGBoost or heuristic fallback.

    Uses XGBClassifier when >= 50 samples are available, otherwise falls back
    to a weighted heuristic sum of normalized features.

    Attributes:
        model: Trained XGBClassifier, or None if using heuristic.
        metrics: Training metrics from the last call to train().
        use_heuristic: True when the heuristic fallback is active.
    """

    def __init__(self) -> None:
        """Initialize BugPredictor with no trained model."""
        self.model: XGBClassifier | None = None
        self.metrics: ModelMetrics = ModelMetrics()
        self.use_heuristic: bool = False
        self._feature_max: pd.Series | None = None

    def train(self, features_df: pd.DataFrame, labels: pd.Series) -> ModelMetrics:
        """Train the bug prediction model.

        Falls back to heuristic scoring when fewer than 50 samples are provided.
        Logs F1, precision, and recall after training.

        Args:
            features_df: DataFrame containing NUMERIC_FEATURES columns.
            labels: Binary Series (1 = historically buggy, 0 = clean).

        Returns:
            ModelMetrics with f1, precision, recall, and training_samples.
        """
        n_samples = len(features_df)

        if n_samples < MIN_SAMPLES_FOR_ML:
            logger.info(
                "Only %d samples — using heuristic fallback (need >= %d for ML).",
                n_samples,
                MIN_SAMPLES_FOR_ML,
            )
            self.use_heuristic = True
            self._fit_heuristic(features_df)
            self.metrics = ModelMetrics(training_samples=n_samples)
            return self.metrics

        self.use_heuristic = False
        X = features_df[NUMERIC_FEATURES].fillna(0).astype(float)

        self.model = XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            objective="binary:logistic",
            eval_metric="logloss",
            verbosity=0,
            use_label_encoder=False,
        )
        self.model.fit(X, labels)

        predictions = self.model.predict(X)
        f1 = float(f1_score(labels, predictions, zero_division=0))
        precision = float(precision_score(labels, predictions, zero_division=0))
        recall = float(recall_score(labels, predictions, zero_division=0))

        logger.info(
            "XGBoost trained: F1=%.3f, Precision=%.3f, Recall=%.3f, samples=%d",
            f1,
            precision,
            recall,
            n_samples,
        )

        self.metrics = ModelMetrics(
            f1=f1,
            precision=precision,
            recall=recall,
            training_samples=n_samples,
        )
        return self.metrics

    def predict(self, features_df: pd.DataFrame) -> np.ndarray:
        """Predict bug probability for each file.

        Uses the trained XGBoost model if available, otherwise applies the
        heuristic fallback. Returns probabilities in [0.0, 1.0].

        Args:
            features_df: DataFrame containing NUMERIC_FEATURES columns.

        Returns:
            1-D numpy array of float probabilities, one per row.
        """
        if features_df.empty:
            return np.array([], dtype=float)

        if self.use_heuristic or self.model is None:
            return self._predict_heuristic(features_df)

        X = features_df[NUMERIC_FEATURES].fillna(0).astype(float)
        proba = self.model.predict_proba(X)[:, 1]
        return proba.astype(float)

    def _fit_heuristic(self, features_df: pd.DataFrame) -> None:
        """Compute per-feature max values for heuristic normalization.

        Args:
            features_df: Training feature DataFrame.
        """
        relevant = [c for c in HEURISTIC_WEIGHTS if c in features_df.columns]
        self._feature_max = features_df[relevant].max().replace(0, 1)

    def _predict_heuristic(self, features_df: pd.DataFrame) -> np.ndarray:
        """Apply weighted heuristic scoring.

        Computes a normalized weighted sum of risk-related features and
        clips to [0.0, 1.0].

        Args:
            features_df: DataFrame with feature columns.

        Returns:
            1-D numpy array of heuristic scores in [0.0, 1.0].
        """
        score = pd.Series(np.zeros(len(features_df)), index=features_df.index)

        for feature, weight in HEURISTIC_WEIGHTS.items():
            if feature not in features_df.columns:
                continue
            col = features_df[feature].fillna(0).astype(float)
            max_val = (
                float(self._feature_max[feature])
                if self._feature_max is not None and feature in self._feature_max
                else float(col.max()) or 1.0
            )
            if max_val == 0:
                max_val = 1.0
            score = score + weight * (col / max_val)

        total_weight = sum(HEURISTIC_WEIGHTS.values())
        score = score / total_weight
        return score.clip(0.0, 1.0).to_numpy(dtype=float)
