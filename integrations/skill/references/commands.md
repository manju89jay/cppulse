# Candidate commands and prerequisites

These are existing public candidate commands. Replace placeholders with explicit
local paths and retained identities. Follow `cppulse COMMAND --help` if an
installed version differs; do not guess unsupported switches. Command metadata
for mechanical compatibility tests is in [commands.json](commands.json).

| Operation | Public command |
|---|---|
| Capability/version negotiation | `cppulse --version`; `cppulse capabilities` |
| Native/optional prerequisite probe | `cppulse doctor` |
| Effective settings | `cppulse config --repo PROJECT` |
| Explicit editable configuration | `cppulse init --repo PROJECT` |
| Static analysis | `cppulse analyze --repo PROJECT --output STORE --format html --compilation-database DATABASE` |
| Explicit finite collection | `cppulse collect --request REQUEST --workspace PROJECT --store STORE` |
| Pinned historical explanation | `cppulse explain --store STORE --run-id RUN --manifest-sha256 HASH` |
| Current retained-material policy check | `cppulse check --store STORE --workspace PROJECT --run-id RUN --manifest-sha256 HASH --policy POLICY` |
| Current retained-material assessment | `cppulse assess --store STORE --workspace PROJECT --run-id RUN --manifest-sha256 HASH --policy POLICY` |
| Pinned evidence HTML | `cppulse report --input STORE --evidence --run-id RUN --manifest-sha256 HASH --format html --output REPORT` |

Compilation database support is named `--compilation-database` in this candidate.
The historical proposed `--compile-commands` examples are not the installed
interface. Collect uses `--request`, not the earlier proposed `--recipe` option.
Explain selects a retained snapshot; it is not a rule-ID lookup command.

Before collecting, the request must already identify finite selected contexts,
commands, inputs, outputs and bindings accepted by the installed request schema.
A policy is data and launches no commands merely by being read. This text package
does not supply project-specific build recipes, a compiler, CMake or native
libraries. Use installed release instructions for those prerequisites.

Optional read-only MCP preview: explicitly start the matching installed Python
with `python -m cppulse.mcp_server --store STORE`. It implements protocol
2024-11-05 over local stdio, with strict schemas, pinned historical selections,
finite payload/page/chunk limits and no execution tools. It is not an indexed
large-project query service or proof of compatibility with every MCP client.
