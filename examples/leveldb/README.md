# cppulse Report: LevelDB

> Analyzed 2026-03-27 · 29,000 LOC · 132 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

LevelDB is Google's fast on-disk key-value storage library, originally written
by Jeff Dean and Sanjay Ghemawat and open-sourced in 2011. It underpins Chrome's
IndexedDB and has been adopted by Bitcoin Core, Ethereum clients, and dozens of
embedded database projects. At just 29K lines across 132 files it is one of the
most studied small systems codebases in existence, making it an excellent
cppulse benchmark. Its overall score of 47.0/100 reflects genuinely strong
complexity and modernization discipline but a near-total MISRA failure driven
by pervasive uninitialized-variable patterns and heavy raw pointer use inherited
from a pre-C++11 codebase.

---

## Health Score

<p>
  <img src="../../assets/leveldb/health-gauge.svg" alt="Health Score: 47.0/100" width="280" />
  <img src="../../assets/leveldb/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **65.6** | 76 | Explicit `delete` (53), raw `new` (23) |
| Complexity | **92.5** | 33 | High cyclomatic complexity (22), excess params (7), long functions (4) |
| Modernization | **83.1** | 96 | `typedef` (72), NULL vs nullptr (8), C-style casts (7) |
| MISRA Compliance | **0.0** | 295 | Uninitialized variables (219), multiple returns (70), dynamic allocation (5) |

**Total: 500 findings across 17 of 22 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `db/builder.cc` | 99.5% | Critical | MISRA violations (7), memory issues (3) |
| `db/db_impl.cc` | 99.5% | Critical | MISRA violations (9), memory issues (1) |
| `db/dumpfile.cc` | 99.5% | Critical | MISRA violations (24), memory issues (6) |
| `db/repair.cc` | 99.5% | Critical | MISRA violations (46), memory issues (7) |
| `db/table_cache.cc` | 99.5% | Critical | MISRA violations (2), memory issues (3) |
| `db/write_batch_test.cc` | 99.5% | Critical | MISRA violations (25), memory issues (1) |
| `issues/issue178_test.cc` | 99.5% | Critical | MISRA violations (4), memory issues (2) |
| `issues/issue200_test.cc` | 99.5% | Critical | MISRA violations (6), memory issues (2) |
| `issues/issue320_test.cc` | 99.5% | Critical | MISRA violations (7), memory issues (1) |
| `table/format.cc` | 99.5% | Critical | MISRA violations (8), memory issues (16) |

**74 files** flagged Critical · **15 files** flagged Low risk (of 89 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `benchmarks/db_bench.cc` | Reduce cyclomatic complexity | complexity | 9h | 24.0 |
| 2 | `benchmarks/db_bench_sqlite3.cc` | Reduce cyclomatic complexity | complexity | 12h | 24.0 |
| 3 | `db/c.cc` | Address MISRA C++ compliance violations | misra | 40h | 24.0 |
| 4 | `db/db_test.cc` | Reduce cyclomatic complexity | complexity | 51h | 24.0 |
| 5 | `db/dbformat.h` | Address MISRA C++ compliance violations | misra | 4h | 24.0 |
| 6 | `db/filename_test.cc` | Reduce cyclomatic complexity | complexity | 3h | 24.0 |
| 7 | `benchmarks/db_bench.cc` | Replace raw pointers with smart pointers | memory_safety | 44h | 16.0 |
| 8 | `benchmarks/db_bench.cc` | Address MISRA C++ compliance violations | misra | 88h | 16.0 |
| 9 | `benchmarks/db_bench_log.cc` | Replace raw pointers with smart pointers | memory_safety | 4h | 16.0 |
| 10 | `benchmarks/db_bench_log.cc` | Modernize C++ code: apply C++11/14/17 idioms | modernization | 2h | 16.0 |

**Total: 197 roadmap items · ~4,296 estimated hours**

## Downloads

- [PDF Executive Report](report.pdf)
- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
