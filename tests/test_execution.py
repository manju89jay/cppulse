"""Real-process regressions for explicit, bounded local recipe execution."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from typing import Any

import pytest

import cppulse
from cppulse import __version__
from cppulse.contracts import validate
from cppulse.errors import ContractError
from cppulse.execution import CancellationToken, ProcessLimits, run_recipe
from cppulse.identities import context_identity, snapshot_inputs


@pytest.fixture
def selected(tmp_path: Path) -> tuple[Path, dict[str, Any], list[dict[str, Any]]]:
    """Create a selected inventory independent of Git or an installed compiler."""
    workspace = tmp_path / "workspace with spaces"
    workspace.mkdir()
    (workspace / "main.cpp").write_text("int main() { return 0; }\n")
    source = snapshot_inputs(workspace, ["main.cpp"])
    contexts = [
        context_identity(
            {
                "id": name,
                "compiler": {"name": "fixture", "version": "1"},
                "argv": ["fixture", name],
                "working_directory": str(workspace),
                "language_standard": "c++17",
                "target": "test-local",
                "provenance": "observed",
                "dependencies": [],
            }
        )
        for name in ["first", "second"]
    ]
    return workspace, source, contexts


def command(
    name: str,
    code: str,
    *,
    context: str = "first",
    depends_on: tuple[str, ...] = (),
    inputs: tuple[str, ...] = ("main.cpp",),
    outputs: tuple[str, ...] = (),
    timeout: float = 5,
) -> dict[str, Any]:
    """Declare a real Python process; no shell or mocked process is involved."""
    return {
        "id": name,
        "context_id": context,
        "argv": [sys.executable, "-c", code],
        "cwd": ".",
        "depends_on": list(depends_on),
        "inputs": list(inputs),
        "outputs": list(outputs),
        "timeout_seconds": timeout,
    }


def recipe(*steps: dict[str, Any], jobs: int = 2) -> dict[str, Any]:
    """Declare the selected contexts and scheduler bound explicitly."""
    return {
        "version": "2.0.0",
        "id": "fixture",
        "jobs": jobs,
        "contexts": sorted({step["context_id"] for step in steps}),
        "steps": list(steps),
    }


def execute(
    tmp_path: Path,
    selected: tuple[Path, dict[str, Any], list[dict[str, Any]]],
    document: dict[str, Any],
    **kwargs: Any,
) -> Any:
    """Run one fixture with a fresh exclusively owned log directory."""
    return run_recipe(document, *selected, tmp_path / "logs", **kwargs)


def process_alive(pid: int) -> bool:
    """Treat an orphan zombie as terminated rather than a running child."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().split(")", 1)[1].split()[0]
        return state != "Z"
    except FileNotFoundError:
        return False


def child_environment() -> dict[str, str]:
    """Propagate the imported package location without relying on pytest paths."""
    environment = dict(os.environ)
    package_root = str(Path(cppulse.__file__).resolve().parents[1])
    environment["PYTHONPATH"] = os.pathsep.join(
        part for part in [package_root, environment.get("PYTHONPATH", "")] if part
    )
    return environment


def test_exact_arguments_cwd_environment_receipt_and_file_facts(
    tmp_path: Path, selected: Any
) -> None:
    workspace, source, _ = selected
    (workspace / "nested").mkdir()
    step = command(
        "literal",
        "import json,os,sys; from pathlib import Path; "
        "Path('result.json').write_text(json.dumps([sys.argv[1:],os.getcwd(),os.environ['CPPULSE_TEST']]))",
        outputs=("nested/result.json",),
    )
    literal = "$(touch injected); 'two words' & $HOME"
    step["argv"].append(literal)
    step["cwd"] = "nested"
    step["environment"] = {"CPPULSE_TEST": "selected value"}
    result = execute(tmp_path, selected, recipe(step))
    item = result.steps[0]
    assert json.loads((workspace / "nested/result.json").read_text()) == [
        [literal],
        str(workspace / "nested"),
        "selected value",
    ]
    assert not (workspace / "nested/injected").exists()
    assert item.receipt["argv"] == step["argv"]
    assert item.receipt["cwd"] == str(workspace / "nested")
    assert item.receipt["source_digest"] == source["digest"]
    assert item.receipt["producer"] == {
        "name": "cppulse.executor",
        "version": __version__,
    }
    assert item.receipt["status"] == "passed"
    assert item.receipt["exit_code"] == 0 and item.receipt["signal"] is None
    validate("execution_receipt", item.receipt)
    assert item.material_status == "available"
    assert item.input_facts[0]["path"] == "main.cpp"
    assert item.input_facts[0]["sha256"] == source["files"][0]["sha256"]
    assert item.input_after_facts == item.input_facts
    assert {"device", "inode", "mtime_ns", "ctime_ns"} <= set(
        item.input_facts[0]["stat"]
    )
    assert item.output_facts[0]["freshness"] == "created"
    assert (
        item.output_facts[0]["sha256"]
        == hashlib.sha256((workspace / "nested/result.json").read_bytes()).hexdigest()
    )
    assert item.stdout_path.is_file() and item.stderr_path.is_file()
    assert result.started_at <= result.finished_at


