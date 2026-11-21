# Production scope and maintenance authority

This is the current maintenance interpretation of the user's accepted production
task. It records authority and operating instructions; it does not change an
original acceptance criterion or establish that a feature works.

## Accepted endpoint

The user explicitly authorized the full production task and retained that scope
when requesting closed batches: “Full 187-item scope, original acceptance and
no-commit/no-push/no-publication remain unchanged.”

The endpoint retains all 118 numbered requirements, 60 M0–M9 tasks, nine additional
obligations, and phases P0–P14. [The original requirements](../specs/production-platform/requirements.md),
[design](../specs/production-platform/design.md), [tasks](../specs/production-platform/tasks.md),
and [full completion plan](cppulse-production-completion-plan.md) remain intact.
Tasks section 14, AC-01 through AC-16 and full-plan P14 define completion.
The ordered canonical definition digest is
`e57e89fb7db188f1f4805b95c0bc6f2896c7ab9eef15d851723cc422a0bd2381`.

`TASK_SPEC.md` is the historical six-component MVP specification. Its old branch,
commit and completion instructions do not replace the current user instructions.
The original production documents' “Proposed” headers record their publication
state before the user's acceptance. Acceptance now authorizes implementation;
it does not establish delivery. Historical S0–S7, release A/B/C and expansion
labels express ordering and provenance. They do not cut off the accepted task.
The user's no-commit/no-push/ref-update/merge/deploy/publication/third-party-message
restriction remains in force for this checkout.

The [ledger](production-delivery-ledger.json) records individual acceptance.
An implementation, passing component, generated scaffold or approved plan alone
does not establish whole-requirement acceptance. Missing applicable evidence
prevents a full completion claim. `open` does not mean “no implementation.”

## Language and expansion boundary

C++ is the first supported analyzed language. Python implementation modules and
the TypeScript dashboard are implementation technologies, not claims that those
project languages have qualified analyzers. Current native evidence is the
source-bound Linux C++17/libclang19 profile recorded in candidate105, including
149 real native tests; other compiler/platform/language promises require their
own evidence. This profile does not imply complete coverage of all C++ syntax,
target environments or the full production specification.

Additional analyzed languages, managed hosting, enterprise identity and automatic
semantic refactoring remain expansion work **within the full retained endpoint**.
Their task definitions and dependencies remain unchanged:

| Task | Retained expansion work |
|---|---|
| M9-01 | Narrow deterministic fixes and dry-run patches with precise, idempotent source edits and relevant compilation/tests |
| M9-02 | Agentic semantic refactoring and PR repair with separate language-specific behavior validation and reviewable changes |
| M9-03 | API/ABI compatibility, fuzzing and dependency evidence adapters with explicit format/platform/scope limits |
| M9-04 | Additional analyzed languages with their own metrics, fixtures, calibration and documentation |
| M9-05 | SSO/RBAC and optional managed hosting with access/data-ownership/deployment specification and operating-cost model |

M8 organization/portfolio tasks and all nine design/environment obligations are
also retained. Dependency order and original optionality remain recorded in the
plan and ledger; “expansion” grants no exemption from applicable final acceptance.
No managed service, identity platform or autonomous source-editing capability is
declared qualified by this scope record.

## Decision histories and current engineering instructions

[DECISIONS.md](../DECISIONS.md) retains the MVP decisions and subsequent production
decisions with their existing unique IDs. Its linked index below distinguishes
historical context from current authority. Existing decision text is preserved;
an old decision's presence is not current execution evidence. New entries receive
an unused `PROD-YYYYMMDD-NN` ID. Never reuse or renumber a historical ID.

The current native build standard is C++17, as declared by
`analyzer-core/CMakeLists.txt` and `.claude/rules/cpp-style.md`. Analyze-target
C++20 support is a separate qualification promise; it does not change the product
build standard. `.clang-format` is the formatting source of truth: Google base,
four-space indentation, 100-column limit, plus its explicit overrides.

Older style/safety text recommending `std::span` or `std::expected` does not make
these C++20/C++23 standard-library APIs available in a C++17 build. Use reviewed
C++17-compatible representations and explicit result/status handling, or make a
separate versioned build-standard/dependency decision before introducing them.
Likewise, blanket `noexcept`, mutex and TSan statements in old guidance are not
proof that exception, callback or concurrency behavior has been tested. Preserve
real error/partial outcomes, review the actual worker boundary, and qualify the
promised sanitizer/compiler profile before claiming it. This resolves instruction
precedence without declaring unfinished runtime or environment criteria complete.

