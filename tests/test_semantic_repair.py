"""Proposal contracts fail closed before execution of any selected project."""

from copy import deepcopy
from pathlib import Path

import pytest

from cppulse.errors import ContractError
from cppulse.semantic_repair import validate_request


def request():
    return {
        "version": "0.1.0",
        "profile": "cpp17-cmake-ctest-v1",
        "before": {
            "run_id": "before",
            "manifest_sha256": "a" * 64,
            "source_digest": "b" * 64,
            "test_evidence_id": "tests",
        },
        "source_files": ["src/clamp.cpp", "tests/clamp.cpp", "CMakeLists.txt"],
        "editable_files": ["src/clamp.cpp"],
        "protected_files": ["tests/clamp.cpp", "CMakeLists.txt"],
        "required_cases": ["lower", "inside", "upper"],
        "adequacy": [
            "Boundary cases selected; unrestricted equivalence is not established."
        ],
        "origin": {
            "kind": "synthetic_fixture",
            "description": "Labeled test proposal",
            "evidence_sha256": "c" * 64,
        },
        "replacements": [
            {
                "path": "src/clamp.cpp",
                "before_sha256": "d" * 64,
                "after": "int clamp(int v,int lo,int hi){return v<lo?lo:v>hi?hi:v;}\n",
            }
        ],
    }


def test_contract_is_pure_and_preserves_explicit_limits():
    original = request()
    frozen = deepcopy(original)
    validate_request(original)
    assert original == frozen


@pytest.mark.parametrize(
    "path",
    [
        "../main.cpp",
        "/main.cpp",
        "a/../main.cpp",
        "./main.cpp",
        "C:/main.cpp",
        "a\\b.cpp",
        "a\x00.cpp",
        ".git/a.cpp",
    ],
)
def test_unsafe_paths_fail_before_any_execution(path):
    proposal = request()
    proposal["replacements"][0]["path"] = path
    with pytest.raises(ContractError):
        validate_request(proposal)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p.update(extra="unknown"),
        lambda p: p["source_files"].append(p["source_files"][0]),
        lambda p: p["editable_files"].append("CMakeLists.txt"),
        lambda p: p["replacements"][0].update(path="tests/clamp.cpp"),
        lambda p: p["replacements"][0].update(path="not-listed.cpp"),
        lambda p: p["replacements"].append(deepcopy(p["replacements"][0])),
        lambda p: p.update(required_cases=[]),
        lambda p: p.update(adequacy=[]),
        lambda p: p["origin"].update(kind="agent"),
        lambda p: p["before"].update(manifest_sha256="bad"),
        lambda p: p["replacements"][0].update(after="\ud800"),
        lambda p: p["replacements"][0].update(after="x" * (1024**2 + 1)),
    ],
)
def test_unsupported_or_ambiguous_requests_fail(mutation):
    proposal = request()
    mutation(proposal)
    with pytest.raises(ContractError):
        validate_request(proposal)


