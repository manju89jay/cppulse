"""Current installed consumers of genuine inventories, reports and sanitizer chains.

Original producer records/timestamps remain unchanged. Explicitly named authored
negative copies exercise rejection; they are never counted as real executions.
"""

from copy import deepcopy
from datetime import datetime, timezone
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from cppulse.adapters.test_results import parse_test_report
from cppulse.adapters.gcc_sanitizer import diagnostics
from cppulse.consumer import (
    describe_distribution,
    declare_consumer_matrix,
    normalize_consumer_usage,
    persist_consumer_documents,
    compare_consumers,
)
from cppulse.contracts import validate, validate_bundle
from cppulse.coverage import normalize_coverage, persist_coverage
from cppulse.errors import (
    ContractError,
    InputChanged,
    IntegrityError,
    UnsupportedVersion,
)
from cppulse.run_store import RunStore
from cppulse.sanitizers import (
    ObjectSelection,
    SanitizerSelection,
    normalize_gcc_sanitizer,
    persist_gcc_sanitizer,
)
from cppulse.test_import import normalize_test_import, persist_test_import
from cppulse.workflows import assess_run, read_documents

CASES = (
    "asan-clean",
    "asan-bad",
    "ubsan-clean",
    "ubsan-bad",
    "tsan-clean",
    "tsan-bad",
    "asan-zero-tests",
    "asan-plain-object",
    "asan-substituted-binary",
    "asan-all-skipped",
    "asan-prebuilt-gap",
    "asan-prebuilt-gap-bad",
)


@pytest.fixture(scope="module")
def inputs():
    name = os.environ.get("CPPULSE_EVIDENCE116_INPUTS")
    assert (
        name
    ), "Frozen genuine input descriptor required; no substitute execution facts"
    document = json.loads(Path(name).read_bytes())
    assert {r["case"] for r in document["sanitizer_cases"]} == set(CASES)
    return document


@pytest.fixture(autouse=True)
def installed_origin_when_requested():
    prefix = os.environ.get("CPPULSE_EVIDENCE_EXPECT_PREFIX116")
    if prefix:
        root = Path(prefix).resolve() / "cppulse"
        for name in (
            "cppulse",
            "cppulse.collection",
            "cppulse.execution",
            "cppulse.consumer",
            "cppulse.test_import",
            "cppulse.coverage",
            "cppulse.sanitizers",
            "cppulse.adapters.coverage",
            "cppulse.adapters.test_results",
            "cppulse.adapters.ctest_log",
            "cppulse.adapters.gcc_sanitizer",
        ):
            assert (
                Path(importlib.import_module(name).__file__)
                .resolve()
                .is_relative_to(root)
            )


def write(path, document):
    path.write_text(json.dumps(document, indent=2) + "\n")


def original(row, store=None):
    snapshot = RunStore.open_existing(store or row["store"]).open_run(
        row["run_id"],
        manifest_sha256=row["manifest_sha256"],
        max_snapshot_bytes=16 * 1024**2,
    )
    snapshot.verify()
    return snapshot


def selection(row):
    return SanitizerSelection(
        row["case"],
        row["sanitizer"],
        tuple(row["requested_files"]),
        "compiler-version",
        "nm-version",
        "readelf-version",
        (ObjectSelection("compile", "nm-object", "elf-object"),),
        "link",
        "elf-binary",
        "sanitizer-tests",
    )