@pytest.mark.parametrize("missing", ["cwd", "executable", "input"])
def test_missing_prerequisites_are_operational_errors(
    tmp_path: Path, selected: Any, missing: str
) -> None:
    step = command("missing", "raise AssertionError('must not launch')")
    if missing == "cwd":
        step["cwd"] = "absent"
    elif missing == "executable":
        step["argv"] = ["cppulse-nonexistent-executable-7e185"]
    else:
        (selected[0] / "main.cpp").unlink()
    item = execute(tmp_path, selected, recipe(step)).steps[0]
    assert item.receipt["status"] == "error"
    assert item.receipt["reason"]
    assert item.receipt["exit_code"] is None
    assert item.material_status == "not_collected"
    validate("execution_receipt", item.receipt)


def test_failed_build_skips_dependents_but_independent_context_continues(
    tmp_path: Path, selected: Any
) -> None:
    document = recipe(
        command("build", "raise SystemExit(7)", outputs=("app",)),
        command("tests", "raise AssertionError('not launched')", depends_on=("build",)),
        command("independent", "print('other context')", context="second"),
    )
    result = execute(tmp_path, selected, document)
    assert [item.receipt["id"] for item in result.steps] == [
        "build",
        "tests",
        "independent",
    ]
    assert [item.receipt["status"] for item in result.steps] == [
        "failed",
        "skipped",
        "passed",
    ]
    assert result.steps[0].receipt["exit_code"] == 7
    assert "build" in result.steps[1].receipt["reason"]
    assert result.steps[2].stdout_path.read_bytes() == b"other context\n"


def test_missing_output_keeps_exit_zero_receipt_and_blocks_dependent(
    tmp_path: Path, selected: Any
) -> None:
    result = execute(
        tmp_path,
        selected,
        recipe(
            command("build", "pass", outputs=("app",)),
            command("tests", "pass", depends_on=("build",), inputs=("app",)),
        ),
    )
    assert result.steps[0].receipt["status"] == "passed"
    assert result.steps[0].material_status == "missing"
    assert result.steps[0].limitations
    assert result.steps[1].receipt["status"] == "skipped"


@pytest.mark.parametrize("rewrite", [False, True])
def test_preexisting_output_requires_an_observed_write_even_with_identical_bytes(
    tmp_path: Path, selected: Any, rewrite: bool
) -> None:
    workspace, _, _ = selected
    old = workspace / "old.xml"
    old.write_bytes(b"same report bytes")
    code = (
        "from pathlib import Path; Path('old.xml').write_bytes(b'same report bytes')"
        if rewrite
        else "pass"
    )
    item = execute(
        tmp_path, selected, recipe(command("report", code, outputs=("old.xml",)))
    ).steps[0]
    assert item.receipt["status"] == "passed"
    assert item.preexisting_output_facts[0]["sha256"] == item.output_facts[0]["sha256"]
    assert item.material_status == ("available" if rewrite else "invalid")
    assert item.output_facts[0]["freshness"] == ("modified" if rewrite else "unchanged")
    assert old.read_bytes() == b"same report bytes"
    if not rewrite:
        assert any("unchanged" in message.lower() for message in item.limitations)


def test_generated_input_requires_ancestor_and_its_facts_match_output(
    tmp_path: Path, selected: Any
) -> None:
    document = recipe(
        command(
            "build",
            "from pathlib import Path; Path('app').write_bytes(b'app')",
            outputs=("app",),
        ),
        command("tests", "print('tested')", depends_on=("build",), inputs=("app",)),
    )
    result = execute(tmp_path, selected, document)
    assert (
        result.steps[0].output_facts[0]["sha256"]
        == result.steps[1].input_facts[0]["sha256"]
    )
    assert all(item.receipt["status"] == "passed" for item in result.steps)


