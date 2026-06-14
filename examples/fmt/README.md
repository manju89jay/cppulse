# cppulse Report: {fmt}

> Analyzed 2026-06-14 · 54,448 LOC · 70 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

{fmt} is Victor Zverovich's type-safe formatting library that became the direct basis for std::format in C++20. Widely deployed across game engines, embedded systems, and cloud infrastructure, fmt is valued for both its ergonomics and its near-zero runtime overhead.
cppulse scores it at 34.7/100 — reflecting strong memory safety (63.6), complexity (0.0), modernization (0.0).

---

## Health Score

<p>
  <img src="../../assets/fmt/health-gauge.svg" alt="Health Score: 34.7/100" width="280" />
  <img src="../../assets/fmt/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **63.6** | 99 | Raw `new` (86), explicit `delete` (12), C-style array params (1) |
| Complexity | **0.0** | 2,308 | long functions (2110), high cyclomatic complexity (190), too many params (8) |
| Modernization | **0.0** | 4,559 | raw string literal (3097), C-style casts (711), unscoped `enum` (326) |

**Total: 6,966 findings across 14 of 15 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `include/fmt/ostream.h` | 98.6% | Critical | Multiple minor findings |
| `include/fmt/args.h` | 98.6% | Critical | Multiple minor findings |
| `include/fmt/os.h` | 98.6% | Critical | Multiple minor findings |
| `src/fmt.cc` | 98.6% | Critical | Multiple minor findings |
| `test/format-test.cc` | 98.6% | Critical | Multiple minor findings |
| `test/ranges-test.cc` | 98.6% | Critical | Multiple minor findings |
| `include/fmt/base.h` | 98.6% | Critical | Multiple minor findings |
| `include/fmt/chrono.h` | 98.6% | Critical | Multiple minor findings |
| `include/fmt/color.h` | 98.6% | Critical | Multiple minor findings |
| `include/fmt/compile.h` | 98.6% | Critical | Multiple minor findings |

**28 files** flagged Critical · **3 files** flagged Medium · **81 files** flagged Low risk (of 112 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `src/format.cc` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 2 | `test/no-builtin-types-test.cc` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 3 | `include/fmt/ostream.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 4 | `D:\repo\cppulse\.showcase-repos\fmt\include\fmt\args.h` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 366h | 6.0 |
| 5 | `D:\repo\cppulse\.showcase-repos\fmt\include\fmt\base.h` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 222h | 6.0 |
| 6 | `D:\repo\cppulse\.showcase-repos\fmt\include\fmt\chrono.h` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 615h | 6.0 |
| 7 | `D:\repo\cppulse\.showcase-repos\fmt\include\fmt\color.h` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 423h | 6.0 |
| 8 | `D:\repo\cppulse\.showcase-repos\fmt\include\fmt\compile.h` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 372h | 6.0 |
| 9 | `D:\repo\cppulse\.showcase-repos\fmt\include\fmt\core.h` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 222h | 6.0 |
| 10 | `D:\repo\cppulse\.showcase-repos\fmt\include\fmt\format-inl.h` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 384h | 6.0 |

**Total: 117 roadmap items · ~12047 estimated hours**

## Downloads

- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
