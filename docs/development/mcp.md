# Local read-only MCP preview

An explicit optional indexed findings mode now supports large retained prototype
reports without opening every original artifact. The default mode described
below keeps its existing no-write tool set. To advertise `indexed_findings`,
supply a separate writable cache outside the source store:

```sh
python -m cppulse.mcp_server --store /absolute/path/to/output --query-cache /absolute/path/to/query-cache
```

Initialization and tool listing create no cache. Calling `indexed_findings` may
build/reuse only that configured cache; original source-store heads stay
unchanged. Arguments use explicit run/hash pins, optional artifact_id (default
findings), page/per_page (maximum100), category, exact file and literal message
text. The response states `read_scope: selected_artifact_only`,
`analysis_cache_eligible: false`, original/derived pins and historical limitations.
Unrelated artifact bytes and ignored metadata semantics remain unverified.
`--query-limits` accepts a complete small private index limits JSON object for an
explicit supported profile, including the32MiB ignored-array-element profile.
See [the indexed consumer contract](../contracts/indexed-findings-mcp.md).
This mode does not expand the existing normalized-observation `findings` tool,
make native/source-freshness claims or close installed/scale/P14 acceptance.

Start explicitly against an existing retained run store:

```sh
python -m cppulse.mcp_server --store /absolute/path/to/output
```

Use the installed Python interpreter containing cppulse. Source-tree development
uses `PYTHONPATH=python .venv/bin/python -m cppulse.mcp_server --store ...`.
No web, PDF, ML, Node process, account or network service is required. This
module is a local stdio MCP server, not an HTTP listener. It implements MCP
`2024-11-05`, newline-delimited JSON-RPC 2.0, initialization, ping,
`tools/list`, and `tools/call`. Configure a client command with separate argv
entries; do not interpolate paths into a shell command.

Every retained-result tool requires both `run_id` and `manifest_sha256`, copied
from an explicitly selected retained run/pointer. The server never resolves a
mutable latest pointer on a tool call. It rejects mismatched hashes, unsafe
store paths, changed artifacts and unsupported contracts through the shared
checked run reader. A retained result is historical: every response labels
`selection: historical-pinned` and `current_source_verified: false`. Reading
an old passed assessment does not make it a fresh current-source check.

| Tool | Read result |
|---|---|
| `run_status` | Stored status, source/config/manifest identities, contexts, stages and limits |
| `health` | Stored legacy health, measured_health documents with original artifact hashes, and the same exact assessment display used by reports; missing health remains null |
| `findings` | Every retained normalized observation occurrence (prototype fallback), in stored order |
| `hotspots` | Stored experimental hotspot ranking; no independent scoring |
| `policy_gaps` | Shared presentation gaps, including failed/unknown controls |
| `documentation` | Packaged rule metadata by rule ID, or retained typed policy by artifact ID |
| `artifact` | Original UTF-8 artifact byte chunks by exact artifact ID, with whole-artifact SHA-256 |

Tools never launch analysis/build/test commands, evaluate a new policy, change
source, publish a run, or write store state. There is no execution capability.
Unknown tool names and extra arguments are rejected. Original artifacts may
contain project content: select a store that the local MCP client is authorized
to read. Merely loading this server does not grant access to other stores.

A call example after initialization:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"policy_gaps","arguments":{"run_id":"selected-run","manifest_sha256":"<64 lowercase hex characters>","offset":0,"limit":25}}}
```

The actual `tools/list` input schemas are authoritative. Page offset is an
integer within the pinned immutable run; page size is 1–100, default 50.
`next_offset` is null at the end. Repeat the exact run/hash and tool arguments
for later pages. Artifact offsets and limits are **bytes**, with a 32 KiB maximum
chunk (16 KiB default). Select UTF-8 boundaries; binary data and chunks splitting
a codepoint return an actionable error. Artifact names are retained IDs, not
arbitrary filesystem paths.

This is a finite preview using the shared in-memory snapshot projection, with an
32 MiB manifest-plus-artifact payload workload limit, enforced before artifact reads and on every bounded descriptor read. It is not indexed large-project
paging. Requests are capped at 64 KiB and responses at 512 KiB. Excess responses
fail explicitly; choose a smaller page/chunk. Later indexed history/query and
large-project qualification remain P5/P8 work. No Windows/macOS/native-platform
support, universal MCP-client compatibility or release qualification is inferred
from Linux source tests.

The test client opens the real server subprocess and exchanges protocol frames;
it verifies stored pass/fail/unknown agreement and original pins, corruption
rejection, strict tool schemas, protocol errors, bounded frames/chunks/pages and
no store writes. Its fixtures are synthetic contract fixtures, not native
analysis accuracy or final installed-client proof:

```sh
PYTHONPATH=python .venv/bin/python -m pytest -v tests/test_mcp_server.py
```

Final P8 acceptance still needs the packaged installed server connected to the
same actual native run as installed CLI/API/dashboard/editor, plus the larger
client and platform matrix. A server source file or transport test does not close
FR-UX-10, AC-12, AC-16 or all M7 work.
