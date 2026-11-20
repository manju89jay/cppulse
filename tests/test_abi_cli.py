"""Public ABI reports retain observed changes without turning exit0 into approval."""

from pathlib import Path
import json
import pytest
from cppulse.cli import main
import test_abi as fixtures


@pytest.fixture
def binaries(tmp_path: Path) -> dict[str, Path]:
    return fixtures.binaries.__wrapped__(tmp_path)


@pytest.mark.parametrize(
    "variant,status,exit_code",
    [
        ("removed", "incompatible_changes_reported", 0),
        ("stripped", "unsupported", 3),
    ],
)
def test_public_actual_abi_report(
    binaries: dict[str, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    variant: str,
    status: str,
    exit_code: int,
) -> None:
    original = binaries["old"].read_bytes()
    document = fixtures.request(binaries["old"], binaries[variant])
    path = tmp_path / "request.json"
    path.write_text(json.dumps(document))
    output = tmp_path / "report"
    assert (
        main(["abi-compare", "--request", str(path), "--output", str(output)])
        == exit_code
    )
    response = json.loads(capsys.readouterr().out)
    report = json.loads(Path(response["report"]).read_text())
    assert report["results"][0]["status"] == status
    assert binaries["old"].read_bytes() == original
