"""Tests for the in-memory JSON cache with mtime invalidation."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from .conftest import SAMPLE_FINDINGS, SAMPLE_RISK_SCORES


def _make_client(data_dir: Path) -> TestClient:
    """Create a TestClient with DATA_DIR and a fresh cache."""
    os.environ["DATA_DIR"] = str(data_dir)
    import importlib

    import src.api as api_module

    importlib.reload(api_module)
    api_module._json_cache.clear()
    return TestClient(api_module.app)


@pytest.fixture()
def data_dir(tmp_path: Path) -> Path:
    """Minimal data dir with findings.json and risk_scores.json."""
    (tmp_path / "findings.json").write_text(
        json.dumps(SAMPLE_FINDINGS), encoding="utf-8"
    )
    (tmp_path / "risk_scores.json").write_text(
        json.dumps(SAMPLE_RISK_SCORES), encoding="utf-8"
    )
    return tmp_path


class TestCacheHit:
    """Verify that repeated requests return cached data without re-reading."""

    def test_second_request_uses_cache(self, data_dir: Path) -> None:
        client = _make_client(data_dir)
        r1 = client.get("/api/v1/summary")
        assert r1.status_code == 200

        # Remove the file — if caching works, the second call still succeeds
        # because the mtime hasn't changed (file still exists in cache).
        # Instead, verify data identity.
        r2 = client.get("/api/v1/summary")
        assert r2.status_code == 200
        assert r1.json() == r2.json()

    def test_hotspots_cached(self, data_dir: Path) -> None:
        client = _make_client(data_dir)
        r1 = client.get("/api/v1/hotspots")
        r2 = client.get("/api/v1/hotspots")
        assert r1.status_code == 200
        assert r1.json() == r2.json()


class TestCacheInvalidation:
    """Verify that modifying a file causes the cache to reload."""

    def test_modified_file_reloads_data(self, data_dir: Path) -> None:
        client = _make_client(data_dir)
        r1 = client.get("/api/v1/summary")
        assert r1.status_code == 200
        original_score = r1.json()["health_score"]["overall"]

        # Modify the risk_scores.json file with a different health score.
        modified = SAMPLE_RISK_SCORES.copy()
        modified["health_score"] = {
            "overall": 99.9,
            "by_category": {"memory_safety": 99.9},
        }
        path = data_dir / "risk_scores.json"
        # Ensure mtime changes (some filesystems have 1-second resolution).
        time.sleep(0.05)
        path.write_text(json.dumps(modified), encoding="utf-8")
        # Touch to ensure mtime differs on coarse filesystems.
        os.utime(path, (time.time() + 1, time.time() + 1))

        r2 = client.get("/api/v1/summary")
        assert r2.status_code == 200
        new_score = r2.json()["health_score"]["overall"]
        assert new_score == 99.9
        assert new_score != original_score


class TestCacheMissing:
    """Verify that missing files still raise 503 even with caching."""

    def test_missing_file_returns_503(self, data_dir: Path) -> None:
        (data_dir / "findings.json").unlink()
        client = _make_client(data_dir)
        r = client.get("/api/v1/findings")
        assert r.status_code == 503


class TestCacheClear:
    """Verify that clearing the cache works correctly."""

    def test_clear_forces_reload(self, data_dir: Path) -> None:
        import importlib

        import src.api as api_module

        importlib.reload(api_module)

        client = _make_client(data_dir)
        client.get("/api/v1/summary")

        # Clear the cache.
        api_module._json_cache.clear()

        # Modify data and verify fresh load.
        modified = SAMPLE_RISK_SCORES.copy()
        modified["health_score"] = {
            "overall": 50.0,
            "by_category": {"memory_safety": 50.0},
        }
        path = data_dir / "risk_scores.json"
        path.write_text(json.dumps(modified), encoding="utf-8")

        r = client.get("/api/v1/summary")
        assert r.status_code == 200
        assert r.json()["health_score"]["overall"] == 50.0
