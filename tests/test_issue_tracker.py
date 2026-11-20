"""Finite public GitHub observations and explicit cost inputs never invent ROI."""

from pathlib import Path
import json
import pytest
from cppulse.issue_tracker import collect, validate_request
from cppulse.errors import ContractError


def request() -> dict:
    return {
        "version": "1.0.0",
        "provider": "github-rest-2022-11-28",
        "repository": "manju89jay/cppulse",
        "window": {"start": "2020-01-01T00:00:00Z", "end": "2026-11-16T00:00:00Z"},
        "limits": {"pages": 2, "page_bytes": 65536, "wall_seconds": 10},
        "cost_inputs": [],
    }


def issue(number: int = 1) -> dict:
    return {
        "id": number + 100,
        "number": number,
        "title": "Actual fixture issue",
        "state": "closed",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-03-01T00:00:00Z",
        "closed_at": "2026-03-01T00:00:00Z",
        "html_url": f"https://github.com/manju89jay/cppulse/issues/{number}",
    }


def transport(rows: list, headers: dict | None = None):
    return lambda url, timeout: (200, headers or {}, json.dumps(rows).encode())


def test_observed_public_rows_retain_raw_page_and_no_inferred_costs(
    tmp_path: Path,
) -> None:
    value = collect(request(), tmp_path / "result", transport=transport([issue()]))
    assert value["status"] == "complete"
    assert value["issue_count"] == 1
    assert value["issues"][0]["state_observed"] == "closed"
    assert value["issues"][0]["historical_state"] == "unknown"
    assert value["costs"] == []
    assert (tmp_path / "result" / value["pages"][0]["path"]).read_bytes() == json.dumps(
        [issue()]
    ).encode()


def test_rate_limit_is_unavailable_not_zero_issues(tmp_path: Path) -> None:
    value = collect(
        request(),
        tmp_path / "result",
        transport=lambda *_: (403, {}, b'{"message":"API rate limit exceeded"}'),
    )
    assert value["status"] == "unavailable"
    assert value["issue_count"] is None
    assert value["pages"][0]["http_status"] == 403


def test_pagination_budget_retains_partial_unknown_total(tmp_path: Path) -> None:
    config = request()
    config["limits"]["pages"] = 1
    value = collect(
        config,
        tmp_path / "result",
        transport=transport(
            [issue()],
            {
                "Link": '<https://api.github.com/repos/manju89jay/cppulse/issues?page=2>; rel="next"'
            },
        ),
    )
    assert value["status"] == "partial"
    assert value["issue_count"] is None
    assert len(value["issues"]) == 1


def test_explicit_estimates_and_observed_roi_are_separate(tmp_path: Path) -> None:
    config = request()

    def cost(id, kind, basis, amount):
        return {
            "id": id,
            "issue": 1,
            "kind": kind,
            "basis": basis,
            "currency": "USD",
            "amount": amount,
            "recorded_at": "2026-01-01T00:00:00Z",
            "evidence_sha256": "a" * 64,
            "description": "Declared fixture claim",
        }

    config["cost_inputs"] = [
        cost("e-cost", "cost", "estimated", 100),
        cost("e-benefit", "benefit", "estimated", 150),
        cost("o-cost", "cost", "observed", 120),
    ]
    value = collect(config, tmp_path / "result", transport=transport([issue()]))
    estimated = next(row for row in value["costs"] if row["basis"] == "estimated")
    observed = next(row for row in value["costs"] if row["basis"] == "observed")
    assert estimated["roi_ratio"] == "0.5"
    assert observed["roi_ratio"] is None
    assert observed["status"] == "missing_benefit"
    assert observed["evidence_status"] == "caller_claim_unverified"


@pytest.mark.parametrize(
    "repository", ["../private", "owner/repo/extra", "https://evil.invalid/repo"]
)
def test_bad_scope_rejected_before_creating_output(
    repository: str, tmp_path: Path
) -> None:
    config = request()
    config["repository"] = repository
    with pytest.raises(ContractError):
        validate_request(config)


def test_existing_output_never_overwritten(tmp_path: Path) -> None:
    output = tmp_path / "result"
    output.mkdir()
    (output / "keep").write_bytes(b"preserve")
    with pytest.raises(ContractError):
        collect(request(), output, transport=transport([]))
    assert (output / "keep").read_bytes() == b"preserve"


def test_caller_mutation_cannot_rebind_executed_scope_or_retained_request(
    tmp_path: Path,
) -> None:
    config = request()
    original = json.loads(json.dumps(config))

    def mutate(url, timeout):
        config["repository"] = "other/repository"
        config["limits"]["pages"] = 10
        return transport([issue()])(url, timeout)

    value = collect(config, tmp_path / "result", transport=mutate)
    assert value["repository"] == original["repository"]
    assert json.loads((tmp_path / "result/request.json").read_text()) == original


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value["limits"].update(pages=0),
        lambda value: value["limits"].update(wall_seconds=float("nan")),
        lambda value: value["window"].update(end="2020-01-01T00:00:00"),
    ],
)
def test_bad_limits_and_naive_window_are_rejected(tmp_path: Path, mutation) -> None:
    config = request()
    mutation(config)
    with pytest.raises(ContractError):
        collect(config, tmp_path / "result", transport=transport([]))
    assert not (tmp_path / "result").exists()


