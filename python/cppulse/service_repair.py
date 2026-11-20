"""Explicit trusted C++17 ELF relink and finite loopback-service regression lane.

This separate profile does not extend the ordinary CMake/CTest repair profile.
It never applies a change to the original project or starts/stops a service. It
relinks a copied selected implementation with copied, declared object/library
bytes, then runs one protected probe. Only wall/log supervision is established;
host execution, inherited toolchain and live service state remain trusted.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
from importlib import resources
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
from typing import Any
import uuid

import jsonschema

from cppulse.errors import ContractError, IntegrityError
from cppulse.execution import CancellationToken, ProcessLimits, run_bounded_process
from cppulse.identities import canonical_json_bytes
from cppulse.run_store import _copy_new, _directory, _read, _stream_file

MAX_REQUEST_BYTES = 2 * 1024**2
PROFILE = "cpp17-elf-relink-loopback-v1"
_EXEC_CLEAN = (
    "import os,sys;"
    "blocked={'LD_PRELOAD','LD_LIBRARY_PATH','CPATH','CPLUS_INCLUDE_PATH',"
    "'C_INCLUDE_PATH','GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH',"
    "'DEPENDENCIES_OUTPUT','SUNPRO_DEPENDENCIES','PYTHONPATH','PYTHONHOME'};"
    "env={k:v for k,v in os.environ.items() if k not in blocked};"
    "os.execve(sys.argv[1],sys.argv[1:],env)"
)
QUALIFICATION = {
    "trusted_host_execution": True,
    "service_state_isolation_verified": False,
    "semantic_equivalence_established": False,
    "cpu_enforced": False,
    "memory_enforced": False,
    "cgroup_enforced": False,
    "whole_toolchain_closure_verified": False,
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _validate(document: dict[str, Any], kind: str) -> None:
    schema = json.loads(
        resources.files("cppulse.contracts")
        .joinpath(
            "schemas/service_repair_private",
            kind
            + (
                "-v2.schema.json"
                if isinstance(document, dict) and document.get("version") == "0.2.0"
                else ".schema.json"
            ),
        )
        .read_bytes()
    )
    try:
        jsonschema.Draft7Validator(schema).validate(document)
        canonical_json_bytes(document)
    except (jsonschema.ValidationError, ValueError, TypeError, RecursionError) as exc:
        raise ContractError(f"Invalid service repair {kind}") from exc


def _relative(value: str) -> None:
    path = PurePosixPath(value)
    if (
        str(path) != value
        or not path.parts
        or path.is_absolute()
        or PureWindowsPath(value).drive
        or "\\" in value
        or any(part in ("..", ".git") for part in path.parts)
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise ContractError("Service artifact path must be canonical and relative")


def _materials(request: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    result = [
        ("tools/compiler", request["compiler"]),
        ("tools/docker", request["docker"]),
        ("tools/supervisor-python", request["supervisor_python"]),
        ("before/source.cpp", request["before_source"]),
        ("after/source.cpp", request["after_source"]),
        ("probe.cpp", request["probe"]),
    ]
    for kind in ("headers", "objects", "libraries"):
        result.extend((kind + "/" + row["name"], row["file"]) for row in request[kind])
    return result


def validate_request(request: dict[str, Any]) -> None:
    """Validate finite explicit pins without running tools or project code."""
    _validate(request, "request")
    if request["version"] == "0.2.0":
        from cppulse.service_resources import validate_process_resources

        validate_process_resources(request["process_resources"])
    if len(canonical_json_bytes(request)) > MAX_REQUEST_BYTES:
        raise ContractError("Service repair request exceeds two-MiB bound")
    prefix = Path(request["compiler_search_prefix"])
    if (
        not prefix.is_absolute()
        or ".." in prefix.parts
        or any(ord(c) < 32 or ord(c) == 127 for c in str(prefix))
    ):
        raise ContractError(
            "Compiler helper prefix must be an explicit absolute directory"
        )
    prefix = Path(request["compiler_library_prefix"])
    if (
        not prefix.is_absolute()
        or ".." in prefix.parts
        or any(ord(c) < 32 or ord(c) == 127 for c in str(prefix))
    ):
        raise ContractError(
            "Compiler library prefix must be an explicit absolute directory"
        )
    for value in request["compiler_system_include_directories"]:
        path = Path(value)
        if (
            not path.is_absolute()
            or ".." in path.parts
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
        ):
            raise ContractError(
                "Compiler system includes must be explicit absolute directories"
            )
    names = []
    total = 0
    for name, material in _materials(request):
        _relative(name)
        path = Path(material["path"])
        if (
            not path.is_absolute()
            or ".." in path.parts
            or any(ord(c) < 32 or ord(c) == 127 for c in str(path))
        ):
            raise ContractError("Material paths must be absolute without traversal")
        names.append(name.casefold())
        total += material["size_bytes"]
    if len(names) != len(set(names)):
        raise ContractError("Duplicate or case-alias service material names")
    if total > request["limits"]["input_bytes"]:
        raise ContractError("Declared service input bytes exceed configured bound")
    for kind in ("objects", "libraries"):
        for row in request[kind]:
            pattern = (
                r"[A-Za-z0-9_.-]+\.o"
                if kind == "objects"
                else r"lib[A-Za-z0-9_.-]+\.so\.[0-9]+"
            )
            if re.fullmatch(pattern, row["name"]) is None:
                raise ContractError("Object/library names must be finite ELF basenames")
    if any(not row["name"].endswith(".o") for row in request["objects"]):
        raise ContractError("Relink inputs must be explicit object files")
    if len(request["required_cases"]) != len(set(request["required_cases"])):
        raise ContractError("Duplicate required service cases")
    if len(request["defines"]) != len(set(request["defines"])):
        raise ContractError("Duplicate compiler definitions")
    if request["before_source"]["sha256"] == request["after_source"]["sha256"]:
        raise ContractError("Service proposal must change selected source bytes")
    if request["soname"] in {row["name"] for row in request["libraries"]}:
        raise ContractError("Relink library cannot also be a dependency")


def _strict_json(raw: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result:
                raise ContractError("Duplicate service observation field")
            result[key] = value
        return result

    def constant(value: str) -> Any:
        raise ContractError("Nonfinite service observation")

    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        canonical_json_bytes(result)
        return result
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError("Service observation must be bounded strict JSON") from exc


def _fact(path: Path, root: Path, bound: int = 256 * 1024**2) -> dict[str, Any]:
    size, digest = _stream_file(path, max_bytes=bound)
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": digest,
        "size_bytes": size,
    }


def _sealed_tools(
    request: dict[str, Any], root: Path
) -> tuple[dict[str, Any], list[int]]:
    """Freeze checked selected executable bytes into sealed Linux descriptors."""
    import fcntl

    descriptors: list[int] = []
    tools = {}
    try:
        for key, name in (
            ("compiler", "compiler"),
            ("docker", "docker"),
            ("supervisor_python", "supervisor-python"),
        ):
            fd = os.memfd_create(
                "cppulse-service-" + name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING
            )
            descriptors.append(fd)

            def write(raw: bytes) -> None:
                remaining = memoryview(raw)
                while remaining:
                    count = os.write(fd, remaining)
                    if count <= 0:
                        raise OSError("No progress copying sealed executable")
                    remaining = remaining[count:]

            size, digest = _stream_file(
                root / "inputs/tools" / name,
                write=write,
                max_bytes=request["limits"]["input_bytes"],
            )
            if (size, digest) != (request[key]["size_bytes"], request[key]["sha256"]):
                raise IntegrityError("Selected tool changed before executable freeze")
            os.fchmod(fd, 0o700)
            # Linux UAPI F_ADD_SEALS/F_GET_SEALS, including Python builds which
            # omit the symbolic constants. Flags: SEAL|SHRINK|GROW|WRITE.
            fcntl.fcntl(fd, getattr(fcntl, "F_ADD_SEALS", 1033), 15)
            seals = fcntl.fcntl(fd, getattr(fcntl, "F_GET_SEALS", 1034))
            if seals != 15:
                raise IntegrityError("Selected executable sealing was not established")
            tools[key] = {
                "path": f"/proc/{os.getpid()}/fd/{fd}",
                "sha256": digest,
                "size_bytes": size,
                "seals": seals,
                "method": "linux-sealed-memfd-sha256-v1",
            }
        return tools, descriptors
    except BaseException:
        for fd in descriptors:
            os.close(fd)
        raise


def _commands(
    request: dict[str, Any], root: Path, namespace: str, tools: dict[str, Any]
) -> dict[str, list[str]]:
    inputs = root / "inputs"
    compiler = tools["compiler"]["path"]
    driver = [
        compiler,
        "-B" + request["compiler_search_prefix"],
        "-B" + request["compiler_library_prefix"],
    ]
    libraries = [
        str(inputs / "libraries" / row["name"]) for row in request["libraries"]
    ]
    common = [
        "-std=c++17",
        "-isystem" + str(inputs / "headers"),
        *["-isystem" + path for path in request["compiler_system_include_directories"]],
    ]
    inspect = [
        tools["docker"]["path"],
        "inspect",
        "--type",
        "container",
        request["service"]["container_id"],
    ]
    commands = {"service-before": inspect, "service-after": inspect}
    for lane in ("before", "after"):
        folder = root / lane
        library = folder / request["soname"]
        commands[lane + "-compile"] = [
            *driver,
            *common,
            "-fPIC",
            "-O2",
            "-g",
            "-DNDEBUG",
            *["-D" + value for value in request["defines"]],
            "-c",
            str(inputs / lane / "source.cpp"),
            "-o",
            str(folder / "selected.o"),
        ]
        commands[lane + "-link"] = [
            *driver,
            "-shared",
            "-Wl,-soname," + request["soname"],
            "-o",
            str(library),
            str(folder / "selected.o"),
            *[str(inputs / "objects" / row["name"]) for row in request["objects"]],
            *libraries,
            "-lpthread",
            "-ldl",
            "-lrt",
            "-Wl,-rpath," + str(inputs / "libraries"),
        ]
        commands[lane + "-probe-build"] = [
            *driver,
            *common,
            "-Wall",
            "-Wextra",
            "-Werror",
            str(inputs / "probe.cpp"),
            str(library),
            *libraries,
            "-Wl,-rpath," + str(folder) + ":" + str(inputs / "libraries"),
            "-o",
            str(folder / "probe"),
        ]
        commands[lane + "-test"] = [str(folder / "probe"), namespace + "_" + lane]
    wrapped = {
        key: [tools["supervisor_python"]["path"], "-I", "-c", _EXEC_CLEAN, *argv]
        for key, argv in commands.items()
    }
    if request["version"] == "0.2.0":
        from cppulse.service_resources import RESOURCE_EXEC

        for key, argv in commands.items():
            if key.startswith("service-"):
                continue
            limits = request["process_resources"][
                "test" if key.endswith("-test") else "build"
            ]
            wrapped[key] = [
                tools["supervisor_python"]["path"],
                "-I",
                "-c",
                RESOURCE_EXEC + _EXEC_CLEAN,
                canonical_json_bytes(limits).decode(),
                str(root / "logs" / (key + ".resources.json")),
                key,
                *argv,
            ]
    return wrapped


def _service(raw: bytes, request: dict[str, Any]) -> None:
    value = _strict_json(raw)
    selected = request["service"]
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise ContractError("Service inspect must select exactly one container")
    row = value[0]
    for key in ("Config", "State", "NetworkSettings"):
        if not isinstance(row.get(key), dict):
            raise ContractError("Service inspect has malformed identity objects")
    labels = row["Config"].get("Labels") or {}
    ports = row["NetworkSettings"].get("Ports")
    if not isinstance(labels, dict) or not isinstance(ports, dict):
        raise ContractError("Service inspect has malformed labels or port bindings")
    expected_ports = [{"HostIp": "127.0.0.1", "HostPort": str(selected["port"])}]
    if (
        row.get("Id") != selected["container_id"]
        or row.get("Image") != selected["image_id"]
        or row.get("State", {}).get("Running") is not True
        or labels.get("cppulse.task") != selected["task_label"]
        or labels.get("cppulse.fixture") != selected["fixture_label"]
        or row.get("NetworkSettings", {})
        .get("Ports", {})
        .get(str(selected["container_port"]) + "/tcp")
        != expected_ports
    ):
        raise ContractError(
            "Live service identity, running state, ownership or loopback binding differs"
        )


def _cases(raw: bytes, request: dict[str, Any], namespace: str) -> dict[str, bool]:
    value = _strict_json(raw)
    if not isinstance(value, dict) or set(value) != {
        "namespace",
        "cases",
        "observations",
    }:
        raise ContractError("Protected probe has unsupported observation shape")
    cases = value["cases"]
    if (
        value["namespace"] != namespace
        or not isinstance(cases, dict)
        or set(cases) != set(request["required_cases"])
        or any(not isinstance(item, bool) for item in cases.values())
        or not isinstance(value["observations"], dict)
    ):
        raise ContractError(
            "Protected probe cases/namespace are incomplete or inconsistent"
        )
    return cases


def _assessment(
    request: dict[str, Any], report: dict[str, Any], root: Path
) -> list[str]:
    failures = []
    commands = _commands(
        request, Path(report["execution_root"]), report["namespace"], report["tools"]
    )
    expected = [
        "service-before",
        *[
            lane + "-" + kind
            for lane in ("before", "after")
            for kind in ("compile", "link", "probe-build", "test")
        ],
        "service-after",
    ]
    ids = [row["id"] for row in report["steps"]]
    if ids != expected:
        failures.append("All ten actual service/build/test observations are required")
    for row in report["steps"]:
        if row["id"] not in commands or row["argv"] != commands[row["id"]]:
            failures.append("Observed command differs from fixed declared profile")
            continue
        if (
            request["version"] == "0.2.0"
            and row["id"].startswith("service-")
            and row["resource_receipt"] is not None
        ):
            failures.append("Service inspection cannot claim project resource limits")
        if request["version"] == "0.2.0" and not row["id"].startswith("service-"):
            from cppulse.service_resources import validate_resource_receipt

            try:
                receipt = row["resource_receipt"]
                expected_path = "logs/" + row["id"] + ".resources.json"
                if (
                    receipt is None
                    or receipt["path"] != expected_path
                    or _fact(root / expected_path, root) != receipt
                ):
                    raise ContractError("Missing original process resource receipt")
                selected = request["process_resources"][
                    "test" if row["id"].endswith("-test") else "build"
                ]
                validate_resource_receipt(
                    _strict_json(_read(root / expected_path, max_bytes=8 * 1024**2)),
                    selected,
                    step_id=row["id"],
                    argv=row["argv"][7:],
                )
            except (ContractError, IntegrityError) as exc:
                failures.append(str(exc))
        outcome = row["outcome"]
        captured = row["stdout"]["size_bytes"] + row["stderr"]["size_bytes"]
        if (
            captured != outcome["captured_bytes"]
            or captured != outcome["stdout_bytes"] + outcome["stderr_bytes"]
            or row["stdout"]["size_bytes"] != outcome["stdout_bytes"]
            or row["stderr"]["size_bytes"] != outcome["stderr_bytes"]
            or captured > request["limits"]["log_bytes"]
            or outcome["limitations"]
        ):
            failures.append("Observed output is incomplete, truncated or inconsistent")
        raw = _read(
            root / row["stdout"]["path"], max_bytes=request["limits"]["log_bytes"]
        )
        try:
            if row["id"].startswith("service-"):
                if outcome["status"] != "passed" or outcome["returncode"] != 0:
                    raise ContractError("Service inspection did not pass")
                _service(raw, request)
            elif row["id"].endswith("-test"):
                lane = row["id"].split("-", 1)[0]
                cases = _cases(raw, request, report["namespace"] + "_" + lane)
                if lane == "before":
                    if (
                        outcome["status"] != "failed"
                        or outcome["returncode"] != 1
                        or all(cases.values())
                    ):
                        raise ContractError(
                            "Before must retain at least one genuine finite failure"
                        )
                elif (
                    outcome["status"] != "passed"
                    or outcome["returncode"] != 0
                    or not all(cases.values())
                ):
                    raise ContractError(
                        "After must execute every protected case successfully"
                    )
            elif outcome["status"] != "passed" or outcome["returncode"] != 0:
                raise ContractError("An actual compile/link step did not pass")
        except ContractError as exc:
            failures.append(str(exc))
    return failures


def validate_report(
    request: dict[str, Any], report: dict[str, Any], root: Path
) -> None:
    """Recheck retained bytes and derive status; metadata alone never verifies a pair."""
    validate_request(request)
    _validate(report, "report")
    if report["request_sha256"] != _sha(canonical_json_bytes(request)):
        raise ContractError("Service report request digest differs")
    for key, tool in report["tools"].items():
        if (tool["size_bytes"], tool["sha256"]) != (
            request[key]["size_bytes"],
            request[key]["sha256"],
        ):
            raise ContractError("Sealed selected executable differs from request")
    tool_paths = [tool["path"] for tool in report["tools"].values()]
    if (
        len(set(tool_paths)) != 3
        or len({str(Path(path).parent) for path in tool_paths}) != 1
    ):
        raise ContractError(
            "Selected tools require distinct sealed descriptors owned by one supervisor"
        )
    paths = set()
    pins = {}
    for artifact in report["artifacts"]:
        name = artifact["path"]
        _relative(name)
        if name.casefold() in paths:
            raise ContractError("Duplicate service artifact or case alias")
        paths.add(name.casefold())
        if _fact(root / name, root) != artifact:
            raise IntegrityError(
                "Retained service artifact differs from recorded bytes"
            )
        pins[name] = artifact
    for name, material in _materials(request):
        expected = {**material, "path": "inputs/" + name}
        if pins.get(expected["path"]) != expected:
            raise ContractError(
                "Retained declared service material is missing or changed"
            )
    for index, row in enumerate(report["steps"], start=1):
        progress = "progress-" + str(index) + ".json"
        raw = canonical_json_bytes(row)
        if pins.get(progress) != {
            "path": progress,
            "size_bytes": len(raw),
            "sha256": _sha(raw),
        }:
            raise ContractError(
                "Report step differs from retained original progress receipt"
            )
        for stream in ("stdout", "stderr"):
            if row[stream]["path"] != "logs/" + row["id"] + "." + stream:
                raise ContractError("Actual step must retain its own named raw log")
            if pins.get(row[stream]["path"]) != row[stream]:
                raise ContractError(
                    "Actual step log is not bound to retained inventory"
                )
        if request["version"] == "0.2.0":
            resource = row["resource_receipt"]
            if resource is not None and pins.get(resource["path"]) != resource:
                raise ContractError(
                    "Resource receipt is not retained in artifact inventory"
                )
    if (
        report["version"] != request["version"]
        or report["profile"] != request["profile"]
    ):
        raise ContractError("Resource profile version differs from selected request")
    request_bytes = canonical_json_bytes(request)
    if pins.get("request.json") != {
        "path": "request.json",
        "sha256": _sha(request_bytes),
        "size_bytes": len(request_bytes),
    }:
        raise ContractError("Retained service request differs from selected request")
    if report["status"] == "verified_finite_regression":
        for lane in ("before", "after"):
            for name in ("selected.o", request["soname"], "probe"):
                artifact = pins.get(lane + "/" + name)
                if artifact is None or artifact["size_bytes"] == 0:
                    raise ContractError(
                        "Verified service pair must retain actual compiled artifacts"
                    )
    failures = _assessment(request, report, root)
    if report["status"] == "verified_finite_regression" and (
        failures or report["failures"]
    ):
        raise ContractError(
            "Incomplete service observations cannot verify a regression"
        )
    if report["status"] == "incomplete" and not (failures or report["failures"]):
        raise ContractError("Incomplete service report requires an actual reason")


def verify_service_proposal(
    request: dict[str, Any],
    output: Path,
    *,
    execute_trusted_project: bool = False,
    cancel: CancellationToken | None = None,
) -> dict[str, Any]:
    """Retain and execute a disjoint finite proposal only after explicit opt-in.

    Existing owned service identity is observed before/after; its database state
    is not snapshotted or isolated. Compiler helper/system libraries are inherited
    and project code has host/network privileges. CPU/AS probes elsewhere do not
    grant enforcement to this profile.
    """
    request = deepcopy(request)
    validate_request(request)
    if not execute_trusted_project:
        raise ContractError(
            "Service verification requires explicit trusted project execution"
        )
    if os.name != "posix" or not sys.platform.startswith("linux"):
        raise ContractError("Service ELF profile is qualified only on Linux POSIX")
    output = output.absolute()
    if ".." in output.parts:
        raise ContractError("Output cannot traverse directories")
    for _, material in _materials(request):
        path = Path(material["path"])
        if path.is_relative_to(output):
            raise ContractError(
                "Service output must be disjoint from original materials"
            )
        if _stream_file(path, max_bytes=request["limits"]["input_bytes"]) != (
            material["size_bytes"],
            material["sha256"],
        ):
            raise IntegrityError("Declared service material bytes are stale")
    with _directory(output.parent, create=True) as parent:
        os.mkdir(output.name, mode=0o700, dir_fd=parent)
    (output / "request.json").write_bytes(canonical_json_bytes(request))
    for name, material in _materials(request):
        size, digest = _copy_new(Path(material["path"]), output / "inputs" / name)
        if (size, digest) != (material["size_bytes"], material["sha256"]):
            raise IntegrityError("Service material changed during owned copy")
    for lane in ("before", "after"):
        (output / lane).mkdir()
    (output / "logs").mkdir()
    report = {
        "version": request["version"],
        "profile": request["profile"],
        "request_sha256": _sha(canonical_json_bytes(request)),
        "execution_root": str(output),
        "status": "incomplete",
        "namespace": "cppulse_service_" + uuid.uuid4().hex,
        "steps": [],
        "artifacts": [],
        "failures": [],
        "qualification": QUALIFICATION.copy(),
    }
    tools, descriptors = _sealed_tools(request, output)
    report["tools"] = tools
    commands = _commands(request, output, report["namespace"], tools)
    order = [
        "service-before",
        *[
            lane + "-" + kind
            for lane in ("before", "after")
            for kind in ("compile", "link", "probe-build", "test")
        ],
        "service-after",
    ]
    selected_cancel = cancel or CancellationToken()
    interrupted: BaseException | None = None
    try:
        for identifier in order:
            if selected_cancel.is_cancelled():
                report["failures"].append("Cancellation requested before next step")
                break
            stdout = output / "logs" / (identifier + ".stdout")
            stderr = output / "logs" / (identifier + ".stderr")
            with stdout.open("xb") as out, stderr.open("xb") as err:
                outcome = run_bounded_process(
                    commands[identifier],
                    cwd=output,
                    stdout=out,
                    stderr=err,
                    timeout_seconds=request["limits"]["step_wall_seconds"],
                    limits=ProcessLimits(request["limits"]["log_bytes"]),
                    cancel=selected_cancel,
                    environment={
                        "LD_PRELOAD": "",
                        "LD_LIBRARY_PATH": "",
                    },
                )
            row = {
                "id": identifier,
                "argv": commands[identifier],
                "outcome": outcome.__dict__,
                "stdout": _fact(stdout, output),
                "stderr": _fact(stderr, output),
            }
            if request["version"] == "0.2.0":
                resource_path = output / "logs" / (identifier + ".resources.json")
                row["resource_receipt"] = (
                    _fact(resource_path, output) if resource_path.exists() else None
                )
            report["steps"].append(row)
            (output / ("progress-" + str(len(report["steps"])) + ".json")).write_bytes(
                canonical_json_bytes(row)
            )
            if identifier == "service-before":
                if outcome.status != "passed":
                    report["failures"].append("Initial service inspection failed")
                    break
                _service(
                    _read(stdout, max_bytes=request["limits"]["log_bytes"]), request
                )
            elif identifier.endswith("-test"):
                # A genuine before regression is expected; malformed/cancelled tests
                # still cannot become verified through this continuation.
                if outcome.status in ("cancelled", "timed_out", "error"):
                    break
            elif outcome.status != "passed":
                break
    except BaseException as exc:
        report["failures"].append(type(exc).__name__ + ": " + str(exc)[:1024])
        interrupted = exc
    finally:
        for fd in descriptors:
            os.close(fd)
    for _, material in _materials(request):
        try:
            if _stream_file(
                Path(material["path"]), max_bytes=request["limits"]["input_bytes"]
            ) != (material["size_bytes"], material["sha256"]):
                report["failures"].append(
                    "Original declared material changed during execution"
                )
        except IntegrityError:
            report["failures"].append("Original declared material became unavailable")
    # Generated build trees and raw failures remain retained. No cleanup deletes
    # partial attempts. A successful report additionally checks all copied inputs.
    for path in sorted(output.rglob("*")):
        if path.is_file() and not path.is_symlink() and path.name != "report.json":
            report["artifacts"].append(_fact(path, output))
    report["failures"].extend(_assessment(request, report, output))
    for name, material in _materials(request):
        if _fact(output / "inputs" / name, output) != {
            **material,
            "path": "inputs/" + name,
        }:
            report["failures"].append(
                "Retained declared material changed during execution"
            )
    if not report["failures"]:
        report["status"] = "verified_finite_regression"
    validate_report(request, report, output)
    (output / "report.json").write_bytes(canonical_json_bytes(report))
    if interrupted is not None:
        raise interrupted
    return report


def main(argv: list[str] | None = None) -> int:
    """Run the explicitly selected trusted service lane into a new directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--execute-trusted-project", action="store_true")
    args = parser.parse_args(argv)
    try:
        request = _strict_json(
            _read(args.request.absolute(), max_bytes=MAX_REQUEST_BYTES)
        )
        report = verify_service_proposal(
            request, args.output, execute_trusted_project=args.execute_trusted_project
        )
        return 0 if report["status"] == "verified_finite_regression" else 3
    except KeyboardInterrupt:
        return 130
    except (ContractError, IntegrityError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
