"""One API view and its downloads retain the same explicit immutable run pin."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

from cppulse.contracts import validate
from cppulse.errors import CppulseError
from cppulse.run_store import RunSnapshot, RunStore
from .test_run_snapshot_api import publish_attempt, snapshot_api as _snapshot_fixture

snapshot_api = _snapshot_fixture


def pin(snapshot: RunSnapshot) -> dict[str, str]:
    """Select both the retained run identity and original manifest hash."""
    return {"run_id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256}


def test_consolidated_view_binds_every_legacy_section_to_one_attempt(
    snapshot_api: tuple[TestClient, RunStore, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, store, source = snapshot_api
    first = publish_attempt(store, "first", source, score=10)
    original = RunSnapshot.read_bytes
    changed = False

    def read(snapshot: RunSnapshot, name: str) -> bytes:
        nonlocal changed
        content = original(snapshot, name)
        if snapshot.run_id == "first" and name == "risk_scores" and not changed:
            changed = True
            publish_attempt(store, "second", source, score=90, extra_finding=True)
        return content

    monkeypatch.setattr(RunSnapshot, "read_bytes", read)
    response = client.get("/api/v1/view")
    assert response.status_code == 200, response.text
    view = response.json()
    validate("snapshot_view", view)
    assert view["run"]["id"] == first.run_id
    assert view["run"]["manifest_sha256"] == first.manifest_sha256
    assert view["legacy"]["risk_scores"]["document"]["health_score"]["overall"] == 10
    assert view["legacy"]["findings"]["document"]["summary"]["total_findings"] == 4
    assert client.get("/api/v1/view").json()["run"]["id"] == "second"


def test_named_view_stays_pinned_after_current_pointer_advances(
    snapshot_api: tuple[TestClient, RunStore, Path],
) -> None:
    client, store, source = snapshot_api
    first = publish_attempt(store, "first", source, score=10)
    publish_attempt(store, "later", source, score=90)
    response = client.get("/api/v1/view", params=pin(first))
    assert response.status_code == 200
    assert response.json()["run"]["id"] == "first"
    assert (
        response.json()["legacy"]["risk_scores"]["document"]["health_score"]["overall"]
        == 10
    )


@pytest.mark.parametrize("status", ["partial", "cancelled"])
def test_current_incomplete_view_exposes_its_facts_and_never_older_results(
    snapshot_api: tuple[TestClient, RunStore, Path], status: str
) -> None:
    client, store, source = snapshot_api
    publish_attempt(store, "old-completed", source, score=99)
    current = publish_attempt(store, "current", source, status=status)
    response = client.get("/api/v1/view")
    assert response.status_code == 200
    view = response.json()
    validate("snapshot_view", view)
    assert view["run"]["id"] == current.run_id
    assert view["run"]["status"] == status
    assert view["assessment"] is None
    assert all(value is None for value in view["legacy"].values())
    assert view["stages"][0]["status"] in {"error", "cancelled"}
    assert view["gaps"]


@pytest.mark.parametrize(
    "params",
    [
        {"run_id": "current"},
        {"manifest_sha256": "a" * 64},
        {"run_id": "../outside", "manifest_sha256": "a" * 64},
        {"run_id": "current", "manifest_sha256": "invalid"},
    ],
)
def test_view_refuses_partial_or_malformed_run_pins(
    snapshot_api: tuple[TestClient, RunStore, Path], params: dict[str, str]
) -> None:
    client, store, source = snapshot_api
    publish_attempt(store, "current", source)
    response = client.get("/api/v1/view", params=params)
    assert response.status_code == 422


def test_wrong_manifest_hash_never_reselects_current_or_flat_results(
    snapshot_api: tuple[TestClient, RunStore, Path],
) -> None:
    client, store, source = snapshot_api
    snapshot = publish_attempt(store, "current", source)
    selected = pin(snapshot)
    selected["manifest_sha256"] = "0" * 64
    assert client.get("/api/v1/view", params=selected).status_code == 503


def test_exact_artifact_download_is_pinned_even_when_current_is_incomplete(
    snapshot_api: tuple[TestClient, RunStore, Path],
) -> None:
    client, store, source = snapshot_api
    selected = publish_attempt(store, "selected", source)
    publish_attempt(store, "current", source, status="cancelled")
    response = client.get(
        f"/api/v1/runs/{selected.run_id}/artifacts/findings",
        params={"manifest_sha256": selected.manifest_sha256},
    )
    assert response.status_code == 200
    assert response.content == selected.read_bytes("findings")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in response.headers["content-disposition"]
    assert (
        client.get(f"/api/v1/runs/{selected.run_id}/artifacts/findings").status_code
        == 422
    )
    assert (
        client.get(
            f"/api/v1/runs/{selected.run_id}/artifacts/findings",
            params={"manifest_sha256": "0" * 64},
        ).status_code
        == 503
    )
    assert (
        client.get(
            f"/api/v1/runs/{selected.run_id}/artifacts/missing",
            params={"manifest_sha256": selected.manifest_sha256},
        ).status_code
        == 404
    )


def test_named_reads_do_not_depend_on_or_repair_a_corrupt_current_pointer(
    snapshot_api: tuple[TestClient, RunStore, Path],
) -> None:
    client, store, source = snapshot_api
    selected = publish_attempt(store, "selected", source)
    current_pointer = store.root / (
        "heads.json" if store.format_version == "3.0.0" else "latest_attempt.json"
    )
    assert current_pointer.is_file()
    damage = "corrupt current pointer"
    current_pointer.write_text(damage)
    assert client.get("/api/v1/view").status_code == 503
    assert client.get("/api/v1/view", params=pin(selected)).status_code == 200
    assert current_pointer.read_text() == damage


def test_view_reader_never_creates_writer_state_or_upgrades_source_claims(
    snapshot_api: tuple[TestClient, RunStore, Path],
) -> None:
    client, store, source = snapshot_api
    selected = publish_attempt(store, "selected", source)
    (store.root / ".staging").rmdir()
    source.joinpath("main.cpp").unlink()
    before = sorted(path.relative_to(store.root) for path in store.root.rglob("*"))
    response = client.get("/api/v1/view")
    assert response.status_code == 200
    assert response.json()["run"]["input_verification"] == "unverified"
    assert (
        response.json()["run"]["source_digest"] == selected.manifest["source"]["digest"]
    )
    assert (
        sorted(path.relative_to(store.root) for path in store.root.rglob("*")) == before
    )


def test_view_and_download_authenticate_before_exposing_run_state(
    snapshot_api: tuple[TestClient, RunStore, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    client, store, source = snapshot_api
    selected = publish_attempt(store, "selected", source)
    monkeypatch.setenv("CPPULSE_API_KEY", "local-test-key")
    for endpoint in ("view", "report.pdf", "report.html"):
        assert client.get(f"/api/v1/{endpoint}").status_code == 401
    url = f"/api/v1/runs/{selected.run_id}/artifacts/findings"
    assert (
        client.get(
            url, params={"manifest_sha256": selected.manifest_sha256}
        ).status_code
        == 401
    )
    authorized = {"Authorization": "Bearer local-test-key"}
    assert client.get("/api/v1/view", headers=authorized).status_code == 200
    assert (
        client.get(
            url,
            params={"manifest_sha256": selected.manifest_sha256},
            headers=authorized,
        ).status_code
        == 200
    )


def test_flat_view_is_explicit_legacy_unverified_and_has_no_fake_pin(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cppulse.report_engine import api

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.delenv("CPPULSE_API_KEY", raising=False)
    response = TestClient(api.app).get("/api/v1/view")
    assert response.status_code == 200
    document: dict[str, Any] = response.json()
    assert document["mode"] == "legacy-flat"
    assert document["input_verification"] == "unverified"
    assert "run" not in document
    assert set(document["legacy"]) == {
        "findings",
        "git_metrics",
        "risk_scores",
        "roadmap",
    }
    assert document["legacy"]["findings"]["document"]["summary"]["total_findings"] == 4
    assert all("artifact_id" not in value for value in document["legacy"].values())
    assert document["limitations"]


def test_snapshot_pdf_uses_the_same_named_view_and_http_base_url(
    snapshot_api: tuple[TestClient, RunStore, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from cppulse import presentation

    client, store, source = snapshot_api
    selected = publish_attempt(store, "selected", source)
    publish_attempt(store, "current", source, status="partial")
    captured = []

    def render(view: dict[str, Any], *, base_url: str | None = None) -> bytes:
        captured.append((view["run"], base_url))
        return b"%PDF-1.4\nSynthetic HTTP transport fixture, not a rendered PDF.\n"

    monkeypatch.setattr(presentation, "render_snapshot_pdf", render)
    response = client.get("/api/v1/report.pdf", params=pin(selected))
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF")
    assert response.headers["content-type"] == "application/pdf"
    assert "attachment" in response.headers["content-disposition"]
    assert captured[0][0]["id"] == selected.run_id
    assert captured[0][0]["manifest_sha256"] == selected.manifest_sha256
    assert captured[0][1] == "http://testserver/"
    bad = {**pin(selected), "manifest_sha256": "0" * 64}
    assert client.get("/api/v1/report.pdf", params=bad).status_code == 503
    assert len(captured) == 1


def test_snapshot_pdf_dependency_failure_is_actionable_and_never_uses_flat_pdf(
    snapshot_api: tuple[TestClient, RunStore, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from cppulse import presentation

    client, store, source = snapshot_api
    selected = publish_attempt(store, "selected", source)
    (store.root / "report.pdf").write_bytes(b"old flat PDF must not be selected")

    def unavailable(view: dict[str, Any], *, base_url: str | None = None) -> bytes:
        raise CppulseError("Install cppulse[pdf] and required WeasyPrint libraries.")

    monkeypatch.setattr(presentation, "render_snapshot_pdf", unavailable)
    response = client.get("/api/v1/report.pdf", params=pin(selected))
    assert response.status_code == 503
    assert "cppulse[pdf]" in response.text


def test_snapshot_html_preserves_current_incomplete_status_without_legacy_data(
    snapshot_api: tuple[TestClient, RunStore, Path],
) -> None:
    client, store, source = snapshot_api
    selected = publish_attempt(store, "current", source, status="cancelled")
    response = client.get("/api/v1/report.html", params=pin(selected))
    assert response.status_code == 200
    assert "cancelled" in response.text
    assert selected.manifest_sha256 in response.text
    assert "No stored assessment" in response.text


@pytest.mark.parametrize(
    "media_type", ["application/☃", "text/plain\r\nX-Untrusted: yes"]
)
def test_raw_descriptor_media_type_cannot_become_an_invalid_http_header(
    snapshot_api: tuple[TestClient, RunStore, Path], media_type: str
) -> None:
    client, store, source = snapshot_api
    parent = publish_attempt(store, "parent", source)
    with store.begin("valid-contract-odd-media") as stage:
        stage.copy_artifact(
            "odd-media", source / "main.cpp", "raw/blob.bin", media_type
        )
        manifest = parent.manifest
        manifest.update(run_id="valid-contract-odd-media", artifacts=stage.artifacts)
        selected = stage.publish(manifest)
    response = client.get(
        f"/api/v1/runs/{selected.run_id}/artifacts/odd-media",
        params={"manifest_sha256": selected.manifest_sha256},
    )
    assert response.status_code == 200
    assert response.content == source.joinpath("main.cpp").read_bytes()
    assert response.headers["content-type"] == "application/octet-stream"
    assert selected.manifest["artifacts"][0]["media_type"] == media_type
