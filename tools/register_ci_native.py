"""Freeze the analyzer and resource selected by a complete local native check."""

from __future__ import annotations

import argparse
from hashlib import file_digest
import json
import os
from pathlib import Path

from dev import ROOT, _source


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def register(build_result: Path, resource: Path) -> dict:
    result = json.loads(build_result.read_bytes())
    native_checks = {
        f"{component}-{stage}"
        for component in ("analyzer", "cli")
        for stage in ("configure", "build", "tests")
    }
    observed = {row["name"]: row for row in result["checks"]}
    source = _source()
    if (
        result.get("status") != "passed"
        or result.get("exit_status") != 0
        or result.get("source") != source
        or set(observed) != native_checks
        or len(observed) != len(result["checks"])
        or any(
            row["status"] != "passed" or row["returncode"] != 0
            for row in observed.values()
        )
    ):
        raise ValueError(
            "Registration requires all successful native checks for this source"
        )

    analyzer = ROOT / "analyzer-core/build/cppulse-analyzer"
    cache = analyzer.parent / "CMakeCache.txt"
    cache_lines = cache.read_text().splitlines()
    if f"CMAKE_HOME_DIRECTORY:INTERNAL={ROOT / 'analyzer-core'}" not in cache_lines:
        raise ValueError("Analyzer build directory belongs to another source checkout")
    if not analyzer.is_file() or not os.access(analyzer, os.X_OK):
        raise ValueError("The built analyzer is missing or not executable")
    resource = resource.resolve(strict=True)
    resource_files = ("include/stddef.h", "include/__stddef_size_t.h")
    return {
        "source": source,
        "native_result_sha256": sha256(build_result),
        "native_check_log_sha256": {
            name: sha256(Path(row["log"])) for name, row in sorted(observed.items())
        },
        "cmake_cache_sha256": sha256(cache),
        "analyzer": str(analyzer.resolve(strict=True)),
        "analyzer_sha256": sha256(analyzer),
        "resource": str(resource),
        "resource_header_sha256": {
            name: sha256(resource / name) for name in resource_files
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-result", type=Path, required=True)
    parser.add_argument("--resource-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = register(args.build_result, args.resource_dir)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(document, stream, sort_keys=True, indent=2)
        stream.write("\n")


if __name__ == "__main__":
    main()
