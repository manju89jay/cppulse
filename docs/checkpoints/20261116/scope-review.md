# Cloud continuation scope review — 16 November 2026

This is an independent scope/document review, not acceptance of implementation.
Reviewed checkout: `/workspace/cppulse`, branch
`codex/cppulse-local-core-20261114`, starting HEAD
`6f8b662a89b367f8c6883298dc97950150d7ba4f`.
No reset, commit, push, publication or external message was performed.

> Update during continued implementation: the historical eight-obligation planning omission described below has been corrected. Planning JSON/CSV/guard and the execution ledger now all retain nine obligations; `verify_delivery.py --require-complete` still exits 3. See `reconciliation/` for exact commands and all current IDs.

## Authority and preserved inventory

The current user instruction and attached continuation authorize the entire
production program. Historical `feature/full-mvp`, demo-only/S0–S7 stopping
instructions, and suggested conventional commits do not override the requested
branch, full implementation scope, and explicit uncommitted/no-push condition.

The delivery ledger contains **187 items: 118 numbered requirements, 60 M0–M9
tasks and nine supplemental obligations**. All fifteen P0–P14 phases remain.
At review time the ledger states 186 open and one blocked. This records accepted
delivery status, independently of historical audit labels or focused green tests.
The reconciliation audit has 13 verified, 117 partial, 18 implemented but
unverified, 33 missing and six conflicting labels. These are historical labels,
not current-source completion percentages.

Two integrity commands freshly passed:

- `python docs/plans/verify_production_plan.py`: 118 numbered requirements,
  60 tasks, eight supplemental planning obligations, zero missing/unassigned.
- `python scripts/verify_delivery.py`: 187 items, 186 open, one blocked,
  `complete: false`.

The older planning traceability counts eight supplemental obligations; the
execution ledger adds the ninth (`ENV-DOCKER-COMPOSE`). Preserve both historical
source inventories and the full nine-item execution scope. The completion plan's
references to eight do not authorize deleting the ninth. M0-01 is verified in
its inventory-only audit scope, while its delivery ledger remains open; any
promotion requires current evidence and the independent acceptance rule.

## Discovery and specification conflicts

The focused discovery proposes configuration-bound library/header-only evidence
as the strongest initial hypothesis. It explicitly says demand, comparative
advantage, audience and public interface remain unvalidated. The broader
production specification includes application workflows, maintenance/Git
intelligence, organizations, repairs, languages and hosting. The later full-scope
authorization retains all of them. Library evidence is useful prioritization and
acceptance context; it does not replace or narrow the full backlog.

The specification still labels itself proposed and the discovery states it does
not authorize the backlog. Those describe historical documents. The execution
ledger, handoff, PROD-20261114-01 and current user instruction supply later
full-production authorization without rewriting those original records.

Other explicit reconciliation points:

- The design requires analyzed-KLOC caps/weights and worst complete required
  context; historical attempted-file scoring must remain separately versioned.
  Missing required contexts make full health unavailable.
- Historical D8/D13 call MISRA detectors opt-in; later verification notes explain
  all 22 are registered unless disabled and profile controls scoring. Do not
  present the original rationale as a verified detector/configuration claim.
- D11's C++ orchestration remains preserved; D34 refines installed orchestration
  to the Python console dispatcher over namespaced components. This does not
  authorize removal of the native CLI or wholesale rewriting.
- CMake consumer 3.16, helper 3.21 and proposed developer 3.25+ require an explicit
  tested compatibility decision; cross-compilation is not host qualification.
- The C++17 implementation constraint takes precedence over style suggestions
  requiring later-standard span/expected. PROD-20261114-02 records that choice.
- Reused historical D28/D29 identifiers require their `SNAPSHOT-20261114-*`
  provenance labels; do not overwrite current decisions with uploaded text.

## Complete remaining scope by delivery phase

