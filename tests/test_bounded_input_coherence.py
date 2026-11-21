"""Actual TU inputs must agree with the globally pinned source inventory.

A selected header is intentionally changed only during the real native TU parse,
then restored before coordinator postflight. This is a behavioral counterexample,
not an invented native result or receipt. Failed raw facts must remain reviewable.
"""

from __future__ import annotations

from collections.abc import Iterator
import json
import os
from pathlib import Path
from typing import Any

import pytest

import cppulse.analysis_execution as coordinator
from cppulse.config import effective_config
from cppulse.native import NativeInstallation


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def native(tmp_path: Path) -> NativeInstallation:
    binary = Path(
        os.environ.get(
            "CPPULSE_WORK_UNIT_NATIVE",
            ROOT / "work/repairs-bounded-review/native-final/cppulse-analyzer",
        )
    ).resolve()
    assert binary.is_file(), "Actual native analyzer is required; no synthetic fallback"
    resource = tmp_path / "resources"
    (resource / "include").mkdir(parents=True)
    (resource / "include/stddef.h").write_text("// authored resource fixture\n")
    return NativeInstallation(binary, resource, (), None)


def test_transient_header_restore_cannot_relabel_actual_tu_as_frozen_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, native: NativeInstallation
) -> None:
    binary = native.analyzer
    source = tmp_path / "source"
    source.mkdir()
    header = source / "a.hpp"
    original = b"#define BRANCH 0\n"
    header.write_bytes(original)
    (source / "main.cpp").write_text(
        '#include "a.hpp"\n'
        "int value(int x) {\n"
        "#if BRANCH\n"
        " if (x) return 1;\n"
        "#endif\n"
        " return 0;\n"
        "}\n"
    )
    config = effective_config(
        source,
        tmp_path / "store",
        execution={"mode": "bounded", "jobs": 1, "wall_seconds": 20},
        history={"enabled": False},
    )
    actual_execute = coordinator.execute_work_units
    active = False
    saw_main = False

    def execute_with_transient_header(units: Any, **kwargs: Any) -> Iterator[Any]:
        nonlocal active

        def selected() -> Iterator[dict[str, Any]]:
            nonlocal active, saw_main
            for unit in units:
                if unit["primary_file"] == "main.cpp":
                    header.write_text("#define BRANCH 1\n")
                    active = saw_main = True
                yield unit

        for execution in actual_execute(selected(), **kwargs):
            if active:
                header.write_bytes(original)
                active = False
            yield execution

    monkeypatch.setattr(
        coordinator, "execute_work_units", execute_with_transient_header
    )
    try:
        result = coordinator.run_analysis(config, native, tmp_path / "work", timeout=60)
    finally:
        header.write_bytes(original)
    assert saw_main
    assert header.read_bytes() == original
    raw = next(
        (unit, outcome)
        for unit, outcome in result.results
        if unit["primary_file"] == "main.cpp"
    )
    report = json.loads(
        (Path(raw[0]["work_root"]) / "output/findings.json").read_bytes()
    )
    function = report["metadata"]["analysis"]["native_metrics"]["files"][0][
        "functions"
    ][0]
    assert (
        function["cyclomatic_complexity"] == 2
    ), "Actual parser saw temporary header state"
    assert raw[1]["execution_receipt"]["argv"][0] == str(binary)
    assert result.summary["status"] == "input_changed"
    assert result.summary["input_verification"] == "changed"
    aggregate = json.loads(result.report_path.read_bytes())
    assert all(
        row["status"] == "failed" for row in aggregate["metadata"]["analysis"]["files"]
    )
    assert aggregate["findings"] == []


