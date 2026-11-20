"""Actual isolated Linux CMake component installation, without a full core build."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import time

import pytest

from cppulse.elf_runtime import inspect_elf_runtime


@pytest.mark.skipif(
    platform.system() != "Linux", reason="The bounded supervisor profile requires Linux"
)
def test_cmake_installed_helper_runs_outside_checkout(tmp_path):
    root = Path(__file__).resolve().parents[1]
    build = tmp_path / "build"
    prefix = tmp_path / "installed prefix with spaces"
    for command in [
        [
            "cmake",
            "-S",
            str(root / "analyzer-core"),
            "-B",
            str(build),
            "-DCMAKE_BUILD_TYPE=Release",
            "-DBUILD_TESTING=OFF",
            "-DCMAKE_INSTALL_LIBEXECDIR=libexec",
        ],
        [
            "cmake",
            "--build",
            str(build),
            "--target",
            "cppulse-runtime-supervisor",
            "-j",
            "1",
        ],
        [
            "cmake",
            "--install",
            str(build),
            "--component",
            "runtime-supervisor",
            "--prefix",
            str(prefix),
        ],
    ]:
        result = subprocess.run(command, capture_output=True, timeout=60)
        assert result.returncode == 0, result.stdout + result.stderr
    helper = prefix / "libexec/cppulse/cppulse-runtime-supervisor"
    assert (
        helper.is_file() and not (prefix / "libexec/cppulse/cppulse-analyzer").exists()
    )
    metadata = inspect_elf_runtime(
        helper,
        expected_sha256=hashlib.sha256(helper.read_bytes()).hexdigest(),
        expected_size=helper.stat().st_size,
    )
    assert metadata.interpreter and "libstdc++.so.6" in metadata.needed
    working = tmp_path / "unrelated"
    working.mkdir()
    status = working / ".cppulse-native-status.json"
    environment = {
        k: v
        for k, v in os.environ.items()
        if k not in {"PYTHONPATH", "LD_LIBRARY_PATH", "LD_PRELOAD"}
    }
    child = [
        str(Path(sys.executable).resolve()),
        "-c",
        "import os;os.write(1,b'installed\\x00stdout');os.write(2,b'installed stderr')",
    ]
    process = subprocess.Popen(
        [str(helper), str(status), *child], cwd=working, env=environment
    )
    try:
        deadline = time.monotonic() + 5
        while (
            not status.exists()
            and process.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert process.poll() is None and status.is_file()
        observed = json.loads(status.read_bytes())
        assert (
            observed["native_exit_code"] == 0 and observed["native_exec_errno"] is None
        )
        collected = subprocess.run(
            [str(helper), "--archive-output", str(working)],
            cwd=working,
            env=environment,
            capture_output=True,
            timeout=5,
            check=True,
        )
        with tarfile.open(fileobj=io.BytesIO(collected.stdout), mode="r:") as archive:
            assert (
                archive.extractfile(".cppulse-native.stdout").read()
                == b"installed\x00stdout"
            )
            assert (
                archive.extractfile(".cppulse-native.stderr").read()
                == b"installed stderr"
            )
    finally:
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)
