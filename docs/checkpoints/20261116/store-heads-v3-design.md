# Atomic head authority: versioned migration and finite evidence

The actual owned-child SIGKILL red in `work/store-heads-crash-red/` demonstrates
that v2 can expose a new completed latest attempt and the preceding completed
latest collection. It kills the owned publisher after the first pointer replace;
it does not simulate a manifest or relabel a partial collection.

A single v3 `heads.json` must hold both checked manifest references and a
monotonically increasing generation. One atomic replace is the commit point.
Resolvers must acquire one bounded, regular, nofollow JSON snapshot per request;
related consumer reads must retain that snapshot instead of rereading two paths.
Completed publication changes both references in the same document; a partial or
cancelled attempt changes only the attempt reference. Explicit make_latest=False
retains the completed reference. Missing/corrupt heads never fall back to older
pointer files. A renamed but unreferenced run is retained for inspection, never
silently promoted after a crash.

## Proposed explicit compatibility boundary

The coordinator approved this explicit boundary before production changes. Existing v2 stores
remain readable and writable using their unchanged v2 contract until an explicit
upgrade. There is no claim that an old binary understands v3.

1. Under the cooperative publication guard and exclusive writer slot, validate
   both existing v2 pointers/manifests and preserve their exact bytes in an
   exclusive, fsynced migration journal/archive. Reject an active/unknown writer.
2. Persist a format marker with version 3 and phase `migrating`. Current readers
   and writers refuse incomplete migration with an actionable resume message.
3. Replace both legacy pointer pathnames with reserved directories. Preserve
   original bytes before removal. Unsupported v2 readers fail to read JSON;
   unsupported v2 writers cannot atomically replace a directory with a file.
   There are no apparently current v2 mirror files. An old writer might retain
   an unreferenced run and lock before failing: this is a refusal, not successful
   publication, and explicit recovery remains necessary.
4. Write checked initial v3 heads, then atomically activate the format marker.
   Interrupted stages remain identifiable and resumable from the exact journal;
   they do not roll back to a mixed implicit v2 store. Refuse symlinks, foreign
   owners, changed archived bytes, unsafe modes, unknown fields/versions and
   inconsistent heads/marker identities throughout.
5. Export a checked selected head epoch to a separate new v2 snapshot directory
   on explicit request. Preserve original v2 manifest versions and artifact bytes;
   never rewrite the live v3 authority or claim old writers are supported there.

Required tests before rollout: unchanged v2 semantic regression suite; readonly
v2 opening; empty and populated migration; partial latest-attempt migration;
actual old-reader and old-writer refusal; separate v2 export round trip; explicit
migration resume after each durable step; corruption/symlink/version refusal;
actual SIGKILL before/after the single heads replacement; concurrent related
readers observe one coherent generation. Derived old files cannot satisfy these
checks. NFR-MNT06/AC13 and full P14 remain open until their applicable checks pass.

Recovery's separate after-unlink boundary is now covered by 22 passing tests,
including two actual subprocess SIGKILL controls and a new active writer. The
independent source-bound record is
`work/store-recovery-independent-review4/verification.json`; that evidence covers
explicit selected local-lock recovery, not atomic reader-head publication.

## Implementation checkpoint (2026-11-16, still incomplete)

The coordinator approved this boundary. `store_heads.py`, strict private
`heads-v3`, `format-v3` and `migration-v3` schemas and RunStore now implement it.
Fresh empty stores default to v3. Existing v2 stores remain readable; a default
writer refuses with `STORE_UPGRADE_REQUIRED` until explicit migration. An
explicit `format_version="2.0.0"` retains the historical two-pointer lane and its
unqualified atomicity. The original v2 semantic test assertions remain intact in
that explicit lane. Current v3 consumer regressions compare the actual single
`heads.json` authority, including null heads; directory-fence presence never
serves as evidence of a published collection.

