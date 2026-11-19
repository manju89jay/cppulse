# Private local portfolio and scheduled-report preview

This source module reads explicitly selected historical runs from configured
local projects and writes local scheduled JSON reports on an explicit tick. It
is a P10 implementation slice, not complete M8 or a hosted organization service.
Its private draft contracts are in `contracts/schemas/portfolio_private` inside
the installed package. No account, provider, daemon, message or network delivery
is required or executed.

`build_portfolio(config, now=aware_datetime)` reads one exact run ID and manifest
SHA-256 per configured project using the checked, read-only RunStore. It resolves
no latest pointers. Every project preserves its original source/scope, run timestamps, contexts,
collection/input-verification state and measured-health artifact/document/hash.
Failures stay project-local and produce a partial inventory alongside independent
readable projects. A replay cutoff before a selected run finished makes that
project unavailable; later facts are never borrowed into an earlier report.
The report's complete/partial status means selected run
**readability**, not source verification, policy acceptance or goal satisfaction.

The trusted local configuration explicitly supplies authorized absolute roots
and project stores beneath them. Roots and stores must be canonical absolute
paths; symlink ancestors are refused by the checked reader. A store cannot be
counted as two projects. The caller must own/approve this configuration: accepting
an allowlist supplied by a remote user is not tenant authorization. No SSO/RBAC,
repository-provider authentication or independent identity review is claimed.

## Goals and team declarations

No project scores are averaged. Each goal selects one project plus the exact
file-scope digest, full scorer/profile/calibration digest, required contexts and
minimum measured health. Project output includes scope_digest and
health.scorer_digest so a goal can pin the exact published comparison inputs. Missing or ambiguous measured artifacts, mismatched
scope/method/context, null health, unverified source bindings or partial collection
make that goal unknown. A supported goal over verified completed historical facts
can be observed_met or observed_unmet; both remain explicitly historical with
current_source_verified false. Neither is a current-source policy pass.

If a run has several measured-health artifacts, select health_artifact_id in the
project reference; the producer never silently chooses a favorable score.
Legacy attempted-file health is not substituted for measured context health.
Goals retain their exact comparison prerequisites and raw stored value/threshold.
The report validator rechecks goal predicates against those selected documents.
Pass expected_config to anchor project pins, goal prerequisites, team history and
health selection to an independently trusted caller request. The producer and
repeated-tick readback always do this. Validation without that request checks
internal consistency only; hashes do not authenticate a producer.

Dated team_history entries assign a project to a declared team over half-open
[effective_from,effective_until) UTC-normalized intervals. Overlap for the same
project is rejected. The original declarations remain in the report so changes
have inspectable effective dates. This is project assignment, not authenticated
staff identity, inferred expertise, authorship fragmentation or complete team
alignment. Behavioral measurements retain their independent producer semantics.

## Configuration

Required top-level fields are version (1.0.0), id, authorized_roots, projects,
goals, team_history and schedules. Empty optional-feature arrays are explicit.

| Collection | Required fields |
|---|---|
| projects | id, store, run_id, manifest_sha256; optional health_artifact_id |
| goals | id, project_id, minimum_health, scope_digest, scorer_digest, required_context_ids |
| team_history | project_id, team_id, effective_from, effective_until (timestamp or null) |
| schedules | id, timezone (IANA), hour, minute, start_date, lookback_days, max_attempts, retry_seconds, enabled |

Source calls use public module functions:

```python
from datetime import datetime, timezone
from pathlib import Path
from cppulse.portfolio import build_portfolio, schedule_tick

report = build_portfolio(config, now=datetime.now(timezone.utc))
# Explicit local write; the authorized directory must already exist.
outcome = schedule_tick(config, output_root=Path('/approved/local/reports'),
                        now=datetime.now(timezone.utc))
```

The CLI integration must use these functions and the same contracts; it must
not calculate separate portfolio scores. The actual integration fixture config
is retained at work/portfolio-actual/config.json, with its source/environment
limitations in the corresponding checkpoint. Those absolute paths are this
Cloud execution's evidence, not portable default project locations.

## Explicit local schedule ticks

