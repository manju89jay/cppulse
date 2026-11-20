# P11/M9-01 dry-run repair checkpoint

Implementation is uncommitted. This is a finite implemented slice, not full
M9-01/M9-02 or production-program acceptance. Independent review is pending.
The full requirement/task inventory and acceptance gates remain in the parent
ledger; source presence or the counts below do not close them.

## Implemented contract and behavior

- New `cppulse.repairs` module and private draft-07 plan schema implement a
  narrow ordinary builtin `typedef` → `using` textual proposal for the exact
  native `CPP-MOD-009` detector version `prototype-1`.
- Explicit immutable run/hash pins, checked original source/artifacts, complete
  matched native scope/rule execution, exact registry/version/parse context and
  original raw report matching are prerequisites. The direct API reopens a
  bounded32-MiB reader as well as checking current finite materials.
- Plans retain precise byte spans, source before/after SHA, the original
  observation/job/parser/inventory/receipt/registry/raw-report identities and
  applicable unified diffs. Git LF-line/EOF markers preserve CR/LF/CRLF/LFCR
  and Unicode comments. Compatible contexts share an edit without losing IDs.
- Macro/directive/forced-include, complex/multiple declarations, line-splice,
  partial, unsupported-standard, stale and ambiguous cases remain explicit
  rejections. There is no source application, command/model call, commit or PR.
- Complete plan files are published exclusively through an owned private staging
  directory and no-replace link; existing paths and the selected immutable
  store/run tree are never modified. The root owner separately added the public
  `cppulse fix` wrapper; this checkpoint's installed proof uses `-m` explicitly.

## Actual verification and provenance boundaries

The missing-runtime test first failed collection. Final source-bound focused
verification passed **35 tests, no skips**, with `source_stable:true` and exit0:

```sh
. work/cloud-resume/environment.sh
python scripts/record_delivery_check.py \
 --source python/cppulse/repairs.py \
 --source python/cppulse/contracts/schemas/repairs_private \
 --source tests/test_repairs.py --source docs/development/repairs.md \
 --evidence review/cloud-20261116-repairs-current --timeout 180 -- \
 python -m pytest -q tests/test_repairs.py \
 --basetemp=work/repairs-recorded-current
```

The earlier broader repair+native-inventory regression gate passed49 tests before
later hardening regressions were added; it is not relabeled as a new final count.
Black/Ruff and diff checks passed on the final owned files.

Actual GCC14 C++11/14/17/20 before/after builds use warnings-as-errors, static type
assertions and runtime behavior checks on an authored fixture. These are test
executions; plan construction itself executes no compiler or test.

Actual public collection ran CMake/CTest/native analysis in separate owned C++17
Debug workspaces. The original typedef yields one proposed edit; the separately
patched copy yields zero typedef findings and a no-op plan. Both compile and
execute the declared test. Original source bytes remain unchanged. Current plan
reads retain those exact original receipt/source pins and do not manufacture a
new producer execution. Producer binary SHA is retained in the evidence; a later
native writer candidate is not substituted into this historical run.

The Release variant with `-DNDEBUG` correctly yields an unsupported macro-context
result (exit3). A concurrent workspace-exhaustion attempt failed with ENOSPC and
was preserved rather than counted as green. After space was reclaimed, the
bounded Debug pair passed. These are distinct attempts.

The current module/schema also passed two actual installed-wheel `python -I -m
cppulse.repairs` runs from `/tmp`, with an empty command-tool PATH and GitPython
absent. Installed module/schema SHA values equal the current source. Complete
plans match API results. An initial installation inherited PYTHONPATH and saw
outside metadata; that attempt was corrected with isolated forced installation,
and the final import/hash proof excludes it. Only the exact scoped installed
module is qualified, not unrelated mutable candidate source.

Compact commands/results/hashes/plans are under `repairs-evidence/`. Raw owned
stores/build outputs and recipes remain under `work/repairs-actual/`; the isolated
wheel/closed dependency set/environment/proof remain under
`work/repairs-installed/`. No private source checkout or user Windows tree was
used. No source changes were committed or pushed.

## Remaining acceptance and decision for the shared log

Independent review, wider real-case/counterexample review, full installed public
CLI/client matrix and platform/scale/candidate gates remain open. This module is
not semantic AI repair; that separate language/behavior contract must preserve
fresh new-source verification rather than reusing old receipts. Passing selected
tests does not establish general semantic, ABI, performance or safety equivalence.

Decision recommendation: bind narrow textual proposals to retained actual native
facts and exact source bytes, preserve original evidence and use dry-run-only
publication until a separate safe application/behavior gate exists. The tradeoff
is a deliberately finite unsupported scope, not a claim that arbitrary syntax can
be rewritten safely. Hashes identify bytes, not producer/reviewer authenticity.

Independent native owner review subsequently passed 35/35 focused tests without a
material defect. `repairs-independent-native-review.json` binds the reviewed
module/schema/tests and exact log hash. Its scope is narrow deterministic preview,
not full M9/P11 acceptance; the stable installed/source-bound module hash remains
`17eef3a57c0fe72cd913b2a20a48bcd96b668638f90519eb23e8ec1b3ffce580`.
