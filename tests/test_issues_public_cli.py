"""The shared CLI forwards to the bounded read-only issue invocation boundary."""

from pathlib import Path
import json
import pytest
from cppulse.cli import main
import cppulse.issue_tracker_cli as boundary
from cppulse.issue_tracker import collect
from test_issue_tracker import request, issue, transport


def test_shared_issue_command_preserves_partial_unknown_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = request()
    config["limits"]["pages"] = 1
    source = tmp_path / "request.json"
    source.write_text(json.dumps(config))
    output = tmp_path / "result"

    def actual_producer(config, output):
        return collect(
            config,
            output,
            transport=transport(
                [issue()],
                {
                    "Link": '<https://api.github.com/repos/manju89jay/cppulse/issues?page=2>; rel="next"'
                },
            ),
        )

    monkeypatch.setattr(boundary, "collect", actual_producer)
    assert main(["issues", "--request", str(source), "--output", str(output)]) == 3
    result = json.loads(capsys.readouterr().out)
    assert result["report_status"] == "partial"
    assert (
        json.loads((output / "observations/report.json").read_text())["issue_count"]
        is None
    )
    assert (output / "request.original.json").read_bytes() == source.read_bytes()


def test_shared_issue_command_validates_before_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "request.json"
    source.write_text('{"provider":"unsupported"}')
    monkeypatch.setattr(
        boundary, "collect", lambda *_: pytest.fail("Provider must not run")
    )
    output = tmp_path / "result"
    assert main(["issues", "--request", str(source), "--output", str(output)]) == 2
    assert not output.exists()
