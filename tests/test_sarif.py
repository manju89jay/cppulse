"""SARIF export validates against the unchanged official OASIS schema offline."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess

import jsonschema
import pytest

from cppulse.errors import ContractError
from cppulse.findings import create_finding_baseline
from cppulse.run_store import RunStore
from cppulse.sarif import build_sarif, _uri, _unicode_column
from test_findings import SCOPE, baseline, compare, normalized, retain, now

REFERENCE = Path(__file__).parent / "reference/sarif"


def official(document):
    schema_bytes = (REFERENCE / "sarif-schema-2.1.0.json").read_bytes()
    assert (
        hashlib.sha256(schema_bytes).hexdigest()
        == "c3b4bb2d6093897483348925aaa73af03b3e3f4bd4ca38cef26dcb4212a2682e"
    )
    validator = jsonschema.Draft4Validator(
        json.loads(schema_bytes), format_checker=jsonschema.FormatChecker()
    )
    validator.validate(document)


def test_export_preserves_every_occurrence_and_both_explicit_fingerprint_versions(
    tmp_path,
):
    snapshot = normalized(tmp_path, count=2)
    before = deepcopy(snapshot.manifest)
    document = build_sarif(snapshot)
    official(document)
    run = document["runs"][0]
    assert document["version"] == "2.1.0"
    assert run["columnKind"] == "unicodeCodePoints"
    assert len(run["results"]) == 2
    assert (
        len({row["properties"]["cppulseObservationId"] for row in run["results"]}) == 2
    )
    assert all(
        set(row["partialFingerprints"])
        == {"cppulse/native-1", "cppulse/native-line-anchor-1"}
        for row in run["results"]
    )
    assert all(
        row["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "main.cpp"
        for row in run["results"]
    )
    assert snapshot.manifest == before


def test_partial_and_ambiguous_state_remains_visible_in_valid_sarif(tmp_path):
    partial = build_sarif(normalized(tmp_path, partial=True, ambiguous=True))
    official(partial)
    run = partial["runs"][0]
    assert run["invocations"][0]["executionSuccessful"] is False
    assert run["invocations"][0]["toolExecutionNotifications"]
    assert (
        "cppulse/native-line-anchor-1" not in run["results"][0]["partialFingerprints"]
    )
    assert run["results"][0]["properties"]["cppulseAnchorStatus"] == "ambiguous"


def test_unique_line_shift_exposes_unchanged_state_without_rewriting_native_results(
    tmp_path,
):
    old, _ = baseline(tmp_path)
    current = normalized(tmp_path, prefix="// shifted\n")
    compared = compare(current, old)
    with pytest.raises(ContractError, match="retained"):
        build_sarif(current, comparison=compared.document)
    archived = retain(
        current,
        compared,
        "finding_comparison",
        tmp_path / "checked",
        tmp_path,
        "comparison",
    )
    export_again = build_sarif(archived, comparison=archived.read_json("comparison"))
    official(export_again)
    assert export_again["runs"][0]["results"][0]["baselineState"] == "unchanged"


@pytest.mark.parametrize(
    "path,expected",
    [
        ("src/a b#é.cpp", "src/a%20b%23%C3%A9.cpp"),
        ("a/b.cpp", "a/b.cpp"),
        ("src/100%.hpp", "src/100%25.hpp"),
    ],
)
def test_uri_identity_is_canonical_relative_and_percent_encoded(path, expected):
    assert _uri(path) == expected


@pytest.mark.parametrize(
    "path", ["../escape.cpp", "/absolute.cpp", "a//b.cpp", "a\\b.cpp"]
)
def test_unsafe_uri_paths_are_not_basename_guessed(path):
    with pytest.raises(ContractError):
        _uri(path)


def test_utf8_byte_columns_are_explicitly_converted_to_unicode_code_points():
    line = "int main() { /* é 😀 */ return (int)0.5; }"
    prefix = line[: line.index("(int)")]
    byte_column = len(prefix.encode()) + 1
    assert _unicode_column(line.encode(), byte_column) == len(prefix) + 1
    assert _unicode_column("éx".encode(), 2) is None
    assert _unicode_column(b"\xffx", 2) is None


def test_export_never_executes_or_reads_the_live_checkout(tmp_path, monkeypatch):
    snapshot = normalized(tmp_path)
    (tmp_path / "main.cpp").unlink()
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: pytest.fail("Exporter must not execute"),
    )
    official(build_sarif(snapshot))


def test_comparison_from_another_manifest_cannot_label_current_results(tmp_path):
    old, _ = baseline(tmp_path)
    current = normalized(tmp_path, prefix="// shifted\n")
    result = compare(current, old)
    result.document["current_manifest_sha256"] = "0" * 64
    with pytest.raises(ContractError):
        build_sarif(current, comparison=result.document)


def test_official_reference_retains_actual_provenance_and_upstream_terms():
    provenance = json.loads((REFERENCE / "provenance.json").read_bytes())
    assert (
        provenance["sha256"]
        == hashlib.sha256(
            (REFERENCE / "sarif-schema-2.1.0.json").read_bytes()
        ).hexdigest()
    )
    assert provenance["retrieved_at"] == "2026-11-14T00:50:47.800992+00:00"
    assert hashlib.sha256(
        (REFERENCE / "upstream-LICENSE.md").read_bytes()
    ).hexdigest() == (
        "1ee371a08c4bc2a64cf4382990271676835c3d75bc984560a181de54c88471c5"
    )


def test_unicode_columns_are_derived_from_exact_retained_source_bytes(tmp_path):
    code = "int main() { /* é 😀 */ return (int)0.5; }\n"
    prefix = code[: code.index("(int)")]
    byte_column = len(prefix.encode()) + 1
    snapshot = normalized(tmp_path, code=code, column=byte_column)
    document = build_sarif(snapshot)
    official(document)
    result = document["runs"][0]["results"][0]
    region = result["locations"][0]["physicalLocation"]["region"]
    assert region == {"startLine": 1, "startColumn": len(prefix) + 1}
    assert result["properties"]["cppulseNativeByteColumn"] == byte_column


def test_suppressed_new_occurrence_remains_in_sarif_and_raw_comparison(tmp_path):
    old, _ = baseline(tmp_path, count=0)
    current = normalized(tmp_path)
    initial = compare(current, old).document
    material = create_finding_baseline(
        current,
        baseline_id="metadata",
        reason="Synthetic metadata",
        created_at=now(),
        **SCOPE,
    ).document
    record = {
        "id": "specific-reviewed-exception",
        "gate": "finding_regression",
        "baseline_sha256": initial["baseline_sha256"],
        "fingerprint_version": "native-line-anchor-1",
        "fingerprint": initial["groups"][0]["fingerprint"],
        "file": "main.cpp",
        "context_id": "native",
        "parse_context_digest": material["cells"][0]["parse_context_digest"],
        "rule_id": "CPP-MOD-001",
        "rule_version": material["findings"][0]["rule_version"],
        "max_count": 1,
        "reason": "Explicit reviewed synthetic fixture exception",
        "owner": "fixture-owner",
        "approved_at": (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }
    checked = compare(current, old, suppressions=[record])
    comparison = checked.document
    assert comparison["gate"] == "passed"
    assert comparison["counts"]["new"] == 1
    archived = retain(
        current,
        checked,
        "finding_comparison",
        tmp_path / "checked",
        tmp_path,
        "comparison",
    )
    document = build_sarif(archived, comparison=comparison)
    official(document)
    assert len(document["runs"][0]["results"]) == 1
    result = document["runs"][0]["results"][0]
    assert result["baselineState"] == "new"
    assert result["suppressions"][0]["justification"] == record["reason"]


def test_unknown_comparison_does_not_claim_sarif_unchanged_or_new(tmp_path):
    old, _ = baseline(tmp_path)
    current = normalized(tmp_path, flags=True)
    compared = compare(current, old)
    archived = retain(
        current,
        compared,
        "finding_comparison",
        tmp_path / "checked",
        tmp_path,
        "comparison",
    )
    document = build_sarif(archived, comparison=compared.document)
    official(document)
    result = document["runs"][0]["results"][0]
    assert "baselineState" not in result
    assert result["properties"]["cppulseComparisonState"] == "unknown"


def test_standalone_comparison_cannot_promote_unverified_current_label(tmp_path):
    old, _ = baseline(tmp_path)
    original = normalized(tmp_path)
    with RunStore(tmp_path / "unverified").begin() as stage:
        for entry in original.manifest["artifacts"]:
            if entry.get("contract", {}).get("kind") == "analysis_inventory":
                inventory = original.read_json(entry["id"])
                inventory["compilation_database_artifact_id"] = None
                for row in inventory["items"]:
                    row.update(context_source="fallback", context_match="unverified")
                stage.write_json(
                    entry["path"],
                    inventory,
                    contract=entry["contract"],
                    artifact_id=entry["id"],
                )
            else:
                stage.copy_artifact(
                    entry["id"],
                    original.path / entry["path"],
                    entry["path"],
                    entry["media_type"],
                    contract=entry.get("contract"),
                )
        manifest = original.manifest
        manifest.update(run_id=stage.run_id, artifacts=stage.artifacts)
        current = stage.publish(manifest)
    comparison = compare(current, old).document
    comparison["groups"][0].update(
        unchanged_count=1, unknown_current_count=0, unknown_baseline_count=0
    )
    comparison["counts"].update(unchanged=1, unknown_current=0, unknown_baseline=0)
    with pytest.raises(ContractError, match="credible"):
        build_sarif(current, comparison=comparison)


def test_standalone_comparison_cannot_borrow_another_suppression_context(tmp_path):
    old, _ = baseline(tmp_path, count=0)
    current = normalized(tmp_path)
    comparison = compare(current, old).document
    instant = datetime.now(timezone.utc)
    comparison["groups"][0]["suppressed_count"] = 1
    comparison["counts"].update(suppressed_new=1, unsuppressed_new=0)
    comparison.update(
        gate="passed",
        suppressions_artifact_id="claimed-requests",
        suppressions_sha256="1" * 64,
    )
    comparison["suppressions"] = [
        {
            "id": "borrowed-scope",
            "gate": "finding_regression",
            "baseline_sha256": comparison["baseline_sha256"],
            "fingerprint_version": "native-line-anchor-1",
            "fingerprint": comparison["groups"][0]["fingerprint"],
            "file": "main.cpp",
            "context_id": "native",
            "parse_context_digest": "0" * 64,
            "rule_id": "CPP-MOD-001",
            "rule_version": "future-rule-version",
            "max_count": 1,
            "reason": "Unrelated context claim",
            "owner": "fixture-owner",
            "approved_at": (instant - timedelta(hours=1)).isoformat(),
            "expires_at": (instant + timedelta(hours=1)).isoformat(),
            "active": True,
            "applied_count": 1,
            "inactive_reason": None,
        }
    ]
    with pytest.raises(ContractError, match="suppression"):
        build_sarif(current, comparison=comparison)
