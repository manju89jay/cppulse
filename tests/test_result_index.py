"""Actual derived SQLite queries over tiny authored retained reports."""

import json
import sqlite3

import pytest

from cppulse.errors import ContractError, IntegrityError, CppulseError
from cppulse.result_index import build_result_index, make_index_request
from cppulse.run_store import RunStore
from test_contracts_v2 import manifest_document


def finding(**changes):
    row = dict(
        rule_id="CPP-MEM-001",
        category="memory_safety",
        severity="warning",
        file="src/é a.cpp",
        line=123456789012345678901234567890,
        message="literal % _ quote' ?",
    )
    row.update(changes)
    return row


def source(tmp_path, rows=None, *, body=None, format_version=None):
    store = RunStore(tmp_path / "original", format_version=format_version)
    body = (
        json.dumps(
            {"findings": [finding(), finding()] if rows is None else rows},
            ensure_ascii=False,
        ).encode()
        if body is None
        else body
    )
    path = tmp_path / "authored.json"
    path.write_bytes(body)
    with store.begin("original") as stage:
        artifact = stage.copy_artifact("report", path, "reports/é findings.json")
        manifest = manifest_document()
        manifest.update(run_id=stage.run_id, artifacts=[artifact])
        snapshot = stage.publish(manifest)
    return (
        store,
        snapshot,
        make_index_request(store, snapshot.run_id, snapshot.manifest_sha256, "report"),
    )


def test_cold_warm_and_duplicate_raw_rows_keep_original_heads(tmp_path):
    store, original, request = source(tmp_path)
    before = (store.root / "heads.json").read_bytes()
    index = build_result_index(store, tmp_path / "cache", request)
    assert not index.reused
    page = index.page(per_page=1)
    assert (
        page["items"] == [finding()] and page["total"] == 2 and page["total_pages"] == 2
    )
    assert (
        page["read_scope"] == "selected_artifact_only"
        and page["analysis_cache_eligible"] is False
    )
    assert index.page(page=2, per_page=1)["items"] == [finding()]
    assert index.snapshot.manifest["input_verification"] == "unverified"
    assert (store.root / "heads.json").read_bytes() == before
    warm = build_result_index(store, tmp_path / "cache", request)
    assert (
        warm.reused and warm.snapshot.manifest_sha256 == index.snapshot.manifest_sha256
    )
    detached = index.request
    detached["source"]["run_id"] = "foreign"
    assert index.request == request


def test_filters_literal_sql_and_no_silent_page_shortening(tmp_path):
    rows = [
        finding(),
        finding(
            category="modernization", file="other.cpp", message="unique ' OR 1=1 --"
        ),
        finding(),
    ]
    store, _, request = source(tmp_path, rows)
    index = build_result_index(store, tmp_path / "cache", request)
    assert index.page(category="memory_safety")["items"] == [rows[0], rows[2]]
    assert index.page(file="other.cpp")["items"] == [rows[1]]
    assert index.page(text="' OR 1=1 --")["items"] == [rows[1]]
    assert index.page(text="% _")["total"] == 2
    assert index.page(category="' OR 1=1 --")["total"] == 0
    assert index.page(page=99)["items"] == []
    with pytest.raises(ContractError, match="reduce per_page"):
        index.page(max_page_bytes=1)


def test_empty_index_and_default_cache_location(tmp_path):
    store, _, request = source(tmp_path, [])
    index = build_result_index(store, store.root / ".query-indexes", request)
    page = index.page()
    assert page["items"] == [] and page["total"] == 0 and page["total_pages"] == 1


@pytest.mark.parametrize("bad", [True, 1.0, 0, -1])
def test_page_exact_integer_bounds(tmp_path, bad):
    store, _, request = source(tmp_path, [])
    index = build_result_index(store, tmp_path / "cache", request)
    for field in ["page", "per_page", "max_page_bytes"]:
        with pytest.raises(ContractError):
            index.page(**{field: bad})
    with pytest.raises(ContractError):
        index.page(per_page=201)
    with pytest.raises(ContractError):
        index.page(page=2**63 - 1, per_page=200)


