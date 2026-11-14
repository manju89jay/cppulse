"""HTTP requests bind one checked attempt instead of mutable flat export files."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from cppulse.identities import digest_json, snapshot_inputs
from cppulse.run_store import RunSnapshot, RunStore
from .conftest import (
    SAMPLE_FINDINGS,
    SAMPLE_GIT_METRICS,
    SAMPLE_RISK_SCORES,
    SAMPLE_ROADMAP,
)


def publish_attempt(
    store: RunStore,
    run_id: str,
    source: Path,
    *,
    status: str = "completed",
    score: float = 10,
    extra_finding: bool = False,
    pdf: bytes | None = None,
) -> RunSnapshot:
    """Persist synthetic transport facts; no analyzer or test execution is claimed."""
    documents = {
        "findings": deepcopy(SAMPLE_FINDINGS),
        "git_metrics": deepcopy(SAMPLE_GIT_METRICS),
        "risk_scores": deepcopy(SAMPLE_RISK_SCORES),
        "roadmap": deepcopy(SAMPLE_ROADMAP),
    }
    documents["risk_scores"]["health_score"]["overall"] = score
    if extra_finding:
        findings = documents["findings"]
        findings["findings"].append(deepcopy(findings["findings"][0]))
        findings["summary"]["total_findings"] += 1
        findings["summary"]["by_category"]["memory_safety"] += 1
        findings["summary"]["by_severity"]["error"] += 1
    time = datetime.now(timezone.utc).isoformat()
    with store.begin(run_id) as stage:
        if status == "completed":
            for kind, document in documents.items():
                stage.write_json(
                    f"legacy/{kind}.json",
                    document,
                    artifact_id=kind,
                    contract=(kind, "prototype_v1"),
                )
            if pdf is not None:
                source_pdf = source / f"{run_id}.pdf"
                source_pdf.write_bytes(pdf)
                stage.copy_artifact(
                    "report-pdf", source_pdf, "report.pdf", "application/pdf"
                )
        return stage.publish(
            {
                "version": "2.0.0",
                "run_id": run_id,
                "status": status,
                "source": snapshot_inputs(source, ["main.cpp"]),
                "contexts": [],
                "stages": [
                    {
                        "id": "synthetic-archive",
                        "status": (
                            "passed"
                            if status == "completed"
                            else "cancelled" if status == "cancelled" else "error"
                        ),
                        "depends_on": [],
                        "reason": "Synthetic transport fixture",
                    }
                ],
                "artifacts": stage.artifacts,
                "started_at": time,
                "finished_at": time,
                "config_digest": digest_json({}),
                "versions": {"cppulse": "0.2.0.dev0"},
                "limitations": [
                    "Synthetic API transport fixture; no producer execution was performed."
                ],
            }
        )


@pytest.fixture()
def snapshot_api(
    tmp_path: Path,
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[TestClient, RunStore, Path]:
    """Start with valid old flat data which stored attempts must take precedence over."""
    from cppulse.report_engine import api

    source = tmp_path / "source"
    source.mkdir()
    (source / "main.cpp").write_text("int value = 0;\n")
    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.delenv("CPPULSE_API_KEY", raising=False)
    api._json_cache.clear()
    return TestClient(api.app), RunStore(data_dir), source


def test_summary_binds_snapshot_once_when_latest_changes_between_reads(
    snapshot_api: tuple[TestClient, RunStore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, store, source = snapshot_api
    publish_attempt(store, "first", source, score=10)
    original_read = RunSnapshot.read_bytes
    original_resolve = RunStore.resolve_latest_attempt
    resolutions: list[str] = []
    changed = False

    def resolve(self: RunStore) -> RunSnapshot:
        result = original_resolve(self)
        resolutions.append(result.run_id)
        return result

    def read(self: RunSnapshot, name: str) -> bytes:
        nonlocal changed
        content = original_read(self, name)
        if self.run_id == "first" and name == "risk_scores" and not changed:
            changed = True
            publish_attempt(store, "second", source, score=90, extra_finding=True)
        return content

    monkeypatch.setattr(RunStore, "resolve_latest_attempt", resolve)
    monkeypatch.setattr(RunSnapshot, "read_bytes", read)
    response = client.get("/api/v1/summary")
    assert response.status_code == 200
    assert response.json()["health_score"]["overall"] == 10
    assert response.json()["findings_summary"]["total_findings"] == 4
    assert resolutions == ["first"]
    response = client.get("/api/v1/summary")
    assert response.json()["health_score"]["overall"] == 90
    assert response.json()["findings_summary"]["total_findings"] == 5
    assert resolutions == ["first", "second"]


@pytest.mark.parametrize("status", ["partial", "cancelled"])
def test_incomplete_attempt_blocks_all_data_despite_old_completed_and_flat_outputs(
    snapshot_api: tuple[TestClient, RunStore, Path],
    status: str,
) -> None:
    client, store, source = snapshot_api
    publish_attempt(store, "completed", source)
    publish_attempt(store, "current", source, status=status)
    (store.root / "report.pdf").write_bytes(b"old flat transport fixture")
    for endpoint in (
        "summary",
        "findings",
        "hotspots",
        "risks",
        "silos",
        "roadmap",
        "report/pdf",
    ):
        response = client.get(f"/api/v1/{endpoint}")
        assert response.status_code == 409, (endpoint, response.text)
        assert response.json()["detail"]["status"] == status
        assert response.json()["detail"]["run_id"] == "current"
    current = client.get("/api/v1/run")
    assert current.status_code == 200
    assert current.json()["manifest"]["status"] == status
    assert current.json()["manifest"]["input_verification"] == "unverified"
    assert client.get("/health").json() == {"status": "ok"}


def test_missing_snapshot_pdf_never_uses_flat_pdf_or_generates_a_replacement(
    snapshot_api: tuple[TestClient, RunStore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cppulse.report_engine.api import PDFGenerator

    client, store, source = snapshot_api
    publish_attempt(store, "current", source)
    (store.root / "report.pdf").write_bytes(b"old flat transport fixture")

    def reject_generation(self: PDFGenerator) -> bytes:
        raise AssertionError("Snapshot PDF must be an inventoried artifact")

    monkeypatch.setattr(PDFGenerator, "generate_pdf", reject_generation)
    response = client.get("/api/v1/report/pdf")
    assert response.status_code == 404
    assert "current" in response.text


def test_pdf_returns_current_checked_artifact(
    snapshot_api: tuple[TestClient, RunStore, Path],
) -> None:
    client, store, source = snapshot_api
    transport_fixture = b"%PDF-1.4\nSynthetic transport bytes, not a rendered report.\n"
    publish_attempt(store, "current", source, pdf=transport_fixture)
    response = client.get("/api/v1/report/pdf")
    assert response.status_code == 200
    assert response.content == transport_fixture
    assert response.headers["content-type"] == "application/pdf"


@pytest.mark.parametrize("corruption", ["pointer", "missing_pointer", "artifact"])
def test_corrupt_store_never_falls_back_to_valid_flat_files(
    snapshot_api: tuple[TestClient, RunStore, Path],
    corruption: str,
) -> None:
    client, store, source = snapshot_api
    snapshot = publish_attempt(store, "current", source)
    if corruption == "pointer":
        (store.root / "latest_attempt.json").write_text("not JSON")
    elif corruption == "missing_pointer":
        (store.root / "latest_attempt.json").unlink()
    else:
        (snapshot.path / "legacy/risk_scores.json").write_text("{}")
    assert client.get("/api/v1/summary").status_code == 503
    assert client.get("/api/v1/run").status_code == 503
    assert client.get("/health").status_code == 200


def test_run_metadata_and_store_failures_are_protected_by_api_key(
    snapshot_api: tuple[TestClient, RunStore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, store, _ = snapshot_api
    (store.root / "latest_attempt.json").write_text("not JSON")
    monkeypatch.setenv("CPPULSE_API_KEY", "test-key")
    assert client.get("/api/v1/run").status_code == 401
    assert client.get("/api/v1/summary").status_code == 401
    assert (
        client.get(
            "/api/v1/run", headers={"Authorization": "Bearer test-key"}
        ).status_code
        == 503
    )


def test_flat_run_endpoint_explicitly_describes_unverified_legacy_mode(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cppulse.report_engine import api

    monkeypatch.setenv("DATA_DIR", str(data_dir))
    monkeypatch.delenv("CPPULSE_API_KEY", raising=False)
    response = TestClient(api.app).get("/api/v1/run")
    assert response.status_code == 200
    assert response.json()["mode"] == "legacy-flat"
    assert response.json()["input_verification"] == "unverified"
