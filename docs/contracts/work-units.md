# Bounded native work units, reuse and indexed reads

Status: **contract/design proposal**, 2026-11-14. No scheduler, cache,
checkpoint recovery, indexed API or benchmark result is claimed by this file.
The accompanying draft schemas/tests validate document shapes only; they are
not registered as supported production contracts.

This preserves all M2-01–07 obligations and NFR-SCL-01–10. It also supports
FR-CTX-03–08, FR-GIT-02, FR-UX-06/08 and AC-04/05/06. It extends the existing
analyzer, identities, execution primitives, normalizers and RunStore; it does
not introduce another store, policy evaluator or public product.

## Existing boundaries to preserve

| Existing code | Reuse | Required extension |
|---|---|---|
| `identities.py` | Canonical source/context hashes and finite-input rechecks | Streaming inventory construction and dependency/lookup manifests; never treat the current `inventory_complete` assertion as discovery proof |
| `execution.py` | CancellationToken, bounded log draining, process groups, explicit argv and receipts | Shared bounded native executor; current recipe limits do not enforce CPU/memory and a 100K-unit plan must not become one enormous recipe/`Future` list |
| `analysis.py` | Checked native input/report binding, observed parse contexts, normalized inventory/observations | Explicit selected-file binding, separate authorized source/work roots, dependency observations and checked cache lineage |
| `run_store.py` | Single-publisher staging, artifact hashes, atomic publication and current-attempt semantics | Streaming verified ingestion and an independently rebuildable SQLite index; preserve POSIX support limitations until real platform qualification |
| `analyzer-core` | Existing libclang rule engine and input-size limit | Explicit finite file selection, unambiguous per-context commands, observed dependencies and early per-worker limits |

RunStore remains authoritative. A SQLite row, cache hit, successful process exit
or existing `latest.json` cannot manufacture a current successful assessment.
Existing partial/cancelled runs use the current-attempt path; this work does not
silently change which snapshots advance `latest.json`.

## Unit and native producer contract

One unit is one selected source/header file in one declared parse context. A
header parsed independently remains a header parse; it is not automatically an
observed consumer build. Selected consumer instantiations remain separate,
explicit evidence. Initial workers preserve current per-file diagnostic
ownership rather than silently changing header diagnostic counting.

The parent discovers scope once, records exclusions/unreadable inputs and
expands contexts. It does not let every worker rediscover the entire repository.
The proposed native option is `--file-list PATH`: a JSON array containing this
unit's canonical repository-relative file identity. This option is **not yet
implemented**. The producer must reject duplicates, escapes, symlinks and
unrequested outputs; it must report missing/excluded/skipped selected files.
Changing a selected input during execution leaves that unit incomplete.

For multiple compilation commands, the parent creates a retained single-entry
database for the selected command, preserving its original working directory,
argument order, repeated flags, target, defines, forced includes and standard.
It records the original database/command selection and hashes both original and
effective material. It never rewrites the command to look observed or turns an
inferred header command into a consumer configuration. Native-reported parse
arguments remain the authority for what libclang received.

Keep requested parse/build context, actual native invocation context and observed
libclang parse context distinct. The actual receipt names the native executable
and real argv/cwd; it is not the compiler recorded in the project database.
Temporary output/selection paths belong to invocation provenance, not a fabricated
stable parse context. Reuse keys use the checked effective parse inputs, while
the original invocation and derived parse-context identities remain retained.

The request pins the source manifest, primary file/context, native binary,
registry, effective extraction configuration, selection manifest, compilation
database and resource manifest. Source and work roots are separate explicit
authorizations. Outputs stay under the worker's private work root, allowing
read-only source trees and output outside the checkout while source identities
remain repository-relative. This needs a checked work-unit normalizer; the
existing recipe normalizer's stricter single-workspace behavior remains valid.
Do not use `/` as an artificial workspace or widen the analyzed source scope to
make its output-path checks pass.

## Bounds, isolation and cancellation

The agreed first implementation launches the **actual native executable**;
early native flags apply platform-supported address-space/CPU limits before
AST work. The parent enforces elapsed wall time, output/log byte caps and
process-group cancellation. No `preexec_fn` runs in the threaded scheduler.
Native initialization already performed before the guard must be disclosed;
an address-space limit is not an RSS limit or an aggregate system-memory bound.
An unusably low limit or unavailable capability returns an explicit unsupported
or operational result before parsing, rather than claiming enforcement.