def failing_project(tmp_path, *, mode="failed", test_timeout=30):
    from test_collection import ctest_fixture
    from cppulse.collection import collect
    from cppulse.identities import snapshot_inputs

    plan, _, contexts = ctest_fixture(tmp_path, fail_test=True)
    (tmp_path / "main.cpp").write_text(
        "int observed(){return " + ("0" if mode == "passed" else "1") + ";}\n"
    )
    (tmp_path / "tests.cpp").write_text(
        "int observed(); int main(){return observed()==0?0:1;}\n"
    )
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\nproject(proposal LANGUAGES CXX)\n"
        "add_executable(app main.cpp tests.cpp)\nenable_testing()\n"
        "add_test(NAME actual-case COMMAND app)\n"
    )
    if mode == "zero":
        (tmp_path / "CMakeLists.txt").write_text(
            (tmp_path / "CMakeLists.txt")
            .read_text()
            .replace("add_test(NAME actual-case COMMAND app)\n", "")
        )
    elif mode == "skipped":
        with (tmp_path / "CMakeLists.txt").open("a") as stream:
            stream.write("set_tests_properties(actual-case PROPERTIES DISABLED TRUE)\n")
    plan["recipe"]["steps"][-1]["timeout_seconds"] = test_timeout
    plan["recipe"]["steps"][0]["argv"] += [
        "-DCMAKE_CXX_STANDARD=17",
        "-DCMAKE_CXX_STANDARD_REQUIRED=ON",
        "-DCMAKE_CXX_EXTENSIONS=OFF",
    ]
    plan["recipe"]["steps"][1]["inputs"].append("tests.cpp")
    source = snapshot_inputs(
        tmp_path, ["main.cpp", "tests.cpp", "CMakeLists.txt"], inventory_complete=True
    )
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    proposal = request()
    proposal["before"] = {
        "run_id": snapshot.run_id,
        "manifest_sha256": snapshot.manifest_sha256,
        "source_digest": source["digest"],
        "test_evidence_id": "native-tests",
    }
    proposal["source_files"] = ["main.cpp", "tests.cpp", "CMakeLists.txt"]
    proposal["editable_files"] = ["main.cpp"]
    proposal["protected_files"] = ["tests.cpp", "CMakeLists.txt"]
    proposal["required_cases"] = ["actual-case"]
    import hashlib

    proposal["replacements"] = [
        {
            "path": "main.cpp",
            "before_sha256": hashlib.sha256(
                (tmp_path / "main.cpp").read_bytes()
            ).hexdigest(),
            "after": "int observed(){return 0;}\n",
        }
    ]
    return snapshot, proposal


def test_before_preparation_requires_actual_failure_and_pins(tmp_path):
    from cppulse.semantic_repair import prepare_proposal

    snapshot, proposal = failing_project(tmp_path)
    prepared = prepare_proposal(snapshot, workspace=tmp_path, request=proposal)
    assert prepared.before_tests["failed"] == 1
    assert prepared.source["main.cpp"] == b"int observed(){return 1;}\n"
    assert prepared.source["tests.cpp"] == (tmp_path / "tests.cpp").read_bytes()
    assert (tmp_path / "main.cpp").read_text() == "int observed(){return 1;}\n"
    proposal["replacements"][0]["before_sha256"] = "0" * 64
    with pytest.raises(ContractError):
        prepare_proposal(snapshot, workspace=tmp_path, request=proposal)


def test_wrong_required_case_is_not_a_valid_before(tmp_path):
    from cppulse.semantic_repair import prepare_proposal

    snapshot, proposal = failing_project(tmp_path)
    proposal["required_cases"] = ["missing-case"]
    with pytest.raises(ContractError):
        prepare_proposal(snapshot, workspace=tmp_path, request=proposal)


def test_explicit_isolated_execution_retains_fresh_receipts_and_original(tmp_path):
    from cppulse.semantic_repair import verify_proposal

    source = tmp_path / "original"
    source.mkdir()
    snapshot, proposal = failing_project(source)
    output = tmp_path / "attempts"
    output.mkdir()
    result = verify_proposal(
        snapshot, workspace=source, request=proposal, output_root=output
    )
    assert result["status"] == "selected_tests_passed"
    assert result["semantic_equivalence"] == "not_established"
    assert result["before"]["tests"]["failed"] == 1
    assert result["after"]["tests"]["passed"] == 1
    assert result["after"]["source_digest"] != proposal["before"]["source_digest"]
    assert result["after"]["run_id"] != snapshot.run_id
    assert (source / "main.cpp").read_bytes() == b"int observed(){return 1;}\n"
    assert (source / "tests.cpp").read_bytes() == (
        Path(result["attempt_directory"]) / "source/tests.cpp"
    ).read_bytes()
    assert (Path(result["attempt_directory"]) / "result.json").is_file()


def test_bad_compiling_behavior_is_retained_failure(tmp_path):
    from cppulse.semantic_repair import verify_proposal

    source = tmp_path / "original"
    source.mkdir()
    snapshot, proposal = failing_project(source)
    proposal["replacements"][0]["after"] = "int observed(){return 2;}\n"
    output = tmp_path / "attempts"
    output.mkdir()
    result = verify_proposal(
        snapshot, workspace=source, request=proposal, output_root=output
    )
    assert result["status"] == "known_verification_failure"
    assert result["after"]["tests"]["failed"] == 1


