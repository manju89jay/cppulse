"""Tests for src/feature_engineer.py."""

from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from src.feature_engineer import FEATURE_COLUMNS, FeatureEngineer


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

SAMPLE_FINDINGS: dict[str, Any] = {
    "version": "1.0.0",
    "metadata": {
        "repo_path": "/repo",
        "analyzed_at": "2026-01-01T00:00:00Z",
        "file_count": 2,
        "total_loc": 500,
    },
    "findings": [
        {
            "rule_id": "CPP-MEM-001",
            "category": "memory_safety",
            "severity": "error",
            "file": "src/foo.cpp",
            "line": 10,
            "message": "raw pointer",
        },
        {
            "rule_id": "CPP-MOD-004",
            "category": "modernization",
            "severity": "warning",
            "file": "src/foo.cpp",
            "line": 20,
            "message": "use nullptr",
        },
        {
            "rule_id": "MISRA-001",
            "category": "misra",
            "severity": "error",
            "file": "src/bar.cpp",
            "line": 5,
            "message": "misra violation",
        },
        {
            "rule_id": "CPP-CX-013",
            "category": "complexity",
            "severity": "warning",
            "file": "src/bar.cpp",
            "line": 30,
            "message": "high complexity",
        },
    ],
    "summary": {
        "total_findings": 4,
        "by_category": {"memory_safety": 1, "modernization": 1, "complexity": 1, "misra": 1},
        "by_severity": {"error": 2, "warning": 2, "info": 0},
    },
}

SAMPLE_GIT_METRICS: dict[str, Any] = {
    "version": "1.0.0",
    "metadata": {
        "repo_path": "/repo",
        "analyzed_at": "2026-01-01T00:00:00Z",
        "commit_range": "HEAD~100..HEAD",
        "total_commits": 200,
    },
    "file_metrics": [
        {
            "file": "src/foo.cpp",
            "change_frequency": 15,
            "unique_contributors": 3,
            "age_days": 400,
            "lines_of_code": 200,
            "lines_added_total": 500,
            "lines_removed_total": 300,
            "churn_rate": 4.0,
            "bug_fix_commits": 5,
        },
        {
            "file": "src/baz.cpp",
            "change_frequency": 2,
            "unique_contributors": 1,
            "age_days": 100,
            "lines_of_code": 50,
            "lines_added_total": 60,
            "lines_removed_total": 10,
            "churn_rate": 1.4,
            "bug_fix_commits": 0,
        },
    ],
    "knowledge_silos": [
        {
            "file": "src/baz.cpp",
            "sole_contributor": "alice",
            "last_commit_date": "2025-12-01",
        }
    ],
}

EMPTY_FINDINGS: dict[str, Any] = {
    "version": "1.0.0",
    "metadata": {
        "repo_path": "/repo",
        "analyzed_at": "2026-01-01T00:00:00Z",
        "file_count": 0,
        "total_loc": 0,
    },
    "findings": [],
    "summary": {
        "total_findings": 0,
        "by_category": {},
        "by_severity": {},
    },
}

