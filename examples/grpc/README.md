# cppulse Report: gRPC

> Analyzed 2026-03-27 · 964,485 LOC · 4,188 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

gRPC is Google's open-source, high-performance Remote Procedure Call framework, built on HTTP/2 and Protocol Buffers. It powers microservice communication at Google scale and has become the dominant RPC standard across cloud-native infrastructure.
cppulse scores it at 99.0/100 — reflecting strong memory safety (95.9), complexity (99.6), modernization (99.2).

---

## Health Score

<p>
  <img src="../../assets/grpc/health-gauge.svg" alt="Health Score: 99.0/100" width="280" />
  <img src="../../assets/grpc/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **95.9** | 504 | explicit `delete` (11), Raw `new` (9), C-style array params (2) |
| Complexity | **99.6** | 1,510 | long functions (1), too many params (1), high cyclomatic complexity (1) |
| Modernization | **99.2** | 7,394 | C-style casts (4), range-for opportunities (2), raw string literal (1) |

**Total: 9,408 findings across 15 of 15 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `examples/android/helloworld/app/src/main/cpp/grpc-helloworld.cc` | 98.6% | Critical | 7 total findings |
| `examples/cpp/auth/ssl_client.cc` | 98.6% | Critical | 9 total findings |
| `examples/cpp/auth/ssl_server.cc` | 98.6% | Critical | 6 total findings |
| `examples/cpp/cancellation/client.cc` | 98.6% | Critical | 4 total findings |
| `examples/cpp/cancellation/server.cc` | 98.6% | Critical | 5 total findings, Memory issues (2) |
| `examples/cpp/compression/greeter_client.cc` | 98.6% | Critical | 7 total findings |
| `examples/cpp/compression/greeter_server.cc` | 98.6% | Critical | 2 total findings |
| `examples/cpp/csm/csm_greeter_client.cc` | 98.6% | Critical | 13 total findings |
| `examples/cpp/csm/csm_greeter_server.cc` | 98.6% | Critical | 9 total findings |
| `examples/cpp/csm/observability/csm_greeter_client.cc` | 98.6% | Critical | 5 total findings |

**73 files** flagged Critical · **7 files** flagged Low risk (of 80 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `examples/cpp/cancellation/server.cc` | Fix memory safety issues: replace raw pointers with smart pointers and add bounds checks | memory_safety | 8h | 16.0 |
| 2 | `examples/cpp/flow_control/server_flow_control_client.cc` | Fix memory safety issues: replace raw pointers with smart pointers and add bounds checks | memory_safety | 4h | 8.0 |
| 3 | `examples/cpp/gcp_observability/helloworld/greeter_server.cc` | Modernize C++ code: apply C++11/14/17 idioms and remove deprecated constructs | modernization | 1h | 8.0 |
| 4 | `examples/cpp/helloworld/greeter_async_client2.cc` | Modernize C++ code: apply C++11/14/17 idioms and remove deprecated constructs | modernization | 2h | 8.0 |
| 5 | `examples/cpp/helloworld/greeter_async_client2.cc` | Fix memory safety issues: replace raw pointers with smart pointers and add bounds checks | memory_safety | 8h | 8.0 |
| 6 | `examples/cpp/helloworld/greeter_async_server.cc` | Modernize C++ code: apply C++11/14/17 idioms and remove deprecated constructs | modernization | 1h | 8.0 |
| 7 | `examples/cpp/helloworld/greeter_async_server.cc` | Fix memory safety issues: replace raw pointers with smart pointers and add bounds checks | memory_safety | 4h | 8.0 |
| 8 | `examples/cpp/route_guide/route_guide_callback_client.cc` | Reduce cyclomatic complexity by extracting methods and simplifying control flow | complexity | 3h | 8.0 |
| 9 | `examples/cpp/flow_control/client_flow_control_server.cc` | Fix memory safety issues: replace raw pointers with smart pointers and add bounds checks | memory_safety | 8h | 8.0 |
| 10 | `examples/cpp/flow_control/server_flow_control_server.cc` | Fix memory safety issues: replace raw pointers with smart pointers and add bounds checks | memory_safety | 12h | 8.0 |

**Total: 25 roadmap items · ~110 estimated hours**

## Downloads

- [PDF Executive Report](report.pdf)
- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
