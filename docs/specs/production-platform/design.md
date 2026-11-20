# cppulse Production Platform Design

Status: Proposed
Specification version: 1.0
Date: 2026-11-04

This design implements [requirements.md](requirements.md). Interfaces and
examples below are proposed contracts, not commands or schemas already
available in the current checkout. Reconcile the earlier assurance drafts
before implementing them.

## 1. Component responsibilities

Keep the existing C++ analyzer and CLI, Python analysis components, FastAPI
report engine, and React dashboard. Evolve them into one installed product
with optional capabilities and explicit component boundaries.

~~~mermaid
flowchart TD
  A["Source snapshot and build contexts"] --> B["analyzer-core"]
  A --> C["git-miner"]
  D["Explicit tests and external tool reports"] --> E["Evidence adapters"]
  B --> F["Validated facts and run manifest"]
  C --> F
  E --> F
  F --> G["Health, risk and policy evaluation"]
  G --> H["CLI and build gate"]
  G --> I["HTML, PDF, REST and dashboard"]
  G --> J["MCP and IDE integrations"]
~~~

| Component | Responsibility and extension |
|---|---|
| analyzer-core | AST parsing, context-aware observations, function/file metrics, dependency inventory, worker entry point; preserve CRTP rules |
| git-miner | Stream history once into reusable records; derive history metrics, SZZ labels, ownership, coupling, and symbol history |
| predictor | Deterministic health/hotspot/roadmap evaluation; keep statistical risk modeling an optional, separately reported capability |
| assurance | New policy and evidence evaluation package; no parser, renderer, or subprocess-launching logic in evaluators |
| adapters | Translate producer-specific formats into validated observations/evidence; declare supported tool/report versions |
| report-engine | Render persisted results and expose paginated read interfaces; do not independently recompute scores |
| dashboard | Display assessments, scope, trends, and evidence; calculations that affect gates remain in the shared evaluator |
| cli | Discover installed components, validate configuration, schedule work, publish runs, expose exit semantics, and invoke explicit collection recipes |
| contracts | Package canonical schemas, rule metadata, compatibility helpers, and configuration interpretation for all Python consumers |
| local development runner | Execute the same verification/packaging stages locally and through existing CI wrappers |

Use namespaced Python packages instead of having every installed component
named src. Preserve current module entry points as compatibility wrappers while
migrating. Keep the process boundary between C++ and Python through validated
artifacts; do not introduce a fragile native plugin ABI for the first release.
Native rules remain compiled in. External adapters use versioned contracts.

## 2. Contracts and publication

Continue to produce findings.json, git_metrics.json, risk_scores.json, and
roadmap.json. Their released formats remain supported. Add optional metadata
only where compatible; breaking changes require a new schema major version
and a tested migration/legacy export. Draft schemas are not released contracts.

In particular, the current risk schema constrains model_type to xgboost and
requires numeric health values. Use a new major contract where the actual
method, unavailable health, or non-probabilistic ranking cannot be represented
honestly. Keep reading valid old inputs. Offer an explicit legacy export only
when its semantics are representable; otherwise return a migration error.
Do not fabricate a model name or score to satisfy an obsolete schema. A legacy
API response may report unavailable data rather than invent a compatible value.

| New contract | Minimum information |
|---|---|
| run_manifest.json | Run ID; subject/source identity; revision/dirty state; context inventory; tool/config/rule/scorer versions; stage statuses; scope; artifact paths/hashes; timings; limitations |
| analysis_metrics.json | File/symbol/context IDs; metric identity/version; measured values and units; availability and limitations |
| observations.jsonl | Normalized imported/native findings with producer identity, rule ID, location, fingerprint version, context, severity, and evidence |
| evidence.json | Source/context binding; tool/version; collection or import provenance; execution/test scope; structured outcomes; artifacts and integrity; time/expiry and reviewer information if relevant |
| policy.json | Policy identity/version; standard/edition metadata; scope; contexts; controls/evaluators; weights; required flags; thresholds; deviation policy |
| assessment.json | Run/source/policy binding; control outcomes and reasons; raw score numerators/denominators; rendered scores; gate; accepted deviations; limitations |
| baseline.json | Scope/context and policy/scorer/fingerprint versions; reference run; finding fingerprints and multiplicities; reason and creation metadata |
| rule_registry.json | Rule IDs/versions; category; maturity; required analysis capabilities; supported languages; configuration schema; documentation and fix metadata |

All new JSON contracts use draft-07 schemas, checked at schema load and
validated at consumer boundaries. Validation includes semantic constraints
such as duplicate IDs and unresolved references that JSON Schema cannot fully
express. Input errors produce structured diagnostics, not an empty clean
document. Components may keep valid independent data and mark invalid portions
unavailable; they must not evaluate invalid data as positive evidence.

