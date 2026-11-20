"""Exact duplication consumer acceptance cases against retained token streams."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from cppulse.measurements import duplicate_token_counts


def stream(spellings: list[str]) -> dict[str, Any]:
    """Represent each hand-reviewed token on a separate physical source line."""
    return {
        "availability": "measured",
        "complete": True,
        "records": [
            {
                "kind": "identifier",
                "spelling": text,
                "line": index + 1,
                "column": 1,
                "end_line": index + 1,
                "end_column": len(text) + 1,
            }
            for index, text in enumerate(spellings)
        ],
    }


def test_exact_runs_count_matched_occurrences_and_line_union() -> None:
    shared = [f"token{i}" for i in range(35)]
    counts = duplicate_token_counts({"a.cpp": stream(shared), "b.cpp": stream(shared)})
    assert counts["a.cpp"].tokens == 35
    assert counts["a.cpp"].lines == 35
    assert counts["b.cpp"].tokens == 35


def test_short_equal_inputs_do_not_meet_published_thirty_token_threshold() -> None:
    counts = duplicate_token_counts(
        {"a.cpp": stream(["x"] * 29), "b.cpp": stream(["x"] * 29)}
    )
    assert counts["a.cpp"].tokens == 0
    assert counts["a.cpp"].lines == 0


def test_overlapping_windows_in_one_occurrence_are_not_a_duplicate() -> None:
    counts = duplicate_token_counts({"a.cpp": stream(["x"] * 35)})
    assert counts["a.cpp"].tokens == 0


def test_two_nonoverlapping_occurrences_within_one_file_are_measured() -> None:
    same = [f"t{i}" for i in range(30)]
    counts = duplicate_token_counts({"a.cpp": stream(same + same)})
    assert counts["a.cpp"].tokens == 60
    assert counts["a.cpp"].lines == 60


def test_truncated_peer_prevents_fabricated_zero_for_whole_scope() -> None:
    complete = stream(["unique"])
    partial = deepcopy(complete)
    partial.update(availability="partial", complete=False)
    counts = duplicate_token_counts({"a.cpp": complete, "b.cpp": partial})
    assert all(
        row.tokens is None and row.lines is None and row.limitations
        for row in counts.values()
    )


def test_spelling_and_kind_are_exact_and_multiline_lines_are_union() -> None:
    same = [f"t{i}" for i in range(30)]
    left, right = stream(same), stream(same)
    right["records"][0]["kind"] = "literal"
    assert duplicate_token_counts({"a": left, "b": right})["a"].tokens == 0
    right = deepcopy(left)
    for row in left["records"] + right["records"]:
        row.update(line=1, end_line=3)
    assert duplicate_token_counts({"a": left, "b": right})["a"].lines == 3


def test_multiline_token_excludes_empty_end_line_at_column_one() -> None:
    same = [f"t{i}" for i in range(30)]
    left, right = stream(same), stream(same)
    for row in left["records"] + right["records"]:
        row.update(line=1, end_line=3, end_column=1)
    assert duplicate_token_counts({"a": left, "b": right})["a"].lines == 2
