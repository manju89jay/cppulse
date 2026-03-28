# cppulse Report: LevelDB

> Analyzed 2026-03-27 · 29,000 LOC · 132 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

LevelDB is Google's fast on-disk key-value storage library, originally written
by Jeff Dean and Sanjay Ghemawat and open-sourced in 2011. It underpins Chrome's
IndexedDB and has been adopted by Bitcoin Core, Ethereum clients, and dozens of
embedded database projects. At just 29K lines across 132 files it is one of the
most studied small systems codebases in existence, making it an excellent
cppulse benchmark. With the default profile (MISRA excluded), its score of
76.7/100 reflects a genuine memory safety challenge driven by pervasive raw
pointer use inherited from a pre-C++11 codebase, partially offset by solid
complexity and modernization discipline.

---

## Health Score

<p>
  <img src="../../assets/leveldb/health-gauge.svg" alt="Health Score: 76.7/100" width="280" />
  <img src="../../assets/leveldb/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **28.8** | 76 | Explicit `delete` (53), raw `new` (23) |
| Complexity | **79.4** | 33 | High cyclomatic complexity (22), excess params (7), long functions (4) |
| Modernization | **70.0** | 96 | `typedef` (72), NULL vs nullptr (8), C-style casts (7) |

**Total: 205 findings across 14 of 22 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `db/db_test.cc` | 69.6% | High | Memory issues (28), complexity findings (17), 178 total findings |
| `db/c.cc` | 34.3% | Medium | Memory issues (28), complexity findings (3), 54 total findings |
| `benchmarks/db_bench.cc` | 26.5% | Low | Memory issues (11), complexity findings (3), 70 total findings |
| `benchmarks/db_bench_sqlite3.cc` | 16.7% | Low | Complexity findings (4), 59 total findings |
| `db/corruption_test.cc` | 12.1% | Low | Memory issues (1), complexity findings (1), 42 total findings |
| `benchmarks/db_bench_tree_db.cc` | 10.3% | Low | Memory issues (1), complexity findings (3), 32 total findings |
| `db/builder.cc` | 5.5% | Low | Memory issues (3), complexity findings (1), 11 total findings |
| `benchmarks/db_bench_log.cc` | 4.8% | Low | Memory issues (1), 16 total findings |
| `db/autocompact_test.cc` | 3.9% | Low | Memory issues (1), 13 total findings |
| `db/db_iter.cc` | 3.8% | Low | Memory issues (1), 12 total findings |

**1 file** flagged High · **1 file** flagged Medium · **12 files** flagged Low risk (of 14 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `db/db_test.cc` | Reduce cyclomatic complexity | complexity | 51h | 18.0 |
| 2 | `db/c.cc` | Address MISRA C++ compliance violations | misra | 40h | 12.0 |
| 3 | `db/db_test.cc` | Modernize C++ code: apply C++11/14/17 idioms | modernization | 53h | 12.0 |
| 4 | `db/db_test.cc` | Replace raw pointers with smart pointers | memory_safety | 112h | 12.0 |
| 5 | `db/db_test.cc` | Address MISRA C++ compliance violations | misra | 160h | 12.0 |
| 6 | `db/c.cc` | Modernize C++ code: apply C++11/14/17 idioms | modernization | 3h | 8.0 |
| 7 | `db/c.cc` | Replace raw pointers with smart pointers | memory_safety | 112h | 8.0 |
| 8 | `db/c.cc` | Reduce cyclomatic complexity | complexity | 9h | 8.0 |
| 9 | `benchmarks/db_bench.cc` | Reduce cyclomatic complexity | complexity | 9h | 6.0 |
| 10 | `benchmarks/db_bench_sqlite3.cc` | Reduce cyclomatic complexity | complexity | 12h | 6.0 |

**Total: 42 roadmap items · ~1,105 estimated hours**

## Downloads

- [PDF Executive Report](report.pdf)
- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
