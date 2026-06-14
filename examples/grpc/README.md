# cppulse Report: gRPC

> Analyzed 2026-06-14 · 795,076 LOC · 3,501 files · [Back to Leaderboard](../../README.md#analyzed-codebases)

gRPC is Google's open-source, high-performance Remote Procedure Call framework, built on HTTP/2 and Protocol Buffers. It powers microservice communication at Google scale and has become the dominant RPC standard across cloud-native infrastructure.
cppulse scores it at 68.2/100 — reflecting strong memory safety (86.5), complexity (55.1), modernization (32.7).

---

## Health Score

<p>
  <img src="../../assets/grpc/health-gauge.svg" alt="Health Score: 68.2/100" width="280" />
  <img src="../../assets/grpc/category-bars.svg" alt="Category Breakdown" width="440" />
</p>

## Category Breakdown

| Category | Score | Findings | Key Issues |
|----------|------:|--------:|------------|
| Memory Safety | **86.5** | 537 | Raw `new` (287), explicit `delete` (216), C-style array params (34) |
| Complexity | **55.1** | 3,568 | long functions (2341), high cyclomatic complexity (858), too many params (369) |
| Modernization | **32.7** | 26,738 | raw string literal (23252), deprecated C headers (1296), `typedef` (813) |

**Total: 30,843 findings across 15 of 15 rules**

## Top 10 Riskiest Files

| File | Bug Probability | Risk Level | Top Factors |
|------|----------------:|:----------:|-------------|
| `test/core/end2end/end2end_ph2_config.cc` | 99.5% | Critical | Multiple minor findings |
| `src/core/ext/transport/chttp2/transport/http2_client_transport.cc` | 99.4% | Critical | Multiple minor findings |
| `src/core/telemetry/instrument.h` | 99.3% | Critical | Multiple minor findings |
| `src/core/ext/transport/chttp2/transport/http2_client_transport.h` | 99.3% | Critical | Multiple minor findings |
| `src/core/ext/transport/chaotic_good/data_endpoints.cc` | 99.3% | Critical | Multiple minor findings |
| `src/core/ext/transport/chttp2/transport/http2_server_transport.h` | 99.2% | Critical | Multiple minor findings |
| `src/core/ext/upb-gen/envoy/config/core/v3/resolver.upb.h` | 99.2% | Critical | Multiple minor findings |
| `src/core/ext/upb-gen/envoy/config/trace/v3/lightstep.upb.h` | 99.2% | Critical | Multiple minor findings |
| `src/core/ext/upb-gen/envoy/config/trace/v3/skywalking.upb.h` | 99.2% | Critical | Multiple minor findings |
| `src/core/ext/upb-gen/envoy/type/matcher/v3/metadata.upb.h` | 99.2% | Critical | Multiple minor findings |

**806 files** flagged Critical · **312 files** flagged High · **379 files** flagged Medium · **4990 files** flagged Low risk (of 6487 total)

## Refactoring Roadmap (Top 10 by Impact)

| # | File | Action | Category | Est. Hours | Impact |
|--:|------|--------|----------|----:|------:|
| 1 | `src/core/ext/upb-gen/xds/service/orca/v3/orca.upb_minitable.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 2 | `src/core/ext/upb-gen/envoy/config/core/v3/udp_socket_config.upb_minitable.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 3 | `third_party/upb/upb/reflection/internal/message_def.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 4 | `src/core/ext/upb-gen/google/api/httpbody.upb_minitable.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 5 | `src/core/ext/upb-gen/envoy/config/trace/v3/dynamic_ot.upb.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 6 | `third_party/upb/upb/test/test_generated_code.cc` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 7 | `src/core/ext/upb-gen/envoy/admin/v3/mutex_stats.upb_minitable.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 8 | `src/core/ext/upb-gen/envoy/extensions/http/stateful_session/cookie/v3/cookie.upb.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 9 | `third_party/upb/upb/base/string_view.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |
| 10 | `src/core/ext/upb-gen/xds/core/v3/resource_locator.upb_minitable.h` | Reduce knowledge silo risk: add documentation, conduct knowledge transfer sessions | knowledge_silo | 8h | 8.0 |

**Total: 3890 roadmap items · ~51366 estimated hours**

## Downloads

- [Raw Findings (JSON)](findings.json)
- [Risk Scores (JSON)](risk_scores.json)
- [Refactoring Roadmap (JSON)](roadmap.json)
