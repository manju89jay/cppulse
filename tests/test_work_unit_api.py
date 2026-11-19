"""Actual HTTP query agreement, pinning, authentication and read-only limits."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from cppulse.report_engine.api import app
from cppulse.work_unit_store import WorkUnitIndex


@pytest.fixture
def catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "units.sqlite"
    store = WorkUnitIndex(path)
    store.publish(
        "first-run",
        "a" * 64,
        [
            {"unit_id": f"unit-{number:03}", "outcome": "complete"}
            for number in range(9)
        ],
    )
    monkeypatch.setenv("CPPULSE_WORK_UNIT_CATALOG", str(path))
    monkeypatch.delenv("CPPULSE_API_KEY", raising=False)
    return path


def test_http_pages_agree_with_index_and_preserve_exact_run_pins(catalog: Path) -> None:
    before = catalog.read_bytes()
    with TestClient(app) as client:
        query = {"run_id": "first-run", "manifest_sha256": "a" * 64, "page_size": 4}
        first = client.get("/api/v1/work-units", params=query)
        assert first.status_code == 200, first.text
        data = first.json()
        assert (
            data["items"]
            == WorkUnitIndex(catalog, read_only=True).page(
                "first-run", "a" * 64, page_size=4
            )[0]
        )
        assert data["run_id"] == "first-run"
        assert data["manifest_sha256"] == "a" * 64
        assert first.headers["cache-control"] == "no-store"
        cursor = data["next_cursor"]
        second = client.get("/api/v1/work-units", params={**query, "cursor": cursor})
        assert second.status_code == 200
        assert second.json()["items"][0]["unit_id"] == "unit-004"
        for change in (
            {"page_size": 3},
            {"outcome": "partial"},
            {"manifest_sha256": "b" * 64},
        ):
            response = client.get(
                "/api/v1/work-units", params={**query, "cursor": cursor, **change}
            )
            assert response.status_code == 422
    assert catalog.read_bytes() == before


def test_catalog_reads_require_auth_and_paired_pins(
    catalog: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CPPULSE_API_KEY", "test-secret")
    with TestClient(app) as client:
        query = {"run_id": "first-run", "manifest_sha256": "a" * 64}
        assert client.get("/api/v1/work-units", params=query).status_code == 401
        headers = {"Authorization": "Bearer test-secret"}
        for params in (
            {},
            {"run_id": "first-run"},
            {**query, "page_size": 201},
            {**query, "cursor": "not-base64!"},
        ):
            assert (
                client.get(
                    "/api/v1/work-units", params=params, headers=headers
                ).status_code
                == 422
            )
        assert (
            client.get("/api/v1/work-units", params=query, headers=headers).status_code
            == 200
        )


def test_missing_catalog_is_not_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    absent = tmp_path / "missing-parent" / "units.sqlite"
    monkeypatch.setenv("CPPULSE_WORK_UNIT_CATALOG", str(absent))
    monkeypatch.delenv("CPPULSE_API_KEY", raising=False)
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/work-units", params={"run_id": "run", "manifest_sha256": "a" * 64}
        )
    assert response.status_code in (409, 503)
    assert not absent.parent.exists()


def test_http_transfer_is_byte_bounded_and_corrupt_rows_are_explicit(
    catalog: Path,
) -> None:
    import sqlite3

    store = WorkUnitIndex(catalog)
    store.publish(
        "large-run",
        "b" * 64,
        [
            {
                "unit_id": f"unit-{number:03}",
                "outcome": "partial",
                "reason": "😀" * 4000,
            }
            for number in range(80)
        ],
    )
    query = {"run_id": "large-run", "manifest_sha256": "b" * 64, "page_size": 200}
    seen = []
    with TestClient(app) as client:
        while True:
            response = client.get("/api/v1/work-units", params=query)
            assert response.status_code == 200, response.text
            assert len(response.content) <= 1024 * 1024
            data = response.json()
            seen.extend(row["unit_id"] for row in data["items"])
            if data["next_cursor"] is None:
                break
            query["cursor"] = data["next_cursor"]
        assert seen == [f"unit-{number:03}" for number in range(80)]
        with sqlite3.connect(catalog) as db:
            db.execute(
                "UPDATE units SET payload=? WHERE run_id=? AND unit_id=?",
                ("x" * 20000, "large-run", "unit-000"),
            )
        query.pop("cursor", None)
        response = client.get("/api/v1/work-units", params=query)
        assert response.status_code == 409
        assert "bound" in response.json()["detail"]