Use immutable run directories:

~~~text
output/
  runs/<run-id>/
    run_manifest.json
    findings.json
    git_metrics.json
    risk_scores.json
    roadmap.json
    analysis_metrics.json
    observations.jsonl
    evidence.json
    assessment.json
    artifacts/
  latest.json
~~~

Workers write temporary artifacts and a staging manifest. The orchestrator
validates and commits a snapshot, then atomically replaces latest.json.
Readers resolve latest once per request and read that run throughout the
request. Partial runs may be committed with explicit partial status.
Uncommitted staging directories cannot masquerade as the latest successful run.

Flat legacy exports remain available for old consumers. Assessment and
multi-file API reads use the manifest, not independent reads of mutable flat
files. Use an indexed local history catalog when history/pagination is added;
SQLite is the initial proposed implementation. Raw facts and JSON exports
remain inspectable and portable. Schema/catalog migrations are tested.

## 3. Identity and reproducibility

### Files and symbols

Normalize source identities to repository-relative forward-slash paths.
Resolve dot segments and separator differences; preserve repository spelling.
Do not globally lowercase paths on case-sensitive filesystems. Detect
case-fold collisions on case-insensitive systems rather than merging files.

Keep external include dependencies in a separate identity namespace.
Symlink traversal must not silently enlarge project scope. Record unreadable
files and dependency gaps. Apply Git rename information when comparing paths.

Use libclang symbol identities where available. Give unsymbolized locations a
documented fallback identity. Fingerprints initially combine namespaced rule,
file identity, symbol/anchor, normalized relevant tokens, and occurrence
ordinal. Keep build context separate so reports can group duplicate patterns
without losing the configurations in which they occurred.

Fingerprint version changes require baseline migration. Matching must preserve
multiplicity: two identical problems cannot be reduced to one just because
their basename/rule pair matches. Ambiguous comparisons are disclosed.

### Source, context, and result identities

The source identity hashes a sorted manifest of the declared analyzed inputs,
including relevant generated sources. Revision alone is insufficient for dirty
trees. Missing Git identity does not prevent a content identity.

Context identity includes actual compilation options, target, language
standard, working directory interpretation, include/forced-include inputs,
compiler/libclang identities, and available dependency fingerprints.
Unfingerprinted external dependencies are explicit limits on reuse and assurance.

Separate:

- Run ID: one execution, including timestamps and stage outcomes.
- Source/context identity: what was analyzed.
- Detector/facts version: how observations were produced.
- Scorer and policy identity: how facts became an assessment.

Determinism means semantic results agree for identical inputs and versions,
excluding timestamps, run IDs, progress, and explicitly statistical metadata.
Cross-version scores are not automatically comparable. PDF binary identity is
not required when renderer metadata changes; report content must agree.

## 4. Execution, caching, and scale

The scheduler expands selected translation-unit/context work units. Use a
bounded process pool to isolate libclang crashes and support cancellation and
timeouts. Pool size respects jobs and the configured resource budget. Record
per-unit outcomes and publish available facts even when another unit fails.

Do not hardcode a small file-size limit that silently excludes common
amalgamated libraries. Limits are configurable and every skipped unit appears
in scope/completeness results.

Cache keys include:

~~~text
facts_key = hash(
  source and relevant dependency content,
  compile context,
  analyzer and detector versions,
  fact-extraction configuration
)

assessment_key = hash(
  committed fact identities,
  scorer version,
  resolved policy and evaluation configuration
)
~~~

A scoring-weight change normally reuses facts. Enabling a detector that was
not run requires new extraction. Header, macro, compiler, sysroot, generated
input, or relevant tool-version changes invalidate affected work. When the
dependency graph is incomplete, invalidate conservatively instead of assuming
only directly edited files matter.

Incremental Git mining resumes from a known commit boundary and handles
rewrites/non-descendant history by rebuilding the affected cache. One history
stream supplies all derived metrics. Bulk-formatting commits, bots, merge
semantics, and window limits are configurable and visible.

Stream observations and aggregate summaries in bounded batches. Use indexed
queries for paginated findings and history. Keep the dashboard from downloading
the entire project. Optional ML and PDF work has independent resource budgets;
resource exhaustion cannot turn a skipped stage into success.

Benchmark cold, unchanged warm, source edit, shared header edit, compile-flag
edit, policy-only, and history-append cases. Record the reference machine,
dataset revision, context, repeated runs, peak memory, and timing distribution.
M2 freezes numerical release budgets after measurements; no unmeasured
throughput promise is part of this proposal.

