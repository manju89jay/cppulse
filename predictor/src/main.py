"""CLI entry point for cppulse predictor component.

Orchestrates feature engineering, bug prediction, health scoring,
and roadmap generation from analyzer-core and git-miner outputs.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

import numpy as np
import pandas as pd

from src.feature_engineer import FEATURE_COLUMNS, FeatureEngineer
from src.health_scorer import HealthScorer
from src.model import BugPredictor
from src.roadmap_generator import RoadmapGenerator
from src.schema_validator import SchemaValidator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

NUMERIC_FEATURES: list[str] = [col for col in FEATURE_COLUMNS if col != "file"]

RISK_THRESHOLDS: dict[str, float] = {
    "critical": 0.8,
    "high": 0.6,
    "medium": 0.3,
}


def _load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file and return the parsed dict.

    Args:
        path: Absolute path to the JSON file.

    Returns:
        Parsed JSON dict.

    Raises:
        SystemExit: If the file is not found or cannot be parsed.
    """
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        logger.error("Required input file not found: %s", path)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON from %s: %s", path, exc)
        sys.exit(1)


def _derive_labels(features_df: pd.DataFrame, profile: str = "default") -> pd.Series:
    """Derive training labels from git history.

    Primary source: SZZ analysis — a file is labeled buggy (1) when at least
    one bug-introducing commit touched it. The SZZ column is excluded from
    the model's feature set (see model._BASE_NUMERIC_FEATURES), so the label
    is independent of the features the model trains on.

    Fallback (logged loudly): when no SZZ data is available — e.g. metrics
    produced by an older git-miner — fall back to the legacy heuristic
    (>= 1 memory finding or >= 3 bug-fix commits; MISRA findings on the
    safety-critical profile). Heuristic labels overlap with model features,
    so reported CV metrics are optimistic in that mode.

    Args:
        features_df: Feature DataFrame from FeatureEngineer.
        profile: Analysis profile name.

    Returns:
        Binary pandas Series of integer labels (0 or 1).
    """
    if (
        "szz_bug_introductions" in features_df.columns
        and features_df["szz_bug_introductions"].sum() > 0
    ):
        return (features_df["szz_bug_introductions"] >= 1).astype(int)

    logger.warning(
        "No SZZ bug-introduction data in git_metrics — falling back to "
        "heuristic labels (memory findings / bug-fix commits). CV metrics "
        "will be optimistic; re-run git-miner to produce SZZ labels."
    )
    buggy = (features_df["memory_findings"] >= 1) | (
        features_df["bug_fix_commits"] >= 3
    )
    if profile == "safety-critical":
        buggy = buggy | (features_df["misra_findings"] >= 1)
    return buggy.astype(int)


def _assign_risk_level(probability: float) -> str:
    """Map a bug probability to a risk level string.

    Args:
        probability: Float in [0.0, 1.0].

    Returns:
        One of "critical", "high", "medium", "low".
    """
    if probability > RISK_THRESHOLDS["critical"]:
        return "critical"
    if probability > RISK_THRESHOLDS["high"]:
        return "high"
    if probability > RISK_THRESHOLDS["medium"]:
        return "medium"
    return "low"


def _compute_top_factors(
    row: pd.Series,
    feature_importance: dict[str, float],
) -> list[dict[str, Any]]:
    """Extract top-5 contributing features for a file.

    Args:
        row: One row from the feature DataFrame.
        feature_importance: Mapping of feature name to importance score.

    Returns:
        List of up to 5 dicts with keys feature, importance, value.
    """
    factors = [
        {
            "feature": feat,
            "importance": float(imp),
            "value": float(row.get(feat, 0)),
        }
        for feat, imp in feature_importance.items()
        if feat in row.index
    ]
    factors.sort(key=lambda x: x["importance"], reverse=True)
    return factors[:5]


def _build_feature_importance(predictor: BugPredictor) -> dict[str, float]:
    """Extract feature importance from a trained model or use uniform weights.

    Args:
        predictor: Trained BugPredictor instance.

    Returns:
        Mapping of feature name to normalized importance score.
    """
    if predictor.model is not None and not predictor.use_heuristic:
        raw = predictor.model.feature_importances_
        total = float(raw.sum()) or 1.0
        return {
            feat: float(raw[i]) / total for i, feat in enumerate(predictor._features)
        }

    # Heuristic weights as importance proxy
    total = sum(predictor._heuristic_weights.values())
    return {feat: w / total for feat, w in predictor._heuristic_weights.items()}


