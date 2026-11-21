"""Roadmap ordering uses impact before the identity of a tied row."""

import pytest

from cppulse.predictor.main import build_roadmap


@pytest.mark.parametrize("profile", ["default", "safety-critical"])
def test_tied_roadmap_rows_use_file_then_category(profile: str) -> None:
    findings = {
        "findings": [
            {
                "file": "a.cpp",
                "category": "modernization",
                "severity": "warning",
                "rule_id": "CPP-MOD-001",
            },
            {
                "file": "a.cpp",
                "category": "misra",
                "severity": "warning",
                "rule_id": "MISRA-006",
            },
            {
                "file": "a.cpp",
                "category": "complexity",
                "severity": "warning",
                "rule_id": "CPP-CX-001",
            },
            {
                "file": "z.cpp",
                "category": "memory_safety",
                "severity": "error",
                "rule_id": "CPP-MEM-001",
            },
        ]
    }
    history = {
        "knowledge_silos": [{"file": file} for file in ("c.cpp", "a.cpp", "b.cpp")]
    }
    risk = {"file_risks": [{"file": "z.cpp", "risk_level": "high"}]}
    items = build_roadmap(findings, history, risk, profile)["items"]

    expected = [
        ("z.cpp", "memory_safety", 9.0, 4.0, ["CPP-MEM-001"]),
        ("a.cpp", "complexity", 2.0, 3.0, ["CPP-CX-001"]),
        ("a.cpp", "knowledge_silo", 2.0, 8.0, []),
        ("a.cpp", "modernization", 2.0, 1.0, ["CPP-MOD-001"]),
        ("b.cpp", "knowledge_silo", 2.0, 8.0, []),
        ("c.cpp", "knowledge_silo", 2.0, 8.0, []),
    ]
    if profile == "safety-critical":
        expected.insert(3, ("a.cpp", "misra", 2.0, 2.0, ["MISRA-006"]))

    assert [row["priority"] for row in items] == list(range(1, len(expected) + 1))
    assert [
        (
            row["file"],
            row["category"],
            row["impact_score"],
            row["estimated_hours"],
            row["finding_ids"],
        )
        for row in items
    ] == expected
