"""Pure cross-field namespace checks; full imported facts are tested separately."""

import hashlib
import pytest

from cppulse.contracts.verification import semantic
from cppulse.errors import ContractError


def facts(original, namespaced):
    return {
        "observations": [
            {
                "id": "a",
                "file": "src/main.cpp",
                "original_rule_id": original,
                "namespaced_rule_id": namespaced,
                "rule_version": "14.2.0",
            }
        ],
        "scope_files": ["src/main.cpp"],
        "producer": {"name": "GNU-G++", "version": "14.2.0"},
        "usability": "usable",
        "origin": "import",
        "receipt_id": None,
        "producer_version_receipt_id": None,
        "proof_receipt_ids": [],
    }


def test_reserved_hash_slot_literal_has_its_own_distinct_namespace():
    unsafe = "-Wformat=odd value"
    reserved = "option-" + hashlib.sha256(unsafe.encode()).hexdigest()
    semantic("external_analysis_facts", facts(unsafe, "gcc:" + reserved))
    semantic(
        "external_analysis_facts",
        facts(reserved, "gcc:option-" + hashlib.sha256(reserved.encode()).hexdigest()),
    )


def test_historical_ambiguous_reserved_literal_namespace_is_rejected():
    reserved = "option-" + hashlib.sha256(b"-Wformat=odd value").hexdigest()
    with pytest.raises(ContractError, match="namespace"):
        semantic("external_analysis_facts", facts(reserved, "gcc:" + reserved))


@pytest.mark.parametrize(
    "original",
    ["-Wunused-variable", "plain.rule_id:123", "option-short", "option-" + "A" * 64],
)
def test_ordinary_rule_names_remain_unchanged(original):
    semantic("external_analysis_facts", facts(original, "gcc:" + original))