def test_foreign_pagination_is_not_followed(tmp_path: Path) -> None:
    value = collect(
        request(),
        tmp_path / "result",
        transport=transport(
            [issue()], {"Link": '<https://other.invalid/private?page=2>; rel="next"'}
        ),
    )
    assert value["status"] == "partial"
    assert len(value["pages"]) == 1
    assert any("scope" in message for message in value["limitations"])


def test_duplicate_json_cannot_replace_provider_identity(tmp_path: Path) -> None:
    value = collect(
        request(),
        tmp_path / "result",
        transport=lambda *_: (200, {}, b'[{"number":1,"number":2}]'),
    )
    assert value["status"] == "unavailable"
    assert value["issue_count"] is None
    assert any("Duplicate" in message for message in value["limitations"])


def test_real_worker_deadline_reaps_network_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.issue_tracker as module
    import os
    import time

    # The wall deadline includes isolated interpreter bootstrap. Capture the
    # actual process at spawn, so reaping is still checked when bootstrap takes
    # longer than200ms and the worker never reaches its first Python statement.
    processes = []
    original_popen = module.subprocess.Popen

    def observed_popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        processes.append(process)
        return process

    script = "import time;time.sleep(10)"
    monkeypatch.setattr(module, "_HTTP_WORKER", script)
    monkeypatch.setattr(module.subprocess, "Popen", observed_popen)
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="reaped"):
        module._transport(1024)("https://api.github.com/repos/fmtlib/fmt/issues", 0.2)
    assert len(processes) == 1 and processes[0].returncode is not None
    assert time.monotonic() - started < 2
    with pytest.raises(ProcessLookupError):
        os.kill(processes[0].pid, 0)


def test_oversize_page_retains_only_bounded_prefix_and_unknown_total(
    tmp_path: Path,
) -> None:
    config = request()
    config["limits"]["page_bytes"] = 1024
    value = collect(
        config, tmp_path / "result", transport=lambda *_: (200, {}, b"x" * 2048)
    )
    assert value["status"] == "unavailable"
    assert value["issue_count"] is None
    assert value["pages"][0]["truncated"] is True
    assert (tmp_path / "result/page-001.body").stat().st_size == 1024
    assert (tmp_path / "result/request.json").is_file()


def test_provider_numeric_pagination_stays_on_configured_request_scope(
    tmp_path: Path,
) -> None:
    urls = []

    def get(url, timeout):
        urls.append(url)
        if len(urls) == 1:
            return transport(
                [issue()],
                {
                    "Link": '<https://api.github.com/repositories/123/issues?page=2>; rel="next"'
                },
            )(url, timeout)
        return transport([issue(2)])(url, timeout)

    value = collect(request(), tmp_path / "result", transport=get)
    assert value["status"] == "complete"
    assert value["issue_count"] == 2
    assert all("/repos/manju89jay/cppulse/issues?" in url for url in urls)


def test_response_after_budget_preserves_raw_prefix_without_claiming_parsed_issues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cppulse.issue_tracker as module

    readings = iter([0, 0, 11])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(readings))
    value = collect(request(), tmp_path / "result", transport=transport([issue()]))
    assert value["status"] == "unavailable"
    assert value["issues"] == []
    assert value["pages"][0]["parse_status"] == "not_attempted"


def test_projection_mutation_and_raw_page_corruption_are_rejected(
    tmp_path: Path,
) -> None:
    from copy import deepcopy
    from cppulse.issue_tracker import validate_report

    config = request()
    output = tmp_path / "result"
    value = collect(config, output, transport=transport([issue()]))
    altered = deepcopy(value)
    altered["issues"][0]["title"] = "invented"
    with pytest.raises(ContractError, match="projection"):
        validate_report(altered, expected_request=config, output=output)
    (output / "page-001.body").write_bytes(b"[]")
    with pytest.raises(ContractError, match="bytes"):
        validate_report(value, expected_request=config, output=output)


def test_decimal_caller_precision_and_traps_do_not_change_retained_costs(
    tmp_path: Path,
) -> None:
    from decimal import localcontext, InvalidOperation

    config = request()
    config["cost_inputs"] = [
        {
            "id": str(index),
            "issue": 1,
            "kind": kind,
            "basis": "estimated",
            "currency": "USD",
            "amount": amount,
            "recorded_at": "2026-01-01T00:00:00Z",
            "description": "Declared fixture",
        }
        for index, (kind, amount) in enumerate([("cost", 100), ("benefit", 150)])
    ]
    one = collect(config, tmp_path / "normal", transport=transport([issue()]))
    with localcontext() as context:
        context.prec = 1
        context.Emax = 1
        context.traps[InvalidOperation] = False
        two = collect(config, tmp_path / "altered", transport=transport([issue()]))
    assert one["costs"] == two["costs"]
    assert two["costs"][0]["roi_ratio"] == "0.5"
    assert one["cost_method"] == "declared-monetary-inputs-decimal400-v1"


