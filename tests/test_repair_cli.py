"""The public dry-run repair command uses pinned facts and never applies edits."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cppulse.cli import main
from test_repairs import normalized


def test_public_fix_writes_the_same_bound_plan_without_source_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    snapshot = normalized(tmp_path)
    source = tmp_path / "main.cpp"
    before = source.read_bytes()
    output = tmp_path / "review-plan.json"
    assert (
        main(
            [
                "fix",
                "--store",
                str(tmp_path / "store"),
                "--workspace",
                str(tmp_path),
                "--run-id",
                snapshot.run_id,
                "--manifest-sha256",
                snapshot.manifest_sha256,
                "--output",
                str(output),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    plan = json.loads(output.read_text())
    assert result["source_modified"] is False
    assert result["edits"] == 1
    assert plan["run"]["manifest_sha256"] == snapshot.manifest_sha256
    assert "using Count = unsigned long;" in plan["diff"]
    assert source.read_bytes() == before


def test_source_application_is_not_implicitly_exposed(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as error:
        main(
            [
                "fix",
                "--store",
                str(tmp_path),
                "--workspace",
                str(tmp_path),
                "--run-id",
                "run",
                "--manifest-sha256",
                "a" * 64,
                "--output",
                str(tmp_path / "plan.json"),
                "--apply",
            ]
        )
    assert error.value.code == 2
