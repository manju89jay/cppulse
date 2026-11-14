# Public local workflow commands

This guide describes the development CLI in `python/cppulse/cli.py` and
`python/cppulse/workflows.py`. It adds explicit collection, current checks and
historical views alongside the existing `analyze`, `watch` and legacy `report`
commands. Experimental analyzer findings and ranking do not establish safety,
certification or production readiness.

Use `cppulse --help` and `cppulse COMMAND --help` from the selected installation.
`python -m cppulse` dispatches to the same CLI. The examples below use placeholder
paths, run IDs and SHA-256 values; replace them with the exact values returned by
your own commands. They are command forms, not claims that those inputs passed.

## Selection and output

`--store` selects a local run store. Commands that evaluate current material also
require `--workspace`. Paths in a collection recipe and source inventory are
canonical workspace-relative identities; command argument paths follow each
step's declared working directory. Store paths use the current local POSIX
boundary. No remote store URL is accepted.

For commands that select a run, omit both pins to resolve the latest attempt
once, or supply both `--run-id RUN_ID` and
`--manifest-sha256 MANIFEST_SHA256`. A single pin is invalid. Explicit pins make
review reproducible even if another attempt later advances the current pointer.
The result includes the selected and derived run/hash references. A collection
can expose both its raw capture and final normalized run; retain both references.

New workflow commands print machine-readable JSON on stdout, with diagnostics
separate on stderr. Collection retains step output as artifacts; normalizer
completion means the named transform was produced, not that its findings or
policy passed. `export-sarif` writes the SARIF document itself to stdout.
`report` writes a file and prints its path, selected pin and format as JSON.

| Command | Executes declared project commands? | Effect |
| --- | --- | --- |
| `collect --request` | Yes, the explicit finite recipe | Retains capture and normalized facts in new runs |
| `assess --policy` | No | Retains a current-time policy assessment over checked original facts |
| `check --policy` | No | Retains that assessment and returns the policy check result |
| `baseline create --request` | No | Retains a scoped finding baseline |
| `check --findings` | No | Retains a separate finding-regression comparison |
| `compare` | No | Retains upstream/local consumer correspondence and local-check gaps |
| `explain` | No | Reads the selected historical snapshot view |
| `report --evidence` | No | Renders the selected historical snapshot view to a file |
| `export-sarif` | No | Exports selected retained native observations |

`check --policy` and `check --findings` are mutually exclusive forms of the same
`check` command. There are no literal `check-policy` or `check-findings`
subcommands.

## Collect an explicit request

```bash
cppulse collect --request /path/to/collection-request.json \
  --workspace /path/to/workspace --store /path/to/run-store
```

A v2 `collection_request` contains `id`, `source`, `contexts`, `plan` and ordered
`normalizers`. `source.files` is a finite selected inventory. Its
`inventory_complete` field is a caller assertion about that inventory; cppulse
does not discover every dependency or automatically add newly created files.
The embedded plan declares argv, working directories, dependency ordering,
input/output files, evidence bindings, timeouts and effective byte/termination
limits. Review that plan before execution. Normalizers select retained roles
from declared steps; accepted built-ins are native analysis, coverage, sanitizer
and GCC import, each at its supported version.

Loading a policy, configuration, source file or request for validation does not
run project commands. The CLI adds no hidden build, test, inventory or version
probe: a required probe must be an explicit recipe step. Normalizers consume
retained facts rather than executing arbitrary plugin/module names. Explicit
commands still execute code chosen by the request; this local workflow is not a
hostile-code sandbox or a complete host-dependency attestation.

A successfully captured failed test or sanitizer diagnostic can coexist with
`collect` status `completed` and exit 0. That describes capture/normalization,
not acceptance. Missing outputs, failed transforms, changed inputs or bounded
capture gaps remain partial with retained pins and reasons. SIGINT records a
cancelled attempt when capture can retain it. Read the result and the facts,
then run the intended check.

Request and plan details are in [public workflow contracts](../contracts/public-workflows.md)
and [the collection contract](../contracts/collection.md).

## Assess or check retained current material

```bash
cppulse assess --store /path/to/run-store --workspace /path/to/workspace \
  --run-id RUN_ID --manifest-sha256 MANIFEST_SHA256 \
  --policy /path/to/policy.json

cppulse check --store /path/to/run-store --workspace /path/to/workspace \
  --run-id RUN_ID --manifest-sha256 MANIFEST_SHA256 \
  --policy /path/to/policy.json
```

Both forms evaluate the selected policy at the current recorded UTC time, with
no build, analyzer or test rerun. `assess` returns a workflow result with its
`policy_gate`; `check --policy` returns `mode: policy`, the assessment artifact ID
and policy digest. Repeating a check recomputes expiry and gate decisions rather
than reusing an old passing assessment.

