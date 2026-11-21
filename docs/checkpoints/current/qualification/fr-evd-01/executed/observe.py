"""Call only the ten original FR-EVD-01 assertions with authenticated inputs."""
from collections import Counter
import errno
import importlib.util
import json
import os
from pathlib import Path
import pwd
import socket
import sys
import traceback

from fixture_producers import digest, materialize, write

lane = Path(__file__).resolve().parent
out = Path(sys.argv[1])
assert Path.cwd() == out / "outside"
home = Path(pwd.getpwuid(os.getuid()).pw_dir)
assert Path.home() == home == Path("/home/agent") and not any(home.iterdir())
denial = {}
for family in (socket.AF_INET, socket.AF_INET6, socket.AF_UNIX):
    try:
        with socket.socket(family, socket.SOCK_STREAM):
            raise AssertionError(f"Unexpected socket family {family.name}")
    except OSError as error:
        assert error.errno == errno.ENETUNREACH, error
        denial[family.name] = error.errno
write(out / "child-denial.json", denial)

frozen = json.loads((lane / "lane-inputs.json").read_bytes())
assert frozen["evd03_descriptor"]
candidate_path = Path(frozen["candidate_path"])
assert digest(candidate_path) == frozen["candidate_manifest_sha256"]
candidate = json.loads(candidate_path.read_bytes())
assert candidate["wheel_sha256"] == frozen["wheel_sha256"]
assert digest(Path(candidate["console"])) == candidate["console_sha256"]
assert os.environ["CPPULSE_EVIDENCE_EXPECT_PREFIX116"] == candidate["installed"]
raw_contract = Path(frozen["original_module"])
assert digest(raw_contract) == frozen["original_module_sha256"]
spec = importlib.util.spec_from_file_location("cppulse_original_evidence116", raw_contract)
assert spec is not None and spec.loader is not None
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)
assert Path(original.__file__).resolve() == raw_contract
original.installed_origin_when_requested.__wrapped__()

import cppulse
from cppulse.coverage import normalize_imported_coverage
from cppulse.workflows import read_documents
from scripts import demo_coverage

assert Path(cppulse.__file__).resolve() == Path(candidate["installed"]) / "cppulse/__init__.py"
assert Path(demo_coverage.__file__).resolve() == Path(frozen["coverage_roles_module"])
assert digest(Path(demo_coverage.__file__)) == frozen["coverage_roles_module_sha256"]

plans = json.loads((lane / "plans.json").read_bytes())["junit"]
fresh = materialize(lane, out / "produced", plans)
assert set(frozen["junit"]) == {"clean", "fail", "skip", "zero"} and set(fresh) == {"disabled", "pytest"}
junit = []
for mode, plan in plans.items():
    supplied = fresh[mode] if mode in fresh else frozen["junit"][mode]
    row = {**plan, **supplied, "mode": mode}
    assert digest(Path(row["path"])) == row["sha256"]
    if mode in frozen["junit"]:
        parent = original.original(row)
        assert parent.read_bytes(row["artifact_id"]) == Path(row["path"]).read_bytes()
        documents = read_documents(parent)
        fact, = [item for item in documents["execution_facts"] if any(
            artifact["artifact_id"] == row["artifact_id"]
            for artifact in item["binding"]["output_artifacts"])]
        assert fact["receipt"]["exit_code"] == plan["native_exit"]
        assert fact["receipt"]["tests"] == plan["counts"]
        row["context_id"] = fact["receipt"]["context_id"]
        version, = [item for item in documents["execution_facts"] if
                    Path(item["receipt"]["argv"][0]).name == "ctest" and item["receipt"]["argv"][1:] == ["--version"]]
        assert version["receipt"]["exit_code"] == 0
        assert parent.read_bytes(version["binding"]["log_artifacts"]["stdout"]).splitlines()[0] == b"ctest version 3.31.6"
    junit.append(row)
inputs = {"console": candidate["console"], "header": frozen["header"], "coverage": frozen["coverage"], "junit": junit}
write(out / "actual-inputs.json", inputs)


