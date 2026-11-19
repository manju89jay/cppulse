# Development and candidate review

Generated reference: edit `cppulse.tooling` or the packaged registry, then run
`python scripts/check_generated.py --write` and review the resulting diff.
`python scripts/check_generated.py` only checks; it exits nonzero for stale files.
The local tooling tests also compare the registry with native rule registrations,
categories and complexity defaults. Generated native helpers define registered
types, constructors, option capabilities and defaults. Detector implementations
remain explicit C++ source with reviewed positive and negative fixtures.

## Draft scaffolds

`cppulse.tooling.scaffold(kind, name, destination)` creates a new local directory
for a `rule`, `adapter` or `policy`. Names must be lowercase ASCII slugs. The
destination must already exist and contain no symlink path components. Existing
targets are refused. No code, registry, config or active policy is overwritten.
No command executes and no network call, Git operation or publication occurs.

Rules require a reviewed native ID, implementation, build/variant registration
and positive/negative tests. The rule stub throws until implemented; its draft
registry entry is not loaded. Adapters raise NotImplementedError until reviewed
normalization and failure behavior exist. Policy JSON is schema-valid draft data
with placeholder context/evidence IDs; it is not an approved or evaluated policy.

## Preview and stable candidates

These are review channels, not automatic release or update mechanisms. Current
checks remain experimental. A locally prepared preview candidate may contain an
experimental check only with its scope, fixtures and limitations disclosed. An
installed-artifact smoke run, contract/config compatibility checks, generated-file
checks, dependency inventory and reproducible checksums must accompany review.
This document does not claim those checks passed for a particular candidate.

Stable promotion requires independent review of positive and clean cases,
supported language/build contexts, parse failures and unsupported inputs;
measured false positives/negatives on disclosed representative inputs; versioned
behavior and default changes; compatibility/migration/rollback evidence; and
actual installed-artifact checks on every claimed platform. Agree acceptance
thresholds before evaluation and retain inconclusive results. MISRA-like signals
and experimental ranking do not become certification or calibrated probability
claims through promotion.

A new detector or scoring default must not silently change a pinned policy,
scorer or organization requirement. Promote through an explicit reviewed version
and migration; never rewrite immutable run evidence. Preparation is local and
publication requires a separate authorized action. No stable candidate is
declared by the existence of this registry or a generated scaffold.
