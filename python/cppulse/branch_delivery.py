"""Private bounded local Git branch facts and caller-declared delivery linkage.

No fetch, checkout, ref update, task inference, provider write or DORA claim is
performed. Ref tips are observed now under explicit pins; historical ref states
are not reconstructed by applying a commit timestamp cutoff.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib import resources
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import time
from typing import Any

import jsonschema

from cppulse.errors import ContractError
from cppulse.execution import CancellationToken, ProcessLimits, run_bounded_process
from cppulse.identities import canonical_json_bytes, digest_json

_SHA = re.compile(r"(?:[a-f0-9]{40}|[a-f0-9]{64})\Z")
MAX_CAPTURE_BYTES = 32 * 1024 * 1024
MAX_REPORT_BYTES = 16 * 1024 * 1024
_SUPPORTED_GIT = re.compile(r"git version 2\.52\.\d+(?:[ .+-].*)?\Z")
_OVERRIDES = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_NAMESPACE",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
    "GIT_CONFIG",
    "GIT_SHALLOW_FILE",
)


def _validate(kind: str, value: dict[str, Any]) -> None:
    schema = json.loads(
        resources.files("cppulse.contracts")
        .joinpath("schemas", "branch_delivery_private", kind + ".schema.json")
        .read_bytes()
    )
    try:
        jsonschema.Draft7Validator.check_schema(schema)
        jsonschema.Draft7Validator(
            schema, format_checker=jsonschema.FormatChecker()
        ).validate(value)
        canonical_json_bytes(value)
    except (
        jsonschema.ValidationError,
        jsonschema.SchemaError,
        ValueError,
        TypeError,
    ) as error:
        message = (
            error.message
            if isinstance(error, jsonschema.ValidationError)
            else str(error)
        )
        raise ContractError(
            "Invalid private branch/delivery " + kind + ": " + message
        ) from error


def _time(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(
            value.replace("Z", "+00:00").replace("z", "+00:00")
        )
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError("Timezone required")
        return result.astimezone(timezone.utc)
    except (ValueError, OverflowError) as error:
        raise ContractError(
            "Branch/delivery timestamps must be aware ISO times"
        ) from error


def _epoch_microseconds(value: datetime) -> int:
    """Preserve the supported six fractional digits without float epoch loss."""
    delta = value - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def validate_config(config: dict[str, Any]) -> None:
    """Validate explicit ref pins, linkage and cutoff semantics before Git reads."""
    _validate("config", config)
    if len(canonical_json_bytes(config)) > 512 * 1024:
        raise ContractError("Branch/delivery configuration exceeds 512 KiB")
    if _time(config["window_start"]) >= _time(config["cutoff"]):
        raise ContractError("Branch/delivery window must have positive duration")
    for name in ("refs", "tasks", "deliveries"):
        ids = [row["id"] for row in config[name]]
        if len(ids) != len(set(ids)):
            raise ContractError("Duplicate branch/delivery " + name + " IDs")
    if config["target_ref_id"] not in {row["id"] for row in config["refs"]}:
        raise ContractError("Target ref is not explicitly selected")
    refs = [row["ref"] for row in config["refs"]]
    if len(set(refs)) != len(refs):
        raise ContractError("A ref cannot be counted under multiple branch IDs")
    for ref in refs:
        if (
            not ref.startswith(("refs/heads/", "refs/remotes/"))
            or any(
                ord(char) < 33 or ord(char) == 127 or char in "~^:?*[\\" for char in ref
            )
            or any(token in ref for token in ("..", "@{", "//"))
            or ref.endswith(("/", "."))
            or any(
                part.startswith(".") or part.endswith(".lock")
                for part in ref.split("/")
            )
        ):
            raise ContractError(
                "Expected an explicit canonical local branch/tracking ref, not a revision expression"
            )
    for task in config["tasks"]:
        recorded = _time(task["recorded_at"])
        start = _time(task["started_at"]) if task["started_at"] else None
        end = _time(task["completed_at"]) if task["completed_at"] else None
        if (
            (start and start > recorded)
            or (end and end > recorded)
            or (start and end and end < start)
        ):
            raise ContractError(
                "Declared task times contradict their recorded availability"
            )
    for event in config["deliveries"]:
        if _time(event["occurred_at"]) > _time(event["recorded_at"]):
            raise ContractError(
                "A delivery claim cannot be recorded before its claimed occurrence"
            )


def _file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > 64 * 1024 * 1024:
            raise ContractError("Git executable must be a regular file within 64 MiB")
        digest = hashlib.sha256()
        count = 0
        while chunk := stream.read(1024 * 1024):
            count += len(chunk)
            if count > 64 * 1024 * 1024:
                raise ContractError("Git executable grew beyond its byte budget")
            digest.update(chunk)
    return digest.hexdigest()


def _parse_graph(
    raw: str, maximum: int
) -> tuple[list[dict[str, Any]], list[str], bool]:
    lines = raw.splitlines()
    notes = []
    if raw and not raw.endswith("\n"):
        lines = lines[:-1]
        notes.append("Final graph row is incomplete and was not interpreted.")
    nodes = []
    seen = set()
    for index, line in enumerate(lines):
        tokens = line.split()
        try:
            if (
                len(tokens) < 2
                or len(tokens) > 66
                or not all(_SHA.fullmatch(value) for value in tokens[1:])
            ):
                raise ValueError("Invalid graph fields")
            timestamp = int(tokens[0])
            if not -62135596800 <= timestamp <= 253402300799:
                raise ValueError("Unsupported commit time")
            row = {"id": tokens[1], "committed_at": timestamp, "parents": tokens[2:]}
            if row["id"] in seen or len(set(row["parents"])) != len(row["parents"]):
                raise ContractError("Duplicate graph commit or parent identity")
            seen.add(row["id"])
            nodes.append(row)
        except ContractError:
            raise
        except ValueError:
            notes.append(
                f"Graph row {index + 1} is malformed or outside the finite profile."
            )
    truncated = len(nodes) > maximum
    return nodes[:maximum], notes, truncated


def _git_prefix(executable: str, repo: str) -> list[str]:
    """One finite POSIX read-only Git invocation profile shared by capture/replay."""
    return [
        executable,
        "--no-pager",
        "--no-replace-objects",
        "--no-optional-locks",
        "--no-lazy-fetch",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=" + "/dev/null",
        "-c",
        "gc.auto=0",
        "-c",
        "maintenance.auto=false",
        "-c",
        "protocol.allow=never",
        "-C",
        repo,
    ]


def collect_branch_graph(
    repo: Path, config: dict[str, Any], *, cancel: CancellationToken | None = None
) -> dict[str, Any]:
    """Capture finite all-parent metadata from pinned refs using supervised Git.

    Supported producer slice: local POSIX Git 2.52.x. Logs/wall time are bounded;
    Python/filesystem wall time, OS CPU/memory budgets and complete object-database
    authentication are not claimed. Shallow, promisor, changed refs and missing data stay explicit.
    """
    config = deepcopy(config)
    validate_config(config)
    repo = repo.absolute()
    limits = config["limits"]
    packet = {
        "version": "1.0.0",
        "configuration_digest": digest_json(config),
        "repo_path": str(repo),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "tool": None,
        "refs": [
            {
                **row,
                "observed_tip": None,
                "status": "unavailable",
                "reason": "Not observed",
            }
            for row in config["refs"]
        ],
        "nodes": [],
        "raw_graph": "",
        "raw_graph_sha256": hashlib.sha256(b"").hexdigest(),
        "shallow": None,
        "truncated": False,
        "graph_command_complete": False,
        "commands": [],
        "limitations": [],
    }
    executable = shutil.which("git")
    ambient = [
        key
        for key in _OVERRIDES
        if os.environ.get(key) not in (None, "")
        and not (key == "GIT_CONFIG_COUNT" and os.environ.get(key) == "0")
    ]
    if os.name != "posix" or executable is None or not repo.is_dir() or ambient:
        packet["limitations"].append(
            "POSIX Git executable/repository unavailable or ambient Git repository/configuration overrides must be cleared."
        )
        return packet
    executable_path = Path(executable).resolve()
    deadline = time.monotonic() + limits["total_timeout_seconds"]
    environment = {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_CONFIG_COUNT": "0",
        "GIT_CONFIG_PARAMETERS": "",
        "GIT_INDEX_FILE": os.devnull,
        "GIT_ATTR_SOURCE": "",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CURL_VERBOSE": "",
        "GIT_TRACE2": "0",
        "GIT_TRACE2_EVENT": "0",
        "GIT_TRACE2_PERF": "0",
        "GIT_PREFIX": "",
        "GIT_CEILING_DIRECTORIES": "",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_GRAFT_FILE": os.devnull,
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_PAGER": "cat",
    }
    # Git trace destinations are open-ended; inherited tracing must never
    # create files during a local read. Known selectors above are denied or
    # pinned explicitly, rather than borrowing caller-selected metadata.
    environment.update({key: "" for key in os.environ if key.startswith("GIT_TRACE")})
    prefix = _git_prefix(str(executable_path), str(repo))

    def run(
        arguments: list[str], *, version: bool = False
    ) -> tuple[int | None, str, bool]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            packet["limitations"].append("Total Git metadata wall budget exhausted.")
            return None, "", True
        stdout, stderr = io.BytesIO(), io.BytesIO()
        argv = [str(executable_path), "--version"] if version else prefix + arguments
        started = time.perf_counter()
        outcome = run_bounded_process(
            argv,
            cwd=repo,
            stdout=stdout,
            stderr=stderr,
            timeout_seconds=min(remaining, limits["command_timeout_seconds"]),
            limits=ProcessLimits(max_log_bytes=limits["max_output_bytes"]),
            cancel=cancel,
            environment=environment,
        )
        raw = stdout.getvalue()
        truncated = (
            len(raw) < outcome.stdout_bytes
            or outcome.captured_bytes < outcome.stdout_bytes + outcome.stderr_bytes
        )
        packet["commands"].append(
            {
                "argv": argv,
                "status": outcome.status,
                "returncode": outcome.returncode,
                "wall_seconds": time.perf_counter() - started,
                "stdout_sha256": hashlib.sha256(raw).hexdigest(),
                "stderr_sha256": hashlib.sha256(stderr.getvalue()).hexdigest(),
                "stdout_bytes": outcome.stdout_bytes,
                "stderr_bytes": outcome.stderr_bytes,
                "captured_bytes": outcome.captured_bytes,
                "truncated": truncated,
                "stderr_tail": stderr.getvalue()[-1000:].decode(
                    "utf-8", errors="replace"
                ),
            }
        )
        if outcome.status in {"timed_out", "cancelled", "error"}:
            packet["limitations"].append(
                "Git metadata command " + outcome.status + ": " + outcome.reason
            )
        return outcome.returncode, raw.decode("utf-8", errors="strict"), truncated

    try:
        before = _file_hash(executable_path)
        code, version, cut = run([], version=True)
        packet["tool"] = {
            "path": str(executable_path),
            "version": version.strip()[:256],
            "sha256_before": before,
            "sha256_after": None,
            "stable": False,
        }
        if code != 0 or cut or not _SUPPORTED_GIT.fullmatch(version.strip()):
            packet["limitations"].append(
                "Git producer version is unavailable or outside the qualified 2.52.x local profile."
            )
            return packet
        code, bare, cut = run(["rev-parse", "--is-bare-repository"])
        if code != 0 or cut or bare.strip() not in {"true", "false"}:
            packet["limitations"].append(
                "Selected local Git repository is unavailable."
            )
            return packet
        if bare.strip() == "false":
            code, top, cut = run(["rev-parse", "--show-toplevel"])
            if (
                code != 0
                or cut
                or Path(top.removesuffix("\n")).resolve() != repo.resolve()
            ):
                packet["limitations"].append(
                    "Select the explicit repository root, not an inferred parent repository."
                )
                return packet
        code, promisor, cut = run(
            [
                "config",
                "--local",
                "--get-regexp",
                r"^(extensions\.partialclone|remote\..*\.promisor)$",
            ]
        )
        if cut or code not in {0, 1} or promisor.strip():
            packet["limitations"].append(
                "Promisor/partial-clone metadata is unsupported; no lazy fetch is permitted."
            )
            return packet
        code, shallow, cut = run(["rev-parse", "--is-shallow-repository"])
        if code == 0 and not cut and shallow.strip() in {"true", "false"}:
            packet["shallow"] = shallow.strip() == "true"
        if packet["shallow"] is not False:
            packet["limitations"].append(
                "Shallow or unavailable history boundaries prevent complete negative reachability claims."
            )
        for row in packet["refs"]:
            code, output, cut = run(
                ["rev-parse", "--verify", "--end-of-options", row["ref"] + "^{commit}"]
            )
            tip = output.strip()
            if code != 0 or cut or not _SHA.fullmatch(tip):
                row.update(
                    status="missing",
                    reason="Selected ref could not be observed within the finite profile",
                )
            else:
                row["observed_tip"] = tip
                row.update(
                    status="matched" if tip == row["expected_tip"] else "mismatched",
                    reason=(
                        "Exact selected ref pin matched"
                        if tip == row["expected_tip"]
                        else "Observed ref differs from requested pin"
                    ),
                )
        tips = sorted(
            {
                row["observed_tip"]
                for row in packet["refs"]
                if row["status"] == "matched"
            }
        )
        if tips:
            code, raw, cut = run(
                [
                    "rev-list",
                    "--topo-order",
                    "--timestamp",
                    "--parents",
                    "--max-count=" + str(limits["max_commits"] + 1),
                    *tips,
                    "--",
                ]
            )
            packet["raw_graph"] = raw
            packet["raw_graph_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            packet["nodes"], notes, capped = _parse_graph(raw, limits["max_commits"])
            packet["truncated"] = cut or capped
            packet["graph_command_complete"] = code == 0 and not cut and not notes
            packet["limitations"].extend(notes)
            if cut or capped:
                packet["limitations"].append(
                    "Graph extraction reached its commit/output bound; absent ancestry remains unknown."
                )
            if code != 0:
                packet["limitations"].append(
                    "Git graph extraction did not complete successfully."
                )
        for row in packet["refs"]:
            if row["status"] != "matched":
                continue
            code, output, cut = run(
                ["rev-parse", "--verify", "--end-of-options", row["ref"] + "^{commit}"]
            )
            if code != 0 or cut or output.strip() != row["expected_tip"]:
                row.update(
                    status="changed",
                    reason="Ref pin changed or became unavailable during capture",
                )
    except (OSError, ContractError, UnicodeError) as error:
        packet["limitations"].append("Local Git capture unavailable: " + str(error))
    finally:
        if packet["tool"] is not None:
            try:
                after = _file_hash(executable_path)
                packet["tool"]["sha256_after"] = after
                packet["tool"]["stable"] = after == packet["tool"]["sha256_before"]
            except (OSError, ContractError):
                packet["tool"]["stable"] = False
            if not packet["tool"]["stable"]:
                packet["limitations"].append(
                    "Observed Git executable changed or became unavailable during capture."
                )
                for row in packet["refs"]:
                    row.update(
                        status="unavailable",
                        reason="Git executable identity was unstable",
                    )
    packet["limitations"] = list(dict.fromkeys(packet["limitations"]))
    validate_capture(packet, config=config)
    return packet


def validate_capture(capture: dict[str, Any], *, config: dict[str, Any]) -> None:
    """Reject raw/parsed graph drift, scope substitution and cyclic metadata."""
    validate_config(config)
    _validate("capture", capture)
    process_strings = [
        capture["repo_path"],
        *([capture["tool"]["path"]] if capture["tool"] is not None else []),
        *[argument for command in capture["commands"] for argument in command["argv"]],
    ]
    for value in process_strings:
        if "\x00" in value:
            raise ContractError("Captured Git process arguments cannot contain NUL")
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeError as error:
            raise ContractError(
                "Captured Git process strings must be valid UTF-8"
            ) from error
    if len(canonical_json_bytes(capture)) > MAX_CAPTURE_BYTES:
        raise ContractError("Captured metadata exceeds 32 MiB")
    if capture["configuration_digest"] != digest_json(config):
        raise ContractError("Graph capture configuration differs")
    if [(r["id"], r["ref"], r["expected_tip"]) for r in capture["refs"]] != [
        (r["id"], r["ref"], r["expected_tip"]) for r in config["refs"]
    ]:
        raise ContractError("Graph ref inventory differs from explicit request")
    if (
        hashlib.sha256(capture["raw_graph"].encode("utf-8")).hexdigest()
        != capture["raw_graph_sha256"]
    ):
        raise ContractError("Original graph bytes differ from their digest")
    nodes, parse_notes, capped = _parse_graph(
        capture["raw_graph"], config["limits"]["max_commits"]
    )
    if nodes != capture["nodes"] or (capped and not capture["truncated"]):
        raise ContractError("Parsed graph facts differ from original retained bytes")
    tool = capture["tool"]
    if (
        tool is not None
        and tool["stable"]
        and (
            tool["sha256_after"] is None
            or tool["sha256_before"] != tool["sha256_after"]
        )
    ):
        raise ContractError("Stable Git tool flag contradicts executable identities")
    for ref in capture["refs"]:
        if ref["status"] == "matched" and (
            ref["observed_tip"] != ref["expected_tip"]
            or tool is None
            or not tool["stable"]
            or not _SUPPORTED_GIT.fullmatch(tool["version"])
        ):
            raise ContractError(
                "Matched ref lacks an exact pin and supported stable producer"
            )
    receipts = [row for row in capture["commands"] if "rev-list" in row["argv"]]
    # Output hashes alone cannot establish all-parent, unfiltered ancestry or
    # the requested traversal bound. Bind the command to the pins actually
    # matched before extraction, including pins marked changed/unavailable by
    # the subsequent ref/tool stability probes.
    selected_tips = sorted(
        {
            row["observed_tip"]
            for row in capture["refs"]
            if row["observed_tip"] == row["expected_tip"]
        }
    )
    graph_arguments = [
        "rev-list",
        "--topo-order",
        "--timestamp",
        "--parents",
        "--max-count=" + str(config["limits"]["max_commits"] + 1),
        *selected_tips,
        "--",
    ]
    if any(
        not selected_tips
        or row["argv"][row["argv"].index("rev-list") :] != graph_arguments
        for row in receipts
    ):
        raise ContractError(
            "Graph command differs from the selected pinned all-parent extraction"
        )
    allowed_arguments = {
        ("rev-parse", "--is-bare-repository"),
        ("rev-parse", "--show-toplevel"),
        ("rev-parse", "--is-shallow-repository"),
        (
            "config",
            "--local",
            "--get-regexp",
            r"^(extensions\.partialclone|remote\..*\.promisor)$",
        ),
        tuple(graph_arguments),
        *[
            ("rev-parse", "--verify", "--end-of-options", ref["ref"] + "^{commit}")
            for ref in config["refs"]
        ],
    }
    if not Path(capture["repo_path"]).is_absolute() or (
        tool is not None and not Path(tool["path"]).is_absolute()
    ):
        raise ContractError("Captured Git repository/tool paths must be absolute")
    for command in capture["commands"]:
        argv = command["argv"]
        executable = tool["path"] if tool is not None else argv[0]
        prefix = _git_prefix(executable, capture["repo_path"])
        if argv != [executable, "--version"] and (
            tool is None
            or argv[: len(prefix)] != prefix
            or tuple(argv[len(prefix) :]) not in allowed_arguments
        ):
            raise ContractError(
                "Git command differs from captured tool/repository/read-only profile"
            )
        total = command["stdout_bytes"] + command["stderr_bytes"]
        if (
            command["captured_bytes"] > config["limits"]["max_output_bytes"]
            or command["captured_bytes"] > total
            or command["truncated"] != (command["captured_bytes"] < total)
        ):
            raise ContractError(
                "Git command capture counts contradict byte limits or truncation"
            )
        for stream in ("stdout", "stderr"):
            if (
                command[stream + "_bytes"] == 0
                and command[stream + "_sha256"] != hashlib.sha256(b"").hexdigest()
            ):
                raise ContractError("Empty Git stream contradicts retained digest")
    if (capture["raw_graph"] or receipts) and (
        len(receipts) != 1
        or receipts[0]["stdout_sha256"] != capture["raw_graph_sha256"]
    ):
        raise ContractError("Raw graph differs from observed command output identity")
    if receipts:
        size = len(capture["raw_graph"].encode("utf-8"))
        receipt = receipts[0]
        if (
            size > receipt["stdout_bytes"]
            or size > receipt["captured_bytes"]
            or (not receipt["truncated"] and size != receipt["stdout_bytes"])
        ):
            raise ContractError("Git graph byte counts differ from retained stdout")
    if capture["graph_command_complete"] and (
        parse_notes
        or len(receipts) != 1
        or receipts[0]["returncode"] != 0
        or receipts[0]["status"] != "passed"
        or receipts[0]["truncated"]
    ):
        raise ContractError(
            "Complete graph flag contradicts parsing or execution facts"
        )

    # Replay positive probe claims against retained command output identities.
    # Hashes bind these facts to their receipts, without claiming authenticity.
    def successful_probe(arguments: list[str], output: str) -> list[dict[str, Any]]:
        expected = hashlib.sha256(output.encode("utf-8")).hexdigest()
        return [
            row
            for row in capture["commands"]
            if row["argv"][-len(arguments) :] == arguments
            and row["status"] == "passed"
            and row["returncode"] == 0
            and not row["truncated"]
            and row["stdout_sha256"] == expected
            and row["stdout_bytes"] == len(output.encode("utf-8"))
        ]

    positive = bool(
        capture["raw_graph"]
        or capture["shallow"] is not None
        or any(ref["status"] == "matched" for ref in capture["refs"])
    )
    if positive and (
        tool is None
        or len(successful_probe(["--version"], tool["version"] + "\n")) != 1
        or capture["commands"][0]["argv"] != [tool["path"], "--version"]
    ):
        raise ContractError(
            "Supported Git version claim lacks its original successful version probe"
        )
    if capture["shallow"] is not None and not successful_probe(
        ["rev-parse", "--is-shallow-repository"],
        ("true" if capture["shallow"] else "false") + "\n",
    ):
        raise ContractError("Shallow boundary flag contradicts retained probe receipt")
    for ref in capture["refs"]:
        if (
            ref["status"] == "matched"
            and len(
                successful_probe(
                    [
                        "rev-parse",
                        "--verify",
                        "--end-of-options",
                        ref["ref"] + "^{commit}",
                    ],
                    ref["expected_tip"] + "\n",
                )
            )
            != 2
        ):
            raise ContractError(
                "Matched ref lacks consistent before/after probe receipts"
            )
    for ref in capture["refs"]:
        if ref["status"] != "matched":
            continue
        matched = successful_probe(
            ["rev-parse", "--verify", "--end-of-options", ref["ref"] + "^{commit}"],
            ref["expected_tip"] + "\n",
        )
        positions = [
            index
            for index, command in enumerate(capture["commands"])
            if command in matched
        ]
        graph_positions = [
            index
            for index, command in enumerate(capture["commands"])
            if "rev-list" in command["argv"]
        ]
        if (
            len(positions) != 2
            or len(graph_positions) != 1
            or not positions[0] < graph_positions[0] < positions[1]
        ):
            raise ContractError(
                "Matched ref probes do not bracket original graph extraction"
            )
    formats = (
        {len(row["id"]) for row in nodes}
        | {len(parent) for row in nodes for parent in row["parents"]}
        | {len(row["observed_tip"]) for row in capture["refs"] if row["observed_tip"]}
    )
    if len(formats) > 1:
        raise ContractError(
            "One Git object graph cannot mix SHA-1 and SHA-256 identities"
        )
    graph = {row["id"]: row for row in nodes}
    visiting, done = set(), set()
    for root in graph:
        stack = [(root, False)]
        while stack:
            node, exiting = stack.pop()
            if node not in graph or node in done:
                continue
            if exiting:
                visiting.discard(node)
                done.add(node)
                continue
            if node in visiting:
                raise ContractError("Cyclic Git graph is not supported")
            visiting.add(node)
            stack.append((node, True))
            stack.extend((parent, False) for parent in graph[node]["parents"])


def _closure(tip: str, graph: dict[str, dict[str, Any]]) -> tuple[set[str], bool]:
    seen, stack = set(), [tip]
    complete = True
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        if node not in graph:
            complete = False
            continue
        stack.extend(graph[node]["parents"])
    return seen, complete


def analyze_branch_delivery(
    config: dict[str, Any], capture: dict[str, Any]
) -> dict[str, Any]:
    """Derive selected-tip graph facts and explicitly qualified declared linkage."""
    validate_capture(capture, config=config)
    stable = capture["tool"] is not None and capture["tool"].get("stable") is True
    graph = {row["id"]: row for row in capture["nodes"]} if stable else {}
    refs = {row["id"]: row for row in capture["refs"]}
    closures = {
        key: _closure(row["expected_tip"], graph)
        for key, row in refs.items()
        if row["status"] == "matched"
    }
    start, cutoff = _time(config["window_start"]), _time(config["cutoff"])
    start_epoch, end_epoch = _epoch_microseconds(start), _epoch_microseconds(cutoff)
    target = refs[config["target_ref_id"]]
    target_set, target_closed = closures.get(target["id"], (set(), False))
    branches = []
    for selected in config["refs"]:
        row = refs[selected["id"]]
        reachable, closed = closures.get(row["id"], (set(), False))
        complete = (
            closed and capture["shallow"] is False and capture["graph_command_complete"]
        )
        observed = reachable & graph.keys()
        in_window = sorted(
            node
            for node in observed
            if start_epoch <= graph[node]["committed_at"] * 1_000_000 < end_epoch
        )
        relation, ahead, behind, bases = "unknown", None, None, None
        if row["status"] == target["status"] == "matched" and stable:
            if row["expected_tip"] == target["expected_tip"]:
                relation, ahead, behind, bases = "equal", 0, 0, [row["expected_tip"]]
            elif row["expected_tip"] in target_set:
                relation = "ancestor_of_target"
            elif target["expected_tip"] in reachable:
                relation = "descendant_of_target"
            if complete and target_closed and capture["shallow"] is False:
                common = reachable & target_set
                parent_common = {
                    p for node in common for p in graph[node]["parents"] if p in common
                }
                bases = sorted(common - parent_common)
                ahead, behind = len(reachable - target_set), len(target_set - reachable)
                if relation == "unknown":
                    relation = "diverged" if common else "unrelated"
        branches.append(
            {
                "id": row["id"],
                "ref": row["ref"],
                "expected_tip": row["expected_tip"],
                "observed_tip": row["observed_tip"],
                "availability": (
                    "available" if row["status"] == "matched" else "unavailable"
                ),
                "pin_status": row["status"],
                "reason": row["reason"],
                "relation_to_target": relation,
                "ahead": ahead,
                "behind": behind,
                "merge_bases": bases,
                "observed_commit_count": len(observed),
                "observed_in_window_count": len(in_window),
                "complete_in_window_count": len(in_window) if complete else None,
                "sample_in_window_commit_ids": in_window[:100],
                "sample_limit": 100,
                "history_complete": complete,
            }
        )
    deliveries, selected_deliveries = [], []
    counts = {"succeeded": 0, "failed": 0, "unknown": 0}
    for event in sorted(
        config["deliveries"], key=lambda row: (_time(row["occurred_at"]), row["id"])
    ):
        selected = (
            start <= _time(event["occurred_at"]) < cutoff
            and _time(event["recorded_at"]) <= cutoff
        )
        known = selected and event["commit_id"] in graph
        reason = None if selected else "Outside the event/availability window"
        if selected and not known:
            reason = "Declared delivery revision is outside the observed graph"
        consistent = (
            (
                graph[event["commit_id"]]["committed_at"] * 1_000_000
                <= _epoch_microseconds(_time(event["occurred_at"]))
            )
            if known
            else None
        )
        if consistent is False:
            reason = "Declared delivery predates Git commit timestamp; chronology is unverified, possibly clock skew"
        deliveries.append(
            {
                **event,
                "selected": selected,
                "git_revision_observed": known,
                "git_timestamp_consistent": consistent,
                "limitation": reason,
            }
        )
        if selected:
            counts[event["status"]] += 1
            selected_deliveries.append(event)
    by_environment = {}
    environments = {
        row["environment"] for row in config["tasks"] + config["deliveries"]
    }
    for environment in sorted(environments):
        by_environment[environment] = {
            status: sum(
                event["status"] == status
                for event in selected_deliveries
                if event["environment"] == environment
            )
            for status in ("succeeded", "failed", "unknown")
        }
    tasks = []
    for task in config["tasks"]:
        reason = None
        first = None
        status = "unknown"
        if _time(task["recorded_at"]) > cutoff:
            reason = "Task linkage was not recorded at the selected cutoff"
        elif any(commit not in graph for commit in task["commit_ids"]):
            reason = "A declared task commit is outside the captured graph"
        else:
            candidates, uncertain_events = [], []
            relevant = [
                event
                for event in selected_deliveries
                if event["environment"] == task["environment"]
            ]
            for event in relevant:
                if event["status"] != "succeeded":
                    continue
                reachable, closed = _closure(event["commit_id"], graph)
                closed = (
                    closed
                    and capture["shallow"] is False
                    and capture["graph_command_complete"]
                )
                contained = set(task["commit_ids"]) <= reachable
                timestamp_ok = event["commit_id"] in graph and graph[
                    event["commit_id"]
                ]["committed_at"] * 1_000_000 <= _epoch_microseconds(
                    _time(event["occurred_at"])
                )
                if contained and timestamp_ok:
                    candidates.append(event)
                elif not closed or (contained and not timestamp_ok):
                    uncertain_events.append(event)
            if candidates:
                first = min(
                    candidates,
                    key=lambda event: (_time(event["occurred_at"]), event["id"]),
                )
                if any(
                    _time(event["occurred_at"]) <= _time(first["occurred_at"])
                    for event in uncertain_events
                ):
                    first = None
                    reason = "Earlier selected delivery ancestry/chronology is unknown; first qualifying event cannot be determined"
                else:
                    status = "declared_delivery_observed"
            elif uncertain_events:
                reason = "Incomplete delivery ancestry/chronology cannot prove absence of task changes"
            elif not relevant and not config["delivery_inventory_complete"]:
                reason = "No supplied delivery evidence for task environment; missing inventory is not zero delivery"
            else:
                status = "not_observed_in_selected_deliveries"
                reason = "No selected declared successful delivery contains every mapped commit; not a claim of never delivered"
        delay = None
        if first is not None:
            if task["started_at"] is None:
                reason = "Declared task start is unavailable; no lead duration inferred"
            elif _time(first["occurred_at"]) < _time(task["started_at"]):
                status, reason = (
                    "unknown",
                    "Selected delivery predates the declared task start",
                )
            else:
                delay = (
                    _time(first["occurred_at"]) - _time(task["started_at"])
                ).total_seconds()
        tasks.append(
            {
                **task,
                "status": status,
                "first_selected_delivery_id": first["id"] if first else None,
                "task_to_selected_delivery_seconds": delay,
                "declared_cycle_seconds": (
                    (
                        _time(task["completed_at"]) - _time(task["started_at"])
                    ).total_seconds()
                    if task["started_at"]
                    and task["completed_at"]
                    and _time(task["recorded_at"]) <= cutoff
                    else None
                ),
                "reason": reason,
            }
        )
    graph_status = (
        "available"
        if branches
        and all(row["history_complete"] for row in branches)
        and not capture["limitations"]
        else "partial" if graph else "unavailable"
    )
    report = {
        "version": "1.0.0",
        "method": "local-pinned-branch-delivery-1",
        "configuration_digest": digest_json(config),
        "capture_digest": digest_json(capture),
        "window_start": config["window_start"],
        "cutoff": config["cutoff"],
        "historical_ref_state": "not_reconstructed",
        "graph_status": graph_status,
        "branches": branches,
        "tasks": tasks,
        "deliveries": deliveries,
        "delivery_counts": counts,
        "delivery_counts_by_environment": by_environment,
        "delivery_origin": "caller_declarations_not_execution_receipts",
        "delivery_inventory_complete": config["delivery_inventory_complete"],
        "policy_acceptance": "not_assessed",
        "limitations": [
            *capture["limitations"],
            "Ref pins are observed during capture, not reconstructed historical branch states.",
            "The half-open commit window uses Git committer timestamps, which may be skewed or rewritten.",
            "Task linkage/times and delivery outcomes are caller declarations, not authenticated provider or runtime receipts.",
            "Task-to-delivery duration selects the first supplied successful event in this window, not a proven first deployment ever.",
            "Counts describe selected claims; incomplete inventories are not zero global activity or a DORA/causal performance metric.",
            "Rebases, cherry-picks and squashes keep distinct commit identities; no patch-equivalence or business-task linkage is inferred.",
        ],
    }
    _validate("report", report)
    if len(canonical_json_bytes(report)) > MAX_REPORT_BYTES:
        raise ContractError("Branch/delivery report exceeds 16 MiB")
    return report


def validate_report(
    report: dict[str, Any], *, config: dict[str, Any], capture: dict[str, Any]
) -> None:
    """Validate deterministic consumer results against supplied original inputs."""
    _validate("report", report)
    if report != analyze_branch_delivery(config, capture):
        raise ContractError(
            "Stored branch/delivery result contradicts its selected original inputs"
        )
