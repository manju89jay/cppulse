# Independent portfolio source review — 16 November 2026

This is a new, explicitly source-authorized review after the completed installed-only clean-agent journeys. It does not change or relabel those earlier clean-session records. No implementation or test files were edited. The review reads the private module/contracts, public CLI integration, tests, development documentation, M8-01–05 task acceptance and the P10 plan. It does not qualify external providers, whole M8/P10, release bytes or platform support.

## Findings

### P2 — Public tick reports exit 0 while an active local delivery remains exhausted

Location: `python/cppulse/cli.py:630–636`.

The exit calculation considers only `result['outcomes']`. Exhausted jobs are skipped on subsequent ticks, so an identical invocation immediately changes from an error exit to a successful exit although its only delivery is still exhausted and no report exists. This affects callers using the process exit to supervise local delivery; the JSON correctly exposes the exhausted count, but its process status contradicts the previous invocation for the same unresolved work.

Reproduced with an authored one-occurrence UTC schedule, max_attempts=1, and a controlled local `_publish_report` OSError. First CLI call: exit 2, active exhausted=1. Second identical call with no injected failure: exit 0, active exhausted=1, outcomes=[]. Exact reproducer and output are `work/portfolio-independent-repro/reproduce.py` and `results.json`. This uses real independent local stores and journal publication; it performs no external delivery.

Recommended change: define tick exit semantics from active generation job counts, retaining a nonzero operational status for failed/exhausted jobs even when no new attempt is due. Explicitly define pending-retry semantics and test both waiting failures and exhausted no-op ticks in the public CLI suite. Keep successful local delivery separate from partial report/unknown goal status.

### P2 — Retained report validation accepts missing context inventory with a met context-specific goal

Locations: `python/cppulse/portfolio.py:202–203`, `309–324`; private `report.schema.json` contexts items.

The report validator validates measured health and its source/scorer identities, then recomputes goals by comparing only the health document's required-context ID labels with the goal's labels. It never validates the displayed project context objects against the context contract or checks that these required IDs actually occur in the project's context inventory. A retained report with an empty context inventory can therefore validate while asserting a context-specific historical goal was met.

Reproduced by reading the existing exact native-clean pin through `build_portfolio` from `work/portfolio-actual-final/config.json` (read-only), then replacing only that report project's contexts with []. `validate_report` accepts it; native-clean-target stays observed_met. The accepted inconsistent report is retained at `work/portfolio-independent-repro/accepted-inconsistent-report.json`. This is a report-validation consistency defect; the checked store reader and initial producer were not observed corrupting contexts.

Recommended change: validate each displayed context with the public context validator, require unique IDs and valid digest bindings, and require the selected health/goal context IDs to resolve into the project inventory. Add a retained-report mutation regression for removed/renamed/malformed contexts. Context IDs alone are also weaker than a method/configuration digest across changed project pins; document that distinction or pin full required context identities if goals are intended to survive run updates without silently changing their consumer configuration.

The same reproduction also replaces health.sha256 with 64 zeros and is accepted. This is a narrower validation limitation: a parsed document does not retain the exact original artifact serialization needed to reconstruct its original byte SHA. Either retain raw-byte/manifest-descriptor bindings for an offline integrity check, re-open the exact store pin in an integrity-checking operation, or state clearly that validate_report checks internal goal semantics rather than verifying the reported artifact SHA against pinned bytes. It must not be represented as independent authenticity verification.

## Verified boundaries and limits

The lexical canonical absolute root/store checks, checked no-symlink store reads, and bidirectional selected-store/output overlap rejection are consistent with the documented trusted-local-configuration boundary. This is not tenant authorization or a hostile-code sandbox. No independent root/output escape was demonstrated.

The producer selects exact run ID and manifest SHA, avoids latest pointers, retains project-local read failures, leaves aggregate_health null, and refuses historical goal acceptance for unverified/partial collections. It preserves per-project source digest, file-scope digest, full scorer digest, context inventory and run times. The replay cutoff rejects runs completed after the intended report time. The report's complete status denotes readability, not policy acceptance.