The historical safety document's small fixed-file-limit advice does not override
the accepted large/header-only-library requirements. Current configurable limits
and unavailable/partial outcomes must remain explicit. Required scale evidence
is still judged against its original criterion, not a reduced fixture.

## Maintenance procedure

1. Preserve the existing checkout, branch, dirty files, dependencies, logs and
   artifacts. Record HEAD and starting tracked/untracked hashes for owned paths.
   Reuse existing implementations and matching evidence. Keep uploaded snapshot
   provenance separate from live checkout provenance.
2. Select two or three ready existing IDs with their original criteria, owners,
   file claims, prerequisite checks and done conditions. Other feature work stays
   queued. One writer owns each file; the lead owns shared contracts, store,
   pipeline/config/CLI, dependencies, versions/assets and canonical integration.
3. Implement and run affected checks. Freeze shared source/configuration/version
   once; build one coherent candidate when relevant product bytes change, or reuse
   a candidate whose exact relevant source/artifact/input bytes still match.
   Refresh affected prior evidence once per epoch. Preserve meaningful failures.
4. Reuse one independent read-only batch reviewer. Close only whole original
   criteria supported by current evidence. Record the before/after ledger diff,
   commands, actual exits, source/artifact hashes, limitations and next action.
5. Run `python scripts/verify_delivery.py --require-complete --output <record>`.
   Exit 3 means valid evidence with unfinished scope; exit 2 is an invalid or stale
   proof condition to repair. Full-program completion requires exit 0. Do not
   weaken this verifier, requirements or tests to change the result.

Use `python tools/dev.py verify --scope changed` and its explicit `--section`
options for shared local checks; CI calls this same facade. Use
`python scripts/check_generated.py` for a read-only generated-file check and
`--write` only for intentional regeneration. A full run is warranted by changed
inputs, a failure or an unresolved required gate, not by each ledger row.

Allow at most two code writers including the lead and one heavyweight job. Honor
the 4 GiB disk reserve, existing resource limits and per-task output namespaces.
`work/cloud-resume/cold-fixture-registry.json` contains exact guarded restoration
instructions for retained cold fixtures. Restore the required parent/child scope
before replay; never discard failures or assume an archive is available merely
because its old pathname appears in a log. RAM namespaces are session-local:
verify durable source/artifact/input captures before their owning session ends.

## Missing historical references

The source-bound November14 reconciliation audit identifies references that were
not supplied: PRODUCT_VISION.md; the original ADR-007 density-decision text;
selected cloud-transfer/receipt/review ZIP/PDF materials; and complete raw research
chat, interview and experiment records. Some REVIEW/session/review-index material
was available only in uploaded snapshots, not the live checkout. Preserve that
distinction and the audit's exact snapshot hashes. Do not invent their contents,
approval history, runtime results or thresholds.

Current batch111 also records `git show ... 82120d2` exit128 because that required
historical object is absent locally; health-score-v2 is absent from visible local
refs. M0-01 remains waiting for authoritative baseline/history evidence. This
maintenance record does not reconstruct that history or close M0-01. Missing
research/platform/human inputs remain explicit in their corresponding unfinished
requirements and obligations.

## Decision index

The following index is derived from preserved decision headings. Identity is the
recorded ID, not its current line number; the qualification packet pins exact
decision text and source epoch.

