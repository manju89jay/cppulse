"""Pure semantic guards for typed verification facts, without tool execution.

These contracts describe observed or imported facts. File-byte checks and
supported-format parsing belong to the run store and versioned producers.
"""

from __future__ import annotations

import hashlib
import re
from fractions import Fraction
from typing import Any


def semantic(kind: str, document: dict[str, Any]) -> None:
    """Validate cross-field semantics after strict structural validation."""
    from .validation import _fail, _safe_path, _unique

    if kind in {"consumer_usage", "consumer_comparison"}:
        from .consumers import semantic

        semantic(kind, document)
        return
    if kind == "sanitizer_facts":
        for path in document["requested_files"]:
            _safe_path(path, "/requested_files")
        _unique(document["object_proofs"], "artifact_id", "/object_proofs")
        _unique(document["linked_components"], "subject_id", "/linked_components")
        _unique(document["diagnostics"], "id", "/diagnostics")
        markers = {
            "asan": r"__asan_report_(?:load|store)(?:[0-9]+|_n)(?:_noabort)?",
            "ubsan": r"__ubsan_handle_[A-Za-z0-9_]+",
            "tsan": r"__tsan_(?:read|write)[0-9]+",
        }
        for object in document["object_proofs"]:
            if object["sanitizer"] != document["sanitizer"] or any(
                not re.fullmatch(markers[document["sanitizer"]], symbol)
                for symbol in object["observed_symbols"]
            ):
                _fail(
                    "Object proof lacks actual named sanitizer data/check callsites",
                    "/object_proofs/observed_symbols",
                )
            if object["compile_receipt_id"] not in document["compile_receipt_ids"]:
                _fail(
                    "Object compiler is absent from compile receipt inventory",
                    "/object_proofs/compile_receipt_id",
                )
            for path in object["source_files"]:
                _safe_path(path, "/object_proofs/source_files")
        runtime = document["runtime_proof"]
        if runtime is not None and (
            runtime["required_soname"]
            != {
                "asan": "libasan.so.8",
                "ubsan": "libubsan.so.1",
                "tsan": "libtsan.so.2",
            }[document["sanitizer"]]
            or runtime["required_soname"] not in runtime["observed_needed"]
        ):
            _fail(
                "Runtime linkage does not contain the named sanitizer runtime",
                "/runtime_proof",
            )
        for diagnostic in document["diagnostics"]:
            if diagnostic["artifact_id"] not in document["diagnostic_artifact_ids"]:
                _fail(
                    "Diagnostic raw artifact is outside diagnostic inventory",
                    "/diagnostics/artifact_id",
                )
            if diagnostic["file"] is not None:
                _safe_path(diagnostic["file"], "/diagnostics/file")
            elif diagnostic["line"] is not None:
                _fail(
                    "Diagnostic line cannot invent an unknown source file",
                    "/diagnostics/line",
                )
        if document["outcome"] == "failed" and not document["diagnostics"]:
            _fail(
                "Sanitizer failure requires actual diagnostic records", "/diagnostics"
            )
        if document["outcome"] == "passed" and (
            document["diagnostics"] or document["usability"] != "usable"
        ):
            _fail(
                "Clean sanitizer result contradicts diagnostics/unavailable proof",
                "/outcome",
            )
        if document["origin"] == "import":
            if (
                document["outcome"] == "passed"
                or any(
                    document[key]
                    for key in [
                        "compile_receipt_ids",
                        "inspection_receipt_ids",
                        "proof_receipt_ids",
                        "object_proofs",
                        "exercise_proofs",
                    ]
                )
                or any(
                    document[key] is not None
                    for key in [
                        "compiler_version_receipt_id",
                        "link_receipt_id",
                        "binary_artifact_id",
                        "runtime_proof",
                        "test_evidence_id",
                    ]
                )
            ):
                _fail(
                    "Imported sanitizer reports cannot assert observed clean execution",
                    "/origin",
                )
            return
        if document["usability"] == "usable":
            if document["outcome"] not in {"passed", "failed"}:
                _fail(
                    "Operationally unavailable sanitizer outcome is not usable verification",
                    "/outcome",
                )
            if any(
                document[key] is None
                for key in [
                    "compiler_version_receipt_id",
                    "link_receipt_id",
                    "binary_artifact_id",
                    "runtime_proof",
                    "test_evidence_id",
                ]
            ) or any(
                not document[key]
                for key in [
                    "compile_receipt_ids",
                    "inspection_receipt_ids",
                    "proof_receipt_ids",
                    "object_proofs",
                    "exercise_proofs",
                    "diagnostic_artifact_ids",
                ]
            ):
                _fail(
                    "Observed sanitizer outcome lacks base compile/link/runtime/execution proof",
                    "/outcome",
                )
            if (
                document["producer"].get("name") != "gcc"
                or document["producer"].get("version") != "14.2.0"
                or document["producer"].get("sha256") is None
            ):
                _fail(
                    "Usable sanitizer proof requires observed GCC14.2 compiler hash",
                    "/producer",
                )
            if document["outcome"] == "passed" and (
                not document["linked_components"]
                or any(
                    row["instrumentation"] != "observed"
                    for row in document["linked_components"]
                )
                or not set(document["requested_files"])
                <= {
                    path
                    for row in document["object_proofs"]
                    for path in row["source_files"]
                }
            ):
                _fail(
                    "Clean sanitizer outcome lacks complete selected component/source instrumentation",
                    "/outcome",
                )
        return
    if kind == "distribution_subject":
        _unique(document["source_files"], "path", "/source_files")
        _unique(document["distribution_files"], "path", "/distribution_files")
        _unique(document["distribution_files"], "artifact_id", "/distribution_files")
        for file in document["source_files"] + document["distribution_files"]:
            _safe_path(file["path"], "/files/path")
        if (document["source_relation"] == "selected_sources") != bool(
            document["source_files"]
        ):
            _fail(
                "Subject source relation disagrees with selected source inventory",
                "/source_relation",
            )
        if (
            document["source_relation"] == "distribution_only"
            and not document["limitations"]
        ):
            _fail(
                "Distribution-only subject must preserve its source limitation",
                "/limitations",
            )
        return
    if kind == "consumer_matrix":
        _unique(document["cases"], "id", "/cases")
        for case in document["cases"]:
            for path in case["self_containment_headers"]:
                _safe_path(path, "/cases/self_containment_headers")
            _unique(
                case["configuration"]["dependencies"],
                "id",
                "/cases/configuration/dependencies",
            )
            for dependency in case["configuration"]["dependencies"]:
                if (dependency["availability"] == "available") != (
                    dependency["sha256"] is not None
                ):
                    _fail(
                        "Dependency hash/availability disagree",
                        "/cases/configuration/dependencies",
                    )
        return
    if kind == "transfer_bundle":
        from .validation import _collection_outputs, _collection_path

        _unique(document["roots"], "id", "/roots")
        _unique(document["files"], "path", "/files")
        _collection_outputs(
            [(row["path"], row["path"]) for row in document["files"]], "/files"
        )
        limits = document["limits"]
        if (
            len(document["files"]) > limits["max_files"]
            or sum(row["size_bytes"] for row in document["files"])
            > limits["max_total_bytes"]
        ):
            _fail(
                "Transfer payload exceeds declared file count/total byte cap", "/limits"
            )
        inventory = {row["path"]: row for row in document["files"]}
        prefixes = []
        for root in document["roots"]:
            prefix = "roots/" + root["id"] + "/runs/" + root["run_id"] + "/"
            prefixes.append(prefix)
            expected = prefix + "run_manifest.json"
            if root["manifest_path"] != expected or expected not in inventory:
                _fail(
                    "Transfer root manifest is absent or outside its exact namespace",
                    "/roots/manifest_path",
                )
            file = inventory[expected]
            if (
                root["manifest_sha256"] != file["sha256"]
                or file["size_bytes"] > limits["max_metadata_bytes"]
            ):
                _fail(
                    "Transfer manifest digest/metadata cap disagrees with inventory",
                    "/roots",
                )
        if len({prefix.casefold() for prefix in prefixes}) != len(prefixes):
            _fail("Transfer root namespaces collide", "/roots")
        for row in document["files"]:
            _collection_path(row["path"], "/files/path")
            if not any(row["path"].startswith(prefix) for prefix in prefixes):
                _fail("Transfer file lies outside every declared root", "/files/path")
            if any(
                part.casefold()
                in {
                    "latest.json",
                    "latest_attempt.json",
                    "heads.json",
                    "store-format.json",
                    ".migration-v3",
                    ".publication.lock",
                    ".coordination.lock",
                    ".recovery",
                    "transfer_bundle.json",
                }
                for part in row["path"].split("/")
            ):
                _fail(
                    "Publication pointers/transfer descriptor cannot be payload",
                    "/files/path",
                )
            if row["size_bytes"] > limits["max_file_bytes"]:
                _fail("Transfer payload file exceeds declared cap", "/files/size_bytes")
        return
    if kind == "external_analysis_facts":
        _unique(document["observations"], "id", "/observations")
        for path in document["scope_files"]:
            _safe_path(path, "/scope_files")
        profiles = {
            "gcc-json": ("gcc", "GNU-G++", "14.2.0"),
            "clang-tidy-text": ("clang-tidy", "clang-tidy", "19.1.7"),
            "cppcheck-xml": ("cppcheck", "Cppcheck", "2.17.1"),
        }
        namespace, producer_name, producer_version = profiles[
            document.get("adapter", {"name": "gcc-json"})["name"]
        ]
        if document.get("producer_namespace", "gcc") != namespace:
            _fail(
                "External adapter namespace disagrees with producer profile",
                "/producer_namespace",
            )
        for row in document["observations"]:
            _safe_path(row["file"], "/observations/file")
            original = row["original_rule_id"]
            expected = namespace + ":" + original
            if (
                not re.fullmatch(r"[A-Za-z0-9_.:-]+", original)
                or len(expected) > 128
                or re.fullmatch(r"option-[0-9a-f]{64}", original)
            ):
                expected = (
                    namespace
                    + ":option-"
                    + hashlib.sha256(original.encode()).hexdigest()
                )
            if (
                row["namespaced_rule_id"] != expected
                or row["rule_version"] != document["producer"]["version"]
            ):
                _fail(
                    "External rule namespace/version disagrees with retained producer",
                    "/observations",
                )
            if row["file"] not in document["scope_files"]:
                _fail(
                    "External diagnostic is outside declared report scope",
                    "/observations/file",
                )
        if document["usability"] == "usable" and any(
            document["producer"][key] != value
            for key, value in {
                "name": producer_name,
                "version": producer_version,
            }.items()
        ):
            _fail(
                "External adapter supports only its declared producer/version profile",
                "/producer",
            )
        if document["origin"] == "import":
            if (
                document["receipt_id"] is not None
                or document["producer_version_receipt_id"] is not None
                or document["proof_receipt_ids"]
            ):
                _fail("Imported diagnostics cannot assert local execution", "/origin")
        return
    if kind != "coverage_facts":
        return
    _unique(document["files"], "file", "/files")
    if document["usability"] == "usable" and not document["files"]:
        _fail("Usable coverage requires actual file measurements", "/files")
    for file in document["files"]:
        _safe_path(file["file"], "/files/file")
        _unique(file["measurements"], "kind", "/files/measurements")
        for measurement in file["measurements"]:
            methods = {
                ("lcov", "line"): "lcov-da-v1",
                ("lcov", "branch"): "lcov-brda-v1",
                ("lcov", "function"): "lcov-fnda-v1",
                ("cobertura", "line"): "cobertura-lines-v1",
                ("cobertura", "branch"): "cobertura-condition-counts-v1",
            }
            if measurement["method"] != methods.get(
                (document["adapter"]["name"], measurement["kind"])
            ):
                _fail(
                    "Coverage measurement kind/method is unsupported for this adapter",
                    "/files/measurements/method",
                )
            _unique(measurement["units"], "id", "/files/measurements/units")
            if measurement["method"] != "cobertura-condition-counts-v1" and any(
                unit["total"] != 1 or unit["covered"] not in {0, 1}
                for unit in measurement["units"]
            ):
                _fail(
                    "Individual measurement points require binary covered/total-one counts",
                    "/files/measurements/units",
                )
            if any(
                Fraction(str(unit["covered"])) > Fraction(str(unit["total"]))
                for unit in measurement["units"]
            ):
                _fail(
                    "Covered unit count exceeds its denominator",
                    "/files/measurements/units",
                )
            if any(
                sum(Fraction(str(unit[key])) for unit in measurement["units"])
                != Fraction(str(measurement[key]))
                for key in ["covered", "total"]
            ):
                _fail(
                    "Coverage aggregate disagrees with exact unit counts",
                    "/files/measurements",
                )
    if document["origin"] == "import":
        if document["receipt_id"] is not None or any(
            document[key]
            for key in [
                "proof_receipt_ids",
                "test_evidence_ids",
                "instrumentation",
                "profiles",
            ]
        ):
            _fail("Imported coverage cannot assert observed execution proof", "/origin")
    elif document["usability"] == "usable":
        if document["receipt_id"] is None or any(
            not document[key]
            for key in [
                "proof_receipt_ids",
                "test_evidence_ids",
                "instrumentation",
                "profiles",
            ]
        ):
            _fail(
                "Usable execution coverage needs typed instrumentation/profile/test proof",
                "/origin",
            )
        if any(file["source_sha256"] is None for file in document["files"]):
            _fail("Execution coverage cannot claim unknown source hashes", "/files")
    _unique(document["instrumentation"], "object_artifact_id", "/instrumentation")
    _unique(document["instrumentation"], "mapping_artifact_id", "/instrumentation")
    _unique(document["profiles"], "artifact_id", "/profiles")
    for object in document["instrumentation"]:
        for path in object["source_files"]:
            _safe_path(path, "/instrumentation/source_files")


