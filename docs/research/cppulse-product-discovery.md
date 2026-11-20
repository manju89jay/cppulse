# cppulse product discovery and working direction

Updated: **2026-11-11**. Status: **Research synthesis and proposed product direction**.

The working direction discussed is:

> cppulse could help maintainers establish and maintain trustworthy verification
> evidence for the C++ configurations they claim to support.

The intended benefit is a repeatable answer to which supported configurations
have current verification, which checks failed, and which evidence is missing
or no longer applicable. Library consumers would use the same evidence to
identify the additional checks their applications need.

This direction has been explored through competitor research, C++ developer
pain points, and a concrete library-release example. User demand, comparative
advantage, final feature scope, and the public interface still need validation.

## What we have gathered

| Area | Outcome so far | Where to look |
|---|---|---|
| Tool landscape | 72 tool-family rows across eight categories, with features, availability, and official sources | [C++ analysis tool landscape](cpp-analysis-tool-landscape.md) |
| Developer problems | Configuration accuracy, library consumption, verification coverage, result interpretation, and release evidence are candidate problems | Pain points below |
| Candidate audience | Library and header-only maintainers, followed by teams adopting their libraries | Users below |
| Working direction | Verification evidence tied to declared C++ configurations and releases | Proposed distinction below |
| Practical workflow | Separate maintainer and consumer opt-in, configured build/test collection, policy assessment, and an optional CMake target | Integration example below |
| Existing foundation | Native analysis, Git mining, experimental ranking, reports, dashboard source, and CLI orchestration | Current implementation below |
| Earlier engineering proposal | Broader requirements, design, and backlog remain proposed | [Production platform specification](../specs/production-platform/requirements.md) |

The tool inventory groups source analyzers, security/quality platforms,
code-health/architecture tools, safety/formal tools, runtime/testing tools,
library compatibility tools, orchestration tools, and dependency/license tools.
It is a broad reference rather than an exhaustive market census.

## Current implementation

Source inspection on 2026-11-11 covered `feature/full-mvp` at `3945825` with
existing uncommitted work. The locally recorded `origin/main` points to
`82120d2`; it was not refreshed from the network. Source presence does not
establish installation support, successful end-to-end execution, or a published
release. This documentation pass did not run application builds or tests.

| Area | Present in source | Important limit |
|---|---|---|
| C++ checks | libclang traversal and 22 built-in checks covering memory-related patterns, modernization, complexity, and checks labeled MISRA | Limited detectors; not complete memory-safety analysis or complete coding-standard verification. See [rule engine](../../analyzer-core/src/rule_engine.h). |
| Project/build configuration | JSON/simple-YAML configuration, exclusions, rule switches, thresholds, compilation-database arguments, and fallback parsing | Header arguments may be inferred; the selected compilation command does not establish all build variants. See [configuration](../../analyzer-core/src/config.cpp) and [analyzer](../../analyzer-core/src/analyzer.cpp). |
| Git information | Churn, change frequency, age, contributors, single-contributor alerts, and simplified SZZ-like labels | History signals and noisy labels do not prove ownership or future defects. See [Git miner](../../git-miner/src/miner.py) and [labeler](../../git-miner/src/szz_labeler.py). |
| Health and risk | Health scores, hotspots, XGBoost/heuristic ranking, conditional cross-validation, and explanation code | Current health is weighted findings per file; ranking is experimental rather than calibrated release risk. See [health scorer](../../predictor/src/health_scorer.py) and [model](../../predictor/src/model.py). |
| Refactoring roadmap | Prioritized actions and effort/impact estimates | Heuristic estimates, not demonstrated hours saved or financial ROI. See [roadmap generator](../../predictor/src/roadmap_generator.py). |
| Presentation | FastAPI routes, PDF generation, and React dashboard components | End-to-end contracts require reconciliation. See [API](../../report-engine/src/api.py), [PDF generator](../../report-engine/src/pdf_generator.py), and [dashboard](../../dashboard/src/App.tsx). |
| CLI | Registered `analyze`, `report`, and periodic `watch` commands | Checkout-relative execution and option behavior need baseline verification; `watch` repeats analysis rather than providing incremental analysis. See [CLI](../../cli/src/main.cpp) and [orchestrator](../../cli/src/orchestrator.cpp). |
| Existing action integration | Repository action source includes an opt-in finding-regression failure gate | A finding-comparison gate is narrower than evaluating configuration-specific verification evidence. See [action configuration](../../.github/actions/cppulse/action.yml) and [entry point](../../.github/actions/cppulse/entrypoint.sh). |
| Assurance drafts | Uncommitted parse-status metadata changes, policy/evidence/assessment schemas, and contract-test source | No implemented general evidence collector, policy assessment engine, or configurable evidence-policy release gate was identified. See [schemas](../schemas/) and [coverage draft](../../analyzer-core/src/analysis_coverage.h). |

