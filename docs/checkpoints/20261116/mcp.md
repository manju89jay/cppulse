# Read-only MCP source checkpoint — 16 November 2026

Implemented seven read-only tools over an explicitly configured existing store:
run status, health, findings, hotspots, policy gaps, packaged rule/retained policy
documentation and retained UTF-8 artifact chunks. Invoked as
`python -m cppulse.mcp_server --store PATH`; no CLI integration changes required.

The stdio server implements JSON-RPC newline framing, MCP 2024-11-05 initialize,
ping, tools/list and tools/call. Strict tool schemas reject unknown/extra arguments.
Every retained-data request requires exact run ID and manifest SHA-256. Stored
historical selection and lack of a new current-source verification are explicit.
All policy display values come from the shared checked snapshot view; normalized
observations preserve occurrences/context and prototype findings are a fallback.
No independent scorer, project execution, publishing, arbitrary filesystem reads,
network listener, extra dependency or writer API exists.

Requests are bounded to 64 KiB; response serialization to 512 KiB; page size to
100; UTF-8 artifact chunks to 32 KiB. The additive optional
`RunStore.open_run(max_snapshot_bytes=...)` enforces an 32 MiB manifest-plus-artifact
payload budget before reading artifacts and uses bounded descriptor reads, with
size checks and read(max+1) growth detection. Default RunStore behavior remains
compatible. JSON object overhead is additional; this is a finite whole-snapshot
preview, not indexed large-project querying.

## Checks

- Before module implementation, seven actual subprocess MCP client checks failed
  because `cppulse.mcp_server` did not exist (expected red reproduction).
- MCP + existing read-store/manifest suites: **80 passed** before the last two
  added MCP regressions.
- MCP + shared presentation/read-store/manifest suites: **97 passed**, two existing
  PDF dependency deprecation warnings, before the final nesting regression.
- Exact final MCP suite: **15 passed in 27.18s**;
  command `PYTHONPATH=python .venv/bin/python -m pytest -v tests/test_mcp_server.py`,
  retained log `mcp-tests.log`.
- Black check and Ruff on MCP, changed RunStore and tests passed.
- `git diff --check` passed at source checkpoint.

The actual subprocess client covers initialized negotiation, tool discovery,
stored pass/fail/unknown agreement, original manifest/artifact pins, no store
writes, schema/tool/path rejection, hash mismatch and corrupt artifacts, chunk
and page boundaries, protocol recovery/notifications, oversized frame draining,
normalized duplicate finding contexts and bounded actual descriptor growth.

## Source identities

- mcp_server.py SHA-256 `1d2b07f96ef83a4aac1c77b257af0dcc066937534f7a1ebf1715bab403d8f0d4`
- run_store.py SHA-256 `ff725b514071fd8423b11272657391118e12bf50273c11d98ea5eabe457382d8`
- test_mcp_server.py SHA-256 `20cd2b8be379753b0c201ec5136f256ee4670fa50863894705e392283d8cb71d`
- development/mcp.md SHA-256 `63129739b2b7cd5f8e72ee9c2011b22ea838e45b02204c45192e601f3fc09bcd`

## Remaining acceptance

Tests use explicitly synthetic shared contracts. Actual final installed wheel
and a real native-produced retained run must be exercised through a real MCP
client and compared with installed CLI/API/dashboard/editor. Parent owns that
candidate integration. Wider clients/protocol versions/platforms, complete later
measured/history product views and indexed scale remain unqualified. No full
FR-UX-10/AC-12/M7/P8 closure or release claim follows from this source gate.
No commits, pushes, deployment, publication or external messages were made.

An actual installed native-normalized fixture retained 14,983,552 payload bytes,
so the original 8 MiB draft cap correctly rejected it. The preview cap was raised
to a still-finite 32 MiB, preserving bounded descriptor reads, to admit that real
workload. The final wheel must be rebuilt before installed-client acceptance.

## Actual installed native-result client check

Rebuilt final wheel SHA-256
`f05d251bb9aea83becffceb7eb02eab89702f98f871599bb01e7eb712a5840c8`
was installed into `work/cloud-resume/installed-final/core-venv`. An actual local
stdio JSON-RPC client ran outside checkout imports (`python -I`, no PYTHONPATH,
no Git on runtime PATH) over two actual native-normalized retained stores:

- Clean run `bebc6244b06647ee826cfcab6664a3fc`, manifest
  `d15c667128b3f55838e64a82b6f179b85d0b91b59ec78fdd2656a1ca1f3f1ffe`, zero observations.
- Finding run `85fbac87dfc34b04b133550da2802752`, manifest
  `59f02af41a8e4622768b0aee36975aca74319c0603734df8e710451b163ba1c3`, three observations.

Both passed: nine protocol replies per session (initialize/list/seven tool
calls), exact shared CLI run/manifest/assessment/observation/gap agreement,
retained artifact chunks and packaged rule documentation, with store hashes
unchanged. Installed `mcp_server.py` SHA-256
`1d2b07f96ef83a4aac1c77b257af0dcc066937534f7a1ebf1715bab403d8f0d4`
matches the current module. Full pinned request/response transcripts and candidate
identity are in `mcp-installed-clean.json` and `mcp-installed-findings.json`.
These actual executions supersede the earlier installed-limit rejection for
this final wheel. They do not establish every MCP SDK/client, editor host,
indexed scale, platform or release scenario.

## Measured-health transport follow-up

Independent review found that the health tool initially exposed legacy health
and assessment but omitted newly produced measured health. Added a
`measured_health` list copying each retained maintenance_health document plus
original artifact ID/SHA-256 from the shared checked facts; no score is recomputed.
A real normalized fixture with a persisted calculation and missing required
context is exercised through the subprocess protocol, preserving overall null
and the exact stored document/hash. Current MCP suite: **16 passed in 48.87s**.
Updated source hashes are in `client-source-hashes.json`. The earlier installed
f05-wheel transcripts above remain proof for their exact earlier bytes; root
must rebuild and repeat measured transport against the final candidate.
