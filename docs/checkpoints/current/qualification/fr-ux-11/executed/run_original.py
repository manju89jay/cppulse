"""Run original extension and privacy predicates against explicitly scoped origins."""
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import xml.etree.ElementTree as ET

group, location, source_location = sys.argv[1:]
output = Path(location)
source = Path(source_location)
expected_prefix = Path(os.environ["CPPULSE_GATE_PACKAGE"])
home = Path(pwd.getpwuid(os.getuid()).pw_dir)
assert home == Path.home() == Path("/home/agent") and not list(home.iterdir())
assert Path.cwd() == output / "outside"
import cppulse
import pytest

extension = "test_extension_lifecycle110.py"
tooling = "test_tooling.py"
privacy = "test_diagnostic_privacy112.py"
compatibility = "test_installed_cli.py"
groups = {
    "extensions": {
        extension: (["ExtensionLifecycleTests"], 4),
        tooling: ([
            "test_scaffolds_are_labeled_drafts_and_do_not_register_or_execute",
            "test_scaffold_refuses_unsafe_names",
            "test_scaffold_refuses_unknown_kind_and_missing_destination",
            "test_scaffold_refuses_every_existing_target",
            "test_scaffold_refuses_symlink_destination_or_ancestor",
            "test_partial_scaffold_write_is_removed",
        ], 22),
    },
    "privacy-installed": {privacy: (["DiagnosticPrivacy112"], 3)},
    "privacy-source": {
        privacy: (["DiagnosticPrivacy112"], 3),
        compatibility: (["test_diagnostics_default_excludes_paths_environment_and_raw_errors"], 1),
    },
}
selection = groups[group]
paths = {name: source / "tests" / name for name in selection}
selectors = [f"{paths[name]}::{case}" for name, (names, _) in selection.items() for case in names]
expected = Counter({name: count for name, (_, count) in selection.items()})


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(name, report):
    with (output / name).open("x", encoding="utf8") as stream:
        json.dump(report, stream, indent=2)
        stream.write("\n")


def origins():
    result = {}
    for name, module in sorted(sys.modules.items()):
        if name == "cppulse" or name.startswith("cppulse."):
            actual = Path(module.__file__).resolve()
            assert actual.is_relative_to(expected_prefix), (name, actual, expected_prefix)
            result[name] = {"path": str(actual), "sha256": sha(actual)}
    assert "cppulse" in result
    return result


class Collection:
    def pytest_collection_finish(self, session):
        counts = Counter(Path(item.path).name for item in session.items)
        assert counts == expected, (counts, expected)
        self.nodes = {item.nodeid: sha(Path(item.path)) for item in session.items}
        assert len(self.nodes) == sum(expected.values())
        write("case-registration.json", self.nodes)


def command(argv):
    result = subprocess.run(argv, cwd=output / "outside", capture_output=True, text=True, timeout=40)
    return {"argv": argv, "exit": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def extension_cli():
    from cppulse.tooling import load_rule_registry

    before = load_rule_registry(include_native_bindings=True)
    commands = []
    for kind in ("rule", "adapter", "policy"):
        parent = output / f"console-{kind}"
        parent.mkdir()
        project = parent / "qualified-draft"
        argv = [sys.executable, "-B", "-m", "cppulse", "scaffold", kind, project.name, "--destination", str(parent)]
        commands.append(positive := command(argv))
        assert positive["exit"] == 0 and json.loads(positive["stdout"]) == {"scaffold": str(project), "registered": False}
        before_files = {str(path.relative_to(project)): sha(path) for path in project.rglob("*") if path.is_file()}
        assert before_files and "incomplete scaffold" in (project / "README.md").read_text()
        commands.append(duplicate := command(argv))
        assert duplicate["exit"] == 2 and duplicate["stdout"] == ""
        assert before_files == {str(path.relative_to(project)): sha(path) for path in project.rglob("*") if path.is_file()}
    assert load_rule_registry(include_native_bindings=True) == before
    return commands


def privacy_cli():
    destination = output / "unexpected-upload.zip"
    argv = [sys.executable, "-B", "-m", "cppulse", "diagnostics", "--upload", "--output", str(destination)]
    result = command(argv)
    assert result["exit"] == 2 and "unrecognized arguments: --upload" in result["stderr"]
    assert not result["stdout"] and not destination.exists()
    return [result]


before = origins()
initial_files = {str(path): sha(path) for path in paths.values()}
plugin = Collection()
junit = output / "results.xml"
status = pytest.main([
    "-q", "--import-mode=importlib", "-c", "/dev/null", f"--rootdir={source}",
    f"--confcutdir={source / 'tests'}", "-p", "no:cacheprovider",
    f"--junitxml={junit}", f"--basetemp={output / 'pytest'}", *selectors,
], plugins=[plugin])
assert initial_files == {str(path): sha(path) for path in paths.values()}
after = origins()
assert all(before[name] == after[name] for name in before)
cases = list(ET.parse(junit).iter("testcase"))
assert Counter(row.attrib["name"] for row in cases) == Counter(node.split("::")[-1] for node in plugin.nodes)
nonpassing = [(row.attrib["name"], kind) for row in cases for kind in ("failure", "error", "skipped")
              if row.find(kind) is not None]
receipt = {
    "group": group, "pytest_exit": int(status), "cases": len(cases), "nonpassing": nonpassing,
    "case_sources": initial_files, "junit_sha256": sha(junit), "origins": after,
    "initial_account_home": str(home), "initial_account_home_empty": True,
}
write("test-readback.json", receipt)
assert status == 0 and not nonpassing
if group == "extensions":
    write("public-controls.json", extension_cli())
elif group == "privacy-installed":
    write("public-controls.json", privacy_cli())
    bundles = sorted((output / "privacy-fixtures").glob("*/*.zip"))
    assert [p.name for p in sorted(bundles, key=lambda p: p.name)] == [
        "discovery-default.zip", "function-default.zip", "optional-metadata-default.zip",
    ]
    write("default-zips.json", {str(p.relative_to(output)): sha(p) for p in bundles})
