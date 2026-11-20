# cppulse — Maximum-Depth Review

**Date:** 2026-06-12 · **Purpose:** interview-readiness review for a Software Architect
candidacy (defense / safety-critical embedded, HENSOLDT-style). Four passes:
Understand → Value → Strategic Fit → Engineering. All test suites were executed
locally on Windows as part of this review.

---

## Pass 1 — UNDERSTAND

### What cppulse actually is (one paragraph)

cppulse is a six-component pipeline that takes a C++ git repository and produces a
prioritized technical-debt report: a C++17/libclang static analyzer emits per-file
findings from 22 AST pattern rules (15 default + 7 opt-in MISRA), a Python git miner
computes 10 behavioral metrics per file (churn, authorship, simplified-SZZ bug-fix
counts, knowledge silos), a Python predictor merges both into a feature matrix to
produce a 0–100 health score, per-file risk levels, and an hour-estimated refactoring
roadmap, and a FastAPI/WeasyPrint report engine plus a React dashboard deliver the
results. The problem it solves — for an engineering lead inheriting a legacy C++
codebase — is not "find more warnings" but "tell me *where* to spend limited
refactoring budget first," by fusing *what the code looks like* (static findings)
with *how the code behaves over time* (git history). That fusion-and-prioritization
framing is genuinely the right problem; the execution has specific credibility gaps
detailed below.

### Architecture as implemented (verified against code, not docs)

| Component | Reality check |
|---|---|
| `analyzer-core` (C++17) | Real libclang cursor visitation. CRTP base (`rule_base.h`) + `std::variant` of 22 rule types + `std::visit` dispatch (`rule_engine.h`) — static dispatch, no virtuals, as documented. One TU per file, fresh rule set per file, single-threaded. |
| `cli` (C++17) | Subprocess orchestrator via `popen`; runs analyzer ∥ git-miner concurrently (`std::async`), then predictor → report. Shell-quoting with real injection tests. |
| `git-miner` (Python) | gitpython; per-file metrics; silo = single contributor in 12 months; "SZZ" = keyword-matched fix commits + whole-file blame at parent. |
| `predictor` (Python) | XGBoost (≥50 files) or honest weighted heuristic (<50); stratified-CV metrics; SHAP if installed; health score = `100 − Σ(weighted findings)/file_count`. |
| `report-engine` (Python) | FastAPI + Jinja2 + matplotlib; WeasyPrint optional with graceful skip; schema validation on inputs. |
| `dashboard` (React/TS) | Vite + Recharts; typed API client; 5 of 9 components tested; `tsc --noEmit` clean. |

