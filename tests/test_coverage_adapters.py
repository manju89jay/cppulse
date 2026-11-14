"""Coverage report claims stay bounded, exact and distinct by measurement kind."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from cppulse.adapters.coverage import CoverageReport, parse_coverage_report

PRODUCER = {"name": "gcovr", "version": "8.8"}
LCOV = """TN:synthetic parser fixture
SF:src/example.cpp
FN:1,choose(int, bool)
FN:8,unused()
FNDA:2,choose(int, bool)
FNDA:0,unused()
FNF:2
FNH:1
BRDA:2,0,0,2
BRDA:2,0,1,0
BRDA:9,0,0,-
BRF:3
BRH:1
DA:1,2
DA:2,2
DA:8,0
DA:9,0
LF:4
LH:2
end_of_record
"""
COBERTURA = """<?xml version="1.0"?>
<!DOCTYPE coverage SYSTEM "http://cobertura.sourceforge.net/xml/coverage-04.dtd">
<coverage version="gcovr 8.8" lines-valid="2" lines-covered="1" branches-valid="4" branches-covered="2" line-rate="0.5" branch-rate="0.5">
<sources><source>/selected</source></sources><packages><package name="src" line-rate="0.5" branch-rate="0.5"><classes>
<class name="example" filename="src/example.cpp" line-rate="0.5" branch-rate="0.5"><methods/>
<lines><line number="2" hits="2" branch="true" condition-coverage="50% (2/4)"><conditions><condition number="0" type="jump" coverage="50%"/></conditions></line><line number="8" hits="0" branch="false"/></lines>
</class></classes></package></packages></coverage>
"""


def parse(tmp_path: Path, value: str, adapter: str = "lcov") -> CoverageReport:
    """Read a clearly synthetic file without asserting execution provenance."""
    path = tmp_path / "coverage-report"
    path.write_text(value)
    return parse_coverage_report(path, adapter, producer=PRODUCER)


def test_lcov_exact_line_branch_function_units_and_parsed_identity(
    tmp_path: Path,
) -> None:
    report = parse(tmp_path, LCOV)
    assert report.usability == "usable" and report.origin == "import"
    assert report.report_sha256 == hashlib.sha256(LCOV.encode()).hexdigest()
    assert report.size_bytes == len(LCOV.encode())
    assert report.files[0].source_sha256 is None
    measurements = {row.kind: row for row in report.files[0].measurements}
    assert (measurements["line"].covered, measurements["line"].total) == (2, 4)
    assert (measurements["branch"].covered, measurements["branch"].total) == (1, 3)
    assert (measurements["function"].covered, measurements["function"].total) == (1, 2)
    assert len({unit.id for unit in measurements["branch"].units}) == 3


def test_cobertura_branch_group_does_not_invent_edges_or_function_calls(
    tmp_path: Path,
) -> None:
    report = parse(tmp_path, COBERTURA, "cobertura")
    assert report.usability == "usable"
    assert report.sources == ("/selected",)
    measurements = {row.kind: row for row in report.files[0].measurements}
    assert (measurements["line"].covered, measurements["line"].total) == (1, 2)
    assert (measurements["branch"].covered, measurements["branch"].total) == (2, 4)
    assert len(measurements["branch"].units) == 1
    assert "function" not in measurements


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.replace("LF:4", "LF:5"),
        lambda value: value.replace("BRH:1", "BRH:3"),
        lambda value: value.replace("FNH:1", "FNH:2"),
        lambda value: value.replace("DA:2,2", "DA:1,2"),
        lambda value: value.replace("BRDA:2,0,1,0", "BRDA:2,0,0,0"),
        lambda value: value.replace("FNDA:0,unused()", "FNDA:-1,unused()"),
    ],
)
def test_lcov_inconsistent_totals_and_duplicate_units_are_malformed(
    tmp_path: Path, change: Callable[[str], str]
) -> None:
    report = parse(tmp_path, change(LCOV))
    assert report.usability == "malformed"
    assert report.files == ()
    assert report.report_sha256 is not None


def test_gcovr_88_exception_arcs_have_distinct_stable_branch_units(
    tmp_path: Path,
) -> None:
    value = LCOV.replace("BRDA:9,0,0,-", "BRDA:9,e0,0,-")
    report = parse(tmp_path, value)
    assert report.usability == "usable"
    measurement = next(
        row for row in report.files[0].measurements if row.kind == "branch"
    )
    assert (measurement.covered, measurement.total) == (1, 3)
    both = (
        value.replace("BRDA:9,e0,0,-", "BRDA:9,e0,0,-\nBRDA:9,0,0,1")
        .replace("BRF:3", "BRF:4")
        .replace("BRH:1", "BRH:2")
    )
    report = parse(tmp_path, both)
    assert report.usability == "usable"
    measurement = next(
        row for row in report.files[0].measurements if row.kind == "branch"
    )
    assert len({row.id for row in measurement.units}) == 4


def test_gcovr_88_pinned_cobertura_doctype_is_recognized_without_fetching(
    tmp_path: Path,
) -> None:
    value = COBERTURA.replace(
        "http://cobertura.sourceforge.net/xml/coverage-04.dtd",
        "https://github.com/cobertura/cobertura/blob/e5eea8679ebce047ec6ccdfdbf6cf2c14b376875/cobertura/src/site/htdocs/xml/coverage-04.dtd",
    )
    assert parse(tmp_path, value, "cobertura").usability == "usable"
    assert (
        parse(
            tmp_path,
            value.replace("e5eea8679ebce047ec6ccdfdbf6cf2c14b376875", "unknown"),
            "cobertura",
        ).usability
        == "malformed"
    )


def test_repeated_source_shards_are_not_summed_or_averaged(tmp_path: Path) -> None:
    report = parse(tmp_path, LCOV + LCOV)
    assert report.usability == "unsupported"
    assert report.files == ()


@pytest.mark.parametrize(
    "value",
    [
        LCOV.replace("end_of_record\n", ""),
        LCOV.replace("DA:8,0", "DA:8,nan"),
        LCOV + "UNKNOWN:1\n",
    ],
)
def test_lcov_truncated_and_unknown_dialects_do_not_pass(
    tmp_path: Path, value: str
) -> None:
    assert parse(tmp_path, value).usability in {"malformed", "unsupported"}


def test_cobertura_exact_counts_check_class_and_root_summaries(tmp_path: Path) -> None:
    value = COBERTURA.replace('lines-covered="1"', 'lines-covered="2"')
    assert parse(tmp_path, value, "cobertura").usability == "malformed"
    value = COBERTURA.replace('line-rate="0.5"', 'line-rate="0"')
    assert parse(tmp_path, value, "cobertura").usability == "malformed"


def test_gcovr_truncated_condition_percentage_preserves_exact_counts(
    tmp_path: Path,
) -> None:
    value = (
        COBERTURA.replace('branches-valid="4"', 'branches-valid="3"')
        .replace('branch-rate="0.5"', 'branch-rate="0.6666666666666666"')
        .replace("50% (2/4)", "66% (2/3)")
        .replace('coverage="50%"', 'coverage="66%"')
    )
    report = parse(tmp_path, value, "cobertura")
    assert report.usability == "usable"
    branch = next(row for row in report.files[0].measurements if row.kind == "branch")
    assert (branch.covered, branch.total) == (2, 3)


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.replace(
            '<package name="src" line-rate="0.5"', '<package name="src" line-rate="0.0"'
        ),
        lambda value: value.replace('coverage="50%"', 'coverage="0%"'),
        lambda value: value.replace("<methods/>", "<methods><unexpected/></methods>"),
    ],
)
def test_cobertura_contradictory_or_unknown_nested_metadata_is_not_usable(
    tmp_path: Path, change: Callable[[str], str]
) -> None:
    assert parse(tmp_path, change(COBERTURA), "cobertura").usability != "usable"
    value = COBERTURA.replace("50% (2/4)", "50% (5/4)")
    assert parse(tmp_path, value, "cobertura").usability == "malformed"


@pytest.mark.parametrize(
    "value",
    [
        COBERTURA.replace("<coverage ", '<coverage xmlns="urn:unknown" ', 1),
        COBERTURA.replace("<sources>", "<unexpected>"),
        '<!DOCTYPE coverage [<!ENTITY x "injected">]><coverage/>',
    ],
)
def test_xml_namespaces_entities_and_unknown_shapes_fail_closed(
    tmp_path: Path, value: str
) -> None:
    assert parse(tmp_path, value, "cobertura").usability in {"malformed", "unsupported"}


def test_zero_denominators_are_known_counts_not_a_pass_percentage(
    tmp_path: Path,
) -> None:
    report = parse(
        tmp_path,
        "SF:empty.cpp\nLF:0\nLH:0\nBRF:0\nBRH:0\nFNF:0\nFNH:0\nend_of_record\n",
    )
    assert report.usability == "usable"
    assert all(row.covered == row.total == 0 for row in report.files[0].measurements)
    assert parse(tmp_path, "").files == ()


def test_nonregular_and_missing_reports_have_no_invented_zero(tmp_path: Path) -> None:
    report = parse_coverage_report(tmp_path / "absent", "lcov", producer=PRODUCER)
    assert report.usability == "missing" and report.files == ()
    assert report.report_sha256 is None


def test_reports_are_bounded_before_reading_and_unknown_adapters_are_unsupported(
    tmp_path: Path,
) -> None:
    import cppulse.adapters.coverage as module

    path = tmp_path / "large.info"
    with path.open("wb") as stream:
        stream.truncate(module.MAX_REPORT_BYTES + 1)
    assert (
        parse_coverage_report(path, "lcov", producer=PRODUCER).usability
        == "unsupported"
    )
    assert (
        parse_coverage_report(path, "unknown", producer=PRODUCER).usability
        == "unsupported"
    )
