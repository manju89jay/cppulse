"""Imported result counts remain attributed claims, never execution evidence."""
from copy import deepcopy

import pytest

from cppulse.contracts import validate
from cppulse.errors import ContractError
from test_external_import import archive


@pytest.mark.parametrize("adapter", ["ctest-junit", "generic-junit"])
def test_import_preserves_counts_context_failed_retries_and_skip(tmp_path, adapter):
    from cppulse.test_import import persist_test_import

    raw = b'<testsuite tests="3" failures="1" skipped="1"><testcase name="retry"><failure>failed attempt</failure></testcase><testcase name="retry"/><testcase name="skipped"><skipped/></testcase></testsuite>'
    parent, store, _ = archive(tmp_path, raw)
    context = parent.manifest["contexts"][0]["id"]
    child = persist_test_import(
        parent,
        workspace=tmp_path,
        store=store,
        report_artifact_id="raw-report",
        context_id=context,
        scope_files=["src/main.cpp"],
        adapter=adapter,
        producer={"name": "ctest", "version": "3.31.6"},
    )
    doc = next(
        child.read_json(a["id"])
        for a in child.manifest["artifacts"]
        if a.get("contract", {}).get("kind") == "evidence"
    )
    validate("evidence", doc)
    record = doc["records"][0]
    assert record["origin"] == "import" and record["receipt_id"] is None
    assert record["context_id"] == context
    assert record["test_counts"] == {
        "total": 3,
        "passed": 1,
        "failed": 1,
        "skipped": 1,
        "errors": 0,
    }
    assert [c["status"] for c in record["test_cases"]] == [
        "failed",
        "passed",
        "skipped",
    ]
    assert len({c["identity"] for c in record["test_cases"]}) == 3
    assert child.read_bytes("raw-report") == raw
    wrong = deepcopy(doc)
    wrong["records"][0]["test_counts"]["failed"] = 0
    with pytest.raises(ContractError):
        validate("evidence", wrong)


@pytest.mark.parametrize(
    "raw",
    [
        b"<unknown/>",
        b'<testsuite tests="0"><testcase name="hidden"/></testsuite>',
        b"<testsuite>",
    ],
)
def test_unknown_malformed_or_contradictory_report_does_not_invent_clean(tmp_path, raw):
    from cppulse.test_import import persist_test_import

    parent, store, _ = archive(tmp_path, raw)
    child = persist_test_import(
        parent,
        workspace=tmp_path,
        store=store,
        report_artifact_id="raw-report",
        context_id=parent.manifest["contexts"][0]["id"],
        scope_files=["src/main.cpp"],
        adapter="generic-junit",
        producer={"name": "fixture", "version": "1"},
    )
    doc = next(
        child.read_json(a["id"])
        for a in child.manifest["artifacts"]
        if a.get("contract", {}).get("kind") == "evidence"
    )
    row = doc["records"][0]
    assert row["test_counts"] is None and row["test_cases"] == []
    assert row["status"] == "error" and row["usability"] != "usable"
    assert child.manifest["status"] == "partial"


def test_zero_test_cases_remain_skipped_not_passed(tmp_path):
    from cppulse.test_import import persist_test_import

    parent, store, _ = archive(tmp_path, b'<testsuite tests="0"/>')
    child = persist_test_import(
        parent,
        workspace=tmp_path,
        store=store,
        report_artifact_id="raw-report",
        context_id=parent.manifest["contexts"][0]["id"],
        scope_files=["src/main.cpp"],
        adapter="generic-junit",
        producer={"name": "fixture", "version": "1"},
    )
    doc = next(
        child.read_json(a["id"])
        for a in child.manifest["artifacts"]
        if a.get("contract", {}).get("kind") == "evidence"
    )
    assert doc["records"][0]["status"] == "skipped"
    assert doc["records"][0]["test_counts"]["total"] == 0


def test_public_collect_import_retains_context_and_counts(tmp_path):
    from test_public_workflows import request_for
    from cppulse.workflows import collect_request
    from cppulse.run_store import RunStore

    raw = b'<testsuite tests="2" failures="1" skipped="1"><testcase name="failed"><failure/></testcase><testcase name="skipped"><skipped/></testcase></testsuite>'
    request = request_for(
        tmp_path,
        "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_bytes("
        + repr(raw)
        + ")",
    )
    request["normalizers"] = [
        {
            "id": "test-import",
            "kind": "test_import",
            "normalizer_version": "1.0.0",
            "report": {"step_id": "build", "role": "output", "path": "build/app"},
            "context_id": "local",
            "scope_files": ["source.cpp"],
            "adapter": "generic-junit",
            "producer": {"name": "fixture", "version": "1"},
        }
    ]
    result = collect_request(request, workspace=tmp_path, store=tmp_path / "store")
    validate("workflow_result", result)
    assert result["exit_code"] == 0, result
    final = RunStore.open_existing(tmp_path / "store").open_run(
        result["final_run"]["run_id"],
        manifest_sha256=result["final_run"]["manifest_sha256"],
    )
    records = [
        row
        for a in final.manifest["artifacts"]
        if a.get("contract", {}).get("kind") == "evidence"
        for row in final.read_json(a["id"])["records"]
        if "import_adapter" in row
    ]
    assert len(records) == 1
    assert records[0]["origin"] == "import" and records[0]["context_id"] == "local"
    assert (
        records[0]["test_counts"]["failed"] == 1
        and records[0]["test_counts"]["skipped"] == 1
    )
