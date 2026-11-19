"""Streaming native semantic parity without whole-report payload retention."""
from copy import deepcopy
from pathlib import Path
import weakref

import pytest

from cppulse.contracts.maintenance import validate_native_metrics
from cppulse.errors import ContractError, IntegrityError
from cppulse.streamed_native_metrics import (
    NativeMetricsLimits,
    validate_streamed_native_metrics,
)
from tests.test_maintenance_metrics_contract import native_metric_report


def pieces(document):
    analysis = document["metadata"]["analysis"]
    raw = analysis["native_metrics"]
    return (
        analysis["files"],
        raw["files"],
        {k: v for k, v in raw.items() if k != "files"},
    )


def run(tmp_path, document):
    a, m, h = pieces(document)
    return validate_streamed_native_metrics(
        iter(a), iter(m), metrics_header=h, directory=tmp_path
    )


def test_valid_roundtrip(tmp_path):
    result = run(tmp_path, native_metric_report())
    assert (
        result.checked and result.analysis_file_count == result.metric_file_count == 1
    )
    assert (
        not result.schema_verified
        and not result.native_executed
        and not result.source_verified
        and not result.analysis_cache_eligible
    )
    assert not list(tmp_path.iterdir())


def test_no_raw_touches_no_iterable_or_filesystem(tmp_path):
    class Bad:
        def __iter__(self):
            raise AssertionError("not allowed")

    result = validate_streamed_native_metrics(
        Bad(), Bad(), metrics_header=None, directory=tmp_path / "absent"
    )
    assert (
        not result.checked
        and result.analysis_file_count == result.metric_file_count == 0
    )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "mutation",
    [
        "status",
        "error_count",
        "complete_partial",
        "function_count",
        "incomplete_count",
        "unobserved_zero",
        "loc",
        "missing_cell",
        "length_zero",
        "complexity_zero",
        "location",
        "length_extent",
        "missing_limitations",
        "unavailable_numeric",
        "token_limit",
        "retained_count",
        "over_budget",
        "complete_availability",
        "total_count",
        "partial_measured",
        "partial_reason",
        "total_under",
        "token_location",
        "include_target",
    ],
)
def test_each_original_rule_invalid_parity(tmp_path, mutation):
    d = native_metric_report()
    a, m, h = pieces(d)
    r = m[0]
    f = r["functions"][0]
    t = r["token_stream"]
    if mutation == "status":
        r["status"] = "partial"
    elif mutation == "error_count":
        r["error_count"] = 1
    elif mutation == "complete_partial":
        a[0]["status"] = r["status"] = "partial"
    elif mutation == "function_count":
        r["function_count"] = 0
    elif mutation == "incomplete_count":
        r["measurement_complete"] = False
    elif mutation == "unobserved_zero":
        a[0]["status"] = r["status"] = "unavailable"
        r["measurement_complete"] = False
        r["function_count"] = None
    elif mutation == "loc":
        r["code_loc"] = 2
    elif mutation == "missing_cell":
        f["parameter_count"] = None
    elif mutation == "length_zero":
        f["function_length"] = 0
    elif mutation == "complexity_zero":
        f["cyclomatic_complexity"] = 0
    elif mutation == "location":
        f["end_column"] = 0
    elif mutation == "length_extent":
        f["function_length"] = 2
    elif mutation == "missing_limitations":
        f["availability"] = "partial"
    elif mutation == "unavailable_numeric":
        f.update(availability="unavailable", limitations=["unknown"])
    elif mutation == "token_limit":
        t["record_limit"] = 1
    elif mutation == "retained_count":
        t["retained_tokens"] = 0
    elif mutation == "over_budget":
        h["max_token_records"] = t["record_limit"] = 0
        d["metadata"]["analysis"]["native_metrics"]["max_token_records"] = 0
    elif mutation == "complete_availability":
        t["availability"] = "partial"
    elif mutation == "total_count":
        t["total_tokens"] = 2
    elif mutation == "partial_measured":
        t.update(complete=False, limitations=["partial"])
    elif mutation == "partial_reason":
        t.update(complete=False, availability="partial")
    elif mutation == "total_under":
        t.update(
            complete=False,
            availability="partial",
            limitations=["partial"],
            total_tokens=0,
        )
    elif mutation == "token_location":
        t["records"][0]["end_column"] = 0
    else:
        r["includes"] = [
            {
                "source": "a.cpp",
                "target": "../outside",
                "target_kind": "project",
                "direct": True,
            }
        ]
    with pytest.raises(ContractError):
        validate_native_metrics(d)
    with pytest.raises(ContractError):
        run(tmp_path, d)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "mutation",
    ["duplicate_analysis", "duplicate_metric", "missing_metric", "extra_metric"],
)
def test_coverage_parity(tmp_path, mutation):
    d = native_metric_report()
    a, m, h = pieces(d)
    if mutation == "duplicate_analysis":
        a.append(deepcopy(a[0]))
    elif mutation == "duplicate_metric":
        m.append(deepcopy(m[0]))
    elif mutation == "missing_metric":
        m.clear()
    else:
        m.append({**deepcopy(m[0]), "path": "other"})
    with pytest.raises(ContractError):
        validate_native_metrics(d)
    with pytest.raises(ContractError):
        run(tmp_path, d)
    assert not list(tmp_path.iterdir())


def test_truncated_valid_and_empty(tmp_path):
    d = native_metric_report()
    a, m, h = pieces(d)
    m[0]["token_stream"].update(
        complete=False,
        availability="partial",
        total_tokens=2,
        limitations=["truncated"],
    )
    validate_native_metrics(d)
    assert run(tmp_path, d).checked
    a.clear()
    m.clear()
    validate_native_metrics(d)
    assert run(tmp_path, d).checked


