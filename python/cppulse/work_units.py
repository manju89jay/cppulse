"""Finite native work units with observed receipts and checked local checkpoints.

The protocol remains private. Checkpoint resume retains its original receipt;
this is not cross-run fact reuse. Dependency discovery is not yet closed, so this
module deliberately never manufactures a positive extraction-cache hit.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from concurrent.futures import (
    FIRST_COMPLETED,
    Future,
    ThreadPoolExecutor,
    as_completed,
    wait,
)
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from importlib import resources
import json
import math
import os
import stat
import shutil
from pathlib import Path
import time
from typing import Any

import jsonschema
from referencing import Registry, Resource

from cppulse import __version__
from cppulse.contracts import validate
from cppulse.errors import ContractError, IntegrityError
from cppulse.execution import CancellationToken, ProcessLimits, run_bounded_process
from cppulse.identities import (
    canonical_json_bytes,
    context_identity,
    digest_json,
    hash_artifact,
    verify_inputs,
    snapshot_inputs,
)


@dataclass(frozen=True)
class WorkUnitExecution:
    """One retained work-unit result; resumed receipts describe their first run."""

    result: dict[str, Any]
    resumed: bool = False


@dataclass(frozen=True)
class ValidatedWorkUnit:
    """Bound native payload and separately observed invocation/parse contexts."""

    report: dict[str, Any]
    invocation_context: dict[str, Any]
    observed_context: dict[str, Any]


@lru_cache(maxsize=1)
def _protocol_schemas() -> tuple[Registry, dict[str, dict[str, Any]]]:
    base = resources.files("cppulse.contracts").joinpath("schemas")
    schemas = []
    private = {}
    for group in ("v2", "work_units_private"):
        for path in base.joinpath(group).iterdir():
            if path.name.endswith(".schema.json"):
                document = json.loads(path.read_bytes())
                jsonschema.Draft7Validator.check_schema(document)
                schemas.append(document)
                if group == "work_units_private":
                    private[path.name.removesuffix(".schema.json")] = document
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    return registry, private


@lru_cache(maxsize=16)
def _validator(name: str) -> jsonschema.Draft7Validator:
    registry, private = _protocol_schemas()
    if name not in private:
        raise ContractError("Unknown private work-unit contract: " + name)
    return jsonschema.Draft7Validator(
        private[name], registry=registry, format_checker=jsonschema.FormatChecker()
    )


def _check(name: str, document: dict[str, Any]) -> None:
    try:
        _validator(name).validate(document)
        canonical_json_bytes(document)
    except jsonschema.ValidationError as exc:
        raise ContractError(f"Invalid private {name}: {exc.message}") from exc


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path, max_bytes: int) -> Any:
    """Read finite regular JSON without following a symlink leaf."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise IntegrityError("JSON material is not a regular file")
            content = stream.read(max_bytes + 1)
        if len(content) > max_bytes:
            raise IntegrityError("JSON material exceeds its byte bound")
        return json.loads(content)
    except (OSError, ValueError) as exc:
        raise IntegrityError("JSON material is incomplete or invalid") from exc


def _write(path: Path, value: Any) -> None:
    """Publish checkpoint data through an atomic sibling replacement."""
    temporary = path.with_name(path.name + ".tmp")
    if path.is_symlink() or temporary.is_symlink():
        raise IntegrityError("Checkpoint path cannot be a symlink")
    temporary.write_bytes(canonical_json_bytes(value))
    temporary.replace(path)


def _roots(source_root: Path | str, work_root: Path | str) -> tuple[Path, Path]:
    source = Path(source_root).resolve(strict=True)
    work = Path(work_root)
    if not work.is_absolute():
        work = Path.cwd() / work
    for component in [work, *work.parents]:
        if component.is_symlink():
            raise IntegrityError("Work-root components cannot be symlinks")
    work = work.resolve()
    if (
        not source.is_dir()
        or work.is_relative_to(source)
        or source.is_relative_to(work)
    ):
        raise IntegrityError("Source and work roots must be disjoint directories")
    return source, work


