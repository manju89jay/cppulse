"""Bind exact coverage counters to retained GCC/CTest execution, without commands.

The supported execution dialect is GCC/gcov14.2 and gcovr8.8 with an explicit
empty configuration and finite fresh profiles. Hashes are byte identities, not
producer authentication or a complete host runtime dependency inventory.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import tempfile
from typing import Any

from cppulse.adapters.coverage import (
    MAX_REPORT_BYTES,
    CoverageReport,
    parse_coverage_report,
)
from cppulse.contracts import validate, validate_bundle
from cppulse.errors import (
    CompatibilityError,
    ContractError,
    InputChanged,
    IntegrityError,
)
from cppulse.identities import digest_json, verify_inputs
from cppulse.run_store import RunSnapshot, RunStore

VERSION = "1.0.0"
LIMITATIONS = [
    "Observed coverage describes only this finite selected source, instrumented binary and nonzero CTest execution; it is not proof of safety or test adequacy.",
    "Line, branch and function measurements are distinct. Decision and MC/DC coverage are not inferred. No report shards or percentages are merged.",
    "The supported first execution slice is GCC/gcov14.2 and gcovr8.8; host runtime and gcovr interpreter/package closure are not inventoried or authenticated.",
    "Only newly created runtime profiles are accepted; cached or accumulated profiles require a future explicit merge protocol. Failed process dependencies currently prevent downstream coverage generation.",
]


def _id(value: str) -> str:
    return "coverage-" + hashlib.sha256(value.encode()).hexdigest()


def _bytes(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            document, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode()


def _documents(snapshot: RunSnapshot) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for entry in snapshot.manifest["artifacts"]:
        contract = entry.get("contract", {})
        if contract.get("version") == "2.0.0":
            result.setdefault(contract["kind"], []).append(
                snapshot.read_json(entry["id"])
            )
    return result


def _descriptor(snapshot: RunSnapshot, identifier: str) -> dict[str, Any]:
    rows = [row for row in snapshot.manifest["artifacts"] if row["id"] == identifier]
    if len(rows) != 1:
        raise ContractError(
            f"Selected artifact ID is absent or ambiguous: {identifier}"
        )
    return rows[0]


def _absolute(path: str, base: str) -> str:
    if not path or "\\" in path or "\0" in path:
        raise ContractError("Coverage path is not a supported POSIX identity")
    return posixpath.normpath(
        path if path.startswith("/") else posixpath.join(base, path)
    )


def _relative(path: str, workspace: str) -> str:
    selected = _absolute(path, workspace)
    prefix = workspace.rstrip("/") + "/"
    if not selected.startswith(prefix):
        raise ContractError("Coverage path is outside the selected workspace")
    return selected[len(prefix) :]


def _workspace(step: dict[str, Any], receipt: dict[str, Any]) -> str:
    observed = receipt["cwd"]
    if not observed.startswith("/") or posixpath.normpath(observed) != observed:
        raise CompatibilityError("Coverage receipt cwd is not canonical POSIX")
    parts = [] if step["cwd"] == "." else step["cwd"].split("/")
    path = PurePosixPath(observed)
    if parts and list(path.parts[-len(parts) :]) != parts:
        raise ContractError("Coverage receipt cwd disagrees with its plan")
    for _ in parts:
        path = path.parent
    return str(path)


def _role(facts: dict[str, Any], identifier: str, direction: str) -> str:
    rows = [
        row["path"]
        for row in facts["binding"][direction + "_artifacts"]
        if row["artifact_id"] == identifier
    ]
    if len(rows) != 1:
        raise ContractError(
            f"Coverage role is not one observed {direction}: {identifier}"
        )
    return rows[0]


def _parsed(snapshot: RunSnapshot, identifier: str, adapter: str) -> CoverageReport:
    descriptor = _descriptor(snapshot, identifier)
    if descriptor["size_bytes"] > MAX_REPORT_BYTES:
        raise CompatibilityError(
            "Selected coverage report exceeds the bounded adapter limit"
        )
    content = snapshot.read_bytes(identifier)
    with tempfile.TemporaryDirectory(prefix="cppulse-coverage-parser-") as temporary:
        report_path = Path(temporary) / "report"
        report_path.write_bytes(content)
        result = parse_coverage_report(
            report_path, adapter, producer={"name": "gcovr", "version": "8.8"}
        )
    if (
        result.report_sha256 != descriptor["sha256"]
        or result.size_bytes != descriptor["size_bytes"]
    ):
        raise IntegrityError(
            "Parsed report bytes do not match the selected archived descriptor"
        )
    return result


def _base(
    snapshot: RunSnapshot,
    adapter: str,
    context_id: str,
    report_id: str,
    parsed: CoverageReport,
    origin: str,
) -> dict[str, Any]:
    if adapter not in {"lcov", "cobertura"}:
        raise CompatibilityError("Unsupported coverage adapter")
    return {
        "version": "2.0.0",
        "id": _id(
            digest_json(
                {
                    "manifest": snapshot.manifest_sha256,
                    "adapter": adapter,
                    "report": report_id,
                    "context": context_id,
                    "origin": origin,
                }
            )
        ),
        "source_digest": snapshot.manifest["source"]["digest"],
        "context_id": context_id,
        "origin": origin,
        "producer": {"name": "cppulse.coverage-normalizer", "version": VERSION},
        "adapter": {"name": adapter, "version": "1.0.0"},
        "report_artifact_id": report_id,
        "receipt_id": None,
        "proof_receipt_ids": [],
        "test_evidence_ids": [],
        "instrumentation": [],
        "profiles": [],
        "usability": (
            parsed.usability
            if parsed.files or parsed.usability != "usable"
            else "missing"
        ),
        "files": [],
        "limitations": list(dict.fromkeys([*LIMITATIONS, *parsed.limitations])),
    }


def _measurements(
    parsed: CoverageReport,
    source: dict[str, dict[str, Any]],
    workspace: str,
    input_bytes: dict[str, bytes],
    *,
    observed: bool,
) -> list[dict[str, Any]]:
    files = []
    seen = set()
    for file in parsed.files:
        path = _relative(file.file, workspace)
        if path in seen or path not in source:
            raise ContractError(
                "Coverage source is duplicated or outside the selected finite inventory"
            )
        seen.add(path)
        content = input_bytes.get(path)
        if observed and content is None:
            raise ContractError("Coverage source has no retained compiler input bytes")
        line_count = len(content.splitlines()) if content is not None else None
        measurements = []
        for measurement in file.measurements:
            if line_count is not None and any(
                unit.line is not None and unit.line > line_count
                for unit in measurement.units
            ):
                raise ContractError(
                    "Coverage unit is outside the retained source line bounds"
                )
            measurements.append(
                {
                    "kind": measurement.kind,
                    "method": measurement.method,
                    "covered": measurement.covered,
                    "total": measurement.total,
                    "units": [
                        {
                            "id": _id(path + ":" + measurement.method + ":" + unit.id),
                            "covered": unit.covered,
                            "total": unit.total,
                        }
                        for unit in measurement.units
                    ],
                }
            )
        files.append(
            {
                "file": path,
                "source_sha256": source[path]["sha256"] if observed else None,
                "measurements": measurements,
            }
        )
    return files


def normalize_imported_coverage(
    snapshot: RunSnapshot,
    *,
    report_artifact_id: str,
    adapter: str,
    context_id: str,
    source_root: str,
) -> dict[str, Any]:
    """Retain exact imported counts without asserting execution or source freshness."""
    snapshot.verify()
    parsed = _parsed(snapshot, report_artifact_id, adapter)
    result = _base(snapshot, adapter, context_id, report_artifact_id, parsed, "import")
    result["files"] = _measurements(
        parsed,
        {row["path"]: row for row in snapshot.manifest["source"]["files"]},
        source_root,
        {},
        observed=False,
    )
    validate_bundle(
        {
            "run_manifest": snapshot.manifest,
            **_documents(snapshot),
            "coverage_facts": [*_documents(snapshot).get("coverage_facts", []), result],
        }
    )
    return result


def normalize_coverage(
    snapshot: RunSnapshot,
    *,
    receipt_id: str,
    report_artifact_id: str,
    adapter: str,
    producer_version_receipt_id: str,
    gcov_version_receipt_id: str,
    compiler_version_receipt_id: str,
    configuration_artifact_id: str,
    gcov_artifact_id: str,
    proof_receipt_ids: list[str],
    test_evidence_ids: list[str],
    instrumentation: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bind report counters to checked explicit GCC14/gcovr8.8 execution roles.

    No commands or live source reads occur here. Explicit role IDs resolve only
    integrity-checked typed execution facts; imported/debug JSON is never proof.
    """
    snapshot.verify()
    manifest = snapshot.manifest
    documents = _documents(snapshot)
    facts = {row["receipt"]["id"]: row for row in documents.get("execution_facts", [])}
    if receipt_id not in facts or manifest.get("input_verification") != "verified":
        raise CompatibilityError(
            "Observed coverage requires typed source-verified execution facts"
        )
    report = facts[receipt_id]
    context_id = report["receipt"]["context_id"]
    plans = [
        (plan, step)
        for plan in documents.get("collection_plan", [])
        for step in plan["recipe"]["steps"]
        if step["id"] == receipt_id and step["context_id"] == context_id
    ]
    if len(plans) != 1 or plans[0][1]["argv"] != report["receipt"]["argv"]:
        raise CompatibilityError("Coverage producer needs one exact retained plan step")
    plan, step = plans[0]
    workspace = _workspace(step, report["receipt"])
    if step["cwd"] != ".":
        raise CompatibilityError(
            "Supported gcovr recipe runs at the selected source root"
        )
    if any(
        row["receipt_id"] == receipt_id
        and row["report_artifact_id"] == report_artifact_id
        for row in documents.get("coverage_facts", [])
    ):
        raise ContractError(
            "This report is already normalized; select its original snapshot"
        )

    def usable(identifier: str) -> dict[str, Any]:
        row = facts.get(identifier)
        if (
            row is None
            or row["receipt"]["context_id"] != context_id
            or row["receipt"]["status"] != "passed"
            or row["material_status"] != "available"
            or row["binding"]["status"] != "verified"
            or row["input_facts"] != row["input_after_facts"]
            or row["logs_truncated"]
        ):
            raise CompatibilityError(
                f"Coverage proof receipt is unavailable, changed or incomplete: {identifier}"
            )
        return row

    def version(identifier: str, name: str, expected: str) -> dict[str, Any]:
        row = usable(identifier)
        if row["receipt"]["argv"] != [row["executable_fact"]["path"], "--version"]:
            raise CompatibilityError(
                "Coverage tool version probe is not an explicit --version invocation"
            )
        stdout = row["binding"]["log_artifacts"]["stdout"]
        if stdout is None:
            raise CompatibilityError("Coverage tool version output is missing")
        try:
            first = snapshot.read_bytes(stdout).decode("utf-8").splitlines()[0]
        except (UnicodeError, IndexError) as error:
            raise CompatibilityError("Coverage version output is malformed") from error
        fields = first.split()
        tool_name = fields[0] if fields else ""
        named = tool_name == name or (
            name == "g++"
            and re.fullmatch(r"(?:[A-Za-z0-9_.-]+-)?g\+\+(?:-14)?", tool_name)
        )
        if not fields or fields[-1] != expected or not named:
            raise CompatibilityError(f"Unsupported {name} version: {first}")
        if datetime.fromisoformat(
            row["receipt"]["finished_at"].replace("Z", "+00:00")
        ) > datetime.fromisoformat(
            report["receipt"]["started_at"].replace("Z", "+00:00")
        ):
            raise CompatibilityError("Coverage version probe is not causal")
        return row

    usable(receipt_id)
    generator = version(producer_version_receipt_id, "gcovr", "8.8")
    gcov = version(gcov_version_receipt_id, "gcov", "14.2.0")
    compiler = version(compiler_version_receipt_id, "g++", "14.2.0")
    if generator["executable_fact"]["sha256"] != report["executable_fact"]["sha256"]:
        raise CompatibilityError(
            "Coverage report and version probe used different generators"
        )
    context = next(row for row in manifest["contexts"] if row["id"] == context_id)
    if (
        context["compiler"]["name"] != "GNU"
        or context["compiler"]["version"] != "14.2.0"
        or context["compiler"].get("sha256") != compiler["executable_fact"]["sha256"]
    ):
        raise CompatibilityError(
            "Coverage compiler context does not match observed GCC14.2 bytes"
        )
    config_path = _role(report, configuration_artifact_id, "input")
    gcov_path = _role(report, gcov_artifact_id, "input")
    config = snapshot.read_bytes(configuration_artifact_id).decode("utf-8")
    if any(
        line.strip() and not line.lstrip().startswith("#")
        for line in config.splitlines()
    ):
        raise CompatibilityError(
            "First coverage slice requires an explicit empty gcovr configuration"
        )
    if (
        _descriptor(snapshot, gcov_artifact_id)["sha256"]
        != gcov["executable_fact"]["sha256"]
        or _absolute(gcov_path, workspace) != gcov["executable_fact"]["path"]
    ):
        raise CompatibilityError(
            "Selected gcov bytes are not the observed versioned tool"
        )
    report_path = _role(report, report_artifact_id, "output")
    argv = report["receipt"]["argv"]
    expected = [
        argv[0],
        "--config",
        config_path,
        "--root",
        workspace,
        "--object-directory",
        workspace,
        "--gcov-executable",
        _absolute(gcov_path, workspace),
        "--no-markers",
        "--lcov-format-version",
        "1.x",
        "--lcov",
        "coverage.info",
        "--cobertura",
        "coverage.xml",
        *sorted(
            _role(usable(profile["test_receipt_id"]), profile["artifact_id"], "output")
            for profile in profiles
        ),
    ]
    if argv != expected or report_path != (
        "coverage.info" if adapter == "lcov" else "coverage.xml"
    ):
        raise CompatibilityError(
            "Coverage report invocation/output is outside the supported explicit gcovr recipe"
        )
    parsed = _parsed(snapshot, report_artifact_id, adapter)
    result = _base(
        snapshot, adapter, context_id, report_artifact_id, parsed, "execution"
    )
    result.update(
        receipt_id=receipt_id,
        proof_receipt_ids=deepcopy(proof_receipt_ids),
        test_evidence_ids=deepcopy(test_evidence_ids),
        instrumentation=deepcopy(instrumentation),
        profiles=deepcopy(profiles),
    )
    needed = {
        receipt_id,
        producer_version_receipt_id,
        gcov_version_receipt_id,
        compiler_version_receipt_id,
    }
    if not needed <= set(proof_receipt_ids):
        raise ContractError(
            "Coverage proof list omits an explicit tool version receipt"
        )
    source = {row["path"]: row for row in manifest["source"]["files"]}
    source_bytes: dict[str, bytes] = {}
    mapping_by_path: dict[str, bytes] = {}

    def owner(identifier: str) -> dict[str, Any]:
        owners = [
            row
            for row in facts.values()
            if row["receipt"]["context_id"] == context_id
            and any(
                link["artifact_id"] == identifier
                for link in row["binding"]["output_artifacts"]
            )
        ]
        if len(owners) != 1:
            raise ContractError(
                "Coverage material needs one unambiguous observed output owner"
            )
        return usable(owners[0]["receipt"]["id"])

    for item in instrumentation:
        compiled = owner(item["object_artifact_id"])
        obj = _role(compiled, item["object_artifact_id"], "output")
        mapping = _role(compiled, item["mapping_artifact_id"], "output")
        if len(item["source_files"]) != 1:
            raise CompatibilityError(
                "Supported compile receipt instruments one explicit translation unit"
            )
        file = item["source_files"][0]
        if (
            file not in source
            or not obj.startswith("build/")
            or mapping != str(PurePosixPath(obj).with_suffix(".gcno"))
        ):
            raise ContractError("GCC object/mapping/source identities disagree")
        if (
            compiled["executable_fact"]["sha256"]
            != compiler["executable_fact"]["sha256"]
            or compiled["receipt"]["argv"]
            != [
                compiler["executable_fact"]["path"],
                "--coverage",
                "-O0",
                "-g",
                "-std=c++17",
                "-c",
                file,
                "-o",
                obj,
            ]
            or compiled["receipt"]["cwd"] != workspace
        ):
            raise CompatibilityError(
                "Coverage compile receipt lacks the supported actual instrumentation command"
            )
        source_links = [
            link
            for link in compiled["binding"]["input_artifacts"]
            if link["path"] == file
        ]
        if len(source_links) != 1:
            raise ContractError(
                "Instrumented source is not one retained compiler input"
            )
        content = snapshot.read_bytes(source_links[0]["artifact_id"])
        if hashlib.sha256(content).hexdigest() != source[file]["sha256"]:
            raise IntegrityError(
                "Retained compiler source differs from selected source"
            )
        source_bytes[file] = content
        notes = snapshot.read_bytes(item["mapping_artifact_id"])
        if len(notes) < 12 or notes[:8] != b"oncg*24B":
            raise CompatibilityError(
                "Coverage notes are not supported GCC14.2 mapping bytes"
            )
        mapping_by_path[mapping] = notes
    for profile in profiles:
        tested = usable(profile["test_receipt_id"])
        profile_path = _role(tested, profile["artifact_id"], "output")
        mapping_path = str(PurePosixPath(profile_path).with_suffix(".gcno"))
        data = snapshot.read_bytes(profile["artifact_id"])
        notes = mapping_by_path.get(mapping_path)
        if (
            notes is None
            or len(data) < 12
            or data[:8] != b"adcg*24B"
            or data[8:12] != notes[8:12]
        ):
            raise CompatibilityError(
                "Runtime profile does not match retained GCC14.2 notes/version/stamp"
            )
        linked = owner(profile["binary_artifact_id"])
        binary = _role(linked, profile["binary_artifact_id"], "output")
        objects = sorted(
            _role(
                owner(item["object_artifact_id"]), item["object_artifact_id"], "output"
            )
            for item in instrumentation
        )
        if (
            linked["executable_fact"]["sha256"] != compiler["executable_fact"]["sha256"]
            or linked["receipt"]["argv"]
            != [
                compiler["executable_fact"]["path"],
                "--coverage",
                *objects,
                "-o",
                binary,
            ]
            or linked["receipt"]["cwd"] != workspace
        ):
            raise CompatibilityError(
                "Exercised binary lacks the supported actual instrumented link command"
            )
    if set(mapping_by_path) != {
        str(
            PurePosixPath(
                _role(
                    usable(profile["test_receipt_id"]), profile["artifact_id"], "output"
                )
            ).with_suffix(".gcno")
        )
        for profile in profiles
    }:
        raise ContractError(
            "Coverage profiles do not exactly cover selected instrumentation mappings"
        )
    result["files"] = _measurements(
        parsed, source, workspace, source_bytes, observed=True
    )
    if parsed.sources and tuple(parsed.sources) != (workspace,):
        raise ContractError(
            "Cobertura declared source root differs from observed workspace"
        )
    validate("coverage_facts", result)
    validate_bundle(
        {
            "run_manifest": manifest,
            **documents,
            "coverage_facts": [*documents.get("coverage_facts", []), result],
        }
    )
    return result


