"""Public branches forwards to the reviewed local producer without losing scope."""

from pathlib import Path
import json
import pytest
from cppulse.cli import main
import test_branch_delivery as fixtures


@pytest.fixture
def history(tmp_path: Path):
    return fixtures.history.__wrapped__(tmp_path)


def test_public_branch_command_retains_original_pins_and_provider_limits(
    history, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo, ids = history
    config = tmp_path / "branches.json"
    config.write_text(json.dumps(fixtures.config(ids)))
    output = tmp_path / "branch-output"
    assert (
        main(
            [
                "branches",
                "--repo",
                str(repo),
                "--config",
                str(config),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["graph_status"] == "available"
    report = json.loads((output / "report.json").read_text())
    assert report["graph_status"] == "available"
    assert (output / "config.original.json").read_bytes() == config.read_bytes()
    assert "no provider" in json.loads((output / "outcome.json").read_text())["meaning"]


def test_public_branch_command_preserves_repo_when_output_overlaps(
    history, tmp_path: Path
) -> None:
    repo, ids = history
    config = tmp_path / "branches.json"
    config.write_text(json.dumps(fixtures.config(ids)))
    before = fixtures.git(repo, "rev-parse", "HEAD")
    output = repo / "unsafe-output"
    assert (
        main(
            [
                "branches",
                "--repo",
                str(repo),
                "--config",
                str(config),
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert not output.exists()
    assert fixtures.git(repo, "rev-parse", "HEAD") == before
