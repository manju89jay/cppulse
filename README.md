# cppulse

**Understand your C++ code. See which checks support your next release.**

cppulse brings C++ source findings, Git history and selected build/test evidence
into one local workflow. It helps developers inspect maintenance problems,
maintainers review declared library configurations, and integrators identify
the checks their application still needs.

[Get started](#get-started) · [Evidence demo](#try-three-evidence-outcomes) ·
[CLI guide](docs/development/public-cli.md) ·
[Rules](docs/generated/rules.md) · [MIT license](LICENSE)

> **Development preview — 0.2.0.dev2.** The full production specification is
> being implemented. The current tool has tested local workflows and known
> limitations; it is not a production-qualified release. See the current
> [delivery status](docs/plans/production-delivery-status.md) and
> [requirement/evidence ledger](docs/plans/production-delivery-ledger.json).

## Start with the decision you need to make

| Your question | Start here | What to inspect |
| --- | --- | --- |
| What deserves attention in this C++ project? | `cppulse analyze` | Rule findings, parsing gaps, available Git signals and experimental priorities |
| Does this candidate satisfy our configured checks? | `cppulse collect`, then `cppulse check --policy` | Executed checks, selected inputs, failed controls and missing evidence |
| Does upstream library evidence apply to our application? | `cppulse compare` | Configuration correspondence, artifact identity and required local checks |
| Did this change introduce findings beyond an agreed baseline? | `cppulse baseline create`, then `cppulse check --findings` | New, unchanged and unknown occurrences within explicit scope |
| Why did a check produce this result? | `cppulse explain` or an evidence report | One retained run, control reasons, original artifacts and limitations |

Compilers, analyzers, test runners and runtime tools remain the producers of
their diagnostics. cppulse connects their results to a declared scope so you
can inspect the facts behind a decision.

For compiled and header-only libraries, select consumer programs, compiler
options and tests explicitly. A passing sample covers those selected uses;
untested platforms, macros and template instantiations remain separate work.

## What works today

- **Native analysis:** a C++17/libclang engine with 22 experimental pattern
  checks, rule configuration, compilation databases and visible parse outcomes.
  Inferred header arguments remain distinct from observed consumer builds.
- **History and prioritization:** current-file churn/contributor signals,
  descriptive health and experimental heuristic/optional XGBoost ranking.
- **Explicit evidence:** finite argv recipes retain selected source/output
  identities, bounded command logs and supported test/coverage/sanitizer results.
- **Local gates:** versioned policies, scoped finding baselines, suppressions and
  SARIF. Six supported predicates cover findings, analysis coverage, tests,
  contexts, coverage and sanitizers. Profile 1.2 adds measured numeric thresholds
  and scoped reviews bound to exact artifact bytes.
- **Retained views:** JSON/HTML/optional PDF, API and a bundled React dashboard
  read stored results. Run/hash pins support reproducible historical review.
- **Opt-in integration:** an installed CLI, CMake helper and local hook template.
  Core operation requires no cppulse account or hosted service.

Measured file/function metrics and explicit density/context scoring now run on
retained native evidence. `cppulse maintenance --store STORE --workspace SOURCE
--required-context CONTEXT` publishes a derived run with full-scope health
unavailable whenever required measurements or checks are missing. The historical
scorer remains distinct; versions are not silently merged in trends.

The [VS Code preview](docs/editor-vscode.md) has actual installed-host evidence;
the [read-only MCP preview](docs/development/mcp.md) reads pinned stored results.
`cppulse analyze --execution bounded --no-history` runs explicit finite native
workers and retains original receipts, full selected scope and checked used SDK
bytes. Qualified warm reuse, atomic final publication and large-project
qualification remain open. The current scorer uses actual measured inputs and
preserves null results for unknown scope or unsupported preprocessing queries.

Separate finite expansion commands include local `branches`, public read-only
GitHub `issues`, `abi-compare`, dry-run `fix`, ordinary `verify-proposal` and
explicitly trusted `verify-service-proposal`. Their supported scopes and retained
evidence are documented in the [Cloud checkpoint](docs/checkpoints/20261116/README.md).
The full remaining production program is tracked in
[scope and maturity](#scope-and-maturity).

## Get started

Use a source checkout or a locally prepared candidate. These instructions do
not assume a published PyPI package or production binary. The Python CLI and
native analyzer are separate installation components.

### Build prerequisites

Use Linux with a C++17 compiler, CMake, libclang development headers/library,
nlohmann/json, spdlog/fmt, CLI11 and GoogleTest. Python **3.11–3.12** is declared;
retained cloud checks exercised **3.12.14**.

Typical Debian/Ubuntu package names are `build-essential`, `cmake`,
`libclang-19-dev`, `nlohmann-json3-dev`, `libspdlog-dev`, `libfmt-dev`, `libcli11-dev`
and `libgtest-dev`. Packages and LLVM layouts vary by distribution.
Set `LIBCLANG_ROOT` for a nonstandard LLVM prefix. The analyzer requires the
libclang binary-opcode API available in the tested LLVM 19 pair; configuration
rejects headers/libraries that lack it.

### Build and run

From the checkout root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

cmake -S analyzer-core -B analyzer-core/build -DBUILD_TESTING=ON
cmake --build analyzer-core/build -j4
ctest --test-dir analyzer-core/build --output-on-failure

export CPPULSE_ANALYZER="$PWD/analyzer-core/build/cppulse-analyzer"
cppulse doctor

cppulse analyze --repo demo/fixture --output output/first-run --format html
cppulse report --input output/first-run --format json \
  --output output/first-run/report.json
```

Check that doctor reports `native.available: true`, then open the HTML path
printed by analyze. Detecting an optional package is not execution verification.
The demo contains a clean file and intentional synthetic rule triggers; the
triggers are analyzed, not executed. Static input does not require `.git`, GitPython or a Git executable. Install
`cppulse[git]` (and Git) for history; missing tooling stays explicitly unavailable.

For your CMake project, generate and supply its actual compilation database:

```bash
cmake -S /path/to/project -B /path/to/project/build \
  -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
cppulse analyze --repo /path/to/project \
  --compilation-database /path/to/project/build/compile_commands.json \
  --output output/my-project --format html
```

Use a generator that emits the database, such as Makefiles or Ninja. Missing
commands can lead to inferred/fallback parsing. `analyze` runs source/history
analysis without building or testing your project. Its compatibility snapshot
uses conservative, unverified evidence binding. Use collection and policy checks
for the explicit evidence workflow.

Create editable settings with `cppulse init --repo /path/to/project`, then use
`cppulse config --repo /path/to/project --output output/my-project` to inspect
effective settings. Exclusions and detector switches belong in `.cppulserc.json`
or YAML; policy controls are separate. Explicit options override the selected
config and defaults. If several config files are present, select one with
`--config /path/to/.cppulserc.json`. The default profile excludes MISRA-labeled
findings from scoring; it does not disable those detectors.

If libclang cannot find built-in headers such as `stddef.h`, set
`CPPULSE_CLANG_RESOURCE_DIR` to its matching resource directory containing
`include/stddef.h`. A standalone analyzer reports less installation metadata
than a prepared native bundle. The [candidate guide](docs/development/candidate.md)
documents host dependencies, offline installation and upgrade/rollback.

### Add the dashboard or PDF

```bash
python -m pip install -e '.[web,pdf]'
cppulse serve --input output/first-run --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. The package includes the built dashboard; Node is
needed for dashboard development, not this runtime. In another terminal:

```bash
cppulse report --input output/first-run --format pdf \
  --output output/first-run/report.pdf
```

PDF needs native Pango/font libraries, typically `libpango-1.0-0`,
`libpangoft2-1.0-0`, `libcairo2` and `fonts-dejavu-core` on Debian/Ubuntu.
HTML/JSON reporting works without PDF or web extras.

## Try three evidence outcomes

A release check must distinguish a failed check from one that was never
demonstrated. The evidence demo builds/tests a clearly synthetic C++ fixture:

| Scenario | Meaning | Expected check exit |
| --- | --- | ---: |
| Clean | Selected required checks have usable passing evidence | `0` |
| Intentional findings | A configured control has a known failure | `1` |
| Missing tests | Required evidence is absent | `3` |

After source setup:

```bash
python scripts/demo_evidence.py \
  --analyzer "$CPPULSE_ANALYZER" \
  --fixture demo/policy-fixture --output output/evidence-demo \
  --scenario all --formats json,html
```

Add `--resource-dir "$CPPULSE_CLANG_RESOURCE_DIR"` for a custom LLVM layout.
Add `pdf` to `--formats` when PDF dependencies are installed. The summary
retains actual commands, outcomes and run pins. These are functional examples,
not accuracy or performance benchmarks.

For your own project, review and adapt a collection request and policy:

```bash
cppulse collect --request /path/to/collection-request.json \
  --workspace /path/to/project --store /path/to/evidence-store
cppulse check --store /path/to/evidence-store \
  --workspace /path/to/project --policy /path/to/policy.json
cppulse report --input /path/to/evidence-store --evidence --format html \
  --output /path/to/evidence-report.html
```

These are placeholder paths for your reviewed files. Collection executes the
declared commands. Checking and rendering do not silently rebuild or run tests.
A completed collection can retain a failed test; completion is not a policy pass.
Changed selected source/output needs new usable evidence. Imported reports
remain identified as imported claims.

See the [CLI guide](docs/development/public-cli.md) for request structure,
baseline checks, comparison, selectors and exit semantics. Historical review
uses both `--run-id` and `--manifest-sha256`; an old pinned pass remains historical.

| Exit | Meaning |
| --- | --- |
| `0` | Requested operation completed; for a check, the selected gate passed |
| `1` | A policy/finding gate has a known failure |
| `2` | Invalid input, missing required capability or an operational failure |
| `3` | Partial analysis or insufficient evidence for the requested decision |
| `130` | Explicit cancellation |

## Add an explicit build check

The packaged CMake helper calls the same `cppulse check` engine. Its target
checks retained current material and supports selected build dependencies;
collection is a separate explicit recipe. Locate the helper with:

```bash
python -c 'from importlib.resources import files; print(files("cppulse").joinpath("data/Cppulse.cmake"))'
```

Follow the [CMake/local hook guide](docs/development/local-check-integrations.md)
to set the store, workspace and policy. Checks are opt-in and outside ordinary
builds unless enforcement is selected. The current helper uses CMake 3.21+
options, with 3.31.6 exercised; the production minimum-version decision is open.

## Read the four results separately

| Result | Meaning | Interpretation boundary |
| --- | --- | --- |
| Maintenance health | Versioned summary of observed findings | Current scoring uses weighted findings per attempted file; density/context scoring remains work in progress |
| Experimental ranking | Heuristic or optional model prioritization | No demonstrated accuracy or calibrated future-defect probability |
| Evidence completeness | Available evidence for applicable controls | Limited to declared scope, contexts and accepted producers |
| Policy acceptance | Satisfaction of the selected policy and gates | A scoped decision, not universal production readiness |

Inspect parse gaps, disabled rules, inferred contexts and history limitations
beside findings. A score cannot replace a required test, authenticate an
upstream producer or establish every template instantiation. MISRA-labeled
checks are a limited pattern subset; no MISRA/ISO 26262/IEC 62304 compliance,
certification or safety classification is inferred.

| Analysis artifact | Contents |
| --- | --- |
| `findings.json` | Findings, selected rule/configuration metadata and parse scope |
| `git_metrics.json` | Available current-file history signals and limitations |
| `risk_scores.json` | Stored health, experimental ranks, model metadata and hotspots |
| `roadmap.json` | Suggested work with heuristic effort/impact estimates |

Evidence workflows also retain immutable run manifests, producer receipts,
original logs/reports, typed evidence and assessments. API/report consumers
select one snapshot. See [contracts](docs/contracts/v2.md) and
[snapshot presentation](docs/development/snapshot-presentation.md).

## Scope and maturity

Updated **2026-11-14**. Capability claims depend on exact source/artifact bytes,
environment and check scope.

| Area | Current qualification |
| --- | --- |
| Linux workflows | Exercised on Linux x86-64, GCC 14.2, libclang 19, CMake 3.31.6 and Python 3.12.14 |
| Real C++ inputs | All six original projects pinned with retained history; sampled and selected full native scans, plus fmt/utfcpp/consumer pipeline. Parsing/resource gaps remain visible; upstream suites and accuracy are unqualified |
| Installed package | Cloud candidate exercised outside the checkout without Git/GitPython/Node/ML/PDF/web; exact candidate proofs remain separate from later source changes |
| Evidence adapters | Selected Linux/GNU/CTest/report dialects with explicit capability/version limits |
| Docker/Compose | Actual synthetic pipeline/API/proxy/PDF pass. Real fmt repeat hit the finite Cloud disk budget; its attempt is incomplete |
| Other environments | Windows/MSVC/MinGW, macOS, other Python/compiler combinations and broad C++20 coverage require separate qualification |
| Production program | Measured metrics/trends, policy 1.2, VS Code/MCP and scale primitives have scoped checks; full incremental/corpus/platform/empirical/expansion acceptance remains tracked |

The current audit identified detector, configuration, incomplete-ranking and CLI
defects under correction. The [delivery ledger](docs/plans/production-delivery-ledger.json)
records their status. The [full completion plan](docs/plans/cppulse-production-completion-plan.md)
preserves all 118 numbered requirements and 60 original tasks. A smaller demo
or early release does not replace that scope.

Historical [example analyses](examples/) have inconsistent totals and cannot
serve as current benchmarks. [Checkpoint checks](review/checkpoint-20261114/summary.json)
and the [installed-candidate review](review/autonomous/S7-REVIEW.md) retain their
own version boundaries. Aggregate test counts do not establish detector accuracy.

## Local operation

Core workflows need no cppulse account and add no runtime dependency to an
analyzed C++ library. Offline use requires dependencies and policy material to
be installed first. Collection commands execute project code with your local
permissions; review recipes before execution. This is not a hostile-code sandbox.

Hashes identify bytes without authenticating producers or proving complete
dependency coverage. Matching upstream configuration does not replace local
integration tests. Local diagnostic bundles omit source excerpts and unrestricted
environment dumps by default; uploading one is a separate action.

On a Docker-enabled host, the existing workflow uses host-output bind mounts:

```bash
REPO_PATH=/absolute/path/to/cpp-project docker compose up --build
bash scripts/integration_test.sh
```

`OUTPUT_PATH` overrides host `./output`. Analysis/PDF jobs are one-shot services;
API/dashboard remain running. The Cloud synthetic path passed with an explicit
session CA BuildKit secret and sequential builds; no TLS verification was
disabled. Real-input repetition and failure/volume/scale matrices remain separate
qualification work. See the [Cloud checkpoint](docs/checkpoints/20261116/README.md).

## Development and architecture

The native engine exchanges schema-validated artifacts with namespaced Python
analysis/evaluation packages. CLI, API, reports and dashboard consume retained
results; the dashboard does not independently calculate policy gates.

| Component | Responsibility |
| --- | --- |
| `analyzer-core/` | C++17/libclang parsing and native checks |
| `python/cppulse/` | Contracts, orchestration, evidence, policy, analysis and presentation |
| `git-miner/`, `predictor/`, `report-engine/` | Preserved component entry points and tests |
| `cli/` | Preserved C++17 orchestration interface |
| `dashboard/` | React/TypeScript UI and development build |
| `docs/`, `demo/`, `scripts/` | Decisions, contracts, labeled fixtures and local checks |

After installing component prerequisites, build the legacy CLI and dashboard
when exercising those components, then run the shared checks:

```bash
cmake -S cli -B cli/build -DBUILD_TESTING=ON
cmake --build cli/build -j4
(cd dashboard && npm ci && npm test && npm run build)
python scripts/check_local.py
```

The runner invokes native CTest, Python components with coverage, contracts and
dashboard checks. Docker verification is explicit:
`python scripts/check_local.py --section docker`. Extra verification tools are
listed in `requirements-verification.txt`; no new external CI service is needed.
See [CONTRIBUTING](CONTRIBUTING.md), [architecture](docs/architecture.md),
[decisions](docs/DECISIONS.md) and [rule reference](docs/generated/rules.md).

Development uses AI-assisted implementation and review. Automation and authorship
remain transparent; claims require reproducible artifacts and actual checks.

## Product direction and license

Read the [product discovery](docs/research/cppulse-product-discovery.md),
[tool landscape](docs/research/cpp-analysis-tool-landscape.md), and complete
[requirements](docs/specs/production-platform/requirements.md),
[design](docs/specs/production-platform/design.md) and
[tasks](docs/specs/production-platform/tasks.md). Similar capabilities exist
elsewhere; this combined workflow's adoption value still needs validation with
maintainers and integrators.

cppulse is [MIT licensed](LICENSE) for public, private and commercial use.
Third-party dependencies retain their licenses. Managed hosting and external
model/API services, if added, have separate operating costs.
