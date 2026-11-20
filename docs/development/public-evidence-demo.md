# Public local evidence demo

`scripts/demo_evidence.py` exercises the actual public dispatcher using a clearly
labeled synthetic C++ fixture. It does not install tools, create Git commits,
change refs, call GitHub, or upload anything. The earlier four-document
analysis/ranking demo remains a separate workflow.

Run with a Python environment containing cppulse and its PDF/report dependencies,
a matching native analyzer and Clang builtin resource tree, GCC, CMake and CTest:

```bash
python /path/to/harness/demo_evidence.py \
  --analyzer /path/to/native/libexec/cppulse/cppulse-analyzer \
  --resource-dir /path/to/native/share/cppulse/clang/19 \
  --fixture /path/to/policy-fixture \
  --output /path/to/fresh-demo-output
```

Use the actual analyzer/resource paths from the selected native installation
metadata; the example does not prescribe an installation layout. The harness
needs its sibling `demo_policy.py`. These two files and `demo/policy-fixture` can
be copied together outside the checkout. Installed execution needs no
`PYTHONPATH`. For explicit source development, set `PYTHONPATH` to the checkout's
absolute `python` directory; the summary records this setting and the imported
module path. The harness never modifies the import path itself.

The default `--formats json,html,pdf` requires every requested format to work.
For a core-only installation without the optional PDF backend, explicitly select
`--formats json,html`. Its summary records that PDF was not requested; it does
not claim a successful PDF check. A requested PDF failure remains a demo failure.

The default `--scenario all` runs three cases:

| Case | Actual native/CTest behavior | Stored policy gate / public check exit |
| --- | --- | --- |
| `clean` | Selected source parses, selected rule has zero findings, CTest passes | `passed` / 0 |
| `findings` | Intentional raw allocation findings; CTest still passes | `failed` / 1 |
| `missing-tests` | CTest succeeds but writes its XML to a different filename than the declared report | `insufficient_evidence` / 3 |

Every case invokes `collect`, `assess`, `check --policy`, historical `explain`,
and `report --evidence` in JSON, HTML and PDF formats as separate public commands.
Requests select finite source/resource files and original receipt input/output
roles; no arbitrary normalizer plugin is loaded. An explicit captured
`cmake -E rm -rf build native-build native-report` step clears only generated
directories inside each newly created harness-owned workspace. The native
report totals, file paths, selected rule execution, observed parse context,
immutable manifest pins and reports are checked. A partial collection does not
become a successful collection because normalization or presentation succeeds.

The clean case also copies the installed `data/Cppulse.cmake` into its fixture
before source capture. Its explicit `cppulse_evidence_check` target depends on
the real `cppulse-policy-demo` binary. A transparent local launcher calls the
same Python interpreter's public `cppulse.cli`; it does not inject an import
path. The default build creates no cppulse runs. The selected check target
reassesses retained material without collecting. Deliberate source and binary
changes produce exit 3 and a new partial attempt; CMake reports an aggregate
nonzero build result for a failed check. Historical pinned clean results remain
readable, and the latest partial attempt exposes no old positive assessment.
The clean workspace is deliberately left stale after this negative check.

Optionally pass `--action-entrypoint /path/to/copied/entrypoint.sh` to exercise
the local Bash wrapper over the real public check for each case. This is not a
Docker container, hosted GitHub Action, comment, upload, or remote CI run. The
wrapper's actual result JSON and exit status are retained.

Outputs are appended under `OUTPUT/batches/<unique-id>/`. `OUTPUT/latest-demo.json`
points to the last fully verified batch. Each case retains request/policy JSON,
the immutable store, reports, exact command argv/cwd, selected environment
overrides, UTC start/end times, actual exit codes and byte-preserved stdout/stderr
logs. A failed harness leaves its batch and logs but does not replace this last
verified pointer. Content hashes identify bytes; they do not authenticate tools
or establish a complete host header/runtime dependency closure. These scoped
experimental rules and gates are not certification or proof of safety.

Launch failures and timeouts retain their attempted argv/cwd, available output
and explicit failure status; their command exit remains null when not observed.
The harness inventory hashes both Python drivers and the optional selected Bash
wrapper. PDF text extraction is verified when `pdftotext` is available and
otherwise explicitly recorded as not run; visual review is separate.

For an interview, open the clean PDF and its matching JSON pin, then the finding
case: the tests pass while the selected rule independently fails. Finish with
the missing XML case and the clean case's stale checks to show why unavailable
or changed evidence cannot silently reuse a previous passing decision.
