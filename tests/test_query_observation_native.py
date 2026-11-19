"""Actual selected native query controls; requirements remain cache-unqualified."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from cppulse.query_observation import collect_query_observation, validate_query_report


def pin(path: Path) -> dict:
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "size_bytes": path.stat().st_size,
    }


@pytest.mark.parametrize("kind", ["search", "query"])
def test_actual_negative_path_becomes_different_ast_without_source_edit(
    tmp_path: Path, kind: str
) -> None:
    root = Path(__file__).resolve().parents[1]
    native = Path(
        os.environ.get(
            "CPPULSE_WORK_UNIT_NATIVE",
            str(
                root
                / "work/native-include-buffer-candidate/9004df27f73a73901e3c231834628c24009ffded1730e598754acd6e7c7a6373/cppulse-analyzer"
            ),
        )
    )
    sdk = Path(
        os.environ.get(
            "CPPULSE_CLANG_RESOURCE_DIR",
            str(root / "work/native-deps/usr/lib/llvm-19/lib/clang/19"),
        )
    )
    source = tmp_path / "source"
    source.mkdir()
    first = tmp_path / "external-first"
    second = tmp_path / "external-second"
    first.mkdir()
    second.mkdir()
    old = second / "config.h"
    old.write_text("#define FLAG 0\n")
    target = first / ("config.h" if kind == "search" else "flag.h")
    text = (
        "#include <config.h>\n#if FLAG\n"
        if kind == "search"
        else '#if __has_include("' + str(target) + '")\n'
    )
    main = source / "main.cpp"
    main.write_text(
        text
        + "int f(int x){if(x)return 1;return 0;}\n#else\nint f(int x){return x;}\n#endif\n"
    )
    original, oldsha = pin(main)["sha256"], pin(old)["sha256"]
    database = source / "compile_commands.json"
    database.write_text(
        json.dumps(
            [
                {
                    "directory": str(source),
                    "file": str(main),
                    "arguments": [
                        "clang++",
                        "-std=c++17",
                        "-I" + str(first),
                        "-I" + str(second),
                        "-c",
                        str(main),
                    ],
                }
            ]
        )
    )
    values = []
    for state in ("absent", "present"):
        if state == "present":
            target.write_text("#define FLAG 1\n")
        output = tmp_path / state
        argv = [
            str(native),
            "--repo",
            str(source),
            "--compilation-database",
            str(database),
            "--resource-dir",
            str(sdk),
            "--output",
            str(output / "native"),
            "--file-size-bytes",
            "8388608",
        ]
        environment = {
            "PATH": "/usr/bin:/bin",
            "LC_ALL": "C",
            "CPPULSE_CLANG_RESOURCE_DIR": str(sdk),
        }
        if os.environ.get("LD_LIBRARY_PATH"):
            environment["LD_LIBRARY_PATH"] = os.environ["LD_LIBRARY_PATH"]
        request = {
            "version": "0.1.0",
            "source_digest": original,
            "context_id": "descriptive-" + kind,
            "native": pin(native),
            "tracer": {
                **pin(Path("/usr/bin/strace")),
                "version": "strace -- version 6.13",
            },
            "invocation": {
                "argv": argv,
                "cwd": str(source),
                "environment": environment,
            },
            "native_report_relative_path": "native/findings.json",
            "limits": {
                "wall_seconds": 30,
                "max_trace_bytes": 1048576,
                "max_stdout_bytes": 65536,
                "max_events": 2000,
                "max_processes": 16,
                "max_line_bytes": 65536,
            },
        }
        report = collect_query_observation(request, output, execute_selected_tools=True)
        validate_query_report(request, report, output)
        raw = json.loads((output / "native/findings.json").read_bytes())
        metric = raw["metadata"]["analysis"]["native_metrics"]["files"][0]
        values.append(
            [function["cyclomatic_complexity"] for function in metric["functions"]]
        )
        selected = [
            event
            for event in report["parsed"]["events"]
            if event["path"] == str(target)
        ]
        assert (
            selected
            and report["cache_eligible"] is False
            and report["closure"] == "unqualified"
        )
        assert report["native_parser"]["name"] == "libclang"
        if state == "absent":
            assert any(event["errno"] == "ENOENT" for event in selected)
        else:
            assert any(event["errno"] is None for event in selected)
        assert pin(main)["sha256"] == original and pin(old)["sha256"] == oldsha
    assert values == [[1], [2]]
