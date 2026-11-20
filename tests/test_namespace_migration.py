"""Installed namespace and checkout-only compatibility entry-point contracts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def execute(
    code: str, cwd: Path, package_path: Path | None = None
) -> subprocess.CompletedProcess[str]:
    """Run an isolated import journey without leaking legacy src modules."""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(package_path or ROOT / "python")
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.mark.parametrize(
    "component, namespace, module",
    [
        ("git-miner", "git_miner", "main"),
        ("git-miner", "git_miner", "miner"),
        ("git-miner", "git_miner", "schema_validator"),
        ("predictor", "predictor", "main"),
        ("predictor", "predictor", "model"),
        ("predictor", "predictor", "schema_validator"),
    ],
)
def test_legacy_and_canonical_imports_share_module_identity(
    component: str, namespace: str, module: str
) -> None:
    """Monkeypatching a legacy import must affect the canonical implementation."""
    execute(
        f"""
import importlib
legacy = importlib.import_module("src.{module}")
canonical = importlib.import_module("cppulse.{namespace}.{module}")
assert legacy is canonical
legacy.synthetic_identity_marker = object()
assert canonical.synthetic_identity_marker is legacy.synthetic_identity_marker
""",
        ROOT / component,
    )


@pytest.mark.parametrize("component", ["git-miner", "predictor"])
def test_legacy_module_cli_bootstraps_only_known_checkout(component: str) -> None:
    """The existing python -m src.main command works without an installed wheel."""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-m", "src.main", "--help"],
        cwd=ROOT / component,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "--output" in result.stdout


def test_canonical_components_import_together_without_src(tmp_path: Path) -> None:
    """Distinct installed namespaces eliminate the former src name collision."""
    execute(
        """
import sys
import cppulse.git_miner.main
import cppulse.predictor.main
assert "src" not in sys.modules
assert cppulse.git_miner.main.run is not cppulse.predictor.main.run
""",
        tmp_path,
    )


def test_packaged_schemas_and_pipeline_do_not_need_checkout_docs(
    tmp_path: Path,
) -> None:
    """A copied package tree has all resources required outside the checkout."""
    package = tmp_path / "installation"
    shutil.copytree(
        ROOT / "python/cppulse",
        package / "cppulse",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    inputs = tmp_path / "input"
    inputs.mkdir()
    findings = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/synthetic",
            "analyzed_at": "2026-11-13T10:00:00Z",
            "file_count": 1,
            "total_loc": 1,
            "analysis": {
                "enabled_rules": ["CPP-MOD-001"],
                "files": [
                    {
                        "path": "/synthetic/clean.cpp",
                        "status": "analyzed",
                        "compile_context": "fallback",
                        "error_count": 0,
                    }
                ],
            },
        },
        "findings": [],
        "summary": {"total_findings": 0, "by_category": {}, "by_severity": {}},
    }
    metrics = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/synthetic",
            "analyzed_at": "2026-11-13T10:00:00Z",
            "commit_range": "N/A",
            "total_commits": 0,
            "history_status": "unavailable",
            "limitations": ["Synthetic no-history case"],
        },
        "file_metrics": [],
        "knowledge_silos": [],
    }
    (inputs / "findings.json").write_text(json.dumps(findings))
    (inputs / "git_metrics.json").write_text(json.dumps(metrics))
    execute(
        """
from pathlib import Path
import json, jsonschema
from cppulse.git_miner.schema_validator import SchemaValidator as GitValidator
from cppulse.predictor.schema_validator import SchemaValidator as PredictionValidator
from cppulse.predictor.main import run
try:
    GitValidator().validate({})
except jsonschema.ValidationError:
    pass
else:
    raise AssertionError("Expected original validation error type")
try:
    PredictionValidator().validate_risk_scores({})
except jsonschema.ValidationError:
    pass
else:
    raise AssertionError("Expected original validation error type")
run(Path("input"), Path("output"))
result = json.loads(Path("output/risk_scores.json").read_text())
assert result["metadata"]["model_type"] == "heuristic"
assert result["file_risks"] == []
assert result["unranked_files"][0]["file"] == "clean.cpp"
assert "missing_history" in result["unranked_files"][0]["reason_codes"]
""",
        tmp_path,
        package,
    )


@pytest.mark.parametrize("missing", ["sklearn", "xgboost"])
def test_missing_optional_ml_backend_uses_explicit_heuristic(
    tmp_path: Path, missing: str
) -> None:
    """A headless installation can rank without either optional ML backend."""
    execute(
        f"""
import importlib.abc
import sys
class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "{missing}" or fullname.startswith("{missing}."):
            raise ModuleNotFoundError("Synthetic missing optional backend")
sys.meta_path.insert(0, BlockOptional())
import numpy as np
import pandas as pd
from cppulse.predictor.model import BugPredictor, NUMERIC_FEATURES
features = pd.DataFrame([{{name: 1 for name in NUMERIC_FEATURES}} for _ in range(60)])
model = BugPredictor()
metrics = model.train(features, pd.Series([0, 1] * 30))
assert model.use_heuristic
assert metrics.fallback_reason == "backend_unavailable"
assert metrics.evaluation_status == "not_evaluated"
assert metrics.f1 is None
assert np.isfinite(model.predict(features)).all()
assert len(model.explain(features)) == 60
""",
        tmp_path,
    )


def test_explicit_schema_overrides_keep_validation_error_type(tmp_path: Path) -> None:
    """Custom schemas remain explicit filesystem overrides in both components."""
    custom = {"type": "object", "required": ["custom"]}
    for filename in [
        "git_metrics.schema.json",
        "risk_scores.schema.json",
        "roadmap.schema.json",
    ]:
        (tmp_path / filename).write_text(json.dumps(custom))
    execute(
        """
from pathlib import Path
import jsonschema
from cppulse.git_miner.schema_validator import SchemaValidator as GitValidator
from cppulse.predictor.schema_validator import SchemaValidator as PredictionValidator
checks = [GitValidator(Path("git_metrics.schema.json")).validate,
          PredictionValidator(Path(".")).validate_risk_scores,
          PredictionValidator(Path(".")).validate_roadmap]
for validate in checks:
    validate({"custom": True})
    try:
        validate({})
    except jsonschema.ValidationError:
        pass
    else:
        raise AssertionError("Custom schema was ignored")
""",
        tmp_path,
    )


def test_optional_shap_native_load_failure_is_nonfatal(tmp_path: Path) -> None:
    """A missing native explanation library must not break heuristic ranking."""
    execute(
        """
import importlib.abc
import sys
class BlockShap(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "shap" or fullname.startswith("shap."):
            raise OSError("Synthetic unavailable SHAP native library")
sys.meta_path.insert(0, BlockShap())
import pandas as pd
from cppulse.predictor import model
features = pd.DataFrame([{name: 0 for name in model.NUMERIC_FEATURES} for _ in range(3)])
ranker = model.BugPredictor()
ranker.train(features, pd.Series([0, 1, 0]))
assert not model._HAS_SHAP
assert ranker.use_heuristic
assert len(ranker.explain(features)) == 3
""",
        tmp_path,
    )
