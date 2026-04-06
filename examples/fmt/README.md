# cppulse Report: {fmt}

> Analyzed 2026-03-27 · 54,000 LOC · 70 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

{fmt} is Victor Zverovich's type-safe formatting library that became the direct
basis for `std::format` in C++20. Widely deployed across game engines, embedded
systems, and cloud infrastructure, fmt is valued for both its ergonomics and its
near-zero runtime overhead.
cppulse scores it at 60.9/100 — strong memory safety (94.0) offset by weaker modernization (0.0).

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
| Complexity | **77.0** | 123 | high cyclomatic complexity (19), long functions (3), too many params (1) |
| Modernization | **0.0** | 1,478 | C-style casts (159), unscoped `enum` (100), range-for opportunities (36) |

**Total: 1,769 findings across 14 of 15 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `include/fmt/chrono.h` | 69.6% | High | Memory issues (1), Complexity findings (7) |
| `include/fmt/args.h` | 63.2% | High | Memory issues (1), Complexity findings (7) |
| `include/fmt/color.h` | 37.8% | Medium | Complexity findings (7) |
| `test/gtest/gtest/gtest.h` | 26.2% | Low | Memory issues (1) |
| `src/fmt.cc` | 26.1% | Low | Memory issues (1) |
| `include/fmt/base.h` | 10.0% | Low | Complexity findings (1) |
| `include/fmt/compile.h` | 7.7% | Low | Multiple minor findings |
| `include/fmt/format-inl.h` | 2.8% | Low | Complexity findings (1) |
| `include/fmt/fmt-c.h` | 0.1% | Low | Multiple minor findings |
| `test/gtest/gmock/gmock.h` | 0.1% | Low | Multiple minor findings |

**2 files** flagged High · **1 file** flagged Medium · **7 files** flagged Low risk (of 10 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `include/fmt/args.h` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 21h | 18.0 |
| 2 | `include/fmt/chrono.h` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 21h | 18.0 |
| 3 | `include/fmt/args.h` | Fix memory safety issues | memory_safety | 4h | 12.0 |
| 4 | `include/fmt/args.h` | Modernize C++ code | modernization | 77h | 12.0 |
| 5 | `include/fmt/chrono.h` | Fix memory safety issues | memory_safety | 4h | 12.0 |
| 6 | `include/fmt/chrono.h` | Modernize C++ code | modernization | 84h | 12.0 |
| 7 | `include/fmt/color.h` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 21h | 12.0 |
| 8 | `include/fmt/color.h` | Modernize C++ code | modernization | 79h | 8.0 |
| 9 | `include/fmt/base.h` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 3h | 6.0 |
| 10 | `include/fmt/format-inl.h` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 3h | 4.0 |

**Total: 17 roadmap items · ~430 estimated hours**

## Downloads

- [PDF Executive Report](report.pdf)
- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
