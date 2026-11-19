"""Bounded C++17 proposal contracts preceding explicit isolated verification.

Validation never runs project code, changes source, contacts a model or establishes
semantic equivalence. Origin metadata is a caller claim, not authentication.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import jsonschema

from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes
from cppulse.run_store import RunSnapshot
from cppulse.execution import CancellationToken

MAX_REQUEST_BYTES = 4 * 1024**2
MAX_FILE_BYTES = 1024**2


@dataclass(frozen=True)
class PreparedProposal:
    """Checked transient before material, never a receipt or acceptance grant."""

    source: dict[str, bytes]
    before_tests: dict[str, int]
    required_cases: tuple[str, ...]


def _path(value: str) -> None:
    path = PurePosixPath(value)
    if (
        any(ord(c) < 32 or ord(c) == 127 for c in value)
        or path.is_absolute()
        or PureWindowsPath(value).drive
        or "\\" in value
        or ".." in path.parts
        or ".git" in path.parts
        or not path.parts
        or str(path) != value
    ):
        raise ContractError(
            "Proposal path must be canonical, relative and outside .git"
        )


def validate_request(request: dict[str, Any]) -> None:
    """Reject unsupported, unsafe and ambiguous requests before any execution."""
    schema = json.loads(
        resources.files("cppulse.contracts")
        .joinpath("schemas/semantic_repair_private/request.schema.json")
        .read_bytes()
    )
    try:
        jsonschema.validate(request, schema)
        if len(canonical_json_bytes(request)) > MAX_REQUEST_BYTES:
            raise ContractError("Proposal request exceeds four-MiB bound")
    except (jsonschema.ValidationError, UnicodeError, RecursionError) as error:
        raise ContractError(
            "Invalid isolated proposal request: " + str(error)
        ) from error
    source = set(request["source_files"])
    editable = set(request["editable_files"])
    protected = set(request["protected_files"])
    for value in source | editable | protected:
        _path(value)
    if editable & protected or editable | protected != source:
        raise ContractError(
            "Editable and protected files must partition selected source"
        )
    if "CMakeLists.txt" not in protected:
        raise ContractError("Initial CMake verification controls must be protected")
    if not any(value.endswith((".cpp", ".cc", ".cxx")) for value in protected):
        raise ContractError("Initial lane requires protected C++ test source")
    if any(not value.endswith((".cpp", ".cc", ".cxx")) for value in editable):
        raise ContractError("Only selected ordinary C++ translation units are editable")
    edited = set()
    for replacement in request["replacements"]:
        path = replacement["path"]
        _path(path)
        if path not in editable or path in edited:
            raise ContractError("Proposal changes an uneditable or duplicate file")
        edited.add(path)
        try:
            content = replacement["after"].encode("utf-8")
        except UnicodeError as error:
            raise ContractError("Replacement must be valid UTF-8") from error
        if len(content) > MAX_FILE_BYTES or b"\x00" in content:
            raise ContractError("Replacement exceeds supported source byte bounds")


def _test_outcomes(
    snapshot: RunSnapshot, documents: dict[str, Any], evidence_id: str
) -> tuple[dict[str, int], list[str]]:
    """Read outcomes only through the existing verified CTest execution binding."""
    import hashlib
    from cppulse.adapters.test_results import parse_test_report
    from cppulse.adapters.ctest_log import parse_ctest_log

    records = [
        r
        for d in documents.get("evidence", [])
        for r in d["records"]
        if r["id"] == evidence_id
    ]
    if len(records) != 1:
        raise ContractError("Selected tests evidence is missing or ambiguous")
    record = records[0]
    if (
        record["kind"] != "tests"
        or record["usability"] != "usable"
        or record["origin"] != "execution"
    ):
        raise ContractError("Selected tests must have usable actual execution evidence")
    facts = [
        f
        for f in documents.get("execution_facts", [])
        if f["receipt"]["id"] == record["receipt_id"]
    ]
    plans = [
        p
        for p in documents.get("collection_plan", [])
        if any(b["id"] == evidence_id for b in p["bindings"])
    ]
    if (
        len(facts) != 1
        or len(plans) != 1
        or facts[0]["binding"]["status"] != "verified"
    ):
        raise ContractError(
            "Selected tests lack an unambiguous verified execution binding"
        )
    binding = next(b for b in plans[0]["bindings"] if b["id"] == evidence_id)
    if binding["adapter"] != "ctest-junit" or binding["adapter_version"] != "1.0.0":
        raise ContractError("Only the reviewed CTest JUnit adapter is supported")
    receipt = facts[0]["receipt"]
    tests = receipt.get("tests")
    if not tests or tests["total"] < 1 or tests["skipped"] or tests["errors"]:
        raise ContractError(
            "Zero, skipped, erroneous or unknown test outcomes are inadequate"
        )
    if receipt["status"] != record["status"]:
        raise ContractError("Test record and actual receipt disagree")
    outputs = [
        r
        for r in facts[0]["binding"]["output_artifacts"]
        if r["path"] == binding["report_path"]
    ]
    if len(outputs) != 1:
        raise ContractError("Selected test report has no exact retained output")
    artifacts = {a["id"]: a for a in snapshot.manifest["artifacts"]}
    report_id = outputs[0]["artifact_id"]
    content = snapshot.read_bytes(report_id)
    if len(content) > MAX_FILE_BYTES:
        raise ContractError("Selected report exceeds one-MiB proposal bound")
    report = parse_test_report(
        snapshot.path / artifacts[report_id]["path"], producer=record["producer"]
    )
    if (
        report.usability != "usable"
        or report.counts != tests
        or report.report_sha256 != hashlib.sha256(content).hexdigest()
        or sorted(record["scope"]["tests"])
        != sorted(case.identity for case in report.cases)
    ):
        raise ContractError("Selected normalized tests differ from retained raw report")
    log_outputs = [
        r
        for r in facts[0]["binding"]["output_artifacts"]
        if r["path"] == binding["execution_log_path"]
    ]
    if len(log_outputs) != 1:
        raise ContractError(
            "Selected tests require retained actual CTest execution log"
        )
    log_id = log_outputs[0]["artifact_id"]
    content = snapshot.read_bytes(log_id)
    if len(content) > MAX_FILE_BYTES:
        raise ContractError("Selected execution log exceeds one-MiB proposal bound")
    log = parse_ctest_log(
        snapshot.path / artifacts[log_id]["path"], producer=record["producer"]
    )
    if (
        log.usability != "usable"
        or log.report_sha256 != hashlib.sha256(content).hexdigest()
        or sorted((r.name, r.outcome) for r in log.records)
        != sorted((c.name, c.status) for c in report.cases)
    ):
        raise ContractError(
            "Selected raw report differs from retained actual execution log"
        )
    cases = [c.name for c in report.cases]
    if len(cases) != tests["total"] or len(set(cases)) != len(cases):
        raise ContractError("Actual cases must have unambiguous positive identities")
    return tests, cases


def prepare_proposal(
    snapshot: RunSnapshot, *, workspace: Path, request: dict[str, Any]
) -> PreparedProposal:
    """Verify before pins and retain finite bytes without running or writing code.

    Returned material is caller-owned transient data, not a verification receipt.
    Execution must recheck these identities; this function cannot grant a pass.
    """
    import hashlib

    from cppulse.contracts import validate_bundle
    from cppulse.run_store import RunStore
    from cppulse.workflows import ensure_current_materials, read_documents

    validate_request(request)
    before = request["before"]
    if (
        before["run_id"] != snapshot.run_id
        or before["manifest_sha256"] != snapshot.manifest_sha256
    ):
        raise ContractError(
            "Proposal before run differs from selected immutable snapshot"
        )
    snapshot = RunStore.open_existing(snapshot.path.parent.parent).open_run(
        snapshot.run_id,
        manifest_sha256=snapshot.manifest_sha256,
        max_snapshot_bytes=32 * 1024**2,
    )
    source = snapshot.manifest["source"]
    if (
        snapshot.manifest.get("input_verification") != "verified"
        or not source["inventory_complete"]
        or source["digest"] != before["source_digest"]
    ):
        raise ContractError("Proposal requires verified complete exact before source")
    if len(snapshot.read_manifest_bytes()) > MAX_FILE_BYTES:
        raise ContractError("Proposal manifest exceeds finite bound")
    identities = {r["path"]: r for r in source["files"]}
    if set(identities) != set(request["source_files"]):
        raise ContractError(
            "Selected finite source must exactly match before inventory"
        )
    ensure_current_materials(snapshot, workspace)
    documents = read_documents(snapshot)
    validate_bundle(documents)
    tests, cases = _test_outcomes(snapshot, documents, before["test_evidence_id"])
    if not tests["failed"] or tests["failed"] + tests["passed"] != tests["total"]:
        raise ContractError(
            "Before verification must contain a real selected test failure"
        )
    if set(cases) != set(request["required_cases"]):
        raise ContractError(
            "Required case identities differ from actual before execution"
        )
    contents = {}
    for path, identity in identities.items():
        if identity["size_bytes"] > MAX_FILE_BYTES:
            raise ContractError("Selected source exceeds one-MiB bound")
        candidates = {
            row["artifact_id"]
            for facts in documents.get("execution_facts", [])
            if facts["binding"]["status"] == "verified"
            for row in facts["binding"]["input_artifacts"]
            if row["path"] == path
        }
        matches = [snapshot.read_bytes(identifier) for identifier in sorted(candidates)]
        matches = [
            b
            for b in matches
            if len(b) == identity["size_bytes"]
            and hashlib.sha256(b).hexdigest() == identity["sha256"]
        ]
        if not matches:
            raise ContractError(
                "Selected source lacks retained exact verified input bytes"
            )
        try:
            matches[0].decode("utf-8")
        except UnicodeError as error:
            raise ContractError("Initial selected source must be UTF-8") from error
        if b"\x00" in matches[0]:
            raise ContractError("Initial selected source cannot contain NUL bytes")
        contents[path] = matches[0]
    for replacement in request["replacements"]:
        path = replacement["path"]
        if replacement["before_sha256"] != identities[path]["sha256"]:
            raise ContractError("Proposal replacement has stale original-file identity")
        if replacement["after"].encode() == contents[path]:
            raise ContractError("Proposal contains an unchanged replacement")
    ensure_current_materials(snapshot, workspace)
    return PreparedProposal(contents, tests, tuple(cases))


def _verification_plan(
    documents: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    """Select one finite reviewed CMake/CTest recipe, never a command string."""
    from copy import deepcopy
    from pathlib import Path
    import hashlib

    evidence_id = request["before"]["test_evidence_id"]
    selected = [
        p
        for p in documents.get("collection_plan", [])
        if any(b["id"] == evidence_id for b in p["bindings"])
    ]
    if len(selected) != 1:
        raise ContractError("Exactly one retained verification plan is required")
    plan = deepcopy(selected[0])
    steps = plan["recipe"]["steps"]
    if len(steps) != 5 or plan["recipe"]["jobs"] > 2:
        raise ContractError(
            "Initial verification lane requires five steps and at most two jobs"
        )
    commands = [step["argv"] for step in steps]
    expected = ["cmake", "cmake", "ctest", "ctest", "ctest"]
    for step, name in zip(steps, expected):
        if Path(step["argv"][0]).name != name or not 0 < step["timeout_seconds"] <= 30:
            raise ContractError(
                "Unsupported command or timeout in selected verification lane"
            )
    if (
        commands[0][1:5] != ["-S", ".", "-B", "build"]
        or set(commands[0][5:])
        != {
            "-DCMAKE_CXX_STANDARD=17",
            "-DCMAKE_CXX_STANDARD_REQUIRED=ON",
            "-DCMAKE_CXX_EXTENSIONS=OFF",
        }
        or commands[1][1:] != ["--build", "build"]
        or commands[2][1:] != ["--version"]
        or commands[3][1:] != ["--show-only=json-v1"]
        or commands[4][1:] != ["--output-junit", "junit.xml"]
    ):
        raise ContractError(
            "Initial lane requires explicit C++17 configure/build/CTest arguments"
        )
    if [s["cwd"] for s in steps] != [".", ".", ".", "build", "build"]:
        raise ContractError("Unsupported verification working directories")
    for fact in documents.get("execution_facts", []):
        executable = fact["executable_fact"]
        if executable is None:
            raise ContractError("Before execution has no observed selected executable")
        path = Path(executable["path"])
        if (
            not path.is_file()
            or path.stat().st_size != executable["size_bytes"]
            or executable["size_bytes"] > 256 * 1024**2
        ):
            raise ContractError("Selected verification tool is stale or exceeds bound")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != executable["sha256"]:
            raise ContractError(
                "Selected verification tool bytes differ from before execution"
            )
    if (
        plan["limits"]["max_artifact_bytes"] > 8 * 1024**2
        or plan["limits"]["max_log_bytes"] > 1024**2
        or plan["limits"]["max_metadata_bytes"] > 16 * 1024**2
    ):
        raise ContractError("Selected verification plan exceeds bounded output profile")
    return plan


def verify_proposal(
    snapshot: RunSnapshot,
    *,
    workspace: Path,
    request: dict[str, Any],
    output_root: Path,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    """Explicitly compile/test a pinned proposal in a new retained local copy.

    Selected project code is trusted. Existing executor bounds jobs, wall time and
    retained logs; this function provides no hostile-code/network/memory sandbox.
    No original source apply, commit, branch, PR, model or network client exists.
    """
    from copy import deepcopy
    import hashlib
    from pathlib import Path
    import tempfile

    from cppulse.collection import collect
    from cppulse.identities import context_identity, digest_json, snapshot_inputs
    from cppulse.repairs import _git_diff
    from cppulse.workflows import ensure_current_materials, read_documents

    prepared = prepare_proposal(snapshot, workspace=workspace, request=request)
    documents = read_documents(snapshot)
    plan = _verification_plan(documents, request)
    root = Path(output_root).absolute()
    original = Path(workspace).resolve(strict=True)
    store = snapshot.path.parent.parent.resolve(strict=True)
    for parent in [root, *root.parents]:
        if parent.is_symlink():
            raise ContractError("Proposal output must not traverse symlinks")
    root = root.resolve(strict=True)
    if not root.is_dir() or any(
        root.is_relative_to(p) or p.is_relative_to(root) for p in [original, store]
    ):
        raise ContractError(
            "Proposal output must be disjoint from original source and store"
        )
    contexts = deepcopy(snapshot.manifest["contexts"])
    if len(contexts) != 1 or contexts[0]["dependencies"]:
        raise ContractError(
            "Initial lane requires one explicit dependency-free selected context"
        )
    attempt = Path(tempfile.mkdtemp(prefix="semantic-", dir=root))
    isolated = attempt / "source"
    isolated.mkdir()
    replacements = {r["path"]: r["after"].encode() for r in request["replacements"]}
    patch = []
    for path, before in prepared.source.items():
        target = isolated / path
        target.parent.mkdir(parents=True, exist_ok=True)
        after = replacements.get(path, before)
        with target.open("xb") as stream:
            stream.write(after)
        if path in replacements:
            patch.append(_git_diff(path, before, after))
    (attempt / "proposal.json").write_bytes(canonical_json_bytes(request))
    (attempt / "proposal.diff").write_text("".join(patch))
    context = contexts[0]
    context["working_directory"] = str(isolated)
    context = context_identity(context)
    after_source = snapshot_inputs(
        isolated, request["source_files"], inventory_complete=True
    )
    result = {
        "version": "0.1.0",
        "status": "incomplete",
        "semantic_equivalence": "not_established",
        "attempt_directory": str(attempt),
        "before": {**request["before"], "tests": prepared.before_tests},
        "after": None,
        "request_sha256": digest_json(request),
        "patch_sha256": hashlib.sha256("".join(patch).encode()).hexdigest(),
        "required_cases": request["required_cases"],
        "origin": request["origin"],
        "adequacy": request["adequacy"],
        "limitations": [
            "Selected tests observe behavior only; semantic equivalence, coverage, ABI and performance are not established.",
            "Trusted project execution inherits host environment; bounds cover wall time, jobs and retained output, not memory or arbitrary escaped processes.",
            "Origin hashes identify caller-supplied evidence and do not authenticate authorship.",
            "No source application, Git operation, PR or model/network client is implemented.",
        ],
    }
    try:
        after = collect(
            plan,
            workspace=isolated,
            source=after_source,
            contexts=[context],
            store=attempt / "store",
            cancel=cancel,
        )
        result["after"] = {
            "run_id": after.run_id,
            "manifest_sha256": after.manifest_sha256,
            "source_digest": after_source["digest"],
            "store": str(attempt / "store"),
            "tests": None,
            "cases": None,
        }
        after_documents = read_documents(after)
        tool_hashes = {
            f["receipt"]["id"]: f["executable_fact"]["sha256"]
            for f in documents.get("execution_facts", [])
            if f["executable_fact"] is not None
        }
        if any(
            f["executable_fact"] is not None
            and f["executable_fact"]["sha256"] != tool_hashes.get(f["receipt"]["id"])
            for f in after_documents.get("execution_facts", [])
        ):
            raise ContractError(
                "Actual after verification tool bytes differ from pinned before execution"
            )
        try:
            tests, cases = _test_outcomes(
                after, after_documents, request["before"]["test_evidence_id"]
            )
            result["after"]["tests"] = tests
            result["after"]["cases"] = cases
            if tests["failed"] or tests["errors"]:
                result["status"] = "known_verification_failure"
            elif (
                set(cases) == set(request["required_cases"])
                and tests["passed"] == tests["total"]
                and after.manifest["status"] == "completed"
            ):
                result["status"] = "selected_tests_passed"
        except ContractError as error:
            result["incomplete_reason"] = str(error)
            if any(
                r["kind"] in {"build", "tests"}
                and r["status"] == "failed"
                and r["usability"] == "usable"
                for d in after_documents.get("evidence", [])
                for r in d["records"]
            ):
                result["status"] = "known_verification_failure"
        if cancel is not None and cancel.is_cancelled():
            result["status"] = "canceled"
        ensure_current_materials(snapshot, workspace)
        ensure_current_materials(after, isolated)
    except BaseException as error:
        result["status"] = (
            "canceled" if isinstance(error, KeyboardInterrupt) else "incomplete"
        )
        result["incomplete_reason"] = type(error).__name__ + ": " + str(error)
        _publish_result(attempt, result)
        raise
    _publish_result(attempt, result)
    return result


def validate_result(result: dict[str, Any]) -> None:
    """Check private result shape and prevent unsubstantiated selected-test passes."""
    schema = json.loads(
        resources.files("cppulse.contracts")
        .joinpath("schemas/semantic_repair_private/result.schema.json")
        .read_bytes()
    )
    try:
        jsonschema.validate(result, schema)
        canonical_json_bytes(result)
    except (jsonschema.ValidationError, UnicodeError, RecursionError) as error:
        raise ContractError(
            "Invalid isolated proposal result: " + str(error)
        ) from error
    if result["status"] == "selected_tests_passed":
        after = result["after"]
        if not after or not after["tests"]:
            raise ContractError(
                "Selected-test pass requires fresh actual after execution"
            )
        tests = after["tests"]
        if (
            tests["total"] < 1
            or tests["passed"] != tests["total"]
            or tests["failed"]
            or tests["errors"]
            or tests["skipped"]
            or not after["cases"]
            or set(after["cases"]) != set(result["required_cases"])
            or len(after["cases"]) != tests["total"]
            or after["source_digest"] == result["before"]["source_digest"]
            or after["run_id"] == result["before"]["run_id"]
        ):
            raise ContractError(
                "Selected-test pass lacks positive fresh exact-case outcomes"
            )


def _publish_result(attempt: Path, result: dict[str, Any]) -> None:
    import os

    validate_result(result)
    temporary = attempt / ".result.json.tmp"
    target = attempt / "result.json"
    with temporary.open("xb") as stream:
        stream.write(canonical_json_bytes(result))
        stream.flush()
        os.fsync(stream.fileno())
    os.link(temporary, target, follow_symlinks=False)
    temporary.unlink()


def main(argv: list[str] | None = None) -> int:
    """Run only on an explicit trusted-project execution request."""
    import argparse
    from pathlib import Path
    import sys

    from cppulse.errors import CppulseError
    from cppulse.run_store import RunStore

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument(
        "--execute-trusted-project",
        action="store_true",
        required=True,
        help="Explicitly execute selected trusted CMake/CTest code in a new copy",
    )
    args = parser.parse_args(argv)
    try:
        with args.request.open("rb") as stream:
            content = stream.read(MAX_REQUEST_BYTES + 1)
        if len(content) > MAX_REQUEST_BYTES:
            raise ContractError("Proposal request exceeds four-MiB read bound")
        request = json.loads(content)
        validate_request(request)
        snapshot = RunStore.open_existing(args.store).open_run(
            request["before"]["run_id"],
            manifest_sha256=request["before"]["manifest_sha256"],
            max_snapshot_bytes=32 * 1024**2,
        )
        result = verify_proposal(
            snapshot,
            workspace=args.workspace,
            request=request,
            output_root=args.output_root,
        )
        print(canonical_json_bytes(result).decode())
        return {
            "selected_tests_passed": 0,
            "known_verification_failure": 3,
            "incomplete": 4,
            "canceled": 130,
        }[result["status"]]
    except KeyboardInterrupt:
        print(
            "Isolated proposal verification canceled; retained attempts remain under output root",
            file=sys.stderr,
        )
        return 130
    except (
        CppulseError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        ValueError,
        RuntimeError,
    ) as error:
        print("Isolated proposal verification rejected: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
