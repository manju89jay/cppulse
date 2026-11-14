"""Regressions for observed source scope and unavailable full-scope health."""

from __future__ import annotations

from pathlib import Path
import json

import pytest
from src.feature_engineer import FeatureEngineer
from src.main import run


def scoped_documents() -> tuple[dict, dict]:
    """A clean untracked file and an excluded history-only source."""
    findings = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/repo",
            "analyzed_at": "2026-11-13T10:00:00Z",
            "file_count": 1,
            "total_loc": 1,
            "analysis": {
                "enabled_rules": ["CPP-MOD-001"],
                "files": [
                    {
                        "path": "/repo/clean.cpp",
                        "status": "analyzed",
                        "compile_context": "fallback",
                        "error_count": 0,
                    },
                    {
                        "path": "/repo/vendor/old.cpp",
                        "status": "excluded",
                        "compile_context": "none",
                        "error_count": 0,
                    },
                ],
            },
        },
        "findings": [],
        "summary": {"total_findings": 0, "by_category": {}, "by_severity": {}},
    }
    metrics = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": "/repo",
            "analyzed_at": "2026-11-13T10:00:00Z",
            "commit_range": "N/A",
            "total_commits": 0,
            "history_status": "unavailable",
        },
        "file_metrics": [
            {
                "file": "vendor/old.cpp",
                "change_frequency": 1,
                "unique_contributors": 1,
                "age_days": 1,
                "lines_of_code": 1,
            }
        ],
        "knowledge_silos": [
            {
                "file": "vendor/old.cpp",
                "sole_contributor": "automation",
                "last_commit_date": "2026-11-13",
            }
        ],
    }
    return findings, metrics


def test_declared_scope_includes_clean_untracked_and_excludes_history() -> None:
    findings, metrics = scoped_documents()
    result = FeatureEngineer().build_features(findings, metrics)
    assert result["file"].tolist() == ["clean.cpp"]
    assert result.iloc[0]["is_knowledge_silo"] == 0


@pytest.mark.parametrize("status", ["partial", "failed", "skipped"])
def test_incomplete_analysis_cannot_receive_full_health(
    tmp_path: Path, status: str
) -> None:
    findings, metrics = scoped_documents()
    findings["metadata"]["analysis"]["files"][0]["status"] = status
    for name, data in [("findings", findings), ("git_metrics", metrics)]:
        (tmp_path / f"{name}.json").write_text(json.dumps(data))
    run(tmp_path, tmp_path)
    result = json.loads((tmp_path / "risk_scores.json").read_text())
    assert result["health_score"]["overall"] is None
    assert result["health_score"]["status"] == "partial"
    assert result["metadata"]["evaluation_status"] == "not_evaluated"
    assert result["metadata"]["limitations"]
    roadmap = json.loads((tmp_path / "roadmap.json").read_text())
    assert all(item["file"] != "vendor/old.cpp" for item in roadmap["items"])


def test_no_enabled_detectors_has_unavailable_health(tmp_path: Path) -> None:
    findings, metrics = scoped_documents()
    findings["metadata"]["analysis"]["enabled_rules"] = []
    for name, data in [("findings", findings), ("git_metrics", metrics)]:
        (tmp_path / f"{name}.json").write_text(json.dumps(data))
    run(tmp_path, tmp_path)
    result = json.loads((tmp_path / "risk_scores.json").read_text())
    assert result["health_score"]["overall"] is None
    assert result["health_score"]["status"] == "partial"


def test_repository_basename_in_relative_identity_is_preserved() -> None:
    findings, metrics = scoped_documents()
    findings["metadata"]["repo_path"] = "project"
    findings["metadata"]["analysis"]["files"] = [
        {
            "path": "project/project/a.cpp",
            "status": "analyzed",
            "compile_context": "fallback",
            "error_count": 0,
        }
    ]
    findings["findings"] = [
        {"file": "project/a.cpp", "category": "modernization", "severity": "warning"}
    ]
    metrics["metadata"]["repo_path"] = "project"
    metrics["file_metrics"] = [{"file": "project/a.cpp", "change_frequency": 2}]
    metrics["knowledge_silos"] = []
    features = FeatureEngineer().build_features(findings, metrics)
    assert features["file"].tolist() == ["project/a.cpp"]
    assert features.iloc[0]["change_frequency"] == 2
