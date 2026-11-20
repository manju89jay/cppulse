"""Finite read-only public GitHub observations and caller-declared cost views.

No tracker mutations, task inference, private-account authentication or messages
are supported. Provider state is observed now; historical state remains unknown.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import (
    Decimal,
    Context,
    localcontext,
    ROUND_HALF_EVEN,
    InvalidOperation,
    DivisionByZero,
    Overflow,
)
import hashlib
import base64
from importlib import resources
import json
import math
import os
import signal
from pathlib import Path
import re
import time
import subprocess
import sys
from typing import Any, Callable
import urllib.parse

import jsonschema

from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes

Transport = Callable[[str, float], tuple[int, dict[str, str], bytes]]
MAX_REQUEST_BYTES = 128 * 1024
COST_METHOD = "declared-monetary-inputs-decimal400-v1"
_ISSUE_VALIDATOR = jsonschema.validators.extend(
    jsonschema.Draft7Validator,
    type_checker=jsonschema.Draft7Validator.TYPE_CHECKER.redefine(
        "integer",
        lambda _checker, value: type(value) is int,  # noqa: E721 -- exact counts and issue identities
    ),
)


def _validate(kind: str, document: dict[str, Any]) -> None:
    schema = json.loads(
        resources.files("cppulse.contracts")
        .joinpath("schemas/issues_private", kind + ".schema.json")
        .read_bytes()
    )
    try:
        canonical_json_bytes(document)
        _ISSUE_VALIDATOR(schema, format_checker=jsonschema.FormatChecker()).validate(
            document
        )
    except (
        ValueError,
        TypeError,
        UnicodeError,
        RecursionError,
        jsonschema.ValidationError,
    ) as exc:
        raise ContractError(f"Invalid issue {kind}: {exc}") from exc


def _time(value: str) -> datetime:
    try:
        # fromisoformat silently truncates fractions beyond microseconds. That
        # could move a provider observation or future cost claim across a cutoff.
        # Reject unsupported precision rather than silently changing the input.
        if (
            not isinstance(value, str)
            or re.fullmatch(
                r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
                r"(?:\.[0-9]{1,6})?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})",
                value,
            )
            is None
        ):
            raise ValueError(
                "a timestamp with at most six fractional digits is required"
            )
        stamp = datetime.fromisoformat(
            value.replace("Z", "+00:00").replace("z", "+00:00")
        )
        if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
            raise ValueError("an aware UTC timestamp is required")
        return stamp
    except (ValueError, TypeError, AttributeError) as exc:
        raise ContractError(f"Invalid issue UTC timestamp: {value!r}") from exc


def validate_request(request: dict[str, Any]) -> None:
    """Validate bounded data before creating output or contacting a provider."""
    _validate("request", request)
    if len(canonical_json_bytes(request)) > MAX_REQUEST_BYTES:
        raise ContractError("Issue request exceeds 128 KiB")
    if (
        re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}",
            request["repository"],
        )
        is None
    ):
        raise ContractError(
            "Issue repository must be one canonical owner/repository identity"
        )
    if _time(request["window"]["start"]) >= _time(request["window"]["end"]):
        raise ContractError("Issue window must be increasing and half-open")
    identifiers = [row["id"] for row in request["cost_inputs"]]
    if len(identifiers) != len(set(identifiers)):
        raise ContractError("Cost input IDs must be unique")
    for row in request["cost_inputs"]:
        if re.fullmatch(r"[A-Z]{3}", row["currency"]) is None:
            raise ContractError(
                "Cost currency must be exactly three uppercase ASCII letters"
            )
        if (
            "evidence_sha256" in row
            and re.fullmatch(r"[a-f0-9]{64}", row["evidence_sha256"]) is None
        ):
            raise ContractError(
                "Cost evidence SHA256 must be exactly 64 lowercase hexadecimal characters"
            )
        _time(row["recorded_at"])


# A separate isolated Python process gives DNS, TLS and slow-body reads one
# parent-enforced wall deadline. Only stdlib code runs; response bytes are capped.
_HTTP_WORKER = r"""
import base64,json,sys,urllib.request,urllib.error
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args): return None
try:
    request=urllib.request.Request(sys.argv[1],headers={
        'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28',
        'User-Agent':'cppulse-readonly-issue-observer'})
    try:
        response=urllib.request.build_opener(NoRedirect()).open(request,timeout=float(sys.argv[3]))
    except urllib.error.HTTPError as error:
        response=error
    with response:
        links=response.headers.get_all('Link',[])
        etags=response.headers.get_all('ETag',[])
        if len(etags)>1:
            raise ValueError('Multiple ETag fields are unsupported')
        headers={'Link':','.join(links),'ETag':etags[0] if etags else ''}
        if any(len(value)>16384 for value in headers.values()):
            raise ValueError('Provider pagination/header exceeds finite bound')
        result={'status':response.code,'headers':headers,
                'body':base64.b64encode(response.read(int(sys.argv[2])+1)).decode('ascii')}
