"""Private cache invalidation and transactional immutable catalog invariants."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from cppulse.errors import ContractError, IntegrityError, PublicationConflict
from cppulse.work_unit_store import (
    CheckedFactCache,
    FactSelection,
    WorkUnitIndex,
    assessment_key,
)


def selection() -> FactSelection:
    return FactSelection(
        "a" * 64,
        "b" * 64,
        "c" * 64,
        "d" * 64,
        "e" * 64,
        (("header.hpp", "f" * 64),),
        True,
    )


def test_incomplete_dependencies_never_produce_cache_hits(tmp_path: Path) -> None:
    cache = CheckedFactCache(tmp_path / "cache")
    unknown = replace(selection(), dependencies_complete=False)
    assert not cache.put(unknown, {"facts": []}, origin={}, complete=True)
    assert cache.get(unknown) is None
    assert not cache.put(selection(), {"facts": []}, origin={}, complete=False)


@pytest.mark.parametrize(
    "field",
    [
        "primary_sha256",
        "context_digest",
        "native_sha256",
        "registry_sha256",
        "extraction_configuration_sha256",
    ],
)
def test_each_extraction_identity_invalidates_facts(tmp_path: Path, field: str) -> None:
    cache = CheckedFactCache(tmp_path / "cache")
    cache.put(
        selection(),
        {"facts": [1]},
        origin={"run_id": "original", "manifest_sha256": "a" * 64},
        complete=True,
    )
    assert cache.get(replace(selection(), **{field: "9" * 64})) is None
    assert (
        cache.get(replace(selection(), dependencies=(("header.hpp", "8" * 64),)))
        is None
    )
    assert cache.get(selection())["origin"]["run_id"] == "original"


def test_policy_only_edit_reuses_facts_but_invalidates_assessment(
    tmp_path: Path,
) -> None:
    cache = CheckedFactCache(tmp_path / "cache")
    cache.put(
        selection(),
        {"facts": [1]},
        origin={"run_id": "original", "manifest_sha256": "a" * 64},
        complete=True,
    )
    first = assessment_key([selection().key()], "score-v1", {"limit": 1}, {})
    second = assessment_key([selection().key()], "score-v1", {"limit": 2}, {})
    assert first != second
    assert cache.get(selection())["payload"] == {"facts": [1]}


def test_cache_tampering_and_receipt_promotion_are_rejected(tmp_path: Path) -> None:
    cache = CheckedFactCache(tmp_path / "cache")
    with pytest.raises(ContractError):
        cache.put(
            selection(),
            {"execution_receipt": {}},
            origin={"run_id": "original", "manifest_sha256": "a" * 64},
            complete=True,
        )
    cache.put(
        selection(),
        {"facts": [1]},
        origin={"run_id": "original", "manifest_sha256": "a" * 64},
        complete=True,
    )
    (tmp_path / "cache" / (selection().key() + ".json")).write_text("{}")
    with pytest.raises(IntegrityError):
        cache.get(selection())


def test_catalog_pages_are_sorted_bounded_and_query_pinned(tmp_path: Path) -> None:
    store = WorkUnitIndex(tmp_path / "catalog.sqlite")
    store.publish(
        "run-one",
        "a" * 64,
        (
            {
                "unit_id": f"unit-{number:03}",
                "outcome": "complete" if number % 2 else "partial",
            }
            for number in reversed(range(23))
        ),
    )
    rows, cursor = store.page("run-one", "a" * 64, page_size=10)
    assert [row["unit_id"] for row in rows] == [f"unit-{n:03}" for n in range(10)]
    next_rows, next_cursor = store.page(
        "run-one", "a" * 64, page_size=10, cursor=cursor
    )
    assert len(next_rows) == 10
    assert next_rows[0]["unit_id"] == "unit-010"
    assert next_cursor
    for changes in (
        {"page_size": 9},
        {"outcome": "partial"},
        {"manifest_sha256": "b" * 64},
    ):
        options = {
            "run_id": "run-one",
            "manifest_sha256": "a" * 64,
            "page_size": 10,
            "cursor": cursor,
            **changes,
        }
        with pytest.raises(ContractError):
            store.page(**options)
    filtered, _ = store.page("run-one", "a" * 64, outcome="complete", page_size=200)
    assert len(filtered) == 11
    with pytest.raises(PublicationConflict):
        store.publish("run-one", "a" * 64, [])


def test_catalog_interrupted_stream_rolls_back_entire_run(tmp_path: Path) -> None:
    store = WorkUnitIndex(tmp_path / "catalog.sqlite")

    def interrupted():
        yield {"unit_id": "unit-1", "outcome": "complete"}
        raise RuntimeError("writer interrupted")

    with pytest.raises(RuntimeError):
        store.publish("run-fault", "b" * 64, interrupted())
    with pytest.raises(IntegrityError):
        store.page("run-fault", "b" * 64)
    store.publish("run-fault", "b" * 64, [{"unit_id": "unit-2", "outcome": "complete"}])
    assert len(store.page("run-fault", "b" * 64)[0]) == 1


@pytest.mark.parametrize("size", [0, 201, True, 1.5])
def test_catalog_rejects_unbounded_pages(tmp_path: Path, size: int) -> None:
    store = WorkUnitIndex(tmp_path / "catalog.sqlite")
    with pytest.raises(ContractError):
        store.page("run", "a" * 64, page_size=size)


@pytest.mark.parametrize("kind", ["cache", "index"])
def test_store_rejects_symlink_ancestor(tmp_path: Path, kind: str) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real, target_is_directory=True)
    with pytest.raises(IntegrityError):
        if kind == "cache":
            CheckedFactCache(tmp_path / "link" / "new")
        else:
            WorkUnitIndex(tmp_path / "link" / "catalog.sqlite")


def test_cache_rejects_oversized_existing_and_new_entries(tmp_path: Path) -> None:
    cache = CheckedFactCache(tmp_path / "cache", max_entry_bytes=1024)
    origin = {"run_id": "original", "manifest_sha256": "a" * 64}
    with pytest.raises(ContractError):
        cache.put(selection(), {"facts": "x" * 2000}, origin=origin, complete=True)
    path = tmp_path / "cache" / (selection().key() + ".json")
    path.write_bytes(b" " * 2000)
    with pytest.raises(IntegrityError):
        cache.get(selection())
    with pytest.raises(IntegrityError):
        cache.put(selection(), {"facts": []}, origin=origin, complete=True)


@pytest.mark.parametrize(
    "document",
    [
        {"unit_id": "../escape", "outcome": "complete"},
        {"unit_id": "valid", "outcome": "invented"},
        {"unit_id": "valid", "outcome": "complete", "payload": "not-a-summary"},
        {"unit_id": "valid", "outcome": "complete", "reason": "x" * 4097},
    ],
)
def test_catalog_rejects_malformed_or_large_summaries(
    tmp_path: Path, document: dict
) -> None:
    store = WorkUnitIndex(tmp_path / "catalog.sqlite")
    with pytest.raises(ContractError):
        store.publish("run", "a" * 64, [document])
    with pytest.raises(IntegrityError):
        store.page("run", "a" * 64)


def test_catalog_readonly_never_creates_or_changes_catalog(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "catalog.sqlite"
    with pytest.raises(IntegrityError):
        WorkUnitIndex(missing, read_only=True)
    assert not missing.parent.exists()
    path = tmp_path / "catalog.sqlite"
    store = WorkUnitIndex(path)
    store.publish("run", "a" * 64, [{"unit_id": "one", "outcome": "partial"}])
    before = path.read_bytes()
    reader = WorkUnitIndex(path, read_only=True)
    assert len(reader.page("run", "a" * 64)[0]) == 1
    with pytest.raises(ContractError):
        reader.publish("other", "b" * 64, [])
    assert path.read_bytes() == before


def test_catalog_page_byte_limit_and_cursor_stay_bound(tmp_path: Path) -> None:
    store = WorkUnitIndex(tmp_path / "catalog.sqlite")
    store.publish(
        "run",
        "a" * 64,
        [
            {"unit_id": str(n), "outcome": "complete", "reason": "x" * 4096}
            for n in range(9)
        ],
    )
    items, cursor = store.page("run", "a" * 64, max_page_bytes=17409)
    assert len(items) == 3
    assert cursor is not None
    with pytest.raises(ContractError):
        store.page("run", "a" * 64, cursor=cursor)
    next_items, _ = store.page("run", "a" * 64, cursor=cursor, max_page_bytes=17409)
    assert next_items[0]["unit_id"] == "3"


def test_catalog_corrupt_oversized_row_is_not_read_as_payload(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "catalog.sqlite"
    store = WorkUnitIndex(path)
    store.publish("run", "a" * 64, [{"unit_id": "one", "outcome": "complete"}])
    with sqlite3.connect(path) as db:
        db.execute("UPDATE units SET payload=?", ("x" * 20000,))
    with pytest.raises(IntegrityError):
        store.page("run", "a" * 64)
