# Checked shared Git history and incremental checkpoints

`cppulse-git-raw-1` is a finite local raw-history producer used once by the miner
pipeline. File metrics, historical silo summaries, the experimental SZZ labels,
optional behavior facts and commit-range metadata share its disk-backed commit
and rename-projected change streams. Producers do not each materialize a full
Git history. File aggregation retains count/date extrema rather than a date
object for every historical file change.

The private schemas are packaged in `schemas/git_history_private/`. They are
not new primary run-manifest evidence contracts. `git_metrics.json` retains its
existing contract; `git_history.json` records the selected head, producer/key
identity, checkpoint SHA, selected-commit digest/count, reuse/extraction/recovery
counts, bounds, current-file identity and incomplete scope. Optional
`git_behavior.json` remains separate. A raw cache hit creates no command receipt,
policy assessment, native-analysis execution or current-source verification.

## Public and producer interfaces

The installed public analyze command accepts history enable/disable, cache and
behavior controls. Exact budgets can be configured in the project history block:

```json
{
  "history": {
    "enabled": true,
    "cache_dir": "/absolute/authorized/history-cache",
    "max_commits": 100000,
    "max_record_bytes": 8388608,
    "max_cache_bytes": 268435456,
    "timeout_seconds": 60,
    "szz_max_fix_commits": 500
  }
}
```

```sh
cppulse analyze --repo /path/to/project --config /path/to/config.json \
  --history-cache /absolute/authorized/history-cache --format json --output /path/to/results
```

Behavior aliases, bots, pair attribution, teams, windows and offboarding remain
an explicitly selected behavior configuration plus an aware UTC cutoff. See
[behavior facts](git-behavior.md). Raw facts do not cache these derived choices;
every invocation recalculates aggregates from the selected raw records.

The Python producer boundary is:

```python
run(repo_path, output_dir, szz_max_fix_commits=500,
    behavior_config=None, behavior_cutoff=None, history_options=None)
```

`behavior_config` accepts an explicit Path or an already validated data mapping.
The public configuration currently selects a file. `history_options` contains
only `cache_dir`, `max_commits`, `max_record_bytes`, `max_cache_bytes` and
`timeout_seconds`; the cache path can be omitted/null for an invocation-private
spool. Relative producer cache paths resolve against the selected repository.
The pure options validator performs no Git or filesystem operations.

`scan_history(repo, options=..., revision=full_commit_id)` also supports an
explicit immutable revision for graph consumers. It does not check out files or
change refs. The current worktree's finite tracked file inventory remains the
projection scope; it is not reconstructed as of a historical cutoff. Consumers
using another revision for graph analysis must not interpret it as an old source
filesystem snapshot.

## Collection and bounds

The named Cloud implementation uses Git 2.52.0, GitPython 3.1.41 and Python 3.12.
The checked producer requires Git >=2.43 for explicit attribute-source selection;
other versions/platforms have not all been qualified. POSIX process supervision
provides elapsed wall-time, capture limits and owned-group cleanup. It makes no
Git process address-space/RSS limit or aggregate process-tree memory claim.

Tracked-path inventory is supervised with a 64 MiB combined output budget,
1,000,000-entry ceiling and 64 KiB individual-path ceiling. UTF-8/path framing
failures are explicit errors. Symlink source paths retain explicit omissions.
These ceilings retain the required 100K-file workload; they are not evidence
that its performance acceptance passed.

A revision traversal is drained into a bounded disk spool. SHA lines are accepted
in batches of 256, with a `max_commits + 1` sentinel to disclose truncation.
Metadata and raw/numstat changes are parsed one bounded commit at a time rather
than retaining every patch or GitPython commit object. Ordinary append/rewrite
views still traverse ordered commit IDs; expensive raw extraction reuses checked
immutable records. This is not a constant-time append claim.

Options have explicit ranges:

| Option | Default | Accepted range |
| --- | --- | --- |
| max_commits | 100,000 | 1..1,000,000 |
| max_record_bytes | 8 MiB | 1 KiB..64 MiB |
| max_cache_bytes | 256 MiB | 1 MiB..8 GiB |
| timeout_seconds | 60 | 1..3,600 per supervised Git command |

