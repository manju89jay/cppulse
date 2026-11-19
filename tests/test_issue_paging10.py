"""Finite mocked provider paging controls; runner selects draft explicitly."""
from __future__ import annotations

from pathlib import Path
from copy import deepcopy
import json

import pytest

from cppulse import issue_tracker as candidate
from cppulse.errors import ContractError


def request() -> dict:
    return {
        "version": "1.0.0",
        "provider": "github-rest-2022-11-28",
        "repository": "fixture/project",
        "window": {"start": "2026-01-01T00:00:00Z", "end": "2026-02-01T00:00:00Z"},
        "limits": {"pages": 3, "page_bytes": 65536, "wall_seconds": 10},
        "cost_inputs": [],
    }


def issue(number: int) -> dict:
    return {
        "number": number,
        "title": "Mocked protocol fixture",
        "state": "open",
        "created_at": "2026-01-02T00:00:00Z",
        "updated_at": "2026-01-03T00:00:00Z",
        "closed_at": None,
        "html_url": f"https://github.com/fixture/project/issues/{number}",
    }


def link(page: int, relation: str, *, repository: str = "fixture/project") -> str:
    return f'<https://api.github.com/repos/{repository}/issues?page={page}>; rel="{relation}"'


@pytest.mark.parametrize(
    "header",
    [
        link(2, "last"),
        link(1, "first", repository="foreign/repository"),
        link(0, "prev"),
    ],
)
def test_inconsistent_or_foreign_relations_cannot_prove_terminal_page(
    tmp_path: Path, header: str
) -> None:
    calls = []

    def get(url, timeout):
        calls.append(url)
        return 200, {"Link": header}, json.dumps([issue(1)]).encode()

    value = candidate.collect(request(), tmp_path / "result", transport=get)
    assert value["status"] == "partial"
    assert value["issue_count"] is None
    assert len(calls) == 1


def test_case_variant_link_headers_do_not_erase_next_page(tmp_path: Path) -> None:
    calls = []

    def get(url, timeout):
        calls.append(url)
        headers = {"Link": link(2, "next"), "link": ""} if len(calls) == 1 else {}
        return 200, headers, json.dumps([issue(len(calls))]).encode()

    value = candidate.collect(request(), tmp_path / "result", transport=get)
    assert value["status"] == "complete"
    assert value["issue_count"] == 2
    assert len(calls) == 2


def test_oversized_etag_is_explicitly_unavailable_not_silently_truncated(
    tmp_path: Path,
) -> None:
    value = candidate.collect(
        request(),
        tmp_path / "result",
        transport=lambda *_: (
            200,
            {"ETag": "x" * 1025},
            json.dumps([issue(1)]).encode(),
        ),
    )
    assert value["status"] == "unavailable"
    assert value["issue_count"] is None


def test_ambiguous_case_variant_etags_do_not_qualify_complete_scope(
    tmp_path: Path,
) -> None:
    value = candidate.collect(
        request(),
        tmp_path / "result",
        transport=lambda *_: (
            200,
            {"ETag": "first", "etag": "second"},
            json.dumps([issue(1)]).encode(),
        ),
    )
    assert value["status"] == "unavailable"
    assert value["issue_count"] is None


def test_consistent_first_previous_last_relations_preserve_terminal_total(
    tmp_path: Path,
) -> None:
    calls = []

    def get(url, timeout):
        calls.append(url)
        header = (
            link(2, "next last")
            if len(calls) == 1
            else link(1, "first prev") + "," + link(2, "last")
        )
        return 200, {"Link": header}, json.dumps([issue(len(calls))]).encode()

    cfg = request()
    output = tmp_path / "result"
    value = candidate.collect(cfg, output, transport=get)
    assert value["status"] == "complete" and value["issue_count"] == 2
    candidate.validate_report(value, expected_request=cfg, output=output)


def test_case_variant_links_combine_relations_and_preserve_opaque_cursor(
    tmp_path: Path,
) -> None:
    calls = []

    def get(url, timeout):
        calls.append(url)
        headers = (
            {
                "Link": link(1, "first"),
                "lInK": '<https://api.github.com/repositories/123/issues?page=2&after=YWJjPQ%3D%3D>; rel="NEXT"',
            }
            if len(calls) == 1
            else {}
        )
        return 200, headers, json.dumps([issue(len(calls))]).encode()

    value = candidate.collect(request(), tmp_path / "result", transport=get)
    assert value["status"] == "complete" and value["issue_count"] == 2
    assert calls[1].endswith("page=2&after=YWJjPQ%3D%3D")
    assert all("/repos/fixture/project/issues?" in url for url in calls)


def test_single_current_last_page_and_empty_headers_are_valid(tmp_path: Path) -> None:
    cfg = request()
    value = candidate.collect(
        cfg,
        tmp_path / "result",
        transport=lambda *_: (
            200,
            {"LINK": link(1, "last"), "ETag": '"finite"'},
            b"[]",
        ),
    )
    assert value["status"] == "complete" and value["issue_count"] == 0
    assert value["pages"][0]["etag"] == '"finite"'


def test_replay_cannot_upgrade_inconsistent_paging_to_complete(tmp_path: Path) -> None:
    cfg = request()
    output = tmp_path / "result"
    value = candidate.collect(
        cfg,
        output,
        transport=lambda *_: (
            200,
            {"Link": link(2, "last")},
            json.dumps([issue(1)]).encode(),
        ),
    )
    forged = deepcopy(value)
    forged.update(status="complete", issue_count=1)
    with pytest.raises(ContractError, match="Incomplete"):
        candidate.validate_report(forged, expected_request=cfg, output=output)


@pytest.mark.parametrize(
    "headers",
    [{"ETag": "x" * 1025}, {"ETag": "first", "etag": "second"}, {"Link": "x" * 16385}],
)
def test_invalid_header_scope_retains_body_but_never_claims_interpretation(
    tmp_path: Path, headers: dict
) -> None:
    cfg = request()
    output = tmp_path / "result"
    body = json.dumps([issue(1)]).encode()
    value = candidate.collect(cfg, output, transport=lambda *_: (200, headers, body))
    assert value["status"] == "unavailable" and value["issues"] == []
    assert value["pages"][0]["parse_status"] == "not_attempted"
    assert (output / "page-001.body").read_bytes() == body
    candidate.validate_report(value, expected_request=cfg, output=output)


@pytest.mark.parametrize(
    "header",
    [
        link(2, "next") + "," + link(1, "last"),
        link(2, "next") + "," + link(2, "next"),
        link(1, "last")[:-1] + ' last"',
    ],
)
def test_contradictory_or_duplicate_relations_never_report_terminal_scope(
    tmp_path: Path, header: str
) -> None:
    value = candidate.collect(
        request(),
        tmp_path / "result",
        transport=lambda *_: (200, {"Link": header}, json.dumps([issue(1)]).encode()),
    )
    assert value["status"] == "partial" and value["issue_count"] is None
