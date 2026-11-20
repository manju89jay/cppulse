# Interrupted owned-container lifecycle repair

Snapshot UTC: 2026-11-17T03:50:51.554152+00:00. Same HEAD `6f8b662a89b367f8c6883298dc97950150d7ba4f` and checkout; all changes uncommitted. All187 IDs/P0–P14 remain, canonical120 open/65 active/2 blocked unchanged.

## Actual trigger and repair

The earlier installed-runtime11 resource stop interrupted a real Docker create client. The immediate cleanup probe observed absence, but the daemon later published a stopped owned container. Exact ownership was verified before manual removal. Original failure, command intents, raw streams and cleanup receipt remain; a later passing retry does not replace them.

The controller now retains cancelled command receipts and raw bytes already observed by its default executor. Exit and full drain counts remain unknown on interruption; captured counts are explicitly limited to retained bytes. Injected exceptions without a receipt produce a clearly labelled diagnostic, rather than pretending it is original client stderr. Durable local name/nonce/image cleanup selectors are written before attempts; selectors alone do not prove creation or ownership.

During cleanup of an interrupted create with no observed immutable ID, only failed empty-array absence observations are retried (at most four probes). The existing independent eight-second cleanup scheduling budget and32command cap remain. A foreign identity, malformed inspect result or later interruption does not authorize removal. Native results/output stay unknown or unqualified as appropriate; client cancellation never implies the daemon stopped.

Source: `python/cppulse/frozen_container.py` SHA `99ab816f97a59033ed3c64f9fefd12d6b7bb64c8df5e1861f85f18481e7fdc9b`. New regression tests: `tests/test_frozen_interruption12.py`. Six meaningful red controls are retained in `work/frozen-interruption12/red.json` and `stream-red.json`. Fresh ordinary production-import owner checks:65passed,93% component statement coverage, actualexit0/stable (`live.json`, `live-coverage.json`). Independent LIVE checks:69passed, actualexit0/stable/noinjection (`work/runtime-review7/frozen-interruption12-live/verification.json`).

## Actual controlled SIGINT

An owned test parent observed its immediate Docker-create child by PPid plus exact argv, then sent SIGINT only to its Python observer. The real create receipt is cancelled with unknown exit; two subsequent failed empty-array inspect observations precede a successful exact name/nonce/image/immutable-ID/stopped-state observation. Only then does removal by immutable ID succeed. There is no start command, native exit or qualified output. The returned status is unknown, cleanup removed, cache/execution readiness false.

All six actual client receipts and raw stdout/stderr remain in `work/frozen-interruption12/actual-cancel-retry2/observation`. Signal and parent records are under `actual-controller-retry2`. The heavyweight record `work/heavyweight-jobs/frozen-interruption12-actual-retry2/record.json` has actualexit0, stable input hashes, no resource stop and minimumfree4,486,000,640B. Independent raw evidence review passed27checks: `work/runtime-review7/frozen-interruption12-actual/verification.json`. Raw PPid contents were not retained, so this is not PID authentication.

The first signal harness used the kernel-unavailable `/proc/PID/task/PID/children` interface and never signalled. Its ordinary actual native run completed with owned cleanup, while its signal assertion failed. That harness failure remains separate and is not a product cancellation failure or interruption pass. The retry uses immediate-child PPid inspection and records the actual selected child argv.

Late daemon completion outside the bounded cleanup window still returns unresolved/unknown. No universal timing guarantee, hostile-native protection, aggregatecgroups, loader closure, cache reuse or whole M2/P14 acceptance is claimed. The previous installedwheel107243 predates branch64a and this controller99ab change.

## Ownership validation and storage preservation

The execution-board validator originally counted owners but missed conflicting exact/directory claims. Independent controls also exposed parent-path aliases, intersecting wildcard claims and the workspace-root dot claim. Active writes now require canonical concrete relative file/directory claims; broad ownership globs are rights, not concurrent write scopes. Ten owner adversarial controls and13 independent controls pass, all187 IDs/79 bundles retained, no cycles or active ownership overlap. Relevant proof: `work/execution-ownership12` and `work/runtime-review7/frozen-interruption12/ownership-final-verification.json`.

One reviewer report was accidentally overwritten during a rerun. The exact previous validator SHA was reconstructed and replayed; this is explicitly a replay, not the preserved original report. `overwrite-disclosure.md` and `ownership-root-dot-replay-verification.json` record that limitation. Original first alias/glob red evidence remains. Final evidence now uses unique phase filenames.

Additional resource headroom came from sharing one exact-byte completed protobuf report with its retained raw copy. Both paths, bytes and modes remain. The target's original mtime differs from its anchor; original metadata was fsynced to the journal before replacement, and `work/storage-preservation/protobuf-retained-copy12/restore.py` restores an independent exact-byte copy and original metadata before future mutation.218,353,664 estimated blockbytes reclaimed; the original retained RunStore still verifies (`store-verification.json`). No current source, project input, log or producer output was removed.

## Next required checks

Full strict acceptance remains incomplete. Continue producer contracts → producers → consumers → presentation → orchestration → integration. Runtime/cache closure, scale/indexing and the remaining retained features still need applicable source/artifact-bound acceptance. ENV-MATRIX/HUMAN-USEFULNESS remain explicit external blockers; independent work continues. No commit/push/remote-ref change/publication occurred.

## Current strict verifier

`.venv/bin/python scripts/verify_delivery.py --require-complete` exited 3 at 2026-11-17T03:51:05.202018+00:00. Actual command/exit, all187 IDs/states, HEAD and unchanged definition SHA are in `work/delivery-verification/20261117-interruption12/check.json`. Nonzero means the full program remains incomplete.
