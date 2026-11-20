# Namespaced Python distribution and migration entry points

NFR-MNT-02 retains its original criterion: one namespaced Python distribution,
shared contracts/configuration helpers and existing component entry points during
migration. All187definitions and P0–P14 remain unchanged. This checkpoint records
installed checks and accepted independent review:1,473 checks/842 pins, zero
issues. Review SHA256
d1b54ac1772c9d0d6df877e1c3b80f996b26dc07e29b5055c3b67044c887486d.

Candidate80 is unchanged: wheel SHA256
4dd953d82771515eabdc68f444e2eb7580ab9502ef4b4c83a97322f5011460a2,
236 payloads,257 Python/test and99 native/editor source pins. No product source,
packaging version, dependency or environment change was needed. No commit/push.

## Actual component behavior

Existing entry points are component-local `python -m src.main` for git-miner and
predictor, `python -m src.pdf_generator` for report-engine, and Uvicorn's
`src.api:app`. No previous named git-miner/predictor/report-engine console alias
was inferred or invented. Wrappers delegate to the canonical cppulse modules.

The original installed journey completed17 real producer/report/PDF operations:
Git and predictor old/new module parity, original checkout compatibility/defaults,
JSON/HTML equality, three real default PDFs with seven expected sections. Exact
copied wrappers live in isolated component directories without sibling Python
source. They resolve installed candidate80. Original checkout compatibility is
separately labelled as source execution. Git/predictor producer comparisons
retain different real generation timestamps; this is migration parity, not a
claim that separately executed analyses produce identical timestamps.

Continuation3 completed two Uvicorn-target imports and meaningful in-process
HTTP summary responses, shared helper/contract/config checks, three module
identity checks and two malformed-input refusals (expected1). The installed API
probe resolves the copied legacy wrapper and installed cppulse API, using the
actual Uvicorn0.27.1 default app-dir rule. The checkout API is labelled separately.
API checks use the existing web dependencies with internet socket/DNS denial and
in-process transport; they do not claim a live TCP server or container platform.
Other journeys use kernel network denial. No live provider or account is used.

## Preserved failures and exact evidence

work/namespace89/worker/run/completion.json remains actual1: its absolute API QA
script omitted Uvicorn's real default app-dir insertion. The successful17 prior
operations and149 sealed artifacts were not rerun or rewritten. The first
continuation also remains actual1: QA readback expected report keys in a file
that recorded only four Git/predictor cases. Neither failure was a product fix.

work/namespace89/worker/run3/completion.json records actual0 and rechecks both
previous failed seals. Qualification SHA256
82b3abac5a97b73741e2885396e4ebb8c7a553d56049e0a40d9c8a837f45e966.
Exact composed commands/results and scope are in run3/qualification.json.
Resource records are work/heavyweight-jobs/namespace89-installed,
namespace89-continuation and namespace89-continuation3. Each had stable pinned
inputs and no resource stop. One heavyweight job and4GiBreserve applied.

Usable existing invocations, from their respective component directory:

```sh
python -m src.main --repo /absolute/repo --output /fresh/git-output
python -m src.main --input /absolute/four-document-input --output /fresh/prediction
python -m src.pdf_generator --data /absolute/input --format json --output /fresh/report.json
python -m src.pdf_generator --data /absolute/input --output /fresh/report.pdf
uvicorn src.api:app --host 127.0.0.1 --port 8000
```

The first two commands belong to git-miner and predictor respectively. Canonical
modules cppulse.git_miner.main, cppulse.predictor.main and
cppulse.report_engine.pdf_generator are available from the single installed
wheel. PDF/web capability requires its existing optional dependencies. Avoid a
global ambiguous src package; retain component wrappers during migration.

Independent review: work/memory-review82/namespace89/review.json.
Canonical proof: work/namespace89/canonical-proof.json after accepted review.
Ledger before/after: work/namespace89/ledger-audit.json after accepted integration.
This requirement does not close M1-03, M9, other Python/platform versions,
all dependency boundaries, network service operation, scale or P14. The unchanged
strict final verifier remains the full-program completion gate.
