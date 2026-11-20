# cppulse research and goal review packet

Created: **2026-11-14, after the initial cloud delegation**.
Purpose: help the project owner verify the saved research, motivation, proposed
product, and original delegation boundary before agreeing further work.

The substantive research and proposals below were saved before delegation.
They are not a verbatim archive of every chat message or a record that every
proposed feature has been implemented. This index and its review ZIP are new
local review aids; they do not change the product scope or authorize cloud work.

## Start here

| Read | Document | What to verify | Preservation |
|---|---|---|---|
| 1 | [Product discovery and working direction](cppulse-product-discovery.md) | Motivation, users, pain points, existing capabilities, candidate distinction, maintainer/consumer workflow, diagnoses, open questions | Saved before delegation; updated 2026-11-11 |
| 2 | [C++ analysis tool landscape](cpp-analysis-tool-landscape.md) | 72 tool-family rows in eight categories, high-level features, availability, official source links | Saved before delegation; snapshot 2026-11-05 |
| 3 | [Production requirements](../specs/production-platform/requirements.md) | Broader proposed product behavior, configurable policies, libraries, usability, scale, maintenance and releases | Saved before delegation; proposed 2026-11-04 |
| 4 | [Production design](../specs/production-platform/design.md) | Architecture, data contracts, identities, caching, scoring, policy examples, CLI/CMake and editor interfaces | Saved before delegation; proposed 2026-11-04 |
| 5 | [Implementation plan](../specs/production-platform/tasks.md) | M0–M9 ordering, release boundaries, acceptance criteria and definition of done | Saved before delegation; proposed backlog 2026-11-04 |
| 6 | [Decisions log](../DECISIONS.md) | Why choices were proposed, tradeoffs and historical scope decisions | Checkpoint contains through D27; local D28 and D29 came later |
| 7 | [Original cloud task brief](../../output/cloud-transfer/start-cloud-task.txt) | The narrower stabilization/demo work originally delegated | Local saved handoff brief; see provenance note below |

The requirements/design/backlog are an earlier broad proposal. The later
discovery document examines a more focused library-evidence direction. These
documents need reconciliation into an agreed goal; their existence does not
make every backlog item an accepted implementation commitment.

## Motivation and proposed direction

The discussion began with the wish to make cppulse useful beyond one project:
production-quality engineering, meaningful assessment of applications and
libraries, configurable requirements, and build integration as approachable
as familiar C++ tooling. Free distribution, maintainability, scalability, and
repeatable bug-fix/release workflows were explicit priorities.

The working direction subsequently discussed was:

> cppulse could help maintainers establish and maintain trustworthy verification
> evidence for the C++ configurations they claim to support.

The proposed benefit is to show which declared compiler/platform/macro/build
configurations have applicable, current evidence, which failed, and which are
unknown, stale, or missing. A library consumer could compare that scope with
its own use and see the additional verification it needs.

This is a product hypothesis. The saved research does not establish unique
capability, validated demand, certification, or suitability for a safety
critical application. Existing analyzers, CMake/CTest, orchestration tools and
verification suites already address substantial parts of the problem.

## Where each requested topic is covered

| Topic from the discussion | Saved location |
|---|---|
| High-level competitor features, including CodeScene | Tool landscape; discovery's proposed distinction and practical value |
| What cppulse supports today versus future ideas | Discovery: Current implementation |
| Major C++ users and unresolved/difficult problems | Discovery: Users and developer pain points |
| Why another tool could be useful | Discovery: Proposed distinction and practical value; What remains to validate |
| Real library/header-only example | Discovery: Proposed maintainer and consumer workflow, using nlohmann/json |
| Exact change, invocation and diagnosis | Discovery: Maintainer setup; A precise change and its diagnosis |
| Maintainer releases and consumer integration | Discovery: Release evidence and consumer adoption |
| Configurable ISO 26262, IEC 62304 or custom requirements | Discovery: Results and configurable standards; requirements; design sections 5–7 |
| Scoring and its limits | Discovery: Results and configurable standards; design section 5 |
| Build/CLI/CMake experience | Discovery workflow; design section 8 |
| Scale, resource bounds and incremental execution | Discovery: Scalability maintainability and usability; design section 4; backlog M2 |
| Easy bug fixes, new rules, verification and releases | Requirements; design section 9; backlog M1 and per-change workflow |
| Editor/VS Code and agent interfaces | Design: API, editor, and agent interfaces; backlog M7; proposals rather than proof of shipped extensions |
| Free local use and Agensi distribution | Discovery: Free distribution and agent skills; design section 10 |
| Ordered implementation and acceptance | Production tasks; historical TASK_SPEC.md for original MVP order |

The concrete example is hypothetical: replacing a library's configurable
exception macro with a raw throw can break a build using `-fno-exceptions`.
Proposed collection runs declared build/test recipes, and assessment explains
failed or missing evidence for that exact profile. It is not a reported
cppulse run against nlohmann/json. Proposed `collect`/`assess` commands and
CMake hooks in these documents are not evidence of implementation.