def test_corruption_in_downstream_json_preserves_original_native_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, native: NativeInstallation
) -> None:
    import cppulse.pipeline as pipeline
    import cppulse.predictor.main as predictor
    from cppulse.run_store import RunStore

    binary = native.analyzer
    source = tmp_path / "source"
    source.mkdir()
    (source / "main.cpp").write_text("int value() { return 1; }\n")
    config = effective_config(
        source,
        tmp_path / "store",
        execution={
            "mode": "bounded",
            "jobs": 1,
            "wall_seconds": 20,
            "work_directory": str(tmp_path / "work"),
        },
        history={"enabled": False},
    )
    malformed = b'{"health_score":'

    def corrupt(*args: Any, **kwargs: Any) -> None:
        (Path(args[1]) / "risk_scores.json").write_bytes(malformed)
        raise RuntimeError("authored crash after downstream partial JSON write")

    monkeypatch.setattr(pipeline, "discover_native", lambda: native)
    monkeypatch.setattr(predictor, "run", corrupt)
    with pytest.raises(RuntimeError, match="downstream partial JSON"):
        pipeline.analyze(config, report_format="json", timeout=60)
    snapshot = RunStore.open_existing(config.output).resolve_latest_attempt()
    snapshot.verify()
    assert snapshot.manifest["status"] == "partial"
    bindings = json.loads(snapshot.read_bytes("analysis-bindings"))["units"]
    assert len(bindings) == 1
    binding = bindings[0]
    original = json.loads(snapshot.read_bytes(binding["result_artifact_id"]))
    receipt = snapshot.read_json(binding["receipt_artifact_id"])
    assert receipt == original["execution_receipt"]
    assert receipt["argv"][0] == str(binary)
    assert receipt["status"] == "passed"
    retained = [
        row
        for row in snapshot.manifest["artifacts"]
        if row["size_bytes"] == len(malformed)
        and snapshot.read_bytes(row["id"]) == malformed
    ]
    assert retained, "Malformed downstream bytes must remain available for diagnosis"
    assert all("contract" not in row for row in retained)
    assert not any(
        row["id"] == "normalized-risk" for row in snapshot.manifest["artifacts"]
    )


def test_corrupted_result_cannot_change_original_receipt_or_promote_public_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, native: NativeInstallation
) -> None:
    from dataclasses import replace
    import hashlib
    import cppulse.pipeline as pipeline
    from cppulse.errors import InputChanged
    from cppulse.identities import canonical_json_bytes
    from cppulse.run_store import RunStore
    from cppulse.workflows import read_documents

    source = tmp_path / "source"
    source.mkdir()
    (source / "main.cpp").write_text("int value() { return 1; }\n")
    work = tmp_path / "work"
    config = effective_config(
        source,
        tmp_path / "store",
        execution={
            "mode": "bounded",
            "jobs": 1,
            "wall_seconds": 20,
            "work_directory": str(work),
        },
        history={"enabled": False},
    )
    original_generate = pipeline.generate_report
    retained: dict[str, bytes] = {}

    def corrupt_after_actual_report(*args: Any, **kwargs: Any) -> Any:
        value = original_generate(*args, **kwargs)
        paths = list(work.rglob("result.json"))
        assert len(paths) == 1
        path = paths[0]
        retained["original"] = path.read_bytes()
        document = json.loads(retained["original"])
        document["execution_receipt"][
            "reason"
        ] = "intentional post-execution corruption"
        retained["corrupt"] = canonical_json_bytes(document)
        path.write_bytes(retained["corrupt"])
        return value

    monkeypatch.setattr(pipeline, "discover_native", lambda: native)
    clean_config = replace(
        config,
        execution={**config.execution, "work_directory": str(tmp_path / "clean-work")},
    )
    clean = pipeline.analyze(clean_config, report_format="json", timeout=60)
    assert clean["analysis_status"] == "completed"
    assert clean["input_verification"] == "verified"
    monkeypatch.setattr(pipeline, "generate_report", corrupt_after_actual_report)
    with pytest.raises(InputChanged, match="Frozen work-unit metadata changed"):
        pipeline.analyze(config, report_format="json", timeout=60)
    store = RunStore.open_existing(config.output)
    assert store.resolve_latest().run_id == clean["run_id"]
    snapshot = store.resolve_latest_attempt()
    assert snapshot.run_id != clean["run_id"]
    assert snapshot.manifest["status"] == "partial"
    assert snapshot.manifest["input_verification"] == "unverified"
    snapshot.verify()
    assert not any(
        row["id"] == "normalized-risk" for row in snapshot.manifest["artifacts"]
    )
    assert all(
        health["aggregate"]["overall"] is None
        for health in read_documents(snapshot).get("maintenance_health", [])
    )
    binding = json.loads(snapshot.read_bytes("analysis-bindings"))["units"][0]
    original = snapshot.read_bytes(binding["result_artifact_id"])
    assert original == retained["original"]
    receipt = snapshot.read_json(binding["receipt_artifact_id"])
    assert receipt == json.loads(retained["original"])["execution_receipt"]
    assert receipt == json.loads(original)["execution_receipt"]
    summary = json.loads(snapshot.read_bytes("analysis-summary"))
    assert summary["results"][0]["sha256"] == hashlib.sha256(original).hexdigest()
    assert any(
        row["size_bytes"] == len(retained["corrupt"])
        and "contract" not in row
        and snapshot.read_bytes(row["id"]) == retained["corrupt"]
        for row in snapshot.manifest["artifacts"]
    ), "Conflicting on-disk bytes must remain available as untyped diagnostics"


