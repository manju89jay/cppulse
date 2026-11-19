"""ABI evidence integrity controls; mocked outcomes never qualify real ABI scope."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import pytest

from cppulse.abi import compare, validate_report
from cppulse.errors import ContractError
from test_abi import binaries as _authored_binaries
from test_abi import request

binaries = _authored_binaries


@pytest.fixture
def mocked_report(binaries: dict, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Use actual tiny ELF inputs, but explicitly synthetic tool-output receipts."""
    import cppulse.abi as module

    cfg = request(binaries["old"], binaries["old"])
    hook = {"callback": lambda _command, _cwd: None}

    def capture(command, environment, cwd, wall, log_limit):
        if command[1:] == ["--version"]:
            log = (
                "abidiff: 2.6.0\n"
                if Path(command[0]).name == "abidiff"
                else "GNU readelf (GNU Binutils for Debian) 2.44\n"
            )
        elif "--debug-dump=info" in command:
            log = "  Compilation Unit @ offset 0:\n <0><c>: Abbrev Number: 1 (DW_TAG_compile_unit)\n"
        else:
            hook["callback"](command, cwd)
            log = ""
        return {
            "returncode": 0,
            "log": log,
            "timed_out": False,
            "log_truncated": False,
            "elapsed_seconds": 0.001,
        }

    monkeypatch.setattr(module, "_capture", capture)
    return cfg, hook


@pytest.mark.parametrize("selected", ["old", "new", "tool", "reader", "library"])
def test_changed_staged_material_cannot_publish_original_input_pins(
    tmp_path: Path, mocked_report: tuple, selected: str
) -> None:
    cfg, hook = mocked_report

    def mutate(command, cwd):
        target = (
            Path(command[-2])
            if selected == "old"
            else Path(command[-1])
            if selected == "new"
            else Path(command[0])
            if selected == "tool"
            else cwd / "readelf"
            if selected == "reader"
            else next((cwd / "libraries").iterdir())
        )
        target.chmod(0o600)
        target.write_bytes(b"different staged analysis bytes")

    hook["callback"] = mutate
    output = tmp_path / "result"
    with pytest.raises(ContractError, match="staged"):
        compare(cfg, output)
    assert not (output / "report.json").exists()
    assert (
        hashlib.sha256(Path(cfg["pairs"][0]["old"]["path"]).read_bytes()).hexdigest()
        == cfg["pairs"][0]["old"]["sha256"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "outside",
        "nested",
        "duplicate",
        "not_library",
        "oversize",
        "aggregate",
        "unselected",
    ],
)
def test_runtime_library_receipts_stay_within_explicit_selection(
    tmp_path: Path, mocked_report: tuple, mutation: str
) -> None:
    cfg, _ = mocked_report
    report = compare(cfg, tmp_path / "result")
    validate_report(report, expected_request=cfg)
    altered = deepcopy(report)
    rows = altered["tool"]["libraries"]
    assert rows
    if mutation == "outside":
        rows[0]["path"] = "/foreign/libabigail.so"
    elif mutation == "nested":
        rows[0]["path"] = str(
            Path(cfg["tool"]["library_directory"]) / "nested" / "libabigail.so"
        )
    elif mutation == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif mutation == "not_library":
        rows[0]["path"] = str(Path(cfg["tool"]["library_directory"]) / "README")
    elif mutation == "oversize":
        rows[0]["bytes"] = 512 * 1024 * 1024 + 1
    elif mutation == "aggregate":
        rows[:] = [deepcopy(rows[0]), deepcopy(rows[0])]
        rows[0]["bytes"] = rows[1]["bytes"] = 300 * 1024 * 1024
        rows[1]["path"] = str(Path(cfg["tool"]["library_directory"]) / "another.so")
    else:
        cfg["tool"]["library_directory"] = None
        from cppulse.identities import canonical_json_bytes

        altered["request_sha256"] = hashlib.sha256(
            canonical_json_bytes(cfg)
        ).hexdigest()
    with pytest.raises(ContractError, match="librar"):
        validate_report(altered, expected_request=cfg)


def test_no_selected_runtime_directory_has_an_empty_declared_inventory(
    tmp_path: Path, mocked_report: tuple
) -> None:
    cfg, _ = mocked_report
    cfg["tool"]["library_directory"] = None
    report = compare(cfg, tmp_path / "result")
    assert report["tool"]["libraries"] == []
    validate_report(report, expected_request=cfg)
    assert report["source_binding"] == "unverified"


def test_aggregate_input_receipts_cannot_exceed_producer_total_budget(
    tmp_path: Path, mocked_report: tuple
) -> None:
    from cppulse.identities import canonical_json_bytes

    cfg, _ = mocked_report
    report = compare(cfg, tmp_path / "result")
    cfg["limits"]["input_bytes"] = 512 * 1024 * 1024
    report["limits"] = deepcopy(cfg["limits"])
    report["request_sha256"] = hashlib.sha256(canonical_json_bytes(cfg)).hexdigest()
    report["results"][0]["old"]["bytes"] = 300 * 1024 * 1024
    report["results"][0]["new"]["bytes"] = 300 * 1024 * 1024
    with pytest.raises(ContractError, match="aggregate"):
        validate_report(report, expected_request=cfg)
