"""Bug prediction model for cppulse predictor.

Provides XGBClassifier-based prediction with a heuristic fallback
when fewer than 50 training samples are available.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from xgboost import XGBClassifier

try:
    import shap

    _HAS_SHAP = True
except ImportError:  # pragma: no cover
    _HAS_SHAP = False

logger = logging.getLogger(__name__)

_BASE_NUMERIC_FEATURES: list[str] = [
    "finding_count",
    "memory_findings",
    "modernization_findings",
    "complexity_findings",
    "max_severity",
    "change_frequency",
    "unique_contributors",
    "churn_rate",
    "bug_fix_commits",
    "age_days",
    "is_knowledge_silo",
]

_MISRA_FEATURE: str = "misra_findings"

NUMERIC_FEATURES: list[str] = _BASE_NUMERIC_FEATURES + [_MISRA_FEATURE]

_BASE_HEURISTIC_WEIGHTS: dict[str, float] = {
    "memory_findings": 3.0,
    "complexity_findings": 1.5,
    "modernization_findings": 1.0,
    "churn_rate": 2.0,
    "bug_fix_commits": 1.5,
}

HEURISTIC_WEIGHTS: dict[str, float] = {
    **_BASE_HEURISTIC_WEIGHTS,
    "misra_findings": 2.5,
}


def _features_for_profile(profile: str) -> list[str]:
    """Return the numeric feature list for the given profile.

    Args:
        profile: "default" or "safety-critical".

    Returns:
        List of feature column names.
    """
    if profile == "safety-critical":
        return _BASE_NUMERIC_FEATURES + [_MISRA_FEATURE]
    return list(_BASE_NUMERIC_FEATURES)


def _heuristic_weights_for_profile(profile: str) -> dict[str, float]:
    """Return heuristic weights for the given profile.

    Args:
        profile: "default" or "safety-critical".

    Returns:
        Dict mapping feature names to weights.
    """
    if profile == "safety-critical":
        return {**_BASE_HEURISTIC_WEIGHTS, _MISRA_FEATURE: 2.5}
    return dict(_BASE_HEURISTIC_WEIGHTS)


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

    Args:
        profile: Analysis profile. "default" excludes MISRA features from
            the model; "safety-critical" includes them.

    Attributes:
        model: Trained XGBClassifier, or None if using heuristic.
        metrics: Training metrics from the last call to train().
        use_heuristic: True when the heuristic fallback is active.
    """

    def __init__(self, profile: str = "default") -> None:
        """Initialize BugPredictor with no trained model."""
        self.model: XGBClassifier | None = None
        self.metrics: ModelMetrics = ModelMetrics()
        self.use_heuristic: bool = False
        self._feature_max: pd.Series | None = None
        self._features = _features_for_profile(profile)
        self._heuristic_weights = _heuristic_weights_for_profile(profile)

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
        X = features_df[self._features].fillna(0).astype(float)

        self.model = XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            objective="binary:logistic",
            eval_metric="logloss",
            verbosity=0,
            use_label_encoder=False,
        )

        # Evaluate via stratified k-fold CV before final training.
        # This prevents inflated metrics from evaluating on training data.
        n_folds = min(5, n_samples)
        n_positive = int(labels.sum())
        n_negative = n_samples - n_positive
        can_stratify = n_positive >= n_folds and n_negative >= n_folds

        if can_stratify:
            cv = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
            cv_predictions = cross_val_predict(self.model, X, labels, cv=cv)
            f1 = float(f1_score(labels, cv_predictions, zero_division=0))
            precision = float(precision_score(labels, cv_predictions, zero_division=0))
            recall = float(recall_score(labels, cv_predictions, zero_division=0))
            logger.info(
                "XGBoost %d-fold CV: F1=%.3f, Precision=%.3f, Recall=%.3f, samples=%d",
                n_folds,
                f1,
                precision,
                recall,
                n_samples,
            )
        else:
            # Too few positives/negatives for stratified CV — report without metrics.
            f1 = 0.0
            precision = 0.0
            recall = 0.0
            logger.info(
                "XGBoost: skipping CV (need >= %d positive and negative samples), "
                "samples=%d, positives=%d",
                n_folds,
                n_samples,
                n_positive,
            )

        # Train final model on all data for production predictions.
        self.model.fit(X, labels)
        self._training_X = X

        self.metrics = ModelMetrics(
            f1=f1,
            precision=precision,
            recall=recall,
            training_samples=n_samples,
        )
        return self.metrics

    def explain(self, features_df: pd.DataFrame) -> list[dict[str, list[dict[str, float]]]]:
        """Compute per-file feature importance using SHAP or XGBoost gain fallback.

        When SHAP is installed, uses TreeExplainer for per-prediction SHAP
        values. Otherwise falls back to global XGBoost feature importances.

        Args:
            features_df: DataFrame containing NUMERIC_FEATURES columns.

        Returns:
            List of dicts, one per row, each with a 'top_factors' key mapping
            to a list of up to 5 {feature, importance, value} dicts sorted
            by descending importance.
        """
        if features_df.empty:
            return []

        X = features_df[self._features].fillna(0).astype(float)

        if _HAS_SHAP and self.model is not None and not self.use_heuristic:
            explainer = shap.TreeExplainer(self.model)
            shap_values = explainer.shap_values(X)
            explanations = []
            for i in range(len(X)):
                factors = [
                    {
                        "feature": feat,
                        "importance": float(abs(shap_values[i, j])),
                        "value": float(X.iloc[i, j]),
                    }
                    for j, feat in enumerate(self._features)
                ]
                factors.sort(key=lambda x: x["importance"], reverse=True)
                explanations.append({"top_factors": factors[:5]})
            return explanations

        # Fallback: global feature importance from XGBoost or heuristic weights
        if self.model is not None and not self.use_heuristic:
            raw = self.model.feature_importances_
            total = float(raw.sum()) or 1.0
            importance = {
                feat: float(raw[i]) / total for i, feat in enumerate(self._features)
            }
        else:
            total = sum(self._heuristic_weights.values())
            importance = {f: w / total for f, w in self._heuristic_weights.items()}

        explanations = []
        for i in range(len(X)):
            factors = [
                {
                    "feature": feat,
                    "importance": imp,
                    "value": float(X.iloc[i][feat]) if feat in X.columns else 0.0,
                }
                for feat, imp in importance.items()
            ]
            factors.sort(key=lambda x: x["importance"], reverse=True)
            explanations.append({"top_factors": factors[:5]})
        return explanations

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

        X = features_df[self._features].fillna(0).astype(float)
        proba = self.model.predict_proba(X)[:, 1]
        return proba.astype(float)

    def _fit_heuristic(self, features_df: pd.DataFrame) -> None:
        """Compute per-feature max values for heuristic normalization.

        Args:
            features_df: Training feature DataFrame.
        """
        relevant = [c for c in self._heuristic_weights if c in features_df.columns]
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

        for feature, weight in self._heuristic_weights.items():
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

        total_weight = sum(self._heuristic_weights.values())
        score = score / total_weight
        return score.clip(0.0, 1.0).to_numpy(dtype=float)
