"""Shared pytest fixtures for report-engine tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

SAMPLE_FINDINGS: dict = {
    "version": "1.0.0",
    "metadata": {
        "repo_path": "/tmp/my_project",
        "analyzed_at": "2026-03-26T10:00:00Z",
        "file_count": 5,
        "total_loc": 2000,
    },
    "findings": [
        {
            "rule_id": "CPP-MEM-001",
            "category": "memory_safety",
            "severity": "error",
            "file": "src/main.cpp",
            "line": 42,
            "column": 5,
            "end_line": 42,
            "message": "Raw pointer usage detected",
            "suggestion": "Use std::unique_ptr instead",
            "confidence": 0.95,
        },
        {
            "rule_id": "CPP-MOD-004",
            "category": "modernization",
            "severity": "warning",
            "file": "src/utils.cpp",
            "line": 10,
            "column": 1,
            "end_line": 10,
            "message": "Use nullptr instead of NULL",
            "suggestion": "Replace NULL with nullptr",
            "confidence": 0.99,
        },
        {
            "rule_id": "CPP-CX-013",
            "category": "complexity",
            "severity": "warning",
            "file": "src/engine.cpp",
            "line": 100,
            "column": 3,
            "end_line": 150,
            "message": "Function complexity exceeds threshold",
            "confidence": 0.88,
        },
        {
            "rule_id": "MISRA-001",
            "category": "misra",
            "severity": "info",
            "file": "src/parser.cpp",
            "line": 5,
            "column": 1,
            "end_line": 5,
            "message": "MISRA C++ rule violation",
            "confidence": 0.80,
        },
    ],
    "summary": {
        "total_findings": 4,
        "by_category": {
            "memory_safety": 1,
            "modernization": 1,
            "complexity": 1,
            "misra": 1,
        },
        "by_severity": {
            "error": 1,
            "warning": 2,
            "info": 1,
        },
    },
}

SAMPLE_GIT_METRICS: dict = {
    "version": "1.0.0",
    "metadata": {
        "repo_path": "/tmp/my_project",
        "analyzed_at": "2026-03-26T10:00:00Z",
        "commit_range": "HEAD~100..HEAD",
        "total_commits": 120,
    },
    "file_metrics": [
        {
            "file": "src/main.cpp",
            "change_frequency": 45,
            "unique_contributors": 3,
            "age_days": 365,
            "last_modified_days": 2,
            "lines_of_code": 500,
            "lines_added_total": 800,
            "lines_removed_total": 300,
            "churn_rate": 2.2,
            "bug_fix_commits": 8,
            "contributor_list": ["alice", "bob", "carol"],
        },
        {
            "file": "src/utils.cpp",
            "change_frequency": 10,
            "unique_contributors": 1,
            "age_days": 200,
            "last_modified_days": 30,
            "lines_of_code": 200,
            "lines_added_total": 250,
            "lines_removed_total": 50,
            "churn_rate": 1.5,
            "bug_fix_commits": 2,
            "contributor_list": ["alice"],
        },
    ],
    "knowledge_silos": [
        {
            "file": "src/utils.cpp",
            "sole_contributor": "alice",
            "last_commit_date": "2026-02-15",
            "risk_note": "Only Alice has touched this file in 12 months",
        }
    ],
}

SAMPLE_RISK_SCORES: dict = {
    "version": "1.0.0",
    "metadata": {
        "generated_at": "2026-03-26T10:05:00Z",
        "model_type": "xgboost",
        "feature_count": 10,
        "training_samples": 500,
        "f1_score": 0.82,
    },
    "health_score": {
        "overall": 72.5,
        "by_category": {
            "memory_safety": 65.0,
            "modernization": 80.0,
            "complexity": 70.0,
            "misra_compliance": 75.0,
        },
    },
    "file_risks": [
        {
            "file": "src/main.cpp",
            "bug_probability": 0.82,
            "risk_level": "critical",
            "top_factors": [
                {"feature": "change_frequency", "importance": 0.35, "value": 45.0},
                {"feature": "bug_fix_commits", "importance": 0.25, "value": 8.0},
            ],
        },
        {
            "file": "src/utils.cpp",
            "bug_probability": 0.40,
            "risk_level": "medium",
            "top_factors": [
                {"feature": "churn_rate", "importance": 0.20, "value": 1.5},
            ],
        },
    ],
    "hotspots": [
        {
            "file": "src/main.cpp",
            "hotspot_score": 184.5,
            "change_frequency": 45,
            "complexity_score": 8.2,
            "finding_count": 3,
        },
        {
            "file": "src/engine.cpp",
            "hotspot_score": 92.0,
            "change_frequency": 20,
            "complexity_score": 9.5,
            "finding_count": 5,
        },
    ],
}

SAMPLE_ROADMAP: dict = {
    "version": "1.0.0",
    "items": [
        {
            "priority": 1,
            "file": "src/main.cpp",
            "action": "Replace raw pointers with std::unique_ptr",
            "category": "memory_safety",
            "estimated_hours": 4.0,
            "impact_score": 85.0,
            "finding_ids": ["CPP-MEM-001"],
        },
        {
            "priority": 2,
            "file": "src/engine.cpp",
            "action": "Refactor complex function into smaller units",
            "category": "complexity",
            "estimated_hours": 8.0,
            "impact_score": 70.0,
            "finding_ids": ["CPP-CX-013"],
        },
        {
            "priority": 3,
            "file": "src/utils.cpp",
            "action": "Onboard second contributor for knowledge silo mitigation",
            "category": "knowledge_silo",
            "estimated_hours": 2.0,
            "impact_score": 60.0,
            "finding_ids": [],
        },
    ],
}


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory with all sample JSON files.

    Args:
        tmp_path: pytest-provided temporary directory.

    Returns:
        Path to the temporary data directory containing sample JSON files.
    """
    (tmp_path / "findings.json").write_text(
        json.dumps(SAMPLE_FINDINGS), encoding="utf-8"
    )
    (tmp_path / "git_metrics.json").write_text(
        json.dumps(SAMPLE_GIT_METRICS), encoding="utf-8"
    )
    (tmp_path / "risk_scores.json").write_text(
        json.dumps(SAMPLE_RISK_SCORES), encoding="utf-8"
    )
    (tmp_path / "roadmap.json").write_text(json.dumps(SAMPLE_ROADMAP), encoding="utf-8")
    return tmp_path
