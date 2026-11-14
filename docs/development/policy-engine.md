# Scoped policy evaluation

The policy evaluator answers a limited question: do the supplied facts satisfy the explicitly selected local policy? It does not collect evidence, execute a build, inspect project files or certify a product. Ranking remains experimental and is separate from policy assessment.

The default evaluator profile `1.0.0` supports four predicates: `finding_limit`, `minimum_analysis_coverage`, `test_outcomes` and `required_contexts`. The analysis predicates consume the gated typed native-analysis producer, not legacy zero-finding labels. Explicit profile `1.1.0` additionally supports typed `minimum_coverage` and `sanitizer_outcome`; it preserves the original four predicates. Generic metric thresholds and reviewed attestations remain unsupported evaluators, even when a descriptive schema can represent them. Stage acceptance still requires the actual complete pipeline and installed-candidate checks; unit fixtures alone are not that acceptance.

## Inputs and integration

Call the pure API with a policy object, a closed collection bundle and an explicit RFC3339 UTC generation time:

```python
from cppulse.policy import evaluate_policy

assessment = evaluate_policy(
    policy,
    documents,
    generated_at=recorded_utc_time,
    deviations=approval_requests,
)
```

`documents` maps each v2 contract kind to one document or a list of documents. It must contain one `run_manifest`. The caller reads a frozen run through `RunStore`, verifies artifact bytes, and supplies the contracted documents. The evaluator validates structural types, source/run/context identities and actual references. It reads immutable packaged schemas as code data and consumes no project filesystem, process, network, environment or wall-clock input.

Missing policy-expected evidence is unknown. An actual dangling reference, duplicate identity, contradictory contract or unsupported option is an error. The result includes the full canonical policy digest and an evaluator tag whose version matches `policy.evaluator_profile`. Omitting that policy field selects `1.0.0`; requesting `1.1.0` is explicit and changes the full policy identity. An older untagged descriptive assessment is not a result of this evaluator.

Generation time must not precede the selected run's finish or a referenced receipt's finish. It is a recorded assessment time, not an arbitrary historical query time. Explicit evidence expiry is checked at that instant; expiry never changes the retained raw evidence.

## Source scope and job roles

Policies select repository-relative POSIX paths and explicit nonempty job context IDs. Globs are case sensitive: `*` matches within a path component, `?` matches one non-slash character, and a complete `**` component matches zero or more directories. Exclusions win. Empty selected source scope cannot pass.

`policy.contexts` declares the job universe. `control.parameters.contexts` optionally narrows a test or analysis control to a nonempty subset; `required_contexts` always names its requested jobs. A test job and an analysis job can therefore have separate controls. Per-file observed libclang parse contexts are not automatically added to the requested job universe.

For a positive test result, every named evidence ID must be present and usable, and their union must cover every selected source file in every requested job. Skipped, erroneous, imported, stale, expired or mismatched results do not supply a positive execution result. A failed process label with no failed test cases is an operational inconsistency: the test control is unknown/incomplete, while the raw process outcome is preserved.

`required_contexts` checks observed scoped job presence, not job success. A usable observed build failure can establish that a job was exercised while a separate test control stays unknown or failed. Configuration labels alone cannot establish presence. A typed, source-bound matched native parse attempt also establishes analysis-job presence, including an observed partial/failed parse; it does not assert that the parse or detectors passed.

## Native analysis predicates

The native normalizer preserves the original job ID separately from per-file observed libclang parse contexts. Assessment selects jobs, then uses their typed file inventories, retained input/output links, exact registry/configuration/resource inputs and observed arguments. It does not reconstruct a compilation context from a label. Matching libclang inputs does not establish GCC/libclang semantic equivalence.

| Predicate | Positive result requires | Missing or incomplete facts |
| --- | --- | --- |
| `finding_limit` | Count is within the configured maximum, with every selected file/job cell's selected rules explicitly requested and executed under a matched, complete parse | Disabled/unrequested/unconsidered rules or missing/mismatched contexts remain unknown; no implicit zero |
| `minimum_analysis_coverage` | Known parse facts for every selected file/job cell and a sufficient percentage of matched, error-free completed parses | Missing/unusable cells remain unknown; an upper bound already below the threshold is a definite incomplete failure |

