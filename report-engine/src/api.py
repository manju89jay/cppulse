"""FastAPI REST API for the cppulse report-engine component."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from src.pdf_generator import PDFGenerator

app = FastAPI(
    title="cppulse Report Engine",
    description="REST API for cppulse health reports.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _data_dir() -> Path:
    """Return the configured data directory.

    Returns:
        Path to the directory containing JSON output files, controlled by
        the DATA_DIR environment variable (default: ``./output``).
    """
    return Path(os.environ.get("DATA_DIR", "./output"))


def _load_json(name: str) -> dict[str, Any]:
    """Load a JSON file from the data directory.

    Args:
        name: Filename without extension (e.g. ``'findings'``).

    Returns:
        Parsed JSON as a dict.

    Raises:
        HTTPException: 503 if the file is missing or unreadable.
    """
    path = _data_dir() / f"{name}.json"
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Data file not available: {name}.json. "
            "Ensure the pipeline has been run.",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[return-value]
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Could not parse {name}.json: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe.

    Returns:
        ``{"status": "ok"}``
    """
    return {"status": "ok"}


@app.get("/api/v1/summary")
def summary() -> dict[str, Any]:
    """Return overall health score and summary statistics.

    Returns:
        Dict containing ``health_score``, ``findings_summary``,
        ``metadata``, and ``model_metadata``.
    """
    risk = _load_json("risk_scores")
    findings = _load_json("findings")

    return {
        "health_score": risk.get("health_score", {}),
        "findings_summary": findings.get("summary", {}),
        "metadata": findings.get("metadata", {}),
        "model_metadata": risk.get("metadata", {}),
    }


@app.get("/api/v1/findings")
def findings(
    page: int = Query(default=1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(default=50, ge=1, le=200, description="Items per page"),
    category: str | None = Query(default=None, description="Filter by category"),
) -> dict[str, Any]:
    """Return a paginated, optionally filtered list of static analysis findings.

    Args:
        page: Page number, 1-based.
        per_page: Number of items per page (max 200).
        category: Optional category filter. One of ``memory_safety``,
            ``modernization``, ``complexity``, ``misra``.

    Returns:
        Dict with ``items``, ``total``, ``page``, ``per_page``,
        and ``total_pages``.
    """
    data = _load_json("findings")
    items: list[dict[str, Any]] = data.get("findings", [])

    if category is not None:
        items = [f for f in items if f.get("category") == category]

    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = items[start:end]
    total_pages = max(1, (total + per_page - 1) // per_page)

    return {
        "items": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


@app.get("/api/v1/hotspots")
def hotspots() -> dict[str, Any]:
    """Return the top 20 hotspot files.

    Returns:
        Dict with ``items`` (list of hotspot objects) and ``total``.
    """
    risk = _load_json("risk_scores")
    items: list[dict[str, Any]] = risk.get("hotspots", [])[:20]
    return {"items": items, "total": len(items)}


@app.get("/api/v1/risks")
def risks() -> dict[str, Any]:
    """Return per-file risk scores from the predictor output.

    Returns:
        Dict with ``items`` (list of file risk objects) and ``total``.
    """
    risk = _load_json("risk_scores")
    items: list[dict[str, Any]] = risk.get("file_risks", [])
    return {"items": items, "total": len(items)}


@app.get("/api/v1/silos")
def silos() -> dict[str, Any]:
    """Return knowledge silo alerts from git metrics.

    Returns:
        Dict with ``items`` (list of silo objects) and ``total``.
    """
    git = _load_json("git_metrics")
    items: list[dict[str, Any]] = git.get("knowledge_silos", [])
    return {"items": items, "total": len(items)}


@app.get("/api/v1/roadmap")
def roadmap() -> dict[str, Any]:
    """Return the prioritised refactoring roadmap.

    Returns:
        Dict with ``items`` (sorted by priority) and ``total``.
    """
    data = _load_json("roadmap")
    items: list[dict[str, Any]] = sorted(
        data.get("items", []),
        key=lambda x: x.get("priority", 999),
    )
    return {"items": items, "total": len(items)}


@app.get("/api/v1/report/pdf")
def report_pdf() -> Response:
    """Generate and return the full PDF health report.

    Returns:
        PDF binary response with ``Content-Disposition: attachment``.

    Raises:
        HTTPException: 503 if PDF generation fails (e.g. WeasyPrint unavailable
            or required data files missing).
    """
    data_dir = _data_dir()
    generator = PDFGenerator(data_dir)
    try:
        pdf_bytes = generator.generate_pdf()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=cppulse_report.pdf"},
    )
