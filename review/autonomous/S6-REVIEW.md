# S6 technical review — accepted native scope

This record covers the exercised local Linux verification/applicability slice.
All final gates below pass. All project edits remain uncommitted. No
publication, GitHub write or human validation is implied.

## Completed boundaries

- Versioned coverage, sanitizer, external-diagnostic, distribution, consumer and
  transfer contracts; explicit evaluator profile 1.1 while absent/1.0 retains
  the original four-predicate meaning. The first contract foundation passed 969
  related tests; later consumer shared corrections passed 618 related tests.
- Actual GCC 14.2/gcovr 8.8/CTest coverage: LCOV line 5/8, branch 1/2, function
  2/3; Cobertura line 5/8 and branch 1/2, function unavailable. Producer 46
  focused tests, 221 related tests and independent actual cwd counterprobes
  pass. No report union, percentage averaging, decision/MC/DC inference or
  positive report after failed process ancestry.
- Sanitizer producer and independent gates each pass 77 tests without skips,
  combined producer coverage 88%; final related producer gate 305 passes.
  Actual twelve-case matrix: three passed, four failed, five unsupported. All
  24 original/derived snapshots verify. Recovering UBSan reports failure even
  though CTest exits zero; actual TSan clean/race cases pass/fail on this host.
- Four actual sanitizer false clean classes reproduced and closed: CTest
  definition changes, automatic custom-file reporting suppression, compile cwd
  substitution and source-defined default suppressions. Known custom runtime
  hooks remain unsupported; selected callsites are not every access or path.
- GNU JSON compiler diagnostics: 34 focused tests, 95% combined coverage and
  151 related tests. Actual warning/clean/error commands retain one/zero/one
  occurrences and their real process results. All external facts remain
  imported with unverified scan completeness, including empty reports.
- Transfer: 36 producer and 18 contract tests, 203 related tests; actual R5
  two-root export/reopen/copy retains 606 files and 29,082,356 bytes. Original
  source namespaces and unauthenticated import labels remain separate. No
  archive extraction, commands or local-current pointer promotion.
- Independent consumer comparison review closes wrong-subject usage borrowing
  and distribution-mismatch schema failures; 27 independent tests pass.
- Read-only policy integration over checked actual snapshot pins passes all 16
  selected sanitizer/LCOV/Cobertura cases. No commands or run publication occur
  in this reassessment, and current workspace freshness is not claimed.

## Retained evidence

| Evidence | Path |
|---|---|
| Coverage execution and exact normalized pins | output/coverage-demo/latest-demo.json |
| Sanitizer final actual matrix | output/sanitizer-demo/batches/d0bce04348cf4ad1aff07495d1451550/summary.json |
| Sanitizer checked original/derived pins | review/autonomous/artifacts/s6-sanitizers-verified.json |
| Independent sanitizer acceptance | review/autonomous/s6-sanitizer-independent-review.json |
| External diagnostics actual batch | output/gcc-diagnostics-demo/batches/f2b8122c0eba454ab325296cddfcef2a/summary.json |
| Pinned actual policy reassessments, final engine SHA | review/autonomous/artifacts/s6-policy-pinned-assessments-final.json |
| Transfer actual artifact | review/autonomous/artifacts/s6-transfer-actual-r5/4320d00c347d4622a3b809df6fe52fdc/summary.json |
| Fresh pinned consumer proof inventory | review/autonomous/artifacts/s6-consumer-verification.json |
| Parent consumer pin/transfer verification | review/autonomous/artifacts/s6-consumer-parent-verification.json |
| Final shared results | review/autonomous/logs/s6-accepted-shared/check-results.json |
| Shared count/source SHA summary | review/autonomous/s6-shared-summary.json |
| Check commands and original failures | review/autonomous/logs/s6-*.log |

## Final gates and acceptance

The final shared runner passes all 15 checks: root 1,618; analyzer 84; CLI 20;
Git miner 90; predictor 98; report engine 95; dashboard 37. Total **2,042 tests**
and the production dashboard build. The previous complete shared run passed
before the last mixed-scope policy correction; it remains retained separately
and is not used as final acceptance. The final run includes that correction
and public invalid-profile regressions. Fourteen dependency deprecation notices
are retained in the root log; no tests are skipped.

The policy producer passes 661 related checks and an isolated independent
130-test engine gate at 96% coverage. The valid mixed-source named-fact case
now returns unknown/incomplete while retaining both raw fact references; the
assessment guard was not weakened. All twelve pinned actual sanitizer cases
and sixteen combined pinned policy cases pass their expected outcomes.

The consumer producer passes 86 tests at 82% coverage, plus 27 independent
comparison tests and original counterprobes. The **fresh default** consumer
command rebuilds the pinned packages (`package_reused: false`) and runs five
scenarios: compatible/local pass; compatible/missing application test; C++20
configuration mismatch/local pass; observed synthetic no-exceptions compile
failure with unknown usage; changed package incompatibility/local pass. A
separate selected UTF header self-containment case runs. Six-root transfer
reopens and verifies 738 payload files and 14,777,357 bytes; import authenticity
remains unverified. Parent review rechecks final comparison pins and labels.

HEAD is b89dce9d22b37ef44843a68eb3373c525b4b8e94 on the requested branch; refs
match the original snapshot exactly (`s6-refs.txt`). Accepted for this exercised
native scope; proceed to S7 contracts before dependent public workflows.

Docker/Compose is unavailable and unexecuted. Native checks do not qualify the
Docker images, other compiler versions, Windows or macOS. Dynamic runtime
closure/authenticity, whole-program instrumentation, representative detector
accuracy and product usefulness are not established. Ranking stays experimental.
S7 public CLI/presentation implementation remains subsequent work at this gate.