def test_both_pipes_are_drained_with_a_combined_storage_budget(
    tmp_path: Path, selected: Any
) -> None:
    count = 1024 * 1024
    code = f"import os; os.write(1,b'o'*{count}); os.write(2,b'e'*{count})"
    item = execute(
        tmp_path,
        selected,
        recipe(command("noisy", code)),
        limits=ProcessLimits(max_log_bytes=8192),
    ).steps[0]
    assert item.receipt["status"] == "passed"
    assert item.stdout_bytes == count and item.stderr_bytes == count
    assert item.captured_bytes == 8192
    assert item.stdout_path.stat().st_size + item.stderr_path.stat().st_size == 8192
    assert item.logs_truncated and item.limitations


@pytest.mark.parametrize("path_kind", ["input", "output", "parent", "cwd"])
def test_symlink_paths_fail_without_following_targets(
    tmp_path: Path, selected: Any, path_kind: str
) -> None:
    workspace, _, _ = selected
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "file").write_bytes(b"preserve")
    (workspace / "linked").symlink_to(outside, target_is_directory=True)
    (workspace / "leaf").symlink_to(outside / "file")
    step = command("symlink", "raise AssertionError('must not launch')")
    if path_kind == "input":
        (workspace / "main.cpp").unlink()
        (workspace / "main.cpp").symlink_to(outside / "file")
    elif path_kind == "output":
        step["outputs"] = ["leaf"]
    elif path_kind == "parent":
        step["outputs"] = ["linked/file"]
    else:
        step["cwd"] = "linked"
    item = execute(tmp_path, selected, recipe(step)).steps[0]
    assert item.receipt["status"] == "error"
    assert (outside / "file").read_bytes() == b"preserve"


@pytest.mark.parametrize(
    "hazard",
    ["traversal", "nul", "jobs", "collision", "unlisted", "producer", "context"],
)
def test_invalid_recipe_is_rejected_before_any_launch(
    tmp_path: Path, selected: Any, hazard: str
) -> None:
    workspace, _, _ = selected
    document = recipe(
        command(
            "first",
            "from pathlib import Path; Path('launched').touch()",
            outputs=("artifact",),
        )
    )
    if hazard == "traversal":
        document["steps"][0]["outputs"] = ["../escape"]
    elif hazard == "nul":
        document["steps"][0]["argv"].append("bad\x00argument")
    elif hazard == "jobs":
        document["jobs"] = 33
    elif hazard == "collision":
        document["steps"].append(command("second", "pass", outputs=("artifact",)))
    elif hazard == "unlisted":
        (workspace / "not-selected.cpp").write_bytes(b"unselected")
        document["steps"][0]["inputs"] = ["not-selected.cpp"]
    elif hazard == "producer":
        document["steps"].append(command("second", "pass", inputs=("artifact",)))
    else:
        document["contexts"] = ["unselected"]
        document["steps"][0]["context_id"] = "unselected"
    with pytest.raises(ContractError):
        execute(tmp_path, selected, document)
    assert not (workspace / "launched").exists()


def test_jobs_bound_is_observed_and_ready_work_actually_overlaps(
    tmp_path: Path, selected: Any
) -> None:
    steps = [
        command(f"job-{index}", "import time; time.sleep(.18)") for index in range(4)
    ]
    result = execute(tmp_path, selected, recipe(*steps, jobs=2))
    assert result.max_parallel_steps == 2
    assert all(item.receipt["status"] == "passed" for item in result.steps)
    ordered = sorted(result.steps, key=lambda item: item.receipt["started_at"])
    assert ordered[1].receipt["started_at"] < ordered[0].receipt["finished_at"]
    assert ordered[2].receipt["started_at"] >= min(
        item.receipt["finished_at"] for item in ordered[:2]
    )


def test_signal_death_is_an_operational_error_not_a_test_failure(
    tmp_path: Path, selected: Any
) -> None:
    item = execute(
        tmp_path,
        selected,
        recipe(
            command("crash", "import os,signal; os.kill(os.getpid(), signal.SIGKILL)")
        ),
    ).steps[0]
    assert item.receipt["status"] == "error"
    assert item.receipt["signal"] == signal.SIGKILL
    assert item.receipt["exit_code"] is None


