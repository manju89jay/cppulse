"""Finite runtime declaration contracts; no source reads or execution claims."""
from copy import deepcopy
import pytest
from cppulse.errors import ContractError
from cppulse.contracts.runtime_input import (
    validate_runtime_manifest,
    validate_namespace,
)


def document():
    def file(path, source, role, size):
        return {
            "container_path": path,
            "source_path": source,
            "role": role,
            "content": {"sha256": "a" * 64, "size_bytes": size},
            "mode": 365,
            "mtime_ns": 1800000000123456789,
        }

    return {
        "version": "0.1.0",
        "state": "declared_runtime_inputs",
        "cache_eligible": False,
        "closure": "unqualified",
        "execution_ready": False,
        "lazy_runtime_closure_verified": False,
        "relocation_search_verified": False,
        "native_container_path": "/runtime/native",
        "loader_candidate_path": "/lib64/loader",
        "files": [
            file("/lib/lib.so", "/host/lib", "shared_library", 64),
            file("/lib64/loader", "/host/loader", "loader_candidate", 32),
            file("/runtime/native", "/host/native", "native", 16),
        ],
        "selection_observation": {
            "kind": "imported_ldd_observation",
            "manifest": {"sha256": "b" * 64, "size_bytes": 100},
            "stdout": {"sha256": "c" * 64, "size_bytes": 100},
            "stderr": {"sha256": "d" * 64, "size_bytes": 0},
            "producer_receipt": None,
            "environment": None,
            "cwd": None,
        },
        "non_file_inputs": ["linux-vdso.so.1"],
        "limits": {"max_entries": 4096, "max_payload_bytes": 536870912},
    }


def directories():
    return [
        {
            "path": p,
            "mode": 365,
            "mtime_ns": 0,
            "uid": 1000,
            "gid": 1000,
            "origin": "synthesized",
        }
        for p in ["/lib", "/lib64", "/runtime"]
    ]


def test_actual_declared_roles_and_namespace_are_not_execution_proof():
    value = document()
    validate_runtime_manifest(value)
    result = validate_namespace(value, [], directories())
    assert result["payload_bytes"] == 112 and result["entry_count"] == 6
    assert result["cache_eligible"] is False and result["closure"] == "unqualified"


def test_optional_supervisor_has_a_distinct_executable_role():
    value = document()
    helper = deepcopy(value["files"][-1])
    helper.update(
        container_path="/supervisor", source_path="/host/helper", role="supervisor"
    )
    value["files"].append(helper)
    validate_runtime_manifest(value)
    helper["mode"] = 0o400
    with pytest.raises(ContractError):
        validate_runtime_manifest(value)


def test_duplicate_supervisor_roles_are_not_one_immutable_helper():
    value = document()
    for path in ["/supervisor-a", "/supervisor-b"]:
        helper = deepcopy(value["files"][-1])
        helper.update(container_path=path, source_path=path, role="supervisor")
        value["files"].append(helper)
    with pytest.raises(ContractError):
        validate_runtime_manifest(value)


@pytest.mark.parametrize(
    "field",
    [
        "cache_eligible",
        "execution_ready",
        "lazy_runtime_closure_verified",
        "relocation_search_verified",
    ],
)
def test_capture_only_contract_cannot_promote_unknown_runtime(field):
    value = document()
    value[field] = True
    with pytest.raises(ContractError):
        validate_runtime_manifest(value)


@pytest.mark.parametrize(
    "path",
    [
        "/proc/self/maps",
        "/sys/cpu",
        "/dev/random",
        "/etc/hosts",
        "/a/../b",
        "//runtime/native",
    ],
)
def test_dynamic_or_noncanonical_destinations_cannot_be_frozen(path):
    value = document()
    value["files"][0]["container_path"] = path
    with pytest.raises(ContractError):
        validate_runtime_manifest(value)


def test_materialized_aliases_charge_each_destination():
    value = document()
    alias = deepcopy(value["files"][0])
    alias["container_path"] = "/lib/other.so"
    value["files"].append(alias)
    value["files"].sort(key=lambda row: row["container_path"])
    assert validate_namespace(value, [], directories())["payload_bytes"] == 176
    value["limits"]["max_payload_bytes"] = 112
    with pytest.raises(ContractError):
        validate_runtime_manifest(value)