def junit_result(target, mode):
    original.test_genuine_ctest_and_generic_junit_counts_are_not_process_success(inputs, target, mode)
    row, = [item for item in junit if item["mode"] == mode]
    parsed = json.loads((target / "genuine-junit-result.json").read_bytes())["report"]
    assert parsed["report_sha256"] == row["sha256"]
    assert parsed["size_bytes"] == Path(row["path"]).stat().st_size
    assert parsed["producer"] == row["producer"]
    assert {case["name"]: case["status"] for case in parsed["cases"]} == row["cases"]
    assert len({case["identity"] for case in parsed["cases"]}) == parsed["counts"]["total"]
    outcomes = Counter(case["status"] for case in parsed["cases"])
    assert {key: outcomes[key] for key in ("passed", "failed", "skipped")} == {
        key: row["counts"][key] for key in ("passed", "failed", "skipped")}
    if mode in {"fail", "skip"}:
        parent = original.original(row)
        selected = {"report_artifact_id": row["artifact_id"], "context_id": row["context_id"],
                    "scope_files": [], "adapter": row["adapter"], "producer": row["producer"]}
        child_store = target / "import-store"
        child = original.persist_test_import(parent, workspace=row["workspace"], store=child_store, **selected)
        record, = [record for fact in read_documents(child)["evidence"] for record in fact["records"] if record["origin"] == "import"]
        assert record["receipt_id"] is None and record["context_id"] == row["context_id"]
        assert record["test_counts"] == row["counts"] and record["test_cases"] == parsed["cases"]
        assert record["status"] == parsed["status"]
        report_out = target / "import-report"
        report_out.mkdir()
        view = original.public_reports(inputs, child, child_store, report_out)
        assert any(record in json.loads(wrapped["raw_json"])["records"] for wrapped in view["facts"]
                   if wrapped["kind"] == "evidence")
        write(target / "imported-nonpassing.json", {
            "run_id": child.run_id, "manifest_sha256": child.manifest_sha256, "record": record})


def coverage_result(target, adapter):
    original.test_genuine_coverage_methods_denominators_context_and_public_output(inputs, target, adapter)
    row = inputs["coverage"]
    parent = original.original(row)
    selected = demo_coverage.roles(parent, adapter)
    report_id = selected["report_artifact_id"]
    raw = row["report_artifacts"][adapter]
    assert report_id == raw["artifact_id"]
    import_fact = normalize_imported_coverage(
        parent, report_artifact_id=report_id, adapter=adapter, context_id="gcc-coverage-job",
        source_root=row["workspace"])
    observed = json.loads((target / "genuine-coverage-result.json").read_bytes())["fact"]
    assert observed["context_id"] == import_fact["context_id"] == "gcc-coverage-job"
    assert observed["origin"] == "execution" and import_fact["origin"] == "import"
    assert import_fact["receipt_id"] is None and not import_fact["proof_receipt_ids"] and not import_fact["test_evidence_ids"]
    assert not import_fact["instrumentation"] and not import_fact["profiles"]
    observed_file, = observed["files"]
    imported_file, = import_fact["files"]
    assert imported_file["source_sha256"] is None and observed_file["source_sha256"]
    assert observed_file["file"] == imported_file["file"] == "main.cpp"
    def fields(file):
        return {m["kind"]: [m["method"], m["covered"], m["total"]] for m in file["measurements"]}
    expected = {
        "line": ["lcov-da-v1" if adapter == "lcov" else "cobertura-lines-v1", 5, 8],
        "branch": ["lcov-brda-v1" if adapter == "lcov" else "cobertura-condition-counts-v1", 1, 2],
    }
    if adapter == "lcov":
        expected["function"] = ["lcov-fnda-v1", 2, 3]
    assert fields(observed_file) == fields(imported_file) == expected
    write(target / "imported-coverage-readback.json", import_fact)


results = []
operations = [(f"junit-{mode}", junit_result, mode) for mode in plans]
operations += [(f"test-import-{adapter}", lambda target, name:
                original.test_public_test_import_keeps_context_and_import_origin(inputs, target, name), adapter)
               for adapter in ("ctest-junit", "generic-junit")]
operations += [(f"coverage-{adapter}", coverage_result, adapter) for adapter in ("lcov", "cobertura")]
for case, operation, argument in operations:
    target = out / case
    target.mkdir()
    try:
        operation(target, argument)
    except Exception as error:
        results.append({"case": case, "passed": False, "error": repr(error)})
        traceback.print_exc()
    else:
        results.append({"case": case, "passed": True})
    print(case, "pass" if results[-1]["passed"] else "fail", flush=True)
assert not any(home.iterdir())
write(out / "observer-summary.json", {
    "scope": "Ten direct unchanged original FR-EVD-01 assertions with genuine registered inputs and supplemental readback",
    "source_module_sha256": frozen["original_module_sha256"],
    "wheel_sha256": candidate["wheel_sha256"], "installed_origin": cppulse.__file__,
    "results": results, "pytest_module_run": False, "sanitizer_fixture_reconstructed": False,
})
assert len(results) == 10 and all(row["passed"] for row in results), results
