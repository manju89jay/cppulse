# Shared local checks

Run the checks from an environment with the project's compiler/libclang, CMake,
Python development extras, Node dependencies and optional PDF/web dependencies
installed. The runner does not install tools, modify source formatting or contact
an external CI service.

```bash
python scripts/check_local.py
```

The default runs Python format checks, generated-resource drift checks, root
contract/integration tests, analyzer CMake build and CTest, the three Python
component suites, dashboard tests/build and CLI CMake build/CTest. Commands use
argument vectors with `shell=False`. CMake and component tests retain their
normal build directories. Native configuration explicitly enables `BUILD_TESTING`,
and CTest treats zero discovered tests as an error. The source checkout must have its build prerequisites
configured. The Bash entry point delegates to the same Python runner:

```bash
CPPULSE_PYTHON=.venv/bin/python scripts/check_local.sh
```

Select repeatable sections for focused review:

```bash
python scripts/check_local.py --section generated --section root
python scripts/check_local.py --section python --section dashboard --jobs 4
python scripts/check_local.py --section docker
```

`--section all` explicitly includes Docker. Docker is not part of the default:
its absence blocks that requested check and never counts as a Compose pass.
The Docker section invokes `scripts/integration_test.sh` and requires Bash,
Docker and Compose. The native Python runner uses platform path handling;
Windows/macOS builds remain unverified until executed on those systems.
`--python`, `--cmake`, `--ctest` and `--npm` select explicit tools without
changing the global PATH.

Results are written after each command to `review/logs/check-results.json` and
per-check logs in that directory. Use `--output-dir PATH` to retain a separate
review run. Each result records the exact argument vector, working directory,
return code, timestamps and log path. A failed prerequisite blocks its dependent
build/test; independent checks continue. Exit status is `0` for selected checks
passed, `1` when any check failed, and `2` when work was blocked by missing tools
or prerequisites. Only the sections named in the results were checked.

Each Python component still runs `pytest -v --cov=src tests/` with an additional
`--cov=cppulse.<component>` target and a JSON report. The legacy `src` modules
are compatibility shims, so the enforced implementation coverage is calculated
only from canonical namespace files: 80% for Git miner and 75% each for predictor
and report engine. Stale coverage files are removed before running tests.
A missing or insufficient canonical report cannot pass because shims are covered.

Formatting is check-only. Its scope includes `python/`, the three migrated
`src/` directories, and changed Python scripts/root tests reported by Git. The
runner reports existing formatting failures without rewriting unrelated source.
Generated schemas/config/dashboard resources are checked by
`scripts/check_generated.py`; updating those snapshots is an explicit developer
action, never a test side effect.
