"""Explicit measured scoring scope crosses the public CLI without tool execution."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from cppulse.cli import main


def test_maintenance_requires_declared_contexts() -> None:
    with pytest.raises(SystemExit) as error:
        main(["maintenance", "--store", "/tmp/store", "--workspace", "/tmp/source"])
    assert error.value.code == 2


def test_maintenance_dispatches_explicit_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import cppulse.cli as cli
    import cppulse.maintenance as maintenance

    import cppulse.workflows as workflows

    health = {
        "aggregate": {"overall": 90},
        "scorer": {
            "id": "analyzed-kloc-context-v4",
            "profile": "default",
            "allow_inferred_parse": False,
        },
        "required_context_ids": ["debug", "release"],
        "optional_context_ids": ["experimental"],
        "contexts": [],
        "consumer_assurance": "not_assessed",
    }
    monkeypatch.setattr(
        workflows,
        "read_documents",
        lambda _: {
            "maintenance_health": [
                health,
                {
                    **health,
                    "required_context_ids": ["debug"],
                    "aggregate": {"overall": 100},
                },
            ]
        },
    )
    selected = object()
    monkeypatch.setattr(cli, "_selected_run", lambda _: selected)
    received = {}

    def persist(snapshot: object, **kwargs: object) -> object:
        assert snapshot is selected
        received.update(kwargs)
        return SimpleNamespace(run_id="derived", manifest_sha256="a" * 64)

    monkeypatch.setattr(maintenance, "persist_maintenance_health", persist)
    assert (
        main(
            [
                "maintenance",
                "--store",
                str(tmp_path / "store"),
                "--workspace",
                str(tmp_path),
                "--required-context",
                "debug",
                "--required-context",
                "release",
                "--optional-context",
                "experimental",
            ]
        )
        == 0
    )
    assert received["required_context_ids"] == ["debug", "release"]
    assert received["optional_context_ids"] == ["experimental"]
    assert received["allow_inferred_parse"] is False
    output = capsys.readouterr().out
    assert '"run_id": "derived"' in output
    assert '"overall": 90' in output


def test_missing_required_context_cli_publishes_explicit_incomplete_result(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json
    from test_analysis_inventory import native_snapshot
    from test_measured_normalization import add_metrics
    from cppulse.analysis import persist_native_analysis
    from cppulse.tooling import load_rule_registry

    snapshot, selection = native_snapshot(tmp_path, mutate=add_metrics)
    selection["requested_rules"] = [row["id"] for row in load_rule_registry()["rules"]]
    normalized = persist_native_analysis(
        snapshot, workspace=tmp_path, store=tmp_path / "store", **selection
    )
    code = main(
        [
            "maintenance",
            "--store",
            str(tmp_path / "store"),
            "--workspace",
            str(tmp_path),
            "--run-id",
            normalized.run_id,
            "--manifest-sha256",
            normalized.manifest_sha256,
            "--required-context",
            "native",
            "--required-context",
            "missing-consumer",
        ]
    )
    assert code == 3
    result = json.loads(capsys.readouterr().out)
    assert result["maintenance"]["overall"] is None
    assert result["maintenance"]["incomplete_required_context_ids"] == [
        "missing-consumer"
    ]
    assert result["consumer_assurance"] == "not_assessed"
