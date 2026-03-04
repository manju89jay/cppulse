# ADR-003: Monorepo with docker-compose

**Date:** 2026-03-04
**Status:** Accepted
**Deciders:** Manjunath Jayaramaiah

---

## Context
cppulse has 6 components in 2 languages (C++17, Python) plus a React frontend.
The question is whether to manage these as a single monorepo or as separate
repositories with a separate orchestration layer.

## Decision
**Monorepo** with **docker-compose** for local development orchestration.

## Consequences

### Positive
- Atomic commits: a single PR can change the JSON schema in analyzer-core AND
  update the Python consumer in git-miner simultaneously — no cross-repo coordination
- Shared interface definitions: output JSON schemas live in one place
- Simpler CI: one GitHub Actions pipeline for all components
- Local dev: `docker-compose up --build` starts the full system in one command
- Portfolio clarity: one repo link demonstrates the full system

### Negative
- Repo size grows as all components build up history together
- CI must build all components even when only one changes (mitigated with path filters)

### Neutral
- Each component still has its own Dockerfile — components are independently deployable
- GitHub Actions matrix can be added later for per-component change detection

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| 6 separate repos | Cross-component changes require 6 PRs. JSON schema changes would break consumers silently. |
| Monorepo with Bazel | Bazel is correct at Google scale. Overkill for a 6-component portfolio project. |
| Single Python package | Cannot accommodate C++17 components alongside Python cleanly. |