| Phase / principal tasks | Remaining acceptance boundary |
|---|---|
| P0 / M0-01 and all inventory | Current source/artifact-bound evidence and independent review; retain all IDs, original optionality, blockers and scope conflicts. |
| P1 / M0/M1/M3 foundation | Complete native/configuration/partial-state repairs, portable full developer runner, generators/registry generation, exact candidate/CPack/install dependency closure, usable CLI and real Docker/Compose one-shot/failure/repeat/output extraction. |
| P2 / early M7 | Actual installed VSIX in a fresh extension host with installed backend; diagnostics/navigation, explicit commands, Unicode/path mapping, stale/delayed/unsaved results, failures and cancellation. Unit mocks and compile do not close it. |
| P3 / M4 and scorer obligations | Native measured producer gate; normalized measured facts, analyzed-KLOC/context health, measured hotspots/roadmap links, duplication/cohesion only where validated, stable symbol/token/occurrence identities and migration, compatible trends/drill-down/critical-code/goals, original six-project accuracy/resource corpus. |
| P4 / M5 | Policy 1.2 metric/review behavior, exact four-outcome gate arithmetic, evidence adapters and actual compiled/header-only consumer matrices, complete cross-interface/installed flows, reviewed edition-bound automotive/medical packs. |
| P5 / M2 | Bounded isolated workers/resources/cancellation, checked dependency-aware extraction and separate assessment caches, resume/checkpoints, streamed reusable Git history, immutable/indexed catalogs with migration/recovery, bounded pinned query pagination/dashboard; semantic equality before performance claims. |
| P6 / M6-01..04 | Aliases/bots/pairs/former contributors, rename/merge/window semantics, supported co-change/coupling, weighted ownership/familiarity/fragmentation/knowledge/offboarding, component and function/symbol history, shared views with inspectable denominators. |
| P7 / M6-05 | Frozen feature/label availability and actual chronological/project holdouts, baseline comparison/calibration report; preserve negative results and experimental fallback, no invented probability/accuracy. |
| P8 / M7 | Complete measured/history/policy editor views, actual packaged MCP transport/client sessions, reusable installed CMake/hook/Git-host consumers, clean-agent skill journey, identical selected snapshot across all clients. |
| P9 / M1/M2/M3/M4/M5/M7 qualification | Actual GCC and Clang/libclang/platform/Python/C++17/C++20 matrix; Linux, MinGW, MSVC and macOS distinct; clean/offline/outside-checkout/upgrade/rollback/migration/optional-runtime scenarios, repeated 1K/10K/100K-file/history budgets and real developer tasks on exact candidate bytes. |
| P10 / all M8-01..05 | Provider/data/access sub-specifications, team history/alignment, multi-repository portfolio/goals/schedules, branches/task/delivery semantics, issue-tracker cost estimates vs observations, delivery/retry/idempotence/outcome integrations. |
| P11 / M9-01..02 | Supported deterministic dry-run transformations with pins, precise edits, idempotence, compile/tests and clean counterexamples; separately bounded semantic/AI repair/PR preparation with language-specific behavior validation. |
| P12 / M9-03..04 | Concrete supported API/ABI/fuzz/dependency/provenance/process producers and actual clean/failure/unsupported matrices; selected additional languages with full producer/metric/rule/calibration/install/client integration. |
| P13 / M9-05 | Approved hosting/IdP/access/cost sub-specification; SSO/RBAC/project-tenant enforcement across every path, identity lifecycle, storage/retention/secrets/backup/restore/deletion/upgrade/isolation/diagnostics. |
| P14 / whole specification | Reconcile every retained item, repeat exact-artifact full/install/compatibility/resource checks, retain SBOM/notices/changelog/support/upgrade packet; preparation/verification/authorization/submission/publication remain separate states. |

Application, compiled-library and header-only workflows all remain required.
The six original repositories are **fmt, grpc, json, leveldb, poco, protobuf**;
utfcpp is additional and must not substitute for one of them.

## Dependency and acceptance gates

Every work package follows contracts → producers → consumers → presentation →
orchestration → integration. Independent tracks can proceed after their own
contract gates. In particular native LOC/metric actual-output validation precedes
positive normalization/scorer acceptance; stable dependency/fact identities
precede checked cache/reuse; indexed query contracts precede large-project
editor/MCP claims. Shared actual-output/interface agreement precedes acceptance
of a UI consumer.

Source presence and scaffolding cannot close tasks. Root collection physically
lacks `python/cppulse/maintenance.py`, `measurements.py` and `work_units.py` at this
starting checkout. Historical passing CTests do not establish those runtimes,
resource protocols, raw metrics, scale, installation, host behavior or accuracy.
Keep the requirement→code→test ledger bound to current bytes and meaningful
observable outcomes; run all original acceptance checks before whole-task closure.

AC-01–16 require clean installed invocation, honest empty/partial states,
canonical identities, invalidation/equality, policy-only reuse, worker/interruption
retention, no-Git/shallow limits, consumer matrices, missing/stale evidence,
blocking fail/unknown precedence, exclusions/deviation/version explanations,
CLI/API/MCP/report agreement, migrations, packaged presentation, six-project
qualification and the actual clean-session released-command skill journey.

## Missing references and historical evidence handling

`docs/PRODUCT_VISION.md` and the referenced ADR-007 text are unavailable. Do not
invent them. The old `review/...` directories, old environments/candidates,
virtualenvs and immutable run stores were intentionally excluded. Several audit
JSON references still use their historical paths. Saved source-bound copies exist
under `docs/checkpoints/20261114/evidence/` and fresh-check copies under
`docs/checkpoints/20261114/reconciliation-update/fresh-checks/`; use their explicit
provenance, not an assumption that the old paths now exist.

Specific referenced historical logs not present at their original paths or an
obvious same-name saved counterpart include `p2-host-resume/editor-unit-green.log`,
`p2-host-resume/host-tcp-verbose.log`, `p2-resumed/install.log`,
`p3-python-resume/trends-red.log`, `p4-policy-resume/runtime-green-first.log`,
`p5-resume/runtime-red.log`, and `r2-development/facade-final.log`. Related agent
notes and selected logs are retained; those do not recreate missing original
bytes. Earlier `review/autonomous` and checkpoint summaries must likewise be
read as historical evidence, not fresh run artifacts.

## Genuine blockers retained separately from implementation

The following cannot be honestly invented in this Linux implementation task:
actual Windows MinGW/MSVC/macOS executions; authorized standards editions and
qualified mapping review; real consenting maintainer/consumer usefulness tasks;
organization/provider credentials and delivery targets; an approved extra
language/tool/model/IdP/hosting/cost selection; and distribution accounts plus
separate publication/deployment/message authorization. Docker executable and
daemon must be freshly checked rather than inheriting the old blocker. A usable
actual editor host must likewise be retried in the new environment.

These blockers do not authorize stopping independent reversible implementation,
shrinking scope, fabricated tests, or marking blocked requirements complete.
The current instruction prohibits commit/push/remote-ref changes, deployment,
publication, marketplace submission and external messages. Prepare reviewable
local artifacts first; retain release-only conditions open.
