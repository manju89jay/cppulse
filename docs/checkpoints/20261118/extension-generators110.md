# Extension generators and shared local checks — batch110

NFR-MNT-04 and M1-07 are verified against their unchanged original criteria. Independent review accepted both; no other row changed. Ledger:24 verified,103 open,58 active,2 blocked. All187 definitions/P0–P14 remain; strict exit3 is valid but incomplete, not full-program completion.

Proof: `work/extension110/canonical-proof.json`; independent review: `work/memory-review82/extension110/review.json`. Exact definitions and before/after are in `work/extension110/ledger-audit.json`.

## Qualification

- Candidate105 reused: wheel SHA256 `17c52c2dfcad73b3f137af69ed27db232c3b5e34c996c3aad7a89b8e9be0d193`; all237 installed payloads and frozen105 inputs match. No package rebuild, product edit or dependency install.
- Combined focused tooling/CI gate:64 passed and1 failed because CTest was absent from PATH. Original failure retained in `qualification.tar.gz`. Existing pinned CTest3.31.6 runs the unchanged zero-test control:1 passed; real CTest rejects the empty suite.
- Installed generator lifecycle: original3 passed, then current4 passed after new-test portability repair. Untouched native stub exits42, adapter raises NotImplementedError, policy remains unknown/readiness0. Implemented private native example produces2 exact call locations and0 clean lookalikes; adapter retains counts/retries/context/import identity and malformed/version refusal; policy evaluates passed/failed/missing separately. Both source epochs, native binaries and closed captures remain.
- Actual `python tools/dev.py verify --scope changed --section generated --output-dir review/extension110/generated`:0, delivery ledger and all6 generated outputs pass. Two new executable CI/facade/drift tests also pass.
- `.venv/bin/python scripts/verify_delivery.py --require-complete --output work/extension110/require-complete.json`: actual3, source stable,24 current verified rows and163 unfinished. Verifier source unchanged.

## Use

Create an existing destination, then invoke `python tools/dev.py new-rule forbid-gets --destination /path/to/drafts`, `new-adapter junit-example`, or `new-policy tests-example` with that destination. Successful generation reports `incomplete-draft`. Implement and review real positive/negative fixtures before explicit integration. Run `python scripts/check_generated.py` to detect drift without writing, or `--write` explicitly to regenerate; existing CI calls the same `tools/dev.py verify` facade.

The installed API is `cppulse.tooling.scaffold(kind, name, destination)`. The executable examples are in `tests/test_extension_lifecycle110.py`; declare both CPPULSE_EXTENSION_CLANG_INCLUDE and CPPULSE_EXTENSION_LIBCLANG for a non-system LLVM kit. Unavailable inputs fail closed.

These are synthetic extension-development fixtures. Structural schema validity does not qualify a detector, authenticate imported tests, approve an organization policy, or activate a scaffold. No new production rule/provider, live GitHub run, alternative platform/toolchain, portable native kit, editor or P14 qualification is claimed. Every edit/artifact remains uncommitted.
