# cppulse: frozen work-in-progress handoff to Codex Cloud

Prepared 14 November 2026. **Implementation is paused. This is not a green release.**

## Saved checkpoint and updated audit

The WIP implementation was pushed to the existing branch at
`79665c4808a7bbd05e69c70ad0bd10379aa8fef1`, directly on top of the earlier
`15492dbfcbc6b20d938e42e760486da4181035f6` checkpoint. The later handover/audit
commit changes documentation and checkpoint records, not implementation.

Read the [updated, filterable full audit](portfolio/cppulse-reconciliation-audit.html)
and [short completion summary](checkpoints/20261114/reconciliation-update/task-completion-summary.md).
All 118 requirements, nine additional obligations and 60 tasks were retained.
The large tasks have not been equated with individual repaired defects.
M0-01 is closed in its inventory scope; no new whole task or milestone is
declared complete. The verified R1 implementation slices are listed separately.

Fresh read-only verification on the pushed implementation checkpoint:

- Native configure/build and **139/139 CTests passed** on the combined frozen source.
- **453 selected Python checks passed**, with source hashes stable before/after.
- Full root collection found **2,322 tests and four collection errors**, due to
  absent `cppulse.maintenance`, `cppulse.measurements` and `cppulse.work_units`.
- Known CR-only LOC correctness and raw native-output schema gaps remain open.

Exact commands/logs are in
`docs/checkpoints/20261114/reconciliation-update/fresh-checks/`.
These newer checks supersede the earlier agent uncertainty about rebuilding the
last native edits. They do not resolve uncovered defects, missing Python
runtime modules, the policy 1.2 failure or real editor-host qualification.

The user requested stopping the current workers, saving their progress and
resuming in Codex Cloud. They then requested using the **same existing branch**:
`codex/cppulse-local-core-20261114`. This checkpoint is directly based on
`15492dbfcbc6b20d938e42e760486da4181035f6`, the previously pushed thirty-commit
delivery. Its earlier history must remain intact; no force-push or main merge.

The handoff save/push is a specific user-authorized exception to the earlier
no-commit/no-push restriction. Subsequent implementation should remain
uncommitted for review unless the user separately authorizes another save/push.
No publication, deployment, marketplace submission, external message or merge
is authorized. The checkpoint intentionally retains failing tests and incomplete
features so a new worker can resume honestly. Do not weaken or skip those tests
to manufacture a green checkpoint.

## Read order and full product authority

1. `TASK_SPEC.md` first, followed by `AGENTS.md`, `CLAUDE.md` and applicable rules.
2. This handoff, then `docs/research/cppulse-product-discovery.md` and
   `docs/research/cpp-analysis-tool-landscape.md`.
3. All three `docs/specs/production-platform/{requirements,design,tasks}.md`.
4. `docs/plans/cppulse-production-completion-plan.md`, the IDE work packages,
   `production-delivery-ledger.json` and `production-delivery-status.md`.
5. `docs/DECISIONS.md`, the architecture and relevant current contracts.
6. `docs/checkpoints/20261114/agents/` and selected evidence/audit records.

The historical branch names and MVP-only stopping rules in early instructions
do not supersede the later user authorization for the complete production plan.
Stay on the selected handoff branch. Keep **all 118 numbered requirements, 60
M0–M9 tasks and nine additional obligations** visible. The broader platform and
focused library-evidence discovery must both remain explicit. An early release,
S7, a scaffold, a source file or aggregate test count is not full completion.
M8/M9 retain their expansion classification and remain in the authorized plan.

Every work package follows contracts → producers → consumers → presentation →
orchestration → integration, with meaningful regressions and independent review.
Check actual current source and hashes: old evidence applies only to its named
source/artifact/environment. The working tree was frozen mid-feature.

## Where work stopped