def test_resume_cannot_replace_deterministic_original_receipt_identity(
    tmp_path: Path, native: NativeInstallation
) -> None:
    from copy import deepcopy
    from cppulse.errors import IntegrityError
    from cppulse.work_units import validate_work_unit

    source = tmp_path / "source"
    source.mkdir()
    (source / "main.cpp").write_text("int value() { return 1; }\n")
    config = effective_config(
        source,
        tmp_path / "store",
        execution={
            "mode": "bounded",
            "jobs": 1,
            "wall_seconds": 20,
            "work_directory": str(tmp_path / "work"),
        },
        history={"enabled": False},
    )
    first = coordinator.run_analysis(config, native, tmp_path / "unused", timeout=60)
    unit, original = first.results[0]
    changed = deepcopy(original)
    forged_id = "deliberately-replaced-receipt-identity"
    changed["execution_receipt"]["id"] = forged_id
    (Path(unit["work_root"]) / "result.json").write_text(json.dumps(changed))
    with pytest.raises(IntegrityError):
        validate_work_unit(unit, changed, native_executable=native.analyzer)
    config.execution["resume"] = True
    try:
        resumed = coordinator.run_analysis(
            config, native, tmp_path / "unused2", timeout=60
        )
    except IntegrityError:
        return
    assert all(
        result["execution_receipt"] is None
        or result["execution_receipt"]["id"] != forged_id
        for _, result in resumed.results
    ), "Changed checkpoint data cannot be relabeled an original actual execution"
    if resumed.summary["resumed_units"]:
        assert all(
            result["execution_receipt"] == original["execution_receipt"]
            for _, result in resumed.results
        )


@pytest.mark.parametrize(
    "metadata,missing_summary",
    [("reason", False), ("timestamps", False), ("reason", True)],
)
def test_resume_checkpoint_metadata_must_match_original_frozen_bytes(
    tmp_path: Path, native: NativeInstallation, metadata: str, missing_summary: bool
) -> None:
    from copy import deepcopy
    from datetime import datetime, timedelta
    from cppulse.errors import IntegrityError
    from cppulse.identities import canonical_json_bytes

    source = tmp_path / "source"
    source.mkdir()
    (source / "main.cpp").write_text("int value() { return 1; }\n")
    config = effective_config(
        source,
        tmp_path / "store",
        execution={
            "mode": "bounded",
            "jobs": 1,
            "wall_seconds": 20,
            "work_directory": str(tmp_path / "work"),
        },
        history={"enabled": False},
    )
    first = coordinator.run_analysis(config, native, tmp_path / "unused", timeout=60)
    if missing_summary:
        first.summary_path.rename(tmp_path / "interrupted-original-summary.json")
    unit, original = first.results[0]
    changed = deepcopy(original)
    if metadata == "reason":
        changed["reason"] = changed["execution_receipt"]["reason"] = "altered together"
    else:
        for field in ("started_at", "finished_at"):
            value = datetime.fromisoformat(changed["execution_receipt"][field])
            changed["execution_receipt"][field] = (
                (value + timedelta(seconds=60)).isoformat().replace("+00:00", "Z")
            )
    (Path(unit["work_root"]) / "result.json").write_bytes(canonical_json_bytes(changed))
    config.execution["resume"] = True
    try:
        resumed = coordinator.run_analysis(
            config, native, tmp_path / "unused2", timeout=60
        )
    except IntegrityError:
        return
    assert all(
        result["execution_receipt"] != changed["execution_receipt"]
        for _, result in resumed.results
    ), "Valid-shaped checkpoint edits cannot acquire original-execution provenance"
    if resumed.summary["resumed_units"]:
        assert all(
            result["execution_receipt"] == original["execution_receipt"]
            for _, result in resumed.results
        )


