"""Owned Docker observations; never a native host-PID or closure certificate."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import time
from typing import Callable
from uuid import uuid4

from cppulse.contracts.frozen_input import validate_frozen_input
from cppulse.errors import ContractError
from cppulse.execution import ProcessLimits, run_bounded_process
from cppulse.frozen_input import _identity, _open_root
from cppulse.identities import canonical_json_bytes

HELPER = "/cppulse-runtime-supervisor"
STATUS = "/output/.cppulse-native-status.json"
TMPFS = "rw,nosuid,nodev,noexec,size=33554432,mode=0700,uid=1000,gid=1000"


@dataclass(frozen=True)
class DockerCommandResult:
    """Bounded executor output with observed drain counts, not invented exits."""

    status: str
    returncode: int | None
    stdout: bytes
    stderr: bytes
    stdout_bytes: int
    stderr_bytes: int
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class DockerCommandReceipt:
    """Actual client argv and retained bounded raw evidence for one attempt."""

    argv: tuple[str, ...]
    status: str
    returncode: int | None
    stdout_path: Path | None
    stderr_path: Path | None
    stdout_bytes: int
    stderr_bytes: int
    retained_stdout_bytes: int
    retained_stderr_bytes: int
    truncated: bool
    wall_seconds: float


@dataclass(frozen=True)
class ContainerObservation:
    """Finite lifecycle facts, explicitly outside native receipt/cache authority."""

    image_id: str
    container_id: str | None
    status: str
    native_exit_code: int | None
    native_signal: int | None
    native_exec_errno: int | None
    cleanup_status: str
    commands: tuple[DockerCommandReceipt, ...]
    output_archive: Path | None
    limitations: tuple[str, ...]
    execution_ready: bool = False
    cache_eligible: bool = False
    closure: str = "unqualified"


Executor = Callable[[list[str], float, int], DockerCommandResult]


def _integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class _Evidence:
    """Keep writes on the selected directory inode even after a hostile rename."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        parent = _open_root(str(directory.parent))
        try:
            os.mkdir(directory.name, mode=0o700, dir_fd=parent)
            created = os.stat(directory.name, dir_fd=parent, follow_symlinks=False)
            self.fd = os.open(
                directory.name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=parent,
            )
            try:
                self.selected = os.fstat(self.fd)
                if self.identity(created) != self.identity(self.selected):
                    raise ContractError("Evidence directory changed during selection")
                self.check()
            except BaseException:
                os.close(self.fd)
                raise
        finally:
            os.close(parent)

    @staticmethod
    def identity(info: os.stat_result) -> tuple[int, int, int]:
        return info.st_dev, info.st_ino, info.st_mode

    def check(self) -> None:
        try:
            current = _open_root(str(self.directory))
            try:
                matches = self.identity(os.fstat(current)) == self.identity(
                    self.selected
                )
            finally:
                os.close(current)
        except OSError as error:
            raise ContractError("Owned evidence pathname became unavailable") from error
        if not matches:
            raise ContractError(
                "Owned evidence pathname was rebound; original descriptor retained"
            )

    def write(self, name: str, content: bytes) -> Path:
        if not name or "/" in name or name in {".", ".."}:
            raise ContractError("Evidence member needs one canonical name")
        fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=self.fd,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        return self.directory / name

    def location(self) -> Path | None:
        # Linux procfs supplies the current name of a retired-but-held inode.
        # Return no path if the host no longer exposes a checked readable name.
        for candidate in (str(self.directory), f"/proc/self/fd/{self.fd}"):
            try:
                value = (
                    Path(os.readlink(candidate))
                    if candidate.startswith("/proc/")
                    else Path(candidate)
                )
                current = _open_root(str(value))
                try:
                    if self.identity(os.fstat(current)) == self.identity(self.selected):
                        return value
                finally:
                    os.close(current)
            except (OSError, ValueError):
                continue
        return None

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        os.close(self.fd)


