"""Exercise the native executable and validate actual reports, not hand-shaped JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from cppulse.contracts import validate


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analyzer", required=True, type=Path)
    parser.add_argument("--resource-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for label, newline in [
        ("lf", "\n"),
        ("cr", "\r"),
        ("crlf", "\r\n"),
        ("lfcr", "\n\r"),
    ]:
        for terminal in [False, True]:
            name = f"{label}-terminal-{terminal}"
            root = args.output / name / "repo"
            root.mkdir(parents=True, exist_ok=True)
            content = (
                "// comment"
                + newline
                + newline
                + "int value() {"
                + newline
                + "    return 1;"
                + newline
                + "}"
                + (newline if terminal else "")
            ).encode()
            (root / "source.cpp").write_bytes(content)
            output = root.parent / "output"
            run = subprocess.run(
                [
                    str(args.analyzer.resolve()),
                    "--repo",
                    str(root.resolve()),
                    "--output",
                    str(output.resolve()),
                    "--resource-dir",
                    str(args.resource_dir.resolve()),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            (root.parent / "execution.log").write_text(run.stdout + run.stderr)
            report = json.loads((output / "findings.json").read_text())
            validate("findings", report, version="prototype_v1")
            raw = report["metadata"]["analysis"]["native_metrics"]
            assert len(raw["files"]) == 1
            item = raw["files"][0]
            expected = len(re.findall(rb"\r\n|\r|\n", content)) + (
                content[-1:] not in [b"\r", b"\n"]
            )
            assert item["physical_loc"] == expected == report["metadata"]["total_loc"]
            assert item["code_loc"] == 3
            assert item["measurement_complete"] is True
            assert item["source_content_sha256"] == hashlib.sha256(content).hexdigest()
            assert item["function_count"] == len(item["functions"]) == 1
            function = item["functions"][0]
            assert function["function_length"] == (5 if label == "lfcr" else 3)
            assert function["cyclomatic_complexity"] == 1
            assert function["nesting_depth"] == 0
            assert function["parameter_count"] == 0
            tokens = item["token_stream"]
            assert tokens["complete"] is True
            assert (
                tokens["retained_tokens"]
                == tokens["total_tokens"]
                == len(tokens["records"])
            )
            assert all(
                1 <= t["line"] <= t["end_line"] <= expected for t in tokens["records"]
            )
            assert report["summary"]["total_findings"] == len(report["findings"]) == 0
            results.append(
                {
                    "case": name,
                    "physical_loc": expected,
                    "schema_and_semantics": "passed",
                    "report_sha256": hashlib.sha256(
                        (output / "findings.json").read_bytes()
                    ).hexdigest(),
                }
            )
    for name in ["partial-missing-include", "truncated-tokens", "trigger-cast"]:
        root = args.output / name / "repo"
        root.mkdir(parents=True, exist_ok=True)
        source = (
            '#include "absent.hpp"\nint value() { return 1; }\n'
            if name == "partial-missing-include"
            else "int value(double x) { return (int)x; }\n"
        )
        (root / "source.cpp").write_text(source)
        if name == "truncated-tokens":
            (root / ".cppulserc.json").write_text('{"max_token_records": 3}')
        output = root.parent / "output"
        run = subprocess.run(
            [
                str(args.analyzer.resolve()),
                "--repo",
                str(root.resolve()),
                "--output",
                str(output.resolve()),
                "--resource-dir",
                str(args.resource_dir.resolve()),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        (root.parent / "execution.log").write_text(run.stdout + run.stderr)
        report = json.loads((output / "findings.json").read_text())
        validate("findings", report, version="prototype_v1")
        item = report["metadata"]["analysis"]["native_metrics"]["files"][0]
        assert (
            item["source_content_sha256"]
            == hashlib.sha256((root / "source.cpp").read_bytes()).hexdigest()
        )
        assert report["summary"]["total_findings"] == len(report["findings"])
        if name == "partial-missing-include":
            assert item["status"] == "partial"
            assert not item["measurement_complete"]
            assert item["function_count"] is None
            assert any(
                edge["target_kind"] == "unresolved" and edge["target"] == "absent.hpp"
                for edge in item["includes"]
            )
        else:
            assert item["measurement_complete"]
            assert any(
                finding["rule_id"] == "CPP-MOD-001" for finding in report["findings"]
            )
        if name == "truncated-tokens":
            tokens = item["token_stream"]
            assert tokens["retained_tokens"] == len(tokens["records"]) == 3
            assert tokens["total_tokens"] > 3
            assert not tokens["complete"]
            assert tokens["availability"] == "partial"
        results.append(
            {
                "case": name,
                "schema_and_semantics": "passed",
                "report_sha256": hashlib.sha256(
                    (output / "findings.json").read_bytes()
                ).hexdigest(),
            }
        )
    (args.output / "verification.json").write_text(json.dumps(results, indent=2) + "\n")
    print(
        f"{len(results)} actual native reports passed schema and independent semantic checks"
    )


if __name__ == "__main__":
    main()