def test_original_or_store_output_is_never_allowed(tmp_path):
    from cppulse.semantic_repair import verify_proposal

    snapshot, proposal = failing_project(tmp_path)
    for output in [tmp_path, tmp_path / "store"]:
        with pytest.raises(ContractError):
            verify_proposal(
                snapshot, workspace=tmp_path, request=proposal, output_root=output
            )


def test_compiler_failure_and_fresh_retry_have_distinct_receipts(tmp_path):
    from cppulse.semantic_repair import verify_proposal

    source = tmp_path / "original"
    source.mkdir()
    snapshot, proposal = failing_project(source)
    output = tmp_path / "attempts"
    output.mkdir()
    invalid = deepcopy(proposal)
    invalid["replacements"][0]["after"] = "invalid C++ source\n"
    failed = verify_proposal(
        snapshot, workspace=source, request=invalid, output_root=output
    )
    assert failed["status"] == "known_verification_failure"
    passed = verify_proposal(
        snapshot, workspace=source, request=proposal, output_root=output
    )
    assert passed["status"] == "selected_tests_passed"
    assert passed["after"]["run_id"] != failed["after"]["run_id"]
    assert passed["attempt_directory"] != failed["attempt_directory"]


def test_pre_cancellation_retains_partial_attempt_and_fresh_retry(tmp_path):
    from cppulse.execution import CancellationToken
    from cppulse.semantic_repair import verify_proposal

    source = tmp_path / "original"
    source.mkdir()
    snapshot, proposal = failing_project(source)
    output = tmp_path / "attempts"
    output.mkdir()
    token = CancellationToken()
    token.cancel()
    canceled = verify_proposal(
        snapshot, workspace=source, request=proposal, output_root=output, cancel=token
    )
    assert canceled["status"] == "canceled"
    assert canceled["after"]["tests"] is None
    passed = verify_proposal(
        snapshot, workspace=source, request=proposal, output_root=output
    )
    assert passed["status"] == "selected_tests_passed"
    assert passed["after"]["run_id"] != canceled["after"]["run_id"]


def test_explicit_module_cli_requires_execution_flag(tmp_path):
    from cppulse.semantic_repair import main

    with pytest.raises(SystemExit) as error:
        main(
            [
                "--store",
                str(tmp_path),
                "--workspace",
                str(tmp_path),
                "--request",
                str(tmp_path / "request.json"),
                "--output-root",
                str(tmp_path),
            ]
        )
    assert error.value.code == 2


def test_worker_exception_preserves_attempt_and_explicit_retry(tmp_path, monkeypatch):
    import json
    import cppulse.collection
    from cppulse.semantic_repair import verify_proposal

    source = tmp_path / "original"
    source.mkdir()
    snapshot, proposal = failing_project(source)
    output = tmp_path / "attempts"
    output.mkdir()
    original = cppulse.collection.collect

    def crash(*args, **kwargs):
        raise RuntimeError("injected worker interruption")

    monkeypatch.setattr(cppulse.collection, "collect", crash)
    with pytest.raises(RuntimeError, match="worker interruption"):
        verify_proposal(
            snapshot, workspace=source, request=proposal, output_root=output
        )
    attempts = list(output.iterdir())
    assert len(attempts) == 1
    report = json.loads((attempts[0] / "result.json").read_text())
    assert report["status"] == "incomplete"
    assert report["after"] is None
    assert (attempts[0] / "proposal.diff").is_file()
    monkeypatch.setattr(cppulse.collection, "collect", original)
    passed = verify_proposal(
        snapshot, workspace=source, request=proposal, output_root=output
    )
    assert passed["status"] == "selected_tests_passed"
    assert Path(passed["attempt_directory"]) != attempts[0]


