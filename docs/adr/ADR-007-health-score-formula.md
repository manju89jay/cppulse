# ADR-007: Density-Based, Weight-Normalized Health Score

**Date:** 2026-06-12
**Status:** Accepted
**Deciders:** Manjunath Jayaramaiah

---

## Context
The original health score was computed as `100 − (Σ weighted findings ÷ file
count)`. An internal audit of the showcase leaderboard exposed two problems:

1. **Doc/code divergence.** README and architecture.md documented a per-KLOC,
   weight-normalized penalty model; the implementation normalized by *file
   count* and never divided by the weight sum. Three conflicting definitions
   of the project's headline number existed simultaneously.
2. **Size bias.** Normalizing by file count makes the score a function of file
   granularity and repository size: a 964K-LOC repository (gRPC) scored 99.0
   while 54K-LOC fmt scored 60.9, largely because findings dilute across more
   files — not because of code quality. A score that rewards being big is not
   auditable and fails the smell test for safety-critical buyers, where every
   reported number must be traceable and defensible.

A defensible score must be (a) implemented exactly as documented, (b)
independent of repository size and file layout, and (c) deterministic: same
inputs, same score.

## Decision
Implement the documented density model in `predictor/src/health_scorer.py`:

```
density_cat  = findings_cat / KLOC          (KLOC from findings.json metadata.total_loc)
penalty_cat  = min(1.0, density_cat / cap_cat)
category     = (1 − penalty_cat) × 100
overall      = (1 − Σ(penalty_cat × w_cat) / Σ w_cat) × 100
```

Weights are unchanged (memory safety 3.0, MISRA 2.5 on the safety-critical
profile, complexity 1.5, modernization 1.0). The **cap** is the density at
which a category is considered fully degraded (category score 0):

| Category | Cap (findings/KLOC) | Rationale |
|---|---|---|
| memory_safety | 5 | Raw new/delete and unsafe arrays are rare in healthy code; 5/KLOC means systematic manual memory management. |
| misra_compliance | 10 | MISRA violations cluster; 10/KLOC indicates no MISRA intent at all. |
| complexity | 10 | At 10 threshold violations/KLOC, most functions breach limits. |
| modernization | 50 | Pre-C++11 idioms are pervasive in legacy code; 50/KLOC ≈ fully legacy. |

Caps are v2 calibration constants — deliberately conservative round numbers,
documented here so any change is an ADR-visible recalibration, not a silent
re-tune. The scorer contains no randomness and no repo-size terms; identical
`findings.json` inputs always produce the identical score.

## Consequences

### Positive
- Score is size-independent: 10 findings in 10 KLOC scores the same as 100
  findings in 100 KLOC (regression-tested).
- Single source of truth: README, architecture.md, and code state the same
  equations; the showcase leaderboard is regenerated from this formula.
- Auditable: per-category penalties are reportable as score → category →
  rule → file:line evidence.

### Negative
- All showcase scores change; historical score comparisons across cppulse
  versions are invalid (the leaderboard is regenerated, not patched).
- Cap choices are judgment calls. They saturate: beyond the cap, additional
  findings in that category no longer lower the score.

### Neutral
- Category scores replace the previous ad-hoc scale constants (15/10/5/12)
  with the same cap mechanism used by the overall score.

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Keep per-file average, fix only the docs | Leaves the size bias: score remains a function of file granularity; gRPC-vs-fmt anomaly persists. |
| Logistic/asymptotic penalty curve instead of linear-with-cap | Harder to explain in an audit; linear-to-cap is fully traceable mentally from the table above. |
| Percentile ranking against a benchmark corpus | Requires maintaining a reference corpus; score would change when the corpus changes — not deterministic from the repo's own inputs. |
