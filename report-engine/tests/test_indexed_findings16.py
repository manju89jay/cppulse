"""Stored findings are paged without materializing unrelated run artifacts."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
import pytest

from cppulse.run_store import RunStore
from .conftest import SAMPLE_FINDINGS
from .test_run_snapshot_api import publish_attempt


@pytest.fixture(params=["2.0.0", "3.0.0"])
def indexed(tmp_path, monkeypatch, request):
    from cppulse.report_engine import api

    source = tmp_path / "source"
    source.mkdir()
    (source / "main.cpp").write_text("int value;\n")
    store = RunStore(tmp_path / "store", format_version=request.param)
    snapshot = publish_attempt(store, "first", source, extra_finding=True)
    cache = tmp_path / "query-cache"
    monkeypatch.setenv("DATA_DIR", str(store.root))
    monkeypatch.setenv("CPPULSE_FINDINGS_CACHE_DIR", str(cache))
    monkeypatch.delenv("CPPULSE_FINDINGS_INDEX_LIMITS", raising=False)
    monkeypatch.delenv("CPPULSE_API_KEY", raising=False)
    api._json_cache.clear()
    return TestClient(api.app), store, snapshot, source, cache


def test_original_full_snapshot_is_never_opened_for_indexed_page(indexed, monkeypatch):
    client, store, snapshot, _, cache = indexed
    original = RunStore.open_run
    authority = store.root / (
        "heads.json" if store.format_version == "3.0.0" else "latest_attempt.json"
    )
    before = authority.read_bytes()

    def checked(self, *args, **kwargs):
        assert (
            self.root != store.root
        ), "Findings must not open/materialize the original full snapshot"
        return original(self, *args, **kwargs)

    monkeypatch.setattr(RunStore, "open_run", checked)
    response = client.get("/api/v1/findings", params={"per_page": 2})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["items"] == SAMPLE_FINDINGS["findings"][:2]
    assert body["total"] == 5 and body["total_pages"] == 3
    assert body["source"]["run_id"] == snapshot.run_id
    assert body["source"]["manifest_sha256"] == snapshot.manifest_sha256
    assert body["source"]["input_verification"] == "unverified"
    assert body["read_scope"] == "selected_artifact_only"
    assert body["analysis_cache_eligible"] is False
    assert body["limitations"] and cache.is_dir()
    assert authority.read_bytes() == before
    warm = client.get("/api/v1/findings", params={"page": 3, "per_page": 2}).json()
    assert warm["items"] == [SAMPLE_FINDINGS["findings"][0]]
    assert warm["index"] == body["index"]


def test_corrupt_unselected_artifact_does_not_fabricate_full_run_verification(indexed):
    client, _, snapshot, _, _ = indexed
    (snapshot.path / "legacy/risk_scores.json").write_text("{}")
    response = client.get("/api/v1/findings")
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 5
    assert response.json()["read_scope"] == "selected_artifact_only"
    assert response.json()["analysis_cache_eligible"] is False
    assert client.get("/api/v1/summary").status_code == 503


def test_file_and_literal_text_filters_preserve_duplicate_order(indexed):
    client, _, _, _, _ = indexed
    first = SAMPLE_FINDINGS["findings"][0]
    response = client.get(
        "/api/v1/findings",
        params={
            "file": first["file"],
            "text": first["message"],
            "per_page": 1,
            "page": 2,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [first] and response.json()["total"] == 2
    assert client.get("/api/v1/findings", params={"text": "%"}).json()["total"] == 0
    assert (
        client.get("/api/v1/findings", params={"file": "main.cpp"}).json()["total"] == 0
    )


@pytest.mark.parametrize("status", ["partial", "cancelled"])
def test_incomplete_attempt_refuses_before_cache_creation(indexed, status):
    client, store, _, source, cache = indexed
    publish_attempt(store, "new", source, status=status)
    response = client.get("/api/v1/findings")
    assert response.status_code == 409
    assert response.json()["detail"]["run_id"] == "new"
    assert response.json()["detail"]["status"] == status
    assert not cache.exists()


def test_explicit_pins_select_older_run_and_hold_one_head(indexed, monkeypatch):
    from cppulse.report_engine import api

    client, store, snapshot, source, _ = indexed
    publish_attempt(store, "new", source)
    original = api.make_index_request
    called = []

    def switched(*args, **kwargs):
        if not called:
            called.append(True)
            publish_attempt(store, "third", source, status="partial")
        return original(*args, **kwargs)

    monkeypatch.setattr(api, "make_index_request", switched)
    response = client.get(
        "/api/v1/findings",
        params={"run_id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256},
    )
    assert response.status_code == 200, response.text
    assert response.json()["source"]["run_id"] == "first"
    assert response.json()["total"] == 5
    assert client.get("/api/v1/findings").status_code == 409


@pytest.mark.parametrize(
    "params",
    [
        {"run_id": "first"},
        {"manifest_sha256": "a" * 64},
        {"run_id": "../first", "manifest_sha256": "a" * 64},
        {"run_id": "first\n", "manifest_sha256": "a" * 64},
        {"run_id": "first", "manifest_sha256": "A" * 64},
        {"artifact_id": "findings\n"},
        {"page": str(2**63)},
        {"text": "\0"},
        {"category": "x" * 4097},
        {"text": "é" * 2049},
    ],
)
def test_invalid_pins_and_filters_refuse_without_cache(indexed, params):
    client, _, _, _, cache = indexed
    response = client.get("/api/v1/findings", params=params)
    assert response.status_code == 422, response.text
    assert not cache.exists()


def test_auth_precedes_broken_store_inspection_and_cache(indexed, monkeypatch):
    client, store, _, _, cache = indexed
    (store.root / "store-format.json").write_text("{}")
    monkeypatch.setenv("CPPULSE_API_KEY", "secret")
    assert client.get("/api/v1/findings").status_code == 401
    assert not cache.exists()
    assert (
        client.get(
            "/api/v1/findings", headers={"Authorization": "Bearer secret"}
        ).status_code
        == 503
    )


@pytest.mark.parametrize("mode", ["missing", "corrupt", "selected-artifact"])
def test_broken_source_never_falls_back_to_flat_export(indexed, mode):
    client, store, snapshot, _, _ = indexed
    (store.root / "findings.json").write_text(json.dumps(SAMPLE_FINDINGS))
    authority = store.root / (
        "heads.json" if store.format_version == "3.0.0" else "latest_attempt.json"
    )
    if mode == "missing":
        authority.unlink()
    elif mode == "corrupt":
        authority.write_text("broken")
    else:
        (snapshot.path / "legacy/findings.json").write_text("{}")
    assert client.get("/api/v1/findings").status_code == 503


@pytest.mark.parametrize(
    "value",
    [
        "{}",
        "null",
        "[]",
        '{"max_rows": true}',
        '{"max_rows":1,"max_rows":2}',
        "x" * 4097,
    ],
)
def test_invalid_server_limits_refuse_before_cache_creation(
    indexed, monkeypatch, value
):
    client, _, _, _, cache = indexed
    monkeypatch.setenv("CPPULSE_FINDINGS_INDEX_LIMITS", value)
    response = client.get("/api/v1/findings")
    assert response.status_code == 503, response.text
    assert not cache.exists()


def test_symlink_cache_is_refused(indexed, tmp_path):
    client, _, _, _, cache = indexed
    target = tmp_path / "target"
    target.mkdir()
    cache.symlink_to(target, target_is_directory=True)
    assert client.get("/api/v1/findings").status_code == 503
    assert list(target.iterdir()) == []


def test_cache_database_mutation_refuses_next_page(indexed):
    client, _, _, _, cache = indexed
    first = client.get("/api/v1/findings")
    assert first.status_code == 200
    database = next(cache.glob("*/runs/*/index.sqlite"))
    with database.open("r+b") as stream:
        stream.seek(100)
        stream.write(b"CORRUPT")
    assert client.get("/api/v1/findings").status_code == 503


def test_legacy_flat_filters_remain_available_without_creating_index(
    data_dir, monkeypatch, tmp_path
):
    from cppulse.report_engine import api

    cache = tmp_path / "query-cache"
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.setenv("CPPULSE_FINDINGS_CACHE_DIR", str(cache))
    monkeypatch.delenv("CPPULSE_API_KEY", raising=False)
    response = TestClient(api.app).get(
        "/api/v1/findings", params={"file": "src/utils.cpp", "text": "nullptr"}
    )
    assert response.status_code == 200
    assert response.json()["items"] == [SAMPLE_FINDINGS["findings"][1]]
    assert "source" not in response.json()
    assert not cache.exists()
