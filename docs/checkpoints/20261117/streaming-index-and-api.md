# Bounded report streaming, transactional query indexes and source API

This is scoped implementation evidence, not whole-program acceptance. All118
requirements,60M0–M9tasks,nine obligations and P0–P14 remain. Canonical states are
unchanged:120open,65active,2blocked. All changes remain uncommitted on
`codex/cppulse-local-core-20261114`, HEAD
`6f8b662a89b367f8c6883298dc97950150d7ba4f`.

## Shared storage gates

`run_store.py` at `0fd780f630bc489cdc9e941e5aaadf1c76260810a677f75b61c6e6f6150b9fda`
adds a material-only publication guard, separate from original source checks,
and rejects oversized/growing/truncated artifact bodies at the checked read
boundary. Material checks cannot promote `input_verification`. The original
whole-run RunSnapshot contract is retained; selected original report reads use
a narrower metadata/descriptor projection instead of fabricating a snapshot.

Material publication:109owner/115independent checks and9pipeline/API checks.
Read bounds:7meaningful original reds, then126owner/132independent checks,
including growth/truncation controls; actual exits0, source stable.
The first126-case run had a monkeypatch keyword-forwarding failure; only that
harness was corrected, retaining its original mutation and single-read checks.

Evidence: `work/store-material14/qualified.json`,
`work/runtime-review7/store-material14/corrected-head-fixture/verification.json`,
`work/store-read-bounds14/live.json`,
`work/runtime-review7/store-read-bounds14/verification.json`.
IDs: NFR-SCL-05,NFR-SCL-06,M2-05,AC-06,NFR-MNT-06.

## Byte-bound streaming producer and request contract

`json_stream.py` at `bc4386123025bc106c954523ff09d662879e49a16c4548597f337beec8f693c5`
checks whole JSON structure, finite budgets, size/SHA and selected raw rows
without materializing the report. Selected rows remain provisional until the
whole document succeeds. Ignored metadata semantics remain unverified. Array
item byte limits apply to ignored as well as selected elements; global array
counts include both.104owner/118independent checks pass (98% producer coverage).

The retained original protobuf report is218,346,801bytes,
SHA`1606afbb0500f328d30065ced1f5e814b052bedebd28fb2ddf66872dbb4fa788`.
The standard1MiB item profile correctly fails on a large ignored metadata
element: its19,017earlier rows remain provisional. An explicitly supported
32MiB item/10M array-element profile succeeds on all original bytes in121.52s,
peakRSS20,512KiB.19,017rows match the independently checked bounded native
summary. Raw rows, in order and prefixed by unsigned8-byte lengths, hash to
`6daecc35d9982440856505266654625c6f11514bdd94e960cc19c9bece587480`.
This is an actual report-row check, not a100K-file benchmark or corpus accuracy.

Evidence: `work/result-stream14/qualification.json`,
`work/result-stream14/actual-profile-default/verification.json` (failed),
`work/result-stream14/actual-profile-large/verification.json`,
`work/runtime-review7/result-stream14-actual/verification.json`.

The closed exact-integer private request contract at
`contracts/result_index.py` SHA`1a958cae3d62035c88d0fb6481b1b75b719c9ee88ad809ec2b2a90823f1e470f`
has59owner/65independent checks. Its run/path/artifact identities agree with
existing storage constraints. Contract evidence does not itself prove indexing.
IDs: NFR-SCL-05,M2-05,FR-GIT-02,FR-UX-08.

## Transactional selected-artifact index

`result_index.py` SHA`c287bdece575d30cf48088dca664f438a269ffdabf3cf986fb186e9e6f5e39da`
builds a private SQLite database, validates each retained finding, and publishes
its database/receipt as a separate verified derived run only after complete
source checks. Exact SQLite tables/indexes, private manifest versions, receipt
scope and search-column/raw-row agreement are validated on reuse/query. No
original store head moves. Native analysis reuse is always false.

Independent review found12real protocol/schema failures and a further real
pre-read budget failure. All remain retained with their repaired controls.
Final owner qualification282checks/92% coverage/Ruff passes; fresh independent
18controls pass, including physical growth before body verification. Source
inputs are frozen; the shared store update9b0→0fd is explicitly journaled.

Evidence: `work/result-index14/implementation/preread-qualification.json`,
`work/runtime-review7/result-index14/preread-c287/corrected-verification.json`.
The review's first2failures were its missing-close spy harness, retained and
corrected without product changes.

The actual report's derived database is10,616,832bytes,
SHA`69b8aa9a56e35816a17b081f8f7e551a1ee15487fd833826410779d952b8b2a7`,
manifest`a42c1dacfb78832b58ac245d20f53ea080b7ccad0efcd96398e350b6f3cd800d`.
Cold construction152.60s, warm verification0.36s, first page0.95s,
peakRSS36,780KiB;19functional assertions passed. However the original overall
driver exited1 because lead incorrectly included the mutable execution board
in its frozen runtime inputs while dispatch changed. That gate stays failed.
Independent46checks isolate that sole metadata change and verify exact original
report, database,19,017ordered raw rows and category counts. A separate fresh
11check reuse/page run exits0 with runtime/source/cache bytes and identities
stable, without rebuilding or rewriting the historical failure.