`RunStore.resolve_heads()` returns `(generation, completed, attempt)` from one
checked authority read. `upgrade_store_to_v3(store)` performs/resumes migration;
`export_store_v2(store, destination)` creates a separate new checked offline v2
snapshot with original manifest/artifact bytes. Root CLI integration and a fresh
installed wheel remain required.

The finite initial gate passed 97 tests in 11.34 seconds with source/test/schema
pins unchanged (`work/store-heads-v3-current/verification.json`); it predates the
default flip and subsequent independent repairs. The default-first gate passed
125 tests, and the delegated metadata/transfer guard suite passed 159. Eight
actual owned subprocess SIGKILL migration boundaries resume original completed
and partial heads; two commit-boundary cases expose the entire old or entire new
v3 epoch. These are process interruption tests, not physical power-loss tests.

Independent review retained two meaningful defects and their repairs. Migration
resume now reopens both pinned run manifests and all artifacts before destructive
fences and again before activation. A reader's already-open old heads descriptor
may legitimately acquire link count zero after atomic replacement; the reader
now accepts zero/one and continues refusing extra hardlinks. A deterministic real
replace-after-open regression demonstrates the old failure and retained old
epoch. These repairs require a new final source-bound review gate.

No whole requirement, cross-platform claim or full P14 completion follows from
these tests. A broader default consumer diagnostic and fresh installed-artifact
verification are pending; preserved earlier diagnostic failures remain in
`work/store-heads-v3-current/`. The authority protocol does not add producer
freshness or reuse previous facts as current evidence.


The final independent v3 gate passed 146 tests in 17.08 seconds with all 20
source/schema/test pins unchanged. Its 739 artifact pins and complete finite
fixture archive are retained in
`store-heads-independent-review4-evidence/verification.json` and adjacent files.
That epoch includes actual installed old-wheel refusal and export reading. The
subsequent public `format_version` accessor delta passed 25 tests in 5.91 seconds;
two repaired actual-tool consumer cases passed in 8.43 seconds. These are separate
qualification epochs, not a single fresh combined acceptance run. A later
corrupt-authority writer-entry red was reproduced and repaired: `begin()` now
validates heads/fences before writer state and repeats validation under the
acquisition guard. Corruption between those checks is covered explicitly.
Shared decision PROD-20261116-17 records the approved boundary and limits.


The final owner gate after the accessor and writer-entry repair passed **148
tests in 15.02 seconds**, exit 0, with all **22** selected source/schema/test pins
unchanged. `store-heads-v3-current-evidence/entry-sourcebound.json` records the
actual command and hashes. Its 1,876 retained fixture entries are recorded with
regular-file SHA256/size, symlink target and modes; the complete fixture archive
is 106,538 bytes. The two original consumer failures also pass with the actual
selected native/CMake environment (2 tests, 8.43 seconds). No fresh complete
393-consumer combined gate, whole root suite or newly installed wheel is claimed
from these separate finite records. Shared root CLI/API work remains coordinated
outside this owner gate. All changes remain uncommitted.


Two internal review-script adapters also required migration: directory-fence
existence is not evidence of a completed v3 head. Actual collection missing-report
CLI originally exited 1 after publishing a valid partial attempt; the fixed
script reads both references from one v3 epoch, preserves the v2 branch, exits 0
and retains `latest_completed_collection=null`. The actual policy missing-tests
journey exits 0 with one partial collection, `insufficient_evidence` and a null
completed snapshot. Its selected native binary remains SHA9004. These source-bound
script fixtures are integration checks only. Their 1,311 original artifact pins
cover 58,452,188 retained bytes; exact run manifests/head/format/plan metadata and
commands/logs are preserved alongside the checkpoint. The mandatory full-plan
verifier rerun after these repairs still exits **3** (120 open, 65 active, 2
blocked), with all 187 IDs and the unchanged definition hash recorded. No ledger
state was changed by this owner, and the production program remains incomplete.
