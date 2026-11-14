# Opt-in local CMake and hook checks

These integrations call the installed engine. They do not implement policy math,
collect implicitly, change refs or send results anywhere. CMake/Makefiles 3.31.6
and pre-commit 4.3.0 were exercised locally; Docker/GitHub runner execution was
not. Hook control tests use an explicitly synthetic CLI; the real installed
journey is recorded separately in the candidate review.

## CMake

Find the helper in the same Python environment as the selected console command:

```bash
python -c 'from importlib.resources import files; print(files("cppulse").joinpath("data/Cppulse.cmake"))'
```

Include that path after defining the desired build targets:

```cmake
include("/absolute/venv/lib/python3.12/site-packages/cppulse/data/Cppulse.cmake")
cppulse_add_check(
  NAME cppulse_check
  EXECUTABLE "/absolute/venv/bin/cppulse"
  STORE "${CMAKE_SOURCE_DIR}/cppulse-output"
  WORKSPACE "${CMAKE_SOURCE_DIR}"
  POLICY "${CMAKE_SOURCE_DIR}/cppulse-policy.json"
  DEPENDS my_application
  EXPORT_COMPILE_COMMANDS
  CONTEXT_DATABASE_OUT_VAR CPPULSE_COMPILATION_DATABASE
)
```

`cmake --build build --target cppulse_check` builds only the selected target
dependencies before invoking the explicit check. The check target is outside
`ALL`; opt into normal-build enforcement by explicitly adding
`ENFORCE_DEFAULT_BUILD`. Failure stops the build, although CMake's aggregate exit
code can differ from the CLI's exit. Invalid modes or half a pin pair fail at
configuration time. Paths with spaces are preserved as arguments.

Use `FINDINGS /absolute/comparison-request.json` instead of `POLICY` for the
separate finding-regression gate. Optional `RUN_ID` and `MANIFEST_SHA256` must be
supplied together. Compile database export is opt-in and supports the Makefiles
and Ninja generator interface; this environment exercised Makefiles. The helper
uses CMake 3.21+ command options, with 3.31.6 tested.

Collection belongs to a separate explicit recipe, with an isolated collection
build directory/configuration. Never make the recipe recursively build the
active check target. Reused owned build directories need explicit captured
cleanup or fresh outputs; a successful cached no-op cannot create new evidence.

`DEPENDS` specifies build ordering, not an applicability claim. The selected
snapshot/policy still defines the actual binary, sources and contexts verified.
A differently configured target needs corresponding collection; naming it as a
dependency does not make unrelated stored evidence apply. The helper does not
infer or rewrite compile contexts from target names.

## Optional local hook

The packaged example is `cppulse/data/templates/pre-commit.example.yaml`.
Copy and adapt it explicitly using your normal hook setup. No project hook is
installed by cppulse or by the demo. The example calls:

```bash
cppulse check --store cppulse-output --workspace . --policy cppulse-policy.json
```

It passes no changed filenames and runs once over the declared scope. It checks
already collected current material; stale or missing data fails instead of
silently launching a build or claiming a changed-file policy pass. The full local
verification suite needs the optional `requirements-verification.txt` tooling;
`CPPULSE_PRE_COMMIT` may select its executable in a separate tool environment.

The [action draft](../action-usage.md) is another local adapter to the same
engine. Its Bash behavior is tested; its Docker definition remains unexecuted.
No external CI service or automatic commenting integration was introduced.