def _json(raw: bytes):
    def pairs(rows: list[tuple]) -> dict:
        result = {}
        for key, value in rows:
            if key in result:
                raise ContractError("Duplicate Docker/status JSON field")
            result[key] = value
        return result

    def bad(value: str) -> None:
        raise ContractError("Nonfinite Docker/status JSON")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)


def _client_pin(request: dict) -> None:
    selected = request["client"]
    path = Path(selected["path"])
    parent = _open_root(str(path.parent))
    try:
        fd = os.open(
            path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
        try:
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_size != selected["size_bytes"]
            ):
                raise ContractError("Docker client differs from selected regular bytes")
            digest = hashlib.sha256()
            size = 0
            while block := os.read(fd, 1024 * 1024):
                size += len(block)
                if size > selected["size_bytes"]:
                    raise ContractError("Docker client grew during hashing")
                digest.update(block)
            if (
                size != selected["size_bytes"]
                or digest.hexdigest() != selected["sha256"]
                or _identity(os.fstat(fd)) != _identity(before)
                or _identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False))
                != _identity(before)
            ):
                raise ContractError("Docker client pin changed")
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def _execute(
    argv: list[str],
    timeout_seconds: float,
    max_stream_bytes: int,
    *,
    daemon_host: str,
    client_config: Path,
) -> DockerCommandResult:
    stdout, stderr = io.BytesIO(), io.BytesIO()
    try:
        result = run_bounded_process(
            argv,
            cwd=Path.cwd(),
            stdout=stdout,
            stderr=stderr,
            timeout_seconds=timeout_seconds,
            limits=ProcessLimits(max_log_bytes=max_stream_bytes),
            environment={
                "DOCKER_HOST": daemon_host,
                "DOCKER_CONTEXT": "",
                "DOCKER_CONFIG": str(client_config),
            },
        )
    except KeyboardInterrupt:
        # Process supervision kills its owned client process group in finally.
        # The daemon may still finish a create; these are only retained client
        # bytes, never complete drain counts or a native/container exit proof.
        raw_stdout, raw_stderr = stdout.getvalue(), stderr.getvalue()
        return DockerCommandResult(
            "cancelled",
            None,
            raw_stdout,
            raw_stderr,
            len(raw_stdout),
            len(raw_stderr),
            (
                "Client interrupted by KeyboardInterrupt; byte counts cover retained bytes only, full drain counts and daemon completion are unknown.",
            ),
        )
    return DockerCommandResult(
        result.status,
        result.returncode,
        stdout.getvalue(),
        stderr.getvalue(),
        result.stdout_bytes,
        result.stderr_bytes,
        tuple(result.limitations),
    )


