# ADR-006: Production Readiness Assessment and Gap Closure

**Date:** 2026-04-07
**Status:** Proposed
**Deciders:** Manjunath Jayaramaiah

---

## Context

cppulse has been validated against 6 major open-source C++ projects (2.2M LOC,
90K+ findings). The core pipeline works end-to-end and produces useful results.
Before a 1.0 release, we need to close gaps in security, portability,
configuration, and ML rigor that would block adoption in real development teams.

This ADR catalogs every production-readiness gap identified during a full
architecture review and proposes a prioritized closure plan.

## Decision

Address the gaps below in priority order (P0 first). Each gap includes what to
fix, why it matters, and estimated scope.

---

## P0 — Must Fix Before 1.0

### 1. Shell Injection in CLI Orchestrator

**File:** `cli/src/orchestrator.cpp:74-101`
**Problem:** `repo_path` and `output_dir` are concatenated directly into shell
commands passed to `popen()`. A path like `/tmp/; rm -rf /` would execute
arbitrary commands.
**Fix:** Use `std::filesystem::path` quoting or, better, switch to
`posix_spawn()` / `CreateProcess()` with argument arrays instead of shell
strings. Never pass user-controlled strings through a shell interpreter.
**Scope:** ~2 days. Touches `orchestrator.cpp` only.

### 2. SHAP Explainability — Documented But Not Implemented

**File:** `predictor/src/model.py`
**Problem:** The README, architecture.md, and `requirements.txt` all claim SHAP
feature importance is computed. The code never imports or calls shap. Users
expecting explainability get nothing.
**Fix:** Either implement SHAP (add `shap.TreeExplainer` after XGBoost training,
emit top 3 feature importances per file in `risk_scores.json`) or remove the
claim from all docs. Implementing it is straightforward (~50 LOC).
**Scope:** 1 day to implement, or 1 hour to remove the claim.

### 3. ML Evaluation on Training Data

**File:** `predictor/src/model.py:161-165`
**Problem:** F1, precision, and recall are computed on the same data used for
training. These metrics are inflated and misleading, especially on small
datasets. No train/test split, no cross-validation.
**Fix:** Add stratified k-fold CV (k=5) when samples >= 50. Report mean +/- std
of metrics. For <50 samples, report "heuristic mode" without fake metrics.
**Scope:** 1 day. Add `cross_val_score` from sklearn.

---

## P1 — Should Fix Before 1.0

### 4. CLI Assumes CWD Is Repo Root

**File:** `cli/src/orchestrator.cpp:82`
**Problem:** Commands like `cd git-miner && python3 -m src.main` assume the
current working directory is the cppulse checkout root. If invoked from anywhere
else, every Python stage fails silently.
**Fix:** Resolve component paths relative to the binary's location using
`std::filesystem::canonical()` on `/proc/self/exe` (Linux) or
`GetModuleFileName` (Windows). Pass absolute paths to all subprocess commands.
**Scope:** 1 day.

### 5. No Windows Support in CLI

**File:** `cli/src/orchestrator.cpp:48`
**Problem:** `WEXITSTATUS` is a POSIX macro. `popen()`/`pclose()` are POSIX.
The CLI doesn't compile on MSVC. Many C++ developers use Windows.
**Fix:** Use `_popen()`/`_pclose()` on MSVC. Replace `WEXITSTATUS` with a
platform abstraction. Or use `boost::process` / C++23 `std::process` when
available. Consider CMake `if(WIN32)` guards.
**Scope:** 2 days.

### 6. No Per-Project Configuration

**Problem:** All rule thresholds (cyclomatic complexity > 15, function length
> 80, etc.) are hardcoded. Users cannot suppress rules, adjust thresholds, or
ignore specific files/directories.
**Fix:** Support a `.cppulserc.yml` or `.cppulse.toml` config file with:
- `exclude_paths: [vendor/**, third_party/**]`
- `rules.CPP-CX-001.warning_threshold: 20`
- `rules.CPP-MEM-001.enabled: false`
- `profile: safety-critical`
**Scope:** 3-4 days. Touches analyzer-core (config parsing + rule thresholds),
CLI (config discovery), and predictor (profile selection).

### 7. Report-Engine Hardcoded CORS

**File:** `report-engine/src/api.py`
**Problem:** CORS allows only `localhost:3000`. Deploying behind a reverse proxy
or on a different host fails.
**Fix:** Read allowed origins from `CORS_ORIGINS` environment variable,
defaulting to `["http://localhost:3000"]`.
**Scope:** 30 minutes.

### 8. No API Authentication

**Problem:** Report-engine exposes codebase security findings (memory safety
violations, bug predictions) with no authentication. In shared CI/CD
environments, anyone on the network can read them.
**Fix:** Add optional API key auth via `CPPULSE_API_KEY` env var. When set,
require `Authorization: Bearer <key>` header. When unset, allow unauthenticated
access (backwards compatible).
**Scope:** 1 day.

---

## P2 — Nice to Have for 1.0

### 9. Dashboard Has Zero Tests

**Problem:** The React dashboard has no Jest/Vitest tests. Every other component
has automated test coverage. UI regressions can ship silently.
**Fix:** Add Vitest + React Testing Library. Cover: HealthScore rendering,
FindingsList filtering, API error states, empty data handling.
**Scope:** 2 days.

### 10. Parallel Pipeline Stages

**Problem:** `run_full_pipeline()` runs analyzer-core then git-miner
sequentially. They are independent — one reads AST, the other reads git log.
Docker Compose already runs them in parallel, but the CLI doesn't.
**Fix:** Use `std::thread` or `std::async` to run stages 1 and 2 concurrently.
Join before stage 3 (predictor needs both outputs).
**Scope:** 1 day.

### 11. Report-Engine Caching

**Problem:** Every API request re-reads JSON files from disk. On large codebases
with big `findings.json` (50MB+), this adds noticeable latency.
**Fix:** Cache parsed JSON in memory with file mtime-based invalidation. Reload
only when the underlying file changes.
**Scope:** Half day.

### 12. CONTRIBUTING.md Missing

**Problem:** README links to `CONTRIBUTING.md` but the file doesn't exist.
**Fix:** Create it with: how to set up the dev environment, how to run tests,
coding standards pointers, PR process.
**Scope:** 1 hour.

---

## Consequences

### Positive
- P0 fixes eliminate security vulnerability (injection) and false advertising (SHAP)
- P1 fixes make cppulse usable by real teams (config, Windows, auth)
- Each fix is scoped to 1-4 days, no architectural changes needed

### Negative
- Config file support (P1.6) adds parsing complexity and a new user-facing schema to maintain
- API auth (P1.8) adds deployment friction for simple local usage

### Neutral
- Docker Compose already handles parallel stages, so P2.10 only benefits CLI users
- Dashboard tests (P2.9) are standard practice, no architectural impact

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Ship 1.0 without P0 fixes | Shell injection is a security vulnerability; misleading SHAP docs erode trust |
| Use clang-tidy instead of custom rules | Already decided against in ADR-001 — custom rules give control over health scoring |
| Add full RBAC instead of API key | Overkill for a developer tool; API key is sufficient for 1.0 |
| Use SQLite instead of JSON files | Already decided against in ADR-004 — JSON is simpler and debuggable |
