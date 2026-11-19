"""Execute shared generated checks and resolve actual GitHub facade commands.

These source-tool regressions qualify command agreement and failure handling,
not a GitHub execution or full production/installed-artifact acceptance.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import sys
from types import ModuleType

import cppulse
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
GENERATED = {
    "analyzer-core/src/generated_rule_types.h",
    "analyzer-core/src/generated_rule_registration.h",
    "docs/generated/rules.md",
    "docs/generated/native-config.schema.json",
    "docs/generated/native-config.example.json",
    "docs/generated/development.md",
}


def _module(name: str, relative: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _tree(root: Path) -> dict[str, tuple[object, ...]]:
    """Observe bytes and non-atime metadata, including unexpected directories."""
    result = {}
    for path in [root, *sorted(root.rglob("*"))]:
        info = path.lstat()
        result[path.relative_to(root).as_posix()] = (
            info.st_mode,
            info.st_size,
            info.st_mtime_ns,
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
        )
    return result


def test_github_generated_commands_use_the_real_shared_facade_plan(
    tmp_path: Path,
) -> None:
    dev = _module("shared_generator_ci110_dev", "tools/dev.py")
    runner = _module("shared_generator_ci110_runner", "scripts/check_local.py")
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    shared_jobs = set()
    generated_plans = []
    for job_name, job in workflow["jobs"].items():
        for step in job["steps"]:
            argv = shlex.split(step.get("run", ""))
            if len(argv) < 3 or argv[1:3] != ["tools/dev.py", "verify"]:
                continue
            # Parse the actual workflow arguments with the same parser users run;
            # only plan selected checks, never execute native/component jobs.
            args = dev._parser().parse_args(argv[2:])
            assert args.scope == "changed"
            shared_jobs.add(job_name)
            if "generated" not in (args.section or []):
                continue
            planned = dev.source_checks(args, tmp_path / "facade-plan")
            selected = [check for check in planned if check.section == "generated"]
            direct = runner.build_checks(
                ROOT, {"generated"}, tmp_path / "facade-plan", python=args.python
            )
            assert [(check.name, check.argv, check.cwd) for check in selected] == [
                (check.name, check.argv, check.cwd) for check in direct
            ]
            assert [(check.name, check.argv) for check in selected] == [
                ("delivery-ledger", (args.python, "scripts/verify_delivery.py")),
                ("generated-check", (args.python, "scripts/check_generated.py")),
            ]
            assert all("--require-complete" not in check.argv for check in selected)
            generated_plans.append([list(check.argv) for check in selected])
    assert shared_jobs == set(workflow["jobs"])
    assert generated_plans


def test_actual_shared_generated_section_and_explicit_write_preserve_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = _module("shared_generator_ci110_execute", "scripts/check_local.py")
    checkout = tmp_path / "isolated checkout; literal"
    scripts = checkout / "scripts"
    scripts.mkdir(parents=True)
    for name in ("check_generated.py", "verify_delivery.py"):
        shutil.copyfile(ROOT / "scripts" / name, scripts / name)
        assert (scripts / name).read_bytes() == (ROOT / "scripts" / name).read_bytes()
    protected = checkout / "README.keep"
    protected.write_bytes(b"Explicit generated writes must preserve unrelated input.\n")
    selected_package = str(Path(cppulse.__file__).resolve().parent.parent)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["PYTHONPATH"] = selected_package + (
        os.pathsep + environment["PYTHONPATH"] if environment.get("PYTHONPATH") else ""
    )
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("PYTHONPATH", environment["PYTHONPATH"])
    monkeypatch.setattr(runner, "ROOT", checkout)
    logs = tmp_path / "actual-results"
    before = _tree(checkout)

    # No manufactured passing ledger: the unchanged verifier must reject this
    # deliberately incomplete isolated source tree, and the shared runner must
    # retain that failure while also running the genuine missing-output check.
    assert runner.main(["--section", "generated", "--output-dir", str(logs)]) == 1
    document = json.loads((logs / "check-results.json").read_text())
    by_name = {row["name"]: row for row in document["checks"]}
    assert set(by_name) == {"delivery-ledger", "generated-check"}
    assert by_name["delivery-ledger"]["argv"] == [
        sys.executable,
        "scripts/verify_delivery.py",
    ]
    assert by_name["delivery-ledger"]["status"] == "failed"
    assert by_name["delivery-ledger"]["returncode"] == 2
    assert '"status": "invalid"' in Path(by_name["delivery-ledger"]["log"]).read_text()
    assert by_name["generated-check"]["status"] == "failed"
    assert by_name["generated-check"]["returncode"] == 1
    assert (
        "Stale generated files" in Path(by_name["generated-check"]["log"]).read_text()
    )
    assert runner.exit_status(document["checks"]) == 1
    assert _tree(checkout) == before

    checks = runner.build_checks(checkout, {"generated"}, logs, python=sys.executable)
    checker = next(check for check in checks if check.name == "generated-check")
    journey = []

    def execute(label: str, *, write: bool = False) -> dict[str, object]:
        command = runner.Check(
            "generated-check",
            "generated",
            (*checker.argv, "--write") if write else checker.argv,
            checker.cwd,
        )
        result = runner.run_check(command, logs / label, environment, checkout)
        journey.append({"phase": label, **result})
        # One cumulative record preserves real command argv/status/log paths;
        # all phase logs have unique paths and are never overwritten.
        (logs / "generated-journey.json").write_text(
            json.dumps(journey, indent=2) + "\n"
        )
        return result

    assert execute("explicit-initial-write", write=True)["status"] == "passed"
    assert {
        path.relative_to(checkout).as_posix()
        for path in checkout.rglob("*")
        if path.is_file()
    } == GENERATED | {
        "README.keep",
        "scripts/check_generated.py",
        "scripts/verify_delivery.py",
    }
    protected_rows = {
        name: row
        for name, row in before.items()
        if name == "README.keep" or name.startswith("scripts/")
    }
    current = _tree(checkout)
    assert all(current[name] == row for name, row in protected_rows.items())
    assert execute("current-output-check")["returncode"] == 0
    assert _tree(checkout) == current

    controls = tmp_path / "retained-negative-inputs"
    controls.mkdir()
    cases = [
        ("missing", "analyzer-core/src/generated_rule_registration.h", None),
        ("stale", "docs/generated/rules.md", b"stale registry reference\n"),
        ("malformed", "docs/generated/native-config.example.json", b"\xff\xfe110\n"),
    ]
    for label, relative, replacement in cases:
        path = checkout / relative
        if replacement is None:
            # Retain the positive fixture bytes before creating an absent-file
            # control. This never removes a checkout/product source file.
            (controls / (label + "-original.bin")).write_bytes(path.read_bytes())
            path.unlink()
        else:
            (controls / (label + "-input.bin")).write_bytes(replacement)
            path.write_bytes(replacement)
        damaged = _tree(checkout)
        result = execute(label + "-check")
        assert result["status"] == "failed"
        assert result["returncode"] == 1
        assert relative in Path(result["log"]).read_text()
        assert _tree(checkout) == damaged
        assert execute(label + "-explicit-repair", write=True)["status"] == "passed"
    final = _tree(checkout)
    assert execute("final-current-check")["returncode"] == 0
    assert _tree(checkout) == final
    assert all(final[name] == row for name, row in protected_rows.items())
    assert [
        row["returncode"]
        for row in journey
        if row["phase"].endswith("-check")
        and row["phase"].split("-")[0] in {"missing", "stale", "malformed"}
    ] == [1, 1, 1]