def test_opaque_after_cursor_is_preserved_on_configured_repository_url(
    tmp_path: Path,
) -> None:
    urls = []

    def get(url, timeout):
        urls.append(url)
        if len(urls) == 1:
            return transport(
                [issue()],
                {
                    "Link": '<https://api.github.com/repositories/123/issues?page=2&after=YWJjPQ%3D%3D>; rel="next"'
                },
            )(url, timeout)
        return transport([issue(2)])(url, timeout)

    value = collect(request(), tmp_path / "result", transport=get)
    assert value["status"] == "complete"
    assert urls[1].endswith("page=2&after=YWJjPQ%3D%3D")


@pytest.mark.parametrize(
    "link",
    [
        "not-a-link",
        "<https://api.github.com/repos/manju89jay/cppulse/issues?page=2>; rel=next",
        '<https://api.github.com/repos/manju89jay/cppulse/issues?page=2>; rel="next last"',
    ],
)
def test_unknown_or_next_relations_never_make_page_one_a_complete_total(
    tmp_path: Path, link: str
) -> None:
    config = request()
    config["limits"]["pages"] = 1
    value = collect(
        config, tmp_path / "result", transport=transport([issue()], {"Link": link})
    )
    assert value["status"] == "partial"
    assert value["issue_count"] is None


def test_deep_provider_json_preserves_prior_observations_as_partial(
    tmp_path: Path,
) -> None:
    def get(url, timeout):
        if "page=1" in url:
            return transport(
                [issue()],
                {
                    "Link": '<https://api.github.com/repos/manju89jay/cppulse/issues?page=2>; rel="next"'
                },
            )(url, timeout)
        return 200, {}, b"[" * 20000 + b"0" + b"]" * 20000

    value = collect(request(), tmp_path / "result", transport=get)
    assert value["status"] == "partial"
    assert value["issues"][0]["number"] == 1
    assert value["issue_count"] is None
    assert len(value["pages"]) == 2
    assert (tmp_path / "result/report.json").is_file()


@pytest.mark.parametrize("constant", [b"NaN", b"Infinity", b"1e9999"])
def test_provider_nonfinite_values_are_not_clean_even_in_unselected_fields(
    tmp_path: Path, constant: bytes
) -> None:
    raw = json.dumps(issue()).encode()[:-1] + b',"extra":' + constant + b"}"
    value = collect(
        request(),
        tmp_path / "result",
        transport=lambda *_: (200, {}, b"[" + raw + b"]"),
    )
    assert value["status"] == "unavailable"
    assert value["issue_count"] is None


def test_malformed_pr_marker_does_not_turn_unknown_rows_into_zero_issues(
    tmp_path: Path,
) -> None:
    value = collect(
        request(), tmp_path / "result", transport=transport([{"pull_request": False}])
    )
    assert value["status"] == "unavailable"
    assert value["issue_count"] is None
    assert value["excluded"]["pull_requests"] == 0


def test_duplicate_prs_are_not_a_complete_zero_issue_scope(tmp_path: Path) -> None:
    row = issue()
    row["html_url"] = "https://github.com/manju89jay/cppulse/pull/1"
    row["pull_request"] = {
        "url": "https://api.github.com/repos/manju89jay/cppulse/pulls/1",
        "html_url": row["html_url"],
        "diff_url": row["html_url"] + ".diff",
        "patch_url": row["html_url"] + ".patch",
    }

    def get(url, timeout):
        header = (
            {
                "Link": '<https://api.github.com/repos/manju89jay/cppulse/issues?page=2>; rel="next"'
            }
            if "page=1" in url
            else {}
        )
        return transport([row], header)(url, timeout)

    value = collect(request(), tmp_path / "result", transport=get)
    assert value["status"] != "complete"
    assert value["issue_count"] is None
    assert value["excluded"]["pull_requests"] == 1


def test_actual_http_multiple_link_fields_preserve_next_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Owned loopback protocol fixture, not evidence of a real GitHub integration.
    import cppulse.issue_tracker as module
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from urllib.parse import urlsplit, parse_qs

    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            page = int(parse_qs(urlsplit(self.path).query)["page"][0])
            received.append(page)
            body = json.dumps([issue(page)]).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            if page == 1:
                self.send_header(
                    "Link",
                    '<https://api.github.com/repos/manju89jay/cppulse/issues?page=1>; rel="first"',
                )
                self.send_header(
                    "Link",
                    '<https://api.github.com/repos/manju89jay/cppulse/issues?page=2>; rel="next"',
                )
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    replacement = f"sys.argv[1].replace('https://api.github.com','http://127.0.0.1:{server.server_port}')"
    monkeypatch.setattr(
        module, "_HTTP_WORKER", module._HTTP_WORKER.replace("sys.argv[1]", replacement)
    )
    try:
        value = collect(request(), tmp_path / "result")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    assert value["status"] == "complete"
    assert value["issue_count"] == 2
    assert received == [1, 2]
