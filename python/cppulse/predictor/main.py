"""CLI entry point for cppulse predictor component.

Orchestrates feature engineering, bug prediction, health scoring,
and roadmap generation from analyzer-core and git-miner outputs.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml  # noqa: F401 -- preserve the intentional import availability probe

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

import jsonschema

from cppulse.contracts import load_schema

import numpy as np
import pandas as pd

from .feature_engineer import (
    FEATURE_COLUMNS,
    FeatureEngineer,
    RankAvailability,
    relative_identity,
)
from .health_scorer import HealthScorer
from .model import BugPredictor
from .roadmap_generator import RoadmapGenerator
from .schema_validator import SchemaValidator

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


def _szz_label_mask(features_df: pd.DataFrame) -> pd.Series:
    """Identify declared SZZ observations without confusing absent and zero."""
    if "szz_bug_introductions" not in features_df.columns:
        return pd.Series(False, index=features_df.index, dtype=bool)
    present = features_df["szz_bug_introductions"].notna()
    observed = features_df.attrs.get("szz_observed_files")
    if observed is not None:
        if "file" not in features_df.columns:
            raise ValueError("Declared SZZ provenance requires file identities")
        present = present & features_df["file"].isin(observed)
    return present


def _label_source(features_df: pd.DataFrame) -> str:
    """Describe the labels used for this exact eligible training cohort."""
    if features_df.empty:
        return "unavailable"
    mask = _szz_label_mask(features_df)
    if mask.all():
        return "szz"
    if mask.any():
        return "mixed_szz_and_feature_derived_heuristic"
    return "feature_derived_heuristic"


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
    if features_df.empty:
        return pd.Series(index=features_df.index, dtype=int)
    observed = _szz_label_mask(features_df)
    if observed.all():
        return (features_df["szz_bug_introductions"] >= 1).astype(int)

    logger.warning(
        "Some eligible files lack declared SZZ observations — falling back to "
        "heuristic labels for those files (memory findings / bug-fix commits). "
        "CV metrics can be optimistic because heuristic labels overlap model inputs; proxy-label evaluation is not future-defect validation."
    )
    buggy = (features_df["memory_findings"] >= 1) | (
        features_df["bug_fix_commits"] >= 3
    )
    if profile == "safety-critical":
        buggy = buggy | (features_df["misra_findings"] >= 1)
    if observed.any():
        buggy.loc[observed] = features_df.loc[observed, "szz_bug_introductions"] >= 1
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


def _compute_hotspot_score(
    row: pd.Series, metrics: dict[str, Any] | None = None
) -> dict[str, float] | None:
    """Use measured CC and physical LOC, never severity or a Git LOC proxy."""
    if metrics is None:
        return None
    from cppulse.maintenance import measured_hotspot_calculation

    return measured_hotspot_calculation(
        change_frequency=int(row.get("change_frequency", 0)),
        complexity=metrics["complexity_score"],
        finding_count=int(row.get("finding_count", 0)),
        physical_loc=metrics["physical_loc"],
    )


def build_risk_scores(
    features_df: pd.DataFrame,
    probabilities: np.ndarray,
    predictor: BugPredictor,
    health_scorer: HealthScorer,
    *,
    behavior: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the risk_scores.json payload.

    Args:
        features_df: Feature DataFrame with one row per file.
        probabilities: Bug probability array aligned with features_df rows.
        predictor: Trained BugPredictor (for model metadata).
        health_scorer: HealthScorer instance.

    Returns:
        Dict matching the risk_scores.schema.json schema.
    """
    health = health_scorer.compute(features_df)
    health_status = "no_data" if health.overall is None else "scored"
    limitations = list(features_df.attrs.get("limitations", []))
    if (
        not features_df.empty or features_df.attrs.get("health_declared_file_count", 0)
    ) and (
        features_df.attrs.get("health_availability") != "scored"
        or features_df.attrs.get("health_profile") != health_scorer.profile_name
        or features_df.attrs.get("health_prerequisites")
        != "normalized-required-context-v4"
    ):
        health.overall = None
        health.by_category = {category: None for category in health.by_category}
        health_status = "partial"
        if not any("Full-scope health unavailable" in text for text in limitations):
            limitations.append(
                "Full-scope health unavailable: a feature frame alone does not establish required analysis prerequisites."
            )

    explanations = predictor.explain(features_df)

    file_risks: list[dict[str, Any]] = []
    hotspot_scores: list[dict[str, Any]] = []
    measured = features_df.attrs.get("measured_hotspot_metrics", {})
    measured_files: set[str] = set()
    availability = dict(features_df.attrs.get("rank_availability", {}))
    for file in features_df["file"]:
        availability.setdefault(
            file,
            RankAvailability(
                file,
                "unverified",
                ("missing_rank_scope",),
                ("No per-file analysis/history inventory establishes ranking inputs.",),
            ),
        )

    for i, (_, row) in enumerate(features_df.iterrows()):
        file = str(row["file"])
        if not availability[file].eligible:
            continue
        prob = float(probabilities[i]) if i < len(probabilities) else None
        if prob is None or not math.isfinite(prob) or not 0 <= prob <= 1:
            availability[file] = RankAvailability(
                file,
                "unavailable",
                ("unavailable_model_output",),
                ("The model did not produce a finite ranking value for this file.",),
            )
            continue
        risk_level = _assign_risk_level(prob)
        top_factors = explanations[i]["top_factors"] if i < len(explanations) else []

        file_risks.append(
            {
                "file": file,
                "bug_probability": round(prob, 6),
                "risk_level": risk_level,
                "top_factors": top_factors,
            }
        )

        metrics = measured.get(file)
        calculation = _compute_hotspot_score(row, metrics)
        if calculation is not None:
            measured_files.add(file)
            hotspot_scores.append(
                {
                    "file": file,
                    **calculation,
                    "change_frequency": int(row.get("change_frequency", 0)),
                    "finding_count": int(row.get("finding_count", 0)),
                    **metrics,
                }
            )

    hotspot_scores.sort(key=lambda x: x["hotspot_score"], reverse=True)
    hotspots = [item for item in hotspot_scores if item["hotspot_score"] > 0][:20]

    active_features = (
        list(predictor._heuristic_weights)
        if predictor.use_heuristic
        else list(predictor._features)
    )
    unranked = [
        entry.unranked_record()
        for _, entry in sorted(availability.items())
        if not entry.eligible
    ]
    result = {
        "version": "1.0.0",
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "model_type": "heuristic" if predictor.use_heuristic else "xgboost",
            "profile": health_scorer.profile_name,
            "score_model": "weighted-findings-per-attempted-file-v2",
            "health_calculation": {
                "method": "weighted-findings-per-attempted-file-v2",
                "version": "2",
                "formula": "clamp(100 - sum(category_weight * finding_count) / denominator_files, 0, 100)",
                "profile": health_scorer.profile_name,
                "weights": dict(health_scorer._profile["weights"]),
                "category_scales": {
                    category: scale
                    for category, (_, scale) in health_scorer._profile[
                        "categories"
                    ].items()
                },
                "denominator_files": len(features_df),
                "declared_files": features_df.attrs.get("health_declared_file_count"),
                "availability": health_status,
            },
            "experimental": True,
            "hotspot_formula": "change_frequency * max_measured_callable_CC * findings / physical_KLOC",
            "hotspot_method": "measured-cc-physical-kloc-v1",
            "hotspot_scope": {
                "status": (
                    "available"
                    if measured_files and len(measured_files) == len(availability)
                    else "partial" if measured_files else "unavailable"
                ),
                "declared_files": len(availability),
                "measured_files": len(measured_files),
                "unavailable_files": [
                    {
                        "file": file,
                        "reason": "Complete measured callable complexity, physical LOC and ranking prerequisites are required.",
                    }
                    for file in sorted(availability)
                    if file not in measured_files
                ],
            },
            "feature_count": len(active_features),
            "active_features": active_features,
            "training_samples": predictor.metrics.training_samples,
            "evaluation_status": predictor.metrics.evaluation_status,
            "evaluation_folds": predictor.metrics.evaluation_folds,
            "fallback_reason": predictor.metrics.fallback_reason,
            "limitations": limitations,
            "f1_score": (
                round(predictor.metrics.f1, 4)
                if predictor.metrics.f1 is not None
                else None
            ),
            "ranking_scope": {
                "version": "file-eligibility-1",
                "declared_files": len(file_risks) + len(unranked),
                "ranked_files": len(file_risks),
                "unranked_files": len(unranked),
            },
        },
        "health_score": {
            "overall": round(health.overall, 2) if health.overall is not None else None,
            "status": health_status,
            "by_category": {
                k: round(v, 2) if v is not None else None
                for k, v in health.by_category.items()
            },
        },
        "file_risks": file_risks,
        "unranked_files": unranked,
        "hotspots": hotspots,
    }
    if behavior is not None:
        from cppulse.component_hotspots import aggregate_component_hotspots

        result["component_hotspots"] = aggregate_component_hotspots(
            behavior=behavior,
            declared_files=availability,
            hotspot_scores=hotspot_scores,
            excluded_files=features_df.attrs.get("component_excluded_files", []),
        )
    return result


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