Evidence: `work/result-index14/actual/verification.json` (overall failed1),
`work/runtime-review7/result-index14/actual-c287/finite-failed-wrapper-verification.json`,
`work/result-index14/actual-reuse/verification.json` (fresh0), corresponding
`work/heavyweight-jobs/result-index14-actual*/record.json`.

## Source API integration

The existing findings endpoint now selects metadata after authentication,
refuses incomplete attempts, pins one v2/v3 attempt, and pages through the
selected artifact index without opening the original full RunSnapshot. Exact
file and literal message filters preserve order and repeated occurrences.
Responses include source/index pins and explicit selected-artifact/false-cache
scope. Flat compatibility remains distinct. See
`docs/contracts/indexed-findings-api.md` for configuration and limitations.

33original new-test failures drove implementation; a subsequent6case failure
preserved the existing layout-error message contract.116owner API/pin/layout
checks pass, then62independent checks including57new owner cases and5additional
auth/head/protocol/query-bound controls. The added artifact-newline negative
control already passed and is not counted as a product regression. The first
coverage report accidentally shared `.coverage` with the worker; later API
coverage uses a unique file and is79% for this named source scope only.

Actual authenticated owned-loopback Uvicorn HTTP exercises the exact retained
large candidate:13checks, serverexit0, source/cache/heads stable; no new cache
key or native execution. Evidence: `work/index-api16/qualified2.json`,
`work/runtime-review7/index-api16/verification.json`,
`work/index-api16/actual-http/verification.json`,
`work/heavyweight-jobs/index-api16-actual-http/record.json`.
IDs: FR-UX-08,M2-06,AC-12,NFR-SCL-05,M2-05.

## Other independently reviewed current producers

GCC sanitizer source`2ebb0c089f22ae525a89c2551195195100664ff6abf233acb0f346044a425c41`
passes100owner checks including all actual normalizations (99% scope coverage),
82independent live checks and993retained12-case evidence assertions. Nine real
reds repaired occurrence-local sanitizer pairing, unknown fatal diagnostics and
invalid Unicode. UBSan exit0/passingCTest still retains failed sanitizer facts;
plain, zero/all-skipped and instrumentation gaps remain unsupported.
Evidence: `work/heavyweight-jobs/sanitizer15-live/record.json`,
`work/runtime-review7/sanitizer-adapter15-live/verification.json`,
`work/runtime-review7/sanitizer-adapter15-live/actual-normalization-audit/verification.json`.
IDs: FR-EVD-02,FR-EVD-08,M5-03,AC-09.

Branch source`48fd7ce2509238da1756e9ad671d6a2e6469af32a7088a5bc5bef09c0908f73c`
replaces floating POSIX-second comparisons with exact integer microseconds.
Two authored real-Git histories reproduce the original wrong selected commit
and falsely qualified early delivery.92branch/provenance/CLI cases pass;
42independent checks cover exact identities at year1/pre1970/year9999/timezone
and half-open boundaries. The isolated30case coverage run is79%; the original
unisolated90% report is explicitly unqualified. No new provider/DORA claims.
Evidence: `work/branch-semantics16/qualification.json`,
`work/runtime-review7/branch-semantics16/verification.json`. ID:M8-03.

## Resources and still-open acceptance

One heavyweight job and at most two product-code writers were enforced. The
earlier index273-test wrapper failed its original32MiB allocation gate despite
passing assertions; it remains failed. Full inode accounting measured directory
overhead omitted by that original wrapper.820completed identical fixture
databases were preserved through checked reversible sharing, with pre-mutation
metadata journals and independent restore proof. Restore before mutating those
old fixture paths. Each subsequent phase uses inclusive unique inode accounting
and a32MiB new-phase limit; aggregate retained index evidence128MiB and global
4GiB reserve are explicit prospective execution limits, not product acceptance.
See `work/storage-preservation/result-index14-fixture-databases/`.

Current source API is newer than wheel107243. Fresh coherent candidate bytes,
installed native/wheel/VSIX/client/editor agreement, whole-root integration,
100K-file tiers, full Git-history indexing, aggregate cache retention, hard
whole-process bounds and the remaining full M0–M9/P0–P14 scope remain open.
Original corpus reports retain partial/context limitations. Windows/macOS
platform access and consenting-human usefulness outcomes remain externally
blocked. No publication or outreach is authorized. The exact strict verifier
command/result and all unresolved IDs are recorded under
`work/delivery-verification/20261117-query16/` after this metadata update.

Strict final command actually run at2026-11-17T06:20:09Z:
` .venv/bin/python scripts/verify_delivery.py --require-complete ` → exit3,
complete=false,120open/65active/2blocked,187items; exact current IDs bystate and
unchanged definitionSHA are in
`work/delivery-verification/20261117-query16/check.json`.
