"""Literal UTF8 CTest identity fields remain data without executing commands."""

from pathlib import Path
import hashlib

import pytest

from cppulse.adapters import ctest_log as candidate

PRODUCER = {"name": "ctest", "version": "3.31.6"}
SEP = "-" * 58


def log(*, name="case", argument="literal value", directory="/selected/build"):
    return f"""Start testing: serialized fixture
{SEP}
1/1 Testing: {name}
1/1 Test: {name}
Command: "/selected/binary" "{argument}"
Directory: {directory}
"{name}" start time: serialized fixture
Output:
{SEP}
Authored log text; no command executes.
<end of output>
Test time =   0.01 sec
{SEP}
Test Passed.
"{name}" end time: serialized fixture
"{name}" time elapsed: 00:00:00
{SEP}

End testing: serialized fixture
"""


def parsed(tmp_path, text):
    path = tmp_path / "LastTest.log"
    path.write_bytes(text.encode())
    return candidate.parse_ctest_log(path, producer=PRODUCER)


def test_module_origin():
    here = Path(__file__).resolve()
    expected = (
        here.parent.parent / "python/cppulse/adapters/ctest_log.py"
        if here.parent.name == "tests"
        else here.with_name("ctest_log.py")
    )
    assert Path(candidate.__file__).resolve() == expected


@pytest.mark.parametrize("space", ["\u00a0", "\u2007", "\u202f", "\u3000"])
@pytest.mark.parametrize("field", ["argument", "directory", "name"])
def test_unicode_space_separators_inside_literal_identity_fields(
    tmp_path, space, field
):
    value = ("/selected/build" if field == "directory" else "literal") + space + "value"
    text = log(**{field: value})
    result = parsed(tmp_path, text)
    assert result.usability == "usable", result.limitations
    record = result.records[0]
    actual = {
        "argument": record.actual_argv[1],
        "directory": record.working_directory,
        "name": record.name,
    }[field]
    assert actual == value
    assert result.report_sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert result.size_bytes == len(text.encode())


@pytest.mark.parametrize(
    "character", ["\t", "\n", "\r", "\x00", "\x1b", "\u2028", "\u2029", "\u200b"]
)
@pytest.mark.parametrize("field", ["argument", "directory", "name"])
def test_controls_and_ambiguous_line_formatting_stay_unavailable(
    tmp_path, character, field
):
    value = (
        ("/selected/build" if field == "directory" else "literal") + character + "value"
    )
    result = parsed(tmp_path, log(**{field: value}))
    assert result.usability in ("unsupported", "malformed")
    assert result.records == ()


@pytest.mark.parametrize("space", [" ", "\u00a0", "\u3000"])
def test_padded_test_names_remain_unsupported(tmp_path, space):
    assert parsed(tmp_path, log(name=space + "case")).usability in (
        "unsupported",
        "malformed",
    )
    assert parsed(tmp_path, log(name="case" + space)).usability in (
        "unsupported",
        "malformed",
    )


def test_empty_disabled_invocation_stays_notrun_despite_passed_footer(tmp_path):
    text = (
        log()
        .replace('Command: "/selected/binary" "literal value"', 'Command: ""')
        .replace('"case" start time: serialized fixture', '"case" start time: ')
    )
    result = parsed(tmp_path, text)
    assert result.usability == "usable" and result.records[0].actual_argv == ()
    assert result.records[0].outcome == "notrun"


def test_zero_test_session_never_invents_a_pass_record(tmp_path):
    text = (
        f"Start testing: serialized fixture\n{SEP}\nEnd testing: serialized fixture\n"
    )
    result = parsed(tmp_path, text)
    assert result.usability == "usable" and result.records == ()
    assert any("No execution records" in text for text in result.limitations)


