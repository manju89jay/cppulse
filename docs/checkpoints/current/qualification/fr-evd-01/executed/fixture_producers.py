"""Create two real JUnit producer outputs from the frozen finite input files."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from xml.etree import ElementTree


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, record):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")


def call(directory, name, command, expected):
    selected = list(map(str, command))
    environment = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    result = subprocess.run(selected, cwd=directory, env=environment, capture_output=True,
                            text=True, timeout=60, check=False)
    (directory / f"{name}.stdout").write_text(result.stdout)
    (directory / f"{name}.stderr").write_text(result.stderr)
    write(directory / f"{name}.command.json", {
        "argv": selected, "cwd": str(directory), "actual_exit": result.returncode, "expected_exit": expected})
    assert result.returncode == expected, (name, result.returncode, result.stdout[-500:], result.stderr[-2000:])
    return result.stdout


def copy(source, target):
    shutil.copyfile(source, target)
    assert digest(source) == digest(target)


def materialize(lane, folder, plans):
    folder.mkdir()
    ctest_dir = folder / "disabled"
    ctest_dir.mkdir()
    copy(lane / "fixture-disabled.cmake", ctest_dir / "CMakeLists.txt")
    ctest_version = call(ctest_dir, "version", ["/workspace/cppulse/.venv/bin/ctest", "--version"], 0)
    assert ctest_version.splitlines()[0] == "ctest version 3.31.6"
    call(ctest_dir, "cmake", ["/workspace/cppulse/.venv/bin/cmake", "-S", ".", "-B", "build"], 0)
    build = ctest_dir / "build"
    inventory = call(build, "inventory", ["/workspace/cppulse/.venv/bin/ctest", "--show-only=json-v1"], 0)
    test, = json.loads(inventory)["tests"]
    assert test["name"] == "disabled-only"
    properties = {row["name"]: row["value"] for row in test["properties"]}
    assert properties["DISABLED"] is True
    assert test["command"][-2:] == ["-E", "false"]
    call(build, "run", ["/workspace/cppulse/.venv/bin/ctest", "--output-on-failure",
                        "--output-junit", "junit.xml"], plans["disabled"]["native_exit"])
    ctest_report = build / "junit.xml"
    case, = ElementTree.parse(ctest_report).getroot().iter("testcase")
    assert case.get("name") == "disabled-only" and case.get("status") == "disabled"
    assert case.find("failure") is None and (build / "Testing/Temporary/LastTest.log").is_file()

    pytest_dir = folder / "pytest"
    pytest_dir.mkdir()
    copy(lane / "fixture-pytest.py", pytest_dir / "test_producer_fixture.py")
    version = call(pytest_dir, "version", [sys.executable, "-B", "-m", "pytest", "--version"], 0)
    assert version.strip() == "pytest 8.0.0"
    call(pytest_dir, "run", [sys.executable, "-B", "-m", "pytest", "-c", "/dev/null",
                             "-p", "no:cacheprovider", "--basetemp", "scratch", "-q",
                             "--junitxml=junit.xml", "test_producer_fixture.py"],
         plans["pytest"]["native_exit"])
    return {
        "disabled": {"path": str(ctest_report), "sha256": digest(ctest_report),
                     "producer_command_receipt": str(build / "run.command.json")},
        "pytest": {"path": str(pytest_dir / "junit.xml"), "sha256": digest(pytest_dir / "junit.xml"),
                   "producer_command_receipt": str(pytest_dir / "run.command.json")},
    }
