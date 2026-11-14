"""FastAPI REST API for the cppulse report-engine component."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextvars import ContextVar
from dataclasses import dataclass
import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from cppulse.errors import CppulseError
from cppulse.report_engine.pdf_generator import PDFGenerator
from cppulse.report_engine.schema_validator import validate_document
from cppulse.run_store import RunSnapshot, RunStore


def _cors_origins() -> list[str]:
    """Return allowed CORS origins from environment or default.

    Reads the ``CORS_ORIGINS`` environment variable as a comma-separated list.
    Falls back to ``["http://localhost:3000"]`` when unset.

    Returns:
        List of allowed origin strings.
    """
    raw = os.environ.get("CORS_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    return ["http://localhost:3000"]


def _api_key() -> str | None:
    """Return the configured API key, or None if auth is disabled.

    Reads the ``CPPULSE_API_KEY`` environment variable. When unset or empty,
    API endpoints are unauthenticated (backwards compatible).

    Returns:
        API key string or None.
    """
    key = os.environ.get("CPPULSE_API_KEY", "").strip()
    return key if key else None


app = FastAPI(
    title="cppulse Report Engine",
    description="REST API for cppulse health reports.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _dashboard_directory() -> Path:
    """Return bundled production assets; serving never starts a Node process."""
    return Path(__file__).parent.parent / "data" / "dashboard"


@app.get("/", include_in_schema=False)
def dashboard_index() -> Response:
    """Serve the bundled public UI shell; data requests retain API-key checks."""
    try:
        content = (_dashboard_directory() / "index.html").read_bytes()
    except OSError as error:
        raise HTTPException(
            status_code=503,
            detail="Dashboard assets were not bundled. Rebuild the candidate with scripts/build_dashboard_assets.py; serving requires no Node installation.",
        ) from error
    return Response(
        content=content,
        media_type="text/html",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


app.mount(
    "/assets",
    StaticFiles(directory=_dashboard_directory() / "assets", check_dir=False),
    name="dashboard-assets",
)


def verify_api_key(request: Request) -> None:
    """FastAPI dependency that enforces API key auth when configured.

    Checks the ``Authorization: Bearer <key>`` header against the
    ``CPPULSE_API_KEY`` environment variable. Skips validation when no key
    is configured (unauthenticated mode).

    Args:
        request: Incoming FastAPI request.

    Raises:
        HTTPException: 401 if the key is missing or incorrect.
    """
    expected = _api_key()
    if expected is None:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing API key. Use Authorization: Bearer <key>."
        )
    token = auth[len("Bearer ") :]
    if token != expected:
        raise HTTPException(status_code=401, detail="Invalid API key.")


def _data_dir() -> Path:
    """Return the configured data directory.

    Returns:
        Path to the directory containing JSON output files, controlled by
        the DATA_DIR environment variable (default: ``./output``).
    """
    return Path(os.environ.get("DATA_DIR", "./output"))


@dataclass(frozen=True)
class _RequestData:
    """One request's selected location and immutable manifest-bound snapshot."""

    path: Path
    snapshot: RunSnapshot | None


_request_data: ContextVar[_RequestData | None] = ContextVar(
    "cppulse_request_data", default=None
)


def _validate_pin(run_id: str | None, manifest_sha256: str | None) -> None:
    """Require a complete canonical run/hash pair before selecting stored data."""
    if run_id is None and manifest_sha256 is None:
        return
    if (
        run_id is None
        or manifest_sha256 is None
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_id) is None
        or re.fullmatch(r"[a-f0-9]{64}", manifest_sha256) is None
    ):
        raise HTTPException(
            status_code=422,
            detail="Select both a canonical run_id and its manifest_sha256.",
        )


def _open_snapshot(path: Path, run_id: str, manifest_sha256: str) -> RunSnapshot:
    """Read one named snapshot without writer initialization or pointer fallback."""
    _validate_pin(run_id, manifest_sha256)
    try:
        return RunStore.open_existing(path).open_run(
            run_id, manifest_sha256=manifest_sha256
        )
    except (CppulseError, OSError) as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": getattr(error, "code", "RUN_STORE_UNAVAILABLE"),
                "message": f"Selected run is unavailable: {error}",
            },
        ) from error


