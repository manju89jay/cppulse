"""Clearly synthetic closed execution facts for pure contract regressions."""

from copy import deepcopy

from test_contracts_v2 import manifest_document


def world():
    data = {
        "run_manifest": manifest_document(),
        "execution_receipt": [],
        "execution_facts": [],
        "evidence": {
            "version": "2.0.0",
            "source_digest": manifest_document()["source"]["digest"],
            "records": [],
        },
    }
    data["run_manifest"]["input_verification"] = "verified"
    data["run_manifest"]["artifacts"] = []
    return data


def artifact(data, identifier, path=None, sha=None, size=10):
    row = {
        "id": identifier,
        "path": path or "materials/" + identifier,
        "sha256": sha or "b" * 64,
        "size_bytes": size,
        "media_type": "application/octet-stream",
    }
    data["run_manifest"]["artifacts"].append(row)
    return row


def step(data, identifier, inputs, outputs, *, depends=(), tests=None, status="passed"):
    context = data["run_manifest"]["contexts"][0]["id"]
    inventory = {row["id"]: row for row in data["run_manifest"]["artifacts"]}

    def fact(path, aid):
        row = inventory[aid]
        return {
            "path": path,
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
            "stat": {"device": 1, "inode": 1, "mtime_ns": 1, "ctime_ns": 1},
        }

    for stream in ["stdout", "stderr"]:
        artifact(
            data,
            identifier + "-" + stream,
            sha="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            size=0,
        )
    receipt = {
        "version": "2.0.0",
        "id": identifier,
        "source_digest": data["run_manifest"]["source"]["digest"],
        "context_id": context,
        "producer": {"name": "cppulse.executor", "version": "1.0.0"},
        "argv": ["/synthetic/g++", identifier],
        "cwd": "/synthetic",
        "status": status,
        "reason": "Synthetic pure contract fixture; no command executed.",
        "exit_code": 0 if status == "passed" else 1,
        "signal": None,
        "started_at": "2026-11-13T10:00:00Z",
        "finished_at": "2026-11-13T10:00:00Z",
        "depends_on": list(depends),
        "artifact_ids": list(dict.fromkeys([*inputs.values(), *outputs.values()])),
        "log_artifact_ids": [identifier + "-stdout", identifier + "-stderr"],
    }
    if tests is not None:
        receipt["tests"] = tests
    before = [fact(path, aid) for path, aid in inputs.items()]
    raw = {
        "version": "2.0.0",
        "collector_version": "1.0.0",
        "receipt": deepcopy(receipt),
        "input_facts": before,
        "input_after_facts": deepcopy(before),
        "output_facts": [
            {**fact(path, aid), "freshness": "created"} for path, aid in outputs.items()
        ],
        "preexisting_output_facts": [],
        "executable_fact": {
            "path": "/synthetic/g++",
            "sha256": "e" * 64,
            "size_bytes": 100,
            "stat": {"device": 1, "inode": 2, "mtime_ns": 1, "ctime_ns": 1},
        },
        "material_status": "available",
        "limitations": [],
        "stdout_bytes": 0,
        "stderr_bytes": 0,
        "captured_bytes": 0,
        "logs_truncated": False,
        "snapshot_limitations": [],
        "binding": {
            "status": "verified",
            "limitations": [],
            "input_artifacts": [
                {"path": path, "artifact_id": aid} for path, aid in inputs.items()
            ],
            "output_artifacts": [
                {"path": path, "artifact_id": aid} for path, aid in outputs.items()
            ],
            "log_artifacts": {
                "stdout": identifier + "-stdout",
                "stderr": identifier + "-stderr",
            },
        },
    }
    data["execution_receipt"].append(receipt)
    data["execution_facts"].append(raw)
    return raw


def add_test_evidence(data, receipt, identifier="test-evidence"):
    data["evidence"]["records"].append(
        {
            "id": identifier,
            "context_id": receipt["context_id"],
            "producer": {"name": "cppulse.ctest-junit", "version": "1.0.0"},
            "origin": "execution",
            "kind": "tests",
            "status": "passed" if receipt["status"] == "passed" else "failed",
            "usability": "usable",
            "artifact_ids": receipt["artifact_ids"],
            "receipt_id": receipt["id"],
            "scope": {
                "files": [
                    row["path"] for row in data["run_manifest"]["source"]["files"]
                ],
                "tests": ["case"],
            },
            "limitations": ["Synthetic parsed test result, not actual execution."],
        }
    )