def test_actual_ctest_nbsp_producer_preserves_argv_cwd_and_name(tmp_path):
    """Generate actual supported producer bytes; lead owns executing this gate."""
    import json
    import re
    import shutil
    import subprocess

    from cppulse.adapters.test_results import parse_test_report

    cmake, ctest = shutil.which("cmake"), shutil.which("ctest")
    if cmake is None or ctest is None:
        pytest.skip("Actual Unicode producer gate requires CMake/CTest3.31.6")
    for executable, expected in [
        (cmake, "cmake version 3.31.6"),
        (ctest, "ctest version 3.31.6"),
    ]:
        version = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        (tmp_path / (Path(executable).name + "-version.stdout")).write_text(
            version.stdout
        )
        (tmp_path / (Path(executable).name + "-version.stderr")).write_text(
            version.stderr
        )
        if version.returncode != 0 or version.stdout.splitlines()[:1] != [expected]:
            pytest.skip("Actual Unicode producer gate requires exactly " + expected)
    name = "case\u00a0name"
    argument = "literal\u00a0argument"
    source = tmp_path / "source"
    source.mkdir()
    build = tmp_path / "build\u00a0tree"
    directory = build / "working\u00a0directory"
    declaration = (
        "cmake_minimum_required(VERSION 3.20)\n"
        "project(UnicodeTraceFixture LANGUAGES NONE)\n"
        "enable_testing()\n"
        'file(MAKE_DIRECTORY "' + str(directory) + '")\n'
        'add_test(NAME "'
        + name
        + '" COMMAND "${CMAKE_COMMAND}" "-E" "echo" "'
        + argument
        + '")\n'
        'set_tests_properties("'
        + name
        + '" PROPERTIES WORKING_DIRECTORY "'
        + str(directory)
        + '")\n'
    )
    (source / "CMakeLists.txt").write_text(declaration, encoding="utf-8")
    configure_argv = [cmake, "-S", str(source), "-B", str(build)]
    configured = subprocess.run(
        configure_argv, capture_output=True, text=True, timeout=30, check=False
    )
    (tmp_path / "configure.stdout").write_text(configured.stdout)
    (tmp_path / "configure.stderr").write_text(configured.stderr)
    assert configured.returncode == 0, configured.stdout + configured.stderr
    junit = tmp_path / "junit.xml"
    run_argv = [
        ctest,
        "--test-dir",
        str(build),
        "--output-junit",
        str(junit),
        "--output-on-failure",
    ]
    executed = subprocess.run(
        run_argv, capture_output=True, text=True, timeout=30, check=False
    )
    (tmp_path / "ctest.stdout").write_text(executed.stdout)
    (tmp_path / "ctest.stderr").write_text(executed.stderr)
    assert executed.returncode == 0, executed.stdout + executed.stderr
    path = build / "Testing/Temporary/LastTest.log"
    raw = path.read_bytes()
    cache = (build / "CMakeCache.txt").read_text(encoding="utf-8")
    selected = re.findall(r"^CMAKE_COMMAND:INTERNAL=(.+)$", cache, re.M)
    assert len(selected) == 1
    expected_argv = (selected[0], "-E", "echo", argument)
    assert ("Testing: " + name).encode("utf-8") in raw
    assert ("Directory: " + str(directory)).encode("utf-8") in raw
    assert ('"' + argument + '"').encode("utf-8") in raw
    trace = candidate.parse_ctest_log(path, producer=PRODUCER)
    assert trace.usability == "usable", trace.limitations
    assert trace.report_sha256 == hashlib.sha256(raw).hexdigest()
    assert trace.size_bytes == len(raw) and len(trace.records) == 1
    record = trace.records[0]
    assert record.actual_argv == expected_argv
    assert record.working_directory == str(directory)
    assert record.name == name and record.outcome == "passed"
    report = parse_test_report(junit, producer=PRODUCER)
    assert report.usability == "usable" and report.status == "passed"
    assert len(report.cases) == 1 and report.cases[0].name == name
    (tmp_path / "producer-observation.json").write_text(
        json.dumps(
            {
                "fixture": "actual CMake/CTest3.31.6, LANGUAGES NONE; no compiler claim",
                "configure_argv": configure_argv,
                "configure_exit": configured.returncode,
                "ctest_argv": run_argv,
                "ctest_exit": executed.returncode,
                "raw_log_sha256": trace.report_sha256,
                "raw_log_size": trace.size_bytes,
                "argv": list(record.actual_argv),
                "cwd": record.working_directory,
                "name": record.name,
                "outcome": record.outcome,
                "junit_status": report.status,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
