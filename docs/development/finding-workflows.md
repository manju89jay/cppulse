# Checked finding baselines and SARIF

`cppulse.findings` compares finite retained native-analysis facts. `create_finding_baseline` produces a `FindingResult` containing a validated `finding_baseline` document and generic `RetainedBlob` artifacts. `compare_findings` produces the same wrapper for a `finding_comparison`. These functions read checked snapshots; they do not execute tools, read the current checkout, publish runs, or update latest pointers. The public workflow owns current-input verification and atomic publication. Request shapes are documented in [the finding contracts](../contracts/finding-workflows.md).

Baseline creation requires an explicit local run, selected canonical source files, job context IDs, rule IDs, baseline ID, reason and UTC creation time. Comparison requires an explicit local current run and pinned historical baseline artifact in either a local snapshot or an imported transfer root. It also receives the selected scope, UTC comparison time, `max_new`, and optional explicit rename and suppression inputs. Imported history remains unauthenticated and is never promoted to current execution evidence.

## What an anchor means

The new `native-line-anchor-1` identity hashes the exact retained diagnostic line and observation identity, excluding its line number. The source line must occur once in the retained file. Leading line insertions can therefore preserve an anchor. Editing the diagnostic line, repeating it, or changing a compatibility dimension can make the comparison unknown. This strategy does not infer C++ semantic equivalence. Existing `native-1` fingerprints remain unchanged and are exported separately.

Each occurrence retains its original observation ID. Equal fingerprints remain multisets: changing two equal occurrences to three records one new occurrence. A missing old occurrence is resolved only when the current file/job has complete consideration of all selected rules. Known new findings from credible partial analysis can fail the check while `incomplete` remains true. Missing, fallback or unverified facts cannot establish a clean result.

The producer reconstructs historical cells and anchors from the original retained manifest, source and observation bytes. A schema-valid baseline with a forged anchor is rejected. Original baseline and manifest bytes remain generic raw artifacts with exact hashes; they do not enter the current typed source namespace.

Compatibility requires exact observed parse context, detector configuration, rule registry and native executable hashes. The overall collection-plan configuration digest is provenance, not detector configuration. No absolute-path arguments are stripped. Native parse arguments omit the source operand, but normalized context identity includes the complete compilation database artifact. Consequently an ordinary rename that changes that database remains unknown. An explicit one-to-one rename map only permits a match when all actual compatibility dimensions still match. Duplicate basenames are never merged.

Dependency changes require a fresh full collection and normalization. This slice has no incremental dependency cache and makes no claim that reusing an old analysis after a header change is safe.

## Suppression is a separate finding-check decision

`finding_suppressions` requests select an exact baseline SHA, anchor version/fingerprint, canonical file, job, observed parse context, rule/version, maximum occurrence count, owner/rationale claims and UTC approval/expiry interval. Only the named `finding_regression` gate is supported. Requests are inactive outside their time or scope. Exact input bytes can be supplied with `suppression_bytes` and are retained unchanged; passing both records and bytes requires agreement.

The comparison always reports raw new/unchanged/resolved/unknown counts. Active requests reduce only `unsuppressed_new`; they never remove native observations, change policy scores, or waive missing analysis coverage. Overlapping requests cannot stack on the same scope. An incomplete check remains insufficient even when all known new findings are suppressed. Owner and approval fields are unauthenticated claims, not a signature or evidence of external review.

## SARIF export

`cppulse.sarif.build_sarif(snapshot, comparison=None)` returns a SARIF 2.1.0 document. Without a comparison it exports the selected typed native scope. An annotation comparison must match a typed `finding_comparison` artifact retained in that checked snapshot, with its closed raw historical roles. Publish the producer result first, then pass the snapshot and its checked comparison document. Standalone caller labels cannot supply annotations. The comparison selects its explicit scope and adds known `new` or `unchanged` baseline states. Unknown identities have no invented SARIF baseline state. A persisted derived run resolves the comparison's exact retained original-current manifest before labeling its observations.

Every occurrence is exported, including suppressed findings. Accepted finding-check suppressions are represented as external SARIF suppressions with justification and claim metadata; the result stays present. Both historical `cppulse/native-1` and eligible new anchor fingerprints are separate `partialFingerprints` keys.

Source locations use canonical relative, percent-encoded URIs. Native byte columns are converted from the exact retained UTF-8 source to Unicode code-point columns, declared by `columnKind`. An invalid or unavailable conversion leaves the line without an invented column and emits a warning. The original native byte column remains a result property.

Invocation success describes complete selected static-analysis consideration. Partial, missing or unverified native scope emits explicit warnings; zero results do not establish a clean analysis. Collection status, source verification claims, imported origin, unauthenticated provenance and the absence of a new source-freshness check remain visible. This export does not authenticate tools, certify code or upload to a code host.

The unchanged official OASIS SARIF 2.1.0 + errata01 schema, original retrieval provenance and supplied upstream terms are retained under `tests/reference/sarif/`. Tests validate emitted documents offline. These reference files are outside the Python package and core wheel; no runtime schema download is required.

## Local verification boundary

```bash
source review/environment.sh
env -u PYTHONPATH .venv/bin/python -m pytest -v \
  --cov=cppulse.findings --cov=cppulse.sarif \
  tests/test_findings.py tests/test_sarif.py
```

These source-byte and adversarial tests deliberately use labeled synthetic native records. Actual C++ collection, line insertion, renames, header/flag changes and installed CLI behavior have separate integration logs and pinned run artifacts. Passing unit tests alone is not an execution claim for those cases.