## 5. Health, ranking, and policy semantics

### Maintenance health

Reuse the density-based scorer from origin/main as the historical baseline:

~~~text
density(category) = finding_count(category) / analyzed_KLOC
penalty(category) = min(1, density(category) / category_cap)
category_health = 100 * (1 - penalty(category))
overall_health = 100 * (1 - sum(weight * penalty) / sum(weight))
~~~

The documented caps and weights are calibration choices, not observed
probabilities. Keep a scorer version and publish the values used. Correct
source/context deduplication and LOC accounting before calibrating new metrics.

Report health per required context. The initial project presentation uses the
worst fully evaluated required context and identifies it; any missing required
context makes the full-scope result unavailable. An observed partial score may
be shown separately with its actual scope. Optional contexts remain visible.
Declared policy exclusions are visible, not silently treated as analyzed code.

Never return a perfect score merely because there are no feature rows.
Source-free input is unavailable. A fully observed, applicable scope with no
violations can legitimately score 100.

### Hotspots and defect ranking

Use measured complexity, actual change activity, and documented debt measures
for hotspots. Include metric values and ranking-method version. Refactoring
effort remains labeled an estimate unless linked to measured project outcomes.
Do not describe a ranking score as financial ROI without cost data.

Heuristic risk values are ranking signals, not bug probabilities. Emit actual
model_type, label_source, evaluation_method, sample/class counts, validation
cutoff, and availability of calibration. An untrained or invalid model falls
back visibly. Future-defect claims require temporal holdouts using only facts
available before the prediction cutoff, calibration measurements, and disclosed
limitations. SZZ keyword heuristics remain imperfect labels.

### Policy controls and scores

For applicable controls, let P, F, and U be the sums of weights of passed,
failed, and unknown controls. Exclude justified not_applicable controls from
the denominator. Preserve them in the report.

~~~text
readiness = 100 * P / (P + F + U)
evidence_completeness = 100 * (P + F) / (P + F + U)
observed_satisfaction = 100 * P / (P + F)
maximum_possible_readiness = 100 * (P + U) / (P + F + U)
~~~

Zero denominators produce null, not 100. Evaluate gates on unrounded values;
round only presentation. Retain the numerator/denominator values for audit.
Readiness measures the configured policy only; there is no cross-project
safety probability implicit in the percentage.

If no applicable controls or no applicable source scope remain, the gate is
incomplete regardless of numerical thresholds.

| Example | Readiness | Completeness | Observed satisfaction |
|---|---:|---:|---:|
| Passed weight 4, failed 2, unknown 4 | 40.00 | 60.00 | 66.67 |
| Same controls, unknown evidence later passes | 80.00 | 100.00 | 80.00 |
| All applicable controls unknown (U > 0, P = F = 0) | 0.00 | 0.00 | null |
| No applicable control weight (P + F + U = 0) | null | null | null |

Gate precedence:

1. fail: an unexcepted required control fails, or even the maximum possible
   readiness is below the configured minimum.
2. incomplete: a required control is unknown, required scope is absent,
   minimum completeness is unmet, or readiness could meet the minimum only
   after resolving unknown evidence.
3. pass: all remaining gates are satisfied.

With complete evidence, readiness below threshold is a fail. Optional known
failures can be tolerated only when the declared policy's thresholds permit
them. A high average never overrides an unexcepted required failure.

A permitted deviation preserves the failed control and its score. It may
unblock that named required-control gate only; global readiness/completeness
thresholds still apply. It cannot convert required unknown evidence to passed.
Require scope, rationale, reviewer/owner, approval metadata, and expiry.
Expired or mismatched deviations are inactive. A passing gate with deviations
is labeled accordingly. Identity/review assertions are not cryptographic
proof unless a separate trusted approval mechanism is configured.

## 6. Policy and configuration example

This illustrative YAML describes the proposed policy model. The automotive
metadata does not make these three controls a complete ISO 26262 assessment.
References to particular standard clauses are intentionally absent.

~~~yaml
schema_version: "1.0"
id: example-automotive-library
policy_version: "0.1.0"
standards:
  - name: ISO 26262
    edition: "2018"
    mapping_status: starter-unreviewed
subject_kinds: [library, header-only]
scope:
  include: ["include/**", "src/**"]
  exclude: ["vendor/**"]
required_contexts: [linux-clang-debug, linux-clang-asan]
gates:
  minimum_readiness: 80
  minimum_completeness: 100
