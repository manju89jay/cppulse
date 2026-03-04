# cppulse Project Constitution

## Project Overview
cppulse is a C++ codebase health analyzer combining static analysis (libclang),
git behavioral analysis, and ML prediction (XGBoost) to generate actionable
technical debt reports for safety-critical C++ projects.

## Architecture
@docs/architecture.md

## Build Commands
- C++ build:   `cd analyzer-core && cmake -B build && cmake --build build`
- C++ test:    `cd analyzer-core/build && ctest --output-on-failure`
- Python test: `pytest -v --cov=src tests/`
- Full stack:  `docker-compose up --build`
- Lint C++:    `clang-tidy src/*.cpp -- -std=c++17`
- Lint Python: `ruff check . && black --check .`

## Key Decisions (see docs/adr/ for full ADRs)
- ADR-001: Use libclang, not custom parser
- ADR-002: XGBoost, not neural networks
- ADR-003: Monorepo with docker-compose
- ADR-004: JSON for inter-component communication
- ADR-005: PDF report over web-only dashboard

## Component Map
- `analyzer-core/` — C++17 static analysis engine (libclang)
- `git-miner/`     — Python git history analyzer
- `predictor/`     — Python ML pipeline (XGBoost)
- `report-engine/` — PDF + REST API (FastAPI + WeasyPrint)
- `dashboard/`     — React + TypeScript UI (Recharts)
- `cli/`           — C++17 CLI orchestrator (CLI11)
- `docs/`          — ADRs, specs, product docs

## Workflow Rules
- Multi-file features: use Plan Mode (Shift+Tab) before implementing
- After each feature: run /simplify to clean up
- Name every session: `/rename <feature-name>` (e.g. /rename raw-pointer-rule)
- Every 3–4 tasks: trigger the review-code skill
- At 70% context fill: `/compact preserve <current-feature-decisions>`
- When compacting, preserve: modified files, current feature, test results, ADR decisions

## NEVER
- Never use raw `new`/`delete` in C++ — use smart pointers (practice what we preach)
- Never commit without passing tests
- Never modify `docs/PRODUCT_VISION.md` without explicit instruction
- Never use `std::cout` for logging — use spdlog
- Never merge an architectural change without a corresponding ADR
