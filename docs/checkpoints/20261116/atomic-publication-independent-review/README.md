# Atomic bounded-publication independent review: expected-red checkpoint

NFR-SCL-06, M2-01 and M2-05 remain open. The current bounded journey publishes
raw, normalized and health runs separately. `make_latest=False` would not fix
this: it still advances latest_attempt. Both existing pointers can advertise a
completed raw run lacking full scope and measured health before the operation
has finished.

`verification.json` retains an actual source-stable owned-child SIGKILL
counterexample. A genuine one-TU/CDB baseline completed with typed facts and
health. A second actual native/consumer journey paused after raw publication;
concurrent readers observed its incomplete raw run as completed. Killing and
reaping only the harness-owned child (-9) left both pointers on that raw run.
All three acceptance checks failed; the actual verifier script exited1. Selected
original immutable manifests and barrier facts are copied here; every artifact
and original receipt remains in the work stores named by the proof.

The portable durable regression is
`tests/test_bounded_atomic_publication_review.py`. Its barrier hooks the pure
normalizer entry and requires no published snapshot/hash from that material, so
it can test the proposed genuine staged read projection. The meaningful current
red is `durable-red-v2.log`: one failure, 27.56s, because both pointers changed
before final publication and remained changed after the owned child was killed.
`durable-crash-proof.json` records exact pins and observed material type. An
initial harness string/Path configuration error is retained separately under
work and is not claimed as a product defect.

`DESIGN.md` proposes one staged raw→typed→health transaction using an explicitly
named checked read projection, pure append/calculation operations and one final
publish. It forbids fabricated RunSnapshots, parent hashes or aggregate receipts.
It retains existing standalone immutable derivations and all source/native/SDK,
missing-scope and conservative-qualification guards. Source-check race recovery
and the limits of the existing two separately atomic pointer files are explicit.

This is an expected-red design/review checkpoint, not a completed feature or full
P5 acceptance. All files and changes remain uncommitted; no remote action occurred.
