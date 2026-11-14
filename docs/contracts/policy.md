# Policy and trusted analysis contracts

S5 defines a pure evaluation boundary over retained versioned facts. Contracts
do not authenticate producers, certify software, or turn experimental ranking
into probability. Producer and evaluator integration require separate acceptance.

## Evaluation profile

The descriptive v2 policy schema retains draft future kinds. The explicit
evaluation profile 1.0.0 permits only these predicates:

| Predicate | Core parameters | Required basis for a positive result |
| --- | --- | --- |
| finding_limit | rule_ids, max_findings | Complete requested file/rule consideration in matching typed inventories and linked observations |
| minimum_analysis_coverage | minimum | Matched error-free analysis parse coverage from typed source/job inventories |
| test_outcomes | evidence_ids | Every named result current and usable, with observed counts and selected file/job scope covered |
| required_contexts | contexts | Actual usable observed result coverage in each requested job, including credible observed failures |

Every initial predicate permits an optional nonempty parameters.contexts subset
of the explicit nonempty policy job contexts. required_contexts requires it.
This separates test jobs from analyzer jobs. Missing expected jobs remain unknown;
configuration presence is not proof of execution. Unsupported predicate/profile
versions fail explicitly. Generic metrics and reviewed-evidence evaluation remain
unsupported. Defining a contract does not qualify its producer or integration.

Policies without evaluator_profile retain profile 1.0.0. Explicit profile 1.1.0
adds two typed predicates while preserving the four earlier meanings:

| Predicate | Parameters | Meaning |
| --- | --- | --- |
| minimum_coverage | fact_ids, minimum, measurement_kind, method, optional contexts | Every selected file/job cell must meet the exact covered/total threshold for the named measurement method |
| sanitizer_outcome | fact_ids, sanitizer, optional contexts | Named execution-derived sanitizer facts must bind emitted checks, runtime linkage and actual exercised binary/test scope |

The method and measurement kind are explicit: line, branch and function counts
cannot substitute for each other. No decision or MC/DC coverage is inferred.
Repeated identical complete unit groups deduplicate; conflicting counts or unit
universes remain unknown. The first profile does not merge shards or average
percentages. Missing files, jobs, named facts or zero denominators are unknown.
A known below-threshold cell or credible sanitizer diagnostic may fail while
another gap remains incomplete. That incomplete failure cannot be waived.

Controls link existing typed documents through fact_ids separately from generic
evidence_ids. A definite outcome cannot hide its known required fact links.
Underlying test expiry and every used proof receipt's finish time constrain a
current assessment. Explicit evaluator versions must match the policy profile;
an API override cannot silently upgrade an untagged policy. See verification.md
for the producer proof contracts and current scope limits.

Analysis parse coverage counts matched, error-free parsed file/job cells over
selected policy files multiplied by requested job contexts. It is separate from
detector completion and runtime coverage. Disabling rules can leave parse coverage
at 100 percent while finding_limit remains unknown because requested rules were
not considered. Known partial, failed or skipped parses contribute zero; missing
usable inventory or unverified source/job scope is not manufactured zero.

Scope uses canonical POSIX identities, case-sensitive matching and exclusions
that win. A star matches zero or more non-slash characters, a question mark one,
and a whole-component double-star zero or more directory components. Thus
double-star/slash/star.cpp includes main.cpp and src/main.cpp. Embedded
double-stars in a name are refused; other characters remain literal. Empty scope
is insufficient evidence. Only explicit source-kind applicability yields N/A.

Shared APIs are validate_evaluation_policy(policy, profile_version=None),
policy_scope_paths(policy, files), policy_gate(policy, controls,
source_scope_empty=..., excepted_control_ids=...), and
validate_deviation_request(document). The gate helper computes arithmetic over
outcomes; it is not a predicate evaluator or approval service. Evaluation reads
supplied facts and packaged schemas, without project files, commands, environment
or an implicit current-time lookup.

## Outcomes and gates

Outputs identify evaluator name cppulse.policy and the explicit selected profile,
1.0.0 or 1.1.0. Unknown
identities fail. Untagged older v2 documents remain descriptive archives. Current
unverified source makes both passed and failed raw signals unknown for assessment.
Tagged assessments cannot predate their run or used receipts.

Controls expose requested job context_ids and incomplete. Definite own failure
remains failed when required subfacts are missing, but is incomplete and cannot be
excepted. A known complete failed prerequisite blocks a dependent positive;
definite complete own failure is preserved. Unknown/incomplete prerequisites make
the dependent result incomplete. N/A prerequisites are neutral.

