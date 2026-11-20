"""CTest execution-log parsing never promotes captured program output to commands."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
from typing import Any

import pytest

from cppulse.adapters.ctest_log import MAX_LOG_BYTES, parse_ctest_log
from cppulse.adapters.test_results import parse_test_report
import test_test_results as result_fixtures

actual_ctest_reports = result_fixtures.actual_ctest_reports
PRODUCER = {"name": "ctest", "version": "3.31.6"}
SEPARATOR = "-" * 58


def synthetic_log(
    *,
    command: str = '"/selected/binary" "argument with spaces"',
    name: str = "case",
    output: str = "synthetic stdout café λ",
    outcome: str = "Test Passed.",
) -> str:
    """Clearly synthetic transport fixture using the observed log structure."""
    return f"""Start testing: fixture time
{SEPARATOR}
1/1 Testing: {name}
1/1 Test: {name}
Command: {command}
Directory: /selected/build with spaces
"{name}" start time: fixture time
Output:
{SEPARATOR}
{output}
<end of output>
Test time =   0.01 sec
{SEPARATOR}
{outcome}
"{name}" end time: fixture time
"{name}" time elapsed: 00:00:00
{SEPARATOR}

End testing: fixture time
"""


def parse_text(tmp_path: Path, text: str, **options: Any) -> Any:
    path = tmp_path / "LastTest.log"
    path.write_text(text, encoding="utf-8")
    return parse_ctest_log(path, producer=PRODUCER, **options)


@pytest.mark.parametrize("mode", ["clean", "fail", "skip", "disabled", "zero"])
def test_actual_ctest_execution_logs(
    actual_ctest_reports: dict[str, tuple[Path, int]], mode: str
) -> None:
    report, _ = actual_ctest_reports[mode]
    path = report.parent / "build/Testing/Temporary/LastTest.log"
    result = parse_ctest_log(path, producer=PRODUCER)
    assert result.usability == "usable", result.limitations
    assert result.report_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert result.size_bytes == path.stat().st_size
    if mode == "zero":
        assert result.records == ()
    elif mode == "disabled":
        assert len(result.records) == 1
        assert result.records[0].name == "disabled"
        assert result.records[0].actual_argv == ()
        assert result.records[0].outcome == "notrun"
    else:
        assert len(result.records) == 1
        record = result.records[0]
        assert record.name == mode
        assert Path(record.actual_argv[0]).name == "cmake"
        assert record.working_directory == str(report.parent / "build")
        assert record.outcome == ("failed" if mode == "fail" else "passed")
        if mode == "skip":
            assert parse_test_report(report, producer=PRODUCER).status == "skipped"
            assert any("JUnit" in limit for limit in result.limitations)


def test_program_output_cannot_replace_structural_command_or_directory(
    tmp_path: Path,
) -> None:
    spoof = (
        '1/1 Testing: decoy\n1/1 Test: decoy\nCommand: "/decoy/binary"\nDirectory: /decoy\n"decoy" start time: fake\nOutput:\n'
        + SEPARATOR
    )
    result = parse_text(tmp_path, synthetic_log(output=spoof))
    assert result.usability == "usable", result.limitations
    assert len(result.records) == 1
    assert result.records[0].name == "case"
    assert result.records[0].actual_argv == ("/selected/binary", "argument with spaces")
    assert result.records[0].working_directory == "/selected/build with spaces"


def test_literal_arguments_preserve_spaces_empty_values_and_backslashes(
    tmp_path: Path,
) -> None:
    result = parse_text(
        tmp_path,
        synthetic_log(
            command='"/selected/binary" "" "literal \\path\\file" "$(not executed)"'
        ),
    )
    assert result.usability == "usable", result.limitations
    assert result.records[0].actual_argv == (
        "/selected/binary",
        "",
        "literal \\path\\file",
        "$(not executed)",
    )


@pytest.mark.parametrize(
    "command",
    [
        "/selected/binary --unquoted",
        '"/selected/binary" && "other"',
        '"/selected/binary" "embedded "quote""',
        '"/selected/binary" "unterminated',
        '"" "argument"',
    ],
)
def test_ambiguous_or_unsupported_command_encoding_never_proves_execution(
    tmp_path: Path, command: str
) -> None:
    result = parse_text(tmp_path, synthetic_log(command=command))
    assert result.usability in {"unsupported", "malformed"}
    assert result.records == ()
    assert result.report_sha256 is not None


@pytest.mark.parametrize(
    "transform",
    [
        lambda value: value.replace("1/1 Test: case", "1/1 Test: different"),
        lambda value: value.replace('"case" end time:', '"different" end time:'),
        lambda value: value.replace(
            "<end of output>", "<end of output>\nCommand: fake"
        ),
        lambda value: value.replace("End testing: fixture time\n", ""),
        lambda value: value.replace("Test time =   0.01 sec", "Test time =   NaN sec"),
        lambda value: value + "unexpected trailing commands\n",
    ],
)
def test_truncated_inconsistent_or_spoofed_boundaries_fail_closed(
    tmp_path: Path, transform: Any
) -> None:
    result = parse_text(tmp_path, transform(synthetic_log()))
    assert result.usability in {"malformed", "unsupported"}
    assert result.records == ()


def test_duplicate_names_are_ambiguous_even_with_distinct_record_numbers(
    tmp_path: Path,
) -> None:
    first = synthetic_log().replace("1/1 ", "1/2 ")
    second = synthetic_log().replace("1/1 ", "2/2 ")
    combined = (
        first.removesuffix("End testing: fixture time\n")
        + second.split(SEPARATOR + "\n", 1)[1]
    )
    result = parse_text(tmp_path, combined)
    assert result.usability == "malformed"
    assert result.records == ()
    assert any("duplicate" in limit.lower() for limit in result.limitations)


def test_unknown_version_missing_and_oversize_logs_remain_distinct(
    tmp_path: Path,
) -> None:
    path = tmp_path / "LastTest.log"
    assert parse_ctest_log(path, producer=PRODUCER).usability == "missing"
    unsupported = parse_ctest_log(path, producer={"name": "ctest", "version": "3.31.5"})
    assert unsupported.usability == "unsupported" and unsupported.report_sha256 is None
    unsupported = parse_ctest_log(path, producer=PRODUCER, adapter_version="9")
    assert unsupported.usability == "unsupported" and unsupported.size_bytes is None
    with path.open("wb") as stream:
        stream.truncate(MAX_LOG_BYTES + 1)
    oversized = parse_ctest_log(path, producer=PRODUCER)
    assert oversized.usability == "malformed"
    assert oversized.report_sha256 is None and oversized.size_bytes is None


def test_digest_tracks_the_same_parsed_bytes_when_path_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.adapters.ctest_log as adapter

    path = tmp_path / "LastTest.log"
    original = synthetic_log().encode()
    path.write_bytes(original)
    read = adapter._read_log

    def replace(selected: Path) -> bytes:
        content = read(selected)
        selected.write_bytes(b"changed after the checked read")
        return content

    monkeypatch.setattr(adapter, "_read_log", replace)
    result = adapter.parse_ctest_log(path, producer=PRODUCER)
    assert result.usability == "usable"
    assert result.report_sha256 == hashlib.sha256(original).hexdigest()
    assert result.size_bytes == len(original)


def test_non_utf8_malformed_log_retains_hash_and_parser_never_executes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Log parsers must never execute")

    monkeypatch.setattr(subprocess, "run", reject)
    path = tmp_path / "LastTest.log"
    data = b"\xffbad UTF-8"
    path.write_bytes(data)
    malformed = parse_ctest_log(path, producer=PRODUCER)
    assert malformed.usability == "malformed"
    assert malformed.report_sha256 == hashlib.sha256(data).hexdigest()
    assert malformed.size_bytes == len(data)


@pytest.mark.parametrize("name", ['quoted "name"', " padded ", "split\nheader"])
def test_ambiguous_test_names_do_not_produce_command_records(
    tmp_path: Path, name: str
) -> None:
    result = parse_text(tmp_path, synthetic_log(name=name))
    assert result.usability in {"unsupported", "malformed"}
    assert result.records == ()


def test_nonregular_log_does_not_block_or_claim_an_observed_digest(
    tmp_path: Path,
) -> None:
    import os

    path = tmp_path / "LastTest.log"
    os.mkfifo(path)
    result = parse_ctest_log(path, producer=PRODUCER)
    assert result.usability == "malformed"
    assert result.report_sha256 is None and result.size_bytes is None
