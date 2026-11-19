"""Finite trace parsing and actual selected-tool capture, not cache proof."""

from pathlib import Path
import hashlib

import pytest

from cppulse.errors import ContractError
from cppulse.query_observation import collect_query_observation, parse_query_trace

LIMITS = {
    "wall_seconds": 5,
    "max_trace_bytes": 65536,
    "max_stdout_bytes": 4096,
    "max_events": 1000,
    "max_processes": 8,
    "max_line_bytes": 16384,
}


def parse(raw: bytes):
    return parse_query_trace(raw, LIMITS)


def test_descriptive_negative_absolute_query_is_retained():
    result = parse(
        b'11 openat(AT_FDCWD</own>, "/missing.h", O_RDONLY) = -1 ENOENT (No such file or directory)\n11 exit_group(0) = ?\n11 +++ exited with 0 +++\n'
    )
    assert result["status"] == "complete_observation"
    assert result["events"][0]["path"] == "/missing.h"
    assert result["events"][0]["errno"] == "ENOENT"


def test_unfinished_and_resumed_are_reconciled_per_original_pid():
    result = parse(
        b'11 openat(AT_FDCWD</own>, "/a", O_RDONLY <unfinished ...>\n12 exit(0) = ?\n12 +++ exited with 0 +++\n11 <... openat resumed>) = 3</a>\n11 +++ exited with 0 +++\n'
    )
    assert result["status"] == "complete_observation"
    assert result["events"][-1]["path"] == "/a"


@pytest.mark.parametrize(
    "raw",
    [
        b"11 <... openat resumed>) = 3\n11 +++ exited with 0 +++\n",
        b'11 openat(AT_FDCWD, "relative.h", O_RDONLY) = 3\n11 +++ exited with 0 +++\n',
        b'11 openat(AT_FDCWD</own>, "\\377", O_RDONLY) = 3\n11 +++ exited with 0 +++\n',
        b'11 imaginary("/a") = 0\n11 +++ exited with 0 +++\n',
    ],
)
def test_unsupported_forms_never_look_complete(raw):
    assert parse(raw)["status"] == "unsupported"


@pytest.mark.parametrize(
    "raw",
    [
        b'11 openat(AT_FDCWD, "/a", O_RDONLY <unfinished ...>\n',
        b"11 exit_group(0) = ?",
        b'11 access("/a", R_OK) = 0\n',
    ],
)
def test_missing_terminals_or_capped_lines_remain_incomplete(raw):
    assert parse(raw)["status"] == "incomplete"


def test_dirfd_annotation_is_observation_not_canonical_closure():
    result = parse(
        b'11 openat(3</own/include>, "x.h", O_RDONLY) = 4\n11 +++ exited with 0 +++\n'
    )
    assert result["events"][0]["path"] == "/own/include/x.h"
    assert result["events"][0]["resolution"] == "observed-dirfd"