Finding counts use distinct observation IDs across selected jobs/rules/files. Equal fingerprints or identical parse-context definitions do not silently deduplicate observations across jobs. A matched partial AST can still contain a known above-limit observation count; that failure remains incomplete because full rule consideration was not established. Unverified/fallback-mode findings do not definitively fail the requested named job.

Analysis parse coverage has a denominator of selected source files multiplied by requested job IDs. A matched, error-free `analyzed` cell contributes one; known partial/failed/excluded/skipped or context-mismatched cells contribute zero. Unknown cells give an optimistic upper bound. If that bound is below the requested minimum the control fails with `incomplete=true`; otherwise missing scope stays unknown. A fully observed below-threshold matrix is a complete failure of an operational/scope requirement, not a source-defect assertion.

Parse coverage does not measure selected-rule consideration or runtime coverage. Disabling a detector can leave parse coverage at 100% while its finding-limit control remains unknown. A complete parse alone cannot prove that a disabled or unrequested rule found nothing.

Source binding must be verified for current outcomes. With unverified binding, both reported successes and reported failures become unknown; the raw reports remain referenced claims rather than current source results. Independent usable facts from a verified partial/cancelled collection can still contribute. Collection status and policy status are distinct.

## Typed runtime coverage

Profile `1.1.0` accepts `minimum_coverage` parameters `minimum`, `fact_ids`, `measurement_kind`, `method` and optional `contexts`. Fact IDs name retained `coverage_facts` documents; generic evidence labels or numeric metrics cannot substitute for them. The currently supported methods are LCOV line/branch/function (`lcov-da-v1`, `lcov-brda-v1`, `lcov-fnda-v1`) and Cobertura line/branch groups (`cobertura-lines-v1`, `cobertura-condition-counts-v1`). These methods are distinct; no decision or MC/DC coverage is inferred.

Every selected source file in every requested job must meet the exact `100 × covered / total` threshold. A highly covered file cannot compensate for a poorly covered file. Repeated facts for one file/job/method must contain identical full unit universes and counts; exact repeats are considered once. Conflicts, disjoint report shards, incompatible methods and zero denominators stay unknown. The evaluator does not choose the best report, average percentages, add aggregate branch groups or infer coverage unions.

Positive coverage requires current execution-origin usable typed facts linking source bytes, actual instrumented objects/mapping files, fresh runtime profiles, the linked/exercised binary, actual nonzero CTest execution and the generated report. Standalone LCOV/Cobertura imports preserve counts as claims and cannot pass this predicate. A test failure and observed coverage are separate facts; reporting coverage does not make a failed test pass.

Missing named facts, missing source/job cells and expired underlying test evidence keep the control incomplete even when an alternative fact covers the scope. An observed below-threshold cell remains failed with `incomplete=true` if another required cell is unknown. This prevents a deviation from waiving an incomplete failure. Output controls list only actual retained `fact_ids`; absent expected IDs are explained in the reason. Assessment generation time must follow every referenced typed proof receipt.

## Typed sanitizer outcomes

Profile `1.1.0` accepts `sanitizer_outcome` parameters `fact_ids`, `sanitizer` (`asan`, `ubsan` or `tsan`) and optional `contexts`. Each sanitizer is selected explicitly; a test job's label or `-fsanitize` flag alone is not proof. The accepted producer links actual source/compiler/object identities, observed emitted instrumentation callsites, the linked runtime/binary and the actual nonzero CTest invocation. It records instrumentation and runtime limits separately.

A clean result requires complete observed instrumentation for every selected file/job cell and the selected linked user components, plus a qualified exercised result without a recognized diagnostic. Uninstrumented or prebuilt gaps, substituted binaries, missing/zero/all-skipped tests, unsupported formats and runtime startup failures stay unknown. An unsupported ThreadSanitizer runtime cannot become either a clean pass or a reported data race.

A credible source-bound diagnostic for an actually exercised selected binary fails this control even when the process exits zero and ordinary tests pass. Recovering UBSan diagnostics demonstrate why `sanitizer_outcome` is separate from `test_outcomes`. A known diagnostic with an additional source/job/component gap remains failed and incomplete, so a deviation cannot waive the missing proof. Missing diagnostic ownership/instrumentation/execution proof itself cannot establish a definite current failure. Imported or expired reports remain referenced claims, not current sanitizer outcomes.