controls:
  - id: memory-patterns
    evaluator: finding_limit
    rules: [cppulse/CPP-MEM-001, cppulse/CPP-MEM-002]
    maximum: 0
    prerequisites: [complete_parse, required_rules_executed]
    required: true
    weight: 4
  - id: consumer-tests
    evaluator: test_outcome
    evidence: consumer-tests
    minimum_executed: 1
    maximum_failed: 0
    contexts: [linux-clang-debug]
    required: true
    weight: 3
  - id: instrumented-consumer
    evaluator: sanitizer_outcome
    evidence: consumer-asan
    require_instrumentation_evidence: true
    require_executed_tests: true
    maximum_findings: 0
    contexts: [linux-clang-asan]
    required: true
    weight: 3
~~~

Top-level project configuration references a policy and defines selected
targets/contexts. Use one shared schema and parser for JSON/YAML, replacing
ad-hoc configuration interpretation. Precedence is explicit CLI options,
explicit config or discovered repository config, then documented defaults.
Conflicting repository config files require disambiguation. Effective
configuration and every override are part of run identity.

Policies may reference pinned local packs. Fetching or upgrading a pack is a
separate explicit operation; ordinary analysis does not silently download or
upgrade its requirements. Detect reference cycles and duplicate controls.
Custom standards use the same evaluators. A requirement needing a new
capability needs a new detector/adapter/evaluator, not a claim that arbitrary
configuration can analyze anything.

For finding limits, observed violations can fail a control even with partial
analysis. Passing requires applicable rules actually executed on sufficient
scope with the required parsing/context quality. Missing files, disabled rules,
or insufficient prerequisites produce unknown.

## 7. Evidence collection and library contexts

External adapters normalize findings/tests/coverage without erasing original
producer metadata. Distinguish:

- execution receipt: cppulse observed an explicit command and recorded its
  outcome, tool/configuration, structured report, and scope;
- imported report: producer metadata states what was run; cppulse validates
  format, binding, and integrity;
- attestation: a reviewer supplies a claim and supporting artifacts.

Successful receipt parsing does not authenticate an external producer.
Missing artifacts, hash mismatches, unsupported formats, stale revisions, or
wrong contexts invalidate positive evidence. Preserve credible observed
failures with their scope; do not convert malformed inputs into clean reports.

Coverage imports retain covered and total counts, not just percentages. Merge
compatible shards only within the same source/context and measurement
semantics. Initial acceptance requires exact source binding; ancestor reuse
would need per-file/content validation and a separate tested design.

ASan and TSan have separate named build/test contexts where required by their
toolchains. No built-in policy presumes every sanitizer is available on every
platform. Unsupported capability is explicit; applicability decisions must be
declared by the policy and justified.

Library assessment includes selected consumer programs and selected targets,
not every file in unrelated applications. For header-only libraries,
self-containment and selected template/type combinations are distinct evidence
items. Runtime evidence describes the actual instrumented consumer/dependency
set. General library use, target-specific use, and safety-related use are
different policies rather than a universal production-ready label.

## 8. Public interfaces

### Proposed CLI

The examples describe the target platform. Release A/M3 supplies health and
finding-regression checks using validated core configuration. The general
policy-pack evaluator, collect/assess commands, and evidence-dependent gates
arrive in M5. Early releases shall reject unsupported options clearly rather
than accepting a policy they cannot evaluate.

~~~bash
cppulse init --kind header-only
cppulse doctor
cppulse config show --effective
cppulse analyze --repo . --compile-commands build/compile_commands.json
cppulse check --changed --base origin/main --policy policies/library.yml
cppulse collect --recipe consumer-tests
cppulse assess --input ./output --policy policies/library.yml
cppulse explain CPP-MEM-001
cppulse report --input ./output --format html
cppulse report --input ./output --format pdf
cppulse baseline create --input ./output
cppulse bugreport --output ./cppulse-diagnostics.zip
~~~

analyze extracts facts and evaluates configured assessments; it does not
silently execute project build/test recipes. collect executes an explicitly
selected recipe. assess reuses valid evidence without unnecessary AST work.
check applies the gate to a declared full/changed scope. For assessment based
only on changed files, findings gates may apply to changed code but project-wide
readiness requires a compatible complete baseline; missing context is unknown.

Text is the default. --format json on suitable commands emits a documented
machine result; --output-format sarif exports findings where applicable.
Diagnostics/logs go to a separate stream and do not corrupt JSON. Configurable
color/progress is disabled appropriately in machine mode.

| Exit | Meaning |
|---:|---|
| 0 | Requested operation completed; for check/assess the policy gate passed |
| 1 | A check/assess gate failed on known results |
| 2 | Invalid invocation/configuration or an operational failure preventing a usable requested result |
| 3 | Analysis/evidence is incomplete and the requested full assessment cannot be accepted |
| 130 | Explicit cancellation; checkpoint and interrupted status preserved where possible |