@pytest.mark.parametrize("bad", ["x" * 4097, "\ud800", "\x00", True])
def test_filter_invalid_values(tmp_path, bad):
    store, _, request = source(tmp_path, [])
    index = build_result_index(store, tmp_path / "cache", request)
    for field in ["category", "file", "text"]:
        with pytest.raises(ContractError):
            index.page(**{field: bad})


def failed_candidates(cache_root):
    return list(cache_root.glob("*/.candidates/*/failure.json"))


def test_malformed_after_valid_rows_rolls_back_and_retains_failure(tmp_path):
    body = b'{"findings":[' + json.dumps(finding()).encode() + b'],"late":[}'
    store, _, request = source(tmp_path, body=body)
    with pytest.raises(ContractError):
        build_result_index(store, tmp_path / "cache", request)
    failures = failed_candidates(tmp_path / "cache")
    assert len(failures) == 1
    assert json.loads(failures[0].read_bytes())["partial_rows_visible"] is False
    with sqlite3.connect(failures[0].parent / "index.sqlite") as connection:
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            == []
        )
    heads = json.loads(next((tmp_path / "cache").glob("*/heads.json")).read_bytes())
    assert heads["latest"] is None and heads["latest_attempt"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"line": True},
        {"line": 1.0},
        {"line": 0},
        {"confidence": float("inf")},
        {"message": None},
        {"category": "unknown"},
    ],
)
def test_finding_item_semantics_are_validated_before_publication(tmp_path, change):
    store, _, request = source(tmp_path, [finding(**change)])
    with pytest.raises(ContractError):
        build_result_index(store, tmp_path / "cache", request)
    assert failed_candidates(tmp_path / "cache")


@pytest.mark.parametrize(
    "field,value", [("max_rows", 1), ("max_item_bytes", 1), ("max_index_bytes", 4096)]
)
def test_index_build_budgets_fail_and_retain(tmp_path, field, value):
    store, _, request = source(tmp_path)
    request["limits"][field] = value
    with pytest.raises(ContractError):
        build_result_index(store, tmp_path / "cache", request)
    assert failed_candidates(tmp_path / "cache")


def test_interruption_rolls_back_unpublished_rows(tmp_path, monkeypatch):
    import cppulse.result_index as module

    store, _, request = source(tmp_path)
    original = module.iter_json_array

    def interrupted(*args, **kwargs):
        for item in original(*args, **kwargs):
            yield item
            raise KeyboardInterrupt("authored interruption")

    monkeypatch.setattr(module, "iter_json_array", interrupted)
    with pytest.raises(KeyboardInterrupt):
        build_result_index(store, tmp_path / "cache", request)
    failure = failed_candidates(tmp_path / "cache")[0]
    assert json.loads(failure.read_bytes())["type"] == "KeyboardInterrupt"
    assert not list((tmp_path / "cache").glob("*/runs/*"))


