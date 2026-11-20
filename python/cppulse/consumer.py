"""Scoped library distribution declarations and checked consumer-use evidence.

Declarations select retained bytes and expected contexts. They never execute a
project, invent an upstream source identity or establish that a consumer passed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import stat
import tempfile
from typing import Any

from cppulse.contracts import validate, validate_bundle
from cppulse.errors import (
    CompatibilityError,
    ContractError,
    InputChanged,
    IntegrityError,
)
from cppulse.identities import verify_inputs
from cppulse.run_store import RunSnapshot, RunStore
from cppulse.transfer import ImportedRun

_VERSION = "1.0.0"
_DECLARATIONS = {
    "distribution_subject",
    "consumer_matrix",
    "consumer_usage",
    "consumer_comparison",
}


@dataclass(frozen=True)
class RetainedBlob:
    """Generic original bytes retained without importing their typed source scope."""

    id: str
    path: str
    content: bytes
    media_type: str = "application/json"

    def descriptor(self) -> dict[str, Any]:
        """Return the exact byte identity for a generic retained artifact."""
        result = {
            "id": self.id,
            "path": self.path,
            "sha256": hashlib.sha256(self.content).hexdigest(),
            "size_bytes": len(self.content),
            "media_type": self.media_type,
        }
        validate("artifact", result)
        return result


@dataclass(frozen=True)
class ConsumerComparison:
    """Pure comparison result and original raw roles needed for publication."""

    document: dict[str, Any]
    artifacts: tuple[RetainedBlob, ...]


def _documents(snapshot: RunSnapshot | ImportedRun) -> dict[str, Any]:
    """Read one checked immutable bundle, retaining its primary source identity."""
    snapshot.verify()
    bundle: dict[str, Any] = {"run_manifest": snapshot.manifest}
    for artifact in snapshot.manifest["artifacts"]:
        reference = artifact.get("contract")
        if not reference or reference["version"] != "2.0.0":
            continue
        kind = reference["kind"]
        document = snapshot.read_json(artifact["id"])
        if kind == "policy":
            bundle[kind] = document
        else:
            bundle.setdefault(kind, []).append(document)
    return bundle


def _append(bundle: dict[str, Any], kind: str, document: dict[str, Any]) -> None:
    entries = bundle.setdefault(kind, [])
    if not isinstance(entries, list):
        raise ContractError(f"Consumer metadata cannot replace singleton {kind}")
    same_id = [row for row in entries if row.get("id") == document["id"]]
    if same_id:
        if len(same_id) != 1 or same_id[0] != document:
            raise ContractError(f"Conflicting {kind} identity: {document['id']}")
    else:
        entries.append(deepcopy(document))


def describe_distribution(
    snapshot: RunSnapshot,
    *,
    subject_id: str,
    kind: str,
    distribution_files: Mapping[str, str],
    source_files: Sequence[str] = (),
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Describe selected retained distribution bytes without asserting a build.

    Args:
        snapshot: Owning run, whose source and artifact identities stay separate.
        subject_id: Stable local name for this selected package subject.
        kind: compiled or header-only; this is a declaration, not file detection.
        distribution_files: Logical package paths mapped to exact artifact IDs.
        source_files: Optional actual subset of this run's selected source files.
            Omit for a consumer with only the distributed package available.
        limitations: Additional explicit scope/provenance limits.

    Returns:
        A validated distribution_subject v2 document.

    Raises:
        ContractError: A selection is missing, aliased or outside the owning run.
    """
    bundle = _documents(snapshot)
    manifest = bundle["run_manifest"]
    source = {row["path"]: row for row in manifest["source"]["files"]}
    artifacts = {row["id"]: row for row in manifest["artifacts"]}
    if any(path not in source for path in source_files):
        raise ContractError("Distribution source selection is outside its owning run")
    if len(set(distribution_files.values())) != len(distribution_files):
        raise ContractError("Logical distribution paths cannot alias one artifact")
    selected = []
    for path, identifier in distribution_files.items():
        if identifier not in artifacts:
            raise ContractError(
                f"Expected exact distribution artifact ID: {identifier}"
            )
        artifact = artifacts[identifier]
        selected.append(
            {
                "path": path,
                "artifact_id": identifier,
                "sha256": artifact["sha256"],
                "size_bytes": artifact["size_bytes"],
            }
        )
    relation = "selected_sources" if source_files else "distribution_only"
    notes = [
        "This selects finite retained package bytes; it does not prove that the package was built or exercised.",
        *limitations,
    ]
    if not source_files:
        notes.append(
            "Original library sources are not asserted in this run; upstream source identity remains separate."
        )
    document = {
        "version": "2.0.0",
        "id": subject_id,
        "source_digest": manifest["source"]["digest"],
        "kind": kind,
        "source_relation": relation,
        "source_files": [deepcopy(source[path]) for path in source_files],
        "distribution_files": selected,
        "limitations": list(dict.fromkeys(notes)),
    }
    validate("distribution_subject", document)
    _append(bundle, "distribution_subject", document)
    validate_bundle(bundle)
    return document


