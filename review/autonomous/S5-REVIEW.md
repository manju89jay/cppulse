# S5 policy assessment technical review

Accepted for the exercised Linux/POSIX native-analysis and CTest slice. The pure
four-predicate evaluator, typed native normalization, six-case integration and
fresh core-only installed proof passed. This is a technical review of an
unpublished development candidate, not a production, usefulness or safety claim.
Public collection/assessment commands and evidence presentation remain S7 work.

## Retained evidence

| Check | Actual result | Evidence |
| --- | --- | --- |
| Native parse trace prerequisite | 84 CTests passed; actual ordered arguments, process cwd and parser version retained | logs/s5-native-trace-tests.log; artifacts/s5-native-trace-smoke/findings.json |
| Pure four-predicate evaluator and policy data | 78 tests passed, reported coverage 95%; broad related gate 893 passed | logs/s5-policy-tests.log; logs/s5-policy-full-gate.log |
| Four original evaluator counterexamples | Reproduced before fixes, independently confirmed corrected | logs/s5-policy-review-reproductions.log; logs/s5-independent-policy-probes.log |
| Interim parent root suite | 858 passed, before subsequent typed producer/property additions | logs/s5-pre-normalizer-root/check-results.json |
| Typed execution-facts producer | 88 collection/execution tests passed | logs/s5-typed-producer-tests.log |
| Repaired typed contracts | 239 focused and 729 related tests passed; seven original invalid cases rejected independently | logs/s5-contract-prerequisite-gate.log; logs/s5-independent-contract-probes.log |
| Native normalization and publication | 35 focused tests passed, 86% coverage, including seven independent regressions; related gate 552 passed | logs/s5-analysis-tests.log; logs/s5-analysis-integrated.log |
| Gate properties | 256 bounded exhaustive cases passed | logs/s5-policy-properties.log |
| Internal C++ test/context slice | Retained clean, failed-test, failed-build and missing-report assessments; not the complete installed R5 proof | artifacts/s5-test-context-slice/summary.json |
| Six-case actual C++ integration | Collection, normalization and assessment verified; all 18 original/derived snapshots SHA-pinned | output/policy-demo/latest-demo.json; logs/s5-demo-policy-config-identity.log |
| Component-installation regression | Missing YAML pin corrected; predictor 98 tests passed, 89% combined coverage; nine host source-layout checks passed | logs/docker-layout-source-audit.log; artifacts/docker-layout-source-audit/ |
| Complete shared runner | All 15 checks passed: 1,604 tests and dashboard production build | logs/s5-final-shared/check-results.json; s5-shared-summary.json |
| Exact installed core candidate | Fresh offline core-only venv and relocated native prefix reproduced all six expected gates | installed-s5/summary.json; logs/s5-installed-policy-final.log |

The property checks cover all four-state three-control combinations, permutation
and common-weight scaling, required failure/unknown precedence, monotonic
thresholds and resolving an unknown to a complete pass. They compare behavior
under transformations rather than implementing a second copy of the score
formula.

Parent commands run from the checkout root:

```sh
source review/environment.sh
python scripts/check_local.py --section root --output-dir review/autonomous/logs/s5-pre-normalizer-root
python -m pytest -v tests/test_policy_gate_properties.py
git diff --check
```

The complete shared runner used root1180/analyzer84/CLI20/Git90/predictor98/
report95/dashboard37 tests, plus formatting, generated-file checks and the
production build. Later isolated verification-launcher changes were separately
linted and exercised by the successful fresh installed run.

## Review findings and current boundary

The first evaluator review reproduced expired evidence, contradictory failed
test labels, floating-point overflow for valid large weights and an assessment
time preceding execution. Corrections preserve supplied raw facts while making
unavailable results unknown, computing exact gate arithmetic and enforcing
supplied timestamp causality.

