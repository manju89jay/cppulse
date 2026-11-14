# One pinned local web view

`cppulse serve --input /absolute/path/to/store` serves the bundled React dashboard
and the optional FastAPI API on the same local port. The default host remains
`127.0.0.1`. Serving the installed wheel needs the `web` extra, and PDF rendering
needs the separate `pdf` extra and WeasyPrint system libraries. Serving never
runs npm, Node, CMake, a compiler, a project test, or a source checkout command.

## Snapshot selection and transport

`GET /api/v1/view` selects the current published attempt once, including partial
and cancelled attempts. It returns the validated `snapshot_view` contract from
`cppulse.presentation.build_snapshot_view`. A named historical selection supplies
**both** `run_id` and `manifest_sha256`. A partial/malformed pair is rejected; a
hash disagreement never selects a different run. An optional
`assessment_artifact_id` selects the exact stored assessment. It must belong to
the selected run; a retained ancestor assessment is not current assurance.

The dashboard makes one view request per load/refresh. Run identity, stored gate,
controls, stages, facts, artifact inventory and optional four legacy documents
come from that one response. Navigation does not resolve another current pointer.
Refreshing clears the former response before requesting the next one; failures
and delayed old responses cannot leave an older result presented as current.

Raw downloads use:

```text
/api/v1/runs/{run_id}/artifacts/{artifact_id}?manifest_sha256={sha256}
```

Only an exact inventoried artifact ID is accepted. Reads validate the original
manifest and file bytes and do not initialize writer directories. Attachment
responses include the run/hash headers and `nosniff`. The API does not accept a
filesystem path for a raw download.

`/api/v1/report.pdf` and `/api/v1/report.html` render the same selected stored
view. Both accept the same optional pin pair and assessment selector. Dashboard
report buttons always pass the displayed run ID, manifest hash and selected
assessment ID. API PDFs receive the request base URL so their original-artifact
links retain the exact pin. Missing PDF support returns an actionable 503; it
never substitutes a flat or older PDF.

`CPPULSE_API_KEY` and `CORS_ORIGINS` retain their existing behavior. The static UI
shell is public; data, raw artifacts and report endpoints require the configured
Bearer key. The optional dashboard key field stays in component memory and is
sent in the Authorization header, not a URL or persistent browser storage.

## Stored decisions and observations

The browser displays assessment gate/control statuses and numeric display strings
verbatim. It calculates no policy gate, readiness score, coverage percentage or
consumer acceptance decision. The stored source-verification label is historical;
serving does not check current source freshness or upgrade an unverified run.

The Findings tab shows every typed native observation in its recorded job and
observation context, joining its analysis inventory for the job label. Rows are
not deduplicated across jobs. External compiler observations keep their producer
namespace and namespaced rule IDs. Available legacy findings remain a separately
labeled section.

Evidence cards show consumer comparison case compatibility/reason/mismatches
separately from local test status and missing checks, including unverified import
authentication. Coverage cards retain each file's count, kind and method.
Sanitizer cards show the stored sanitizer, outcome, requested files and diagnostics.
A display-only JSON token reader preserves original number lexemes as strings,
including values beyond JavaScript's exact integer range. Raw retained JSON and
pinned artifact downloads remain available for detailed review.

## Explicit compatibility mode

If the configured directory has no store metadata, `/view` returns an explicit
`legacy-flat` variant labeled unverified, without invented run or artifact pins.
Its four independent files can change during reading; it cannot establish a
common source/execution context. Once store metadata exists, corrupt pointers,
missing runs or incomplete attempts never cause fallback to those files.
The older legacy API endpoints remain available for existing clients; the new
dashboard does not use their multiple-request composition.

## Bundling and verification

Development builds use the checked npm lock and then explicitly prepare assets:

```sh
(cd dashboard && npm ci)
python scripts/build_dashboard_assets.py
python scripts/build_dashboard_assets.py --check
```

The helper retains `index.html`, hashed JavaScript/CSS and a source/payload SHA-256
inventory under `python/cppulse/data/dashboard/`. `--check` needs no Node and
rejects stale source/lock bytes or changed/missing bundle files. The candidate
must be rebuilt after dashboard source changes. Built assets are package data;
the installed API has no fallback to a checkout's `dashboard/dist` directory.

The actual browser verifier accepts an installed Python interpreter, starts the
server in an unrelated temporary directory, removes Node and other command tools
from its PATH, and checks pinned views, observation rows, semantic evidence cards,
raw-byte downloads and nonempty readable PDF downloads:

```sh
python scripts/verify_snapshot_web.py \
  --python /absolute/path/to/installed-env/bin/python \
  --verification output/evidence-reports/verification.json \
  --consumer-summary output/consumer-demo/latest-demo.json \
  --evidence review/autonomous/artifacts/s7-installed-web
```

`--source-package /absolute/path/to/python` is an explicit development-only
option. Results record source versus installed mode; a source run is not an
installed-wheel claim. Screenshots, checked responses, HTTP requests, downloaded
bytes and server logs remain in the selected evidence directory. This verifies
the selected Linux/browser cases and local artifact integrity, not production
hosting, authentication of upstream producers or other platforms.
