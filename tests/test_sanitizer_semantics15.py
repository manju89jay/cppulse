"""Tiny authored retained-log regressions, not actual sanitizer execution."""
from pathlib import Path

import pytest

from cppulse.adapters import gcc_sanitizer as adapter


def test_module_origin():
    here = Path(__file__).resolve()
    expected = (
        here.parent.parent / "python/cppulse/adapters/gcc_sanitizer.py"
        if here.parent.name == "tests"
        else here.with_name("gcc_sanitizer.py")
    )
    assert Path(adapter.__file__).resolve() == expected


ASAN = "==7==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x00\nSUMMARY: AddressSanitizer: heap-buffer-overflow fixture\n"
UBSAN = "main.cpp:55:40: runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'\n"
TSAN = "WARNING: ThreadSanitizer: data race (pid=9)\nSUMMARY: ThreadSanitizer: data race fixture\n"


def test_asan_summary_cannot_qualify_later_truncated_same_kind_report():
    result = adapter.diagnostics(
        ASAN + "==8==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x01\n",
        "asan",
    )
    assert len(result.records) == 1
    assert result.runtime_error


@pytest.mark.parametrize(
    "sanitizer,valid,unknown",
    [
        ("asan", ASAN, "AddressSanitizer:DEADLYSIGNAL\n"),
        ("ubsan", UBSAN, "other.cpp:1:2: runtime error: division by zero\n"),
        (
            "tsan",
            TSAN,
            "WARNING: ThreadSanitizer: lock-order-inversion (potential deadlock)\n",
        ),
    ],
)
def test_recognized_diagnostic_never_hides_unknown_failure(sanitizer, valid, unknown):
    result = adapter.diagnostics(valid + unknown, sanitizer)
    assert result.records
    assert result.runtime_error


def test_tsan_distinct_report_occurrences_preserved():
    result = adapter.diagnostics(TSAN + TSAN, "tsan")
    assert len(result.records) == 2
    assert result.runtime_error is None


def test_tsan_summary_does_not_qualify_later_truncated_warning():
    result = adapter.diagnostics(
        TSAN + "WARNING: ThreadSanitizer: data race (pid=10)\n", "tsan"
    )
    assert len(result.records) == 1
    assert result.runtime_error


@pytest.mark.parametrize("sanitizer", ["asan", "ubsan", "tsan"])
def test_invalid_unicode_is_typed_unsupported(sanitizer):
    with pytest.raises(adapter.UnsupportedSanitizerFormat):
        adapter.diagnostics("\ud800", sanitizer)


@pytest.mark.parametrize(
    "sanitizer,log,kind",
    [
        ("asan", ASAN, "heap-buffer-overflow"),
        ("ubsan", UBSAN, "signed-integer-overflow"),
        ("tsan", TSAN, "data-race"),
    ],
)
def test_repeated_complete_occurrences_and_clean_output(sanitizer, log, kind):
    result = adapter.diagnostics(log + log, sanitizer)
    assert [row.kind for row in result.records] == [kind, kind]
    assert result.runtime_error is None
    clean = adapter.diagnostics("selected test output without diagnostics\n", sanitizer)
    assert not clean.records and clean.runtime_error is None


@pytest.mark.parametrize(
    "log",
    [
        "SUMMARY: AddressSanitizer: heap-buffer-overflow fixture\n"
        + ASAN.split("SUMMARY:")[0],
        ASAN.replace(
            "SUMMARY: AddressSanitizer: heap-buffer-overflow",
            "SUMMARY: AddressSanitizer: heap-buffer-overflow-other",
        ),
        ASAN.split("SUMMARY:")[0]
        + ASAN.split("SUMMARY:")[0]
        + ASAN[ASAN.index("SUMMARY:") :],
        ASAN + "SUMMARY: AddressSanitizer: heap-buffer-overflow fixture\n",
    ],
)
def test_asan_report_pairing_rejects_orphans_mismatches_and_incomplete(log):
    assert adapter.diagnostics(log, "asan").runtime_error


def test_tsan_warning_count_is_not_a_replacement_for_reports():
    assert (
        adapter.diagnostics(
            TSAN + "ThreadSanitizer: reported 1 warnings\n", "tsan"
        ).runtime_error
        is None
    )
    assert adapter.diagnostics(
        TSAN + "ThreadSanitizer: reported 2 warnings\n", "tsan"
    ).runtime_error
    result = adapter.diagnostics("ThreadSanitizer: reported 1 warnings\n", "tsan")
    assert not result.records and result.runtime_error


def test_known_report_survives_fatal_runtime_metadata_without_becoming_qualified():
    result = adapter.diagnostics(
        TSAN + "FATAL: ThreadSanitizer: unexpected memory mapping 0x1-0x2\n", "tsan"
    )
    assert len(result.records) == 1
    assert (
        result.runtime_error
        == "ThreadSanitizer runtime startup failed: unexpected memory mapping"
    )


def test_ubsan_malformed_and_huge_locations_fail_typed_or_remain_unavailable():
    for location in ["main.cpp:0:1", "main.cpp:1:x", "main.cpp:" + ("1" * 4400) + ":1"]:
        try:
            result = adapter.diagnostics(
                location + ": runtime error: signed integer overflow: value\n", "ubsan"
            )
        except adapter.UnsupportedSanitizerFormat:
            continue
        assert not result.records and result.runtime_error


@pytest.mark.parametrize("sanitizer", ["asan", "ubsan", "tsan"])
def test_nul_evidence_refused(sanitizer):
    with pytest.raises(adapter.UnsupportedSanitizerFormat):
        adapter.diagnostics("fixture\x00", sanitizer)