**Extension points:** adding a rule = new CRTP class + add to the `AnyRule` variant +
`make_rules()` (3 touch points — workable, not pluggable); rules are individually
toggleable with threshold overrides via `.cppulserc`; components are replaceable
behind 4 schema-validated JSON contracts (`docs/schemas/*.schema.json` exist and are
enforced in CI's integration job).

### The three load-bearing technical facts

1. **No compilation database.** `analyzer.cpp:215-220` parses every file with only
   `-std=c++17 -x c++` — no include paths, no defines, diagnostics suppressed. On any
   real codebase, includes don't resolve, so type-dependent checks silently degrade to
   best-effort syntax matching. Token-level rules (goto, C-cast, `new`, typedef) stay
   reliable; type-sensitive ones (implicit conversion, missing override, record-type
   init checks) do not. This is the first thing a clang-literate interviewer will probe.
2. **The health score in code ≠ the health score in the docs.** README and
   `architecture.md` document a weight-normalized, per-KLOC penalty.
   `health_scorer.py:94-105` actually computes `100 − (Σ weighted findings ÷ file
   count)` — no KLOC normalization, no division by the weight sum; category scores use
   separate arbitrary scale constants (15/10/5/12). Three conflicting definitions of
   the project's headline number.
3. **The ML label is circular.** `predictor/src/main.py:71-90` defines "buggy" as
   `memory_findings ≥ 1 OR bug_fix_commits ≥ 3`, then trains XGBoost on features that
   *include those same two columns*. The model re-learns its own label rule; CV
   metrics are inflated by construction. The README's "trained on SZZ-labeled git
   history" is inaccurate — SZZ runs, but its output is not the training label.

---

## Pass 2 — VALUE ASSESSMENT (brutally honest)

### Competitive overlap

| Tool | What it already covers | What cppulse adds over it |
|---|---|---|
| clang-tidy | All 9 modernization rules (`modernize-*`), raw new/delete (`cppcoreguidelines-owning-memory`), arrays (`-avoid-c-arrays`), with full compile-DB type resolution and fix-its | No prioritization, no history, no score |
| clang static analyzer | Real path-sensitive uninitialized reads, leaks | No repo-level aggregation |
| cppcheck (+ MISRA addon) | MISRA C/C++ checking incl. official rule texts | Nothing comparable on history |
| CodeChecker | Orchestrates the above at scale, diffs runs, web UI | No behavioral mining, no single score |
| SonarQube C++ | Hundreds of rules + quality gates + "security rating" letter scores | Weak git-behavior fusion |
| **CodeScene** | **Hotspots = complexity × change frequency, knowledge maps, off-boarding risk — the closest competitor; this is cppulse's git-mining angle, productized since ~2015** | cppulse is C++-AST-deeper per finding |
| IWYU / Sourcetrail | Orthogonal / abandoned | — |

**Verdict:** as a *product*, cppulse's individual capabilities are each covered by an
incumbent, and its analysis is *less* trustworthy than clang-tidy's because it parses
without a compile database. **Market value: 2/10 as-is.** No one should adopt it over
CodeChecker + CodeScene today, and that's fine — it's a hobby project.

**The differentiated niche is real, though:** *a single auditable, deterministic,
safety-weighted health score with an hour-costed remediation roadmap, fusing static
and behavioral signals*. CodeScene is closest but is SaaS, opaque, expensive, and not
safety/MISRA-oriented. Nothing open-source produces "one defensible number + ranked
plan" for safety-critical C++. That niche is exactly Pass 3.

**Portfolio value: 7/10** — and this is the rating that matters for you. It
demonstrates: polyglot system design (C++17/Python/TypeScript), clean contract-first
component boundaries (schema-validated JSON, ADR-004), a non-trivial C++ design choice
you can defend at a whiteboard (CRTP + variant vs virtual dispatch — and *why*:
value semantics, no heap, closed rule set), real CI with an end-to-end integration job,
6 ADRs that record actual trade-offs, and dogfooding on 2.2M LOC of real code. It would
be 8.5/10 if the headline number weren't currently indefensible (see below) — an
interviewer who recomputes the leaderboard finds that `examples/grpc/findings.json`
holds 38 findings while the README claims 9,408, that fmt's modernization category
scores 0.0/100, and that the 99.0-vs-60.9 spread is mostly file-count dilution, not
code quality. **The single highest-risk artifact in the repo is the leaderboard.**

**Smallest pivot that changes the value:** stop competing on *detection* and own
*scoring + evidence*. Make the score the product: documented formula, per-KLOC
normalized, deterministic, with a traceability annex (score → category → rule →
file:line). Optionally let clang-tidy/cppcheck *feed* findings into the same scorer.
That converts "weaker clang-tidy" into "the audit layer nobody else has."

---

## Pass 3 — STRATEGIC FIT: "C++ Memory-Safety / Modern-C++ Health Score"

**Feasibility verdict: strong fit, mostly already built — IF you reposition the
detection layer honestly and fix the score.** This direction also aligns with where
the industry is in 2026 (CISA/NSA memory-safety pressure, C++ Safety Profiles
discussion, MISRA C++:2023 adoption) — excellent interview talking points for defense.

### Already in place (verified)

- Raw `new` / `delete` / C-array-parameter detection via real AST checks
  (CPP-MEM-001..003), each with remediation suggestion and confidence field.
- 7 MISRA C++ rules mapped to MISRA C++:2023 rule numbers (README table), correctly
  **opt-in** via profile with a documented rationale (D13 in `docs/DECISIONS.md`) —
  architecturally the right call and a good story ("I shipped MISRA-on-by-default,
  saw false signal on general-purpose code, wrote the decision record, moved it
  behind a profile").
- Weighted scoring with safety categories weighted 3.0×/2.5×, profile mechanism,
  per-rule enable/threshold config, PDF report, schema-validated artifacts — i.e.,
  the *audit-shaped delivery* layer that clang-tidy lacks.
- Deterministic inputs→score path exists in principle (no randomness in the scorer).

### Missing, with honest difficulty

| Capability | Difficulty | Notes |
|---|---|---|
| `compile_commands.json` support | **Hours-days** | `clang_CompilationDatabase_fromDirectory` is ~50 lines. Single biggest credibility unlock; without it, type-aware rules are demo-grade. |
| bounds-unsafe API calls (strcpy/sprintf/memcpy…) | **Hours** | `CXCursor_CallExpr` + name table. Cheap, high-signal for the memory-safety pitch. |
| span/string_view adoption metric | **Days** | Type spelling of params — a *positive* adoption metric, nice differentiator. |
| const-correctness | **Days-weeks** | Member-function constness is feasible on AST; parameter/local const analysis gets fuzzy fast. |
| Uninitialized **reads** | **Research-grade** | Needs CFG/dataflow. Current MISRA-007 is "declared without initializer" — fine, but never call it uninitialized-*read* detection. Don't build; delegate to clang analyzer if ever needed. |
| Ownership clarity | **Research-grade** | Real ownership inference is a PhD topic; a defensible proxy is "owning raw pointer = raw ptr member + delete in destructor" (days). |
| CERT-C++ mapping | **Hours** | Mostly a documentation/traceability matrix over existing rules. |
| Auditable score | **Hours** | Fix formula, document it, emit per-rule contribution breakdown in the PDF. |

### Technology approach

**Keep libclang C API for now; do not rewrite.** For the 6-week, interview-first
horizon: (a) the existing 22 rules are token/cursor-level and libclang handles them;
(b) a libTooling/AST-matcher rewrite costs weeks and unstable-API maintenance for zero
interview value; (c) the architecturally mature answer — which you should *say* in
interviews and record as ADR-007 — is that the detection layer is commoditized
(clang-tidy could be ingested as a finding source through the same JSON contract),
and cppulse's defensible layer is **scoring, fusion, and auditability**. Adding
compile-DB support to the existing libclang core is the one detection investment
worth making.

### Defense-buyer reality check

HENSOLDT-style organizations buy: deterministic, reproducible results (same commit →
same score, hash-stamped inputs); traceability (score → rule → MISRA/CERT clause →
file:line evidence); air-gapped operation (cppulse is already fully offline — say
this out loud, it beats CodeScene/Sonar SaaS); and tool-qualification awareness
(ISO 26262 TCL / DO-330 concepts — you don't need to implement qualification, you
need to demonstrate you know the score is a *decision-support* metric, not a
certified verification result). Frame cppulse as the *fleet-level health KPI and
refactoring planner* that sits above qualified analyzers, never as a replacement
for them.

---

## Pass 4 — ENGINEERING REVIEW

### Test execution results (all run during this review)

| Suite | Result | Coverage / notes |
|---|---|---|
| cli (GoogleTest, MinGW Windows) | **16/16 pass** | Includes genuine shell-injection tests (semicolon, backtick, `$`) — interview-quotable. |
| analyzer-core (Windows) | **build FAILS** | `CMakeLists.txt:20-24` hardcodes Ubuntu LLVM paths; fails even with MSYS2 clang 21.1.7 installed. Builds and tests fine in CI (Ubuntu). |
| git-miner (pytest) | **71 pass, 0 fail** | 91% line coverage; tests build real temp git repos (good). |
| predictor (pytest) | **67 pass, 0 fail** | 62% overall — but `main.py` 30% and `roadmap_generator.py` 33%: the pipeline entry and roadmap ranking are essentially untested. Core (model 91%, features 99%, scorer 97%) solid. |
| report-engine (pytest) | **72 pass, 2 skip** | 93%; WeasyPrint cleanly skipped on Windows. Latent bug: `pdf_generator.py:313` catches only `ImportError`, but GTK-missing raises `OSError` → `/api/v1/report/pdf` would 500 instead of the documented 503. |
| dashboard (vitest + tsc) | **30/30 pass, tsc clean** | 5/9 components untested; no coverage tooling installed; `npm audit`: 1 high (lodash via recharts) + 3 moderate — notable for a defense pitch. |
| root (`tests/test_gitlab_ci.py`) | **8 pass** | Nice touch: CI config itself is tested. |

CI (GitHub Actions) is genuinely good: clang-format gate, ruff+black, C++ build+test
with libclang, all Python suites, dashboard build, and an **end-to-end integration
job that runs cppulse on itself and schema-validates all four artifacts**. A
mirrored GitLab pipeline exists. This is above typical hobby-project bar.

### Findings that could embarrass you (ranked)

1. **Leaderboard not reproducible from its own evidence** (HIGH). README claims gRPC
   9,408 findings / 99.0; `examples/grpc/findings.json` contains 38 findings. fmt
   shows category score 0.0/100 inside an overall 60.9. Score formula in code matches
   neither README nor architecture.md. An interviewer with 15 minutes and `jq` finds
   this. Fix or remove before sharing the repo.
2. **Circular ML labels** (HIGH). `_derive_labels` vs feature set, detailed in Pass 1.
   One honest sentence fixes the pitch; ~2h fixes the code (label from SZZ only, drop
   `bug_fix_commits`/`memory_findings` from the feature matrix, report honest CV).
3. **No compile DB** (HIGH, expert-only). Covered in Pass 3.
4. **Windows source build broken for analyzer-core** (MEDIUM). Ubuntu-only find paths;
   you develop on Windows — interviewers may try `cmake -B build` on whatever they have.
5. **Doc-vs-code drift** (MEDIUM). architecture.md still says "15 rules… 22 with
   profile" in one place and embeds a stale "gRPC 99.0" paragraph with a mojibake `�`
   at line 162; `.claude/rules/safety-critical.md` claims a thread-safe mutex-guarded
   FileAnalyzer that doesn't exist (it's single-threaded); README pins `python3` paths
   the orchestrator hardcodes (breaks on Windows, where the `python3 -c "…"` quoting
   in `orchestrator.cpp:160-163` is also broken).
6. **Hygiene** (LOW). `requirements.txt` pins drift from the environment that actually
   passes (xgboost 2.0.3 pinned, 3.2.0 used); lodash high-severity advisory;
   `.claude/session-state.md` committed (17 tracked `.claude` files — the rules/agents
   files are actually *interesting* AI-tooling artifacts, but session state is noise);
   commit `"Fix clang format"` and `"feat : add"` spacing in recent history.

### What's genuinely good (use these in interviews)

- CRTP + `std::variant`/`std::visit` rule engine — correct, modern, and you can
  articulate the trade-off vs virtual dispatch and vs a plugin architecture.
- Contract-first decoupling with *enforced* JSON schemas, including in CI.
- Proper libclang resource discipline (every `CXString` disposed; TU/index lifecycles
  correct) and graceful degradation paths (oversized files, unparseable files,
  empty repos, <50-sample ML fallback — all explicitly handled and tested).
- Six real ADRs + a DECISIONS.md with honest reversals (MISRA-out-of-default).
- An actually-shipped GitHub Action with PR diff-comment bot, plus self-testing CI config.

---

## (a) 60-Second Interview Pitch

> "cppulse started from a problem I kept hitting in ADAS platform work: static
> analyzers tell you *everything* that's wrong — thousands of findings — but never
> *where to spend a limited refactoring budget*. So I built a pipeline that fuses two
> signals: a C++17 libclang analyzer with 22 AST rules — memory safety weighted 3×,
> plus an opt-in MISRA C++:2023 profile — and a git-history miner that measures how
> code *behaves*: churn, bug-fix density, knowledge silos. A Python layer fuses both
> into one auditable health score and an hour-costed refactoring roadmap, delivered
> as a PDF report and a REST/React dashboard. Architecturally it's six components in
> three languages, decoupled through schema-validated JSON contracts, so any stage is
> replaceable — CI runs the whole pipeline end-to-end on the repo itself and validates
> every artifact against its schema. I made some deliberate trade-offs I'm happy to
> defend: a CRTP-plus-variant rule engine instead of virtual dispatch, MISRA moved
> behind a profile after dogfooding showed false signal on general-purpose code —
> that's ADR'd — and everything runs fully offline, which matters in this industry.
> The honest limitation: detection itself is commoditized — clang-tidy does more —
> so the roadmap is to make cppulse the *audit layer*: ingest qualified analyzers'
> findings through the same contracts, and own the deterministic, traceable score
> that a safety organization can actually defend in a review."

(~55 seconds. The pre-emptive limitation sentence is the architect move — it converts
the strongest attack into evidence of judgment.)

## (b) Ranked Backlog — max 15 hours, interview-impact per hour

| # | Item | Hours | Why first |
|---|---|---|---|
| 1 | **Make the score defensible.** Implement the documented formula (per-KLOC density, weight-normalized), add a per-rule contribution breakdown to risk_scores.json, then `make showcase` to regenerate the leaderboard so README, code, and `examples/` JSONs agree. Record as ADR-007. | 5 | The leaderboard is the first thing an interviewer checks and currently the easiest thing to break. Also *becomes* your best story: "I found my own headline metric didn't survive audit, so I fixed it the way I'd demand at work — formula, evidence trail, decision record." |
| 2 | **De-circularize the ML, honestly relabel.** Label = SZZ-derived bug-introduction counts only; remove `bug_fix_commits` and finding-count features from training; report the (worse, honest) CV numbers; reword README from "bug prediction" to "risk prioritization." | 3 | Converts the most attackable claim into a demonstration of ML rigor — very on-brand for safety-critical. |
| 3 | **`compile_commands.json` support** in analyzer-core (`clang_CompilationDatabase_fromDirectory`, fall back to current flags; note it in README). | 4 | Kills the expert-level objection and is the only detection-layer investment with interview ROI. |
| 4 | **30-minute hygiene sweep:** fix `architecture.md` mojibake + stale 15/22-rule and gRPC paragraphs, delete the thread-safety claim in `.claude/rules/safety-critical.md`, untrack `.claude/session-state.md`, align `requirements.txt` pins, `npm audit fix` for lodash. | 1.5 | Cheap insurance against "sloppy" first impressions. |
| 5 | **Fix Windows builds:** add MSYS2/`llvm-config`-based libclang discovery to `CMakeLists.txt`; replace hardcoded `python3` + the broken Windows `python3 -c "…"` quoting in `orchestrator.cpp` (write a temp script file instead). | 1.5 | You demo from a Windows laptop; the repo should build where you'll be showing it. |

**Total: 15h.** Deliberately cut: const-correctness and span-adoption rules (days, low
interview delta), SARIF export, dashboard test coverage, libTooling migration, any new
rule work, CERT matrix (mention it as roadmap instead — it costs nothing to *say*).

---

## Post-fix note (2026-06-14) — leaderboard regenerated + made reproducible

All six showcase projects are now regenerated through the ADR-007 density pipeline
(`feat/health-score-v2`). The old size-biased, under-counted leaderboard is gone.

| Project | Old (stale) | New | Old findings | New findings |
|---|--:|--:|--:|--:|
| nlohmann/json | 96.8 | **88.4** | 177 | 979 |
| POCO | (97.8) | **70.6** | — | 17,017 |
| gRPC | 99.0 | **68.2** | **38** | **30,843** |
| Protocol Buffers | 93.9 | **47.2** | 146 | **106,765** |
| fmt | 60.9 | **34.7** | 372 | 6,966 |
| LevelDB | — | **18.9** | — | 1,621 |

Resolves the ranked findings:

- **#1 (leaderboard not reproducible).** FIXED. Scores are now decoupled from repo
  size (gRPC is the largest repo yet mid-pack; tiny json scores highest). Added
  `scripts/verify_scores.py`, which re-derives every score *independently* from each
  `findings.json` using the documented ADR-007 caps/weights and asserts it equals the
  pipeline output — **6/6 reproduce exactly**. CI runs it on every push (integration
  job) over both the fresh self-analysis and all six committed examples. A README note
  points readers at it. This converts the single highest-risk artifact into the
  credibility story.
- **#5 (mojibake `�` in architecture.md).** FIXED. Root cause was `refresh_showcase.py`
  writing the file as cp1252; added `encoding="utf-8"` to its read+write and repaired
  the stray byte. Full-repo UTF-8 scan is clean.
- **ML labels (#2):** F1 now ranges 0.72–0.89 across the regenerated projects (json
  0.894, fmt 0.853, grpc 0.818, protobuf 0.718) — no 1.0 tautology. LevelDB sits at
  0.994 (small, cleanly separable dataset; not the old circular-label artifact, which
  was removed in WP-C).

Also removed the stale committed `examples/poco/report.pdf` and fixed the example
README template, which was emitting a `report.pdf` link unconditionally (most examples
never had one). The PDF *feature* (report-engine, ADR-005) is unchanged.

Note: four category scores read `0.0` (protobuf & fmt complexity+modernization) —
these are density-saturated (finding density exceeds the documented cap), legitimate
and explainable under ADR-007, kept as-is per the project owner's call (credibility
over cosmetics for a hobby project).