For applicable raw weights P, F and U:

| Value | Definition |
| --- | --- |
| Readiness | 100 P / (P + F + U) |
| Evidence completeness | 100 (P + F) / (P + F + U) |
| Observed satisfaction | 100 P / (P + F) |
| Maximum possible readiness | 100 (P + U) / (P + F + U) |

Zero denominators produce null. Fractions of the string representation of JSON
numbers avoid floating-point threshold and large-weight overflow. Display scores
may use tolerated floats; gates use exact raw control weights. Weights are never
silently clipped.

An unexcepted required failure or an unreachable readiness threshold yields
failed first. Otherwise no applicable weight, empty scope, required unknown or
incomplete results, insufficient completeness, or readiness below a still-reachable
threshold yields insufficient_evidence. Otherwise the gate passes.

Expired evidence cannot support a current positive. A failed test label without
an observed failed testcase remains raw evidence, not a definite waivable defect.

## Scoped exceptions

Per-control allow_deviation defaults to false. Only the named required_controls
gate is initially permitted. Thresholds, control failures, weights and scores
remain unchanged. Requests preserve source/control/context identity, original
reason, owner, reviewer and approval/expiry times. Caller active flags are optional
and never authorize use; activity is recomputed.

An active output explicitly names required_controls, targets a complete failed
control, covers exactly its nonempty aggregate context_ids, matches source and
satisfies approved_at <= generated_at < expires_at. Granular exceptions require
separate controls. Unknowns and incomplete failures cannot be excepted. Owner,
reviewer and reason cannot be blank; those strings do not authenticate a reviewer.
Inactive historical rows can omit the gate and preserve the original reason;
inactive_reason explains their lack of effect.

Observed matching partial analysis can establish that a job context was exercised
without asserting that parsing or detector checks passed.

## Typed execution lineage

execution_facts v2 is actual collector StepResult data with a version and explicit
contract annotation. Legacy debug JSON is never silently promoted. It retains the
exact typed receipt, before/after material facts, output freshness, executable
identity, captured/drained log counts and limitations.

The required binding contains post-freeze verified/invalid/not_collected status,
limitations, explicit input/output path-to-artifact maps and stdout/stderr IDs.
Verified binding means retained observations agree, not command success. Descriptor
hashes/sizes and receipt references must match; generated inputs need an
unambiguous typed ancestor output from a verified, passed, fresh producer in the
same job context that finished before the child started. Changed inputs, failed copies and tool changes
cannot disappear into an earlier successful process exit.

RunStore verifies actual bytes. Pure validation checks supplied identities and
relationships; neither establishes interpreter or complete host/runtime closure.

## Analysis inventory

analysis_inventory v2 binds source, producer, receipt, job context and original
report output plus registry/config/database input IDs. The database is nullable.
It retains exact raw registry SHA, requested files/rules, actually enabled rules
and one row per requested file: observed parse context, native status/errors,
context source/match, completed rules, finding_count and limitations.

Per-file parse contexts are additional observed libclang contexts: actual process
cwd and exact ordered libclang arguments, including every working-directory
override. The receipt job context selects policy jobs. No argument reconstruction
or compiler-option guessing substitutes for the native trace.

Only analyzed, error-free matched rows justify completed requested rule
consideration. Inferred/fallback contexts remain unverified for job claims.
Partial AST findings remain retained even with empty executed_rules; they cannot
establish zero or an inside-limit result. Known enabled nonrequested findings
also remain retained.

New observations identify analysis_inventory_id and match source, producer, file,
parse context and registry rule/version. finding_count includes all known enabled
findings in requested files, and must equal linked observation cardinality.
Dropped normalized rows cannot manufacture zero. Older unlinked observations
remain descriptive.

Original inputs remain generic blobs. A derived typed registry/resource copy
under a new ID must have identical raw SHA and size to its original input.
Semantic reserialization cannot replace raw identity. The first slice requires
unambiguous registry/resource content.

An optional resource_manifest_artifact_id binds a typed resource_manifest v2:
workspace-relative root, explicit file/hash/size list and limitations. Files stay
beneath the root and include include/stddef.h. Listed identities match selected
source and native inputs; all selected native inputs under that prefix are listed.
This fingerprints a finite selected inventory, not discovery of new unlisted
files or all system/runtime dependencies. Unbound resources remain unverified.
The resource role is optional only for unverified inventory rows; matched claims
require the bound selected resource inventory.
