"""Actual excluded native peers prevent qualified global duplication zeroes."""

from pathlib import Path

import pytest

from cppulse.contracts import validate_bundle
from cppulse.pipeline import analyze
from cppulse.run_store import RunStore
from cppulse.workflows import read_documents
import test_bounded_pipeline as fixtures


@pytest.mark.parametrize("consumer_failure", [False, True])
def test_excluded_native_peer_publishes_unknown_global_duplication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, consumer_failure: bool
) -> None:
    config = fixtures.config(tmp_path)
    (config.repo / "second.cpp").write_text("int second() { return 2; }\n")
    config.settings["exclude_paths"] = ["second.cpp"]
    fixtures.select_native(monkeypatch, fixtures.native.__wrapped__())
    if consumer_failure:
        import cppulse.predictor.main as predictor

        def failed_consumer(*args: object, **kwargs: object) -> None:
            raise RuntimeError("Authored consumer failure after excluded native peer")

        monkeypatch.setattr(predictor, "run", failed_consumer)
        with pytest.raises(RuntimeError, match="Authored consumer failure"):
            analyze(config, report_format="json", timeout=60)
        snapshot = RunStore(config.output).resolve_latest_attempt()
        assert snapshot.manifest["status"] == "partial"
    else:
        summary = analyze(config, report_format="json", timeout=60)
        snapshot = RunStore(config.output).open_run(
            summary["run_id"], manifest_sha256=summary["manifest_sha256"]
        )
    documents = read_documents(snapshot)
    validate_bundle(documents)
    scope = documents["analysis_scope"][0]
    excluded = next(row for row in scope["units"] if row["primary_file"] == "second.cpp")
    assert excluded["parse_status"] == "excluded"
    assert excluded["execution"] is not None and excluded["outcome"] == "partial"
    duplicates = [
        row for doc in documents["analysis_metrics"] for row in doc["items"]
        if row["metric"] in {"duplicate_tokens", "duplicate_lines"}
    ]
    assert len(duplicates) == 2
    assert {row["file"] for row in duplicates} == {"main.cpp"}
    assert {row["metric"] for row in duplicates} == {"duplicate_tokens", "duplicate_lines"}
    assert all(row["availability"] == "unavailable" and row["value"] is None for row in duplicates)
