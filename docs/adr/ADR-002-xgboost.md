# ADR-002: Use XGBoost for Bug Prediction

**Date:** 2026-03-04
**Status:** Accepted
**Deciders:** Manjunath Jayaramaiah

---

## Context
The predictor component needs to classify files as bug-prone based on 10 features
extracted from static analysis and git history. The model trains on each target
repository's own history — not a pre-trained general model.

Key constraints: must train in seconds on a laptop, must be interpretable
(explain WHY a file is high-risk), must work without a GPU.

## Decision
Use **XGBoost** gradient-boosted decision trees.

## Consequences

### Positive
- Interpretability: feature importance (SHAP values) shows exactly which signals
  drive predictions — engineering managers can understand and trust the output
- Training speed: trains in seconds on repo-sized datasets (thousands of files)
- Accuracy: 85–89% F1 on published CI/CD bug prediction benchmarks (TravisTorrent)
- No GPU required: runs on any developer laptop or CI server
- Handles mixed feature types well (float rates + integer counts)
- Mature Python library with sklearn-compatible API

### Negative
- Requires enough commit history to label training data (sparse repos <50 commits
  will have insufficient training data)
- Not a real-time model — batch training per repo adds startup time

### Neutral
- Model is saved as model.pkl and loaded for inference — standard pattern

## Alternatives Considered

| Alternative | Why Rejected |
|-------------|--------------|
| Neural network (PyTorch) | Not interpretable — cannot explain predictions. Requires more data. Overkill for tabular features. |
| Random Forest | XGBoost consistently outperforms Random Forest on tabular data in SE prediction tasks. |
| Logistic Regression | Too simple — cannot capture non-linear interactions between features (e.g. high churn AND single contributor). |
| Pre-trained model | A general model cannot capture repo-specific patterns. SZZ labeling on the target repo is the key differentiator. |