def _artifact(work: Path, relative: str, identifier: str) -> dict[str, Any]:
    return hash_artifact(work / relative, identifier, relative, "application/json")


def _verify_artifact(work: Path, record: dict[str, Any]) -> None:
    current = work
    for part in Path(record["path"]).parts:
        if part in ("..", ".") or Path(record["path"]).is_absolute():
            raise IntegrityError("Artifact must remain inside work root")
        current /= part
        if current.is_symlink():
            raise IntegrityError("Artifact components cannot be symlinks")
    try:
        actual = hash_artifact(
            current, record["id"], record["path"], record["media_type"]
        )
    except OSError as exc:
        raise IntegrityError(f"Work-unit artifact is unavailable: {exc}") from exc
    if actual != record:
        raise IntegrityError("Work-unit artifact content differs from checkpoint")


def prepare_work_unit(
    *,
    unit_id: str,
    source_root: Path | str,
    work_root: Path | str,
    source: dict[str, Any],
    primary_file: str,
    context: dict[str, Any],
    native_executable: Path | str,
    configuration: dict[str, Any],
    registry: dict[str, Any],
    limits: dict[str, Any] | None = None,
    resource_directory: Path | str | None = None,
    context_mode: str = "parse_arguments",
    compilation_database: list[dict[str, Any]] | None = None,
    global_source_digest: str | None = None,
    environment: dict[str, str] | None = None,
    artifact_prefix: str | None = None,
    compilation_database_file: Path | None = None,
    retain_primary: bool = False,
    inherit_resource_environment: bool = True,
    process_working_directory: Path | None = None,
) -> dict[str, Any]:
    """Retain a finite, explicitly selected extraction request outside source.

    Raises:
        ContractError: If the request or bounds are malformed.
        IntegrityError: If selected source differs or roots overlap.
    """
    validate("source", source)
    validate("context", context)
    validate("rule_registry", registry)
    root, work = _roots(source_root, work_root)
    errors = verify_inputs(root, source)
    if errors:
        raise IntegrityError("; ".join(errors))
    selected = [row for row in source["files"] if row["path"] == primary_file]
    if len(selected) != 1:
        raise ContractError("Primary file must occur once in selected source")
    chosen_resource = (
        resource_directory
        if resource_directory is not None
        else (
            os.environ.get("CPPULSE_CLANG_RESOURCE_DIR")
            if inherit_resource_environment
            else None
        )
    )
    resource = None
    if chosen_resource is not None:
        if not str(chosen_resource).strip():
            raise ContractError("Explicit resource directory cannot be empty")
        resource_root = Path(chosen_resource).resolve(strict=True)
        if not (resource_root / "include/stddef.h").is_file():
            raise IntegrityError("Resource directory requires include/stddef.h")
        resource_snapshot = snapshot_inputs(
            resource_root, _resource_files(resource_root)
        )
        resource = {
            "version": "1.0.0",
            "root": str(resource_root),
            "source": resource_snapshot,
        }
        _check("resource_inputs", resource)
    native = Path(native_executable).resolve(strict=True)
    native_fact = hash_artifact(native, "native", "native", "application/octet-stream")
    selected_limits = {
        "wall_seconds": 60,
        "address_space_bytes": None,
        "cpu_seconds": None,
        "max_log_bytes": 1024 * 1024,
        "max_artifact_bytes": 32 * 1024 * 1024,
        **(limits or {}),
    }
    wall = selected_limits["wall_seconds"]
    if (
        isinstance(wall, bool)
        or not isinstance(wall, (int, float))
        or not math.isfinite(wall)
        or wall <= 0
    ):
        raise ContractError("Wall bound must be finite")
    request = {
        "version": "1.0.0",
        "unit_id": unit_id,
        "source_digest": global_source_digest or source["digest"],
        "source_scope": (
            "primary-with-global-guard" if global_source_digest else "whole-inventory"
        ),
        "context_mode": context_mode,
        "environment": environment or {},
        "primary_file": primary_file,
        "primary_sha256": selected[0]["sha256"],
        "context": context_identity(
            {
                **{
                    key: value
                    for key, value in context.items()
                    if key not in ("id", "digest", "version")
                },
                "argv": [
                    *(
                        ["-working-directory=" + context["working_directory"]]
                        if context_mode == "parse_arguments"
                        else []
                    ),
                    *context["argv"],
                    *(
                        ["-resource-dir=" + resource["root"]]
                        if resource is not None
                        else []
                    ),
                ],
            }
        ),
        "source_root": str(root),
        "work_root": str(work),
        "native": {
            "name": "cppulse-analyzer",
            "version": __version__,
            "sha256": native_fact["sha256"],
        },
        "inputs": {},
        "dependency_manifest": None,
        "fact_key": None,
        "limits": selected_limits,
    }
    if process_working_directory is not None:
        selected_cwd = process_working_directory.resolve()
        if selected_cwd not in (root, work):
            raise ContractError(
                "Native process cwd must be the selected source or work root"
            )
        request["process_working_directory"] = str(selected_cwd)
    if artifact_prefix is not None:
        request["artifact_prefix"] = artifact_prefix
    if context_mode == "compilation_database":
        request["context"] = context_identity(
            {
                key: value
                for key, value in context.items()
                if key not in ("id", "digest", "version")
            }
        )
    if resource is not None:
        selected_context = request["context"]
        request["context"] = context_identity(
            {
                **{
                    key: value
                    for key, value in selected_context.items()
                    if key not in ("id", "digest", "version")
                },
                "dependencies": [
                    *selected_context["dependencies"],
                    {
                        "id": "builtin-resources",
                        "sha256": resource["source"]["digest"],
                        "availability": "available",
                    },
                ],
            }
        )
    # Validate all path and limit syntax before creating any work material.
    dummy = {
        "id": "placeholder",
        "path": "placeholder.json",
        "sha256": "0" * 64,
        "size_bytes": 0,
        "media_type": "application/json",
    }
    request["inputs"] = {
        name: dummy
        for name in (
            "source_manifest",
            "selection",
            "configuration",
            "rule_registry",
            "compilation_database",
            "resource_manifest",
        )
    }
    _check("work_request", request)
    work.mkdir(parents=True, exist_ok=True)
    input_dir = work / "inputs"
    if input_dir.is_symlink():
        raise IntegrityError("Input directory cannot be a symlink")
    input_dir.mkdir(exist_ok=True)
    database = [
        {
            "directory": context["working_directory"],
            "file": str(root / primary_file),
            "arguments": ["clang", *context["argv"], str(root / primary_file)],
        }
    ]
    if context_mode == "compilation_database":
        if not compilation_database:
            raise ContractError("Compilation-database mode requires retained commands")
        database = compilation_database
    documents = {
        "source_manifest": source,
        "selection": [primary_file],
        "configuration": configuration,
        "rule_registry": registry,
        "compilation_database": database,
    }
    if context_mode == "fallback":
        documents.pop("compilation_database")
    if resource is not None:
        documents["resource_manifest"] = resource
    inputs = {}
    for name, document in documents.items():
        relative = (
            "inputs/compile_commands.json"
            if name == "compilation_database"
            else f"inputs/{name}.json"
        )
        path = work / relative
        if (
            name == "compilation_database"
            and compilation_database_file is not None
            and not path.exists()
        ):
            os.link(compilation_database_file, path)
        if path.exists():
            if (
                path.is_symlink()
                or (
                    name == "compilation_database"
                    and compilation_database_file is not None
                    and not path.samefile(compilation_database_file)
                )
                or (
                    not (
                        name == "compilation_database"
                        and compilation_database_file is not None
                    )
                    and hash_artifact(path, name, relative, "application/json")[
                        "sha256"
                    ]
                    != digest_json(document)
                )
            ):
                raise IntegrityError("Existing work unit has different retained inputs")
        else:
            _write(path, document)
        inputs[name] = _artifact(work, relative, _identifier(request, name))
    if retain_primary:
        relative = "inputs/primary.cpp"
        destination = work / relative
        if not destination.exists():
            shutil.copyfile(root / primary_file, destination, follow_symlinks=False)
        record = hash_artifact(
            destination, _identifier(request, "primary-content"), relative, "text/x-c++"
        )
        if record["sha256"] != request["primary_sha256"]:
            raise IntegrityError("Retained primary bytes differ from selected source")
        inputs["primary_content"] = record
    if context_mode == "fallback":
        inputs["compilation_database"] = None
    if resource is None:
        inputs["resource_manifest"] = None
    request["inputs"] = inputs
    _check("work_request", request)
    request_path = work / "request.json"
    if request_path.exists() and digest_json(
        _read_json(request_path, 1024 * 1024)
    ) != digest_json(request):
        raise IntegrityError("Work root already belongs to another request")
    _write(request_path, request)
    return request


