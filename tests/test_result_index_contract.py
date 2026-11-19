"""Selected-artifact scope and identities remain explicit before indexing."""
from copy import deepcopy
import json
from pathlib import Path

import jsonschema
import pytest

from cppulse.contracts.result_index import validate_index_request
from cppulse.errors import ContractError


def request():
    return {
        "version": "0.1.0",
        "kind": "prototype_findings",
        "read_scope": "selected_artifact_only",
        "source": {
            "run_id": "sample-run",
            "manifest_sha256": "a" * 64,
            "artifact_id": "raw-findings",
            "artifact_path": "raw/δ findings.json",
            "sha256": "b" * 64,
            "size_bytes": 128,
        },
        "limits": {
            "max_index_bytes": 1024**2,
            "max_rows": 100_000,
            "max_item_bytes": 1024**2,
            "sqlite_cache_kib": 8192,
            "wall_seconds": 60,
        },
    }


def test_declared_scope_and_unicode_identity_remain_unchanged():
    value = request()
    original = deepcopy(value)
    validate_index_request(value)
    assert value == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "valid\n"),
        ("run_id", "../foreign"),
        ("run_id", "run.name"),
        ("run_id", "r" * 65),
        ("manifest_sha256", "A" * 64),
        ("artifact_path", "../raw/findings.json"),
        ("artifact_path", "/raw/findings.json"),
        ("artifact_path", "C:/raw/findings.json"),
        ("artifact_path", "C:raw/findings.json"),
        ("artifact_path", "raw//findings.json"),
        ("artifact_path", "raw/./findings.json"),
        ("artifact_path", "raw/x/../findings.json"),
        ("artifact_path", "raw\\findings.json"),
        ("artifact_path", "."),
        ("artifact_path", "raw/\0findings.json"),
        ("artifact_path", "raw/\ud800.json"),
        ("artifact_path", "raw/" + "δ" * 2048),
        ("artifact_id", "bad\0id"),
        ("artifact_id", "\ud800"),
        ("artifact_id", "😃"),
        ("artifact_id", "not an ID"),
        ("artifact_id", "r" * 129),
        ("artifact_id", "valid\n"),
        ("size_bytes", 1.0),
        ("size_bytes", True),
        ("size_bytes", 0),
        ("size_bytes", 16 * 1024**3 + 1),
    ],
)
def test_noncanonical_source_claims_are_rejected(field, value):
    document = request()
    document["source"][field] = value
    with pytest.raises(ContractError):
        validate_index_request(document)


@pytest.mark.parametrize("name", request()["limits"])
@pytest.mark.parametrize("value", [True, 1.0, 0, -1, 2**64])
def test_all_budgets_reject_coercion_and_out_of_profile_values(name, value):
    document = request()
    document["limits"][name] = value
    with pytest.raises(ContractError):
        validate_index_request(document)


@pytest.mark.parametrize(
    "field,value",
    [
        ("read_scope", "full_run_verified"),
        ("kind", "arbitrary_json"),
        ("version", "1.0.0"),
        ("extra", "claimed pass"),
    ],
)
def test_request_cannot_expand_its_scope_or_dialect(field, value):
    document = request()
    document[field] = value
    with pytest.raises(ContractError):
        validate_index_request(document)


def test_private_schema_is_valid_draft7():
    from cppulse.contracts import result_index

    path = (
        Path(result_index.__file__).with_name("schemas")
        / "result_index_private/request.schema.json"
    )
    jsonschema.Draft7Validator.check_schema(json.loads(path.read_bytes()))


def test_request_boundaries_agree_with_existing_runstore_selectors():
    from cppulse.run_store import _relative, _run_id

    document = request()
    document["source"]["run_id"] = "r" * 64
    document["source"]["artifact_id"] = "r" * 128
    _run_id(document["source"]["run_id"])
    _relative(document["source"]["artifact_path"])
    validate_index_request(document)