Policy satisfaction would describe the evidence checked against a selected,
versioned policy. It would not turn a code-health score into ASIL, a medical
software safety class, or certification. Unknown and unsupported checks must
remain visible. Linux results would not establish Windows or ARM support.

## What was transferred before cloud work

Repository: [manju89jay/cppulse](https://github.com/manju89jay/cppulse).
Initial isolated branch: `codex/job-application-demo-20261113`.
Immutable checkpoint:
[`b89dce9d22b37ef44843a68eb3373c525b4b8e94`](https://github.com/manju89jay/cppulse/commit/b89dce9d22b37ef44843a68eb3373c525b4b8e94).

Both research documents, all three production-platform documents, the portfolio
Markdown, README, decisions through D27, and the selected draft schemas were
included in that checkpoint. On 2026-11-14, a read-only GitHub check confirmed
the immutable blob identities for the two research documents, three platform
documents, decisions and portfolio Markdown. The local core documents also
match the saved manifest after normalizing line endings; the decisions file
has later appended entries.

Evidence available locally:

- [Original selected-file manifest](../../output/cloud-transfer/checkpoint-manifest.json): file identities for the checkpoint selection.
- [Original local checkpoint backup](../../output/cloud-transfer/local-checkpoint-backup.zip): selected local files before transfer, preserving their original line endings.
- [Review verification report](../../output/review/checkpoint-verification.json): fresh local comparisons and remote blob verification.
- [Original task receipt](../../output/cloud-transfer/cloud-task-receipt.json): checkpoint and task identity; its November 13 status is historical.
- [Cloud chat](https://chatgpt.com/c/6af74749-cc68-83ed-a768-6200cd97a9cf): subsequent discussion and work may differ from the initial handoff.

The saved task brief is a local record of the handoff's intent and restrictions;
it is not a byte-for-byte transcript of the prompt submitted through the browser.
The manifest, backup, task brief, receipt, portfolio PDF and this review packet
are local generated materials, not source documents included in that checkpoint.

## Original delegated scope

The selected cloud task was to make the **current prototype build, pass checks,
and provide a reproducible job-application demo**. The handoff expressly kept
the full production-platform proposal and new evidence-policy workflow outside
that initial task, while including them as reference material.

Consequently, the broad specification was saved and available, but its complete
implementation was not the original cloud assignment. Later instructions in
the cloud chat are separate from that initial boundary. This review packet
does not assess completion of that later work or change its instructions.

## Supporting materials

- [Portfolio overview and application paragraph](../portfolio/cppulse-project-overview.md).
- [One-page portfolio PDF](../../output/pdf/cppulse-project-overview.pdf), generated locally; presentation material rather than a product specification.
- [Historical MVP task specification](../../TASK_SPEC.md) and [operating instructions](../../AGENTS.md).
- [Architecture](../architecture.md) and [historical ADRs](../adr/ADR-006-production-readiness.md).
- Draft contracts: [assessment](../schemas/assessment.schema.json), [assurance evidence](../schemas/assurance_evidence.schema.json), [assurance policy](../schemas/assurance_policy.schema.json), and [findings](../schemas/findings.schema.json).

The ZIP includes the complete current `docs/` tree, the historical task and
operating files, README/license, the relevant handoff/provenance files and the
portfolio PDF. Historical documents can contain claims not freshly verified;
the later discovery document records known limitations. A schema is a contract
draft, not proof that a collector, evaluator or integration exists.

## Context recovered for this review and remaining gaps

These notes were reconstructed from the supplied conversation on 2026-11-14;
they were not an additional document in the pre-cloud checkpoint:

- The initial trigger was an unsolicited Agensi message offering a marketplace
  for standalone agent skills. The sender claimed about 65,000 monthly visitors,
  free non-exclusive listings and a 70% seller share. Those are sender claims,
  not independently verified market evidence. The user's preference was free
  initial availability. A skill listing would package instructions around the
  tool; it would not itself implement or distribute every native dependency.
- The user asked to inspect CodeScene and other tools before deciding the goal,
  then asked for developer pain points, a concrete library example and realistic
  maintainer/consumer invocations. The synthesis preserves those substantive
  topics, but no complete raw research-session transcript or webpage archive
  was saved in the core documents.
- Rough delivery estimates were discussed in chat. They were not measured or
  approved schedules and are not a validated delivery commitment in these specs.
- User interviews, competitor experiments, a selected pilot library, agreed
  acceptance thresholds, and a final reconciled scope remain to be established.
- Some early decisions (D14–D17) use implementation-like language. Read them as
  historical design intent alongside the later proposal and discovery status.
- The requirements document refers to `docs/PRODUCT_VISION.md`; that file is
  absent from this workspace. It is not part of the saved packet.
- Employer-specific local `REVIEW.md` notes were deliberately excluded from the
  public checkpoint and this general research packet.

## Owner verification

Use the existing documents to verify whether the audience, pain points,
differentiation hypothesis, workflows, configurable-policy semantics, operating
requirements and delivery order reflect your intent. Then resolve the earlier
broad platform proposal against the later focused direction and state the
implementation boundary explicitly. No new product goal or scope is selected
by this index.