def test_conflicting_same_source_aliases_are_not_declared_identical():
    value = document()
    alias = deepcopy(value["files"][0])
    alias.update(container_path="/lib/other.so", mtime_ns=0)
    value["files"].append(alias)
    value["files"].sort(key=lambda row: row["container_path"])
    with pytest.raises(ContractError):
        validate_runtime_manifest(value)


def test_duplicate_destinations_and_file_ancestors_fail_before_streaming():
    value = document()
    value["files"].insert(1, deepcopy(value["files"][0]))
    with pytest.raises(ContractError):
        validate_runtime_manifest(value)
    value = document()
    value["files"][0]["container_path"] = "/runtime"
    with pytest.raises(ContractError):
        validate_namespace(value, [], directories())


def test_every_parent_has_one_explicit_directory_record():
    value = document()
    with pytest.raises(ContractError):
        validate_namespace(value, [], directories()[1:])
    with pytest.raises(ContractError):
        validate_namespace(value, [], directories() + [directories()[0]])


def test_metadata_and_imported_provenance_cannot_be_invented():
    value = document()
    value["files"][0]["mtime_ns"] = 0.0
    with pytest.raises(ContractError):
        validate_runtime_manifest(value)
    value = document()
    value["selection_observation"]["environment"] = {"LANG": "C"}
    with pytest.raises(ContractError):
        validate_runtime_manifest(value)


def test_source_paths_and_receipts_are_not_semantic_layer_identity():
    value = document()
    original = validate_namespace(value, [], directories())["semantic_namespace_sha256"]
    value["files"][0]["source_path"] = "/other/identical-library"
    value["selection_observation"]["stdout"]["sha256"] = "e" * 64
    assert (
        validate_namespace(value, [], directories())["semantic_namespace_sha256"]
        == original
    )


@pytest.mark.parametrize("captures,dirs", [(None, []), ({}, []), ([], None), ([], {})])
def test_namespace_component_shapes_fail_as_contract_errors(captures, dirs):
    with pytest.raises(ContractError):
        validate_namespace(document(), captures, dirs)


@pytest.mark.parametrize(
    "bad",
    [
        None,
        3,
        {
            "path": "\ud800",
            "mode": 365,
            "mtime_ns": 0,
            "uid": 1000,
            "gid": 1000,
            "origin": "synthesized",
        },
    ],
)
def test_malformed_synthesized_records_do_not_escape_typed_boundary(bad):
    with pytest.raises(ContractError):
        validate_namespace(document(), [], [bad])


@pytest.mark.parametrize(
    "role,mode", [("native", 256), ("loader_candidate", 256), ("shared_library", 0)]
)
def test_declared_permissions_must_allow_normalized_user_to_read_and_execute(
    role, mode
):
    value = document()
    next(row for row in value["files"] if row["role"] == role)["mode"] = mode
    with pytest.raises(ContractError):
        validate_runtime_manifest(value)


def test_actual_retained_project_combines_without_reopening_source(tmp_path):
    import shutil
    from cppulse.frozen_layer import retain_frozen_layer, verify_frozen_layer
    from test_frozen_input_inventory import selected

    source, request = selected(tmp_path)
    path = tmp_path / "layer.gz"
    capture = retain_frozen_layer(request, path)
    verify_frozen_layer(capture, path, request=request)
    shutil.rmtree(source)
    result = validate_namespace(document(), [capture], directories())
    assert result["payload_bytes"] == 119 and result["entry_count"] == 9
    assert result["cache_eligible"] is False


def test_runtime_file_cannot_overwrite_actual_captured_project_path(tmp_path):
    from cppulse.frozen_layer import retain_frozen_layer
    from test_frozen_input_inventory import selected

    _, request = selected(tmp_path)
    capture = retain_frozen_layer(request, tmp_path / "layer.gz")
    value = document()
    value["files"][0]["container_path"] = "/input/a.cpp"
    value["files"].sort(key=lambda row: row["container_path"])
    with pytest.raises(ContractError):
        validate_namespace(value, [capture], directories())


def test_actual_captured_proc_root_cannot_be_promoted_to_image_inputs(tmp_path):
    from cppulse.frozen_layer import retain_frozen_layer
    from test_frozen_input_inventory import selected

    _, request = selected(tmp_path)
    request["path_map"][0]["container_root"] = "/proc"
    capture = retain_frozen_layer(request, tmp_path / "layer.gz")
    with pytest.raises(ContractError):
        validate_namespace(document(), [capture], directories())
