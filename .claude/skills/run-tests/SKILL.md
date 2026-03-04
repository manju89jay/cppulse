---
name: run-tests
description: Run the full test suite for one or all components and report coverage.
             Invoke before any commit to main.
allowed-tools: Bash, Read
---

# run-tests Skill

## Steps

1. **Determine scope**: which component(s) to test (default: all)

2. **C++ tests** (if analyzer-core or cli changed):
   ```bash
   cd analyzer-core && cmake --build build && ctest --output-on-failure
   ```
   Report: total tests, passing, failing, any output from failures.

3. **Python tests** (for each changed Python component):
   ```bash
   cd <component> && pytest -v --cov=src --cov-report=term-missing tests/
   ```
   Report: total tests, passing, failing, coverage % per module.

4. **Lint check**:
   - C++: `clang-tidy analyzer-core/src/*.cpp -- -std=c++17`
   - Python: `ruff check . && black --check .`

5. **Coverage gate**: if any component is below 70% coverage, list the
   uncovered functions and ask: "Write tests for these, or accept lower coverage?"

6. **Report**:
   ```
   Test Results:
   - analyzer-core: N/N passing, coverage N%
   - git-miner:     N/N passing, coverage N%
   - predictor:     N/N passing, coverage N%
   - report-engine: N/N passing, coverage N%
   Lint: CLEAN / ISSUES (list)
   Ready to commit: YES / NO (reason)
   ```
