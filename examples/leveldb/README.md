# cppulse Report: LevelDB

> Analyzed 2026-03-27 · 29,000 LOC · 132 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

LevelDB is Google's fast on-disk key-value storage library, originally written
by Jeff Dean and Sanjay Ghemawat and open-sourced in 2011. It underpins Chrome's
IndexedDB and has been adopted by Bitcoin Core, Ethereum clients, and dozens of
embedded database projects. At just 29K lines across 132 files it is one of the
most studied small systems codebases in existence, making it an excellent
cppulse benchmark.
cppulse scores it at 76.7/100 — dragged down by memory safety (28.8).

---

## Health Score

<p>
  <img src="../../assets/leveldb/health-gauge.svg" alt="Health Score: 76.7/100" width="280" />
  <img src="../../assets/leveldb/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **28.8** | 204 | explicit `delete` (53), Raw `new` (23) |
| Complexity | **79.4** | 67 | high cyclomatic complexity (22), too many params (7), long functions (4) |
| Modernization | **70.0** | 301 | range-for opportunities (72), raw string literal (8), C-style casts (7) |

**Total: 572 findings across 12 of 15 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `db/db_test.cc` | 69.6% | High | Memory issues (28), Complexity findings (17) |
| `db/c.cc` | 34.3% | Medium | Memory issues (28), Complexity findings (3) |
| `benchmarks/db_bench.cc` | 26.5% | Low | Memory issues (11), Complexity findings (3) |
| `benchmarks/db_bench_sqlite3.cc` | 16.7% | Low | Complexity findings (4) |
| `db/corruption_test.cc` | 12.1% | Low | Memory issues (1), Complexity findings (1) |
| `benchmarks/db_bench_tree_db.cc` | 10.3% | Low | Memory issues (1), Complexity findings (3) |
| `db/builder.cc` | 5.5% | Low | Memory issues (3), Complexity findings (1) |
| `benchmarks/db_bench_log.cc` | 4.8% | Low | Memory issues (1) |
| `db/autocompact_test.cc` | 3.9% | Low | Memory issues (1) |
| `db/db_iter.cc` | 3.8% | Low | Memory issues (1) |

**1 file** flagged High · **1 file** flagged Medium · **14 files** flagged Low risk (of 16 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `db/db_test.cc` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 51h | 18.0 |
| 2 | `db/db_test.cc` | Modernize C++ code | modernization | 53h | 12.0 |
| 3 | `db/db_test.cc` | Fix memory safety issues | memory_safety | 112h | 12.0 |
| 4 | `db/c.cc` | Modernize C++ code | modernization | 3h | 8.0 |
| 5 | `db/c.cc` | Fix memory safety issues | memory_safety | 112h | 8.0 |
| 6 | `db/c.cc` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 9h | 8.0 |
| 7 | `benchmarks/db_bench.cc` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 9h | 6.0 |
| 8 | `benchmarks/db_bench_sqlite3.cc` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 12h | 6.0 |
| 9 | `benchmarks/db_bench.cc` | Fix memory safety issues | memory_safety | 44h | 4.0 |
| 10 | `benchmarks/db_bench_log.cc` | Modernize C++ code | modernization | 2h | 4.0 |

**Total: 30 roadmap items · ~515 estimated hours**

## Downloads

- [PDF Executive Report](report.pdf)
- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
