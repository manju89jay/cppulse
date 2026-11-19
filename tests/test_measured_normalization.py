"""Measured normalization tests using labeled synthetic execution contracts."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

import pytest

from cppulse.analysis import normalize_native_analysis, persist_native_analysis
from cppulse.contracts import validate
from cppulse.errors import ContractError
from test_analysis_inventory import native_snapshot
from tests.test_maintenance_metrics_contract import native_metric_report


def add_metrics(report: dict[str, Any], root: Path) -> None:
    """Attach the measured raw test shape to the existing closed fixture."""
    raw = deepcopy(native_metric_report()["metadata"]["analysis"]["native_metrics"])
    raw["files"][0]["path"] = str(root / "main.cpp")
    raw["files"][0]["source_content_sha256"] = hashlib.sha256(
        (root / "main.cpp").read_bytes()
    ).hexdigest()
    report["metadata"]["analysis"]["native_metrics"] = raw


def test_native_measured_cells_have_distinct_stable_file_function_context_ids(
    tmp_path: Path,
) -> None:
    snapshot, selection = native_snapshot(tmp_path, mutate=add_metrics)
    result = normalize_native_analysis(snapshot, **selection)
    validate("analysis_metrics", result.metrics)
    metrics = result.metrics
    assert metrics["analysis_inventory_id"] == result.inventory["id"]
    assert metrics["job_context_id"] == "native"
    assert all(row["file"] == "main.cpp" for row in metrics["items"])
    assert len({row["id"] for row in metrics["items"]}) == len(metrics["items"])
    assert {row["context_id"] for row in metrics["items"]} == {
        result.inventory["items"][0]["parse_context_id"]
    }
    values = {(row["symbol"], row["metric"]): row["value"] for row in metrics["items"]}
    assert values[(None, "physical_loc")] == 1
    assert values[("c:@F@a#", "cyclomatic_complexity")] == 1
    assert result.metrics == normalize_native_analysis(snapshot, **selection).metrics


def test_missing_legacy_metrics_remain_missing(tmp_path: Path) -> None:
    snapshot, selection = native_snapshot(tmp_path)
    assert normalize_native_analysis(snapshot, **selection).metrics is None


def test_actual_buffer_digest_must_agree_with_frozen_native_input(
    tmp_path: Path,
) -> None:
    def mutate(report: dict[str, Any], root: Path) -> None:
        add_metrics(report, root)
        report["metadata"]["analysis"]["native_metrics"]["files"][0][
            "source_content_sha256"
        ] = ("f" * 64)

    snapshot, selection = native_snapshot(tmp_path, mutate=mutate)
    with pytest.raises(ContractError, match="buffer|content|digest"):
        normalize_native_analysis(snapshot, **selection)


def test_publication_retains_metrics_as_a_typed_immutable_artifact(
    tmp_path: Path,
) -> None:
    snapshot, selection = native_snapshot(tmp_path, mutate=add_metrics)
    derived = persist_native_analysis(
        snapshot, workspace=tmp_path, store=tmp_path / "store", **selection
    )
    derived.verify()
    descriptors = [
        row
        for row in derived.manifest["artifacts"]
        if row.get("contract", {}).get("kind") == "analysis_metrics"
    ]
    assert len(descriptors) == 1
    document = derived.read_json(descriptors[0]["id"])
    assert document["job_context_id"] == "native"
    assert any(row["metric"] == "cyclomatic_complexity" for row in document["items"])


@pytest.mark.parametrize(
    "source,lines",
    [
        (b"int main() { return 0; }\r", 1),
        (b"\rint main() { return 0; }\r\n", 2),
        (b"\n\rint main() { return 0; }", 3),
    ],
)
def test_retained_buffer_line_accounting_matches_native_crlf_profile(
    tmp_path: Path, source: bytes, lines: int
) -> None:
    def mutate(report: dict[str, Any], root: Path) -> None:
        (root / "main.cpp").write_bytes(source)
        add_metrics(report, root)
        report["metadata"]["total_loc"] = lines
        raw = report["metadata"]["analysis"]["native_metrics"]["files"][0]
        raw["physical_loc"] = lines

    snapshot, selection = native_snapshot(tmp_path, mutate=mutate)
    result = normalize_native_analysis(snapshot, **selection)
    assert (
        next(
            row["value"]
            for row in result.metrics["items"]
            if row["metric"] == "physical_loc"
        )
        == lines
    )


def test_health_publication_and_html_keep_missing_required_context_explicit(
    tmp_path: Path,
) -> None:
    from cppulse.maintenance import persist_maintenance_health
    from cppulse.presentation import build_snapshot_view, render_snapshot_html

    snapshot, selection = native_snapshot(tmp_path, mutate=add_metrics)
    from cppulse.tooling import load_rule_registry

    selection["requested_rules"] = [row["id"] for row in load_rule_registry()["rules"]]
    normalized = persist_native_analysis(
        snapshot, workspace=tmp_path, store=tmp_path / "store", **selection
    )
    derived = persist_maintenance_health(
        normalized,
        workspace=tmp_path,
        store=tmp_path / "store",
        required_context_ids=["native", "missing-consumer"],
    )
    derived.verify()
    health_artifacts = [
        row
        for row in derived.manifest["artifacts"]
        if row.get("contract", {}).get("kind") == "maintenance_health"
    ]
    assert len(health_artifacts) == 1
    health = derived.read_json(health_artifacts[0]["id"])
    assert health["aggregate"]["overall"] is None
    assert health["aggregate"]["incomplete_required_context_ids"] == [
        "missing-consumer"
    ]
    assert health["contexts"][0]["availability"] == "scored"
    view = build_snapshot_view(derived)
    html = render_snapshot_html(view)
    assert "Measured maintenance health" in html
    assert "Inferred parse opt-in does not waive" in html
    assert "Measured file and function facts" in html
    assert "missing-consumer" in html
    assert "Full required scope: partial; overall: Unavailable" in html


@pytest.mark.parametrize("metric,value", [("physical_loc", 2), ("code_loc", 0)])
def test_raw_line_metrics_must_reproduce_bound_bytes_and_complete_tokens(
    tmp_path: Path, metric: str, value: int
) -> None:
    def mutate(report: dict[str, Any], root: Path) -> None:
        add_metrics(report, root)
        report["metadata"]["analysis"]["native_metrics"]["files"][0][metric] = value

    snapshot, selection = native_snapshot(tmp_path, mutate=mutate)
    with pytest.raises(ContractError, match="LOC"):
        normalize_native_analysis(snapshot, **selection)


def test_missing_selected_native_peer_keeps_duplication_scope_unknown(
    tmp_path: Path,
) -> None:
    snapshot, selection = native_snapshot(tmp_path, mutate=add_metrics)
    # This deliberately requests a retained input that native traversal did not
    # parse. Its absence must remain a gap rather than a clean duplicate count.
    selection["requested_files"].append("native-config.json")
    result = normalize_native_analysis(snapshot, **selection)
    duplicates = [
        row for row in result.metrics["items"] if row["metric"].startswith("duplicate_")
    ]
    assert duplicates
    assert all(
        row["availability"] == "unavailable" and row["value"] is None
        for row in duplicates
    )


def test_partitioned_metrics_preserve_global_duplication_and_unknown_peers(
    tmp_path: Path,
) -> None:
    from cppulse.analysis import _normalize_metrics
    from cppulse.measurements import DuplicateCount

    snapshot, selection = native_snapshot(tmp_path, mutate=add_metrics)
    normalized = normalize_native_analysis(snapshot, **selection)
    raw = deepcopy(native_metric_report()["metadata"]["analysis"]["native_metrics"])
    raw["files"][0]["path"] = str(tmp_path / "main.cpp")
    raw["files"][0]["source_content_sha256"] = hashlib.sha256(
        (tmp_path / "main.cpp").read_bytes()
    ).hexdigest()
    for count, expected in (
        (DuplicateCount(30, 1), "available"),
        (DuplicateCount(None, None, ("Unstarted peer.",)), "unavailable"),
    ):
        result = _normalize_metrics(
            raw,
            normalized.inventory,
            str(tmp_path),
            str(tmp_path),
            lambda file: (tmp_path / file).read_bytes(),
            duplication_counts={"main.cpp": count},
        )
        cells = {row["metric"]: row for row in result["items"]}
        assert cells["duplicate_tokens"]["value"] == count.tokens
        assert cells["duplicate_lines"]["value"] == count.lines
        assert cells["duplicate_tokens"]["availability"] == expected
    with pytest.raises(ContractError, match="omit selected"):
        _normalize_metrics(
            raw,
            normalized.inventory,
            str(tmp_path),
            str(tmp_path),
            lambda file: (tmp_path / file).read_bytes(),
            duplication_counts={},
        )
