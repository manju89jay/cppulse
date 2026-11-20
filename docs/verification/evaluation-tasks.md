# Maintainer and consumer evaluation tasks

Status: prepared for the first evidence-capable candidate. No human evaluation,
outreach, adoption measurement or usability improvement is claimed. Technical
self-review and successful fixtures do not replace these sessions.

## Baseline to record first

Ask the participant to show how they currently reconcile build/test output,
coverage, sanitizer reports and supported configurations. Record elapsed setup
and decision time, commands, manual lookups, missing information and mistakes.
Use a project they are authorized to inspect; do not upload their source or
contact anyone automatically. Agree success thresholds only after observing
this baseline.

## Library maintainer

1. Follow the candidate's recorded installation instructions from an empty
   working directory. Explain which tools are required and which features are
   optional. Record any unanticipated dependency or path repair.
2. Collect the selected clean fixture, then assess its explicit policy. Find the
   actual binary, requested job, source scope and test report behind one passing
   control. Explain why a completed collection is different from a passed policy.
3. Inspect a real observed failure and a missing-evidence case. Identify the
   failure or missing material without reading implementation code. Compare the
   CLI, report and dashboard answers; record ambiguous language or disagreement.
4. Change a selected source/header, flag or binary after collection. Explain why
   the old evidence cannot establish a current pass and what must be recollected.
5. Create a finding baseline with a reason. Compare a line insertion, repeated
   finding and rename. Identify any unsupported comparison and distinguish a
   finding-regression result from an evidence-policy result.

## Application integrator

1. Open the transferred pinned library evidence. Identify its original source
   identity, selected package, configuration, unauthenticated origin and limits.
2. Compare a matching local package/application against the upstream matrix.
   Find the actual packaged header and archive member used by the compiler/linker.
3. Inspect the compatible case with a missing application workload. Explain which
   additional local check is required and why upstream compatibility does not
   replace it.
4. Inspect a changed package and a different C++ standard. Locate each mismatch
   and decide whether existing evidence applies to the selected configuration.
5. Inspect the intentionally seeded no-exceptions compile failure. Distinguish
   the actual compiler failure from unavailable package-use/test evidence, and
   avoid attributing the synthetic defect to fmt or utfcpp.

## Review record

| Measure | Record during the session |
|---|---|
| Installation | Time, failed commands, dependency/path repairs |
| Decision accuracy | Correct pass/fail/missing distinction against seeded facts |
| Evidence traceability | Time and manual steps to locate the original command/report |
| Applicability | Correct package/context/local-test explanation |
| Confusion | Exact misleading text, false alarms and missing use cases |
| Comparison to existing tools | Baseline and candidate timings plus qualitative comments |
| Outcome | Useful as scoped; needs a named correction; or scope should change |

Keep observations and participant feedback distinct from developer interpretation.
Any later release, marketplace listing or participant outreach requires its own
authorization. The current candidate remains local and unpublished.