def _compute_hotspot_score(row: pd.Series) -> float:
    """Compute the hotspot score for a file row.

    hotspot_score = change_frequency * normalized_complexity * debt_density

    Normalized complexity maps max_severity (1–3) to [0.33, 1.0].
    Debt density = finding_count / max(1, age_days / 365).

    Args:
        row: One row from the feature DataFrame.

    Returns:
        Non-negative float hotspot score.
    """
    change_freq = float(row.get("change_frequency", 0))
    max_sev = float(row.get("max_severity", 0))
    finding_count = float(row.get("finding_count", 0))
    age_days = float(row.get("age_days", 1)) or 1.0

    normalized_complexity = max_sev / 3.0 if max_sev > 0 else 0.0
    debt_density = finding_count / max(age_days / 365.0, 1.0)

    return change_freq * normalized_complexity * debt_density


def build_risk_scores(
    features_df: pd.DataFrame,
    probabilities: np.ndarray,
    predictor: BugPredictor,
    health_scorer: HealthScorer,
    total_loc: int,
) -> dict[str, Any]:
    """Assemble the risk_scores.json payload.

    Args:
        features_df: Feature DataFrame with one row per file.
        probabilities: Bug probability array aligned with features_df rows.
        predictor: Trained BugPredictor (for model metadata).
        health_scorer: HealthScorer instance.
        total_loc: Total analyzed lines of code (findings.json metadata),
            used to normalize finding densities per KLOC.

    Returns:
        Dict matching the risk_scores.schema.json schema.
    """
    health = health_scorer.compute(features_df, total_loc)
    explanations = predictor.explain(features_df)

    file_risks: list[dict[str, Any]] = []
    hotspot_scores: list[dict[str, Any]] = []

    for i, (_, row) in enumerate(features_df.iterrows()):
        prob = float(probabilities[i]) if i < len(probabilities) else 0.0
        risk_level = _assign_risk_level(prob)
        top_factors = explanations[i]["top_factors"] if i < len(explanations) else []

        file_risks.append(
            {
                "file": str(row["file"]),
                "bug_probability": round(prob, 6),
                "risk_level": risk_level,
                "top_factors": top_factors,
            }
        )

        hs = _compute_hotspot_score(row)
        hotspot_scores.append(
            {
                "file": str(row["file"]),
                "hotspot_score": round(hs, 6),
                "change_frequency": int(row.get("change_frequency", 0)),
                "complexity_score": round(float(row.get("max_severity", 0)) / 3.0, 4),
                "finding_count": int(row.get("finding_count", 0)),
            }
        )

    hotspot_scores.sort(key=lambda x: x["hotspot_score"], reverse=True)
    hotspots = hotspot_scores[:20]

    return {
        "version": "1.0.0",
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model_type": "xgboost",
            "feature_count": len(NUMERIC_FEATURES),
            "training_samples": predictor.metrics.training_samples,
            "f1_score": round(predictor.metrics.f1, 4),
        },
        "health_score": {
            "overall": round(health.overall, 2),
            "by_category": {k: round(v, 2) for k, v in health.by_category.items()},
        },
        "file_risks": file_risks,
        "hotspots": hotspots,
    }


def build_roadmap(
    findings_data: dict[str, Any],
    git_metrics_data: dict[str, Any],
    risk_scores_data: dict[str, Any],
    profile: str = "default",
) -> dict[str, Any]:
    """Assemble the roadmap.json payload.

    Args:
        findings_data: Parsed findings.json.
        git_metrics_data: Parsed git_metrics.json.
        risk_scores_data: Assembled risk scores dict.
        profile: Analysis profile. "default" excludes MISRA items.

    Returns:
        Dict matching the roadmap.schema.json schema.
    """
    generator = RoadmapGenerator(profile=profile)
    items = generator.generate(findings_data, git_metrics_data, risk_scores_data)

    return {
        "version": "1.0.0",
        "items": [
            {
                "priority": item.priority,
                "file": item.file,
                "action": item.action,
                "category": item.category,
                "estimated_hours": item.estimated_hours,
                "impact_score": round(item.impact_score, 4),
                "finding_ids": item.finding_ids,
            }
            for item in items
        ],
    }