| Track | Saved implementation and actual evidence | Remaining work / known failure |
|---|---|---|
| R1 native correctness | Already-auto, logical counting, template rules, strict JSON/simple-YAML, ambiguity, configurable 16 MiB file budget and skip reasons. Earlier R1 suite 114/114 passed; the final handover rebuilt the combined source and passed 139/139 CTests. | Reproduce in the new cloud environment. Tested libclang pair is 19.1.7, not every discovered version; this suite does not establish every native metric's correctness. |
| R1 ranking/CLI/presentation | Partial/unverified/history-incomplete files retained in `unranked_files`; four-document verifier checks ranked ∪ unranked scope. CLI/config 70, predictor 110, report 125, dashboard 57 tests plus production build passed in their recorded runs. | No claim these counts constitute a fresh full-suite pass at this checkpoint. |
| Actual real-code R1 integration | Pinned fmt and utfcpp plus tiny authored consumer rebuilt/analyzed. Actual utfcpp API/packaged dashboard/PDF passed: seven unranked files, insufficient-history labels, no browser errors, readable 9-page PDF. | Library parse gaps remain. Full upstream suites, six-original-project qualification and predictive accuracy were not established. |
| P1/R2 developer tooling | `tools/dev.py`, benchmark runner, typed results, shared checks/CI wrappers; 73 focused tests and actual developer-command resource observations passed. | Exact final candidate, representative scale, all platforms and Docker remain unqualified. Existing CI definitions were edited but remote CI was not run. |
| README | Product overview, developer journeys, commands, distinctions and full-plan links rewritten; documented source/runtime flows exercised. | Refresh against finished features and a verified candidate; do not relabel preview as production complete. |
| P2 VS Code | Source, protocol/process tests, explicit commands and diagnostic views saved. Compile and latest 16 unit tests passed. A prior VSIX was built. | Latest source is newer than that VSIX. Real host remains unverified: AF_UNIX/NETLINK restricted; TCP-only Xvfb gets past display then VS Code stalls. Finite settings/package metadata and docs need completion. |
| P3 native metrics | Live-TU LOC/code-LOC, functions/USR/location, semantic CC/length/nesting/parameters, token records, include callbacks and content SHA implemented. Twenty metric tests passed; the later root handover check rebuilt the combined source and passed 139/139 CTests. | **CR-only line endings miscount LOC**; raw actual report schema gate was not run because PYTHONPATH was absent. Unresolved include edges are omitted; legacy total_loc saturates int. |
| P3 Python/scorer | Typed metrics/health/duplication contracts and 69 tests passed. Red tests for measured normalization, health, duplication and trends retained. | Measured normalizer/scorer/hotspot/duplication/trend runtime implementation is absent. Wait for accepted native producer gate, then implement consumers. |
| P4 policies | Profile 1.2 contracts/review details and metric/review evaluator implementation started. Prerequisite gate 532 passed; behavior went from 36 red to 35 passed / 1 failed. | Remaining fixture/control approval-ID mismatch is an agent diagnosis, not a verified fix. Inspect and reproduce. No final runtime/presentation/installed qualification. Domain standard mappings must remain unreviewed until authorized-edition review exists. |
| P5 scale | Draft/private schemas, native finite file selection and Linux resource-limit flags, public execution wrapper and red tests saved. The combined native build and 139 CTests passed in the final read-only verification. | Native tests do not establish scheduler/resource-protocol integration. `cppulse.work_units` runtime is absent, so collection fails. Scheduler/cache/resume/index are not implemented. |
| P6 and expansions | Full requirements/tasks retained. | Deep Git intelligence, temporal model evaluation, MCP/skill qualification, organization/repair/language/hosting expansions remain unfinished. No silent scope reduction. |

Individual checkpoint notes include exact paths, commands, red/green logs,
provenance boundaries and next actions. Do not add overlapping test counts.

## First actions in the new cloud workspace

1. Record `git branch --show-current`, `git rev-parse HEAD`, `git status --short`
   and environment versions. Verify this branch contains the checkpoint and its
   parent baseline. Do not reset to the historical starting commit.
2. Install/locate compiler, matching libclang headers/library/resources, CMake,
   native development libraries, Python, Node and optional PDF/web dependencies.
   Follow the managed cloud runtime guidance. Check Docker executable **and**
   daemon; record unavailable platforms rather than claim Compose passed.
3. Establish the current expected-red baseline. Rebuild native into a new local
   build directory and run CTest; run contract and affected Python/editor tests.
   Preserve failures. A full root collection failure for the absent work-unit
   module is unfinished work, not permission to remove its tests.
4. Add failing CR/LF/CRLF (and actual Clang LFCR behavior) LOC cases, fix the
   measured native producer, and execute raw report schema/semantic validation.
   Address unresolved dependency facts before declaring cache closure complete.