def validate_verification_bundle(
    flat: list[tuple[str, dict[str, Any]]],
    manifest: dict[str, Any],
    receipts: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
) -> None:
    """Check typed verification identities and actual execution-role references."""
    from .validation import _datetime, _fail, _unique

    documents = [row for kind, row in flat if kind == "coverage_facts"]
    _unique(documents, "id", "/coverage_facts")
    artifacts = {row["id"]: row for row in manifest["artifacts"]}
    source = {row["path"]: row for row in manifest["source"]["files"]}
    facts = {
        row["receipt"]["id"]: row for kind, row in flat if kind == "execution_facts"
    }
    external = [row for kind, row in flat if kind == "external_analysis_facts"]
    _unique(external, "id", "/external_analysis_facts")
    subjects = _unique(
        [row for kind, row in flat if kind == "distribution_subject"],
        "id",
        "/distribution_subject",
    )
    matrices = _unique(
        [row for kind, row in flat if kind == "consumer_matrix"],
        "id",
        "/consumer_matrix",
    )
    sanitizers = _unique(
        [row for kind, row in flat if kind == "sanitizer_facts"],
        "id",
        "/sanitizer_facts",
    )
    for subject in subjects.values():
        for file in subject["source_files"]:
            if source.get(file["path"]) != file:
                _fail(
                    "Library subject selected source differs from owning run",
                    "/distribution_subject/source_files",
                    "SUBJECT_MISMATCH",
                )
        for file in subject["distribution_files"]:
            descriptor = artifacts.get(file["artifact_id"])
            if descriptor is None or any(
                descriptor[key] != file[key] for key in ["sha256", "size_bytes"]
            ):
                _fail(
                    "Distributed bytes differ from original artifact",
                    "/distribution_subject/distribution_files",
                    "SUBJECT_MISMATCH",
                )
    for matrix in matrices.values():
        if matrix["subject_id"] not in subjects:
            _fail(
                "Consumer matrix subject is missing",
                "/consumer_matrix/subject_id",
                "UNRESOLVED_REFERENCE",
            )

    def require_artifact(identifier: str) -> None:
        if identifier not in artifacts:
            _fail(
                "Verification role refers to an absent artifact",
                "/coverage_facts",
                "UNRESOLVED_REFERENCE",
            )

    def require_fact(identifier: str, context: str) -> dict[str, Any]:
        if identifier not in receipts or identifier not in facts:
            _fail(
                "Verification proof requires typed execution facts and receipt",
                "/coverage_facts",
                "UNRESOLVED_REFERENCE",
            )
        fact = facts[identifier]
        if fact["receipt"]["context_id"] != context:
            _fail(
                "Verification proof belongs to another job context",
                "/coverage_facts",
                "SUBJECT_MISMATCH",
            )
        return fact

    def output_owner(artifact: str, context: str) -> dict[str, Any]:
        owners = [
            fact
            for fact in facts.values()
            if any(
                link["artifact_id"] == artifact
                for link in fact["binding"]["output_artifacts"]
            )
        ]
        if len(owners) != 1:
            _fail(
                "Verification material needs one typed producing execution",
                "/coverage_facts",
                "UNRESOLVED_REFERENCE",
            )
        return require_fact(owners[0]["receipt"]["id"], context)

    def usable(
        fact: dict[str, Any],
        *,
        command_passed: bool = True,
    ) -> None:
        if (
            fact["binding"]["status"] != "verified"
            or fact["material_status"] != "available"
            or (command_passed and fact["receipt"]["status"] != "passed")
        ):
            _fail(
                "Usable verification contradicts unavailable execution material",
                "/coverage_facts",
                "SUBJECT_MISMATCH",
            )

    def inputs(fact: dict[str, Any]) -> set[str]:
        return {row["artifact_id"] for row in fact["binding"]["input_artifacts"]}

    def same_bytes(first: str, second: str) -> bool:
        return all(
            artifacts[first][key] == artifacts[second][key]
            for key in ["sha256", "size_bytes"]
        )

    def consumes(fact: dict[str, Any], identifier: str) -> bool:
        return any(same_bytes(candidate, identifier) for candidate in inputs(fact))

    def test_binary_binding(
        test: dict[str, Any], identifier: str, evidence_ids: list[str]
    ) -> None:
        bindings = [
            (plan, binding)
            for kind, plan in flat
            if kind == "collection_plan"
            for binding in plan["bindings"]
            if binding["kind"] == "tests"
            and binding["step_id"] == test["receipt"]["id"]
            and binding["id"] in evidence_ids
        ]
        paths = {
            row["path"]
            for row in test["binding"]["input_artifacts"]
            if same_bytes(row["artifact_id"], identifier)
        }
        if not any(paths & set(binding["exercised_inputs"]) for _, binding in bindings):
            _fail(
                "Verification binary lacks an actual selected CTest binding",
                "/verification/test_binding",
            )
        for plan, binding in bindings:
            for key in ["inventory_step_id", "producer_version_step_id"]:
                usable(require_fact(binding[key], test["receipt"]["context_id"]))

    for document in sanitizers.values():
        if not set(document["requested_files"]) <= source.keys():
            _fail(
                "Sanitizer scope is outside selected source",
                "/sanitizer_facts/requested_files",
            )
        for identifier in [
            document["binary_artifact_id"],
            *document["diagnostic_artifact_ids"],
            *(row["artifact_id"] for row in document["object_proofs"]),
            *(row["artifact_id"] for row in document["linked_components"]),
            *(row["artifact_id"] for row in document["exercise_proofs"]),
        ]:
            if identifier is not None:
                require_artifact(identifier)
        for object in document["object_proofs"]:
            for identifier in object["inspection_artifact_ids"]:
                require_artifact(identifier)
        if document["runtime_proof"] is not None:
            require_artifact(document["runtime_proof"]["inspection_artifact_id"])
        if document["origin"] != "execution":
            continue
        context = document["context_id"]
        for identifier in set(
            document["proof_receipt_ids"]
            + document["compile_receipt_ids"]
            + document["inspection_receipt_ids"]
            + [
                value
                for value in [
                    document["compiler_version_receipt_id"],
                    document["link_receipt_id"],
                ]
                if value is not None
            ]
        ):
            require_fact(identifier, context)
        if document["usability"] != "usable":
            continue
        if manifest.get("input_verification") != "verified":
            _fail(
                "Usable sanitizer execution requires verified finite selected sources",
                "/sanitizer_facts",
            )
        version = require_fact(document["compiler_version_receipt_id"], context)
        usable(version)
        expected_hash = document["producer"]["sha256"]
        needed_receipts = {
            document["compiler_version_receipt_id"],
            document["link_receipt_id"],
            *document["compile_receipt_ids"],
            *document["inspection_receipt_ids"],
        }

        def compiler(fact: dict[str, Any]) -> None:
            usable(fact)
            if (
                fact["executable_fact"] is None
                or fact["executable_fact"]["sha256"] != expected_hash
            ):
                _fail(
                    "Sanitizer compiler/version/link executable hashes disagree",
                    "/sanitizer_facts/producer",
                )
            if fact["receipt"]["id"] != version["receipt"]["id"] and _datetime(
                version["receipt"]["finished_at"]
            ) > _datetime(fact["receipt"]["started_at"]):
                _fail(
                    "Sanitizer version probe postdates compiler execution",
                    "/sanitizer_facts/compiler_version_receipt_id",
                )

        compiler(version)
        link = require_fact(document["link_receipt_id"], context)
        compiler(link)
        binary = document["binary_artifact_id"]
        if binary not in {
            row["artifact_id"] for row in link["binding"]["output_artifacts"]
        }:
            _fail(
                "Sanitizer binary is not the original link output",
                "/sanitizer_facts/binary_artifact_id",
            )

        def inspect(artifact: str, inspected: str) -> None:
            candidates = [
                require_fact(identifier, context)
                for identifier in document["inspection_receipt_ids"]
            ]
            owners = [
                fact
                for fact in candidates
                if artifact
                in (
                    {row["artifact_id"] for row in fact["binding"]["output_artifacts"]}
                    | {
                        value
                        for value in fact["binding"]["log_artifacts"].values()
                        if value is not None
                    }
                )
            ]
            if len(owners) != 1 or artifacts[artifact]["size_bytes"] == 0:
                _fail(
                    "Sanitizer inspection lacks one nonempty actual output/log",
                    "/sanitizer_facts/inspection_receipt_ids",
                )
            inspection = owners[0]
            needed_receipts.add(inspection["receipt"]["id"])
            usable(inspection)
            if not consumes(inspection, inspected) or inspection["logs_truncated"]:
                _fail(
                    "Sanitizer inspection did not consume the selected object/binary",
                    "/sanitizer_facts/inspection_receipt_ids",
                )

        for object in document["object_proofs"]:
            compile = require_fact(object["compile_receipt_id"], context)
            needed_receipts.add(object["compile_receipt_id"])
            compiler(compile)
            if object["artifact_id"] not in {
                row["artifact_id"] for row in compile["binding"]["output_artifacts"]
            } or not consumes(link, object["artifact_id"]):
                _fail(
                    "Sanitizer object does not connect its compile and link",
                    "/sanitizer_facts/object_proofs",
                )
            if (
                not set(object["source_files"])
                <= {row["path"] for row in compile["input_facts"]}
                or not set(object["source_files"]) <= source.keys()
            ):
                _fail(
                    "Sanitizer compiler did not observe the claimed selected source",
                    "/sanitizer_facts/object_proofs/source_files",
                )
            for identifier in object["inspection_artifact_ids"]:
                inspect(identifier, object["artifact_id"])
        for component in document["linked_components"]:
            if component["instrumentation"] == "observed" and not any(
                same_bytes(component["artifact_id"], object["artifact_id"])
                for object in document["object_proofs"]
            ):
                _fail(
                    "Observed component is not backed by emitted object proof",
                    "/sanitizer_facts/linked_components",
                )
        inspect(document["runtime_proof"]["inspection_artifact_id"], binary)
        record = evidence.get(document["test_evidence_id"])
        if (
            record is None
            or record["origin"] != "execution"
            or record["kind"] != "tests"
            or record["usability"] != "usable"
            or record["context_id"] != context
        ):
            _fail(
                "Sanitizer needs usable actual test evidence",
                "/sanitizer_facts/test_evidence_id",
            )
        test_artifacts = set()
        cases = set()
        for exercise in document["exercise_proofs"]:
            test = require_fact(exercise["test_receipt_id"], context)
            needed_receipts.add(exercise["test_receipt_id"])
            usable(test, command_passed=False)
            if record["receipt_id"] != exercise["test_receipt_id"] or not set(
                exercise["test_case_ids"]
            ) <= set(record["scope"].get("tests", [])):
                _fail(
                    "Sanitizer exercise cases differ from observed test scope",
                    "/sanitizer_facts/exercise_proofs",
                )
            if exercise["artifact_id"] not in inputs(test) or not same_bytes(
                exercise["artifact_id"], binary
            ):
                _fail(
                    "Actually exercised input differs from instrumented linked binary",
                    "/sanitizer_facts/exercise_proofs/artifact_id",
                )
            counts = test["receipt"].get("tests", {})
            if (
                not counts
                or counts["passed"] + counts["failed"] + counts["errors"] == 0
            ):
                _fail(
                    "Sanitizer has no actually executed nonzero test cases",
                    "/sanitizer_facts/exercise_proofs",
                )
            if document["outcome"] == "passed" and (
                test["receipt"]["status"] != "passed"
                or record["status"] != "passed"
                or counts["failed"]
                or counts["errors"]
            ):
                _fail(
                    "Clean sanitizer outcome contradicts test failure",
                    "/sanitizer_facts/outcome",
                )
            test_binary_binding(test, binary, [document["test_evidence_id"]])
            cases.update(exercise["test_case_ids"])
            test_artifacts.update(
                row["artifact_id"] for row in test["binding"]["output_artifacts"]
            )
            test_artifacts.update(
                value
                for value in test["binding"]["log_artifacts"].values()
                if value is not None
            )
        if not set(document["diagnostic_artifact_ids"]) <= test_artifacts:
            _fail(
                "Sanitizer diagnostic logs are not actual exercised test outputs",
                "/sanitizer_facts/diagnostic_artifact_ids",
            )
        if any(
            row["test_case_id"] not in cases
            or (row["file"] is not None and row["file"] not in source)
            for row in document["diagnostics"]
        ):
            _fail(
                "Sanitizer diagnostic has unrelated case/source ownership",
                "/sanitizer_facts/diagnostics",
            )
        if not needed_receipts <= set(document["proof_receipt_ids"]):
            _fail(
                "Sanitizer proof list omits an actual required execution",
                "/sanitizer_facts/proof_receipt_ids",
            )

    for document in external:
        require_artifact(document["report_artifact_id"])
        if not set(document["scope_files"]) <= source.keys():
            _fail(
                "External report scope is outside selected source",
                "/external_analysis_facts/scope_files",
                "SUBJECT_MISMATCH",
            )

    for document in documents:
        require_artifact(document["report_artifact_id"])
        for file in document["files"]:
            if file["file"] not in source or file["source_sha256"] not in {
                None,
                source[file["file"]]["sha256"],
            }:
                _fail(
                    "Coverage file/hash differs from selected source",
                    "/coverage_facts/files",
                    "SUBJECT_MISMATCH",
                )
        for object in document["instrumentation"]:
            for identifier in [
                object["object_artifact_id"],
                object["mapping_artifact_id"],
            ]:
                require_artifact(identifier)
            if not set(object["source_files"]) <= source.keys():
                _fail(
                    "Instrumented object scope is outside selected source",
                    "/coverage_facts/instrumentation",
                    "SUBJECT_MISMATCH",
                )
        for profile in document["profiles"]:
            require_artifact(profile["artifact_id"])
            require_artifact(profile["binary_artifact_id"])
        if document["origin"] != "execution":
            continue
        context = document["context_id"]
        for identifier in document["proof_receipt_ids"]:
            require_fact(identifier, context)
        if document["receipt_id"] is None:
            continue
        report = require_fact(document["receipt_id"], context)
        if document["report_artifact_id"] not in {
            row["artifact_id"] for row in report["binding"]["output_artifacts"]
        }:
            _fail(
                "Coverage report is not an observed output of its receipt",
                "/coverage_facts/report_artifact_id",
                "SUBJECT_MISMATCH",
            )
        if document["usability"] != "usable":
            continue
        if manifest.get("input_verification") != "verified":
            _fail(
                "Usable execution coverage requires verified selected sources",
                "/coverage_facts",
            )
        usable(report)
        needed_receipts = {document["receipt_id"]}
        for object in document["instrumentation"]:
            producer = output_owner(object["object_artifact_id"], context)
            needed_receipts.add(producer["receipt"]["id"])
            usable(producer)
            if object["mapping_artifact_id"] not in {
                row["artifact_id"] for row in producer["binding"]["output_artifacts"]
            }:
                _fail(
                    "Object and coverage mapping need the same actual compiler receipt",
                    "/coverage_facts/instrumentation",
                )
            observed = {row["path"] for row in producer["input_facts"]}
            if not set(object["source_files"]) <= observed:
                _fail(
                    "Coverage compiler did not observe selected source inputs",
                    "/coverage_facts/instrumentation",
                )
            if not consumes(report, object["mapping_artifact_id"]):
                _fail(
                    "Coverage report did not consume declared compiler mapping",
                    "/coverage_facts/instrumentation",
                )
        if not {row["file"] for row in document["files"]} <= {
            path
            for object in document["instrumentation"]
            for path in object["source_files"]
        }:
            _fail(
                "Reported coverage files lack observed instrumented objects",
                "/coverage_facts/files",
            )
        if not set(document["test_evidence_ids"]) <= evidence.keys():
            _fail(
                "Coverage test evidence is missing",
                "/coverage_facts/test_evidence_ids",
                "UNRESOLVED_REFERENCE",
            )
        for profile in document["profiles"]:
            execution = require_fact(profile["test_receipt_id"], context)
            needed_receipts.add(profile["test_receipt_id"])
            usable(execution, command_passed=False)
            counts = execution["receipt"].get("tests", {})
            if (
                not counts
                or counts["passed"] + counts["failed"] + counts["errors"] == 0
            ):
                _fail(
                    "Coverage requires actually executed nonzero test cases",
                    "/coverage_facts/profiles",
                )
            if profile["artifact_id"] not in {
                row["artifact_id"] for row in execution["binding"]["output_artifacts"]
            } or not consumes(execution, profile["binary_artifact_id"]):
                _fail(
                    "Runtime profile/binary is not observed test output/input",
                    "/coverage_facts/profiles",
                )
            link = output_owner(profile["binary_artifact_id"], context)
            needed_receipts.add(link["receipt"]["id"])
            usable(link)
            if not any(
                consumes(link, object["object_artifact_id"])
                for object in document["instrumentation"]
            ):
                _fail(
                    "Exercised binary did not consume the instrumented object",
                    "/coverage_facts/profiles",
                )
            profile_paths = {
                row["path"]
                for row in execution["binding"]["output_artifacts"]
                if row["artifact_id"] == profile["artifact_id"]
            }
            if any(
                row["path"] in profile_paths and row["freshness"] != "created"
                for row in execution["output_facts"]
            ) or any(
                row["path"] in profile_paths
                for row in execution["preexisting_output_facts"]
            ):
                _fail(
                    "Initial coverage profile must be newly created, not accumulated",
                    "/coverage_facts/profiles",
                )
            test_binary_binding(
                execution, profile["binary_artifact_id"], document["test_evidence_ids"]
            )
            matching = [
                evidence[key]
                for key in document["test_evidence_ids"]
                if evidence[key]["receipt_id"] == profile["test_receipt_id"]
            ]
            if not matching or any(
                row["kind"] != "tests"
                or row["origin"] != "execution"
                or row["usability"] != "usable"
                for row in matching
            ):
                _fail(
                    "Runtime profile requires usable observed test evidence",
                    "/coverage_facts/test_evidence_ids",
                )
            if not consumes(report, profile["artifact_id"]) or _datetime(
                execution["receipt"]["finished_at"]
            ) > _datetime(report["receipt"]["started_at"]):
                _fail(
                    "Coverage report does not consume a causal runtime profile",
                    "/coverage_facts/profiles",
                )
        if not needed_receipts <= set(document["proof_receipt_ids"]):
            _fail(
                "Coverage proof list omits a material-producing execution",
                "/coverage_facts/proof_receipt_ids",
            )
    from .consumers import validate_consumer_bundle

    validate_consumer_bundle(flat, manifest, receipts, evidence)


