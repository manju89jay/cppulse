# Single-stage bounded publication checkpoint

M2-01/M2-05/NFR-SCL-06 implementation continues. This finite checkpoint does not
accept the entire tasks or full production program.

The bounded publisher now keeps one exclusively owned stage across raw producer
facts, used-SDK capture, checked material projection, pure normalization and
conservative maintenance health. It publishes exactly once after a final current
source/input check. The `StagedReadProjection` is a separate factory-created
checked reader, not a RunSnapshot; it exposes no published path, manifest hash or
run reference. It checks registered immutable descriptor prefixes, byte hashes,
namespace safety and active writer token, while permitting additional registered
artifacts to be appended to its owner stage.

Independent actual SIGKILL evidence first showed a completed raw intermediate
becoming both latest pointers. The repaired journey preserves previous pointers
through normalization and an owned-process crash. Independent controls also
exposed final publication losing its writer token and direct caller metadata
bypassing the projection factory. Final publication now rechecks ownership before
visibility, after source callbacks, before directory rename and pointer changes.
Factory-only construction refuses the unchecked caller path. These are API and
cooperative writer invariants, not a hostile Python execution boundary.

A current source-bound broad gate passed137 checks in208.36s with reviewed
sources stable: all existing RunStore/reader/streaming controls, projection,
independent constructor/ownership controls, actual source-after-typed append
race, actual SIGKILL, bounded pipeline, work-unit bridge and SDK positive/negative
cases. Exact source/schema/test hashes and commands are in the evidence directory.
A final formatting/unused-test-import-only delta passed15 focused controls; Ruff
passed. Independent current source-bound review passed22 controls separately.

The source-after-typed race preserves the earlier positive facts as unpublished
diagnostic bytes, leaves the previous completed latest unchanged, and constructs
a separate partial/unverified/null-health attempt. It never demotes the same
already-qualified staged documents to an unverified published success. Original
per-unit receipts remain original; no aggregate native receipt is invented.

Remaining work: exact installed artifact after these changes; explicit safe
interruption recovery for the retained writer lock; separately interrupted
promotion between the two pointer files; all build configurations, qualified
cache reuse, whole-parent memory/representative scale and broader production
acceptance. The next recovery contract will retain process-incarnation identity,
coordinate local filesystem recovery and preserve old lock/stage evidence. Old
or foreign lock identity must remain unknown rather than being blindly cleared.
All changes and new files remain uncommitted; no Git refs or remote state changed.