analyze can complete successfully while reporting violations; use check to
enforce policy. A partial analyze returns 3. A known failed check has precedence
over incomplete evidence, so its exit is 1 and the report also shows gaps.
report returns its rendering result; rendering a clearly labeled partial report
does not change the underlying assessment gate.

### Proposed CMake integration

~~~cmake
option(CPPULSE_ENABLE "Enable cppulse checks" OFF)
if(CPPULSE_ENABLE)
  find_package(CPPulse CONFIG REQUIRED)
  cppulse_add_check(
    TARGET cppulse-check
    ANALYZE_TARGETS my_library library_consumer_tests
    POLICY "policies/library.yml"
  )
endif()
~~~

~~~bash
cmake -S . -B build -DCPPULSE_ENABLE=ON -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cmake --build build --target cppulse-check
~~~

The installed CMake package supplies the function and resolves relative policy
paths against the project source directory. The check target depends on
selected build/generated-input targets. Running tests requires an explicit
configured collection recipe. An optional CPPULSE_CHECK_ON_BUILD setting adds
the target to ordinary builds. Initial compilation database support targets
generators producing compile_commands.json; unsupported IDE-generator context
extraction is visible rather than silently assumed complete.

### API, editor, and agent interfaces

Retain existing /api/v1 read routes with compatible responses. Add versioned
run/history/assessment routes and pagination with a cursor tied to an immutable
run and query. New paginated envelopes use a new version where necessary.
Preserve optional API-key behavior; SSO/RBAC is later expansion work.

MCP tools initially expose run status, health explanations, findings,
hotspots, assessment gaps, and rule/policy documentation. Execution/modification
tools are separate capabilities. The IDE uses the same interfaces and stable
rule/location IDs. No independent editor-specific scoring implementation.

## 9. Development and release workflow

Add one cross-platform developer entry point:

~~~bash
python tools/dev.py doctor
python tools/dev.py verify --scope changed
python tools/dev.py verify --scope full
python tools/dev.py new-rule CPP-MEM-004
python tools/dev.py new-adapter example-tool
python tools/dev.py benchmark --suite reference
python tools/dev.py package --candidate
python tools/dev.py release --dry-run
~~~

These commands are proposed. The runner invokes existing component tools; it
does not replace CTest, pytest, or the dashboard toolchain. Full verification
runs mandatory component tests, contract/scorer checks, installed-package
integration, and selected performance scenarios. Changed-scope verification
uses conservative dependency mapping; release candidates always run the full
required suite.

Generators create implementation stubs, metadata, test fixtures, and reference
documentation hooks. Rule registrations and docs are generated from one
registry. Tests exercise observable detection/evaluation behavior, including
false positives, not only generated wording.

Release packages separate:

- core analyzer/CLI and deterministic assessment;
- optional Git/risk-model capability where dependencies differ;
- optional PDF renderer, API/dashboard distribution, and editor integrations.

Extend CMake with install targets and CPack; build a namespaced Python wheel
and container images. Package schemas, policies, CMake helpers, and supported
runtimes with each appropriate artifact. Validate native loader/dependency
behavior and invoke installed binaries outside the checkout.

Candidate automation produces a changelog from conventional commits and
curated compatibility notes, versions, artifact checksums, dependency inventory,
license notices, support matrix, and verification manifest. A tag/publication
step acts on the verified candidate, not a fresh untested build.
Dependency refresh, generated docs, bug reproductions, and release notes are
automation opportunities. Ordinary verification is local and reproducible.

Maintain a stable channel and explicit preview capabilities. Policy/scorer
upgrades are pinned and migration-aware. Keep prior artifacts and support
rollback; software does not silently change its own scoring implementation.
Code-fix generation starts with narrow deterministic edits and dry-run diffs.
Automatic semantic refactoring requires its own sub-specification, language
support matrix, behavior checks, and failure handling.

## 10. Free distribution and validation

Distribute the executable independently of the agent skill. After M3, publish
a basic workflow skill containing only commands available in that release.
After M5/M7, extend it with evidence and policy workflows. The ZIP contains a
single SKILL.md and necessary text references, version information, and license.
Test it in a clean agent session before submission.

Maintain a benchmark corpus of the six existing example projects pinned to
commits with real history, plus small positive/negative fixtures and library
consumer configurations. Publish methodology, analysis gaps, accuracy review,
and resource results. Evaluate usefulness with maintainers as feedback becomes
available; downloading a free tool is not evidence that its scores are trusted.
