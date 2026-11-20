# Explicit collection plan contract

Status: S4 contract foundation. The schema and pure validator define declarations;
they do not execute a build, establish an assessment gate or implement a public
collection command. Producer acceptance requires the execution and artifact checks
below in addition to schema validation.

`collection_plan` uses exact version `2.0.0` and packaged draft-07 references.
Unknown fields, versions, adapter names and unsupported limit options fail. A plan
contains one existing v2 `recipe`, explicit evidence `bindings` and effective
`limits`. Source inventories and full compiler-context objects are supplied
separately and retained in the run manifest. Merely loading a plan, analyzing
sources or reading a policy must never execute its commands.

| Field | Meaning |
| --- | --- |
| `id` | Unique selected plan ID within one run |
| `recipe` | Explicit argv, working directories, context IDs, dependency DAG, file inputs/outputs and per-step timeouts |
| `bindings[].id` | Intended evidence ID, unique across plans in a run |
| `bindings[].step_id` | A step in this plan's embedded recipe |
| `bindings[].kind` | `build` or `tests`; other adapters arrive through a reviewed extension |
| `bindings[].scope_files` | Nonempty selected source-file identities; declaration is not dynamic coverage |
| `bindings[].exercised_inputs` | Nonempty actual artifact paths to bind: declared outputs for a build, declared inputs for tests |
| `bindings[].report_path` | A declared test output path; null for build bindings |
| `bindings[].execution_log_path` | Distinct declared actual CTest execution-log output; null for builds |
| `bindings[].adapter` / `adapter_version` | `ctest-junit` / `1.0.0` for tests; both null for builds |
| `bindings[].inventory_step_id` | Same-context ancestor step recording explicit CTest command inventory; null for builds |
| `bindings[].producer_version_step_id` | Distinct same-context ancestor step recording actual CTest version; null for builds |
| `limits.max_log_bytes` | Combined retained stdout and stderr bytes per step; positive integer, at most 64 MiB |
| `limits.max_artifact_bytes` | Positive per-file cap for source/output/log/report snapshots, at most 256 MiB; effective default 64 MiB |
| `limits.max_metadata_bytes` | Separate positive per-file cap for cppulse-authored control JSON and manifest, at most 64 MiB; effective default 16 MiB |
| `limits.termination_grace_seconds` | Positive grace interval before forced process-group termination |

All four effective limits are required in persisted JSON. A CLI may materialize
documented defaults before validation, but an old plan is never silently rewritten
to adopt new defaults. At most 32 concurrent jobs are supported by this plan
version. Plain v2 recipes retain their existing shape. These limits do not claim
a memory quota, a total disk quota, streaming run-store copies or a hostile-code
sandbox. Initial process-group collection support is POSIX; platform support still
requires actual installed execution.

JSON Schema permits integer-valued numbers such as `4096.0` for integer fields.
Runtime readers normalize those bounds to local integers after validation; the
retained plan and its configuration digest preserve the original supplied data.
Snapshot and metadata caps are distinct; generated JSON has no silent exemption
from a recorded bound. An insufficient metadata budget must fail clearly before
execution where predictable, or retain an incomplete/private attempt if required
facts cannot be published within the bound. It must never publish truncated JSON
as a valid contract.

## Path and identity rules

`cwd`, `inputs`, `outputs`, report paths and artifact paths are workspace-root
relative, regardless of the step's working directory. `cwd` may be `.`; file
identities may not. The recipe's argv is passed as an argument vector with no
implicit shell interpretation; argv-relative filenames follow the selected cwd.
Paths supplied to the collector API for the workspace, run store and private log
directory are separate invocation inputs, not embedded session paths in the plan.

The contract rejects absolute/drive/backslash paths, traversal, aliases, control
characters, Windows reserved components and trailing dots/spaces. Spaces inside a
component and Unicode names remain data. Outputs cannot overlap each other,
case-folded aliases, working-directory file identities, Git metadata or selected
source files/directories. Filesystem symlinks, regular-file types and actual path
containment still require producer checks; a pure validator cannot inspect them.

A generated input must refer to an ancestor step's declared output in the same
context; this first slice cannot relabel a GCC artifact as a Clang artifact.
Every other input must be in the selected source inventory. Every scope file and selected
context resolves against the manifest. Every recipe context has a declared step;
this does not mean its verification passed. Output writers, plan IDs, recipe IDs
and evidence-binding IDs must be unambiguous across multiple plans in one run.
Step IDs remain local to their recipe. Do not also retain the same embedded recipe
as a standalone recipe artifact with a duplicate ID. Cross-plan generated inputs
are unsupported; use one explicit recipe DAG for dependent work.
If an observed evidence record uses a binding's ID, its execution origin, kind,
context and declared source scope must match that binding. A plan alone is not
an assertion that its intended evidence has been collected.

