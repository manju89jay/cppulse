# Public workflow contracts

These version 2.0.0 declarations and result contracts define the installed
workflow boundary. Their test gates do not by themselves establish that every
CLI, renderer or installed integration has passed its separate acceptance gate.
Reading or validating a request does not execute project commands.

## Explicit collection requests

collection_request contains id, source, contexts, plan and ordered normalizers.
Source selects explicit canonical workspace-relative file paths, a subject kind,
inventory_complete and limitations. Completeness is a caller assertion for that
finite inventory, not discovery of new unlisted files. Contexts are existing typed
context documents with checked identity digests; plan is collection_plan v2.
Workspace and output store are explicit runtime arguments.

Each normalizer names a finite built-in kind and normalizer_version 1.0.0.
No arbitrary plugin/module, successful outcome or executable policy field is
accepted. Role selectors contain step_id, role and path. Input/output paths must
be declared by that step; stdout/stderr selectors require a null path. Source,
job, generated-input, binding and duplicate-selection checks run before dispatch.
Actual producer format, byte and execution checks still run after capture.
Coverage binary selectors must also name the corresponding declared test input
and exercised binding. Repeating object/mapping/profile roles cannot manufacture
extra proof and is rejected before execution.

| Kind | Selected data |
| --- | --- |
| native_analysis | One native step, its report/config/registry and optional database/resource inputs, requested files and known packaged rules |
| coverage | Report/configuration/gcov roles, explicit version/proof steps, compiler objects/mappings, runtime profiles and test bindings |
| sanitizer | Named sanitizer, requested files, explicit compiler/inspection version steps, object inspections, link/runtime inspection and test binding |
| gcc_import | Retained input/output/log report, declared source root/scope/context and pinned imported producer metadata |

GCC import remains an import even when its report was captured locally. A
normalizer transforms retained facts; it does not manufacture independent
confirmation. Native normalization cannot repeat for one receipt, coverage
cannot repeat a report/adapter selection, and repeated semantic GCC selections
are refused even if source-scope ordering differs.

## Results and exits

workflow_result identifies the operation, resolved local store, raw and final
RunRefs, optional facts-base/upstream RunRefs, selected derived artifact IDs,
normalizer outcomes, reason and structured error. A RunRef contains run_id,
manifest_sha256, collection status and source_digest. Upstream source identity
remains separate; local derived pins retain the selected source identity.

| Operation | Meaning and exit |
| --- | --- |
| collect | Completed capture/transforms: 0; partial: 3; cancellation: 130 |
| assess | Stored policy passed: 0; known failure: 1; insufficient evidence: 3 |
| compare | Comparison performed: 0, independently of compatible/incompatible/unknown cases and missing application checks |
| baseline | Explicit baseline artifact created: 0, not a policy or certification result |
| check | Passed selected gate: 0; known failure: 1; insufficient evidence: 3 |
| invalid request/selector/schema | Structured error: 2 |

Known failed tests or sanitizer diagnostics can be successfully captured. They
do not turn collection completion into policy acceptance. A completed normalizer
means it produced the named typed artifacts; an unsupported fact can still
explain an unknown result. Missing transform output preserves the raw/last
successful pins and partial status rather than returning success.

check_result explicitly chooses policy or findings mode. Policy mode pins an
assessment and policy digest; finding mode pins a finding comparison and baseline
digest. These selections cannot be mixed. Stale source or generated output is
insufficient evidence with an actionable recollection diagnostic, not invalid
syntax or a proven policy failure. Existing legacy command contracts remain
separate; these result objects do not silently change analyze/report/watch.
Known changed/unverified-input diagnostics require exit 3, and a completed or
passed operation cannot simultaneously carry a fatal error.

## Assessment-only lineage

Public assessment requires an explicit current workspace. Before evaluation and
publication, runtime checks selected source bytes and all retained observed
execution-output bytes. A source-unverified parent cannot be promoted merely by
adding an assessment.

assessment_lineage pins the original unassessed facts base and selected parent,
their exact raw manifest artifacts, the current active policy/assessment, and
generic historical bytes. Only one active policy, assessment and lineage is
allowed. A derived run cannot name itself as its ancestor. Schema validation
checks source identities, raw descriptor digests, active document kinds and
history references; it does not replace opening and validating actual ancestors.

The runtime reopens the original base from the same selected local store by
exact RunRef, requires it to be unassessed, and verifies unchanged source,
contexts, effective configuration and producer-fact descriptors. Unrecognized
lineage, missing bases, changed or added facts cannot silently migrate. Prior
policy/assessment/lineage remain byte-preserved generic history, while the new
active assessment evaluates the policy and expiry at its new explicit time.
Old gates are never reused as current decisions. Adding producer facts or a
consumer comparison remains a distinct workflow and cannot bypass this narrow
assessment-only protocol.

Historical explain/report are read-only. New assessments preserve original
history rather than overwriting files or updating earlier run contents. Local
hash and reference verification establishes integrity, not producer authenticity.
