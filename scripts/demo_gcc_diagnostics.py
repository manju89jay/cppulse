"""Collect actual GNU diagnostics and import their attributed raw reports locally."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any
from uuid import uuid4

from cppulse.collection import collect
from cppulse.external import normalize_gcc_import, persist_gcc_import
from cppulse.identities import context_identity, hash_artifact, snapshot_inputs
from cppulse.run_store import RunStore

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: Any) -> None:
    """Replace one demo summary only after its complete JSON is written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    pending.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    pending.replace(path)


def main() -> None:
    """Run explicit compiler commands; keep imported findings separate from proof."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "output/gcc-diagnostics-demo"
    )
    parser.add_argument("--fixture", type=Path, default=ROOT / "demo/gcc-diagnostics")
    parser.add_argument("--compiler", default="g++")
    args = parser.parse_args()
    compiler = shutil.which(args.compiler)
    if compiler is None:
        raise RuntimeError("Selected GNU C++ compiler is unavailable")
    compiler = str(Path(compiler).resolve(strict=True))
    inspect = [compiler, "-dumpfullversion", "-dumpversion"]
    version = subprocess.check_output(inspect, text=True, timeout=10).strip()
    target_probe = [compiler, "-dumpmachine"]
    target = subprocess.check_output(target_probe, text=True, timeout=10).strip()
    output = args.output.resolve()
    batch = output / "batches" / uuid4().hex
    workspace = batch / "workspace"
    shutil.copytree(args.fixture.resolve(strict=True), workspace)
    compiler_sha = hash_artifact(
        compiler, "compiler", "compiler", "application/octet-stream"
    )["sha256"]
    base = [
        compiler,
        "-std=c++17",
        "-Wall",
        "-Wextra",
        "-fsyntax-only",
        "-fdiagnostics-format=json",
        "-fdiagnostics-column-unit=byte",
        "-fdiagnostics-column-origin=1",
    ]
    modes = {
        "warning": ["-DCPPULSE_DEMO_GCC_WARNING=1"],
        "clean": [],
        "error": ["-DCPPULSE_DEMO_GCC_ERROR=1"],
    }
    contexts = []
    steps = []
    for name, switches in modes.items():
        argv = [*base, *switches, str(workspace / "fixture.cpp")]
        context = "gcc-json-" + name
        contexts.append(
            context_identity(
                {
                    "id": context,
                    "compiler": {
                        "name": "GNU-G++",
                        "version": version,
                        "sha256": compiler_sha,
                    },
                    "argv": argv,
                    "working_directory": str(workspace),
                    "language_standard": "c++17",
                    "target": target,
                    "provenance": "inferred",
                    "dependencies": [],
                    "limitations": [
                        "Selected coarse diagnostic job; actual compiler argv and byte identity are retained in individual receipts. Imported diagnostics do not assert completed analysis."
                    ],
                }
            )
        )
        for suffix, command, dependencies, inputs, outputs in [
            ("version", inspect, [], [], []),
            ("diagnostics", argv, [name + "-version"], ["fixture.cpp"], []),
        ]:
            steps.append(
                {
                    "id": name + "-" + suffix,
                    "context_id": context,
                    "argv": command,
                    "cwd": ".",
                    "depends_on": dependencies,
                    "inputs": inputs,
                    "outputs": outputs,
                    "timeout_seconds": 30,
                }
            )
    steps.append(
        {
            "id": "clean-build",
            "context_id": "gcc-json-clean",
            "argv": [compiler, "-std=c++17", "fixture.cpp", "-o", "clean-consumer"],
            "cwd": ".",
            "depends_on": ["clean-version"],
            "inputs": ["fixture.cpp"],
            "outputs": ["clean-consumer"],
            "timeout_seconds": 30,
        }
    )
    plan = {
        "version": "2.0.0",
        "id": "synthetic-gcc-diagnostics",
        "recipe": {
            "version": "2.0.0",
            "id": "explicit-gcc-diagnostics",
            "jobs": 3,
            "contexts": [c["id"] for c in contexts],
            "steps": steps,
        },
        "bindings": [
            {
                "id": "clean-consumer-build",
                "step_id": "clean-build",
                "kind": "build",
                "scope_files": ["fixture.cpp"],
                "exercised_inputs": ["clean-consumer"],
                "report_path": None,
                "execution_log_path": None,
                "adapter": None,
                "adapter_version": None,
                "inventory_step_id": None,
                "producer_version_step_id": None,
            }
        ],
        "limits": {
            "max_log_bytes": 1048576,
            "max_artifact_bytes": 67108864,
            "max_metadata_bytes": 16777216,
            "termination_grace_seconds": 1,
        },
    }
    source = snapshot_inputs(
        workspace,
        ["fixture.cpp", "README.md"],
        kind="application",
        inventory_complete=True,
    )
    write_json(
        batch / "tools.json",
        {
            "inspection_commands": [inspect, target_probe],
            "version": version,
            "target": target,
            "compiler_sha256": compiler_sha,
        },
    )
    write_json(batch / "plan.json", plan)
    store = RunStore(output / "store")
    raw = collect(
        plan, workspace=workspace, source=source, contexts=contexts, store=store
    )
    raw.verify()
    facts = {
        d["receipt"]["id"]: d
        for a in raw.manifest["artifacts"]
        if a.get("contract", {}).get("kind") == "execution_facts"
        for d in [raw.read_json(a["id"])]
    }
    derived = raw
    imported = []
    for name in modes:
        fact = facts[name + "-diagnostics"]
        observed = fact["receipt"]
        expected = "failed" if name == "error" else "passed"
        if observed["status"] != expected:
            raise AssertionError(
                f"Actual compiler mode {name} is {observed['status']}, expected {expected}; inspect {raw.path}"
            )
        artifact = fact["binding"]["log_artifacts"]["stderr"]
        selection = {
            "report_artifact_id": artifact,
            "context_id": "gcc-json-" + name,
            "source_root": str(workspace),
            "scope_files": ["fixture.cpp"],
            "producer": {"name": "GNU-G++", "version": version},
        }
        document = normalize_gcc_import(derived, **selection)
        if (
            document["usability"] != "usable"
            or document["scope_completeness"] != "unverified"
        ):
            raise AssertionError(f"Actual GNU report unavailable: {document}")
        expected_count = 0 if name == "clean" else 1
        if len(document["observations"]) != expected_count:
            raise AssertionError(
                f"Actual diagnostic count differs for {name}: {document}"
            )
        derived = persist_gcc_import(
            derived, workspace=workspace, store=store, **selection
        )
        derived.verify()
        imported.append(
            {
                "mode": name,
                "compiler_status": observed["status"],
                "diagnostic_count": len(document["observations"]),
                "report_artifact_id": artifact,
                "fact_id": document["id"],
                "origin": document["origin"],
                "scope_completeness": document["scope_completeness"],
                "derived_run_id": derived.run_id,
                "derived_manifest_sha256": derived.manifest_sha256,
            }
        )
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "batch": str(batch),
        "store": str(store.root),
        "raw_run_id": raw.run_id,
        "raw_manifest_sha256": raw.manifest_sha256,
        "imports": imported,
        "limitations": [
            "Synthetic compiler diagnostics, not an accuracy benchmark. Only the separate clean consumer was built; no executable was run.",
            "All GNU diagnostic facts stay imported and scan completeness stays unverified, even for an empty array. Native finding policy and totals are not merged.",
        ],
    }
    write_json(batch / "summary.json", summary)
    write_json(output / "latest-demo.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