Timezone conversion uses the retained TZif bytes it hashes; generation bindings reject provider changes. DST gap/fold behavior, retry admission beyond local-midnight catch-up rollover, finite attempts, config-generation retention and output descriptor protections were inspected. Journal pending state precedes publication; immutable report bytes and atomic final state support retry after interruption. Unknown stale locks require operator recovery, which is documented. Successful report rechecks apply to later due occurrences, not every historical artifact on every no-op tick. These are explicit local semantics, not daemon/provider qualification.

## Validation and reviewed identities

Command from `/workspace/cppulse`:

```sh
PYTHONPATH=python .venv/bin/python -m pytest -q --basetemp=/workspace/cppulse/work/portfolio-independent-pytest tests/test_portfolio.py tests/test_portfolio_cli.py
```

Observed exit 0: **33 passed in 11.33s**. Log: `work/portfolio-independent-pytest.log`, SHA-256 `6be29619e8b0e444449a7c0ebe95fbb5bf61d5f0e42b6f8bef43f929d34c94ab`.

Reviewed SHA-256 values before coordinator fixes:

| File | SHA-256 |
|---|---|
| python/cppulse/portfolio.py | aed629b50893e26d981bc56a2f4d2b2958c545a2897eb52382a36b19f8e8994e |
| python/cppulse/cli.py | 3b0992abb9df94f13aacf26ec07918be8c580dabc94559f4dbe8963d40035229 |
| tests/test_portfolio.py | de17b9f96143cd30b772fa1f59e5b31a12ca84ae06dfe195d0095e1652f76ca8 |
| tests/test_portfolio_cli.py | d3459cd4621f9f8e0de5248427155b8243683e699d599235536d4a20d6709983 |
| private config.schema.json | deaa4ac9b4a7112dc1bb58f467e1da672509896458bd6a6d6bc2e47dfdc1cc3d |
| private report.schema.json | 7a43bb6fb5a540d64dbc487c426521ce012db1b5d7294bca1137a7991609f158 |
| private state.schema.json | 6d2c9dc1b1b3953f0b986a4bf4390723ff119f7ab61161d2292301142d2d3283 |
| docs/development/portfolio.md | 115969ec4b3c49e2f906ca33c740d540c18582250d5a1105edb051f2282c1edb |

The separate actual-fixture source-hash refresh belongs to the coordinator; this review does not claim the old portfolio-actual-final.json matches later source changes. No network, commits, push or external messages were performed.

## Follow-up recheck of reviewed fixes

Finding 2 is resolved in reviewed module SHA-256 `5abb6affd156ec48c8eadefffcc330fac6bf4451f9a9919ac27df40181ba3f81`. A freshly generated current-schema report from the earlier exact native fixture config is accepted with `expected_config`. The original missing-context reproduction now rejects with `Portfolio projection differs from its pinned original manifest`. Changing the health SHA, raw health bytes, parsed health document, raw manifest bytes, expected-config project pin or expected-config team history also rejects. Exact independent recheck script/output: `work/portfolio-independent-repro/recheck.py` and `recheck-results.json`.

The fix retains original manifest and health JSON bytes, checks selected manifest SHA and copied context/source/run fields, validates typed contexts, checks health descriptor ID/contract/SHA/size/parsed equality, resolves scored required contexts, and optionally anchors the complete selection to the separately trusted expected configuration. These are byte consistency and request-binding checks, not producer authentication. Producer and successful-tick readback pass the trusted configuration. Per-project and report output bounds remain explicit; the module retains other independent projects when a selected project projection is oversized.

Repeated focused command with `--basetemp=/workspace/cppulse/work/portfolio-independent-pytest-recheck`: **36 passed in 15.79s**, exit 0; `work/portfolio-independent-pytest-recheck.log`. Reviewed updated identities:

| File | SHA-256 |
|---|---|
| tests/test_portfolio.py | 16e9543d7718edde91afb31bc3727ed260ff82a8aef9bf33c687e4cca905ebf3 |
| private report.schema.json | 7e9c27076a013c85a6a069c3df86f4debe1aaaf534e123f3c82a40f30ce263fd |
| docs/development/portfolio.md | 4d0a41e3173606f0262ca9e751509ba6b05bc7d72973073eaefdffee0920bd0a |

Finding 1 remains pending at this recheck: CLI source hash is still the original `3b0992abb9df94f13aacf26ec07918be8c580dabc94559f4dbe8963d40035229`; its strict active-count exit fix is being completed separately by the coordinator. Original finding descriptions above remain historical review evidence; later resolution does not erase them.