except Exception as error:
    result={'error':type(error).__name__+': '+str(error)[:512]}
print(json.dumps(result))
"""


def _transport(limit: int) -> Transport:
    def get(url: str, timeout: float) -> tuple[int, dict[str, str], bytes]:
        with subprocess.Popen(
            [sys.executable, "-I", "-c", _HTTP_WORKER, url, str(limit), str(timeout)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name == "posix",
        ) as process:

            def stop_and_reap() -> None:
                if process.poll() is None:
                    try:
                        if os.name == "posix":
                            os.killpg(process.pid, signal.SIGKILL)
                        else:
                            process.kill()
                    except ProcessLookupError:
                        pass
                # communicate's KeyboardInterrupt path can leave a killed child
                # unreaped; wait explicitly before propagating cancellation.
                process.wait()

            try:
                stdout, _ = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as error:
                stop_and_reap()
                raise TimeoutError(
                    "Provider worker exceeded overall wall budget and was reaped"
                ) from error
            except BaseException:
                stop_and_reap()
                raise
            returncode = process.returncode
        if returncode or len(stdout) > 2 * (limit + 1) + 262144:
            raise OSError("Bounded provider worker did not return a usable response")
        value = json.loads(stdout)
        if "error" in value:
            raise OSError(value["error"])
        return (
            value["status"],
            value["headers"],
            base64.b64decode(value["body"], validate=True),
        )

    return get


def _reject_constant(value: str) -> None:
    raise ContractError("Non-finite provider JSON constant: " + value)


def _finite_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ContractError("Provider JSON number exceeds finite numeric scope")
    return result


def _provider_json(body: bytes) -> Any:
    return json.loads(
        body,
        object_pairs_hook=_object_pairs,
        parse_constant=_reject_constant,
        parse_float=_finite_float,
    )


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("Duplicate provider JSON field")
        result[key] = value
    return result


def _issue(raw: Any, repository: str, *, is_pr: bool = False) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ContractError("Provider issue must be an object")
    number = raw.get("number")
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or not 1 <= number <= 2**63 - 1
    ):
        raise ContractError("Provider issue number is invalid")
    if (
        raw.get("state") not in ("open", "closed")
        or not isinstance(raw.get("title"), str)
        or len(raw["title"]) > 4096
    ):
        raise ContractError("Provider issue title/state is unsupported")
    try:
        raw["title"].encode("utf-8")
    except UnicodeError as error:
        raise ContractError("Provider title is not valid UTF-8") from error
    created, updated = _time(raw["created_at"]), _time(raw["updated_at"])
    closed = None if raw.get("closed_at") is None else _time(raw["closed_at"])
    if updated < created or (closed is not None and closed < created):
        raise ContractError("Provider issue dates contradict creation")
    if (
        (closed is not None and closed > updated)
        or (raw["state"] == "open" and closed is not None)
        or (raw["state"] == "closed" and closed is None)
    ):
        raise ContractError("Provider issue closure contradicts observed state/update")
    section = "pull" if is_pr else "issues"
    expected = f"https://github.com/{repository}/{section}/{number}"
    if raw.get("html_url") != expected:
        raise ContractError(
            "Provider issue identity differs from configured repository"
        )
    return {
        "id": f"github:{repository}#{number}",
        "number": number,
        "title": raw["title"],
        "url": expected,
        "created_at": created.isoformat(),
        "updated_at": updated.isoformat(),
        "closed_at_observed": None if closed is None else closed.isoformat(),
        "state_observed": raw["state"],
        "historical_state": "unknown",
    }


def _endpoint_record(raw: Any, repository: str) -> tuple[dict[str, Any], bool]:
    is_pr = isinstance(raw, dict) and "pull_request" in raw
    row = _issue(raw, repository, is_pr=is_pr)
    if is_pr:
        marker = raw["pull_request"]
        expected = {
            "url": f"https://api.github.com/repos/{repository}/pulls/{row['number']}",
            "html_url": row["url"],
            "diff_url": row["url"] + ".diff",
            "patch_url": row["url"] + ".patch",
        }
        if not isinstance(marker, dict) or any(
            marker.get(key) != value for key, value in expected.items()
        ):
            raise ContractError("Provider pull-request marker or scope is invalid")
    return row, is_pr


def _costs(
    request: dict[str, Any], issues: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    # 400 digits cover finite Python-float amounts down to subnormals, sums of
    # 1000 bounded inputs and deterministic ratios, independent of caller state.
    context = Context(
        prec=400,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[InvalidOperation, DivisionByZero, Overflow],
    )
    with localcontext(context):
        return _costs_precise(request, issues)


def _costs_precise(
    request: dict[str, Any], issues: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], int]:
    groups: dict[tuple[int, str, str], list[dict[str, Any]]] = defaultdict(list)
    future = 0
    for row in request["cost_inputs"]:
        if _time(row["recorded_at"]) > _time(request["window"]["end"]):
            future += 1
        else:
            groups[(row["issue"], row["basis"], row["currency"])].append(row)
    selected = {row["number"] for row in issues}
    result = []
    for (issue, basis, currency), rows in sorted(groups.items()):
        costs = [row for row in rows if row["kind"] == "cost"]
        benefits = [row for row in rows if row["kind"] == "benefit"]
        cost = sum((Decimal(str(row["amount"])) for row in costs), Decimal(0))
        benefit = sum((Decimal(str(row["amount"])) for row in benefits), Decimal(0))
        status = (
            "issue_not_observed"
            if issue not in selected
            else (
                "missing_cost"
                if not costs
                else (
                    "missing_benefit"
                    if not benefits
                    else "zero_cost_denominator"
                    if cost == 0
                    else "calculated"
                )
            )
        )
        result.append(
            {
                "issue": issue,
                "basis": basis,
                "currency": currency,
                "cost": str(cost) if costs else None,
                "benefit": str(benefit) if benefits else None,
                "status": status,
                "roi_ratio": (
                    str((benefit - cost) / cost) if status == "calculated" else None
                ),
                "input_ids": [row["id"] for row in rows],
                "evidence_status": "caller_claim_unverified",
            }
        )
    return result, future


def _page_url(repository: str, page: int, after: str | None = None) -> str:
    query = {"state": "all", "per_page": "100", "page": str(page)}
    if after is not None:
        query["after"] = after
    return (
        f"https://api.github.com/repos/{repository}/issues?"
        + urllib.parse.urlencode(query)
    )


def _headers(headers: dict[str, str]) -> dict[str, str]:
    """Normalize supported HTTP fields without erasing repeated Link evidence."""
    if not isinstance(headers, dict):
        raise ContractError("Provider headers must be a string mapping")
    links, etags = [], []
    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ContractError("Provider headers must be string fields")
        if key.lower() not in {"link", "etag"}:
            continue
        if "\r" in value or "\n" in value:
            raise ContractError("Folded provider headers are unsupported")
        if key.lower() == "link":
            if value.strip():
                links.append(value.strip())
        else:
            etags.append(value)
    link = ",".join(links)
    if len(link) > 16384 or len(etags) > 1 or (etags and len(etags[0]) > 1024):
        raise ContractError(
            "Provider headers exceed bounds or contain ambiguous ETag fields"
        )
    return {"link": link, "etag": etags[0] if etags else ""}


def _next_page(link: str, repository: str, page: int) -> str | None:
    if len(link) > 16384:
        raise ContractError("Provider pagination header exceeds finite bound")
    position = 0
    text = link.strip()
    targets: dict[str, tuple[str, str | None]] = {}
    pattern = re.compile(
        r'\s*<([^<>\s]+)>\s*;\s*rel\s*=\s*(?:"([^"\r\n]+)"|([A-Za-z][A-Za-z0-9_-]*))\s*(,|$)'
    )
    while position < len(text):
        match = pattern.match(text, position)
        if match is None:
            raise ContractError("Unsupported or malformed provider Link header")
        relations = (match[2] or match[3]).lower().split()
        if not relations or set(relations) - {"first", "prev", "next", "last"}:
            raise ContractError("Unsupported provider pagination relation")
        target = urllib.parse.urlsplit(match[1])
        query = urllib.parse.parse_qs(target.query, keep_blank_values=True)
        pages = query.get("page", [])
        if (
            target.scheme != "https"
            or target.netloc != "api.github.com"
            or target.fragment
            or not (
                target.path == f"/repos/{repository}/issues"
                or re.fullmatch(r"/repositories/[0-9]+/issues", target.path)
            )
            or len(pages) != 1
            or re.fullmatch(r"[1-9][0-9]*", pages[0]) is None
            or set(query) - {"page", "per_page", "state", "after"}
            or query.get("state", ["all"]) != ["all"]
            or query.get("per_page", ["100"]) != ["100"]
        ):
            raise ContractError("Provider pagination escapes configured public scope")
        after = query.get("after")
        if after is not None and (
            len(after) != 1
            or re.fullmatch(r"[A-Za-z0-9_+/=-]{1,4096}", after[0]) is None
        ):
            raise ContractError("Unsupported provider pagination cursor")
        number, cursor = pages[0], None if after is None else after[0]
        for relation in relations:
            if relation in targets:
                raise ContractError("Ambiguous provider pagination relation")
            expected = {"first": "1", "prev": str(page - 1), "next": str(page + 1)}.get(
                relation
            )
            if expected is not None and number != expected:
                raise ContractError(
                    "Provider pagination relation contradicts current page"
                )
            if relation == "last" and (len(number), number) < (
                len(str(page)),
                str(page),
            ):
                raise ContractError("Provider last page precedes current page")
            targets[relation] = number, cursor
        position = match.end()
        if match[4] == "," and position == len(text):
            raise ContractError("Malformed provider pagination separator")
    if "last" in targets:
        last = targets["last"][0]
        if "next" not in targets and last != str(page):
            raise ContractError(
                "Provider advertises later pages without a usable next relation"
            )
        if "next" in targets:
            following = targets["next"][0]
            if (len(last), last) < (len(following), following):
                raise ContractError("Provider next page exceeds declared last page")
    if "next" not in targets:
        return None
    return _page_url(repository, page + 1, targets["next"][1])


def validate_report(
    report: dict[str, Any], *, expected_request: dict[str, Any], output: Path
) -> None:
    """Check retained projection against explicit request pins and original pages."""
    from cppulse.run_store import _read

    validate_request(expected_request)
    _validate("report", report)
    request_bytes = canonical_json_bytes(expected_request)
    if (
        report["request_sha256"] != hashlib.sha256(request_bytes).hexdigest()
        or _read(Path(output) / "request.json", max_bytes=MAX_REQUEST_BYTES)
        != request_bytes
        or report["repository"] != expected_request["repository"]
        or report["window"] != expected_request["window"]
        or len(report["pages"]) > expected_request["limits"]["pages"]
    ):
        raise ContractError("Issue report differs from its selected request")
    rows, seen = [], set()
    pulls, outside = 0, 0
    stopped, last_next = False, True
    expected_url = _page_url(report["repository"], 1)
    for index, page in enumerate(report["pages"], 1):
        if stopped:
            raise ContractError(
                "Issue report contains pages after a retained terminal response"
            )
        if page["path"] != f"page-{index:03}.body" or page["url"] != expected_url:
            raise ContractError("Retained issue page escapes its request sequence")
        body = _read(
            Path(output) / page["path"],
            max_bytes=expected_request["limits"]["page_bytes"],
        )
        if (
            len(body) != page["size_bytes"]
            or hashlib.sha256(body).hexdigest() != page["sha256"]
        ):
            raise ContractError(
                "Retained issue page bytes differ from their descriptor"
            )
        if (
            page["http_status"] != 200
            or page["truncated"]
            or page["parse_status"] == "not_attempted"
        ):
            stopped = True
            continue
        try:
            raw_rows = _provider_json(body)
            if not isinstance(raw_rows, list) or len(raw_rows) > 100:
                raise ContractError("Unsupported provider page")
            for raw in raw_rows:
                row, is_pr = _endpoint_record(raw, report["repository"])
                if row["number"] in seen:
                    raise ContractError("Overlapping provider pages")
                seen.add(row["number"])
                if is_pr:
                    pulls += 1
                    continue
                if not (
                    _time(report["window"]["start"])
                    <= _time(row["created_at"])
                    < _time(report["window"]["end"])
                ):
                    outside += 1
                    continue
                rows.append(row)
            next_url = _next_page(page["link"], report["repository"], index)
            last_next = next_url is not None
            if next_url is not None:
                expected_url = next_url
            if not last_next:
                stopped = True
        except (ContractError, ValueError, TypeError, KeyError, RecursionError):
            stopped = True
            last_next = True
    rows.sort(key=lambda row: row["number"])
    costs, future = _costs(expected_request, rows)
    if (
        rows != report["issues"]
        or costs != report["costs"]
        or report["excluded"]
        != {
            "pull_requests": pulls,
            "outside_created_window": outside,
            "future_cost_inputs": future,
        }
    ):
        raise ContractError(
            "Issue or cost projection differs from its pinned raw inputs"
        )
    if report["status"] == "complete":
        if (
            not report["pages"]
            or last_next
            or any(
                page["http_status"] != 200
                or page["truncated"]
                or page["parse_status"] != "complete"
                for page in report["pages"]
            )
        ):
            raise ContractError(
                "Incomplete provider scope cannot claim complete issue data"
            )
        if report["issue_count"] != len(rows):
            raise ContractError("Complete issue count differs from retained scope")
    elif report["issue_count"] is not None:
        raise ContractError("Incomplete issue scope must retain an unknown total")


def collect(
    request: dict[str, Any], output: Path, *, transport: Transport | None = None
) -> dict[str, Any]:
    """Read explicit public scope into a new retained output; no external writes."""
    request = deepcopy(request)
    validate_request(request)
    output = Path(output).absolute()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise ContractError("Issue output must be a new writable directory") from exc
    with (output / "request.json").open("xb") as stream:
        stream.write(canonical_json_bytes(request))
    started = datetime.now(timezone.utc).isoformat()
    deadline = time.monotonic() + request["limits"]["wall_seconds"]
    get = transport or _transport(request["limits"]["page_bytes"])
    repository = request["repository"]
    pages, issues, limitations = [], [], []
    seen = set()
    pull_requests, outside = 0, 0
    finished = False
    url = _page_url(repository, 1)
    for page in range(1, request["limits"]["pages"] + 1):
        try:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Overall issue collection wall budget exhausted")
            status, headers, body = get(url, remaining)
            if type(status) is not int or not 100 <= status <= 599:  # noqa: E721 -- no float/bool status coercion
                raise ContractError(
                    "Provider HTTP status must be an exact integer within 100..599"
                )
            if not isinstance(body, bytes):
                raise ContractError("Provider response body is not bytes")
            truncated = len(body) > request["limits"]["page_bytes"]
            retained = body[: request["limits"]["page_bytes"]]
            relative = f"page-{page:03}.body"
            with (output / relative).open("xb") as stream:
                stream.write(retained)
            header_problem = None
            try:
                headers = _headers(headers)
            except ContractError as error:
                headers = {}
                header_problem = error
            pages.append(
                {
                    "url": url,
                    "http_status": status,
                    "path": relative,
                    "sha256": hashlib.sha256(retained).hexdigest(),
                    "size_bytes": len(retained),
                    "truncated": truncated,
                    "parse_status": "not_attempted",
                    "link": headers.get("link", "")[:16384],
                    "etag": headers.get("etag", "")[:1024],
                }
            )
            if header_problem is not None:
                raise header_problem
            if truncated:
                raise ContractError(
                    "Provider page exceeds configured byte limit; only bounded prefix retained"
                )
            if time.monotonic() >= deadline:
                raise TimeoutError("Provider response exceeded overall wall budget")
            if status != 200:
                raise ContractError(
                    f"Provider HTTP status {status}; total issue scope unavailable"
                )
            pages[-1]["parse_status"] = "attempted"
            rows = _provider_json(body)
            if not isinstance(rows, list) or len(rows) > 100:
                raise ContractError("Provider page must contain at most100 issues")
            for raw in rows:
                row, is_pr = _endpoint_record(raw, repository)
                if row["number"] in seen:
                    raise ContractError(
                        "Provider pages overlap; transactional snapshot is unavailable"
                    )
                seen.add(row["number"])
                if is_pr:
                    pull_requests += 1
                    continue
                if (
                    not _time(request["window"]["start"])
                    <= _time(row["created_at"])
                    < _time(request["window"]["end"])
                ):
                    outside += 1
                    continue
                issues.append(row)
            pages[-1]["parse_status"] = "complete"
            if time.monotonic() >= deadline:
                raise TimeoutError("Provider parsing exceeded overall wall budget")
            next_url = _next_page(headers.get("link", ""), repository, page)
            if next_url is None:
                finished = True
                break
            url = next_url
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            ContractError,
            RecursionError,
        ) as error:
            limitations.append(str(error)[:1024])
            break
    if not finished and not limitations:
        limitations.append(
            "Provider page budget exhausted; total issue scope unavailable"
        )
    issues.sort(key=lambda row: row["number"])
    costs, future = _costs(request, issues)
    report = {
        "version": "1.0.0",
        "provider": request["provider"],
        "repository": repository,
        "status": "complete" if finished else "partial" if issues else "unavailable",
        "issue_count": len(issues) if finished else None,
        "issues": issues,
        "pages": pages,
        "costs": costs,
        "cost_method": COST_METHOD,
        "request_sha256": hashlib.sha256(canonical_json_bytes(request)).hexdigest(),
        "transport": "https-public-github" if transport is None else "caller_transport",
        "window": request["window"],
        "excluded": {
            "pull_requests": pull_requests,
            "outside_created_window": outside,
            "future_cost_inputs": future,
        },
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "limitations": limitations
        + [
            "Public REST observations are not an atomic provider snapshot or reconstructed historical state.",
            "Costs and benefits are explicit caller claims, separated by basis/currency; no currency conversion or inferred savings.",
            "Evidence hashes retain declared claims; no financial authentication or causal ROI is established.",
        ],
    }
    validate_report(report, expected_request=request, output=output)
    with (output / "report.json").open("xb") as stream:
        stream.write(canonical_json_bytes(report))
    return report
