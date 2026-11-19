"""Actual public finite-service lane; inspector is explicitly a test fixture."""

import json
from pathlib import Path

import pytest

from cppulse.cli import main
from cppulse.service_repair import validate_report
from tests.test_service_repair import _request


def test_public_service_verification_requires_explicit_trusted_execution(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output"
    with pytest.raises(SystemExit) as error:
        main(
            [
                "verify-service-proposal",
                "--request",
                str(tmp_path / "request.json"),
                "--output",
                str(output),
            ]
        )
    assert error.value.code == 2
    assert not output.exists()


def test_public_service_verification_retains_actual_finite_before_after_pair(
    tmp_path: Path,
) -> None:
    (tmp_path / "material").mkdir()
    request = _request(tmp_path / "material")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request))
    output = tmp_path / "output"
    assert (
        main(
            [
                "verify-service-proposal",
                "--request",
                str(request_path),
                "--output",
                str(output),
                "--execute-trusted-project",
            ]
        )
        == 0
    )
    report = json.loads((output / "report.json").read_bytes())
    validate_report(request, report, output)
    assert report["status"] == "verified_finite_regression"
