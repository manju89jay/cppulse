"""Shared history facts, not expertise, source authentication or symbol mining.

The adapter reuses one checked HistoryScan and its existing identity/trailer
adapter. Eligibility and distinct-commit sets are explicit; no weights or risk
scoring are introduced. Unseen-parent deltas never become ownership/co-change.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from fnmatch import fnmatchcase
from itertools import combinations
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from cppulse.errors import ContractError
from cppulse.identities import digest_json

REASONS = (
    "future",
    "outside_window",
    "explicit_exclusion",
    "unknown_delta",
    "merge",
    "bulk",
    "generated_only",
    "no_selected_files",
    "bot_only",
)
LIMITATIONS = (
    "Authorship is a knowledge proxy, not proof of expertise.",
    "Hashes and validated declarations do not authenticate the producer.",
    "File lineage follows selected first-parent history; unobserved ancestry and cross-branch identity are not proven.",
    "Component history projects the current declared component map, not historical architecture.",
)


def _fail(message: str, path: str = "") -> None:
    raise ContractError(message, path=path, code="INVALID_SHARED_HISTORY")


def _unique(rows: list[dict], label: str) -> dict[str, dict]:
    by_id = {row["id"]: row for row in rows}
    if len(by_id) != len(rows):
        _fail("Duplicate " + label + " identity", "/" + label)
    return by_id


def _path(value: str) -> None:
    path = PurePosixPath(value)
    if (
        not value
        or "\\" in value
        or "\x00" in value
        or path.is_absolute()
        or PureWindowsPath(value).drive
        or ".." in path.parts
        or path.as_posix() != value
        or value == "."
    ):
        _fail("History paths must be canonical relative paths")


def _identity(value: str) -> str:
    result = value.strip().casefold()
    if not result or result != value or any(c in value for c in "\r\n\x00"):
        _fail("Contributor identities/aliases must be normalized nonblank strings")
    return result


def _reason(commit: dict, files: dict, contributors: dict, policy: dict, cutoff: int):
    if commit["committed_at"] > cutoff:
        return "future"
    if commit["committed_at"] < policy["window_start"]:
        return "outside_window"
    if commit["id"] in policy["exclude_commit_ids"]:
        return "explicit_exclusion"
    if commit["delta_availability"] != "available":
        return "unknown_delta"
    if commit["is_merge"] and not policy["include_merges"]:
        return "merge"
    if commit["total_files"] > policy["max_files_per_commit"]:
        return "bulk"
    selected = [f for f in commit["file_ids"] if not files[f]["excluded"]]
    if not selected:
        return "generated_only" if commit["file_ids"] else "no_selected_files"
    if not commit["participant_ids"]:
        return "bot_only"
    return None


def _touches(document: dict) -> dict[str, dict[str, set[str]]]:
    accepted = [row for row in document["commits"] if row["excluded_reason"] is None]
    files = {row["id"]: set() for row in document["files"]}
    excluded = {row["id"] for row in document["files"] if row["excluded"]}
    for commit in accepted:
        for identity in set(commit["file_ids"]) - excluded:
            files[identity].add(commit["id"])
    components = {
        row["id"]: (
            set().union(*(files[f] for f in row["file_ids"]))
            if row["file_ids"]
            else set()
        )
        for row in document["components"]
    }
    symbols = {row["id"]: set(row["commit_ids"]) for row in document["symbols"]}
    return {"file": files, "component": components, "symbol": symbols}


def _pairs(document: dict) -> tuple[list[dict], bool]:
    minimum = document["policy"]["minimum_support"]
    rows = []
    for kind, touches in _touches(document).items():
        # Generate only observed co-touches, not every pair of unrelated files.
        per_commit = defaultdict(list)
        for identity, commits in touches.items():
            for commit in commits:
                per_commit[commit].append(identity)
        supporting = defaultdict(set)
        for commit, identities in per_commit.items():
            for pair in combinations(sorted(identities), 2):
                supporting[pair].add(commit)
        for (left, right), commits in sorted(supporting.items()):
            if len(commits) >= minimum:
                rows.append(
                    {
                        "entity_kind": kind,
                        "left_id": left,
                        "right_id": right,
                        "commit_ids": sorted(commits),
                        "support": len(commits),
                        "left_touches": len(touches[left]),
                        "right_touches": len(touches[right]),
                    }
                )
    limit = document["policy"]["max_pair_records"]
    return rows[:limit], len(rows) > limit


def semantic(document: dict[str, Any]) -> None:
    """Validate cross-references/counts after the packaged v2 structural schema."""
    contributors = _unique(document["contributors"], "contributors")
    files = _unique(document["files"], "files")
    commits = _unique(document["commits"], "commits")
    components = _unique(document["components"], "components")
    symbols = _unique(document["symbols"], "symbols")
    entity_ids = list(files) + list(components) + list(symbols)
    if len(entity_ids) != len(set(entity_ids)):
        _fail("File/component/symbol identities must be distinct")
    aliases = {}
    for identity, row in contributors.items():
        _identity(identity)
        for alias in row["aliases"]:
            _identity(alias)
            if alias in aliases or alias in contributors:
                _fail("Conflicting alias/canonical contributor identity")
            aliases[alias] = identity
    policy, scope = document["policy"], document["scope"]
    if policy["window_start"] > document["cutoff"]:
        _fail("History window begins after its cutoff")
    if len(commits) > policy["max_commits"]:
        _fail("Observed history exceeds the declared commit bound")
    boundaries = set(scope["boundary_commit_ids"])
    if not boundaries <= commits.keys():
        _fail("Unknown history boundary commit")
    paths = set()
    for identity, row in files.items():
        _path(row["current_path"])
        _path(row["anchor_path"])
        if row["current_path"] in paths:
            _fail("Duplicate current file path")
        paths.add(row["current_path"])
        if (
            identity
            != "file-"
            + digest_json(
                [document["repository_id"], row["anchor_commit_id"], row["anchor_path"]]
            )[:32]
        ):
            _fail("Persistent file ID disagrees with declared lineage anchor")
        if (
            row["anchor_commit_id"] is not None
            and row["anchor_commit_id"] not in commits
        ):
            _fail("Unknown file lineage anchor")
        if not set(row["commit_ids"]) <= commits.keys():
            _fail("Unknown file history commit")
    excluded = Counter()
    for identity, row in commits.items():
        if identity in row["parent_ids"]:
            _fail("A history commit cannot parent itself")
        if bool(len(row["parent_ids"]) > 1) != row["is_merge"]:
            _fail("Merge state disagrees with parent identities")
        unknown_parent = bool(row["parent_ids"] and row["parent_ids"][0] not in commits)
        if unknown_parent and identity not in boundaries:
            _fail("History boundary must name each missing first parent")
        if identity in boundaries and row["delta_availability"] != "unavailable":
            _fail("Unseen-parent tree listing is not a verified changed-file set")
        if not set(row["declared_contributor_ids"]) <= contributors.keys():
            _fail("Unknown declared contributor")
        expected_participants = sorted(
            c for c in row["declared_contributor_ids"] if not contributors[c]["bot"]
        )
        if row["participant_ids"] != expected_participants:
            _fail("Participants must be unique canonical non-bot declared contributors")
        if (
            policy["pair_attribution"] == "author_only"
            and len(row["declared_contributor_ids"]) > 1
        ):
            _fail("Author-only attribution cannot declare a pair")
        if not set(row["file_ids"]) <= files.keys():
            _fail("Unknown changed-file identity")
        if row["delta_availability"] == "unavailable":
            if row["total_files"] is not None or row["file_ids"]:
                _fail(
                    "Unavailable delta must not publish changed-file counts/identities"
                )
        elif row["total_files"] is None or row["total_files"] < len(row["file_ids"]):
            _fail("All-path changed-file count is below the selected file count")
        expected = _reason(row, files, contributors, policy, document["cutoff"])
        if row["excluded_reason"] != expected:
            _fail("Commit exclusion disagrees with declared eligibility policy")
        if expected is not None:
            excluded[expected] += 1
    # A bounded ancestry DFS catches declared cycles without recursive depth.
    visited = set()
    for identity in commits:
        stack, active = [(identity, False)], set()
        while stack:
            node, leaving = stack.pop()
            if leaving:
                active.discard(node)
                visited.add(node)
            elif node in active:
                _fail("Cyclic commit ancestry")
            elif node not in visited:
                active.add(node)
                stack.append((node, True))
                stack.extend(
                    (p, False) for p in commits[node]["parent_ids"] if p in commits
                )
    accepted = len(commits) - sum(excluded.values())
    if (
        scope["observed_commits"] != len(commits)
        or scope["accepted_commits"] != accepted
    ):
        _fail("History counts disagree with distinct observed/accepted commits")
    if scope["excluded_commits"] != {k: excluded[k] for k in REASONS}:
        _fail("Exclusion census disagrees with explicit commit records")
    expected_availability = (
        "unavailable"
        if not accepted
        else ("partial" if boundaries or scope["limitations"] else "available")
    )
    if scope["availability"] != expected_availability:
        _fail("History availability contradicts observed scope/boundaries")
    for row in files.values():
        expected = sorted(
            c["id"] for c in commits.values() if row["id"] in c["file_ids"]
        )
        if row["commit_ids"] != expected:
            _fail("File history must reference exactly its known changed-file commits")
        if row["identity_scope"] == "complete_first_parent_lineage" and (
            boundaries or scope["limitations"] or row["anchor_commit_id"] is None
        ):
            _fail("Incomplete history cannot promise complete persistent lineage")
    rename_keys = set()
    current_paths = {identity: row["current_path"] for identity, row in files.items()}
    order = {identity: i for i, identity in enumerate(commits)}
    for row in document["renames"]:
        if row["file_id"] not in files or row["commit_id"] not in commits:
            _fail("Unknown rename file/commit identity")
        _path(row["from_path"])
        _path(row["to_path"])
        key = (row["file_id"], row["commit_id"])
        if key in rename_keys or row["from_path"] == row["to_path"]:
            _fail("Duplicate/identity rename event")
        rename_keys.add(key)
        commit = commits[row["commit_id"]]
        if (
            commit["delta_availability"] != "available"
            or row["file_id"] not in commit["file_ids"]
        ):
            _fail("Rename requires an observed changed-file delta")
    for row in sorted(document["renames"], key=lambda r: order[r["commit_id"]]):
        if current_paths[row["file_id"]] != row["to_path"]:
            _fail("Rename lineage is disconnected or ambiguous")
        current_paths[row["file_id"]] = row["from_path"]
    for row in files.values():
        if (
            row["identity_scope"] == "complete_first_parent_lineage"
            and current_paths[row["id"]] != row["anchor_path"]
        ):
            _fail("Persistent anchor path disagrees with rename lineage")
    membership = [f for c in components.values() for f in c["file_ids"]]
    if sorted(membership) != sorted(files):
        _fail("Current components must partition every declared file exactly once")
    if len({c["name"] for c in components.values()}) != len(components):
        _fail("Duplicate component name")
    touch = _touches(document)
    for row in components.values():
        if (
            row["id"]
            != "component-" + digest_json([document["repository_id"], row["name"]])[:32]
        ):
            _fail("Component ID disagrees with its repository/name anchor")
        if row["commit_ids"] != sorted(touch["component"][row["id"]]):
            _fail("Component support must be a distinct union of member file commits")
        state = scope["availability"] if row["commit_ids"] else "unavailable"
        if row["availability"] != state:
            _fail("Component availability contradicts its usable member history")
    symbol_scope = document["symbol_history"]
    if document["origin"] == "git_scan":
        if document["producer"]["name"] != "cppulse-history-scan":
            _fail("Git scan provenance has the wrong declared producer")
        if (
            symbols
            or symbol_scope["origin"] != "unavailable"
            or symbol_scope["availability"] != "unavailable"
        ):
            _fail("File Git scan does not produce symbol history")
    elif document["producer"]["name"] != "consumer-authored":
        _fail("Authored symbol fixtures must retain consumer-authored provenance")
    if symbol_scope["availability"] == "unavailable" and any(
        s["commit_ids"] for s in symbols.values()
    ):
        _fail("Unavailable symbol history cannot claim supporting commits")
    for row in symbols.values():
        if (
            row["id"]
            != "symbol-"
            + digest_json(
                [document["repository_id"], row["file_id"], row["anchor_key"]]
            )[:32]
        ):
            _fail("Symbol ID disagrees with its declared persistent anchor")
        if row["file_id"] not in files:
            _fail("Unknown symbol file identity")
        if row["current_key"] in row["previous_keys"]:
            _fail("Symbol key lineage repeats the current identity")
        if row["lineage"] in {"ambiguous", "unavailable"} and (
            row["availability"] != "unavailable" or row["commit_ids"]
        ):
            _fail("Ambiguous/missing symbol lineage must remain unavailable")
        if not set(row["commit_ids"]) <= touch["file"][row["file_id"]]:
            _fail("Symbol history must reference accepted changes of its declared file")
        if row["availability"] != "unavailable" and (
            symbol_scope["origin"] != "consumer_authored" or not row["limitations"]
        ):
            _fail(
                "Declared symbol history needs explicit authored provenance/limitations"
            )
    if not symbol_scope["limitations"]:
        _fail("Symbol-history availability requires an explicit scope limitation")
    if symbol_scope["origin"] == "unavailable" and symbols:
        _fail("Missing symbol producer cannot declare symbol rows")
    for row in symbols.values():
        expected = (
            "unavailable"
            if not row["commit_ids"] or row["lineage"] != "declared"
            else scope["availability"]
        )
        if row["availability"] != expected:
            _fail("Symbol availability exceeds its declared lineage/support/root scope")
        if (
            row["current_key"] != row["anchor_key"]
            and row["anchor_key"] not in row["previous_keys"]
        ):
            _fail("Changed symbol key must retain its declared persistent anchor")
    usable = [row for row in symbols.values() if row["availability"] != "unavailable"]
    symbol_availability = (
        "unavailable"
        if not usable
        else (
            "partial"
            if len(usable) != len(symbols)
            or any(row["availability"] == "partial" for row in usable)
            else "available"
        )
    )
    if symbol_scope["availability"] != symbol_availability:
        _fail("Aggregate symbol availability contradicts declared symbol coverage")
    expected_pairs, truncated = _pairs(document)
    if (
        document["coupling"]["pairs"] != expected_pairs
        or document["coupling"]["truncated"] != truncated
    ):
        _fail(
            "Co-change support/denominators/pairs differ from distinct accepted commit sets"
        )
    if not set(LIMITATIONS) <= set(document["limitations"]):
        _fail("Required history/proxy/authentication limitations are missing")


def validate_history_binding(
    document: dict, *, source_digest: str, context_id: str
) -> None:
    """Check a declaration against a caller's expected source/context, not trust."""
    from .validation import validate

    validate("shared_history", document)
    if (
        document["source_digest"] != source_digest
        or document["context_id"] != context_id
    ):
        _fail(
            "History source/context differs from the selected input", "/source_digest"
        )


