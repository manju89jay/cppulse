# Optional retrospective risk evaluation

The private evaluation module compares a train-only logistic experiment with
zero-probability, training-base-rate and designated-feature ranking baselines.
It does not replace cppulse's current predictor, qualify its XGBoost model, or
establish calibrated future C++ defect risk. No runtime subprocess, external
model service, account or corpus download is used.

Run it explicitly from an installed candidate:

```sh
python -m cppulse.predictor.evaluation --input observations.json --output evaluation.json
```

Install the `ml` extra to enable the optional scikit-learn model. Without it,
baselines remain available and the candidate result explains its unavailable
backend. A missing training class or empty training set remains unavailable;
an empty test partition never becomes a zero-error result. Exit 0 means a
validated report was written, including when empirical evaluation is
unavailable. Invalid inputs or output errors exit 2; check the exit code before
reading an existing output path. Files are local JSON, not executable recipes.
Input is a regular file bounded to 8 MiB, 100,000 observations and 64 features;
output is bounded to 32 MiB. Symlink final inputs/outputs are rejected and
output is replaced atomically only after validation.

## Freeze features, labels and projects before evaluation

The draft schemas are packaged under
`cppulse/contracts/schemas/risk_evaluation_private/`. Input version is `1.0.0`.
See the complete controlled example in
`docs/checkpoints/20261116/risk-evaluation/controlled-input.json`.

Every observation declares an ID, project, prediction time, the latest
availability time of **all** its numeric features, optional binary label and
label-availability time. Unknown labels require both label fields to be null.
Feature names must match the declared finite set exactly; non-finite values,
booleans, duplicate IDs, timezone-free dates and future features are rejected.
A declared label definition and forecast horizon are required. Label
availability cannot precede completion of that horizon, including negative
examples. These timestamps and label semantics remain caller claims; validation
does not authenticate them or detect an incorrectly backdated feature.

Training includes only non-heldout-project observations predicted on or before
`training_cutoff` whose labels were available by that cutoff. Later labels are
excluded from training, rather than silently made available earlier. The
training cutoff must precede `evaluation_cutoff`.

Test observations are predicted after the training cutoff and on or before the
evaluation cutoff, with labels available by the latter cutoff. They are split
into chronological non-heldout projects and the explicitly declared heldout
projects. Earlier heldout-project rows are excluded, never trained on. Scaler
statistics and logistic parameters use training rows only. Test features,
labels and projects contribute nothing to fitting. Each excluded row retains
an explicit reason. Report sample IDs and original input digest make the
selection inspectable.

This slice does not add rolling-origin retraining, project-specific class
reweighting, feature selection, hyperparameter search or pooled random cross
validation. Its fixed standardized logistic baseline uses scikit-learn
`StandardScaler` and `LogisticRegression(solver='liblinear', C=1,
random_state=0, max_iter=1000)`. Backend and Python versions are retained.
Unconverged or failed fitting remains unavailable. Different environments may
produce different floating point results; exact candidate versions matter.

## Interpret the comparisons honestly

Probability outputs use a fixed classification threshold of 0.5 and report
precision, recall and F1, with zero-division convention 0. The report also
retains positive count, sample count and prevalence. AUROC and grouped-threshold
average precision are unavailable on single-class test labels. Score ties are
grouped for rank metrics. Precision at the top 20% uses expected prevalence
within a partially selected tie group, rather than outcome-based tie ordering.
The designated ranking feature assumes larger values imply higher risk; it is
chosen before looking at test labels and receives no probability loss.

Only actual probability outputs (constant zero, observed training base rate,
and logistic `predict_proba`) receive Brier loss and ten fixed-width reliability
bins. Each bin retains its count, mean forecast and observed positive rate;
empty bins retain null means. Raw ranking scores have null Brier/reliability.
Observed reliability on a tiny, selected dataset is descriptive and does not
justify a calibration or predictive-accuracy claim. Poor results are retained.
No post-test calibrator is fitted.

## Reproduced evidence and remaining empirical gap

The controlled authored twelve-row dataset exercises eight training rows and
two rows in each test partition. It is a software fixture, not an accuracy
benchmark. Its retained report demonstrates actual executed calculations and
repeatable source-bound report generation only.

A separate retained input covers 100 actual commits from the pinned fmt clone.
It uses historical changed-path counts and explicit null labels. Commit hashes,
HEAD, exact local Git commands and limitations are in
`fmt-history-provenance.json`. Git committer dates are controllable metadata;
merge/default diff semantics and selected-file counts are not independently
validated defect observations. No future labels were inferred from commit
messages, current findings, current source, SZZ candidates or a synthetic
heuristic. Consequently the real input correctly produces `not_evaluable`,
zero training labels and unavailable test partitions.

P7/M6-05 remains incomplete empirically. It requires independently validated,
cutoff-available real features and future labels, appropriate leakage and
project-generalization review, representative project/horizon selection,
imbalance comparisons and calibration evidence on final model/candidate bytes.
These controlled and unlabeled runs do not close that acceptance requirement.
