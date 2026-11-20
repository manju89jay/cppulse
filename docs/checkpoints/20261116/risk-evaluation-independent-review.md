# Independent private risk-evaluation review — 16 November 2026

Reviewed the private input/report schemas, evaluator, temporal tests and current
controlled/unlabeled result boundaries. No evaluator files were edited by this
reviewer.

Initial focused suite: 19 passed. Independently reproduced a failure for a valid
JSON feature integer `10**1000`: `math.isfinite` raised an uncaught OverflowError.
Owner added finite conversion guards and a regression; the final independent
suite `PYTHONPATH=python .venv/bin/python -m pytest -q tests/test_temporal_evaluation.py`
passed **22 tests in 16.80s**.

Reviewed feature availability before prediction, label availability after the
complete declared horizon, training labels available at the training cutoff,
post-cutoff chronological evaluation and project holdouts excluded from training.
The scaler and fitted logistic model receive only training rows. Unavailable
labels never become negative examples. The optional logistic candidate remains
separate from the existing XGBoost/heuristic production model; missing backend,
single-class/absent labels and failed fitting stay explicit.

Independently enumerated 1,134 combinations of four binary labels with both
classes and three-valued tied ranking scores. ROC AUC and grouped average
precision agreed with `sklearn.metrics.roc_auc_score` and
`average_precision_score` within 1e-12. Top-k tie handling uses expected group
prevalence rather than outcome-based tie ordering. Probability losses/reliability
are restricted to probability-like model/baseline outputs; they do not establish
calibration. Report validation now enforces split disjointness, count consistency,
baseline/candidate model presence and reliability-count totals.

Input/provenance and label semantics remain caller claims. Controlled synthetic
results and real unlabeled history cannot establish real future-defect accuracy,
generalization, useful calibration or empirical superiority. The private harness
is a verified implementation slice, not full M6-05/P7 acceptance or promotion of
the existing production risk scorer. Model/artifact/feature/corpus versions and
real cutoff-reviewed labels still need the full program's evidence.

Reviewed evaluator SHA-256:
`8a917a92737beb899f3236d4fc0ac9a8f0809b61849e15f4359c9c6bd8b9ad86`.
Reviewed test SHA-256:
`8dca5f611375f6ac4f6816ad401db1de87fd877e45bab3c551033a1d765d664a`.
