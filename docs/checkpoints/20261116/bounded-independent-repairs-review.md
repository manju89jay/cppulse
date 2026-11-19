# Independent bounded orchestration review — in progress

Scope: `analysis_execution.py`, work-unit extensions, bounded pipeline publication,
and narrow importer history sidecar retention. Production owner: `/root/scale`.
Reviewer changes are limited to owned `tests/test_bounded_input_coherence.py` and
this checkpoint/evidence; no shared config/CLI implementation edits, commits or
pushes. This is not P5/R5 or full-plan acceptance.

Requirement links: PR-03 provenance, NFR-SCL-06 checkpoint/mixed-run prevention,
AC-06 valid coherent partial facts, M0-04 producer partial retention, M2-02
independent-unit resource/failure behavior.

Retained native binaries:

- Historical baseline: `work/repairs-bounded-review/native/cppulse-analyzer`,
  SHA `f5bb07d809bbd741c1c04d1aa00b0b4cea012aaeb78343719c91e6795ce8a8c3`.
- Actual counterexamples: `work/repairs-bounded-review/native-final/cppulse-analyzer`,
  SHA `ac80052f481472529b31067414ca53c29ae7cec114bd6f2e5660183667bdf61c`.

The historical baseline ran 90 actual tests with no skips in 389.26 seconds:
analysis execution contracts/runtime, bounded public pipeline and work-unit
API/runtime/store. `work/repairs-bounded-review/baseline-tests.log` retains output.
It is not a current source-bound acceptance gate: production implementation and
native candidates are changing concurrently. No mutable binary was overwritten.

Confirmed issues and current status:

1. A selected header macro was changed only while the actual primary TU parsed,
   then restored before postflight. Original code reported completed/verified with
   the same global source digest as clean execution but complexity 2 instead of
   clean 1. Raw runs/proof are under `work/repairs-bounded-review/transient-header`.
   A corrected meaningful pytest red is `coherence-red2.log`; initial
   `coherence-red.log` is explicitly an authored fixture-scope bug, not that proof.
   Owner added separate filesystem observations and conservative unknown-input
   handling; actual TU buffer identities are being added separately. The owned
   transient-header regression subsequently passed on retained ac80052 native.
2. Actual downstream failure after writing malformed partial risk JSON prevented
   any raw-facts snapshot and deleted generated diagnostics. Proof/log are under
   `corrupt-consumer` and `corrupt-consumer-repro.log`. Owner now retains failed
   consumer documents untyped and preserves unpublished diagnostics. Owned
   malformed-consumer regression passed and checks exact malformed bytes plus
   original actual receipt values in a partial run.
3. Deliberate post-run valid-JSON result mutation was copied as original while its
   embedded receipt differed from the separately retained original receipt, and
   result bytes contradicted the frozen summary hash. Actual original bytes and
   proof are under `result-mutation`. Owner now reconstructs exact canonical
   frozen bytes only when they match old pins, quarantines changed bytes, records
   failed publication integrity and prevents public success. The owned public
   corruption regression passed after actual normal report generation.
4. A checkpoint receipt ID could be replaced and returned by completed warm
   resume without execution. Proof is under `receipt-resume`; meaningful red is
   `receipt-id-red.log`. Owner added deterministic receipt/namespace checks and
   separate work checkpoint byte pins. Whole reason-pair/timestamp mutations with
   an existing previous summary now pass owned negative tests (both rejected or
   retried/recovered without relabeling modified metadata as actual).
5. Still open at this checkpoint: simulate missing coordinator summary after real
   unit completion, then alter result/receipt reason together. Worker rejects the
   changed checkpoint, but final coordinator collection reloads and registers
   that rejected receipt as actual partial facts. Proof/original summary/result:
   `work/repairs-bounded-review/interrupted-summary`. Owned pytest case
   `test_resume_checkpoint_metadata_must_match_original_frozen_bytes[reason-True]`
   is a meaningful failing test in `interruption-red.log` (one failed, two passed).
   Owner has the reproduction and is fixing final collection validation.