An explicitly named fact whose object proofs cover only unselected source files remains an incomplete scope mismatch, even when another clean fact covers the selected files. Its raw diagnostic is retained without becoming either a selected-source failure or a clean pass. This differs from a null/header/runtime diagnostic location within a fact that actually proves the selected binary/source scope; that qualified diagnostic is not filtered away by its reported filename.

These outcomes cover the finite selected inputs, supported runtime/format and exercised workloads. They do not prove every memory access was instrumented, absence of bugs, all runtime paths, or the authenticity and complete dependency closure of the loaded host runtime. The ordinary four predicates retain their prior meanings; sanitizer metadata is never silently converted into an ordinary test result.

## Outcomes and arithmetic

Each applicable control is passed, failed or unknown. Not-applicable is permitted only for the policy's explicit subject-kind mismatch; it contributes no weight. Missing data does not become not-applicable or zero findings.

Let `P`, `F` and `U` be the summed weights and `D = P + F + U`:

| Score | Formula | Meaning |
| --- | --- | --- |
| Readiness | `100 P / D` | Confirmed passed share of applicable control weight |
| Evidence completeness | `100 (P + F) / D` | Share with an observed control outcome |
| Observed satisfaction | `100 P / (P + F)` | Passed share of the observed outcomes |
| Maximum possible readiness | `100 (P + U) / D` | Optimistic bound if unknown controls later pass |

Zero denominators produce null scores. The engine uses exact fractions derived from JSON numbers for gate comparisons; displayed rounding cannot turn a threshold miss into a pass. Large whole-number masses remain exact JSON integers rather than overflowing intermediate float percentages.

A definite unexcepted required failure, or an optimistic bound below minimum readiness, fails the gate. Otherwise empty scope, zero applicable weight, required unknown/incomplete controls or unmet readiness/completeness thresholds produce insufficient evidence. The remaining cases pass. Optional unknown controls do not blanket-block a policy whose explicit thresholds are already guaranteed; the unknown weights remain visible.

A failed or unknown prerequisite blocks a dependent success. A direct definite failure remains failed. Unknown/incomplete prerequisites keep dependent results incomplete; a known complete prerequisite failure does not erase a separate known complete failure. An explicitly not-applicable prerequisite is neutral.

## Approval requests and examples

Approval requests never rewrite a control outcome or raw score. The only supported named exception gate is `required_controls`; threshold exceptions raise `UnsupportedVersion`. A control must explicitly allow deviations, be definitively failed and complete, and have an exact nonempty approval context scope. Source identity must match, approval must already be effective and expiry must be later than assessment time. Required unknowns and incomplete failures cannot be excepted.

The engine recomputes `active`; caller flags do not authorize an exception. Inactive approvals retain their original reason and receive an `inactive_reason`. Omitted named gates remain inactive for descriptive compatibility. Separate controls per context are needed for granular exceptions to an aggregate multi-job control.

Packaged examples live in `cppulse/data/policies/starter.json` and `organization-example.json`. They cover all four implemented predicates, require full readiness/completeness, and default to denying deviations. Replace job, evidence and selected-rule IDs with the chosen recipe/binding/registry IDs. The starter separates `build-debug` tests from `analysis-debug` analysis; the organization example uses two test jobs and a separate native-analysis job. Their source globs intentionally select C++ translation units rather than tool-resource/configuration inputs. Edit those globs for the project's intended files; header analysis needs explicitly bound parse contexts as well. Neither example maps to standards certification or production readiness.

`verification-example.json` explicitly selects profile `1.1.0`, separate coverage/ASan/UBSan/TSan job IDs, named typed fact IDs and an ordinary application-test check. Its 80% line threshold is an editable example requirement, not a recommended adequacy or safety threshold. Replace the placeholder fact/job/evidence IDs and source globs with the selected recipe's actual identities. It does not collect or infer missing measurements; unavailable required capabilities produce insufficient evidence.

Validation combines synthetic in-memory boundary cases with an actual selected C++ CMake/CTest collection snapshot. Raw fixtures and property tests do not establish prediction accuracy, global project coverage or safety assurance. See the fresh review logs for commands/results; Docker availability remains a separate environment limitation.