Source discrepancies to reconcile before expanding public claims include:

- Detector selection and scoring profiles differ: all 22 detectors are registered
  unless individually disabled, while the predictor's default profile excludes
  MISRA from selected scoring behavior. The README's opt-in detector description
  therefore needs reconciliation with this branch.
- The current overall health formula divides weighted findings by file count,
  despite the README describing KLOC normalization. An empty feature frame
  receives 100; missing verification must not inherit that interpretation.
- Static/Git path identities and API/dashboard response shapes have source-level
  mismatches that need validation and correction.
- The CLI accepts a report-format option but invokes PDF generation regardless
  of the selected format. A portable installed workflow remains delivery work.

These are baseline observations, not fixes completed by this document. Earlier
implementation drafts and the proposed platform backlog remain separate from
supported functionality.

## Users and developer pain points

| Candidate user | Decision they need help making | Useful outcome to investigate |
|---|---|---|
| Library/header-only maintainer | Can this change or candidate satisfy our declared release checks? | Current results and explicit gaps for selected consumer configurations |
| Application team adopting a library | Which upstream results apply to our exact integration, and what remains to test? | Configuration comparison and application-specific verification |
| Build/platform engineer | Are checks using the right inputs, and why do they take this long? | Reproducible configuration, understandable reruns, and bounded resources |
| Embedded/safety-oriented team | What evidence supports this component's particular intended use? | Scoped evidence and controlled exceptions under a reviewed policy |

The first two groups are the strongest initial discovery candidates. That is a
product hypothesis, not a market-size finding or a committed release scope.

