"""Actual retained runtime bytes; this does not execute an ELF or container."""
from copy import deepcopy
import hashlib
import os
import shutil
import stat
import tarfile
import pytest
from cppulse.frozen_layer import retain_frozen_layer, verify_archive
from cppulse.errors import ContractError, InputChanged
from cppulse.contracts.runtime_input import validate_runtime_layer
from cppulse.runtime_layer import retain_runtime_layer
from test_runtime_input_contract import document, directories
from test_frozen_input_inventory import selected


def inputs_fixture(tmp_path):
    value = document()
    sources = tmp_path / "runtime-sources"
    sources.mkdir()
    for row in value["files"]:
        path = sources / row["role"]
        data = ("selected-" + row["role"]).encode()
        path.write_bytes(data)
        path.chmod(0o500 if row["role"] != "shared_library" else 0o600)
        row["source_path"] = str(path)
        row["mode"] = stat.S_IMODE(path.stat().st_mode)
        row["mtime_ns"] = path.stat().st_mtime_ns
        row["content"] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        }
    source, request = selected(tmp_path)
    archive = tmp_path / "input.gz"
    capture = retain_frozen_layer(request, archive)
    return value, source, {"capture": capture, "request": request, "path": str(archive)}


def test_composed_archive_uses_retained_project_after_source_deletion(tmp_path):
    value, source, capture = inputs_fixture(tmp_path)
    shutil.rmtree(source)
    path = tmp_path / "runtime.gz"
    result = retain_runtime_layer(value, [capture], directories(), path)
    verify_archive(result["archive"], path)
    assert result["cache_eligible"] is False and not result["native_executed"]
    with tarfile.open(path, "r:gz") as archive:
        assert archive.extractfile("input/a.cpp").read() == b"int a;\n"
        assert archive.extractfile("runtime/native").read() == b"selected-native"
    assert result["runtime_manifest_sha256"] and result["input_capture_sha256"]


def test_changed_runtime_source_preserves_partial_without_final(tmp_path, monkeypatch):
    value, _, capture = inputs_fixture(tmp_path)
    path = tmp_path / "runtime.gz"
    target = value["files"][0]["source_path"]
    original = os.read
    changed = False

    def read(fd, count):
        nonlocal changed
        data = original(fd, count)
        if data and not changed and os.readlink("/proc/self/fd/" + str(fd)) == target:
            changed = True
            with open(target, "wb") as stream:
                stream.write(b"X" * len(data))
        return data

    monkeypatch.setattr(os, "read", read)
    with pytest.raises(InputChanged):
        retain_runtime_layer(value, [capture], directories(), path)
    assert (
        changed
        and not path.exists()
        and path.with_name(path.name + ".partial").exists()
    )


def test_alias_materialization_streams_each_declared_destination(tmp_path):
    from copy import deepcopy

    value, _, capture = inputs_fixture(tmp_path)
    alias = deepcopy(value["files"][0])
    alias["container_path"] = "/lib/alias.so"
    value["files"].append(alias)
    value["files"].sort(key=lambda row: row["container_path"])
    path = tmp_path / "runtime.gz"
    result = retain_runtime_layer(value, [capture], directories(), path)
    verify_archive(result["archive"], path)
    with tarfile.open(path, "r:gz") as archive:
        assert (
            archive.extractfile("lib/alias.so").read()
            == archive.extractfile("lib/lib.so").read()
        )


@pytest.mark.parametrize("field", ["native_executed", "cache_eligible"])
def test_byte_capture_cannot_claim_execution_or_cache(tmp_path, field):
    value, _, capture = inputs_fixture(tmp_path)
    result = retain_runtime_layer(
        value, [capture], directories(), tmp_path / "runtime.gz"
    )
    result[field] = True
    with pytest.raises(ContractError):
        validate_runtime_layer(result)


def test_receipt_semantic_digest_binds_every_entry(tmp_path):
    value, _, capture = inputs_fixture(tmp_path)
    result = retain_runtime_layer(
        value, [capture], directories(), tmp_path / "runtime.gz"
    )
    forged = deepcopy(result)
    forged["archive"]["entries"][0]["mtime_ns"] += 1
    with pytest.raises(ContractError):
        validate_runtime_layer(forged)


def test_equal_input_epochs_produce_identical_gzip_and_semantic_identity(tmp_path):
    value, _, capture = inputs_fixture(tmp_path)
    first = tmp_path / "first.gz"
    second = tmp_path / "second.gz"
    a = retain_runtime_layer(value, [capture], directories(), first)
    b = retain_runtime_layer(value, [capture], directories(), second)
    assert a == b and first.read_bytes() == second.read_bytes()


def test_existing_output_and_partial_are_preserved(tmp_path):
    value, _, capture = inputs_fixture(tmp_path)
    destination = tmp_path / "runtime.gz"
    destination.write_bytes(b"foreign-final")
    with pytest.raises(FileExistsError):
        retain_runtime_layer(value, [capture], directories(), destination)
    assert destination.read_bytes() == b"foreign-final"
    destination.unlink()
    partial = tmp_path / "runtime.gz.partial"
    partial.write_bytes(b"foreign-partial")
    with pytest.raises(FileExistsError):
        retain_runtime_layer(value, [capture], directories(), destination)
    assert partial.read_bytes() == b"foreign-partial" and not destination.exists()