def _resource_files(root: Path) -> list[str]:
    selected = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise IntegrityError("Resource components cannot be symlinks")
        if path.is_file():
            selected.append(path.relative_to(root).as_posix())
    return sorted(selected)


def _resource_manifest(unit: dict[str, Any], work: Path) -> dict[str, Any] | None:
    record = unit["inputs"]["resource_manifest"]
    if record is None:
        return None
    manifest = _read_json(work / record["path"], unit["limits"]["max_artifact_bytes"])
    _check("resource_inputs", manifest)
    validate("source", manifest["source"])
    root = Path(manifest["root"])
    if not root.is_absolute() or str(root) != str(root.resolve()):
        raise IntegrityError("Resource root must be absolute and canonical")
    return manifest


def _identifier(unit: dict[str, Any], name: str) -> str:
    prefix = unit.get("artifact_prefix")
    return prefix + "." + name if prefix else name


def _verify_request(
    unit: dict[str, Any], native_executable: Path | str
) -> tuple[Path, Path]:
    _check("work_request", unit)
    root, work = _roots(unit["source_root"], unit["work_root"])
    if Path(unit.get("process_working_directory", str(work))).resolve() not in (
        root,
        work,
    ):
        raise IntegrityError("Native process cwd escapes selected source/work roots")
    native = Path(native_executable).resolve(strict=True)
    if (
        hash_artifact(native, "native", "native", "application/octet-stream")["sha256"]
        != unit["native"]["sha256"]
    ):
        raise IntegrityError("Selected native executable differs from request")
    for record in unit["inputs"].values():
        if record is not None:
            _verify_artifact(work, record)
    resource = _resource_manifest(unit, work)
    if resource is not None:
        resource_root = Path(resource["root"])
        actual = snapshot_inputs(resource_root, _resource_files(resource_root))
        if actual["files"] != resource["source"]["files"]:
            raise IntegrityError(
                "Selected builtin resources differ from retained manifest"
            )
    source = _read_json(
        work / unit["inputs"]["source_manifest"]["path"],
        unit["limits"]["max_artifact_bytes"],
    )
    validate("source", source)
    validate("context", unit["context"])
    if unit.get("source_scope", "whole-inventory") == "whole-inventory":
        if source["digest"] != unit["source_digest"]:
            raise IntegrityError("Source manifest differs from request identity")
    elif (
        len(source["files"]) != 1
        or source["files"][0]["path"] != unit["primary_file"]
        or source["files"][0]["sha256"] != unit["primary_sha256"]
    ):
        raise IntegrityError("Primary-scoped manifest differs from selected unit")
    errors = verify_inputs(root, source)
    if errors:
        raise IntegrityError("; ".join(errors))
    return root, work