Assessment-only lineage reopens the original unassessed facts base by its exact
run/hash in the same local store. The selected source inventory and **every
finite generated output recorded in execution facts** must still match their
retained hashes and sizes, before evaluation and again before publication. A
replaced binary cannot inherit tests of its old bytes. This checks the recorded
finite material, not an entire directory, unlisted dependencies or current host
libraries.

Each reassessment creates a new run with one active policy/assessment/lineage.
Original producer facts and the original execution window remain unchanged.
Previous exact policy, assessment and lineage bytes become generic historical
artifacts; they cannot silently become the new active decision. An unverified
historical/imported claim cannot be upgraded to local execution merely because
today's files happen to match.

Changed source or a missing/replaced observed output returns insufficient
evidence with `STALE_SOURCE` or `STALE_OUTPUT`, exit 3, and an actionable reason.
Where a compact attempt can be published, latest-attempt advances to a new
partial, unverified gap linked to the exact historical parent. It has no copied
active assessment. Thus an unpinned `explain` or evidence report shows the gap
rather than the old green gate. The previous pinned run remains available for
historical reading. Recollect the changed material before seeking a current
positive check. Integrity, quota or publication errors remain explicit errors;
a retained historical positive is never a substitute for a failed current check.

The supported evaluator profiles and predicates are documented in
[policy evaluation](policy-engine.md). Unsupported evaluators or malformed
policies are invalid input, not a failed source-code requirement.

## Create and check a finding baseline

```bash
cppulse baseline create --store /path/to/run-store \
  --workspace /path/to/workspace \
  --run-id FACTS_RUN_ID --manifest-sha256 FACTS_MANIFEST_SHA256 \
  --request /path/to/baseline-request.json

cppulse check --store /path/to/run-store --workspace /path/to/workspace \
  --run-id CURRENT_RUN_ID --manifest-sha256 CURRENT_MANIFEST_SHA256 \
  --findings /path/to/finding-check-request.json
```

A baseline request selects a nonempty explicit `scope_files`, `context_ids` and
`rule_ids`, plus a new `baseline_id` and reason. Creation retains a reviewed
reference; it neither suppresses observations nor asserts a passing policy.
Reuse of an already-retained baseline ID is rejected. Baseline and comparison
workflows require current verified, unassessed material; select the original
facts run if the latest run already has an active policy assessment.

A finding-check request selects the same finite dimensions, `max_new`, and an
exact baseline artifact. Its reference is either a local store/run/manifest
SHA/artifact ID or a transfer bundle/root/manifest SHA/artifact ID. There is no
implicit latest baseline. Optional rename mappings are explicit one-to-one path
mappings; optional suppression inputs are separately selected and retained.
Relative baseline/bundle/suppression paths in the request resolve from that
request file's directory.

The `native-line-anchor-1` strategy compares exact retained diagnostic-line
bytes and occurrence identities while excluding the line number. A unique
unchanged line can survive an insertion above it. Repeated lines, unavailable
anchors, changed tool/configuration/registry/parse context or unsupported
relocation remain unknown. A rename map does not rewrite detector context or
infer C++ semantic equivalence. Duplicate observations remain occurrence
multisets, so two equal findings becoming three records one additional finding.

The finding gate fails when known unsuppressed new occurrences exceed
`max_new`. Otherwise incomplete, incomparable or empty scope remains
insufficient evidence. Only a complete comparable result within the threshold
passes. Missing old findings are resolved only with complete current
consideration of the selected rules/files/jobs. A known new finding can fail a
partial check while the incompleteness remains visible.

Finding suppressions are exact, bounded and expiring requests for the
`finding_regression` gate. They reduce `unsuppressed_new` only; raw observations,
new counts, policy results and missing coverage remain visible. Owner and approval
fields are unauthenticated claims. A finding-check pass is distinct from a
policy pass, and neither implies absence of all C++ defects. See
[finding workflows](finding-workflows.md) and
[finding request contracts](../contracts/finding-workflows.md).

## Compare upstream consumer evidence with local material

```bash
cppulse compare --store /path/to/local-run-store \
  --workspace /path/to/local-workspace \
  --run-id LOCAL_RUN_ID --manifest-sha256 LOCAL_MANIFEST_SHA256 \
  --upstream-bundle /path/to/upstream-bundle \
  --upstream-root-id UPSTREAM_ROOT_ID \
  --upstream-manifest-sha256 UPSTREAM_MANIFEST_SHA256 \
  --upstream-subject-id UPSTREAM_SUBJECT_ID \
  --local-subject-id LOCAL_SUBJECT_ID \
  --upstream-matrix-id UPSTREAM_MATRIX_ID \
  --local-matrix-id LOCAL_MATRIX_ID
```

The explicit bundle root and manifest pin are checked before deriving the local
comparison. Local source and all recorded generated outputs must still match;
select an unassessed local facts run. Original upstream source identities and
bytes remain separate from the local source namespace. Imports remain
unauthenticated claims and do not supply local execution, source freshness,
application testing or policy acceptance.

