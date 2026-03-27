# AGENTS.md — Claude Code Operating Instructions

> **Read TASK_SPEC.md first.** This file tells you HOW to work. TASK_SPEC.md tells you WHAT to build.

## Mission

Build the complete cppulse MVP on branch `feature/full-mvp`. When done, `docker-compose up` with any C++ git repo must produce a full technical debt report.

## Operating Rules

1. **Follow the build order in TASK_SPEC.md exactly** — schemas first, then data producers, then consumers, then presentation, then orchestration, then integration.

2. **Test before proceeding** — every component must have passing tests before you start the next. Run:
   - C++: `cd analyzer-core && cmake -B build && cmake --build build && cd build && ctest --output-on-failure`
   - Python: `cd <component> && pytest -v --cov=src tests/`

3. **Document every decision** — when you make a choice not explicitly specified in TASK_SPEC.md, add it to `docs/DECISIONS.md` following the format there (Context, Decision, Why, Tradeoffs, Interview angle).

4. **Conventional commits** — use the commit messages from TASK_SPEC.md Appendix.

5. **Preserve existing code** — don't delete working code. Extend it. The existing `hello_libclang.cpp` should become a utility.

6. **Follow the style rules** — read `.claude/rules/cpp-style.md` for C++, `.claude/rules/python-style.md` for Python.

7. **No raw new/delete** — use smart pointers everywhere (project rule from CLAUDE.md).

8. **No std::cout** — use spdlog for all logging.

9. **Schema validation** — every component that reads JSON must validate against the schema on startup.

10. **Graceful degradation** — if a component fails, log the error and produce partial output (don't crash the pipeline).

## Phase Checklist

After completing each phase, verify:

### Phase 1 — Schemas ✓ when:
- [ ] All 4 schema files exist in `docs/schemas/`
- [ ] Each is valid JSON Schema draft-07

### Phase 2 — Data Producers ✓ when:
- [ ] `analyzer-core` builds, tests pass, produces valid `findings.json` from test fixtures
- [ ] `git-miner` tests pass, produces valid `git_metrics.json` from any git repo

### Phase 3 — Predictor ✓ when:
- [ ] Merges findings + git_metrics into feature matrix
- [ ] XGBoost trains and predicts (or falls back to heuristic for small repos)
- [ ] Produces valid `risk_scores.json` and `roadmap.json`

### Phase 4 — Presentation ✓ when:
- [ ] FastAPI serves all endpoints, returns data from JSON files
- [ ] WeasyPrint generates a non-empty PDF with all 7 sections
- [ ] React dashboard renders and connects to the API

### Phase 5 — CLI ✓ when:
- [ ] `cppulse analyze --repo <path> --output ./output` runs the full pipeline
- [ ] `cppulse report --input ./output --format pdf` generates the report

### Phase 6 — Integration ✓ when:
- [ ] `docker-compose up` completes without errors
- [ ] All JSON outputs validate against schemas
- [ ] PDF report exists and is non-empty
- [ ] Dashboard is accessible on :3000
- [ ] `scripts/integration_test.sh` passes

## Error Recovery

If you get stuck:
1. Check if the issue is a missing dependency → add to Dockerfile or requirements.txt
2. If a libclang API doesn't work as expected → simplify the rule (detect the pattern with a simpler cursor check)
3. If XGBoost training fails (too few samples) → activate the heuristic fallback
4. If WeasyPrint has rendering issues → simplify the HTML template
5. If docker-compose has networking issues → use `depends_on` with `condition: service_completed_successfully`

## What NOT to Do

- Don't rewrite the CMakeLists.txt from scratch — extend the existing one
- Don't use any external CI/CD services — just local docker-compose
- Don't optimize prematurely — working > fast for v1.0
- Don't skip DECISIONS.md — it's the entire point for interview prep