@pytest.mark.parametrize("kind", ["analysis", "metrics"])
def test_one_row_liveness(tmp_path, kind):
    class Row(dict):
        pass

    base = native_metric_report()
    a, m, h = pieces(base)

    def rows(template):
        ref = None
        for i in range(3):
            if ref is not None:
                assert ref() is None, "previous payload retained"
            row = Row(deepcopy(template))
            row["path"] = str(i)
            ref = weakref.ref(row)
            yield row
            del row

    ar = (
        rows(a[0])
        if kind == "analysis"
        else [{**a[0], "path": str(i)} for i in range(3)]
    )
    mr = (
        rows(m[0])
        if kind == "metrics"
        else [{**deepcopy(m[0]), "path": str(i)} for i in range(3)]
    )
    assert (
        validate_streamed_native_metrics(
            ar, mr, metrics_header=h, directory=tmp_path
        ).metric_file_count
        == 3
    )


@pytest.mark.parametrize(
    "limits",
    [
        NativeMetricsLimits(max_files=True),
        NativeMetricsLimits(max_database_bytes=1),
        NativeMetricsLimits(max_path_bytes=0),
    ],
)
def test_bad_limits_before_input(tmp_path, limits):
    def rows():
        raise AssertionError("input touched")
        yield

    with pytest.raises(ContractError):
        validate_streamed_native_metrics(
            rows(), rows(), metrics_header={}, directory=tmp_path, limits=limits
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("field", ["max_files", "max_path_bytes", "max_database_bytes"])
def test_capacity(tmp_path, field):
    d = native_metric_report()
    a, m, h = pieces(d)
    if field == "max_files":
        a.append({**a[0], "path": "second"})
        limits = NativeMetricsLimits(max_files=1)
    elif field == "max_path_bytes":
        limits = NativeMetricsLimits(max_path_bytes=1)
    else:
        for i in range(100):
            a.append({**a[0], "path": "x" * 100 + str(i)})
        limits = NativeMetricsLimits(max_database_bytes=8192)
    with pytest.raises(ContractError):
        validate_streamed_native_metrics(
            a, m, metrics_header=h, directory=tmp_path, limits=limits
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_generator_failure(tmp_path, error):
    a, m, h = pieces(native_metric_report())

    def rows():
        yield m[0]
        raise error("tail")

    with pytest.raises(error):
        validate_streamed_native_metrics(
            a, rows(), metrics_header=h, directory=tmp_path
        )
    assert not list(tmp_path.iterdir())


@pytest.fixture(autouse=True)
def source_origin():
    import cppulse.streamed_native_metrics as module

    assert (
        Path(module.__file__).resolve()
        == Path(__file__).resolve().parents[1]
        / "python/cppulse/streamed_native_metrics.py"
    )


def test_foreign_replacement_preserved(tmp_path):
    a, m, h = pieces(native_metric_report())

    def rows():
        yield m[0]
        p = next(tmp_path.glob("native-metrics-*.sqlite"))
        p.rename(tmp_path / "retired.sqlite")
        p.write_bytes(b"foreign sentinel")

    with pytest.raises(IntegrityError):
        validate_streamed_native_metrics(
            a, rows(), metrics_header=h, directory=tmp_path
        )
    assert (
        next(tmp_path.glob("native-metrics-*.sqlite")).read_bytes()
        == b"foreign sentinel"
    )
    assert (tmp_path / "retired.sqlite").exists()


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_analysis_generator_failure(tmp_path, error):
    a, m, h = pieces(native_metric_report())

    def rows():
        yield a[0]
        raise error("analysis tail")

    with pytest.raises(error):
        validate_streamed_native_metrics(
            rows(), m, metrics_header=h, directory=tmp_path
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "mode", ["partial_function", "unavailable_function", "failed_file"]
)
def test_valid_missingness_parity(tmp_path, mode):
    from cppulse.contracts.maintenance import FUNCTION_UNITS

    d = native_metric_report()
    a, m, h = pieces(d)
    r = m[0]
    f = r["functions"][0]
    if mode in ("partial_function", "unavailable_function"):
        f["availability"] = "partial" if mode == "partial_function" else "unavailable"
        f["limitations"] = ["Explicitly unmeasured function cells."]
        if mode == "unavailable_function":
            for k in FUNCTION_UNITS:
                f[k] = None
    else:
        a[0].update(status="failed", error_count=1)
        r.update(
            status="failed",
            error_count=1,
            measurement_complete=False,
            physical_loc=None,
            code_loc=None,
            function_count=None,
            functions=[],
        )
        r["token_stream"].update(
            availability="unavailable",
            complete=False,
            total_tokens=None,
            retained_tokens=0,
            records=[],
            limitations=["Parse failed."],
        )
    validate_native_metrics(d)
    assert run(tmp_path, d).checked


def test_reversed_inventory_order_and_unicode(tmp_path):
    d = native_metric_report()
    a, m, h = pieces(d)
    a.append({**a[0], "path": "/repo/λ space.cpp"})
    m.insert(0, {**deepcopy(m[0]), "path": "/repo/λ space.cpp"})
    validate_native_metrics(d)
    result = run(tmp_path, d)
    assert result.analysis_file_count == result.metric_file_count == 2


def test_header_and_iterable_shape_before_io(tmp_path):
    for header, analysis in [({"files": []}, []), ({}, None), ([], [])]:
        with pytest.raises(ContractError):
            validate_streamed_native_metrics(
                analysis, [], metrics_header=header, directory=tmp_path
            )
    assert not list(tmp_path.iterdir())