Additional actual missing-external-include recovery correctly reruns native
instead of reusing a stale partial receipt; proof is under `partial-resume`.
Its unsupported dependency coherence stays explicit. Importer history sidecars
remain opaque archived bytes in an unverified import, without retroactive native
execution/source claims. Source observations now have a private schema and
summary digest. Manual interrupt semantics are being repaired to publish canceled
producer facts and stop before consumers; no independent final interrupt gate
has yet been completed by this reviewer.

All owned actual fixtures, original copies, logs and scripts remain in
`work/repairs-bounded-review`. Current owned regression file has seven collected
cases. Final current-source/binary gates, independent publication/resume checks
and compact evidence manifest remain required after owner fixes settle. Do not
infer a completion claim from any historical passing subset here.

Later update (before final source freeze): owner fixed issue 5 by rechecking every
collected result against its independent work-checkpoint pin and deterministic
receipt/namespace; rejected bytes remain diagnostics and are excluded from actual
execution results. The seven owned coherence cases subsequently passed on pinned
include-buffer native candidate
`9004df27f73a73901e3c231834628c24009ffded1730e598754acd6e7c7a6373`
in 14.36 seconds (`coherence-v2.log`). An eighth actual case now checks a known
external header changing after successful report generation; native buffer hash
availability is asserted, publication becomes partial/unverified and original
passed receipt remains retained (`external-current.log`, 1 passed in 6.86 seconds).
The current owned file has eight cases, superseding the seven-case count above.

Owner added manual interrupt propagation (publish canceled facts, then stop before
consumers), private source-observation schema/hash pins, and actual published-run
catalog integration. This reviewer is waiting for the coherent source freeze
before a broad current-source/native-bound final gate. Catalog coverage of failed
and canceled publications and typed legacy aggregate memory bounds remain named
qualification points; neither is silently established by the passing subsets.

Further actual P5/R5 counterexample (currently open): `__has_include` can query an
external file without producing an inclusion edge. With identical primary source,
args and resource identities, create that external file between two runs. Current
warm resume reuses complexity 1 and reports completed/resumed1, while an actual
fresh parse measures complexity 2. Evidence is
`work/repairs-bounded-review/negative-include-resume/proof.json` with all three
actual runs. New ninth owned case
`test_negative_include_query_forces_fresh_resume_equal_to_clean_native` retains a
meaningful red (`negative-query-red.log`, 2.09 seconds). It requires fresh native
execution and clean/resumed semantic equality, without demanding a completeness
claim for an unsupported query closure. Empty resolved include edges cannot by
themselves establish safe resume eligibility. Owner has the case and is fixing
conservative eligibility before final source freeze.

Final independent slice gate (2026-11-16T17:13:07Z): **140 tests passed, no skips,
138.43 seconds; exit 0; source_stable:true.** The literal command and 35 selected
source/schema/test hashes are retained by
`review/cloud-20261116-bounded-independent-repairs-current/check.json`.
Supplemental CLI/history/tooling hashes and the immutable selected native9004 hash
were independently unchanged. `bounded-independent-repairs-review.json` records
source/artifact pins, repaired actual findings and remaining acceptance scope.
Compact historical reds, exact original result/summary bytes, actual native
reports and final logs are in `bounded-independent-repairs-evidence/MANIFEST.json`.

All previously reproduced correctness/provenance issues in this finite slice are
resolved. Both ordinary and standard line-spliced negative-query variants now
run fresh and agree with independent clean native facts. **This safe fallback is
not public qualified cache/warm-resume implementation**: public units currently
have no qualified dependency/query manifests and therefore all execute fresh.
The generic historical checkpoint retrieval gate remains separate from proof of
current extraction reuse. End-to-end parent-memory bounds, broad scale/platform
coverage and full P5/R5/P14 acceptance remain open; typed aggregate compatibility
consumers still load complete JSON documents. No whole-product completion claim
is made. Every change remains uncommitted; no push/remote action occurred.
