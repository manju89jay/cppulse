# VS Code, MCP and portable-skill production work packages

Planning snapshot: 2026-11-14. No extension, MCP server or clean-session skill
was implemented or validated by this planning task. Existing local integrations
are a foundation, not completion of M7/S11. Do not narrow FR-UX-10 to SARIF export
alone, a mock editor test, a generated template or a skill text ZIP.

## Current foundation and gaps

| Existing foundation | What integration must still add |
| --- | --- |
| Installed `cppulse` CLI, doctor/config, explicit collect/assess/check/explain/report/baseline/SARIF workflows | Stable client capability/version handshake; friendly progress/errors; clients that call supported public commands rather than import internal modules |
| Checked manifest/run pins, original artifact hashes, one `snapshot_view`, historical versus current-check semantics | Editor/MCP run selection, per-response identity checks, stale-editor and delayed-response handling; bounded queries when S9 ships |
| SARIF 2.1.0 with per-occurrence rule/location/context, checked comparison annotations, Unicode-column provenance | Actual editor diagnostics with URI/root/path mapping and tested editor character-unit conversion; not raw byte-column reuse |
| Installed API/dashboard/PDF agreement; optional web/PDF/ML separation | IDE/MCP agreement over the same pins; VSIX/native offline installation; no mandatory FastAPI/PDF/ML account or Node process outside the host |
| Local CMake, pre-commit and Bash workflow templates | Reusable packaged examples, supported-version/client integration tests and actual distribution guidance |

Current `snapshot_view` is consolidated. The legacy findings endpoint already
has basic page/per-page/category filtering, but indexed immutable-run/history
queries remain S9 work. An early extension must advertise a finite tested input
limit, retain explicit gaps, and use the eventual bounded query contract rather
than claim large-project support from the current whole-view response.

## Work sequence and actual acceptance evidence

Every work package follows contracts -> producers -> consumers -> presentation
-> orchestration -> integration, with checks before dependent work. Keep old
public commands and stored schema versions compatible or give actionable
migration errors. Pin SDK/host/extension dependency versions at implementation;
this plan does not invent a supported editor release range.

| Package | Implementation and dependencies | Required acceptance evidence |
| --- | --- | --- |
| IDE-01: shared client contract | Versioned capability description, runtime discovery, finite/paged selection, paired run/hash pins, exact rule/severity/context/score tokens, unsupported-version errors. Depends on existing installed CLI/contracts; align S9 query protocol before large-input claims. Specify stored history separately from fresh current checks. | Contract tests reject mixed pins, unknown capabilities, unsafe paths, malformed reports and incompatible versions. CLI/API/editor/MCP golden fixtures share source bytes and IDs, with no duplicated policy or score computation. |
| IDE-02: VS Code read-only preview | Create actual extension project/manifest and package. Discover configured installed CLI via explicit argv; run doctor on an explicit user action. Read a selected retained run/SARIF, populate Problems diagnostics, navigate to source, show run/gate/scope/gaps and open report/evidence links. Initial Linux setup can proceed while broader metrics/platform work continues. | Build an installable VSIX and install it into a fresh real extension host. Activate against a copied real C++ fixture and actual installed cppulse, not only a mocked VS Code API. Verify diagnostic counts/rules/severities, duplicate basenames, spaces/quotes, path root mapping, Unicode/non-BMP positions, baseline multiplicity, context and exact run/hash identity. |
| IDE-03: explicit execution and lifecycle | Add user-invoked analyze/collect/check/report commands, request/policy/baseline selection, progress, cancellation and separate raw logs. Reading or opening a project must not execute project recipes, modify files or refresh an old assessment silently. Trusted-workspace/capability boundaries and shell-free arguments are explicit. | In actual extension-host tests, opening/reading a workspace launches no build/test and writes no run. Explicit clean/finding/missing-evidence actions show 0/1/3, invalid request 2 and cancellation 130 without turning unknown into clean. Verify missing executable/native runtime/optional extra, tool crash, timeout, malformed JSON, stale header/binary, unsaved editor text and delayed older responses. Preserve prior historical pins while the current gap remains visible. |
| IDE-04: MCP reader and separated execution capability | Implement actual local MCP transport/handlers for run metadata, health, findings, hotspots, policy gaps, rule/policy documentation and bounded artifact reads. Use the public checked-view/query layer. Any execution interface is a separate explicitly enabled capability and uses the same public workflow engine; no arbitrary shell/SQL/internal-module escape. Core stays account-free and usable offline. | A real MCP client connects to the packaged server, negotiates supported versions and exercises all tools, including rule/policy documentation, over the same actual retained run as CLI/API/editor. Verify exact status, numeric display tokens, source/context/rule identities and original artifact hashes. Test invalid IDs/pins, expired historical versus current checks, unsupported capability/schema, changed current pointer, cancellation/closed client and oversize output. Reading tools execute no project commands and write no repository/store state. |
| IDE-05: complete product views | Expose the later measured metrics/trends, consumer comparisons, coverage kinds, sanitizer outcomes, ownership/coupling and evidence-policy controls through shared clients once their producers and query contracts pass. Do not label the initial Problems preview complete M7. | For each producer slice, run identical selected snapshots through installed CLI/API/dashboard/MCP/editor; compare the relevant underlying values/IDs/gaps. Exercise partial/unsupported/imported data, a blocking failure with high aggregate score, and required unknown. Large-data paging/search uses S9 limits and stable cursors, including concurrent latest-pointer changes. |
| IDE-06: platform and compatibility matrix | Qualify real native/Python artifacts and VSIX installation on Linux x86-64, Windows MinGW, Windows MSVC and macOS as separately declared combinations. Carry configured versions, native discovery, dependency notices, migration/rollback and offline instructions. Editor portability does not prove native analyzer portability. | Install final artifacts outside checkout on each named host and run actual C++ analysis plus explicit build/check and Problems navigation. Include Windows separators/case/path spaces, native library discovery, C++17/C++20 cases and Python versions promised by the release. Exercise clean install, missing/mismatched dependencies, unsupported editor/tool versions, upgrade/rollback and older supported schemas/baselines. Record unavailable hosts as blocked, not passed or removed. |
| IDE-07: reusable integration distribution | Complete packaged CMake/pre-commit/Git-host templates and consumer examples over the public engine. Include installation/migration/version checks and clear operation-versus-gate exit handling. Reuse shared local checks; add no new external CI service. | Real compiled-library/header-only consumer examples execute packaged integration commands. Default build remains opt-in; explicit dependency/check targets propagate observed fail/unknown. Run local hook framework and wrapper over real 0/1/3 outcomes; qualify any advertised container/hosted integration separately. No automatic ref checkout, remote comments or uploads. |
| IDE-08: portable free skill | Produce a versioned text skill using only documented released commands/capabilities, install prerequisites and offline operation. Include correct historical/current selection, unknown/failure explanations and optional dependency instructions. Text loading does not install or qualify native software. | In a fresh agent session without source/bootstrap paths, follow the packaged skill against actual installed artifacts to analyze, collect, check, explain and produce/open reports. Retain the transcript and IDs; compare results with direct CLI/MCP/editor. Unknown capabilities fail clearly; absence of PDF/web/ML leaves core usable. No account/subscription or external API is required for local analysis. AC-16 is incomplete until this execution happens. |
| IDE-09: complete release packet and publication gate | Build versioned VSIX/server/skill/integration artifacts with checksums, source identity, dependency inventory/notices, support matrix, changelog, compatibility guide and user documentation. Prepare listing text from actually qualified behavior. Keep candidate verification and marketplace/registry submission as distinct states. | Verify exact final artifact bytes in clean install/host/client tests, plus a real developer installation/interpretation task review. Prepare reviewable publication material and retain the qualified matrix. Marketplace/registry submission or any outreach happens only with its separate authorization; a ZIP/VSIX alone is not submission or publication. |

