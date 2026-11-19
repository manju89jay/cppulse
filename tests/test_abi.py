"""Private ABI adapter: real ELF/DWARF and bounded failure evidence."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from cppulse.abi import compare, validate_report, validate_request
from cppulse.errors import ContractError

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "work/abi-tooling/prefix/usr/bin/abidiff"
LIBS = ROOT / "work/abi-tooling/prefix/usr/lib/x86_64-linux-gnu"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def binaries(tmp_path: Path) -> dict[str, Path]:
    if not TOOL.is_file():
        pytest.fail(
            "Required real libabigail tool missing; no synthetic success fallback"
        )
    variants = {
        "old": 'struct S { int x; }; extern "C" int read(S* s) { return s->x; }',
        "removed": 'extern "C" int unrelated() { return 1; }',
        "break": 'struct S { long long pad; int x; }; extern "C" int read(S* s) { return s->x; }',
        "addition": 'struct S { int x; }; extern "C" int read(S* s) { return s->x; } extern "C" int extra() { return 1; }',
    }
    result = {}
    for name, source in variants.items():
        cpp = tmp_path / f"{name}.cpp"
        cpp.write_text(source)
        so = tmp_path / f"{name}.so"
        subprocess.run(
            ["g++", "-shared", "-fPIC", "-g", "-Og", str(cpp), "-o", str(so)],
            check=True,
        )
        result[name] = so
    stripped = tmp_path / "stripped.so"
    subprocess.run(
        ["strip", "--strip-debug", "-o", str(stripped), str(result["old"])], check=True
    )
    result["stripped"] = stripped
    malformed = tmp_path / "malformed.so"
    malformed.write_bytes(b"\x7fELFbroken")
    result["malformed"] = malformed
    return result


def request(old: Path, new: Path) -> dict:
    return {
        "version": "1.0.0",
        "tool": {
            "path": str(TOOL),
            "sha256": sha(TOOL),
            "version": "2.6.0",
            "library_directory": str(LIBS),
        },
        "reader": {
            "path": "/usr/bin/readelf",
            "sha256": sha(Path("/usr/bin/readelf")),
            "version": "2.44",
        },
        "limits": {
            "input_bytes": 4 * 1024 * 1024,
            "wall_seconds": 10,
            "log_bytes": 65536,
        },
        "pairs": [
            {
                "id": "api",
                "old": {"path": str(old), "sha256": sha(old)},
                "new": {"path": str(new), "sha256": sha(new)},
            }
        ],
    }


@pytest.mark.parametrize(
    ("new", "status", "code"),
    [
        ("old", "no_changes_reported", 0),
        ("break", "changes_reported", 4),
        ("removed", "incompatible_changes_reported", 12),
        ("addition", "changes_reported", 4),
    ],
)
def test_real_dwarf_comparisons(binaries, tmp_path, new, status, code):
    report = compare(request(binaries["old"], binaries[new]), tmp_path / "result")
    validate_report(report)
    result = report["results"][0]
    assert result["status"] == status
    assert result["returncode"] == code
    assert report["source_binding"] == "unverified"
    assert report["status"] == "reported"
    assert json.loads((tmp_path / "result/report.json").read_text()) == report


@pytest.mark.parametrize("new", ["stripped", "malformed"])
def test_real_unsupported_never_clean(binaries, tmp_path, new):
    report = compare(request(binaries["old"], binaries[new]), tmp_path / "result")
    assert report["status"] == "incomplete"
    assert report["results"][0]["status"] in ("unsupported", "unusable")


def test_stale_inputs_refuse_positive_output(binaries, tmp_path):
    document = request(binaries["old"], binaries["old"])
    binaries["old"].write_bytes(b"changed")
    with pytest.raises(ContractError, match="hash"):
        compare(document, tmp_path / "result")
    assert not (tmp_path / "result/report.json").exists()


def test_existing_output_never_overwritten(binaries, tmp_path):
    output = tmp_path / "result"
    output.mkdir()
    (output / "report.json").write_text("preserve")
    with pytest.raises(ContractError):
        compare(request(binaries["old"], binaries["old"]), output)
    assert (output / "report.json").read_text() == "preserve"


def test_duplicate_ids_rejected(binaries):
    document = request(binaries["old"], binaries["old"])
    document["pairs"] *= 2
    with pytest.raises(ContractError, match="Duplicate"):
        validate_request(document)


def test_input_bound(binaries, tmp_path):
    document = request(binaries["old"], binaries["old"])
    document["limits"]["input_bytes"] = 10
    with pytest.raises(ContractError, match="bound"):
        compare(document, tmp_path / "result")


def test_real_timeout_is_incomplete(binaries, tmp_path):
    document = request(binaries["old"], binaries["break"])
    document["limits"]["wall_seconds"] = 0.000001
    report = compare(document, tmp_path / "result")
    assert report["status"] == "incomplete"
    assert report["results"][0]["timed_out"]


def test_log_truncation_never_classified_as_complete(binaries, tmp_path):
    document = request(binaries["old"], binaries["break"])
    document["limits"]["log_bytes"] = 8
    report = compare(document, tmp_path / "result")
    assert report["status"] == "incomplete"
    assert report["results"][0]["log_truncated"]
    assert len(report["results"][0]["log"].encode()) <= 8


def test_report_status_tampering_rejected(binaries, tmp_path):
    report = compare(
        request(binaries["old"], binaries["stripped"]), tmp_path / "result"
    )
    report["status"] = "reported"
    with pytest.raises(ContractError):
        validate_report(report)


def test_fifo_input_rejected_without_waiting(binaries, tmp_path):

    fifo = tmp_path / "pipe"
    os.mkfifo(fifo)
    document = request(binaries["old"], binaries["old"])
    document["pairs"][0]["new"]["path"] = str(fifo)
    with pytest.raises(ContractError, match="regular"):
        compare(document, tmp_path / "result")


def test_wrong_tool_pin_rejected(binaries, tmp_path):
    document = request(binaries["old"], binaries["old"])
    document["tool"]["sha256"] = "0" * 64
    with pytest.raises(ContractError, match="hash"):
        compare(document, tmp_path / "result")


def test_expected_request_anchors_input_receipt(binaries, tmp_path):
    document = request(binaries["old"], binaries["old"])
    report = compare(document, tmp_path / "result")
    validate_report(report, expected_request=document)
    report["results"][0]["new"]["sha256"] = "0" * 64
    with pytest.raises(ContractError, match="expected request"):
        validate_report(report, expected_request=document)


def test_finite_wall_limit(binaries):
    document = request(binaries["old"], binaries["old"])
    document["limits"]["wall_seconds"] = float("nan")
    with pytest.raises(ContractError):
        validate_request(document)


def test_unqualified_elf_is_not_clean(binaries, tmp_path):
    import struct

    old = binaries["old"]
    data = bytearray(old.read_bytes())
    # ET_EXEC is outside the documented shared-object qualification.
    struct.pack_into("<H", data, 16, 2)
    executable = tmp_path / "executable"
    executable.write_bytes(data)
    report = compare(request(old, executable), tmp_path / "result")
    assert report["results"][0]["status"] == "unsupported"
    assert report["results"][0]["returncode"] is None


def test_source_changes_during_analysis_refuse_publication(
    binaries, tmp_path, monkeypatch
):
    import cppulse.abi as adapter

    original_capture = adapter._capture
    document = request(binaries["old"], binaries["break"])

    def mutate_after_capture(command, env, cwd, wall, log_limit):
        outcome = original_capture(command, env, cwd, wall, log_limit)
        if "--version" not in command:
            binaries["old"].write_bytes(b"changed while tool ran")
        return outcome

    monkeypatch.setattr(adapter, "_capture", mutate_after_capture)
    with pytest.raises(ContractError, match="hash"):
        compare(document, tmp_path / "result")
    assert not (tmp_path / "result/report.json").exists()


def test_descendant_holding_stdout_is_killed_at_wall_deadline(tmp_path):
    import sys
    import time
    from cppulse.abi import _capture

    started = time.monotonic()
    outcome = _capture(
        [
            sys.executable,
            "-c",
            'import subprocess,sys; subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"])',
        ],
        {"PATH": "/usr/bin:/bin"},
        tmp_path,
        0.2,
        1024,
    )
    assert outcome["timed_out"]
    assert time.monotonic() - started < 5


def test_schema_documents_are_valid_draft7():
    import jsonschema

    for path in (ROOT / "python/cppulse/contracts/schemas/abi_private").glob("*.json"):
        jsonschema.Draft7Validator.check_schema(json.loads(path.read_text()))


def test_zeroed_dwarf_is_unsupported_even_when_compared_to_itself(binaries, tmp_path):
    import struct

    data = bytearray(binaries["old"].read_bytes())
    header = struct.unpack_from("<HHIQQQIHHHHHH", data, 16)
    sections = [
        struct.unpack_from("<IIQQQQIIQQ", data, header[5] + index * header[10])
        for index in range(header[11])
    ]
    names_section = sections[header[12]]
    names = data[names_section[4] : names_section[4] + names_section[5]]
    for section in sections:
        end = names.find(b"\0", section[0])
        if names[section[0] : end] in (b".debug_info", b".debug_abbrev"):
            data[section[4] : section[4] + section[5]] = bytes(section[5])
    corrupt = tmp_path / "zeroed.so"
    corrupt.write_bytes(data)
    report = compare(request(corrupt, corrupt), tmp_path / "result")
    assert report["status"] == "incomplete"
    assert report["results"][0]["status"] in ("unsupported", "unusable")
    assert report["results"][0]["returncode"] is None
    assert report["results"][0]["preflight"][0]["status"] == "unsupported"


def test_control_character_paths_rejected(binaries):
    document = request(binaries["old"], binaries["old"])
    document["pairs"][0]["old"]["path"] = "/tmp/invalid\0path"
    with pytest.raises(ContractError, match="control"):
        validate_request(document)


def test_interrupt_kills_and_reaps_owned_process(tmp_path, monkeypatch):
    import cppulse.abi as adapter

    actual_popen = adapter.subprocess.Popen
    actual_selector = adapter.selectors.DefaultSelector
    children = []

    def record_child(*args, **kwargs):
        child = actual_popen(*args, **kwargs)
        children.append(child)
        return child

    class InterruptSelector:
        def __init__(self):
            self.inner = actual_selector()

        def register(self, *args):
            return self.inner.register(*args)

        def get_map(self):
            return self.inner.get_map()

        def select(self, *args):
            raise KeyboardInterrupt

        def close(self):
            self.inner.close()

    monkeypatch.setattr(adapter.subprocess, "Popen", record_child)
    monkeypatch.setattr(adapter.selectors, "DefaultSelector", InterruptSelector)
    with pytest.raises(KeyboardInterrupt):
        adapter._capture(
            ["/usr/bin/sleep", "30"], {"PATH": "/usr/bin:/bin"}, tmp_path, 10, 1024
        )
    assert len(children) == 1
    assert children[0].poll() is not None
    with pytest.raises(ProcessLookupError):
        os.kill(children[0].pid, 0)


def test_caller_mutation_cannot_change_selected_inputs(binaries, tmp_path, monkeypatch):
    import cppulse.abi as adapter

    original_capture = adapter._capture
    document = request(binaries["old"], binaries["old"])
    expected = json.loads(json.dumps(document))

    def mutate_caller(*args):
        document["pairs"][0]["new"]["sha256"] = "0" * 64
        return original_capture(*args)

    monkeypatch.setattr(adapter, "_capture", mutate_caller)
    report = compare(document, tmp_path / "result")
    validate_report(report, expected_request=expected)
    assert report["results"][0]["status"] == "no_changes_reported"


def test_non_utf8_request_is_a_concise_invalid_request(tmp_path, capsys):
    from cppulse.abi import main

    malformed = tmp_path / "bad.json"
    malformed.write_bytes(b"\xff\xfe")
    assert (
        main(["--request", str(malformed), "--output", str(tmp_path / "result")]) == 2
    )
    assert "ABI comparison failed:" in capsys.readouterr().err
    assert not (tmp_path / "result").exists()


@pytest.mark.parametrize(
    "diagnostic",
    [
        "Warning: corrupted unit DW_TAG_compile_unit",
        "Error: invalid abbreviation DW_TAG_compile_unit",
        "no compilation unit here",
    ],
)
def test_claimed_validated_dwarf_must_match_retained_log(
    binaries, tmp_path, diagnostic
):
    report = compare(request(binaries["old"], binaries["old"]), tmp_path / "result")
    stage = report["results"][0]["preflight"][0]
    stage["log"] = diagnostic
    stage["log_sha256"] = hashlib.sha256(diagnostic.encode()).hexdigest()
    with pytest.raises(ContractError, match="preflight"):
        validate_report(report)


def test_null_root_dwarf_is_not_validated_from_unused_abbreviation(binaries, tmp_path):
    import struct

    data = bytearray(binaries["old"].read_bytes())
    header = struct.unpack_from("<HHIQQQIHHHHHH", data, 16)
    sections = [
        struct.unpack_from("<IIQQQQIIQQ", data, header[5] + index * header[10])
        for index in range(header[11])
    ]
    names_section = sections[header[12]]
    names = data[names_section[4] : names_section[4] + names_section[5]]
    for section in sections:
        if names[section[0] : names.find(b"\0", section[0])] == b".debug_info":
            assert struct.unpack_from("<H", data, section[4] + 4)[0] == 5
            data[section[4] + 12 : section[4] + section[5]] = bytes(section[5] - 12)
    corrupt = tmp_path / "null-root.so"
    corrupt.write_bytes(data)
    report = compare(request(corrupt, corrupt), tmp_path / "result")
    assert report["status"] == "incomplete"
    assert report["results"][0]["status"] == "unsupported"
    assert report["results"][0]["returncode"] is None


def test_each_dwarf_unit_requires_its_actual_root_die():
    from cppulse.abi import _dwarf_valid

    valid = "  Compilation Unit @ offset 0:\n <0><c>: Abbrev Number: 1 (DW_TAG_compile_unit)\n"
    invalid = "  Compilation Unit @ offset 0x80:\n"
    outcome = {
        "returncode": 0,
        "timed_out": False,
        "log_truncated": False,
        "log": valid,
    }
    assert _dwarf_valid(outcome)
    outcome["log"] += (
        invalid
        + "\nContents of the .debug_abbrev section:\n 1 DW_TAG_compile_unit [has children]\n"
    )
    assert not _dwarf_valid(outcome)


def test_real_mixed_valid_and_null_root_units_remain_unsupported(binaries, tmp_path):
    import struct

    second = tmp_path / "second.cpp"
    second.write_text('extern "C" int other() { return 41; }')
    mixed = tmp_path / "mixed.so"
    subprocess.run(
        [
            "g++",
            "-shared",
            "-fPIC",
            "-g",
            "-Og",
            str(tmp_path / "old.cpp"),
            str(second),
            "-o",
            str(mixed),
        ],
        check=True,
    )
    data = bytearray(mixed.read_bytes())
    header = struct.unpack_from("<HHIQQQIHHHHHH", data, 16)
    sections = [
        struct.unpack_from("<IIQQQQIIQQ", data, header[5] + index * header[10])
        for index in range(header[11])
    ]
    names_section = sections[header[12]]
    names = data[names_section[4] : names_section[4] + names_section[5]]
    for section in sections:
        if names[section[0] : names.find(b"\0", section[0])] == b".debug_info":
            first_length = struct.unpack_from("<I", data, section[4])[0]
            second_offset = section[4] + 4 + first_length
            assert struct.unpack_from("<H", data, second_offset + 4)[0] == 5
            data[second_offset + 12 : section[4] + section[5]] = bytes(
                section[4] + section[5] - second_offset - 12
            )
    mixed.write_bytes(data)
    report = compare(request(mixed, mixed), tmp_path / "result")
    assert report["status"] == "incomplete"
    assert report["results"][0]["status"] == "unsupported"
    assert report["results"][0]["returncode"] is None