@pytest.mark.parametrize("stop", ["timeout", "cancel"])
def test_termination_reaps_parent_and_kills_sigterm_ignoring_grandchild(
    tmp_path: Path, selected: Any, stop: str
) -> None:
    workspace, _, _ = selected
    child = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)"
    code = (
        "import subprocess,sys,time; from pathlib import Path; "
        f"p=subprocess.Popen([sys.executable,'-c',{child!r}]); "
        "Path('child.pid').write_text(str(p.pid)); time.sleep(30)"
    )
    token = CancellationToken()
    timer: threading.Thread | None = None
    if stop == "cancel":

        def cancel_when_spawned() -> None:
            deadline = time.monotonic() + 5
            while (
                not (workspace / "child.pid").exists() and time.monotonic() < deadline
            ):
                time.sleep(0.01)
            time.sleep(0.1)
            token.cancel()

        timer = threading.Thread(target=cancel_when_spawned)
        timer.start()
    try:
        result = execute(
            tmp_path,
            selected,
            recipe(command("tree", code, timeout=0.45 if stop == "timeout" else 5)),
            limits=ProcessLimits(termination_grace_seconds=0.15),
            cancel=token,
        )
        pid = int((workspace / "child.pid").read_text())
        assert result.steps[0].receipt["status"] == (
            "timed_out" if stop == "timeout" else "cancelled"
        )
        assert not process_alive(pid)
        assert result.cancelled == (stop == "cancel")
    finally:
        if timer is not None:
            timer.join(timeout=5)
        if (workspace / "child.pid").exists():
            pid = int((workspace / "child.pid").read_text())
            if process_alive(pid):
                os.kill(pid, signal.SIGKILL)


def test_pre_cancelled_recipe_does_not_launch(tmp_path: Path, selected: Any) -> None:
    token = CancellationToken()
    token.cancel()
    result = execute(
        tmp_path,
        selected,
        recipe(command("never", "raise AssertionError()")),
        cancel=token,
    )
    assert result.cancelled and result.max_parallel_steps == 0
    assert result.steps[0].receipt["status"] == "cancelled"
    assert result.steps[0].material_status == "not_collected"


def test_background_pipe_holder_does_not_hang_after_main_process_exits(
    tmp_path: Path, selected: Any
) -> None:
    workspace, _, _ = selected
    code = (
        "import subprocess,sys; from pathlib import Path; "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
        "Path('child.pid').write_text(str(p.pid))"
    )
    result = execute(
        tmp_path,
        selected,
        recipe(command("background", code)),
        limits=ProcessLimits(termination_grace_seconds=0.1),
    )
    assert result.steps[0].receipt["status"] == "error"
    assert not process_alive(int((workspace / "child.pid").read_text()))


def test_sigint_driver_returns_cancelled_receipts_and_cleans_processes(
    tmp_path: Path, selected: Any
) -> None:
    workspace, source, contexts = selected
    code = (
        "import os,time; from pathlib import Path; "
        "Path('running.pid.tmp').write_text(str(os.getpid())); "
        "Path('running.pid.tmp').replace('running.pid'); time.sleep(30)"
    )
    document = recipe(command("interrupt", code, timeout=10))
    driver = (
        "import json; from pathlib import Path; from cppulse.execution import run_recipe,ProcessLimits; "
        f"r=run_recipe({document!r},Path({str(workspace)!r}),{source!r},{contexts!r},"
        f"Path({str(tmp_path / 'driver-logs')!r}),limits=ProcessLimits(termination_grace_seconds=.1)); "
        "print(json.dumps({'cancelled':r.cancelled,'status':r.steps[0].receipt['status']}))"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", driver],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=child_environment(),
    )
    try:
        deadline = time.monotonic() + 8
        while not (workspace / "running.pid").exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.01)
        assert (workspace / "running.pid").exists()
        os.kill(process.pid, signal.SIGINT)
        stdout, stderr = process.communicate(timeout=5)
        assert process.returncode == 0, stderr.decode()
        assert json.loads(stdout) == {"cancelled": True, "status": "cancelled"}
        assert not process_alive(int((workspace / "running.pid").read_text()))
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        if (workspace / "running.pid").exists():
            pid = int((workspace / "running.pid").read_text())
            if process_alive(pid):
                os.kill(pid, signal.SIGKILL)


