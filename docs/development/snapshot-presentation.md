# Checked snapshot reports

The evidence report is one view of one retained run. JSON, HTML, PDF, the API and
the dashboard use the same source identity and stored assessment. Rendering does
not run project commands, inspect live source files, or evaluate a policy again.

Use explicit evidence mode; the existing default legacy report contract remains
available:

```sh
cppulse report --input /path/to/run-store --evidence --format html
cppulse report --input /path/to/run-store --evidence --format json
```

The default output is `evidence-report.html` or `evidence-report.json`. This does
not overwrite the old `report.json` compatibility export. Historical selection
uses both pins together:

```sh
cppulse report --input /path/to/run-store --evidence \
  --run-id RUN_ID --manifest-sha256 MANIFEST_SHA256 --format pdf
```

A named report defaults to `derived/RUN_ID/evidence-report.pdf`. A concrete
`runs/RUN_ID` directory is also supported. Output inside immutable runs, staging,
or store metadata is rejected. Partial and cancelled attempts remain visible in
evidence mode. No older successful run or flat-file export fills their gaps.
PDF requires the optional `cppulse[pdf]` dependencies and system libraries;
JSON and styled HTML need only the core package.

## What the view means

- **Collection status** describes retained execution/completeness. The policy
  gate is a separate stored assessment value.
- **Input verification** describes the finite inventory check recorded at
  publication. Historical rendering performs no fresh source check.
- **Policy gate, scores, controls and deviations** are copied from the selected
  typed assessment artifact. Missing assessment means `Not assessed`; missing
  scores stay unavailable. An archived generic history artifact cannot become
  the current assessment merely by selecting its filename.
- **Exact numeric display strings** retain original JSON number tokens, including
  large weight masses beyond browser number precision. No renderer recalculates
  a score, threshold, percentage, deviation state or gate.
- **Facts** retain original type, byte identity, producer metadata and raw JSON.
  Human labels show receipt steps or selected paths with short IDs; full IDs,
  SHA-256 pins and original bytes remain in JSON and raw-download references.

The report shows per-file analysis status, selected jobs and contexts; typed
observations preserve every recorded occurrence across jobs. External diagnostic
namespaces remain separate. Coverage displays stored `covered / total`, kind and
method; it does not infer a percentage or MC/DC. Sanitizer outcomes and original
diagnostics remain distinct from ordinary test exit status. Consumer comparison
shows imported configuration correspondence, local test status, mismatches and
missing checks separately, including its unverified authentication label.

All seven prototype report sections remain available. Their four optional legacy
documents are validated and hash-bound inside explicit slots. Missing documents
and valid empty outputs have different labels. Legacy health and ranking remain
experimental descriptive data; they do not supply the evidence-policy gate.

## Python interface

```python
from cppulse.presentation import (
    build_snapshot_view,
    render_snapshot_json,
    render_snapshot_html,
    render_snapshot_pdf,
)

view = build_snapshot_view(snapshot, assessment_artifact_id=None)
json_text = render_snapshot_json(view)
html_text = render_snapshot_html(view)
pdf_bytes = render_snapshot_pdf(view)  # optional backend
```

Selection uses artifact IDs, never path guessing. Multiple current typed
assessments or multiple legacy documents of one kind require explicit selectors.
`legacy_artifact_ids=None` automatically selects unique typed legacy slots;
an explicit mapping selects only its named slots, and `{}` disables all four.
The pure builder verifies the snapshot and reads its exact original manifest
bytes through `RunSnapshot.read_manifest_bytes()`.

`render_snapshot_pdf(view, base_url=...)` can resolve raw-download annotations
against an explicitly supplied API origin. API-generated PDFs use the actual
request origin. Offline PDFs contain original identities without inventing a
server address. HTML/PDF have no external document resources; artifact links are
optional local API downloads pinned to the same run and manifest SHA.

## Fresh verification evidence

`output/evidence-reports/verification.json` records the exact retained S5 source
snapshots and fresh JSON/HTML/PDF output hashes for four actual execution cases:

| Case | Published collection state | Stored policy gate |
| --- | --- | --- |
| Clean selected input | completed | passed |
| Intentional native findings | completed | failed |
| Partial parse / failed build | partial | failed |
| Missing test report | partial | insufficient_evidence |

These are fresh renderings of original real execution snapshots; no new producer
execution is claimed by the rendering probe. The finding report includes the
actual rule IDs, source locations and native job. Original source/configuration
identities and producer artifacts remain unchanged.

Tests cover exact-byte manifest reads, current/historical pins, ambiguity,
partial/cancelled/unassessed data, numeric precision, HTML escaping, optional PDF
failure, real readable PDFs and explicit annotation origins. A zipped installed
package builds the view and renders styled HTML/JSON outside the checkout while
PDF, API, ML, plotting and heavy mining imports are blocked. Final PDF layout
review and the complete installed API/dashboard journey are recorded separately
in the stage review logs.
