"""The installed API serves built local assets without a Node runtime or project cwd."""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient
import pytest


def test_dashboard_shell_and_all_selected_assets_are_served(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from cppulse.report_engine import api

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "unconfigured-output"))
    monkeypatch.setenv("CPPULSE_API_KEY", "optional-key")
    client = TestClient(api.app)
    shell = client.get("/")
    assert shell.status_code == 200
    assert "text/html" in shell.headers["content-type"]
    paths = re.findall(r'(?:src|href)="(/assets/[^"\s]+)"', shell.text)
    assert any(path.endswith(".js") for path in paths)
    assert any(path.endswith(".css") for path in paths)
    for path in paths:
        response = client.get(path)
        assert response.status_code == 200
        assert len(response.content) > 100
    assert client.get("/api/v1/view").status_code == 401
    assert not (tmp_path / "unconfigured-output").exists()
    assert client.get("/assets/missing.js").status_code == 404


def test_missing_bundle_has_actionable_error_and_does_not_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from cppulse.report_engine import api

    monkeypatch.setattr(api, "_dashboard_directory", lambda: tmp_path / "absent-assets")
    response = TestClient(api.app).get("/")
    assert response.status_code == 503
    assert "build_dashboard_assets.py" in response.text
    assert not (tmp_path / "absent-assets").exists()