The first qualified limit platform must be named and actually tested. Other
platforms cannot ignore requested limits and report success. Windows Job Objects
and macOS resource semantics need their own implementation/installed checks.
This design does not make arbitrary project commands a sandbox.

A Python wrapper cannot be substituted while recording `argv[0]` as native:
the current normalizer checks the actual executable hash and native options in
the receipt. A future wrapper would require honest wrapper/child receipts and
new validation. There is no such transparent wrapper exception here.

The scheduler keeps at most `jobs` active processes and a bounded ready queue.
It stops launching on cancellation, sends TERM then KILL to owned groups and
drains/reaps them. A timeout, signal, failed exec, malformed/oversized output,
write failure or input change is a unit result, never an empty clean report.
Independent accepted units survive another unit's crash. A generic SIGKILL is
not labeled an observed out-of-memory kill without evidence of its cause.

Keep execution outcome separate from parse outcome and finding violations.
Successful execution may yield a partial AST; findings do not make process
execution fail. Record requested/applied limit capabilities, exit/signal,
elapsed time, measured resource values and their scope. Unmeasured CPU/peak
memory is null with a reason; do not substitute a sum of unrelated high-water
marks for a measured process-tree peak.

## Facts cache and assessment reuse

The facts key contains the primary input and relevant dependency content,
include-search/negative-lookup state, ordered effective context, native/parser
and toolchain/resource identities, detector/registry versions and effective
extraction configuration. Rendering and policy weights are not extraction
inputs. Detector thresholds/enabled checks and `max_file_bytes` are extraction
inputs because they change produced facts or scope.

| Change | Invalidation |
|---|---|
| Source, included/forced header, generated input, macro, standard or target | Affected facts; conservative wider invalidation when relationships are incomplete |
| Compiler/libclang/resource/sysroot/tool identity | Every affected context |
| New/deleted earlier-search header or `__has_include` result | Affected facts even when previously included header bytes are unchanged |
| Unbound external dependency, include-search state or relevant environment | No positive cache reuse until the missing identity is resolved |
| Time/mtime-dependent built-ins such as `__TIME__` or `__TIMESTAMP__` | No reuse unless their effective inputs are explicitly fixed and verified |
| Policy weight/gate/scorer change only | Re-evaluate retained compatible facts; no AST process |
| Policy scope requiring previously unextracted inputs/checks | Extract missing facts; do not turn absence into zero |

Dependency closure must include the include-search state relevant to negative
lookups, response files, forced includes, generated inputs, resources and
authorized external/toolchain inputs. `clang_getInclusions` alone does not prove
negative lookup completeness. Relevant environment is an explicit allowlisted
identity, not a saved unrestricted environment dump. Unknown closure causes a
miss; hashing only the primary file is never an acceptable fallback. A complete
project manifest may conservatively invalidate project changes, but cannot
resolve unknown external inputs by itself.

Only stable, integrity-checked, fully observed facts are positive reusable cache
entries. Cache entries preserve original producer/receipt/source timestamps and
scope. A cache lookup does not execute the native process. The result therefore
has `mode: reused`, no new execution receipt, and a pinned original run/artifact
plus a current content/context binding proof. Failed/partial entries may be
retained diagnostically but cannot masquerade as a complete hit.

Current typed native facts link a whole-source digest and execution receipt.
They cannot be copied into a different-source run by rewriting those fields.
Before positive reuse is enabled, add a checked analysis-facts reuse profile
and lineage that derives a new current inventory from identical relevant
inputs while retaining original bytes/receipts. Unknown profiles must be
rejected by consumers. This is a required contract/consumer implementation,
not permission to weaken existing exact-source validation. Runtime tests,
coverage and sanitizer evidence are not promoted by the analysis cache.

An assessment key hashes the committed compatible fact pins, scorer/policy
versions, resolved control configuration, required contexts/scope and applicable
baseline/suppression identities. Re-evaluation is pure and never launches
recipes. Changing source applicability requires a new binding, not a convenient
reuse of an old passing gate.

## Checkpoints and recovery

Unit requests/results and output hashes are written to private attempt state.
A unit becomes accepted only after complete validation and durable publication
of its result descriptor. Pending/running work is not complete. On restart,
verify every retained result and its current key; accept only matching complete
units, reschedule interrupted units, and invalidate changed inputs/contexts.
Malformed or truncated journal/result bytes do not become empty results.

The parent assembles one coherent run, validates its source again and uses the
existing RunStore publication lock/staging/pointers. It does not publish each
worker as a new project-wide `latest`. Failure between fact acceptance, final
manifest, pointer and index updates is covered by interruption tests. A stale
prior pass cannot replace the interrupted current attempt.

