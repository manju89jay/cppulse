"""Pure identity checks for selected library use and imported applicability."""

from typing import Any


def semantic(kind: str, document: dict[str, Any]) -> None:
    from .validation import _fail, _safe_path, _unique

    if kind == "consumer_comparison":
        _unique(document["cases"], "case_id", "/cases")
        if document["producer"] != {
            "name": "cppulse.consumer-compare",
            "version": "1.0.0",
        }:
            _fail("Unsupported consumer comparison semantics", "/producer")
        if document["source_digest"] != document["local_source_digest"]:
            _fail(
                "Comparison owning source must be the local selected subject",
                "/local_source_digest",
            )
        for case in document["cases"]:
            if not set(case["missing_local_checks"]) <= set(
                case["required_local_checks"]
            ):
                _fail(
                    "Missing local check is outside declared required checks",
                    "/cases/missing_local_checks",
                )
            if case["status"] == "compatible" and (
                case["upstream_case_id"] is None
                or case["mismatches"]
                or not case["matching_dimensions"]
            ):
                _fail(
                    "Compatible configuration lacks an actual counterpart/dimension agreement",
                    "/cases",
                )
            if case["status"] == "incompatible" and not case["mismatches"]:
                _fail(
                    "Incompatibility requires explicit mismatching dimensions",
                    "/cases/mismatches",
                )
            if (
                case["local_test_status"] in {"passed", "failed"}
                and not case["local_test_evidence_ids"]
            ):
                _fail(
                    "Observed local test outcome requires actual evidence links",
                    "/cases/local_test_evidence_ids",
                )
        return
    if kind != "consumer_usage":
        return
    for path in document["self_containment_headers"]:
        _safe_path(path, "/self_containment_headers")
    if (
        document["producer"]["name"] != "cppulse.consumer-use"
        or document["producer"]["version"] != "1.0.0"
    ):
        _fail("Unsupported consumer usage producer", "/producer")
    if document["status"] == "verified":
        if any(
            document[key] is None
            for key in [
                "receipt_id",
                "observed_configuration",
                "configuration_probe_receipt_id",
                "target_probe_receipt_id",
            ]
        ):
            _fail(
                "Verified usage lacks actual execution/configuration probes", "/status"
            )
        if not set(document["required_artifact_ids"]) <= {
            row["distribution_artifact_id"] for row in document["records"]
        }:
            _fail("Verified usage omits required distributed artifacts", "/records")
        if document["compiler_version"] != "14.2.0":
            _fail(
                "Consumer use adapter currently supports GCC14.2.0", "/compiler_version"
            )
        if (
            any(row["proof_kind"] == "gnu-linker-map" for row in document["records"])
            and document["linker_version"] != "2.44"
        ):
            _fail("GNU linker map adapter currently supports ld2.44", "/linker_version")