def declare_consumer_matrix(
    snapshot: RunSnapshot,
    subject: dict[str, Any],
    *,
    matrix_id: str,
    cases: Sequence[dict[str, Any]],
    limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Declare expected consumer contexts/checks without executing or passing them.

    Args:
        snapshot: Owning immutable run.
        subject: Distribution subject belonging to that run.
        matrix_id: Local matrix name.
        cases: Explicit expected configurations, tests and selected use checks.
        limitations: Extra scope constraints.

    Returns:
        A validated consumer_matrix v2 declaration. Missing expected contexts
        remain valid requirements, never implicit executed successes.

    Raises:
        ContractError: The subject, case fields or owning identities disagree.
    """
    bundle = _documents(snapshot)
    validate("distribution_subject", subject)
    _append(bundle, "distribution_subject", subject)
    document = {
        "version": "2.0.0",
        "id": matrix_id,
        "source_digest": snapshot.manifest["source"]["digest"],
        "subject_id": subject["id"],
        "cases": deepcopy(list(cases)),
        "limitations": list(
            dict.fromkeys(
                [
                    "Matrix cases are declared requirements; missing contexts, use proof or application tests are not passed verification.",
                    *limitations,
                ]
            )
        ),
    }
    validate("consumer_matrix", document)
    _append(bundle, "consumer_matrix", document)
    validate_bundle(bundle)
    return document


def _json_bytes(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            document, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
        )
        + "\n"
    ).encode("utf-8")


def persist_consumer_documents(
    snapshot: RunSnapshot,
    documents: Sequence[tuple[str, dict[str, Any]]],
    *,
    workspace: Path,
    store: RunStore | Path,
    max_metadata_bytes: int = 4 * 1024 * 1024,
    raw_artifacts: Sequence[RetainedBlob] = (),
) -> RunSnapshot:
    """Retain consumer declarations in a new run without rewriting parent facts.

    Args:
        snapshot: Local parent run; imported claims need a separate namespace.
        documents: Kind/document pairs from the supported consumer contracts.
        workspace: Owning selected source directory, checked before publication.
        store: Explicit output store; no commands run and no source is modified.
        max_metadata_bytes: Additional local bound, never raising a recorded cap.

    Returns:
        A new coherent snapshot, or the parent when every exact document is
        already retained. Parent source verification is never retroactively
        promoted merely because today's files happen to match.

    Raises:
        ContractError: Unsupported/contradictory metadata.
        InputChanged: The finite selected source inventory changed.
        IntegrityError: Parent bytes changed or metadata exceeds its bound.
    """
    if not isinstance(snapshot, RunSnapshot):
        raise ContractError(
            "Derived current-source publication requires a local RunSnapshot, not imported claims"
        )
    if (
        not isinstance(max_metadata_bytes, int)
        or isinstance(max_metadata_bytes, bool)
        or not 1 <= max_metadata_bytes <= 64 * 1024 * 1024
    ):
        raise ContractError("max_metadata_bytes must be an integer from 1 to 64MiB")
    bundle = _documents(snapshot)
    manifest = snapshot.manifest
    caps = [
        int(plan["limits"]["max_metadata_bytes"])
        for plan in bundle.get("collection_plan", [])
    ]
    cap = min(max_metadata_bytes, *caps) if caps else max_metadata_bytes

    def checked(document: dict[str, Any]) -> None:
        if len(_json_bytes(document)) > cap:
            raise IntegrityError("Consumer control JSON exceeds its metadata cap")

    additions = []
    blobs = []
    known_artifacts = {row["id"]: row for row in manifest["artifacts"]}
    for blob in raw_artifacts:
        if len(blob.content) > cap:
            raise IntegrityError("Consumer raw JSON exceeds its metadata cap")
        descriptor = blob.descriptor()
        if blob.id in known_artifacts:
            if known_artifacts[blob.id] != descriptor:
                raise ContractError("Conflicting retained consumer raw role")
        else:
            bundle["run_manifest"]["artifacts"].append(descriptor)
            known_artifacts[blob.id] = descriptor
            blobs.append(blob)
    for kind, original in documents:
        if kind not in _DECLARATIONS:
            raise ContractError(f"Consumer contract {kind!r} awaits its producer gate")
        document = deepcopy(original)
        validate(kind, document)
        checked(document)
        previous = len(bundle.get(kind, []))
        _append(bundle, kind, document)
        if len(bundle[kind]) != previous:
            additions.append((kind, document))
    validate_bundle(bundle)

    def source_check() -> None:
        changed = verify_inputs(workspace, manifest["source"])
        if changed:
            raise InputChanged(
                "Selected sources changed before/during consumer publication: "
                + "; ".join(changed)
            )

    source_check()
    if not additions and not blobs:
        return snapshot
    checked(manifest)
    runtime = store if isinstance(store, RunStore) else RunStore(store)
    with tempfile.TemporaryDirectory(prefix="cppulse-consumer-") as temporary:
        descriptor = os.open(
            snapshot.path / "run_manifest.json",
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        )
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise IntegrityError("Parent manifest is not a regular file")
            parent_bytes = stream.read(cap + 1)
        if (
            len(parent_bytes) > cap
            or hashlib.sha256(parent_bytes).hexdigest() != snapshot.manifest_sha256
        ):
            raise IntegrityError(
                "Parent manifest changed or exceeds consumer metadata cap"
            )
        parent_file = Path(temporary) / "parent.json"
        parent_file.write_bytes(parent_bytes)
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
                    raise IntegrityError(
                        "Parent bytes changed during derived consumer copy"
                    )
            for index, blob in enumerate(blobs):
                raw_path = Path(temporary) / ("blob-" + str(index))
                raw_path.write_bytes(blob.content)
                stage.copy_artifact(blob.id, raw_path, blob.path, blob.media_type)
            provenance_id = "consumer-parent-" + snapshot.manifest_sha256
            stage.copy_artifact(
                provenance_id,
                parent_file,
                "consumer/provenance/" + provenance_id + ".json",
                "application/json",
            )
            for kind, document in additions:
                identity = hashlib.sha256(
                    (kind + ":" + document["id"]).encode()
                ).hexdigest()
                stage.write_json(
                    "consumer/" + kind + "/" + identity + ".json",
                    document,
                    artifact_id="consumer-" + identity,
                    contract=kind,
                )
            derived = deepcopy(manifest)
            derived.update(
                run_id=stage.run_id,
                artifacts=stage.artifacts,
                finished_at=datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            )
            derived["stages"].append(
                {
                    "id": "consumer-" + stage.run_id,
                    "status": "passed",
                    "depends_on": [],
                    "reason": "Consumer metadata retained; declaration is not verification success.",
                }
            )
            derived["versions"] = {
                **derived["versions"],
                "consumer-normalizer": _VERSION,
                "parent-manifest-sha256": snapshot.manifest_sha256,
            }
            checked(derived)
            # An unverified parent remains unverified: this copy cannot recover
            # missing historical before/after execution checks.
            return stage.publish(
                derived,
                source_check=(
                    source_check
                    if manifest.get("input_verification") == "verified"
                    else None
                ),
            )


def _text(content: bytes, kind: str) -> str:
    if len(content) > 10 * 1024 * 1024:
        raise CompatibilityError(f"{kind} exceeds the supported 10MiB format bound")
    try:
        value = content.decode("utf-8")
    except UnicodeError as error:
        raise CompatibilityError(f"{kind} is not UTF-8") from error
    if "\x00" in value or "\r" in value:
        raise CompatibilityError(f"Unsupported control characters in {kind}")
    return value


def parse_gcc_depfile(content: bytes) -> tuple[str, list[str]]:
    """Read one GCC14.2 GNU-make dependency rule, preserving escaped filenames.

    Multiple targets/rules, make-variable expansion and unsupported encodings
    stay unavailable. This parser does not execute make or touch listed paths.
    """
    text = _text(content, "GCC dependency file").replace("\\\n", " ").strip()
    if "\n" in text:
        raise CompatibilityError("Multiple dependency rules are unsupported")
    sides: list[list[str]] = [[], []]
    side, token, index, separator = 0, "", 0, False
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 1
            if index == len(text):
                raise CompatibilityError("Incomplete dependency filename escape")
            token += text[index]
        elif char == "$":
            if index + 1 >= len(text) or text[index + 1] != "$":
                raise CompatibilityError("Make variable expansion is unsupported")
            token += "$"
            index += 1
        elif char == ":":
            if side or separator:
                raise CompatibilityError("Ambiguous dependency rule separator")
            if token:
                sides[side].append(token)
                token = ""
            side, separator = 1, True
        elif char == "#":
            raise CompatibilityError("Unescaped dependency comments are unsupported")
        elif char.isspace():
            if token:
                sides[side].append(token)
                token = ""
        else:
            token += char
        index += 1
    if token:
        sides[side].append(token)
    if not separator or len(sides[0]) != 1 or not sides[1]:
        raise CompatibilityError("Expected one dependency target and observed inputs")
    return sides[0][0], list(dict.fromkeys(sides[1]))


def parse_gnu_linker_map(content: bytes) -> dict[str, list[str]]:
    """Read selected archive members from GNU ld2.44's initial selection section.

    A LOAD line alone is deliberately insufficient: an unused archive can be
    named by the command without contributing a member to the linked binary.
    """
    lines = _text(content, "GNU linker map").splitlines()
    heading = "Archive member included to satisfy reference by file (symbol)"
    if not lines or lines[0].strip() != heading:
        return {}
    result: dict[str, list[str]] = {}
    for line in lines[1:]:
        if line and not line.startswith((" ", "\t")):
            match = re.match(r"^([^()\n]+\.a)\(([^()\n]+)\)(?:\s|$)", line)
            if match is None:
                break
            archive, member = match.groups()
            result.setdefault(archive, [])
            if member not in result[archive]:
                result[archive].append(member)
    return result


def _absolute(value: str, cwd: str) -> str:
    if not value or "\x00" in value or "\\" in value:
        raise CompatibilityError("Unsupported observed POSIX path")
    return posixpath.normpath(
        value if value.startswith("/") else posixpath.join(cwd, value)
    )


def _workspace(plan: dict[str, Any], receipt: dict[str, Any]) -> str:
    step = next(row for row in plan["recipe"]["steps"] if row["id"] == receipt["id"])
    cwd = receipt["cwd"]
    if not cwd.startswith("/") or posixpath.normpath(cwd) != cwd:
        raise CompatibilityError("Observed consumer cwd is not canonical POSIX")
    parts = [] if step["cwd"] == "." else step["cwd"].split("/")
    suffix = "/".join(parts)
    if parts and not cwd.endswith("/" + suffix):
        raise CompatibilityError("Observed consumer cwd differs from selected plan")
    return cwd[: -len(suffix) - 1] if parts else cwd


def _flags(argv: list[str], cwd: str, *, probe: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "semantic": [],
        "macros": {},
        "sources": [],
        "archives": [],
        "includes": [],
        "output": None,
        "depfile": None,
        "map": None,
        "dependencies": False,
    }
    index = 1
    while index < len(argv):
        value = argv[index]
        if value in {"-o", "-MF", "-I", "-D", "-U", "-x"}:
            if index + 1 >= len(argv):
                raise CompatibilityError("Incomplete observed compiler option")
            parameter = argv[index + 1]
            index += 1
            if value == "-o":
                result["output"] = _absolute(parameter, cwd)
            elif value == "-MF":
                result["depfile"] = _absolute(parameter, cwd)
            elif value == "-I":
                result["includes"].append(_absolute(parameter, cwd))
            elif value == "-x":
                if not probe or parameter != "c++":
                    raise CompatibilityError(
                        "Only explicit C++ configuration probes are supported"
                    )
            else:
                name, _, selected = parameter.partition("=")
                if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                    raise CompatibilityError("Unsupported preprocessor definition")
                result["macros"][name] = None if value == "-U" else selected or "1"
                result["semantic"].append(value + parameter)
        elif value.startswith(("-D", "-U")):
            name, _, selected = value[2:].partition("=")
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                raise CompatibilityError("Unsupported preprocessor definition")
            result["macros"][name] = None if value.startswith("-U") else selected or "1"
            result["semantic"].append(value)
        elif value.startswith("-I"):
            result["includes"].append(_absolute(value[2:], cwd))
        elif value in {"-MD", "-MMD"}:
            result["dependencies"] = True
        elif value in {"-dM", "-E"} and probe:
            pass
        elif value == "-v":
            pass
        elif value.startswith("-Wl,-v,-Map,") and not probe:
            result["map"] = _absolute(value.removeprefix("-Wl,-v,-Map,"), cwd)
        elif value in {
            "-std=c++17",
            "-std=c++20",
            "-std=c++14",
            "-std=c++11",
            "-O0",
            "-O1",
            "-O2",
            "-O3",
            "-g",
            "-g0",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fexceptions",
            "-fno-exceptions",
            "-frtti",
            "-fno-rtti",
        }:
            result["semantic"].append(value)
        elif not value.startswith("-") and value.endswith((".cpp", ".cc", ".cxx")):
            result["sources"].append(_absolute(value, cwd))
        elif not probe and not value.startswith("-") and value.endswith(".a"):
            result["archives"].append(_absolute(value, cwd))
        else:
            raise CompatibilityError(f"Unreviewed compiler argument: {value!r}")
        index += 1
    if len(result["sources"]) != 1:
        raise CompatibilityError(
            "Use proof requires exactly one explicit C++ translation unit"
        )
    return result


def _fact_usable(fact: dict[str, Any]) -> bool:
    material = fact["material_status"] == "available"
    return bool(
        fact["receipt"]["status"] == "passed"
        and fact["binding"]["status"] == "verified"
        and material
        and fact["executable_fact"] is not None
        and not fact["logs_truncated"]
    )


def normalize_consumer_usage(
    snapshot: RunSnapshot,
    subject: dict[str, Any],
    *,
    usage_id: str,
    receipt_id: str,
    configuration_probe_receipt_id: str,
    target_probe_receipt_id: str,
    required_artifact_ids: Sequence[str],
    depfile_artifact_ids: Sequence[str] = (),
    link_map_artifact_id: str | None = None,
) -> dict[str, Any]:
    """Normalize actual selected package consumption from checked GCC facts.

    Only the exercised direct GCC14.2/ld2.44 slice is supported. No tools or
    project files are read. Invalid selections reject; missing/unsupported use
    proof remains unverified while usable partial observations are retained.
    """
    if not isinstance(snapshot, RunSnapshot):
        raise ContractError(
            "Current consumer use requires a local run, not imported claims"
        )
    bundle = _documents(snapshot)
    validate("distribution_subject", subject)
    _append(bundle, "distribution_subject", subject)
    validate_bundle(bundle)
    distributed = {row["artifact_id"]: row for row in subject["distribution_files"]}
    if (
        not required_artifact_ids
        or not set(required_artifact_ids) <= distributed.keys()
    ):
        raise ContractError(
            "Required use selection is outside its distribution subject"
        )
    facts = {row["receipt"]["id"]: row for row in bundle.get("execution_facts", [])}
    if receipt_id not in facts:
        raise ContractError("Selected consumer receipt lacks typed execution facts")
    fact = facts[receipt_id]
    receipt = fact["receipt"]
    issues = []
    result: dict[str, Any] = {
        "version": "2.0.0",
        "id": usage_id,
        "source_digest": snapshot.manifest["source"]["digest"],
        "subject_id": subject["id"],
        "context_id": receipt["context_id"],
        "receipt_id": receipt_id,
        "producer": {"name": "cppulse.consumer-use", "version": _VERSION},
        "status": "unverified",
        "required_artifact_ids": list(required_artifact_ids),
        "records": [],
        "proof_receipt_ids": [receipt_id],
        "observed_configuration": None,
        "configuration_probe_receipt_id": None,
        "target_probe_receipt_id": None,
        "compiler_version": None,
        "linker_version": None,
        "self_containment_headers": [],
        "limitations": [],
    }
    descriptors = {row["id"]: row for row in snapshot.manifest["artifacts"]}

    def same(first: str, second: str) -> bool:
        return all(
            descriptors[first][key] == descriptors[second][key]
            for key in ("sha256", "size_bytes")
        )

    def logs(selected: dict[str, Any], stream: str) -> bytes:
        identifier = selected["binding"]["log_artifacts"][stream]
        if identifier is None:
            raise CompatibilityError("Observed compiler/probe stream was not retained")
        return snapshot.read_bytes(identifier)

    try:
        if snapshot.manifest.get(
            "input_verification"
        ) != "verified" or not _fact_usable(fact):
            raise CompatibilityError(
                "Consumer execution/source/material is incomplete or unverified"
            )
        candidates = [
            plan
            for plan in bundle.get("collection_plan", [])
            for step in plan["recipe"]["steps"]
            if step["id"] == receipt_id
            and step["argv"] == receipt["argv"]
            and step["context_id"] == receipt["context_id"]
        ]
        if len(candidates) != 1:
            raise CompatibilityError(
                "Consumer receipt does not bind one exact retained recipe step"
            )
        workspace = _workspace(candidates[0], receipt)
        arguments = _flags(receipt["argv"], receipt["cwd"])
        source_roles = [
            row
            for row in fact["binding"]["input_artifacts"]
            if _absolute(row["path"], workspace) == arguments["sources"][0]
        ]
        selected_sources = [
            row
            for row in snapshot.manifest["source"]["files"]
            if _absolute(row["path"], workspace) == arguments["sources"][0]
        ]
        if (
            len(source_roles) != 1
            or len(selected_sources) != 1
            or any(
                descriptors[source_roles[0]["artifact_id"]][key]
                != selected_sources[0][key]
                for key in ("sha256", "size_bytes")
            )
        ):
            raise CompatibilityError(
                "Actual compiler source operand is not the byte-bound selected consumer source"
            )
        compiler_versions = set(
            re.findall(
                r"^gcc version ([0-9.]+)(?: |$)",
                _text(logs(fact, "stderr"), "GCC build log"),
                re.MULTILINE,
            )
        )
        if compiler_versions != {"14.2.0"}:
            raise CompatibilityError("Unsupported or ambiguous actual GCC version log")
        result["compiler_version"] = "14.2.0"
        linker_versions = set(
            re.findall(
                r"^GNU ld [^\n]*? ([0-9]+\.[0-9]+)(?:\s|$)",
                _text(logs(fact, "stdout"), "linker build log"),
                re.MULTILINE,
            )
        )
        if len(linker_versions) == 1:
            result["linker_version"] = next(iter(linker_versions))
        probes = []
        for identifier in (configuration_probe_receipt_id, target_probe_receipt_id):
            selected = facts.get(identifier)
            if (
                selected is None
                or not _fact_usable(selected)
                or selected["receipt"]["context_id"] != receipt["context_id"]
                or selected["executable_fact"]["sha256"]
                != fact["executable_fact"]["sha256"]
            ):
                raise CompatibilityError(
                    "Configuration/target probe is missing, incomplete or from another compiler job"
                )
            probes.append(selected)
        configuration_probe, target_probe = probes
        probe_flags = _flags(
            configuration_probe["receipt"]["argv"],
            configuration_probe["receipt"]["cwd"],
            probe=True,
        )
        if (
            arguments["semantic"] != probe_flags["semantic"]
            or arguments["includes"] != probe_flags["includes"]
            or not {"-dM", "-E"} <= set(configuration_probe["receipt"]["argv"])
        ):
            raise CompatibilityError(
                "Configuration probe does not use the observed build flags/include context"
            )
        if target_probe["receipt"]["argv"][1:] != ["-dumpmachine"]:
            raise CompatibilityError(
                "Target probe must explicitly inspect the same GCC driver"
            )
        probe_plans = [
            plan
            for plan in bundle.get("collection_plan", [])
            for step in plan["recipe"]["steps"]
            if step["id"] == configuration_probe_receipt_id
            and step["argv"] == configuration_probe["receipt"]["argv"]
            and step["context_id"] == receipt["context_id"]
        ]
        if len(probe_plans) != 1:
            raise CompatibilityError(
                "Macro probe does not bind one exact retained recipe step"
            )
        probe_workspace = _workspace(probe_plans[0], configuration_probe["receipt"])
        if probe_workspace != workspace:
            raise CompatibilityError("Macro probe belongs to another workspace")
        probe_sources = [
            row
            for row in configuration_probe["binding"]["input_artifacts"]
            if _absolute(row["path"], workspace) == probe_flags["sources"][0]
        ]
        if len(probe_sources) != 1:
            raise CompatibilityError("Macro probe source bytes were not retained")
        probe_body = _text(
            snapshot.read_bytes(probe_sources[0]["artifact_id"]),
            "configuration probe source",
        )
        probe_body = re.sub(r"//[^\n]*|/\*.*?\*/", "", probe_body, flags=re.DOTALL)
        if not re.fullmatch(r"\s*#\s*include\s*<bits/c\+\+config\.h>\s*", probe_body):
            raise CompatibilityError(
                "Unreviewed macro probe source could override toolchain facts"
            )
        macros = {}
        for line in _text(
            logs(configuration_probe, "stdout"), "GCC macro probe"
        ).splitlines():
            match = re.fullmatch(r"#define ([A-Za-z_][A-Za-z0-9_]*) (.*)", line)
            if match:
                macros[match[1]] = match[2]
        standard = {
            "199711L": "c++98",
            "201103L": "c++11",
            "201402L": "c++14",
            "201703L": "c++17",
            "202002L": "c++20",
        }.get(macros.get("__cplusplus"))
        selected_standard = [
            flag.removeprefix("-std=")
            for flag in arguments["semantic"]
            if flag.startswith("-std=")
        ]
        if len(selected_standard) != 1 or standard != selected_standard[0]:
            raise CompatibilityError(
                "Macro-observed language standard differs from the selected compiler flags"
            )
        target = _text(logs(target_probe, "stdout"), "GCC target probe").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.+-]+", target):
            raise CompatibilityError("Target probe is missing or ambiguous")
        outputs = {
            row["artifact_id"]: row["path"]
            for row in fact["binding"]["output_artifacts"]
        }
        if arguments["output"] not in {
            _absolute(path, workspace) for path in outputs.values()
        }:
            raise CompatibilityError(
                "Actual selected compiler output bytes were not retained"
            )
        input_paths = {}
        for identifier in required_artifact_ids:
            links = [
                row
                for row in fact["binding"]["input_artifacts"]
                if row["artifact_id"] == identifier
            ]
            if not links:
                links = [
                    row
                    for row in fact["binding"]["input_artifacts"]
                    if same(row["artifact_id"], identifier)
                ]
            if len(links) != 1:
                raise CompatibilityError(
                    "Selected distribution input is absent or byte-aliased ambiguously"
                )
            input_paths[identifier] = _absolute(links[0]["path"], workspace)
        dependencies = set()
        all_input_paths = {
            _absolute(row["path"], workspace): row["artifact_id"]
            for row in fact["binding"]["input_artifacts"]
        }
        if not depfile_artifact_ids:
            issues.append(
                "A retained compiler dependency rule is required for selected source/dependency identity"
            )
        for identifier in depfile_artifact_ids:
            if identifier not in outputs:
                raise ContractError(
                    "Dependency proof is not a selected compiler output"
                )
            if not arguments["dependencies"] or arguments["depfile"] != _absolute(
                outputs[identifier], workspace
            ):
                raise CompatibilityError(
                    "Retained dependency file is not the actual GCC output selection"
                )
            target_name, paths = parse_gcc_depfile(snapshot.read_bytes(identifier))
            if _absolute(target_name, receipt["cwd"]) != arguments["output"]:
                raise CompatibilityError(
                    "Dependency target is not the selected compiled output"
                )
            dependencies = {_absolute(path, receipt["cwd"]) for path in paths}
            if arguments["sources"][0] not in dependencies:
                raise CompatibilityError(
                    "Dependency proof does not name the actual selected consumer source"
                )
            if any(
                path.startswith(workspace.rstrip("/") + "/")
                and path not in all_input_paths
                for path in dependencies
            ):
                raise CompatibilityError(
                    "Actual workspace source/header dependency was not a byte-bound declared compiler input"
                )
            for artifact_id, path in input_paths.items():
                if path in dependencies and not path.endswith(".a"):
                    result["records"].append(
                        {
                            "distribution_artifact_id": artifact_id,
                            "proof_kind": "depfile",
                            "proof_artifact_id": identifier,
                            "members": [posixpath.relpath(path, workspace)],
                        }
                    )
        archives = {}
        if arguments["archives"] and link_map_artifact_id is None:
            issues.append(
                "Archive arguments require a fresh member map for dependency context"
            )
        if link_map_artifact_id is not None:
            if link_map_artifact_id not in outputs:
                raise ContractError("Link map proof is not a selected compiler output")
            if result["linker_version"] != "2.44" or arguments["map"] != _absolute(
                outputs[link_map_artifact_id], workspace
            ):
                raise CompatibilityError(
                    "Unsupported actual GNU linker version or mismatched map output"
                )
            archives = {
                _absolute(path, receipt["cwd"]): members
                for path, members in parse_gnu_linker_map(
                    snapshot.read_bytes(link_map_artifact_id)
                ).items()
            }
            for artifact_id, path in input_paths.items():
                if path in archives and path in arguments["archives"]:
                    result["records"].append(
                        {
                            "distribution_artifact_id": artifact_id,
                            "proof_kind": "gnu-linker-map",
                            "proof_artifact_id": link_map_artifact_id,
                            "members": archives[path],
                        }
                    )
            if any(
                path.startswith(workspace.rstrip("/") + "/")
                and path not in all_input_paths
                for path in archives
            ):
                raise CompatibilityError(
                    "Actual local archive dependency was not a byte-bound declared compiler input"
                )
        covered = {row["distribution_artifact_id"] for row in result["records"]}
        for identifier in required_artifact_ids:
            if identifier not in covered:
                issues.append(
                    "Required archive member was not observed"
                    if input_paths[identifier].endswith(".a")
                    else "Required selected header was not observed in dependency output"
                )
        abi_keys = ["__GXX_ABI_VERSION", "__GLIBCXX__", "_GLIBCXX_USE_CXX11_ABI"]
        abi = (
            "observed-macros-v1:"
            + ";".join(key + "=" + macros[key] for key in abi_keys)
            if all(key in macros for key in abi_keys)
            else None
        )
        result["observed_configuration"] = {
            "compiler": {
                "name": "GNU",
                "version": "14.2.0",
                "sha256": fact["executable_fact"]["sha256"],
            },
            "os": "linux" if "__linux__" in macros else None,
            "target": target,
            "abi": abi,
            "language_standard": standard,
            "macros": arguments["macros"],
            "exceptions": "__EXCEPTIONS" in macros,
            "rtti": "__GXX_RTTI" in macros,
            "linking": "static" if arguments["archives"] else "header-only",
            "dependencies": [
                {
                    "id": "input-"
                    + hashlib.sha256(
                        posixpath.relpath(path, workspace).encode("utf-8")
                    ).hexdigest(),
                    "sha256": descriptors[all_input_paths[path]]["sha256"],
                    "availability": "available",
                }
                for path in sorted(
                    (dependencies | set(archives))
                    & set(all_input_paths) - set(arguments["sources"])
                )
            ],
            "sanitizers": [],
        }
        result["configuration_probe_receipt_id"] = configuration_probe_receipt_id
        result["target_probe_receipt_id"] = target_probe_receipt_id
        result["proof_receipt_ids"] = list(
            dict.fromkeys(
                [receipt_id, configuration_probe_receipt_id, target_probe_receipt_id]
            )
        )
        if not any(row["proof_kind"] == "gnu-linker-map" for row in result["records"]):
            source_links = [
                row
                for row in fact["binding"]["input_artifacts"]
                if _absolute(row["path"], workspace) == arguments["sources"][0]
            ]
            if len(source_links) == 1:
                body = _text(
                    snapshot.read_bytes(source_links[0]["artifact_id"]),
                    "selected C++ translation unit",
                )
                body = re.sub(r"//[^\n]*|/\*.*?\*/", "", body, flags=re.DOTALL)
                minimal = re.fullmatch(
                    r'\s*#\s*include\s*[<"]([^>"\n]+)[>"]\s*int\s+main\s*\(\s*\)\s*\{\s*return\s+0\s*;\s*\}\s*',
                    body,
                )
                if minimal:
                    for identifier, path in input_paths.items():
                        if identifier in covered and any(
                            posixpath.join(include, minimal[1]) == path
                            for include in arguments["includes"]
                        ):
                            result["self_containment_headers"].append(
                                distributed[identifier]["path"]
                            )
        if not issues:
            result["status"] = "verified"
    except CompatibilityError as error:
        issues.append(str(error))
    result["limitations"] = list(
        dict.fromkeys(
            [
                *issues,
                "Use and configuration describe the selected compiler inputs/outputs only; host runtime/header closure and producer authenticity are not established.",
                "ABI identifies observed compiler/library macros, not a general binary-compatibility result.",
                "Template instantiation names remain declared selected test scope, not exhaustive template coverage.",
            ]
        )
    )
    validate("consumer_usage", result)
    _append(bundle, "consumer_usage", result)
    validate_bundle(bundle)
    return result


def _utc(value: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)", value
    ):
        raise ContractError("Comparison requires explicit RFC3339 UTC generated_at")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ContractError("Invalid comparison generation time") from error


def _date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))


def _manifest_bytes(snapshot: RunSnapshot | ImportedRun) -> bytes:
    if isinstance(snapshot, ImportedRun):
        content = snapshot.read_manifest_bytes()
    else:
        descriptor = os.open(
            snapshot.path / "run_manifest.json",
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
        )
        with os.fdopen(descriptor, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise IntegrityError("Comparison manifest is not a regular file")
            content = stream.read(16 * 1024 * 1024 + 1)
    if (
        len(content) > 16 * 1024 * 1024
        or hashlib.sha256(content).hexdigest() != snapshot.manifest_sha256
    ):
        raise IntegrityError("Comparison manifest exceeds bound or changed")
    return content


def _selected(bundle: dict[str, Any], kind: str, identifier: str) -> dict[str, Any]:
    candidates = [row for row in bundle.get(kind, []) if row["id"] == identifier]
    if len(candidates) != 1:
        raise ContractError(f"Expected one retained {kind}: {identifier}")
    return candidates[0]


def _raw_document(
    snapshot: RunSnapshot | ImportedRun, kind: str, identifier: str
) -> bytes:
    candidates = [
        entry
        for entry in snapshot.manifest["artifacts"]
        if entry.get("contract", {}).get("kind") == kind
        and snapshot.read_json(entry["id"])["id"] == identifier
    ]
    if len(candidates) != 1:
        raise ContractError(f"Expected one byte-bound original {kind}: {identifier}")
    return snapshot.read_bytes(candidates[0]["id"])


def _known_configuration(configuration: dict[str, Any]) -> bool:
    for key, value in configuration.items():
        if value is None or (key == "compiler" and value["sha256"] is None):
            return False
        if key == "dependencies" and any(
            row["availability"] != "available" or row["sha256"] is None for row in value
        ):
            return False
    return True


def _case_usage(
    bundle: dict[str, Any], case: dict[str, Any], subject_id: str
) -> tuple[list[dict[str, Any]], str | None]:
    usages = {row["id"]: row for row in bundle.get("consumer_usage", [])}
    selected = [
        usages[identifier] for identifier in case["usage_ids"] if identifier in usages
    ]
    if any(row["subject_id"] != subject_id for row in selected):
        return (
            [],
            "Selected package-use evidence belongs to another distribution subject",
        )
    if not selected or len(selected) != len(case["usage_ids"]):
        return selected, "Declared package-use checks are missing"
    if any(
        row["status"] != "verified" or row["context_id"] != case["context_id"]
        for row in selected
    ):
        return (
            selected,
            "Selected package-use checks are incomplete or belong to another context",
        )
    if not _known_configuration(case["configuration"]):
        return selected, "A declared configuration dimension is unavailable"
    if any(row["observed_configuration"] != case["configuration"] for row in selected):
        return (
            selected,
            "Declared configuration differs from the independently observed compiler context",
        )
    return selected, None


def _test_outcomes(
    bundle: dict[str, Any],
    case: dict[str, Any],
    usages: list[dict[str, Any]],
    now: datetime,
) -> tuple[str, list[str], list[str]]:
    evidence = {
        row["id"]: row
        for document in bundle.get("evidence", [])
        for row in document["records"]
    }
    facts = {row["receipt"]["id"]: row for row in bundle.get("execution_facts", [])}
    receipts = {row["id"]: row for row in bundle.get("execution_receipt", [])}
    descriptors = {row["id"]: row for row in bundle["run_manifest"]["artifacts"]}
    expected = {}
    for usage in usages:
        if usage["status"] != "verified":
            continue
        fact = facts[usage["receipt_id"]]
        plans = [
            plan
            for plan in bundle.get("collection_plan", [])
            for step in plan["recipe"]["steps"]
            if step["id"] == usage["receipt_id"]
        ]
        if len(plans) != 1:
            continue
        root = _workspace(plans[0], fact["receipt"])
        output = _flags(fact["receipt"]["argv"], fact["receipt"]["cwd"])["output"]
        for link in fact["binding"]["output_artifacts"]:
            if _absolute(link["path"], root) == output:
                descriptor = descriptors[link["artifact_id"]]
                expected[(descriptor["sha256"], descriptor["size_bytes"])] = usage[
                    "receipt_id"
                ]
    selected_ids = []
    missing = []
    failed = []
    covered = set()
    for name in case["tests"]:
        record = evidence.get(name)
        if (
            record is None
            or record["kind"] != "tests"
            or record["origin"] != "execution"
            or record["usability"] != "usable"
            or record["context_id"] != case["context_id"]
            or record["receipt_id"] not in facts
            or (record.get("expires_at") and _date(record["expires_at"]) <= now)
        ):
            missing.append(name)
            continue
        receipt = receipts[record["receipt_id"]]
        if _date(receipt["finished_at"]) > now:
            raise ContractError("Comparison predates selected local test facts")
        counts = receipt.get("tests")
        if (
            not counts
            or not counts["total"]
            or counts["errors"]
            or (
                record["status"] == "passed"
                and (not counts["passed"] or counts["failed"])
            )
            or (record["status"] == "failed" and not counts["failed"])
            or record["status"] not in {"passed", "failed"}
        ):
            missing.append(name)
            continue
        pending = list(receipt["depends_on"])
        ancestors = set()
        while pending:
            parent = pending.pop()
            if parent not in ancestors:
                ancestors.add(parent)
                pending.extend(receipts[parent]["depends_on"])
        exercised = {
            (
                descriptors[link["artifact_id"]]["sha256"],
                descriptors[link["artifact_id"]]["size_bytes"],
            )
            for link in facts[record["receipt_id"]]["binding"]["input_artifacts"]
        }
        matching = {
            identity
            for identity, producer in expected.items()
            if identity in exercised and producer in ancestors
        }
        if (
            not matching
            or bundle["run_manifest"].get("input_verification") != "verified"
        ):
            missing.append(name)
            continue
        selected_ids.append(name)
        covered.update(matching)
        if record["status"] == "failed":
            failed.append(name)
    if not case["tests"]:
        return "unknown", [], ["application-tests:undeclared"]
    if not set(expected) <= covered or not expected:
        missing = list(case["tests"])
    return (
        ("failed" if failed else "unknown" if missing else "passed"),
        selected_ids,
        missing,
    )


def compare_consumers(
    upstream: RunSnapshot | ImportedRun,
    local: RunSnapshot,
    *,
    upstream_subject_id: str,
    local_subject_id: str,
    upstream_matrix_id: str,
    local_matrix_id: str,
    generated_at: str,
    case_mapping: Mapping[str, str] | None = None,
    comparison_id: str | None = None,
) -> ConsumerComparison:
    """Compare checked foreign scope with independently observed local consumers.

    ``compatible`` means scoped configuration correspondence only. Foreign
    source identities and raw documents stay separate; authentication is always
    unverified. Tests are expected evidence-check names/IDs, not implicit JUnit
    case-name searches. No local tools, project files or wall clock are read.
    """
    if not isinstance(local, RunSnapshot):
        raise ContractError(
            "Current local consumer evidence requires a local RunSnapshot"
        )
    if not isinstance(upstream, (RunSnapshot, ImportedRun)):
        raise ContractError(
            "Upstream comparison requires a checked retained/imported run"
        )
    now = _utc(generated_at)
    up, down = _documents(upstream), _documents(local)
    if any(_date(bundle["run_manifest"]["finished_at"]) > now for bundle in [up, down]):
        raise ContractError(
            "Comparison generation time precedes retained source/run facts"
        )
    up_subject = _selected(up, "distribution_subject", upstream_subject_id)
    local_subject = _selected(down, "distribution_subject", local_subject_id)
    up_matrix = _selected(up, "consumer_matrix", upstream_matrix_id)
    local_matrix = _selected(down, "consumer_matrix", local_matrix_id)
    if (
        up_matrix["subject_id"] != upstream_subject_id
        or local_matrix["subject_id"] != local_subject_id
    ):
        raise ContractError("Selected matrix describes another distribution subject")
    if case_mapping and not set(case_mapping) <= {
        row["id"] for row in local_matrix["cases"]
    }:
        raise ContractError("Case mapping includes an unknown local requirement")
    up_files = {
        row["path"]: (row["sha256"], row["size_bytes"])
        for row in up_subject["distribution_files"]
    }
    local_files = {
        row["path"]: (row["sha256"], row["size_bytes"])
        for row in local_subject["distribution_files"]
    }
    package_matches = (
        up_files == local_files and up_subject["kind"] == local_subject["kind"]
    )
    upstream_cases = {row["id"]: row for row in up_matrix["cases"]}
    cases = []
    for case in local_matrix["cases"]:
        selected_up = upstream_cases.get(
            (case_mapping or {}).get(case["id"], case["id"])
        )
        if selected_up is None and not case_mapping and len(upstream_cases) == 1:
            selected_up = next(iter(upstream_cases.values()))
        usages, local_issue = _case_usage(down, case, local_subject_id)
        _, up_issue = (
            _case_usage(up, selected_up, upstream_subject_id)
            if selected_up
            else ([], "No unambiguous upstream consumer case is selected")
        )
        matching = []
        mismatches = []
        if selected_up:
            for key, value in case["configuration"].items():
                other = selected_up["configuration"][key]
                if value is not None and other is not None:
                    (matching if value == other else mismatches).append(key)
        if not package_matches:
            mismatches = ["distribution", *mismatches]
            status, reason = (
                "incompatible",
                "Selected distributed artifact bytes/logical paths or package kind differ; upstream evidence cannot identify this package.",
            )
        elif local_issue or up_issue:
            status, reason = "unknown", "; ".join(
                value for value in [local_issue, up_issue] if value
            )
        elif mismatches:
            status, reason = (
                "incompatible",
                "Observed selected configuration differs in: " + ", ".join(mismatches),
            )
        else:
            status, reason = (
                "compatible",
                "All selected known configuration dimensions correspond; this is not an application-test or release pass.",
            )
        test_status, evidence_ids, missing = _test_outcomes(
            down, case, usages if local_issue is None else [], now
        )
        required = list(case["tests"])
        if not required:
            required.append("application-tests:undeclared")
        required.extend(case["self_containment_headers"])
        headers = {
            header
            for usage in usages
            if usage["status"] == "verified" and local_issue is None
            for header in usage["self_containment_headers"]
        }
        missing.extend(
            header
            for header in case["self_containment_headers"]
            if header not in headers
        )
        for name in case["instantiations"]:
            check = "selected-instantiation:" + name
            required.append(check)
            if test_status != "passed" or local_issue:
                missing.append(check)
        if not case["usage_ids"]:
            required.append("package-use:undeclared")
            missing.append("package-use:undeclared")
        else:
            for identifier in case["usage_ids"]:
                check = "package-use:" + identifier
                required.append(check)
                if not any(
                    usage["id"] == identifier and usage["status"] == "verified"
                    for usage in usages
                ):
                    missing.append(check)
        cases.append(
            {
                "case_id": case["id"],
                "upstream_case_id": selected_up["id"] if selected_up else None,
                "status": status,
                "reason": reason,
                "matching_dimensions": matching,
                "mismatches": mismatches,
                "local_test_status": test_status,
                "local_test_evidence_ids": evidence_ids,
                "required_local_checks": list(dict.fromkeys(required)),
                "missing_local_checks": list(dict.fromkeys(missing)),
            }
        )

    def raw(role: str, content: bytes) -> RetainedBlob:
        identity = "consumer-" + role + "-" + hashlib.sha256(content).hexdigest()
        return RetainedBlob(identity, "consumer/imports/" + identity + ".json", content)

    blobs = (
        raw("upstream-manifest", _manifest_bytes(upstream)),
        raw("local-manifest", _manifest_bytes(local)),
        raw(
            "upstream-subject",
            _raw_document(upstream, "distribution_subject", upstream_subject_id),
        ),
        raw(
            "upstream-matrix",
            _raw_document(upstream, "consumer_matrix", upstream_matrix_id),
        ),
    )
    document = {
        "version": "2.0.0",
        "id": comparison_id
        or "comparison-"
        + hashlib.sha256(
            (
                upstream.manifest_sha256
                + local.manifest_sha256
                + generated_at
                + upstream_matrix_id
                + local_matrix_id
            ).encode()
        ).hexdigest(),
        "source_digest": local.manifest["source"]["digest"],
        "local_source_digest": local.manifest["source"]["digest"],
        "upstream_source_digest": upstream.manifest["source"]["digest"],
        "upstream_manifest_sha256": upstream.manifest_sha256,
        "local_manifest_sha256": local.manifest_sha256,
        "upstream_manifest_artifact_id": blobs[0].id,
        "local_manifest_artifact_id": blobs[1].id,
        "upstream_subject_artifact_id": blobs[2].id,
        "upstream_matrix_artifact_id": blobs[3].id,
        "upstream_subject_id": upstream_subject_id,
        "local_subject_id": local_subject_id,
        "upstream_matrix_id": upstream_matrix_id,
        "local_matrix_id": local_matrix_id,
        "import_origin": "import",
        "authentication": "unverified",
        "producer": {"name": "cppulse.consumer-compare", "version": _VERSION},
        "generated_at": generated_at,
        "cases": cases,
        "limitations": [
            "Upstream raw source/execution fields remain unauthenticated imported claims, not current local assurance.",
            "Compatible means configuration correspondence for selected artifact bytes only; matching upstream evidence never substitutes for local application tests.",
            "Declared template instantiation names label selected compiled/tested source scope; no exhaustive semantic template coverage is inferred.",
            "ABI labels identify observed compiler/library macros, not a general binary-compatibility guarantee.",
        ],
    }
    validate("consumer_comparison", document)
    preview = deepcopy(down)
    known = {row["id"] for row in preview["run_manifest"]["artifacts"]}
    for blob in blobs:
        if blob.id not in known:
            preview["run_manifest"]["artifacts"].append(blob.descriptor())
            known.add(blob.id)
    _append(preview, "consumer_comparison", document)
    validate_bundle(preview)
    return ConsumerComparison(document, blobs)