def run(
    input_dir: Path,
    output_dir: Path,
    profile: str = "default",
    *,
    maintenance_health: dict[str, Any] | None = None,
    source_digest: str | None = None,
) -> None:
    """Execute the full predictor pipeline.

    Args:
        input_dir: Directory containing findings.json and git_metrics.json.
        output_dir: Directory to write risk_scores.json and roadmap.json.
        profile: Analysis profile. "default" excludes MISRA rules,
            "safety-critical" includes them.
        maintenance_health: Existing same-stage normalized analysis decision;
            only prerequisite availability is reused, not its scoring formula.
        source_digest: Selected original source digest of that decision.
    """
    from tempfile import TemporaryDirectory
    import os
    import stat
    from cppulse.errors import IntegrityError
    from .input_projection import open_predictor_inputs

    # Keep candidate outputs private until the original input's final guard
    # succeeds. Use the destination filesystem for the existing per-file replace
    # protocol; this does not promise an atomic two-file publication.
    output_dir = Path(output_dir).absolute()
    for boundary in (output_dir, *output_dir.parents):
        if boundary.is_symlink():
            raise IntegrityError("Predictor output boundary must not follow symlinks")
    if output_dir.exists() and not output_dir.is_dir():
        raise IntegrityError("Predictor output must be an ordinary directory")
    output_dir.mkdir(parents=True, exist_ok=True)
    boundary_identity = (output_dir.stat().st_dev, output_dir.stat().st_ino)
    names = ("risk_scores.json", "roadmap.json")

    def output_guard() -> None:
        """Validate both leaves before any publication; do not follow aliases."""
        info = output_dir.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or (info.st_dev, info.st_ino) != boundary_identity
        ):
            raise IntegrityError("Predictor output directory changed during generation")
        for name in names:
            try:
                leaf = (output_dir / name).lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(leaf.st_mode):
                raise IntegrityError(
                    "Predictor output leaf must remain a regular file: " + name
                )

    output_guard()
    # A mountpoint can have a different device from its parent. Exclusive owned
    # staging inside the validated destination keeps every replace on that device.
    with TemporaryDirectory(prefix=".cppulse-predictor-", dir=output_dir) as scratch:
        stage = Path(scratch) / "output"
        with open_predictor_inputs(
            input_dir / "findings.json", directory=Path(scratch) / "projection"
        ) as inputs:
            qualification = {}
            if maintenance_health is not None:
                qualification["maintenance_health"] = maintenance_health
            if source_digest is not None:
                qualification["source_digest"] = source_digest
            _run_projected(
                input_dir,
                stage,
                profile,
                inputs.findings,
                inputs.measured_hotspot_metrics,
                **qualification,
            )
        # Original-input verification and generation/schema validation have
        # completed, and their handles have closed, before either file is exposed.
        output_guard()
        for name in names:
            if not stat.S_ISREG((stage / name).lstat().st_mode):
                raise IntegrityError("Predictor staged output is not a regular file")
        for name in names:
            os.replace(stage / name, output_dir / name)


