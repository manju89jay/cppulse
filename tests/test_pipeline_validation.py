"""Independent artifact invariants, including non-demo names and corrupt totals."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.verify_pipeline import verify_pipeline


@pytest.fixture
def results(tmp_path: Path) -> Path:
    """Write a minimal pipeline with different filenames from the demo."""
    data = {
        "findings": {
            "version": "1.0.0",
            "metadata": {
                "repo_path": "/example",
                "analyzed_at": "2026-11-13T10:00:00Z",
                "file_count": 2,
                "total_loc": 20,
            },
            "findings": [
                {
                    "rule_id": "CPP-MOD-001",
                    "category": "modernization",
                    "severity": "warning",
                    "file": "src/alpha.cpp",
                    "line": 1,
                    "message": "cast",
                }
            ],
            "summary": {
                "total_findings": 1,
                "by_category": {"modernization": 1},
                "by_severity": {"warning": 1},
            },
        },
        "git_metrics": {
            "version": "1.0.0",
            "metadata": {
                "repo_path": "/example",
                "analyzed_at": "2026-11-13T10:00:00Z",
                "commit_range": "N/A",
                "total_commits": 0,
                "history_status": "unavailable",
            },
            "file_metrics": [],
            "knowledge_silos": [],
        },
        "risk_scores": {
            "version": "1.0.0",
            "metadata": {
                "generated_at": "2026-11-13T10:00:00Z",
                "model_type": "heuristic",
                "feature_count": 10,
            },
            "health_score": {"overall": 99.5, "by_category": {}, "status": "scored"},
            "file_risks": [
                {
                    "file": name,
                    "bug_probability": 0.1,
                    "risk_level": "low",
                    "top_factors": [],
                }
                for name in ["src/alpha.cpp", "include/beta.hpp"]
            ],
            "hotspots": [],
        },
        "roadmap": {"version": "1.0.0", "items": []},
    }
    for name, document in data.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(document))
    return tmp_path


def test_non_demo_static_only_results_validate(results: Path) -> None:
    """General verification supports clean files and absent history."""
    assert verify_pipeline(results)["risk_files"] == 2


def test_corrupt_summary_is_rejected(results: Path) -> None:
    path = results / "findings.json"
    data = json.loads(path.read_text())
    data["summary"]["by_severity"]["warning"] = 3
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="totals"):
        verify_pipeline(results)


def test_duplicate_risk_identity_is_rejected(results: Path) -> None:
    path = results / "risk_scores.json"
    data = json.loads(path.read_text())
    data["file_risks"].append(data["file_risks"][0])
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Duplicate"):
        verify_pipeline(results)


@pytest.mark.parametrize(
    "identity", ["/etc/source.cpp", "C:\\source.cpp", "src/../source.cpp"]
)
def test_external_or_noncanonical_identity_is_rejected(
    results: Path, identity: str
) -> None:
    path = results / "findings.json"
    data = json.loads(path.read_text())
    data["findings"][0]["file"] = identity
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="identity"):
        verify_pipeline(results)


def test_empty_risk_scope_cannot_be_perfect(results: Path) -> None:
    path = results / "findings.json"
    data = json.loads(path.read_text())
    data["findings"] = []
    data["summary"] = {"total_findings": 0, "by_category": {}, "by_severity": {}}
    path.write_text(json.dumps(data))
    path = results / "risk_scores.json"
    data = json.loads(path.read_text())
    data["file_risks"] = []
    data["health_score"]["overall"] = 100
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Empty"):
        verify_pipeline(results)


def test_clean_source_missing_from_risk_scope_is_rejected(results: Path) -> None:
    path = results / "findings.json"
    data = json.loads(path.read_text())
    data["metadata"]["analysis"] = {
        "enabled_rules": ["CPP-MOD-001"],
        "files": [
            {
                "path": "/example/" + name,
                "status": "analyzed",
                "compile_context": "fallback",
                "error_count": 0,
            }
            for name in ["src/alpha.cpp", "include/beta.hpp", "src/clean.cpp"]
        ],
    }
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="inventory"):
        verify_pipeline(results)
