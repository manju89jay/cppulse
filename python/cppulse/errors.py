"""Structured failures shared by cppulse contracts and local persistence."""

from __future__ import annotations

from typing import Any


class CppulseError(ValueError):
    """Base error with stable code and an optional JSON pointer or local path."""

    default_code = "CPPULSE_ERROR"

    def __init__(
        self, message: str, *, code: str | None = None, path: str = ""
    ) -> None:
        super().__init__(message)
        self.code = code or self.default_code
        self.path = path

    def as_dict(self) -> dict[str, Any]:
        """Return a transport-neutral diagnostic without stack/environment data."""
        return {"code": self.code, "message": str(self), "path": self.path}


class ContractError(CppulseError):
    """A document violates its structural or semantic contract."""

    default_code = "INVALID_CONTRACT"


class UnsupportedVersion(ContractError):
    """A requested contract version is unavailable locally."""

    default_code = "UNSUPPORTED_VERSION"


class CompatibilityError(ContractError):
    """A conversion cannot preserve the requested contract's semantics."""

    default_code = "INCOMPATIBLE_CONTRACT"


class InputChanged(CppulseError):
    """Selected inputs no longer match the recorded source snapshot."""

    default_code = "INPUT_CHANGED"


class IntegrityError(CppulseError):
    """A persisted artifact is missing, unsafe or differs from its digest."""

    default_code = "INTEGRITY_ERROR"


class PublicationConflict(CppulseError):
    """A run ID or publication slot is already owned by another writer."""

    default_code = "PUBLICATION_CONFLICT"
