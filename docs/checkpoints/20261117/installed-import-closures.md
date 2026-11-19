# Installed external and test-result import closures

UTC checkpoint: 2026-11-17T11:44:50.856937+00:00. HEAD `6f8b662a89b367f8c6883298dc97950150d7ba4f`, branch `codex/cppulse-local-core-20261114`. All changes remain uncommitted. Full production authorization continues; no stop-after-batch limit, commits, pushes or publication.

## Accepted original criteria

**FR-EVD-01**: Import CTest/JUnit results and coverage reports, initially LCOV and Cobertura. Preserve test counts, failed/skipped cases, covered/total counts, measurement type, and context.

The existing evidence contract now retains imported `test_counts`, occurrence-qualified `test_cases` and the versioned `import_adapter`. The public `collect` workflow accepts `test_import` without asserting an execution receipt. Counts/case algebra, exact occurrence identities, scope and context are checked. Unsupported or malformed results retain unavailable counts, and zero test cases remain skipped. JSON and HTML reports expose these attributed outcomes without turning them into executed passing tests.

Six genuine producer reports are qualified with current installed code: CTest3.31.6 clean, failed, skipped, disabled and zero; pytest8.0.0 total3/pass1/fail1/skip1. The deliberate pytest failure has raw producer exit1 and is not counted as a successful product test. CTest skipped/disabled classifications remain distinct from LastTest footer text. Raw XML and original logs remain retained. Matching real GCC14/gcovr8.8 coverage evidence is freshly normalized and publicly assessed/reported: LCOV line5/8, branch1/2, function2/3; Cobertura line5/8, branch1/2, function unavailable. Method/type/context and covered/total counts remain separate.

**FR-ANA-09**: Support normalized findings from external analyzers through adapters. Keep imported diagnostic identifiers and distinguish overlapping findings from independent confirmation.

| Provider | Qualified version / format | Actual normalized occurrences |
| --- | --- | --- |
| GNU-G++ |14.2.0 JSON|one primary warning plus one supplemental note|
| clang-tidy |19.1.7 text diagnostics|two primary diagnostics; secondary notes raw-retained|
| Cppcheck |2.17.1 XML2|four primary diagnostics; callstack raw-retained|

New bounded pure parsers and the public `external_import` normalizer retain namespaces, original supplied option/check/XML IDs, report artifacts and imported producer claims. A snapshot-view relationship projection distinguishes repeated diagnostics from potential same-context/file/line overlaps. It retains every occurrence, sets independent_confirmation=false and confidence_adjustment=0, and validates the derived projection against raw facts. HTML shows these limits. Same-line proximity is not proof of equivalent defects or independent producers.

GCC supplies `-Wuninitialized` on the actual primary warning, preserved verbatim. Its actual child note has no option ID; the existing `diagnostic-note` fallback is a derived kind label, not a supplied original ID, second primary warning or independent confirmation. The raw child and absence of an option remain preserved. Hashes bind bytes, not producer authenticity. No adapter claims a completed clean scan from an empty report. Other versions/formats require separately qualified profiles; unknown formats do not become clean results.

## Exact candidate and evidence

Wheel SHA256: `f294761379f5750727897ae100fe74d2077c0d4c669317797711c7dabc3f6e72`. All228 installed payloads equal the wheel and frozen source bytes. Source/package/test freeze has234 inputs. Native archive SHA256 `96bee81401f068c45c4b0329f551e0f30b15c553140a49666085ccca5d01c19d`; installed native analyzer remains5f7a130b5871c5a25307304d50542babeaf84e52cbdfeddbba97e149ff1c7b9d. Dependencies are preinstalled/shared explicitly; this is not a fresh optional-extras/platform/editor qualification.

- Original source-bound proof: `work/closure-evd-ana/verification.json`.
- Candidate/build/install identity: `work/closure-evd-ana/candidate.json`. Build staging is separate; no prior build artifact was replaced.
- Actual raw provider commands/versions/exits: `work/closure-evd-ana/actual-analyzers-retry2/receipt.json`. Local tool extraction/config setup failures remain retained.
- Public import commands: `work/closure-evd-ana/public-installed-retry4/commands.json`; pass summary and exact run/hash pins alongside.
- Current prior-three refresh: `work/closure-evd-ana/prior-refresh/results.json`; positive preinstalled offline pack: `work/closure-evd-ana/positive-preinstalled-pack/verification.json`.
- Independent acceptance: `work/runtime-review7/closure-evd-ana/review.json`,2,907read-only assertions, source/artifact pins unchanged.
- Affected component gate:409pass/11skip. The11live-tool skips are not claimed as new producer execution; retained genuine producers are freshly parsed with installed code. Parser gate87pass,93%isolated coverage. Counts alone are not acceptance.

Public collection/report commands exit0 on supported attributed imports. Imported tests remain insufficient evidence for executed verification (assessment3). Unknown/malformed/version controls retain partial/unavailable3; unrecognized adapter configuration exits2 before creating a store. Expected nonzero controls and harness errors are retained.

## Usable installed output

This read-only invocation renders the exact qualified imported results without changing any fixture or store:

```sh
PYTHONPATH=/workspace/cppulse/work/closure-evd-ana/installed \
  /workspace/cppulse/work/closure-evd-ana/installed/bin/cppulse report \
  --input /workspace/cppulse/work/closure-evd-ana/public-installed-retry4/positive-store \
  --evidence --run-id e7ed427eb19e461b9aef8923b0024b49 \
  --manifest-sha256 8430a3249e4b4ed3d7690662ddf174fc46c81e315510f8b4c865e73c10d6d80e \
  --format html --output /tmp/cppulse-qualified-imports.html
```

Full authoring examples and all role/context selections are in the recorded positive request. Use a fresh workspace/output for collection; retained fixtures are acceptance inputs.

## Ledger and continuation

Only FR-EVD-01 and FR-ANA-09 gain verified state. FR-UX-12, FR-EVD-09 and FR-GIT-03 keep verified state with refreshed current installed consumer evidence. Their original artifacts and reviews remain archived unchanged. Other182rows are unchanged; all187 definitions retain SHA256 `e57e89fb7db188f1f4805b95c0bc6f2896c7ab9eef15d851723cc422a0bd2381` and P0–P14. No broader M5/M6 task is closed from these narrower criteria.

Before:3verified/118open/64active/2blocked. After:5verified/116open/64active/2blocked. The unchanged strict verifier returns3, complete=false. Actual command/result/IDs are in `work/closure-evd-ana/require-complete-record.json`. This accepts evidence structure, not full production delivery.

FR-EVD-03 is now executing as the next locally-ready requirement in disjoint artifact paths; the critical bounded native-ingestion prerequisite remains lead-owned. All remaining tasks/obligations stay retained. No original MemoryError, skipped case or external platform/human blocker is erased.
