"""Checked local fact storage and immutable indexed work-unit snapshots.

This private store does not promote runtime evidence or create native receipts.
An extraction-cache caller must supply an independently closed dependency
manifest; current native include callbacks do not establish that closure.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json
import os
import stat

import jsonschema
from pathlib import Path
import re
import sqlite3
from typing import Any

from cppulse.errors import ContractError, IntegrityError, PublicationConflict
from cppulse.identities import canonical_json_bytes, digest_json


@dataclass(frozen=True)
class FactSelection:
    """All extraction-key inputs; assessment settings have a separate key."""

    primary_sha256: str
    context_digest: str
    native_sha256: str
    registry_sha256: str
    extraction_configuration_sha256: str
    dependencies: tuple[tuple[str, str], ...]
    dependencies_complete: bool

    def key(self) -> str | None:
        """Return no positive cache key when dependency closure is unknown."""
        hashes = [
            self.primary_sha256,
            self.context_digest,
            self.native_sha256,
            self.registry_sha256,
            self.extraction_configuration_sha256,
            *(digest for _, digest in self.dependencies),
        ]
        if any(not re.fullmatch(r"[a-f0-9]{64}", digest) for digest in hashes):
            raise ContractError("Fact-key inputs must be SHA-256 digests")
        if len({path for path, _ in self.dependencies}) != len(self.dependencies):
            raise ContractError("Dependency identities must be unique")
        if self.dependencies_complete is not True:
            return None
        return digest_json(
            {
                "primary": self.primary_sha256,
                "context": self.context_digest,
                "native": self.native_sha256,
                "registry": self.registry_sha256,
                "configuration": self.extraction_configuration_sha256,
                "dependencies": sorted(self.dependencies),
            }
        )


def assessment_key(
    fact_keys: Iterable[str],
    scorer: str,
    policy: dict[str, Any],
    configuration: dict[str, Any],
) -> str:
    """Identify assessment settings separately from reusable extracted facts."""
    return digest_json(
        {
            "facts": sorted(fact_keys),
            "scorer": scorer,
            "policy": policy,
            "configuration": configuration,
        }
    )


class CheckedFactCache:
    """Content-addressed local payloads checked on every read; not authenticated."""

    def __init__(
        self, root: Path | str, *, max_entry_bytes: int = 8 * 1024 * 1024
    ) -> None:
        self.root = Path(root).absolute()
        _safe_ancestors(self.root)
        if (
            isinstance(max_entry_bytes, bool)
            or not isinstance(max_entry_bytes, int)
            or not 1024 <= max_entry_bytes <= 64 * 1024 * 1024
        ):
            raise ContractError("Cache entry bound must be between 1024 and 67108864")
        self.max_entry_bytes = max_entry_bytes
        self.root.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        selection: FactSelection,
        payload: dict[str, Any],
        *,
        origin: dict[str, Any],
        complete: bool,
    ) -> bool:
        """Store only complete facts with explicit origin; never store receipts."""
        key = selection.key()
        if key is None or complete is not True:
            return False
        if not origin.get("run_id") or not re.fullmatch(
            r"[a-f0-9]{64}", origin.get("manifest_sha256", "")
        ):
            raise ContractError("Cache origin needs a pinned immutable run")
        if "execution_receipt" in payload:
            raise ContractError(
                "Extraction-cache payload cannot promote an execution receipt"
            )
        document = {
            "key": key,
            "payload_sha256": digest_json(payload),
            "payload": payload,
            "origin": origin,
        }
        path = self.root / (key + ".json")
        encoded = canonical_json_bytes(document)
        if len(encoded) > self.max_entry_bytes:
            raise ContractError("Cache entry exceeds byte bound")
        _safe_ancestors(path)
        if path.exists():
            if path.is_symlink() or self.get(selection) != document:
                raise IntegrityError("Cache key already has different material")
            return True
        try:
            with path.open("xb") as stream:
                stream.write(encoded)
        except FileExistsError:
            if self.get(selection) != document:
                raise IntegrityError(
                    "Concurrent cache writer supplied different material"
                )
        return True

    def get(self, selection: FactSelection) -> dict[str, Any] | None:
        """Return original facts/origin after checked identity; no new receipt."""
        key = selection.key()
        if key is None:
            return None
        path = self.root / (key + ".json")
        if not path.exists():
            return None
        _safe_ancestors(path)
        try:
            descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            with os.fdopen(descriptor, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise IntegrityError("Cache entry must be a regular file")
                content = stream.read(self.max_entry_bytes + 1)
                if len(content) > self.max_entry_bytes:
                    raise IntegrityError("Cache entry exceeds byte bound")
            document = json.loads(content)
        except (OSError, ValueError) as exc:
            raise IntegrityError("Cache entry is incomplete or invalid") from exc
        if not isinstance(document, dict) or set(document) != {
            "key",
            "payload_sha256",
            "payload",
            "origin",
        }:
            raise IntegrityError("Cache entry shape differs from contract")
        if (
            not isinstance(document["payload"], dict)
            or not isinstance(document["origin"], dict)
            or not document["origin"].get("run_id")
            or not re.fullmatch(
                r"[a-f0-9]{64}", document["origin"].get("manifest_sha256", "")
            )
        ):
            raise IntegrityError("Cache payload or origin differs from contract")
        if document.get("key") != key or document.get("payload_sha256") != digest_json(
            document.get("payload")
        ):
            raise IntegrityError("Cache payload differs from retained digest")
        return document


_OUTCOMES = [
    "complete",
    "partial",
    "process_error",
    "timed_out",
    "cancelled",
    "input_changed",
    "unsupported",
    "not_attempted",
    "crashed",
    "invalid_output",
]
_SUMMARY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "unit_id": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"},
        "outcome": {"enum": _OUTCOMES},
        "reason": {"type": "string", "maxLength": 4096},
        "request_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "primary_file": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4096,
            "pattern": "^(?!/)(?![A-Za-z]:)(?!.*\\\\)(?!.*(?:^|/)\\.{1,2}(?:/|$))(?!.*//)(?!.*/$)[^\\u0000-\\u001f\\u007f]+$",
        },
        "input_verification": {
            "enum": ["verified", "unverified", "changed", "unavailable"]
        },
        "execution_status": {
            "enum": ["completed", "partial", "cancelled", "input_changed"]
        },
        "parse_status": {
            "enum": [
                "analyzed",
                "partial",
                "failed",
                "skipped",
                "excluded",
                "missing",
                None,
            ]
        },
    },
    "required": ["unit_id", "outcome"],
}
_MAX_SUMMARY_BYTES = 16 * 1024


def _safe_ancestors(path: Path) -> None:
    for component in (path, *path.parents):
        if component.is_symlink():
            raise IntegrityError("Store path components cannot be symlinks")


def _summary(document: dict[str, Any]) -> bytes:
    try:
        jsonschema.Draft7Validator(_SUMMARY_SCHEMA).validate(document)
    except jsonschema.ValidationError as exc:
        raise ContractError("Invalid catalog summary: " + exc.message) from exc
    encoded = canonical_json_bytes(document)
    if len(encoded) > _MAX_SUMMARY_BYTES:
        raise ContractError("Catalog summary exceeds byte bound")
    return encoded


class WorkUnitIndex:
    """Transactional catalog of finite summaries; not a findings/history index."""

    def __init__(self, path: Path | str, *, read_only: bool = False) -> None:
        self.path = Path(path).absolute()
        self.read_only = read_only
        _safe_ancestors(self.path)
        if read_only:
            if not self.path.is_file():
                raise IntegrityError("Selected catalog does not exist")
            with self._connect() as db:
                if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                    raise ContractError("Unsupported work-unit catalog version")
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ContractError("Unsupported work-unit catalog version")
            db.execute(
                "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, manifest_sha256 TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS units (run_id TEXT NOT NULL REFERENCES runs(run_id), unit_id TEXT NOT NULL, outcome TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id,unit_id))"
            )
            db.execute(
                "CREATE INDEX IF NOT EXISTS units_outcome ON units(run_id,outcome,unit_id)"
            )
            db.execute("PRAGMA user_version=1")

    def _connect(self) -> sqlite3.Connection:
        _safe_ancestors(self.path)
        if self.read_only:
            connection = sqlite3.connect(
                self.path.as_uri() + "?mode=ro", uri=True, timeout=10
            )
        else:
            connection = sqlite3.connect(self.path, timeout=10)
            connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def publish(
        self, run_id: str, manifest_sha256: str, results: Iterable[dict[str, Any]]
    ) -> None:
        """Publish schema-checked summaries atomically; interruption rolls back."""
        if self.read_only:
            raise ContractError("Catalog reader cannot publish")
        if not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", run_id
        ) or not re.fullmatch(r"[a-f0-9]{64}", manifest_sha256):
            raise ContractError("Catalog run identity is invalid")
        with self._connect() as db:
            if db.execute("SELECT 1 FROM runs WHERE run_id=?", (run_id,)).fetchone():
                raise PublicationConflict("Catalog run is immutable")
            db.execute("INSERT INTO runs VALUES (?,?)", (run_id, manifest_sha256))
            for result in results:
                encoded = _summary(result)
                db.execute(
                    "INSERT INTO units VALUES (?,?,?,?)",
                    (run_id, result["unit_id"], result["outcome"], encoded.decode()),
                )

    def page(
        self,
        run_id: str,
        manifest_sha256: str,
        *,
        outcome: str | None = None,
        page_size: int = 100,
        cursor: dict[str, Any] | None = None,
        max_page_bytes: int = 1024 * 1024,
    ) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """Return schema-checked, row/byte-bounded, immutable query-pinned pages."""
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or not 1 <= page_size <= 200
        ):
            raise ContractError("Catalog page size must be between 1 and 200")
        if (
            isinstance(max_page_bytes, bool)
            or not isinstance(max_page_bytes, int)
            or not _MAX_SUMMARY_BYTES + 1025 <= max_page_bytes <= 16 * 1024 * 1024
        ):
            raise ContractError("Page byte bound must be between 17409 and 16777216")
        if outcome is not None and outcome not in _OUTCOMES:
            raise ContractError("Unknown catalog outcome filter")
        query = digest_json(
            {
                "run_id": run_id,
                "manifest_sha256": manifest_sha256,
                "outcome": outcome,
                "page_size": page_size,
                "max_page_bytes": max_page_bytes,
                "sort": "unit_id",
            }
        )
        after = ""
        if cursor is not None:
            if (
                set(cursor) != {"query_sha256", "after"}
                or cursor.get("query_sha256") != query
                or not isinstance(cursor.get("after"), str)
                or not re.fullmatch(
                    r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", cursor["after"]
                )
            ):
                raise ContractError("Cursor differs from the pinned run or query")
            after = cursor["after"]
        selected: list[dict[str, Any]] = []
        retained_bytes = 1024
        next_cursor = None
        with self._connect() as db:
            run = db.execute(
                "SELECT manifest_sha256 FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if run is None or run[0] != manifest_sha256:
                raise IntegrityError("Catalog run differs from selected manifest")
            # CASE bounds data crossing the SQLite/Python boundary even for a
            # corrupt externally edited catalog containing an oversized row.
            rows = db.execute(
                "SELECT unit_id, CASE WHEN length(CAST(payload AS BLOB))<=? THEN payload ELSE NULL END FROM units WHERE run_id=? AND unit_id>? AND (? IS NULL OR outcome=?) ORDER BY unit_id LIMIT ?",
                (_MAX_SUMMARY_BYTES, run_id, after, outcome, outcome, page_size + 1),
            )
            for identifier, payload in rows:
                if payload is None:
                    raise IntegrityError("Catalog row exceeds summary byte bound")
                try:
                    document = json.loads(payload)
                    encoded = _summary(document)
                except (ValueError, ContractError) as exc:
                    raise IntegrityError(
                        "Catalog row violates summary contract"
                    ) from exc
                if document["unit_id"] != identifier:
                    raise IntegrityError("Catalog row key differs from its payload")
                if (
                    len(selected) == page_size
                    or retained_bytes + len(encoded) + 1 > max_page_bytes
                ):
                    next_cursor = {
                        "query_sha256": query,
                        "after": selected[-1]["unit_id"],
                    }
                    break
                selected.append(document)
                retained_bytes += len(encoded) + 1
        return selected, next_cursor