def validate_verification_assessment(
    flat: list[tuple[str, dict[str, Any]]],
    manifest: dict[str, Any],
    policy: dict[str, Any],
    assessment: dict[str, Any],
    evidence: dict[str, dict[str, Any]],
) -> None:
    """Guard current typed references/positive claims without executing a policy."""
    from .validation import _datetime, _fail, policy_scope_paths

    if policy.get("evaluator_profile", "1.0.0") not in {"1.1.0", "1.2.0"}:
        return
    families = {
        kind: {row["id"]: row for family, row in flat if family == kind}
        for kind in ["coverage_facts", "sanitizer_facts"]
    }
    receipts = {row["id"]: row for kind, row in flat if kind == "execution_receipt"}
    results = {row["id"]: row for row in assessment["controls"]}
    selected = set(
        policy_scope_paths(policy, [row["path"] for row in manifest["source"]["files"]])
    )
    generated = _datetime(assessment["generated_at"])

    def current(fact):
        if fact["origin"] != "execution" or fact["usability"] != "usable":
            return False
        ids = (
            fact["test_evidence_ids"]
            if "test_evidence_ids" in fact
            else [fact["test_evidence_id"]]
        )
        return all(
            identifier in evidence
            and (
                evidence[identifier].get("expires_at") is None
                or _datetime(evidence[identifier]["expires_at"]) > generated
            )
            for identifier in ids
        )

    for control in policy["controls"]:
        if control["kind"] not in {"minimum_coverage", "sanitizer_outcome"}:
            continue
        result = results[control["id"]]
        if result["status"] == "not_applicable":
            continue
        params = control["parameters"]
        family = (
            "coverage_facts"
            if control["kind"] == "minimum_coverage"
            else "sanitizer_facts"
        )
        records = families[family]
        named = set(params["fact_ids"])
        linked = set(result.get("fact_ids", []))
        if not linked <= records.keys():
            _fail(
                "Assessment references an absent/wrong-kind typed fact",
                "/assessment/controls/fact_ids",
                "UNRESOLVED_REFERENCE",
            )
        if (
            result["status"] in {"passed", "failed"}
            and not (named & records.keys()) <= linked
        ):
            _fail(
                "Definite verification outcome omits known required fact links",
                "/assessment/controls/fact_ids",
            )
        for identifier in linked:
            for receipt_id in records[identifier]["proof_receipt_ids"]:
                if generated < _datetime(receipts[receipt_id]["finished_at"]):
                    _fail(
                        "Assessment predates used typed verification proof",
                        "/assessment/generated_at",
                        "SUBJECT_MISMATCH",
                    )
        missing = not named <= records.keys()
        if missing and (
            result["status"] == "passed" or result.get("incomplete") is False
        ):
            _fail(
                "Missing named verification facts must remain incomplete",
                "/assessment/controls",
            )
        if result["status"] == "passed" and (
            not named <= linked or result.get("incomplete") is not False
        ):
            _fail(
                "Passed verification omits required complete fact links",
                "/assessment/controls/fact_ids",
            )
        contexts = set(params.get("contexts", policy["contexts"]))
        facts = [records[identifier] for identifier in named if identifier in records]
        available = [
            fact for fact in facts if current(fact) and fact["context_id"] in contexts
        ]
        if result["status"] == "passed" and (
            not selected or len(available) != len(facts)
        ):
            _fail(
                "Positive verification lacks current observed source/job facts",
                "/assessment/controls",
            )
        incomplete = missing or len(available) != len(facts)
        if control["kind"] == "minimum_coverage":
            below = False
            for context in contexts:
                for path in selected:
                    groups = [
                        measurement
                        for fact in available
                        if fact["context_id"] == context
                        for file in fact["files"]
                        if file["file"] == path
                        for measurement in file["measurements"]
                        if measurement["kind"] == params["measurement_kind"]
                        and measurement["method"] == params["method"]
                    ]
                    signatures = {
                        tuple(
                            sorted(
                                (unit["id"], unit["covered"], unit["total"])
                                for unit in measurement["units"]
                            )
                        )
                        for measurement in groups
                    }
                    if len(signatures) != 1 or not groups or groups[0]["total"] == 0:
                        incomplete = True
                        if result["status"] == "passed":
                            _fail(
                                "Coverage cell is missing, zero or conflicting",
                                "/assessment/controls",
                            )
                        continue
                    low = (
                        100
                        * Fraction(str(groups[0]["covered"]))
                        / Fraction(str(groups[0]["total"]))
                    ) < Fraction(str(params["minimum"]))
                    below |= low
                    if low and result["status"] == "passed":
                        _fail(
                            "Positive coverage contradicts an exact per-file/job ratio",
                            "/assessment/controls",
                        )
            if result["status"] == "failed" and not below:
                _fail(
                    "Coverage failure lacks a known below-threshold selected cell",
                    "/assessment/controls",
                )
        else:
            matching = [
                fact for fact in available if fact["sanitizer"] == params["sanitizer"]
            ]
            incomplete |= len(matching) != len(available)
            if result["status"] == "failed" and not any(
                fact["outcome"] == "failed" and fact["diagnostics"] for fact in matching
            ):
                _fail(
                    "Sanitizer failure lacks a credible observed diagnostic",
                    "/assessment/controls",
                )
            for context in contexts:
                job = [fact for fact in matching if fact["context_id"] == context]
                scope = {
                    path
                    for fact in job
                    for object in fact["object_proofs"]
                    for path in object["source_files"]
                }
                incomplete |= not selected <= scope or any(
                    row["instrumentation"] != "observed"
                    for fact in job
                    for row in fact["linked_components"]
                )
                if result["status"] == "passed" and (
                    not selected <= scope
                    or any(fact["outcome"] != "passed" for fact in job)
                ):
                    _fail(
                        "Positive sanitizer lacks clean instrumented selected file/job scope",
                        "/assessment/controls",
                    )
        if incomplete and (
            result["status"] == "passed" or result.get("incomplete") is False
        ):
            _fail(
                "Incomplete verification cannot be a complete/waivable result",
                "/assessment/controls",
            )
