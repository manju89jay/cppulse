# cppulse Report: POCO C++ Libraries

> Analyzed 2026-03-26 · 640,665 LOC · 3,068 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

---

## Health Score

<p>
  <img src="../../assets/poco/health-gauge.svg" alt="Health Score: 55.2/100" width="280" />
  <img src="../../assets/poco/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **92.8** | 473 | Raw `new` (229), explicit `delete` (188), C-style arrays (56) |
| Complexity | **90.1** | 975 | High cyclomatic complexity (154), long functions (290), too many params (531) |
| Modernization | **33.7** | 13,085 | `typedef` (6,986), unscoped `enum` (3,128), C-style casts (1,081) |
| MISRA Compliance | **0.0** | 11,288 | Uninitialized variables (10,014), multiple returns (1,006), `goto` (83) |

**Total: 25,821 findings across 21 of 22 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `Crypto/src/EVPCipherImpl.cpp` | 99.9% | Critical | misra, memory |
| `Crypto/src/RSACipherImpl.cpp` | 99.9% | Critical | misra, memory |
| `Crypto/testsuite/src/EVPTest.cpp` | 99.9% | Critical | misra, memory |
| `Crypto/testsuite/src/RSATest.cpp` | 99.9% | Critical | misra, memory |
| `Foundation/include/Poco/AbstractCache.h` | 99.9% | Critical | misra, memory |
| `Foundation/include/Poco/Buffer.h` | 99.9% | Critical | misra, memory |
| `Foundation/include/Poco/MPSCQueue.h` | 99.9% | Critical | misra, memory |
| `Foundation/testsuite/src/AnyTest.cpp` | 99.9% | Critical | misra, memory |
| `Foundation/testsuite/src/AutoPtrTest.cpp` | 99.9% | Critical | misra, memory |
| `DNSSD/samples/HTTPTimeServer/src/HTTPTimeServer.cpp` | 99.9% | Critical | misra, memory |

**780 files** flagged Critical · **207 files** flagged Low risk (of 987 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `ActiveRecord/.../CodeGenerator.cpp` | MISRA compliance fixes | misra | 12h | 16.0 |
| 2 | `ActiveRecord/.../Compiler.cpp` | MISRA compliance fixes | misra | 8h | 16.0 |
| 3 | `ActiveRecord/.../HeaderGenerator.cpp` | MISRA compliance fixes | misra | 6h | 16.0 |
| 4 | `ActiveRecord/.../ImplGenerator.cpp` | Reduce cyclomatic complexity | complexity | 3h | 16.0 |
| 5 | `ActiveRecord/.../Parser.cpp` | MISRA compliance fixes | misra | 10h | 16.0 |
| 6 | `ActiveRecord/.../Query.h` | Replace raw pointers with smart pointers | memory_safety | 8h | 16.0 |
| 7 | `ActiveRecord/.../Query.h` | MISRA compliance fixes | misra | 6h | 16.0 |
| 8 | `ActiveRecord/.../ActiveRecordTest.cpp` | MISRA compliance fixes | misra | 58h | 16.0 |
| 9 | `ActiveRecord/.../ImplGenerator.cpp` | MISRA compliance fixes | misra | 2h | 16.0 |
| 10 | `ActiveRecord/.../ActiveRecordTestSuite.cpp` | MISRA compliance fixes | misra | 2h | 16.0 |

**Total: 1,633 roadmap items · ~40,478 estimated hours**

## Downloads

- [PDF Executive Report (272 pages)](report.pdf)
- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
