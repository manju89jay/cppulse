# cppulse Report: POCO C++ Libraries

> Analyzed 2026-03-26 · 640,665 LOC · 3,068 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

POCO C++ Libraries is a mature, widely-deployed open-source C++ framework providing
networking, file system, threading, and cryptography primitives. With over 640K lines
of production code spanning 3,068 files and a git history stretching back nearly two
decades, it represents a realistic benchmark for cppulse: a large, actively maintained
codebase that predates modern C++ idioms.
cppulse scores it at 97.8/100 — reflecting strong memory safety (95.3), complexity control (98.6), modernization (94.7).

---

## Health Score

<p>
  <img src="../../assets/poco/health-gauge.svg" alt="Health Score: 97.8/100" width="280" />
  <img src="../../assets/poco/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **95.3** | 473 | Raw `new` (8), explicit `delete` (7), C-style array params (1) |
| Complexity | **98.6** | 975 | long functions (5), high cyclomatic complexity (1), too many params (1) |
| Modernization | **94.7** | 13,085 | raw string literal (24), unscoped `enum` (16), `typedef` (5) |

**Total: 14,533 findings across 15 of 15 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `ActiveRecord/testsuite/src/ActiveRecordTestSuite.cpp` | 97.9% | Critical | 1 total findings |
| `ActiveRecord/testsuite/src/WinDriver.cpp` | 97.9% | Critical | 1 total findings |
| `CppParser/src/Utility.cpp` | 97.9% | Critical | 1 total findings |
| `CppParser/testsuite/src/AttributesTestSuite.cpp` | 97.9% | Critical | 1 total findings |
| `CppParser/testsuite/src/CppParserTestSuite.cpp` | 97.9% | Critical | 1 total findings |
| `CppParser/testsuite/src/WinDriver.cpp` | 97.9% | Critical | 1 total findings |
| `Crypto/testsuite/src/Driver.cpp` | 97.9% | Critical | 1 total findings |
| `Crypto/testsuite/src/ECTest.cpp` | 97.9% | Critical | 1 total findings |
| `Data/SQLParser/src/parser/bison_parser.cpp` | 97.9% | Critical | 1 total findings |
| `ActiveRecord/Compiler/src/CodeGenerator.cpp` | 97.2% | Critical | 7 total findings, Modernization issues (1) |

**38 files** flagged Critical · **13 files** flagged Low risk (of 51 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `ActiveRecord/Compiler/src/ImplGenerator.cpp` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 3h | 16.0 |
| 2 | `Benchmark/src/BenchmarkApp.cpp` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 9h | 16.0 |
| 3 | `ActiveRecord/include/Poco/ActiveRecord/Query.h` | Fix memory safety issues | memory_safety | 8h | 16.0 |
| 4 | `ApacheConnector/samples/FormServer/src/FormServer.cpp` | Fix memory safety issues | memory_safety | 4h | 16.0 |
| 5 | `ApacheConnector/samples/TimeServer/src/TimeServer.cpp` | Fix memory safety issues | memory_safety | 4h | 16.0 |
| 6 | `ActiveRecord/Compiler/src/ImplGenerator.cpp` | Modernize C++ code | modernization | 9h | 8.0 |
| 7 | `Benchmark/src/BenchmarkApp.cpp` | Modernize C++ code | modernization | 2h | 8.0 |
| 8 | `Crypto/src/EVPCipherImpl.cpp` | Fix memory safety issues | memory_safety | 16h | 8.0 |
| 9 | `Crypto/src/X509Certificate.cpp` | Modernize C++ code | modernization | 1h | 8.0 |
| 10 | `Data/SQLParser/src/SQLParser.cpp` | Modernize C++ code | modernization | 1h | 8.0 |

**Total: 40 roadmap items · ~139 estimated hours**

## Downloads

- [PDF Executive Report (272 pages)](report.pdf)
- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
