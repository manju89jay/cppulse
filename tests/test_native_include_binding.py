"""Native normalization binds parsed include buffers, not restored disk bytes."""

from pathlib import Path
import hashlib
from typing import Any
from cppulse.analysis import normalize_native_analysis
from test_analysis_inventory import native_snapshot
from test_measured_normalization import add_metrics


def snapshot(tmp_path: Path, *, mode: str):
    def mutate(report: dict[str, Any], root: Path) -> None:
        add_metrics(report, root)
        original = (root / "resources/clang/include/stddef.h").read_bytes()
        identity = {
            "method": "libclang-tu-buffer-sha256-v1",
            "status": "available",
            "sha256": hashlib.sha256(
                original if mode != "restored" else b"changed during parse"
            ).hexdigest(),
            "size_bytes": len(
                original if mode != "restored" else b"changed during parse"
            ),
        }
        edge = {
            "source": "main.cpp",
            "target": str(root / "resources/clang/include/stddef.h"),
            "target_kind": "external",
            "direct": True,
        }
        if mode != "legacy":
            edge["content_identity"] = identity
        report["metadata"]["analysis"]["native_metrics"]["files"][0]["includes"] = [
            edge
        ]

    return native_snapshot(tmp_path, mutate=mutate)


def test_retained_resource_include_matches_actual_tu_buffer(tmp_path: Path) -> None:
    frozen, args = snapshot(tmp_path, mode="matching")
    result = normalize_native_analysis(frozen, **args)
    assert result.inventory["items"][0]["context_match"] == "matched"


def test_restored_resource_cannot_hide_different_parsed_include_bytes(
    tmp_path: Path,
) -> None:
    frozen, args = snapshot(tmp_path, mode="restored")
    result = normalize_native_analysis(frozen, **args)
    assert result.inventory["items"][0]["context_match"] == "mismatched"
    assert any(
        "include buffer" in message
        for message in result.inventory["items"][0]["limitations"]
    )


def test_legacy_path_only_include_does_not_establish_matched_source(
    tmp_path: Path,
) -> None:
    frozen, args = snapshot(tmp_path, mode="legacy")
    assert (
        normalize_native_analysis(frozen, **args).inventory["items"][0]["context_match"]
        == "unverified"
    )


def test_legacy_report_without_include_inventory_remains_readable_unverified(
    tmp_path: Path,
) -> None:
    frozen, args = native_snapshot(tmp_path)
    result = normalize_native_analysis(frozen, **args)
    assert result.metrics is None
    assert result.inventory["items"][0]["context_match"] == "unverified"


def test_parsed_include_changes_observed_context_identity(tmp_path: Path) -> None:
    one, args1 = snapshot(tmp_path / "one", mode="matching")
    two, args2 = snapshot(tmp_path / "two", mode="restored")
    first = normalize_native_analysis(one, **args1).derived_parse_contexts[0]
    second = normalize_native_analysis(two, **args2).derived_parse_contexts[0]
    # Compare dependency identity rather than different fixture cwd roots.
    assert first["dependencies"] != second["dependencies"]


def test_precompiled_or_forced_include_closure_is_not_inferred_from_empty_edges(
    tmp_path: Path,
) -> None:
    def mutate(report: dict[str, Any], root: Path) -> None:
        add_metrics(report, root)
        report["metadata"]["analysis"]["files"][0]["parse_arguments"].extend(
            ["-include", "potential-pch.hpp"]
        )

    frozen, args = native_snapshot(tmp_path, mutate=mutate)
    row = normalize_native_analysis(frozen, **args).inventory["items"][0]
    assert row["context_match"] == "unverified"
    assert any("closure" in message for message in row["limitations"])


def test_known_preprocessing_query_cannot_get_verified_buffer_coherence(
    tmp_path: Path,
) -> None:
    def mutate(report: dict[str, Any], root: Path) -> None:
        # Conservative finite-profile rejection also applies inside comments;
        # this tests the binding rule, not native preprocessing accuracy.
        (root / "main.cpp").write_text(
            "int main(){return 0;} // __has_include unknown query\n"
        )
        add_metrics(report, root)

    frozen, args = native_snapshot(tmp_path, mutate=mutate)
    row = normalize_native_analysis(frozen, **args).inventory["items"][0]
    assert row["context_match"] == "unverified"
    assert row["buffer_coherence"] == "unverified"


def test_literal_directory_name_is_not_a_preprocessing_operator(tmp_path: Path) -> None:
    root = tmp_path / "__has_include"
    frozen, args = native_snapshot(root, mutate=add_metrics)
    row = normalize_native_analysis(frozen, **args).inventory["items"][0]
    assert row["context_match"] == "matched"
    assert row["buffer_coherence"] == "verified"