def run(input_dir: Path, output_dir: Path, profile: str = "default") -> None:
    """Execute the full predictor pipeline.

    Args:
        input_dir: Directory containing findings.json and git_metrics.json.
        output_dir: Directory to write risk_scores.json and roadmap.json.
        profile: Analysis profile. "default" excludes MISRA rules,
            "safety-critical" includes them.
    """
    logger.info("Loading inputs from %s", input_dir)
    findings_data = _load_json(input_dir / "findings.json")
    git_metrics_data = _load_json(input_dir / "git_metrics.json")

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Engineering features...")
    engineer = FeatureEngineer()
    features_df = engineer.build_features(findings_data, git_metrics_data)
    logger.info("Feature matrix shape: %s", features_df.shape)

    logger.info("Training bug predictor...")
    predictor = BugPredictor(profile=profile)
    labels = _derive_labels(features_df, profile=profile)
    predictor.train(features_df, labels)

    logger.info("Generating predictions...")
    probabilities = predictor.predict(features_df)

    logger.info("Computing health scores...")
    health_scorer = HealthScorer(profile=profile)
    total_loc = int(findings_data.get("metadata", {}).get("total_loc", 0))
    if total_loc <= 0:
        logger.warning(
            "findings.json metadata has no total_loc — density normalization "
            "degenerates to a 1-KLOC baseline"
        )

    logger.info("Building risk scores output...")
    risk_scores = build_risk_scores(
        features_df, probabilities, predictor, health_scorer, total_loc
    )

    logger.info("Validating risk_scores.json schema...")
    validator = SchemaValidator()
    validator.validate_risk_scores(risk_scores)

    risk_scores_path = output_dir / "risk_scores.json"
    with risk_scores_path.open("w", encoding="utf-8") as fh:
        json.dump(risk_scores, fh, indent=2)
    logger.info("Wrote %s", risk_scores_path)

    logger.info("Generating refactoring roadmap...")
    roadmap = build_roadmap(findings_data, git_metrics_data, risk_scores, profile)

    logger.info("Validating roadmap.json schema...")
    validator.validate_roadmap(roadmap)

    roadmap_path = output_dir / "roadmap.json"
    with roadmap_path.open("w", encoding="utf-8") as fh:
        json.dump(roadmap, fh, indent=2)
    logger.info("Wrote %s", roadmap_path)

    overall = risk_scores["health_score"]["overall"]
    logger.info("Pipeline complete. Overall health score: %.1f/100", overall)


def _load_profile_from_config(config_path: Path) -> str:
    """Extract the profile setting from a .cppulserc.yml/.json config file.

    Args:
        config_path: Path to the config file.

    Returns:
        Profile string ("default" or "safety-critical").
    """
    try:
        content = config_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning("Config file not found: %s", config_path)
        return "default"

    if config_path.suffix == ".json":
        data = json.loads(content)
    elif _HAS_YAML and config_path.suffix in (".yml", ".yaml"):
        data = yaml.safe_load(content) or {}
    else:
        # Fallback: try JSON first, then simple line scanning for YAML.
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Simple YAML fallback: scan for "profile:" line.
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith("profile:"):
                    value = stripped.split(":", 1)[1].strip().strip("'\"")
                    if value in ("default", "safety-critical"):
                        return value
            return "default"

    profile = data.get("profile", "default")
    if profile not in ("default", "safety-critical"):
        logger.warning("Unknown profile '%s' in config, using 'default'", profile)
        return "default"
    return profile


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments.

    Args:
        argv: Argument list (defaults to sys.argv if None).

    Returns:
        Parsed namespace with input and output Path attributes.
    """
    parser = argparse.ArgumentParser(
        description="cppulse predictor: ML-based bug risk scoring for C++ codebases."
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="Directory containing findings.json and git_metrics.json.",
    )
    parser.add_argument(
        "--output",
        default=Path("./output"),
        type=Path,
        help="Output directory for risk_scores.json and roadmap.json (default: ./output).",
    )
    parser.add_argument(
        "--profile",
        default="default",
        choices=["default", "safety-critical"],
        help="Analysis profile. 'default' excludes MISRA rules; 'safety-critical' includes them.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to .cppulserc.yml/.json config file. Profile is read from it if --profile is not explicitly set.",
    )
    return parser.parse_args(argv)


def main() -> None:
    """Entry point for the predictor CLI."""
    args = parse_args()
    profile = args.profile
    # If --config is given and --profile was not explicitly set, read profile from config.
    if args.config is not None and profile == "default":
        config_profile = _load_profile_from_config(args.config)
        if config_profile != "default":
            logger.info("Using profile '%s' from config file", config_profile)
            profile = config_profile
    run(input_dir=args.input, output_dir=args.output, profile=profile)


if __name__ == "__main__":
    main()