| ID | History | Decision |
|---|---|---|
| D1 | historical MVP | libclang over custom parser / Tree-sitter / Clang plugin |
| D2 | historical MVP | CRTP rule engine over virtual dispatch |
| D3 | historical MVP | std::variant rule container over type-erasure |
| D4 | historical MVP | XGBoost over neural networks / logistic regression |
| D5 | historical MVP | SZZ algorithm — simplified keyword-based approach |
| D6 | historical MVP | JSON files over REST for pipeline communication |
| D7 | historical MVP | Health score weighted penalty system |
| D8 | historical MVP | 15 default rules + 7 opt-in MISRA — standard-grounded where possible |
| D9 | historical MVP | WeasyPrint for PDF generation |
| D10 | historical MVP | React + Recharts dashboard |
| D11 | historical MVP | CLI in C++ (not Python) |
| D12 | historical MVP | Cold-start fallback for ML predictor |
| D13 | historical MVP | MISRA rules opt-in via analysis profiles |
| D14 | historical MVP | Configurable assurance assessment separate from health and bug ranking |
| D15 | historical MVP | Expose analysis gaps before awarding positive evidence |
| D16 | historical MVP | Local evidence integrity and a build gate, without replacing sanitizers |
| D17 | historical MVP | Free Agensi skill as a text workflow package |
| D18 | production evolution | Consolidate existing work before expanding the platform |
| D19 | production evolution | Immutable runs and an indexed history catalog |
| D20 | production evolution | Separate fact extraction from assessment caching |
| D21 | production evolution | One installed product and one locally runnable verification path |
| D22 | production evolution | Version scoring, policies, and comparison identities explicitly |
| D23 | production evolution | Automate extension and candidate preparation with behavior checks |
| D24 | production evolution | Keep the tool landscape as a repository reference |
| D25 | production evolution | Consolidate product discovery separately from feature commitments |
| D26 | production evolution | Present cppulse as an engineering prototype in application materials |
| D27 | production evolution | Delegate prototype stabilization using an isolated cloud checkpoint |
| D28 | production evolution | Stabilize the existing prototype without expanding its product scope |
| D29 | production evolution | Use shared local checks, transparent synthetic history and explicit report dispatch |
| D30 | production evolution | Validate demo totals against independent producers |
| D31 | production evolution | Autonomous core stages with retained technical review packets |
| D32 | production evolution | Scope health to attempted current sources and retain unavailable results |
| D33 | production evolution | Version meaning and publish coherent local snapshots |
| D34 | production evolution | Install canonical Python components beside a separately qualified native analyzer |
| D35 | production evolution | Resolve current attempts once and preserve failed analysis facts |
| D36 | production evolution | Judge observed collection separately from process exit and pre-run intention |
| D37 | production evolution | Separate the selected collection job from the observed parse context |
| D38 | production evolution | Give component installations the same YAML profile semantics |
| D39 | production evolution | Keep coverage measurements and policy versions explicit |
| D40 | production evolution | Transfer evidence without promoting foreign claims |
| D41 | production evolution | Bind sanitizer outcomes to observed instrumentation and test controls |
| D42 | production evolution | Compare actual distributed artifacts and application evidence separately |
| D43 | production evolution | Share public workflow engines and reject stale current material |
| D44 | production evolution | Keep finding regressions and snapshot presentation explicit |
| PROD-20261114-01 | production evolution | Execute the full reconciled production scope |
| PROD-20261114-02 | production evolution | Reconcile C++17 style and configurable library limits |
| PROD-20261114-03 | production evolution | Preserve snapshot decision provenance |
| PROD-20261114-04 | production evolution | Qualify installed editor bytes against one closed backend wheelhouse |
| PROD-20261116-01 | production evolution | Preserve exact native measurement and runtime capabilities |
| PROD-20261116-02 | production evolution | Make Git tooling optional for installed static analysis |
| PROD-20261116-03 | production evolution | Bind declared reviews to exact artifact bytes |
| PROD-20261116-04 | production evolution | Expose measured scoring and bounded read clients explicitly |
| PROD-20261116-05 | production evolution | Keep incremental primitives conservative and catalog reads finite |
| PROD-20261116-06 | production evolution | Bound candidate MCP and skill claims to exercised installed bytes |
| PROD-20261116-07 | production evolution | Freeze and exercise the original six-project corpus without substituting samples |
| PROD-20261116-08 | production evolution | Keep behavioral and temporal claims in separate finite channels |
| PROD-20261116-09 | production evolution | Keep execution budgets separate from native detector settings |
| PROD-20261116-12 | production evolution | Publish bounded native work as original independent executions |
| PROD-20261116-13 | production evolution | Require parsed-buffer coherence for fresh measured claims |
| PROD-20261116-14 | production evolution | Retain actual used SDK buffers outside project source |
| PROD-20261116-15 | production evolution | Separate finite service regression observations from ordinary repair verification |
| PROD-20261116-16 | production evolution | Display exact stored measured evidence and watch its selected source scope |
| PROD-20261116-17 | production evolution | Version atomic store heads and refuse unsupported legacy access |
| PROD-20261116-18 | production evolution | Expose explicit store transitions and format negotiation |
| PROD-20261116-19 | production evolution | Evidence-gated single-writer execution board |
| PROD-20261116-20 | production evolution | Retain exact selected layer bytes before runtime qualification |
| PROD-20261116-21 | production evolution | Review finite runtime bytes before actual immutable-image execution |
| PROD-20261117-01 | production evolution | Collect live tmpfs output through a pinned in-container helper |
| PROD-20261117-02 | production evolution | Keep independent code moving against frozen source inputs |
| PROD-20261117-03 | production evolution | Qualify one installed epoch and preserve resource interruption |
| PROD-20261117-04 | production evolution | Retain interruption receipts and distinguish late daemon completion |
| PROD-20261117-05 | production evolution | Bind query optimization to selected report bytes |
| PROD-20261117-06 | production evolution | Compare supported Git timestamps without floating-point rounding |
| PROD-20261117-07 | production evolution | Reserve external rule hash slots and opt in to derived MCP cache writes |
| PROD-20261117-08 | production evolution | Preserve the eager-reader failure while specifying bounded native projections |
| PROD-20261117-09 | production evolution | Close only the three approved original requirements |
| PROD-20261117-10 | production evolution | Resume full scope through source-bound installed import closures |
| PROD-20261117-11 | production evolution | Prove false-pass guards with genuine installed controls |
| PROD-20261117-12 | production evolution | bounded native byte ingestion and unknown scopes |
| PROD-20261117-13 | production evolution | Bound work-unit raw reports and preserve cold fixtures reversibly |
| PROD-20261117-14 | production evolution | Disclose behavioral versus retained legacy history scope |
| PROD-20261117-15 | production evolution | Check integrity before declining unrepresentable SDK proof |
| PROD-20261117-16 | production evolution | Aggregate complete measured file priorities by declared component |
| PROD-20261117-17 | production evolution | Separate excluded architecture members and retain excluded duplication peers |
| PROD-20261118-18 | production evolution | Project checked native inputs for the legacy predictor |
| PROD-20261118-19 | production evolution | Separate bounded SZZ label provenance from retained-history completeness |
| PROD-20261118-20 | production evolution | Bound SDK capture using its actual stored representation |
| PROD-20261118-21 | production evolution | Generate native registration and reject unsupported configuration |
| PROD-20261118-22 | production evolution | Preserve accepted scope and distinguish analysis language from implementation language |
| PROD-20261118-23 | production evolution | Close small batches against exact bytes and resolve historical instruction precedence |
| PROD-20261118-24 | production evolution | Gate compatibility health on retained prerequisite evidence |

