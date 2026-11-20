# SDK proof wire budget and current installed qualification

The SDK91 repair corrects a genuine producer/reader size mismatch. It does not
close NFR-SCL-02, NFR-SCL-05, M2-05 or AC-06. All187 definitions,118 requirements,
60 tasks,nine obligations and P0–P14 remain unchanged. Every edit is uncommitted.

## Failure and repair

One actual native execution produced32 distinct translation units, files, content
hashes and receipts. Under unchanged64MiB production limits, the old producer
estimated275364 bytes but the store wrote279438 bytes. Replaying retention on the
same sealed results with a LOWER process-local proof cap279437 admitted all32;
the actual reader rejected it with IntegrityError and exit70. Original reports,
requests/results, source pins and traceback remain in
work/sdk-wire-budget91/worker/run. This is a wire-size regression, not a genuine
SDK OOM. The separate authored serialization boundary also failed1 and remains
retained with its exact old source in work/sdk-wire-budget91/frozen-red.

The producer now uses the existing store encoder to account for UTF8, indent2,
root-array row indentation and separators. It reserves only the wire width of
the existing maximum captured-byte counter, preventing later digit growth from
invalidating earlier admission. There is no new JSON format, schema, cap,
validation flag, authentication claim or eager-reader replacement. Production
proof/total limits stay64MiB and per-file limit8MiB. Raw integrity/EOF checks and
reader/cache implementation are unchanged. Thirty-one affected checks passed.

## Exact installed results

One new wheel was built and installed offline without changing dependencies,
versions, assets, native pack or VSIX. Wheel SHA256
0dec05d19cda30d8ad28732ea285495663728dd2821299a5dba195a19647192e.
There are236 payloads:235 match candidate80 exactly; only sdk_inputs.py changed.
Source freeze258+99 SHA256
6e2cdbc469c29a696b0e94efe67552935a51f16f5e236ce8f16bf1c3f3c49944.
SDK source SHA256
f883eefe1b139e3974db50cb2a19dc3f32a5e59ab72ea4c0bcd5759bb4c1658f.
The native archive remains96bee81401f068c45c4b0329f551e0f30b15c553140a49666085ccca5d01c19d;
VSIX remains0838719deebdd74789b17d4976b006ba2830be7dea573e28533c5169cffe36f5.
No new editor/platform qualification is inferred.

Installed93 replay uses those SAME32 sealed native results, with no new native
execution. Its full-cap proof keeps32 units and is byte-identical to the original:
279438 bytes,SHA2565bc00526921bb9d9a423c75f6131df9936746a00e922a8dc1f728450c2826044.
With the lowered279437 test cap it keeps31 units, writes271796 bytes, and the
actual SDK reader accepts it. Actual job sdk93-wire-installed exits0 with stable
inputs and no resource stop. Original red70 is not rewritten as success.

Installed public SDK/component journey also exits0. Supported CLI exits0 with
one used SDK unit,708 captured bytes, verified coherence and health100.
Unsupported CLI exits3 with unverified coherence and null health. Declined SDK
capture is an installed public pipeline API case using a process-local lowered
cap; it stays unverified/null with zero retained units/bytes. Five sha/size/growth/
missing/symlink integrity controls reject altered material. These relocate test
requests and do not attest extra native executions. Complete and excluded-member
component controls retain measured sums, realzero, separate historical coupling,
excluded denominators and unknown duplication. JSON/HTML/schema outputs are
retained. Network is kernel-denied and profiles have no account.

## Historical evidence and independent acceptance

The actual reuse93 audit checks25634 historical pins. The ONLY relocated old
current-source path is sdk_inputs.py SHA6ffed57e..., preserved exactly under
work/installed-memory-szz80/build-input/python/cppulse/sdk_inputs.py. Earlier
execution logs keep their original artifacts and scope. The unchanged235
payloads and identical dependency METADATA justify matching prior controls;
new source qualification comes from the actual affected installed journeys.

Read-only review work/memory-review82/installed93/review.json accepts refresh of
all20 previously accepted FULL original criteria, with no new closure. Review
SHA25623517299a97af6631ff530aa1d0f267f6e0095a68d9cd13c9dbb351316f9177a.
Its30808 artifact/map/contract assertions are not product tests or re-executions
of historical matrices. The final canonical proof retains the FULL resolved
historical map, current source/installed payloads and fresh result pins.

Canonical proof: work/installed-sdk-wire93/current-source-proof.json.
Ledger before/after: work/installed-sdk-wire93/ledger-refresh-audit.json.
Actual strict command/result: work/installed-sdk-wire93/require-complete-command.json.
The strict verifier and original definitions are unchanged; global exit3 remains
incomplete and cannot close the other167 items by implication.

## Usable installed invocation

The retained minimal interpreter needs its installed package/dependency paths
and preinstalled native pack. For example, with fresh output/work directories:

```sh
env PYTHONPATH=/workspace/cppulse/work/installed-sdk-wire93/installed:/workspace/cppulse/work/closure-fr3/dependencies \
  CPPULSE_NATIVE_PREFIX=/workspace/cppulse/work/installed-runtime11/cppulse-native-0.2.0.dev2-linux-x86_64 \
  LD_LIBRARY_PATH=/workspace/cppulse/work/native-deps/usr/lib/x86_64-linux-gnu \
  /workspace/cppulse/work/installed-sdk-wire93/installed/bin/cppulse analyze \
  --repo /absolute/repository --output /fresh/store --execution bounded \
  --jobs 1 --no-history --work-directory /fresh/native-work --format json
```

The example is a usage template, not an additional executed result. All actual
argv, input hashes, exits and closed outputs are in the qualification packets.

SDK-v2 embedded report/resource parsing and typed material still eagerly
materialize within their existing limits. No whole SDK memory, full protobuf
pipeline, scale, producer authentication, M2/M6/M8/M9, platform, human usefulness
or P14 completion is claimed. The original218MB predictor MemoryError and its
qualified bounded component repair remain separate evidence.
