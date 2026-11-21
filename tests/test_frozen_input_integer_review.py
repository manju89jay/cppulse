"""Exact private integer fields cannot authorize invalid timestamp syntax."""

import pytest
from cppulse.contracts.frozen_input import load_frozen_input, validate_frozen_input
from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes
from test_frozen_input_contract import request, manifest


@pytest.mark.parametrize("field", ["mtime_ns", "mode", "size_bytes"])
def test_manifest_integer_values_reject_integral_json_floats(field):
    document = manifest()
    if field == "size_bytes":
        document["entries"][1]["content"][field] = 1.0
    else:
        document["entries"][0][field] = float(document["entries"][0][field])
    with pytest.raises(ContractError):
        validate_frozen_input("manifest", document)
    with pytest.raises(ContractError):
        load_frozen_input("manifest", canonical_json_bytes(document))


@pytest.mark.parametrize("field", ["native_size", "entry_limit"])
def test_request_integer_values_reject_integral_json_floats(field):
    document = request()
    if field == "native_size":
        document["native"]["size_bytes"] = 1.0
    else:
        document["limits"]["max_entries"] = 100.0
    with pytest.raises(ContractError):
        validate_frozen_input("request", document)
