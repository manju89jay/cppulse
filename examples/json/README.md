# cppulse Report: nlohmann/json

> Analyzed 2026-06-14 · 99,017 LOC · 488 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

nlohmann/json is the most widely starred C++ JSON library on GitHub, created by Niels Lohmann. Its single-header design, intuitive API, and comprehensive test suite have made it the de facto standard for JSON handling in modern C++ projects across game engines, scientific computing, and cloud services.
cppulse scores it at 88.4/100 — reflecting strong memory safety (90.5), complexity (87.5), modernization (83.7).

---

## Health Score

<p>
  <img src="../../assets/json/health-gauge.svg" alt="Health Score: 88.4/100" width="280" />
  <img src="../../assets/json/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **90.5** | 47 | Raw `new` (25), C-style array params (13), explicit `delete` (9) |
| Complexity | **87.5** | 124 | high cyclomatic complexity (49), long functions (43), too many params (32) |
| Modernization | **83.7** | 808 | C-style casts (369), raw string literal (166), `typedef` (116) |

**Total: 979 findings across 14 of 15 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `tests/src/unit-class_parser.cpp` | 99.9% | Critical | Multiple minor findings |
| `tests/src/unit-conversions.cpp` | 99.9% | Critical | Multiple minor findings |
| `tests/src/unit-bson.cpp` | 99.9% | Critical | Multiple minor findings |
| `tests/src/unit-iterators2.cpp` | 99.9% | Critical | Multiple minor findings |
| `tests/src/unit-json_patch.cpp` | 99.9% | Critical | Multiple minor findings |
| `tests/src/unit-udt.cpp` | 99.9% | Critical | Multiple minor findings |
| `tests/src/unit-deserialization.cpp` | 99.9% | Critical | Multiple minor findings |
| `tests/src/unit-alt-string.cpp` | 99.9% | Critical | Multiple minor findings |
| `tests/src/unit-serialization.cpp` | 99.9% | Critical | Multiple minor findings |
| `tests/src/unit-cbor.cpp` | 99.9% | Critical | Multiple minor findings |

**238 files** flagged Critical · **16 files** flagged High · **41 files** flagged Medium · **1138 files** flagged Low risk (of 1433 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `tests/src/unit-msgpack.cpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 2 | `tests/src/unit-reference_access.cpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 3 | `include/nlohmann/detail/iterators/iterator_traits.hpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 4 | `include/nlohmann/detail/meta/identity_tag.hpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 5 | `docs/mkdocs/docs/examples/nlohmann_define_type_non_intrusive_explicit.cpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 6 | `tests/src/unit-wstring.cpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 7 | `tests/src/unit-ordered_map.cpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 8 | `tests/src/unit-byte_container_with_subtype.cpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 9 | `include/nlohmann/detail/meta/void_t.hpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 10 | `tests/src/unit-json_patch.cpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |

**Total: 318 roadmap items · ~2600 estimated hours**

## Downloads

- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
