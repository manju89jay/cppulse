# Finding regression contracts

These additive v2 contracts describe finding workflows. They do not modify historical `baseline` documents, `native-1` observations, policy evaluator 1.0/1.1, or raw finding totals. Producer and installed-workflow acceptance are separate from this contract gate.

| Kind | Purpose |
| --- | --- |
| `finding_baseline_request` | Explicit selected files/jobs/rules, baseline ID and reason |
| `finding_check_request` | The same finite selectors plus a pinned baseline reference, maximum new count and optional rename/suppression input |
| `finding_baseline` | Original source/run/manifest and observation roles, analysis cells and anchored occurrence multisets |
| `finding_suppressions` | Exact, bounded, expiring finding-regression suppression requests |
| `finding_comparison` | Raw multiset conservation, unknowns, suppression applications and the separate finding check gate |

References select either a local store/run/manifest SHA/artifact or a standalone transfer bundle/root/manifest SHA/artifact. There is no implicit latest selection or network reference. Suppression inputs may instead name an explicit local file. Request dates are supplied by the caller to the pure producer as recorded UTC operation times.

## Anchor identity and compatibility

The explicit new strategy is `native-line-anchor-1`. Its fingerprint hashes the canonical file, producer and rule identities/versions, severity, message, optional integral column and SHA-256 of the exact retained diagnostic-line bytes. The line number is excluded. JSON integral coordinate spellings such as `4` and `4.0` have the same coordinate identity. Job and observed parse-context identities remain separate matching/compatibility fields; equal patterns across jobs retain separate counts.

This is a narrow byte-line anchor, not C++ token, symbol or semantic equivalence. A line shift is eligible only when the anchor uniquely identifies the retained source line. Repeated source lines remain ambiguous. Unavailable anchors carry null hashes; no stable fingerprint is invented. Native historical fingerprints remain unchanged and cannot silently acquire the new meaning.

The scope digest hashes selected canonical paths, job IDs and rule IDs, excluding source contents. Source hashes necessarily may change between compared runs. Exact relevant detector configuration, registry, native tool and observed parse-context identities govern compatibility. The global collection-plan config digest is retained as provenance; it is not substituted for detector configuration. Unsupported relocation/context changes remain unknown. Explicit one-to-one rename mappings can alter matching paths only; they do not rewrite the original baseline or strip context arguments.

Each baseline records exactly one analysis cell per selected file/job. A complete cell requires bound source, context, inventory, detector configuration, registry, tool and selected-rule consideration. Creating a baseline does not imply those facts are complete. Original manifest bytes and selected observation roles remain pinned; foreign baseline material is retained as generic raw artifacts rather than merged into the current source namespace.

## Conservation and gates

Comparisons retain occurrence IDs and multiplicity. They enforce:

```
current = new + unchanged + unknown_current
baseline = resolved + unchanged + unknown_baseline
unsuppressed_new = new - suppressed_new
```

An absent old observation is resolved only with complete current consideration of its selected rule/file/job. Current fallback or unverified observations remain unknown rather than establishing known new/unchanged named-job states. A known new observation from a matched partial AST may fail the check while incompleteness remains visible.

The finding gate fails when known unsuppressed new occurrences exceed `max_new`. Otherwise incomplete/incomparable or empty-scope comparisons produce insufficient evidence. Only a comparable complete result within the explicit threshold passes. A suppression cannot waive unknown coverage or make an incomplete comparison pass.

## Suppression scope

Suppression requests name only `gate = finding_regression`, exact baseline SHA, fingerprint/version, canonical file, job and observed parse-context digest, rule/version, maximum count, rationale, owner and approval/expiry times. Overlapping requests for the same exact scope cannot stack; disjoint renewal windows remain descriptive. Caller-supplied active flags are not authorization.

Comparison output copies request claims and records computed active state, applied count and inactive reason. Active suppression requires current matching scope and time, and its count cannot exceed the known new matched occurrences or the approved maximum. Raw new counts and native/policy findings remain unchanged. Owner/rationale strings and checksums do not authenticate a reviewer or producer.

Contract tests use labeled synthetic facts, including a closed typed native-analysis lineage. They validate structure, identity references and arithmetic without executing tools or reading source bytes. Actual anchor production, source-line uniqueness, rename behavior, SARIF export and end-to-end acceptance require their separate producer and integration checks.
