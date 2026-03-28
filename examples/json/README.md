# cppulse Report: nlohmann/json

> Analyzed 2026-03-27 · 98,000 LOC · 479 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

nlohmann/json is the most widely starred C++ JSON library on GitHub, created by
Niels Lohmann. Its single-header design, intuitive API, and comprehensive test
suite have made it the de facto standard for JSON handling in modern C++ projects
across game engines, scientific computing, and cloud services. With the default
profile (MISRA excluded), it scores 96.8/100 — one of the strongest performers
in the cppulse benchmark set, reflecting rigorous code quality and consistent
use of modern C++ idioms. The remaining penalties are concentrated in complexity
hotspots inside the binary reader and lexer — areas that are inherently complex
by the nature of a full-featured JSON parser.

---

## Health Score

<p>
  <img src="../../assets/json/health-gauge.svg" alt="Health Score: 96.8/100" width="280" />
  <img src="../../assets/json/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **95.8** | 22 | Raw `new` (15), explicit `delete` (5), C-style array params (2) |
| Complexity | **90.9** | 72 | High cyclomatic complexity (32), long functions (31), excess params (9) |
| Modernization | **94.8** | 83 | `auto` opportunities (21), C-style casts (19), unscoped `enum` (12) |

**Total: 177 findings across 16 of 22 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `docs/mkdocs/docs/examples/get_to.cpp` | 99.4% | Critical | MISRA violations (5), 5 total findings |
| `include/nlohmann/detail/iterators/iter_impl.hpp` | 99.4% | Critical | MISRA violations (5), 5 total findings |
| `include/nlohmann/detail/json_pointer.hpp` | 99.4% | Critical | MISRA violations (6), 6 total findings |
| `include/nlohmann/ordered_map.hpp` | 99.4% | Critical | MISRA violations (7), memory issues (3), 10 total findings |
| `tests/src/unit-bson.cpp` | 99.4% | Critical | MISRA violations (3), 3 total findings |
| `tests/src/unit-cbor.cpp` | 99.4% | Critical | MISRA violations (3), 3 total findings |
| `tests/src/unit-class_parser.cpp` | 99.4% | Critical | MISRA violations (13), 13 total findings |
| `tests/src/unit-class_parser_diagnostic_positions.cpp` | 99.4% | Critical | MISRA violations (12), 12 total findings |
| `tests/src/unit-msgpack.cpp` | 99.4% | Critical | MISRA violations (3), 3 total findings |
| `tests/src/unit-testsuites.cpp` | 99.4% | Critical | MISRA violations (2), 2 total findings |

**47 files** flagged Critical · **2 files** flagged High · **2 files** flagged Medium · **28 files** flagged Low risk (of 79 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `docs/mkdocs/docs/examples/get_to.cpp` | Address MISRA C++ compliance violations | misra | 10h | 16.0 |
| 2 | `docs/mkdocs/docs/examples/operator_spaceship__const_reference.c++20.cpp` | Address MISRA C++ compliance violations | misra | 2h | 16.0 |
| 3 | `docs/mkdocs/docs/examples/operator_spaceship__scalartype.c++20.cpp` | Address MISRA C++ compliance violations | misra | 2h | 16.0 |
| 4 | `docs/mkdocs/docs/examples/parse__istream__parser_callback_t.cpp` | Address MISRA C++ compliance violations | misra | 2h | 16.0 |
| 5 | `docs/mkdocs/docs/examples/parse__string__parser_callback_t.cpp` | Address MISRA C++ compliance violations | misra | 2h | 16.0 |
| 6 | `include/nlohmann/detail/conversions/to_chars.hpp` | Reduce cyclomatic complexity | complexity | 15h | 12.0 |
| 7 | `include/nlohmann/detail/input/binary_reader.hpp` | Reduce cyclomatic complexity | complexity | 66h | 12.0 |
| 8 | `include/nlohmann/detail/input/binary_reader.hpp` | Address MISRA C++ compliance violations | misra | 92h | 12.0 |
| 9 | `include/nlohmann/detail/input/lexer.hpp` | Address MISRA C++ compliance violations | misra | 62h | 12.0 |
| 10 | `include/nlohmann/detail/input/lexer.hpp` | Reduce cyclomatic complexity | complexity | 21h | 12.0 |

**Total: 107 roadmap items · ~1,033 estimated hours**

## Downloads

- [PDF Executive Report](report.pdf)
- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
