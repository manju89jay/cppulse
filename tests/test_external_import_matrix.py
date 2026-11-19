"""Versioned external namespaces and conservative relationship semantics."""
from copy import deepcopy

import pytest

from cppulse.contracts import validate
from cppulse.errors import ContractError
from cppulse.external import normalize_gcc_import
from test_external_import import archive


@pytest.mark.parametrize(
    "adapter,namespace,name,version",
    [
        ("clang-tidy-text", "clang-tidy", "clang-tidy", "19.1.7"),
        ("cppcheck-xml", "cppcheck", "Cppcheck", "2.17.1"),
    ],
)
def test_supported_external_matrix_has_explicit_namespace(
    tmp_path, adapter, namespace, name, version
):
    snapshot, _, selection = archive(tmp_path)
    fact = normalize_gcc_import(snapshot, **selection)
    fact["adapter"]["name"] = adapter
    fact["producer_namespace"] = namespace
    fact["producer"] = {"name": name, "version": version}
    for row in fact["observations"]:
        row["namespaced_rule_id"] = namespace + ":" + row["original_rule_id"]
        row["rule_version"] = version
    validate("external_analysis_facts", fact)
    wrong = deepcopy(fact)
    wrong["producer_namespace"] = "gcc"
    with pytest.raises(ContractError):
        validate("external_analysis_facts", wrong)


def test_repeated_and_overlapping_imports_never_become_confirmation(tmp_path):
    from cppulse.external import external_relationships

    snapshot, _, selection = archive(tmp_path)
    fact = normalize_gcc_import(snapshot, **selection)
    groups = external_relationships([fact])
    assert len(groups) == 1
    assert groups[0]["classification"] == "repeated_diagnostic"
    assert len(groups[0]["occurrences"]) == 2
    assert groups[0]["independent_confirmation"] is False
    assert groups[0]["confidence_adjustment"] == 0
    other = deepcopy(fact)
    other["id"] = "other-report"
    other["producer_namespace"] = "cppcheck"
    other["observations"] = deepcopy(other["observations"][:1])
    other["observations"][0]["id"] = "other-occurrence"
    other["observations"][0]["original_rule_id"] = "different-cppcheck-id"
    other["observations"][0]["namespaced_rule_id"] = "cppcheck:different-cppcheck-id"
    other["observations"][0]["fingerprint"] = "f" * 64
    groups = external_relationships([fact, other])
    assert (
        len(groups) == 1 and groups[0]["classification"] == "potential_location_overlap"
    )
    assert len(groups[0]["occurrences"]) == 3
    assert groups[0]["independent_confirmation"] is False
    assert groups[0]["confidence_adjustment"] == 0
    other["context_id"] = "different-job"
    assert external_relationships([fact, other]) == external_relationships([fact])


def test_public_relationships_are_bound_to_retained_occurrences(tmp_path):
    from cppulse.external import persist_gcc_import
    from cppulse.presentation import build_snapshot_view, render_snapshot_html

    snapshot, store, selection = archive(tmp_path)
    derived = persist_gcc_import(snapshot, workspace=tmp_path, store=store, **selection)
    view = build_snapshot_view(derived)
    validate("snapshot_view", view)
    assert view["external_relationships"][0]["classification"] == "repeated_diagnostic"
    assert "Independent confirmation: false" in render_snapshot_html(view)
    tampered = deepcopy(view)
    tampered["external_relationships"][0]["occurrences"].pop()
    with pytest.raises(ContractError):
        validate("snapshot_view", tampered)
    tampered = deepcopy(view)
    tampered["external_relationships"][0][
        "classification"
    ] = "potential_location_overlap"
    with pytest.raises(ContractError):
        validate("snapshot_view", tampered)
