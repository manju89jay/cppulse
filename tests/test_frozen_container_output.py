"""Bounded real helper collection, without Docker or third-party tool copies."""

import io
import json
import subprocess
import sys
import tarfile
import time

import pytest

import test_frozen_container_supervisor as supervisor_fixtures


@pytest.fixture(scope="module")
def supervisor(tmp_path_factory):
    return supervisor_fixtures.supervisor.__wrapped__(tmp_path_factory)


def collect(supervisor, *arguments):
    return subprocess.run(
        [str(supervisor), *map(str, arguments)], capture_output=True, timeout=5
    )


def test_missing_status_is_pending_and_valid_status_preserves_original_bytes(
    supervisor, tmp_path
):
    path = tmp_path / "status"
    assert collect(supervisor, "--read-status", path).returncode == 1
    raw = b'{"version":"0.1.0","native_exit_code":7,"native_signal":null,"native_exec_errno":null}\n'
    path.write_bytes(raw)
    result = collect(supervisor, "--read-status", path)
    assert result.returncode == 0 and result.stdout == raw


@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory", "oversize"])
def test_unsupported_status_is_refused_without_blocking(supervisor, tmp_path, kind):
    import os

    path = tmp_path / "status"
    if kind == "symlink":
        target = tmp_path / "target"
        target.write_bytes(b"{}")
        path.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "directory":
        path.mkdir()
    else:
        path.write_bytes(b"x" * 4097)
    assert collect(supervisor, "--read-status", path).returncode == 74


def test_archive_retains_regular_aliases_empty_dirs_and_actual_bytes(
    supervisor, tmp_path
):
    import os

    (tmp_path / "empty").mkdir()
    source = tmp_path / "first"
    source.write_bytes(b"original\x00bytes")
    os.link(source, tmp_path / "second")
    result = collect(supervisor, "--archive-output", tmp_path)
    assert result.returncode == 0
    with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
        assert archive.getnames() == ["empty", "first", "second"]
        assert archive.getmember("empty").isdir()
        assert archive.getmember("second").isfile()
        assert (
            archive.extractfile("first").read()
            == archive.extractfile("second").read()
            == b"original\x00bytes"
        )


@pytest.mark.parametrize("kind", ["symlink", "fifo", "long_name", "oversize"])
def test_unsafe_archive_inventory_is_refused_before_streaming(
    supervisor, tmp_path, kind
):
    import os

    if kind == "symlink":
        (tmp_path / "foreign").symlink_to("/etc/passwd")
    elif kind == "fifo":
        os.mkfifo(tmp_path / "fifo")
    elif kind == "long_name":
        (tmp_path / ("x" * 100)).write_bytes(b"x")
    else:
        with (tmp_path / "large").open("wb") as stream:
            stream.truncate(8 * 1024**2 + 1)
    result = collect(supervisor, "--archive-output", tmp_path)
    assert result.returncode == 74 and result.stdout == b""


def test_supervised_native_streams_can_be_collected_while_supervisor_alive(
    supervisor, tmp_path
):
    status = tmp_path / ".cppulse-native-status.json"
    native = [
        sys.executable,
        "-c",
        "import os; os.write(1,b'actual\\x00stdout'); os.write(2,b'actual stderr')",
    ]
    process = subprocess.Popen([str(supervisor), str(status), *native])
    try:
        until = time.monotonic() + 5
        while (
            not status.exists() and process.poll() is None and time.monotonic() < until
        ):
            time.sleep(0.01)
        assert process.poll() is None and status.exists()
        read = collect(supervisor, "--read-status", status)
        assert read.returncode == 0 and json.loads(read.stdout)["native_exit_code"] == 0
        result = collect(supervisor, "--archive-output", tmp_path)
        assert result.returncode == 0
        with tarfile.open(fileobj=io.BytesIO(result.stdout), mode="r:") as archive:
            assert (
                archive.extractfile(".cppulse-native.stdout").read()
                == b"actual\x00stdout"
            )
            assert (
                archive.extractfile(".cppulse-native.stderr").read() == b"actual stderr"
            )
            assert (
                json.load(archive.extractfile(".cppulse-native-status.json"))[
                    "native_exit_code"
                ]
                == 0
            )
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
