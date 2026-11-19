# C++17 isolated proposal validation — P11/M9-02 sub-specification

Status: the initial private contract and explicit isolated runtime are implemented.
This separate finite behavior-validation lane does not mark M9-02 or P11 accepted.
The full reviewed production acceptance matrix remains open.
No external model provider, new budget, source application, branch/commit, PR,
message, deployment or network integration is authorized by this workflow.

## First language and behavior scope

The initial lane is an explicitly selected ordinary C++17 CMake/CTest project on
the exercised Linux/GCC14/CMake-CTest3.31.6 toolchain. A selected before run has
verified finite source identities and actual usable test outcomes, including at
least one failed selected test. The proposal changes only declared production
source files; CMake, test sources, scripts, verification controls and their
identities remain protected. Tests cannot be weakened or omitted to obtain a
passing result. Unsupported tools/languages, empty/skipped/unusable tests and
unknown provenance are explicit incomplete/invalid outcomes.

A provider-neutral proposal is caller-supplied pinned replacement text with an
inspectable diff. Origin records separate an actual agent-authored proposal from
a human claim or synthetic test fixture. An agent name/transcript digest does
not authenticate authorship. The actual agent acceptance example must be produced
by a clean collaboration session over retained source/test evidence; a scripted
replacement or an authored stub cannot be labeled that example. This uses the
existing authorized task budget, not a new remote model API or provider account.

## Required contracts

A private versioned request identifies the original run/hash and source digest,
exact selected source files, editable production subset, protected verification
files, selected before test-evidence ID and required case names/properties,
explicit collection-plan artifact and its contexts, proposal origin and each
old-file SHA/replacement bytes. All paths are finite canonical relative paths.
No symlink, traversal, duplicate/colliding identity, unlisted file, command string
or implicit shell interpretation is accepted. Payload, file, step, log, time,
artifact and attempt bounds are explicit and validated before any project command.

The result references the original before run and a fresh after-source snapshot,
new source digest, actual new execution receipts/evidence and exact observed test
outcomes. Statuses distinguish selected-test pass, known verification failure,
incomplete evidence, invalid request and cancellation. Every result states
`semantic_equivalence:not_established` and caller-declared test-adequacy limits.
A test pass is an observation, not approval to apply the proposal.

## Execution and ownership

1. Open the exact original immutable run with a finite read budget; reject stale
   current finite source/generated artifacts and unsupported/inadequate before
   test evidence. Preserve original receipts byte-for-byte.
2. Validate the full request and proposal before executing code. Reopen protected
   source/test/control artifacts by retained IDs and byte hashes, not caller
   basenames. Proposed replacements cannot touch those protected controls.
3. Allocate an exclusively owned disjoint workspace/attempt directory. Copy only
   selected retained source bytes, with no `.git`, symlinks or unrelated files.
   Apply the proposal only to that owned after copy; the original project and
   original run store remain unchanged.
4. Construct new observed invocation contexts for the copy. Reuse the existing
   typed collection/execution/test-adapter contracts and explicit argument-vector
   plan; never relabel an old receipt as new execution. Bind after-source bytes to
   the actual configure/build/inventory/test operations and generated artifacts.
5. Run only the explicitly selected trusted verification recipe with finite
   supervision. The initial lane uses the reviewed CTest/JUnit/log/inventory
   bindings so process success, forged reports, zero tests or skipped cases alone
   cannot supply a positive test result. This is not a hostile-code sandbox.
6. Require unchanged protected controls, the same required actual case identities,
   positive executed counts, no skipped required cases and known passing outcomes
   for a selected-test pass. Retain observed failures even if other evidence is
   incomplete. Do not infer coverage, sanitizer instrumentation, ABI/performance
   or unrestricted behavior equivalence from ordinary tests.
7. Publish a complete local result atomically and retain source/patch/receipt/
   report artifacts. Cancellation/crash/write interruption must preserve valid
   committed partial facts and distinguish the interrupted attempt. A subsequent
   explicit retry creates fresh execution; no stale passed result is reused.