def _resolve_request_data(
    *, run_id: str | None = None, manifest_sha256: str | None = None
) -> _RequestData:
    _validate_pin(run_id, manifest_sha256)
    path = _data_dir().absolute()
    if run_id is not None and manifest_sha256 is not None:
        return _RequestData(path, _open_snapshot(path, run_id, manifest_sha256))
    # Existing store metadata, including a missing/corrupt current pointer,
    # must never cause a fallback to older flat compatibility exports.
    is_store = any(
        (path / name).exists() or (path / name).is_symlink()
        for name in ("latest_attempt.json", "latest.json", "runs", ".staging")
    )
    if not is_store:
        return _RequestData(path, None)
    try:
        snapshot = RunStore.open_existing(path).resolve_latest_attempt()
    except (CppulseError, OSError) as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": getattr(error, "code", "RUN_STORE_UNAVAILABLE"),
                "message": f"Current run is unavailable: {error}",
            },
        ) from error
    return _RequestData(path, snapshot)


async def _bind_request_data(request: Request) -> AsyncIterator[None]:
    """Resolve once after authentication; isolate concurrent requests' snapshots."""
    token = _request_data.set(
        _resolve_request_data(
            run_id=request.query_params.get("run_id"),
            manifest_sha256=request.query_params.get("manifest_sha256"),
        )
    )
    try:
        yield
    finally:
        _request_data.reset(token)


def _current_data() -> _RequestData:
    # Direct Python calls remain supported; HTTP calls use the bound context.
    return _request_data.get() or _resolve_request_data()


def _require_completed(snapshot: RunSnapshot) -> None:
    manifest = snapshot.manifest
    if manifest["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "RUN_INCOMPLETE",
                "run_id": snapshot.run_id,
                "status": manifest["status"],
                "message": "Data is unavailable for this incomplete published attempt.",
            },
        )


_DATA_DEPENDENCIES = [Depends(verify_api_key), Depends(_bind_request_data)]


