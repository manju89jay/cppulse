"""Deterministic measurements from retained native token and metric facts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DuplicateCount:
    """Union of token occurrences and physical lines in exact repeated runs."""

    tokens: int | None
    lines: int | None
    limitations: tuple[str, ...] = ()


def duplicate_token_counts(
    streams: dict[str, dict[str, Any]], *, minimum_tokens: int = 30
) -> dict[str, DuplicateCount]:
    """Count exact kind/spelling runs with at least two disjoint occurrences.

    Truncated or unavailable peers make the entire selected scope unknown.
    Overlapping windows extend a repeated run but do not establish an independent
    second occurrence within one file. No whitespace or identifier normalization
    is performed.
    """
    if minimum_tokens != 30:
        raise ValueError("The published duplication profile requires thirty tokens")
    if any(
        not row.get("complete") or row.get("availability") != "measured"
        for row in streams.values()
    ):
        return {
            file: DuplicateCount(None, None, ("Selected token scope is incomplete.",))
            for file in streams
        }
    windows: dict[tuple[tuple[str, str], ...], list[tuple[str, int]]] = {}
    for file in sorted(streams):
        records = streams[file]["records"]
        tokens = [(row["kind"], row["spelling"]) for row in records]
        for index in range(len(tokens) - minimum_tokens + 1):
            windows.setdefault(
                tuple(tokens[index : index + minimum_tokens]), []
            ).append((file, index))
    matched: dict[str, set[int]] = {file: set() for file in streams}
    for occurrences in windows.values():
        if len(occurrences) < 2:
            continue
        # Same-file occurrences must be disjoint; a run cannot duplicate itself.
        for file, index in occurrences:
            if any(
                peer != file or abs(other - index) >= minimum_tokens
                for peer, other in occurrences
            ):
                matched[file].update(range(index, index + minimum_tokens))
    result = {}
    for file, indices in matched.items():
        lines: set[int] = set()
        for index in indices:
            record = streams[file]["records"][index]
            end_line = record["end_line"] - int(
                record["end_line"] > record["line"] and record["end_column"] == 1
            )
            lines.update(range(record["line"], end_line + 1))
        result[file] = DuplicateCount(len(indices), len(lines))
    return result
