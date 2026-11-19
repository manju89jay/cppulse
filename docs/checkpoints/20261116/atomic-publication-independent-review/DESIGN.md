# Proposed atomic bounded publication (review, not implemented)

Authority: NFR-SCL-06, M2-01 and M2-05. The original acceptance scope is unchanged.
Current actual owned-child SIGKILL reproduction is `verification.json` (expected
exit1, all three pointer checks false, reviewed source unchanged). Both pointers
advertise a completed raw run with no analysis scope or health after the child
is killed before normalization. Baseline and raw immutable stores remain intact.

## Recommended smallest complete normal-path correction

Keep the existing public `StagedRun` open throughout raw retention, normalization
and health calculation, then call `publish` once. Do not call the two immutable
`persist_*` workflows from this path. They remain legitimate standalone commands
that derive from a real already-published parent.

1. Introduce an explicitly named read-only `StagedReadProjection` / material
   protocol: a frozen candidate manifest plus frozen artifact descriptors,
   checked `read_bytes` / `read_json`, and material-integrity verification.
   It is not a `RunSnapshot`, has no published-manifest hash, no public run
   reference and no fabricated parent provenance. Its candidate run ID is the
   real active staging ID, not evidence that it has committed. Reads check
   only its frozen descriptor inventory; final publication validates the entire
   final registered stage. Mutation and publication are absent from this API.
2. `normalize_work_unit_analysis` accepts this explicit material protocol as
   well as an adapter over a genuine published snapshot. Preserve original
   requests/results/receipts, distinct declaration/invocation/parse contexts,
   SDK bytes, full declared missing/excluded scope and global duplication.
3. Extract pure append/build operations from `persist_work_unit_analysis`:
   write checked normalized contracts and typed registry aliases into the same
   existing stage; return normalized documents and merged contexts. No artifact
   copy from a newly published run and no nested writer acquisition.
4. Calculate default health with `compute_maintenance_health` from those checked
   documents and full scope, append it to the same stage. Preserve unavailable
   input/null-health behavior and the conservative default inferred policy.
5. Build the final manifest with all raw/typed facts and operation stages.
   Recheck the existing strong project/discovery/native/resource callback and
   call the existing `stage.publish` once. Only this final publication changes
   pointers. Index/catalog work consumes that final immutable pin; it does not
   create a synthetic aggregate native receipt.

Normal completion writes each original artifact once and publishes one final
run. Existing standalone immutable derivations still copy actual parent bytes
and retain actual parent-manifest hashes. The bounded single-stage path has no
published parent, so it must not manufacture a parent hash merely to reuse that
standalone implementation.

## Failure and race semantics that must stay explicit

- Known partial/cancelled unit outcomes yield the complete declared scope and
  genuine receipts only, null/unavailable qualification as required, then one
  terminal partial/cancelled publication: latest_attempt advances; latest
  completed remains unchanged.
- A producer/normalizer exception before final commit leaves the existing
  completed/attempt pointers unchanged and preserves the owned unpublished
  stage plus work directory and the exact error. Never expose raw material as
  an implicitly completed whole bounded journey.
- A final current-input check failing after typed metadata was written cannot
  be repaired by changing the manifest to unverified while keeping qualified
  typed facts. Preserve that uncommitted failed stage. If a diagnostic partial
  publication is required, construct a fresh unverified attempt from the
  frozen raw descriptor inventory and rederive unknown facts; do not mutate a
  previously written qualified contract or invent source freshness. This rare
  fallback may copy raw material once; it must not reintroduce normal 3x copies.
- A child SIGKILL while the sole writer stage is open may leave its lock. The
  existing explicit-recovery boundary remains: preserve it, do not auto-delete
  an unknown prior lock or upload fixture Git objects.
- Each legacy pointer replacement is individually atomic, but latest_attempt
  and latest_completed are still two files. Do not claim pair-generation
  atomicity or arbitrary power-loss recovery from this correction. If required,
  a separately specified canonical pointer envelope/journal is needed.

## Rejected shortcut / smaller honest intermediate alternative

`make_latest=False` only suppresses latest_completed; it still advances
latest_attempt and therefore fails this regression. If a detached-publication
interim is chosen instead, it needs an explicit orthogonal visibility policy
that advances neither pointer, and exactly one checked final promotion. All
intermediate objects must remain genuine immutable published snapshots with
explicit intermediate semantics. That alternative still incurs repeated copies
and is not the recommended full normal-path transaction above.

## Meaningful independent gates

- Pause at the existing pure normalizer entry after raw material has been
  retained. The same barrier works when its input becomes a named staged
  projection: do not require a RunSnapshot or a fake published hash.
- While an owned child is paused, resolve both pointers independently and prove
  they still identify the previous complete typed+health snapshot.
- SIGKILL only that owned child at the barrier; after wait/reap, prove both
  pointers and prior bytes unchanged. Preserve the failed stage and lock.
- On success, readers see either the previous final pin or the new full final
  pin. Resolve once and bind all artifacts to that manifest, including scope,
  all original receipts, metrics, SDK proofs and default health.
- Exercise partial/cancelled scope, source/native/SDK drift before final commit,
  malformed output, failed validation and index failure without stale success.
- Add projection-only tests: no published reference/hash, frozen descriptors,
  safe reads, corruption/unknown artifact rejection, closed-stage behavior;
  ordinary published-snapshot workflows remain compatible.

This proposal does not close the full P5 scale/cache/catalog/platform plan or
M2-01/M2-05 by itself. All work remains uncommitted; no remote actions occurred.
