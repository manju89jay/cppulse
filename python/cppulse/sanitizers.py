"""Normalize observed direct-GCC material chains, never compiler flags alone.

The bounded 1.0.0 producer supports GCC 14.2.0, binutils 2.44, CTest 3.31.6,
Linux x86-64 ELF64, unstripped non-LTO direct compile/link commands. Selected
source callsites are evidence of instrumentation, not all-access/path coverage.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import posixpath
import re
from typing import Any

from cppulse.adapters.ctest_log import parse_ctest_log
from cppulse.adapters.gcc_sanitizer import (
    SONAMES,
    UnsupportedSanitizerFormat,
    diagnostics,
    object_instrumentation,
    runtime_linkage,
)
from cppulse.adapters.test_results import parse_test_report
from cppulse.contracts import validate, validate_bundle
from cppulse.errors import ContractError, InputChanged, IntegrityError
from cppulse.identities import verify_inputs
from cppulse.run_store import RunSnapshot, RunStore

_LIMITS = [
    "Experimental selected-input sanitizer proof; not certification, absence-of-bugs, all-access instrumentation or dynamic source/path coverage.",
    "Only explicitly linked user object/library inputs are counted; host compiler headers, standard libraries and actually loaded runtime dependency closure are not proven instrumented.",
    "DT_NEEDED identifies requested runtime linkage, not the hash of an actually loaded runtime. Retained test output and file hashes are not producer authentication.",
    "Supported dialect: Linux x86-64 ELF64, GCC14.2.0, GNU binutils2.44, CTest3.31.6; direct argv, unstripped, no LTO/static sanitizer runtime or wrapper commands.",
]
CTEST_GUARD_BYTES = (
    b"# cppulse gcc-sanitizer 1.0.0: explicit inert CTest custom configuration guard.\n"
)
_FLAGS = {"asan": "address", "ubsan": "undefined", "tsan": "thread"}


@dataclass(frozen=True)
class ObjectSelection:
    """Explicit compile and independent nm/readelf receipt roles for one object."""

    compile_receipt_id: str
    nm_receipt_id: str
    elf_receipt_id: str


@dataclass(frozen=True)
class SanitizerSelection:
    """Role selectors only; proof and outcome values are derived from bytes."""

    id: str
    sanitizer: str
    requested_files: tuple[str, ...]
    compiler_version_receipt_id: str
    nm_version_receipt_id: str
    readelf_version_receipt_id: str
    objects: tuple[ObjectSelection, ...]
    link_receipt_id: str
    runtime_inspection_receipt_id: str
    test_evidence_id: str


def _typed(snapshot: RunSnapshot) -> dict[str, list[dict[str, Any]]]:
    documents: dict[str, list[dict[str, Any]]] = {}
    for entry in snapshot.manifest["artifacts"]:
        if entry.get("contract", {}).get("version") == "2.0.0":
            documents.setdefault(entry["contract"]["kind"], []).append(
                snapshot.read_json(entry["id"])
            )
    return documents


class _Observed:
    def __init__(self, snapshot: RunSnapshot) -> None:
        self.snapshot = snapshot
        self.documents = _typed(snapshot)
        self.facts = {
            row["receipt"]["id"]: row
            for row in self.documents.get("execution_facts", [])
        }
        self.artifacts = {row["id"]: row for row in snapshot.manifest["artifacts"]}

    def fact(self, identifier: str, *, passed: bool = True) -> dict[str, Any]:
        if identifier not in self.facts:
            raise ContractError(
                f"Explicit receipt has no typed execution facts: {identifier}"
            )
        fact = self.facts[identifier]
        if (
            fact["binding"]["status"] != "verified"
            or fact["material_status"] != "available"
            or fact["logs_truncated"]
            or (passed and fact["receipt"]["status"] != "passed")
            or fact["input_facts"] != fact["input_after_facts"]
        ):
            raise UnsupportedSanitizerFormat(
                f"Receipt/material/log/input proof is unavailable: {identifier}"
            )
        return fact

    def log(self, fact: dict[str, Any], stream: str = "stdout") -> tuple[str, str]:
        identifier = fact["binding"]["log_artifacts"].get(stream)
        if identifier is None:
            raise UnsupportedSanitizerFormat(
                "Retained untruncated inspection log is missing"
            )
        try:
            return identifier, self.snapshot.read_bytes(identifier).decode("utf-8")
        except UnicodeError as error:
            raise UnsupportedSanitizerFormat("Inspection log is not UTF-8") from error

    def same(self, first: str, second: str) -> bool:
        return all(
            self.artifacts[first][key] == self.artifacts[second][key]
            for key in ["sha256", "size_bytes"]
        )

    def output(self, fact: dict[str, Any]) -> tuple[str, str]:
        rows = fact["binding"]["output_artifacts"]
        if len(rows) != 1:
            raise UnsupportedSanitizerFormat(
                "Direct compile/link must have exactly one output"
            )
        return rows[0]["path"], rows[0]["artifact_id"]

    def role(self, fact: dict[str, Any], path: str, key: str) -> str:
        rows = [
            row["artifact_id"] for row in fact["binding"][key] if row["path"] == path
        ]
        if len(rows) != 1:
            raise UnsupportedSanitizerFormat(
                f"Direct command has no bound {key} for {path}"
            )
        return rows[0]


def _path(value: str, cwd: str) -> str:
    return posixpath.normpath(
        value if value.startswith("/") else posixpath.join(cwd, value)
    )


def _arguments(
    fact: dict[str, Any], *, compile: bool, sanitizer: str
) -> tuple[list[str], str]:
    argv = fact["receipt"]["argv"][1:]
    if argv.count("-o") != 1:
        raise UnsupportedSanitizerFormat(
            "Only one explicit -o direct GCC output is supported"
        )
    position = argv.index("-o")
    if position + 1 >= len(argv):
        raise UnsupportedSanitizerFormat("Missing GCC output argument")
    output = argv[position + 1]
    remaining = argv[:position] + argv[position + 2 :]
    allowed = {
        "-std=c++17",
        "-O0",
        "-g",
        "-fno-omit-frame-pointer",
        "-fno-pie",
        "-no-pie",
        "-pthread",
        "-fsanitize=" + _FLAGS[sanitizer],
    }
    if compile:
        if remaining.count("-c") != 1:
            raise UnsupportedSanitizerFormat(
                "Only direct single-source -c compilation is supported"
            )
        remaining.remove("-c")
    operands = []
    for value in remaining:
        if value in allowed or re.fullmatch(r"-D[A-Z][A-Z0-9_]*=[0-9]+", value):
            continue
        if value.startswith(("-", "@")):
            raise UnsupportedSanitizerFormat(
                f"Unsupported direct GCC argument: {value}"
            )
        operands.append(value)
    if compile and len(operands) != 1:
        raise UnsupportedSanitizerFormat("Direct compile must select one source")
    if not operands:
        raise UnsupportedSanitizerFormat("Direct GCC command has no selected operands")
    return operands, output


def _inspection(
    observed: _Observed,
    receipt: str,
    selected: str,
    args: list[str],
    version: dict[str, Any],
    workspace_root: str,
) -> tuple[str, str]:
    fact = observed.fact(receipt)
    if fact["receipt"]["cwd"] != workspace_root:
        raise UnsupportedSanitizerFormat(
            "File inspection cwd must be the observed workspace root"
        )
    if (
        fact["executable_fact"] is None
        or fact["executable_fact"]["sha256"] != version["executable_fact"]["sha256"]
        or fact["receipt"]["argv"][1:-1] != args
        or not fact["receipt"]["argv"][-1:]
    ):
        raise UnsupportedSanitizerFormat(
            "Inspection command/tool differs from explicit supported probe"
        )
    operand = _path(fact["receipt"]["argv"][-1], fact["receipt"]["cwd"])
    matches = [
        row
        for row in fact["binding"]["input_artifacts"]
        if observed.same(row["artifact_id"], selected)
    ]
    if len(matches) != 1:
        raise UnsupportedSanitizerFormat(
            "Inspection did not consume selected material bytes"
        )
    # Input paths are workspace relative; locate the workspace using the selected
    # plan step's declared cwd, without resolving live filesystem contents.
    plans = observed.documents.get("collection_plan", [])
    steps = [
        step
        for plan in plans
        for step in plan["recipe"]["steps"]
        if step["id"] == receipt
    ]
    if len(steps) != 1:
        raise UnsupportedSanitizerFormat(
            "Inspection has no unique selected recipe step"
        )
    root = fact["receipt"]["cwd"]
    for _ in [] if steps[0]["cwd"] == "." else steps[0]["cwd"].split("/"):
        root = posixpath.dirname(root)
    if operand != _path(matches[0]["path"], root):
        raise UnsupportedSanitizerFormat(
            "Inspection argv does not name its selected input"
        )
    return observed.log(fact)


def _test_definitions(
    observed: _Observed,
    test: dict[str, Any],
    inventory: dict[str, Any],
    step: dict[str, Any],
    binding: dict[str, Any],
) -> None:
    """Bind the finite direct CTest definition before both tool invocations."""
    if inventory["receipt"]["cwd"] != test["receipt"]["cwd"]:
        raise UnsupportedSanitizerFormat(
            "CTest definition directories differ between inventory and execution"
        )
    for name in ["CTestCustom.cmake", "CTestCustom.ctest"]:
        control = posixpath.join(step["cwd"], name).removeprefix("./")
        try:
            first_custom = observed.role(inventory, control, "input_artifacts")
            second_custom = observed.role(test, control, "input_artifacts")
            if not observed.same(first_custom, second_custom):
                raise UnsupportedSanitizerFormat(
                    "CTest custom configuration changed between inventory and execution"
                )
            custom = observed.snapshot.read_bytes(second_custom)
            if custom != CTEST_GUARD_BYTES:
                raise UnsupportedSanitizerFormat(
                    "Only exact inert CTest custom configuration guard bytes are supported"
                )
        except (UnsupportedSanitizerFormat, UnicodeError) as error:
            raise UnsupportedSanitizerFormat(
                "Finite CTest custom guard proof unavailable: " + str(error)
            ) from error
    definition = posixpath.join(step["cwd"], "CTestTestfile.cmake").removeprefix("./")
    first = observed.role(inventory, definition, "input_artifacts")
    second = observed.role(test, definition, "input_artifacts")
    if not observed.same(first, second):
        raise UnsupportedSanitizerFormat(
            "CTest definition changed between inventory and execution"
        )
    report_name = posixpath.basename(binding["report_path"])
    if (
        inventory["receipt"]["argv"][1:] != ["--show-only=json-v1"]
        or test["receipt"]["argv"][1:]
        != ["--output-on-failure", "--output-junit", report_name]
        or binding["report_path"]
        != posixpath.join(step["cwd"], report_name).removeprefix("./")
    ):
        raise UnsupportedSanitizerFormat(
            "CTest definition requires the supported direct current-directory commands"
        )
    try:
        content = observed.snapshot.read_bytes(second)
        if len(content) > 1024 * 1024:
            raise UnsupportedSanitizerFormat(
                "CTest definition exceeds finite supported byte limit"
            )
        lines = content.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise UnsupportedSanitizerFormat("CTest definition is not UTF-8") from error
    names: set[str] = set()
    properties: set[str] = set()
    for line in lines:
        if not line.strip() or line.lstrip() == "#" or line.lstrip().startswith("# "):
            continue
        added = re.fullmatch(
            r'add_test\(([A-Za-z0-9_.-]+)(?: +"[^"\\$\r\n]*")+\)', line
        )
        if added:
            if added[1] in names:
                raise UnsupportedSanitizerFormat("CTest definition repeats a test")
            names.add(added[1])
            continue
        selected = re.fullmatch(
            r"set_tests_properties\(([A-Za-z0-9_.-]+) PROPERTIES +(.+)\)", line
        )
        if selected:
            payload = selected[2]
            if (
                selected[1] not in names
                or selected[1] in properties
                or not re.fullmatch(r'(?:[A-Z_]+ +"[^"\\$\r\n]*" *)+', payload)
            ):
                raise UnsupportedSanitizerFormat(
                    "Unsupported literal CTest definition properties"
                )
            keys = re.findall(r'([A-Z_]+) +"[^"\\$\r\n]*"', payload)
            if len(keys) != len(set(keys)) or not set(keys) <= {
                "WORKING_DIRECTORY",
                "_BACKTRACE_TRIPLES",
                "SKIP_RETURN_CODE",
            }:
                raise UnsupportedSanitizerFormat(
                    "Unsupported effective CTest definition properties"
                )
            properties.add(selected[1])
            continue
        raise UnsupportedSanitizerFormat(
            "Indirect or nonliteral CTest definition requires another producer"
        )


def normalize_gcc_sanitizer(
    snapshot: RunSnapshot, selection: SanitizerSelection
) -> dict[str, Any]:
    """Derive sanitizer facts from immutable typed execution and retained bytes.

    Invalid selector IDs/duplicate IDs are caller errors. Supported but incomplete
    or operationally unavailable chains return explicit unavailable facts. This
    function performs no subprocesses, source discovery or network operations.
    """
    snapshot.verify()
    if selection.sanitizer not in SONAMES:
        raise ContractError("Unsupported selected sanitizer")
    observed = _Observed(snapshot)
    if selection.id in {
        row["id"] for row in observed.documents.get("sanitizer_facts", [])
    }:
        raise ContractError("Sanitizer fact ID already exists in selected snapshot")
    if not selection.objects or not selection.requested_files:
        raise ContractError("Select at least one compile role and source file")
    version = observed.facts.get(selection.compiler_version_receipt_id)
    if version is None:
        raise ContractError("Selected compiler version receipt is absent")
    context = version["receipt"]["context_id"]
    proof_ids = list(
        dict.fromkeys(
            [
                selection.compiler_version_receipt_id,
                selection.nm_version_receipt_id,
                selection.readelf_version_receipt_id,
                *[
                    role
                    for row in selection.objects
                    for role in [
                        row.compile_receipt_id,
                        row.nm_receipt_id,
                        row.elf_receipt_id,
                    ]
                ],
                selection.link_receipt_id,
                selection.runtime_inspection_receipt_id,
            ]
        )
    )
    for identifier in proof_ids:
        fact = observed.facts.get(identifier)
        if fact is None or fact["receipt"]["context_id"] != context:
            raise ContractError(
                "Selected sanitizer proof IDs must resolve in one job context"
            )
    source = {row["path"]: row for row in snapshot.manifest["source"]["files"]}
    if not set(selection.requested_files) <= source.keys():
        raise ContractError(
            "Sanitizer selected files are outside finite source inventory"
        )
    document: dict[str, Any] = {
        "version": "2.0.0",
        "id": selection.id,
        "source_digest": snapshot.manifest["source"]["digest"],
        "context_id": context,
        "requested_files": list(selection.requested_files),
        "origin": "execution",
        "producer": {"name": "gcc", "version": "unavailable"},
        "adapter": {"name": "gcc-sanitizer", "version": "1.0.0"},
        "sanitizer": selection.sanitizer,
        "compiler_version_receipt_id": selection.compiler_version_receipt_id,
        "compile_receipt_ids": [row.compile_receipt_id for row in selection.objects],
        "link_receipt_id": selection.link_receipt_id,
        "inspection_receipt_ids": [
            role
            for row in selection.objects
            for role in [row.nm_receipt_id, row.elf_receipt_id]
        ]
        + [selection.runtime_inspection_receipt_id],
        "proof_receipt_ids": proof_ids,
        "binary_artifact_id": None,
        "object_proofs": [],
        "linked_components": [],
        "runtime_proof": None,
        "test_evidence_id": None,
        "exercise_proofs": [],
        "diagnostic_artifact_ids": [],
        "diagnostics": [],
        "outcome": "unsupported",
        "usability": "unsupported",
        "limitations": list(_LIMITS),
    }
    try:
        if snapshot.manifest.get("input_verification") != "verified":
            raise UnsupportedSanitizerFormat(
                "Finite selected sources were not verified"
            )
        version = observed.fact(selection.compiler_version_receipt_id)
        _, version_text = observed.log(version)
        if (
            version["receipt"]["argv"][1:] != ["-dumpfullversion", "-dumpversion"]
            or version_text.strip() != "14.2.0"
            or not version["executable_fact"]
        ):
            raise UnsupportedSanitizerFormat(
                "Only explicitly observed direct GCC14.2.0 is supported"
            )
        document["producer"] = {
            "name": "gcc",
            "version": version_text.strip(),
            "sha256": version["executable_fact"]["sha256"],
        }
        version_steps = [
            step
            for plan in observed.documents.get("collection_plan", [])
            for step in plan["recipe"]["steps"]
            if step["id"] == selection.compiler_version_receipt_id
        ]
        if len(version_steps) != 1:
            raise UnsupportedSanitizerFormat(
                "Compiler version probe has no unique recipe directory"
            )
        workspace_root = version["receipt"]["cwd"]
        relative_cwd = version_steps[0]["cwd"]
        parts = [] if relative_cwd == "." else relative_cwd.split("/")
        if parts and workspace_root.split("/")[-len(parts) :] != parts:
            raise UnsupportedSanitizerFormat(
                "Compiler version probe directory is inconsistent"
            )
        for _ in parts:
            workspace_root = posixpath.dirname(workspace_root)
        tools = []
        for identifier, name in [
            (selection.nm_version_receipt_id, "nm"),
            (selection.readelf_version_receipt_id, "readelf"),
        ]:
            tool = observed.fact(identifier)
            _, text = observed.log(tool)
            if (
                tool["receipt"]["argv"][1:] != ["--version"]
                or not re.match(
                    r"GNU " + name + r" \(GNU Binutils(?: for Debian)?\) 2\.44\n", text
                )
                or not tool["executable_fact"]
            ):
                raise UnsupportedSanitizerFormat(
                    "Only explicitly observed GNU binutils2.44 nm/readelf is supported"
                )
            tools.append(tool)
        link = observed.fact(selection.link_receipt_id)
        if link["receipt"]["cwd"] != workspace_root:
            raise UnsupportedSanitizerFormat(
                "Direct link cwd must be the observed workspace root"
            )
        if (link["executable_fact"] or {}).get("sha256") != document["producer"][
            "sha256"
        ]:
            raise UnsupportedSanitizerFormat(
                "Link compiler differs from observed GCC identity"
            )
        operands, output = _arguments(
            link, compile=False, sanitizer=selection.sanitizer
        )
        binary_path, binary = observed.output(link)
        if output != binary_path or set(operands) != {
            row["path"] for row in link["binding"]["input_artifacts"]
        }:
            raise UnsupportedSanitizerFormat(
                "Link argv inputs/output differ from selected material bindings"
            )
        document["binary_artifact_id"] = binary
        gap = False
        for row in selection.objects:
            compile = observed.fact(row.compile_receipt_id)
            if compile["receipt"]["cwd"] != workspace_root:
                raise UnsupportedSanitizerFormat(
                    "Direct compile cwd must be the observed workspace root"
                )
            if (compile["executable_fact"] or {}).get("sha256") != document["producer"][
                "sha256"
            ]:
                raise UnsupportedSanitizerFormat(
                    "Compile compiler differs from observed GCC identity"
                )
            operands, output = _arguments(
                compile, compile=True, sanitizer=selection.sanitizer
            )
            object_path, object_id = observed.output(compile)
            source_path = operands[0]
            if output != object_path or source_path not in source:
                raise UnsupportedSanitizerFormat(
                    "Compile source/output are outside selected source/material"
                )
            source_id = observed.role(compile, source_path, "input_artifacts")
            if any(
                observed.artifacts[source_id][key] != source[source_path][key]
                for key in ["sha256", "size_bytes"]
            ):
                raise UnsupportedSanitizerFormat(
                    "Compile source bytes differ from selected source"
                )
            if not any(
                observed.same(item["artifact_id"], object_id)
                for item in link["binding"]["input_artifacts"]
            ):
                raise UnsupportedSanitizerFormat(
                    "Selected compile object is not actually linked"
                )
            nm_id, nm = _inspection(
                observed, row.nm_receipt_id, object_id, ["-u"], tools[0], workspace_root
            )
            elf_id, elf = _inspection(
                observed,
                row.elf_receipt_id,
                object_id,
                ["-h", "-S", "-r", "-W"],
                tools[1],
                workspace_root,
            )
            try:
                proof = object_instrumentation(nm, elf, selection.sanitizer)
            except UnsupportedSanitizerFormat as error:
                gap = True
                document["limitations"].append(f"Unverified {source_path}: {error}")
            else:
                document["object_proofs"].append(
                    {
                        "artifact_id": object_id,
                        "compile_receipt_id": row.compile_receipt_id,
                        "source_files": [source_path],
                        "sanitizer": selection.sanitizer,
                        "method": "elf-relocations-v1",
                        "observed_symbols": list(proof.symbols),
                        "inspection_artifact_ids": [nm_id, elf_id],
                        "elf": proof.elf,
                    }
                )
        for index, row in enumerate(link["binding"]["input_artifacts"]):
            status = (
                "observed"
                if any(
                    observed.same(row["artifact_id"], proof["artifact_id"])
                    for proof in document["object_proofs"]
                )
                else "unverified"
            )
            gap |= status != "observed"
            document["linked_components"].append(
                {
                    "subject_id": "linked-input-" + str(index),
                    "artifact_id": row["artifact_id"],
                    "instrumentation": status,
                }
            )
        runtime_id, runtime_text = _inspection(
            observed,
            selection.runtime_inspection_receipt_id,
            binary,
            ["-h", "-S", "-d", "-s", "-W"],
            tools[1],
            workspace_root,
        )
        runtime = runtime_linkage(runtime_text, selection.sanitizer)
        document["runtime_proof"] = {
            "inspection_artifact_id": runtime_id,
            "required_soname": SONAMES[selection.sanitizer],
            "observed_needed": list(runtime.needed),
            "elf": runtime.elf,
        }
        records = [
            row
            for evidence in observed.documents.get("evidence", [])
            for row in evidence["records"]
            if row["id"] == selection.test_evidence_id
        ]
        if len(records) != 1:
            raise ContractError("Selected test evidence ID is absent or ambiguous")
        evidence = records[0]
        if (
            evidence["origin"] != "execution"
            or evidence["usability"] != "usable"
            or evidence["context_id"] != context
        ):
            raise UnsupportedSanitizerFormat(
                "Actual test evidence is unavailable or belongs to another job"
            )
        test = observed.fact(evidence["receipt_id"], passed=False)
        document["proof_receipt_ids"].append(test["receipt"]["id"])
        plans = [
            binding
            for plan in observed.documents.get("collection_plan", [])
            for binding in plan["bindings"]
            if binding["id"] == selection.test_evidence_id
            and binding["kind"] == "tests"
            and binding["step_id"] == test["receipt"]["id"]
        ]
        if len(plans) != 1:
            raise UnsupportedSanitizerFormat("No unique selected CTest binding")
        binding = plans[0]
        test_steps = [
            step
            for plan in observed.documents["collection_plan"]
            for step in plan["recipe"]["steps"]
            if step["id"] == test["receipt"]["id"]
        ]
        if len(test_steps) != 1:
            raise UnsupportedSanitizerFormat("No unique selected CTest execution step")
        expected_environment = {
            "ASAN_OPTIONS": "detect_leaks=0:halt_on_error=1:symbolize=0:suppressions=:log_path=stderr",
            "UBSAN_OPTIONS": "halt_on_error=0:print_stacktrace=0:symbolize=0:suppressions=:log_path=stderr",
            "TSAN_OPTIONS": "halt_on_error=1:report_bugs=1:exitcode=66:symbolize=0:suppressions=:log_path=stderr",
            "LD_PRELOAD": "",
            "LD_AUDIT": "",
            "LC_ALL": "C",
        }
        selected_environment = test_steps[0].get("environment", {})
        loader_path = selected_environment.get("LD_LIBRARY_PATH")
        if (
            any(
                selected_environment.get(key) != value
                for key, value in expected_environment.items()
            )
            or not isinstance(loader_path, str)
            or (
                loader_path != ""
                and any(
                    not part.startswith("/") or posixpath.normpath(part) != part
                    for part in loader_path.split(":")
                )
            )
        ):
            raise UnsupportedSanitizerFormat(
                "Unsupported or inherited sanitizer runtime environment"
            )
        inventory_fact = observed.fact(binding["inventory_step_id"])
        try:
            _test_definitions(observed, test, inventory_fact, test_steps[0], binding)
        except UnsupportedSanitizerFormat as error:
            raise UnsupportedSanitizerFormat(
                "Finite CTest definition proof unavailable: " + str(error)
            ) from error
        _, inventory_text = observed.log(inventory_fact)
        try:
            inventory = json.loads(inventory_text)
            if any(
                prop["name"] in {"ENVIRONMENT", "ENVIRONMENT_MODIFICATION"}
                for item in inventory["tests"]
                for prop in item.get("properties", [])
            ):
                raise UnsupportedSanitizerFormat(
                    "CTest per-case runtime environment overrides are unsupported"
                )
        except (ValueError, KeyError, TypeError) as error:
            raise UnsupportedSanitizerFormat(
                "CTest inventory runtime properties are unavailable"
            ) from error
        for name in ["inventory_step_id", "producer_version_step_id"]:
            observed.fact(binding[name])
            document["proof_receipt_ids"].append(binding[name])
        inputs = [
            row
            for row in test["binding"]["input_artifacts"]
            if row["path"] in binding["exercised_inputs"]
            and observed.same(row["artifact_id"], binary)
        ]
        if len(inputs) != 1:
            raise UnsupportedSanitizerFormat(
                "CTest selected input differs from actual linked binary"
            )
        outputs = test["binding"]["output_artifacts"]

        def output_id(path: str) -> str:
            ids = [row["artifact_id"] for row in outputs if row["path"] == path]
            if len(ids) != 1:
                raise UnsupportedSanitizerFormat(
                    "Actual CTest report/log output is unavailable"
                )
            return ids[0]

        junit = output_id(binding["report_path"])
        log_id = output_id(binding["execution_log_path"])
        junit_path = snapshot.path / observed.artifacts[junit]["path"]
        log_path = snapshot.path / observed.artifacts[log_id]["path"]
        producer = {"name": "ctest", "version": "3.31.6"}
        report = parse_test_report(junit_path, producer=producer)
        trace = parse_ctest_log(log_path, producer=producer)
        # Match exact parsed bytes to the already verified immutable descriptors.
        for parsed, aid in [(report, junit), (trace, log_id)]:
            if (
                parsed.usability != "usable"
                or parsed.report_sha256 != observed.artifacts[aid]["sha256"]
                or parsed.size_bytes != observed.artifacts[aid]["size_bytes"]
            ):
                raise UnsupportedSanitizerFormat(
                    "CTest parsed bytes/dialect differ from retained proof"
                )
        cases = {row.name: row for row in report.cases if row.status != "skipped"}
        if not cases or len(cases) != len(
            [row for row in report.cases if row.status != "skipped"]
        ):
            raise UnsupportedSanitizerFormat(
                "Zero/all-skipped or ambiguous repeated test cases cannot prove sanitizer execution"
            )
        log_text = snapshot.read_bytes(log_id).decode("utf-8").replace("\r\n", "\n")
        blocks = re.findall(r"(?ms)^Output:\n-{58}\n(.*?)^<end of output>$", log_text)
        if len(blocks) != len(trace.records):
            raise UnsupportedSanitizerFormat(
                "Captured CTest output boundaries are ambiguous"
            )
        # CTest cwd can be nested: derive workspace from the selected recipe cwd.
        step = next(
            step
            for plan in observed.documents["collection_plan"]
            for step in plan["recipe"]["steps"]
            if step["id"] == test["receipt"]["id"]
        )
        root = test["receipt"]["cwd"]
        for _ in [] if step["cwd"] == "." else step["cwd"].split("/"):
            root = posixpath.dirname(root)
        actual_binary = _path(inputs[0]["path"], root)
        runtime_errors = []
        case_ids = []
        for trace_record, output_text in zip(trace.records, blocks):
            case = cases.get(trace_record.name)
            if case is None:
                continue
            if (
                not trace_record.actual_argv
                or _path(trace_record.actual_argv[0], trace_record.working_directory)
                != actual_binary
            ):
                raise UnsupportedSanitizerFormat(
                    "Actual CTest invocation substituted another executable"
                )
            case_ids.append(case.identity)
            parsed = diagnostics(output_text, selection.sanitizer)
            if parsed.runtime_error:
                runtime_errors.append(parsed.runtime_error)
            for diagnostic in parsed.records:
                file = diagnostic.file
                if file is not None:
                    absolute = _path(
                        file,
                        (
                            root
                            if not file.startswith("/")
                            else trace_record.working_directory
                        ),
                    )
                    file = next(
                        (path for path in source if _path(path, root) == absolute), None
                    )
                document["diagnostics"].append(
                    {
                        "id": "diagnostic-" + str(len(document["diagnostics"])),
                        "kind": diagnostic.kind,
                        "message": diagnostic.message,
                        "file": file,
                        "line": diagnostic.line if file else None,
                        "artifact_id": log_id,
                        "test_case_id": case.identity,
                    }
                )
        if not case_ids or set(case_ids) != {case.identity for case in cases.values()}:
            raise UnsupportedSanitizerFormat(
                "Actual selected non-skipped CTest cases lack binary invocation proof"
            )
        document["test_evidence_id"] = selection.test_evidence_id
        document["diagnostic_artifact_ids"] = [log_id]
        document["exercise_proofs"] = [
            {
                "artifact_id": inputs[0]["artifact_id"],
                "test_receipt_id": test["receipt"]["id"],
                "test_case_ids": case_ids,
            }
        ]
        if runtime_errors:
            raise UnsupportedSanitizerFormat("; ".join(runtime_errors))
        if not document["object_proofs"]:
            raise UnsupportedSanitizerFormat(
                "No bound instrumented object exists for the exercised binary"
            )
        gap |= not set(selection.requested_files) <= {
            path
            for proof in document["object_proofs"]
            for path in proof["source_files"]
        }
        if document["diagnostics"]:
            document.update(outcome="failed", usability="usable")
            if gap:
                document["limitations"].append(
                    "A credible selected-binary diagnostic was observed, but additional selected sources/components lack instrumentation proof."
                )
        elif gap:
            raise UnsupportedSanitizerFormat(
                "Selected source/component instrumentation inventory is incomplete"
            )
        elif test["receipt"]["status"] != "passed" or report.status != "passed":
            raise UnsupportedSanitizerFormat(
                "Test failed without a recognized qualified sanitizer diagnostic"
            )
        else:
            document.update(outcome="passed", usability="usable")
    except UnsupportedSanitizerFormat as error:
        document["limitations"].append(str(error))
    document["proof_receipt_ids"] = list(dict.fromkeys(document["proof_receipt_ids"]))
    validate("sanitizer_facts", document)
    validate_bundle(
        {
            "run_manifest": snapshot.manifest,
            **observed.documents,
            "sanitizer_facts": [
                *observed.documents.get("sanitizer_facts", []),
                document,
            ],
        }
    )
    return document


def persist_gcc_sanitizer(
    snapshot: RunSnapshot,
    *,
    workspace: Path,
    store: RunStore | Path,
    selection: SanitizerSelection,
) -> RunSnapshot:
    """Publish derived facts while retaining original artifact/source/config bytes."""
    document = normalize_gcc_sanitizer(snapshot, selection)
    storage_id = "sanitizer-" + hashlib.sha256(selection.id.encode("utf-8")).hexdigest()
    cap = min(
        int(plan["limits"]["max_metadata_bytes"])
        for plan in _typed(snapshot)["collection_plan"]
    )

    def checked_metadata(value: dict[str, Any]) -> None:
        if (
            len(
                (
                    json.dumps(
                        value,
                        sort_keys=True,
                        indent=2,
                        ensure_ascii=False,
                        allow_nan=False,
                    )
                    + "\n"
                ).encode("utf-8")
            )
            > cap
        ):
            raise IntegrityError("Derived sanitizer JSON exceeds max_metadata_bytes")

    checked_metadata(document)

    def source_check() -> None:
        changes = verify_inputs(workspace, snapshot.manifest["source"])
        if changes:
            raise InputChanged(
                "Selected sanitizer sources changed: " + "; ".join(changes)
            )

    source_check()
    runtime = store if isinstance(store, RunStore) else RunStore(store)
    with runtime.begin() as stage:
        for artifact in snapshot.manifest["artifacts"]:
            if (
                stage.copy_artifact(
                    artifact["id"],
                    snapshot.path / artifact["path"],
                    artifact["path"],
                    artifact["media_type"],
                    contract=artifact.get("contract"),
                )
                != artifact
            ):
                raise IntegrityError("Sanitizer derivation changed parent artifacts")
        stage.write_json(
            "sanitizers/" + storage_id + ".json",
            document,
            contract="sanitizer_facts",
            artifact_id=storage_id + "-document",
        )
        parent = stage.copy_artifact(
            storage_id + "-provenance",
            snapshot.path / "run_manifest.json",
            "sanitizers/" + storage_id + "-parent.json",
            "application/json",
        )
        if parent["sha256"] != snapshot.manifest_sha256:
            raise IntegrityError("Parent sanitizer manifest changed during derivation")
        manifest = deepcopy(snapshot.manifest)
        manifest.update(run_id=stage.run_id, artifacts=stage.artifacts)
        manifest["versions"]["gcc-sanitizer-normalizer"] = "1.0.0"
        manifest["limitations"] = list(
            dict.fromkeys([*manifest["limitations"], *_LIMITS])
        )
        manifest["stages"].append(
            {
                "id": storage_id + "-normalize",
                "status": "passed",
                "depends_on": [],
                "reason": "Retained sanitizer facts normalized; outcome="
                + document["outcome"]
                + ", usability="
                + document["usability"],
            }
        )
        checked_metadata(manifest)
        return stage.publish(manifest, source_check=source_check)
