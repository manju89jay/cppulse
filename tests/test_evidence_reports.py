"""Explicit evidence reports preserve the default legacy report contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cppulse.contracts import validate
from cppulse.errors import ContractError, IntegrityError
from cppulse.pipeline import generate_report
from test_presentation import legacy_documents, publish_snapshot


@pytest.mark.parametrize("format", ["json", "html", "pdf"])
def test_explicit_evidence_report_uses_same_checked_run_without_legacy_documents(
    tmp_path: Path, format: str
) -> None:
    snapshot = publish_snapshot(tmp_path, gate="failed")
    result = generate_report(snapshot.path.parent.parent, format, evidence=True)
    path = Path(result["report"])
    assert path.name == "evidence-report." + format
    assert result["run_id"] == snapshot.run_id
    assert result["manifest_sha256"] == snapshot.manifest_sha256
    assert result["mode"] == "snapshot_view"
    assert result["bytes"] == path.stat().st_size > 0
    if format == "json":
        view = json.loads(path.read_text())
        validate("snapshot_view", view)
        assert view["assessment"]["display"]["gate"] == "failed"
    elif format == "html":
        assert "failed" in path.read_text()
    else:
        assert path.read_bytes().startswith(b"%PDF-")
    snapshot.verify()


def test_default_flat_json_report_shape_is_unchanged(tmp_path: Path) -> None:
    inputs = tmp_path / "flat"
    inputs.mkdir()
    for name, document in legacy_documents().items():
        (inputs / (name + ".json")).write_text(json.dumps(document))
    result = generate_report(inputs, "json")
    assert json.loads(Path(result["report"]).read_text()) == legacy_documents()
    with pytest.raises(ContractError):
        generate_report(inputs, "json", evidence=True)


def test_evidence_default_filename_preserves_old_export(tmp_path: Path) -> None:
    snapshot = publish_snapshot(tmp_path)
    store = snapshot.path.parent.parent
    old = store / "report.json"
    old.write_text("existing unrelated legacy export")
    generate_report(store, "json", evidence=True)
    assert old.read_text() == "existing unrelated legacy export"


def test_named_report_pins_historical_run_while_current_pointer_changes(
    tmp_path: Path,
) -> None:
    first = publish_snapshot(tmp_path, run_id="first", gate="passed")
    second = publish_snapshot(tmp_path, run_id="second", gate="failed")
    store = first.path.parent.parent
    result = generate_report(
        store,
        "json",
        evidence=True,
        run_id=first.run_id,
        manifest_sha256=first.manifest_sha256,
    )
    view = json.loads(Path(result["report"]).read_text())
    assert view["run"]["id"] == "first"
    assert view["assessment"]["display"]["gate"] == "passed"
    current = generate_report(store, "json", evidence=True)
    assert current["run_id"] == second.run_id
    with pytest.raises(IntegrityError):
        generate_report(
            store, "json", evidence=True, run_id="first", manifest_sha256="0" * 64
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"run_id": "first"},
        {"manifest_sha256": "0" * 64},
        {"assessment_artifact_id": "selected-assessment"},
    ],
)
def test_partial_or_ignored_report_selectors_are_rejected(
    tmp_path: Path, kwargs: dict
) -> None:
    snapshot = publish_snapshot(tmp_path)
    with pytest.raises(ContractError):
        generate_report(snapshot.path.parent.parent, "json", **kwargs)


@pytest.mark.parametrize("status", ["partial", "cancelled"])
def test_evidence_reports_expose_incomplete_attempt_instead_of_old_success(
    tmp_path: Path, status: str
) -> None:
    first = publish_snapshot(tmp_path, run_id="old")
    latest = publish_snapshot(tmp_path, run_id="current", status=status, assessed=False)
    result = generate_report(first.path.parent.parent, "json", evidence=True)
    view = json.loads(Path(result["report"]).read_text())
    assert view["run"]["id"] == latest.run_id
    assert view["run"]["status"] == status
    assert view["assessment"] is None
    with pytest.raises(RuntimeError):
        generate_report(first.path.parent.parent, "json")


def test_concrete_snapshot_selection_and_report_output_cannot_modify_store_metadata(
    tmp_path: Path,
) -> None:
    snapshot = publish_snapshot(tmp_path)
    result = generate_report(snapshot.path, "json", evidence=True)
    assert snapshot.run_id in result["report"]
    for path in [
        snapshot.path / "new.json",
        snapshot.path / "run_manifest.json",
        snapshot.path.parent.parent / "latest_attempt.json",
    ]:
        with pytest.raises(ContractError):
            generate_report(snapshot.path, "json", path, evidence=True)
    snapshot.verify()