def _run_projected(
    input_dir: Path,
    output_dir: Path,
    profile: str,
    findings_data: dict[str, Any],
    measured_hotspot_metrics: dict[str, dict[str, Any]],
    *,
    maintenance_health: dict[str, Any] | None = None,
    source_digest: str | None = None,
) -> None:
    """Consume copied feature inputs while the checked original remains pinned."""
    logger.info("Loading inputs from %s", input_dir)
    git_metrics_data = _load_json(input_dir / "git_metrics.json")
    behavior_path = input_dir / "git_behavior.json"
    behavior = _load_json(behavior_path) if behavior_path.exists() else None
    if behavior is not None:
        from cppulse.git_miner.behavior import validate_behavior_report

        validate_behavior_report(behavior)

    for name, data in [("findings", findings_data), ("git_metrics", git_metrics_data)]:
        schema = load_schema(name, "prototype_v1")
        jsonschema.validate(data, schema)

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Engineering features...")
    engineer = FeatureEngineer()
    features_df = engineer.build_features(
        findings_data,
        git_metrics_data,
        profile=profile,
        maintenance_health=maintenance_health,
        source_digest=source_digest,
    )
    features_df.attrs["measured_hotspot_metrics"] = measured_hotspot_metrics
    logger.info("Feature matrix shape: %s", features_df.shape)

    logger.info("Training bug predictor...")
    predictor = BugPredictor(profile=profile)
    eligibility = features_df.attrs["rank_availability"]
    eligible_mask = (
        features_df["file"].map(lambda file: eligibility[file].eligible).astype(bool)
    )
    training = features_df.loc[eligible_mask].copy()
    label_source = _label_source(training)
    labels = _derive_labels(training, profile=profile)
    predictor.train(training, labels)

    logger.info("Generating predictions...")
    probabilities = predictor.predict(features_df)

    logger.info("Computing health scores...")
    health_scorer = HealthScorer(profile=profile)

    logger.info("Building risk scores output...")
    risk_scores = build_risk_scores(
        features_df, probabilities, predictor, health_scorer, behavior=behavior
    )

    risk_scores["metadata"]["label_source"] = label_source
    szz_mask = _szz_label_mask(training)
    risk_scores["metadata"]["training_label_provenance"] = {
        "kind": "declared_experimental_proxy_labels",
        "training_files": training["file"].tolist(),
        "szz_files": training.loc[szz_mask, "file"].tolist(),
        "feature_derived_files": training.loc[~szz_mask, "file"].tolist(),
    }
    szz_provenance = git_metrics_data.get("metadata", {}).get("szz")
    if isinstance(szz_provenance, dict):
        risk_scores["metadata"]["szz"] = deepcopy(szz_provenance)
    risk_scores["metadata"]["limitations"].extend(
        git_metrics_data.get("metadata", {}).get("limitations", [])
    )
    if label_source in {
        "feature_derived_heuristic",
        "mixed_szz_and_feature_derived_heuristic",
    }:
        risk_scores["metadata"]["limitations"].append(
            "Labels are derived from features; cross-validation is not evidence of future-defect predictive accuracy."
        )
    if label_source == "unavailable":
        risk_scores["metadata"]["limitations"].append(
            "No eligible training labels are available; missing data is not a clean example."
        )

    logger.info("Validating risk_scores.json schema...")
    validator = SchemaValidator()
    validator.validate_risk_scores(risk_scores)

    risk_scores_path = output_dir / "risk_scores.json"
    with risk_scores_path.open("w", encoding="utf-8") as fh:
        json.dump(risk_scores, fh, indent=2)
    logger.info("Wrote %s", risk_scores_path)

    logger.info("Generating refactoring roadmap...")
    eligible = set(features_df["file"])
    scoped_findings = {
        **findings_data,
        "findings": [
            {**entry, "file": relative_identity(entry["file"], findings_data)}
            for entry in findings_data["findings"]
            if relative_identity(entry["file"], findings_data) in eligible
        ],
    }
    scoped_git = {
        **git_metrics_data,
        "knowledge_silos": [
            {**entry, "file": relative_identity(entry["file"], git_metrics_data)}
            for entry in git_metrics_data["knowledge_silos"]
            if relative_identity(entry["file"], git_metrics_data) in eligible
        ],
    }
    roadmap = build_roadmap(scoped_findings, scoped_git, risk_scores, profile)

    logger.info("Validating roadmap.json schema...")
    validator.validate_roadmap(roadmap)

    roadmap_path = output_dir / "roadmap.json"
    with roadmap_path.open("w", encoding="utf-8") as fh:
        json.dump(roadmap, fh, indent=2)
    logger.info("Wrote %s", roadmap_path)

    overall = risk_scores["health_score"]["overall"]
    logger.info("Pipeline complete. Overall health score: %s/100", overall)


