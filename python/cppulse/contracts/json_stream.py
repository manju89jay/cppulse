"""Private bounded JSON-array stream contract for derived result indexes.

Yielded item bytes are provisional until the iterator finishes successfully:
the complete JSON structure, end-of-file and original SHA/size must all pass.
An index consumer must use a transaction and publish only after full iteration.
Parsing alone does not validate a report schema or authenticate its producer.
"""
from __future__ import annotations

from dataclasses import dataclass

from cppulse.errors import ContractError

VERSION = "0.1.0"


@dataclass(frozen=True)
class JsonStreamLimits:
    """Finite logical budgets, independent of a file's declared size.

    Buffers, token strings, selected item bytes and simultaneously live object
    keys are bounded independently. Counters include ignored metadata. JSON
    numbers retain their source lexemes; semantic numeric validation belongs
    to the consuming report contract.
    """

    max_bytes: int = 1024**3
    chunk_bytes: int = 16 * 1024
    max_token_bytes: int = 64 * 1024
    max_item_bytes: int = 1024**2
    max_depth: int = 64
    max_object_members: int = 32768
    max_live_key_bytes: int = 512 * 1024
    max_key_bytes: int = 1024
    max_array_items: int = 2_000_000
    max_records: int = 1_000_000

    def validate(self) -> None:
        """Refuse coercion and budgets that exceed this implementation profile."""
        bounds = {
            "max_bytes": 16 * 1024**3,
            "chunk_bytes": 1024**2,
            "max_token_bytes": 8 * 1024**2,
            "max_item_bytes": 32 * 1024**2,
            "max_depth": 128,
            "max_object_members": 100_000,
            "max_live_key_bytes": 8 * 1024**2,
            "max_key_bytes": 8192,
            "max_array_items": 10_000_000,
            "max_records": 10_000_000,
        }
        for name, bound in bounds.items():
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= bound:  # noqa: E721 -- exact count, no bool/subclass coercion
                raise ContractError(f"Unsupported JSON stream budget: {name}")
