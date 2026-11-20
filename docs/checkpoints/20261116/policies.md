# Policy 1.2 Cloud continuation checkpoint

Branch baseline: `codex/cppulse-local-core-20261114` at
`6f8b662a89b367f8c6883298dc97950150d7ba4f`. All changes remain uncommitted.

## Completed slices

- Reproduced the saved runtime fixture failure (35 passed, one failed): its
  approval named `tests`, but the selected policy declared `unit-tests`.
  Corrected fixture target and exact context scope. The test now asserts the
  specific refusal of an incomplete failure; unrelated approval IDs still fail
  reference validation. No production identity checks were relaxed.
- Found and reproduced a substantive review gap: a same-source report could
  change its artifact SHA under the same local ID and retain a positive review.
  Added optional `reviewed_artifact_sha256` metadata. Profile 1.2 requires the
  exact current hashes for all required reviewed artifacts. Legacy records stay
  readable and yield unknown. Malformed or undeclared hash identities fail
  contracts. Stored positive reviews are revalidated against current identities.
- Review quorums are per file/job and count distinct declared IDs. Reject an
  impossible quorum larger than the selected review record count. Fixed the
  two-reviewer packaged example to select two records (independent review finding).
- Numeric incomplete failures now expose the observed values and threshold in
  the reason. Added complete two-job mean cases proving no cross-job pooling.
- Added explicit measured-library and organization-review policy examples and
  corrected stale supported-profile documentation. Thresholds are example
  choices, and no standards mappings or reviewer authentication are claimed.
- API and HTML transport tests persist actual evaluated review outcomes with
  checked authored source bytes and clearly synthetic review/receipt claims;
  passed and missing-hash unknown results preserve stored gates, raw values,
  evidence links and identity limitations.

## Reproducible checks

From `/workspace/cppulse`, source `work/cloud-resume/environment.sh`.

```sh
python -m pytest -q tests/test_policy_extensions_runtime.py tests/test_policy_extensions_contract.py tests/test_policy_profile12_presentation.py tests/test_policy_contracts.py tests/test_verification_policy_contract.py tests/test_assurance_contracts.py tests/test_policy_gate_properties.py tests/test_policy.py
```

**585 passed**, no skipped cases, one upstream Starlette/AnyIO deprecation warning,
116.91 seconds. Log: `policy-logs/full-policy-final.log`. The source-bound focused
profile 1.2 check passed 79 tests (`policy-logs/profile12-final.log`). These counts
are overlapping checks, not additive evidence totals.

The executed producer set includes the CMake/CTest fixture, GCC14.2 coverage
through gcovr8.8 and LCOV/Cobertura, and the ASan/UBSan/TSan fixture cases with their
explicit runtime/operational gaps. Earlier attempts without CMake on PATH or with
CMake4.4.5 failed the required finite adapter prerequisites; those logs are retained
as historical diagnostics, not final acceptance. CMake3.31.6 is required here.

Installed gcovr8.8 in the isolated tool venv `work/gcovr-8.8`; set
`CPPULSE_GCOVR=/workspace/cppulse/work/gcovr-8.8/bin/gcovr`.

Formatting and focused Ruff checks passed. Scope-review agent independently read
and reran the initial 77 focused tests and found the unreachable example quorum;
the follow-up fix adds the semantic regression above.

## Remaining acceptance

This is a P4 implementation slice, not completion of P4/M5 or a production release.
Automotive/medical pack acceptance remains blocked by unavailable authorized
pinned editions and qualified mapping review. Broad supported producer/platform
matrices, all consumer/distribution scenarios, installed-artifact review and
independent human product usefulness remain separate acceptance obligations.
Review metadata is self-declared and does not authenticate people or prove
independent review. Native numeric integration on the measured producer owner's
actual authored fixture is recorded separately in `policy-actual-evidence.json`: three
public assessments returned passed, failed and insufficient_evidence as expected;
pinned API responses preserved exact raw assessments and each PDF was readable
with ten pages and the correct gate/control text. It does not qualify real-project accuracy.
