"""Exact imported counter semantics; fixtures prove no execution provenance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from cppulse.adapters import coverage as candidate


def test_method_rate_work_tracks_units_and_aliases_not_their_product(
    tmp_path: Path, monkeypatch
) -> None:
    original = candidate.CoverageUnit.__getattribute__
    reads = 0

    def counted(unit, name):
        nonlocal reads
        if name == "line":
            reads += 1
        return original(unit, name)

    monkeypatch.setattr(candidate.CoverageUnit, "__getattribute__", counted)
    samples = []
    for count in (32, 64):
        lines = [
            f'<line number="{i + 1}" hits="1" branch="true" condition-coverage="50% (1/2)"/>'
            for i in range(count)
        ]
        methods = "".join(
            f'<method name="m{i}" line-rate="1" branch-rate="0.5"><lines>{line}</lines></method>'
            for i, line in enumerate(lines)
        )
        document = (
            '<coverage><packages><package><classes><class filename="a.cpp"><methods>'
            + methods
            + "</methods><lines>"
            + "".join(lines)
            + "</lines></class></classes></package></packages></coverage>"
        )
        reads = 0
        report = parse(tmp_path, document, "cobertura")
        assert report.usability == "usable"
        samples.append({"units": count, "line_reads": reads})
    (tmp_path / "operation-counts.json").write_text(json.dumps(samples))
    assert samples[1]["line_reads"] <= 3 * samples[0]["line_reads"], samples


def parse(tmp_path: Path, text: str, adapter: str):
    path = tmp_path / "coverage-report"
    path.write_text(text)
    return candidate.parse_coverage_report(
        path, adapter, producer={"name": "fixture", "version": "1"}
    )


@pytest.mark.parametrize("summary", ["LH", "BRH", "FNH"])
def test_hit_only_summary_does_not_invent_an_empty_unit_denominator(
    tmp_path: Path, summary: str
) -> None:
    text = f"SF:example.cpp\n{summary}:0\nend_of_record\n"
    report = parse(tmp_path, text, "lcov")
    assert report.usability == "malformed"
    assert report.files == ()
    assert report.report_sha256 == hashlib.sha256(text.encode()).hexdigest()


def cobertura(
    *, line_rate: str = "0", branch_rate: str = "0", duplicate: bool = False
) -> str:
    line = '<line number="2" hits="0" branch="true" condition-coverage="0% (0/2)"/>'
    return f'<coverage><packages><package><classes><class filename="example.cpp"><methods><method name="f" signature="()" line-rate="{line_rate}" branch-rate="{branch_rate}"><lines>{line}{line if duplicate else ""}</lines></method></methods><lines>{line}</lines></class></classes></package></packages></coverage>'


@pytest.mark.parametrize("line_rate,branch_rate", [("1", "0"), ("0", "1")])
def test_method_rates_must_agree_with_aliased_line_branch_units(
    tmp_path: Path, line_rate: str, branch_rate: str
) -> None:
    report = parse(
        tmp_path, cobertura(line_rate=line_rate, branch_rate=branch_rate), "cobertura"
    )
    assert report.usability == "malformed"
    assert report.files == ()


def test_repeated_method_lines_are_not_a_disjoint_method_inventory(
    tmp_path: Path,
) -> None:
    assert (
        parse(tmp_path, cobertura(duplicate=True), "cobertura").usability == "malformed"
    )


@pytest.mark.parametrize(
    "summary,kind", [("LF", "line"), ("BRF", "branch"), ("FNF", "function")]
)
def test_explicit_zero_found_count_remains_known_empty_not_unknown(
    tmp_path: Path, summary: str, kind: str
) -> None:
    report = parse(tmp_path, f"SF:empty.cpp\n{summary}:0\nend_of_record\n", "lcov")
    assert report.usability == "usable"
    measurement = next(row for row in report.files[0].measurements if row.kind == kind)
    assert measurement.covered == measurement.total == 0


@pytest.mark.parametrize(
    "records,summary,kind",
    [
        ("DA:2,0", "LH", "line"),
        ("BRDA:2,0,0,0", "BRH", "branch"),
        ("FN:2,fn\nFNDA:0,fn", "FNH", "function"),
    ],
)
def test_explicit_unit_inventory_can_supply_denominator_without_found_summary(
    tmp_path: Path, records: str, summary: str, kind: str
) -> None:
    report = parse(
        tmp_path, f"SF:example.cpp\n{records}\n{summary}:0\nend_of_record\n", "lcov"
    )
    assert report.usability == "usable"
    measurement = next(row for row in report.files[0].measurements if row.kind == kind)
    assert (measurement.covered, measurement.total) == (0, 1)


def test_valid_method_rates_do_not_invent_function_entry_counts(tmp_path: Path) -> None:
    report = parse(tmp_path, cobertura(), "cobertura")
    assert report.usability == "usable"
    measurements = {row.kind: row for row in report.files[0].measurements}
    assert set(measurements) == {"line", "branch"}
    assert (measurements["line"].covered, measurements["line"].total) == (0, 1)
    assert (measurements["branch"].covered, measurements["branch"].total) == (0, 2)


def test_method_rates_use_only_aliased_subset_not_class_denominator(
    tmp_path: Path,
) -> None:
    line = '<line number="2" hits="1" branch="true" condition-coverage="50% (1/2)"/>'
    text = f'<coverage><packages><package><classes><class filename="example.cpp"><methods><method name="f" signature="()" line-rate="1" branch-rate="0.5"><lines>{line}</lines></method></methods><lines>{line}<line number="3" hits="0"/></lines></class></classes></package></packages></coverage>'
    report = parse(tmp_path, text, "cobertura")
    assert report.usability == "usable"
    assert (
        next(row for row in report.files[0].measurements if row.kind == "line").total
        == 2
    )
    assert all(row.kind != "function" for row in report.files[0].measurements)


def test_unknown_denominator_in_later_file_does_not_publish_partial_claims(
    tmp_path: Path,
) -> None:
    text = "SF:known.cpp\nDA:2,1\nend_of_record\nSF:unknown.cpp\nLH:0\nend_of_record\n"
    report = parse(tmp_path, text, "lcov")
    assert report.usability == "malformed" and report.files == ()
    assert report.report_sha256 == hashlib.sha256(text.encode()).hexdigest()
