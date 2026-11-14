"""Validate any supported pipeline output without synthetic-demo assumptions."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import jsonschema

SCHEMAS = Path(__file__).resolve().parents[1] / "docs/schemas"


def _identity(value: str) -> str:
    """Require a nonempty normalized repository-relative POSIX identity."""
    path = PurePosixPath(value)
    if not value or "\\" in value or path.is_absolute() or PureWindowsPath(value).drive:
        raise ValueError(f"Non-relative file identity: {value!r}")
    if ".." in path.parts or str(path) != value:
        raise ValueError(f"Non-canonical file identity: {value!r}")
    return value


def _unique(records: list[dict[str, Any]], label: str) -> set[str]:
    """Validate unique file records, retaining repeated findings separately."""
    files = [_identity(record["file"]) for record in records]
    if len(set(files)) != len(files):
        raise ValueError(f"Duplicate {label} file records")
    return set(files)


def verify_pipeline(output: Path, require_pdf: bool = False) -> dict[str, Any]:
    """Validate schema, count, path and reference invariants for a pipeline run."""
    data = {}
    for name in ("findings", "git_metrics", "risk_scores", "roadmap"):
        data[name] = json.loads((output / f"{name}.json").read_text(encoding="utf-8"))
        schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text())
        jsonschema.Draft7Validator(
            schema, format_checker=jsonschema.FormatChecker()
        ).validate(data[name])
    findings = data["findings"]["findings"]
    summary = data["findings"]["summary"]
    if summary["total_findings"] != len(findings):
        raise ValueError("Finding total disagrees with findings array")
    for field, column in [("by_category", "category"), ("by_severity", "severity")]:
        actual = Counter(record[column] for record in findings)
        published = summary[field]
        if sum(published.values()) != len(findings) or any(
            actual[key] != published.get(key, 0) for key in set(actual) | set(published)
        ):
            raise ValueError(f"Finding {field} totals disagree")
    finding_files = {_identity(item["file"]) for item in findings}
    git_files = _unique(data["git_metrics"]["file_metrics"], "Git metric")
    risks = data["risk_scores"]
    risk_files = _unique(risks["file_risks"], "risk")
    hotspot_files = _unique(risks["hotspots"], "hotspot")
    if not finding_files <= risk_files:
        raise ValueError("Findings refer to files missing from risk scope")
    if not hotspot_files <= risk_files:
        raise ValueError("Hotspots refer to files missing from risk scope")
    inventory = data["findings"].get("metadata", {}).get("analysis")
    if inventory is not None:
        root = PurePosixPath(
            data["findings"]["metadata"]["repo_path"].replace("\\", "/")
        )
        eligible = set()
        incomplete = not inventory.get("enabled_rules") and bool(inventory["files"])
        for unit in inventory["files"]:
            path = PurePosixPath(unit["path"].replace("\\", "/"))
            if path.is_absolute() or path.parts[: len(root.parts)] == root.parts:
                path = path.relative_to(root)
            if unit["status"] in {"analyzed", "partial"}:
                eligible.add(_identity(str(path)))
            incomplete = (
                incomplete
                or unit["status"] not in {"analyzed", "excluded"}
                or unit.get("error_count", 0) > 0
            )
        if risk_files != eligible:
            raise ValueError("Risk files disagree with attempted source inventory")
        if data["findings"]["metadata"]["file_count"] != len(eligible):
            raise ValueError("Analyzed file count disagrees with inventory")
        if incomplete and (
            risks["health_score"]["overall"] is not None
            or risks["health_score"].get("status") != "partial"
        ):
            raise ValueError("Incomplete source inventory has qualified health")
    if not risk_files and risks["health_score"]["overall"] is not None:
        raise ValueError("Empty risk scope has numeric health")

    counts = Counter(item["file"] for item in findings)
    for item in risks["hotspots"]:
        if (
            item["hotspot_score"] <= 0
            or item.get("finding_count") != counts[item["file"]]
        ):
            raise ValueError("Hotspot count or positive-score invariant failed")
    for item in data["roadmap"]["items"]:
        _identity(item["file"])
        if item["file"] not in risk_files:
            raise ValueError("Roadmap file is outside risk scope")
    health = risks["health_score"]
    if health.get("status") in {"no_data", "partial"} and health["overall"] is not None:
        raise ValueError("Unavailable full-scope health must not have a numeric score")
    pdf_pages = None
    if require_pdf:
        from pypdf import PdfReader

        path = output / "report.pdf"
        if path.stat().st_size < 1000 or not path.read_bytes().startswith(b"%PDF"):
            raise ValueError("Missing or empty PDF")
        reader = PdfReader(path)
        if not reader.pages or not any(
            page.extract_text().strip() for page in reader.pages
        ):
            raise ValueError("PDF has no readable text")
        pdf_pages = len(reader.pages)
    return {
        "findings": len(findings),
        "risk_files": len(risk_files),
        "git_files": len(git_files),
        "hotspots": len(hotspot_files),
        "health_status": health.get("status", "legacy"),
        "pdf_pages": pdf_pages,
    }


def main() -> None:
    """Validate an output directory and print a machine-readable summary."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--require-pdf", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify_pipeline(args.output, args.require_pdf), indent=2))


if __name__ == "__main__":
    main()