def _invocation(unit: dict[str, Any], native: Path) -> tuple[list[str], dict[str, Any]]:
    work = Path(unit["work_root"])
    argv = [
        str(native),
        "--repo",
        unit["source_root"],
        "--output",
        str(work / "output"),
        "--file-list",
        str(work / unit["inputs"]["selection"]["path"]),
        "--config",
        str(work / unit["inputs"]["configuration"]["path"]),
        "--execution-limits-report",
        str(work / "limits.json"),
        "--file-size-bytes",
        str(unit["limits"]["max_artifact_bytes"]),
    ]
    database = unit["inputs"]["compilation_database"]
    if database is not None:
        argv.extend(["--compilation-database", str(work / database["path"])])
    resource = _resource_manifest(unit, work)
    if resource is not None:
        argv.extend(["--resource-dir", resource["root"]])
    for key, option in (
        ("address_space_bytes", "--address-space-bytes"),
        ("cpu_seconds", "--cpu-seconds"),
    ):
        if unit["limits"][key] is not None:
            argv.extend([option, str(unit["limits"][key])])
    context = context_identity(
        {
            "compiler": unit["native"],
            "argv": argv,
            "working_directory": unit.get("process_working_directory", str(work)),
            "language_standard": None,
            "target": None,
            "provenance": "observed",
            "dependencies": [],
            "limitations": [
                "Invocation identity is separate from native-observed parse context."
            ],
        }
    )
    return argv, context


