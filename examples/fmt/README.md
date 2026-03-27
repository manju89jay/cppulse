# cppulse Report: {fmt}

> Analyzed 2026-03-27 · 54,000 LOC · 70 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

{fmt} is Victor Zverovich's type-safe formatting library that became the direct
basis for `std::format` in C++20. Widely deployed across game engines, embedded
systems, and cloud infrastructure, fmt is valued for both its ergonomics and its
near-zero runtime overhead. Despite its reputation for clean, modern C++, cppulse
flags a score of 17.2/100 — driven almost entirely by a blanket MISRA compliance
failure and zero-score modernization, both artifacts of the library's aggressive
use of template metaprogramming and variadic interfaces that are inherently
incompatible with MISRA C++'s strict subset rules.

---

## Health Score

<p>
  <img src="../../assets/fmt/health-gauge.svg" alt="Health Score: 17.2/100" width="280" />
  <img src="../../assets/fmt/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **57.3** | 168 | Raw `new` (2), explicit `delete` (1), C-style array params (1) |
| Complexity | **79.2** | 123 | High cyclomatic complexity (19), long functions (3), excess params (1) |
| Modernization | **0.0** | 1,478 | C-style casts (159), `auto` opportunities (100), `typedef` (36) |
| MISRA Compliance | **0.0** | 1,087 | Multiple returns (107), `union` usage (9), recursion (7) |

**Total: 2,856 findings across 18 of 22 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `include/fmt/args.h` | 99.2% | Critical | MISRA violations (34), memory issues (1), 119 total findings |
| `include/fmt/chrono.h` | 99.2% | Critical | MISRA violations (46), memory issues (1), 138 total findings |
| `include/fmt/ostream.h` | 99.2% | Critical | MISRA violations (46), memory issues (1), 138 total findings |
| `include/fmt/std.h` | 99.2% | Critical | MISRA violations (52), memory issues (1), 145 total findings |
| `include/fmt/xchar.h` | 99.2% | Critical | MISRA violations (50), memory issues (1), 148 total findings |
| `src/fmt.cc` | 99.2% | Critical | MISRA violations (12), memory issues (2), 14 total findings |
| `src/os.cc` | 99.2% | Critical | MISRA violations (12), memory issues (2), 14 total findings |
| `test/format-test.cc` | 99.2% | Critical | MISRA violations (41), memory issues (1), 70 total findings |
| `test/gtest-extra-test.cc` | 99.2% | Critical | MISRA violations (131), memory issues (2), 144 total findings |
| `test/gtest/gmock/gmock.h` | 99.2% | Critical | Memory issues (53), MISRA violations (43), 258 total findings |

**53 files** flagged Critical · **4 files** flagged Low risk (of 59 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `include/fmt/args.h` | Reduce cyclomatic complexity | complexity | 21h | 24.0 |
| 2 | `include/fmt/args.h` | Address MISRA C++ compliance violations | misra | 68h | 24.0 |
| 3 | `include/fmt/base.h` | Reduce cyclomatic complexity | complexity | 3h | 24.0 |
| 4 | `include/fmt/base.h` | Address MISRA C++ compliance violations | misra | 22h | 24.0 |
| 5 | `include/fmt/chrono.h` | Reduce cyclomatic complexity | complexity | 21h | 24.0 |
| 6 | `include/fmt/chrono.h` | Address MISRA C++ compliance violations | misra | 92h | 24.0 |
| 7 | `include/fmt/color.h` | Reduce cyclomatic complexity | complexity | 21h | 24.0 |
| 8 | `include/fmt/color.h` | Address MISRA C++ compliance violations | misra | 70h | 24.0 |
| 9 | `include/fmt/compile.h` | Reduce cyclomatic complexity | complexity | 21h | 24.0 |
| 10 | `include/fmt/compile.h` | Address MISRA C++ compliance violations | misra | 68h | 24.0 |

**Total: 132 roadmap items · ~4,693 estimated hours**

## Downloads

- [PDF Executive Report](report.pdf)
- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
