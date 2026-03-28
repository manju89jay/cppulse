"""Tests for the report-engine FastAPI application."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _make_client(data_dir: Path) -> TestClient:
    """Create a TestClient with DATA_DIR pointed at the given directory.

    Args:
        data_dir: Path to a directory containing sample JSON files.

    Returns:
        Configured TestClient instance.
    """
    os.environ["DATA_DIR"] = str(data_dir)
    # Re-import to pick up env var — use importlib to avoid module-level caching
    import importlib

    import src.api as api_module

    importlib.reload(api_module)
    return TestClient(api_module.app)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


def test_health_returns_ok(data_dir: Path) -> None:
    """GET /health returns 200 and status ok."""
    client = _make_client(data_dir)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /api/v1/summary
# ---------------------------------------------------------------------------


def test_summary_returns_200(data_dir: Path) -> None:
    """GET /api/v1/summary returns 200."""
    client = _make_client(data_dir)
    response = client.get("/api/v1/summary")
    assert response.status_code == 200


def test_summary_contains_health_score(data_dir: Path) -> None:
    """Summary response includes health_score with overall field."""
    client = _make_client(data_dir)
    body = client.get("/api/v1/summary").json()
    assert "health_score" in body
    assert "overall" in body["health_score"]
    assert body["health_score"]["overall"] == pytest.approx(72.5)


def test_summary_contains_findings_summary(data_dir: Path) -> None:
    """Summary response includes findings_summary with total_findings."""
    client = _make_client(data_dir)
    body = client.get("/api/v1/summary").json()
    assert "findings_summary" in body
    assert body["findings_summary"]["total_findings"] == 4


def test_summary_missing_file_returns_503(tmp_path: Path) -> None:
    """GET /api/v1/summary returns 503 when data files are absent."""
    client = _make_client(tmp_path)
    response = client.get("/api/v1/summary")
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# /api/v1/findings
# ---------------------------------------------------------------------------


def test_findings_returns_200(data_dir: Path) -> None:
    """GET /api/v1/findings returns 200."""
    client = _make_client(data_dir)
    response = client.get("/api/v1/findings")
    assert response.status_code == 200


def test_findings_default_pagination(data_dir: Path) -> None:
    """Default findings response has correct pagination shape."""
    client = _make_client(data_dir)
    body = client.get("/api/v1/findings").json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "per_page" in body
    assert "total_pages" in body
    assert body["total"] == 4
    assert body["page"] == 1


def test_findings_pagination_page2(data_dir: Path) -> None:
    """Pagination: page 2 with per_page=2 returns last 2 items."""
    client = _make_client(data_dir)
    body = client.get("/api/v1/findings?page=2&per_page=2").json()
    assert body["page"] == 2
    assert body["per_page"] == 2
    assert len(body["items"]) == 2
    assert body["total_pages"] == 2


def test_findings_pagination_empty_page(data_dir: Path) -> None:
    """Requesting a page beyond the last returns empty items list."""
    client = _make_client(data_dir)
    body = client.get("/api/v1/findings?page=99&per_page=50").json()
    assert body["items"] == []
    assert body["total"] == 4


def test_findings_category_filter(data_dir: Path) -> None:
    """Category filter returns only matching findings."""
    client = _make_client(data_dir)
    body = client.get("/api/v1/findings?category=memory_safety").json()
    assert body["total"] == 1
    assert all(f["category"] == "memory_safety" for f in body["items"])


def test_findings_category_filter_modernization(data_dir: Path) -> None:
    """Category filter for modernization returns correct count."""
    client = _make_client(data_dir)
    body = client.get("/api/v1/findings?category=modernization").json()
    assert body["total"] == 1
    assert body["items"][0]["rule_id"] == "CPP-MOD-004"


def test_findings_category_filter_nonexistent(data_dir: Path) -> None:
    """Category filter for unknown category returns empty list."""
    client = _make_client(data_dir)
    body = client.get("/api/v1/findings?category=nonexistent").json()
    assert body["total"] == 0
    assert body["items"] == []


def test_findings_missing_file_returns_503(tmp_path: Path) -> None:
    """GET /api/v1/findings returns 503 when findings.json is absent."""
    client = _make_client(tmp_path)
    response = client.get("/api/v1/findings")
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# /api/v1/hotspots
# ---------------------------------------------------------------------------


def test_hotspots_returns_200(data_dir: Path) -> None:
    """GET /api/v1/hotspots returns 200."""
    client = _make_client(data_dir)
    response = client.get("/api/v1/hotspots")
    assert response.status_code == 200


def test_hotspots_shape(data_dir: Path) -> None:
    """Hotspots response has items list and total."""
    client = _make_client(data_dir)
    body = client.get("/api/v1/hotspots").json()
    assert "items" in body
    assert "total" in body
    assert body["total"] == 2
    assert body["items"][0]["file"] == "src/main.cpp"


def test_hotspots_missing_file_returns_503(tmp_path: Path) -> None:
    """GET /api/v1/hotspots returns 503 when risk_scores.json is absent."""
    client = _make_client(tmp_path)
    response = client.get("/api/v1/hotspots")
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# /api/v1/risks
# ---------------------------------------------------------------------------


def test_risks_returns_200(data_dir: Path) -> None:
    """GET /api/v1/risks returns 200."""
    client = _make_client(data_dir)
    response = client.get("/api/v1/risks")
    assert response.status_code == 200


def test_risks_shape(data_dir: Path) -> None:
    """Risks response has items and total."""
    client = _make_client(data_dir)
    body = client.get("/api/v1/risks").json()
    assert "items" in body
    assert "total" in body
    assert body["total"] == 2


def test_risks_missing_file_returns_503(tmp_path: Path) -> None:
    """GET /api/v1/risks returns 503 when risk_scores.json is absent."""
    client = _make_client(tmp_path)
    response = client.get("/api/v1/risks")
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# /api/v1/silos
# ---------------------------------------------------------------------------


def test_silos_returns_200(data_dir: Path) -> None:
    """GET /api/v1/silos returns 200."""
    client = _make_client(data_dir)
    response = client.get("/api/v1/silos")
    assert response.status_code == 200


def test_silos_shape(data_dir: Path) -> None:
    """Silos response has items and total."""
    client = _make_client(data_dir)
    body = client.get("/api/v1/silos").json()
    assert "items" in body
    assert "total" in body
    assert body["total"] == 1
    assert body["items"][0]["sole_contributor"] == "alice"


def test_silos_missing_file_returns_503(tmp_path: Path) -> None:
    """GET /api/v1/silos returns 503 when git_metrics.json is absent."""
    client = _make_client(tmp_path)
    response = client.get("/api/v1/silos")
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# /api/v1/roadmap
# ---------------------------------------------------------------------------


def test_roadmap_returns_200(data_dir: Path) -> None:
    """GET /api/v1/roadmap returns 200."""
    client = _make_client(data_dir)
    response = client.get("/api/v1/roadmap")
    assert response.status_code == 200


def test_roadmap_sorted_by_priority(data_dir: Path) -> None:
    """Roadmap items are sorted ascending by priority."""
    client = _make_client(data_dir)
    body = client.get("/api/v1/roadmap").json()
    priorities = [item["priority"] for item in body["items"]]
    assert priorities == sorted(priorities)
    assert body["total"] == 3


def test_roadmap_missing_file_returns_503(tmp_path: Path) -> None:
    """GET /api/v1/roadmap returns 503 when roadmap.json is absent."""
    client = _make_client(tmp_path)
    response = client.get("/api/v1/roadmap")
    assert response.status_code == 503


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


def test_cors_headers_present(data_dir: Path) -> None:
    """CORS response header is present for allowed origin."""
    client = _make_client(data_dir)
    response = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
