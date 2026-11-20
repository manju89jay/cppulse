"""Finite streaming recognizer controls; absence is not a closure proof."""

from pathlib import Path

import pytest

from cppulse.analysis_execution import _contains_dynamic_input_query


def test_ordinary_continued_directive_does_not_invent_dynamic_query(
    tmp_path: Path,
) -> None:
    path = tmp_path / "header.h"
    path.write_bytes(
        b"#if defined(A) || \\\n defined(B)\ntypedef unsigned long size_t;\n#endif\n"
    )
    assert not _contains_dynamic_input_query(path)


@pytest.mark.parametrize("ending", [b"\n", b"\r\n", b"\r"])
def test_spliced_dynamic_query_remains_unknown_across_raw_chunk_boundary(
    tmp_path: Path, ending: bytes
) -> None:
    path = tmp_path / "query.h"
    prefix = b" " * (1024 * 1024 - len(b"__has_inc\\"))
    path.write_bytes(prefix + b"__has_inc\\" + ending + b'lude("external.flag")\n')
    assert _contains_dynamic_input_query(path)


def test_long_splice_sequence_preserves_logical_operator(tmp_path: Path) -> None:
    path = tmp_path / "query.h"
    path.write_bytes(
        b"__has_inc" + b"\\\n" * (1024 * 1024 // 2) + b'lude("external.flag")'
    )
    assert _contains_dynamic_input_query(path)
