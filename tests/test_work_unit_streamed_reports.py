"""Original work-unit semantics survive bounded native report replay."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from cppulse.errors import ContractError, IntegrityError
from cppulse.work_unit_analysis import normalize_work_unit_analysis
import test_work_unit_analysis as fixtures

published = fixtures.published


class StreamingOnly:
    """Forbid eager native-body reads while preserving genuine stored bytes."""

    def __init__(self, original: Any) -> None:
        self.original = original
        self.manifest = original.manifest
        self.native_ids = {
            row["id"]
            for row in self.manifest["artifacts"]
            if row["path"].endswith("/output/findings.json")
        }
        assert len(self.native_ids) == 2
        self.active = self.peak = self.opened = 0
        self.refuse_after_open = False

    def verify(self) -> None:
        if self.refuse_after_open:
            raise IntegrityError("Injected late retained material change")
        self.original.verify()

    def read_bytes(self, name: str) -> bytes:
        assert name not in self.native_ids, "Eager native report materialization"
        return self.original.read_bytes(name)

    def read_json(self, name: str) -> Any:
        return self.original.read_json(name)

    @contextmanager
    def open_binary(self, name: str):
        assert name in self.native_ids
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.opened += 1
        try:
            with self.original.open_binary(name) as stream:
                yield stream
        finally:
            self.active -= 1


def test_normalization_never_eagerly_reads_native_report_and_closes_each_unit(
    published: Any,
) -> None:
    material = StreamingOnly(published)
    result = normalize_work_unit_analysis(material)
    assert len(result.analyses) == 2
    assert material.opened >= 2
    assert material.peak == 1
    assert material.active == 0


def test_public_replay_remains_detached_json_with_original_report_budget(
    published: Any,
) -> None:
    from cppulse.work_unit_analysis import read_work_unit_analysis

    replay = read_work_unit_analysis(published)
    for unit in replay.units:
        assert isinstance(unit.report, dict)
        assert isinstance(unit.report["findings"], list)
        assert unit.report_artifact_id in {
            item["id"] for item in unit.result["artifacts"]
        }
    with pytest.raises(IntegrityError, match="native reports exceed"):
        read_work_unit_analysis(published, max_report_bytes=1)


def test_late_material_change_refuses_normalized_result(
    published: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cppulse.native_report_reader as reader

    material = StreamingOnly(published)
    original = reader.open_native_report

    @contextmanager
    def changed(*args: Any, **kwargs: Any):
        with original(*args, **kwargs) as report:
            yield report
            material.refuse_after_open = True

    monkeypatch.setattr(reader, "open_native_report", changed)
    with pytest.raises(IntegrityError, match="late retained material"):
        normalize_work_unit_analysis(material)
    assert material.active == 0


def test_actual_cross_unit_duplicates_survive_without_global_token_arrays(
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cppulse.pipeline as pipeline
    from cppulse.run_store import RunStore

    config = fixtures.fixtures.config(tmp_path)
    body = (
        "int value(int x) {\n"
        + "\n".join("  x += " + str(index) + ";" for index in range(20))
        + "\n  return x;\n}\n"
    )
    (config.repo / "main.cpp").write_text(body)
    (config.repo / "second.cpp").write_text(body)
    fixtures.fixtures.select_native(monkeypatch, fixtures.fixtures.native.__wrapped__())
    summary = pipeline.analyze(config, report_format="json", timeout=60)
    material = StreamingOnly(RunStore(config.output).open_run(summary["run_id"]))
    result = normalize_work_unit_analysis(material)
    duplicates = [
        item
        for analysis in result.analyses
        for item in analysis.metrics["items"]
        if item["metric"] in {"duplicate_tokens", "duplicate_lines"}
    ]
    assert len(duplicates) == 4
    assert all(
        item["availability"] == "available" and item["value"] > 0 for item in duplicates
    )
    assert material.peak == 1 and material.active == 0


def test_index_capacity_failure_closes_active_original_report(
    published: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cppulse.indexed_duplication as duplication

    material = StreamingOnly(published)

    def no_capacity(rows: Any, **kwargs: Any) -> Any:
        next(rows)
        raise ContractError("Injected duplication database capacity failure")

    monkeypatch.setattr(duplication, "indexed_duplicate_token_counts", no_capacity)
    with pytest.raises(ContractError, match="database capacity") as failure:
        normalize_work_unit_analysis(material)
    # Keep the traceback alive: correctness must not depend on garbage
    # collection eventually closing the generator's open input and spool.
    assert failure.traceback
    assert material.active == 0
