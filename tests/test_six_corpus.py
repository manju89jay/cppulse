"""Pin and scope checks for original-corpus execution, without network downloads."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from scripts.run_six_corpus import validate_lock

ROOT = Path(__file__).resolve().parents[1]


def lock():
    return json.loads((ROOT / "demo/six-corpus-lock.json").read_text())


def test_original_six_are_present_with_immutable_pins():
    validate_lock(lock())


@pytest.mark.parametrize(
    "mutation", ["missing", "substitution", "moving_pin", "duplicate", "history"]
)
def test_missing_substituted_unpinned_or_historyless_sources_rejected(mutation):
    value = deepcopy(lock())
    if mutation == "missing":
        value["projects"].pop()
    elif mutation == "substitution":
        value["projects"][0]["id"] = "utfcpp"
    elif mutation == "moving_pin":
        value["projects"][0]["revision"] = "HEAD"
    elif mutation == "duplicate":
        value["projects"].append(value["projects"][0])
    else:
        value["methodology"]["history_depth"] = 1
    with pytest.raises(ValueError):
        validate_lock(value)


def test_real_history_cleanliness_and_revision_are_rechecked(tmp_path):
    import subprocess
    from scripts.run_six_corpus import check_source

    source = tmp_path / "source"
    source.mkdir()

    def run(*args):
        return subprocess.check_output(
            ["git", "-C", str(source), *args], text=True
        ).strip()

    run("init", "-q")
    run("config", "user.name", "Local corpus test fixture")
    run("config", "user.email", "corpus-fixture@example.invalid")
    (source / "a.cpp").write_text("int value() { return 1; }\n")
    run("add", "a.cpp")
    run("commit", "-qm", "Local fixture only")
    revision = run("rev-parse", "HEAD")
    with pytest.raises(RuntimeError, match="Insufficient retained real history"):
        check_source(source, revision, 100)
    assert check_source(source, revision, 1)["retained_commits"] == 1
    with pytest.raises(RuntimeError, match="Unexpected revision"):
        check_source(source, "0" * 40, 1)
    (source / "untracked.cpp").write_text("int untracked;")
    with pytest.raises(RuntimeError, match="Dirty original corpus source"):
        check_source(source, revision, 1)


def test_native_report_gate_rejects_source_hash_drift_and_scope_mismatch(tmp_path):
    import hashlib
    from scripts.run_six_corpus import verify_report
    from tests.test_maintenance_metrics_contract import native_metric_report

    source = tmp_path / "source"
    source.mkdir()
    content = b"int a() { return 1; }\n"
    (source / "a.cpp").write_bytes(content)
    report = native_metric_report()
    report["metadata"]["repo_path"] = str(source)
    report["metadata"]["analysis"]["files"][0]["path"] = str(source / "a.cpp")
    file = report["metadata"]["analysis"]["native_metrics"]["files"][0]
    file["path"] = str(source / "a.cpp")
    file["source_content_sha256"] = hashlib.sha256(content).hexdigest()
    assert (
        verify_report(report, source, ["a.cpp"])["schema_and_semantic_checks"]
        == "passed"
    )
    with pytest.raises(RuntimeError, match="finite declared source selection"):
        verify_report(report, source, ["a.cpp", "missing.cpp"])
    (source / "a.cpp").write_text("int modified;\n")
    with pytest.raises(RuntimeError, match="hash differs"):
        verify_report(report, source, ["a.cpp"])


def test_driver_budget_is_observed_in_an_isolated_process():
    import subprocess
    import sys

    if sys.platform != "linux":
        pytest.skip("This evidence runner explicitly qualifies Linux limits only")
    output = subprocess.check_output(
        [
            sys.executable,
            "-c",
            "import json; from scripts.run_six_corpus import apply_driver_limit; "
            "print(json.dumps(apply_driver_limit(1024**3)))",
        ],
        text=True,
        cwd=ROOT,
    )
    assert json.loads(output)["driver_address_space_bytes"] == 1024**3


def test_unusable_driver_budget_fails_before_changing_process_limits():
    import subprocess
    import sys

    if sys.platform != "linux":
        pytest.skip("This evidence runner explicitly qualifies Linux limits only")
    code = """from scripts.run_six_corpus import apply_driver_limit
import resource
before = resource.getrlimit(resource.RLIMIT_AS)
try:
    apply_driver_limit(1)
except ValueError as error:
    assert 'initial mappings' in str(error)
else:
    raise AssertionError('Unusable budget was accepted')
assert resource.getrlimit(resource.RLIMIT_AS) == before
"""
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT)
