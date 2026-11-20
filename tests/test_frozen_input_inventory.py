"""Actual filesystem controls for finite descriptor inventory, not closure."""

import hashlib
import os

import pytest

from cppulse.errors import ContractError, InputChanged
from cppulse.frozen_input import inventory_frozen_inputs
from test_frozen_input_contract import request


def selected(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    (root / "a.cpp").write_bytes(b"int a;\n")
    (root / "empty").mkdir()
    req = request()
    req["path_map"][0]["source_root"] = str(root)
    return root, req


def test_real_inventory_retains_bytes_empty_dirs_metadata_and_mapping(tmp_path):
    root, req = selected(tmp_path)
    rows = inventory_frozen_inputs(req)
    assert [row["path"] for row in rows] == ["/input", "/input/a.cpp", "/input/empty"]
    assert rows[1]["content"] == {
        "sha256": hashlib.sha256(b"int a;\n").hexdigest(),
        "size_bytes": 7,
    }
    assert rows[1]["mtime_ns"] == (root / "a.cpp").stat().st_mtime_ns
    assert rows[2]["content"] is None


def test_previously_absent_header_changes_namespace_with_same_source_hash(tmp_path):
    root, req = selected(tmp_path)
    before = inventory_frozen_inputs(req)
    (root / "flag.h").write_bytes(b"#define FLAG 1\n")
    after = inventory_frozen_inputs(req)
    assert before != after
    assert before[1]["content"] == after[1]["content"]
    assert after[-1]["path"] == "/input/flag.h"


@pytest.mark.parametrize("kind", ["symlink", "fifo", "hardlink", "root_alias"])
def test_unsupported_objects_fail_without_following_or_blocking(tmp_path, kind):
    root, req = selected(tmp_path)
    if kind == "symlink":
        (root / "escape").symlink_to(tmp_path)
    elif kind == "fifo":
        os.mkfifo(root / "pipe")
    elif kind == "hardlink":
        os.link(root / "a.cpp", root / "b.cpp")
    else:
        alias = tmp_path / "alias"
        alias.symlink_to(root, target_is_directory=True)
        req["path_map"][0]["source_root"] = str(alias)
    with pytest.raises((ContractError, InputChanged)):
        inventory_frozen_inputs(req)


@pytest.mark.parametrize("limit,value", [("max_entries", 1), ("max_payload_bytes", 1)])
def test_entry_and_payload_boundaries_stop_real_reads(tmp_path, limit, value):
    _, req = selected(tmp_path)
    req["limits"][limit] = value
    with pytest.raises(ContractError):
        inventory_frozen_inputs(req)


def test_large_directory_iteration_stops_before_materializing_all_names(
    tmp_path, monkeypatch
):
    root, req = selected(tmp_path)
    for index in range(20):
        (root / (str(index) + ".h")).write_bytes(b"header")
    req["limits"]["max_entries"] = 2
    original = os.scandir
    observed = 0

    class Counted:
        def __init__(self, descriptor):
            self.iterator = original(descriptor)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.iterator.close()

        def __iter__(self):
            return self

        def __next__(self):
            nonlocal observed
            child = next(self.iterator)
            observed += 1
            return child

    monkeypatch.setattr(os, "scandir", Counted)
    with pytest.raises(ContractError, match="directory exceeds"):
        inventory_frozen_inputs(req)
    assert observed == 3


@pytest.mark.parametrize("mutation", ["file", "ancestor_create_delete"])
def test_concurrent_content_or_negative_namespace_race_fails(
    tmp_path, monkeypatch, mutation
):
    root, req = selected(tmp_path)
    original = os.read
    changed = False

    def read(descriptor, count):
        nonlocal changed
        result = original(descriptor, count)
        if result and not changed:
            changed = True
            if mutation == "file":
                (root / "a.cpp").write_bytes(b"int b;\n")
            else:
                transient = root / "flag.h"
                transient.write_bytes(b"#define FLAG\n")
                transient.unlink()
        return result

    monkeypatch.setattr(os, "read", read)
    with pytest.raises(InputChanged):
        inventory_frozen_inputs(req)
