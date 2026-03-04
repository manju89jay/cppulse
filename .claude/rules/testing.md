---
paths:
  - "**/tests/**"
  - "**/*_test.cpp"
  - "**/test_*.py"
---

# Testing Rules

## C++ Tests (GoogleTest)
- Test file naming: `test_<class_name>.cpp` in the component's `tests/` directory
- Test naming: `TEST(RuleNameTest, DetectsViolationInSimpleCase)`
- Every rule must have at minimum:
  - One test that finds a violation (with expected line number)
  - One test with a clean file that returns zero findings
  - One edge case test (empty file, template code, system header)
- Use `ASSERT_EQ` for counts, `EXPECT_EQ` for individual field checks
- Test fixtures (sample .cpp files with known violations) go in `tests/fixtures/`

## Python Tests (pytest)
- Test file naming: `test_<module_name>.py` in the component's `tests/` directory
- Use `pytest.fixture` in `conftest.py` for shared test data
- Synthetic git repos: create with `git.Repo.init(tmp_path)` — always use `tmp_path` fixture for isolation
- No hardcoded paths — all paths relative to `tmp_path` or repo root
- Coverage target: ≥70% branch coverage on every Python component
- Run with: `pytest -v --cov=src --cov-report=term-missing tests/`

## General
- Tests must be independent — no test should depend on another test's side effects
- Tests must be deterministic — no randomness without a fixed seed
- Tests must clean up after themselves — no files left in working directory
- Test names must describe WHAT they test, not HOW: `detects_raw_pointer_in_constructor` not `test1`