| PROD-20261118-25 | production evolution | Define shared history independently of unavailable symbol production |

- `PROD-20261118-26` — deterministic maintenance replay, freshness, explicit scope and separate historical formula; [decision](../DECISIONS.md#prod-20261118-26-preserve-calculation-identity-during-explicit-maintenance-replay). Acceptance remains evidence/ledger governed.

- `PROD-20261118-27` — repository identity and observed/absent proxy-label provenance; [decision](../DECISIONS.md#prod-20261118-27-keep-repository-and-proxy-label-identity-explicit). Original PR-04/M0-05 conditions remain unchanged.

- `PROD-20261119-28` — resolve local detector packs separately from scoring and policy.
- `PROD-20261120-29` — integrate reviewer fixes without inheriting old score or evidence claims.
- `PROD-20261120-30` — qualify literal exclusions and range-for advice on the receiving host.
- `PROD-20261120-31` — match dashboard notices to the resolved production dependencies.
- `PROD-20261121-32` — separate legacy analysis completion from health qualification.
- `PROD-20261121-33` — order tied roadmap rows by file and category after impact.
- `PROD-20261121-34` — bind master CI to current producers and explicit test scopes.
- `PROD-20261121-35` — refuse late bounded metadata changes during publication.
- `PROD-20261121-36` — close the dashboard lock under the hosted npm version.
- `PROD-20261121-37` — trust the Actions checkout for the pinned Git provider.
- `PROD-20261121-38` — include canonical contract tests in component coverage.

## Receiving checkout provenance

The object and reference observations in batch111 apply to its originating
workspace. The receiving checkout resolves the pinned commit
`82120d26b51f99b64068f9d66f6e000fcaee97c2` as the proposed second parent.
Its isolated review checkout has no matching branch ref. The receiving source
repository retains a local remote-tracking reference at
`refs/remotes/origin/feat/health-score-v2`. Those local observations leave
the authoritative baseline and remaining M0-01 history requirements open.
