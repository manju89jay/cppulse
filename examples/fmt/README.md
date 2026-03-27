# cppulse Report: {fmt}

> Analyzed 2026-03-27 · 54,000 LOC · 70 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

{fmt} is Victor Zverovich's type-safe formatting library that became the direct
basis for `std::format` in C++20. Widely deployed across game engines, embedded
systems, and cloud infrastructure, fmt is valued for both its ergonomics and its
near-zero runtime overhead. With the default profile (MISRA excluded), cppulse
scores fmt at 60.9/100 — memory safety is strong at 94.0, complexity is solid
at 77.0, but modernization scores 0.0, reflecting the library's aggressive use
of template metaprogramming and variadic interfaces that accumulate C-style casts
and typedef-heavy patterns throughout the implementation.

---

## Health Score

<p>
  <img src="../../assets/fmt/health-gauge.svg" alt="Health Score: 60.9/100" width="280" />
  <img src="../../assets/fmt/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **94.0** | 168 | Raw `new` (2), explicit `delete` (1), C-style array params (1) |
| Complexity | **77.0** | 123 | High cyclomatic complexity (19), long functions (3), excess params (1) |
| Modernization | **0.0** | 1,478 | C-style casts (159), `auto` opportunities (100), `typedef` (36) |

**Total: 1,769 findings across 18 of 22 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `include/fmt/chrono.h` | 69.6% | High | Complexity findings (7), memory issues (1), 138 total findings |
| `include/fmt/args.h` | 63.2% | High | Memory issues (1), complexity findings (7), 119 total findings |
| `include/fmt/color.h` | 37.8% | Medium | Complexity findings (7), 121 total findings |
| `test/gtest/gtest/gtest.h` | 26.2% | Low | Memory issues (1), 2 total findings |
| `src/fmt.cc` | 26.1% | Low | Memory issues (1), 1 total findings |
| `include/fmt/base.h` | 9.96% | Low | Complexity findings (1), 40 total findings |
| `include/fmt/compile.h` | 7.66% | Low | 74 total findings |
| `include/fmt/format-inl.h` | 2.81% | Low | Complexity findings (1), 3 total findings |
| `include/fmt/fmt-c.h` | 0.10% | Low | 1 total findings |
| `test/gtest/gmock/gmock.h` | 0.10% | Low | 1 total findings |

**2 files** flagged High · **1 file** flagged Medium · **7 files** flagged Low risk (of 10 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `include/fmt/args.h` | Reduce cyclomatic complexity | complexity | 21h | 18.0 |
| 2 | `include/fmt/args.h` | Address MISRA C++ compliance violations | misra | 68h | 18.0 |
| 3 | `include/fmt/chrono.h` | Reduce cyclomatic complexity | complexity | 21h | 18.0 |
| 4 | `include/fmt/chrono.h` | Address MISRA C++ compliance violations | misra | 92h | 18.0 |
| 5 | `include/fmt/args.h` | Replace raw pointers with smart pointers | memory_safety | 4h | 12.0 |
| 6 | `include/fmt/args.h` | Modernize C++ code: apply C++11/14/17 idioms | modernization | 77h | 12.0 |
| 7 | `include/fmt/chrono.h` | Replace raw pointers with smart pointers | memory_safety | 4h | 12.0 |
| 8 | `include/fmt/chrono.h` | Modernize C++ code: apply C++11/14/17 idioms | modernization | 84h | 12.0 |
| 9 | `include/fmt/color.h` | Reduce cyclomatic complexity | complexity | 21h | 12.0 |
| 10 | `include/fmt/color.h` | Address MISRA C++ compliance violations | misra | 70h | 12.0 |

**Total: 22 roadmap items · ~686 estimated hours**

## Downloads

- [PDF Executive Report](report.pdf)
- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