def test_late_external_header_change_cannot_keep_current_verified_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, native: NativeInstallation
) -> None:
    import hashlib
    import cppulse.pipeline as pipeline
    from cppulse.errors import InputChanged
    from cppulse.run_store import RunStore

    dependency = tmp_path / "external.hpp"
    initial = b"#define EXTERNAL_VALUE 1\n"
    dependency.write_bytes(initial)
    source = tmp_path / "source"
    source.mkdir()
    (source / "main.cpp").write_text(
        '#include "' + str(dependency) + '"\nint value(){return EXTERNAL_VALUE;}\n'
    )
    work = tmp_path / "work"
    config = effective_config(
        source,
        tmp_path / "store",
        execution={
            "mode": "bounded",
            "jobs": 1,
            "wall_seconds": 20,
            "work_directory": str(work),
        },
        history={"enabled": False},
    )
    original_generate = pipeline.generate_report

    def change_after_actual_report(*args: Any, **kwargs: Any) -> Any:
        value = original_generate(*args, **kwargs)
        paths = list(work.rglob("output/findings.json"))
        assert len(paths) == 1
        report = json.loads(paths[0].read_bytes())
        include = report["metadata"]["analysis"]["native_metrics"]["files"][0][
            "includes"
        ][0]
        identity = include.get("content_identity")
        assert (
            identity and identity["status"] == "available"
        ), "Native include-buffer proof is required for this gate"
        assert identity["sha256"] == hashlib.sha256(initial).hexdigest()
        dependency.write_text("#define EXTERNAL_VALUE 2\n")
        return value

    monkeypatch.setattr(pipeline, "discover_native", lambda: native)
    monkeypatch.setattr(pipeline, "generate_report", change_after_actual_report)
    with pytest.raises(InputChanged, match="Native include buffer binding changed"):
        pipeline.analyze(config, report_format="json", timeout=60)
    _, completed, snapshot = RunStore.open_existing(config.output).resolve_heads()
    assert completed is None and snapshot is not None
    assert snapshot.manifest["status"] == "partial"
    assert snapshot.manifest["input_verification"] == "unverified"
    snapshot.verify()
    binding = json.loads(snapshot.read_bytes("analysis-bindings"))["units"][0]
    assert snapshot.read_json(binding["receipt_artifact_id"])["status"] == "passed"
    assert dependency.read_bytes() != initial


@pytest.mark.parametrize("query_builtin", ["__has_include", "__ha\\\ns_include"])
def test_negative_include_query_forces_fresh_resume_equal_to_clean_native(
    tmp_path: Path, native: NativeInstallation, query_builtin: str
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    queried = external / "feature.hpp"
    (source / "main.cpp").write_text(
        "int value(int x){\n#if "
        + query_builtin
        + '("'
        + str(queried)
        + '")\n if(x) return 1;\n#endif\n return 0;\n}\n'
    )
    config = effective_config(
        source,
        tmp_path / "store",
        execution={
            "mode": "bounded",
            "jobs": 1,
            "wall_seconds": 20,
            "work_directory": str(tmp_path / "work"),
        },
        history={"enabled": False},
    )
    first = coordinator.run_analysis(config, native, tmp_path / "unused", timeout=60)

    def raw_functions(execution: coordinator.AnalysisExecution) -> list[dict[str, Any]]:
        unit, _ = execution.results[0]
        report = json.loads(
            (Path(unit["work_root"]) / "output/findings.json").read_bytes()
        )
        metric = report["metadata"]["analysis"]["native_metrics"]["files"][0]
        assert metric["includes"] == [], "The dependency is a query, not an inclusion"
        return metric["functions"]

    assert raw_functions(first)[0]["cyclomatic_complexity"] == 1
    queried.write_text("// queried external feature now exists\n")
    config.execution["resume"] = True
    resumed = coordinator.run_analysis(config, native, tmp_path / "unused2", timeout=60)
    clean_config = effective_config(
        source,
        tmp_path / "store",
        execution={
            **config.execution,
            "resume": False,
            "work_directory": str(tmp_path / "clean-work"),
        },
        history={"enabled": False},
    )
    clean = coordinator.run_analysis(
        clean_config, native, tmp_path / "unused3", timeout=60
    )
    assert first.source == resumed.source == clean.source
    assert raw_functions(clean)[0]["cyclomatic_complexity"] == 2
    assert resumed.summary["resumed_units"] == 0
    assert raw_functions(resumed) == raw_functions(clean)
    assert (
        resumed.results[0][1]["execution_receipt"]["id"]
        != first.results[0][1]["execution_receipt"]["id"]
    )