def validate_consumer_bundle(
    flat: list[tuple[str, dict[str, Any]]],
    manifest: dict[str, Any],
    receipts: dict[str, dict[str, Any]],
    evidence: dict[str, dict[str, Any]],
) -> None:
    """Bind selected distribution use and imported comparison references."""
    from .validation import _datetime, _fail, _unique

    usages = _unique(
        [row for kind, row in flat if kind == "consumer_usage"], "id", "/consumer_usage"
    )
    subjects = {row["id"]: row for kind, row in flat if kind == "distribution_subject"}
    artifacts = {row["id"]: row for row in manifest["artifacts"]}
    facts = {
        row["receipt"]["id"]: row for kind, row in flat if kind == "execution_facts"
    }

    def same_bytes(first, second):
        return all(
            artifacts[first][key] == artifacts[second][key]
            for key in ["sha256", "size_bytes"]
        )

    def actual(identifier, context):
        fact = facts.get(identifier)
        if (
            identifier not in receipts
            or fact is None
            or fact["receipt"]["context_id"] != context
        ):
            _fail(
                "Consumer use requires a typed same-context execution",
                "/consumer_usage/proof_receipt_ids",
                "UNRESOLVED_REFERENCE",
            )
        return fact

    def usable(fact):
        if (
            fact["binding"]["status"] != "verified"
            or fact["material_status"] != "available"
            or fact["receipt"]["status"] != "passed"
        ):
            _fail(
                "Verified consumer use contradicts incomplete execution",
                "/consumer_usage/status",
            )

    for usage in usages.values():
        subject = subjects.get(usage["subject_id"])
        if subject is None:
            _fail(
                "Consumer use subject is missing",
                "/consumer_usage/subject_id",
                "UNRESOLVED_REFERENCE",
            )
        distributed = {row["artifact_id"]: row for row in subject["distribution_files"]}
        if not set(usage["required_artifact_ids"]) <= distributed.keys():
            _fail(
                "Required consumer artifacts are not the selected distribution",
                "/consumer_usage/required_artifact_ids",
            )
        for record in usage["records"]:
            if (
                record["distribution_artifact_id"] not in distributed
                or record["proof_artifact_id"] not in artifacts
            ):
                _fail(
                    "Consumer use proof/distribution artifact is missing",
                    "/consumer_usage/records",
                    "UNRESOLVED_REFERENCE",
                )
        for identifier in usage["proof_receipt_ids"]:
            actual(identifier, usage["context_id"])
        if usage["status"] != "verified":
            continue
        if manifest.get("input_verification") != "verified":
            _fail(
                "Verified consumer use requires current selected sources",
                "/consumer_usage",
            )
        execution = actual(usage["receipt_id"], usage["context_id"])
        usable(execution)
        expected = {
            usage["receipt_id"],
            usage["configuration_probe_receipt_id"],
            usage["target_probe_receipt_id"],
        }
        if not expected <= set(usage["proof_receipt_ids"]):
            _fail(
                "Usage proof list omits required actual probes",
                "/consumer_usage/proof_receipt_ids",
            )
        executable = execution["executable_fact"]
        compiler = usage["observed_configuration"]["compiler"]
        if (
            executable is None
            or compiler is None
            or compiler["sha256"] != executable["sha256"]
            or compiler["version"] != usage["compiler_version"]
        ):
            _fail(
                "Observed consumer configuration/compiler executable disagree",
                "/consumer_usage/observed_configuration",
            )
        for identifier in [
            usage["configuration_probe_receipt_id"],
            usage["target_probe_receipt_id"],
        ]:
            probe = actual(identifier, usage["context_id"])
            usable(probe)
            if (
                probe["executable_fact"] is None
                or probe["executable_fact"]["sha256"] != executable["sha256"]
                or probe["logs_truncated"]
                or _datetime(probe["receipt"]["finished_at"])
                > _datetime(execution["receipt"]["started_at"])
            ):
                _fail(
                    "Consumer configuration probe is not complete/causal/same-compiler",
                    "/consumer_usage",
                )
        input_ids = {
            row["artifact_id"] for row in execution["binding"]["input_artifacts"]
        }
        output_ids = {
            row["artifact_id"] for row in execution["binding"]["output_artifacts"]
        }
        for record in usage["records"]:
            if (
                not any(
                    same_bytes(identifier, record["distribution_artifact_id"])
                    for identifier in input_ids
                )
                or record["proof_artifact_id"] not in output_ids
            ):
                _fail(
                    "Consumer distribution input/proof output is not actually bound",
                    "/consumer_usage/records",
                )
        logical = {
            row["path"]
            for row in subject["distribution_files"]
            if row["artifact_id"] in usage["required_artifact_ids"]
        }
        if not set(usage["self_containment_headers"]) <= logical or (
            usage["self_containment_headers"]
            and any(row["proof_kind"] != "depfile" for row in usage["records"])
        ):
            _fail(
                "Self-containment claim is outside selected header proofs",
                "/consumer_usage/self_containment_headers",
            )
    comparisons = _unique(
        [row for kind, row in flat if kind == "consumer_comparison"],
        "id",
        "/consumer_comparison",
    )
    matrices = {row["id"]: row for kind, row in flat if kind == "consumer_matrix"}
    for comparison in comparisons.values():
        for key in [
            "upstream_manifest_artifact_id",
            "local_manifest_artifact_id",
            "upstream_subject_artifact_id",
            "upstream_matrix_artifact_id",
        ]:
            if comparison[key] not in artifacts:
                _fail(
                    "Comparison retained raw subject/manifest/matrix role is missing",
                    "/consumer_comparison/" + key,
                    "UNRESOLVED_REFERENCE",
                )
        for side in ["upstream", "local"]:
            if (
                artifacts[comparison[side + "_manifest_artifact_id"]]["sha256"]
                != comparison[side + "_manifest_sha256"]
            ):
                _fail(
                    "Comparison manifest SHA differs from retained original bytes",
                    "/consumer_comparison",
                )
        matrix = matrices.get(comparison["local_matrix_id"])
        if matrix is None or matrix["subject_id"] != comparison["local_subject_id"]:
            _fail(
                "Comparison local matrix/subject identity is unresolved",
                "/consumer_comparison/local_matrix_id",
            )
        cases = {case["id"]: case for case in matrix["cases"]}
        if set(cases) != {case["case_id"] for case in comparison["cases"]}:
            _fail(
                "Comparison must account for every declared local case",
                "/consumer_comparison/cases",
            )
        generated = _datetime(comparison["generated_at"])
        for result in comparison["cases"]:
            case = cases[result["case_id"]]
            required = set(case["tests"]) | set(case["self_containment_headers"])
            if not required <= set(result["required_local_checks"]):
                _fail(
                    "Comparison hides declared required local checks",
                    "/consumer_comparison/cases/required_local_checks",
                )
            selected = [
                usages[identifier]
                for identifier in case["usage_ids"]
                if identifier in usages
            ]
            verified = [
                usage
                for usage in selected
                if usage["status"] == "verified"
                and usage["context_id"] == case["context_id"]
                and usage["subject_id"] == matrix["subject_id"]
            ]
            if result["status"] == "compatible":
                config = case["configuration"]
                if (
                    not selected
                    or len(verified) != len(case["usage_ids"])
                    or set(result["matching_dimensions"]) != set(config)
                ):
                    _fail(
                        "Positive applicability lacks all actual local configuration dimensions",
                        "/consumer_comparison/cases",
                    )
                for key, value in config.items():
                    if (
                        value is None
                        or (key == "compiler" and value.get("sha256") is None)
                        or (
                            key == "dependencies"
                            and any(
                                row["availability"] != "available"
                                or row["sha256"] is None
                                for row in value
                            )
                        )
                        or any(
                            usage["observed_configuration"][key] != value
                            for usage in verified
                        )
                    ):
                        _fail(
                            "Unknown/mismatched observed configuration cannot be compatible",
                            "/consumer_comparison/cases/matching_dimensions",
                        )
            headers = {
                header
                for usage in verified
                for header in usage["self_containment_headers"]
            }
            if not set(case["self_containment_headers"]) - headers <= set(
                result["missing_local_checks"]
            ):
                _fail(
                    "Unobserved header self-containment must remain a missing local check",
                    "/consumer_comparison/cases",
                )
            if result["local_test_status"] == "unknown" and not set(
                case["tests"]
            ) <= set(result["missing_local_checks"]):
                _fail(
                    "Unknown application tests must remain missing local checks",
                    "/consumer_comparison/cases",
                )
            for identifier in result["local_test_evidence_ids"]:
                record = evidence.get(identifier)
                if (
                    record is None
                    or record["kind"] != "tests"
                    or record["origin"] != "execution"
                    or record["usability"] != "usable"
                    or record["context_id"] != case["context_id"]
                    or (
                        record.get("expires_at") is not None
                        and _datetime(record["expires_at"]) <= generated
                    )
                ):
                    _fail(
                        "Comparison local test reference is unavailable/mismatched/expired",
                        "/consumer_comparison/cases/local_test_evidence_ids",
                    )
                receipt = receipts[record["receipt_id"]]
                if generated < _datetime(receipt["finished_at"]):
                    _fail(
                        "Comparison predates its local tests",
                        "/consumer_comparison/generated_at",
                    )
                if result["local_test_status"] == "passed" and (
                    record["status"] != "passed"
                    or not receipt.get("tests", {}).get("passed")
                ):
                    _fail(
                        "Local application pass lacks observed passed test cases",
                        "/consumer_comparison/cases/local_test_status",
                    )