def test_reusing_step_log_paths_never_overwrites_prior_evidence(
    tmp_path: Path, selected: Any
) -> None:
    document = recipe(command("once", "print('first')"))
    first = execute(tmp_path, selected, document)
    original = first.steps[0].stdout_path.read_bytes()
    with pytest.raises((FileExistsError, ContractError)):
        execute(tmp_path, selected, deepcopy(document))
    assert first.steps[0].stdout_path.read_bytes() == original


def test_selected_executable_facts_resolve_host_style_symlinks_and_relative_path(
    tmp_path: Path, selected: Any
) -> None:
    workspace, _, _ = selected
    tools = workspace / "tools"
    tools.mkdir()
    (tools / "python").symlink_to(sys.executable)
    step = command("tool", "print('observed executable')")
    step["argv"][0] = "python"
    step["environment"] = {"PATH": "tools"}
    item = execute(tmp_path, selected, recipe(step)).steps[0]
    assert item.receipt["status"] == "passed"
    assert item.executable_fact is not None
    assert item.executable_fact["path"] == str(Path(sys.executable).resolve())
    assert (
        item.executable_fact["sha256"]
        == hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
    )
    assert item.stdout_path.read_bytes() == b"observed executable\n"


def test_executable_mutation_invalidates_material_without_implicit_version_command(
    tmp_path: Path, selected: Any
) -> None:
    workspace, _, _ = selected
    executable = workspace / "tool"
    executable.write_text(
        f"#!{sys.executable}\n"
        "from pathlib import Path\n"
        "p=Path(__file__)\n"
        "p.write_text(p.read_text()+'# changed\\n')\n"
        "Path('app').write_bytes(b'produced')\n"
    )
    executable.chmod(0o755)
    before = hashlib.sha256(executable.read_bytes()).hexdigest()
    step = command("changing-tool", "unused", outputs=("app",))
    step["argv"] = ["./tool"]
    item = execute(tmp_path, selected, recipe(step)).steps[0]
    assert item.receipt["status"] == "error"
    assert item.receipt["exit_code"] == 0
    assert item.material_status == "invalid"
    assert item.executable_fact["sha256"] == before
    assert "executable" in item.receipt["reason"].lower()
    assert item.limitations


@pytest.mark.parametrize(
    "limits",
    [
        {"max_log_bytes": 0},
        {"max_log_bytes": True},
        {"max_log_bytes": 64 * 1024 * 1024 + 1},
        {"termination_grace_seconds": 0},
        {"termination_grace_seconds": float("nan")},
    ],
)
def test_invalid_process_limits_are_rejected(limits: dict[str, Any]) -> None:
    with pytest.raises(ContractError):
        ProcessLimits(**limits)


@pytest.mark.parametrize("hazard", ["del", "c1", "git", "secret"])
def test_direct_api_rejects_collection_path_and_environment_hazards(
    tmp_path: Path, selected: Any, hazard: str
) -> None:
    step = command("hazard", "raise AssertionError('must not launch')")
    if hazard == "secret":
        step["environment"] = {"EXAMPLE_API_KEY": "test-only-value"}
    else:
        step["outputs"] = [
            {"del": "out\x7ffile", "c1": "out\x85file", "git": ".GiT/config"}[hazard]
        ]
    with pytest.raises(ContractError):
        execute(tmp_path, selected, recipe(step))


def test_changed_selected_source_is_not_executed_under_the_old_digest(
    tmp_path: Path, selected: Any
) -> None:
    workspace, _, _ = selected
    (workspace / "main.cpp").write_bytes(b"changed after snapshot")
    step = command(
        "changed-source", "from pathlib import Path; Path('launched').touch()"
    )
    item = execute(tmp_path, selected, recipe(step)).steps[0]
    assert item.receipt["status"] == "error"
    assert item.receipt["exit_code"] is None
    assert not (workspace / "launched").exists()


def test_executable_symlink_loop_records_error_and_independent_branch_continues(
    tmp_path: Path, selected: Any
) -> None:
    workspace, _, _ = selected
    (workspace / "loop").symlink_to("loop")
    step = command("bad-tool", "unused")
    step["argv"] = ["./loop"]
    result = execute(
        tmp_path,
        selected,
        recipe(step, command("independent", "pass", context="second")),
    )
    assert result.steps[0].receipt["status"] == "error"
    assert result.steps[0].receipt["exit_code"] is None
    assert result.steps[1].receipt["status"] == "passed"


