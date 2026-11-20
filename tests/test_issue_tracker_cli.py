"""Explicit issue CLI preserves inputs and partial artifacts without provider writes."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from cppulse import issue_tracker_cli as cli
from cppulse.issue_tracker import collect as producer


def request() -> dict:
    return {
        "version": "1.0.0",
        "provider": "github-rest-2022-11-28",
        "repository": "owner/repo",
        "window": {"start": "2020-01-01T00:00:00Z", "end": "2026-11-16T00:00:00Z"},
        "limits": {"pages": 1, "page_bytes": 65536, "wall_seconds": 10},
        "cost_inputs": [],
    }


def issue() -> dict:
    return {
        "number": 1,
        "title": "Fixture",
        "state": "open",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-03-01T00:00:00Z",
        "closed_at": None,
        "html_url": "https://github.com/owner/repo/issues/1",
    }


def source(tmp_path: Path, document: dict | None = None) -> Path:
    path = tmp_path / "request.json"
    path.write_text(json.dumps(document or request(), indent=2) + "\n")
    return path


def invoke(path: Path, output: Path) -> int:
    return cli.main(["--request", str(path), "--output", str(output)])


@pytest.mark.parametrize(
    ("status", "headers", "rows", "expected"),
    [
        (200, {}, [issue()], 0),
        (
            200,
            {
                "Link": '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="next"'
            },
            [issue()],
            3,
        ),
        (403, {}, [], 3),
    ],
)
def test_cli_uses_actual_producer_retains_original_and_binds_artifacts(
    tmp_path, monkeypatch, capsys, status, headers, rows, expected
):
    path = source(tmp_path)
    original = path.read_bytes()
    output = tmp_path / "output"
    monkeypatch.setattr(
        cli,
        "collect",
        lambda document, destination: producer(
            document,
            destination,
            transport=lambda *_: (status, headers, json.dumps(rows).encode()),
        ),
    )
    assert invoke(path, output) == expected
    summary = json.loads(capsys.readouterr().out)
    manifest = json.loads((output / "outcome.json").read_bytes())
    assert summary["exit_status"] == expected
    assert (
        summary["outcome_sha256"]
        == hashlib.sha256((output / "outcome.json").read_bytes()).hexdigest()
    )
    assert (output / "request.original.json").read_bytes() == original
    assert manifest["request_original_sha256"] == hashlib.sha256(original).hexdigest()
    for artifact in manifest["artifacts"]:
        content = (output / artifact["path"]).read_bytes()
        assert len(content) == artifact["size_bytes"]
        assert hashlib.sha256(content).hexdigest() == artifact["sha256"]
    assert (output / "observations/report.json").exists()


@pytest.mark.parametrize(
    "raw",
    [
        b'{"version":"1.0.0","version":"other"}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":1e9999}',
        b"\xff",
        b"[" * 20000 + b"0" + b"]" * 20000,
        b" " * 131073,
    ],
)
def test_invalid_raw_request_never_creates_output_or_contacts_provider(
    tmp_path, monkeypatch, capsys, raw
):
    path = tmp_path / "bad.json"
    path.write_bytes(raw)
    calls = []
    monkeypatch.setattr(cli, "collect", lambda *args: calls.append(args))
    assert invoke(path, tmp_path / "output") == 2
    assert not calls
    assert not (tmp_path / "output").exists()
    assert json.loads(capsys.readouterr().out)["exit_status"] == 2


def test_schema_invalid_request_is_rejected_before_output(tmp_path, monkeypatch):
    path = source(tmp_path, {"version": "wrong"})
    monkeypatch.setattr(cli, "collect", lambda *_: pytest.fail("provider must not run"))
    assert invoke(path, tmp_path / "output") == 2
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("kind", ["symlink", "ancestor_symlink", "fifo"])
def test_nofollow_regular_request_boundary(tmp_path, monkeypatch, kind):
    path = source(tmp_path)
    selected = tmp_path / "selected.json"
    if kind == "symlink":
        selected.symlink_to(path)
    elif kind == "ancestor_symlink":
        folder = tmp_path / "folder"
        folder.mkdir()
        (folder / "request.json").write_bytes(path.read_bytes())
        link = tmp_path / "linked"
        link.symlink_to(folder, target_is_directory=True)
        selected = link / "request.json"
    else:
        os.mkfifo(selected)
    monkeypatch.setattr(cli, "collect", lambda *_: pytest.fail("provider must not run"))
    assert invoke(selected, tmp_path / "output") == 2
    assert not (tmp_path / "output").exists()


def test_existing_output_rejected_before_provider_and_preserved(tmp_path, monkeypatch):
    path = source(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    (output / "preserve").write_bytes(b"original")
    monkeypatch.setattr(cli, "collect", lambda *_: pytest.fail("provider must not run"))
    assert invoke(path, output) == 2
    assert list(output.iterdir()) == [output / "preserve"]
    assert (output / "preserve").read_bytes() == b"original"


def test_output_ancestor_symlink_rejected_before_provider(tmp_path, monkeypatch):
    path = source(tmp_path)
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(target, target_is_directory=True)
    monkeypatch.setattr(cli, "collect", lambda *_: pytest.fail("provider must not run"))
    assert invoke(path, link / "output") == 2
    assert not list(target.iterdir())


def test_cancel_preserves_prior_raw_page_and_owned_diagnostics(
    tmp_path, monkeypatch, capsys
):
    config = request()
    config["limits"]["pages"] = 2
    path = source(tmp_path, config)
    output = tmp_path / "output"
    calls = []

    def get(*args):
        calls.append(args)
        if len(calls) > 1:
            raise KeyboardInterrupt
        return (
            200,
            {
                "Link": '<https://api.github.com/repos/owner/repo/issues?page=2>; rel="next"'
            },
            json.dumps([issue()]).encode(),
        )

    monkeypatch.setattr(
        cli,
        "collect",
        lambda document, destination: producer(document, destination, transport=get),
    )
    assert invoke(path, output) == 130
    assert json.loads(capsys.readouterr().out)["status"] == "cancelled"
    outcome = json.loads((output / "outcome.json").read_bytes())
    assert outcome["status"] == "cancelled"
    assert (output / "request.original.json").read_bytes() == path.read_bytes()
    assert (output / "observations/page-001.body").is_file()
    assert (output / "diagnostics.txt").is_file()
    assert not (output / "observations/report.json").exists()


def test_retained_report_mutation_cannot_be_bound_as_success(tmp_path, monkeypatch):
    path = source(tmp_path)
    output = tmp_path / "output"

    def mutate(document, destination):
        value = producer(
            document,
            destination,
            transport=lambda *_: (200, {}, json.dumps([issue()]).encode()),
        )
        (destination / "report.json").write_bytes(
            b'{"invented":"financial authentication"}'
        )
        return value

    monkeypatch.setattr(cli, "collect", mutate)
    assert invoke(path, output) == 2
    assert json.loads((output / "outcome.json").read_bytes())["status"] == "failed"


def test_real_module_entrypoint_invalid_input_has_json_exit2(tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(b'{"bad":NaN}')
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cppulse.issue_tracker_cli",
            "--request",
            str(path),
            "--output",
            str(tmp_path / "output"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert json.loads(result.stdout)["exit_status"] == 2
    assert not (tmp_path / "output").exists()


def test_producer_mutation_cannot_rebind_original_selected_request(
    tmp_path, monkeypatch
):
    path = source(tmp_path)
    output = tmp_path / "output"

    def mutate(document, destination):
        document["repository"] = "different/repo"
        row = issue()
        row["html_url"] = "https://github.com/different/repo/issues/1"
        return producer(
            document,
            destination,
            transport=lambda *_: (200, {}, json.dumps([row]).encode()),
        )

    monkeypatch.setattr(cli, "collect", mutate)
    assert invoke(path, output) == 2
    assert (
        json.loads((output / "request.original.json").read_bytes())["repository"]
        == "owner/repo"
    )
    assert json.loads((output / "outcome.json").read_bytes())["status"] == "failed"


def test_finalization_cancellation_retains_a_cancel_outcome_and_diagnostics(
    tmp_path, monkeypatch, capsys
):
    path = source(tmp_path)
    output = tmp_path / "output"
    monkeypatch.setattr(
        cli,
        "collect",
        lambda document, destination: producer(
            document,
            destination,
            transport=lambda *_: (200, {}, json.dumps([issue()]).encode()),
        ),
    )

    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_inventory", interrupt)
    assert invoke(path, output) == 130
    summary = json.loads(capsys.readouterr().out)
    assert summary["status"] == "cancelled"
    assert (output / "diagnostics.txt").is_file()
    assert (output / "observations/report.json").is_file()
    assert (
        json.loads((output / "outcome.json").read_bytes())["artifact_inventory_status"]
        == "incomplete"
    )


def test_long_finite_numeric_token_within_request_budget_remains_supported(
    tmp_path, monkeypatch
):
    path = source(tmp_path)
    path.write_text(
        path.read_text().replace('"wall_seconds": 10', '"wall_seconds": 1.' + "0" * 300)
    )
    monkeypatch.setattr(
        cli,
        "collect",
        lambda document, destination: producer(
            document,
            destination,
            transport=lambda *_: (200, {}, json.dumps([issue()]).encode()),
        ),
    )
    assert invoke(path, tmp_path / "output") == 0


def test_late_cancellation_preserves_already_written_outcome_and_selects_cancelled_one(
    tmp_path, monkeypatch, capsys
):
    path = source(tmp_path)
    output = tmp_path / "output"
    monkeypatch.setattr(
        cli,
        "collect",
        lambda document, destination: producer(
            document,
            destination,
            transport=lambda *_: (200, {}, json.dumps([issue()]).encode()),
        ),
    )
    original_write = cli._write
    completed = []

    def interrupt_after_publication(directory, name, content):
        artifact = original_write(directory, name, content)
        if name == "outcome.json":
            completed.append(content)
            raise KeyboardInterrupt
        return artifact

    monkeypatch.setattr(cli, "_write", interrupt_after_publication)
    assert invoke(path, output) == 130
    summary = json.loads(capsys.readouterr().out)
    assert summary["outcome"].endswith("/outcome.cancelled.json")
    assert (output / "outcome.json").read_bytes() == completed[0]
    assert (
        json.loads((output / "outcome.cancelled.json").read_bytes())["status"]
        == "cancelled"
    )


def test_original_request_corruption_cannot_be_reported_as_verified_inventory(
    tmp_path, monkeypatch
):
    path = source(tmp_path)
    output = tmp_path / "output"

    def corrupt(document, destination):
        report = producer(
            document,
            destination,
            transport=lambda *_: (200, {}, json.dumps([issue()]).encode()),
        )
        (destination.parent / "request.original.json").write_bytes(b"corrupt")
        return report

    monkeypatch.setattr(cli, "collect", corrupt)
    assert invoke(path, output) == 2
    outcome = json.loads((output / "outcome.json").read_bytes())
    assert outcome["artifact_inventory_status"] == "incomplete"
    assert outcome["status"] == "failed"
    assert (output / "request.original.json").read_bytes() == b"corrupt"


def test_actual_sigint_reaps_network_worker_and_retains_cancelled_invocation(tmp_path):
    import signal
    import time

    path = source(tmp_path)
    output = tmp_path / "output"
    pidfile = tmp_path / "network.pid"
    runner = tmp_path / "runner.py"
    worker = (
        f"import os,time;path={str(pidfile)!r};temporary=path+'.pending';"
        "stream=open(temporary,'w');stream.write(str(os.getpid()));stream.flush();"
        "os.fsync(stream.fileno());stream.close();os.replace(temporary,path);time.sleep(30)"
    )
    runner.write_text(
        "import sys\nimport cppulse.issue_tracker as leaf\nfrom cppulse.issue_tracker_cli import main\nleaf._HTTP_WORKER="
        + repr(worker)
        + "\nraise SystemExit(main(sys.argv[1:]))\n"
    )
    process = subprocess.Popen(
        [sys.executable, str(runner), "--request", str(path), "--output", str(output)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    child = None
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if pidfile.exists() and pidfile.read_text().isdigit():
                child = int(pidfile.read_text())
                break
            if process.poll() is not None:
                break
            time.sleep(0.01)
        assert child is not None
        os.kill(process.pid, signal.SIGINT)
        stdout, stderr = process.communicate(timeout=8)
        assert process.returncode == 130, stderr
        assert json.loads(stdout)["status"] == "cancelled"
        assert json.loads((output / "outcome.json").read_bytes())["exit_status"] == 130
        assert (output / "request.original.json").is_file()
        assert (output / "observations/request.json").is_file()
        assert (output / "diagnostics.txt").is_file()
        with pytest.raises(ProcessLookupError):
            os.kill(child, 0)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        if child is not None:
            try:
                command = Path(f"/proc/{child}/cmdline").read_bytes()
                if os.fsencode(str(pidfile)) in command:
                    os.kill(child, signal.SIGKILL)
            except (FileNotFoundError, ProcessLookupError):
                pass
