# P4 policy runtime frozen handoff

Frozen immediately for requested branch/Codex Cloud handoff. No P4 process remains running. No Git or external publication writes occurred.

Current implementation is unfinished and uncommitted. The new profile 1.2 pure numeric/review runtime and narrow dispatch/validation hooks exist. Prior profiles retain explicit capability rejection, and old score/gate/deviation code was preserved.

## Executed checks

- Prerequisite contracts and old policy gate: **532 passed in 19.34s**.
- New behavior before runtime implementation: **36 failed in 0.99s** (unsupported evaluator, captured red).
- First runtime attempt: **35 passed, 1 failed in 0.74s**. Failure is the new rejection/deviation test using inherited approval helper `control_id="tests"` while selected policy control is `unit-tests`. STOP arrived before correcting it.

Exact commands, hashes and logs are in `policy_runtime_resume.json`. Logs are retained in `review/production-20261114/p4-policy-resume/`.

## Remaining work

Fix that test-only approval ID, then finish focused behavior coverage and run full affected checks, formatting/lint and independent review. Actual typed native metric producer integration, multi-file/job no-pooling cases, API/rendered-gap proof and general/custom/domain examples remain unrun/unimplemented. Existing runtime tests use synthetic closed lineage; they do not prove actual producer execution.

Explicit `max`/`min` aggregation names were added while preserving inherited `maximum`/`minimum` aliases; aggregation is always required. Numeric evaluation never pools files or declared jobs. Review quorums count configured distinct declared IDs and make no authentication claim. Available linked metrics retain strict verified native/source contract requirements; malformed claims are errors, missing/unbound legacy facts remain unknown.

Automotive/medical mappings remain blocked pending authorized editions and qualified human review. No clause text, real reviewer decision, certification or P4 completion has been invented.

Resume environment: `cd /workspace/scratch/b3d4e6fff494/cppulse` then `source review/environment.sh`.