def test_stale_and_symlink_source_rejected_before_staging(tmp_path):
    from cppulse.semantic_repair import verify_proposal
    from cppulse.errors import InputChanged

    source = tmp_path / "original"
    source.mkdir()
    snapshot, proposal = failing_project(source)
    output = tmp_path / "attempts"
    output.mkdir()
    current = (source / "main.cpp").read_bytes()
    (source / "main.cpp").write_text("int observed(){return 99;}\n")
    with pytest.raises(InputChanged):
        verify_proposal(
            snapshot, workspace=source, request=proposal, output_root=output
        )
    assert list(output.iterdir()) == []
    outside = tmp_path / "other.cpp"
    outside.write_bytes(current)
    (source / "main.cpp").unlink()
    (source / "main.cpp").symlink_to(outside)
    with pytest.raises(InputChanged):
        verify_proposal(
            snapshot, workspace=source, request=proposal, output_root=output
        )
    assert list(output.iterdir()) == []


def test_actual_crashing_proposal_cannot_pass(tmp_path):
    from cppulse.semantic_repair import verify_proposal

    source = tmp_path / "original"
    source.mkdir()
    snapshot, proposal = failing_project(source)
    proposal["replacements"][0]["after"] = "int observed(){__builtin_trap();}\n"
    output = tmp_path / "attempts"
    output.mkdir()
    result = verify_proposal(
        snapshot, workspace=source, request=proposal, output_root=output
    )
    assert result["status"] == "known_verification_failure"
    assert result["semantic_equivalence"] == "not_established"


def test_result_validator_rejects_missing_or_zero_fresh_cases(tmp_path):
    from cppulse.semantic_repair import verify_proposal, validate_result

    source = tmp_path / "original"
    source.mkdir()
    snapshot, proposal = failing_project(source)
    output = tmp_path / "attempts"
    output.mkdir()
    result = verify_proposal(
        snapshot, workspace=source, request=proposal, output_root=output
    )
    for mutation in [
        lambda r: r.update(after=None),
        lambda r: r["after"].update(cases=[]),
        lambda r: r["after"]["tests"].update(total=0, passed=0),
        lambda r: r["after"].update(run_id=r["before"]["run_id"]),
        lambda r: r["after"].update(source_digest=r["before"]["source_digest"]),
        lambda r: r.update(semantic_equivalence="proven"),
    ]:
        tampered = deepcopy(result)
        mutation(tampered)
        with pytest.raises(ContractError):
            validate_result(tampered)


def test_raw_report_cannot_inherit_mismatched_normalized_counts(tmp_path):
    from cppulse.semantic_repair import _test_outcomes
    from cppulse.workflows import read_documents

    snapshot, _ = failing_project(tmp_path)
    docs = read_documents(snapshot)
    facts = next(f for f in docs["execution_facts"] if f["receipt"]["id"] == "tests")
    facts["receipt"]["tests"].update(passed=1, failed=0)
    # This assertion deliberately isolates the raw-vs-normalized boundary; no
    # forged document is persisted or relabeled as actual producer evidence.
    with pytest.raises(ContractError, match="raw report"):
        _test_outcomes(snapshot, docs, "native-tests")


@pytest.mark.parametrize("mode", ["passed", "zero", "skipped"])
def test_actual_before_without_required_failed_executed_cases_rejected(tmp_path, mode):
    from cppulse.semantic_repair import prepare_proposal

    snapshot, proposal = failing_project(tmp_path, mode=mode)
    with pytest.raises(ContractError):
        prepare_proposal(snapshot, workspace=tmp_path, request=proposal)


def test_actual_wall_timeout_remains_incomplete_and_retained(tmp_path):
    from cppulse.semantic_repair import verify_proposal
    from cppulse.run_store import RunStore
    from cppulse.workflows import read_documents

    source = tmp_path / "original"
    source.mkdir()
    snapshot, proposal = failing_project(source, test_timeout=1)
    proposal["replacements"][0]["after"] = "int observed(){for(;;){}}\n"
    output = tmp_path / "attempts"
    output.mkdir()
    result = verify_proposal(
        snapshot, workspace=source, request=proposal, output_root=output
    )
    assert result["status"] == "incomplete"
    after = result["after"]
    retained = RunStore.open_existing(Path(after["store"])).open_run(
        after["run_id"], manifest_sha256=after["manifest_sha256"]
    )
    receipt = next(
        r for r in read_documents(retained)["execution_receipt"] if r["id"] == "tests"
    )
    assert receipt["status"] == "timed_out"
    assert (Path(result["attempt_directory"]) / "result.json").is_file()
