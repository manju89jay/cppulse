"""Independent descriptive-trace integrity controls; never cache eligibility."""

from copy import deepcopy
import hashlib
import os

import pytest

from cppulse.errors import ContractError
from cppulse.query_observation import (
    collect_query_observation,
    parse_query_trace,
    validate_query_report,
)
from tests.test_query_observation import (
    LIMITS,
    actual_pair as _base_actual_pair,
    request,
)


@pytest.fixture(scope="module")
def actual_pair(tmp_path_factory):
    return _base_actual_pair.__wrapped__(tmp_path_factory)


@pytest.mark.parametrize(
    "mutation", ["passed-nonzero", "passed-dropped-trace", "duplicate-tool-descriptor"]
)
def test_actual_receipts_cannot_contradict_selected_execution(actual_pair, mutation):
    selected, original, output = actual_pair
    report = deepcopy(original)
    if mutation == "passed-nonzero":
        report["tracer_receipt"]["exit_status"] = 19
    elif mutation == "passed-dropped-trace":
        report["tracer_receipt"]["observed_bytes"]["trace"] += 1
    else:
        path = report["tool_bindings"]["native"]["path"]
        report["tool_bindings"]["tracer"]["path"] = path
        report["tracer_receipt"]["argv"][0] = path
        report["tool_bindings"]["tracer"]["version_receipt"]["argv"][0] = path
    with pytest.raises(ContractError):
        validate_query_report(selected, report, output)


def test_empty_version_stream_is_contract_failure_without_traceback(
    actual_pair, tmp_path
):
    selected, original, output = actual_pair
    report = deepcopy(original)
    view = tmp_path / "view"
    view.mkdir()
    for artifact in report["artifacts"]:
        target = view / artifact["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(output / artifact["path"], target)
    version = view / "version/stdout.log"
    version.unlink()
    version.write_bytes(b"")
    for artifact in report["artifacts"]:
        if artifact["path"] == "version/stdout.log":
            artifact.update(size_bytes=0, sha256=hashlib.sha256(b"").hexdigest())
    with pytest.raises(ContractError):
        validate_query_report(selected, report, view)
    assert (output / "version/stdout.log").read_bytes()


@pytest.mark.parametrize(
    "raw",
    [
        b'11 +++ exited with 0 +++\n11 access("/after-death", R_OK) = 0\n',
        b"11 exit_group(1) = ?\n11 +++ exited with 0 +++\n",
        b'11 access("/a", R_OK) = nonsensical-result\n11 +++ exited with 0 +++\n',
        b'11 access("/bad\\qpath", R_OK) = -1 ENOENT (missing)\n11 +++ exited with 0 +++\n',
    ],
)
def test_impossible_or_unsupported_trace_never_looks_complete(raw):
    assert parse_query_trace(raw, LIMITS)["status"] != "complete_observation"


def test_dot_report_path_refused_before_creating_owned_output(tmp_path):
    selected = request(tmp_path)
    output = tmp_path / "capture"
    selected["native_report_relative_path"] = "."
    selected["invocation"]["argv"] += [
        "--output",
        str(output.parent),
        "--file-size-bytes",
        "8388608",
    ]
    with pytest.raises(ContractError):
        collect_query_observation(selected, output, execute_selected_tools=True)
    assert not output.exists()


@pytest.mark.parametrize(
    "mutation", ["failed-dropped-trace", "version-cwd", "version-counts"]
)
def test_all_observation_receipts_match_their_retained_streams(actual_pair, mutation):
    selected, original, output = actual_pair
    report = deepcopy(original)
    if mutation == "failed-dropped-trace":
        report["tracer_receipt"].update(status="failed", exit_status=19)
        report["tracer_receipt"]["observed_bytes"]["trace"] += 1
    elif mutation == "version-cwd":
        report["tool_bindings"]["tracer"]["version_receipt"]["cwd"] = "/changed-cwd"
    else:
        report["tool_bindings"]["tracer"]["version_receipt"]["captured_bytes"][
            "stdout"
        ] += 1
    with pytest.raises(ContractError):
        validate_query_report(selected, report, output)


def trace_view(actual_pair, tmp_path, mutate):
    selected, original, output = actual_pair
    report = deepcopy(original)
    view = tmp_path / "view"
    view.mkdir()
    for artifact in report["artifacts"]:
        target = view / artifact["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(output / artifact["path"], target)
    trace = view / "trace.log"
    original_bytes = trace.read_bytes()
    raw = mutate(original_bytes)
    assert raw != original_bytes
    trace.unlink()
    trace.write_bytes(raw)
    for artifact in report["artifacts"]:
        if artifact["path"] == "trace.log":
            artifact.update(size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    report["tracer_receipt"]["captured_bytes"]["trace"] = len(raw)
    report["tracer_receipt"]["observed_bytes"]["trace"] = len(raw)
    report["parsed"] = parse_query_trace(raw, selected["limits"])
    actual_path = report["tool_bindings"]["native"]["path"]
    for event in report["parsed"]["events"]:
        if event["operation"] == "execve" and event["path"] == actual_path:
            report["native_execution_observations"][0]["actual_execve_arguments"] = (
                event["arguments"]
            )
    return selected, report, view


def test_failed_exec_attempt_is_not_a_selected_native_execution(actual_pair, tmp_path):
    selected, report, view = trace_view(
        actual_pair,
        tmp_path,
        lambda raw: raw.replace(b" = 0\n", b" = -1 EACCES (Permission denied)\n", 1),
    )
    with pytest.raises(ContractError):
        validate_query_report(selected, report, view)


def test_actual_native_environment_must_match_selected_environment(
    actual_pair, tmp_path
):
    selected, report, view = trace_view(
        actual_pair,
        tmp_path,
        lambda raw: raw.replace(b'"LC_ALL=C"', b'"LC_ALL=CHANGED"', 1),
    )
    with pytest.raises(ContractError):
        validate_query_report(selected, report, view)


@pytest.mark.parametrize(
    "raw",
    [
        b"0 exit_group(0) = ?\n0 +++ exited with 0 +++\n",
        b"9" * 5000 + b" exit_group(0) = ?\n",
        b"11 clone(child_stack=NULL, flags=SIGCHLD) = "
        + b"9" * 5000
        + b"\n11 +++ exited with 0 +++\n",
        b"11 +++ exited with " + b"9" * 5000 + b" +++\n",
    ],
)
def test_invalid_but_byte_bounded_process_integers_are_safe_unknown(raw):
    assert parse_query_trace(raw, LIMITS)["status"] != "complete_observation"


@pytest.mark.parametrize("which,pid", [("tracer", True), ("version", 0)])
def test_actual_receipt_pid_cannot_be_boolean_or_process_group(actual_pair, which, pid):
    selected, original, output = actual_pair
    report = deepcopy(original)
    receipt = (
        report["tracer_receipt"]
        if which == "tracer"
        else report["tool_bindings"]["tracer"]["version_receipt"]
    )
    receipt["pid"] = pid
    with pytest.raises(ContractError):
        validate_query_report(selected, report, output)
