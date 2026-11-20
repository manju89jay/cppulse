# Separate service profile per-process resource checkpoint

The full production program remains incomplete. All changes remain uncommitted.
This slice extends the separate service lane; the ordinary CMake/CTest semantic
repair profile and version0.1.0 service schemas remain unchanged.

Version0.2.0 uses explicit build/test CPU soft/hard limits and address-space byte
limits. Null preserves inherited limits. The selected sealed supervisor records
requested, inherited and actual limits, its PID, selected step ID and exact
selected exec argv before exec. Setup failure exits125 without executing the
project. Per-step resource files are exclusive, retained and linked into exact
original progress rows and the report artifact inventory. Replay verifies the
actual limits, OS soft/hard ordering, step/argv identity and build/test-only
scope. Inspection steps cannot claim project limits.

Current producer/request/report/helper sources and tests were stable across
**67 passed, no skips,86% combined statement/branch coverage**. This includes all
35 prior v1 cases,21 v2 cases and11 independent review cases. Ruff passed.
`service-resources-evidence/sourcebound-check.json` records exact commands and
source hashes; coverage is retained without claiming every file reaches86%.
Independent review separately passed30cases with stable hashes and68 selected
actual artifact pins, retained in `service-resource-independent-review/`.

Three material replay defects were independently reproduced and repaired:
invalid OS soft/hard pairs, swapping resource observations between different
steps/PIDs, and attaching project-resource observations to service inspection.
Meaningful initial contract and independent red logs remain retained; no
acceptance assertion was weakened. A later version-dispatch regression on
non-object JSON was also retained as three genuine CLI failures, then repaired
with object-type guarding; all three now return2 without creating output. The
final67-case gate includes that delta at current source hashes.

Separate actual controlled native observations are pinned by source/executable
hashes and actual return codes: CPUsoft1/hard2 with a soft handler exits78;
ignore-soft observes hard termination(-9);64MiB RLIMIT_AS rejects128MiB allocation
(exit42), while the inherited-limit control succeeds(exit0). Receipt contents,
raw streams, commands and observed outcomes are retained. The producer also
executes its genuine ten-step finite pair with checked resources: before2cases
pass/1fails; after3pass, all selected cases run. The current real Poco repair
pair/upstream30-case observations belong to the preceding v1 source epoch;
these new resource controls do not retroactively qualify that older execution.

These are Linux per-process limits inherited by children, not aggregate CPU,
RSS, PID, cgroup, storage, network or hostile-project isolation. Conservative
global CPU/memory/cgroup qualification flags remain false; per-step receipts are
the precise scoped observation. SIGKILL alone does not diagnose an arbitrary
process death. Helper/runtime closure, full installed v2 artifacts, broader
service/property/platform matrices and full P11/M9 adequacy remain open.

The exact mandatory command was rerun:
`/workspace/cppulse/.venv/bin/python scripts/verify_delivery.py --require-complete`
returned **3**, completefalse,187items retained,120open/65active/2blocked. The
record includes all current IDs/states, unchanged requirement-definition digest
and all phases. No requirement state was changed for this checkpoint, and no
commit, push, remote update, deployment, publication or third-party message ran.