def request(tmp_path: Path):
    def pin(path):
        p = Path(path)
        return {
            "path": str(p),
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "size_bytes": p.stat().st_size,
        }

    return {
        "version": "0.1.0",
        "source_digest": "a" * 64,
        "context_id": "observed-query",
        "native": pin("/usr/bin/true"),
        "tracer": {**pin("/usr/bin/strace"), "version": "strace -- version 6.13"},
        "invocation": {
            "argv": ["/usr/bin/true"],
            "cwd": str(tmp_path),
            "environment": {"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        },
        "native_report_relative_path": None,
        "limits": LIMITS,
    }


def test_explicit_execution_required_before_output(tmp_path):
    output = tmp_path / "capture"
    with pytest.raises(ContractError, match="Explicit"):
        collect_query_observation(request(tmp_path), output)
    assert not output.exists()


def test_actual_sealed_selected_tools_have_descriptive_receipts(tmp_path):
    report = collect_query_observation(
        request(tmp_path), tmp_path / "capture", execute_selected_tools=True
    )
    assert report["tracer_receipt"]["exit_status"] == 0
    assert report["native_execution_observations"]
    assert report["closure"] == "unqualified" and report["cache_eligible"] is False
    assert report["tool_bindings"]["native"]["seals"] == 15
    assert report["tracer_receipt"]["environment"] == {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
    }


def test_created_child_without_any_terminal_record_is_incomplete():
    result = parse(
        b"11 clone(child_stack=NULL, flags=SIGCHLD) = 22\n11 +++ exited with 0 +++\n"
    )
    assert result["status"] == "incomplete"
    assert 22 in result["processes"]


@pytest.fixture(scope="module")
def actual_pair(tmp_path_factory):
    from cppulse.query_observation import validate_query_report

    directory = tmp_path_factory.mktemp("query-pair")
    selected = request(directory)
    output = directory / "capture"
    report = collect_query_observation(selected, output, execute_selected_tools=True)
    validate_query_report(selected, report, output)
    return selected, report, output


@pytest.mark.parametrize(
    "mutation",
    [
        "cache",
        "closure",
        "argv",
        "environment",
        "trace-fact",
        "captured-count",
        "native-exit",
        "native-tool",
    ],
)
def test_replay_rejects_forged_qualification_or_receipts(actual_pair, mutation):
    from copy import deepcopy
    from cppulse.query_observation import validate_query_report

    selected, original, output = actual_pair
    report = deepcopy(original)
    if mutation == "cache":
        report["cache_eligible"] = True
    elif mutation == "closure":
        report["closure"] = "closed"
    elif mutation == "argv":
        report["tracer_receipt"]["argv"][-1] = "changed"
    elif mutation == "environment":
        report["tracer_receipt"]["environment"]["EXTRA"] = "value"
    elif mutation == "trace-fact":
        report["parsed"]["events"][0]["path"] = "/invented"
    elif mutation == "captured-count":
        report["tracer_receipt"]["captured_bytes"]["trace"] += 1
    elif mutation == "native-exit":
        report["native_execution_observations"][0]["observed_exit_status"] = 17
    else:
        report["tool_bindings"]["native"]["sha256"] = "f" * 64
    with pytest.raises((ContractError,)):
        validate_query_report(selected, report, output)


def test_actual_trace_limit_preserves_incomplete_receipt(tmp_path):
    selected = request(tmp_path)
    selected["limits"] = {**LIMITS, "max_trace_bytes": 256}
    report = collect_query_observation(
        selected, tmp_path / "capped", execute_selected_tools=True
    )
    assert report["capture_status"] == "incomplete"
    assert report["tracer_receipt"]["status"] == "output_limit"
    assert report["tracer_receipt"]["captured_bytes"]["trace"] <= 256
    assert report["cache_eligible"] is False


def test_existing_output_preserved_and_stale_pin_refused(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "keep"
    marker.write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        collect_query_observation(
            request(tmp_path), output, execute_selected_tools=True
        )
    assert marker.read_bytes() == b"preserve"
    selected = request(tmp_path)
    selected["native"]["sha256"] = "f" * 64
    from cppulse.errors import IntegrityError

    with pytest.raises(IntegrityError, match="bytes changed"):
        collect_query_observation(
            selected, tmp_path / "stale", execute_selected_tools=True
        )


@pytest.mark.parametrize(
    "mutation", ["sensitive-environment", "nan-wall", "bool-events", "nul-argv"]
)
def test_request_invalid_finite_or_environment_inputs_refused(tmp_path, mutation):
    selected = request(tmp_path)
    if mutation == "sensitive-environment":
        selected["invocation"]["environment"]["AUTH_TOKEN"] = "not-a-real-token"
    elif mutation == "nan-wall":
        selected["limits"] = {**LIMITS, "wall_seconds": float("nan")}
    elif mutation == "bool-events":
        selected["limits"] = {**LIMITS, "max_events": True}
    else:
        selected["invocation"]["argv"].append("\x00")
    output = tmp_path / "invalid"
    with pytest.raises(ContractError):
        collect_query_observation(selected, output, execute_selected_tools=True)
    assert not output.exists()


@pytest.mark.parametrize("field", ["argv", "environment"])
def test_trace_encoded_string_bounds_are_checked_before_output(tmp_path, field):
    selected = request(tmp_path)
    if field == "argv":
        selected["invocation"]["argv"].append("é" * 3000)
    else:
        selected["invocation"]["environment"]["VALUE"] = "x" * 4096
    output = tmp_path / "excessive-encoding"
    with pytest.raises(ContractError, match="trace byte-string length"):
        collect_query_observation(selected, output, execute_selected_tools=True)
    assert not output.exists()