def public_reports(inputs, snapshot, store, output):
    outputs = {}
    for kind in ("json", "html"):
        target = output / ("report." + kind)
        command = [
            inputs["console"],
            "report",
            "--input",
            str(store),
            "--evidence",
            "--run-id",
            snapshot.run_id,
            "--manifest-sha256",
            snapshot.manifest_sha256,
            "--format",
            kind,
            "--output",
            str(target),
        ]
        result = subprocess.run(
            command,
            cwd=output,
            env=dict(os.environ),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        (output / (kind + ".stdout")).write_text(result.stdout)
        (output / (kind + ".stderr")).write_text(result.stderr)
        write(
            output / (kind + "-command.json"),
            {"argv": command, "exit_status": result.returncode},
        )
        assert result.returncode == 0, (kind, result.stderr[-2500:])
        if kind == "json":
            outputs[kind] = json.loads(target.read_bytes())
            validate("snapshot_view", outputs[kind])
        else:
            assert snapshot.run_id in target.read_text()
    return outputs["json"]


@pytest.mark.parametrize("case", CASES)
def test_genuine_twelve_sanitizer_cases_retained_scope_and_public_output(
    inputs, tmp_path, case
):
    row = next(r for r in inputs["sanitizer_cases"] if r["case"] == case)
    parent = original(row, inputs["sanitizer_store"])
    fact = normalize_gcc_sanitizer(parent, selection(row))
    if row["expected_fact"]:
        assert fact == json.loads(Path(row["expected_fact"]).read_bytes())
    assert fact["origin"] == "execution"
    assert fact["adapter"] == {"name": "gcc-sanitizer", "version": "1.0.0"}
    assert fact["producer"]["version"] == "14.2.0"
    assert (fact["outcome"], fact["usability"]) == (
        row["expected_outcome"],
        row["expected_usability"],
    )
    plan = json.loads(Path(row["plan"]).read_bytes())
    assert plan["recipe"]["id"] == row["recipe_id"]
    assert plan["recipe"]["version"] == row["recipe_version"] == "2.0.0"
    assert fact["context_id"] in plan["recipe"]["contexts"]
    documents = read_documents(parent)
    receipts = {r["id"]: r for r in documents["execution_receipt"]}
    assert all(key in receipts for key in fact["proof_receipt_ids"])
    if row["expected_usability"] == "usable":
        assert fact["object_proofs"] and fact["object_proofs"][0]["observed_symbols"]
        assert (
            fact["runtime_proof"]["required_soname"]
            in fact["runtime_proof"]["observed_needed"]
        )
        assert fact["exercise_proofs"] and all(
            r["test_case_ids"] for r in fact["exercise_proofs"]
        )
    else:
        assert fact["outcome"] == "unsupported" and fact["limitations"]
    if case == "ubsan-bad":
        assert (
            receipts["tests"]["exit_code"] == 0
            and receipts["tests"]["tests"]["passed"] == 1
        )
        assert fact["outcome"] == "failed" and fact["diagnostics"]
    if "prebuilt-gap" in case:
        assert fact["requested_files"] == ["main.cpp", "prebuilt.cpp"]
        assert any(
            r["instrumentation"] == "unverified" for r in fact["linked_components"]
        )
    if case == "asan-substituted-binary":
        assert not fact["exercise_proofs"] and any(
            "differs from actual linked binary" in s for s in fact["limitations"]
        )
    store = tmp_path / "store"
    derived = persist_gcc_sanitizer(
        parent, workspace=Path(row["workspace"]), store=store, selection=selection(row)
    )
    assert read_documents(derived)["sanitizer_facts"] == [fact]
    policy = {
        "version": "2.0.0",
        "id": "selected-sanitizer116",
        "policy_version": "1.0.0",
        "evaluator_profile": "1.1.0",
        "standards": [],
        "scope": {"include": row["requested_files"], "exclude": []},
        "contexts": [fact["context_id"]],
        "gates": {"minimum_readiness": 100, "minimum_completeness": 100},
        "controls": [
            {
                "id": "sanitizer",
                "title": "Selected actual sanitizer scope",
                "kind": "sanitizer_outcome",
                "weight": 1,
                "required": True,
                "parameters": {
                    "fact_ids": [fact["id"]],
                    "sanitizer": fact["sanitizer"],
                },
                "depends_on": [],
            }
        ],
    }
    result = assess_run(derived, policy, workspace=Path(row["workspace"]), store=store)
    ref = result["final_run"]
    assessed = RunStore.open_existing(store).open_run(
        ref["run_id"], manifest_sha256=ref["manifest_sha256"]
    )
    documents = read_documents(assessed)
    validate_bundle(documents)
    assessment = documents["assessment"][0]
    status = "unknown" if fact["outcome"] == "unsupported" else fact["outcome"]
    assert assessment["controls"][0]["status"] == status
    assert assessment["controls"][0]["incomplete"] is (
        status == "unknown" or case == "asan-prebuilt-gap-bad"
    )
    assert result["exit_code"] == {"passed": 0, "failed": 1, "unknown": 3}[status]
    view = public_reports(inputs, assessed, store, tmp_path)
    assert any(
        r["kind"] == "sanitizer_facts" and json.loads(r["raw_json"]) == fact
        for r in view["facts"]
    )
    write(
        tmp_path / "genuine-sanitizer-result.json",
        {
            "case": case,
            "original_run_id": parent.run_id,
            "original_manifest_sha256": parent.manifest_sha256,
            "outcome": fact["outcome"],
            "usability": fact["usability"],
            "current_control_status": status,
            "incomplete": assessment["controls"][0]["incomplete"],
            "derived_run_id": derived.run_id,
            "assessment_run_id": assessed.run_id,
            "producer_executed_in_this_test": False,
        },
    )
    parent.verify()


@pytest.mark.parametrize(
    "mode", ["clean", "fail", "skip", "disabled", "zero", "pytest"]
)
def test_genuine_ctest_and_generic_junit_counts_are_not_process_success(
    inputs, tmp_path, mode
):
    row = next(r for r in inputs["junit"] if r["mode"] == mode)
    result = parse_test_report(
        Path(row["path"]), row["adapter"], producer=row["producer"]
    )
    assert result.usability == "usable" and result.origin == "import"
    assert (
        result.counts == row["counts"] and len(result.cases) == row["counts"]["total"]
    )
    assert result.status == (
        "passed"
        if mode == "clean"
        else "failed" if mode in {"fail", "pytest"} else "skipped"
    )
    write(
        tmp_path / "genuine-junit-result.json",
        {
            "mode": mode,
            "path": row["path"],
            "report": result.as_dict(),
            "context": "Exact original producer context retained; parser output is imported claims, not new executed verification.",
        },
    )


@pytest.mark.parametrize("adapter", ["ctest-junit", "generic-junit"])
def test_public_test_import_keeps_context_and_import_origin(inputs, tmp_path, adapter):
    parent = original(inputs["header"])
    documents = read_documents(parent)
    test = next(
        r for r in documents["execution_facts"] if r["receipt"]["id"] == "tests"
    )
    candidates = [
        r
        for r in test["binding"]["output_artifacts"]
        if r["path"].endswith("junit.xml")
    ]
    assert len(candidates) == 1
    selected = {
        "report_artifact_id": candidates[0]["artifact_id"],
        "context_id": test["receipt"]["context_id"],
        "scope_files": [],
        "adapter": adapter,
        "producer": {"name": "ctest", "version": "3.31.6"},
    }
    expected = normalize_test_import(parent, **selected)
    (record,) = expected["records"]
    assert record["test_counts"] == {
        "total": 2,
        "passed": 2,
        "failed": 0,
        "skipped": 0,
        "errors": 0,
    }
    assert record["origin"] == "import" and record["receipt_id"] is None
    assert record["context_id"] == test["receipt"]["context_id"]
    store = tmp_path / "store"
    derived = persist_test_import(
        parent, workspace=Path(inputs["header"]["workspace"]), store=store, **selected
    )
    derived_documents = read_documents(derived)
    assert any(record in doc["records"] for doc in derived_documents["evidence"])
    view = public_reports(inputs, derived, store, tmp_path)
    assert view["run"]["id"] == derived.run_id
    write(
        tmp_path / "genuine-test-import-result.json",
        {"adapter": adapter, "fact": expected, "run_id": derived.run_id},
    )


@pytest.mark.parametrize("adapter", ["lcov", "cobertura"])
def test_genuine_coverage_methods_denominators_context_and_public_output(
    inputs, tmp_path, adapter
):
    from scripts.demo_coverage import roles

    row = inputs["coverage"]
    parent = original(row)
    selected = roles(parent, adapter)
    fact = normalize_coverage(parent, **selected)
    measurements = {
        m["kind"]: m for file in fact["files"] for m in file["measurements"]
    }
    assert (measurements["line"]["covered"], measurements["line"]["total"]) == (5, 8)
    assert (measurements["branch"]["covered"], measurements["branch"]["total"]) == (
        1,
        2,
    )
    assert "decision" not in measurements and "mcdc" not in measurements
    if adapter == "lcov":
        assert (
            measurements["function"]["covered"],
            measurements["function"]["total"],
        ) == (2, 3)
    else:
        assert "function" not in measurements
    assert fact["origin"] == "execution" and fact["context_id"] == "gcc-coverage-job"
    store = tmp_path / "store"
    derived = persist_coverage(
        parent, workspace=Path(row["workspace"]), store=store, **selected
    )
    assert read_documents(derived)["coverage_facts"] == [fact]
    view = public_reports(inputs, derived, store, tmp_path)
    assert any(
        r["kind"] == "coverage_facts" and json.loads(r["raw_json"]) == fact
        for r in view["facts"]
    )
    write(
        tmp_path / "genuine-coverage-result.json",
        {"adapter": adapter, "fact": fact, "run_id": derived.run_id},
    )


def test_genuine_selected_header_context_inventory_and_missing_checks(inputs, tmp_path):
    row = inputs["header"]
    parent = original(row)
    docs = read_documents(parent)
    facts = {r["receipt"]["id"]: r for r in docs["execution_facts"]}
    header = next(
        r["artifact_id"]
        for r in facts["consumer"]["binding"]["input_artifacts"]
        if r["path"] == "package/demo.hpp"
    )
    subject = describe_distribution(
        parent,
        subject_id="selected-header116",
        kind="header-only",
        distribution_files={"include/demo.hpp": header},
    )
    usages = []
    for name, depfile in (
        ("consumer", "build/main.d"),
        ("selfcontained", "build/self.d"),
    ):
        dep = next(
            r["artifact_id"]
            for r in facts[name]["binding"]["output_artifacts"]
            if r["path"] == depfile
        )
        usage = normalize_consumer_usage(
            parent,
            subject,
            usage_id=name + "-116",
            receipt_id=name,
            configuration_probe_receipt_id="configuration",
            target_probe_receipt_id="target",
            required_artifact_ids=[header],
            depfile_artifact_ids=[dep],
        )
        assert usage["status"] == "verified", usage["limitations"]
        assert usage["observed_configuration"]["language_standard"] == "c++17"
        assert usage["observed_configuration"]["target"] == "x86_64-linux-gnu"
        usages.append(usage)
    assert usages[1]["self_containment_headers"] == ["include/demo.hpp"]
    matrix = declare_consumer_matrix(
        parent,
        subject,
        matrix_id="selected116",
        cases=[
            {
                "id": "selected-int-macro7",
                "required": True,
                "context_id": facts["consumer"]["receipt"]["context_id"],
                "configuration": usages[0]["observed_configuration"],
                "tests": ["declared-template-checks"],
                "instantiations": ["selected<int>/SELECTED_MACRO=7"],
                "self_containment_headers": ["include/demo.hpp"],
                "usage_ids": [r["id"] for r in usages],
            }
        ],
        limitations=["Finite selected int/macro7, not all types/macros."],
    )
    store = tmp_path / "store"
    local = persist_consumer_documents(
        parent,
        [
            ("distribution_subject", subject),
            *[("consumer_usage", r) for r in usages],
            ("consumer_matrix", matrix),
        ],
        workspace=Path(row["workspace"]),
        store=store,
    )
    positive = compare_consumers(
        local,
        local,
        upstream_subject_id=subject["id"],
        local_subject_id=subject["id"],
        upstream_matrix_id=matrix["id"],
        local_matrix_id=matrix["id"],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    assert positive.document["cases"][0]["local_test_status"] == "passed"
    assert positive.document["cases"][0]["missing_local_checks"] == []
    missing = deepcopy(matrix)
    missing["id"] = "missing116"
    missing["cases"][0]["tests"] = ["not-observed116"]
    variant = persist_consumer_documents(
        local,
        [("consumer_matrix", missing)],
        workspace=Path(row["workspace"]),
        store=store,
    )
    negative = compare_consumers(
        local,
        variant,
        upstream_subject_id=subject["id"],
        local_subject_id=subject["id"],
        upstream_matrix_id=matrix["id"],
        local_matrix_id=missing["id"],
        generated_at=datetime.now(timezone.utc).isoformat(),
    )
    assert negative.document["cases"][0]["local_test_status"] == "unknown"
    assert "not-observed116" in negative.document["cases"][0]["missing_local_checks"]
    published = persist_consumer_documents(
        variant,
        [("consumer_comparison", negative.document)],
        workspace=Path(row["workspace"]),
        store=store,
        raw_artifacts=negative.artifacts,
    )
    public_reports(inputs, published, store, tmp_path)
    write(
        tmp_path / "genuine-header-inventory-result.json",
        {
            "subject": subject,
            "matrix": matrix,
            "usages": usages,
            "positive": positive.document,
            "missing": negative.document,
        },
    )


def test_fresh_genuine_archive_depfile_linkmap_and_executed_binary(inputs, tmp_path):
    row = inputs["archive"]
    assert row["status"] == "passed" and row["exit_status"] == 0
    parent = original(row)
    roles = row["roles"]
    usage = normalize_consumer_usage(
        parent,
        row["subject"],
        usage_id="actual-package-use",
        receipt_id="consumer",
        configuration_probe_receipt_id="configuration",
        target_probe_receipt_id="target",
        required_artifact_ids=[roles["package/demo.hpp"], roles["package/libdemo.a"]],
        depfile_artifact_ids=[roles["build/main.d"]],
        link_map_artifact_id=roles["build/main.map"],
    )
    assert usage == row["observed_usage"] and usage["status"] == "verified"
    assert {r["proof_kind"] for r in usage["records"]} == {"depfile", "gnu-linker-map"}
    assert next(r for r in usage["records"] if r["proof_kind"] == "gnu-linker-map")[
        "members"
    ] == ["library.o"]
    config = usage["observed_configuration"]
    assert (
        config["compiler"]["version"] == "14.2.0"
        and config["target"] == "x86_64-linux-gnu"
    )
    assert (
        config["language_standard"] == "c++17"
        and config["exceptions"]
        and config["rtti"]
    )
    assert usage["linker_version"] == "2.44"
    docs = read_documents(parent)
    executed = next(
        r for r in docs["execution_facts"] if r["receipt"]["id"] == "execute"
    )
    assert (
        executed["receipt"]["exit_code"] == 0
        and executed["receipt"]["status"] == "passed"
    )
    by_id = {r["id"]: r for r in parent.manifest["artifacts"]}
    binary = by_id[roles["build/consumer"]]
    assert any(
        r["path"] == "build/consumer"
        and all(
            by_id[r["artifact_id"]][key] == binary[key]
            for key in ("sha256", "size_bytes")
        )
        for r in executed["binding"]["input_artifacts"]
    )
    store = tmp_path / "store"
    child = persist_consumer_documents(
        parent,
        [("distribution_subject", row["subject"]), ("consumer_usage", usage)],
        workspace=Path(row["workspace"]),
        store=store,
    )
    public_reports(inputs, child, store, tmp_path)
    write(
        tmp_path / "genuine-archive-inventory-result.json",
        {
            "run_id": parent.run_id,
            "manifest_sha256": parent.manifest_sha256,
            "usage": usage,
            "execute_receipt": executed["receipt"],
        },
    )


@pytest.mark.parametrize("kind", ["wrong_context", "unknown_adapter", "empty_proof"])
def test_authored_negative_claims_do_not_upgrade_genuine_material(
    inputs, tmp_path, kind
):
    row = next(r for r in inputs["sanitizer_cases"] if r["case"] == "asan-clean")
    parent = original(row, inputs["sanitizer_store"])
    documents = read_documents(parent)
    changed = normalize_gcc_sanitizer(parent, selection(row))
    if kind == "wrong_context":
        changed["context_id"] = "never-observed116"
    elif kind == "unknown_adapter":
        changed["adapter"]["version"] = "999.0.0"
    else:
        empty = diagnostics("", "asan")
        assert not empty.records and empty.runtime_error is None
        changed.update(object_proofs=[], runtime_proof=None, exercise_proofs=[])
    write(
        tmp_path / ("AUTHORED-TAMPERING-" + kind + ".json"),
        {
            "meaning": "Invalid consumer-authored negative, not a producer execution.",
            "claim": changed,
        },
    )
    with pytest.raises((ContractError, UnsupportedVersion)):
        validate_bundle({**documents, "sanitizer_facts": [changed]})


def test_actual_copied_artifact_tampering_and_stale_source_are_rejected(
    inputs, tmp_path
):
    row = next(r for r in inputs["sanitizer_cases"] if r["case"] == "asan-clean")
    parent = original(row, inputs["sanitizer_store"])
    fact = normalize_gcc_sanitizer(parent, selection(row))
    copied = RunStore(tmp_path / "AUTHORED-tampered-store")
    destination = copied.root / "runs" / parent.run_id
    shutil.copytree(parent.path, destination)
    selected = next(
        r
        for r in parent.manifest["artifacts"]
        if r["id"] == fact["object_proofs"][0]["artifact_id"]
    )
    target = destination / selected["path"]
    data = target.read_bytes()
    assert data
    target.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    with pytest.raises(IntegrityError):
        copied.open_run(parent.run_id, manifest_sha256=parent.manifest_sha256).verify()
    workspace = tmp_path / "AUTHORED-stale-source"
    workspace.mkdir()
    for entry in parent.manifest["source"]["files"]:
        path = workspace / entry["path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(row["workspace"]) / entry["path"], path)
    with (workspace / "main.cpp").open("ab") as stream:
        stream.write(b"\n// AUTHORED stale negative116\n")
    with pytest.raises(InputChanged):
        persist_gcc_sanitizer(
            parent,
            workspace=workspace,
            store=tmp_path / "must-not-promote",
            selection=selection(row),
        )
    parent.verify()
