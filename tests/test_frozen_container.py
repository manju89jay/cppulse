"""Owned lifecycle tests use only an injected Docker executor, never a daemon."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tarfile

import pytest

from cppulse.frozen_container import DockerCommandResult, observe_frozen_native
from cppulse.errors import ContractError


IMAGE = "sha256:" + "a" * 64
CID = "b" * 64
NATIVE = b"selected native fixture"
HELPER = b"selected supervisor fixture"


def archive(rows: dict[str, bytes]) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        for name, data in rows.items():
            item = tarfile.TarInfo(name)
            item.size = len(data)
            tar.addfile(item, io.BytesIO(data))
    return stream.getvalue()


def request(tmp_path: Path) -> dict:
    client = tmp_path / "docker-client"
    client.write_bytes(b"pinned mocked Docker client; never executed")
    return {
        "version": "0.1.0",
        "cache_eligible": False,
        "closure": "unqualified",
        "original_request_sha256": "c" * 64,
        "native": {
            "sha256": hashlib.sha256(NATIVE).hexdigest(),
            "size_bytes": len(NATIVE),
        },
        "runtime_manifest_sha256": "d" * 64,
        "platform": "linux-x86_64",
        "client": {
            "path": str(client),
            "sha256": hashlib.sha256(client.read_bytes()).hexdigest(),
            "size_bytes": client.stat().st_size,
        },
        "path_map": [{"source_root": str(tmp_path), "container_root": "/input"}],
        "invocation": {
            "argv": [
                "/runtime/native",
                "--input",
                "/input",
                "--output",
                "/output/report.json",
            ],
            "cwd": "/input",
            "environment": {"LANG": "C", "PATH": "/usr/bin:/bin"},
        },
        "limits": {
            "wall_seconds": 10,
            "max_stream_bytes": 65536,
            "max_entries": 100,
            "max_payload_bytes": 1000000,
        },
    }


class Docker:
    """Faithful small response model; every call and ownership field is explicit."""

    def __init__(self, cfg: dict):
        self.cfg = deepcopy(cfg)
        self.calls = []
        self.running = False
        self.owner = self.name = None
        self.entrypoint = [
            "/cppulse-runtime-supervisor",
            "/output/.cppulse-native-status.json",
        ]
        self.cmd = cfg["invocation"]["argv"]
        self.status = {
            "version": "0.1.0",
            "native_exit_code": 0,
            "native_signal": None,
            "native_exec_errno": None,
        }

    def container(self) -> dict:
        return {
            "Id": CID,
            "Name": "/" + self.name,
            "Image": IMAGE,
            "Config": {
                "Image": IMAGE,
                "Labels": {"cppulse.owner": self.owner},
                "Entrypoint": self.entrypoint,
                "Cmd": self.cmd,
                "WorkingDir": "/input",
                "Env": ["LANG=C", "PATH=/usr/bin:/bin"],
                "User": "1000:1000",
                "Healthcheck": {"Test": ["NONE"]},
            },
            "HostConfig": {
                "ReadonlyRootfs": True,
                "NetworkMode": "none",
                "CapDrop": ["ALL"],
                "CapAdd": None,
                "Privileged": False,
                "SecurityOpt": ["no-new-privileges:true"],
                "Binds": None,
                "Mounts": None,
                "PortBindings": {},
                "Tmpfs": {
                    "/output": "rw,nosuid,nodev,noexec,size=33554432,mode=0700,uid=1000,gid=1000"
                },
                "LogConfig": {"Type": "none", "Config": {}},
            },
            "Mounts": [],
            "State": {"Running": self.running, "Paused": False},
        }

    def __call__(
        self, argv: list[str], timeout_seconds: float, max_stream_bytes: int
    ) -> DockerCommandResult:
        self.calls.append(argv)
        args = argv[1:]
        if args[:2] == ["image", "inspect"]:
            body = json.dumps(
                [
                    {
                        "Id": IMAGE,
                        "Os": "linux",
                        "Architecture": "amd64",
                        "Config": {"Volumes": None, "Entrypoint": self.entrypoint},
                    }
                ]
            ).encode()
        elif args[0] == "create":
            self.name = args[args.index("--name") + 1]
            self.owner = args[args.index("--label") + 1].split("=", 1)[1]
            self.cmd = args[args.index(IMAGE) + 1 :]
            if "--entrypoint" in args:
                self.entrypoint = [args[args.index("--entrypoint") + 1]]
            body = (CID + "\n").encode()
        elif args[0] == "inspect":
            body = json.dumps([self.container()]).encode()
        elif args[0] == "start":
            self.running = True
            body = (CID + "\n").encode()
        elif args[0] == "cp":
            source = args[1]
            if source.endswith(":/runtime/native"):
                body = archive({"native": NATIVE})
            elif source.endswith(":/cppulse-runtime-supervisor"):
                body = archive({"cppulse-runtime-supervisor": HELPER})
            else:
                raise AssertionError(
                    "tmpfs output must be read inside the running container"
                )
        elif args[0] == "exec":
            assert self.running, "tmpfs output must be collected before stop"
            assert args[1:3] == [CID, "/cppulse-runtime-supervisor"]
            if args[3:] == ["--read-status", "/output/.cppulse-native-status.json"]:
                body = json.dumps(self.status).encode()
            else:
                assert args[3:] == ["--archive-output", "/output"]
                body = archive(
                    {
                        "report.json": b"{}",
                        ".cppulse-native-status.json": json.dumps(self.status).encode(),
                        ".cppulse-native.stdout": b"actual native log",
                        ".cppulse-native.stderr": b"",
                    }
                )
        elif args[0] == "stop":
            self.running = False
            body = (CID + "\n").encode()
        elif args[0] == "rm":
            assert not self.running
            body = (CID + "\n").encode()
        else:
            raise AssertionError(args)
        return DockerCommandResult("passed", 0, body, b"", len(body), 0)


def test_success_preserves_owned_output_before_cleanup(tmp_path: Path) -> None:
    cfg = request(tmp_path)
    docker = Docker(cfg)
    result = observe_frozen_native(
        cfg,
        IMAGE,
        tmp_path / "evidence",
        supervisor_sha256=hashlib.sha256(HELPER).hexdigest(),
        executor=docker,
    )
    assert result.status == "observed"
    assert result.native_exit_code == 0
    assert result.cleanup_status == "removed"
    assert result.container_id == CID
    assert result.output_archive.is_file()
    assert result.execution_ready is result.cache_eligible is False
    assert result.closure == "unqualified"
    assert all(call[-1] == CID for call in docker.calls if call[1] in {"stop", "rm"})
    assert not any(
        "--mount" in call or "--volume" in call or "--publish" in call
        for call in docker.calls
    )


def observe(tmp_path: Path, cfg: dict, docker) -> object:
    return observe_frozen_native(
        cfg,
        IMAGE,
        tmp_path / "evidence",
        supervisor_sha256=hashlib.sha256(HELPER).hexdigest(),
        executor=docker,
    )


@pytest.mark.parametrize("mutation", ["image", "volumes", "architecture", "entrypoint"])
def test_image_identity_and_configuration_are_gates(
    tmp_path: Path, mutation: str
) -> None:
    cfg, docker = request(tmp_path), None
    docker = Docker(cfg)

    def executor(argv, timeout, limit):
        result = docker(argv, timeout, limit)
        if argv[1:3] == ["image", "inspect"]:
            rows = json.loads(result.stdout)
            if mutation == "image":
                rows[0]["Id"] = "sha256:" + "f" * 64
            elif mutation == "volumes":
                rows[0]["Config"]["Volumes"] = {"/input": {}}
            elif mutation == "architecture":
                rows[0]["Architecture"] = "arm64"
            else:
                rows[0]["Config"]["Entrypoint"] = ["/bin/sh"]
            data = json.dumps(rows).encode()
            return DockerCommandResult("passed", 0, data, b"", len(data), 0)
        return result

    result = observe(tmp_path, cfg, executor)
    assert result.status == "unavailable"
    assert result.cleanup_status == "not_created"
    assert not any(call[1] == "create" for call in docker.calls)


@pytest.mark.parametrize("mutation", ["owner", "id", "name", "image"])
def test_foreign_container_is_never_stopped_or_removed(
    tmp_path: Path, mutation: str
) -> None:
    cfg = request(tmp_path)
    docker = Docker(cfg)
    original = docker.container

    def foreign():
        row = original()
        if mutation == "owner":
            row["Config"]["Labels"]["cppulse.owner"] = "foreign"
        elif mutation == "id":
            row["Id"] = "f" * 64
        elif mutation == "name":
            row["Name"] = "/foreign"
        else:
            row["Image"] = "sha256:" + "f" * 64
        return row

    docker.container = foreign
    result = observe(tmp_path, cfg, docker)
    assert result.status == "unknown"
    assert result.cleanup_status == "unknown"
    assert not any(
        call[1] in {"stop", "rm", "start", "cp", "exec"} for call in docker.calls
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "writable",
        "network",
        "privileged",
        "bind",
        "environment",
        "caps",
        "ports",
        "tmpfs",
        "command",
    ],
)
def test_actual_container_configuration_is_checked_before_start(
    tmp_path: Path, mutation: str
) -> None:
    cfg = request(tmp_path)
    docker = Docker(cfg)
    original = docker.container

    def modified():
        row = original()
        host = row["HostConfig"]
        if mutation == "writable":
            host["ReadonlyRootfs"] = False
        elif mutation == "network":
            host["NetworkMode"] = "host"
        elif mutation == "privileged":
            host["Privileged"] = True
        elif mutation == "bind":
            host["Binds"] = ["/host:/input"]
        elif mutation == "environment":
            row["Config"]["Env"].append("HIDDEN=1")
        elif mutation == "caps":
            host["CapAdd"] = ["SYS_ADMIN"]
        elif mutation == "ports":
            host["PortBindings"] = {"80/tcp": [{}]}
        elif mutation == "tmpfs":
            host["Tmpfs"] = {"/output": "size=1g"}
        else:
            row["Config"]["Cmd"] = ["/other"]
        return row

    docker.container = modified
    result = observe(tmp_path, cfg, docker)
    assert result.status == "unknown"
    assert result.cleanup_status == "removed"
    assert not any(call[1] in {"start", "cp", "exec"} for call in docker.calls)


@pytest.mark.parametrize("selected", ["native", "supervisor"])
def test_selected_inside_image_bytes_are_checked_before_start(
    tmp_path: Path, selected: str
) -> None:
    cfg = request(tmp_path)
    docker = Docker(cfg)

    def executor(argv, timeout, limit):
        result = docker(argv, timeout, limit)
        target = (
            ":/runtime/native"
            if selected == "native"
            else ":/cppulse-runtime-supervisor"
        )
        if argv[1] == "cp" and argv[2].endswith(target):
            data = archive(
                {
                    "native"
                    if selected == "native"
                    else "cppulse-runtime-supervisor": b"different bytes"
                }
            )
            return DockerCommandResult("passed", 0, data, b"", len(data), 0)
        return result

    result = observe(tmp_path, cfg, executor)
    assert result.status == "unknown"
    assert result.cleanup_status == "removed"
    assert not any(call[1] == "start" for call in docker.calls)


@pytest.mark.parametrize("operation", ["create", "start"])
def test_client_timeout_is_resolved_by_actual_owned_state(
    tmp_path: Path, operation: str
) -> None:
    cfg = request(tmp_path)
    docker = Docker(cfg)

    def executor(argv, timeout, limit):
        result = docker(argv, timeout, limit)
        if argv[1] == operation:
            return DockerCommandResult(
                "timed_out", None, b"", b"client deadline", 0, 15
            )
        return result

    result = observe(tmp_path, cfg, executor)
    assert result.status == "unknown"
    assert result.container_id == CID
    assert result.cleanup_status == "removed"
    assert any(
        receipt.status == "timed_out" and receipt.returncode is None
        for receipt in result.commands
    )
    if operation == "start":
        stop = next(i for i, call in enumerate(docker.calls) if call[1] == "stop")
        assert docker.calls[stop - 1] == [cfg["client"]["path"], "inspect", CID]
        assert docker.calls[stop + 1] == [cfg["client"]["path"], "inspect", CID]


@pytest.mark.parametrize("operation", ["stop", "rm"])
def test_cleanup_failure_preserves_observed_native_and_unknown_cleanup(
    tmp_path: Path, operation: str
) -> None:
    cfg = request(tmp_path)
    docker = Docker(cfg)

    def executor(argv, timeout, limit):
        if argv[1] == operation:
            docker.calls.append(argv)
            return DockerCommandResult("timed_out", None, b"", b"deadline", 0, 8)
        return docker(argv, timeout, limit)

    result = observe(tmp_path, cfg, executor)
    assert result.status == "observed"
    assert result.cleanup_status == "unknown"
    assert result.output_archive.is_file()
    if operation == "stop":
        assert docker.running is True
        assert not any(call[1] == "rm" for call in docker.calls)


@pytest.mark.parametrize(
    "status,expected",
    [
        ({"native_exit_code": 127, "native_exec_errno": 2}, "exec_failed"),
        ({"native_exit_code": 5}, "native_failed"),
        ({"native_exit_code": None, "native_signal": 9}, "native_failed"),
    ],
)
def test_native_failure_is_not_a_successful_client_receipt(
    tmp_path: Path, status: dict, expected: str
) -> None:
    cfg = request(tmp_path)
    docker = Docker(cfg)
    docker.status.update(status)
    result = observe(tmp_path, cfg, docker)
    assert result.status == expected
    assert result.cleanup_status == "removed"


@pytest.mark.parametrize(
    "status",
    [
        {"native_exit_code": True},
        {"native_exec_errno": 2},
        {"native_exit_code": None},
        {"native_signal": 9},
        {"version": "other"},
    ],
)
def test_malformed_supervisor_status_never_proves_native_exit(
    tmp_path: Path, status: dict
) -> None:
    cfg = request(tmp_path)
    docker = Docker(cfg)
    docker.status.update(status)
    result = observe(tmp_path, cfg, docker)
    assert result.status == "unknown"
    assert result.native_exit_code is None
    assert result.output_archive is None


def test_status_polling_is_bounded_and_keeps_owned_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.frozen_container as module

    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    cfg = request(tmp_path)
    docker = Docker(cfg)
    polls = []

    def executor(argv, timeout, limit):
        if argv[1:] == [
            "exec",
            CID,
            "/cppulse-runtime-supervisor",
            "--read-status",
            "/output/.cppulse-native-status.json",
        ]:
            docker.calls.append(argv)
            polls.append(argv)
            return DockerCommandResult("failed", 1, b"", b"not found", 0, 9)
        return docker(argv, timeout, limit)

    result = observe(tmp_path, cfg, executor)
    assert result.status == "unknown"
    assert len(polls) == 8
    assert len(result.commands) <= 32
    assert result.cleanup_status == "removed"


@pytest.mark.parametrize("foreign_snapshot", [False, True])
def test_unknown_native_keeps_unqualified_output_and_still_cleans_owned_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, foreign_snapshot: bool
) -> None:
    import cppulse.frozen_container as module

    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    cfg = request(tmp_path)
    docker = Docker(cfg)
    snapshot = tmp_path / "evidence/unqualified-output.tar"

    def executor(argv, timeout, limit):
        if argv[1:] == [
            "exec",
            CID,
            "/cppulse-runtime-supervisor",
            "--read-status",
            "/output/.cppulse-native-status.json",
        ]:
            docker.calls.append(argv)
            return DockerCommandResult("failed", 1, b"", b"pending", 0, 7)
        result = docker(argv, timeout, limit)
        if foreign_snapshot and argv[1] == "create":
            snapshot.write_bytes(b"foreign-snapshot")
        return result

    result = observe(tmp_path, cfg, executor)
    assert result.status == "unknown" and result.native_exit_code is None
    assert result.output_archive is None and result.cleanup_status == "removed"
    if foreign_snapshot:
        assert snapshot.read_bytes() == b"foreign-snapshot"
    else:
        with tarfile.open(snapshot, "r:") as preserved:
            assert (
                preserved.extractfile(".cppulse-native.stdout").read()
                == b"actual native log"
            )


@pytest.mark.parametrize(
    "mutation", ["oversize", "traversal", "entries", "different_status"]
)
def test_output_is_bounded_and_not_extracted(tmp_path: Path, mutation: str) -> None:
    cfg = request(tmp_path)
    docker = Docker(cfg)
    if mutation == "entries":
        cfg["limits"]["max_entries"] = 1

    def executor(argv, timeout, limit):
        result = docker(argv, timeout, limit)
        if argv[1:] == [
            "exec",
            CID,
            "/cppulse-runtime-supervisor",
            "--archive-output",
            "/output",
        ]:
            if mutation == "oversize":
                data = b"x" * 70000
            elif mutation == "traversal":
                data = archive({"../escape": b"x"})
            elif mutation == "different_status":
                changed = {**docker.status, "native_exit_code": 1}
                data = archive(
                    {".cppulse-native-status.json": json.dumps(changed).encode()}
                )
            else:
                return result
            return DockerCommandResult("passed", 0, data, b"", len(data), 0)
        return result

    result = observe(tmp_path, cfg, executor)
    assert result.status == "unknown"
    assert result.output_archive is None
    assert result.cleanup_status == "removed"
    assert not (tmp_path / "escape").exists()
    assert all(
        row.stdout_path.stat().st_size + row.stderr_path.stat().st_size
        <= cfg["limits"]["max_stream_bytes"]
        for row in result.commands
    )


def test_invalid_request_or_mutable_image_never_calls_executor(tmp_path: Path) -> None:
    cfg = request(tmp_path)
    calls = []
    with pytest.raises(ContractError):
        observe_frozen_native(
            cfg,
            "latest",
            tmp_path / "evidence",
            supervisor_sha256="a" * 64,
            executor=lambda *args: calls.append(args),
        )
    assert not calls
    assert not (tmp_path / "evidence").exists()


@pytest.mark.parametrize("broken", ["exception", "invalid_receipt"])
def test_executor_failure_preserves_attempt_without_forged_exit(
    tmp_path: Path, broken: str
) -> None:
    cfg = request(tmp_path)

    def executor(*args):
        if broken == "exception":
            raise RuntimeError("injected transport failure")
        return {"invented": "receipt"}

    result = observe(tmp_path, cfg, executor)
    assert result.status == "unavailable"
    assert result.commands[0].returncode is None
    assert result.commands[0].status == "error"
    assert (tmp_path / "evidence" / "command-001.intent.json").is_file()
    assert (tmp_path / "evidence" / "command-001.json").is_file()


def test_status_can_become_available_on_later_bounded_poll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.frozen_container as module

    monkeypatch.setattr(module.time, "sleep", lambda _: None)
    cfg = request(tmp_path)
    docker = Docker(cfg)
    polls = []

    def executor(argv, timeout, limit):
        if argv[1:] == [
            "exec",
            CID,
            "/cppulse-runtime-supervisor",
            "--read-status",
            "/output/.cppulse-native-status.json",
        ]:
            polls.append(argv)
            if len(polls) == 1:
                docker.calls.append(argv)
                return DockerCommandResult("failed", 1, b"", b"not found", 0, 9)
        return docker(argv, timeout, limit)

    assert observe(tmp_path, cfg, executor).status == "observed"
    assert len(polls) == 2


def test_default_executor_is_wired_to_frozen_local_daemon_and_bounded_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.frozen_container as module
    from types import SimpleNamespace

    cfg = request(tmp_path)
    docker = Docker(cfg)
    environments = []
    monkeypatch.setenv("DOCKER_HOST", "unix:///owned/docker.sock")
    monkeypatch.setenv("DOCKER_CONTEXT", "ambient-remote-context")
    ambient = tmp_path / "ambient-client-config"
    ambient.mkdir()
    foreign_settings = b'{"proxies":{"default":{"httpProxy":"http://ambient.invalid"}}}'
    (ambient / "config.json").write_bytes(foreign_settings)
    monkeypatch.setenv("DOCKER_CONFIG", str(ambient))

    def bounded(argv, **kwargs):
        environments.append(kwargs["environment"])
        result = docker(argv, kwargs["timeout_seconds"], kwargs["limits"].max_log_bytes)
        kwargs["stdout"].write(result.stdout)
        kwargs["stderr"].write(result.stderr)
        monkeypatch.setenv("DOCKER_HOST", "tcp://changed.invalid:1234")
        return SimpleNamespace(
            status=result.status,
            returncode=result.returncode,
            stdout_bytes=result.stdout_bytes,
            stderr_bytes=result.stderr_bytes,
            limitations=[],
        )

    monkeypatch.setattr(module, "run_bounded_process", bounded)
    result = observe_frozen_native(
        cfg,
        IMAGE,
        tmp_path / "evidence",
        supervisor_sha256=hashlib.sha256(HELPER).hexdigest(),
    )
    assert result.status == "observed"
    assert all(
        env
        == {
            "DOCKER_HOST": "unix:///owned/docker.sock",
            "DOCKER_CONTEXT": "",
            "DOCKER_CONFIG": str(tmp_path / "evidence/docker-client-config"),
        }
        for env in environments
    )
    selected = tmp_path / "evidence/docker-client-config"
    assert selected.is_dir() and not selected.is_symlink()
    assert selected.stat().st_mode & 0o777 == 0o700
    assert list(selected.iterdir()) == []
    assert (ambient / "config.json").read_bytes() == foreign_settings


@pytest.mark.parametrize("mutation", ["file", "directory", "symlink"])
def test_private_client_configuration_change_prevents_container_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    import cppulse.frozen_container as module
    from types import SimpleNamespace

    cfg = request(tmp_path)
    docker = Docker(cfg)
    foreign = tmp_path / "foreign-config"
    foreign.mkdir()
    sentinel = foreign / "config.json"
    sentinel.write_bytes(b"foreign-settings")

    def bounded(argv, **kwargs):
        result = docker(argv, kwargs["timeout_seconds"], kwargs["limits"].max_log_bytes)
        selected = Path(kwargs["environment"]["DOCKER_CONFIG"])
        if argv[1:3] == ["image", "inspect"]:
            if mutation == "file":
                (selected / "config.json").write_bytes(b"changed-settings")
            else:
                selected.rename(selected.with_name("retired-config"))
                if mutation == "directory":
                    selected.mkdir(mode=0o700)
                else:
                    selected.symlink_to(foreign, target_is_directory=True)
        kwargs["stdout"].write(result.stdout)
        kwargs["stderr"].write(result.stderr)
        return SimpleNamespace(
            status=result.status,
            returncode=result.returncode,
            stdout_bytes=result.stdout_bytes,
            stderr_bytes=result.stderr_bytes,
            limitations=[],
        )

    monkeypatch.setattr(module, "run_bounded_process", bounded)
    result = observe_frozen_native(
        cfg,
        IMAGE,
        tmp_path / "evidence",
        supervisor_sha256=hashlib.sha256(HELPER).hexdigest(),
    )
    assert result.status in {"unknown", "unavailable"}
    assert not any(call[1] in {"create", "start"} for call in docker.calls)
    assert sentinel.read_bytes() == b"foreign-settings"


def test_default_remote_daemon_is_rejected_without_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCKER_HOST", "tcp://remote.invalid:1234")
    cfg = request(tmp_path)
    with pytest.raises(ContractError, match="Unix"):
        observe_frozen_native(
            cfg, IMAGE, tmp_path / "evidence", supervisor_sha256="a" * 64
        )
    assert not (tmp_path / "evidence").exists()


def test_client_pin_change_does_not_execute_unchecked_client(tmp_path: Path) -> None:
    cfg = request(tmp_path)
    docker = Docker(cfg)

    def executor(argv, timeout, limit):
        result = docker(argv, timeout, limit)
        Path(cfg["client"]["path"]).write_bytes(b"changed")
        return result

    result = observe(tmp_path, cfg, executor)
    assert result.status == "unknown"
    assert len(docker.calls) == 1
    assert result.cleanup_status == "unknown"
    assert any("client" in note.lower() for note in result.limitations)


def test_existing_evidence_is_never_overwritten(tmp_path: Path) -> None:
    cfg = request(tmp_path)
    directory = tmp_path / "evidence"
    directory.mkdir()
    (directory / "keep").write_bytes(b"retained")
    with pytest.raises(ContractError):
        observe(tmp_path, cfg, Docker(cfg))
    assert (directory / "keep").read_bytes() == b"retained"


def linked_output(
    status: dict, *, target: str = "witness", chain: bool = False, forward: bool = False
) -> bytes:
    stream = io.BytesIO()
    data = json.dumps(status).encode()
    with tarfile.open(fileobj=stream, mode="w") as tar:
        regular = tarfile.TarInfo("witness")
        regular.size = len(data)
        if not forward:
            tar.addfile(regular, io.BytesIO(data))
        if chain:
            link = tarfile.TarInfo("middle")
            link.type = tarfile.LNKTYPE
            link.linkname = "witness"
            tar.addfile(link)
        link = tarfile.TarInfo(".cppulse-native-status.json")
        link.type = tarfile.LNKTYPE
        link.linkname = target
        tar.addfile(link)
        if forward:
            tar.addfile(regular, io.BytesIO(data))
    return stream.getvalue()


def test_status_hardlink_resolves_prior_regular_without_extraction(
    tmp_path: Path,
) -> None:
    cfg = request(tmp_path)
    docker = Docker(cfg)

    def executor(argv, timeout, limit):
        result = docker(argv, timeout, limit)
        if argv[1:] == [
            "exec",
            CID,
            "/cppulse-runtime-supervisor",
            "--archive-output",
            "/output",
        ]:
            data = linked_output(docker.status)
            return DockerCommandResult("passed", 0, data, b"", len(data), 0)
        return result

    result = observe(tmp_path, cfg, executor)
    assert result.status == "observed"
    assert result.output_archive.is_file()
    assert not (tmp_path / "witness").exists()


@pytest.mark.parametrize(
    "target,chain,forward",
    [
        ("../outside", False, False),
        ("/outside", False, False),
        ("middle", True, False),
        ("witness", False, True),
    ],
)
def test_output_hardlink_escape_chain_and_forward_targets_reject(
    tmp_path: Path, target: str, chain: bool, forward: bool
) -> None:
    cfg = request(tmp_path)
    docker = Docker(cfg)

    def executor(argv, timeout, limit):
        result = docker(argv, timeout, limit)
        if argv[1:] == [
            "exec",
            CID,
            "/cppulse-runtime-supervisor",
            "--archive-output",
            "/output",
        ]:
            data = linked_output(
                docker.status, target=target, chain=chain, forward=forward
            )
            return DockerCommandResult("passed", 0, data, b"", len(data), 0)
        return result

    result = observe(tmp_path, cfg, executor)
    assert result.status == "unknown"
    assert result.output_archive is None


@pytest.mark.parametrize("rebind_parent", [False, True])
def test_retired_owned_directory_keeps_cleanup_evidence_without_foreign_mutation(
    tmp_path: Path, rebind_parent: bool
) -> None:
    cfg = request(tmp_path)
    docker = Docker(cfg)
    parent = tmp_path / "evidence-parent"
    parent.mkdir()
    evidence = parent / "evidence"
    retired = tmp_path / "retired"
    rebound = False

    def executor(argv, timeout, limit):
        nonlocal rebound
        result = docker(argv, timeout, limit)
        if argv[1] == "start" and not rebound:
            rebound = True
            if rebind_parent:
                parent.rename(retired)
                parent.mkdir()
                evidence.mkdir()
            else:
                evidence.rename(retired)
                evidence.mkdir()
            (evidence / "command-007.stdout").write_bytes(b"foreign sentinel")
        return result

    result = observe_frozen_native(
        cfg,
        IMAGE,
        evidence,
        supervisor_sha256=hashlib.sha256(HELPER).hexdigest(),
        executor=executor,
    )
    actual = retired / "evidence" if rebind_parent else retired
    assert result.status == "unknown" and result.cleanup_status == "removed"
    assert {p.name: p.read_bytes() for p in evidence.iterdir()} == {
        "command-007.stdout": b"foreign sentinel"
    }
    assert any(row.argv[1] == "stop" for row in result.commands)
    assert any(row.argv[1] == "rm" for row in result.commands)
    for row in result.commands:
        assert row.stdout_path.parent == actual and row.stdout_path.is_file()
        assert row.stderr_path.parent == actual and row.stderr_path.is_file()
    assert (actual / "request.json").is_file()


def test_precreated_artifact_is_not_overwritten(tmp_path: Path) -> None:
    cfg = request(tmp_path)
    docker = Docker(cfg)
    sentinel = tmp_path / "evidence" / "command-001.stdout"

    def executor(argv, timeout, limit):
        result = docker(argv, timeout, limit)
        if argv[1:3] == ["image", "inspect"]:
            sentinel.write_bytes(b"foreign precreated artifact")
        return result

    result = observe(tmp_path, cfg, executor)
    assert result.status == "unavailable"
    assert sentinel.read_bytes() == b"foreign precreated artifact"


def test_client_pin_work_cannot_reuse_an_expired_launch_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.frozen_container as module

    cfg = request(tmp_path)
    docker = Docker(cfg)
    clock = [0.0]
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])

    def delayed_pin(_request):
        clock[0] += 20.0

    monkeypatch.setattr(module, "_client_pin", delayed_pin)
    result = observe(tmp_path, cfg, docker)
    assert result.status == "unavailable"
    assert docker.calls == []
