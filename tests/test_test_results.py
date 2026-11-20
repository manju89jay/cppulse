"""Local report parsing observes outcomes without proving producer execution."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import shutil
import subprocess
from typing import Any

import pytest

from cppulse.adapters.test_results import MAX_REPORT_BYTES, parse_test_report

CTEST = {"name": "ctest", "version": "3.31.6"}
GENERIC = {"name": "synthetic-junit-import", "version": "1.0"}


def parse_xml(tmp_path: Path, text: str, **options: Any) -> Any:
    """Parse one clearly synthetic generic-JUnit transport fixture."""
    path = tmp_path / "report.xml"
    path.write_text(text, encoding="utf-8")
    return parse_test_report(path, adapter="generic-junit", producer=GENERIC, **options)


@pytest.fixture(scope="module")
def actual_ctest_reports(
    tmp_path_factory: pytest.TempPathFactory,
) -> dict[str, tuple[Path, int]]:
    """Generate real CTest 3.31.6 reports from a tiny selected CMake-only project."""
    cmake, ctest = shutil.which("cmake"), shutil.which("ctest")
    if cmake is None or ctest is None:
        pytest.skip("Actual CTest fixtures require CMake and CTest 3.31.6")
    version = subprocess.run(
        [ctest, "--version"], capture_output=True, text=True, check=True
    ).stdout
    if version.splitlines()[0] != "ctest version 3.31.6":
        pytest.skip(
            f"Adapter declares only CTest 3.31.6; actual tool is {version.splitlines()[0]}"
        )
    root = tmp_path_factory.mktemp("actual-ctest-junit")
    reports = {}
    for mode in ("clean", "fail", "skip", "disabled", "zero"):
        source, build = root / mode / "source", root / mode / "build"
        source.mkdir(parents=True)
        cmake_text = "cmake_minimum_required(VERSION 3.20)\nproject(AdapterFixture LANGUAGES NONE)\nenable_testing()\n"
        if mode in {"clean", "fail"}:
            script = source / "case.cmake"
            script.write_text(
                'execute_process(COMMAND "${CMAKE_COMMAND}" -E echo "stdout café λ")\nmessage("stderr café λ")\n'
                + (
                    'message(FATAL_ERROR "Intentional fixture failure")\n'
                    if mode == "fail"
                    else ""
                ),
                encoding="utf-8",
            )
            cmake_text += (
                f'add_test(NAME {mode} COMMAND "${{CMAKE_COMMAND}}" -P "{script}")\n'
            )
        elif mode == "skip":
            cmake_text += 'add_test(NAME skip COMMAND "${CMAKE_COMMAND}" -E false)\nset_tests_properties(skip PROPERTIES SKIP_RETURN_CODE 1)\n'
        elif mode == "disabled":
            cmake_text += 'add_test(NAME disabled COMMAND "${CMAKE_COMMAND}" -E false)\nset_tests_properties(disabled PROPERTIES DISABLED TRUE)\n'
        (source / "CMakeLists.txt").write_text(cmake_text)
        configured = subprocess.run(
            [cmake, "-S", str(source), "-B", str(build)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert configured.returncode == 0, configured.stdout + configured.stderr
        report = root / mode / "junit.xml"
        run = subprocess.run(
            [
                ctest,
                "--test-dir",
                str(build),
                "--output-junit",
                str(report),
                "--output-on-failure",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        (root / mode / "ctest.stdout.log").write_text(run.stdout)
        (root / mode / "ctest.stderr.log").write_text(run.stderr)
        assert report.is_file(), run.stdout + run.stderr
        reports[mode] = (report, run.returncode)
    return reports


@pytest.mark.parametrize(
    ("mode", "expected", "status"),
    [
        (
            "clean",
            {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "errors": 0},
            "passed",
        ),
        (
            "fail",
            {"total": 1, "passed": 0, "failed": 1, "skipped": 0, "errors": 0},
            "failed",
        ),
        (
            "skip",
            {"total": 1, "passed": 0, "failed": 0, "skipped": 1, "errors": 0},
            "skipped",
        ),
        (
            "disabled",
            {"total": 1, "passed": 0, "failed": 0, "skipped": 1, "errors": 0},
            "skipped",
        ),
        (
            "zero",
            {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "errors": 0},
            "skipped",
        ),
    ],
)
def test_actual_ctest_reports(
    actual_ctest_reports: dict[str, tuple[Path, int]],
    mode: str,
    expected: dict[str, int],
    status: str,
) -> None:
    report, exit_code = actual_ctest_reports[mode]
    result = parse_test_report(report, producer=CTEST)
    assert result.usability == "usable", result.limitations
    assert result.counts == expected
    assert result.status == status
    assert exit_code == (8 if mode == "fail" else 0)
    if mode == "disabled":
        assert any("disabled" in limit.lower() for limit in result.limitations)
    if mode in {"clean", "fail"}:
        assert "stdout café λ" in report.read_text()
        assert "stderr café λ" in report.read_text()


def test_multisuite_failures_and_operational_errors_are_observed_not_passed(
    tmp_path: Path,
) -> None:
    result = parse_xml(
        tmp_path,
        """<testsuites tests="4" failures="1" errors="1" skipped="1">
      <testsuite name="suite" tests="4" failures="1" errors="1" skipped="1">
        <testcase classname="fixture" name="pass"><system-out>café λ &amp; stdout</system-out><system-err>stderr</system-err></testcase>
        <testcase name="fail"><failure message="intentional"/></testcase>
        <testcase name="error"><error message="harness error"/></testcase>
        <testcase name="skip"><skipped/></testcase>
      </testsuite></testsuites>""",
    )
    assert result.usability == "usable"
    assert result.status == "error"
    assert result.counts == {
        "total": 4,
        "passed": 1,
        "failed": 1,
        "skipped": 1,
        "errors": 1,
    }
    assert result.origin == "import"
    assert any("execution" in limitation for limitation in result.limitations)
    assert json.loads(json.dumps(result.as_dict()))["counts"] == result.counts


def test_duplicate_cases_preserve_failed_attempt_instead_of_last_pass_winning(
    tmp_path: Path,
) -> None:
    result = parse_xml(
        tmp_path,
        '<testsuite name="repeat" tests="2" failures="1"><testcase classname="same" name="retry"><failure/></testcase><testcase classname="same" name="retry"/></testsuite>',
    )
    assert result.usability == "usable"
    assert result.status == "failed"
    assert result.failed == 1 and result.passed == 1
    assert len({case.identity for case in result.cases}) == 2
    assert [case.name for case in result.cases] == ["retry", "retry"]
    assert any("duplicate" in limitation.lower() for limitation in result.limitations)


@pytest.mark.parametrize(
    "body",
    [
        '<testsuite tests="2"><testcase name="one"/></testsuite>',
        '<testsuite tests="1" failures="1"><testcase name="one"/></testsuite>',
        '<testsuite tests="1.0"><testcase name="one"/></testsuite>',
        '<testsuite tests="-1"/>',
        '<testsuite><testcase name="one" status="mystery"/></testsuite>',
        '<testsuite><testcase name="one" status="passed"><failure/></testcase></testsuite>',
        '<testsuite><testcase name="one" status="disabled"><failure/></testcase></testsuite>',
        '<testsuite><testcase name="one"><failure/><skipped/></testcase></testsuite>',
        '<testsuite><testcase name="one" time="NaN"/></testsuite>',
        '<testsuite><testcase name="one" time="inf"/></testsuite>',
        '<testsuite><testcase name="one" time="-1"/></testsuite>',
        '<testsuite time="NaN"><testcase name="one"/></testsuite>',
        '<testsuite><testcase name="one"><system-out><failure/></system-out></testcase></testsuite>',
        '<testsuite><testcase name="one"><properties><testcase name="hidden"/></properties></testcase></testsuite>',
        "<testsuite><testcase/></testsuite>",
        '<testsuite><testcase name="one">',
    ],
)
def test_invalid_report_never_invents_zero_or_success(
    tmp_path: Path, body: str
) -> None:
    result = parse_xml(tmp_path, body)
    assert result.usability == "malformed"
    assert result.status == "error"
    assert result.counts is None
    assert result.total is None
    assert result.cases == ()
    assert result.limitations


@pytest.mark.parametrize(
    "body",
    [
        '<!DOCTYPE testsuite [<!ENTITY huge "expanded">]><testsuite><testcase name="&huge;"/></testsuite>',
        '<!DOCTYPE testsuite SYSTEM "file:///etc/passwd"><testsuite/>',
    ],
)
def test_dtd_and_entities_are_rejected_without_resolution(
    tmp_path: Path, body: str
) -> None:
    result = parse_xml(tmp_path, body)
    assert result.usability == "malformed"
    assert result.counts is None
    assert any(
        "DTD" in limitation or "entit" in limitation
        for limitation in result.limitations
    )


def test_cdata_markup_and_standard_escaped_characters_are_safe_text(
    tmp_path: Path,
) -> None:
    result = parse_xml(
        tmp_path,
        '<testsuite tests="1"><testcase name="a &amp; λ"><system-out><![CDATA[<!DOCTYPE text only>]]></system-out></testcase></testsuite>',
    )
    assert result.usability == "usable"
    assert result.cases[0].name == "a & λ"


@pytest.mark.parametrize(
    ("options", "reason"),
    [
        ({"adapter": "unknown"}, "adapter"),
        ({"adapter_version": "9.0.0"}, "version"),
        ({"producer": {"name": "ctest", "version": "3.31.5"}}, "3.31.6"),
        ({"producer": {"name": "not-ctest", "version": "3.31.6"}}, "ctest"),
    ],
)
def test_unknown_adapter_or_ctest_producer_is_explicitly_unsupported(
    tmp_path: Path, options: dict[str, Any], reason: str
) -> None:
    path = tmp_path / "report.xml"
    path.write_text('<testsuite tests="1"><testcase name="one"/></testsuite>')
    arguments = {"producer": CTEST, **options}
    result = parse_test_report(path, **arguments)
    assert result.usability == "unsupported"
    assert result.counts is None
    assert result.report_sha256 is None and result.size_bytes is None
    assert reason in " ".join(result.limitations)


def test_missing_report_is_distinct_from_observed_zero_tests(tmp_path: Path) -> None:
    result = parse_test_report(tmp_path / "missing.xml", producer=CTEST)
    assert result.usability == "missing"
    assert result.status == "error"
    assert result.total is None
    assert result.counts is None
    assert result.report_sha256 is None and result.size_bytes is None


def test_size_depth_and_node_limits_are_enforced(tmp_path: Path) -> None:
    path = tmp_path / "large.xml"
    with path.open("wb") as stream:
        stream.truncate(MAX_REPORT_BYTES + 1)
    result = parse_test_report(path, producer=CTEST)
    assert result.usability == "malformed"
    assert result.report_sha256 is None and result.size_bytes is None
    assert any("byte" in limitation for limitation in result.limitations)
    result = parse_xml(tmp_path, "<testsuite>" * 65 + "</testsuite>" * 65)
    assert result.usability == "malformed"
    assert any("depth" in limitation for limitation in result.limitations)
    result = parse_xml(
        tmp_path,
        "<testsuite><properties>"
        + "<property/>" * 100_000
        + "</properties></testsuite>",
    )
    assert result.usability == "malformed"
    assert any("node" in limitation for limitation in result.limitations)


def test_parser_never_executes_commands_or_mutates_declared_producer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def reject_execution(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("A report parser must never execute commands")

    monkeypatch.setattr(subprocess, "run", reject_execution)
    path = tmp_path / "report.xml"
    path.write_text('<testsuite tests="1"><testcase name="reported-only"/></testsuite>')
    producer = dict(CTEST)
    result = parse_test_report(path, producer=producer)
    producer["name"] = "edited by caller"
    assert result.producer == CTEST
    assert result.origin == "import"


def test_nested_suites_and_disabled_counts_preserve_total(tmp_path: Path) -> None:
    result = parse_xml(
        tmp_path,
        """<testsuites tests="2" skipped="0" disabled="1">
      <testsuite name="outer" tests="2" skipped="0" disabled="1">
        <testsuite name="inner" tests="2" skipped="0" disabled="1">
          <testcase name="normal" time="0.125"/>
          <testcase name="disabled" status="disabled"><skipped/></testcase>
        </testsuite>
      </testsuite></testsuites>""",
    )
    assert result.usability == "usable", result.limitations
    assert result.counts == {
        "total": 2,
        "passed": 1,
        "failed": 0,
        "skipped": 1,
        "errors": 0,
    }
    assert result.cases[0].duration_seconds == 0.125


@pytest.mark.parametrize(
    "body",
    [
        "<not-junit/>",
        '<j:testsuite xmlns:j="urn:unsupported" tests="0"/>',
        '<testsuite xmlns="urn:unsupported" tests="1"><testcase name="claimed-pass"/></testsuite>',
        '<testsuite tests="1"><testcase xmlns="urn:unsupported" name="claimed-pass"/></testsuite>',
    ],
)
def test_other_xml_formats_are_unsupported_not_empty_pass(
    tmp_path: Path, body: str
) -> None:
    result = parse_xml(tmp_path, body)
    assert result.usability == "unsupported"
    assert result.counts is None
    assert result.report_sha256 == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert result.size_bytes == len(body.encode("utf-8"))


def test_non_utf8_and_nonregular_reports_are_unavailable(tmp_path: Path) -> None:
    import os

    path = tmp_path / "report.xml"
    path.write_bytes(b"\xff\xfeinvalid UTF-8")
    assert parse_test_report(path, producer=CTEST).usability == "malformed"
    path.unlink()
    os.mkfifo(path)
    assert parse_test_report(path, producer=CTEST).usability == "malformed"
    path.unlink()
    target = tmp_path / "other.xml"
    target.write_text('<testsuite tests="0"/>')
    path.symlink_to(target)
    assert parse_test_report(path, producer=CTEST).usability == "missing"


def test_report_encoding_declaration_and_producer_fields_are_checked(
    tmp_path: Path,
) -> None:
    result = parse_xml(
        tmp_path, '<?xml version="1.0" encoding="ISO-8859-1"?><testsuite/>'
    )
    assert result.usability == "malformed"
    path = tmp_path / "report.xml"
    for producer in ({}, {"name": "ctest", "version": ""}):
        assert parse_test_report(path, producer=producer).usability == "unsupported"


def test_report_digest_binds_the_same_bytes_parsed_after_path_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cppulse.adapters.test_results as adapter

    path = tmp_path / "report.xml"
    original = b'<testsuite tests="1"><testcase name="original"/></testsuite>'
    changed = b'<testsuite tests="1" failures="1"><testcase name="changed"><failure/></testcase></testsuite>'
    path.write_bytes(original)
    read = adapter._read_xml

    def replace_after_read(selected: Path) -> bytes:
        content = read(selected)
        selected.write_bytes(changed)
        return content

    monkeypatch.setattr(adapter, "_read_xml", replace_after_read)
    report = adapter.parse_test_report(path, producer=CTEST)
    assert report.status == "passed"
    assert report.cases[0].name == "original"
    assert report.report_sha256 == hashlib.sha256(original).hexdigest()
    assert report.size_bytes == len(original)
    assert report.report_sha256 != hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("content", [b"<testsuite>", b"\xffbad UTF-8"])
def test_malformed_observed_bytes_still_have_an_exact_digest(
    tmp_path: Path, content: bytes
) -> None:
    path = tmp_path / "report.xml"
    path.write_bytes(content)
    result = parse_test_report(path, producer=CTEST)
    assert result.usability == "malformed"
    assert result.counts is None
    assert result.report_sha256 == hashlib.sha256(content).hexdigest()
    assert result.size_bytes == len(content)