def from_history_scan(
    scan: Any,
    config: Any,
    *,
    source_digest: str,
    context_id: str,
    repository_id: str,
    cutoff: datetime,
    head: str | None = None,
) -> dict:
    """Project existing Git facts once; no repository reads or new scans.

    File IDs anchor to observed introduction commit/path, surviving later
    first-parent renames. With missing ancestry, stability is only within the
    selected observed lineage; unknown-parent tree listings are discarded.
    """
    from cppulse.git_miner.behavior import (
        BehaviorConfig,
        records_from_scan,
        has_known_change_delta,
    )
    from .validation import validate

    offset = cutoff.utcoffset()
    if cutoff.tzinfo is None or offset is None or offset.total_seconds() != 0:
        _fail("History cutoff must be aware UTC")
    validated_config = BehaviorConfig.from_document(config.document)
    cfg = validated_config.document
    records = list(records_from_scan(scan, validated_config))
    truncated = len(records) > cfg["max_commits"]
    records = records[: cfg["max_commits"]]
    observed = {r.commit_id for r in records}
    objects = {c.hexsha: c for c in scan.commits[: cfg["max_commits"]]}
    parents = {key: [p.hexsha for p in value.parents] for key, value in objects.items()}
    boundaries = {
        key for key, value in parents.items() if value and value[0] not in observed
    }
    boundaries.update(r.commit_id for r in records if not has_known_change_delta(r))
    notes = list(scan.limitations)
    notes.extend(note for record in records for note in record.limitations)
    if boundaries:
        notes.append(
            "Missing first-parent deltas remain unavailable; boundary tree listings are not changed-file evidence."
        )
    if truncated:
        notes.append("History truncated at the configured observed-commit bound.")

    def resolve(value):
        value = value.strip().casefold()
        while value in cfg["aliases"]:
            value = cfg["aliases"][value]
        return value

    identities = {resolve(a) for r in records for a in r.authors}
    identities.update(resolve(a) for a in cfg["aliases"])
    identities.update(cfg["bot_ids"])
    identities.update(cfg["former_contributor_ids"])
    contributors = [
        {
            "id": identity,
            "aliases": sorted(a for a in cfg["aliases"] if resolve(a) == identity),
            "bot": identity in cfg["bot_ids"],
            "former": identity in cfg["former_contributor_ids"],
        }
        for identity in sorted(identities)
    ]
    paths = sorted(scan.files)
    if len(paths) > 100000:
        _fail("Selected history file inventory exceeds its existing behavior bound")
    walking = {name: name for name in paths}
    anchors = {name: [None, name] for name in paths}
    rename_paths = []
    for change in scan.changes:
        key = change.commit.hexsha
        if key not in observed or key in boundaries:
            continue
        name = change.file
        if name not in walking:
            _fail("History change refers to a noncurrent file")
        if change.parent_file is None:
            anchors[name] = [key, walking[name]]
        elif change.parent_file != walking[name]:
            rename_paths.append((name, key, change.parent_file, walking[name]))
            walking[name] = change.parent_file
    for name in paths:
        if anchors[name][0] is None:
            anchors[name][1] = walking[name]
    ids = {
        name: "file-" + digest_json([repository_id, *anchors[name]])[:32]
        for name in paths
    }
    files = [
        {
            "id": ids[name],
            "current_path": name,
            "anchor_commit_id": anchors[name][0],
            "anchor_path": anchors[name][1],
            "identity_scope": (
                "complete_first_parent_lineage"
                if not notes and anchors[name][0]
                else "observed_lineage_only"
            ),
            "excluded": any(fnmatchcase(name, p) for p in cfg["exclude_paths"]),
            "commit_ids": [],
        }
        for name in paths
    ]
    policy = {
        "window_start": int(cutoff.timestamp()) - cfg["window_days"] * 86400,
        **{
            k: cfg[k]
            for k in (
                "include_merges",
                "pair_attribution",
                "max_files_per_commit",
                "minimum_support",
                "max_pair_records",
                "max_commits",
                "exclude_commit_ids",
            )
        },
    }
    by_file, by_contributor = {r["id"]: r for r in files}, {
        r["id"]: r for r in contributors
    }
    commits = []
    for record in records:
        declared = sorted({resolve(a) for a in record.authors})
        row = {
            "id": record.commit_id,
            "committed_at": record.committed_at,
            "parent_ids": parents[record.commit_id],
            "declared_contributor_ids": declared,
            "participant_ids": [a for a in declared if not by_contributor[a]["bot"]],
            "file_ids": (
                []
                if record.commit_id in boundaries
                else sorted(ids[f] for f in record.files)
            ),
            "delta_availability": (
                "unavailable" if record.commit_id in boundaries else "available"
            ),
            "total_files": (
                None if record.commit_id in boundaries else record.total_files
            ),
            "is_merge": record.is_merge,
            "excluded_reason": None,
        }
        row["excluded_reason"] = _reason(
            row, by_file, by_contributor, policy, int(cutoff.timestamp())
        )
        commits.append(row)
    excluded = Counter(
        c["excluded_reason"] for c in commits if c["excluded_reason"] is not None
    )
    accepted = len(commits) - sum(excluded.values())
    availability = (
        "unavailable" if not accepted else ("partial" if notes else "available")
    )
    for row in files:
        row["commit_ids"] = sorted(
            c["id"] for c in commits if row["id"] in c["file_ids"]
        )
    component_members = defaultdict(list)
    for name in paths:
        matched = [
            c
            for c, patterns in cfg["components"].items()
            if any(fnmatchcase(name, p) for p in patterns)
        ]
        if len(matched) > 1:
            _fail("Ambiguous current architectural component")
        component_members[matched[0] if matched else "__unassigned__"].append(ids[name])
    document = {
        "version": "2.0.0",
        "id": "shared-history-"
        + digest_json([repository_id, source_digest, context_id]),
        "source_digest": source_digest,
        "context_id": context_id,
        "repository_id": repository_id,
        "head": head,
        "cutoff": int(cutoff.timestamp()),
        "origin": "git_scan",
        "producer": {
            "name": "cppulse-history-scan",
            "version": "1.0.0",
            "authenticated": False,
        },
        "policy": policy,
        "scope": {
            "availability": availability,
            "basis": "first_parent_current_file_projection",
            "boundary_commit_ids": sorted(boundaries),
            "observed_commits": len(commits),
            "accepted_commits": accepted,
            "excluded_commits": {k: excluded[k] for k in REASONS},
            "limitations": list(dict.fromkeys(notes)),
        },
        "contributors": contributors,
        "files": files,
        "commits": commits,
        "renames": [
            {"file_id": ids[name], "commit_id": key, "from_path": old, "to_path": new}
            for name, key, old, new in rename_paths
        ],
        "components": [
            {
                "id": "component-" + digest_json([repository_id, name])[:32],
                "name": name,
                "file_ids": sorted(members),
                "commit_ids": [],
                "availability": "unavailable",
                "basis": "current_configuration_projection",
            }
            for name, members in sorted(component_members.items())
        ],
        "symbol_history": {
            "availability": "unavailable",
            "origin": "unavailable",
            "limitations": [
                "No symbol-history producer is implemented by this file-history projection."
            ],
        },
        "symbols": [],
        "coupling": {
            "method": "historical_cochange",
            "count_unit": "distinct_accepted_commit",
            "pairs": [],
            "truncated": False,
        },
        "limitations": list(LIMITATIONS),
    }
    touches = _touches(document)
    for component in document["components"]:
        component["commit_ids"] = sorted(touches["component"][component["id"]])
        component["availability"] = (
            availability if component["commit_ids"] else "unavailable"
        )
    document["coupling"]["pairs"], document["coupling"]["truncated"] = _pairs(document)
    validate("shared_history", document)
    return document
