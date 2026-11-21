"""New protocol contract controls; no claim that v3 publication is integrated."""

from copy import deepcopy
import pytest
from cppulse.errors import ContractError
from cppulse.store_coordination import validate_store_document


def heads():
    return {
        "version": "3.0.0",
        "generation": 1,
        "latest": {"run_id": "completed", "manifest_sha256": "a" * 64},
        "latest_attempt": {"run_id": "partial", "manifest_sha256": "b" * 64},
    }


def test_empty_and_distinct_completed_attempt_heads_are_valid() -> None:
    validate_store_document("heads-v3", heads())
    validate_store_document(
        "heads-v3",
        dict(version="3.0.0", generation=0, latest=None, latest_attempt=None),
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", "2.0.0"),
        ("generation", True),
        ("generation", -1),
        ("generation", 2**53),
        ("latest", {"run_id": "../escape", "manifest_sha256": "a" * 64}),
        ("latest_attempt", {"run_id": "safe", "manifest_sha256": "A" * 64}),
        ("latest", {"run_id": "safe", "manifest_sha256": "a" * 64, "unverified": True}),
    ],
)
def test_invalid_heads_are_refused(field, value) -> None:
    document = deepcopy(heads())
    document[field] = value
    with pytest.raises(ContractError):
        validate_store_document("heads-v3", document)


def test_unknown_fields_and_missing_reference_are_refused() -> None:
    document = heads()
    document["cache_eligible"] = True
    with pytest.raises(ContractError):
        validate_store_document("heads-v3", document)
    del document["cache_eligible"]
    del document["latest_attempt"]
    with pytest.raises(ContractError):
        validate_store_document("heads-v3", document)


@pytest.mark.parametrize(
    "name",
    [
        "heads.json",
        "HEADS.JSON",
        "store-format.json",
        ".migration-v3/plan.json",
        "nested/heads.json",
    ],
)
def test_v3_protocol_metadata_cannot_be_imported_as_artifact_or_transfer(
    name: str,
) -> None:
    from cppulse.contracts import validate
    from test_contracts_v2 import artifact_document
    from test_transfer_bundle_contract import transfer_document

    artifact = artifact_document()
    artifact["path"] = name
    with pytest.raises(ContractError):
        validate("artifact", artifact)
    transfer = transfer_document()
    transfer["files"].append(
        {
            "path": "roots/upstream/runs/run1/artifacts/" + name,
            "sha256": "b" * 64,
            "size_bytes": 1,
        }
    )
    with pytest.raises(ContractError):
        validate("transfer_bundle", transfer)