class _JsonCache:
    """Thread-safe in-memory cache for parsed JSON files with mtime invalidation.

    Each entry tracks the file's modification time. On access, if the mtime
    has changed the file is re-read; otherwise the cached dict is returned.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, dict[str, Any]]] = {}

    def get(self, path: Path) -> dict[str, Any]:
        """Load and cache a JSON file, invalidating on mtime change.

        Args:
            path: Absolute path to the JSON file.

        Returns:
            Parsed JSON dict (possibly from cache).

        Raises:
            HTTPException: 503 if the file is missing or malformed.
        """
        name = path.stem
        key = str(path.resolve())
        if not path.exists():
            raise HTTPException(
                status_code=503,
                detail=f"Data file not available: {name}.json. "
                "Ensure the pipeline has been run.",
            )

        current_mtime = path.stat().st_mtime

        with self._lock:
            if key in self._entries:
                cached_mtime, cached_data = self._entries[key]
                if cached_mtime == current_mtime:
                    return cached_data

        # Read outside the lock to avoid holding it during I/O.
        try:
            data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Could not parse {name}.json: {exc}",
            ) from exc

        errors = validate_document(data, name)
        if errors:
            raise HTTPException(status_code=503, detail=f"Invalid {name}: {errors[0]}")

        with self._lock:
            self._entries[key] = (current_mtime, data)

        return data

    def clear(self) -> None:
        """Evict all cached entries."""
        with self._lock:
            self._entries.clear()


_json_cache = _JsonCache()


def _load_json(name: str) -> dict[str, Any]:
    """Load a JSON file from the data directory (cached with mtime invalidation).

    Args:
        name: Filename without extension (e.g. ``'findings'``).

    Returns:
        Parsed JSON as a dict.

    Raises:
        HTTPException: 503 if the file is missing or unreadable.
    """
    current = _current_data()
    if current.snapshot is None:
        return _json_cache.get(current.path / f"{name}.json")
    snapshot = current.snapshot
    _require_completed(snapshot)
    try:
        return snapshot.read_json(name, contract=(name, "prototype_v1"))
    except (CppulseError, OSError) as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": getattr(error, "code", "ARTIFACT_UNAVAILABLE"),
                "run_id": snapshot.run_id,
                "message": str(error),
            },
        ) from error


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


@app.get("/api/v1/run", dependencies=_DATA_DEPENDENCIES)
def current_run() -> dict[str, Any]:
    """Expose current collection status and source limitations, including failures."""
    current = _current_data()
    if current.snapshot is None:
        return {
            "mode": "legacy-flat",
            "run_id": None,
            "input_verification": "unverified",
            "limitations": [
                "Legacy flat files have no request-bound run manifest or source verification."
            ],
        }
    snapshot = current.snapshot
    return {
        "mode": "snapshot",
        "run_id": snapshot.run_id,
        "manifest_sha256": snapshot.manifest_sha256,
        "manifest": snapshot.manifest,
        "status_meaning": "Collection completion does not mean checks or policies passed.",
    }


@app.get("/api/v1/view", dependencies=_DATA_DEPENDENCIES)
def snapshot_view(
    response: Response, assessment_artifact_id: str | None = None
) -> dict[str, Any]:
    """Present one stored attempt, including incomplete facts, without new gates.

    An optional run_id/manifest_sha256 pair selects a named historical snapshot.
    With no pair, request binding resolves the current attempt once. Legacy flat
    files remain an explicitly unverified compatibility mode with no fake pin.
    """
    response.headers["Cache-Control"] = "no-store"
    current = _current_data()
    if current.snapshot is None:
        legacy = {}
        for kind in ("findings", "git_metrics", "risk_scores", "roadmap"):
            path = current.path / f"{kind}.json"
            legacy[kind] = (
                {"document": _json_cache.get(path)}
                if path.exists() or path.is_symlink()
                else None
            )
        return {
            "mode": "legacy-flat",
            "input_verification": "unverified",
            "legacy": legacy,
            "limitations": [
                "Legacy flat compatibility files have no immutable run/manifest pin or source verification.",
                "Separate flat files can change during reading; this mode does not establish a common source or execution context.",
            ],
        }
    from cppulse.presentation import build_snapshot_view

    try:
        return build_snapshot_view(
            current.snapshot, assessment_artifact_id=assessment_artifact_id
        )
    except (CppulseError, OSError) as error:
        raise HTTPException(
            status_code=503,
            detail={
                "code": getattr(error, "code", "VIEW_UNAVAILABLE"),
                "run_id": current.snapshot.run_id,
                "message": str(error),
            },
        ) from error


@app.get(
    "/api/v1/runs/{run_id}/artifacts/{artifact_id}",
    dependencies=[Depends(verify_api_key)],
)
def artifact_download(
    run_id: str,
    artifact_id: str,
    manifest_sha256: str = Query(..., pattern=r"^[a-f0-9]{64}$"),
) -> Response:
    """Download exact inventoried bytes bound to both run identity and hash."""
    snapshot = _open_snapshot(_data_dir().absolute(), run_id, manifest_sha256)
    artifacts = [
        entry for entry in snapshot.manifest["artifacts"] if entry["id"] == artifact_id
    ]
    if not artifacts:
        raise HTTPException(status_code=404, detail="Artifact ID is not in this run.")
    try:
        content = snapshot.read_bytes(artifact_id)
    except (CppulseError, OSError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    # Retained media metadata is a claim, not an HTTP-header grammar guarantee.
    # Keep its original bytes in the descriptor while limiting the transport.
    selected_type = artifacts[0]["media_type"]
    media_type = (
        selected_type
        if re.fullmatch(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+", selected_type)
        else "application/octet-stream"
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={
            "Content-Disposition": 'attachment; filename="cppulse-artifact.bin"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
            "X-CPPulse-Run-ID": snapshot.run_id,
            "X-CPPulse-Manifest-SHA256": snapshot.manifest_sha256,
        },
    )


def _snapshot_report(
    request: Request, format_name: str, assessment_id: str | None
) -> Response:
    """Render the bound stored view without substituting flat or older data."""
    if _current_data().snapshot is None:
        raise HTTPException(
            status_code=409,
            detail="Snapshot reports require a stored run. Legacy flat reports use /api/v1/report/pdf.",
        )
    from cppulse.presentation import render_snapshot_html, render_snapshot_pdf

    view = snapshot_view(Response(), assessment_artifact_id=assessment_id)
    try:
        content = (
            render_snapshot_pdf(view, base_url=str(request.base_url))
            if format_name == "pdf"
            else render_snapshot_html(view)
        )
    except (CppulseError, OSError, RuntimeError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return Response(
        content=content,
        media_type="application/pdf" if format_name == "pdf" else "text/html",
        headers={
            "Content-Disposition": f'attachment; filename="cppulse_snapshot.{format_name}"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/v1/report.pdf", dependencies=_DATA_DEPENDENCIES)
def snapshot_pdf(
    request: Request, assessment_artifact_id: str | None = None
) -> Response:
    """Download a PDF rendered from the same optional explicit run/hash pin."""
    return _snapshot_report(request, "pdf", assessment_artifact_id)


@app.get("/api/v1/report.html", dependencies=_DATA_DEPENDENCIES)
def snapshot_html(
    request: Request, assessment_artifact_id: str | None = None
) -> Response:
    """Download HTML rendered from the same optional explicit run/hash pin."""
    return _snapshot_report(request, "html", assessment_artifact_id)


@app.get("/api/v1/summary", dependencies=_DATA_DEPENDENCIES)
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


@app.get("/api/v1/findings", dependencies=_DATA_DEPENDENCIES)
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


@app.get("/api/v1/hotspots", dependencies=_DATA_DEPENDENCIES)
def hotspots() -> dict[str, Any]:
    """Return the top 20 hotspot files.

    Returns:
        Dict with ``items`` (list of hotspot objects) and ``total``.
    """
    risk = _load_json("risk_scores")
    items: list[dict[str, Any]] = risk.get("hotspots", [])[:20]
    return {"items": items, "total": len(items)}


@app.get("/api/v1/risks", dependencies=_DATA_DEPENDENCIES)
def risks() -> dict[str, Any]:
    """Return per-file risk scores from the predictor output.

    Returns:
        Compatible ranked ``items`` and ``total``, plus separately unavailable
        files, their count and the producer's optional ranking-scope metadata.
    """
    risk = _load_json("risk_scores")
    items: list[dict[str, Any]] = risk.get("file_risks", [])
    unranked = risk.get("unranked_files", [])
    return {
        "items": items,
        "total": len(items),
        "unranked_files": unranked,
        "unranked_total": len(unranked),
        "ranking_scope": risk.get("metadata", {}).get("ranking_scope"),
    }


@app.get("/api/v1/silos", dependencies=_DATA_DEPENDENCIES)
def silos() -> dict[str, Any]:
    """Return knowledge silo alerts from git metrics.

    Returns:
        Observed ``items`` and ``total``, with explicit history availability and
        limitations. An empty observed list does not establish absent risk.
    """
    git = _load_json("git_metrics")
    items: list[dict[str, Any]] = git.get("knowledge_silos", [])
    metadata = git.get("metadata", {})
    return {
        "items": items,
        "total": len(items),
        "history_status": metadata.get("history_status", "unverified"),
        "limitations": metadata.get("limitations", []),
    }


@app.get("/api/v1/roadmap", dependencies=_DATA_DEPENDENCIES)
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


@app.get("/api/v1/report/pdf", dependencies=_DATA_DEPENDENCIES)
def report_pdf() -> Response:
    """Generate and return the full PDF health report.

    Returns:
        PDF binary response with ``Content-Disposition: attachment``.

    Raises:
        HTTPException: 503 if PDF generation fails (e.g. WeasyPrint unavailable
            or required data files missing).
    """
    current = _current_data()
    if current.snapshot is not None:
        snapshot = current.snapshot
        _require_completed(snapshot)
        if not any(
            entry["id"] == "report-pdf" for entry in snapshot.manifest["artifacts"]
        ):
            raise HTTPException(
                status_code=404,
                detail=f"No PDF artifact was retained for run {snapshot.run_id}.",
            )
        try:
            pdf_bytes = snapshot.read_bytes("report-pdf")
        except (CppulseError, OSError) as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
    else:
        generator = PDFGenerator(current.path)
        try:
            pdf_bytes = generator.generate_pdf()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=cppulse_report.pdf"},
    )
