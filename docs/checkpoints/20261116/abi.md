# P12 / M9-03 local ABI evidence slice

Status: finite adapter implementation and reviewed installed-module proof passed;
**FR-EVD-10, M9-03 and P12 remain open as whole requirements.** This is not full
API/ABI/fuzz/dependency delivery or the AC-01..16 / P14 endpoint. No commit,
push, publication, deployment, external provider or analyzed-binary execution
was performed.

Implementation is `python/cppulse/abi.py`, packaged private request/report schemas
under `abi_private`, `tests/test_abi.py` and
[the supported-scope documentation](../../development/abi.md). Source bindings
remain `unverified`; hashes and producer claims do not authenticate source.

The concrete supported scope is Linux ELF shared-object embedded full-CU DWARF,
libabigail `abidiff` 2.6.0 and GNU Debian `readelf` 2.44. Tools, binaries and
explicit local libraries are copied and hash-bound. Input bytes, comparison wall
time and aggregate captured logs have finite enforced limits. CPU/address-space
limits and security sandboxing are not claimed. Preflight versions have separate
finite bounds. Current output must be new; preparation/stale-input failure
cannot publish a positive report.

## Current exact checks

- `.venv/bin/python -m pytest -q tests/test_abi.py --basetemp=work/abi-test-final-epoch3 --cov=cppulse.abi --cov-branch --cov-report=term-missing`: exit **0**, **32 passed**, no skips, **82%** statement/branch aggregate coverage. Selected module/test/schema bytes were unchanged before/after. [Receipt](abi-evidence/final-check.json), [log](abi-evidence/final-tests.log).
- Independent reviewer ran the same 32 tests with its own basetemp: exit **0**, source stable. [Receipt](abi-evidence/independent-check.json), [review](abi-independent-repairs-review.json).
- Fresh virtual environment installed a built wheel and all declared core dependencies. From an arbitrary directory, `python -I -m cppulse.abi --request ABSOLUTE --output NEW` used only the installed module/schemas. Identity / indirect layout change / additive export / removed export yielded exact producer codes **0 / 4 / 4 / 12**; adapter exit **0** means complete observations, including differences. Stripped input gave adapter **3** with unsupported receipt; overwriting an existing output gave **2**, preserving original bytes. [Installed commands, hashes and exits](abi-evidence/installed-manifest.json), [actual report](abi-evidence/installed-reported.json).

Current installed wheel SHA256:
`f432e47e9c4be03c4d168c331954087df2d9a58ea7b2b838d62858f7ea82a769`.
Installed module SHA256:
`c7b350ea4e600502c52dd3741a0cd9591ab95c8a7e5635851bfa6eb3b24edd87`.
Installed schema bytes equal current source. The wheel and complete fixture/tool
artifacts remain under `work/abi-installed-final/` and `work/abi-tooling/`.

## Meaningful failures retained and repaired

Initial contract-first collection failed because the module did not exist.
The first real runtime matrix then exposed stripped build-ID fast paths and the
incorrect assumption that an indirect struct layout break must set exit12.
The adapter retains producer codes: exit4 is “changes reported”, never “safe”.

Independent review reproduced actual orphaned subprocesses after SIGINT,
zeroed DWARF sections returning abidiff0, a null root DIE hidden by an unused
abbreviation, and a mixed valid-CU/null-CU object appearing clean. Corrected
execution reaps the process group, and readelf validation requires each actual
info CU to contain its own level-zero compile-unit root. Both corrupt cases now
remain unsupported while a real valid two-CU object still produces a complete
observation. Warning/empty retained logs cannot be relabeled “validated”.
Control/NUL/non-UTF8 requests are concise failures; mutable caller requests are
frozen. Tests retain stale-input, during-run mutation, overwrite, duplicate-ID,
input-size, timeout, log-limit, descendant-pipe and report-tampering failures.

All red artifacts are retained in the original work directories and compact
[initial runtime log](abi-evidence/initial-runtime-red.log) and
[independent review evidence](abi-independent-repairs-evidence/).
Earlier wheel/test epochs remain historical and are not substituted for the
current exact-source checks.

## Remaining applicable work

The private module does not yet provide public CLI/API/policy/report/editor
integration. API compatibility, fuzzing, dependency/provenance evidence, compiler
receipt lineage, additional formats/tool versions/platforms and the rest of
FR-EVD-10 / M9-03 / P12 remain open. The complete production acceptance ledger,
AC-01..16 and P14 must still pass `scripts/verify_delivery.py --require-complete`
before any full-program completion claim.

[Source/evidence hash manifest](abi-evidence/manifest.json) binds this slice.
