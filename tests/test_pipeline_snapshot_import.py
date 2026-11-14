"""Import existing pipeline bytes without manufacturing historical source proof."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cppulse.run_store import RunStore
from cppulse.run_store import StagedRun
from cppulse.errors import InputChanged
from scripts.import_pipeline_run import import_pipeline


@pytest.fixture
def bundle(tmp_path: Path) -> tuple[Path, Path, Path]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "sample.cpp").write_text("int value = 1;\n")
    output = tmp_path / "flat"
    output.mkdir()
    documents = {
        "findings": {
            "version": "1.0.0",
            "metadata": {
                "repo_path": str(source),
                "analyzed_at": "2026-11-13T10:00:00Z",
                "file_count": 1,
                "total_loc": 1,
                "analysis": {
                    "enabled_rules": ["CPP-MOD-001"],
                    "files": [
                        {
                            "path": str(source / "sample.cpp"),
                            "status": "analyzed",
                            "compile_context": "fallback",
                            "error_count": 0,
                        }
                    ],
                },
            },
            "findings": [],
            "summary": {"total_findings": 0, "by_category": {}, "by_severity": {}},
        },
        "git_metrics": {
            "version": "1.0.0",
            "metadata": {
                "repo_path": str(source),
                "analyzed_at": "2026-11-13T10:00:00Z",
                "commit_range": "N/A",
                "total_commits": 0,
                "history_status": "unavailable",
            },
            "file_metrics": [],
            "knowledge_silos": [],
        },
        "risk_scores": {
            "version": "1.0.0",
            "metadata": {
                "generated_at": "2026-11-13T10:00:00Z",
                "model_type": "heuristic",
                "feature_count": 5,
            },
            "health_score": {
                "overall": 100,
                "by_category": {"modernization": 100},
                "status": "scored",
            },
            "file_risks": [
                {
                    "file": "sample.cpp",
                    "bug_probability": 0,
                    "risk_level": "low",
                    "top_factors": [],
                }
            ],
            "hotspots": [],
        },
        "roadmap": {"version": "1.0.0", "items": []},
    }
    for name, document in documents.items():
        (output / f"{name}.json").write_text(json.dumps(document, indent=2))
    return output, source, tmp_path / "store"


def test_archive_retains_bytes_and_marks_binding_unverified(
    bundle: tuple[Path, Path, Path]
) -> None:
    output, source, store = bundle
    result = import_pipeline(output, source, store, run_id="example")
    assert result["input_verification"] == "unverified"
    snapshot = RunStore(store).resolve_latest_attempt()
    for name in ["findings", "git_metrics", "risk_scores", "roadmap"]:
        assert snapshot.read_bytes(name) == (output / f"{name}.json").read_bytes()
    normalized = snapshot.read_json("normalized-risk")
    assert normalized["health_score"]["overall"] is None
    assert normalized["health_score"]["availability"] == "unverified"
    assert normalized["legacy_observed_health"] == 100
    assert snapshot.manifest["contexts"] == []


def test_mismatched_source_root_cannot_be_attached(
    bundle: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    output, _, store = bundle
    wrong = tmp_path / "other"
    wrong.mkdir()
    with pytest.raises(ValueError, match="source root"):
        import_pipeline(output, wrong, store)


def test_original_output_edits_do_not_change_archive(
    bundle: tuple[Path, Path, Path]
) -> None:
    output, source, store = bundle
    import_pipeline(output, source, store, run_id="archive")
    snapshot = RunStore(store).open_run("archive")
    before = snapshot.read_bytes("risk_scores")
    (output / "risk_scores.json").write_text("{}")
    assert snapshot.read_bytes("risk_scores") == before
    snapshot.verify()


def test_import_summary_pins_its_run_after_latest_changes(
    bundle: tuple[Path, Path, Path]
) -> None:
    """A client never needs to resolve mutable latest to recover its own result."""
    output, source, store = bundle
    first = import_pipeline(output, source, store, run_id="first-client")
    second = import_pipeline(output, source, store, run_id="second-client")
    selected = RunStore.open_existing(store).open_run(
        first["run_id"], manifest_sha256=first["manifest_sha256"]
    )
    assert selected.run_id == "first-client"
    assert first["manifest_sha256"] != second["manifest_sha256"]
    assert (
        RunStore.open_existing(store).resolve_latest_attempt().run_id == "second-client"
    )


def test_changed_artifact_cannot_publish_mixed_import(
    bundle: tuple[Path, Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    output, source, store = bundle
    original_copy = StagedRun.copy_artifact

    def change_before_copy(
        self: StagedRun, id: str, *args: object, **kwargs: object
    ) -> dict:
        if id == "risk_scores":
            path = output / "risk_scores.json"
            changed = json.loads(path.read_bytes())
            changed["health_score"]["overall"] = 23
            path.write_text(json.dumps(changed))
        return original_copy(self, id, *args, **kwargs)

    monkeypatch.setattr(StagedRun, "copy_artifact", change_before_copy)
    with pytest.raises(InputChanged, match="changed while copying"):
        import_pipeline(output, source, store, run_id="changed")
    assert not (store / "latest.json").exists()
    assert not (store / "latest_attempt.json").exists()
    assert not (store / "runs" / "changed").exists()