def _validate_receipt_identity(
    unit: dict[str, Any], result: dict[str, Any], native: Path
) -> None:
    argv, invocation = _invocation(unit, native.resolve())
    receipt = result["execution_receipt"]
    if (
        receipt is None
        or receipt["id"] != "native-" + digest_json(unit)
        or receipt["producer"] != {"name": "cppulse.execution", "version": __version__}
    ):
        raise IntegrityError(
            "Receipt deterministic producer identity differs from original work unit"
        )
    if (
        receipt["argv"] != argv
        or receipt["context_id"] != invocation["id"]
        or receipt["source_digest"] != unit["source_digest"]
        or receipt["cwd"] != unit.get("process_working_directory", unit["work_root"])
    ):
        raise IntegrityError("Receipt differs from selected invocation")
    artifacts = result["artifacts"]
    if len({row["id"] for row in artifacts}) != len(artifacts) or len(
        {row["path"] for row in artifacts}
    ) != len(artifacts):
        raise IntegrityError("Result artifact identity is duplicated")
    if receipt["artifact_ids"] != [
        row["id"] for row in artifacts if row["media_type"] == "application/json"
    ] or receipt["log_artifact_ids"] != [
        _identifier(unit, "stdout"),
        _identifier(unit, "stderr"),
    ]:
        raise IntegrityError(
            "Receipt artifact namespace differs from original work unit"
        )


def validate_work_unit(
    unit: dict[str, Any], result: dict[str, Any], *, native_executable: Path | str
) -> ValidatedWorkUnit:
    """Recheck bytes, receipt/argv identity, finite scope and native contracts."""
    _, work = _verify_request(unit, native_executable)
    _check("work_result", result)
    _validate_receipt_identity(unit, result, Path(native_executable))
    if (
        result["request_sha256"] != digest_json(unit)
        or result["unit_id"] != unit["unit_id"]
    ):
        raise IntegrityError("Result does not bind this exact request")
    argv, invocation = _invocation(unit, Path(native_executable).resolve(strict=True))
    receipt = result["execution_receipt"]
    if (
        receipt is None
        or receipt["argv"] != argv
        or receipt["context_id"] != invocation["id"]
        or receipt["source_digest"] != unit["source_digest"]
        or receipt["cwd"] != unit.get("process_working_directory", str(work))
    ):
        raise IntegrityError("Receipt differs from selected invocation")
    for record in result["artifacts"]:
        _verify_artifact(work, record)
    reports = [
        record
        for record in result["artifacts"]
        if record["id"] == _identifier(unit, "native-report")
    ]
    if len(reports) != 1:
        raise IntegrityError("Successful work unit needs one retained native report")
    report = _read_json(work / reports[0]["path"], unit["limits"]["max_artifact_bytes"])
    validate("findings", report, version="prototype_v1")
    files = report["metadata"]["analysis"]["files"]
    if (
        len(files) != 1
        or Path(files[0]["path"]).resolve()
        != (Path(unit["source_root"]) / unit["primary_file"]).resolve()
    ):
        raise IntegrityError("Native report scope differs from finite selection")
    if Path(report["metadata"]["repo_path"]).resolve() != Path(unit["source_root"]):
        raise IntegrityError("Native report repository differs from selected source")
    row = files[0]
    metrics = report["metadata"]["analysis"].get("native_metrics", {}).get("files", [])
    if row["status"] in ("analyzed", "partial") and (
        len(metrics) != 1
        or metrics[0].get("source_content_sha256") != unit["primary_sha256"]
    ):
        raise IntegrityError("Native TU bytes differ from selected source")
    mode = unit.get("context_mode", "parse_arguments")
    if row["parse_arguments"] is not None:
        if mode == "compilation_database":
            if (
                row["compile_context"] not in ("database", "inferred")
                or not row["parse_arguments"]
            ):
                raise IntegrityError(
                    "Retained compilation database was not used by native parser"
                )
        elif row["parse_arguments"] != unit["context"]["argv"]:
            raise IntegrityError("Native parse arguments differ from requested context")
        if mode == "fallback" and row["compile_context"] != "fallback":
            raise IntegrityError(
                "Unexpected implicit compilation database changed fallback selection"
            )
    if row["status"] != result["parse_status"]:
        raise IntegrityError("Result parse status differs from native inventory")
    if result["outcome"] == "complete" and (
        row["status"] != "analyzed" or receipt["status"] != "passed"
    ):
        raise IntegrityError("Complete result requires an error-free native receipt")
    return ValidatedWorkUnit(report, invocation, _observed_context(unit, report))


