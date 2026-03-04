---
name: implement-feature
description: Step-by-step workflow for implementing a cppulse feature using SDD.
             Invoke at the start of any new implementation task.
allowed-tools: Read, Write, Edit, Bash, Grep, Glob
---

# implement-feature Skill

Follow these steps in order. Do not skip steps.

## Step 1 — Read the Spec
Read `docs/specs/<feature>/requirements.md`, `design.md`, and `tasks.md`.
If no spec exists: STOP and invoke the spec-writer agent first.

## Step 2 — Understand the Interface
Read the adjacent component's output format (JSON schema, header file, or API endpoint)
to understand exactly what your inputs look like and what your outputs must produce.

## Step 3 — Write the Interface First
For C++: write the `.hpp` header with all public method signatures and Doxygen comments.
For Python: write the module with function signatures and type hints only (no body yet).
This is your implementation contract.

## Step 4 — Implement
Fill in the implementation. Follow the relevant `.claude/rules/` for this file type.
For C++: run clang-format after each file.
For Python: run black + ruff after each file.

## Step 5 — Write Tests
Write tests BEFORE confirming the implementation is correct.
Minimum: one passing test, one edge case test.
Run tests. If any fail, fix the implementation — not the test.

## Step 6 — Verify
- C++: `cmake --build build && ctest --output-on-failure`
- Python: `pytest -v --cov=src tests/`
- All tests must pass before proceeding.

## Step 7 — Report
State: "Implemented: <files>. Tests: <N> passing. Ready for commit."
