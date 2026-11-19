"""Bounded historical authorship/co-change facts, never expertise or dependencies.

The pure producer consumes a finite shared record stream. The optional adapter
reuses the existing rename-projected HistoryScan; it does not qualify that older
scanner as a streaming, incremental or resource-bounded history collector.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from fnmatch import fnmatchcase
from importlib import resources
from itertools import combinations, islice
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import TYPE_CHECKING, Any

import jsonschema

from cppulse.errors import ContractError
from cppulse.identities import digest_json

if TYPE_CHECKING:
    from .history import HistoryScan

METHOD = "cppulse-git-behavior-1"
UNKNOWN_PARENT_DELTA_LIMITATION = (
    "Parent history is unavailable; this shallow boundary snapshot does not establish changed files."
)
_PAIR = re.compile(
    r"^Co-authored-by:\s*[^\r\n<>]+<([^<>\r\n]+)>\s*$", re.MULTILINE | re.IGNORECASE
)


def _schema(name: str) -> dict[str, Any]:
    return json.loads(
        resources.files("cppulse.contracts")
        .joinpath("schemas", "behavior_v1", name + ".schema.json")
        .read_text()
    )


def _validate(name: str, document: dict[str, Any]) -> None:
    try:
        json.dumps(document, allow_nan=False)
        jsonschema.Draft7Validator(
            _schema(name), format_checker=jsonschema.FormatChecker()
        ).validate(document)
    except (ValueError, TypeError, jsonschema.ValidationError) as error:
        raise ContractError(f"Invalid Git behavior {name}: {error}") from error


def _path(value: str) -> str:
    parts = PurePosixPath(value).parts
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or "\x00" in value
        or PurePosixPath(value).as_posix() != value
        or any(part in {".", ".."} for part in value.split("/"))
        or not parts
    ):
        raise ContractError("Git behavior requires canonical relative paths")
    return value


def _identifier(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > 512
        or "\x00" in value
        or "\n" in value
        or "\r" in value
    ):
        raise ContractError("Invalid declared contributor identifier")
    return value.strip().casefold()


def _resolve(identifier: str, aliases: dict[str, str]) -> str:
    value = _identifier(identifier)
    seen: set[str] = set()
    while value in aliases:
        if value in seen:
            raise ContractError("Contributor alias cycle")
        seen.add(value)
        value = aliases[value]
    return value


@dataclass(frozen=True)
class BehaviorConfig:
    """Validated explicit producer choices; callers retain their original JSON."""

    document: dict[str, Any]

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> BehaviorConfig:
        """Validate configuration and canonicalize declared contributor identities."""
        _validate("config", document)
        value = deepcopy(document)
        aliases: dict[str, str] = {}
        for key, target in value["aliases"].items():
            key, target = _identifier(key), _identifier(target)
            if key in aliases and aliases[key] != target:
                raise ContractError("Conflicting normalized contributor aliases")
            aliases[key] = target
        for key in aliases:
            _resolve(key, aliases)
        value["aliases"] = dict(sorted(aliases.items()))
        for key in ["bot_ids", "former_contributor_ids", "offboarding_ids"]:
            value[key] = sorted({_resolve(item, aliases) for item in value[key]})
        teams: dict[str, str] = {}
        for author, team in value["teams"].items():
            author = _resolve(author, aliases)
            if not team.strip() or team == "__unassigned__":
                raise ContractError(
                    "Declared team must have a nonblank unreserved name"
                )
            if author in teams and teams[author] != team:
                raise ContractError("Conflicting teams for aliased contributor")
            teams[author] = team
        value["teams"] = dict(sorted(teams.items()))
        for pattern in value["exclude_paths"]:
            _path(pattern)
        for component, patterns in value["components"].items():
            if not component.strip() or component == "__unassigned__":
                raise ContractError(
                    "Declared component must have a nonblank unreserved name"
                )
            for pattern in patterns:
                _path(pattern)
        return cls(value)


@dataclass(frozen=True)
class CommitRecord:
    """One observed commit projected onto current selected file identities.

    Authors are declared identifiers. The first is the Git author; additional
    identities count only under explicit coauthor_trailers attribution. total_files
    retains all changed paths, including paths outside selected C++ scope, for
    the bulk exclusion. It must not be replaced by the selected file count.
    A shallow boundary has an unavailable delta: files is empty and total_files
    is an internal zero sentinel only when has_known_change_delta() is false.
    Consumers must preserve that unavailable state rather than publish known0.
    """

    commit_id: str
    committed_at: int
    authors: tuple[str, ...]
    files: tuple[str, ...]
    total_files: int
    is_merge: bool
    limitations: tuple[str, ...] = ()


def has_known_change_delta(record: CommitRecord) -> bool:
    """Distinguish known changes from the explicit unknown-parent sentinel.

    This is an availability decision, not execution or contributor authentication.
    """
    return UNKNOWN_PARENT_DELTA_LIMITATION not in record.limitations


def _shallow_boundaries(
    commits: Sequence[Any], *, repository: Any = None
) -> set[str]:
    """Read only local declared Git boundaries; never ask an ODB to lazy-fetch.

    Checked cache commits intentionally carry no repository handle. Their owning
    scan retains the repository used to collect the same local Git facts.
    """
    selected: dict[Path, set[str]] = defaultdict(set)
    for commit in commits:
        repo = getattr(commit, "repo", None) or repository
        if repo is not None:
            selected[Path(repo.common_dir)].add(commit.hexsha)
    boundaries: set[str] = set()
    for common_dir, wanted in selected.items():
        try:
            with (common_dir / "shallow").open("r", encoding="ascii") as stream:
                while line := stream.readline(66):
                    identity = line.rstrip("\n")
                    if not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", identity):
                        raise ContractError("Invalid local shallow-history metadata")
                    if identity in wanted:
                        boundaries.add(identity)
        except FileNotFoundError:
            continue
        except (OSError, UnicodeError) as error:
            raise ContractError("Local shallow-history metadata is unavailable") from error
    return boundaries


def _coauthor_trailers(
    message: str, author: str, config: BehaviorConfig
) -> tuple[list[str], list[str]]:
    """Read a finite final blank-separated single-line trailer block only."""
    if len(message) > 65536:
        return [], [
            "Coauthor attribution unavailable: message exceeds 65536 characters."
        ]
    paragraphs = re.split(
        r"\n[ \t]*\n",
        message.replace("\r\n", "\n").replace("\r", "\n").rstrip(),
    )
    if len(paragraphs) < 2:
        return [], []
    lines = paragraphs[-1].splitlines()
    # Body examples followed by prose are not trailer declarations. This
    # finite profile deliberately supports single-line key:value footers.
    if not all(re.fullmatch(r"[A-Za-z0-9-]+:\s+\S.*", line) for line in lines):
        return [], []
    # Bound additional *identities*, not raw footer lines: aliases, repeated
    # authors and configured bots must not crowd out a later real contributor.
    aliases = config.document["aliases"]
    seen = {_resolve(author, aliases), *config.document["bot_ids"]}
    identities = []
    for line in lines:
        if match := _PAIR.fullmatch(line):
            identity = _resolve(match.group(1), aliases)
            if identity not in seen:
                seen.add(identity)
                identities.append(identity)
    notes = []
    if len(identities) > 63:
        notes.append(
            "Coauthor trailer attribution capped at 63 additional declared identities."
        )
    return identities[:63], notes


def records_from_scan(
    scan: HistoryScan, config: BehaviorConfig
) -> Iterable[CommitRecord]:
    """Reuse the existing current-file/rename projection without another scan.

    This bounded adapter does not remove the existing scanner's initial full
    materialization. That limitation remains explicit in the optional document.
    """
    selected = scan.commits[: config.document["max_commits"] + 1]
    owner = getattr(scan, "_cache_owner", None)
    unknown_boundaries = _shallow_boundaries(
        selected, repository=getattr(owner, "repo", None)
    )
    identities = {commit.hexsha for commit in selected}
    paths: dict[str, set[str]] = defaultdict(set)
    for change in scan.changes:
        if change.commit.hexsha in identities:
            paths[change.commit.hexsha].add(change.file)
    totals = getattr(scan, "commit_file_counts", {})
    for commit in selected:
        total_files = totals.get(commit.hexsha)
        unknown_delta = commit.hexsha in unknown_boundaries
        if total_files is None and not unknown_delta:
            raise ContractError(
                "Shared history lacks an all-path changed-file total; bulk eligibility is unknown"
            )
        authors = [commit.author.email or commit.author.name or "unknown"]
        notes = []
        if config.document["pair_attribution"] == "coauthor_trailers":
            coauthors, notes = _coauthor_trailers(commit.message, authors[0], config)
            authors.extend(coauthors)
        if unknown_delta:
            notes.append(UNKNOWN_PARENT_DELTA_LIMITATION)
            if total_files is not None:
                notes.append(
                    f"Local Git boundary snapshot listed {total_files} paths; this is not a known changed-file count."
                )
        yield CommitRecord(
            commit.hexsha,
            commit.committed_date,
            tuple(authors),
            () if unknown_delta else tuple(sorted(paths[commit.hexsha])),
            0 if unknown_delta else total_files,
            len(commit.parents) > 1,
            tuple(notes),
        )


def _record(record: CommitRecord) -> None:
    if (
        not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", record.commit_id)
        or not isinstance(record.committed_at, int)
        or isinstance(record.committed_at, bool)
    ):
        raise ContractError("Invalid Git behavior commit identity/time")
    if (
        not record.authors
        or len(record.authors) > 64
        or len(record.files) > 100000
        or len(set(record.files)) != len(record.files)
    ):
        raise ContractError("Invalid or over-bound commit authors/files")
    if (
        not isinstance(record.total_files, int)
        or isinstance(record.total_files, bool)
        or record.total_files < len(record.files)
        or not isinstance(record.is_merge, bool)
    ):
        raise ContractError("Invalid total changed-file count or merge state")
    for author in record.authors:
        _identifier(author)
    for path in record.files:
        _path(path)


def _ownership(
    label: str, counts: int, masses: dict[str, float], config: dict[str, Any]
) -> dict[str, Any]:
    total = math.fsum(masses.values())
    authors = [
        {
            "id": author,
            "weighted_changes": weight,
            "share": weight / total,
            "team": config["teams"].get(author),
            "former_contributor": author in config["former_contributor_ids"],
        }
        for author, weight in sorted(masses.items())
        if weight > 0 and total > 0
    ]
    shares = [row["share"] for row in authors]
    squared = math.fsum(share * share for share in shares)
    teams: dict[str, float] = defaultdict(float)
    for row in authors:
        # Unassigned contributors remain separate unknown-team cells, not a
        # fictional team whose apparent ownership combines unrelated people.
        key = (
            "team:" + row["team"]
            if row["team"] is not None
            else "unassigned:" + row["id"]
        )
        teams[key] += row["weighted_changes"]
    team_rows = [
        {"id": key, "weighted_changes": weight, "share": weight / total}
        for key, weight in sorted(teams.items())
    ]
    team_squared = math.fsum(row["share"] ** 2 for row in team_rows)
    removed = math.fsum(
        row["share"] for row in authors if row["id"] in config["offboarding_ids"]
    )
    return {
        "file": label,
        "availability": "available" if total > 0 else "unavailable",
        "touches": counts,
        "weighted_changes": total,
        "authors": authors,
        "fragmentation": max(0.0, 1 - squared) if total > 0 else None,
        "effective_authors": 1 / squared if squared > 0 else None,
        "teams": team_rows,
        "team_fragmentation": max(0.0, 1 - team_squared) if total > 0 else None,
        "offboarding": {
            "removed_ids": config["offboarding_ids"],
            "removed_share": min(1.0, removed) if total > 0 else None,
            "remaining_share": max(0.0, 1 - removed) if total > 0 else None,
            "remaining_author_ids": [
                row["id"]
                for row in authors
                if row["id"] not in config["offboarding_ids"]
            ],
        },
    }


def _coupling(
    pairs: Counter[tuple[str, str]], touches: Counter[str], support: int
) -> list[dict[str, Any]]:
    return [
        {
            "left": a,
            "right": b,
            "support": count,
            "left_touches": touches[a],
            "right_touches": touches[b],
            "jaccard": count / (touches[a] + touches[b] - count),
            "left_confidence": count / touches[a],
            "right_confidence": count / touches[b],
        }
        for (a, b), count in sorted(pairs.items())
        if count >= support
    ]


def analyze_behavior(
    records: Iterable[CommitRecord],
    files: Iterable[str],
    config: BehaviorConfig,
    *,
    cutoff: datetime,
    head: str | None = None,
    history_limitations: Sequence[str] = (),
) -> dict[str, Any]:
    """Compute bounded recency-weighted ownership and historical file co-change.

    Each accepted commit contributes one recency mass per selected touched file;
    distinct configured pair authors split it equally. Component ownership sums
    file-change masses; component coupling counts one touch per commit/component.
    A caller-supplied stream truncates after max_commits plus one sentinel. Its
    traversal order determines a truncated subset; calculations within that
    bounded subset use a stable timestamp/commit ordering.
    """
    if cutoff.tzinfo is None or cutoff.utcoffset() != timedelta(0):
        raise ContractError("Git behavior cutoff must be an aware UTC datetime")
    cfg = BehaviorConfig.from_document(config.document).document
    scope_list = list(islice(files, 100001))
    if len(scope_list) > 100000 or len(set(scope_list)) != len(scope_list):
        raise ContractError(
            "Current file inventory is duplicate or exceeds 100000 files"
        )
    scope = sorted(_path(path) for path in scope_list)
    if head is not None and not re.fullmatch(r"[a-f0-9]{40}|[a-f0-9]{64}", head):
        raise ContractError("Invalid declared Git HEAD identity")
    bounded = list(islice(records, cfg["max_commits"] + 1))
    truncated = len(bounded) > cfg["max_commits"]
    bounded = bounded[: cfg["max_commits"]]
    seen = set()
    for record in bounded:
        _record(record)
        if record.commit_id in seen:
            raise ContractError("Duplicate Git behavior commit record")
        seen.add(record.commit_id)
    bounded.sort(key=lambda row: (row.committed_at, row.commit_id), reverse=True)
    notes = list(history_limitations)
    if truncated:
        notes.append(
            "Shared commit stream truncated at the configured max_commits bound; traversal order selects the retained subset."
        )
    source_files = {
        path
        for path in scope
        if not any(fnmatchcase(path, p) for p in cfg["exclude_paths"])
    }
    component_by_file: dict[str, str] = {}
    for path in scope:
        matches = [
            name
            for name, patterns in cfg["components"].items()
            if any(fnmatchcase(path, p) for p in patterns)
        ]
        if len(matches) > 1:
            raise ContractError(f"Ambiguous architectural component for {path}")
        component_by_file[path] = matches[0] if matches else "__unassigned__"
    mass: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    component_mass: dict[str, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    touches: Counter[str] = Counter()
    component_touches: Counter[str] = Counter()
    pairs: Counter[tuple[str, str]] = Counter()
    component_pairs: Counter[tuple[str, str]] = Counter()
    excluded: Counter[str] = Counter()
    dropped = accepted = 0
    cutoff_seconds = cutoff.timestamp()
    start = cutoff_seconds - cfg["window_days"] * 86400
    for record in bounded:
        notes.extend(record.limitations)
        reason = None
        if record.committed_at > cutoff_seconds:
            reason = "future"
        elif record.committed_at < start:
            reason = "outside_window"
        elif record.commit_id in cfg["exclude_commit_ids"]:
            reason = "explicit_exclusion"
        elif not has_known_change_delta(record):
            # Keep the existing closed report vocabulary. There are no trusted
            # selected changes; the explicit limitation preserves why unknown.
            reason = "no_selected_files"
        elif record.is_merge and not cfg["include_merges"]:
            reason = "merge"
        elif record.total_files > cfg["max_files_per_commit"]:
            reason = "bulk"
        if reason:
            excluded[reason] += 1
            continue
        selected = sorted(set(record.files) & source_files)
        if not selected:
            excluded[
                (
                    "generated_only"
                    if set(record.files) & set(scope)
                    else "no_selected_files"
                )
            ] += 1
            continue
        declared = (
            record.authors
            if cfg["pair_attribution"] == "coauthor_trailers"
            else record.authors[:1]
        )
        authors = sorted(
            {_resolve(author, cfg["aliases"]) for author in declared}
            - set(cfg["bot_ids"])
        )
        if not authors:
            excluded["bot_only"] += 1
            continue
        weight = 2 ** (
            -(cutoff_seconds - record.committed_at) / 86400 / cfg["half_life_days"]
        )
        if weight == 0 or weight / len(authors) == 0:
            notes.append(
                "Recency weight underflowed; this commit could not contribute finite ownership mass."
            )
        accepted += 1
        components = sorted({component_by_file[path] for path in selected})
        for path in selected:
            touches[path] += 1
            for author in authors:
                share = weight / len(authors)
                mass[path][author] += share
                component_mass[component_by_file[path]][author] += share
        for component in components:
            component_touches[component] += 1
        for selected_paths, counter in [
            (selected, pairs),
            (components, component_pairs),
        ]:
            for pair in combinations(selected_paths, 2):
                if pair not in counter and len(counter) >= cfg["max_pair_records"]:
                    dropped += 1
                else:
                    counter[pair] += 1
    if dropped:
        notes.append(
            "Historical pair inventory reached max_pair_records; omitted pair updates make coupling incomplete."
        )
    rows = [_ownership(path, touches[path], mass[path], cfg) for path in scope]
    components = []
    for name in sorted(set(component_by_file.values())):
        members = [path for path in scope if component_by_file[path] == name]
        ownership = _ownership(
            name, sum(touches[path] for path in members), component_mass[name], cfg
        )
        ownership.pop("file")
        components.append({"id": name, "files": members, "ownership": ownership})
    status = "partial" if notes else "available" if accepted else "unavailable"
    result = {
        "version": "1.0.0",
        "method": METHOD,
        "relationship_kind": "historical_cochange",
        "head": head,
        "cutoff": cutoff.isoformat(),
        "configuration": cfg,
        "configuration_digest": digest_json(cfg),
        "input_digest": digest_json(
            {"records": [asdict(record) for record in bounded], "files": scope}
        ),
        "history_status": status,
        "counts": {
            "observed_commits": len(bounded),
            "accepted_commits": accepted,
            "excluded_commits": dict(sorted(excluded.items())),
            "dropped_pair_updates": dropped,
        },
        "files": rows,
        "coupling": _coupling(pairs, touches, cfg["minimum_support"]),
        "components": components,
        "component_coupling": _coupling(
            component_pairs, component_touches, cfg["minimum_support"]
        ),
        "limitations": list(
            dict.fromkeys(
                [
                    *notes,
                    "Authorship is a historical familiarity/knowledge proxy, not proof of expertise, individual performance or current availability.",
                    "Historical co-change is not a static include/call dependency or evidence that one change causes another.",
                    "Ownership mass uses one exponentially decayed file-touch per accepted commit, split equally across selected distinct declared authors.",
                    "Component ownership sums file-touch mass; component coupling deduplicates component touches within each accepted commit.",
                    "Function/symbol history, incremental rewrite-safe reuse and complete cross-branch rename lineage are not provided by this producer.",
                ]
            )
        ),
    }
    validate_behavior_report(result)
    return result


def validate_behavior_report(document: dict[str, Any]) -> None:
    """Validate the standalone behavior contract and inspectable denominators."""
    _validate("report", document)
    cfg = BehaviorConfig.from_document(document["configuration"]).document
    if document["configuration_digest"] != digest_json(cfg):
        raise ContractError("Git behavior configuration digest disagrees")
    rows = {row["file"]: row for row in document["files"]}
    if len(rows) != len(document["files"]):
        raise ContractError("Duplicate Git behavior file identity")
    for path, row in rows.items():
        _path(path)
        weights = [author["weighted_changes"] for author in row["authors"]]
        if not math.isclose(
            math.fsum(weights), row["weighted_changes"], rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ContractError("Ownership denominator disagrees with author masses")
        if row["availability"] == "available":
            if row["weighted_changes"] <= 0 or not math.isclose(
                math.fsum(a["share"] for a in row["authors"]), 1, abs_tol=1e-12
            ):
                raise ContractError(
                    "Available ownership needs observed positive mass and normalized shares"
                )
        elif row["authors"] or row["fragmentation"] is not None:
            raise ContractError(
                "Unavailable ownership cannot claim known shares or fragmentation"
            )
    counts = document["counts"]
    if (
        counts["observed_commits"] > cfg["max_commits"]
        or counts["accepted_commits"] + sum(counts["excluded_commits"].values())
        != counts["observed_commits"]
    ):
        raise ContractError(
            "Behavior commit accounting disagrees with its bounded input"
        )
    if (document["history_status"] == "unavailable" and counts["accepted_commits"]) or (
        document["history_status"] == "available" and not counts["accepted_commits"]
    ):
        raise ContractError(
            "Behavior availability contradicts observed accepted commits"
        )
    if counts["dropped_pair_updates"] and document["history_status"] != "partial":
        raise ContractError("Truncated coupling cannot claim complete history")
    for path, row in rows.items():
        if any(fnmatchcase(path, pattern) for pattern in cfg["exclude_paths"]) and (
            row["touches"] or row["weighted_changes"] or row["authors"]
        ):
            raise ContractError(
                "Excluded behavior file cannot retain accepted touches or ownership"
            )
        if row["touches"] > counts["accepted_commits"]:
            raise ContractError("File touch count exceeds accepted commit denominator")
        authors = {
            author["id"]: author["weighted_changes"] for author in row["authors"]
        }
        if len(authors) != len(row["authors"]) or not _same(
            row, _ownership(path, row["touches"], authors, cfg)
        ):
            raise ContractError(
                "Stored ownership/fragmentation/offboarding calculations disagree"
            )
    component_rows = {row["id"]: row for row in document["components"]}
    if len(component_rows) != len(document["components"]):
        raise ContractError("Duplicate architectural component identity")
    membership: dict[str, list[str]] = defaultdict(list)
    for path in rows:
        selected = [
            name
            for name, patterns in cfg["components"].items()
            if any(fnmatchcase(path, pattern) for pattern in patterns)
        ]
        if len(selected) > 1:
            raise ContractError("Ambiguous component membership")
        membership[selected[0] if selected else "__unassigned__"].append(path)
    if set(component_rows) != set(membership):
        raise ContractError("Component inventory differs from selected file membership")
    for name, members in membership.items():
        component = component_rows[name]
        if sorted(component["files"]) != sorted(members):
            raise ContractError("Component file membership differs")
        masses: dict[str, float] = defaultdict(float)
        for path in sorted(members):
            for author in rows[path]["authors"]:
                masses[author["id"]] += author["weighted_changes"]
        expected = _ownership(
            name, sum(rows[path]["touches"] for path in members), masses, cfg
        )
        expected.pop("file")
        if not _same(component["ownership"], expected):
            raise ContractError("Component ownership denominator/calculations disagree")
    for key, subjects in [("coupling", rows), ("component_coupling", component_rows)]:
        pairs_seen: set[tuple[str, str]] = set()
        component_denominators: dict[str, int] = {}
        if len(document[key]) > cfg["max_pair_records"]:
            raise ContractError("Coupling inventory exceeds its configured bound")
        for pair in document[key]:
            identity = (pair["left"], pair["right"])
            if (
                identity in pairs_seen
                or pair["left"] >= pair["right"]
                or pair["left"] not in subjects
                or pair["right"] not in subjects
            ):
                raise ContractError("Coupling needs unique ordered selected identities")
            pairs_seen.add(identity)
            support, a, b = pair["support"], pair["left_touches"], pair["right_touches"]
            if (
                support < cfg["minimum_support"]
                or support > min(a, b)
                or support < a + b - counts["accepted_commits"]
                or max(a, b) > counts["accepted_commits"]
            ):
                raise ContractError(
                    "Co-change support exceeds accepted touch denominators"
                )
            if key == "coupling" and (
                a != rows[pair["left"]]["touches"]
                or b != rows[pair["right"]]["touches"]
            ):
                raise ContractError(
                    "Co-change denominators differ from selected file touches"
                )
            if key == "component_coupling":
                for name, denominator in ((pair["left"], a), (pair["right"], b)):
                    member_touches = [
                        rows[path]["touches"] for path in subjects[name]["files"]
                    ]
                    if (
                        not max(member_touches, default=0)
                        <= denominator
                        <= min(counts["accepted_commits"], sum(member_touches))
                    ):
                        raise ContractError(
                            "Component co-change denominator contradicts member file touches"
                        )
                    if (
                        name in component_denominators
                        and component_denominators[name] != denominator
                    ):
                        raise ContractError(
                            "Component co-change denominator differs across pairs"
                        )
                    component_denominators[name] = denominator
            if not all(
                math.isclose(pair[field], value, rel_tol=1e-12, abs_tol=1e-12)
                for field, value in [
                    ("jaccard", support / (a + b - support)),
                    ("left_confidence", support / a),
                    ("right_confidence", support / b),
                ]
            ):
                raise ContractError("Stored co-change ratios disagree with raw support")


def _same(actual: Any, expected: Any) -> bool:
    """Compare stored formula leaves without a rounded display threshold."""
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and set(actual) == set(expected)
            and all(_same(actual[key], value) for key, value in expected.items())
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_same(a, b) for a, b in zip(actual, expected))
        )
    if isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return (
            isinstance(actual, (int, float))
            and not isinstance(actual, bool)
            and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
        )
    return actual == expected