def _observed_context(unit: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    row = report["metadata"]["analysis"]["files"][0]
    resource = _resource_manifest(unit, Path(unit["work_root"]))
    include_dependencies = {}
    for metric in (
        report["metadata"]["analysis"].get("native_metrics", {}).get("files", [])
    ):
        for edge in metric["includes"]:
            identity = edge.get("content_identity")
            identifier = "include-" + digest_json({"path": edge["target"]})[:48]
            available = identity is not None and identity["status"] == "available"
            include_dependencies[identifier] = {
                "id": identifier,
                "sha256": identity["sha256"] if available else None,
                "availability": "available" if available else "unavailable",
            }
    return context_identity(
        {
            "compiler": report["metadata"]["analysis"]["parser"],
            "argv": row["parse_arguments"] or [],
            "working_directory": row["working_directory"]
            or unit.get("process_working_directory", unit["work_root"]),
            "language_standard": None,
            "target": None,
            "provenance": (
                "observed" if row["parse_arguments"] is not None else "fallback"
            ),
            "dependencies": [
                *(
                    [
                        {
                            "id": "builtin-resources",
                            "sha256": resource["source"]["digest"],
                            "availability": "available",
                        }
                    ]
                    if resource is not None
                    else []
                ),
                *[include_dependencies[key] for key in sorted(include_dependencies)],
            ],
            "limitations": [
                (
                    "Native parse arguments do not establish a complete dependency closure."
                    if row["parse_arguments"] is not None
                    else "No native parse context was observed for this skipped/excluded unit."
                )
            ],
        }
    )


def _execute_locked(
    unit: dict[str, Any], native: Path, cancel: CancellationToken
) -> WorkUnitExecution:
    _, work = _verify_request(unit, native)
    checkpoint = work / "result.json"
    if checkpoint.exists():
        if checkpoint.is_symlink():
            raise IntegrityError("Result checkpoint cannot be a symlink")
        try:
            result = _read_json(checkpoint, 1024 * 1024)
            _check("work_result", result)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise IntegrityError("Result checkpoint is incomplete or invalid") from exc
        pin = _read_json(work / "checkpoint.json", 8192)
        _check("work_checkpoint", pin)
        if pin["request_sha256"] != digest_json(unit) or pin[
            "result_sha256"
        ] != digest_json(result):
            raise IntegrityError(
                "Result checkpoint differs from retained original identity"
            )
        _validate_receipt_identity(unit, result, native)
        if result["outcome"] in ("complete", "partial"):
            checked = validate_work_unit(unit, result, native_executable=native)
            metrics = checked.report["metadata"]["analysis"].get("native_metrics", {})
            if result["outcome"] == "complete" and any(
                row.get("includes") for row in metrics.get("files", [])
            ):
                raise IntegrityError(
                    "Dependency closure is incomplete; use a fresh work root"
                )
        else:
            _check("work_result", result)
            if result["request_sha256"] != digest_json(unit):
                raise IntegrityError("Checkpoint request differs")
            for artifact in result["artifacts"]:
                _verify_artifact(work, artifact)
        return WorkUnitExecution(result, True)
    output = work / "output"
    if output.exists() or output.is_symlink():
        raise IntegrityError("Interrupted output requires an explicit fresh work root")
    output.mkdir()
    argv, invocation = _invocation(unit, native)
    started, began = _stamp(), time.monotonic()
    with (
        (work / "stdout.log").open("xb") as stdout,
        (work / "stderr.log").open("xb") as stderr,
    ):
        outcome = run_bounded_process(
            argv,
            cwd=Path(unit.get("process_working_directory", str(work))),
            stdout=stdout,
            stderr=stderr,
            timeout_seconds=unit["limits"]["wall_seconds"],
            limits=ProcessLimits(max_log_bytes=unit["limits"]["max_log_bytes"]),
            cancel=cancel,
            environment={
                **unit.get("environment", {}),
                "CPPULSE_CLANG_RESOURCE_DIR": "",
            },
        )
    elapsed, finished = time.monotonic() - began, _stamp()
    artifacts = [
        hash_artifact(
            work / name, _identifier(unit, name.split(".")[0]), name, "text/plain"
        )
        for name in ("stdout.log", "stderr.log")
    ]
    parse_status = None
    outcome_name = {
        "passed": "invalid_output",
        "error": "process_error",
        "failed": "process_error",
    }.get(outcome.status, outcome.status)
    if (
        outcome.returncode is not None
        and outcome.returncode < 0
        and outcome.status not in ("timed_out", "cancelled")
    ):
        outcome_name = "crashed"
    report_path = output / "findings.json"
    if (
        report_path.exists()
        and report_path.stat().st_size <= unit["limits"]["max_artifact_bytes"]
    ):
        artifacts.append(
            _artifact(work, "output/findings.json", _identifier(unit, "native-report"))
        )
        try:
            report = _read_json(report_path, unit["limits"]["max_artifact_bytes"])
            validate("findings", report, version="prototype_v1")
            files = report["metadata"]["analysis"]["files"]
            if len(files) == 1:
                parse_status = files[0]["status"]
                if outcome.status == "passed":
                    outcome_name = (
                        "complete" if parse_status == "analyzed" else "partial"
                    )
        except (ValueError, KeyError, TypeError):
            outcome_name = "invalid_output"
    limits_applied = {
        "wall_time": True,
        "address_space": False,
        "cpu_time": False,
        "output_bytes": False,
    }
    guards_path = work / "limits.json"
    if guards_path.exists():
        artifacts.append(_artifact(work, "limits.json", _identifier(unit, "limits")))
        try:
            guards = _read_json(guards_path, 65536)
            applied = guards["applied"]
            if any(
                not isinstance(applied[key], bool)
                for key in ("address_space", "cpu_time", "file_size")
            ):
                raise IntegrityError("Native guard report has invalid capability flags")
            limits_applied.update(
                {
                    "address_space": applied["address_space"],
                    "cpu_time": applied["cpu_time"],
                    "output_bytes": applied["file_size"],
                }
            )
        except (ValueError, KeyError, TypeError):
            outcome_name = "invalid_output"
    receipt = {
        "version": "2.0.0",
        "id": "native-" + digest_json(unit),
        "source_digest": unit["source_digest"],
        "context_id": invocation["id"],
        "producer": {"name": "cppulse.execution", "version": __version__},
        "argv": argv,
        "cwd": unit.get("process_working_directory", str(work)),
        "status": outcome.status,
        "reason": outcome.reason or "Native process completed",
        "exit_code": (
            outcome.returncode
            if outcome.returncode is None or outcome.returncode >= 0
            else None
        ),
        "signal": (
            -outcome.returncode
            if outcome.returncode is not None and outcome.returncode < 0
            else None
        ),
        "started_at": started,
        "finished_at": finished,
        "artifact_ids": [
            a["id"] for a in artifacts if a["media_type"] == "application/json"
        ],
        "log_artifact_ids": [_identifier(unit, "stdout"), _identifier(unit, "stderr")],
        "depends_on": [],
    }
    result = {
        "version": "1.0.0",
        "unit_id": unit["unit_id"],
        "request_sha256": digest_json(unit),
        "mode": "fresh",
        "outcome": outcome_name,
        "parse_status": parse_status,
        "execution_receipt": receipt,
        "cache_origin": None,
        "artifacts": artifacts,
        "limits_applied": limits_applied,
        "measurements": {
            "wall_seconds": elapsed,
            "cpu_seconds": None,
            "peak_memory_bytes": None,
            "peak_memory_scope": None,
            "measurement_method": None,
        },
        "reason": outcome.reason or "Native result retained",
        "limitations": [
            "No cross-run cache reuse: dependency closure is not established.",
            "CPU and peak-memory measurements are unavailable.",
            *(
                [
                    "Global source identity is guarded by analysis execution before/after; this worker checks only its primary file."
                ]
                if unit.get("source_scope") == "primary-with-global-guard"
                else []
            ),
            *outcome.limitations,
        ],
    }
    try:
        _verify_request(unit, native)
    except (IntegrityError, OSError) as exc:
        outcome_name = "input_changed"
        result["outcome"] = "input_changed"
        result["reason"] = str(exc)
    _check("work_result", result)
    if outcome_name in ("complete", "partial"):
        try:
            validate_work_unit(unit, result, native_executable=native)
        except (ContractError, IntegrityError) as exc:
            result["outcome"] = "invalid_output"
            result["reason"] = str(exc)
            _check("work_result", result)
    _validate_receipt_identity(unit, result, native)
    _write(
        work / "checkpoint.json",
        {
            "version": "1.0.0",
            "request_sha256": digest_json(unit),
            "result_sha256": digest_json(result),
        },
    )
    _write(checkpoint, result)
    return WorkUnitExecution(result)


def _execute(
    unit: dict[str, Any], native: Path, cancel: CancellationToken
) -> WorkUnitExecution:
    _, work = _verify_request(unit, native)
    lock = work / ".execution.lock"
    try:
        descriptor = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise IntegrityError(
            "Work root has another owner or an interrupted execution"
        ) from exc
    try:
        os.close(descriptor)
        return _execute_locked(unit, native, cancel)
    finally:
        lock.unlink()


def execute_work_units(
    units: Iterable[dict[str, Any]],
    *,
    native_executable: Path | str,
    jobs: int = 1,
    cancel: CancellationToken | None = None,
    propagate_interrupt: bool = False,
) -> Iterator[WorkUnitExecution]:
    """Execute at most jobs isolated native children, consuming inputs lazily.

    The queue contains at most jobs units. Results stream in completion order.
    Input-integrity failures are exceptions; independent process failures remain
    explicit results. Cancellation stops input consumption and drains workers.
    A returned checkpoint preserves historical execution, not current closed-input
    qualification; coordinators must reject warm reuse without dependency/query
    proof. Missing include edges are not such proof.
    """
    if isinstance(jobs, bool) or not isinstance(jobs, int) or not 1 <= jobs <= 32:
        raise ContractError("jobs must be an integer between 1 and 32")
    native = Path(native_executable).resolve(strict=True)
    token = cancel or CancellationToken()
    iterator = iter(units)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        pending: set[Future[WorkUnitExecution]] = set()
        exhausted = False
        owned: set[str] = set()
        try:
            while pending or not exhausted:
                while (
                    not exhausted and len(pending) < jobs and not token.is_cancelled()
                ):
                    try:
                        unit = next(iterator)
                    except StopIteration:
                        exhausted = True
                        break
                    root = str(Path(unit["work_root"]).resolve())
                    if root in owned:
                        raise ContractError("Each work root needs one scheduler owner")
                    owned.add(root)
                    pending.add(pool.submit(_execute, unit, native, token))
                if token.is_cancelled():
                    exhausted = True
                if pending:
                    finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in finished:
                        yield future.result()
        except KeyboardInterrupt:
            token.cancel()
            for future in as_completed(pending):
                yield future.result()
            if propagate_interrupt:
                raise
        finally:
            if pending:
                token.cancel()