## Required end-to-end scenario set

Use actual installed core/native outputs, not fabricated editor-only fixtures,
for the final positive/negative matrix. Small pure client fixture tests complement
these cases rather than substitute for them.

1. Clean C++ case: all interfaces show the same selected scope and passed gate.
2. Native finding case: compiler/CTest may pass while the selected rule fails;
   Problems retains every occurrence and report/CLI/MCP show the same failure.
3. Missing report/unsupported context: partial/unknown remains visible, with no
   old positive carried over during refresh or editor navigation.
4. Header/binary/flag change: explicit current check rejects stale material;
   historical pinned views remain historical, not silently recollected.
5. Two equal basenames, line insertion, repeated anchors, explicit rename limits,
   context changes and suppression expiry: preserve backend decisions exactly.
6. UTF-8 multibyte and non-BMP source text: editor navigation follows documented
   character-unit conversion and retained source; edited/unsaved source is stale.
7. Interrupted/cancelled execution and a delayed older read: no stale green
   state, duplicate process, orphan child or mixed-run response.
8. Optional runtimes absent, no account/network, unrelated cwd and path spaces:
   installed core and read-only IDE/MCP remain useful with actionable limits.
9. Large accepted workload and concurrent history/latest reads: stable pinned
   page/query identities, bounded transfer/memory and no whole-project download.
10. Every promised platform/artifact combination: actual install/run evidence,
    not only cross-compilation or extension API mocks.

## Traceability and completion states

| Specification item | Covered work and completion rule |
| --- | --- |
| FR-UX-10 | IDE-01 through IDE-09. All three deliverables (VS Code, MCP and portable skill) must exist, use shared public results, and be actually exercised. |
| AC-12 | IDE-01/02/04/05 plus the actual scenario set. Cross-interface agreement extends existing CLI/API/report/dashboard proof to editor and MCP; initial SARIF display alone is partial. |
| AC-16 | IDE-08/09. Retain a clean-session actual execution transcript using documented released commands. A skill draft is incomplete. |
| M7-01 | IDE-01 and the explicit read/execute separation in IDE-03/04; client negative-contract fixtures pass before dependent implementation. |
| M7-02 | IDE-02 through IDE-06; actual run/health/findings/hotspot/policy-gap MCP tools and real VS Code diagnostics pass against installed public fixtures. |
| M7-03 | IDE-07; packaged examples execute the public engine rather than independent gate/scoring logic. Existing local templates are a useful subset, not automatic completion. |
| M7-04 | IDE-08/09; clean-session validation and artifact verification complete preparation. Submission/publication remains separately observable and authorized; do not claim it happened from preparation alone. |
| NFR-MNT-01/03/06 | IDE-01/05/06/09; shared contracts/registry, separate presentation, version/compatibility tests and consistent rule metadata. |

The early VS Code preview is a concrete deliverable that can proceed from the
existing installed core. It does not cancel the remaining measured metrics,
scale, behavioral analysis, platform qualification, MCP/skill or production
backlog. Later reviews close these packages; only explicit user-approved scope
changes may remove a requirement. No implementation, Git mutation, publication,
message or new external CI operation was performed for this planning note.
