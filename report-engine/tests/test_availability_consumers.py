"""API and report consumers must retain unavailable file and history scope."""

from __future__ import annotations

import json
import importlib
import os
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.pdf_generator import PDFGenerator


def _make_client(directory: Path) -> TestClient:
    """Use the actual data-bound API routes with no mocked result adapter."""
    from cppulse.report_engine import api

    os.environ["DATA_DIR"] = str(directory)
    importlib.reload(api)
    return TestClient(api.app)


@pytest.fixture()
def availability_data(data_dir: Path) -> tuple[Path, list[dict[str, Any]]]:
    """Attach explicit synthetic incomplete files to otherwise valid legacy data."""
    unranked = [
        {
            "file": "src/incomplete.hpp",
            "availability": "partial",
            "reason_codes": ["PARTIAL_ANALYSIS"],
            "reasons": ["The compiler could not parse the selected <header> context."],
        },
        {
            "file": "src/unverified.hpp",
            "availability": "unverified",
            "reason_codes": ["MISSING_CONTEXT"],
            "reasons": ["No applicable parse context was recorded."],
        },
    ]
    path = data_dir / "risk_scores.json"
    document = json.loads(path.read_bytes())
    document["unranked_files"] = unranked
    document["metadata"]["ranking_scope"] = {
        "version": "file-eligibility-1",
        "declared_files": 4,
        "ranked_files": 2,
        "unranked_files": 2,
    }
    path.write_text(json.dumps(document), encoding="utf-8")
    return data_dir, unranked


def test_risk_api_preserves_unranked_files_and_existing_numeric_items(
    availability_data: tuple[Path, list[dict[str, Any]]],
) -> None:
    """New unavailable rows remain distinct from the compatible ranked envelope."""
    directory, unranked = availability_data
    client = _make_client(directory)

    response = client.get("/api/v1/risks")

    assert response.status_code == 200
    body = response.json()
    assert body["unranked_files"] == unranked
    assert body["unranked_total"] == 2
    assert body["ranking_scope"]["declared_files"] == 4
    assert body["total"] == 2
    assert all(isinstance(item["bug_probability"], float) for item in body["items"])
    assert not {item["file"] for item in unranked} & {
        item["file"] for item in body["items"]
    }


@pytest.mark.parametrize("status", ["partial", "unavailable", None])
def test_silo_api_preserves_observations_and_history_availability(
    data_dir: Path, status: str | None
) -> None:
    """An observed count remains numeric, with explicit limits on interpretation."""
    path = data_dir / "git_metrics.json"
    document = json.loads(path.read_bytes())
    if status is not None:
        document["metadata"]["history_status"] = status
    document["metadata"]["limitations"] = ["Synthetic incomplete-history example."]
    path.write_text(json.dumps(document), encoding="utf-8")

    response = _make_client(data_dir).get("/api/v1/silos")

    assert response.status_code == 200
    body = response.json()
    assert body["history_status"] == (status or "unverified")
    assert body["limitations"] == document["metadata"]["limitations"]
    assert body["total"] == 1
    assert body["items"] == document["knowledge_silos"]


def test_legacy_report_renders_unranked_reasons_without_numeric_risk(
    availability_data: tuple[Path, list[dict[str, Any]]],
) -> None:
    """The report shows why a file lacks a rank, instead of dropping that file."""
    directory, unranked = availability_data

    rendered = PDFGenerator(directory).render_html()

    assert "Files without a usable rank" in rendered
    assert all(item["file"] in rendered for item in unranked)
    assert "PARTIAL_ANALYSIS" in rendered
    assert "No applicable parse context was recorded." in rendered
    assert "&lt;header&gt;" in rendered
    assert "could not parse the selected <header>" not in rendered


@pytest.mark.parametrize("status", ["partial", "unavailable", None])
def test_legacy_report_never_claims_no_silos_from_insufficient_history(
    data_dir: Path, status: str | None
) -> None:
    """An empty observed list cannot settle knowledge risk for incomplete history."""
    path = data_dir / "git_metrics.json"
    document = json.loads(path.read_bytes())
    document["knowledge_silos"] = []
    if status is not None:
        document["metadata"]["history_status"] = status
    document["metadata"]["limitations"] = ["Synthetic shallow history."]
    path.write_text(json.dumps(document), encoding="utf-8")

    rendered = PDFGenerator(data_dir).render_html()

    assert "Insufficient history" in rendered
    assert "No knowledge silos detected" not in rendered
    assert "Synthetic shallow history." in rendered


def test_complete_history_can_report_no_observed_single_contributor_alerts(
    data_dir: Path,
) -> None:
    """An explicit usable history remains distinguishable from unknown history."""
    path = data_dir / "git_metrics.json"
    document = json.loads(path.read_bytes())
    document["knowledge_silos"] = []
    document["metadata"]["history_status"] = "available"
    path.write_text(json.dumps(document), encoding="utf-8")

    rendered = PDFGenerator(data_dir).render_html()

    assert "No single-contributor alerts in the available history." in rendered
    assert "Insufficient history" not in rendered
