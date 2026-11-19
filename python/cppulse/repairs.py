"""Finite native-bound textual repair proposals; source files are never applied.

The sole initial transformation is a simple one-line builtin typedef declaration
already observed by libclang. Plans retain original execution identities. A patch
is not execution evidence, proof of semantic equivalence or authorization to
compile, commit, submit a PR or contact a service.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import difflib
import hashlib
from importlib import resources
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
import tempfile
from typing import Any

import jsonschema

from cppulse.contracts import validate_bundle
from cppulse.errors import ContractError, CppulseError
from cppulse.identities import digest_json, file_identity
from cppulse.run_store import RunSnapshot, RunStore
from cppulse.workflows import ensure_current_materials, read_documents

METHOD = "cppulse-builtin-typedef-to-using-v1"
RULE_VERSION = "prototype-1"
MAX_SNAPSHOT_BYTES = 32 * 1024**2
MAX_SOURCE_BYTES = 1024**2
MAX_OBSERVATIONS = 64
_BUILTIN = rb"(?:const|volatile|signed|unsigned|short|long|int|char|bool|float|double|wchar_t|char16_t|char32_t|void)"
_ALIAS = re.compile(
    rb"(?P<indent>[ \t]*)typedef[ \t]+(?P<type>"
    + _BUILTIN
    + rb"(?:[ \t]+"
    + _BUILTIN
    + rb")*)[ \t]+(?P<name>[A-Za-z_][A-Za-z_0-9]*)[ \t]*;(?P<tail>[ \t]*(?://[^\r\n]*)?)(?P<ending>\r\n|\r|\n)?\Z"
)
_LIMITATIONS = [
    "Dry-run textual proposal only: no source write, command, commit, PR or network operation occurred.",
    "Only simple builtin typedef declarations in selected complete native contexts are supported; other declarations remain unsupported.",
    "Original receipt identities are retained. A patch does not constitute fresh build/test, ABI, performance or runtime evidence.",
    "Source freshness covers the retained finite input/output inventory; unlisted additions and the complete host/dependency closure are not established.",
    "Compile and test the proposed source in every required configuration before accepting it; no semantic or safety equivalence is claimed.",
]


@dataclass(frozen=True)
class _Candidate:
    file: str
    start: int
    end: int
    before: bytes
    after: bytes
    reference: dict[str, str]


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _path(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or not path.parts
        or bool(PureWindowsPath(value).drive)
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in value
        or str(path) != value
        or "\x00" in value
    ):
        raise ContractError(
            "Repair path must be a canonical repository-relative POSIX path"
        )


def validate_plan(plan: dict[str, Any]) -> None:
    """Validate a finite review artifact, including byte bounds and self-digests."""
    schema = json.loads(
        resources.files("cppulse.contracts")
        .joinpath("schemas/repairs_private/plan.schema.json")
        .read_bytes()
    )
    try:
        jsonschema.Draft7Validator.check_schema(schema)
        jsonschema.validate(plan, schema)
        json.dumps(plan, allow_nan=False)
    except (
        jsonschema.ValidationError,
        jsonschema.SchemaError,
        ValueError,
        TypeError,
    ) as error:
        raise ContractError(f"Invalid repair plan: {error}") from error
    body = {key: value for key, value in plan.items() if key != "id"}
    if plan["id"] != "repair-" + digest_json(body) or plan["diff_sha256"] != _sha(
        plan["diff"].encode()
    ):
        raise ContractError("Repair plan differs from its recorded digest")
    if (plan["status"] == "planned") != bool(plan["edits"]):
        raise ContractError("Repair plan status disagrees with proposed edits")
    ends: dict[str, int] = {}
    file_hashes: dict[str, tuple[str, str]] = {}
    refs: set[str] = set()
    for edit in plan["edits"]:
        _path(edit["file"])
        if edit["end_byte"] <= edit["start_byte"] or edit["end_byte"] - edit[
            "start_byte"
        ] != len(edit["before"].encode()):
            raise ContractError(
                "Repair byte bounds disagree with retained original text"
            )
        if edit["start_byte"] < ends.get(edit["file"], 0):
            raise ContractError("Repair edits overlap or are out of order")
        ends[edit["file"]] = edit["end_byte"]
        identity = (edit["before_sha256"], edit["after_sha256"])
        if edit["file"] in file_hashes and file_hashes[edit["file"]] != identity:
            raise ContractError("Repair file hashes conflict")
        file_hashes[edit["file"]] = identity
        for ref in edit["observations"]:
            if ref["id"] in refs:
                raise ContractError("Repair observation is selected more than once")
            refs.add(ref["id"])
            if len(refs) > MAX_OBSERVATIONS:
                raise ContractError(
                    "Repair plan exceeds the finite selected-observation bound"
                )


def _line_span(content: bytes, line: int) -> tuple[int, int]:
    starts = [0] + [match.end() for match in re.finditer(rb"\r\n|\r|\n", content)]
    if line < 1 or line > len(starts):
        raise ContractError("Observed repair line lies outside retained bytes")
    start = starts[line - 1]
    return start, starts[line] if line < len(starts) else len(content)


def _source_content(
    snapshot: RunSnapshot,
    documents: dict[str, Any],
    inventory: dict[str, Any],
    file: str,
) -> bytes:
    source = {row["path"]: row for row in snapshot.manifest["source"]["files"]}
    if file not in source:
        raise ContractError(
            "Repair source is absent from the retained source inventory"
        )
    if source[file]["size_bytes"] > MAX_SOURCE_BYTES:
        raise ContractError(
            "Repair source exceeds the supported one-MiB transformation bound"
        )
    facts = [
        row
        for row in documents.get("execution_facts", [])
        if row["receipt"]["id"] == inventory["receipt_id"]
    ]
    if (
        len(facts) != 1
        or facts[0]["binding"]["status"] != "verified"
        or facts[0]["receipt"]["status"] != "passed"
    ):
        raise ContractError(
            "Repair needs the original passed, verified native execution facts"
        )
    selected = [
        row for row in facts[0]["binding"]["input_artifacts"] if row["path"] == file
    ]
    if len(selected) != 1:
        raise ContractError(
            "Repair source bytes were not retained as an original native input"
        )
    content = snapshot.read_bytes(selected[0]["artifact_id"])
    if (
        _sha(content) != source[file]["sha256"]
        or len(content) != source[file]["size_bytes"]
    ):
        raise ContractError(
            "Repair source bytes differ from the selected source identity"
        )
    content.decode("utf-8")
    return content


def _check_original_finding(
    snapshot: RunSnapshot,
    documents: dict[str, Any],
    inventory: dict[str, Any],
    observation: dict[str, Any],
    workspace: Path,
    reports: dict[str, dict[str, Any]],
) -> None:
    """Require a matching finding in the receipt-bound original producer bytes."""
    identifier = inventory["report_artifact_id"]
    if identifier not in reports:
        reports[identifier] = snapshot.read_json(
            identifier, contract=("findings", "prototype_v1")
        )
    report = reports[identifier]
    receipt = next(
        row
        for row in documents["execution_receipt"]
        if row["id"] == inventory["receipt_id"]
    )
    repo = Path(report["metadata"]["repo_path"])
    if not repo.is_absolute():
        repo = Path(receipt["cwd"]) / repo
    for finding in report["findings"]:
        if any(
            finding.get(key) != observation.get(key)
            for key in ("rule_id", "line", "column", "severity", "message")
        ):
            continue
        path = Path(finding["file"])
        if (
            file_identity(workspace, path if path.is_absolute() else repo / path)
            == observation["file"]
        ):
            return
    raise ContractError("Repair observation does not match its original native report")


def _candidate(
    snapshot: RunSnapshot,
    documents: dict[str, Any],
    inventory: dict[str, Any],
    observation: dict[str, Any],
) -> tuple[_Candidate, bytes]:
    file = observation["file"]
    _path(file)
    selected = [row for row in inventory["items"] if row["file"] == file]
    if len(selected) != 1:
        raise ContractError("Repair file has no unambiguous native scope cell")
    cell = selected[0]
    if (
        cell["status"] != "analyzed"
        or cell["error_count"]
        or cell["context_match"] != "matched"
        or cell["parse_context_id"] != observation["context_id"]
        or observation["rule_id"] not in cell["executed_rules"]
    ):
        raise ContractError(
            "Repair needs complete matched analysis and observed rule execution"
        )
    registry = snapshot.read_json(
        inventory["registry_artifact_id"], contract="rule_registry"
    )
    rule = next((row for row in registry["rules"] if row["id"] == "CPP-MOD-009"), None)
    if (
        rule is None
        or rule["version"] != observation["rule_version"]
        or rule["version"] != RULE_VERSION
    ):
        raise ContractError(
            "Repair rule version differs from the retained native registry"
        )
    contexts = {row["id"]: row for row in snapshot.manifest["contexts"]}
    context = contexts.get(observation["context_id"])
    standards = (
        []
        if context is None
        else [
            arg.removeprefix("-std=")
            for arg in context["argv"]
            if arg.startswith("-std=")
        ]
    )
    supported = {
        "c++11",
        "gnu++11",
        "c++14",
        "gnu++14",
        "c++17",
        "gnu++17",
        "c++20",
        "gnu++20",
    }
    if (
        context is None
        or context["provenance"] != "observed"
        or len(standards) != 1
        or standards[0] not in supported
        or context["language_standard"] not in {None, standards[0]}
    ):
        raise ContractError(
            "Repair requires an explicitly observed supported C++11-or-later context"
        )
    if any(arg.startswith(("-D", "-include", "-imacros")) for arg in context["argv"]):
        raise ContractError(
            "Unsupported alias context: explicit macro definitions require separate transformation support"
        )
    content = _source_content(snapshot, documents, inventory, file)
    start, end = _line_span(content, observation["line"])
    line = content[start:end]
    match = _ALIAS.fullmatch(line)
    if (
        match is None
        or len(line) > 4096
        or re.search(rb"(?:\A|[\r\n])[ \t\v\f]*(?:#|%:|\?\?=)", content)
        or b"\x00" in content
        or b"\\\n" in content
        or b"\\\r" in content
    ):
        raise ContractError(
            "Unsupported alias: require one ordinary builtin typedef statement per physical line"
        )
    name = match["name"].decode("ascii")
    if (
        observation["message"]
        != f"typedef '{name}' should use a C++11 type alias instead"
    ):
        raise ContractError(
            "Observed typedef name does not match literal retained source (possible macro expansion)"
        )
    statement = (
        b"typedef"
        + line[
            len(match["indent"])
            + len(b"typedef") : len(line)
            - len(match["tail"])
            - len(match["ending"] or b"")
        ]
    )
    offset = start + len(match["indent"])
    after = b"using " + match["name"] + b" = " + match["type"] + b";"
    ref = {
        "id": observation["id"],
        "context_id": observation["context_id"],
        "job_context_id": inventory["job_context_id"],
        "inventory_id": inventory["id"],
        "receipt_id": inventory["receipt_id"],
        "rule_version": observation["rule_version"],
        "registry_sha256": inventory["registry_sha256"],
        "report_artifact_id": inventory["report_artifact_id"],
        "report_sha256": next(
            item["sha256"]
            for item in snapshot.manifest["artifacts"]
            if item["id"] == inventory["report_artifact_id"]
        ),
    }
    return (
        _Candidate(file, offset, offset + len(statement), statement, after, ref),
        content,
    )


def _git_diff(file: str, before: bytes, after: bytes) -> str:
    """Emit an applicable unified diff using Git's LF line model and EOF marker."""

    def lines(content: bytes) -> list[str]:
        parts = content.decode().split("\n")
        return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])

    result = []
    for chunk in difflib.unified_diff(
        lines(before), lines(after), fromfile="a/" + file, tofile="b/" + file
    ):
        result.append(chunk)
        if not chunk.endswith("\n"):
            result.append("\n\\ No newline at end of file\n")
    return "".join(result)


