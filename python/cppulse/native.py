"""Discover a declared native analyzer without executing it or guessing source paths.

Installation metadata identifies selected paths and optional executable bytes.
Discovery does not qualify the host loader or authenticate the installer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import stat
import sys
from typing import Any

from cppulse import __version__
from cppulse.contracts import validate
from cppulse.errors import CppulseError, UnsupportedVersion

_METADATA = "share/cppulse/native-install.json"
_MACHINE_ALIASES = {
    "amd64": "x86_64",
    "x64": "x86_64",
    "x86_64": "x86_64",
    "arm64": "aarch64",
    "aarch64": "aarch64",
}


@dataclass(frozen=True)
class NativeInstallation:
    """Selected native paths and inspection limitations, with no executable action.

    Paths returned by discovery are absolute. A standalone analyzer lacks the
    version, target and library declarations of an installation manifest.
    """

    analyzer: Path
    resource_dir: Path | None
    library_dirs: tuple[Path, ...]
    metadata: Path | None
    limitations: tuple[str, ...] = ()

    def environment(self, baseenv: Mapping[str, str] | None = None) -> dict[str, str]:
        """Copy a child environment and select only this installation's paths.

        Inherited loader and cppulse builtin-header overrides are removed. On
        Windows, selected DLL directories precede the existing executable PATH;
        Linux/macOS use a replacement loader path. The caller's environment is
        never modified, and no source-checkout paths are introduced.
        """
        environment = dict(os.environ if baseenv is None else baseenv)
        for name in [
            "LD_LIBRARY_PATH",
            "DYLD_LIBRARY_PATH",
            "CPPULSE_CLANG_RESOURCE_DIR",
        ]:
            environment.pop(name, None)
        if self.resource_dir is not None:
            environment["CPPULSE_CLANG_RESOURCE_DIR"] = str(self.resource_dir)
        if self.library_dirs:
            libraries = os.pathsep.join(str(path) for path in self.library_dirs)
            if sys.platform == "win32":
                current = environment.get("PATH", "")
                environment["PATH"] = (
                    libraries + os.pathsep + current if current else libraries
                )
            else:
                name = (
                    "DYLD_LIBRARY_PATH"
                    if sys.platform == "darwin"
                    else "LD_LIBRARY_PATH"
                )
                environment[name] = libraries
        return environment


def _error(message: str, path: Path | str = "") -> CppulseError:
    return CppulseError(message, code="INVALID_NATIVE_INSTALL", path=str(path))


def _setting(name: str) -> str | None:
    if name not in os.environ:
        return None
    value = os.environ[name]
    if not value.strip():
        raise _error(f"{name} must name an existing path, not an empty value")
    return value


def _directory(value: Path | str) -> Path:
    try:
        path = Path(value).expanduser().resolve(strict=True)
        if not path.is_dir():
            raise _error("Native installation directory is not a directory", value)
        return path
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, CppulseError):
            raise
        raise _error(
            f"Native directory is missing or inaccessible: {exc}", value
        ) from exc


def _within(prefix: Path, relative: str, *, directory: bool) -> Path:
    """Check each declared prefix-relative entry without accepting symlinks."""
    selected = prefix
    try:
        for part in PurePosixPath(relative).parts:
            selected = selected / part
            if stat.S_ISLNK(selected.lstat().st_mode):
                raise _error(
                    "Symlink native installation paths are not allowed", selected
                )
        physical = selected.resolve(strict=True)
        if not physical.is_relative_to(prefix):
            raise _error("Native installation path escapes its prefix", selected)
        expected = physical.is_dir() if directory else physical.is_file()
        if not expected:
            kind = "directory" if directory else "regular file"
            raise _error(f"Native installation path must be a {kind}", selected)
        return physical
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, CppulseError):
            raise
        raise _error(
            f"Native installation path is unavailable: {exc}", selected
        ) from exc


def _executable(path: Path) -> Path:
    try:
        selected = path.expanduser().resolve(strict=True)
        if not selected.is_file() or not os.access(selected, os.X_OK):
            raise _error(
                "Selected native analyzer must be an executable regular file", path
            )
        return selected
    except (OSError, RuntimeError, ValueError) as exc:
        if isinstance(exc, CppulseError):
            raise
        raise _error(
            f"Selected native analyzer is missing or inaccessible: {exc}", path
        ) from exc


def _resource_directory(value: Path | str) -> Path:
    directory = _directory(value)
    try:
        _within(directory, "include/stddef.h", directory=False)
    except CppulseError as exc:
        raise _error(
            "Native resource directory requires a regular include/stddef.h without symlinks",
            directory,
        ) from exc
    return directory


def _sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            while content := stream.read(1024 * 1024):
                hasher.update(content)
    except OSError as exc:
        raise _error(f"Cannot read native analyzer checksum: {exc}", path) from exc
    return hasher.hexdigest()


def _machine(value: str) -> str:
    spelling = value.casefold()
    return _MACHINE_ALIASES.get(spelling, spelling)


def _from_prefix(value: Path | str) -> NativeInstallation:
    prefix = _directory(value)
    metadata = _within(prefix, _METADATA, directory=False)
    try:
        document: dict[str, Any] = json.loads(metadata.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise _error(
            f"Cannot read native installation metadata: {exc}", metadata
        ) from exc
    validate("native_install", document)
    if document["tool_version"] != __version__:
        raise UnsupportedVersion(
            f"Native tool version {document['tool_version']!r} does not match cppulse "
            f"{__version__!r}; install a matching native bundle",
            path=str(metadata),
        )
    target = document["target"]
    if target["platform"] != sys.platform or _machine(target["machine"]) != _machine(
        platform.machine()
    ):
        raise CppulseError(
            f"Native target {target['platform']}/{target['machine']} does not match "
            f"this host {sys.platform}/{platform.machine()}",
            code="NATIVE_TARGET_MISMATCH",
            path=str(metadata),
        )
    analyzer = _executable(_within(prefix, document["analyzer"], directory=False))
    resource_dir = _resource_directory(
        _within(prefix, document["resource_dir"], directory=True)
    )
    libraries = tuple(
        _within(prefix, relative, directory=True)
        for relative in document["library_dirs"]
    )
    limitations = list(document["limitations"])
    if "analyzer_sha256" in document:
        if _sha256(analyzer) != document["analyzer_sha256"]:
            raise CppulseError(
                "Native analyzer checksum differs from installation metadata",
                code="NATIVE_CHECKSUM_MISMATCH",
                path=str(analyzer),
            )
    else:
        limitations.append(
            "Installation metadata does not supply an analyzer checksum."
        )
    limitations.append(
        "Host requirements are declarations; discovery does not test dynamic loading."
    )
    return NativeInstallation(
        analyzer, resource_dir, libraries, metadata, tuple(limitations)
    )


def _standalone(path: Path) -> NativeInstallation:
    return NativeInstallation(
        _executable(path),
        None,
        (),
        None,
        (
            "Standalone analyzer has no installation metadata: tool version, target, "
            "runtime libraries and checksum are unverified.",
            "No builtin resource directory was declared; header parsing may be incomplete.",
        ),
    )


def discover_native() -> NativeInstallation:
    """Select the native analyzer using strict, transparent installation precedence.

    CPPULSE_ANALYZER wins, followed by CPPULSE_NATIVE_PREFIX metadata, metadata
    beneath sys.prefix, then cppulse-analyzer on PATH. Invalid explicit settings
    and invalid existing installation manifests fail instead of falling back.
    CPPULSE_CLANG_RESOURCE_DIR is an optional validated explicit override.

    Returns:
        Absolute selected paths and limitations, without executing the analyzer.

    Raises:
        CppulseError: If a setting, manifest, target or installed input is invalid,
            or no analyzer can be found.
        UnsupportedVersion: If the contract or native tool version is unsupported.
    """
    analyzer = _setting("CPPULSE_ANALYZER")
    prefix = _setting("CPPULSE_NATIVE_PREFIX") if analyzer is None else None
    resource_override = _setting("CPPULSE_CLANG_RESOURCE_DIR")
    if analyzer is not None:
        selected = _standalone(Path(analyzer))
    elif prefix is not None:
        selected = _from_prefix(prefix)
    else:
        metadata = Path(sys.prefix) / _METADATA
        if metadata.exists() or metadata.is_symlink():
            selected = _from_prefix(sys.prefix)
        else:
            found = shutil.which("cppulse-analyzer")
            if found is None:
                raise CppulseError(
                    "Native analyzer not found; install its bundle or set "
                    "CPPULSE_NATIVE_PREFIX or CPPULSE_ANALYZER explicitly",
                    code="NATIVE_NOT_FOUND",
                )
            selected = _standalone(Path(found))
    if resource_override is not None:
        limitations = tuple(
            value
            for value in selected.limitations
            if not value.startswith("No builtin resource directory")
        ) + (
            "Builtin resources use an explicit override; installation metadata does "
            "not identify these resource bytes.",
        )
        selected = NativeInstallation(
            selected.analyzer,
            _resource_directory(resource_override),
            selected.library_dirs,
            selected.metadata,
            limitations,
        )
    return selected
