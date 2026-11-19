# Bounded local branch and delivery facts

The private `cppulse.branch_delivery` API implements the local Git/data-contract
portion of M8-03. It does not complete P10, authenticate workflow claims, connect
to a tracker/deployment provider, or establish DORA metrics. No public CLI or
provider integration is qualified by this module.

`validate_config(config)` runs before repository access. Select explicit local
`refs/heads/` or existing `refs/remotes/` refs and immutable full object IDs;
select one target, an aware `[window_start, cutoff)` interval, and resource limits.
Task mappings and delivery observations are explicit caller data with separate
environments and recorded-at availability. Empty/missing evidence remains empty
or unknown. No branch name, commit message, or issue identifier creates linkage.

`collect_branch_graph(repository, config)` records bounded parent-only Git facts,
ref checks before and after capture, raw output hashes, command receipts, and the
Git executable hashes. It never checks out, fetches, writes refs, runs hooks, or
contacts a provider. This producer supports the POSIX Git 2.52.x profile; tests
exercise Git 2.52.0. Other versions return unavailable. Partial clones and ambient
Git repository overrides are denied. Existing local tracking refs do not imply
fresh remote state. SHA-1 and SHA-256 repositories are supported.

Budgets are explicit: at most 100,000 commits plus one truncation sentinel,
8 MiB output per command, 30 seconds per command, 120 seconds overall, 512 KiB
configuration, 32 MiB capture, and 16 MiB report. Each actual invocation uses the
shared bounded-process runner. Cancellation, shallow ancestry, missing objects,
changed refs/tools, output exhaustion, and failures are disclosed; incomplete
ancestry does not become exact zero ahead/behind or a negative delivery claim.
The producer does not modify or reuse the full-history delta cache.

`analyze_branch_delivery(config, capture)` validates the capture, then computes
all-parent reachability, best common ancestors, exact ahead/behind where closed,
and separately bounded observed commit counts. Ref tips describe the captured
selection; applying a committer timestamp cutoff does not reconstruct historical
ref positions. Window counts use committer times and disclose that limitation.
Merge inclusion follows ancestry, including merge parents. Cherry-picks and
rebases retain distinct commit identities; patch equivalence is not inferred.

Delivery rows remain caller assertions. Counts are separated by environment.
A task's selected successful delivery must have matching environment, contain
all explicitly mapped commit identities, have an available observation by the
cutoff, and have consistent times. Earlier unknown candidate ancestry prevents
claiming that a later known delivery was first. Missing start time gives null
elapsed time. Cycle time uses only declared task start/completion; the separate
task-to-selected-delivery interval is not a general deployment lead-time metric.
Observed failure counts do not establish a global failure rate. Unverified
claims never become policy acceptance or trusted deployment outcomes.

`validate_report(report, config=config, capture=capture)` binds the report to the
expected original inputs and replays the pure consumer. This protects accidental
or adversarial projection changes relative to those inputs; no signature or
independent authenticity is claimed. Persist all three objects together when a
caller needs offline replay. The private schemas live in
`python/cppulse/contracts/schemas/branch_delivery_private/`.

Verification uses real authored Git graphs: diverging branches, merge ancestry,
unmerged work, shallow clones, cherry-picks, SHA-256, hostile literal paths,
missing/moving pins, truncation, cancellation, unknown tools, and malformed or
altered captures. Authored delivery events test linkage semantics; they are not
actual provider deliveries. Provider access/history contracts, actual configured
workflow integration, user interpretation, and broader production qualification
remain open.

## Local command adapter

`python -m cppulse.branch_delivery_cli --repo ROOT --config FILE --output NEW_DIR`
validates a strict JSON configuration before Git access. The input must be a
regular file of at most512 KiB; duplicate keys, nonfinite values, symlinks and
FIFOs are rejected. The explicit output parent must exist. The new directory
must be outside the selected source and Git metadata, including linked-worktree
metadata, with no symlink ancestor. Existing output is never replaced or cleaned.

The adapter retains original configuration bytes, normalized configuration,
capture, report, and an outcome containing artifact hashes. Failed/interrupted
execution retains completed files and an error diagnostic when output allocation
succeeded; earlier validation/allocation errors go to stderr. Interrupted writes
can leave an incomplete artifact without a successful outcome. Reuse a new output
directory after failure. Directory durability across host/power failure and
concurrent hostile filesystem mutation are not qualified by this local adapter.

Exit0 means the selected local graph is available; exit3 means partial or
unavailable graph evidence; exit2 means invalid input or execution/persistence
failure; exit130 means cancellation. These codes do not approve a policy or
verify a provider delivery. Shared CLI forwarding and installed distribution
execution need their own integration evidence.

Inherited Git tracing destinations are masked, including open-ended
`GIT_TRACE*` keys. Trace2 configuration targets are disabled. Index, attribute and
configuration environment sources are isolated; ambient shallow-file and config
file selectors are denied. This prevents tracing from silently creating caller
files during metadata reads. It does not sandbox a replaced/malicious executable
or qualify arbitrary hostile filesystem mutation.
