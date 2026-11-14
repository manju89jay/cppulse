"""Validate fresh demo contracts, internal counts, file identities and PDF content."""

from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path
import jsonschema
from pypdf import PdfReader
from verify_pipeline import verify_pipeline


def main(output: Path) -> None:
    """Fail if the demo artifacts disagree or the clean fixture has findings."""
    verify_pipeline(output, require_pdf=True)
    root = Path(__file__).resolve().parents[1]
    data = {}
    for name in ("findings", "git_metrics", "risk_scores", "roadmap"):
        data[name] = json.loads((output / f"{name}.json").read_text())
        schema = json.loads((root / "docs/schemas" / f"{name}.schema.json").read_text())
        jsonschema.Draft7Validator(
            schema, format_checker=jsonschema.FormatChecker()
        ).validate(data[name])
    findings = data["findings"]["findings"]
    summary = data["findings"]["summary"]
    assert summary["total_findings"] == len(findings) > 0
    for field, source in [("by_category", "category"), ("by_severity", "severity")]:
        counts = Counter(f[source] for f in findings)
        assert all(counts[key] == value for key, value in summary[field].items())
        assert sum(summary[field].values()) == len(findings)
    assert not any(f["file"] == "clean.cpp" for f in findings)
    assert {f["file"] for f in findings} == {"intentional.cpp"}
    files = {f["file"] for f in data["git_metrics"]["file_metrics"]}
    assert files == {"clean.cpp", "intentional.cpp"}
    assert {f["file"] for f in data["risk_scores"]["file_risks"]} == files
    for records in [
        findings,
        data["risk_scores"]["file_risks"],
        data["roadmap"]["items"],
    ]:
        assert all(
            f["file"] in files and not Path(f["file"]).is_absolute() for f in records
        )
    risk = data["risk_scores"]
    assert risk["metadata"]["model_type"] == "heuristic"
    assert risk["metadata"]["experimental"] is True
    assert all(item["hotspot_score"] > 0 for item in risk["hotspots"])
    assert all(item["file"] != "clean.cpp" for item in risk["hotspots"])
    assert data["findings"]["metadata"]["file_count"] == 2
    assert data["findings"]["metadata"]["total_loc"] == sum(
        item["lines_of_code"] for item in data["git_metrics"]["file_metrics"]
    )
    for hotspot in risk["hotspots"]:
        assert hotspot["finding_count"] == sum(
            f["file"] == hotspot["file"] for f in findings
        )
    pdf = output / "report.pdf"
    assert pdf.stat().st_size > 1000
    reader = PdfReader(pdf)
    text = "\n".join(p.extract_text() for p in reader.pages)
    assert "cppulse" in text and "intentional.cpp" in text
    (output / "report-text.txt").write_text(text)
    print(
        f"PASS: 4 schemas, totals, relative identities, clean/trigger cases; PDF {len(reader.pages)} pages, {pdf.stat().st_size} bytes"
    )
    print(
        f"Findings: {len(findings)}; files: {len(files)}; health: {risk['health_score']['overall']}; model: heuristic (experimental)"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