5. Complete Python metric normalization/scoring only after the producer gate.
   Use `analyzed-kloc-context-v3`: actual physical LOC, required job contexts and
   rule versions, null for missing scope, worst complete required context, exact
   raw calculations and no severity proxy as measured complexity. Preserve
   historical scorer identities rather than silently rebaseline trends.
6. Finish and test policy 1.2, fresh work-unit scheduling and checked reuse,
   editor host, remaining integration and the rest of P0–P14. Preserve receipt
   identity and source/work-root boundaries. Cache reuse cannot fabricate a new
   native receipt or promote runtime test/sanitizer evidence to a new source.
7. After each checkpoint update the ledger/status with actual commands, source
   and artifact hashes, independent review and open blockers. Run the required
   component coverage commands, dashboard build and exact installed artifacts.

Useful commands after local dependencies are installed (choose real local
libclang paths; these are instructions, not newly executed handoff results):

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev,ml,pdf,web]' -r requirements-demo.txt
export PYTHONPATH="$PWD/python"
cmake -S analyzer-core -B analyzer-core/build-cloud-resume -DBUILD_TESTING=ON
cmake --build analyzer-core/build-cloud-resume -j2
ctest --test-dir analyzer-core/build-cloud-resume --output-on-failure
cmake -S cli -B cli/build-cloud-resume -DBUILD_TESTING=ON
cmake --build cli/build-cloud-resume -j2
ctest --test-dir cli/build-cloud-resume --output-on-failure
python -m pytest -v tests/test_maintenance_metrics_contract.py tests/test_duplication_contract.py
python scripts/verify_delivery.py
(cd git-miner && python -m pytest -v --cov=src --cov=cppulse.git_miner tests/)
(cd predictor && python -m pytest -v --cov=src --cov=cppulse.predictor tests/)
(cd report-engine && python -m pytest -v --cov=src --cov=cppulse.report_engine tests/)
(cd dashboard && npm ci && npm test && npm run build)
(cd editors/vscode && npm ci && npm run test:unit && npm run compile)
```

Inspect `python tools/dev.py --help` and `docs/development/workflow.md` for shared
checks. Full verification deliberately blocks without required candidate,
installed-smoke and reference-benchmark inputs. Do not substitute a partial
source check or developer-command timing for full acceptance.

## Environment and excluded local material

The tested old host used Linux x86-64/glibc2.41, GCC14.2, libclang19.1.7,
CMake3.31.6, Python3.12.14, Node24.22.1 and clang-format19.1.7. Compiler/libclang
resource identities and system PDF libraries are runtime requirements, not
bundled portable support. Read `requirements-demo.txt`, `requirements-verification.txt`,
`pyproject.toml` and component requirements. Install matching native packages
(nlohmann-json, spdlog, CLI11, GTest and libclang development files) as supported
by the new environment; record deviations and validate them.

Old `review/environment.sh` paths reference the previous scratch workspace and
are not portable. Dependencies, virtualenvs, compiler downloads, npm modules,
build outputs, temporary test Git repositories, old candidate archives and
large immutable run stores are excluded from this Git checkpoint. No synthetic
fixture Git objects/commits are uploaded. Rebuild/regenerate needed artifacts
from the saved source and recipes. Selected logs, manifests, original audit
tables and agent checkpoints are saved under `docs/checkpoints/20261114/`.
Absolute historical paths/timestamps in those records remain historical.

`docs/PRODUCT_VISION.md`, the referenced ADR-007 text and several older handoff
artifacts were unavailable. The original audit describes these gaps. Do not
invent their contents, successful tests, human usefulness studies, standards
review, benchmark numbers, accuracy or certification.

## Suggested Codex Cloud task prompt

> Continue cppulse autonomously on codex/cppulse-local-core-20261114 from its
> latest WIP handoff. Read TASK_SPEC.md first, then AGENTS.md, CLAUDE.md and
> docs/CODEX_CLOUD_HANDOFF.md. Follow the full production completion plan and
> delivery ledger: retain every requirement and all P0–P14 phases. Preserve
> saved work. Start by reproducing the documented failures and establishing
> fresh environment/source-bound checks; do not assume this checkpoint is green.
> Complete contracts, producers, consumers, presentation, orchestration and
> integration with tests and independent reviews. Update the status/ledger at
> every checkpoint. Continue independent work around genuine blockers without
> narrowing scope. No further commits, pushes, main merges, publication,
> deployment or messages without separate authorization.
