# ADR-004: JSON for Inter-Component Communication

**Date:** 2026-03-04
**Status:** Accepted
**Deciders:** Manjunath Jayaramaiah

---

## Context
analyzer-core (C++) must pass findings to predictor (Python). git-miner (Python)
must pass metrics to predictor. All outputs feed report-engine and the REST API.
We need a data exchange format that works seamlessly between C++ and Python.

## Decision
**JSON files** written to a shared `./output/` directory, validated against
a JSON schema at each stage boundary.

## Consequences

### Positive
- Human-readable: findings.json can be inspected with cat or jq — essential for
  debugging the pipeline
- Universal: both nlohmann/json (C++) and the stdlib json module (Python) are
  mature and well-documented
- Schema validation: jsonschema library validates contracts at each interface
- REST API: report-engine serves the same JSON via FastAPI with no transformation
- Debuggable: if the pipeline fails, the intermediate JSON files show exactly
  where it broke

### Negative
- Performance: JSON parsing is slower than binary formats for very large repos
  (acceptable — cppulse is batch analysis, not real-time)
- File I/O: writing to disk adds latency vs in-memory IPC (acceptable for same
  reasons)

### Neutral
- Output directory is mounted as a Docker volume shared between containers

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Protocol Buffers | Not human-readable. Cross-language schema management adds build complexity. Not justified for batch analysis. |
| MessagePack | Binary, not human-readable. Harder to debug. Marginal performance gain not needed. |
| Unix pipes / shared memory | Cannot cross Docker container boundaries without complexity. |
| SQLite | Heavyweight for a pipeline that runs once per analysis. Adds a dependency with no benefit over flat files. |
