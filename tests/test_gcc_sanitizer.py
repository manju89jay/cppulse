"""Bounded GCC/ELF parser regressions; synthetic text is explicitly labeled."""

from __future__ import annotations

import pytest

from cppulse.adapters.gcc_sanitizer import (
    UnsupportedSanitizerFormat,
    diagnostics,
    object_instrumentation,
    runtime_linkage,
)


def elf(kind: str = "REL", symbols: str = "__asan_report_load4") -> str:
    """Return a small explicitly synthetic readelf dialect example."""
    return f"""ELF Header:
  Class: ELF64
  Data: 2's complement, little endian
  Type: {kind} (fixture)
  Machine: Advanced Micro Devices X86-64
Section Headers:
  [ 1] .text PROGBITS 0000000000000000 000040 000050 00 AX 0 0 1
  [ 2] .symtab SYMTAB 0000000000000000 000090 000030 18 0 0 8
Relocation section '.rela.text' at offset 0x90 contains 1 entry:
0000000000000010 0000000000000004 R_X86_64_PLT32 0000000000000000 {symbols} - 4
"""


def test_qualified_callsite_is_intersection_of_undefined_and_text_relocation() -> None:
    proof = object_instrumentation(
        " U __asan_init\n U __asan_report_load4\n", elf(), "asan"
    )
    assert proof.symbols == ("__asan_report_load4",)
    assert proof.elf == {"class": "ELF64", "machine": "x86_64", "type": "REL"}


@pytest.mark.parametrize(
    "nm,report,sanitizer",
    [
        (" U __asan_init", elf(symbols="__asan_init"), "asan"),
        (" U __asan_report_load4", elf(), "ubsan"),
        (" T __asan_report_load4", elf(), "asan"),
        (
            " U __asan_report_load4",
            elf().replace(".rela.text", ".rela.debug_info"),
            "asan",
        ),
        (
            " U __asan_report_load4",
            elf().replace("R_X86_64_PLT32", "R_X86_64_64"),
            "asan",
        ),
        (" U __asan_report_load4", elf().replace("ELF64", "ELF32"), "asan"),
        (" U __asan_report_load4", elf().replace(".symtab", ".dynsym"), "asan"),
        (" U __asan_report_load4", elf() + "\n.gnu.lto_fixture\n", "asan"),
    ],
)
def test_init_wrong_sanitizer_debug_data_stripped_or_lto_is_not_proof(
    nm: str, report: str, sanitizer: str
) -> None:
    with pytest.raises(UnsupportedSanitizerFormat):
        object_instrumentation(nm, report, sanitizer)


@pytest.mark.parametrize(
    "sanitizer,symbol",
    [("ubsan", "__ubsan_handle_add_overflow"), ("tsan", "__tsan_write4")],
)
def test_other_selected_sanitizers(sanitizer: str, symbol: str) -> None:
    assert object_instrumentation(
        " U " + symbol, elf(symbols=symbol), sanitizer
    ).symbols


def test_runtime_requires_expected_dynamic_soname() -> None:
    report = (
        elf("DYN")
        + " 0x0000000000000001 (NEEDED) Shared library: [libasan.so.8]\n"
        + "Symbol table '.symtab' contains 1 entries:\n"
        + " 1: 0000000000000000 42 FUNC GLOBAL DEFAULT 14 main\n"
    )
    assert runtime_linkage(report, "asan").needed == ("libasan.so.8",)
    with pytest.raises(UnsupportedSanitizerFormat):
        runtime_linkage(report, "tsan")


def test_recovering_ubsan_diagnostic_does_not_need_failure_exit() -> None:
    result = diagnostics(
        "main.cpp:55:40: runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'\n",
        "ubsan",
    )
    assert result.records[0].kind == "signed-integer-overflow"
    assert result.records[0].file == "main.cpp"
    assert result.records[0].line == 55
    assert result.runtime_error is None


def test_asan_requires_error_and_matching_summary() -> None:
    valid = "==7==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x00\nSUMMARY: AddressSanitizer: heap-buffer-overflow fixture\n"
    assert diagnostics(valid, "asan").records[0].kind == "heap-buffer-overflow"
    assert not diagnostics(valid.split("SUMMARY:")[0], "asan").records
    assert not diagnostics("AddressSanitizer:DEADLYSIGNAL\n", "asan").records
    assert diagnostics("AddressSanitizer:DEADLYSIGNAL\n", "asan").runtime_error


def test_tsan_startup_mapping_failure_is_unsupported_not_data_race() -> None:
    result = diagnostics(
        "FATAL: ThreadSanitizer: unexpected memory mapping 0x1-0x2\n", "tsan"
    )
    assert not result.records
    assert (
        result.runtime_error
        == "ThreadSanitizer runtime startup failed: unexpected memory mapping"
    )
    race = diagnostics(
        "WARNING: ThreadSanitizer: data race (pid=9)\nSUMMARY: ThreadSanitizer: data race fixture\n",
        "tsan",
    )
    assert race.records[0].kind == "data-race"


def test_unknown_or_oversized_dialect_is_rejected() -> None:
    with pytest.raises(UnsupportedSanitizerFormat):
        object_instrumentation(" U __asan_report_load4", elf(), "msan")
    with pytest.raises(UnsupportedSanitizerFormat):
        diagnostics("x" * (10 * 1024 * 1024 + 1), "asan")


def test_unsupported_runtime_diagnostic_does_not_become_clean() -> None:
    assert diagnostics(
        "main.cpp:1:2: runtime error: division by zero\n", "ubsan"
    ).runtime_error
    assert diagnostics(
        "FATAL: ThreadSanitizer: unsupported VMA range\n", "tsan"
    ).runtime_error
    with pytest.raises(UnsupportedSanitizerFormat):
        object_instrumentation(
            " U __asan_report_load4", elf() + "  Class: ELF64\n", "asan"
        )


@pytest.mark.parametrize(
    "symbol,section",
    [
        ("__ubsan_default_options", "14"),
        ("__asan_on_error", "14"),
        ("__ubsan_on_report", "14"),
        ("__tsan_default_suppressions", "14"),
        ("__sanitizer_set_report_path", "UND"),
    ],
)
def test_custom_reporting_hooks_are_outside_first_runtime_configuration(
    symbol: str, section: str
) -> None:
    report = (
        elf("DYN")
        + " 0x0000000000000001 (NEEDED) Shared library: [libasan.so.8]\n"
        + "Symbol table '.symtab' contains 1 entries:\n"
        + f" 1: 0000000000000000 42 FUNC GLOBAL DEFAULT {section} {symbol}\n"
    )
    with pytest.raises(UnsupportedSanitizerFormat, match="custom sanitizer runtime"):
        runtime_linkage(report, "asan")


def test_runtime_full_symbols_are_required_even_when_section_header_exists() -> None:
    report = (
        elf("DYN") + " 0x0000000000000001 (NEEDED) Shared library: [libasan.so.8]\n"
    )
    with pytest.raises(UnsupportedSanitizerFormat, match="full symbol"):
        runtime_linkage(report, "asan")
    with pytest.raises(UnsupportedSanitizerFormat, match="symbol table is unavailable"):
        runtime_linkage(report + "Symbol table '.symtab' contains 1 entries:\n", "asan")
