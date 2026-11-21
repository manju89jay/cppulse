"""Run three finite groups of original installed criterion predicates."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import pwd
import sys
import shutil
import subprocess
from types import ModuleType
import xml.etree.ElementTree as ET

import pytest


test_root = Path("/workspace/work/governance-qualification/checkout/tests")
package = Path("/workspace/work/git-scope-qualification/gates/candidate/installed")
group, output_arg = sys.argv[1:]
output = Path(output_arg)
policy_public = (
    "test_public_hand_calculation_four_outcomes_and_blocking_precedence",
    "test_public_declared_deviations_never_rewrite_raw_scores_or_unknowns",
    "test_public_contracts_reject_invalid_pack_and_actual_reference_claims",
)
git_cache_methods = (
    "test_cold_warm_and_append_reuse_one_checked_stream_with_clean_equality",
    "test_pipeline_shared_scan_is_not_repeated_by_silo_szz_or_metadata",
    "test_bounds_are_explicit_and_expanding_scope_matches_clean",
    "test_raw_byte_cap_is_incomplete_and_is_never_a_warm_positive_hit",
    "test_interrupted_accepted_records_resume_but_pending_does_not_pass",
)
groups = {
    "policy": [
        ("test_policy_gate_properties.py", (), 256),
        ("test_policy_public115.py", policy_public, 16),
        ("test_policy.py", (
            "test_evaluation_performs_no_project_io_process_network_or_environment_reads",
            "test_generated_time_must_be_explicit_utc",
            "test_mixed_raw_weights_and_exact_bounds_decide_gate_without_rounding",
            "test_score_display_rounding_cannot_raise_exact_readiness_to_threshold",
            "test_empty_selected_scope_cannot_pass_or_import_an_out_of_scope_failure",
            "test_missing_policy_permission_and_incomplete_failure_cannot_be_waived",
            "test_aggregate_control_requires_exact_all_context_approval",
            "test_unknown_control_cannot_be_excepted_and_threshold_gate_requests_are_rejected",
        ), 11),
    ],
    "git-cache": [("test_git_history_cache.py", git_cache_methods, 5)],
    "szz": [
        ("test_szz_cutoff_history79.py", (), 17),
        ("test_szz_public_cutoff79.py", (), 6),
    ],
}
selection = groups[group]
expected_counts = Counter({name: count for name, _, count in selection})
methods = {name: set(names) for name, names, _ in selection}
selectors = []
for name, selected, _ in selection:
    path = test_root / name
    selectors.extend(f"{path}::{method}" for method in selected)
    if not selected:
        selectors.append(str(path))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name, record):
    with (output / name).open("x", encoding="utf8") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")


def origins():
    result = {}
    for name, module in sorted(sys.modules.items()):
        if name == "cppulse" or name.startswith("cppulse."):
            path = Path(module.__file__).resolve()
            assert path.is_relative_to(package), (name, path)
            result[name] = {"file": str(path), "sha256": sha(path)}
    assert "cppulse" in result
    return result


class VerifySelection:
    def pytest_collection_finish(self, session):
        counts = Counter(Path(item.path).name for item in session.items)
        assert counts == expected_counts, counts
        actual = {}
        for item in session.items:
            path = Path(item.path).resolve()
            assert path == test_root / path.name
            allowed = methods[path.name]
            if allowed:
                assert item.name.split("[", 1)[0] in allowed, item.nodeid
            assert item.nodeid not in actual
            actual[item.nodeid] = sha(path)
        self.case_ids = actual
        write("selected-cases.json", actual)


home = Path(pwd.getpwuid(os.getuid()).pw_dir)
assert home == Path(os.environ["HOME"]) == Path("/home/agent") and not any(home.iterdir())
assert Path.cwd() == output / "outside"
git = Path(shutil.which("git")).resolve()
assert git == Path("/usr/bin/git")
assert sha(git) == "356db14e102d68a1a37d8a1ac577dfd678d45d46e92f468bef8b7154e7bfdc60"
write("provider.json", {"git": str(git), "sha256": sha(git),
                       "version": subprocess.check_output([git, "--version"], text=True).strip()})
if group == "szz":
    assert "tests" not in sys.modules
    namespace = ModuleType("tests")
    namespace.__path__ = [str(test_root)]
    sys.modules["tests"] = namespace
import cppulse
initial = origins()
plugin = VerifySelection()
xml = output / "results.xml"
status = pytest.main([
    "-q", "--import-mode=importlib", "-c", "/dev/null", f"--rootdir={test_root.parent}",
    f"--confcutdir={test_root}", "-p", "no:cacheprovider",
    f"--junitxml={xml}", f"--basetemp={output / 'fixtures'}", *selectors,
], plugins=[plugin])
final = origins()
rows = list(ET.parse(xml).iter("testcase"))
expected_junit = Counter(name.split("::")[-1] for name in plugin.case_ids)
actual_junit = Counter(row.attrib["name"] for row in rows)
assert expected_junit == actual_junit and len(rows) == sum(expected_counts.values())
nonpass = {row.attrib["name"]: tag for row in rows for tag in ("error", "failure", "skipped")
           if row.find(tag) is not None}
assert all(final[name] == value for name, value in initial.items())
write("receipt.json", {
    "group": group, "pytest_exit": int(status), "case_count": len(rows),
    "nonpassing": nonpass, "selectors": selectors, "junit_sha256": sha(xml),
    "initial_home_empty": True, "starting_origins": initial, "final_origins": final,
})
sys.exit(int(status) or int(bool(nonpass)))