def _predictor_settings(config_path: Path) -> dict[str, Any]:
    """Read and validate one explicit component configuration exactly once."""
    from cppulse.config import read_settings
    from cppulse.errors import ContractError

    settings = read_settings(config_path)
    if "ruleset" in settings or "execution" in settings or "history" in settings:
        raise ContractError(
            "Predictor component needs resolved native settings; use cppulse config --native-output"
        )
    return settings


def _load_profile_from_config(config_path: Path) -> str:
    """Extract the profile setting from a .cppulserc.yml/.json config file.

    Args:
        config_path: Path to the config file.

    Returns:
        Profile string ("default" or "safety-critical").
    """
    return _predictor_settings(config_path).get("profile", "default")


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
        default=None,
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
    profile = args.profile or "default"
    retained = None
    if args.config is not None:
        from cppulse.errors import ContractError
        from cppulse.identities import digest_json

        # Validate even when an explicit profile is supplied, before prediction.
        settings = _predictor_settings(args.config)
        config_profile = settings.get("profile", "default")
        profile = args.profile or config_profile
        identity_path = args.config.with_name(args.config.name + ".identity.json")
        retained = {
            "settings": deepcopy(settings),
            "profile_source": "config",
            "limitations": [
                "Retained component configuration; no Docker execution or complete environment claim."
            ],
        }
        if identity_path.is_file():
            retained = json.loads(identity_path.read_bytes())
            if retained.get("settings") != settings:
                raise ContractError(
                    "Configuration identity sidecar does not match native settings"
                )
        retained["settings"]["profile"] = profile
        if args.profile is not None:
            retained["profile_source"] = "command"
            if retained.get("ruleset") is not None:
                identity = retained["ruleset"]
                identity["effective_native"] = deepcopy(retained["settings"])
                identity["profile_source"] = "command"
                identity["origins"]["native.profile"] = "command"
                identity.pop("digest", None)
                identity["digest"] = digest_json(identity)
    run(input_dir=args.input, output_dir=args.output, profile=profile)
    if retained is not None:
        (args.output / "effective_config.json").write_text(
            json.dumps(retained, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()