A tick performs finite due daily occurrences within lookback_days, counted by
local calendar dates including today, and no earlier than start_date. Earlier
missed dates are deliberately outside that configured catch-up window. Already
recorded failed/pending jobs keep their retries after a midnight/window rollover;
the window bounds new occurrence admission, not the loss of queued retry work. There is
no background scheduler, cron/system-service installation or automatic project
analysis/build/test. Tick callers choose when it runs.

IANA timezone conversion uses the exact installed TZif bytes whose SHA-256 is
journal-bound to the configuration generation. A changed provider blocks further
delivery for the same generation; review the timezone change and supply an
explicit new configuration generation before resuming. The loaded bytes used for
conversion are the same bytes whose digest is bound. Nonexistent spring-forward
local times are skipped. Repeated autumn local times use fold 0 (the earlier
instant) once. Intended times are retained in UTC. Configuration/occurrence
identities prevent repeated ticks from duplicating a successful local delivery.

Each selected generation retains immutable configuration-<digest>.json input
bytes, so changing a goal/team/schedule file cannot erase historical settings.
Active job counts refer only to the selected generation; old jobs and original
configurations remain retained, not silently retargeted. Each occurrence
publishes report-<job-sha256>.json and an atomic
schedule-state.json journal. The job digest binds configuration, schedule and
intended UTC instant. Pending state is recorded before report publication;
subsequent failure/interruption cannot manufacture success. Reports use the
intended instant for deterministic membership selection and fact-availability
cutoff. A late backfill cannot claim facts produced after its intended instant. The journal records
actual attempts, retry time, error, report SHA-256 and report readability.
The tick returns active_job_counts and next_retry_at even when no new outcome
is due, so a successful no-op cannot conceal waiting failures. Retry delay is relative to the last attempted tick, not a promise that a daemon
will wake at that instant. Failed attempts stop at max_attempts. A pending crash
at the retry budget is exhausted explicitly rather than launching an extra job.

Successful jobs recheck retained report hashes on later due ticks. Changed
report bytes do not retain a positive delivery state and are not overwritten.
Interrupted report publication can be retried idempotently when the exact pinned
bytes already exist. A local report may be delivered successfully while its
portfolio is partial or goals unknown; report_status and policy_acceptance
preserve that distinction. No message, webhook, provider tracker or remote report
is sent.

An exclusive cooperative writer lock prevents concurrent ticks. A missing journal with retained report artifacts is an error requiring journal
restoration, not a silent restart. Unknown stale
locks are not deleted automatically: establish writer ownership/termination
before explicit local operator recovery. Directory-relative POSIX descriptors,
no-follow reads, exclusive temporary files and atomic publication protect the
selected local output paths. This is not a hostile-code sandbox or a portable
Windows implementation. Keep prior reports and journal when starting a new
configuration generation; do not edit old outcomes to look current.

## Finite limits and remaining work

Configuration is at most 256 KiB, up to 64 projects, 256 goals, 512 dated team
assignments and 16 schedules. Each checked snapshot has a 32 MiB manifest/artifact
payload budget. A projected project is at most 1 MiB (including raw JSON); aggregate project
payload is at most 3 MiB. An overbudget project remains explicitly unavailable
while independent admitted projects survive. A report and journal are bounded
at 4 MiB. Daily catch-up is
1–31 days; retries 1–5; retry interval 1–86,400 seconds. The private journal holds
up to 4,096 jobs and 1,024 timezone-generation bindings; reaching its limit is an
explicit error requiring reviewed retention/migration, not silent history loss.
These are payload/admission bounds, not measured OS memory/CPU guarantees.

The source suite exercises actual persisted RunStores and actual local delivery,
with authored controlled contracts. Actual native-clean, native-finding and
unverified-consumer snapshots are separately exercised with source/artifact pins.
Neither replaces final installed-CLI/client or support-matrix qualification.

M8 still includes deeper team/fragmentation views, provider-specific portfolio
access, branches/task/delivery analytics, issue-tracker cost/ROI, external report
and notification integrations, real provider scheduling/delivery outcomes and
release/user/platform qualification. Those require their contracts, configured
access and separate authorization for external effects. This local slice closes
none of those by implication and claims no full M8 or P10 completion.
