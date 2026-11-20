# Finite historical ownership and co-change facts

`cppulse-git-behavior-1` is an optional standalone producer. It preserves the
existing `git_metrics.json` contract and writes a separate `git_behavior.json`
only after validating the requested behavior configuration and result. It does
not alter health scores, risk ranks, policy decisions or legacy contributor
metrics. The schemas are packaged under `schemas/behavior_v1/`; this separate
1.0.0 channel does not silently add a primary run-manifest v2 fact kind.

From a source checkout:

```sh
python -m cppulse.git_miner.main --repo /path/to/repository \
  --output /path/to/results --szz-max-fix-commits 1 \
  --behavior-config python/cppulse/data/git-behavior-example.json \
  --behavior-cutoff 2026-11-16T23:00:00Z
```

The example configuration is packaged as `cppulse/data/git-behavior-example.json`.
Copy and adapt it for the project. An aware UTC cutoff and configuration must be
selected together; the optional document has no implicit clock. The ordinary
miner invocation remains unchanged. Invalid optional requests fail before
rewriting existing outputs. Existing files in an output directory are historical
artifacts, not evidence that a later failed invocation produced them.

## Inputs and bounded processing

The pure `analyze_behavior` API accepts shared `CommitRecord` values and a finite
current file inventory. Each record retains commit ID, committed UTC timestamp,
Git author plus configured coauthors, current rename-projected file identities,
total changed paths before C++ selection, and merge status. The selected stream
is read at most `max_commits + 1` times (one truncation sentinel). It is sorted by
timestamp and commit ID within that bounded subset. If truncated, caller stream
traversal order selects the retained subset; the result is partial.

Current scope is limited to 100,000 canonical relative file paths. Duplicate
commit IDs and paths, ambiguous architectural components, nonfinite parameters
and alias cycles fail explicitly. Configuration also bounds touched paths per
commit and retained historical pairs. Pair omission counts and truncation remain
visible. The result identifies method, HEAD, cutoff, canonical configuration and
its digest, bounded input digest, observed/accepted/excluded counts and reasons.
These identities are not authentication or proof of unchanged current sources.

The optional miner adapter consumes the same checked disk-backed history scan
as file metrics, silo summaries and SZZ. `HistoryScan.commit_file_counts` retains
all changed paths for bulk filtering, including non-C++ paths. The shared
producer streams raw records, verifies incremental checkpoints and reprojects
current rename scope. See [checked history](git-history.md) for append, rewrite,
shallow, attribute/root identity and recovery semantics. First-parent/merge
limitations propagate. Representative large-tier resource budgets, symbol
history, complete cross-branch lineage and the whole M2/P5/P6 gates remain open.

## Explicit attribution and eligibility

Contributor identifiers are trimmed/case-folded; configured aliases resolve
transitively, with cycles/conflicts rejected. Identity remains a declared email
or fallback author name. Aliases do not authenticate people. Bot identifiers are
resolved through the same aliases and removed before attribution denominators.
Former contributors remain in historical totals and are marked; the separate
configured offboarding set controls a hypothetical removal scenario.

`author_only` uses the Git author. `coauthor_trailers` additionally recognizes
`Co-authored-by: Name <identifier>` in a final blank-separated block consisting
of single-line `key: value` trailers. Body examples followed by prose are not
attribution. This finite dialect does not claim every Git trailer syntax or
multiline continuation. Messages exceeding 65,536 characters yield no additional
coauthor attribution and an explicit partial limitation; at most 63 additional
declared identities are retained. Distinct aliased non-bot contributors split
one contribution equally, rather than each receiving a full duplicate credit.

Commit timestamps after the cutoff, before the configured inclusive window,
explicit exclusions, disallowed merges, and commits above the total touched-file
bulk threshold do not enter any denominator. Generated/excluded paths use
Python `fnmatch.fnmatchcase` over the full canonical POSIX path: `*` may match a
slash. These are not the policy engine's component-aware glob semantics.

A commit with no selected path or no remaining non-bot author contributes no
ownership or coupling. Every exclusion reason and accepted count is inspectable.
The current file inventory is discovered at current HEAD/worktree, not rebuilt
as of an older cutoff. This output is not a point-in-time predictive evaluation.

## Calculations

For an accepted commit aged `d` fractional days at the explicit cutoff, its
recency mass is `2 ** (-d / half_life_days)`. It contributes that mass once per
touched selected file, split equally across distinct eligible declared authors.
The raw weighted denominator and author masses are retained. Numeric underflow
is disclosed and yields unavailable ownership rather than a perfect score.

For each file, author share is author mass divided by total mass. Fragmentation
is `1 - sum(share ** 2)`; effective author count is `1 / sum(share ** 2)`. Team
fragmentation uses summed configured team masses. Contributors without a team
remain separate `unassigned:<identifier>` cells; they are not combined into an
invented team. Offboarding returns removed and remaining shares and remaining
declared IDs. With no positive observed mass, shares/fragmentation/offboarding
ratios are unavailable/null. No expertise, staffing sufficiency or actual
availability is inferred.

Historical coupling counts distinct accepted commits touching each unordered
file pair. Minimum support is required. For support `s`, file touches `a` and
`b`, Jaccard is `s / (a + b - s)`, and directional confidences are `s/a` and
`s/b`. Raw support and denominators accompany each ratio. This is historical
co-change, separate from static include/call dependencies and causation.

A file must match at most one configured component; unmatched files use
`__unassigned__`. Component ownership sums file-touch masses (a commit touching
two files contributes two file-touch units); component coupling counts each
component only once per accepted commit. The distinct denominators are retained.
The standalone validator checks stored arithmetic, identities, support and
membership consistency. It does not independently rerun the original history.

## Acceptance boundary

Controlled Git fixtures cover author aliases, bots, configured pairs, renames,
non-C++ bulk changes and legacy output preservation. Hand calculations cover
recency decay, per-author/team shares, fragmentation, offboarding, coupling and
component denominators. Tests reject altered stored formulas and review-found
canonical-path/body-attribution defects. A frozen cppulse history is exercised
separately in the Cloud checkpoint.

Function/symbol history, cross-branch rename qualification, history append and
rewrite-safe reuse, representative resource budgets, indexed queries, installed
CLI routing beyond the explicit miner module, and dashboard/goal workflows
remain open. This producer does not close all FR-GIT requirements or M6/P6.
