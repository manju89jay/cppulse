# Current native policy input binding

Fresh policy evaluation requires `analysis_inventory.items.buffer_coherence ==
verified` in addition to the existing execution/source/context guards before
native metrics, findings, parse coverage, or analysis-derived required-context
presence can qualify. Missing legacy, unverified and mismatched buffer facts
remain unknown, including apparent numerical/finding breaches. Build/test
required-context evidence retains its independent existing qualification.

Every fresh assessment carries `native_input_binding:
tu-buffer-coherence-v1`; historical assessment bytes and evaluator predicate-set
versions remain unchanged. The additive schema and historical/current validator
migration are root-owned.

The new `tests/test_policy_buffer_coherence.py` isolates old matched context facts
from the separate buffer proof, checks all three native coverage predicates and
metric thresholds, verifies explicit synthetic positives, and checks that
unbound breaches cannot become definite failures. These are synthetic contracts,
not producer execution or real-project accuracy evidence. Policy fixture
normalization now composes retained-byte raw measurements after existing
mutations; partial/failed rows preserve incomplete measurement status. The
legacy native fixture default remains unchanged.

Initial new regression gate: 14 passed. Pre-marker broader gate: 186 passed,
one fixture migration failure (dangling analysis_metrics after intentionally
removing inventory); corrected by removing the dependent metrics document too.
Final marker/schema-aware gate: **188 passed, no skips, 45.50s**,
`work/policy-buffer-full-current.log`. This includes historical profile1.2
replay on a private fact copy (original facts unchanged), fresh unknown result,
and rejection of a forged current-marker positive. Ruff/Black/diff-check clean. All changes
remain uncommitted. This does not close full P4/P5 acceptance.
