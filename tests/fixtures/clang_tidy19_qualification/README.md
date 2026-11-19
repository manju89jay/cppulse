# Controlled clang-tidy 19.1.7 qualification samples

These are genuine local producer captures from 19 November 2026, not authored
diagnostic text and not a general accuracy benchmark. The three C++ sources are
synthetic and intentionally contain warning triggers. No fixture binary was
executed.

The [case manifest](cases.json) declares the expected counts and settings before
the producer run. The [producer receipt](producer-receipt.json) retains exact
tool/source/argument identities, raw-output hashes and observed results. Files
under `captured/` are unmodified stdout/stderr. The executable was Debian LLVM
19.1.7, SHA-256
`9ebd2c4f2a123c058f4744e9a02a8000ab9ba22f9b835958dfda7c4d7de2527c`.
Its execution used C++17 and the declared per-case macro; compiler resource paths
and the historical Cloud source root are in the exact recorded argv. Source and
report hashes identify bytes; they do not authenticate imported producer claims
or close system-header/runtime dependencies.

| Family / controlled context | Actual primary records |
| --- | ---: |
| use-after-move: local value moved then read | 1 |
| use-after-move: reinitialized before read | 0 |
| use-after-move: one mutually exclusive if/else | 0 |
| use-after-move: correlated independent conditions | 1; known false positive |
| use-after-move: member and global values | 0; outside qualified detection scope |
| dangling-handle: default string view with temporary owner | 1 |
| dangling-handle: persistent owner | 0 |
| dangling-handle: custom handle under default selection | 0; custom support not established |
| unused-return-value: selected function ignored | 1 |
| unused-return-value: void cast, tool default | 1 |
| unused-return-value: void cast, explicit false | 1 |
| unused-return-value: void cast, explicit true | 0 |
| unused-return-value: selected function result used | 0 |
| unused-return-value: selected error type ignored | 1 |
| unused-return-value: selected error type used | 0 |
| unused-return-value: function not selected | 0 |

`bugprone-use-after-move` is flow-sensitive, not path-sensitive: the correlated
conditions sample cannot execute both branches, yet warns. It does not qualify
member/global move detection. The default dangling-handle classes are
`std::basic_string_view;std::experimental::basic_string_view`; these samples do
not establish arbitrary `span` or custom-handle coverage. The unused-return-value
samples explicitly pin `CheckedFunctions`/`CheckedReturnTypes`. LLVM 19.1.7's
`AllowCastToVoid=false` default makes a void cast a positive, unlike ordinary
nodiscard warnings. The raw default-option captures are included.

The old genuine report audited before this batch had only
`modernize-use-nullptr` and `clang-analyzer-core.NullDereference` primaries. Those
are not counted as qualification of these three new families. That audit is
retained at `work/coverage-t123/t2/actual1/prior-coverage-audit.json` in the Cloud
checkpoint.

Run the existing adapter/public-workflow tests from the repository root with the
development dependencies already installed:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  python -m pytest -q tests/test_clang_tidy19_families.py
```

That checks the retained genuine samples. To run the four actual public
collector/import/report journeys too, set `CPPULSE_TIDY19_TOOL` to the exact
qualified clang-tidy executable and expose its required shared libraries via
your normal loader environment. Those journeys also require `/usr/bin/g++-14`
and the recorded Clang resource directory; they skip explicitly when the tool
opt-in is absent. A skip is not completed qualification. The fixed Cloud run
used the existing resource wrapper and had no skips.

Observed empty stdout controls retain successful actual tool receipts, but the
text import remains `missing`, `origin=import`, and scope completeness
`unverified`. Notes remain original raw text and never multiply findings.
Declared local execution does not turn normalized imports into authenticated or
independently confirmed observations. The five existing external-analyzer,
import, boundary, matrix and public-workflow test modules remain the shared
negative controls rather than a copied test framework.