8. Prepare local PR-review metadata only (source pins, diff, before/after test
   references, limitations and unresolved work). There is no branch/commit/PR,
   model call, external message or automatic source application action.

## Acceptance and counterexamples

Contracts fail first for unknown/duplicate IDs, unsafe or symlink paths, changed
source/tool/control bytes, unsupported producer versions, edits to tests/build
controls, missing actual before failure and unavailable evidence. Meaningful
actual C++ cases include a failing boundary behavior repaired in the owned copy,
unchanged clean behavior, invalid/noncompiling proposals and fresh source digests.
The isolated source must remain unchanged after both successful and failed runs.

The workflow must also exercise zero/all-skipped tests, report/actual-execution
mismatch, wrong/missing cases, stale source, worker crash/timeout/cancellation,
interrupted publication and explicit fresh retry. Tests with unavailable outcomes
remain incomplete rather than positive. Actual installed invocation and a clean
agent-authored proposal transcript are required separately from unit fixtures.

Full M9-02 acceptance also needs reviewed real language-specific cases and all
applicable public-client/platform/scale/installation gates. Missing provider,
authentication or adequacy evidence remains named work, not invented proof.

## Current explicit interface

`python -m cppulse.semantic_repair --store STORE --workspace SOURCE --request
REQUEST.json --output-root EXISTING_DISJOINT_DIRECTORY --execute-trusted-project`
executes only after the explicit trust flag and finite private request validation.
The original pinned plan must use exactly five configure/build/version/inventory/
test steps, CMake `-DCMAKE_CXX_STANDARD=17`, required standard and extensions off,
CTest3.31.6, at most two jobs and 30 seconds per step. Output directories must be
outside the original finite source and original run store. The request records
editable/protected partitions, selected actual case names, old hashes, whole-file
UTF-8 replacements, declared adequacy and origin evidence digest. Tool hashes
must match observed before execution; tool runtime/host/compiler dependency
closure is not established.

Every attempt retains its source copy, original pinned request, reviewable Git
unified diff, fresh actual run store and atomic `result.json`. The result's
request/diff hashes identify those artifacts. Return values are 0 for selected
cases passed, 3 for known verification failure, 4 for incomplete execution and
130 for cancellation; invalid selection exits 2. These values cannot authorize
application or claim equivalence. Reading/validating a proposal executes no code.
The initial runtime reuses actual `collect` receipts and reparses retained raw
JUnit and CTest execution logs with the existing adapters, so mismatched imported
counts, zero/skipped cases and ordinary process success cannot supply a pass.

Tests cover failed-before/passed-after, wrong behavior, actual crash, invalid
compilation, cancellation with distinct fresh retry, interrupted worker recovery,
unsafe/stale/symlink source, unknown paths/cases, protected-control edits and
result tampering. Actual timeout, zero/all-skipped before and installed execution
are separate evidence, rather than inferred from test doubles. A real clean
fork-none proposal author inspected retained source/receipt/JUnit/log bytes and
produced the clamp boundary proposal under `work/semantic-actual`; synthetic unit
fixture requests explicitly keep `origin.kind:synthetic_fixture`.

Installation uncovered a genuine dependency failure: Python wrapper CMake/CTest
commands required a repository PYTHONPATH entry. That incomplete attempt is
retained. A fresh before receipt selecting the actual native CMake/CTest binaries
preserves the same source digest and cases and permits installed `-I` execution
without repository import overrides. This repairs the execution recipe rather
than changing an old receipt or promoting the failed attempt.

Remaining full-plan work includes independent runtime review, public-client
integration, broader language/configuration/property adequacy cases, all required
resource/platform/scale gates and review of local PR metadata semantics. The
runtime is a selected trusted-project executor with job/wall/log bounds, not a
hostile-code or memory/CPU/network isolation guarantee. No remote agent/model
provider, Git application, branch, commit, PR publication or message is performed.
