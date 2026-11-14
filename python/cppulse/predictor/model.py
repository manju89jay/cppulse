"""Experimental file-risk ranking for cppulse predictor.

Uses XGBoost when training is feasible and a heuristic fallback otherwise.
Scores and cross-validation metrics do not establish calibrated defect risk.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

# ML is optional for the installed core. Keep imported symbols available for
# compatibility, while explicitly identifying unavailable native/backends.
_HAS_ML = True
_ML_IMPORT_ERROR: str | None = None
try:
    from sklearn.metrics import f1_score, precision_score, recall_score
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from xgboost import XGBClassifier
    from xgboost.core import XGBoostError
except (ImportError, OSError, RuntimeError, ValueError, AttributeError) as exc:
    _HAS_ML = False
    _ML_IMPORT_ERROR = type(exc).__name__
    XGBClassifier = None
    StratifiedKFold = cross_val_predict = None
    f1_score = precision_score = recall_score = None

    class XGBoostError(RuntimeError):
        """Unavailable-backend placeholder for the existing error boundary."""


shap = None
_HAS_SHAP = False
if _HAS_ML:
    try:
        import shap

        _HAS_SHAP = True
    except (ImportError, OSError, RuntimeError, ValueError, AttributeError):
        _HAS_SHAP = False

logger = logging.getLogger(__name__)

# NOTE: deliberately excludes the label-adjacent columns. Training labels are
# derived from SZZ bug introductions, and bug_fix_commits counts the very
# fix commits SZZ starts from — including either as a feature would leak the
# label into the model and inflate CV metrics.
_BASE_NUMERIC_FEATURES: list[str] = [
    "finding_count",
    "memory_findings",
    "modernization_findings",
    "complexity_findings",
    "max_severity",
    "change_frequency",
    "unique_contributors",
    "churn_rate",
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
    """Evaluation metadata for the experimental predictor.

    Metrics are out-of-fold estimates when cross-validation executes. None
    means evaluation was unavailable; it is distinct from a measured zero.

    Attributes:
        f1: Out-of-fold F1, or None when not evaluated.
        precision: Out-of-fold precision, or None when not evaluated.
        recall: Out-of-fold recall, or None when not evaluated.
        training_samples: Number of input training rows.
        evaluation_status: Whether compatible cross-validation completed.
        evaluation_folds: Number of completed stratified folds, otherwise zero.
        fallback_reason: Why heuristic mode replaced the model, if applicable.
    """

    f1: float | None = None
    precision: float | None = None
    recall: float | None = None
    training_samples: int = 0
    evaluation_status: str = "not_evaluated"
    evaluation_folds: int = 0
    fallback_reason: str | None = None


class BugPredictor:
    """Ranks file risk experimentally using XGBoost or a heuristic fallback.

    Uses XGBoost when at least 50 samples and both label classes are available;
    otherwise uses a weighted heuristic sum. Scores are not calibrated defect
    probabilities.

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
        """Train a model when samples and label classes permit it.

        Small or single-class datasets use heuristic ranking. Backend training
        errors also degrade explicitly to heuristic results; no evaluation
        numbers from a failed model survive that transition.

        Args:
            features_df: DataFrame containing the numeric feature columns.
            labels: Binary 0/1 labels in the same row order as features_df.

        Returns:
            Evaluation metadata, with unavailable metrics represented by None.

        Raises:
            ValueError: If labels do not match rows or contain nonbinary values.
        """
        n_samples = len(features_df)
        if len(labels) != n_samples:
            raise ValueError("Label count must match the feature row count")
        if labels.isna().any() or not labels.isin([0, 1]).all():
            raise ValueError("Training labels must contain only binary 0/1 values")

        # Retraining must never keep an old model or old evaluation metadata.
        self.model = None
        self.metrics = ModelMetrics(training_samples=n_samples)
        self._fit_heuristic(features_df)
        if not _HAS_ML or XGBClassifier is None:
            logger.info(
                "Optional ML backend unavailable (%s): using heuristic ranking.",
                _ML_IMPORT_ERROR or "not installed",
            )
            return self._activate_heuristic(n_samples, "backend_unavailable")
        if n_samples < MIN_SAMPLES_FOR_ML:
            logger.info(
                "Only %d samples: using experimental heuristic ranking (need %d for ML).",
                n_samples,
                MIN_SAMPLES_FOR_ML,
            )
            return self._activate_heuristic(n_samples, "insufficient_samples")
        if labels.nunique() < 2:
            logger.info("Only one label class: using experimental heuristic ranking.")
            return self._activate_heuristic(n_samples, "insufficient_label_classes")

        self.use_heuristic = False
        X = features_df[self._features].fillna(0).astype(float)
        candidate = XGBClassifier(
            n_estimators=100,
            max_depth=6,
            learning_rate=0.1,
            objective="binary:logistic",
            eval_metric="logloss",
            verbosity=0,
            use_label_encoder=False,
            random_state=42,
            n_jobs=1,
        )
        f1 = precision = recall = None
        evaluation_status = "not_evaluated"
        evaluation_folds = 0
        n_folds = min(5, n_samples)
        n_positive = int(labels.sum())
        n_negative = n_samples - n_positive
        can_stratify = n_positive >= n_folds and n_negative >= n_folds

        try:
            if can_stratify:
                cv = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=42)
                cv_predictions = cross_val_predict(candidate, X, labels, cv=cv)
                f1 = float(f1_score(labels, cv_predictions, zero_division=0))
                precision = float(
                    precision_score(labels, cv_predictions, zero_division=0)
                )
                recall = float(recall_score(labels, cv_predictions, zero_division=0))
                evaluation_status = "cross_validated"
                evaluation_folds = n_folds
                logger.info(
                    "Experimental XGBoost %d-fold CV: F1=%.3f, precision=%.3f, "
                    "recall=%.3f, samples=%d",
                    n_folds,
                    f1,
                    precision,
                    recall,
                    n_samples,
                )
            else:
                logger.info(
                    "XGBoost CV not evaluated: need %d examples per class; "
                    "samples=%d, positives=%d.",
                    n_folds,
                    n_samples,
                    n_positive,
                )
            candidate.fit(X, labels)
        except (ValueError, RuntimeError, XGBoostError) as exc:
            logger.warning("XGBoost training failed; using heuristic ranking: %s", exc)
            return self._activate_heuristic(n_samples, "training_failed")

        self.model = candidate
        self.metrics = ModelMetrics(
            f1=f1,
            precision=precision,
            recall=recall,
            training_samples=n_samples,
            evaluation_status=evaluation_status,
            evaluation_folds=evaluation_folds,
        )
        return self.metrics

    def _activate_heuristic(self, training_samples: int, reason: str) -> ModelMetrics:
        """Discard unusable model state and retain explicit fallback metadata."""
        self.model = None
        self.use_heuristic = True
        self.metrics = ModelMetrics(
            training_samples=training_samples,
            fallback_reason=reason,
        )
        return self.metrics

    def explain(
        self, features_df: pd.DataFrame
    ) -> list[dict[str, list[dict[str, float]]]]:
        """Compute per-file feature importance using SHAP or XGBoost gain fallback.

        When SHAP is installed, uses TreeExplainer for per-prediction SHAP
        values. Otherwise falls back to global XGBoost feature importances or
        heuristic weights. Those fallback importances are global proxies, not
        per-file contributions; their values still reflect the original row.

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
            try:
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
            except (
                ValueError,
                TypeError,
                RuntimeError,
                AttributeError,
                IndexError,
            ) as exc:
                logger.warning(
                    "SHAP explanation unavailable; using global importance: %s", exc
                )

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

        # Heuristic features deliberately differ from ML inputs: for example,
        # bug_fix_commits must not leak into the trained model, but does affect
        # heuristic ranking. Read displayed values from the original facts.
        values = (
            features_df.reindex(columns=list(importance), fill_value=0)
            .fillna(0)
            .astype(float)
        )
        explanations = []
        for i in range(len(values)):
            factors = [
                {
                    "feature": feat,
                    "importance": imp,
                    "value": float(values.iloc[i][feat]),
                }
                for feat, imp in importance.items()
            ]
            factors.sort(key=lambda x: x["importance"], reverse=True)
            explanations.append({"top_factors": factors[:5]})
        return explanations

    def predict(self, features_df: pd.DataFrame) -> np.ndarray:
        """Return an experimental risk score for each file.

        Uses a trained XGBoost classifier when available, otherwise applies
        the heuristic fallback. Both return uncalibrated values in [0.0, 1.0].

        Args:
            features_df: DataFrame containing NUMERIC_FEATURES columns.

        Returns:
            1-D numpy array of experimental risk scores, one per row.
        """
        if features_df.empty:
            return np.array([], dtype=float)

        if self.use_heuristic or self.model is None:
            return self._predict_heuristic(features_df)

        X = features_df[self._features].fillna(0).astype(float)
        try:
            proba = self.model.predict_proba(X)[:, 1]
            if not np.isfinite(proba).all():
                raise ValueError("Model returned non-finite scores")
            return proba.astype(float)
        except (ValueError, RuntimeError, XGBoostError) as exc:
            logger.warning("XGBoost inference failed; using heuristic ranking: %s", exc)
            self._activate_heuristic(self.metrics.training_samples, "prediction_failed")
            return self._predict_heuristic(features_df)

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
