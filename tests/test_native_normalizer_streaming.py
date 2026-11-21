"""Native byte streaming preserves the existing pure transformation contract."""

from dataclasses import asdict
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest

from cppulse.analysis import normalize_native_analysis
from cppulse.errors import ContractError, IntegrityError
from cppulse.run_store import RunSnapshot
from test_analysis_inventory import native_snapshot
from test_measured_normalization import add_metrics


def test_public_normalizer_never_reads_whole_report_bytes(tmp_path, monkeypatch):
    snapshot, selection = native_snapshot(tmp_path, mutate=add_metrics)
    original = RunSnapshot.read_bytes

    def bounded(self, name):
        assert name != selection["report_artifact_id"], "Whole native report read"
        return original(self, name)

    monkeypatch.setattr(RunSnapshot, "read_bytes", bounded)
    result = normalize_native_analysis(snapshot, **selection)
    assert result.metrics is not None
    assert result.inventory["items"][0]["file"] == "main.cpp"


@pytest.mark.parametrize("metrics", [False, True])
def test_exact_output_parity_with_preserved_prechange_normalizer(tmp_path, metrics):
    before = Path(__file__).parents[1] / "work/native-normalizer32/analysis-before.py"
    if not before.exists():
        pytest.skip(
            "Local preserved prechange oracle is not part of installed distribution"
        )
    name = "cppulse_native_normalizer32_original"
    spec = importlib.util.spec_from_file_location(name, before)
    original = importlib.util.module_from_spec(spec)
    sys.modules[name] = original
    try:
        spec.loader.exec_module(original)
        snapshot, selection = native_snapshot(
            tmp_path, mutate=add_metrics if metrics else None
        )
        assert asdict(normalize_native_analysis(snapshot, **selection)) == asdict(
            original.normalize_native_analysis(snapshot, **selection)
        )
    finally:
        sys.modules.pop(name, None)


@pytest.mark.parametrize("gap", ["closed-prefix", "metric-semantics", "metric-census"])
def test_schema_and_native_semantic_gaps_cannot_pass_normalization(tmp_path, gap):
    def mutate(report, root):
        add_metrics(report, root)
        analysis = report["metadata"]["analysis"]
        if gap == "closed-prefix":
            analysis["unexpected-extension"] = []
        elif gap == "metric-semantics":
            analysis["native_metrics"]["files"][0]["function_count"] = 999
        else:
            analysis["native_metrics"]["files"] = []

    snapshot, selection = native_snapshot(tmp_path, mutate=mutate)
    with pytest.raises(ContractError):
        normalize_native_analysis(snapshot, **selection)


def test_input_change_after_normalization_prevents_return(tmp_path, monkeypatch):
    import cppulse.analysis as module

    snapshot, selection = native_snapshot(tmp_path, mutate=add_metrics)
    descriptor = next(
        r
        for r in snapshot.manifest["artifacts"]
        if r["id"] == selection["report_artifact_id"]
    )
    original = module._normalize_metrics

    def change_after_metrics(*args, **kwargs):
        result = original(*args, **kwargs)
        with (snapshot.path / descriptor["path"]).open("r+b") as raw:
            raw.write(b"!")
        return result

    monkeypatch.setattr(module, "_normalize_metrics", change_after_metrics)
    with pytest.raises(IntegrityError):
        normalize_native_analysis(snapshot, **selection)


def test_late_real_partial_peer_does_not_exhaust_tiny_duplicate_budget(
    tmp_path, monkeypatch
):
    import hashlib
    import cppulse.indexed_duplication as module
    from cppulse.analysis import _normalize_metrics
    from tests.test_maintenance_metrics_contract import native_metric_report

    snapshot, selection = native_snapshot(tmp_path, mutate=add_metrics)
    normalized = normalize_native_analysis(snapshot, **selection)
    raw = deepcopy(native_metric_report()["metadata"]["analysis"]["native_metrics"])
    first = raw["files"][0]
    content = (tmp_path / "main.cpp").read_bytes()
    first.update(
        path=str(tmp_path / "main.cpp"),
        source_content_sha256=hashlib.sha256(content).hexdigest(),
    )
    token = first["token_stream"]["records"][0]
    first["token_stream"].update(
        records=[dict(token, spelling="unique-" + str(i)) for i in range(180)],
        retained_tokens=180,
        total_tokens=180,
        record_limit=200,
    )
    peer = deepcopy(first)
    peer["path"] = str(tmp_path / "peer.cpp")
    peer["token_stream"].update(
        complete=False,
        availability="partial",
        limitations=["Controlled incomplete frame."],
    )
    raw["files"].append(peer)
    inventory = deepcopy(normalized.inventory)
    inventory["items"].append(dict(inventory["items"][0], file="peer.cpp"))
    original = module.indexed_duplicate_token_counts

    def with_small_budget(streams, **kwargs):
        return original(
            streams,
            **kwargs,
            limits=module.DuplicationIndexLimits(max_database_bytes=64 * 1024),
        )

    # Same real frames and capacity fail before reaching the late partial peer
    # unless the checked preliminary census avoids the unnecessary index.
    with pytest.raises(ContractError, match="budget|storage"):
        original(
            ((r["path"], r["token_stream"]) for r in raw["files"]),
            directory=tmp_path,
            limits=module.DuplicationIndexLimits(max_database_bytes=64 * 1024),
        )
    monkeypatch.setattr(module, "indexed_duplicate_token_counts", with_small_budget)
    result = _normalize_metrics(
        raw, inventory, str(tmp_path), str(tmp_path), lambda _: content
    )
    cells = [r for r in result["items"] if r["metric"].startswith("duplicate_")]
    assert len(cells) == 4
    assert all(r["availability"] == "unavailable" and r["value"] is None for r in cells)