def _file_archive(
    raw: bytes,
    name: str,
    *,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        member = archive.next()
        if (
            member is None
            or not member.isfile()
            or member.name != name
            or member.size > 16777216
        ):
            raise ContractError(
                "Docker file archive has unsupported identity/type/size"
            )
        content = archive.extractfile(member).read(16777217)
        if len(content) != member.size or archive.next() is not None:
            raise ContractError("Docker file archive is incomplete or ambiguous")
    if (expected_size is not None and len(content) != expected_size) or (
        expected_sha256 is not None
        and hashlib.sha256(content).hexdigest() != expected_sha256
    ):
        raise ContractError("Container file differs from selected SHA/size")
    return content


def _native_status(raw: bytes) -> dict:
    if len(raw) > 4096:
        raise ContractError("Supervisor status exceeds byte bound")
    value = _json(raw)
    if (
        not isinstance(value, dict)
        or set(value)
        != {"version", "native_exit_code", "native_signal", "native_exec_errno"}
        or value["version"] != "0.1.0"
    ):
        raise ContractError("Unsupported supervisor status")
    code, signal, errno = (
        value[key] for key in ("native_exit_code", "native_signal", "native_exec_errno")
    )
    if (
        (code is not None and (not _integer(code) or not 0 <= code <= 255))
        or (signal is not None and (not _integer(signal) or not 1 <= signal <= 64))
        or (errno is not None and (not _integer(errno) or not 1 <= errno <= 4095))
        or (code is None) == (signal is None)
        or (errno is not None and code != 127)
    ):
        raise ContractError("Supervisor native exit/signal/exec status is inconsistent")
    return value


def _output(raw: bytes, request: dict, expected_status: dict) -> tuple[dict, ...]:
    seen, total, status, regulars, metadata = set(), 0, None, {}, []

    def canonical(name: str) -> str:
        while name.startswith("./"):
            name = name[2:]
        path = PurePosixPath(name)
        if (
            not name
            or path.is_absolute()
            or ".." in path.parts
            or "\x00" in name
            or (name != "." and str(path) != name)
            or len(name.encode("utf-8")) > 4096
        ):
            raise ContractError("Output archive has unsafe member/link identity")
        return name

    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:") as archive:
        for member in archive:
            name = canonical(member.name)
            if (
                name in seen
                or (name == "." and not member.isdir())
                or not (member.isfile() or member.isdir() or member.islnk())
            ):
                raise ContractError("Output archive has unsafe/ambiguous entries")
            seen.add(name)
            total += member.size
            if len(seen) > request["limits"]["max_entries"] or total > min(
                33554432, request["limits"]["max_payload_bytes"]
            ):
                raise ContractError("Output archive exceeds entry/payload budget")
            content, target = None, None
            if member.isfile():
                content = (
                    archive.extractfile(member).read(member.size)
                    if member.size <= 4096
                    else None
                )
                regulars[name] = (member.size, content)
            elif member.islnk():
                target = canonical(member.linkname)
                if member.size != 0 or target not in regulars:
                    raise ContractError(
                        "Output hardlink requires a prior regular archive member; chains/forward/outside targets refused"
                    )
                _, content = regulars[target]
            if name == ".cppulse-native-status.json":
                if content is None:
                    raise ContractError(
                        "Output supervisor status is not a bounded regular-file identity"
                    )
                status = _native_status(content)
            metadata.append(
                {
                    "path": name,
                    "kind": "hardlink"
                    if member.islnk()
                    else "regular"
                    if member.isfile()
                    else "directory",
                    "size_bytes": member.size,
                    "target": member.linkname if member.islnk() else None,
                    "resolved_target": target,
                }
            )
    if status != expected_status:
        raise ContractError(
            "Output archive does not preserve selected supervisor status"
        )
    return tuple(metadata)


def observe_frozen_native(
    request: dict,
    image_id: str,
    evidence_directory: Path,
    *,
    supervisor_sha256: str,
    executor: Executor | None = None,
) -> ContainerObservation:
    """Observe an immutable image in one owned container with bounded cleanup.

    Native time is bounded by the request wall budget. Cleanup has a separate
    maximum eight-second grace; client timeout never proves a container stopped.
    All controller tests inject the executor; default execution is explicit Docker.
    """
    request = deepcopy(request)
    validate_frozen_input("request", request)
    if (
        not isinstance(image_id, str)
        or not isinstance(supervisor_sha256, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None
        or re.fullmatch(r"[0-9a-f]{64}", supervisor_sha256) is None
    ):
        raise ContractError("Immutable image and supervisor SHA256 pins are required")
    if any(
        PurePosixPath(row["container_root"]) == PurePosixPath("/output")
        or PurePosixPath("/output") in PurePosixPath(row["container_root"]).parents
        for row in request["path_map"]
    ):
        raise ContractError("Output tmpfs cannot shadow selected frozen inputs")
    daemon_host = os.environ.get("DOCKER_HOST") or "unix:///var/run/docker.sock"
    if executor is None and (
        not daemon_host.startswith("unix:///") or "\x00" in daemon_host
    ):
        raise ContractError(
            "Default controller requires an explicit local Unix Docker endpoint"
        )
    directory = Path(evidence_directory).absolute()
    try:
        with _Evidence(directory) as evidence:
            return _observe_owned(
                request, image_id, supervisor_sha256, executor, daemon_host, evidence
            )
    except OSError as error:
        raise ContractError(
            "Docker evidence requires an owned new nofollow directory"
        ) from error


def _observe_owned(
    request: dict,
    image_id: str,
    supervisor_sha256: str,
    executor: Executor | None,
    daemon_host: str,
    evidence: _Evidence,
) -> ContainerObservation:
    directory = evidence.directory
    evidence.write("request.json", canonical_json_bytes(request))
    owner, name = uuid4().hex, "cppulse-owned-" + uuid4().hex
    evidence.write(
        "container-owner.json",
        canonical_json_bytes(
            {
                "version": "0.1.0",
                "owner": owner,
                "name": name,
                "image_id": image_id,
                "qualification": "Local cleanup selectors only; creation and ownership require observed command/inspect evidence.",
            }
        ),
    )
    client = request["client"]["path"]
    config_identity = None
    if executor is None:
        os.mkdir("docker-client-config", mode=0o700, dir_fd=evidence.fd)
        config_identity = _Evidence.identity(
            os.stat("docker-client-config", dir_fd=evidence.fd, follow_symlinks=False)
        )
        evidence.write(
            "client-settings.json",
            canonical_json_bytes(
                {
                    "daemon_endpoint": daemon_host,
                    "configuration": "owned_empty_directory",
                    "ambient_configuration_used": False,
                }
            ),
        )

    def default_executor(
        argv: list[str], timeout: float, cap: int
    ) -> DockerCommandResult:
        selected = os.open(
            "docker-client-config",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=evidence.fd,
        )
        try:
            if _Evidence.identity(os.fstat(selected)) != config_identity or os.listdir(
                selected
            ):
                raise ContractError("Owned Docker client configuration changed")
            location = evidence.location()
            if location is None:
                raise ContractError(
                    "Owned Docker client configuration has no checked pathname"
                )
            return _execute(
                argv,
                timeout,
                cap,
                daemon_host=daemon_host,
                client_config=location / "docker-client-config",
            )
        finally:
            os.close(selected)

    invoke = executor or default_executor
    commands, limitations = (
        [],
        [
            "Container client/status observations are not authenticated native host-PID receipts, loader closure or cgroup enforcement evidence.",
            "Supervisor and native share the output UID; status is not hostile-native-proof.",
            "Cleanup uses a separate eight-second command scheduling budget; Python/filesystem work and process-supervision termination grace are additional.",
            "Native stdout/stderr are supervised output files; they are observed only when the bounded inside-container archive is successfully collected. Docker daemon logging is disabled.",
            "Client hashes are observed before each attempt, not an atomic FD-pinned client exec or daemon authentication.",
        ],
    )
    deadline = time.monotonic() + request["limits"]["wall_seconds"]
    cid, outcome, cleanup, native, output = (
        None,
        "unavailable",
        "not_created",
        None,
        None,
    )
    attempted = False
    attempts = 0

    def call(
        arguments: list[str], *, cleanup_call: bool = False
    ) -> DockerCommandResult:
        nonlocal attempts
        remaining = (cleanup_deadline if cleanup_call else deadline) - time.monotonic()
        if remaining <= 0 or attempts >= (32 if cleanup_call else 28):
            raise ContractError("Docker lifecycle wall/command budget exhausted")
        argv = [client, *arguments]
        start = time.monotonic()
        if not cleanup_call:
            evidence.check()
        attempts += 1
        prefix = f"command-{attempts:03}"
        evidence.write(
            prefix + ".intent.json",
            canonical_json_bytes(
                {"argv": argv, "launch_status": "attempted_not_yet_observed"}
            ),
        )
        try:
            _client_pin(request)
            remaining = (
                cleanup_deadline if cleanup_call else deadline
            ) - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    "Docker scheduling budget exhausted after client pin verification"
                )
            result = invoke(
                argv,
                min(2.0, remaining) if cleanup_call else remaining,
                request["limits"]["max_stream_bytes"],
            )
        except (Exception, KeyboardInterrupt) as error:
            message = (type(error).__name__ + ": " + str(error)).encode()[:1024]
            result = DockerCommandResult(
                "cancelled"
                if isinstance(error, KeyboardInterrupt)
                else "timed_out"
                if isinstance(error, TimeoutError)
                else "error",
                None,
                b"",
                message,
                0,
                len(message),
                (
                    "Executor raised before returning a receipt; stderr contains a generated diagnostic, original client streams and full drain counts are unknown.",
                ),
            )
        if (
            not isinstance(result, DockerCommandResult)
            or result.status
            not in {"passed", "failed", "timed_out", "cancelled", "error"}
            or not isinstance(result.stdout, bytes)
            or not isinstance(result.stderr, bytes)
            or not _integer(result.stdout_bytes)
            or not _integer(result.stderr_bytes)
            or result.stdout_bytes < len(result.stdout)
            or result.stderr_bytes < len(result.stderr)
            or (
                result.returncode is not None
                and (
                    not _integer(result.returncode)
                    or not -255 <= result.returncode <= 255
                )
            )
        ):
            raw_stdout = getattr(result, "stdout", b"")
            raw_stderr = getattr(result, "stderr", b"")
            raw_stdout = raw_stdout if isinstance(raw_stdout, bytes) else b""
            raw_stderr = raw_stderr if isinstance(raw_stderr, bytes) else b""
            result = DockerCommandResult(
                "error",
                None,
                raw_stdout,
                raw_stderr,
                len(raw_stdout),
                len(raw_stderr),
                (
                    "Invalid executor receipt: raw byte lengths retained; total drain counts and exit are unknown.",
                ),
            )
        cap = request["limits"]["max_stream_bytes"]
        stdout, stderr = (
            result.stdout[:cap],
            result.stderr[: max(0, cap - len(result.stdout))],
        )
        truncated = (
            len(stdout) < result.stdout_bytes or len(stderr) < result.stderr_bytes
        )
        stdout_path, stderr_path = (
            directory / (prefix + ".stdout"),
            directory / (prefix + ".stderr"),
        )
        evidence.write(stdout_path.name, stdout)
        evidence.write(stderr_path.name, stderr)
        receipt = DockerCommandReceipt(
            tuple(argv),
            result.status,
            result.returncode,
            stdout_path,
            stderr_path,
            result.stdout_bytes,
            result.stderr_bytes,
            len(stdout),
            len(stderr),
            truncated,
            time.monotonic() - start,
        )
        commands.append(receipt)
        evidence.write(
            prefix + ".json",
            canonical_json_bytes(
                {
                    "argv": argv,
                    "status": result.status,
                    "returncode": result.returncode,
                    "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                    "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
                    "stdout_bytes": result.stdout_bytes,
                    "stderr_bytes": result.stderr_bytes,
                    "retained_stdout_bytes": len(stdout),
                    "retained_stderr_bytes": len(stderr),
                    "truncated": truncated,
                    "wall_seconds": receipt.wall_seconds,
                    "limitations": list(result.limitations),
                }
            ),
        )
        limitations.extend(result.limitations)
        if not cleanup_call:
            evidence.check()
        return DockerCommandResult(
            result.status,
            result.returncode,
            stdout,
            stderr,
            result.stdout_bytes,
            result.stderr_bytes,
        )

    def good(result: DockerCommandResult) -> bytes:
        if (
            result.status != "passed"
            or result.returncode != 0
            or len(result.stdout) != result.stdout_bytes
            or len(result.stderr) != result.stderr_bytes
        ):
            raise ContractError(
                "Docker command did not produce complete successful evidence"
            )
        return result.stdout

    def owned(*, cleanup_call: bool = False) -> dict:
        nonlocal cid
        # An interrupted create client can return before the daemon publishes
        # its container. Keep failed probes as evidence; never infer no object
        # from a client timeout, and never retry an observed foreign identity.
        for retry in range(4):
            result = call(["inspect", cid or name], cleanup_call=cleanup_call)
            if not (
                cleanup_call
                and cid is None
                and retry < 3
                and result.status == "failed"
                and result.returncode == 1
                and result.stdout.strip() == b"[]"
            ):
                break
            remaining = cleanup_deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(1.0, remaining))
        rows = _json(good(result))
        if not isinstance(rows, list) or len(rows) != 1:
            raise ContractError("Container inspect is absent or ambiguous")
        row = rows[0]
        if (
            not isinstance(row, dict)
            or re.fullmatch(r"[0-9a-f]{64}", row.get("Id", "")) is None
            or (cid is not None and row["Id"] != cid)
            or row.get("Name") != "/" + name
            or row.get("Image") != image_id
            or row.get("Config", {}).get("Labels", {}).get("cppulse.owner") != owner
        ):
            raise ContractError("Container identity/owner differs; cleanup refused")
        cid = row["Id"]
        if not isinstance(row.get("State", {}).get("Running"), bool):
            raise ContractError("Container running state is unknown")
        return row

    def configuration(row: dict) -> None:
        config, host = row["Config"], row["HostConfig"]
        if (
            config.get("Image") != image_id
            or config.get("Entrypoint") != [HELPER, STATUS]
            or config.get("Cmd") != request["invocation"]["argv"]
            or config.get("WorkingDir") != request["invocation"]["cwd"]
            or sorted(config.get("Env") or [])
            != sorted(
                k + "=" + v for k, v in request["invocation"]["environment"].items()
            )
            or config.get("User") != "1000:1000"
            or config.get("Healthcheck", {}).get("Test") != ["NONE"]
            or host.get("ReadonlyRootfs") is not True
            or host.get("NetworkMode") != "none"
            or host.get("Privileged") is not False
            or host.get("CapDrop") != ["ALL"]
            or host.get("CapAdd")
            or host.get("SecurityOpt") != ["no-new-privileges:true"]
            or host.get("Binds")
            or host.get("Mounts")
            or host.get("PortBindings")
            or host.get("Tmpfs") != {"/output": TMPFS}
            or host.get("LogConfig") != {"Type": "none", "Config": {}}
            or any(
                mount.get("Type") != "tmpfs" or mount.get("Destination") != "/output"
                for mount in row.get("Mounts", [])
            )
        ):
            raise ContractError(
                "Observed container configuration differs from bounded request"
            )

    try:
        images = _json(good(call(["image", "inspect", image_id])))
        if (
            not isinstance(images, list)
            or len(images) != 1
            or images[0].get("Id") != image_id
            or images[0].get("Os") != "linux"
            or images[0].get("Architecture") != "amd64"
            or images[0].get("Config", {}).get("Volumes")
            or images[0].get("Config", {}).get("Entrypoint") != [HELPER, STATUS]
        ):
            raise ContractError(
                "Selected immutable image platform/configuration is unavailable"
            )
        arguments = [
            "create",
            "--pull=never",
            "--name",
            name,
            "--label",
            "cppulse.owner=" + owner,
            "--read-only",
            "--network=none",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            "--user=1000:1000",
            "--workdir",
            request["invocation"]["cwd"],
            "--tmpfs",
            "/output:" + TMPFS,
            "--no-healthcheck",
            "--log-driver=none",
        ]
        for key, value in sorted(request["invocation"]["environment"].items()):
            arguments.extend(["--env", key + "=" + value])
        arguments.extend([image_id, *request["invocation"]["argv"]])
        attempted = True
        response = good(call(arguments)).decode("ascii").strip()
        if re.fullmatch(r"[0-9a-f]{64}", response) is None:
            raise ContractError("Create did not return an immutable container ID")
        cid = response
        configuration(owned())
        _file_archive(
            good(call(["cp", cid + ":" + request["invocation"]["argv"][0], "-"])),
            PurePosixPath(request["invocation"]["argv"][0]).name,
            expected_sha256=request["native"]["sha256"],
            expected_size=request["native"]["size_bytes"],
        )
        _file_archive(
            good(call(["cp", cid + ":" + HELPER, "-"])),
            PurePosixPath(HELPER).name,
            expected_sha256=supervisor_sha256,
        )
        good(call(["start", cid]))
        for attempt in range(8):
            row = owned()
            if not row["State"]["Running"] or row["State"].get("Paused") is not False:
                raise ContractError(
                    "Supervisor is not observed running; tmpfs output is unknown"
                )
            status_result = call(["exec", cid, HELPER, "--read-status", STATUS])
            if status_result.status == "passed" and status_result.returncode == 0:
                native = _native_status(good(status_result))
                break
            if status_result.status != "failed" or status_result.returncode != 1:
                raise ContractError("Supervisor status collection did not complete")
            time.sleep(
                min(
                    request["limits"]["wall_seconds"] / 8,
                    max(0, deadline - time.monotonic()),
                )
            )
        if native is None:
            raise ContractError("Supervisor status unavailable within bounded polling")
        if not owned()["State"]["Running"]:
            raise ContractError("Supervisor stopped before tmpfs output collection")
        raw = good(call(["exec", cid, HELPER, "--archive-output", "/output"]))
        entries = _output(raw, request, native)
        evidence.write(
            "output-entries.json", canonical_json_bytes({"entries": list(entries)})
        )
        output = evidence.write("output.tar", raw)
        evidence.check()
        outcome = (
            "exec_failed"
            if native["native_exec_errno"] is not None
            else "observed"
            if native["native_exit_code"] == 0
            else "native_failed"
        )
    except (
        ContractError,
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        tarfile.TarError,
        UnicodeError,
        RecursionError,
    ) as error:
        limitations.append(str(error)[:2048])
        outcome = "unknown" if attempted else "unavailable"
    finally:
        cleanup_deadline = time.monotonic() + 8
        if attempted:
            cleanup = "unknown"
            try:
                row = owned(cleanup_call=True)
                if row["State"]["Running"]:
                    if output is None:
                        try:
                            partial_output = call(
                                ["exec", cid, HELPER, "--archive-output", "/output"],
                                cleanup_call=True,
                            )
                            if (
                                partial_output.status == "passed"
                                and partial_output.returncode == 0
                            ):
                                evidence.write(
                                    "unqualified-output.tar", good(partial_output)
                                )
                                limitations.append(
                                    "An unqualified bounded output snapshot is retained separately from a completed native observation"
                                )
                        except (ContractError, OSError, ValueError, TypeError) as error:
                            limitations.append(
                                "Unqualified output unavailable: " + str(error)[:2048]
                            )
                        row = owned(cleanup_call=True)
                    if row["State"]["Running"]:
                        call(["stop", "--time=1", cid], cleanup_call=True)
                    row = owned(cleanup_call=True)
                if row["State"]["Running"]:
                    raise ContractError(
                        "Owned container remains running after bounded stop"
                    )
                good(call(["rm", cid], cleanup_call=True))
                cleanup = "removed"
            except (
                ContractError,
                OSError,
                ValueError,
                TypeError,
                KeyError,
                AttributeError,
                UnicodeError,
                RecursionError,
            ) as error:
                limitations.append("Cleanup unresolved: " + str(error)[:2048])
    try:
        _client_pin(request)
    except (OSError, ContractError) as error:
        limitations.append("Final client pin unresolved: " + str(error)[:2048])
        outcome = "unknown" if attempted else "unavailable"
    try:
        evidence.check()
    except ContractError as error:
        limitations.append(str(error))
        outcome = "unknown" if attempted else "unavailable"
    location = evidence.location()
    if location is None:
        limitations.append(
            "Held evidence directory has no verified pathname; raw descriptor evidence could not be exposed after closure"
        )
    commands = [
        replace(
            row,
            stdout_path=None if location is None else location / row.stdout_path.name,
            stderr_path=None if location is None else location / row.stderr_path.name,
        )
        for row in commands
    ]
    output = None if output is None or location is None else location / output.name
    return ContainerObservation(
        image_id,
        cid,
        outcome,
        None if native is None else native["native_exit_code"],
        None if native is None else native["native_signal"],
        None if native is None else native["native_exec_errno"],
        cleanup,
        tuple(commands),
        output,
        tuple(dict.fromkeys(limitations)),
    )
