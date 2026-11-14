# S4 bounded collection technical review

Accepted for the exercised POSIX/Linux, direct-binary CTest3.31.6 slice. Public
collect/assess CLI and policy assessment remain subsequent work. This review does
not establish arbitrary CMake/CTest support, a sandbox or product usefulness.

Implemented strict effective collection plans, explicit argv/DAG execution,
bounded dual-pipe capture, timeout/cancellation/process-group cleanup, source and
artifact checks, versioned JUnit and actual-command-log adapters, and coherent
receipt/evidence publication. Policy/plan loading does not execute project code.
Collection executes only the selected recipe. No implicit version command runs;
the CTest version and inventory probes are explicit recipe steps.

## Verification

```sh
source review/environment.sh
python scripts/check_local.py --output-dir review/autonomous/logs/s4-final-shared-checks
PYTHONPATH=python python scripts/demo_collection.py
PYTHONPATH=python python scripts/demo_collection.py --scenario missing-report --output output/collection-missing-only
```

All15 shared checks passed: root656, analyzer77, CLI20, Git90, predictor95,
report95 and dashboard37 tests, plus formatting/generated checks and the
production build. Collector-specific gate38passed (87% coverage); related gate
464passed. Independent final collector/log/JUnit review107passed. Executor
48real-process cases cover actual SIGINT, timeout/cancellation and grandchildren,
dual-pipe floods, file-size storage failures, stale outputs and changed inputs or
executables. Child-process source imports were fixed and verified with
PYTHONPATH unset. Earlier failed reproductions remain in logs/s4-*.log.

Fresh actual C++ fixture results are retained in output/collection-demo, with a
review summary in s4-demo-summary.json:

| Selected case | Collection | Build evidence | Test evidence |
|---|---|---|---|
| Clean | completed | passed/usable | passed/usable |
| Intentional test failure | completed | passed/usable | failed/usable |
| Intentional compilation failure | completed | failed/usable | skipped/missing |
| Intentional missing report | partial | passed/usable | error/missing |

The missing-only case has no last-completed pointer; it does not invent a prior
success. The combined demonstration retains earlier completed runs while making
the missing-report attempt current. Every snapshot verifies its bytes/contracts.
The tiny library/consumer is explicitly synthetic. The compiler context records
the selected configure command as inferred; actual compile_commands.json is
retained separately. This is not an exact whole-toolchain observation.

## Independent review corrections

Pre-run inventory alone named an expected binary while a decoy directory or a
changed generated test definition actually ran something else. The accepted
implementation additionally retains exact LastTest.log command records, matches
them outside captured program output to JUnit cases and selected binary bytes,
checks working-directory/configuration/selection/environment consistency, and
checks producing-step output identities against later inputs. Both original and
strengthened real counterexamples now produce partial/mismatched evidence.

Other corrected cases include actual CTest failed/disabled spellings, default XML
namespaces, non-UTF-8 tool output, numeric JSON integer compatibility, source/tool
mutation, host executable path handling, metadata cap enforcement and publication
races. Final source mutation aborts the first publication and republishes frozen
historical facts as partial/stale without rerunning commands.

## Bounds and scope

The effective plan records concurrency (at most32), per-step timeout, combined
stdout/stderr retention (default1MiB), per source/output/report/log file retention
(default64MiB), cppulse-authored control-metadata file retention (default16MiB)
and termination grace. Defaults are materialized before validation; persisted
plans are not silently rewritten. JSON integer-valued numbers are accepted and
normalized only for runtime APIs. No CPU/memory/total-disk quota is claimed.

Unchanged preexisting outputs do not establish fresh collection; use fresh build
directories or explicitly selected clean builds. Generic JUnit is import-only.
Unsupported producer versions, wrappers, ambiguous log boundaries and invocation
options remain unavailable. Source verification concerns a finite declared input
inventory; interpreter/runtime closures and producer authenticity are not proved.
Raw debug facts are hashed artifacts, not invented validated v2 contracts.
Docker/Compose and other operating systems remain unqualified.
