# Coverage and JUnit producer integration

Snapshot UTC: 2026-11-17T04:12:10.672177+00:00. Same HEAD `6f8b662a89b367f8c6883298dc97950150d7ba4f` and Cloud checkout; all changes uncommitted. All118requirements,60tasks,nineobligations,P0–P14 retained. Canonical120open/65active/2blocked unchanged; no whole requirement accepted here.

## Coverage source/consumer agreement

FR-EVD-01/09, M5-02, AC-09: LCOV hit-only zero summaries without found counts or explicit units could become invented0/0 denominators. Cobertura method-rate metadata could contradict aliased exact class line/branch units or repeat the same method line. Six genuine red cases were repaired while preserving explicit zero denominators, exact unit inventories and the distinction between line, branch and function-entry counts.

Independent review then found a real quadratic method validation loop. Its deterministic operation counter doubled class lines and methods from32to64 and observed1024to4096 line-field reads. Lead added a both-line-and-branch regression (2048to8192 red), replaced scans with per-class line maps and selected only each method's aliases. Independent current counts are32to32/64to64. Aliases never add duplicate class units; method rates do not invent function-entry measurements.

Current live parser SHA `f080cde77ab902c1e27068ba3e6dc646a9e24cc98aa52943399c613865bcd105`; new test SHA `270915734ea05c3bab838570b0a7c2c6f45cf2c14d756d8e6b45b6fcb718f17c`. All4live modules ran with no deselection: **103passed/22.83s,87% parser statement coverage**, actualexit0/source stable/no resource stop. This includes the originally deferred16MiB+1 sparse-file guard and actual GCC/gcovr/CTest normalization. Record: `work/heavyweight-jobs/coverage12-live/record.json`, raw log alongside.

Fresh independent ordinary LIVE imports passed **87tests**, including that sparse guard (zero allocated bodyblocks), and the additional method/measurement controls. Independent read-only actual-normalization audit passed **76assertions** over65retained artifacts/630,809B. It replayed only pure normalization with subprocess forbidden: LCOV line5/8, branch1/2, function2/3; Cobertura line5/8, branch1/2 with no invented function measurement. Exact source/manifest/receipts agree. Evidence: `work/runtime-review7/coverage-adapter12-live/verification.json` and `normalization-audit/retry-glob1/verification.json`.

Initial workcopy coverage-plugin name shadowing and audit glob-name failures were harness failures, retained separately; neither is a product red or substituted passing epoch. Pre-linear source/test/patch/qualification bytes remain in `work/coverage-adapter12/before-linear`.

## JUnit/CTest outcome agreement

FR-EVD-01/03, M5-02, AC-09: nested XML under skipped/failure/error outcome elements was silently ignored. A passing testcase plus skipped containing failure could yield usable/passed with no failure. Six genuine negatives now reject nested outcome structure atomically, rather than retaining misleading partial counts. Plain escaped text, CDATA, comments, repeated test occurrences and independent failed/error classifications retain their original meaning.

Current live adapter SHA `380a52a9e70447463db6a601790ea1d96762e3defa389b7c2cb3327f304f4396`; new tests SHA `4432f2f745bdae9932503b0925e9c217184c5977fe883be26efee1f6ff83569b`. Owner full component: **81passed/8.22s,97% statement coverage**, actualexit0/source stable/no resource stop. All11workcopy deferrals ran, including10actual CMake/CTest cases and the extra10MiB sparse log guard. Record: `work/heavyweight-jobs/junit13-live/record.json`.

Fresh independent LIVE verification passed **75tests**, no injection. It did not repeat10build-backed cases; **64read-only assertions** verify their retained XML, LastTest logs, source bytes and outcomes for clean/fail/skip/disabled/zero across both actual fixtures. Skipped JUnit classification remains distinct from the CTest text log's passed classification; neither becomes a successful required-test denominator. Evidence: `work/runtime-review7/junit-adapter13-live/verification.json` and `actual-artifact-audit/verification.json`.

## Scope and next producer gates

These are current finite declared-dialect source/actual-consumer checks, not universal provider/platform qualification or a new installed candidate. Wheel107243 predates branch64a, controller99ab and both parser changes. Broad root3646 predates even paging629. No older artifact/root proof is relabelled current.

Next source work is bounded JSON streaming plus a transactional selected-artifact query index for NFR-SCL-05/M2-05/FR-UX-08. Frozen JSON producer contract and index request contract have separate ownership and tests; consumer implementation waits for passing stable stream producer evidence. Contract tests or source scaffolding are not working indexed paging and do not close those requirements.

Full tasks section14/AC-01..16/P14 and strict require-complete remain required. All retained advanced/native/provider/team/language/maintenance/delivery scope stays present. ENV-MATRIX/HUMAN-USEFULNESS still require unavailable platform/participant evidence; independent authorized work continues. No commits/pushes/remote-ref changes/publication occurred.

## Recorded strict verifier

`.venv/bin/python scripts/verify_delivery.py --require-complete` exited 3 at 2026-11-17T04:12:10.747856+00:00. Exact command/exit, all187 IDs/states, HEAD and unchanged definition SHA are in `work/delivery-verification/20261117-adapters13/check.json`; raw stdout/stderr remain alongside it. Nonzero means incomplete.