def test_wall_budget_is_checked_before_queries_and_build(tmp_path, monkeypatch):
    import cppulse.result_index as module

    store, _, request = source(tmp_path)
    request["limits"]["wall_seconds"] = 1
    calls = iter([0.0, 2.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(calls, 2.0))
    with pytest.raises(ContractError, match="wall-time"):
        build_result_index(store, tmp_path / "cache", request)


@pytest.mark.parametrize("target", ["source", "manifest", "database", "receipt"])
def test_mutated_material_never_reused_or_queried(tmp_path, target):
    store, snapshot, request = source(tmp_path)
    index = build_result_index(store, tmp_path / "cache", request)
    paths = {
        "source": snapshot.path / request["source"]["artifact_path"],
        "manifest": snapshot.path / "run_manifest.json",
        "database": index.snapshot.path / "index.sqlite",
        "receipt": index.snapshot.path / "receipt.json",
    }
    path = paths[target]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises((ContractError, IntegrityError)):
        index.page()
    with pytest.raises((ContractError, IntegrityError)):
        build_result_index(store, tmp_path / "cache", request)


def test_source_drift_after_provisional_row_rolls_back(tmp_path, monkeypatch):
    import cppulse.result_index as module

    store, snapshot, request = source(tmp_path)
    original = module.iter_json_array
    path = snapshot.path / request["source"]["artifact_path"]

    def changed(*args, **kwargs):
        for ordinal, item in enumerate(original(*args, **kwargs)):
            yield item
            if ordinal == 0:
                path.write_bytes(path.read_bytes().replace(b"literal", b"changed"))

    monkeypatch.setattr(module, "iter_json_array", changed)
    with pytest.raises(IntegrityError):
        build_result_index(store, tmp_path / "cache", request)
    assert failed_candidates(tmp_path / "cache")


def test_query_withholds_page_on_post_sql_source_drift(tmp_path, monkeypatch):
    import cppulse.result_index as module

    store, snapshot, request = source(tmp_path)
    index = build_result_index(store, tmp_path / "cache", request)
    connect = module._connect
    path = snapshot.path / request["source"]["artifact_path"]

    def changed(*args, **kwargs):
        connection = connect(*args, **kwargs)
        if kwargs.get("readonly"):
            path.write_bytes(path.read_bytes() + b" ")
        return connection

    monkeypatch.setattr(module, "_connect", changed)
    with pytest.raises(IntegrityError):
        index.page()


@pytest.mark.parametrize("location", ["same", "runs", "staging", "recovery"])
def test_cache_cannot_share_original_authority(tmp_path, location):
    store, _, request = source(tmp_path, [])
    cache = {
        "same": store.root,
        "runs": store.root / "runs/cache",
        "staging": store.root / ".staging/cache",
        "recovery": store.root / ".recovery/cache",
    }[location]
    with pytest.raises(ContractError):
        build_result_index(store, cache, request)


def test_metadata_only_selection_never_opens_full_original_run(tmp_path, monkeypatch):
    store, snapshot, _ = source(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("selected view must not materialize/open full original run")

    monkeypatch.setattr(store, "open_run", forbidden)
    request = make_index_request(
        store, snapshot.run_id, snapshot.manifest_sha256, "report"
    )
    assert build_result_index(store, tmp_path / "cache", request).page()["total"] == 2


def test_metadata_reader_has_no_artifact_reads_or_cache_writes(tmp_path):
    from cppulse.result_index import read_source_manifest_metadata

    store, snapshot, request = source(tmp_path)
    (snapshot.path / request["source"]["artifact_path"]).unlink()
    metadata = read_source_manifest_metadata(
        store, snapshot.run_id, snapshot.manifest_sha256
    )
    assert metadata["status"] == "completed"
    metadata["source"]["files"].clear()
    assert read_source_manifest_metadata(
        store, snapshot.run_id, snapshot.manifest_sha256
    )["source"]["files"]
    assert not (store.root / ".query-indexes").exists()


def test_parent_cold_lease_covers_distinct_requests_but_not_warm_readers(tmp_path):
    from cppulse.run_store import _directory
    from cppulse.store_coordination import publication_guard
    from cppulse.errors import PublicationConflict

    store, _, request = source(tmp_path)
    index = build_result_index(store, tmp_path / "cache", request)
    other = json.loads(json.dumps(request))
    other["limits"]["max_rows"] -= 1
    with (
        _directory(tmp_path / "cache") as parent,
        publication_guard(parent, timeout_seconds=0, required=True),
    ):
        assert build_result_index(store, tmp_path / "cache", request).reused
        assert index.page()["total"] == 2
        with pytest.raises(PublicationConflict):
            build_result_index(store, tmp_path / "cache", other)
    assert not failed_candidates(tmp_path / "cache")


def test_concurrent_readers_and_readonly_connection_cannot_write(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from cppulse.result_index import _connect, _deadline

    store, _, request = source(tmp_path)
    index = build_result_index(store, tmp_path / "cache", request)
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(
            executor.map(
                lambda page: index.page(page=page, per_page=1)["items"], [1, 2]
            )
        ) == [[finding()], [finding()]]
    connection = _connect(
        index.snapshot.path / "index.sqlite",
        request["limits"],
        _deadline(1),
        readonly=True,
    )
    try:
        assert connection.execute("PRAGMA query_only").fetchone()[0] == 1
        assert connection.execute("PRAGMA trusted_schema").fetchone()[0] == 0
        with pytest.raises(sqlite3.OperationalError):
            connection.execute("DELETE FROM findings")
    finally:
        connection.close()


def test_raw_numeric_lexemes_and_source_status_are_retained(tmp_path):
    raw = json.dumps(finding()).encode()[:-1] + b',"confidence":1.2300e-02}'
    store, snapshot, request = source(
        tmp_path,
        body=b'{"ignored":{"not_report_schema":false},"findings":[' + raw + b"]}",
    )
    index = build_result_index(store, tmp_path / "cache", request)
    with sqlite3.connect(index.snapshot.path / "index.sqlite") as connection:
        assert (
            connection.execute("SELECT raw FROM findings")
            .fetchone()[0]
            .endswith(b'"confidence":1.2300e-02}')
        )
    assert index.page()["source"]["status"] == "completed"
    assert (
        index.page()["source"]["input_verification"]
        == snapshot.manifest["input_verification"]
    )


def test_ignored_element_budget_requires_explicit_larger_request(tmp_path):
    body = b'{"findings":[],"ignored":[[' + b"0," * 20 + b"0]]}"
    store, _, request = source(tmp_path, body=body)
    request["limits"]["max_item_bytes"] = 16
    with pytest.raises(ContractError):
        build_result_index(store, tmp_path / "cache", request)
    request["limits"]["max_item_bytes"] = 64
    assert build_result_index(store, tmp_path / "cache", request).page()["total"] == 0


def test_symlink_source_and_cache_ancestors_fail_closed(tmp_path):
    store, snapshot, request = source(tmp_path)
    artifact = snapshot.path / request["source"]["artifact_path"]
    original = artifact.read_bytes()
    artifact.unlink()
    foreign = tmp_path / "foreign"
    foreign.write_bytes(original)
    artifact.symlink_to(foreign)
    with pytest.raises(IntegrityError):
        build_result_index(store, tmp_path / "cache", request)
    (tmp_path / "alias").symlink_to(store.root, target_is_directory=True)
    with pytest.raises((ContractError, IntegrityError)):
        build_result_index(store, tmp_path / "alias/cache", request)
    assert foreign.read_bytes() == original


def test_selected_original_changes_during_publication_retains_staging(
    tmp_path, monkeypatch
):
    from cppulse.run_store import StagedRun

    store, snapshot, request = source(tmp_path)
    original = StagedRun.publish
    path = snapshot.path / request["source"]["artifact_path"]
    before = (store.root / "heads.json").read_bytes()

    def changed(self, *args, **kwargs):
        if kwargs.get("material_check"):
            path.write_bytes(path.read_bytes() + b" ")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(StagedRun, "publish", changed)
    with pytest.raises(IntegrityError):
        build_result_index(store, tmp_path / "cache", request)
    assert list((tmp_path / "cache").glob("*/.staging/*/index.sqlite"))
    assert not list((tmp_path / "cache").glob("*/runs/*"))
    assert (store.root / "heads.json").read_bytes() == before


def test_rebound_candidate_failure_evidence_uses_retained_directory_fd(
    tmp_path, monkeypatch
):
    import cppulse.result_index as module

    store, _, request = source(tmp_path)
    original = module.iter_json_array
    retired = []

    def rebound(*args, **kwargs):
        for item in original(*args, **kwargs):
            candidate = next((tmp_path / "cache").glob("*/.candidates/*"))
            moved = candidate.with_name(candidate.name + "-retired")
            candidate.rename(moved)
            candidate.mkdir()
            (candidate / "sentinel").write_bytes(b"foreign-owned")
            retired.append(moved)
            yield item

    monkeypatch.setattr(module, "iter_json_array", rebound)
    with pytest.raises(IntegrityError, match="candidate directory changed"):
        build_result_index(store, tmp_path / "cache", request)
    assert (retired[0] / "failure.json").exists()
    foreign = retired[0].with_name(retired[0].name.removesuffix("-retired"))
    assert sorted(x.name for x in foreign.iterdir()) == ["sentinel"]
    assert (foreign / "sentinel").read_bytes() == b"foreign-owned"


def test_source_rebind_with_same_bytes_is_still_identity_failure(tmp_path, monkeypatch):
    import cppulse.result_index as module

    store, snapshot, request = source(tmp_path)
    original = module.iter_json_array
    path = snapshot.path / request["source"]["artifact_path"]

    def rebound(*args, **kwargs):
        for ordinal, item in enumerate(original(*args, **kwargs)):
            yield item
            if ordinal == 0:
                retired = path.with_name("retired.json")
                path.rename(retired)
                path.write_bytes(retired.read_bytes())

    monkeypatch.setattr(module, "iter_json_array", rebound)
    with pytest.raises(IntegrityError):
        build_result_index(store, tmp_path / "cache", request)


def test_receipt_closed_fields_are_checked_even_if_artifact_hashes_valid(
    tmp_path, monkeypatch
):
    import cppulse.result_index as module

    store, _, request = source(tmp_path)
    index = build_result_index(store, tmp_path / "cache", request)
    original = module._json

    def wrong_scope(raw):
        document = original(raw)
        if isinstance(document, dict) and document.get("complete") is True:
            document["native_executed"] = True
        return document

    monkeypatch.setattr(module, "_json", wrong_scope)
    with pytest.raises(IntegrityError, match="receipt differs"):
        index.page()


@pytest.mark.parametrize(
    "field,value", [("version", "999.0.0"), ("phase", "migrating")]
)
@pytest.mark.parametrize("operation", ["metadata", "request", "cold", "warm", "page"])
def test_source_protocol_is_a_central_selection_boundary(
    tmp_path, field, value, operation
):
    from cppulse.result_index import read_source_manifest_metadata

    store, snapshot, request = source(tmp_path)
    if operation in ("warm", "page"):
        index = build_result_index(store, tmp_path / "cache", request)
    marker = store.root / "store-format.json"
    document = json.loads(marker.read_bytes())
    document[field] = value
    marker.write_text(json.dumps(document))
    with pytest.raises(CppulseError):
        if operation == "metadata":
            read_source_manifest_metadata(
                store, snapshot.run_id, snapshot.manifest_sha256
            )
        elif operation == "request":
            make_index_request(
                store, snapshot.run_id, snapshot.manifest_sha256, "report"
            )
        elif operation in ("cold", "warm"):
            build_result_index(store, tmp_path / "cache", request)
        else:
            index.page()


def republish_cache(
    index,
    tmp_path,
    *,
    sql=None,
    manifest_change=None,
    slot="index.sqlite",
    media_type="application/octet-stream",
):
    cache = RunStore(index.snapshot._root)
    database = tmp_path / "changed-cache.sqlite"
    database.write_bytes((index.snapshot.path / "index.sqlite").read_bytes())
    if sql:
        with sqlite3.connect(database) as connection:
            for statement, params in sql:
                connection.execute(statement, params)
    manifest = index.snapshot.manifest
    if manifest_change:
        manifest_change(manifest)
    with cache.begin() as stage:
        entries = [
            stage.copy_artifact("index", database, slot, media_type),
            stage.copy_artifact(
                "receipt", index.snapshot.path / "receipt.json", "receipt.json"
            ),
        ]
        manifest.update(run_id=stage.run_id, artifacts=entries)
        return stage.publish(manifest)


@pytest.mark.parametrize(
    "key,value",
    [
        ("index", "999.0.0"),
        ("stream", "999.0.0"),
        ("operation", "analysis"),
        ("native_executed", "true"),
        ("analysis_cache_eligible", "true"),
        ("extra", "unknown"),
    ],
)
def test_cache_manifest_version_and_nonexecution_markers_are_closed(
    tmp_path, key, value
):
    store, _, request = source(tmp_path)
    index = build_result_index(store, tmp_path / "cache", request)
    republish_cache(
        index,
        tmp_path,
        manifest_change=lambda manifest: manifest["versions"].update({key: value}),
    )
    with pytest.raises(IntegrityError, match="manifest scope"):
        build_result_index(store, tmp_path / "cache", request)


@pytest.mark.parametrize(
    "slot,media_type",
    [("other.sqlite", "application/octet-stream"), ("index.sqlite", "text/plain")],
)
def test_cache_artifact_layout_is_a_private_profile(tmp_path, slot, media_type):
    store, _, request = source(tmp_path)
    index = build_result_index(store, tmp_path / "cache", request)
    republish_cache(index, tmp_path, slot=slot, media_type=media_type)
    with pytest.raises(IntegrityError, match="opaque artifacts"):
        build_result_index(store, tmp_path / "cache", request)


@pytest.mark.parametrize(
    "statements",
    [
        ["CREATE TABLE extra(value)"],
        ["CREATE TRIGGER hidden AFTER INSERT ON findings BEGIN SELECT 1; END"],
        ["DROP INDEX findings_file"],
        ["DROP INDEX findings_file", "CREATE INDEX findings_file ON findings(message)"],
        ["PRAGMA user_version=99"],
        ["PRAGMA application_id=99"],
        ["UPDATE findings SET ordinal=9 WHERE ordinal=1"],
        [
            "ALTER TABLE findings RENAME TO original_findings",
            "CREATE VIEW findings AS SELECT * FROM original_findings",
        ],
    ],
)
def test_cache_sqlite_schema_and_ordinals_are_checked_before_warm_reuse(
    tmp_path, statements
):
    store, _, request = source(tmp_path)
    index = build_result_index(store, tmp_path / "cache", request)
    republish_cache(index, tmp_path, sql=[(sql, ()) for sql in statements])
    with pytest.raises(IntegrityError):
        build_result_index(store, tmp_path / "cache", request)


@pytest.mark.parametrize(
    "kind",
    [
        "invalid_item",
        "invalid_unicode",
        "contradictory_category",
        "contradictory_file",
        "contradictory_message",
        "text_raw",
        "over_item_bytes",
    ],
)
def test_page_validates_raw_row_and_auxiliary_search_columns(tmp_path, kind):
    store, _, request = source(tmp_path)
    request["limits"]["max_item_bytes"] = 512
    index = build_result_index(store, tmp_path / "cache", request)
    if kind == "invalid_item":
        statement, params = "UPDATE findings SET raw=?", (b'{"madeup":true}',)
    elif kind == "invalid_unicode":
        statement, params = (
            "UPDATE findings SET raw=?",
            (json.dumps(finding(message="\ud800")).encode(),),
        )
    elif kind.startswith("contradictory_"):
        column = kind.removeprefix("contradictory_")
        statement, params = "UPDATE findings SET " + column + "=?", ("contradictory",)
    elif kind == "text_raw":
        statement, params = "UPDATE findings SET raw=?", (json.dumps(finding()),)
    else:
        statement, params = (
            "UPDATE findings SET raw=?",
            (json.dumps(finding()).encode() + b" " * 512,),
        )
    republish_cache(index, tmp_path, sql=[(statement, params)])
    warm = build_result_index(store, tmp_path / "cache", request)
    with pytest.raises((ContractError, IntegrityError)):
        warm.page()


@pytest.mark.parametrize("format_version", ["2.0.0", "3.0.0"])
def test_valid_original_protocols_retain_selected_reader_semantics(
    tmp_path, format_version
):
    from cppulse.result_index import read_source_manifest_metadata

    store, snapshot, request = source(tmp_path, format_version=format_version)
    metadata = read_source_manifest_metadata(
        store, snapshot.run_id, snapshot.manifest_sha256
    )
    assert metadata["run_id"] == snapshot.run_id
    assert build_result_index(store, tmp_path / "cache", request).page()["total"] == 2


@pytest.mark.parametrize("operation", ["build", "publication", "query"])
def test_source_protocol_transition_during_operation_is_rechecked(
    tmp_path, monkeypatch, operation
):
    import cppulse.result_index as module
    from cppulse.run_store import StagedRun

    store, _, request = source(tmp_path)
    marker = store.root / "store-format.json"

    def migrate():
        document = json.loads(marker.read_bytes())
        document["phase"] = "migrating"
        marker.write_text(json.dumps(document))

    if operation == "build":
        original = module.iter_json_array

        def changed(*args, **kwargs):
            for item in original(*args, **kwargs):
                yield item
                migrate()

        monkeypatch.setattr(module, "iter_json_array", changed)
    elif operation == "publication":
        original = StagedRun.publish

        def changed(self, *args, **kwargs):
            if kwargs.get("material_check"):
                migrate()
            return original(self, *args, **kwargs)

        monkeypatch.setattr(StagedRun, "publish", changed)
    else:
        index = build_result_index(store, tmp_path / "cache", request)
        original = module._connect

        def changed(*args, **kwargs):
            connection = original(*args, **kwargs)
            if kwargs.get("readonly"):
                migrate()
            return connection

        monkeypatch.setattr(module, "_connect", changed)
    with pytest.raises(CppulseError):
        if operation == "query":
            index.page()
        else:
            build_result_index(store, tmp_path / "cache", request)


@pytest.mark.parametrize("which", ["original", "derived"])
def test_final_protocol_guard_follows_cache_manifest_recheck(
    tmp_path, monkeypatch, which
):
    from cppulse.run_store import RunSnapshot

    store, _, request = source(tmp_path)
    index = build_result_index(store, tmp_path / "cache", request)
    original = RunSnapshot._check_manifest
    calls = 0

    def changed(self):
        nonlocal calls
        result = original(self)
        if self.run_id == index.snapshot.run_id:
            calls += 1
            if calls == 4:
                marker = (
                    store.root if which == "original" else index.snapshot._root
                ) / "store-format.json"
                document = json.loads(marker.read_bytes())
                document["phase"] = "migrating"
                marker.write_text(json.dumps(document))
        return result

    monkeypatch.setattr(RunSnapshot, "_check_manifest", changed)
    with pytest.raises(CppulseError):
        index.page()
    assert calls == 4


def test_metadata_protocol_is_rechecked_after_manifest_validation(
    tmp_path, monkeypatch
):
    import cppulse.result_index as module

    store, snapshot, _ = source(tmp_path)
    validate = module.validate

    def changed(*args, **kwargs):
        result = validate(*args, **kwargs)
        marker = store.root / "store-format.json"
        document = json.loads(marker.read_bytes())
        document["phase"] = "migrating"
        marker.write_text(json.dumps(document))
        return result

    monkeypatch.setattr(module, "validate", changed)
    with pytest.raises(CppulseError):
        module.read_source_manifest_metadata(
            store, snapshot.run_id, snapshot.manifest_sha256
        )


@pytest.mark.parametrize("artifact_id", ["index", "receipt"])
def test_cache_descriptor_budget_rejected_before_any_payload_hash(
    tmp_path, monkeypatch, artifact_id
):
    import cppulse.run_store as store_module

    store, _, request = source(tmp_path)
    request["limits"]["max_index_bytes"] = 65536
    index = build_result_index(store, tmp_path / "cache", request)
    oversized = tmp_path / "overbudget-opaque"
    oversized.write_bytes(b"x" * 65537)
    cache = RunStore(index.snapshot._root)
    manifest = index.snapshot.manifest
    with cache.begin() as stage:
        entries = [
            stage.copy_artifact(
                "index",
                (
                    oversized
                    if artifact_id == "index"
                    else index.snapshot.path / "index.sqlite"
                ),
                "index.sqlite",
            ),
            stage.copy_artifact(
                "receipt",
                (
                    oversized
                    if artifact_id == "receipt"
                    else index.snapshot.path / "receipt.json"
                ),
                "receipt.json",
            ),
        ]
        manifest.update(run_id=stage.run_id, artifacts=entries)
        published = stage.publish(manifest)
    original = store_module._check_file
    hashed = []

    def checked(path, *args, **kwargs):
        if path.parent == published.path:
            hashed.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(store_module, "_check_file", checked)
    with pytest.raises(IntegrityError, match="declared budgets"):
        build_result_index(store, tmp_path / "cache", request)
    assert hashed == []


@pytest.mark.parametrize("artifact_id", ["index", "receipt"])
def test_query_physical_size_preflight_precedes_payload_verification(
    tmp_path, monkeypatch, artifact_id
):
    import cppulse.run_store as store_module

    store, _, request = source(tmp_path)
    index = build_result_index(store, tmp_path / "cache", request)
    entry = index.snapshot._entry(artifact_id)
    path = index.snapshot.path / entry["path"]
    path.write_bytes(path.read_bytes() + b" ")
    original = store_module._check_file
    hashed = []

    def checked(path, *args, **kwargs):
        if path.parent == index.snapshot.path:
            hashed.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(store_module, "_check_file", checked)
    with pytest.raises(IntegrityError):
        index.page()
    assert hashed == []


def test_warm_factory_budget_is_exact_manifest_and_two_payload_sizes(
    tmp_path, monkeypatch
):
    store, _, request = source(tmp_path)
    index = build_result_index(store, tmp_path / "cache", request)
    expected = len((index.snapshot.path / "run_manifest.json").read_bytes()) + sum(
        row["size_bytes"] for row in index.snapshot.manifest["artifacts"]
    )
    original = RunStore.open_run
    budgets = []

    def opened(self, *args, **kwargs):
        if self.root == index.snapshot._root:
            budgets.append(kwargs.get("max_snapshot_bytes"))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(RunStore, "open_run", opened)
    assert build_result_index(store, tmp_path / "cache", request).reused
    assert budgets == [expected]


@pytest.mark.parametrize("value", [True, 16384.0])
def test_cache_exact_descriptor_size_preflight_rejects_coercion(
    tmp_path, monkeypatch, value
):
    import cppulse.run_store as store_module

    store, _, request = source(tmp_path)
    index = build_result_index(store, tmp_path / "cache", request)
    manifest = index.snapshot.manifest
    manifest["artifacts"][0]["size_bytes"] = value
    raw = json.dumps(manifest).encode()
    (index.snapshot.path / "run_manifest.json").write_bytes(raw)
    import hashlib

    digest = hashlib.sha256(raw).hexdigest()
    head = index.snapshot._root / "heads.json"
    document = json.loads(head.read_bytes())
    for name in ["latest", "latest_attempt"]:
        document[name]["manifest_sha256"] = digest
    head.write_text(json.dumps(document))
    hashed = []
    original = store_module._check_file

    def checked(path, *args, **kwargs):
        if path.parent == index.snapshot.path:
            hashed.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(store_module, "_check_file", checked)
    with pytest.raises((ContractError, IntegrityError)):
        build_result_index(store, tmp_path / "cache", request)
    assert hashed == []


def test_private_pinned_hash_growth_reads_only_one_extra_byte(tmp_path):
    import hashlib
    import cppulse.result_index as module

    path = tmp_path / "pin"
    body = b"bounded"
    path.write_bytes(body)
    pinned = module._Pinned(
        path, len(body), hashlib.sha256(body).hexdigest(), lambda: None
    )
    original = pinned.stream
    requests = []
    returned = []

    class Growing:
        def seek(self, *args):
            return original.seek(*args)

        def fileno(self):
            return original.fileno()

        def read(self, size):
            if not requests:
                with path.open("ab") as writer:
                    writer.write(b"x" * 100000)
            requests.append(size)
            block = original.read(size)
            returned.append(len(block))
            return block

        def close(self):
            original.close()

    pinned.stream = Growing()
    try:
        with pytest.raises(IntegrityError):
            pinned.verify()
        assert sum(returned) <= len(body) + 1
        assert requests == [len(body) + 1]
    finally:
        pinned.close()
