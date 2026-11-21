"""Actual small Linux supervisor; no Docker daemon or analyzer is invoked."""

from __future__ import annotations

import json
from pathlib import Path
import signal
import subprocess
import time

import pytest


@pytest.fixture(scope="module")
def supervisor(tmp_path_factory):
    output = tmp_path_factory.mktemp("supervisor") / "supervisor"
    source = (
        Path(__file__).resolve().parents[1] / "tools/frozen_container_supervisor.cpp"
    )
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Os",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(source),
            "-o",
            str(output),
        ],
        check=True,
        capture_output=True,
        timeout=30,
    )
    return output


def observed(supervisor, tmp_path, argv):
    status = tmp_path / "status.json"
    process = subprocess.Popen([str(supervisor), str(status), *argv])
    try:
        until = time.monotonic() + 5
        while (
            not status.exists() and time.monotonic() < until and process.poll() is None
        ):
            time.sleep(0.01)
        assert status.exists(), process.poll()
        assert process.poll() is None
        value = json.loads(status.read_bytes())
        assert status.stat().st_mode & 0o777 == 0o400
        return value
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)


@pytest.mark.parametrize("exit_code", [0, 7, 127])
def test_native_exit_keeps_supervisor_and_status_alive(supervisor, tmp_path, exit_code):
    result = observed(supervisor, tmp_path, ["/bin/sh", "-c", f"exit {exit_code}"])
    assert result == {
        "version": "0.1.0",
        "native_exit_code": exit_code,
        "native_signal": None,
        "native_exec_errno": None,
    }


def test_native_signal_is_distinct_from_exit(supervisor, tmp_path):
    result = observed(supervisor, tmp_path, ["/bin/sh", "-c", "kill -TERM $$"])
    assert (
        result["native_signal"] == signal.SIGTERM and result["native_exit_code"] is None
    )


def test_exec_failure_has_actual_errno(supervisor, tmp_path):
    result = observed(supervisor, tmp_path, [str(tmp_path / "absent")])
    assert result["native_exit_code"] == 127 and result["native_exec_errno"] == 2


@pytest.mark.parametrize("kind", ["regular", "symlink"])
def test_foreign_status_prevents_native_start(supervisor, tmp_path, kind):
    status = tmp_path / "status.json"
    marker = tmp_path / "native-started"
    original = tmp_path / "foreign"
    original.write_bytes(b"untouched")
    if kind == "symlink":
        status.symlink_to(original)
    else:
        status.write_bytes(b"untouched")
    result = subprocess.run(
        [str(supervisor), str(status), "/bin/sh", "-c", f"touch '{marker}'"], timeout=5
    )
    assert result.returncode == 73 and not marker.exists()
    assert status.read_bytes() == b"untouched" and original.read_bytes() == b"untouched"


def test_symlink_parent_prevents_native_start(supervisor, tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    result = subprocess.run(
        [str(supervisor), str(alias / "status"), "/bin/true"], timeout=5
    )
    assert result.returncode == 73 and not list(actual.iterdir())
