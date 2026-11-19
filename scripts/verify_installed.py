"""Exercise real wheel/native artifacts outside the checkout with core deps only."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import Any


def verify(
    wheel: Path,
    native_prefix: Path,
    wheelhouse: Path,
    evidence: Path,
    *,
    real_repo: Path | None = None,
    compilation_database: Path | None = None,
    policy_demo: Path | None = None,
    policy_fixture: Path | None = None,
    host_tool_library_path: Path | None = None,
) -> dict[str, Any]:
    """Install from local files and retain exact command/output evidence."""
    if (policy_demo is None) != (policy_fixture is None):
        raise ValueError("Policy verification requires both driver and fixture")
    if host_tool_library_path is not None:
        if policy_demo is None or not host_tool_library_path.is_dir():
            raise ValueError(
                "Host tool libraries require an existing directory and explicit policy proof"
            )
    if policy_demo is not None:
        if not policy_demo.is_file() or not policy_fixture.is_dir():
            raise ValueError("Explicit policy driver/fixture is unavailable")
        if any(path.is_symlink() for path in policy_fixture.rglob("*")):
            raise ValueError("Policy fixture must contain plain selected inputs")
    wheel_sha256 = hashlib.sha256(wheel.read_bytes()).hexdigest()
    evidence = evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    for key in (
        "PYTHONPATH",
        "LD_LIBRARY_PATH",
        "DYLD_LIBRARY_PATH",
        "LIBCLANG_ROOT",
        "CMAKE_PREFIX_PATH",
        "CPPULSE_ANALYZER",
        "CPPULSE_CLANG_RESOURCE_DIR",
        "CPPULSE_NATIVE_PREFIX",
    ):
        environment.pop(key, None)
    transcript: list[dict[str, Any]] = []

    def run(
        argv: list[str], *, expected: int = 0, env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            argv,
            cwd=evidence,
            env=env or environment,
            text=True,
            capture_output=True,
            timeout=300,
            shell=False,
            check=False,
        )
        entry = {
            "argv": argv,
            "returncode": result.returncode,
            "expected": expected,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        transcript.append(entry)
        (evidence / "transcript.json").write_text(
            json.dumps(transcript, indent=2), encoding="utf-8"
        )
        if result.returncode != expected:
            raise AssertionError(
                f"Installed check failed ({result.returncode}, expected {expected}): {argv}\n{result.stdout}\n{result.stderr}"
            )
        return result

    venv = evidence / "core-venv"
    run([sys.executable, "-m", "venv", str(venv)])
    python = str(venv / "bin/python")
    run(
        [
            python,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheelhouse.resolve()),
            str(wheel.resolve()),
        ]
    )
    relocated = evidence / "relocated native with spaces"
    shutil.copytree(native_prefix, relocated)
    environment["CPPULSE_NATIVE_PREFIX"] = str(relocated)
    # Only explicitly needed executables are visible during the runtime proof.
    # A failed proxy also catches accidental ordinary HTTP download attempts.
    helpers = evidence / "runtime-bin"
    helpers.mkdir()
    environment["PATH"] = str(venv / "bin") + os.pathsep + str(helpers)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        environment[name] = "http://127.0.0.1:9"
    environment["NO_PROXY"] = ""
    environment["no_proxy"] = ""
    origin = run(
        [
            python,
            "-c",
            "import cppulse,json,sys,importlib.util,shutil,jsonschema; from cppulse.contracts import load_schema; from importlib import resources; from pathlib import Path; p=Path(cppulse.__file__); assert 'site-packages' in p.parts; missing=['git','xgboost','sklearn','shap','weasyprint','matplotlib','fastapi','uvicorn']; assert all(importlib.util.find_spec(x) is None for x in missing); assert shutil.which('node') is None; assert shutil.which('git') is None; n=0\nfor group in ['v2','prototype_v1','legacy','install_v1']:\n for f in resources.files('cppulse.contracts').joinpath('schemas',group).iterdir():\n  if f.name.endswith('.json'): jsonschema.Draft7Validator.check_schema(json.loads(f.read_bytes())); n+=1\nprint(json.dumps({'origin':str(p),'schemas':n,'optional_absent':missing,'node_visible':False,'git_visible':False}))",
        ]
    )
    cli = str(venv / "bin/cppulse")
    doctor = json.loads(run([cli, "doctor"]).stdout)
    if not doctor["native"]["available"]:
        raise AssertionError("Installed native startup unavailable")
    target = evidence / "sample repo's literal $(touch forbidden)"
    target.mkdir()
    (target / "clean.cpp").write_text(
        "#include <string>\n#include <vector>\nint count(const std::string& s) { const std::vector<int> v{1}; return static_cast<int>(s.size() + v.size()); }\n",
        encoding="utf-8",
    )
    (target / "intentional.cpp").write_text(
        "int legacy() { int* value = new int(2); int n = (int)3.2; delete value; return n; }\n",
        encoding="utf-8",
    )
    (target / "CMakeLists.txt").write_text(
        "execute_process(COMMAND touch forbidden-project-execution)\n", encoding="utf-8"
    )
    run([cli, "init", "--repo", str(target)])
    config = json.loads(run([cli, "config", "--repo", str(target)]).stdout)
    output = evidence / "analysis output's $(touch forbidden)"
    analysis = json.loads(
        run(
            [
                cli,
                "analyze",
                "--repo",
                str(target),
                "--output",
                str(output),
                "--format",
                "html",
            ]
        ).stdout
    )
    risk = json.loads((output / "risk_scores.json").read_bytes())
    findings = json.loads((output / "findings.json").read_bytes())
    if risk["metadata"]["model_type"] != "heuristic":
        raise AssertionError(
            "Core-only installation did not use explicit heuristic mode"
        )
    if findings["summary"]["total_findings"] < 1:
        raise AssertionError("Intentional rule triggers did not produce findings")
    if findings["summary"]["total_findings"] != len(findings["findings"]):
        raise AssertionError("Finding summary disagrees with actual records")
    for field, key in [("by_category", "category"), ("by_severity", "severity")]:
        actual = Counter(item[key] for item in findings["findings"])
        declared = {
            name: value for name, value in findings["summary"][field].items() if value
        }
        if dict(actual) != declared:
            raise AssertionError(f"Finding totals disagree: {field}")
    if any(Path(item["file"]).name == "clean.cpp" for item in findings["findings"]):
        raise AssertionError("Clean counterexample has findings")
    ranked = {row["file"] for row in risk["file_risks"]}
    unranked = {row["file"] for row in risk.get("unranked_files", [])}
    if ranked & unranked or ranked | unranked != {"clean.cpp", "intentional.cpp"}:
        raise AssertionError(
            "Current risk universe or relative file identities disagree"
        )
    history = json.loads((output / "git_metrics.json").read_bytes())
    if (
        history["metadata"]["history_status"] != "unavailable"
        or history["file_metrics"]
    ):
        raise AssertionError("Absent Git tooling manufactured available file history")
    if ranked or any(
        "missing_history" not in row["reason_codes"] for row in risk["unranked_files"]
    ):
        raise AssertionError("Absent history was converted into ranked predictions")
    if any(row["file"] == "clean.cpp" for row in risk["hotspots"]):
        raise AssertionError("Clean input is incorrectly labeled a hotspot")
    inventory = findings["metadata"]["analysis"]["files"]
    if len(inventory) != 2 or any(row["status"] != "analyzed" for row in inventory):
        raise AssertionError("Selected core example has incomplete analysis scope")
    weights = {"memory_safety": 3, "complexity": 1.5, "modernization": 1}
    expected_health = max(
        0,
        100 - sum(weights.get(row["category"], 0) for row in findings["findings"]) / 2,
    )
    if risk["health_score"]["overall"] != expected_health:
        raise AssertionError("Independent weighted health total disagrees")
    if (target / "forbidden-project-execution").exists() or (
        evidence / "forbidden"
    ).exists():
        raise AssertionError("A shell expression or project build command was executed")
    html = (output / "report.html").read_text(encoding="utf-8")
    if "<style>" not in html or len(html) < 2000:
        raise AssertionError("Installed HTML template/CSS resources missing")
    run([cli, "report", "--input", str(output), "--format", "json"])
    pdf_missing = run(
        [cli, "report", "--input", str(output), "--format", "pdf"], expected=2
    )
    if "cppulse[pdf]" not in pdf_missing.stderr:
        raise AssertionError("Missing PDF dependency error is not actionable")
    web_missing = run([cli, "serve", "--input", str(output)], expected=2)
    if "cppulse[web]" not in web_missing.stderr:
        raise AssertionError("Missing web dependency error is not actionable")
    run([cli, "diagnostics", "--output", str(evidence / "diagnostics.zip")])
    real_result = None
    if real_repo is not None:
        if compilation_database is None:
            raise ValueError(
                "Real consumer verification requires an explicit compilation database"
            )
        real_output = evidence / "real-consumer-output"
        real_result = json.loads(
            run(
                [
                    cli,
                    "analyze",
                    "--repo",
                    str(real_repo.resolve()),
                    "--compilation-database",
                    str(compilation_database.resolve()),
                    "--output",
                    str(real_output),
                    "--format",
                    "html",
                ]
            ).stdout
        )
        actual = json.loads((real_output / "findings.json").read_bytes())
        files = actual["metadata"]["analysis"]["files"]
        if (
            len(files) != 1
            or files[0]["status"] != "analyzed"
            or files[0]["compile_context"] != "database"
        ):
            raise AssertionError(
                "Installed real consumer did not parse in its exact compilation context"
            )
    policy_result = None
    if policy_demo is not None:
        # Only this opt-in proof executes the explicitly selected CMake fixture.
        # Earlier static checks retain a PATH without any Git executable.
        required_tools = ("cmake", "ctest", "g++", "make", "as", "ld", "ar")
        selected_tools = {name: shutil.which(name) for name in required_tools}
        missing_tools = [name for name, path in selected_tools.items() if not path]
        if missing_tools:
            raise RuntimeError(f"Policy fixture tools unavailable: {missing_tools}")
        for name, selected in selected_tools.items():
            actual_tool = Path(selected).resolve(strict=True)
            if host_tool_library_path is not None and name in {"cmake", "ctest"}:
                # The cloud's separately extracted CMake tools have their own
                # loader dependencies. Scope that override to these explicit
                # launchers; native analyzer/Python discovery remains clean.
                launcher = helpers / name
                launcher.write_text(
                    "#!/bin/sh\nLD_LIBRARY_PATH="
                    + shlex.quote(str(host_tool_library_path.resolve(strict=True)))
                    + " exec "
                    + shlex.quote(str(actual_tool))
                    + ' "$@"\n',
                    encoding="utf-8",
                )
                launcher.chmod(0o755)
            else:
                (helpers / name).symlink_to(actual_tool)
        for name in ("gcc", "cc", "c++", "ranlib", "nm", "strip"):
            selected = shutil.which(name)
            if selected:
                (helpers / name).symlink_to(Path(selected).resolve(strict=True))
        copied_driver = evidence / "policy-driver.py"
        copied_fixture = evidence / "policy-fixture"
        shutil.copy2(policy_demo, copied_driver)
        shutil.copytree(policy_fixture, copied_fixture)
        module_proof = json.loads(
            run(
                [
                    python,
                    "-c",
                    "import json,sys,cppulse,cppulse.collection,cppulse.analysis,cppulse.policy; "
                    "from pathlib import Path; modules=[cppulse,cppulse.collection,cppulse.analysis,cppulse.policy]; "
                    "paths={m.__name__:str(Path(m.__file__).resolve()) for m in modules}; "
                    "assert all(Path(p).is_relative_to(Path(sys.prefix).resolve()) for p in paths.values()); "
                    "print(json.dumps({'modules':paths,'sys_path':sys.path}))",
                ]
            ).stdout
        )
        policy_output = evidence / "policy-demo-output"
        run(
            [
                python,
                str(copied_driver),
                "--fixture",
                str(copied_fixture),
                "--analyzer",
                doctor["native"]["path"],
                "--resource-dir",
                doctor["native"]["resource_dir"],
                "--output",
                str(policy_output),
                "--scenario",
                "all",
            ]
        )
        policy_result = {
            "module_proof": module_proof,
            "explicit_fixture_tools": selected_tools,
            "host_tool_library_path": (
                str(host_tool_library_path.resolve(strict=True))
                if host_tool_library_path is not None
                else None
            ),
            "driver": str(copied_driver),
            "fixture": str(copied_fixture),
            "summary": json.loads((policy_output / "latest-demo.json").read_bytes()),
            "limitations": [
                "Explicit synthetic CMake/CTest/native recipe, not a benchmark or general verification claim.",
                "The original checkout was present but absent from Python import paths; source hiding is a separate proof.",
                "Optional CMake/CTest launchers scope their explicit loader path to those tools and descendants; they do not qualify a self-contained host compiler/runtime closure.",
            ],
        }
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != wheel_sha256:
        raise AssertionError("Wheel bytes changed during installed verification")
    manifest = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "wheel": str(wheel.resolve()),
        "wheel_sha256": wheel_sha256,
        "verification_script_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "native_prefix": str(relocated),
        "core_import": json.loads(origin.stdout),
        "doctor": doctor,
        "effective_config": config,
        "analysis": analysis,
        "real_consumer_analysis": real_result,
        "policy_demo": policy_result,
        "findings": findings["summary"],
        "runtime_network": "No runtime setup/download required; ordinary proxy directed at a closed local port. This is not a network sandbox.",
        "limitations": [
            "Selected local synthetic input, not detector accuracy or universal platform qualification.",
            "Host compiler headers/libclang/LLVM/runtime remain installed requirements.",
        ],
    }
    (evidence / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    """Verify explicit locally built artifacts; never download or publish them."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--native-prefix", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--real-repo", type=Path)
    parser.add_argument("--compilation-database", type=Path)
    parser.add_argument("--policy-demo", type=Path)
    parser.add_argument("--policy-fixture", type=Path)
    parser.add_argument("--host-tool-library-path", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            verify(
                args.wheel,
                args.native_prefix,
                args.wheelhouse,
                args.evidence,
                real_repo=args.real_repo,
                compilation_database=args.compilation_database,
                policy_demo=args.policy_demo,
                policy_fixture=args.policy_fixture,
                host_tool_library_path=args.host_tool_library_path,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
