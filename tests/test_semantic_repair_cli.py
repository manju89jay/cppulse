"""Public proposal verification requires explicit execution and fresh retained facts."""

from pathlib import Path
import json
import pytest
from cppulse.cli import main
from test_semantic_repair import failing_project


def test_public_proposal_requires_execution_authorization(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as error:
        main(
            [
                "verify-proposal",
                "--store",
                str(tmp_path),
                "--workspace",
                str(tmp_path),
                "--request",
                str(tmp_path / "request.json"),
                "--output-root",
                str(tmp_path),
            ]
        )
    assert error.value.code == 2


def test_public_proposal_retains_actual_test_failure_and_fresh_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    before, request = failing_project(source)
    original = (source / "main.cpp").read_bytes()
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request))
    output = tmp_path / "attempts"
    output.mkdir()
    capsys.readouterr()
    result = main(
        [
            "verify-proposal",
            "--store",
            str(source / "store"),
            "--workspace",
            str(source),
            "--request",
            str(request_path),
            "--output-root",
            str(output),
            "--execute-trusted-project",
        ]
    )
    assert result == 0
    response = json.loads(capsys.readouterr().out)
    assert response["status"] == "selected_tests_passed"
    assert response["after"]["run_id"] != before.run_id
    assert (source / "main.cpp").read_bytes() == original
