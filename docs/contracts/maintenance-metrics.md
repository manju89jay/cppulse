# Measured maintenance metrics and context health

Status: contracts under implementation. Source/schema presence is not evidence
that a metric producer, scorer, supported platform or useful result is complete.
Native and normalized producer gates precede scoring and presentation work.

## Source and context identities

Reuse `analysis_metrics` v2 and the existing closed source/run bundle. A metrics
document adds `analysis_inventory_id` and `job_context_id` when it contains the
`cppulse-metrics-1` profile. The former links to the native analysis receipt and
per-file outcomes. The latter identifies the declared build/consumer job.

Each metric's existing `context_id` identifies its actual libclang parse context.
It remains distinct from the job context: individual translation units have
different argv and include inputs within one build. Multiple translation-unit
parse identities must not become invented consumer configurations. An inferred
header command remains inferred even when its C API argv was directly observed.

Each item retains its file, symbol (USR or a documented fallback), metric/version,
units, value or null, availability and limitations. Function items add a source
`location` with line/column and end-line/end-column. Metric identities preserve
the source, declared job, actual parse context, file, symbol and method version.
Fallback symbol identities disclose their limited edit/rename stability.

## Initial measured profile

| Metric | Unit | Definition |
|---|---|---|
| `physical_loc` | lines | Actual source physical lines including comments and blanks; empty input is zero; a terminal newline creates no additional line. This is the initial density denominator. |
| `code_loc` | lines | Union of source-spelled, non-comment lexical-token lines. Multiline literal lines count. Includes directives and inactive preprocessor branches; it is neither executed nor active-configuration coverage. |
| `function_length` | lines | Inclusive source extent of a function definition; a template prefix is included. |
| `cyclomatic_complexity` | count | One base plus the declared semantic decision-counting convention. Short-circuit operators count once; nested callable bodies are separately measured; lambda capture initializers belong to the enclosing function. |
| `nesting_depth` | levels | Maximum declared control/conditional nesting within the callable, excluding nested callable bodies. An else-if is nested under this initial method. |
| `parameter_count` | parameters | Ordinary declared parameters; template parameters are separate, and a parameter pack is one declaration. |
| `duplicate_tokens` | tokens | Actual matched source-token occurrences under a separately documented and executed duplication algorithm. Until that producer exists, the value is unavailable, never fabricated zero. |
| `duplicate_lines` | lines | Actual source lines implicated by that duplication method. No textual similarity implies semantic equivalence. |

The first six metrics can be produced before duplication. Every claim names its
method version. The normalized contract rejects impossible units, negative or
fractional counts, duplicate metric cells, reversed source locations and code
LOC above physical LOC. Unavailable values are null with an explicit limitation.
Partial AST measurements cannot satisfy complete required health prerequisites.
The raw source/report retains credible partial observations for inspection.

The initial duplication consumer has a separate method identity,
`cppulse-exact-duplicates-30-v1`. It compares the exact `(kind, spelling)`
sequence of every contiguous thirty-token window in the retained native
`cppulse-spelled-tokens-1` streams. A window is duplicated only when it occurs
in another selected file, or at a non-overlapping position in the same file.
The result counts the union of implicated token occurrences and the union of
their physical source lines, including multiline tokens. Whitespace/comments
are absent from the native stream; identifiers and literal contents are not
renamed or normalized. Shorter matches and semantically similar code are not
reported. This is exact lexical duplication, not a semantic clone detector.

The declared comparison scope is one native inventory/job. If any applicable
selected file has an unavailable, incomplete or truncated stream, duplication
for that entire scope remains unavailable: a complete peer cannot receive a
fabricated zero merely because a possible matching peer was truncated. A
complete empty stream can legitimately report zero. Duplication counts use
the separate duplication metric version; the base metric profile continues
to reject unqualified available duplication values. These definitions and
synthetic tests precede producer execution and do not by themselves qualify it.

The native producer adds a versioned `metadata.analysis.native_metrics` payload.
Its per-file path/status/error count must agree with the ordinary parse inventory.
It contains measured LOC, function records, includes and a versioned lexical token
stream. Token record bounds are explicit: truncation remains visible and prevents
a claim of complete duplication analysis. Include paths alone do not establish
external dependency content identity or complete dependency closure.

## Authoritative health result

`maintenance_health` v2 is the authoritative calculation. A normalized risk
document can name its exact retained `maintenance_health_artifact_id`. Consumers
display the stored result instead of implementing their own scorer. Closed-bundle
validation resolves that artifact and source identity.

Initial method: `analyzed-kloc-context-v3`, scorer version `3.0.0`.
The scorer records its profile, metric version, `physical_loc` denominator,
`allow_inferred_parse`, category weights/caps and a canonical configuration digest.
It also pins required rule identities and versions. Default requires the 15
non-MISRA native checks; safety-critical requires all 22; a custom profile names
its narrower required set explicitly. Disabled, unrequested or unexecuted required
checks cannot become zero-finding category scores. Registry/threshold/configuration
changes require compatibility review before continuing a historical trend.
Changing any of those inputs changes the method identity. This method is distinct
from the historical attempted-file scorer; historical trends are not silently
rebaselined or made numerically comparable by renaming a field.

Historical constants are reused from cached `origin/main` at
`82120d26b51f99b64068f9d66f6e000fcaee97c2`:

| Category | Weight | Cap in findings per analyzed KLOC |
|---|---:|---:|
| Memory safety patterns | 3.0 | 5.0 |
| Complexity | 1.5 | 10.0 |
| Modernization | 1.0 | 50.0 |
| MISRA-inspired subset, when selected | 2.5 | 10.0 |

These are unvalidated calibration choices, not defect probabilities or complete
coding-standard coverage. The older scorer's empty-input health 100 and fake
one-line denominator are expressly not reused.

For each fully evaluated declared job context:

```text
KLOC = measured analyzed physical LOC / 1000
density(category) = finding count(category) / KLOC
penalty(category) = min(1, density(category) / cap(category))
category health = 100 × (1 − penalty(category))
overall = 100 × (1 − Σ(weight × penalty) / Σ(weight))
```

Raw counts, LOC, caps, weights, densities and penalties remain in the result.
Only display rounding is allowed; validation compares derived numeric values
against independent rational calculations within 1e-9. Policy acceptance is
separate and cannot be inferred from this maintenance number.

Each context records declared/analyzed/excluded file counts, physical/code LOC,
the supporting metric and analysis-inventory IDs, exact/inferred/fallback/none
parse counts, category calculations, availability and limitations. Scored scope
requires all applicable selected files, enabled requested rules and required
metric cells. Missing inventory, failed/partial/skipped source, zero LOC, absent
metrics or a missing required job context makes full health unavailable.

By default, `allow_inferred_parse=false`: inferred or fallback source parsing
cannot establish complete required context health. Explicit opt-in may permit
inferred arguments for maintenance only, with a limitation retained in the
result and the option included in the method digest. Fallback/unknown project
arguments remain unverified. No such option upgrades library consumer evidence.

Required and optional context identities remain separate. When all required
contexts are fully scored, the aggregate uses the lowest overall required-context
score and copies that context's category values; ties use the context ID's lexical
order. Optional contexts remain visible but do not hide a required gap. Missing
or incomplete required scope gives null overall/category scores and no selected
worst context. A fully applicable observed zero-violation context with nonzero
measured LOC can legitimately score 100.

Tests with hand-calculated synthetic contracts check the equations, prerequisites,
context grouping and deliberate contradictions. They are not native execution,
an accuracy benchmark, performance qualification or certification evidence.
