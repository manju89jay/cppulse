"""Bounded GNU ELF callsite and GCC sanitizer output parsers, adapter 1.0.0.

This first dialect is Linux x86-64 ELF64, GNU binutils 2.44 and GCC 14.2.
Parsers observe retained text only: material/execution ownership is checked by
cppulse.sanitizers. A runtime dependency and init symbol alone prove no checks.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

MAX_BYTES = 10 * 1024 * 1024
SONAMES = {"asan": "libasan.so.8", "ubsan": "libubsan.so.1", "tsan": "libtsan.so.2"}
_MARKERS = {
    "asan": r"__asan_report_(?:load|store)(?:[0-9]+|_n)(?:_noabort)?",
    "ubsan": r"__ubsan_handle_[A-Za-z0-9_]+",
    "tsan": r"__tsan_(?:read|write)[0-9]+",
}


class UnsupportedSanitizerFormat(ValueError):
    """Retained evidence is outside the bounded supported proof dialect."""


@dataclass(frozen=True)
class ObjectInstrumentation:
    """Intersected undefined symbols and executable-section check relocations."""

    symbols: tuple[str, ...]
    elf: dict[str, str]


@dataclass(frozen=True)
class RuntimeLinkage:
    """Observed DT_NEEDED entries, not a hash of the actually loaded runtime."""

    needed: tuple[str, ...]
    elf: dict[str, str]


@dataclass(frozen=True)
class Diagnostic:
    """One recognized diagnostic claim from a selected test's captured output."""

    kind: str
    message: str
    file: str | None = None
    line: int | None = None


@dataclass(frozen=True)
class DiagnosticResult:
    """Recognized bug diagnostics and a separate runtime availability failure."""

    records: tuple[Diagnostic, ...]
    runtime_error: str | None


def _bounded(text: str, sanitizer: str) -> str:
    if sanitizer not in SONAMES:
        raise UnsupportedSanitizerFormat(f"Unsupported sanitizer {sanitizer!r}")
    try:
        oversized = len(text) > MAX_BYTES or len(text.encode("utf-8")) > MAX_BYTES
    except UnicodeError as error:
        raise UnsupportedSanitizerFormat("Evidence contains invalid Unicode") from error
    if oversized or "\x00" in text:
        raise UnsupportedSanitizerFormat("Evidence exceeds byte limit or contains NUL")
    return text


def _elf(report: str, types: set[str]) -> dict[str, str]:
    def field(name: str) -> str:
        matches = re.findall(r"^\s*" + name + r":\s*(.*?)\s*$", report, re.M)
        if len(matches) != 1:
            raise UnsupportedSanitizerFormat(f"Ambiguous/missing ELF {name}")
        return matches[0]

    if (
        field("Class") != "ELF64"
        or field("Data") != "2's complement, little endian"
        or field("Machine") != "Advanced Micro Devices X86-64"
    ):
        raise UnsupportedSanitizerFormat("Only little-endian x86-64 ELF64 is supported")
    kind = field("Type").split()[0]
    if kind not in types or ".gnu.lto_" in report:
        raise UnsupportedSanitizerFormat("Unexpected ELF kind or LTO material")
    if not re.search(r"^\s*\[\s*\d+\]\s+\.symtab\s+SYMTAB\s", report, re.M):
        raise UnsupportedSanitizerFormat("Unstripped ELF symbol table is required")
    return {"class": "ELF64", "machine": "x86_64", "type": kind}


def object_instrumentation(
    nm: str, readelf: str, sanitizer: str
) -> ObjectInstrumentation:
    """Require undefined data/check markers with executable text call relocations.

    Init/version callbacks, strings, defined fake handlers and debug/data-only
    relocations cannot satisfy this proof. No whole-program claim is made.
    """
    _bounded(nm, sanitizer)
    _bounded(readelf, sanitizer)
    header = _elf(readelf, {"REL"})
    undefined = set(re.findall(r"^\s*U\s+(\S+)\s*$", nm, re.M))
    # Section headers identify executable .text sections. Debug/data relocation
    # sections never become qualifying even if their symbol text looks familiar.
    executable = set(
        re.findall(
            r"^\s*\[\s*\d+\]\s+(\.text(?:\.[^\s]+)?)\s+PROGBITS\s+"
            r"\S+\s+\S+\s+\S+\s+\S+\s+[A-Z]*X[A-Z]*\s",
            readelf,
            re.M,
        )
    )
    section = ""
    relocated: set[str] = set()
    for line in readelf.splitlines():
        heading = re.fullmatch(r"Relocation section '([^']+)' .*", line)
        if heading:
            section = heading[1]
        elif section.startswith(".rela") and section[5:] in executable:
            row = re.fullmatch(
                r"\s*[0-9a-fA-F]+\s+[0-9a-fA-F]+\s+R_X86_64_PLT32\s+"
                r"[0-9a-fA-F]+\s+(\S+)\s+[-+]\s+\S+\s*",
                line,
            )
            if row:
                relocated.add(row[1])
    symbols = tuple(
        sorted(
            symbol
            for symbol in undefined & relocated
            if re.fullmatch(_MARKERS[sanitizer], symbol)
        )
    )
    if not symbols:
        raise UnsupportedSanitizerFormat(
            "No selected sanitizer data/check callsite was observed"
        )
    return ObjectInstrumentation(symbols, header)


