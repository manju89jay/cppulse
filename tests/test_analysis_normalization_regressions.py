"""Independent normalization checks using explicitly synthetic retained records.

These fixtures test transformations and publication integrity. Actual native
execution is qualified separately by the six-case C++ review driver.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from cppulse.analysis import normalize_native_analysis, persist_native_analysis
from cppulse.errors import ContractError, InputChanged
from cppulse.run_store import RunStore, StagedRun
from test_analysis_inventory import native_snapshot


def test_native_report_must_match_observed_output_option(tmp_path: Path) -> None:
    """Fresh unrelated JSON cannot replace the native invocation's report."""
    snapshot, selection = native_snapshot(
        tmp_path, report_path="different-output/findings.json"
    )
    snapshot.verify()
    with pytest.raises(ContractError, match="output|report|invocation"):
        normalize_native_analysis(snapshot, **selection)


@pytest.mark.parametrize(
    "contradiction", ["duplicate", "file_total", "finding_total", "rule"]
)
def test_raw_report_contradictions_are_checked_before_selection(
    tmp_path: Path, contradiction: str
) -> None:
    def mutate(report: dict[str, Any], root: Path) -> None:
        if contradiction == "duplicate":
            row = deepcopy(report["metadata"]["analysis"]["files"][0])
            row["path"] = str(root / "subdir" / ".." / "main.cpp")
            report["metadata"]["analysis"]["files"].append(row)
        elif contradiction == "file_total":
            report["metadata"]["file_count"] = 2
        elif contradiction == "finding_total":
            report["summary"]["total_findings"] = 1
        else:
            report["metadata"]["analysis"]["enabled_rules"].append("UNKNOWN-001")

    snapshot, selection = native_snapshot(tmp_path, mutate=mutate)
    with pytest.raises(ContractError):
        normalize_native_analysis(snapshot, **selection)


def test_normalization_reads_retained_bytes_without_live_project_or_commands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    from test_measured_normalization import add_metrics

    snapshot, selection = native_snapshot(tmp_path, mutate=add_metrics)
    (tmp_path / "main.cpp").unlink()
    (tmp_path / "native-config.json").unlink()
    (tmp_path / "compile_commands.json").unlink()

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Pure normalization must not execute project commands")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    result = normalize_native_analysis(snapshot, **selection)
    assert result.inventory["items"][0]["context_match"] == "matched"


def test_source_change_during_derived_publication_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot, selection = native_snapshot(tmp_path)
    store = RunStore(tmp_path / "store")
    original = StagedRun.publish
    parent_bytes = (snapshot.path / "run_manifest.json").read_bytes()

    def publish(self: StagedRun, manifest: dict[str, Any], **kwargs: Any):
        (tmp_path / "main.cpp").write_text("// changed after derived staging\n")
        return original(self, manifest, **kwargs)

    monkeypatch.setattr(StagedRun, "publish", publish)
    with pytest.raises(InputChanged, match="during derived publication"):
        persist_native_analysis(snapshot, workspace=tmp_path, store=store, **selection)
    assert store.resolve_latest_attempt().run_id == snapshot.run_id
    assert [path.name for path in (store.root / "runs").iterdir()] == [snapshot.run_id]
    assert (snapshot.path / "run_manifest.json").read_bytes() == parent_bytes
    snapshot.verify()
