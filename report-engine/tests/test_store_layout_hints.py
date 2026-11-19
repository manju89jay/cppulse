"""Corrupt v3 metadata must never reveal stale flat compatibility results."""

from pathlib import Path

from fastapi.testclient import TestClient
import pytest


@pytest.mark.parametrize("marker", ["heads.json", "store-format.json", ".migration-v3"])
@pytest.mark.parametrize("shape", ["file", "dangling-symlink"])
def test_v3_metadata_hints_fail_closed_before_flat_fallback(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch, marker: str, shape: str
) -> None:
    from cppulse.report_engine.api import app

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.delenv("CPPULSE_API_KEY", raising=False)
    with TestClient(app) as client:
        assert client.get("/api/v1/summary").status_code == 200
        path = data_dir / marker
        if shape == "file":
            path.write_bytes(b"{invalid store metadata")
        else:
            path.symlink_to(data_dir / "missing-metadata-target")
        for endpoint in ("run", "summary", "findings"):
            response = client.get("/api/v1/" + endpoint)
            assert response.status_code == 503
            assert "Current run is unavailable" in response.json()["detail"]["message"]
