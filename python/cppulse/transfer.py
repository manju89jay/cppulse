"""Bounded, byte-preserving directory transfer of unauthenticated foreign runs.

Checksums establish consistency with the supplied descriptor, not who produced
it. Readers retain checked byte buffers and never initialize a RunStore, execute
a tool, refresh source identities or change publication pointers. Publication is
qualified for Linux/POSIX and requires atomic no-replace rename support.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from copy import deepcopy
import ctypes
from dataclasses import asdict, dataclass, field
import errno
import hashlib
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import stat
from types import MappingProxyType
from typing import Any, ClassVar
from uuid import uuid4

from cppulse.contracts import validate, validate_bundle
from cppulse.errors import ContractError, IntegrityError, PublicationConflict
from cppulse.run_store import Contract, RunSnapshot

_DESCRIPTOR = "transfer_bundle.json"
_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_HARD_LIMITS = {
    "max_files": 10000,
    "max_file_bytes": 256 * 1024 * 1024,
    "max_total_bytes": 1024 * 1024 * 1024,
    "max_metadata_bytes": 16 * 1024 * 1024,
}


@dataclass(frozen=True)
class TransferLimits:
    """Caller-controlled payload caps; descriptor metadata has a separate cap."""

    max_files: int = 10000
    max_file_bytes: int = 256 * 1024 * 1024
    max_total_bytes: int = 1024 * 1024 * 1024
    max_metadata_bytes: int = 4 * 1024 * 1024

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not 1 <= value <= _HARD_LIMITS[name]
            ):
                raise ContractError(
                    f"{name} must be an integer from 1 to {_HARD_LIMITS[name]}"
                )


def _hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _relative(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or path.is_absolute()
        or PureWindowsPath(value).drive
        or ".." in path.parts
        or path.as_posix() != value
        or value == "."
        or len(path.parts) > 64
    ):
        raise IntegrityError(f"Unsafe or excessively deep transfer path: {value!r}")
    return value


@contextmanager
def _directory(path: Path, *, create: bool = False) -> Iterator[int]:
    descriptor = os.open(path.absolute().anchor, os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.absolute().parts[1:]:
            if part == "..":
                raise IntegrityError("Transfer directories cannot contain traversal")
            try:
                child = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, mode=0o700, dir_fd=descriptor)
                os.fsync(descriptor)
                child = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
            os.close(descriptor)
            descriptor = child
        yield descriptor
    except OSError as error:
        raise IntegrityError(
            f"Unsafe or inaccessible transfer directory: {path}"
        ) from error
    finally:
        os.close(descriptor)


def _read(path: Path, limit: int) -> bytes:
    try:
        with _directory(path.parent) as parent:
            return _read_at(parent, path.name, limit)
    except OSError as error:
        raise IntegrityError(
            f"Missing, unsafe or unreadable transfer file: {path}"
        ) from error


def _read_at(directory: int, path: str, limit: int) -> bytes:
    parts = PurePosixPath(_relative(path)).parts
    parent = os.dup(directory)
    try:
        for part in parts[:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
            )
            os.close(parent)
            parent = child
        descriptor = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
        )
        with os.fdopen(descriptor, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode):
                raise IntegrityError(f"Transfer input is not a regular file: {path}")
            if before.st_size > limit:
                raise IntegrityError(f"Transfer file exceeds its byte bound: {path}")
            content = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            if len(content) > limit:
                raise IntegrityError(
                    f"Transfer file grew beyond its byte bound: {path}"
                )
            if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_size,
                after.st_mtime_ns,
                after.st_ctime_ns,
            ):
                raise IntegrityError(f"Transfer input changed while reading: {path}")
            return content
    except OSError as error:
        raise IntegrityError(
            f"Missing, unsafe or unreadable transfer file: {path}"
        ) from error
    finally:
        os.close(parent)


def _object(content: bytes, name: str, limit: int) -> dict[str, Any]:
    if len(content) > limit:
        raise IntegrityError(f"Transfer metadata exceeds its byte bound: {name}")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"Duplicate JSON key {key!r}")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise ValueError(f"Non-finite JSON constant: {value}")

    try:
        document = json.loads(content, object_pairs_hook=pairs, parse_constant=constant)
        # Reject overflowed floating literals too; parse_constant sees NaN only.
        json.dumps(document, allow_nan=False)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise IntegrityError(f"Invalid bounded JSON metadata: {name}") from error
    if not isinstance(document, dict):
        raise IntegrityError(f"Transfer metadata must be a JSON object: {name}")
    return document


def _json(content: dict[str, Any]) -> bytes:
    try:
        return (
            json.dumps(
                content, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
            )
            + "\n"
        ).encode("utf-8")
    except (ValueError, TypeError) as error:
        raise ContractError("Transfer metadata must be finite JSON") from error


def _effective(document: dict[str, Any], limits: TransferLimits) -> TransferLimits:
    return TransferLimits(
        **{
            name: min(value, document["limits"][name])
            for name, value in asdict(limits).items()
        }
    )


def _caps(files: list[dict[str, Any]], limits: TransferLimits) -> None:
    if len(files) > limits.max_files:
        raise IntegrityError("Transfer payload exceeds the local file count cap")
    if sum(entry["size_bytes"] for entry in files) > limits.max_total_bytes:
        raise IntegrityError("Transfer payload exceeds the local total byte cap")
    if any(entry["size_bytes"] > limits.max_file_bytes for entry in files):
        raise IntegrityError("Transfer payload exceeds the local per-file byte cap")


def _reference(contract: Contract, document: dict[str, Any]) -> dict[str, str]:
    if isinstance(contract, str):
        result = {"kind": contract, "version": document.get("version", "2.0.0")}
    elif isinstance(contract, tuple) and len(contract) == 2:
        result = {"kind": contract[0], "version": contract[1]}
    elif isinstance(contract, dict) and set(contract) == {"kind", "version"}:
        result = contract
    else:
        raise ContractError("JSON reads need a declared kind and contract version")
    validate(result["kind"], document, version=result["version"])
    return result


def _validate_root(
    root: dict[str, Any],
    manifest_bytes: bytes,
    artifacts: Mapping[str, bytes],
    limits: TransferLimits,
) -> dict[str, Any]:
    if _hash(manifest_bytes) != root["manifest_sha256"]:
        raise IntegrityError("Transferred root manifest digest disagrees")
    manifest = _object(manifest_bytes, root["manifest_path"], limits.max_metadata_bytes)
    validate("run_manifest", manifest)
    if (
        manifest["run_id"] != root["run_id"]
        or manifest["source"]["digest"] != root["source_digest"]
    ):
        raise IntegrityError("Transferred root source/run identity disagrees")
    declared = {_relative(entry["path"]): entry for entry in manifest["artifacts"]}
    if set(declared) != set(artifacts):
        raise IntegrityError(
            "Transferred payload differs from the root's artifact inventory"
        )
    bundle: dict[str, Any] = {"run_manifest": manifest}
    for path, entry in declared.items():
        content = artifacts[path]
        if len(content) != entry["size_bytes"] or _hash(content) != entry["sha256"]:
            raise IntegrityError(f"Transferred artifact digest/size mismatch: {path}")
        if len(content) > limits.max_file_bytes:
            raise IntegrityError(f"Transferred artifact exceeds local byte cap: {path}")
        if "contract" not in entry:
            continue
        document = _object(content, path, limits.max_metadata_bytes)
        reference = _reference(entry["contract"], document)
        if reference["version"] != "2.0.0":
            continue
        kind = reference["kind"]
        if kind == "run_manifest":
            raise ContractError(
                "A transferred root cannot contain a second run manifest"
            )
        if kind == "policy":
            if kind in bundle:
                raise ContractError("A transferred root can bind only one policy")
            bundle[kind] = document
        else:
            bundle.setdefault(kind, []).append(document)
    validate_bundle(bundle)
    return manifest


@dataclass(frozen=True)
class ImportedRun:
    """Frozen checked foreign bytes; original verification flags remain claims."""

    root_id: str
    run_id: str
    manifest_sha256: str
    _root: dict[str, Any] = field(repr=False)
    _manifest_bytes: bytes = field(repr=False)
    _artifacts: Mapping[str, bytes] = field(repr=False)
    _limits: TransferLimits = field(repr=False)
    origin: ClassVar[str] = "import"
    authentication: ClassVar[str] = "unverified"
    source_freshness: ClassVar[str] = "not_rechecked"

    @property
    def manifest(self) -> dict[str, Any]:
        """Return original manifest claims without changing their byte identity."""
        return _object(
            self._manifest_bytes, "run_manifest.json", self._limits.max_metadata_bytes
        )

    def read_manifest_bytes(self) -> bytes:
        """Return exact frozen foreign manifest bytes bound to manifest_sha256."""
        return self._manifest_bytes

    def _entry(self, name: str) -> dict[str, Any]:
        entries = [
            entry
            for entry in self.manifest["artifacts"]
            if name in {entry["id"], entry["path"]}
        ]
        if len(entries) != 1:
            raise IntegrityError(f"Imported artifact is absent or ambiguous: {name!r}")
        return entries[0]

    def read_bytes(self, name: str) -> bytes:
        """Return the immutable byte buffer checked when this import was opened."""
        return self._artifacts[self._entry(name)["path"]]

    def read_json(
        self, name: str, *, contract: Contract | None = None
    ) -> dict[str, Any]:
        """Read and validate checked JSON; this never authenticates its producer."""
        entry = self._entry(name)
        document = _object(
            self.read_bytes(name), entry["path"], self._limits.max_metadata_bytes
        )
        reference = entry.get("contract") if contract is None else contract
        if reference is None:
            raise ContractError("Imported JSON needs an explicit or declared contract")
        _reference(reference, document)
        return document

    def verify(self) -> None:
        """Revalidate frozen buffers, not the mutable input directory."""
        _validate_root(self._root, self._manifest_bytes, self._artifacts, self._limits)


@dataclass(frozen=True)
class TransferBundle:
    """A bounded directory import with explicit unauthenticated provenance."""

    path: Path
    _descriptor: bytes = field(repr=False)
    _payload: Mapping[str, bytes] = field(repr=False)
    _runs: Mapping[str, ImportedRun] = field(repr=False)
    _limits: TransferLimits = field(repr=False)

    @property
    def metadata(self) -> dict[str, Any]:
        """Return an independent copy of the checked transfer descriptor."""
        return _object(self._descriptor, _DESCRIPTOR, self._limits.max_metadata_bytes)

    @property
    def root_ids(self) -> tuple[str, ...]:
        """Return deterministic labels for separately retained source/run roots."""
        return tuple(sorted(self._runs))

    def open_run(self, root_id: str) -> ImportedRun:
        """Select one imported root without initializing a writable RunStore."""
        if root_id not in self._runs:
            raise IntegrityError(f"Unknown transferred root: {root_id!r}")
        return self._runs[root_id]

    def verify(self) -> None:
        """Verify frozen descriptor, inventories, contracts and raw byte digests."""
        _bundle(self.path, self._descriptor, self._payload, self._limits)


def _bundle(
    path: Path,
    descriptor: bytes,
    payload: Mapping[str, bytes],
    limits: TransferLimits,
) -> TransferBundle:
    document = _object(descriptor, _DESCRIPTOR, limits.max_metadata_bytes)
    validate("transfer_bundle", document)
    effective = _effective(document, limits)
    if len(descriptor) > effective.max_metadata_bytes:
        raise IntegrityError("Transfer descriptor exceeds its declared metadata bound")
    _caps(document["files"], effective)
    expected = {entry["path"] for entry in document["files"]}
    if expected != set(payload):
        raise IntegrityError("Transfer file inventory differs from checked payload")
    for entry in document["files"]:
        content = payload[entry["path"]]
        if len(content) != entry["size_bytes"] or _hash(content) != entry["sha256"]:
            raise IntegrityError(
                f"Transfer payload digest/size mismatch: {entry['path']}"
            )
    runs = {}
    for root in document["roots"]:
        prefix = f"roots/{root['id']}/runs/{root['run_id']}/"
        artifacts = {
            name[len(prefix) :]: content
            for name, content in payload.items()
            if name.startswith(prefix) and name != root["manifest_path"]
        }
        raw = payload[root["manifest_path"]]
        _validate_root(root, raw, artifacts, effective)
        runs[root["id"]] = ImportedRun(
            root["id"],
            root["run_id"],
            root["manifest_sha256"],
            deepcopy(root),
            raw,
            MappingProxyType(artifacts),
            effective,
        )
    return TransferBundle(
        path,
        descriptor,
        MappingProxyType(dict(payload)),
        MappingProxyType(runs),
        effective,
    )


def _scan_at(directory: int, entries: Mapping[str, int]) -> None:
    expected_dirs = {
        parent.as_posix()
        for name in entries
        for parent in PurePosixPath(name).parents
        if parent.as_posix() != "."
    }
    found: set[str] = set()

    def walk(directory: int, prefix: str) -> None:
        with os.scandir(directory) as children:
            for child in children:
                name = _relative(prefix + child.name)
                info = child.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    if name not in expected_dirs:
                        raise IntegrityError(f"Unlisted transfer directory: {name}")
                    descriptor = os.open(
                        child.name,
                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                        dir_fd=directory,
                    )
                    try:
                        walk(descriptor, name + "/")
                    finally:
                        os.close(descriptor)
                elif stat.S_ISREG(info.st_mode):
                    if name not in entries or info.st_size != entries[name]:
                        raise IntegrityError(
                            f"Unlisted or size-mismatched transfer file: {name}"
                        )
                    found.add(name)
                else:
                    raise IntegrityError(
                        f"Transfer contains a symlink or special file: {name}"
                    )

    try:
        walk(directory, "")
    except OSError as error:
        raise IntegrityError("Transfer directory changed or is inaccessible") from error
    if found != set(entries):
        raise IntegrityError("Transfer directory is missing declared payload files")


def _scan(path: Path, entries: Mapping[str, int]) -> None:
    with _directory(path) as directory:
        _scan_at(directory, entries)


def open_bundle(
    path: str | Path, *, limits: TransferLimits | None = None
) -> TransferBundle:
    """Read a strict directory into checked buffers without any filesystem writes.

    Caller caps cannot be raised by a foreign descriptor. The complete payload
    is bounded and retained in memory, so later input mutation cannot mix runs.
    """
    path, limits = Path(path).absolute(), limits or TransferLimits()
    raw = _read(path / _DESCRIPTOR, limits.max_metadata_bytes)
    document = _object(raw, _DESCRIPTOR, limits.max_metadata_bytes)
    validate("transfer_bundle", document)
    effective = _effective(document, limits)
    if len(raw) > effective.max_metadata_bytes:
        raise IntegrityError("Transfer descriptor exceeds its declared metadata bound")
    _caps(document["files"], effective)
    entries = {entry["path"]: entry["size_bytes"] for entry in document["files"]}
    _scan(path, {**entries, _DESCRIPTOR: len(raw)})
    # Parse bounded root manifests first: they identify which payload files are
    # contracted metadata, so an oversized JSON artifact is rejected before it
    # is read, even if the separate binary-file cap would permit it.
    payload = {}
    for root in document["roots"]:
        name = root["manifest_path"]
        content = _read(path / _relative(name), effective.max_metadata_bytes)
        manifest = _object(content, name, effective.max_metadata_bytes)
        validate("run_manifest", manifest)
        prefix = f"roots/{root['id']}/runs/{root['run_id']}/"
        for entry in manifest["artifacts"]:
            if (
                "contract" in entry
                and entry["size_bytes"] > effective.max_metadata_bytes
            ):
                raise IntegrityError("Contract JSON exceeds transfer metadata cap")
            declared = prefix + _relative(entry["path"])
            if declared not in entries or entries[declared] != entry["size_bytes"]:
                raise IntegrityError(
                    "Root artifacts disagree with the transfer inventory"
                )
        payload[name] = content
    for name, size in entries.items():
        if name not in payload:
            payload[name] = _read(path / _relative(name), size)
    _scan(path, {**entries, _DESCRIPTOR: len(raw)})
    return _bundle(path, raw, payload, effective)


def _write(directory: int, path: str, content: bytes) -> None:
    parts = PurePosixPath(_relative(path)).parts
    parent = os.dup(directory)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=parent)
                os.fsync(parent)
            except FileExistsError:
                pass
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
            )
            os.close(parent)
            parent = child
        descriptor = os.open(
            parts[-1],
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.fsync(parent)
    finally:
        os.close(parent)


def _commit(parent: int, staging: str, destination: str) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    rename = getattr(library, "renameat2", None)
    if rename is None:
        raise IntegrityError("Atomic no-replace directory publication is unsupported")
    rename.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    rename.restype = ctypes.c_int
    if rename(parent, os.fsencode(staging), parent, os.fsencode(destination), 1) != 0:
        code = ctypes.get_errno()
        if code in {errno.EEXIST, errno.ENOTEMPTY}:
            raise PublicationConflict("Transfer destination already exists")
        if code in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP}:
            raise IntegrityError(
                "Atomic no-replace directory publication is unsupported"
            )
        raise IntegrityError(f"Atomic transfer publication failed: {os.strerror(code)}")


def _publish(bundle: TransferBundle, destination: Path) -> TransferBundle:
    with _directory(destination.parent, create=True) as parent:
        staging = ".cppulse-transfer-" + uuid4().hex
        os.mkdir(staging, mode=0o700, dir_fd=parent)
        descriptor = os.open(
            staging, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
        )
        committed = False
        try:
            for path, content in sorted(bundle._payload.items()):
                _write(descriptor, path, content)
            _write(descriptor, _DESCRIPTOR, bundle._descriptor)
            written = {**bundle._payload, _DESCRIPTOR: bundle._descriptor}
            _scan_at(
                descriptor, {name: len(content) for name, content in written.items()}
            )
            for name, content in written.items():
                if _read_at(descriptor, name, len(content)) != content:
                    raise IntegrityError(
                        f"Staged transfer copy differs from checked bytes: {name}"
                    )
            os.fsync(descriptor)
            _commit(parent, staging, destination.name)
            committed = True
            os.fsync(parent)
        finally:
            os.close(descriptor)
            if not committed:
                shutil.rmtree(staging, dir_fd=parent)
    return _bundle(destination, bundle._descriptor, bundle._payload, bundle._limits)


def _outside(destination: Path, roots: list[Path]) -> None:
    if any(destination.is_relative_to(root.absolute()) for root in roots):
        raise IntegrityError(
            "Transfer destination cannot be inside an input snapshot/bundle"
        )


def export_bundle(
    roots: Mapping[str, RunSnapshot],
    destination: str | Path,
    *,
    bundle_id: str | None = None,
    limits: TransferLimits | None = None,
) -> TransferBundle:
    """Export checked local snapshots as a new unauthenticated transfer directory.

    Raw manifests and artifacts remain byte-identical. No source inspection,
    execution, authentication, publication pointer or local run is created.
    """
    destination, limits = Path(destination).absolute(), limits or TransferLimits()
    if not roots or any(
        not isinstance(snapshot, RunSnapshot) for snapshot in roots.values()
    ):
        raise ContractError("Export requires named local RunSnapshot inputs")
    if any(
        not isinstance(label, str) or not _LABEL.fullmatch(label) for label in roots
    ):
        raise ContractError(
            "Transfer root labels must be canonical run-like identifiers"
        )
    _outside(destination, [snapshot.path for snapshot in roots.values()])
    payload: dict[str, bytes] = {}
    files, root_entries = [], []
    for label, snapshot in sorted(roots.items()):
        raw = _read(snapshot.path / "run_manifest.json", limits.max_metadata_bytes)
        if _hash(raw) != snapshot.manifest_sha256:
            raise IntegrityError("Source run manifest changed before export")
        manifest = _object(raw, "run_manifest.json", limits.max_metadata_bytes)
        validate("run_manifest", manifest)
        prefix = f"roots/{label}/runs/{snapshot.run_id}/"
        root = {
            "id": label,
            "run_id": snapshot.run_id,
            "manifest_path": prefix + "run_manifest.json",
            "manifest_sha256": snapshot.manifest_sha256,
            "source_digest": manifest["source"]["digest"],
        }
        root_entries.append(root)
        root_files = [
            {
                "path": root["manifest_path"],
                "sha256": _hash(raw),
                "size_bytes": len(raw),
            }
        ]
        root_files.extend(
            {
                "path": prefix + _relative(entry["path"]),
                "sha256": entry["sha256"],
                "size_bytes": entry["size_bytes"],
            }
            for entry in manifest["artifacts"]
        )
        _caps(files + root_files, limits)
        payload[root["manifest_path"]] = raw
        for entry in manifest["artifacts"]:
            if "contract" in entry and entry["size_bytes"] > limits.max_metadata_bytes:
                raise IntegrityError("Contract JSON exceeds transfer metadata cap")
            payload[prefix + entry["path"]] = _read(
                snapshot.path / entry["path"], entry["size_bytes"]
            )
        files.extend(root_files)
    document = {
        "version": "2.0.0",
        "id": bundle_id or uuid4().hex,
        "origin": "import",
        "authentication": "unverified",
        "limits": asdict(limits),
        "files": sorted(files, key=lambda entry: entry["path"]),
        "roots": root_entries,
        "limitations": [
            "Checksums detect disagreement with this descriptor; they do not authenticate a producer or protect against a rewritten descriptor.",
            "Original source verification, execution and assessment fields are retained foreign claims; no source freshness was rechecked and no tools were executed.",
        ],
    }
    bundle = _bundle(destination, _json(document), payload, limits)
    return _publish(bundle, destination)


def copy_bundle(
    source: str | Path | TransferBundle,
    destination: str | Path,
    *,
    limits: TransferLimits | None = None,
) -> TransferBundle:
    """Copy checked foreign buffers to a new standalone directory, without reuse.

    This is an archival import, not RunStore publication or policy evaluation.
    The original descriptor and all raw payload bytes remain unchanged.
    """
    bundle = (
        source
        if isinstance(source, TransferBundle)
        else open_bundle(source, limits=limits)
    )
    destination = Path(destination).absolute()
    _outside(destination, [bundle.path])
    checked = _bundle(
        bundle.path, bundle._descriptor, bundle._payload, limits or bundle._limits
    )
    return _publish(checked, destination)


import_bundle = copy_bundle