Explicit environment entries cannot have empty, NUL or `=` names or NUL values.
Names containing token, password/passwd, secret or API-key patterns are refused so
recognized credential values are not retained in a plan. This is a limited name
filter, not comprehensive secret detection. The collector must not serialize its
whole inherited environment. Exact user-selected argv and bounded logs are private
local run artifacts; diagnostic export does not include them automatically.

## Validation and persistence API

```python
from cppulse.contracts import validate, validate_bundle
from cppulse.identities import digest_json

validate("collection_plan", plan)  # Pure; no target commands or filesystem reads.
manifest["config_digest"] = digest_json(plan)
validate_bundle({"run_manifest": manifest, "collection_plan": plan})
# A singleton list has the same meaning and digest:
validate_bundle({"run_manifest": manifest, "collection_plan": [plan]})
```

For multiple plans the digest projection is
`{"collection_plans": sorted(plans, key=lambda plan: plan["id"])}`. This makes bundle
input order irrelevant while preserving every argv, dependency list and effective
bound within each plan. Source/context identities remain independently validated.
The run store must retain the exact effective plan with contract
`{"kind": "collection_plan", "version": "2.0.0"}` before publication. Changing any
limit or binding changes the configuration digest.

The complete declaration fixture in `tests/test_collection_plan_contract.py`
contains five explicit steps: configure, build, `ctest --version`,
`ctest --show-only=json-v1`, and tests. The inventory and version steps must be
distinct ancestors of the test step in the same context. Inventory inputs must
include every selected exercised artifact. Its test command runs from `build` with
argv `ctest --output-junit junit.xml`; its declared report is `build/junit.xml`.
Its distinct declared actual execution log is
`build/Testing/Temporary/LastTest.log`.
Its binding includes the actual selected `build/app` artifact. This illustrates
identity semantics; the contract fixture is not a claim that these commands ran.

## Producer obligations and outcomes

The runner must check executable availability, cwd, declared inputs, safe outputs,
bounded logs, timeouts and cancellation, and retain the actual command, tool
identity/version, start/end time, terminal status and logs. Inputs and exercised
artifacts must be fingerprinted before and after execution. Retained snapshots
must respect `max_artifact_bytes` before memory-backed copying; authored JSON and
the manifest must respect `max_metadata_bytes`. Oversize or changed files produce
explicit unavailable/partial results. Independent completed facts
remain available when another context fails or is cancelled.

A zero exit code is an execution fact. Positive build/test evidence additionally
requires retained, nonempty declared artifact binding and verified source/context
identity. A header or package listed in a declaration does not by itself establish
that a consumer exercised it. Generic JUnit does not authenticate its producer or
prove which binary ran. The supported execution producer must parse retained
version/inventory stdout, verify that all three steps resolved the same actual
CTest executable hash, and compare JUnit cases with both inventory and actual
run-command records from the supported CTest execution log. A pre-run inventory
alone describes intention: a different test directory or a modified generated
test definition can run another command under the same case name. Actual command
and working-directory records must be parsed outside captured test output and
bind every selected binary path with unchanged before/after fingerprints.
A version or inventory probe is an explicit recipe step; loading a plan never
adds or runs a hidden probe. Imported reports retain import origin and cannot
invent a cppulse-observed receipt.

Keep execution and evidence outcomes separate:

| Observation | Required interpretation |
| --- | --- |
| Command exits zero, required output/report missing | Passed receipt; missing/error evidence and operationally partial collection |
| Build/test command returns a normal nonzero result | Failed receipt; credible observed failure remains usable with its retained scope/artifacts |
| Valid report records failures despite zero process exit | Passed process receipt, failed test evidence; retain exact counts |
| Valid zero-test or all-skipped report | Exact counts and skipped evidence; never passed verification |
| Missing/malformed/unsupported report | Unavailable evidence; omit unknown receipt test counts rather than inventing zeros |
| Signal, timeout or cancellation | Explicit operational status and partial/cancelled run; dependent work is skipped/unattempted with reasons |
| Source/artifact changes during collection | Preserve raw facts with stale/unverified binding; no current positive evidence or latest-completed promotion |

The `ctest-junit` adapter version describes cppulse's supported normalization
contract, not an invented JUnit specification version. Raw reports and actual
producer metadata must remain retained. Policy evaluation of these facts belongs
to S5; `run_manifest.status=completed` describes collection completion, not passing
tests or an accepted policy gate.
