"""Independent artifact invariants, including non-demo names and corrupt totals."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import jsonschema
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


def _unrank_all(output: Path) -> None:
    path = output / "risk_scores.json"
    data = json.loads(path.read_text())
    files = [row["file"] for row in data["file_risks"]]
    data["file_risks"] = []
    data["unranked_files"] = [
        {
            "file": file,
            "availability": "unavailable",
            "reason_codes": ["unavailable_history"],
            "reasons": ["No observed history is available for this file."],
        }
        for file in files
    ]
    data["metadata"]["ranking_scope"] = {
        "version": "file-eligibility-1",
        "declared_files": len(files),
        "ranked_files": 0,
        "unranked_files": len(files),
    }
    path.write_text(json.dumps(data))


def test_valid_findings_remain_in_scope_when_ranking_is_unavailable(
    results: Path,
) -> None:
    """A missing rank must not erase observed static findings or their roadmap."""
    _unrank_all(results)
    path = results / "roadmap.json"
    document = json.loads(path.read_text())
    document["items"] = [
        {
            "priority": 1,
            "file": "src/alpha.cpp",
            "action": "Review observed cast",
            "category": "modernization",
            "estimated_hours": 0.5,
            "impact_score": 1,
        }
    ]
    path.write_text(json.dumps(document))
    summary = verify_pipeline(results)
    assert summary["risk_files"] == 0
    assert summary["unranked_files"] == 2
    assert summary["health_status"] == "scored"


def test_ranking_inventory_counts_cannot_hide_an_unranked_file(results: Path) -> None:
    _unrank_all(results)
    path = results / "risk_scores.json"
    data = json.loads(path.read_text())
    data["metadata"]["ranking_scope"]["unranked_files"] = 1
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="[Rr]anking.*count"):
        verify_pipeline(results)


def test_file_cannot_be_both_ranked_and_unranked(results: Path) -> None:
    path = results / "risk_scores.json"
    data = json.loads(path.read_text())
    ranked = data["file_risks"][0]
    _unrank_all(results)
    data = json.loads(path.read_text())
    data["file_risks"] = [ranked]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="both ranked and unranked"):
        verify_pipeline(results)


def test_hotspot_cannot_use_an_explicitly_unranked_file(results: Path) -> None:
    _unrank_all(results)
    path = results / "risk_scores.json"
    data = json.loads(path.read_text())
    data["hotspots"] = [
        {
            "file": "src/alpha.cpp",
            "hotspot_score": 1.0,
            "change_frequency": 1,
            "complexity_score": 1.0,
            "finding_count": 1,
        }
    ]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Hotspots"):
        verify_pipeline(results)


def test_unranked_scope_without_counts_cannot_be_silently_accepted(
    results: Path,
) -> None:
    _unrank_all(results)
    path = results / "risk_scores.json"
    data = json.loads(path.read_text())
    del data["metadata"]["ranking_scope"]
    path.write_text(json.dumps(data))
    with pytest.raises(
        jsonschema.ValidationError, match="ranking_scope.*required property"
    ):
        verify_pipeline(results)
