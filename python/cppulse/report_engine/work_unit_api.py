"""Optional bounded reads of an explicitly configured private work-unit catalog.

The catalog is an index, not a producer or an assessment authority. Reads never
create a missing catalog, follow latest pointers, or execute project commands.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from cppulse.errors import ContractError, IntegrityError


def _decode_cursor(value: str | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if len(value) > 2048:
        raise ContractError("Work-unit cursor exceeds the finite input limit")
    try:
        raw = base64.b64decode(value, altchars=b"-_", validate=True)
        document = json.loads(raw)
    except (ValueError, binascii.Error) as exc:
        raise ContractError("Work-unit cursor is malformed") from exc
    if not isinstance(document, dict):
        raise ContractError("Work-unit cursor must identify one pinned query")
    return document


def register_work_unit_api(app: FastAPI, dependencies: list[Any]) -> None:
    """Register authenticated, explicitly pinned catalog reads on the API.

    Args:
        app: Existing report-engine API application.
        dependencies: Its existing authentication dependencies.
    """
    router = APIRouter()

    @router.get("/api/v1/work-units", dependencies=dependencies)
    def work_units(
        run_id: str = Query(..., pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"),
        manifest_sha256: str = Query(..., pattern=r"^[a-f0-9]{64}$"),
        outcome: str | None = Query(None, max_length=64),
        page_size: int = Query(100, ge=1, le=200),
        cursor: str | None = Query(None, max_length=2048),
    ) -> JSONResponse:
        """Read one finite page without creating or modifying catalog state."""
        configured = os.environ.get("CPPULSE_WORK_UNIT_CATALOG")
        if not configured:
            raise HTTPException(503, "No work-unit catalog is configured")
        try:
            # Keep the optional catalog backend out of the minimal renderer import.
            from cppulse.identities import canonical_json_bytes
            from cppulse.work_unit_store import WorkUnitIndex

            index = WorkUnitIndex(Path(configured), read_only=True)
            rows, next_cursor = index.page(
                run_id,
                manifest_sha256,
                outcome=outcome,
                page_size=page_size,
                cursor=_decode_cursor(cursor),
            )
            encoded = (
                base64.urlsafe_b64encode(canonical_json_bytes(next_cursor)).decode()
                if next_cursor is not None
                else None
            )
            return JSONResponse(
                {
                    "version": "1.0.0",
                    "protocol": "private-work-unit-index",
                    "run_id": run_id,
                    "manifest_sha256": manifest_sha256,
                    "items": rows,
                    "next_cursor": encoded,
                    "limitations": [
                        "Catalog summaries do not establish current source freshness or a policy pass."
                    ],
                },
                headers={"Cache-Control": "no-store"},
            )
        except ContractError as exc:
            raise HTTPException(422, str(exc)) from exc
        except IntegrityError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (OSError, ValueError, ImportError, sqlite3.DatabaseError) as exc:
            raise HTTPException(503, "Work-unit catalog is unavailable") from exc

    app.include_router(router)