def plan_repairs(
    snapshot: RunSnapshot, *, workspace: Path, observation_ids: list[str] | None = None
) -> dict[str, Any]:
    """Propose bounded textual edits using original native facts and current pins.

    Args:
        snapshot: Explicit immutable retained native result, never a loose report.
        workspace: Source root whose retained finite bytes must still match.
        observation_ids: Optional explicit observation selection, at most64 IDs.

    Returns:
        Validated deterministic dry-run plan; unsupported cases retain reasons.

    Raises:
        ContractError: Input scope, identity or selection is invalid or unsupported.
        InputChanged: Current retained source/generated materials changed.
    """
    snapshot = RunStore.open_existing(snapshot.path.parent.parent).open_run(
        snapshot.run_id,
        manifest_sha256=snapshot.manifest_sha256,
        max_snapshot_bytes=MAX_SNAPSHOT_BYTES,
    )
    if (
        len(snapshot.read_manifest_bytes()) > 1024**2
        or sum(row["size_bytes"] for row in snapshot.manifest["artifacts"])
        > MAX_SNAPSHOT_BYTES
    ):
        raise ContractError("Repair snapshot exceeds the finite32-MiB preview budget")
    if (
        snapshot.manifest.get("input_verification") != "verified"
        or not snapshot.manifest["source"]["inventory_complete"]
    ):
        raise ContractError("Repair requires verified, complete retained source scope")
    ensure_current_materials(snapshot, workspace)
    documents = read_documents(snapshot)
    validate_bundle(documents)
    inventories = {row["id"]: row for row in documents.get("analysis_inventory", [])}
    pairs = [
        (document, row)
        for document in documents.get("observations", [])
        for row in document["items"]
    ]
    known = {row["id"] for _, row in pairs}
    if observation_ids is not None and (
        not isinstance(observation_ids, list)
        or not observation_ids
        or any(
            not isinstance(value, str) or not value or len(value) > 128
            for value in observation_ids
        )
        or len(observation_ids) > MAX_OBSERVATIONS
        or len(set(observation_ids)) != len(observation_ids)
        or not set(observation_ids) <= known
    ):
        raise ContractError(
            "Repair observation selection is empty, duplicate, oversized or unknown"
        )
    selected = (
        [(document, row) for document, row in pairs if row["id"] in observation_ids]
        if observation_ids is not None
        else [
            (document, row)
            for document, row in pairs
            if row["rule_id"] == "CPP-MOD-009"
        ]
    )
    if len(selected) > MAX_OBSERVATIONS:
        raise ContractError(
            "Repair observation selection exceeds64; select a finite subset"
        )
    candidates: dict[tuple[str, int, int], tuple[_Candidate, list[dict[str, str]]]] = {}
    originals: dict[str, bytes] = {}
    rejected = []
    reports: dict[str, dict[str, Any]] = {}
    for document, row in sorted(selected, key=lambda pair: pair[1]["id"]):
        try:
            if row["rule_id"] != "CPP-MOD-009":
                raise ContractError("Unsupported repair rule")
            inventory = inventories.get(document.get("analysis_inventory_id"))
            if inventory is None:
                raise ContractError(
                    "Repair observation is not linked to native inventory"
                )
            _check_original_finding(
                snapshot, documents, inventory, row, workspace, reports
            )
            candidate, content = _candidate(snapshot, documents, inventory, row)
            key = (candidate.file, candidate.start, candidate.end)
            if key in candidates:
                prior, refs = candidates[key]
                if prior.before != candidate.before or prior.after != candidate.after:
                    raise ContractError(
                        "Selected native contexts disagree on proposed edit"
                    )
                refs.append(candidate.reference)
            else:
                candidates[key] = (candidate, [candidate.reference])
            originals[candidate.file] = content
        except (ContractError, UnicodeError) as error:
            rejected.append({"observation_id": row["id"], "reason": str(error)})
    edits = []
    diffs = []
    for file in sorted(originals):
        before = originals[file]
        chosen = sorted(
            (value for key, value in candidates.items() if key[0] == file),
            key=lambda value: value[0].start,
        )
        after = before
        for candidate, _ in reversed(chosen):
            after = after[: candidate.start] + candidate.after + after[candidate.end :]
        for candidate, refs in chosen:
            edits.append(
                {
                    "file": file,
                    "before_sha256": _sha(before),
                    "after_sha256": _sha(after),
                    "start_byte": candidate.start,
                    "end_byte": candidate.end,
                    "before": candidate.before.decode(),
                    "after": candidate.after.decode(),
                    "observations": refs,
                }
            )
        diffs.append(_git_diff(file, before, after))
    diff = "".join(diffs)
    plan = {
        "version": "1.0.0",
        "method": METHOD,
        "run": {"id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256},
        "source_digest": snapshot.manifest["source"]["digest"],
        "status": "planned" if edits else "no_changes",
        "edits": edits,
        "rejected": rejected,
        "diff": diff,
        "diff_sha256": _sha(diff.encode()),
        "limitations": list(_LIMITATIONS),
    }
    plan["id"] = "repair-" + digest_json(plan)
    validate_plan(plan)
    ensure_current_materials(snapshot, workspace)
    return plan


def _publish_plan(path: Path, plan: dict[str, Any]) -> None:
    """Publish complete bytes without replacing any preexisting caller path."""
    content = (
        json.dumps(plan, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode()
    if len(content) > 8 * 1024**2:
        raise ContractError(
            "Repair plan exceeds the finite eight-MiB publication bound"
        )
    with tempfile.TemporaryDirectory(
        prefix=".cppulse-repair-", dir=path.parent
    ) as private:
        temporary = Path(private) / "plan.json"
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)


def main(argv: list[str] | None = None) -> int:
    """Write an explicit dry-run plan; no source application or tool execution."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--observation-id", action="append")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if any(
            "\x00" in str(path) for path in (args.output, args.store, args.workspace)
        ):
            raise ContractError("Repair paths cannot contain NUL")
        if args.output.resolve().is_relative_to(args.store.resolve()):
            raise ContractError(
                "Repair output cannot be inside the selected store or its immutable runs"
            )
        snapshot = RunStore.open_existing(args.store).open_run(
            args.run_id,
            manifest_sha256=args.manifest_sha256,
            max_snapshot_bytes=MAX_SNAPSHOT_BYTES,
        )
        plan = plan_repairs(
            snapshot, workspace=args.workspace, observation_ids=args.observation_id
        )
        _publish_plan(args.output, plan)
        print(
            json.dumps(
                {
                    "plan": str(args.output),
                    "status": plan["status"],
                    "edits": len(plan["edits"]),
                    "rejected": len(plan["rejected"]),
                    "source_modified": False,
                }
            )
        )
        return 0 if not plan["rejected"] else 3
    except KeyboardInterrupt:
        print("cppulse repairs: cancelled", file=sys.stderr)
        return 130
    except (CppulseError, OSError, UnicodeError, RuntimeError, ValueError) as error:
        print(f"cppulse repairs: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
