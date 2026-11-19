# Measured maintenance continuation (2026-11-16)

Scope owner: measured normalization, experimental scorer, token duplication,
measured hotspots/roadmap/trends, immutable publication and report rendering.
All edits are uncommitted. This is an implementation slice, not completion of P3.

## Behavior and evidence boundaries

- `collect`'s existing `native_analysis` normalizer retains typed immutable
  `analysis_metrics`. Legacy reports without raw metrics keep `metrics=None`.
  Per-file source buffer SHA-256, CR/LF/CRLF physical line counts and (when
  complete) token code-line unions are independently checked against retained
  bytes/facts. Job IDs and per-file effective parse-context IDs remain separate.
- `compute_maintenance_health` implements `analyzed-kloc-context-v3` with pinned
  detector versions, physical KLOC density, published caps/weights and unrounded
  fractions. Required incomplete scope returns null aggregate scores; optional
  complete jobs cannot hide a missing required job. Inferred parsing requires
  explicit maintenance-only opt-in and changes the scorer configuration digest.
  Existing attempted-file-v2 scoring remains unchanged, historical and separate.
- Missing/duplicated observation documents cannot manufacture clean health or
  inflate penalties. Metric/observation source, file and parse identities are
  checked. Complete function inventories need every function measurement cell.
- Exact duplication uses kind/spelling windows of thirty tokens, disjoint
  occurrences for self-duplicates, and token/physical-line unions. Truncated
  peers make selected-scope duplication unavailable. Token end coordinates are
  exclusive, including an end at column one.
- Hotspots require measured function complexity and physical LOC plus explicit
  history; severity is never substituted for complexity. Roadmap estimates link
  precise observations/metrics and are labeled heuristic. Trends break across
  scorer, declared context, effective parse context and selected file changes;
  missing measurements yield gaps rather than zero deltas.
- `persist_maintenance_health` reads verified retained native facts and publishes
  a derived immutable calculation through the existing source/material-freshness
  wrapper. Required contexts are explicit caller input; they are not guessed.
  JSON/API snapshot facts already retain these typed documents. HTML/PDF now
  present measured metrics and recorded per-context health separately from
  legacy scores, with nulls, limitations and original artifact links.

## Verification

Initial attempted Python baseline could not collect because dependency setup was
still in progress (pytest, then jsonschema absent). After dependencies became
available, the four saved expected-red suites ran: 31 passed and one fixture
failed before the runtime call. The fixture shared one list between requested,
enabled and executed rules, so disabling a rule removed it twice. Independent
lists repaired this setup bug without changing the disabled-scope expectation.

The initial broader command covering measured suites, contracts and native
inventory suites passed **195 tests**. Independent review by the native owner
identified duplicate/missing observation handling, exclusive token end-lines and
effective-context trend compatibility; each received runtime fixes and retained
regressions. Publication and presentation integration regressions were added.
Fresh final commands/results are appended below after execution.

These synthetic contract/consumer tests do not qualify native producer accuracy,
six-project corpus coverage, empirically calibrated priority/effort, full function
UI/dashboard, complete historical baseline migration, or complete production.
The native owner's separately recorded actual-output gate must pass before any
producer-to-consumer qualification is claimed. No remote CI/publication was run.

## Fresh final verification and actual authored C++ execution

- `python -m pytest -q tests/test_measured_normalization.py tests/test_measured_maintenance.py tests/test_measured_duplication.py tests/test_maintenance_trends.py tests/test_maintenance_metrics_contract.py tests/test_duplication_contract.py tests/test_analysis_inventory.py tests/test_analysis_inventory_contract.py`: **205 passed in31.83s**; log `measured/contracts.log`. A subsequent selected-scope missing-peer duplication regression passed separately. The earlier four-suite consumer log records42 passed; counts overlap and are not summed.
- `ruff check` passed for `analysis.py`, `maintenance.py`, `measurements.py`, `presentation.py`; Black formatted the changed Python files.
- Actual native producer gate was accepted from native owner:142 CTests and11 raw native report schema/semantic validations passed, separately recorded under `native/`.
- `source work/cloud-resume/environment.sh; python work/run_measured_actual.py` ran the actual built native analyzer through public CLI `collect` on clean and triggered authored C++ fixtures. The explicit request retained all22 detector IDs; the default maintenance profile uses15 required detectors. Each normalized9 metric cells and then published health with explicitly required `native-job`. `measured/verify_actual_consumers.py` preserves the executed scratch harness (invoke from checkout root; output destination must be fresh).
- Clean: health100; all default category scores100;45,681-byte9-page readable PDF. Trigger: overall45.45454545454545, memory_safety0 and other selected categories100;47,430-byte readable PDF. These are hand-authored fixture results, not corpus or calibrated accuracy claims.
- JSON/HTML/PDF and immutable raw/derived stores remain under `work/measured-actual/{clean,findings}`. `summary.json` records exact run and manifest pins; small source/artifact hashes are retained with this checkpoint. `pdftotext` confirmed the measured context, overall/category values and method text in generated PDFs.
- An initial broad presentation/routing run passed201 and skipped1 but failed actual sanitizer routing because this environment selected unqualified CTest4.4.5. Root subsequently pinned CMake/CTest3.31.6; the focused routing rerun is separately recorded. No dialect was broadened to conceal that failure.

## Decision for shared decision log

Context: historical health estimates were based on attempted files and generic
complexity proxies; overwriting them would silently change stored meaning.
Decision: preserve the historical scorer and expose the measured profile as
`analyzed-kloc-context-v3`, with explicit context selection, exact rule versions,
physical-KLOC formulas and separate immutable publication. Source/metric gaps
produce null aggregate health. Display original measured values without
recomputing a score in renderers. Why: a developer must distinguish an actually
measured maintenance estimate from missing verification and consumer assurance.
Tradeoffs: calibration remains experimental; complete corpus, migration UX,
advanced function UI, debt goals and all-platform qualification remain open.
Interview angle: "A clean optional job cannot hide a missing required consumer."
- With pinned CTest3.31.6, `python -m pytest -q tests/test_public_normalizer_routing.py` passed2 tests in30.23s (see exact recorded timing in `measured/routing-cmake331.log`). Trigger PDF has10 pages; clean PDF9 pages. Both extracted texts contain exact method, required context and stored score values.

## Public hotspot producer and presentation correction (16 November continuation)

The predictor's compatible public report still used finding severity as a
complexity proxy. New reports now identify `measured-cc-physical-kloc-v1` and
require complete native callable CC, physical LOC and available history. They
retain the maximum callable CC, physical denominator, source-buffer hash and raw
metric pointer. Missing prerequisites produce explicit unavailable scope; the
historical scorer/model ranking remains separate. Historical stored reports keep
their original values and receive an explicit severity-proxy label.

Actual executable fixture: `work/cloud-resume/actual-hotspots/verification.json`
records native CC2/physicalLOC1 with3 changes and1 finding, stored score6000;
source-buffer hash matches the selected C++ file. This is a producer arithmetic
fixture, not a corpus accuracy or verified-current-source consumer claim.
API exposes method/scope; PDF/HTML and dashboard identify the correct formula
without recalculating scores. Predictor110 tests, report128 tests, dashboard61
tests and dashboard build pass in retained `work/cloud-resume/hotspot-*` logs.
Root regression gate is separate to avoid component `tests` namespace collision;
failed collection attempts are retained rather than counted as execution.
Full FR-ANA-04/M4-04 corpus, configuration, priority calibration and downstream
installed-artifact acceptance remain open.