Facts/cache objects are immutable and content-addressed. Cache cleanup is a
separate operation that cannot remove objects pinned by retained runs. Cache
trust is local filesystem integrity, not authenticated producer identity.

## SQLite catalog, streaming and cursors

The catalog indexes committed `(run_id, manifest_sha256)` pins, contexts, unit
lineage, observations and searchable fields. It is disposable derived state;
RunStore artifacts remain the portable truth. Ingest one run transactionally
only after its artifact hashes/contracts/counts pass. An existing run ID with a
different manifest hash is an integrity error, not an upsert.

Resolve a requested run once, then query only that pin. If a committed run is
not indexed, return an explicit `index_pending` result or index that exact pin;
do not fall back to another run's rows. A corrupt/missing catalog can be rebuilt
from retained runs. Schema upgrades use an explicit migration/rebuild, keeping
the prior catalog until the replacement validates. SQLite files/locks must be
on a qualified local filesystem. WAL is an optional qualified concurrency mode,
not an assumption that network/shared filesystems provide those semantics.

Use prepared SQL and keyset pagination with a deterministic total sort. Cursor
payloads bind protocol version, run ID, manifest hash, normalized query hash,
sort and last stable row key. Reject wrong-run/wrong-filter/version cursors and
unbounded page sizes. Checksums identify accidental corruption, not producer
authentication. Filtering/counts and rows use the same run and query semantics.
Dashboard/API consumers request bounded pages instead of downloading a project.

Native per-unit JSON is capped. Aggregate facts, source inventories and legacy
JSON exports are streamed/batched from accepted units/catalog rows; a 100K-file
run must not materialize every request, observation and duplicate export in
memory. Existing `read_bytes`, JSON-list construction and full-document
validation are not a streaming implementation. New stream ingestion validates
each record, hashes through EOF and commits index/results only after integrity
passes. Canonical streaming hashes must equal existing canonical identity
functions, including Unicode/key ordering, before they replace them.

## Implementation and acceptance order

1. Approve request/result/cache/cursor drafts and semantic checks. Keep unsupported
   profiles unregistered until producers/consumers exist. Test schema bounds,
   duplicate IDs, root/selection bindings, exact key computation and invalid
   reuse before launching work.
2. Implement native finite selection, observed dependencies and early limit
   capabilities. Verify one source/header/context at a time, equal basenames,
   compilation-command variants, exclusions, outside-source outputs, missing
   inputs, resource failure and unchanged baseline diagnostics.
3. Implement bounded processes and durable accepted-unit checkpoints. Assert
   active workers never exceed jobs; preserve independent units after SIGSEGV,
   timeout, cancellation, limit exhaustion, malformed output and write failure.
4. Implement dependency/lookup-aware keys and checked lineage. Compare complete
   semantic facts with clean execution after source/shared-header/add-delete
   lookup/flags/tool/sysroot/generated/environment edits. Verify zero AST launches
   on a valid weight-only policy re-evaluation. Unknown closure remains a miss.
5. Implement transactional indexed ingestion, migration/rebuild and pinned
   keyset queries. Exercise latest/index races, repeated finding occurrences,
   query changes, concurrent readers and bounded page/export memory.
6. Connect public orchestration and presentation using the existing contracts.
   CLI/API/report/editor values and incomplete states must agree on the same pin.
7. Run actual named-host native-analysis tiers near 1K/10K/100K files and growing
   histories, with cold/warm/source/shared-header/flag/policy/history-append and
   interrupted/resumed cases. Use repeated measurements; retain workload/source
   identities, counts, cache decisions, wall/CPU/peak-memory method/environment
   and semantic comparisons. Synthetic fixtures are labeled. Scheduler-only
   load tests do not establish analyzer throughput. Set budgets after results,
   then test repeated regressions rather than one noisy timing.

## Primary implementation references

- [Python subprocess](https://docs.python.org/3.12/library/subprocess.html):
  explicit argv, process sessions and the thread-safety restriction on pre-exec hooks.
- [Python resource](https://docs.python.org/3.12/library/resource.html):
  platform-dependent limits and resource-measurement definitions.
- [SQLite transactions](https://www.sqlite.org/lang_transaction.html) and
  [WAL](https://www.sqlite.org/wal.html): transaction snapshots and local-filesystem
  concurrency constraints. These references are technical guidance, not evidence
  that cppulse has implemented or qualified the proposed behavior.