Exit 0 with `completed` means the comparison artifact was created. Inspect its
compatible/incompatible/unknown correspondence, mismatches and required local
checks separately. A configuration mismatch does not mean a local build failed;
a compatible configuration does not mean the consumer tests passed. This
command performs metadata comparison without running those tests. See
[consumer applicability](consumer-applicability.md) for the qualified direct
GCC/GNU-linker slice and its finite package-use proof.

## Read historical results and export observations

```bash
cppulse explain --store /path/to/run-store \
  --run-id RUN_ID --manifest-sha256 MANIFEST_SHA256

cppulse report --input /path/to/run-store --evidence --format html \
  --run-id RUN_ID --manifest-sha256 MANIFEST_SHA256 \
  --output /path/to/evidence-report.html

cppulse export-sarif --store /path/to/run-store \
  --run-id RUN_ID --manifest-sha256 MANIFEST_SHA256 \
  --comparison-artifact-id COMPARISON_ARTIFACT_ID > /path/to/findings.sarif
```

`explain` and `report --evidence` use the checked snapshot view and optionally
select an active typed assessment with `--assessment-artifact-id`. They verify
retained artifact integrity but do not inspect today's source or re-evaluate
policy expiry. Historical gates retain their recorded evaluation time. A
missing assessment stays unassessed; partial and cancelled attempts remain
visible. Explicit historical selection never upgrades that result to a current
source claim.

Evidence reports support JSON, HTML and optional PDF. The default filename is
`evidence-report.FORMAT`; pinned runs default to
`derived/RUN_ID/evidence-report.FORMAT`. Output cannot overwrite immutable run
contents, staging or store metadata. Rendering writes the requested derived
file without changing the selected run or latest pointers. PDF requires the
optional PDF dependencies and host libraries. The legacy report mode remains
separate. See [snapshot presentation](snapshot-presentation.md).

`export-sarif` emits SARIF 2.1.0 directly on stdout and leaves the store unchanged.
Without a comparison selector it exports the selected typed native observations.
With `--comparison-artifact-id`, the selector must name a checked typed
`finding_comparison` retained in that snapshot; arbitrary caller-supplied
baseline labels cannot annotate results. Exported occurrences include accepted
finding suppressions and separate old/new fingerprint keys. Unknown matches
have no invented baseline state. Zero SARIF results are not proof of clean
analysis; selected-scope completeness, import origin and warnings remain
explicit. Export performs no upload and no fresh source check.

## Exit codes and verification boundary

For the new collection/assessment/check/baseline/comparison workflows:

| Exit | Meaning |
| --- | --- |
| `0` | Collection, baseline or comparison operation completed; for assessment/check, the selected gate passed |
| `1` | The selected assessment/check gate has a known failure |
| `2` | Invalid request, selector, unsupported schema/version or CLI usage |
| `3` | Partial or insufficient evidence, changed/unverified current material or an integrity/operational gap |
| `130` | Cancellation |

Read the operation, mode, status, reason and pins with the code. Completion of a
capture/transform/baseline/comparison is deliberately separate from an
assessment or finding-regression pass. Historical export/render success means
that view was produced, not that a gate passed now.

The following retained gates were inspected for this guide; they overlap and
must not be summed into a unique test total:

| Evidence log under `review/autonomous/logs/` | Observed result and scope |
| --- | --- |
| `s7-collect-producer-tests.log` | 24 passed: finite collection/normalizer and request-boundary cases |
| `s7-core-workflow-tests.log` | 35 passed: retained assessment/reassessment, expiry, stale material and capture cases |
| `s7-finding-cli-tests.log` | 9 passed: CLI selection/exits, stale latest-attempt, finding baseline/check, read-only SARIF and SIGINT cases |
| `s7-owned-workflow-tests.log` | 44 passed: refreshed collection, assessment, actual normalizer routing, findings, CLI and request-boundary tests |
| `s7-compare-workflow-boundary-tests.log` | 6 passed: exact import pins/namespaces, current source/output gaps, publication race and metadata-only CLI comparison |
| `s7-finding-producer-related-final.log` | 289 passed: finding producers and related contracts/workflows |
| `s7-sarif-retained-independent-final.log` | 4 passed: checked comparison lineage and retained SARIF annotation cases |
| `s7-evidence-report-tests.log` | 12 passed: explicit evidence formats, historical pins and protected output paths |

These tests include clearly labeled synthetic records and local fixture
processes. Their success does not establish every real project, installed wheel,
Docker path or compiler variant. The exercised cloud host is Linux x86_64,
Python 3.12.14, glibc 2.41, GCC 14.2 and libclang 19. Windows/macOS and other
combinations remain unqualified; Docker/Compose was unavailable in this host.
Fresh installed-candidate and actual C++ acceptance evidence must be reviewed
separately for the exact artifact bytes. No commit, publication or remote write
is implied by these local commands.
