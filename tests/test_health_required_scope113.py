"""Required-analysis health controls, starting with a genuine native producer."""
from __future__ import annotations

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest
import cppulse

from cppulse.analysis_execution import run_analysis
from cppulse.config import effective_config
from cppulse.native import NativeInstallation
from cppulse.predictor.feature_engineer import FeatureEngineer
from cppulse.predictor.health_scorer import HealthScorer
from cppulse.predictor.main import build_risk_scores
from cppulse.predictor.model import BugPredictor
from cppulse.run_store import RunStore
from cppulse.workflows import read_documents


@pytest.fixture(autouse=True)
def exact_installed_package_when_requested():
    """Installed qualification may never fall back to this checkout's package."""
    selected = os.environ.get("CPPULSE_HEALTH_EXPECT_PREFIX113")
    if selected is not None:
        assert Path(cppulse.__file__).resolve().parent == Path(selected).resolve() / "cppulse"


def public_health(document, *, profile="default", maintenance_health=None, source_digest=None):
    """Real feature/scorer consumer; classifier calibration is not this control."""
    history = {"metadata": {"repo_path": document["metadata"]["repo_path"]},
               "file_metrics": [], "knowledge_silos": []}
    frame = FeatureEngineer().build_features(
        document, history, profile=profile, maintenance_health=maintenance_health,
        source_digest=source_digest,
    )
    model = BugPredictor(profile=profile)
    model.train(frame, pd.Series([0] * len(frame), dtype=int))
    return build_risk_scores(frame, model.predict(frame), model,
                             HealthScorer(profile=profile))


def test_actual_current_nonempty_missing_required_rule_is_not_full_health(tmp_path):
    """Disabling one required detector cannot turn zero findings into health100."""
    binary = Path(os.environ["CPPULSE_WORK_UNIT_NATIVE"])
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == (
        "1a34a3ad2a344728af729ec6d54c0277e01bac9503435e7462982d06f45d17c1")
    resource = Path(os.environ["CPPULSE_CLANG_RESOURCE_DIR"])
    repo = tmp_path / "source"
    repo.mkdir()
    source = repo / "plain.cpp"
    source.write_text("int plain(int input) { return input; }\n")
    (repo / "compile_commands.json").write_text(json.dumps([{
        "directory": str(repo), "file": str(source),
        "arguments": ["clang++", "-std=c++17", "-c", str(source)],
    }]))
    config = effective_config(repo, tmp_path / "store", execution={"mode": "bounded", "jobs": 1})
    config.settings["rules"] = {"CPP-MEM-001": {"enabled": False}}
    native = NativeInstallation(binary, resource, (), None)
    result = run_analysis(config, native, tmp_path / "native-work", timeout=60)
    document = json.loads(result.report_path.read_bytes())
    analysis = document["metadata"]["analysis"]
    assert analysis["enabled_rules"] and "CPP-MEM-001" not in analysis["enabled_rules"]
    assert all(row["status"] == "analyzed" and row["error_count"] == 0 for row in analysis["files"])
    risk = public_health(document)
    (tmp_path / "observed-risk.json").write_text(json.dumps(risk, indent=2) + "\n")
    assert risk["health_score"]["overall"] is None
    assert risk["health_score"]["status"] == "partial"


def pipeline_case(tmp_path, monkeypatch, *, profile="default", disabled=None,
                  database=True, broken=False):
    """Real pipeline, original native receipts and same-stage normalized health."""
    from cppulse.pipeline import analyze

    binary = Path(os.environ["CPPULSE_WORK_UNIT_NATIVE"])
    assert hashlib.sha256(binary.read_bytes()).hexdigest() == (
        "1a34a3ad2a344728af729ec6d54c0277e01bac9503435e7462982d06f45d17c1")
    resource = Path(os.environ["CPPULSE_CLANG_RESOURCE_DIR"])
    native = NativeInstallation(binary, resource, (), None)
    monkeypatch.setattr("cppulse.pipeline.discover_native", lambda: native)
    repo = tmp_path / "source"
    repo.mkdir()
    source = repo / "plain.cpp"
    source.write_text("void broken( {\n" if broken else
                      "#include <__stddef_size_t.h>\nvoid plain() {}\n")
    if database:
        (repo / "compile_commands.json").write_text(json.dumps([{
            "directory": str(repo), "file": str(source),
            "arguments": ["clang++", "-std=c++17", "-c", str(source)],
        }]))
    config = effective_config(repo, tmp_path / "store", profile=profile,
        history={"enabled": False}, execution={"mode": "bounded", "jobs": 1,
            "work_directory": str(tmp_path / "native-work")})
    if disabled:
        config.settings["rules"] = {disabled: {"enabled": False}}
    analyze(config, report_format="json", timeout=60)
    snapshot = RunStore.open_existing(config.output).resolve_latest_attempt()
    snapshot.verify()
    documents = read_documents(snapshot)
    risk = (json.loads(snapshot.read_bytes("risk_scores"))
            if any(row["id"] == "risk_scores" for row in snapshot.manifest["artifacts"])
            else None)
    return snapshot, documents, risk