def runtime_linkage(readelf: str, sanitizer: str) -> RuntimeLinkage:
    """Require the selected dynamic sanitizer runtime in a supported final ELF."""
    _bounded(readelf, sanitizer)
    header = _elf(readelf, {"EXEC", "DYN"})
    needed = tuple(
        sorted(set(re.findall(r"\(NEEDED\)\s+Shared library: \[([^\]\n]+)\]", readelf)))
    )
    if SONAMES[sanitizer] not in needed:
        raise UnsupportedSanitizerFormat(
            "Selected sanitizer DT_NEEDED runtime is absent"
        )
    if not re.search(
        r"^Symbol table '\.symtab' contains [1-9][0-9]* entries:", readelf, re.M
    ):
        raise UnsupportedSanitizerFormat("Final ELF full symbol inspection is required")
    symbols = re.findall(
        r"^\s*[0-9]+:\s+[0-9a-fA-F]+\s+[0-9]+\s+\S+\s+\S+\s+\S+\s+(\S+)\s+(\S+)",
        readelf,
        re.M,
    )
    if not symbols:
        raise UnsupportedSanitizerFormat("Final ELF symbol table is unavailable")
    for section, name in symbols:
        name = name.split("@", 1)[0]
        custom_hook = re.fullmatch(
            r"__(?:asan|ubsan|tsan|lsan|sanitizer)_(?:default_options|default_suppressions|on_error|on_report|on_print|report_error_summary)",
            name,
        )
        control_api = name in {
            "__sanitizer_set_report_path",
            "__sanitizer_set_report_fd",
            "__sanitizer_set_death_callback",
            "__asan_set_error_report_callback",
            "__asan_set_death_callback",
        }
        if (section != "UND" and custom_hook) or control_api:
            raise UnsupportedSanitizerFormat(
                "Unsupported custom sanitizer runtime hook/control API: " + name
            )
    return RuntimeLinkage(needed, header)


def diagnostics(output: str, sanitizer: str) -> DiagnosticResult:
    """Recognize a narrow diagnostic dialect, including recovering UBSan errors.

    Bare deadly signals, startup failures and unknown runtime error dialects
    remain unavailable rather than becoming a false clean result or bug claim.
    Exit status is deliberately not an input to this parser.
    """
    _bounded(output, sanitizer)
    records: list[Diagnostic] = []
    runtime_error = None
    if sanitizer == "ubsan":
        for line in output.splitlines():
            match = re.fullmatch(
                r"(.+?):([1-9][0-9]*):[0-9]+: runtime error: (signed integer overflow:[^\n]+)",
                line,
            )
            if match:
                try:
                    number = int(match[2])
                except ValueError as error:
                    raise UnsupportedSanitizerFormat(
                        "Unsupported UBSan source line"
                    ) from error
                records.append(
                    Diagnostic("signed-integer-overflow", line, match[1], number)
                )
            elif "runtime error:" in line or "UndefinedBehaviorSanitizer" in line:
                runtime_error = "Unsupported UBSan diagnostic kind"
        return DiagnosticResult(tuple(records), runtime_error)

    # A summary closes exactly one preceding report. Matching globally would
    # let an earlier summary qualify a later truncated same-kind occurrence.
    pending: Diagnostic | None = None
    unknown = False
    name = "AddressSanitizer" if sanitizer == "asan" else "ThreadSanitizer"
    for line in output.splitlines():
        if sanitizer == "asan":
            header = re.fullmatch(
                r"==[0-9]+==ERROR: AddressSanitizer: ([a-z][a-z0-9-]+)\b[^\n]*", line
            )
        else:
            header = re.fullmatch(
                r"WARNING: ThreadSanitizer: (data race)(?:[ \t].*)?", line
            )
        summary = re.fullmatch(
            r"SUMMARY: " + name + r": ([a-z][a-z0-9-]*(?: race)?)(?:[ \t].*)?", line
        )
        if header:
            if pending is not None:
                unknown = True
            kind = header[1] if sanitizer == "asan" else "data-race"
            message = (
                line if sanitizer == "asan" else "WARNING: ThreadSanitizer: data race"
            )
            pending = Diagnostic(kind, message)
        elif summary:
            kind = summary[1] if sanitizer == "asan" else summary[1].replace(" ", "-")
            if pending is None or pending.kind != kind:
                unknown = True
            else:
                records.append(pending)
            pending = None
        elif sanitizer == "tsan" and (
            trailer := re.fullmatch(
                r"ThreadSanitizer: reported ([0-9]+) warnings", line
            )
        ):
            # A count is metadata, not a diagnostic. It must agree with the
            # occurrences observed so far and cannot repair a missing summary.
            try:
                count = int(trailer[1])
            except ValueError as error:
                raise UnsupportedSanitizerFormat(
                    "Unsupported TSan warning count"
                ) from error
            if pending is not None or count != len(records):
                unknown = True
        elif name in line or (sanitizer == "asan" and "LeakSanitizer" in line):
            unknown = True
    if pending is not None:
        unknown = True
    if unknown:
        if sanitizer == "asan":
            runtime_error = "Unqualified AddressSanitizer diagnostic or runtime failure"
        elif "FATAL: ThreadSanitizer: unexpected memory mapping" in output:
            runtime_error = (
                "ThreadSanitizer runtime startup failed: unexpected memory mapping"
            )
        else:
            runtime_error = "Unsupported ThreadSanitizer diagnostic or runtime failure"
    return DiagnosticResult(tuple(records), runtime_error)
