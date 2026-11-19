"""Actual source-race controls after final typed facts have been staged."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cppulse.errors import InputChanged
from cppulse.pipeline import analyze
from cppulse.run_store import RunStore
from cppulse.workflows import read_documents
import cppulse.work_unit_analysis as bridge
import test_bounded_pipeline as fixtures


def test_source_change_after_typed_append_preserves_pending_and_never_demotes_facts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = fixtures.config(tmp_path)
    (config.repo / "compile_commands.json").write_text(
        json.dumps(
            [
                {
                    "directory": str(config.repo),
                    "file": str(config.repo / "main.cpp"),
                    "arguments": [
                        "clang++",
                        "-std=c++17",
                        "-c",
                        str(config.repo / "main.cpp"),
                    ],
                }
            ]
        )
    )
    fixtures.select_native(monkeypatch, fixtures.native.__wrapped__())
    first = analyze(config, report_format="json", timeout=60)
    store = RunStore(config.output)
    baseline = store.open_run(first["run_id"])
    baseline.verify()
    original = bridge.append_work_unit_analysis
    pending: list[tuple[Path, dict[str, Any]]] = []

    def change_after_append(stage: Any, material: Any, **kwargs: Any) -> dict[str, Any]:
        result = original(stage, material, **kwargs)
        if not pending:
            pending.append((stage.path, result))
            (config.repo / "main.cpp").write_text("int changed_after_typed_append;\n")
        return result

    monkeypatch.setattr(bridge, "append_work_unit_analysis", change_after_append)
    with pytest.raises(InputChanged):
        analyze(config, report_format="json", timeout=60)
    assert store.resolve_latest().run_id == baseline.run_id
    attempt = store.resolve_latest_attempt()
    assert attempt.run_id != baseline.run_id
    assert attempt.manifest["status"] == "partial"
    assert attempt.manifest["input_verification"] == "unverified"
    assert all(
        health["aggregate"]["overall"] is None
        for health in read_documents(attempt).get("maintenance_health", [])
    )
    path, declaration = pending[0]
    assert path.is_dir()
    assert not (path / "run_manifest.json").exists()
    assert not (store.root / "runs" / declaration["run_id"]).exists()
    kinds = {row.get("contract", {}).get("kind") for row in declaration["artifacts"]}
    assert {"analysis_scope", "maintenance_health"} <= kinds
    # The unpublished positive facts remain diagnostic bytes, rather than being
    # rewritten as if their earlier measured observation had never existed.
    for row in declaration["artifacts"]:
        assert (path / row["path"]).is_file()
    assert not (store.root / ".publication.lock").exists()
