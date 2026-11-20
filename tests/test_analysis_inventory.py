"""Native normalization transforms checked facts; synthetic records are labeled."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cppulse.collection import collect
from test_collection import build_plan, documents


def test_collection_produces_typed_execution_facts_with_original_path_bindings(
    tmp_path: Path,
) -> None:
    plan, source, contexts = build_plan(
        tmp_path,
        "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_text('actual local command output')",
    )
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    facts = documents(snapshot, "execution_facts")
    assert len(facts) == 1
    facts = facts[0]
    assert facts["version"] == "2.0.0" and facts["binding"]["status"] == "verified"
    assert facts["receipt"] == documents(snapshot, "execution_receipt")[0]
    assert {row["path"] for row in facts["binding"]["input_artifacts"]} == {
        "build.py",
        "source.cpp",
    }
    output = facts["binding"]["output_artifacts"][0]
    assert output["path"] == "build/app"
    assert snapshot.read_bytes(output["artifact_id"]) == b"actual local command output"
    assert set(facts["binding"]["log_artifacts"]) == {"stdout", "stderr"}


def test_post_collection_tool_problem_is_typed_invalid_without_rewriting_process_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.collection as module

    plan, source, contexts = build_plan(
        tmp_path,
        "from pathlib import Path\nPath('build').mkdir()\nPath('build/app').write_text('actual local command output')",
    )
    monkeypatch.setattr(
        module,
        "_tool_problem",
        lambda result: "Synthetic post-command tool identity change for binding regression",
    )
    snapshot = collect(
        plan,
        workspace=tmp_path,
        source=source,
        contexts=contexts,
        store=tmp_path / "store",
    )
    facts = documents(snapshot, "execution_facts")[0]
    assert facts["receipt"]["status"] == "passed" and facts["receipt"]["exit_code"] == 0
    assert facts["binding"]["status"] == "invalid"
    assert any(
        "tool identity change" in reason for reason in facts["binding"]["limitations"]
    )
    assert snapshot.manifest["status"] == "partial"


# The following fixtures are explicitly synthetic closed contract records. They
# test transformation/error semantics, not a claim that the synthetic tool ran.
def native_snapshot(
    root: Path,
    *,
    typed: bool = True,
    mutate: Any = None,
    job: str = "native",
    report_path: str = "native-output/findings.json",
    database_directory: bool = False,
    verified: bool = True,
    job_tool_sha: str = "e" * 64,
) -> tuple[Any, dict[str, Any]]:
    """Create immutable synthetic records; actual native execution is a demo gate."""
    import hashlib
    import json
    from copy import deepcopy
    from cppulse import __version__
    from cppulse.identities import (
        context_identity,
        digest_json,
        snapshot_inputs,
        verify_inputs,
    )
    from cppulse.run_store import RunStore
    from cppulse.tooling import load_rule_registry

    root.mkdir(parents=True, exist_ok=True)

    def write(path: str, data: bytes) -> None:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def encoded(data: Any) -> bytes:
        return (
            json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
        ).encode()

    write("main.cpp", b"int main() { return 0; }\n")
    registry = load_rule_registry()
    write("rule-registry.json", encoded(registry))
    write(
        "native-config.json",
        encoded(
            {
                "profile": "default",
                "exclude_paths": ["build/**", "resources/**"],
                "rules": {},
            }
        ),
    )
    resource_root = "resources/clang"
    for name in ["stddef.h", "stdint.h"]:
        write(
            resource_root + "/include/" + name,
            b"// Synthetic selected resource data, not a real compiler distribution.\n",
        )
    resource_files = [
        {
            "path": resource_root + "/include/" + name,
            "sha256": hashlib.sha256(
                (root / resource_root / "include" / name).read_bytes()
            ).hexdigest(),
            "size_bytes": (root / resource_root / "include" / name).stat().st_size,
        }
        for name in ["stddef.h", "stdint.h"]
    ]
    resource = {
        "version": "2.0.0",
        "root": resource_root,
        "files": resource_files,
        "limitations": [
            "Synthetic finite resource inventory for normalization unit tests."
        ],
    }
    write("resource-manifest.json", encoded(resource))
    database = [
        {
            "directory": str(root),
            "file": "main.cpp",
            "arguments": ["/synthetic/g++", "-std=c++17", "-c", "main.cpp"],
        }
    ]
    write("compile_commands.json", encoded(database))
    parser_arguments = [
        "-working-directory=" + str(root),
        "--driver-mode=g++",
        "-std=c++17",
        "-resource-dir=" + str(root / resource_root),
    ]
    report = {
        "version": "1.0.0",
        "metadata": {
            "repo_path": str(root),
            "analyzed_at": "2026-11-13T10:00:00Z",
            "file_count": 1,
            "total_loc": 1,
            "analysis": {
                "parser": {"name": "libclang", "version": "synthetic libclang 19"},
                "enabled_rules": [rule["id"] for rule in registry["rules"]],
                "files": [
                    {
                        "path": str(root / "main.cpp"),
                        "status": "analyzed",
                        "error_count": 0,
                        "compile_context": "database",
                        "parse_arguments": parser_arguments,
                        "working_directory": str(root),
                    }
                ],
            },
        },
        "findings": [],
        "summary": {
            "total_findings": 0,
            "by_category": {
                "memory_safety": 0,
                "modernization": 0,
                "complexity": 0,
                "misra": 0,
            },
            "by_severity": {"error": 0, "warning": 0, "info": 0},
        },
    }
    if mutate is not None:
        mutate(report, root)
    paths = [
        "main.cpp",
        "rule-registry.json",
        "native-config.json",
        "resource-manifest.json",
        "compile_commands.json",
        *[item["path"] for item in resource_files],
    ]
    source = snapshot_inputs(root, paths, inventory_complete=True)
    argv = [
        "/synthetic/cppulse-analyzer",
        "--repo",
        str(root),
        "--config",
        "native-config.json",
        "--compilation-database",
        "." if database_directory else "compile_commands.json",
        "--resource-dir",
        resource_root,
        "--output",
        "native-output",
    ]
    context = context_identity(
        {
            "id": job,
            "compiler": {
                "name": "cppulse-analyzer",
                "version": __version__,
                "sha256": job_tool_sha,
            },
            "argv": argv,
            "working_directory": str(root),
            "language_standard": None,
            "target": None,
            "provenance": "inferred",
            "dependencies": [],
            "limitations": [
                "Synthetic coarse job declaration; no actual tool was executed."
            ],
        }
    )
    plan = {
        "version": "2.0.0",
        "id": "synthetic-plan-" + job,
        "recipe": {
            "version": "2.0.0",
            "id": "synthetic-recipe-" + job,
            "contexts": [job],
            "jobs": 1,
            "steps": [
                {
                    "id": "analyze",
                    "context_id": job,
                    "argv": argv,
                    "cwd": ".",
                    "depends_on": [],
                    "inputs": paths,
                    "outputs": [report_path],
                    "timeout_seconds": 30,
                },
                {
                    "id": "unattempted-build",
                    "context_id": job,
                    "argv": ["/synthetic/build"],
                    "cwd": ".",
                    "depends_on": [],
                    "inputs": [],
                    "outputs": ["build/placeholder"],
                    "timeout_seconds": 30,
                },
            ],
        },
        "bindings": [
            {
                "id": "unattempted-build-proof",
                "step_id": "unattempted-build",
                "kind": "build",
                "scope_files": ["main.cpp"],
                "report_path": None,
                "execution_log_path": None,
                "adapter": None,
                "adapter_version": None,
                "inventory_step_id": None,
                "producer_version_step_id": None,
                "exercised_inputs": ["build/placeholder"],
            }
        ],
        "limits": {
            "max_log_bytes": 1048576,
            "max_artifact_bytes": 67108864,
            "max_metadata_bytes": 16777216,
            "termination_grace_seconds": 1,
        },
    }
    write(report_path, encoded(report))
    write("stdout.log", b"")
    write("stderr.log", b"")
    store = RunStore(root / "store")
    with store.begin() as stage:
        inputs = []
        facts = []
        roles = {}
        for index, path in enumerate(paths):
            artifact = stage.copy_artifact(
                "input-" + str(index), root / path, "original-inputs/" + path
            )
            roles[path] = artifact["id"]
            inputs.append({"path": path, "artifact_id": artifact["id"]})
            info = (root / path).stat()
            facts.append(
                {
                    "path": path,
                    "sha256": artifact["sha256"],
                    "size_bytes": artifact["size_bytes"],
                    "stat": {
                        "device": info.st_dev,
                        "inode": info.st_ino,
                        "mtime_ns": info.st_mtime_ns,
                        "ctime_ns": info.st_ctime_ns,
                    },
                }
            )
        output = stage.copy_artifact(
            "native-report",
            root / report_path,
            "original-output/findings.json",
        )
        output_stat = (root / report_path).stat()
        output_fact = {
            "path": report_path,
            "sha256": output["sha256"],
            "size_bytes": output["size_bytes"],
            "stat": {
                "device": output_stat.st_dev,
                "inode": output_stat.st_ino,
                "mtime_ns": output_stat.st_mtime_ns,
                "ctime_ns": output_stat.st_ctime_ns,
            },
            "freshness": "created",
        }
        for stream in ["stdout", "stderr"]:
            stage.copy_artifact(
                "native-" + stream,
                root / (stream + ".log"),
                "original-logs/" + stream + ".log",
                "text/plain",
            )
        receipt = {
            "version": "2.0.0",
            "id": "analyze",
            "source_digest": source["digest"],
            "context_id": job,
            "producer": {"name": "cppulse.executor", "version": __version__},
            "argv": argv,
            "cwd": str(root),
            "status": "passed",
            "reason": "Synthetic contract fixture; this is not an execution claim.",
            "exit_code": 0,
            "signal": None,
            "started_at": "2026-11-13T10:00:00Z",
            "finished_at": "2026-11-13T10:00:01Z",
            "depends_on": [],
            "artifact_ids": [row["artifact_id"] for row in inputs]
            + ["native-report", "native-facts"],
            "log_artifact_ids": ["native-stdout", "native-stderr"],
        }
        raw = {
            "version": "2.0.0",
            "collector_version": "1.0.0",
            "receipt": deepcopy(receipt),
            "input_facts": facts,
            "input_after_facts": deepcopy(facts),
            "output_facts": [output_fact],
            "preexisting_output_facts": [],
            "executable_fact": {
                "path": "/synthetic/cppulse-analyzer",
                "sha256": "e" * 64,
                "size_bytes": 100,
                "stat": {"device": 1, "inode": 1, "mtime_ns": 1, "ctime_ns": 1},
            },
            "material_status": "available",
            "limitations": ["Synthetic metadata for pure transformation tests."],
            "stdout_bytes": 0,
            "stderr_bytes": 0,
            "captured_bytes": 0,
            "logs_truncated": False,
            "snapshot_limitations": [],
            "binding": {
                "status": "verified",
                "limitations": [],
                "input_artifacts": inputs,
                "output_artifacts": [
                    {
                        "path": report_path,
                        "artifact_id": "native-report",
                    }
                ],
                "log_artifacts": {"stdout": "native-stdout", "stderr": "native-stderr"},
            },
        }
        stage.write_json(
            "documents/plan.json",
            plan,
            contract="collection_plan",
            artifact_id="selected-plan",
        )
        stage.write_json(
            "documents/receipt.json",
            receipt,
            contract="execution_receipt",
            artifact_id="native-receipt",
        )
        if typed:
            stage.write_json(
                "documents/facts.json",
                raw,
                contract="execution_facts",
                artifact_id="native-facts",
            )
        else:
            write("debug.json", encoded(raw))
            stage.copy_artifact(
                "native-facts",
                root / "debug.json",
                "documents/facts.json",
                "application/json",
            )
        manifest = {
            "version": "2.0.0",
            "run_id": stage.run_id,
            "status": "partial",
            "source": source,
            "contexts": [context],
            "stages": [
                {
                    "id": "synthetic-native",
                    "status": "passed",
                    "depends_on": [],
                    "reason": "Synthetic transformation fixture, no commands.",
                },
                {
                    "id": "unattempted-build",
                    "status": "not_attempted",
                    "depends_on": [],
                    "reason": "Explicitly absent independent synthetic build.",
                },
            ],
            "artifacts": stage.artifacts,
            "started_at": "2026-11-13T10:00:00Z",
            "finished_at": "2026-11-13T10:00:02Z",
            "config_digest": digest_json(plan),
            "versions": {"cppulse": __version__},
            "limitations": ["Synthetic data; not actual native execution evidence."],
        }

        def check() -> None:
            assert not verify_inputs(root, source)

        snapshot = stage.publish(manifest, source_check=check if verified else None)
    args = {
        "receipt_id": "analyze",
        "report_artifact_id": "native-report",
        "registry_artifact_id": roles["rule-registry.json"],
        "config_artifact_id": roles["native-config.json"],
        "compilation_database_artifact_id": roles["compile_commands.json"],
        "resource_manifest_artifact_id": roles["resource-manifest.json"],
        "requested_files": ["main.cpp"],
        "requested_rules": ["CPP-MOD-001"],
    }
    return snapshot, args


def test_native_normalizer_uses_observed_arguments_and_distinct_parse_context(
    tmp_path: Path,
) -> None:
    from cppulse.analysis import normalize_native_analysis

    from test_measured_normalization import add_metrics

    snapshot, args = native_snapshot(tmp_path, mutate=add_metrics)
    result = normalize_native_analysis(snapshot, **args)
    row = result.inventory["items"][0]
    assert row["context_match"] == "matched"
    assert row["executed_rules"]
    assert row["parse_context_id"] != "native"
    assert result.derived_parse_contexts[0]["compiler"]["name"] == "libclang"
    assert result.derived_parse_contexts[0]["provenance"] == "observed"
    assert result.derived_parse_contexts[0]["argv"] == [
        "-working-directory=" + str(tmp_path),
        "--driver-mode=g++",
        "-std=c++17",
        "-resource-dir=" + str(tmp_path / "resources/clang"),
    ]
    assert result.observations["items"] == []


def test_uncontracted_debug_facts_are_not_upgraded(tmp_path: Path) -> None:
    from cppulse.analysis import normalize_native_analysis
    from cppulse.errors import ContractError

    snapshot, args = native_snapshot(tmp_path, typed=False)
    with pytest.raises(ContractError, match="typed|contract"):
        normalize_native_analysis(snapshot, **args)


def test_derived_analysis_preserves_parent_bytes_and_original_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess
    from cppulse.analysis import persist_native_analysis

    snapshot, args = native_snapshot(tmp_path)
    original = snapshot.manifest

    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Normalization must not launch commands")

    monkeypatch.setattr(subprocess, "run", forbidden)
    result = persist_native_analysis(
        snapshot, workspace=tmp_path, store=tmp_path / "store", **args
    )
    assert result.run_id != snapshot.run_id
    assert result.manifest["config_digest"] == original["config_digest"]
    assert result.manifest["contexts"][0] == original["contexts"][0]
    assert result.manifest["input_verification"] == "verified"
    for entry in original["artifacts"]:
        assert result.read_bytes(entry["id"]) == snapshot.read_bytes(entry["id"])
    assert len(documents(result, "analysis_inventory")) == 1
    assert (
        documents(result, "observations")[0]["analysis_inventory_id"]
        == documents(result, "analysis_inventory")[0]["id"]
    )
    assert any(
        entry.get("contract", {}).get("kind") == "resource_manifest"
        for entry in result.manifest["artifacts"]
    )


def _finding(
    report: dict[str, Any],
    root: Path,
    *,
    rule: str = "CPP-MOD-001",
    partial: bool = False,
    duplicate: bool = False,
) -> None:
    """Emit labeled synthetic native finding claims with consistent raw totals."""
    (root / "main.cpp").write_text("int main() { return (int)0.5; }\n")
    finding = {
        "rule_id": rule,
        "category": "modernization",
        "severity": "warning",
        "file": "main.cpp",
        "line": 1,
        "column": 1,
        "message": "Synthetic intentional modernization trigger",
    }
    report["findings"] = [finding, dict(finding)] if duplicate else [finding]
    count = len(report["findings"])
    report["summary"]["total_findings"] = count
    report["summary"]["by_category"]["modernization"] = count
    report["summary"]["by_severity"]["warning"] = count
    if partial:
        report["metadata"]["analysis"]["files"][0].update(
            status="partial", error_count=1
        )


def test_unobserved_registry_rule_version_cannot_relabel_current_tool(
    tmp_path: Path,
) -> None:
    import json
    from cppulse.analysis import normalize_native_analysis
    from cppulse.errors import ContractError

    def mutate(report: dict[str, Any], root: Path) -> None:
        _finding(report, root)
        data = json.loads((root / "rule-registry.json").read_text())
        next(rule for rule in data["rules"] if rule["id"] == "CPP-MOD-001")[
            "version"
        ] = "invented-version-999"
        (root / "rule-registry.json").write_text(json.dumps(data))

    snapshot, args = native_snapshot(tmp_path, mutate=mutate)
    with pytest.raises(ContractError, match="registry|version"):
        normalize_native_analysis(snapshot, **args)


def test_explicit_database_workspace_directory_is_supported(tmp_path: Path) -> None:
    from cppulse.analysis import normalize_native_analysis

    from test_measured_normalization import add_metrics

    snapshot, args = native_snapshot(
        tmp_path, database_directory=True, mutate=add_metrics
    )
    value = normalize_native_analysis(snapshot, **args)
    assert value.inventory["items"][0]["context_match"] == "matched"


@pytest.mark.parametrize("missing", ["parser", "parse_arguments", "working_directory"])
def test_legacy_native_report_without_observed_trace_is_not_positive(
    tmp_path: Path, missing: str
) -> None:
    from cppulse.analysis import normalize_native_analysis
    from cppulse.errors import ContractError

    def mutate(report: dict[str, Any], root: Path) -> None:
        if missing == "parser":
            report["metadata"]["analysis"].pop("parser")
        else:
            report["metadata"]["analysis"]["files"][0].pop(missing)

    snapshot, args = native_snapshot(tmp_path, mutate=mutate)
    with pytest.raises(ContractError, match="trace|parse"):
        normalize_native_analysis(snapshot, **args)


def test_unverified_parent_source_cannot_be_upgraded(tmp_path: Path) -> None:
    from cppulse.analysis import normalize_native_analysis
    from cppulse.errors import ContractError

    snapshot, args = native_snapshot(tmp_path, verified=False)
    with pytest.raises(ContractError, match="source-verified"):
        normalize_native_analysis(snapshot, **args)


def test_native_tool_hash_must_match_coarse_job_declaration(tmp_path: Path) -> None:
    from cppulse.analysis import normalize_native_analysis
    from cppulse.errors import ContractError

    snapshot, args = native_snapshot(tmp_path, job_tool_sha="f" * 64)
    with pytest.raises(ContractError, match="job hash"):
        normalize_native_analysis(snapshot, **args)


def test_partial_ast_keeps_known_findings_without_completed_rule_claim(
    tmp_path: Path,
) -> None:
    from cppulse.analysis import normalize_native_analysis

    from test_measured_normalization import add_metrics

    def current_partial(report: dict[str, Any], root: Path) -> None:
        _finding(report, root, partial=True)
        add_metrics(report, root)
        report["metadata"]["analysis"]["native_metrics"]["files"][0].update(
            status="partial",
            error_count=1,
            measurement_complete=False,
            function_count=None,
        )

    snapshot, args = native_snapshot(tmp_path, mutate=current_partial)
    value = normalize_native_analysis(snapshot, **args)
    row = value.inventory["items"][0]
    assert row["status"] == "partial" and row["context_match"] == "matched"
    assert row["executed_rules"] == [] and row["finding_count"] == 1
    assert len(value.observations["items"]) == 1


def test_disabled_requested_rule_has_no_completed_zero_proof(tmp_path: Path) -> None:
    import json
    from cppulse.analysis import normalize_native_analysis

    def mutate(report: dict[str, Any], root: Path) -> None:
        config = json.loads((root / "native-config.json").read_text())
        config["rules"]["CPP-MOD-001"] = {"enabled": False}
        (root / "native-config.json").write_text(json.dumps(config))
        report["metadata"]["analysis"]["enabled_rules"].remove("CPP-MOD-001")
        from test_measured_normalization import add_metrics

        add_metrics(report, root)

    snapshot, args = native_snapshot(tmp_path, mutate=mutate)
    value = normalize_native_analysis(snapshot, **args)
    row = value.inventory["items"][0]
    assert row["context_match"] == "matched" and row["status"] == "analyzed"
    assert "CPP-MOD-001" not in row["executed_rules"]


def test_enabled_nonrequested_findings_are_preserved_for_requested_files(
    tmp_path: Path,
) -> None:
    from cppulse.analysis import normalize_native_analysis

    snapshot, args = native_snapshot(
        tmp_path, mutate=lambda report, root: _finding(report, root, rule="CPP-MOD-009")
    )
    value = normalize_native_analysis(snapshot, **args)
    assert value.inventory["requested_rules"] == ["CPP-MOD-001"]
    assert value.inventory["items"][0]["finding_count"] == 1
    assert value.observations["items"][0]["rule_id"] == "CPP-MOD-009"


def test_repeated_findings_and_cross_job_occurrences_are_not_deduplicated(
    tmp_path: Path,
) -> None:
    from cppulse.analysis import normalize_native_analysis

    def mutate(report: dict[str, Any], root: Path) -> None:
        _finding(report, root, duplicate=True)

    first, args = native_snapshot(tmp_path, mutate=mutate, job="first-job")
    one = normalize_native_analysis(first, **args)
    second, args = native_snapshot(tmp_path, mutate=mutate, job="second-job")
    two = normalize_native_analysis(second, **args)
    first_rows, second_rows = one.observations["items"], two.observations["items"]
    assert len(first_rows) == len(second_rows) == 2
    assert len({row["fingerprint"] for row in first_rows + second_rows}) == 1
    assert len({row["id"] for row in first_rows + second_rows}) == 4
    assert one.derived_parse_contexts == two.derived_parse_contexts


def test_ambiguous_database_variants_do_not_become_strict_matches(
    tmp_path: Path,
) -> None:
    import json
    from cppulse.analysis import normalize_native_analysis

    def mutate(report: dict[str, Any], root: Path) -> None:
        commands = json.loads((root / "compile_commands.json").read_text())
        commands.append(
            {**commands[0], "arguments": commands[0]["arguments"] + ["-DOTHER=1"]}
        )
        (root / "compile_commands.json").write_text(json.dumps(commands))

    snapshot, args = native_snapshot(tmp_path, mutate=mutate)
    assert (
        normalize_native_analysis(snapshot, **args).inventory["items"][0][
            "context_match"
        ]
        == "unverified"
    )


@pytest.mark.parametrize(
    "role", ["compilation_database_artifact_id", "resource_manifest_artifact_id"]
)
def test_unselected_context_roles_remain_unverified(tmp_path: Path, role: str) -> None:
    from cppulse.analysis import normalize_native_analysis

    snapshot, args = native_snapshot(tmp_path)
    args[role] = None
    value = normalize_native_analysis(snapshot, **args)
    assert value.inventory["items"][0]["context_match"] == "unverified"


def test_exact_duplicate_parse_flags_are_not_reconstructed_or_collapsed(
    tmp_path: Path,
) -> None:
    from cppulse.analysis import normalize_native_analysis

    def mutate(report: dict[str, Any], root: Path) -> None:
        report["metadata"]["analysis"]["files"][0]["parse_arguments"][2:2] = [
            "-DVALUE=7",
            "-DVALUE=7",
        ]

    snapshot, args = native_snapshot(tmp_path, mutate=mutate)
    value = normalize_native_analysis(snapshot, **args)
    assert value.derived_parse_contexts[0]["argv"].count("-DVALUE=7") == 2
    assert "--driver-mode=g++" in value.derived_parse_contexts[0]["argv"]


def test_unknown_active_file_is_rejected_but_excluded_generated_file_stays_raw(
    tmp_path: Path,
) -> None:
    from copy import deepcopy
    from cppulse.analysis import normalize_native_analysis
    from cppulse.errors import ContractError

    def active(report: dict[str, Any], root: Path) -> None:
        extra = deepcopy(report["metadata"]["analysis"]["files"][0])
        extra["path"] = str(root / "unlisted.cpp")
        report["metadata"]["analysis"]["files"].append(extra)

    snapshot, args = native_snapshot(tmp_path / "active", mutate=active)
    with pytest.raises(ContractError, match="outside selected source"):
        normalize_native_analysis(snapshot, **args)

    def excluded(report: dict[str, Any], root: Path) -> None:
        report["metadata"]["analysis"]["files"].append(
            {
                "path": str(root / "build/generated.cpp"),
                "status": "excluded",
                "compile_context": "none",
                "error_count": 0,
                "parse_arguments": None,
                "working_directory": None,
            }
        )

    snapshot, args = native_snapshot(tmp_path / "excluded", mutate=excluded)
    value = normalize_native_analysis(snapshot, **args)
    assert [row["file"] for row in value.inventory["items"]] == ["main.cpp"]
    assert len(value.derived_parse_contexts) == 1


@pytest.mark.parametrize("status", ["failed", "skipped", "excluded", "missing"])
def test_incomplete_requested_file_never_claims_completed_rules(
    tmp_path: Path, status: str
) -> None:
    from cppulse.analysis import normalize_native_analysis

    def mutate(report: dict[str, Any], root: Path) -> None:
        report["metadata"].update(file_count=0, total_loc=0)
        if status == "missing":
            report["metadata"]["analysis"]["files"] = []
        else:
            row = report["metadata"]["analysis"]["files"][0]
            row["status"] = status
            if status != "failed":
                row.update(
                    compile_context="none", parse_arguments=None, working_directory=None
                )

    snapshot, args = native_snapshot(tmp_path, mutate=mutate)
    value = normalize_native_analysis(snapshot, **args)
    assert value.inventory["items"][0]["status"] == status
    assert value.inventory["items"][0]["executed_rules"] == []
    assert value.observations["items"] == []


@pytest.mark.parametrize("origin", ["inferred", "fallback"])
def test_non_database_origin_preserves_actual_trace_but_not_strict_match(
    tmp_path: Path, origin: str
) -> None:
    import json
    from cppulse.analysis import normalize_native_analysis

    def mutate(report: dict[str, Any], root: Path) -> None:
        report["metadata"]["analysis"]["files"][0]["compile_context"] = origin
        commands = (
            []
            if origin == "fallback"
            else [
                {
                    "directory": str(root),
                    "file": "other.cpp",
                    "arguments": ["/synthetic/g++", "-c", "other.cpp"],
                }
            ]
        )
        (root / "compile_commands.json").write_text(json.dumps(commands))

    snapshot, args = native_snapshot(tmp_path, mutate=mutate)
    value = normalize_native_analysis(snapshot, **args)
    assert value.inventory["items"][0]["context_match"] == "unverified"
    assert value.derived_parse_contexts[0]["provenance"] == "observed"


def test_source_changed_before_enrichment_leaves_parent_and_latest_attempt(
    tmp_path: Path,
) -> None:
    from cppulse.analysis import persist_native_analysis
    from cppulse.errors import InputChanged
    from cppulse.run_store import RunStore

    snapshot, args = native_snapshot(tmp_path)
    (tmp_path / "main.cpp").write_text("changed after collection\n")
    with pytest.raises(InputChanged, match="before derived publication"):
        persist_native_analysis(
            snapshot, workspace=tmp_path, store=tmp_path / "store", **args
        )
    assert (
        RunStore(tmp_path / "store").resolve_latest_attempt().run_id == snapshot.run_id
    )