Commit metadata, encoded raw records and captured delta output are checked
against their bounds. A skipped/unavailable delta retains a reason and cannot
be a positive reusable record. Selected-record completeness and history
truncation are separate; shallow or missing-parent history stays partial.
Legacy unavailable counters are not promoted into complete history or ranking.
When history is truncated, legacy total_commits and age fields describe the
selected observed prefix, not a claimed complete repository lifetime. The
sidecar carries the explicit count, truncation and gap identity. Observed binary
markers can be reused as raw observations; their line counters remain unavailable
and the corresponding current C++ history retains a partial limitation.

SQLite database pages and actual file size are checked against the requested
cache budget using the actual SQLite page size, including existing databases
with non-default page sizes. DELETE journaling is the qualified mode; existing
WAL/other modes require explicit migration. Temporary rollback journals and
bounded command spools add disk overhead. Cache exhaustion is an operational
failure, not permission to use an older successful view. A larger explicit
budget can resume accepted records; selecting a fresh cache also preserves old
primary reports.

## Repository and extraction identity

All inventory/raw/blame subprocesses bind selected Git metadata, worktree,
index, object directory, shallow file and namespace rather than inheriting
caller root/index overrides. Environment-injected Git configuration, lazy fetch,
terminal prompts and trace-file destinations are masked. Repository fsmonitor
and hooks are disabled; no project diff/textconv driver is run. The collection
reads local Git objects; it does not fetch, commit, check out or push.

Raw deltas use the selected commit's `.gitattributes` via `--attr-source`, not a
mutable working-tree attribute file. System/global attributes are disabled;
local `info/attributes` identities are explicit key inputs and rechecked.
Producer/projection source, raw schema, Git executable bytes/version, Python and
GitPython versions, shallow boundaries and effective extraction choices bind
the profile. Mutable producer/attribute/boundary identities are checked again
before exposing a scan. An unclosed generation's raw hits are invalidated.

Object replacements are disabled for the recorded graph. Legacy graft files
are explicitly unsupported rather than silently changing a cached graph.
This is local byte/key consistency, not producer authentication or a sandbox
against a hostile host modifying trusted executables.

## Cache, recovery and current-file projection

Complete raw records are identified by commit ID and extraction profile, with
canonical payload SHA checks on every reuse. Accepted view checkpoints bind the
ordered selected-commit inventory and every raw record digest. Raw corruption
causes recollection; inconsistent checkpoint headers are rebuilt. Unavailable
records are retried and never counted as complete warm hits.

Raw acceptance and its checkpoint marker are committed transactionally with
FULL synchronization. Revision selection, pending raw work and accepted records
remain separate states. A reader cannot interpret a pending record as accepted.
Recovery tests kill actual processes after accepted work, inside a raw-record
transaction and inside final checkpoint publication. Recovered metrics agree
with independent clean extraction on the controlled histories.

A same-head warm request verifies accepted bytes without a new revision walk.
Appends extract missing records and reuse prior immutable facts. Non-descendant
rewrites build a new selected view; unreachable old branch changes do not enter
it. Shallow/deepening changes and extraction-profile changes invalidate the
appropriate generation. Raising a traversal bound expands the selected view;
alias/window/cutoff changes recompute behavior without changing raw identities.

Current tracked regular C++ files are rediscovered for every invocation. The
rename projection replays accepted raw changes once, terminates old lineages
at new-file boundaries, handles rename destinations before alias updates, and
is shared by all producers. Changing a current filename or deleting a worktree
file therefore does not reuse an old current-file projection. Merge histories
retain their explicit first-parent/cross-branch limitation.

## Output and acceptance boundary

A raw scan failure returns an operational error before producer output; it does
not trigger an unbounded metadata fallback. Existing optional positive sidecars
that are incompatible with a disabled/unavailable new request cause refusal
before writes. Prior artifacts remain byte-identical; choose a fresh output
rather than treating those historical files as current. Public disabled/missing
history branches enforce the same boundary.

The local cache is disposable derived state, not the immutable report store or
authorization system. Primary captured artifacts retain their own source/run
pins. Flat miner files are not a multi-reader atomic snapshot interface.

The Cloud checkpoint covers controlled cold/warm/append/rewrite/rename/shallow,
corruption, bounds, actual process interruption and real pinned-input comparisons.
It does not close all M2/P5/P6 acceptance. Large 1K/10K/100K workloads and growing
histories, repeated release budgets, abrupt collector death while Git is still
in flight, full process-tree resource enforcement, every Git/platform/version,
symbol history and cross-branch merge lineage remain open. No timing or source
presence is substituted for these gates.