def persist_coverage(
    snapshot: RunSnapshot, *, workspace: Path, store: RunStore | Path, **selection: Any
) -> RunSnapshot:
    """Publish a new immutable derived snapshot, preserving checked parent bytes."""
    result = normalize_coverage(snapshot, **selection)
    manifest = snapshot.manifest

    def source_check() -> None:
        changed = verify_inputs(workspace, manifest["source"])
        if changed:
            raise InputChanged(
                "Selected source changed during coverage publication: "
                + "; ".join(changed)
            )

    source_check()
    documents = _documents(snapshot)
    cap = min(
        int(plan["limits"]["max_metadata_bytes"])
        for plan in documents["collection_plan"]
    )
    if len(_bytes(result)) > cap:
        raise IntegrityError("Coverage control JSON exceeds max_metadata_bytes")
    runtime = store if isinstance(store, RunStore) else RunStore(store)
    with runtime.begin() as stage:
        for entry in manifest["artifacts"]:
            copied = stage.copy_artifact(
                entry["id"],
                snapshot.path / entry["path"],
                entry["path"],
                entry["media_type"],
                contract=entry.get("contract"),
            )
            if any(copied[key] != entry[key] for key in ("sha256", "size_bytes")):
                raise IntegrityError("Parent coverage artifact changed during copying")
        # Read the pinned parent through its checked public API before retaining
        # a descriptive provenance blob; this blob is not another run contract.
        snapshot.verify()
        parent = _bytes(manifest)
        if (
            len(parent) > cap
            or hashlib.sha256(parent).hexdigest() != snapshot.manifest_sha256
        ):
            raise IntegrityError(
                "Parent manifest serialization/hash or metadata cap differs"
            )
        with tempfile.TemporaryDirectory(
            prefix="cppulse-coverage-publish-"
        ) as temporary:
            path = Path(temporary) / "parent.json"
            path.write_bytes(parent)
            identifier = _id("parent:" + snapshot.manifest_sha256)
            stage.copy_artifact(
                identifier,
                path,
                "coverage/provenance/" + identifier + ".json",
                "application/json",
            )
        artifact_id = _id("facts:" + result["id"])
        stage.write_json(
            "coverage/facts/" + artifact_id + ".json",
            result,
            contract="coverage_facts",
            artifact_id=artifact_id,
        )
        derived = deepcopy(manifest)
        derived["run_id"] = stage.run_id
        derived["artifacts"] = stage.artifacts
        if derived["status"] == "completed" and result["usability"] != "usable":
            derived["status"] = "partial"
        derived["finished_at"] = (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        derived["stages"].append(
            {
                "id": _id("normalize:" + result["id"]),
                "status": "passed" if result["usability"] == "usable" else "error",
                "depends_on": [],
                "reason": "Checked source-bound coverage normalization; this is not a policy pass.",
            }
        )
        derived["versions"] = {
            **derived["versions"],
            "coverage-normalizer": VERSION,
            "parent-manifest-sha256": snapshot.manifest_sha256,
        }
        derived["limitations"] = list(
            dict.fromkeys([*derived["limitations"], *LIMITATIONS])
        )
        if len(_bytes(derived)) > cap:
            raise IntegrityError("Derived coverage manifest exceeds max_metadata_bytes")
        return stage.publish(derived, source_check=source_check)