@pytest.mark.parametrize("mutation", ["write", "remove"])
def test_postexecution_source_input_change_invalidates_material_preserving_exit_zero(
    tmp_path: Path, selected: Any, mutation: str
) -> None:
    operation = ".write_bytes(b'new source')" if mutation == "write" else ".unlink()"
    step = command(
        "changed-input", "from pathlib import Path; Path('main.cpp')" + operation
    )
    item = execute(tmp_path, selected, recipe(step)).steps[0]
    assert item.receipt["status"] == "passed" and item.receipt["exit_code"] == 0
    assert item.material_status == "invalid"
    assert any("main.cpp" in entry for entry in item.limitations)
    if mutation == "write":
        assert item.input_facts[0]["sha256"] != item.input_after_facts[0]["sha256"]
    else:
        assert item.input_after_facts == []


def test_generated_binary_mutated_by_tests_blocks_their_dependents(
    tmp_path: Path, selected: Any
) -> None:
    document = recipe(
        command(
            "build",
            "from pathlib import Path; Path('app').write_bytes(b'binary')",
            outputs=("app",),
        ),
        command(
            "tests",
            "from pathlib import Path; Path('app').write_bytes(b'changed')",
            depends_on=("build",),
            inputs=("app",),
        ),
        command(
            "after-tests", "raise AssertionError('must not run')", depends_on=("tests",)
        ),
    )
    result = execute(tmp_path, selected, document)
    item = result.steps[1]
    assert item.receipt["status"] == "passed" and item.receipt["exit_code"] == 0
    assert item.material_status == "invalid"
    assert item.input_facts[0]["sha256"] != item.input_after_facts[0]["sha256"]
    assert result.steps[2].receipt["status"] == "skipped"


def test_direct_api_cannot_relabel_generated_binary_with_another_context(
    tmp_path: Path, selected: Any
) -> None:
    document = recipe(
        command(
            "build", "from pathlib import Path; Path('app').touch()", outputs=("app",)
        ),
        command(
            "tests", "pass", context="second", depends_on=("build",), inputs=("app",)
        ),
    )
    with pytest.raises(ContractError):
        execute(tmp_path, selected, document)


def test_absolute_host_executable_uses_host_filename_rules(
    tmp_path: Path, selected: Any
) -> None:
    executable = tmp_path / "tool:local"
    executable.write_text(f"#!{sys.executable}\nprint('host tool')\n")
    executable.chmod(0o755)
    step = command("host-tool", "unused")
    step["argv"] = [str(executable)]
    item = execute(tmp_path, selected, recipe(step)).steps[0]
    assert item.receipt["status"] == "passed"
    assert item.executable_fact["path"] == str(executable)
    assert item.stdout_path.read_bytes() == b"host tool\n"


def test_log_storage_failure_preserves_actual_exit_and_drained_bytes(
    tmp_path: Path, selected: Any
) -> None:
    workspace, source, contexts = selected
    document = recipe(command("write", "import os; os.write(1,b'x'*2000)"))
    driver = (
        "import json,resource,signal; from pathlib import Path; from cppulse.execution import run_recipe; "
        "signal.signal(signal.SIGXFSZ,signal.SIG_IGN); resource.setrlimit(resource.RLIMIT_FSIZE,(1024,1024)); "
        f"r=run_recipe({document!r},Path({str(workspace)!r}),{source!r},{contexts!r},Path({str(tmp_path / 'limited-logs')!r})); "
        "s=r.steps[0]; print(json.dumps({'status':s.receipt['status'],'exit':s.receipt['exit_code'],"
        "'drained':s.stdout_bytes,'captured':s.captured_bytes,'size':s.stdout_path.stat().st_size,"
        "'stderr_size':s.stderr_path.stat().st_size,"
        "'limitations':s.limitations}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", driver],
        capture_output=True,
        timeout=5,
        check=False,
        # A file-size-limited auxiliary process must not write coverage databases.
        env={
            key: value
            for key, value in child_environment().items()
            if not key.startswith("COV_CORE_") and key != "COVERAGE_PROCESS_START"
        },
    )
    assert completed.returncode == 0, completed.stderr.decode()
    facts = json.loads(completed.stdout)
    assert facts["status"] == "error" and facts["exit"] == 0
    assert facts["drained"] == 2000
    assert facts["size"] == 1024
    assert facts["captured"] == facts["size"] + facts["stderr_size"]
    assert facts["limitations"]