EMPTY_GIT_METRICS: dict[str, Any] = {
    "version": "1.0.0",
    "metadata": {
        "repo_path": "/repo",
        "analyzed_at": "2026-01-01T00:00:00Z",
        "commit_range": "HEAD~100..HEAD",
        "total_commits": 0,
    },
    "file_metrics": [],
    "knowledge_silos": [],
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFeatureEngineerMerge:
    """Tests for the core merge behaviour of FeatureEngineer."""

    def test_returns_dataframe_with_correct_columns(self) -> None:
        """Output DataFrame must have exactly FEATURE_COLUMNS."""
        eng = FeatureEngineer()
        df = eng.build_features(SAMPLE_FINDINGS, SAMPLE_GIT_METRICS)
        assert list(df.columns) == FEATURE_COLUMNS

    def test_row_count_is_union_of_files(self) -> None:
        """Row count equals the number of unique files across both sources."""
        eng = FeatureEngineer()
        df = eng.build_features(SAMPLE_FINDINGS, SAMPLE_GIT_METRICS)
        # files: src/foo.cpp (both), src/bar.cpp (findings only), src/baz.cpp (git only)
        assert len(df) == 3

    def test_foo_cpp_finding_counts(self) -> None:
        """src/foo.cpp should have 1 memory, 1 modernization finding."""
        eng = FeatureEngineer()
        df = eng.build_features(SAMPLE_FINDINGS, SAMPLE_GIT_METRICS)
        row = df[df["file"] == "src/foo.cpp"].iloc[0]
        assert row["memory_findings"] == 1
        assert row["modernization_findings"] == 1
        assert row["complexity_findings"] == 0
        assert row["misra_findings"] == 0
        assert row["finding_count"] == 2

    def test_foo_cpp_max_severity_is_error(self) -> None:
        """src/foo.cpp has an error-level finding; max_severity must be 3."""
        eng = FeatureEngineer()
        df = eng.build_features(SAMPLE_FINDINGS, SAMPLE_GIT_METRICS)
        row = df[df["file"] == "src/foo.cpp"].iloc[0]
        assert row["max_severity"] == 3

    def test_foo_cpp_git_metrics(self) -> None:
        """src/foo.cpp git columns are correctly populated."""
        eng = FeatureEngineer()
        df = eng.build_features(SAMPLE_FINDINGS, SAMPLE_GIT_METRICS)
        row = df[df["file"] == "src/foo.cpp"].iloc[0]
        assert row["change_frequency"] == 15
        assert row["unique_contributors"] == 3
        assert row["churn_rate"] == pytest.approx(4.0)
        assert row["bug_fix_commits"] == 5
        assert row["age_days"] == 400
        assert row["is_knowledge_silo"] == 0

    def test_bar_cpp_git_defaults_to_zero(self) -> None:
        """src/bar.cpp appears only in findings; git columns default to zero."""
        eng = FeatureEngineer()
        df = eng.build_features(SAMPLE_FINDINGS, SAMPLE_GIT_METRICS)
        row = df[df["file"] == "src/bar.cpp"].iloc[0]
        assert row["change_frequency"] == 0
        assert row["churn_rate"] == pytest.approx(0.0)
        assert row["bug_fix_commits"] == 0

    def test_baz_cpp_finding_defaults_to_zero(self) -> None:
        """src/baz.cpp appears only in git metrics; finding columns default to zero."""
        eng = FeatureEngineer()
        df = eng.build_features(SAMPLE_FINDINGS, SAMPLE_GIT_METRICS)
        row = df[df["file"] == "src/baz.cpp"].iloc[0]
        assert row["finding_count"] == 0
        assert row["memory_findings"] == 0
        assert row["max_severity"] == 0

    def test_baz_cpp_is_knowledge_silo(self) -> None:
        """src/baz.cpp is in knowledge_silos list; is_knowledge_silo must be 1."""
        eng = FeatureEngineer()
        df = eng.build_features(SAMPLE_FINDINGS, SAMPLE_GIT_METRICS)
        row = df[df["file"] == "src/baz.cpp"].iloc[0]
        assert row["is_knowledge_silo"] == 1

    def test_no_nan_values(self) -> None:
        """Output DataFrame must not contain any NaN values."""
        eng = FeatureEngineer()
        df = eng.build_features(SAMPLE_FINDINGS, SAMPLE_GIT_METRICS)
        assert not df.isnull().any().any()


class TestFeatureEngineerEdgeCases:
    """Edge-case tests for FeatureEngineer."""

    def test_empty_inputs_returns_empty_dataframe(self) -> None:
        """Both empty inputs must return an empty DataFrame with correct columns."""
        eng = FeatureEngineer()
        df = eng.build_features(EMPTY_FINDINGS, EMPTY_GIT_METRICS)
        assert df.empty
        assert list(df.columns) == FEATURE_COLUMNS

    def test_only_findings_no_git(self) -> None:
        """Findings only — git columns should be zero-filled."""
        eng = FeatureEngineer()
        df = eng.build_features(SAMPLE_FINDINGS, EMPTY_GIT_METRICS)
        assert len(df) == 2  # src/foo.cpp, src/bar.cpp
        assert (df["change_frequency"] == 0).all()
        assert (df["churn_rate"] == 0.0).all()

    def test_only_git_no_findings(self) -> None:
        """Git metrics only — finding columns should be zero-filled."""
        eng = FeatureEngineer()
        df = eng.build_features(EMPTY_FINDINGS, SAMPLE_GIT_METRICS)
        assert len(df) == 2  # src/foo.cpp, src/baz.cpp
        assert (df["finding_count"] == 0).all()
        assert (df["memory_findings"] == 0).all()

    def test_knowledge_silo_without_file_metrics_entry(self) -> None:
        """A silo file not in file_metrics should still appear with is_knowledge_silo=1."""
        git_silo_only: dict[str, Any] = {
            "version": "1.0.0",
            "metadata": {
                "repo_path": "/repo",
                "analyzed_at": "2026-01-01T00:00:00Z",
                "commit_range": "HEAD",
                "total_commits": 5,
            },
            "file_metrics": [],
            "knowledge_silos": [
                {
                    "file": "src/orphan.cpp",
                    "sole_contributor": "bob",
                    "last_commit_date": "2025-06-01",
                }
            ],
        }
        eng = FeatureEngineer()
        df = eng.build_features(EMPTY_FINDINGS, git_silo_only)
        assert len(df) == 1
        row = df.iloc[0]
        assert row["file"] == "src/orphan.cpp"
        assert row["is_knowledge_silo"] == 1
        assert row["change_frequency"] == 0

    def test_severity_mapping_info_only(self) -> None:
        """An info-severity finding should produce max_severity=1."""
        findings: dict[str, Any] = {
            "version": "1.0.0",
            "metadata": {
                "repo_path": "/r",
                "analyzed_at": "2026-01-01T00:00:00Z",
                "file_count": 1,
                "total_loc": 10,
            },
            "findings": [
                {
                    "rule_id": "CPP-MOD-005",
                    "category": "modernization",
                    "severity": "info",
                    "file": "src/a.cpp",
                    "line": 1,
                    "message": "info finding",
                }
            ],
            "summary": {
                "total_findings": 1,
                "by_category": {"modernization": 1},
                "by_severity": {"info": 1},
            },
        }
        eng = FeatureEngineer()
        df = eng.build_features(findings, EMPTY_GIT_METRICS)
        assert df.iloc[0]["max_severity"] == 1

    def test_finding_with_empty_file_is_skipped(self) -> None:
        """Findings with empty file field must be ignored."""
        findings: dict[str, Any] = {
            "version": "1.0.0",
            "metadata": {
                "repo_path": "/r",
                "analyzed_at": "2026-01-01T00:00:00Z",
                "file_count": 0,
                "total_loc": 0,
            },
            "findings": [
                {
                    "rule_id": "CPP-MEM-001",
                    "category": "memory_safety",
                    "severity": "error",
                    "file": "",
                    "line": 1,
                    "message": "bad finding",
                }
            ],
            "summary": {"total_findings": 1, "by_category": {}, "by_severity": {}},
        }
        eng = FeatureEngineer()
        df = eng.build_features(findings, EMPTY_GIT_METRICS)
        assert df.empty