JetBrains' 2025 survey covers 1,800 C++ respondents in 22 countries. It reports
37% writing no C++ unit tests, and compiler/library constraints and migration
resources among reasons for retaining an existing language standard. These
indicate compatibility and adoption friction, but do not establish its causes
or demand for cppulse. The report notes possible sampling skew toward JetBrains
users. [State of C++ 2025](https://lp.jetbrains.com/the-state-of-cpp-2025/)

| Pain point | What is already available | Remaining difficulty worth investigating |
|---|---|---|
| Correct analysis configuration | Compilation databases, IDE/build integration, compiler discovery | Headers can receive inferred commands; missing flags change what the tool understands. Make checked and inferred contexts visible. [clangd](https://clangd.llvm.org/design/compile-commands) |
| Slow builds and costly templates | Timing reports, caching, distributed compilation | Identify worthwhile changes and measure improvement in representative builds. Profiling itself already exists. [ClangBuildAnalyzer](https://github.com/aras-p/ClangBuildAnalyzer) |
| Dependency upgrades | Package managers and API/ABI comparison | Compatibility still depends on the consuming application, toolchain, options, and behavior. [vcpkg build identity](https://learn.microsoft.com/en-us/vcpkg/reference/binarycaching), [ABI Compliance Checker](https://lvc.github.io/abi-compliance-checker/) |
| Header/template verification | Standalone-header compilation and instantiation coverage | Select representative usages and make missing scenarios visible; arbitrary template arguments cannot be exhaustively covered by a small generated test set. [CMake](https://cmake.org/cmake/help/latest/prop_tgt/VERIFY_INTERFACE_HEADER_SETS.html), [LLVM coverage](https://clang.llvm.org/docs/SourceBasedCodeCoverage.html) |
| Compiler/platform/option combinations | Build matrices and multi-variant analyzers | Reconcile results from several environments without implying unchecked combinations passed. Sonar's documented variant mode requires the same analysis environment. [Sonar variants](https://docs.sonarsource.com/sonarqube-server/analyzing-source-code/languages/c-family/customizing-the-analysis#analyzing-several-code-variants) |
| Memory and concurrency defects | Static analyzers, sanitizers, fuzzers, verification tools | Relevant workloads, execution paths, platform support, reproduction, and instrumentation remain substantial work. [ASan](https://clang.llvm.org/docs/AddressSanitizer.html), [TSan](https://clang.llvm.org/docs/ThreadSanitizer.html) |
| Finding overload and legacy debt | Baselines, suppressions, fixes, hotspots, architecture tools | Deliver changes worth acting on with manageable review cost. Workflow integration and useful diagnostics are established adoption concerns. [Google's experience](https://abseil.io/resources/swe-book/html/ch20.html) |
| Release evidence reconciliation | Commercial suites combine analysis, tests, runtime failures, coverage, and build-associated reporting | Determine whether independently produced results still apply to this release/configuration. Aggregation alone is established functionality. [Parasoft](https://www.parasoft.com/products/parasoft-c-ctest/c-c-reporting-analytics/) |
| Safety-oriented component adoption | Traceability, compliance suites, deviation management, qualification support | Suitability depends on lifecycle and integration evidence for a particular use. A code score cannot settle it. [ISO 26262 software development](https://www.iso.org/standard/68388.html), [IEC 62304](https://www.iso.org/standard/38421.html) |

## Proposed distinction and practical value

Candidate positioning:

> C++ verification evidence tied to the configurations you support, with clear
> gaps and repeatable release checks.

The potential distinction is the combined workflow below. None of these
individual capabilities has been established as exclusive to cppulse.

| Proposed capability | Benefit for current C++ developers | Evidence needed before claiming an advantage |
|---|---|---|
| Declared support matrix with results per context | Shows which OS, architecture, compiler/library, language standard, and options have current checks | A more useful release decision than users' existing matrices and reports |
| Identity and freshness checks | Flags mismatched source, distributed artifacts, configurations, and tool/policy versions | Correct rejection of deliberately stale or mismatched evidence |
| Explicit incomplete results | Exposes skipped headers, failed parsing, absent variants, and unverified checks | No positive gate when a required part of the declared scope is unknown |
| Consumer-oriented library assessment | Helps adopters compare upstream evidence with their application's actual integration | Fewer manual reconciliation steps and useful identification of missing consumer tests |
| Adapters for existing tools with producer attribution | Lets teams retain their compilers, analyzers, tests, sanitizers, and coverage tools | Lower integration and maintenance effort with reliable adapter behavior |
| Repository configuration and optional build target | Makes local checks and automated release checks repeatable | An understandable first useful result with little configuration duplication |
| Explainable change handling | Explains what must be rerun after header, option, dependency, or tool changes | Incremental results agree with clean execution and stay within resource budgets |

Existing competition is substantial. CodeChecker already records failed
analysis and supports incremental analysis. Parasoft already combines several
verification methods and associates results with builds. CodeScene already
combines code health, hotspots, and coverage. CLI access, local execution, free
use, custom gates, and dashboards are useful adoption properties rather than
unique inventions. [CodeChecker](https://codechecker.readthedocs.io/en/latest/usage/),
[Parasoft](https://www.parasoft.com/products/parasoft-c-ctest/c-c-reporting-analytics/),
[CodeScene coverage](https://codescene.io/docs/integrations/using-code-coverage.html)

One specific opportunity concerns analysis contexts: Sonar documents that
unused headers are not analyzed through source files and that combining
independent targets can reduce precision. This supports investigating explicit
public-header/consumer scope. It does not establish absence of equivalent
solutions across the market. [Sonar scope](https://docs.sonarsource.com/sonarqube-server/analyzing-source-code/languages/c-family/understanding-the-analysis)

## Proposed maintainer and consumer workflow

All commands, recipes, output, and gates in this section describe a proposed
experience. `collect`, `assess`, and the optional build target are not current
CLI functionality. Configuration schemas and final command details remain to
be agreed.

### Maintainer setup

Install cppulse as a development tool, then configure existing CMake presets
and selected tests in the library repository. Keep separate build directories
for each verification configuration. A release policy declares required checks
and evidence; the compiler and tests remain the producers of their diagnostics.

The worked example uses nlohmann/json. It already documents extensive checks
and publishes an assurance case; this is an illustration of packaging and
interpreting existing evidence, not a finding of missing verification in the
actual library. [Quality assurance](https://json.nlohmann.me/community/quality_assurance/),
[assurance case](https://json.nlohmann.me/community/assurance_case/)

| Illustrative preset | Settings and selected checks |
|---|---|
| `gcc-cxx11` | GCC, C++11, default options; build and selected tests |
| `gcc-cxx17-noexceptions` | GCC, C++17, `-fno-exceptions`, `JSON_NOEXCEPTION=1`; build and appropriate tests |
| `clang-cxx20-sanitizers` | Clang, C++20, ASan/UBSan compile and link flags; instrumented build and selected tests |

The recipe maps these names to ordinary configure/build/CTest commands, for
example `cmake --preset gcc-cxx17-noexceptions`,
`cmake --build --preset gcc-cxx17-noexceptions`, and
`ctest --preset gcc-cxx17-noexceptions --output-on-failure`.
Matching configure, build, and test presets must be supplied by the project.

### A precise change and its diagnosis

Suppose an error-handling helper is accidentally changed as follows:

```diff
- JSON_THROW(error);
+ throw error;
```

This is a hypothetical regression. The exception-disabled GCC/Clang profile
needs the actual `-fno-exceptions` compiler flag to reject raw `throw`;
`JSON_NOEXCEPTION` alone does not prohibit it at compiler level.
[Exception configuration](https://json.nlohmann.me/api/macros/json_noexception/)

The release recipe must compile and exercise the actual distributed
`json.hpp` or package, record it as the check's input, and identify missing
artifact-specific verification explicitly. Recording a header hash next to
results from different input files is insufficient.

The proposed calls from the library repository are:

```bash
cppulse collect --recipe linux-release
cppulse assess --input ./output --policy policies/release.yml
```

Collection runs the explicitly configured commands, retains failures and logs,
and continues independent configurations. Within a failed configuration,
dependent tests are marked not run. Assessment evaluates the collected records
against the selected policy and determines the gate's exit status.

Illustrative output, not an executed test result:

```text
Source: current scoped contents, including working-tree changes
Artifact: distributed json.hpp [content hash recorded]

gcc-cxx11                    PASS
gcc-cxx17-noexceptions        FAIL: compilation
clang-cxx20-sanitizers        PASS: selected instrumented tests

Producer: GCC
Diagnostic: exception handling disabled
Changed code: throw error;
No-exception tests: NOT RUN because compilation failed

Release policy: FAILED
Assessment exit code: 1
Action: repair exception-disabled compilation and rerun checks
```

The compiler finds the compilation problem. cppulse would connect the result
to the project's required configuration and retain its diagnostic context.
After a fix, changed inputs invalidate the corresponding evidence. A first
implementation can conservatively rerun all required configurations.

An optional `cppulse-check` CMake target could execute collection and assessment:

```bash
cmake --build build/dev --target cppulse-check
```

Keep this target outside `ALL`, avoid recursive invocation, and use separate
build directories for its verification jobs. Collection should complete with
recorded check failures so assessment can report them; an operational failure
must remain distinguishable from an observed code/test failure.

### Release evidence and consumer adoption

An accepted release policy would produce a scoped evidence package containing
source/input identities, the exact distributed header/package identity,
compiler/standard-library/target/options, producers and versions, executed
checks, results, limitations, policy version, and linked logs. A Git commit
alone misses dirty contents; tests on split headers alone do not identify the
released amalgamated header. Hashes help identify changed contents, but do not
authenticate the producer or prove adequate testing.

The application developer opts in separately. They install cppulse in their
development environment and configure their application build and integration
tests against the selected library artifact and options. The library acquires
no runtime cppulse dependency.

```bash
cppulse collect --recipe application-linux
cppulse assess --input ./output --policy policies/application.yml
```

If upstream evidence is supplied, the user configures its location and source.
The assessment labels upstream and local results and compares applicable
contexts. Linux/x86 results do not establish Windows/MSVC or embedded-target
verification. A matching upstream configuration still does not replace tests
of the application's own conversions, workloads, and error handling.

## Results and configurable standards

| Result | Meaning |
|---|---|
| Code health | Explainable maintenance indicators under a versioned scoring model |
| Experimental change-risk ranking | A prioritization aid with dataset/method limitations |
| Evidence completeness | How much of the declared required verification has usable evidence |
| Policy assessment | Whether the applicable controls of a selected, versioned policy are satisfied |

Policies should declare required configurations, applicability, evidence,
thresholds, and controlled exceptions. A general library release, one
consumer's adoption, and a safety-oriented integration need different scopes.
Required missing, stale, failed, or unverified evidence cannot silently pass.
Stale evidence is unusable for the current assessment; it is not itself proof
of a code defect. Rule/control outcomes should preserve passed, failed,
unknown, and justified not-applicable states.

The proposed product does not derive ASIL, medical software classification,
universal production readiness, or certification from syntax or a score.
Domain policies need reviewed scope and mappings against the relevant
authorized standard edition. Tool confidence also depends on the particular
tool, use, and environment; commercial qualification packages already address
this work. [Axivion qualification kit](https://www.qt.io/quality-assurance/axivion/tool-qualification-kit)

## Scalability maintainability and usability

These are product requirements to prove, not performance results achieved.

| Concern | Proposed engineering property | How to verify usefulness |
|---|---|---|
| Large repositories and expensive templates | Bounded workers, time/memory limits, visible progress, cancellation, and partial results | Representative repository benchmarks and understandable incomplete outcomes |
| Repeated checks | Dependency/context-aware invalidation with conservative fallback | Compare warm/incremental results with clean execution after header, macro, tool, and dependency changes |
| Setup effort | One installed CLI, effective configuration display, environment diagnostics, opt-in build integration | Observe installation and first useful result on supported platforms |
| Adding tool support | Versioned adapters/contracts, captured fixtures, supported-version declarations | Detect changed producer formats and unsupported capabilities without manufacturing a pass |
| Fixes and features | Small reproducible bug cases, regression fixtures, shared local checks, documentation tied to interfaces | Reproduce issues and verify intended behavior through one documented local path |
| Releases and upgrades | Scripted candidate preparation, installed-artifact checks, versioned policies/results, migration notes | Verify the package users install and make semantic changes visible |

Automation should run locally through shared scripts and Docker Compose, in
line with repository instructions. Existing automation may invoke that same
path. Tool execution is explicit through selected recipes; merely opening or
analyzing a repository should not silently execute arbitrary project commands.

## Free distribution and agent skills

The repository is [MIT licensed](../../LICENSE). The desired direction is a
free, locally usable core for public and private C++ projects, with third-party
tools retaining their own licensing. Free access supports adoption; existing
OSS alternatives mean price alone does not establish differentiation.

A free Agensi skill remains a proposed distribution option for instructions
around released cppulse workflows. A skill is an instruction package; native
tool installation and capability delivery remain separate. This research does
not establish that a listing has been published or that the proposed workflows
are available through a marketplace.

## What remains to validate

| Question | Useful next evidence |
|---|---|
| Is this painful enough to adopt another tool? | Maintainers show recent failed releases, upgrades, or manual verification reconciliations |
| Which audience should come first? | Compare recurring work for library maintainers and application adopters, with separate safety-oriented discovery |
| Does cppulse improve existing workflows? | Compare the same tasks against CMake/CTest scripts, CodeChecker, relevant health platforms, and available verification suites |
| Are the results trustworthy within scope? | Deliberate stale/mismatched inputs, missing headers/variants, failed jobs, and controlled source/configuration changes |
| Is the tool affordable to operate and maintain? | Setup time, manual steps, review effort, false alarms, check duration, peak resources, adapter upgrade effort |

A useful evaluation should include at least a compiled library and a header-only
library, plus a consuming application. Use real project failures where
available and label seeded regressions. Acceptance thresholds should be set
after observing the baseline workflow, rather than invented from a score.

## Planning status and related documents

The discussion has established the importance of configurable requirements,
easy build integration, free initial distribution, scalability, maintainability,
and a clear distinction between code health and verification evidence.
The focused library-evidence direction is a working hypothesis. It has not
established unique capabilities, validated demand, final scope, delivery dates,
or safety qualification.

The earlier production platform specification is broader than this discovery
focus and remains proposed. This synthesis does not authorize its backlog or
rewrite the historical MVP task specification. When implementation is agreed,
retain the required contract/producer/consumer/presentation/orchestration/
integration order and component verification.

- [Tool landscape](cpp-analysis-tool-landscape.md)
- [Proposed production requirements](../specs/production-platform/requirements.md)
- [Proposed design and interfaces](../specs/production-platform/design.md)
- [Proposed implementation backlog](../specs/production-platform/tasks.md)
- [Decisions log](../DECISIONS.md)
- [Historical MVP task specification](../../TASK_SPEC.md)
