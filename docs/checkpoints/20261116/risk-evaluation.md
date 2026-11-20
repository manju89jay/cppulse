# P7 optional temporal risk evaluation — source-bound slice

All changes are uncommitted. No commit/push, existing predictor replacement,
external model call, deployment or publication occurred.

## Contract → runtime → actual evidence

Added packaged private input/report JSON schemas first, then meaningful tests.
Initial root collection failed on the absent evaluation module; the preserved
red log is `risk-evaluation/initial-red.log`. Implemented the standalone public
module invocation `python -m cppulse.predictor.evaluation`, without modifying
the existing predictor `model.py` or `main.py`.

The module freezes numeric features at declared prediction times and requires
explicit timezone-aware training/evaluation cutoffs and label horizon semantics.
Training labels must be available at the training cutoff. Chronological test
and project-heldout partitions remain disjoint from training, including scaler
statistics and fitted parameters. Unknown labels stay null; post-cutoff labels
are excluded with reasons. Future features, duplicate IDs, malformed horizons,
non-finite/huge features and ambiguous duplicate JSON keys are rejected.
Regular input and output bytes are finite; a FIFO is rejected without blocking.

A train-only standardized logistic experiment uses optional scikit-learn.
Zero-probability, training-base-rate and designated-feature ranking baselines
retain imbalance counts, precision/recall/F1 where applicable, grouped AP/AUC
and expected-tie precision at top20%. Single-class ranking denominators remain
unavailable. Only actual probabilities receive Brier/reliability calculations;
no calibration or future-defect performance claim is made. Missing optional
backend, missing training labels, a missing class and empty test partitions
remain explicit. The retained results are deterministic for the named tested
backend/environment, not a supported-platform reproducibility claim.

The independent scope review caught huge integer features raising OverflowError
rather than ContractError. A guarded finite-number check and regression fixed
that cause. No test was weakened, deleted or skipped. Documentation is in
`docs/development/risk-evaluation.md`.

## Actual checks and artifacts

From `/workspace/cppulse`:

```sh
.venv/bin/python -m pytest -q tests/test_temporal_evaluation.py
.venv/bin/python -m pytest -q tests/test_temporal_evaluation.py predictor/tests
.venv/bin/python -m cppulse.predictor.evaluation \
  --input docs/checkpoints/20261116/risk-evaluation/controlled-input.json \
  --output docs/checkpoints/20261116/risk-evaluation/controlled-report.json
.venv/bin/python -m cppulse.predictor.evaluation \
  --input docs/checkpoints/20261116/risk-evaluation/fmt-history-unlabeled-input.json \
  --output docs/checkpoints/20261116/risk-evaluation/fmt-history-unlabeled-report.json
(cd predictor && /workspace/cppulse/.venv/bin/python -m pytest -v --cov=src tests/)
```

Final focused tests: **22/22 passed**, no skips. Earlier combined focused19 +
existing predictor110 suite: **129 passed**, not an additional independent count.
Required final predictor component command: **110 passed**, source-wrapper
coverage **81%**, 14 dependency warnings, no skips. Its command is logged under
`work/p7-predictor-component-coverage.log`; the component's `src` wrappers have
limited executable coverage because implementations live in packaged Python.
Ruff and Black passed for new runtime/tests. Independent review repeated all
22 tests and compared 1,134 exhaustive tied-ranking cases against scikit-learn
AUC/AP within 1e-12. See `risk-evaluation-independent-review.md`; no remaining
review blocker was identified for this private slice.

The controlled authored12-row input produced actual logistic probability and
baseline results, with eight training rows and two examples in each test
partition. This is a software fixture only. It does not measure real defect
accuracy, calibration or generalization.

The real-history input contains100 actual fmt commits at HEAD
`e69e5f977d458f2650bb346dadf2ad30c5320281`. Exact Git commands and limitations
are retained in `risk-evaluation/fmt-history-provenance.json`. Historical
changed-path counts were computed from actual Git trees; no future labels
were invented from commit messages, current findings/source or SZZ guesses.
All labels remain unavailable, so actual report status is **not_evaluable**,
with zero training labels and unavailable test partitions. Git dates remain
caller-controlled metadata, not authenticated availability evidence. This run
verifies missing-label behavior, not empirical predictive usefulness.

Input/report/source hashes are retained in
`risk-evaluation/source-artifact-sha256.txt`. Model parameters and actual
Python/scikit-learn versions are embedded in reports. Exact final artifact
and platform qualification remains the overall candidate workflow's job.

## Scope retained

P7/M6-05 remains empirically open: independently reviewed real features and
future-defect labels available at their true historical times, representative
chronological/project holdouts, imbalance-aware comparisons and calibration
on final model bytes are not supplied by these controlled/unlabeled artifacts.
This standalone logistic experiment does not validate the existing XGBoost
model, silently switch production scorer identities, or close the full task.