@pytest.mark.parametrize("profile", ["default", "safety-critical"])
def test_actual_typed_complete_clean_analysis_retains_health100(tmp_path, monkeypatch, profile):
    _, documents, risk = pipeline_case(tmp_path, monkeypatch, profile=profile)
    assert risk is not None
    health = next(row for row in documents["maintenance_health"]
                  if not row["scorer"]["allow_inferred_parse"])
    assert health["aggregate"]["availability"] == "scored"
    assert health["aggregate"]["overall"] == 100
    assert risk["health_score"]["status"] == "scored"
    assert risk["health_score"]["overall"] == 100
    assert risk["metadata"]["score_model"] == "weighted-findings-per-attempted-file-v2"


@pytest.mark.parametrize("profile,disabled,available", [
    ("default", "CPP-MEM-001", False),
    ("default", "MISRA-001", True),
    ("safety-critical", "MISRA-001", False),
])
def test_actual_profile_required_rule_omissions(tmp_path, monkeypatch, profile, disabled, available):
    _, documents, risk = pipeline_case(tmp_path, monkeypatch, profile=profile, disabled=disabled)
    assert risk is not None
    health = next(row for row in documents["maintenance_health"]
                  if not row["scorer"]["allow_inferred_parse"])
    if available:
        assert risk["health_score"]["overall"] == health["aggregate"]["overall"] == 100
    else:
        assert health["aggregate"]["overall"] is None
        assert risk["health_score"]["overall"] is None
        assert risk["health_score"]["status"] == "partial"


@pytest.mark.parametrize("database,broken", [(False, False), (True, True)])
def test_actual_fallback_or_failed_parse_cannot_qualify_health(tmp_path, monkeypatch, database, broken):
    _, documents, risk = pipeline_case(tmp_path, monkeypatch, database=database, broken=broken)
    assert all(row["aggregate"]["overall"] is None for row in documents.get("maintenance_health", []))
    rows = [row for document in documents["analysis_inventory"] for row in document["items"]]
    assert rows
    if broken:
        assert any(row["status"] != "analyzed" for row in rows)
    else:
        assert any(row["context_source"] == "fallback" for row in rows)
    if risk is not None:
        assert risk["health_score"]["overall"] is None
        assert risk["health_score"]["status"] in {"partial", "no_data"}


def test_required_context_metrics_and_input_gaps_use_original_v4_decision(tmp_path, monkeypatch):
    """Authored evidence-selection negatives; original producer facts stay intact."""
    from cppulse.maintenance import compute_maintenance_health
    from cppulse.tooling import load_rule_registry

    snapshot, documents, risk = pipeline_case(tmp_path, monkeypatch)
    assert risk is not None
    assert risk["health_score"]["overall"] == 100
    original = json.loads(snapshot.read_bytes("findings"))
    good = next(row for row in documents["maintenance_health"]
                if not row["scorer"]["allow_inferred_parse"])
    base = {"source_digest": good["source_digest"],
            "inventories": documents["analysis_inventory"],
            "metrics": documents["analysis_metrics"],
            "observations": documents["observations"],
            "registry": load_rule_registry(),
            "required_context_ids": good["required_context_ids"],
            "expected_scopes": documents["analysis_scope"]}
    for gap in ["missing-required-context", "metric", "input"]:
        inputs = deepcopy(base)
        if gap == "missing-required-context":
            inputs["optional_context_ids"] = inputs["required_context_ids"]
            inputs["required_context_ids"] = ["unobserved-required-context"]
        elif gap == "metric":
            inputs["metrics"] = []
        else:
            inputs["expected_scopes"][0]["input_verification"] = "unavailable"
        incomplete = compute_maintenance_health(**inputs)
        assert incomplete["aggregate"]["overall"] is None
        selected = public_health(original, maintenance_health=incomplete,
                                 source_digest=good["source_digest"])
        assert selected["health_score"]["overall"] is None, gap
        assert selected["health_score"]["status"] == "partial", gap
    for profile, digest in [("default", "0" * 64), ("safety-critical", good["source_digest"])]:
        selected = public_health(original, profile=profile, maintenance_health=good,
                                 source_digest=digest)
        assert selected["health_score"]["overall"] is None


def test_bare_calibration_frame_is_not_published_as_full_scope_health():
    columns = {"file": ["plain.cpp"], "finding_count": [0], "memory_findings": [0],
               "complexity_findings": [0], "modernization_findings": [0], "misra_findings": [0],
               "max_severity": [0], "change_frequency": [0], "unique_contributors": [0],
               "churn_rate": [0], "bug_fix_commits": [0], "szz_bug_introductions": [0],
               "age_days": [0], "is_knowledge_silo": [0]}
    frame = pd.DataFrame(columns)
    scorer = HealthScorer()
    assert scorer.compute(frame).overall == 100  # Historical math-only API.
    model = BugPredictor()
    model.train(frame, pd.Series([0]))
    result = build_risk_scores(frame, model.predict(frame), model, scorer)
    assert result["health_score"]["overall"] is None
    assert result["health_score"]["status"] == "partial"


def test_empty_frame_has_no_numeric_health():
    document = {"metadata": {"repo_path": "/authored-empty-input", "analysis": {
        "enabled_rules": [], "files": []}}, "findings": []}
    result = public_health(document)
    assert result["health_score"]["overall"] is None
    assert result["health_score"]["status"] == "no_data"

