"""A bounded ordered identity census over caller-owned lazy metric rows."""
# Exact finite declarations intentionally exclude bool/subclasses.
# ruff: noqa: E721
from __future__ import annotations

from collections.abc import Mapping, Sequence

from cppulse.errors import ContractError


class MetricRowIndex(Mapping[str, dict]):
    """Keep ordinals only; row payloads are redecoded by their owning Sequence.

    Lookup checks current normalized identity, not schema, source authenticity or
    arbitrary payload immutability. The caller owns row validation and lifetime.
    """

    def __init__(
        self, rows, identity, *, max_files=100000, max_identity_bytes=16 * 1024**2
    ):
        if any(
            type(v) is not int or not 1 <= v <= 2**63 - 1
            for v in (max_files, max_identity_bytes)
        ):
            raise ContractError(
                "Metric index budgets require finite exact positive integers"
            )
        if (
            not isinstance(rows, Sequence)
            or isinstance(rows, (str, bytes, bytearray))
            or not callable(identity)
        ):
            raise ContractError(
                "Metric index requires a random-access Sequence and identity callback"
            )
        count = len(rows)
        if count > max_files:
            raise ContractError("Metric index file count exceeds budget")
        self._rows = rows
        self._identity = identity
        self._ordinals = {}
        self._max_identity_bytes = max_identity_bytes
        metadata = 0
        for ordinal in range(count):
            row = rows[ordinal]
            key = self._key(row)
            if len(key) > max_identity_bytes - metadata:
                raise ContractError("Metric index identity byte budget exceeded")
            metadata += len(key.encode("utf-8", errors="strict"))
            if metadata > max_identity_bytes:
                raise ContractError("Metric index identity UTF8 byte budget exceeded")
            if key in self._ordinals:
                raise ContractError("Duplicate normalized metric row identity")
            self._ordinals[key] = ordinal
            row = None
        if len(rows) != count:
            raise ContractError("Metric row Sequence size changed during indexing")

    def _key(self, row):
        if not isinstance(row, dict) or type(row.get("path")) is not str:
            raise ContractError("Metric row requires a literal path string")
        key = self._identity(row["path"])
        if type(key) is not str:
            raise ContractError("Metric identity callback must return a literal string")
        if len(key) > self._max_identity_bytes:
            raise ContractError("Metric normalized identity exceeds byte budget")
        try:
            key.encode("utf-8", errors="strict")
        except UnicodeError as error:
            raise ContractError(
                "Metric normalized identity contains invalid Unicode"
            ) from error
        return key

    def __len__(self):
        return len(self._ordinals)

    def __iter__(self):
        return iter(self._ordinals)

    def __getitem__(self, key):
        ordinal = self._ordinals[key]
        row = self._rows[ordinal]
        if self._key(row) != key:
            raise ContractError("Metric row normalized identity changed after indexing")
        return row
