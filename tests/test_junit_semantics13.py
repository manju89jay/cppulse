"""Closed outcome structure; imported XML never proves a test executed."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from cppulse.adapters import test_results as candidate


def parse(tmp_path: Path, text: str):
    path = tmp_path / "report.xml"
    path.write_text(text)
    return candidate.parse_test_report(
        path, "generic-junit", producer={"name": "fixture", "version": "1"}
    )


@pytest.mark.parametrize(
    "outer,inner",
    [
        ("skipped", "failure"),
        ("skipped", "error"),
        ("skipped", "testcase"),
        ("failure", "error"),
        ("error", "failure"),
        ("failure", "testcase"),
    ],
)
def test_nested_outcome_structure_cannot_publish_supported_case_counts(
    tmp_path: Path, outer: str, inner: str
) -> None:
    text = f'<testsuite tests="2"><testcase name="control"/><testcase name="hidden"><{outer}><{inner} name="concealed"/></{outer}></testcase></testsuite>'
    report = parse(tmp_path, text)
    assert report.usability == "malformed"
    assert report.status == "error" and report.counts is None
    assert report.cases == ()
    assert report.report_sha256 == hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.parametrize(
    "marker,expected",
    [("skipped", "skipped"), ("failure", "failed"), ("error", "error")],
)
def test_outcome_text_and_cdata_are_not_reinterpreted_as_nested_cases(
    tmp_path: Path, marker: str, expected: str
) -> None:
    text = f'<testsuite tests="1"><testcase name="literal"><{marker} message="reported"><![CDATA[<testcase><failure/></testcase>]]></{marker}></testcase></testsuite>'
    report = parse(tmp_path, text)
    assert report.usability == "usable" and report.status == expected
    assert report.total == 1


def test_multiple_failure_messages_still_describe_one_failed_occurrence(
    tmp_path: Path,
) -> None:
    report = parse(
        tmp_path,
        '<testsuite tests="1" failures="1"><testcase name="case"><failure>first</failure><failure>second</failure></testcase></testsuite>',
    )
    assert report.usability == "usable" and report.failed == 1 and report.total == 1


def test_nested_suite_totals_keep_failed_retry_disabled_and_empty_distinct(
    tmp_path: Path,
) -> None:
    text = '<testsuites tests="3" failures="1" disabled="1" skipped="0"><testsuite name="nested" tests="3" failures="1" disabled="1" skipped="0"><testcase name="retry"><failure>first attempt</failure></testcase><testcase name="retry"/><testcase name="disabled" status="disabled"/></testsuite><testsuite name="empty" tests="0"/></testsuites>'
    report = parse(tmp_path, text)
    assert report.usability == "usable" and report.status == "failed"
    assert report.counts == {
        "total": 3,
        "passed": 1,
        "failed": 1,
        "skipped": 1,
        "errors": 0,
    }
    assert len({case.identity for case in report.cases}) == 3


def test_all_skipped_and_zero_are_never_passed(tmp_path: Path) -> None:
    for text, total in [
        ('<testsuite tests="0"/>', 0),
        (
            '<testsuite tests="1" skipped="1"><testcase name="skip"><skipped/></testcase></testsuite>',
            1,
        ),
    ]:
        report = parse(tmp_path, text)
        assert report.usability == "usable" and report.status == "skipped"
        assert report.total == total and report.passed == 0
