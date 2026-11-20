"""Bounded payload inventories retain separate, unauthenticated foreign roots."""

from copy import deepcopy

import pytest

from cppulse.contracts import validate
from cppulse.errors import ContractError


def transfer_document():
    path = "roots/upstream/runs/run1/run_manifest.json"
    return {
        "version": "2.0.0",
        "id": "transfer-example",
        "origin": "import",
        "authentication": "unverified",
        "limits": {
            "max_files": 10000,
            "max_file_bytes": 268435456,
            "max_total_bytes": 1073741824,
            "max_metadata_bytes": 4194304,
        },
        "files": [{"path": path, "sha256": "a" * 64, "size_bytes": 10}],
        "roots": [
            {
                "id": "upstream",
                "run_id": "run1",
                "manifest_path": path,
                "manifest_sha256": "a" * 64,
                "source_digest": "b" * 64,
            }
        ],
        "limitations": [
            "Synthetic transfer inventory; hashes do not authenticate a producer."
        ],
    }


def test_transfer_namespace_preserves_distinct_upstream_and_local_subjects():
    document = transfer_document()
    root = deepcopy(document["roots"][0])
    root.update(
        id="local",
        manifest_path="roots/local/runs/run1/run_manifest.json",
        source_digest="c" * 64,
    )
    document["roots"].append(root)
    file = deepcopy(document["files"][0])
    file["path"] = root["manifest_path"]
    document["files"].append(file)
    validate("transfer_bundle", document)


@pytest.mark.parametrize(
    "mutation",
    [
        "traversal",
        "absolute",
        "wrong_namespace",
        "case_alias",
        "duplicate_root",
        "duplicate_file",
        "missing_manifest",
        "hash",
        "count_cap",
        "file_cap",
        "total_cap",
        "metadata_cap",
        "oversized_bound",
        "pointer",
        "descriptor",
        "no_auth_claim",
    ],
)
def test_transfer_rejects_unbounded_unsafe_or_relabelled_payload(mutation):
    document = transfer_document()
    file = document["files"][0]
    if mutation == "traversal":
        file["path"] = "../escape"
    elif mutation == "absolute":
        file["path"] = "/escape"
    elif mutation == "wrong_namespace":
        file["path"] = "roots/other/runs/run1/file"
    elif mutation == "case_alias":
        duplicate = deepcopy(file)
        duplicate["path"] = file["path"].replace("upstream", "UPSTREAM")
        document["files"].append(duplicate)
    elif mutation == "duplicate_root":
        document["roots"].append(deepcopy(document["roots"][0]))
    elif mutation == "duplicate_file":
        document["files"].append(deepcopy(file))
    elif mutation == "missing_manifest":
        document["roots"][0]["manifest_path"] = "roots/upstream/runs/run1/absent.json"
    elif mutation == "hash":
        document["roots"][0]["manifest_sha256"] = "f" * 64
    elif mutation == "count_cap":
        document["limits"]["max_files"] = 1
        document["files"].append({**file, "path": "roots/upstream/runs/run1/x"})
    elif mutation == "file_cap":
        document["limits"]["max_file_bytes"] = 9
    elif mutation == "total_cap":
        document["limits"]["max_total_bytes"] = 9
    elif mutation == "metadata_cap":
        document["limits"]["max_metadata_bytes"] = 9
    elif mutation == "oversized_bound":
        document["limits"]["max_total_bytes"] = 1073741825
    elif mutation == "pointer":
        document["files"].append(
            {**file, "path": "roots/upstream/runs/run1/latest.json"}
        )
    elif mutation == "descriptor":
        document["files"].append({**file, "path": "transfer_bundle.json"})
    else:
        document["authentication"] = "verified"
    with pytest.raises(ContractError):
        validate("transfer_bundle", document)


def test_transfer_requires_explicit_positive_bounds():
    document = transfer_document()
    document["limits"]["max_files"] = 0
    with pytest.raises(ContractError):
        validate("transfer_bundle", document)
