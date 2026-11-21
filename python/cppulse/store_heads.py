"""Explicit v3 atomic head authority and fail-closed v2 migration.

This local protocol is cooperative persistence, not protection from the store
owner. V3 intentionally refuses unsupported old readers/writers at legacy slots.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any
from uuid import uuid4

from cppulse.errors import IntegrityError, PublicationConflict
from cppulse.store_coordination import publication_guard, validate_store_document

FORMAT = "store-format.json"
HEADS = "heads.json"
ARCHIVE = ".migration-v3"
LEGACY = ("latest.json", "latest_attempt.json")
BUDGET = 65536


def _exists(path: Path) -> bool:
    try:
        path.lstat()
        return True
    except FileNotFoundError:
        return False


def _control_bytes(path: Path) -> bytes:
    from cppulse.run_store import _directory

    maximum = BUDGET * 5 if path.name == "plan.json" else BUDGET
    try:
        with _directory(path.parent) as parent:
            descriptor = os.open(
                path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
            )
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                # An opened immutable head may lose its sole pathname when
                # the next generation atomically replaces it. Its descriptor
                # still pins the complete old epoch. Extra links are unsafe.
                or metadata.st_nlink > 1
                or metadata.st_mode & 0o022
                or metadata.st_size > maximum
            ):
                raise IntegrityError(
                    "Store protocol control file is foreign, unsafe or oversized"
                )
            raw = stream.read(maximum + 1)
            if len(raw) > maximum:
                raise IntegrityError(
                    "Store protocol control file exceeds finite byte limit"
                )
            return raw
    except OSError as exc:
        raise IntegrityError(
            "Store protocol control file is missing, unsafe or unreadable"
        ) from exc


def _document(path: Path) -> dict[str, Any]:
    raw = _control_bytes(path)

    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise IntegrityError("Duplicate store protocol JSON key")
            result[key] = value
        return result

    try:
        value = json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise IntegrityError("Invalid store protocol JSON") from exc
    if not isinstance(value, dict):
        raise IntegrityError("Store protocol must be a JSON object")
    return value


def _bytes(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode()


def _replace(root: Path, name: str, document: dict[str, Any]) -> None:
    from cppulse.run_store import _directory, _write_new

    temporary = ".heads-" + uuid4().hex + ".tmp"
    _write_new(root / temporary, _bytes(document))
    try:
        with _directory(root) as fd:
            os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
            os.fsync(fd)
    finally:
        (root / temporary).unlink(missing_ok=True)


def protocol(root: Path, *, allow_migrating: bool = False) -> dict[str, Any] | None:
    """Read checked format marker; absent means the original v2 protocol."""
    if not _exists(root / FORMAT):
        return None
    marker = _document(root / FORMAT)
    validate_store_document("format-v3", marker)
    if marker["phase"] != "active" and not allow_migrating:
        raise PublicationConflict(
            "Store v3 migration is incomplete; explicitly resume upgrade_store_to_v3 before reading or publishing",
            code="STORE_MIGRATION_INCOMPLETE",
        )
    return marker


def _fences(root: Path) -> None:
    from cppulse.run_store import _directory

    for name in LEGACY:
        with _directory(root / name) as fd:
            metadata = os.fstat(fd)
            if (
                metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700
            ):
                raise IntegrityError(
                    "Legacy v3 compatibility fence is foreign or unsafe"
                )
            if os.listdir(fd):
                raise IntegrityError("Legacy v3 compatibility fence must remain empty")


def read_heads(root: Path) -> dict[str, Any]:
    """Read one bounded authority snapshot without fallback to legacy mirrors."""
    if protocol(root) is None:
        raise IntegrityError("V3 heads require an active v3 store marker")
    _fences(root)
    heads = _document(root / HEADS)
    validate_store_document("heads-v3", heads)
    if heads["latest"] is not None and heads["latest_attempt"] is None:
        raise IntegrityError("Completed head requires an attempt head")
    return heads


def publish_heads(store: Any, snapshot: Any, *, make_latest: bool) -> None:
    """Replace both v3 references once; caller owns the publication guard/slot."""
    heads = read_heads(store.root)
    reference = {"run_id": snapshot.run_id, "manifest_sha256": snapshot.manifest_sha256}
    heads["generation"] += 1
    heads["latest_attempt"] = reference
    if make_latest and snapshot.manifest["status"] == "completed":
        heads["latest"] = reference
    validate_store_document("heads-v3", heads)
    _replace(store.root, HEADS, heads)


def _verify_references(reader: Any, heads: dict[str, Any]) -> None:
    for field in ("latest", "latest_attempt"):
        reference = heads[field]
        if reference is None:
            continue
        snapshot = reader.open_run(
            reference["run_id"], manifest_sha256=reference["manifest_sha256"]
        )
        if field == "latest" and snapshot.manifest["status"] != "completed":
            raise IntegrityError(
                "Migration completed head must identify a completed collection"
            )


def upgrade_store_to_v3(store: str | Path) -> dict[str, Any]:
    """Explicitly migrate/resume a v2 store, preserving exact original pointers.

    Active writers are refused. Interrupted migration remains fail-closed and
    can only resume using its checked original plan; no pointer is fabricated.
    """
    from cppulse.run_store import RunStore, _directory, _read, _write_new

    root = Path(store).absolute()
    reader = RunStore.open_existing(root)
    with _directory(root) as root_fd, publication_guard(root_fd) as lease:
        if _exists(root / ".publication.lock"):
            raise PublicationConflict(
                "Cannot migrate a store with a writer lock; inspect/recover its exact owner first"
            )
        marker = protocol(root, allow_migrating=True)
        if marker is not None and marker["phase"] == "active":
            heads = read_heads(root)
            _verify_references(reader, heads)
            return heads
        if marker is None:
            originals = {}
            heads = {
                "version": "3.0.0",
                "generation": 0,
                "latest": None,
                "latest_attempt": None,
            }
            for name, field in zip(LEGACY, ("latest", "latest_attempt")):
                if _exists(root / name):
                    raw = _read(root / name, max_bytes=BUDGET)
                    snapshot = reader._resolve_pointer(
                        name, completed=field == "latest"
                    )
                    originals[name] = raw.hex()
                    heads[field] = {
                        "run_id": snapshot.run_id,
                        "manifest_sha256": snapshot.manifest_sha256,
                    }
                else:
                    originals[name] = None
            if heads["latest"] is not None and heads["latest_attempt"] is None:
                raise IntegrityError(
                    "Cannot migrate completed pointer without retained latest-attempt pointer"
                )
            plan = {"version": "3.0.0", "originals": originals, "heads": heads}
            validate_store_document("migration-v3", plan)
            # A crash before marker creation leaves a retained archive and requires
            # explicit inspection rather than overwriting an unknown prior plan.
            if not _exists(root / ARCHIVE):
                os.mkdir(ARCHIVE, mode=0o700, dir_fd=root_fd)
                os.fsync(root_fd)
            with _directory(root / ARCHIVE) as archive_fd:
                metadata = os.fstat(archive_fd)
                if (
                    metadata.st_uid != os.geteuid()
                    or stat.S_IMODE(metadata.st_mode) != 0o700
                ):
                    raise IntegrityError("Migration archive is foreign or unsafe")
                names = os.listdir(archive_fd)
                if any(name != "plan.json" for name in names):
                    raise IntegrityError(
                        "Unrecognized pre-marker migration archive content"
                    )
            if _exists(root / ARCHIVE / "plan.json"):
                if _read(root / ARCHIVE / "plan.json", max_bytes=BUDGET * 5) != _bytes(
                    plan
                ):
                    raise IntegrityError(
                        "Pre-marker migration plan does not match current original v2 pointers"
                    )
            else:
                _write_new(root / ARCHIVE / "plan.json", _bytes(plan))
            marker = {
                "version": "3.0.0",
                "phase": "migrating",
                "plan_sha256": hashlib.sha256(_bytes(plan)).hexdigest(),
            }
            validate_store_document("format-v3", marker)
            _write_new(root / FORMAT, _bytes(marker))
        with _directory(root / ARCHIVE) as archive_fd:
            metadata = os.fstat(archive_fd)
            if (
                metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700
            ):
                raise IntegrityError("Migration archive is foreign or unsafe")
        plan_raw = _control_bytes(root / ARCHIVE / "plan.json")
        if hashlib.sha256(plan_raw).hexdigest() != marker["plan_sha256"]:
            raise IntegrityError(
                "V3 migration original plan changed; preserve and inspect archive"
            )
        plan = _document(root / ARCHIVE / "plan.json")
        validate_store_document("migration-v3", plan)
        _verify_references(reader, plan["heads"])
        for name in LEGACY:
            lease.check()
            path = root / name
            if _exists(path):
                metadata = path.lstat()
                if stat.S_ISDIR(metadata.st_mode):
                    continue
                original = plan["originals"][name]
                if original is None or _read(path, max_bytes=BUDGET) != bytes.fromhex(
                    original
                ):
                    raise IntegrityError("Legacy pointer changed during v3 migration")
                os.unlink(name, dir_fd=root_fd)
                os.fsync(root_fd)
            os.mkdir(name, mode=0o700, dir_fd=root_fd)
            os.fsync(root_fd)
        _fences(root)
        if _exists(root / HEADS):
            if _document(root / HEADS) != plan["heads"]:
                raise IntegrityError(
                    "Interrupted migration heads differ from pinned original plan"
                )
        else:
            _write_new(root / HEADS, _bytes(plan["heads"]))
        lease.check()
        _verify_references(reader, plan["heads"])
        marker = deepcopy(marker)
        marker["phase"] = "active"
        _replace(root, FORMAT, marker)
        return read_heads(root)


def export_store_v2(store: str | Path, destination: str | Path) -> dict[str, Any]:
    """Export one checked v3 epoch to a distinct new v2 directory.

    Original manifest/artifact bytes are copied and checked. Failure preserves
    incomplete output for inspection; pointers are written only after all run
    bytes verify. This is an explicit historical snapshot, not a live mirror.
    """
    from cppulse.run_store import RunStore, _copy_new, _directory, _read, _write_new

    root = Path(store).absolute()
    output = Path(destination).absolute()
    if output.is_relative_to(root) or root.is_relative_to(output):
        raise PublicationConflict(
            "V2 export must use a separate directory outside the source store"
        )
    reader = RunStore.open_existing(root)
    generation, completed, attempt = reader.resolve_heads()
    with _directory(output.parent) as parent:
        try:
            os.mkdir(output.name, mode=0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError as exc:
            raise PublicationConflict(
                "V2 export destination must not already exist"
            ) from exc
    exported = RunStore(output, format_version="2.0.0")
    snapshots = {
        snapshot.run_id: snapshot
        for snapshot in (completed, attempt)
        if snapshot is not None
    }
    for snapshot in snapshots.values():
        base = output / "runs" / snapshot.run_id
        with _directory(base, create=True):
            pass
        for artifact in snapshot.manifest["artifacts"]:
            size, digest = _copy_new(
                root / "runs" / snapshot.run_id / artifact["path"],
                base / artifact["path"],
            )
            if size != artifact["size_bytes"] or digest != artifact["sha256"]:
                raise IntegrityError(
                    "V2 export source artifact changed from selected head epoch"
                )
        manifest = _read(root / "runs" / snapshot.run_id / "run_manifest.json")
        if hashlib.sha256(manifest).hexdigest() != snapshot.manifest_sha256:
            raise IntegrityError(
                "V2 export source manifest changed from selected head epoch"
            )
        _write_new(base / "run_manifest.json", manifest)
        exported.open_run(snapshot.run_id, manifest_sha256=snapshot.manifest_sha256)
    # This directory is an offline export. Its two legacy pointers cannot be
    # mistaken for a live v3 publication authority or a supported old-writer lane.
    if attempt is not None:
        exported._publish_pointer(attempt, "latest_attempt.json")
    if completed is not None:
        exported._publish_pointer(completed, "latest.json")
    report = {
        "version": "1.0.0",
        "source_store": str(root),
        "destination": str(output),
        "source_generation": generation,
        "scope": "explicit_offline_v2_snapshot",
        "latest": (
            None
            if completed is None
            else {
                "run_id": completed.run_id,
                "manifest_sha256": completed.manifest_sha256,
            }
        ),
        "latest_attempt": (
            None
            if attempt is None
            else {"run_id": attempt.run_id, "manifest_sha256": attempt.manifest_sha256}
        ),
    }
    _write_new(output / "v3-export.json", _bytes(report))
    return report
