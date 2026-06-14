# cppulse Report: POCO C++ Libraries

> Analyzed 2026-06-13 · 657,650 LOC · 3,099 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

POCO C++ Libraries is a mature, widely-deployed open-source C++ framework providing networking, file system, threading, and cryptography primitives. With a git history stretching back nearly two decades, it represents a realistic benchmark for cppulse: a large, actively maintained codebase that predates modern C++ idioms.
cppulse scores it at 70.6/100 — reflecting strong memory safety (82.6), complexity (54.1), modernization (59.2).

---

## Health Score

<p>
  <img src="../../assets/poco/health-gauge.svg" alt="Health Score: 70.6/100" width="280" />
  <img src="../../assets/poco/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **82.6** | 573 | Raw `new` (305), explicit `delete` (209), C-style array params (59) |
| Complexity | **54.1** | 3,016 | long functions (2279), too many params (537), high cyclomatic complexity (200) |
| Modernization | **59.2** | 13,428 | `typedef` (6556), unscoped `enum` (3155), C-style casts (1714) |

**Total: 17,017 findings across 15 of 15 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `Foundation/testsuite/src/ProcessRunnerTest.cpp` | 99.7% | Critical | Multiple minor findings |
| `Foundation/include/Poco/AsyncNotificationCenter.h` | 99.7% | Critical | Multiple minor findings |
| `Foundation/src/AsyncNotificationCenter.cpp` | 99.6% | Critical | Multiple minor findings |
| `Foundation/src/ProcessRunner.cpp` | 99.6% | Critical | Multiple minor findings |
| `Data/ODBC/testsuite/src/ODBCSQLServerTest.cpp` | 99.6% | Critical | Multiple minor findings |
| `Net/include/Poco/Net/SocketReactor.h` | 99.6% | Critical | Multiple minor findings |
| `Data/MySQL/testsuite/src/SQLExecutor.cpp` | 99.5% | Critical | Multiple minor findings |
| `Foundation/testsuite/src/ProcessTest.cpp` | 99.5% | Critical | Multiple minor findings |
| `Foundation/src/URI.cpp` | 99.5% | Critical | Multiple minor findings |
| `Net/include/Poco/Net/SocketDefs.h` | 99.5% | Critical | Multiple minor findings |

**950 files** flagged Critical · **454 files** flagged High · **449 files** flagged Medium · **2676 files** flagged Low risk (of 4529 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `Trace/src/utils/utils.hpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 2 | `SevenZip/src/LzHash.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 3 | `Foundation/testsuite/src/MPSCQueueTest.cpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 4 | `Trace/src/binary/pe.hpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 5 | `Encodings/src/ISO8859_4Encoding.cpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 6 | `Foundation/src/Process_WIN32U.cpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 7 | `SevenZip/src/Lzma2Enc.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 8 | `dependencies/v8_double_conversion/src/fast-dtoa.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 9 | `dependencies/zlib/src/zlib.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 10 | `Foundation/src/UTF8Encoding.cpp` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |

**Total: 2567 roadmap items · ~37816 estimated hours**

## Downloads

- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
