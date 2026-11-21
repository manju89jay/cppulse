"""Model interrupted Docker create; no daemon or native process is invoked."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import test_frozen_container as fixtures

from cppulse import frozen_container as candidate


def observe(tmp_path, cfg, executor):
    try:
        return fixtures.observe(tmp_path, cfg, executor)
    except KeyboardInterrupt:
        pytest.fail(
            "Interrupted client must retain a cancelled receipt and bounded cleanup outcome"
        )


@pytest.mark.parametrize("mode", ["late_owned", "always_absent", "foreign"])
def test_interrupted_create_retains_identity_and_observes_late_object(
    tmp_path: Path, monkeypatch, mode: str
) -> None:
    cfg = fixtures.request(tmp_path)
    docker = fixtures.Docker(cfg)
    probes = []
    pauses = []
    monkeypatch.setattr(candidate.time, "sleep", pauses.append)

    def executor(argv, timeout, cap):
        if argv[1] == "create":
            docker(argv, timeout, cap)
            raise KeyboardInterrupt("owned resource guard")
        if argv[1] == "inspect":
            probes.append(argv)
            if mode == "always_absent" or len(probes) < 3:
                docker.calls.append(argv)
                return candidate.DockerCommandResult(
                    "failed", 1, b"[]\n", b"no such object", 3, 14
                )
            if mode == "foreign":
                docker.owner = "foreign-owner"
        return docker(argv, timeout, cap)

    result = observe(tmp_path, cfg, executor)
    assert result.status == "unknown" and result.native_exit_code is None
    assert result.output_archive is None
    assert not any(c[1] == "start" for c in docker.calls)
    evidence = tmp_path / "evidence"
    receipt = json.loads((evidence / "command-002.json").read_bytes())
    assert receipt["status"] == "cancelled" and receipt["returncode"] is None
    assert b"KeyboardInterrupt" in (evidence / "command-002.stderr").read_bytes()
    owner = json.loads((evidence / "container-owner.json").read_bytes())
    assert owner["name"] == docker.name
    (create,) = [c for c in docker.calls if c[1] == "create"]
    assert owner["owner"] == create[create.index("--label") + 1].split("=", 1)[1]
    assert owner["image_id"] == fixtures.IMAGE
    assert len(probes) <= 4 and len(docker.calls) <= 32 and len(pauses) <= 3
    if mode == "late_owned":
        assert (
            result.container_id == fixtures.CID and result.cleanup_status == "removed"
        )
        assert [c[1] for c in docker.calls][-1] == "rm"
    else:
        assert result.cleanup_status == "unknown"
        assert not any(c[1] in ("stop", "rm") for c in docker.calls)


def test_interrupt_before_create_keeps_unavailable_without_container_claim(tmp_path):
    cfg = fixtures.request(tmp_path)

    def executor(argv, timeout, cap):
        raise KeyboardInterrupt("cancelled before image observation")

    result = observe(tmp_path, cfg, executor)
    assert result.status == "unavailable" and result.cleanup_status == "not_created"
    assert result.container_id is None and result.output_archive is None


def test_interrupt_after_start_retains_only_unqualified_output_then_cleanup(tmp_path):
    cfg = fixtures.request(tmp_path)
    docker = fixtures.Docker(cfg)

    def executor(argv, timeout, cap):
        if argv[1] == "exec" and "--read-status" in argv:
            docker.calls.append(argv)
            raise KeyboardInterrupt("cancelled while observing native")
        return docker(argv, timeout, cap)

    result = observe(tmp_path, cfg, executor)
    assert result.status == "unknown" and result.native_exit_code is None
    assert result.cleanup_status == "removed" and result.output_archive is None
    assert (tmp_path / "evidence/unqualified-output.tar").is_file()
    assert not (tmp_path / "evidence/output.tar").exists()


def test_interrupted_default_executor_retains_observed_raw_client_bytes(
    tmp_path, monkeypatch
):
    def interrupted(argv, **kwargs):
        kwargs["stdout"].write(b"original client stdout\x00")
        kwargs["stderr"].write(b"original client stderr\x00")
        raise KeyboardInterrupt("resource guard")

    monkeypatch.setattr(candidate, "run_bounded_process", interrupted)
    try:
        result = candidate._execute(
            ["never-executed-client"],
            1,
            1024,
            daemon_host="unix:///fixture",
            client_config=tmp_path,
        )
    except KeyboardInterrupt:
        pytest.fail("Default executor lost its observed raw streams on interruption")
    assert result.status == "cancelled" and result.returncode is None
    assert result.stdout == b"original client stdout\x00"
    assert result.stderr == b"original client stderr\x00"
    assert result.stdout_bytes == len(result.stdout)
    assert result.stderr_bytes == len(result.stderr)
    assert any("unknown" in note.lower() for note in result.limitations)
