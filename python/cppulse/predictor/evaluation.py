"""Private, cutoff-frozen retrospective evaluation of optional risk ranking.

Observed labels and feature availability are caller claims, not authenticated
corpus provenance. A measured Brier score does not establish calibrated future
C++ defect probability, nor qualify the existing production predictor model.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from importlib import resources
import json
import math
import os
import stat
from pathlib import Path
import platform
import sys
from typing import Any

import jsonschema

from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes, digest_json

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_REPORT_BYTES = 32 * 1024 * 1024


def _schema(name: str) -> dict[str, Any]:
    return json.loads(
        resources.files("cppulse.contracts")
        .joinpath("schemas", "risk_evaluation_private", name + ".schema.json")
        .read_bytes()
    )


def _time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Timestamp requires timezone")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ContractError(
            "Evaluation timestamps must be explicit timezone-aware ISO dates"
        ) from exc


def _finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except (ValueError, OverflowError):
        return False


def validate_input(document: dict[str, Any]) -> None:
    """Validate finite observations and reject features unavailable at prediction.

    Training availability is enforced separately when selecting labels. Label
    semantics themselves require independent corpus review.
    """
    try:
        jsonschema.Draft7Validator(
            _schema("input"), format_checker=jsonschema.FormatChecker()
        ).validate(document)
        if len(canonical_json_bytes(document)) > MAX_INPUT_BYTES:
            raise ContractError("Evaluation input exceeds the 8 MiB bound")
    except (jsonschema.ValidationError, ValueError, TypeError) as exc:
        raise ContractError("Invalid risk-evaluation input: " + str(exc)) from exc
    training = _time(document["training_cutoff"])
    evaluation = _time(document["evaluation_cutoff"])
    if evaluation <= training:
        raise ContractError("Evaluation cutoff must be later than training cutoff")
    names = set(document["feature_names"])
    if document["ranking_feature"] not in names:
        raise ContractError("Ranking feature must be one frozen input feature")
    seen = set()
    for row in document["observations"]:
        if row["id"] in seen:
            raise ContractError("Observation IDs must be unique")
        seen.add(row["id"])
        prediction = _time(row["prediction_at"])
        if _time(row["features_available_at"]) > prediction:
            raise ContractError(
                "Future features cannot be used at an earlier prediction time"
            )
        if set(row["features"]) != names or any(
            not _finite_number(value) for value in row["features"].values()
        ):
            raise ContractError(
                "Each frozen observation requires exactly the finite numeric features"
            )
        if (row["label"] is None) != (row["label_available_at"] is None):
            raise ContractError(
                "Unavailable labels require null label and availability together"
            )
        if isinstance(row["label"], bool):
            raise ContractError(
                "Labels must be integer binary outcomes, never booleans"
            )
        if row["label_available_at"] is not None:
            try:
                horizon_end = prediction + timedelta(
                    days=document["prediction_horizon_days"]
                )
            except OverflowError as exc:
                raise ContractError(
                    "Forecast horizon exceeds supported timestamp range"
                ) from exc
            if _time(row["label_available_at"]) < horizon_end:
                raise ContractError(
                    "Label availability cannot precede the complete declared forecast horizon"
                )


def _unavailable(reason: str) -> dict[str, Any]:
    return {"status": "unavailable", "reason": reason}


def _metrics(
    labels: list[int], scores: list[float], *, probability: bool
) -> dict[str, Any]:
    positives, count = sum(labels), len(labels)
    pairs = sorted(zip(scores, labels), reverse=True)
    groups: dict[float, list[int]] = {}
    for score, label in pairs:
        groups.setdefault(score, []).append(label)
    true_seen = false_seen = 0
    average_precision = concordant = 0.0
    for group in groups.values():
        true_group = sum(group)
        false_group = len(group) - true_group
        true_seen += true_group
        false_seen += false_group
        if positives:
            average_precision += (
                (true_group / positives) * true_seen / (true_seen + false_seen)
            )
        # Descending scores: these positives outrank every remaining negative.
        concordant += (
            true_group * (count - positives - false_seen)
            + 0.5 * true_group * false_group
        )
    has_both = 0 < positives < count
    precision = recall = f1 = None
    if probability:
        predictions = [int(score >= 0.5) for score in scores]
        tp = sum(
            label == prediction == 1 for label, prediction in zip(labels, predictions)
        )
        predicted_positives = sum(predictions)
        precision = tp / predicted_positives if predicted_positives else 0.0
        recall = tp / positives if positives else 0.0
        f1 = (
            2 * precision * recall / (precision + recall) if precision + recall else 0.0
        )
    bins = None
    if probability:
        bins = []
        for index in range(10):
            selected = [
                (score, label)
                for score, label in zip(scores, labels)
                if min(9, int(score * 10)) == index
            ]
            bins.append(
                {
                    "lower": index / 10,
                    "upper": (index + 1) / 10,
                    "count": len(selected),
                    "mean_probability": (
                        sum(score for score, _ in selected) / len(selected)
                        if selected
                        else None
                    ),
                    "observed_rate": (
                        sum(label for _, label in selected) / len(selected)
                        if selected
                        else None
                    ),
                }
            )
    top_k = max(1, math.ceil(0.2 * count))
    remaining = top_k
    top_positives = 0.0
    for group in groups.values():
        take = min(remaining, len(group))
        top_positives += take * sum(group) / len(group)
        remaining -= take
        if not remaining:
            break
    return {
        "status": "evaluated",
        "reason": None,
        "score_kind": "probability" if probability else "ranking",
        "sample_count": count,
        "positive_count": positives,
        "prevalence": positives / count,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "roc_auc": concordant / (positives * (count - positives)) if has_both else None,
        "average_precision": average_precision if has_both else None,
        "ranking_reason": None if has_both else "single_class_test_labels",
        "top_k": top_k,
        "precision_at_k": top_positives / top_k,
        "brier_score": (
            sum((score - label) ** 2 for score, label in zip(scores, labels)) / count
            if probability
            else None
        ),
        "reliability": bins,
        "probability_interpretation": (
            "Observed forecast losses only; no calibrated defect-risk claim."
            if probability
            else None
        ),
    }


def evaluate(document: dict[str, Any]) -> dict[str, Any]:
    """Fit a train-only optional logistic model and compare frozen holdouts.

    No project command, subprocess, remote model or corpus download is invoked.
    The chronological and held-out-project partitions never contribute labels,
    scaler statistics or fitted parameters to training.
    """
    validate_input(document)
    cutoff = _time(document["training_cutoff"])
    evaluation = _time(document["evaluation_cutoff"])
    heldout = set(document["holdout_projects"])
    train: list[dict[str, Any]] = []
    partitions: dict[str, list[dict[str, Any]]] = {
        "chronological": [],
        "project_holdout": [],
    }
    excluded: dict[str, str] = {}
    for row in sorted(
        document["observations"],
        key=lambda row: (_time(row["prediction_at"]), row["id"]),
    ):
        prediction = _time(row["prediction_at"])
        available = (
            _time(row["label_available_at"]) if row["label_available_at"] else None
        )
        reason = None
        if prediction > evaluation:
            reason = "prediction_after_evaluation_cutoff"
        elif prediction <= cutoff:
            if row["project"] in heldout:
                reason = "heldout_before_training_cutoff"
            elif available is None or available > cutoff:
                reason = "training_label_unavailable_at_cutoff"
            else:
                train.append(row)
        elif available is None or available > evaluation:
            reason = "evaluation_label_unavailable_at_cutoff"
        else:
            partitions[
                "project_holdout" if row["project"] in heldout else "chronological"
            ].append(row)
        if reason:
            excluded[row["id"]] = reason
    names = list(document["feature_names"])

    def matrix(rows: list[dict[str, Any]]) -> list[list[float]]:
        return [[row["features"][name] for name in names] for row in rows]

    model = None
    model_reason = "no_training_labels" if not train else "single_class_training_labels"
    backend_version = None
    if len({row["label"] for row in train}) == 2:
        try:
            import sklearn
            from sklearn.linear_model import LogisticRegression
            from sklearn.pipeline import make_pipeline
            from sklearn.preprocessing import StandardScaler

            backend_version = sklearn.__version__
            model = make_pipeline(
                StandardScaler(),
                LogisticRegression(solver="liblinear", random_state=0, max_iter=1000),
            )
            model.fit(matrix(train), [row["label"] for row in train])
            if model[-1].n_iter_[0] >= 1000:
                model = None
                model_reason = "training_did_not_converge"
        except (ImportError, OSError, AttributeError) as exc:
            model_reason = "optional_ml_backend_unavailable:" + type(exc).__name__
        except (ValueError, RuntimeError, ArithmeticError) as exc:
            model_reason = "training_failed:" + type(exc).__name__
    results = {}
    for name, rows in partitions.items():
        if not rows:
            results[name] = {
                "status": "unavailable",
                "reason": "no_available_test_labels",
                "sample_count": 0,
                "sample_ids": [],
                "models": {},
            }
            continue
        labels = [row["label"] for row in rows]
        baseline = sum(row["label"] for row in train) / len(train) if train else None
        models = {
            "zero": _metrics(labels, [0.0] * len(rows), probability=True),
            "training_base_rate": (
                _metrics(labels, [baseline] * len(rows), probability=True)
                if baseline is not None
                else _unavailable("no_training_labels")
            ),
            "feature_ranking": _metrics(
                labels,
                [row["features"][document["ranking_feature"]] for row in rows],
                probability=False,
            ),
            "logistic": _unavailable(model_reason),
        }
        if model is not None:
            try:
                scores = [float(row[1]) for row in model.predict_proba(matrix(rows))]
                if any(
                    not math.isfinite(score) or not 0 <= score <= 1 for score in scores
                ):
                    raise ValueError("Non-finite probability")
                models["logistic"] = _metrics(labels, scores, probability=True)
            except (ValueError, RuntimeError, ArithmeticError) as exc:
                models["logistic"] = _unavailable(
                    "prediction_failed:" + type(exc).__name__
                )
        results[name] = {
            "status": "evaluated",
            "reason": None,
            "sample_count": len(rows),
            "sample_ids": [row["id"] for row in rows],
            "models": models,
        }
    report = {
        "version": "1.0.0",
        "protocol": "private-retrospective-risk-evaluation",
        "status": (
            "evaluated"
            if any(rows for rows in partitions.values())
            else "not_evaluable"
        ),
        "input_sha256": digest_json(document),
        "training_cutoff": document["training_cutoff"],
        "evaluation_cutoff": document["evaluation_cutoff"],
        "label_definition": document["label_definition"],
        "prediction_horizon_days": document["prediction_horizon_days"],
        "feature_names": names,
        "ranking_feature": document["ranking_feature"],
        "holdout_projects": list(document["holdout_projects"]),
        "training": {
            "sample_count": len(train),
            "positive_count": sum(row["label"] for row in train),
            "sample_ids": [row["id"] for row in train],
            "projects": sorted({row["project"] for row in train}),
        },
        "partitions": results,
        "excluded": excluded,
        "model": {
            "name": "train-only-standardized-logistic-v1",
            "backend_version": backend_version,
            "python_version": platform.python_version(),
            "parameters": {
                "solver": "liblinear",
                "random_state": 0,
                "max_iter": 1000,
                "C": 1.0,
            },
        },
        "limitations": [
            "Feature and label availability are caller-supplied and not authenticated.",
            "This retrospective evaluation does not validate corpus labels or causal defect claims.",
            "Brier and reliability measurements do not establish calibrated future C++ defect probability.",
            "This optional model is separate from the existing production risk scorer; no model was silently replaced.",
            "Ranking metrics group score ties; precision_at_k uses expected tie-group prevalence, without label-based ordering.",
        ],
    }
    validate_report(report)
    encoded = canonical_json_bytes(report)
    if len(encoded) > MAX_REPORT_BYTES:
        raise ContractError("Risk-evaluation report exceeds finite output limit")
    return report


def validate_report(report: dict[str, Any]) -> None:
    """Validate the private report contract before publishing measured results."""
    try:
        jsonschema.Draft7Validator(
            _schema("report"), format_checker=jsonschema.FormatChecker()
        ).validate(report)
        canonical_json_bytes(report)
    except (jsonschema.ValidationError, ValueError, TypeError) as exc:
        raise ContractError("Invalid evaluation report: " + str(exc)) from exc
    training = report["training"]
    if (
        training["sample_count"] != len(training["sample_ids"])
        or training["positive_count"] > training["sample_count"]
    ):
        raise ContractError("Training counts differ from selected labels")
    seen = set(training["sample_ids"])
    for partition in report["partitions"].values():
        if partition["sample_count"] != len(partition["sample_ids"]):
            raise ContractError("Evaluation partition count differs from selected IDs")
        if seen.intersection(partition["sample_ids"]):
            raise ContractError("Training and test partitions must be disjoint")
        seen.update(partition["sample_ids"])
        if partition["status"] == "evaluated":
            if not partition["sample_count"] or set(partition["models"]) != {
                "zero",
                "training_base_rate",
                "feature_ranking",
                "logistic",
            }:
                raise ContractError(
                    "Evaluated partitions require all baseline and candidate results"
                )
        elif partition["sample_count"] or partition["models"]:
            raise ContractError(
                "Unavailable partitions cannot present evaluated results"
            )
        for metric in partition["models"].values():
            if metric["status"] == "evaluated":
                if (
                    metric["sample_count"] != partition["sample_count"]
                    or metric["positive_count"] > metric["sample_count"]
                ):
                    raise ContractError(
                        "Metric counts differ from selected evaluation labels"
                    )
                if metric["score_kind"] == "probability" and (
                    metric["brier_score"] is None
                    or metric["reliability"] is None
                    or sum(row["count"] for row in metric["reliability"])
                    != metric["sample_count"]
                ):
                    raise ContractError(
                        "Probability losses require complete reliability counts"
                    )
            if (
                metric["status"] == "evaluated"
                and metric["score_kind"] == "ranking"
                and (
                    metric["brier_score"] is not None
                    or metric["reliability"] is not None
                )
            ):
                raise ContractError(
                    "Ranking outputs cannot claim probability calibration"
                )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    selected: dict[str, Any] = {}
    for key, value in pairs:
        if key in selected:
            raise ContractError("Duplicate JSON keys are ambiguous evaluation inputs")
        selected[key] = value
    return selected


def _reject_constant(value: str) -> None:
    raise ContractError("Non-finite JSON token: " + value)


def main(argv: list[str] | None = None) -> int:
    """Evaluate one finite local JSON input; atomically write its report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        descriptor = os.open(
            args.input,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_INPUT_BYTES:
                raise ContractError(
                    "Evaluation input must be a finite regular JSON file within 8 MiB"
                )
            raw = stream.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ContractError("Input exceeds finite 8 MiB bound")
        document = json.loads(
            raw, parse_constant=_reject_constant, object_pairs_hook=_unique_object
        )
        report = evaluate(document)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_name(args.output.name + ".tmp")
        if args.output.is_symlink() or temporary.is_symlink():
            raise ContractError("Evaluation output paths cannot be symlinks")
        with temporary.open("xb") as stream:
            stream.write(canonical_json_bytes(report))
        temporary.replace(args.output)
        return 0
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        print("Risk evaluation failed: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