The independent typed-contract review additionally retained counterexamples for
missing observed source inputs, unchanged reports, missing selected-resource
binding and invalid, unchanged, different-context or later-executing generated
database producers. Their original probes are in probes/s5-contract-originals.py
and logs/s5-independent-contract-probes.log. The final contract gate and exact
independent rerun now reject all seven original invalid cases while retaining
both valid baselines. Normalizer review then reproduced an output-directory
mismatch and an unsupported registry/version interpretation. Both were corrected
before the focused producer, independent regression and actual-data gates passed.

The initial minimum_analysis_coverage predicate is specifically analysis parse
coverage: matched, error-free file/job cells. It does not measure runtime line
coverage or selected-rule execution. Finding-limit positives independently need
complete consideration of the requested rules. A disabled rule may leave parse
coverage unchanged while making its finding limit unknown. Missing usable scope
remains incomplete; no absent job is replaced by its declaration.

## Actual outcomes and installed artifact

| Case | Gate | Relevant distinction |
| --- | --- | --- |
| Clean | passed | Selected source/rule/test/job requirements met |
| Intentional findings | failed | Test pass does not erase a selected-rule failure |
| Partial parse | failed | Parse-coverage requirement fails; finding/test evidence stays unknown |
| Disabled requested rule | insufficient_evidence | Parsing succeeds but cannot establish a zero for an unconsidered rule |
| Failed test | failed | Credible test failure remains a failure |
| Missing report | insufficient_evidence | Successful process without required report does not establish verification |

The 24 controls comprise 17 passed, 3 failed and 4 unknown. All six cases preserve
original facts and config identity through collection, normalization and
assessment. An integration failure first exposed a driver that changed
config_digest despite retaining the original effective collection plan; the
driver was corrected, the original failed log retained, and the same pinned
snapshots resumed without project commands or re-normalization. Changing only
the collection digest now rejects. Pure policy-only reassessment of the same
actual facts is retained in s5-policy-only-reassessment.json; it changes outcomes
under explicit requirements without changing observations or rebuilding ASTs.

Fresh candidate: output/candidates/s5-preview/cppulse-0.2.0.dev1-linux-x86_64-candidate.
Wheel SHA-256: 5abb2ca228e8be7ad387e7ab0f23e60264a4bb2d6d9554ccb336bf9e6c602a43.
Native archive SHA-256: 8acb99a62be545392d17691818411642bb6131560168dd9379f945e16869330b.
The frozen S3 dev0 candidate is preserved. Source-run collection versions remain
dev0; the later assessment runtime is recorded separately as dev1. The fresh
installed dev1 proof collected new facts under the actual installed version.

The successful installed evidence is outside the checkout at
/workspace/scratch/b3d4e6fff494/s5-installed-policy-final, with small summary
copies under installed-s5/. Core modules resolve inside its fresh venv; optional
ML/PDF/web modules and Node are absent. Original checkout files were present but
absent from Python import paths; S3's separate checkout-hidden proof is not
retroactively claimed for this new run. The first installed attempt failed
because extracted host CMake/CTest lacked their loader path. The successful
retry uses explicit CMake/CTest-only launchers with the selected host library
directory; Python and native analyzer discovery retain clean loader settings.
Both attempts and exact command transcripts are retained.

The six-case source collection has a clean input, intentional findings,
partial parsing, a disabled requested rule, a failed test and a missing test
report. All native commands used an actual compilation database and retained
241 selected Clang resource files per case. The source inventory and native
binding are verified. Five collections completed; the missing-report attempt
is partial. Collection completion remains separate from the policy outcomes.

Docker is still unavailable. Linux/POSIX support is qualified only by the
exercised versions and cases; hashes are integrity checks, not authentication.
All project edits remain uncommitted. No publication or remote writes are
authorized or performed.

The first six-case producer batch is retained as collection-only. The current
batch additionally pins original manifest SHA values at publication and rejects
ID-only resume if those manifest bytes change. Its pointer summary distinguishes
the last original completed collection from a later completed derived snapshot.
See logs/s5-demo-policy-resume-reproduction.log and
logs/s5-demo-policy-pinned-snapshots.log.