def coverage_execution_bundle():
    from test_coverage_facts_contract import coverage_document

    data = world()
    source = data["run_manifest"]["source"]["files"][0]
    artifact(data, "source", sha=source["sha256"], size=source["size_bytes"])
    for identifier in [
        "object",
        "mapping",
        "binary",
        "profile",
        "report",
        "junit",
        "last-log",
    ]:
        artifact(
            data,
            identifier,
            sha={
                "object": "b",
                "mapping": "c",
                "binary": "d",
                "profile": "e",
                "report": "f",
                "junit": "1",
                "last-log": "2",
            }[identifier]
            * 64,
        )
    step(
        data,
        "compile",
        {source["path"]: "source"},
        {"build/main.o": "object", "build/main.gcno": "mapping"},
    )
    step(
        data,
        "link",
        {"build/main.o": "object"},
        {"build/app": "binary"},
        depends=["compile"],
    )
    test = step(
        data,
        "test",
        {"build/app": "binary"},
        {
            "build/main.gcda": "profile",
            "build/junit.xml": "junit",
            "build/LastTest.log": "last-log",
        },
        depends=["link"],
        tests={"total": 1, "passed": 1, "failed": 0, "skipped": 0, "errors": 0},
    )
    add_test_evidence(data, test["receipt"])
    step(
        data,
        "report",
        {"build/main.gcno": "mapping", "build/main.gcda": "profile"},
        {"coverage.info": "report"},
        depends=["compile", "test"],
    )
    document = coverage_document()
    document.update(
        id="coverage-observed",
        origin="execution",
        receipt_id="report",
        report_artifact_id="report",
        proof_receipt_ids=["compile", "link", "test", "report"],
        test_evidence_ids=["test-evidence"],
        instrumentation=[
            {
                "object_artifact_id": "object",
                "mapping_artifact_id": "mapping",
                "source_files": [source["path"]],
            }
        ],
        profiles=[
            {
                "artifact_id": "profile",
                "binary_artifact_id": "binary",
                "test_receipt_id": "test",
            }
        ],
    )
    data["coverage_facts"] = document
    add_ctest_plan(data)
    return data


def add_ctest_plan(data):
    from cppulse.identities import digest_json

    if not any(row["id"] == "ctest-version" for row in data["execution_receipt"]):
        step(data, "ctest-version", {}, {})
        step(data, "ctest-inventory", {"build/app": "binary"}, {}, depends=["link"])
        for row in data["execution_receipt"]:
            if row["id"] == "test":
                row["depends_on"] += ["ctest-version", "ctest-inventory"]
        for row in data["execution_facts"]:
            if row["receipt"]["id"] == "test":
                row["receipt"]["depends_on"] += ["ctest-version", "ctest-inventory"]
    context = data["run_manifest"]["contexts"][0]["id"]
    steps = [
        {
            "id": fact["receipt"]["id"],
            "context_id": context,
            "argv": fact["receipt"]["argv"],
            "cwd": ".",
            "depends_on": fact["receipt"]["depends_on"],
            "inputs": [row["path"] for row in fact["binding"]["input_artifacts"]],
            "outputs": [row["path"] for row in fact["binding"]["output_artifacts"]],
            "timeout_seconds": 30,
        }
        for fact in data["execution_facts"]
    ]
    plan = {
        "version": "2.0.0",
        "id": "synthetic-verify",
        "recipe": {
            "version": "2.0.0",
            "id": "synthetic-recipe",
            "contexts": [context],
            "jobs": 1,
            "steps": steps,
        },
        "bindings": [
            {
                "id": "test-evidence",
                "step_id": "test",
                "kind": "tests",
                "scope_files": [
                    row["path"] for row in data["run_manifest"]["source"]["files"]
                ],
                "report_path": "build/junit.xml",
                "execution_log_path": "build/LastTest.log",
                "adapter": "ctest-junit",
                "adapter_version": "1.0.0",
                "inventory_step_id": "ctest-inventory",
                "producer_version_step_id": "ctest-version",
                "exercised_inputs": ["build/app"],
            }
        ],
        "limits": {
            "max_log_bytes": 1048576,
            "max_artifact_bytes": 67108864,
            "max_metadata_bytes": 16777216,
            "termination_grace_seconds": 1,
        },
    }
    data["collection_plan"] = plan
    data["run_manifest"]["config_digest"] = digest_json(plan)
