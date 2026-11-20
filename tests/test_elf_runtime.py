"""Pure ELF fixture inspection; no subject executable is ever run."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
import struct

import pytest

from cppulse.elf_runtime import inspect_elf_runtime
from cppulse.errors import ContractError


BASE = 0x400000


def image(*, rpath: bytes = b":$ORIGIN::", runpath: bytes = b"") -> bytearray:
    """Create a small non-executed ELF64LE with three file-backed segments."""
    value = bytearray(4096)
    ident = b"\x7fELF\x02\x01\x01" + bytes(9)
    struct.pack_into(
        "<16sHHIQQQIHHHHHH",
        value,
        0,
        ident,
        3,
        62,
        1,
        BASE + 512,
        64,
        0,
        0,
        64,
        56,
        3,
        0,
        0,
        0,
    )
    interpreter = b"/lib64/ld-linux-x86-64.so.2\0"
    strings = b"\0libalpha.so\0" + rpath + b"\0" + runpath + b"\0"
    dynamic = [
        (5, BASE + 1280),
        (10, len(strings)),
        (1, 1),
        (15, 13),
        (29, 14 + len(rpath)),
        (0, 0),
    ]
    for index, header in enumerate(
        [
            (1, 5, 0, BASE, BASE, len(value), len(value), 4096),
            (3, 4, 512, BASE + 512, 0, len(interpreter), len(interpreter), 1),
            (2, 4, 768, BASE + 768, 0, len(dynamic) * 16, len(dynamic) * 16, 8),
        ]
    ):
        struct.pack_into("<IIQQQQQQ", value, 64 + index * 56, *header)
    value[512 : 512 + len(interpreter)] = interpreter
    for index, row in enumerate(dynamic):
        struct.pack_into("<qQ", value, 768 + index * 16, *row)
    value[1280 : 1280 + len(strings)] = strings
    return value


def inspect(path: Path, data: bytes | bytearray, **overrides: object):
    """Write only an owned fixture and pin the exact bytes supplied to the reader."""
    path.write_bytes(data)
    pins = {
        "expected_sha256": hashlib.sha256(data).hexdigest(),
        "expected_size": len(data),
    }
    pins.update(overrides)
    return inspect_elf_runtime(path, **pins)


@pytest.mark.parametrize(
    "address,offset,filesz,memsz",
    [
        (BASE + 1281, 2000, 10, 10),
        (BASE + 1280, 2000, 1, 1),
        (BASE + 1285, 2000, 20, 20),
        (BASE + 1281, 1281, 0, 10),
        (BASE + 1280, 1280, 1, 10),
    ],
)
def test_partial_load_overlay_cannot_change_selected_strings(
    tmp_path: Path, address: int, offset: int, filesz: int, memsz: int
) -> None:
    data = image()
    struct.pack_into("<IIQQQQQQ", data, 120, 1, 4, offset, address, 0, filesz, memsz, 1)
    with pytest.raises(ContractError):
        inspect(tmp_path / "subject", data)


def test_consistent_partial_file_mapping_preserves_literal_strings(
    tmp_path: Path,
) -> None:
    data = image()
    struct.pack_into("<IIQQQQQQ", data, 120, 1, 4, 1281, BASE + 1281, 0, 10, 10, 1)
    assert inspect(tmp_path / "subject", data).needed == ("libalpha.so",)


def test_literal_search_paths_and_order_are_frozen_metadata(tmp_path: Path) -> None:
    data = image()
    result = inspect(tmp_path / "subject", data)
    assert result.sha256 == hashlib.sha256(data).hexdigest()
    assert result.size_bytes == len(data)
    assert (result.elf_class, result.machine, result.elf_type) == (64, 62, 3)
    assert result.interpreter == "/lib64/ld-linux-x86-64.so.2"
    assert result.needed == ("libalpha.so",)
    assert result.rpath == ":$ORIGIN::"
    assert result.runpath == ""
    with pytest.raises(FrozenInstanceError):
        result.machine = 0


@pytest.mark.parametrize(
    "offset,format,value",
    [
        (4, "B", 1),
        (5, "B", 2),
        (6, "B", 0),
        (16, "H", 1),
        (18, "H", 183),
        (20, "I", 0),
        (52, "H", 63),
        (54, "H", 55),
        (56, "H", 1025),
        (32, "Q", 4090),
    ],
)
def test_unsupported_or_out_of_bounds_headers_reject(
    tmp_path: Path, offset: int, format: str, value: int
) -> None:
    data = image()
    struct.pack_into("<" + format, data, offset, value)
    with pytest.raises(ContractError):
        inspect(tmp_path / "subject", data)


@pytest.mark.parametrize(
    "mutation",
    [
        "segment_bounds",
        "load_memory",
        "strtab_va",
        "strtab_size",
        "dynamic_null",
        "interp_null",
        "string_null",
    ],
)
def test_malformed_segments_and_dynamic_tables_reject(
    tmp_path: Path, mutation: str
) -> None:
    data = image()
    if mutation == "segment_bounds":
        struct.pack_into("<Q", data, 64 + 32, 4097)
    elif mutation == "load_memory":
        struct.pack_into("<Q", data, 64 + 40, 1)
    elif mutation == "strtab_va":
        struct.pack_into("<Q", data, 768 + 8, BASE + len(data))
    elif mutation == "strtab_size":
        struct.pack_into("<Q", data, 768 + 16 + 8, 4096)
    elif mutation == "dynamic_null":
        struct.pack_into("<qQ", data, 768 + 5 * 16, 1, 1)
    elif mutation == "interp_null":
        data[512 + len(b"/lib64/ld-linux-x86-64.so.2")] = 1
    else:
        struct.pack_into("<Q", data, 768 + 16 + 8, 12)
    with pytest.raises(ContractError):
        inspect(tmp_path / "subject", data)


@pytest.mark.parametrize("kind", [2, 3])
def test_static_exec_and_dyn_without_runtime_tables(tmp_path: Path, kind: int) -> None:
    data = image()
    struct.pack_into("<H", data, 16, kind)
    struct.pack_into("<H", data, 56, 1)
    result = inspect(tmp_path / "subject", data)
    assert result.elf_type == kind
    assert (result.interpreter, result.needed, result.rpath, result.runpath) == (
        None,
        (),
        None,
        None,
    )


def test_needed_order_and_duplicates_are_literal_not_resolved(tmp_path: Path) -> None:
    data = image()
    struct.pack_into("<Q", data, 64 + 2 * 56 + 32, 112)
    struct.pack_into("<Q", data, 64 + 2 * 56 + 40, 112)
    struct.pack_into("<qQ", data, 768 + 5 * 16, 1, 1)
    struct.pack_into("<qQ", data, 768 + 6 * 16, 0, 0)
    result = inspect(tmp_path / "subject", data)
    assert result.needed == ("libalpha.so", "libalpha.so")


@pytest.mark.parametrize(
    "mutation",
    [
        "bss",
        "duplicate_tag",
        "ambiguous_load",
        "dynamic_va",
        "needed_index",
        "empty_needed",
        "alignment",
        "virtual_overflow",
        "empty_interpreter",
        "invalid_utf8",
    ],
)
def test_additional_runtime_metadata_malformations(
    tmp_path: Path, mutation: str
) -> None:
    data = image()
    if mutation == "bss":
        struct.pack_into("<Q", data, 64 + 40, 8192)
        struct.pack_into("<Q", data, 768 + 8, BASE + 4096)
    elif mutation == "duplicate_tag":
        struct.pack_into("<qQ", data, 768 + 3 * 16, 5, BASE + 1280)
    elif mutation == "ambiguous_load":
        struct.pack_into("<IIQQQQQQ", data, 64 + 56, 1, 4, 1, BASE, 0, 4095, 4095, 1)
    elif mutation == "dynamic_va":
        struct.pack_into("<Q", data, 64 + 2 * 56 + 16, BASE + 800)
    elif mutation == "needed_index":
        struct.pack_into("<Q", data, 768 + 2 * 16 + 8, 4096)
    elif mutation == "empty_needed":
        struct.pack_into("<Q", data, 768 + 2 * 16 + 8, 0)
    elif mutation == "alignment":
        struct.pack_into("<Q", data, 64 + 48, 3)
    elif mutation == "virtual_overflow":
        struct.pack_into("<Q", data, 64 + 16, 2**64 - 1)
    elif mutation == "empty_interpreter":
        struct.pack_into("<Q", data, 64 + 56 + 32, 1)
    else:
        data[1281] = 255
    with pytest.raises(ContractError):
        inspect(tmp_path / "subject", data)


@pytest.mark.parametrize("mutation", ["dynamic_entries", "long_string"])
def test_finite_dynamic_and_string_budgets(tmp_path: Path, mutation: str) -> None:
    data = image()
    data.extend(bytes(70000 - len(data)))
    struct.pack_into("<Q", data, 64 + 32, len(data))
    struct.pack_into("<Q", data, 64 + 40, len(data))
    if mutation == "dynamic_entries":
        struct.pack_into("<Q", data, 64 + 2 * 56 + 32, 4097 * 16)
    else:
        struct.pack_into("<Q", data, 768 + 16 + 8, 5000)
        data[1281 : 1281 + 4096] = b"x" * 4096
    with pytest.raises(ContractError):
        inspect(tmp_path / "subject", data)


@pytest.mark.parametrize(
    "overrides",
    [
        {"expected_sha256": "0" * 64},
        {"expected_sha256": "0" * 64 + "\n"},
        {"expected_size": 4095},
        {"expected_size": True},
        {"expected_size": 4096.0},
        {"max_bytes": 4095},
        {"max_bytes": True},
    ],
)
def test_exact_pin_and_budget_validation(tmp_path: Path, overrides: dict) -> None:
    with pytest.raises(ContractError):
        inspect(tmp_path / "subject", image(), **overrides)


@pytest.mark.parametrize(
    "kind", ["file_symlink", "parent_symlink", "directory", "fifo"]
)
def test_nofollow_regular_file_boundary(tmp_path: Path, kind: str) -> None:
    import os

    data = image()
    selected = tmp_path / "subject"
    if kind == "file_symlink":
        (tmp_path / "actual").write_bytes(data)
        selected.symlink_to("actual")
    elif kind == "parent_symlink":
        (tmp_path / "actual").mkdir()
        (tmp_path / "actual" / "subject").write_bytes(data)
        (tmp_path / "linked").symlink_to("actual", target_is_directory=True)
        selected = tmp_path / "linked" / "subject"
    elif kind == "directory":
        selected.mkdir()
    else:
        os.mkfifo(selected)
    with pytest.raises(ContractError):
        inspect_elf_runtime(
            selected,
            expected_sha256=hashlib.sha256(data).hexdigest(),
            expected_size=len(data),
        )


@pytest.mark.parametrize("mutation", ["bytes", "mode", "pathname", "parent"])
def test_same_descriptor_and_path_identity_are_rechecked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    import cppulse.elf_runtime as module

    parent = tmp_path / "selected"
    parent.mkdir()
    selected = parent / "subject"
    data = image()
    selected.write_bytes(data)
    original = module.os.pread
    changed = False

    def racing_read(fd: int, count: int, offset: int) -> bytes:
        nonlocal changed
        result = original(fd, count, offset)
        if count == 64 and offset == 0 and not changed:
            changed = True
            if mutation == "bytes":
                with selected.open("r+b") as stream:
                    stream.seek(4000)
                    stream.write(b"X")
            elif mutation == "mode":
                selected.chmod(0o700)
            elif mutation == "pathname":
                selected.rename(parent / "retired")
                selected.write_bytes(data)
            else:
                parent.rename(tmp_path / "retired-parent")
                parent.mkdir()
                selected.write_bytes(data)
        return result

    monkeypatch.setattr(module.os, "pread", racing_read)
    with pytest.raises(ContractError, match="changed"):
        inspect_elf_runtime(
            selected,
            expected_sha256=hashlib.sha256(data).hexdigest(),
            expected_size=len(data),
        )


def test_selected_actual_native_metadata_without_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os
    import subprocess

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "Pure ELF inspection must never execute a subject or helper"
        )

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "execve", forbidden)
    import cppulse.elf_runtime as module

    original_read = module.os.pread
    reads = []

    def measured_read(fd: int, count: int, offset: int) -> bytes:
        reads.append(count)
        return original_read(fd, count, offset)

    monkeypatch.setattr(module.os, "pread", measured_read)
    selected = Path(
        "work/cloud-resume/native-tu-buffer-final/cppulse-native-0.2.0.dev2-linux-x86_64/libexec/cppulse/cppulse-analyzer"
    )
    result = inspect_elf_runtime(
        selected,
        expected_sha256="5f7a130b5871c5a25307304d50542babeaf84e52cbdfeddbba97e149ff1c7b9d",
        expected_size=1365408,
    )
    assert result.machine == 62
    assert result.interpreter == "/lib64/ld-linux-x86-64.so.2"
    assert "libstdc++.so.6" in result.needed
    assert "libc.so.6" in result.needed
    assert max(reads) <= 1024 * 1024
    assert sum(reads) >= 2 * result.size_bytes


def test_replacement_between_stat_and_open_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.elf_runtime as module

    data = image()
    selected = tmp_path / "subject"
    selected.write_bytes(data)
    original = module.os.open
    replaced = False

    def racing_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        nonlocal replaced
        if path == "subject" and not replaced:
            replaced = True
            selected.rename(tmp_path / "retired")
            selected.write_bytes(data)
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(module.os, "open", racing_open)
    with pytest.raises(ContractError, match="changed during selection"):
        inspect_elf_runtime(
            selected,
            expected_sha256=hashlib.sha256(data).hexdigest(),
            expected_size=len(data),
        )


def test_short_metadata_read_is_not_interpreted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.elf_runtime as module

    original = module.os.pread

    def short_read(fd: int, count: int, offset: int) -> bytes:
        result = original(fd, count, offset)
        return result[:-1] if count == 64 else result

    monkeypatch.setattr(module.os, "pread", short_read)
    with pytest.raises(ContractError, match="truncated"):
        inspect(tmp_path / "subject", image())


@pytest.mark.parametrize("selected", ["missing", "../escape", "nul\0path"])
def test_missing_or_noncanonical_path_is_a_contract_error(
    tmp_path: Path, selected: str
) -> None:
    with pytest.raises(ContractError):
        inspect_elf_runtime(
            tmp_path / selected, expected_sha256="0" * 64, expected_size=4096
        )


@pytest.mark.parametrize(
    "mutation", ["no_load", "duplicate_dynamic", "duplicate_interpreter"]
)
def test_ambiguous_or_missing_program_roles_reject(
    tmp_path: Path, mutation: str
) -> None:
    data = image()
    offset, tag = {
        "no_load": (64, 0),
        "duplicate_dynamic": (120, 2),
        "duplicate_interpreter": (176, 3),
    }[mutation]
    struct.pack_into("<I", data, offset, tag)
    with pytest.raises(ContractError):
        inspect(tmp_path / "subject", data)


def test_empty_dynamic_table_is_not_fabricated_as_missing_libraries(
    tmp_path: Path,
) -> None:
    data = image()
    struct.pack_into("<qQ", data, 768, 0, 0)
    result = inspect(tmp_path / "subject", data)
    assert result.needed == ()
    assert result.rpath is result.runpath is None


def test_missing_dynamic_string_table_rejects(tmp_path: Path) -> None:
    data = image()
    struct.pack_into("<qQ", data, 768, 4, 0)
    with pytest.raises(ContractError, match="string table"):
        inspect(tmp_path / "subject", data)


def test_invalid_path_type_is_a_contract_error() -> None:
    with pytest.raises(ContractError, match="pathname"):
        inspect_elf_runtime(None, expected_sha256="0" * 64, expected_size=4096)


def test_short_streaming_hash_is_not_metadata_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.elf_runtime as module

    original = module.os.pread
    monkeypatch.setattr(
        module.os, "pread", lambda fd, count, offset: original(fd, count, offset)[:-1]
    )
    with pytest.raises(ContractError, match="streaming hash"):
        inspect(tmp_path / "subject", image())
