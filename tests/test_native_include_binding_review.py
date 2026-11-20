"""Independent regressions for unsupported embedded inputs and absent TUs.

These are synthetic contract controls. Actual pinned native counterexamples and
red logs are retained in docs/checkpoints/20261116/coherence-independent-review2.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from cppulse.analysis import _include_binding, normalize_native_analysis
from test_analysis_inventory import native_snapshot
from test_measured_normalization import add_metrics


def binding(**kwargs: Any) -> tuple[str, list[str], list[dict[str, Any]]]:
    """Exercise a labeled finite synthetic input scope."""
    contents = {
        "main.cpp": kwargs.get("main", b"int main(){return 0;}\n"),
        "h.hpp": kwargs.get("header", b"// header\n"),
    }
    facts = {
        path: {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
        for path, data in contents.items()
    }
    edge: dict[str, Any] = {"target": "/owned/h.hpp"}
    if kwargs.get("identity", True):
        edge["content_identity"] = {"status": "available", **facts["h.hpp"]}
    return _include_binding(
        {
            "path": "/owned/main.cpp",
            "status": kwargs.get("status", "analyzed"),
            "includes": [edge],
        },
        arguments=kwargs.get("arguments", []),
        workspace="/owned",
        repo="/owned",
        sources=facts,
        input_facts=facts,
        input_links={path: path for path in contents},
        read_content=contents.__getitem__,
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"main": b'int x; // __has_inclu\\\nde("missing")\n'},
        {"header": b"const char* d = __DATE__;\n"},
        {"arguments": ["-D", 'QUERY=__has_include("missing")']},
        {"arguments": ['-DQUERY=__has_include("missing")']},
        {"arguments": ["-fmodules-cache-path=/external/cache"]},
        {"arguments": ["-Xclang", "-include-pch", "-Xclang", "/external/main.pch"]},
        {"identity": False},
    ],
)
def test_unsupported_scope_remains_unknown(kwargs: dict[str, Any]) -> None:
    assert binding(**kwargs)[0] == "unverified"


def test_closed_regular_buffers_remain_supported() -> None:
    assert binding()[0] == "matched"


@pytest.mark.parametrize(
    "directive",
    [
        b'#embed "payload.bin"',
        b'# embed "payload.bin"',
        b'%:embed "payload.bin"',
        b'#/**/embed "payload.bin"',
        b'#em\\\nbed "payload.bin"',
        b'#em\\\r\nbed "payload.bin"',
    ],
)
def test_embed_spellings_need_external_closure(directive: bytes) -> None:
    assert (
        binding(main=b"unsigned char bytes[] = {\n" + directive + b"\n};\n")[0]
        == "unverified"
    )


def test_failed_tu_never_claims_verified_buffers() -> None:
    assert binding(status="failed")[0] == "unverified"


def test_actual_failed_tu_shape_remains_readable_unknown(tmp_path: Path) -> None:
    def mutate(report: dict[str, Any], root: Path) -> None:
        add_metrics(report, root)
        report["metadata"].update(file_count=0, total_loc=0)
        report["metadata"]["analysis"]["files"][0].update(
            status="failed", reason="libclang failed to create translation unit"
        )
        raw = report["metadata"]["analysis"]["native_metrics"]["files"][0]
        raw.update(
            status="failed",
            source_content_sha256=None,
            physical_loc=None,
            code_loc=None,
            function_count=None,
            functions=[],
            includes=[],
            measurement_complete=False,
            limitations=["libclang failed to create translation unit"],
        )
        raw["token_stream"].update(
            availability="unavailable",
            complete=False,
            records=[],
            retained_tokens=0,
            total_tokens=None,
            limitations=["libclang failed to create translation unit"],
        )

    frozen, args = native_snapshot(tmp_path, mutate=mutate)
    result = normalize_native_analysis(frozen, **args)
    row = result.inventory["items"][0]
    assert row["status"] == "failed"
    assert row["buffer_coherence"] == "unverified"
    assert all(
        item["availability"] == "unavailable" for item in result.metrics["items"]
    )


@pytest.mark.parametrize("ending", [b"\\\n", b"\\\r\n", b"\\\r"])
def test_streamed_query_detection_preserves_splices_at_raw_chunk_boundaries(
    tmp_path: Path, ending: bytes
) -> None:
    from cppulse.analysis_execution import _contains_dynamic_input_query

    prefix = b"__has_inclu"
    boundary = 1024 * 1024
    path = tmp_path / "query.cpp"
    path.write_bytes(
        b" " * (boundary - len(prefix) - 1) + prefix + ending + b'de("missing")\n'
    )
    assert _contains_dynamic_input_query(path)


def test_streamed_query_detection_keeps_logical_overlap_across_many_splices(
    tmp_path: Path,
) -> None:
    from cppulse.analysis_execution import _contains_dynamic_input_query

    path = tmp_path / "query.cpp"
    path.write_bytes(b"__has_" + b"\\\n" * (1024 * 1024) + b'include("missing")\n')
    assert _contains_dynamic_input_query(path)


def test_streamed_harmless_line_continuation_is_not_an_unknown_query(
    tmp_path: Path,
) -> None:
    from cppulse.analysis_execution import _contains_dynamic_input_query

    path = tmp_path / "ordinary.hpp"
    path.write_bytes(
        b"#if !defined(SIZE_T) || \\\n    defined(ORDINARY_MACRO)\ntypedef unsigned long size_t;\n#endif\n"
    )
    assert not _contains_dynamic_input_query(path)
