# Contributing to cppulse

Thank you for your interest in contributing to cppulse! This guide covers
how to set up a development environment, run tests, and submit changes.

## Development Environment

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| GCC or Clang | C++17 support | Build analyzer-core and CLI |
| CMake | >= 3.16 | C++ build system |
| Python | >= 3.10 | predictor, git-miner, report-engine |
| Node.js | >= 18 | dashboard |
| libclang-dev | 17 or 18 | AST parsing in analyzer-core |

### Quick Start

```bash
# Clone the repository
git clone https://gitlab.com/manju89jay1/cppulse.git
cd cppulse

# C++ components (analyzer-core, CLI)
cd analyzer-core && cmake -B build && cmake --build build
cd ../cli && cmake -B build && cmake --build build

# Python components
pip install -r predictor/requirements.txt
pip install -r report-engine/requirements.txt
pip install -r git-miner/requirements.txt

# Dashboard
cd dashboard && npm install
```

### MSYS2 / MinGW (Windows)

```bash
pacman -S mingw-w64-x86_64-gcc mingw-w64-x86_64-cmake \
          mingw-w64-x86_64-spdlog mingw-w64-x86_64-nlohmann-json \
          mingw-w64-x86_64-cli11 mingw-w64-x86_64-gtest
export PATH="/c/msys64/mingw64/bin:$PATH"
cmake -B build -G "MinGW Makefiles" && cmake --build build
```

## Running Tests

Every component has its own test suite. Run them before submitting changes.

```bash
# analyzer-core (requires libclang)
cd analyzer-core/build && ctest --output-on-failure

# CLI
cd cli/build && ctest --output-on-failure

# predictor
cd predictor && pytest -v --cov=src tests/

# report-engine
cd report-engine && pytest -v --cov=src tests/

# git-miner
cd git-miner && pytest -v --cov=src tests/

# dashboard
cd dashboard && npm test
```

## Coding Standards

### C++ (analyzer-core, CLI)

- **Standard:** C++17. Compile with `-Wall -Wextra -Werror`.
- **Smart pointers only:** Never use raw `new`/`delete`.
- **Logging:** Use `spdlog`, not `std::cout`.
- **JSON:** Use `nlohmann/json` for all serialization.
- **Format:** Follow the existing code style. Run `clang-tidy` before submitting.

### Python (predictor, git-miner, report-engine)

- **Format:** `black` and `ruff` for linting.
- **Type hints:** Use type annotations on all public functions.
- **Docstrings:** Google-style docstrings on all public functions.
- **Tests:** pytest with `--cov` for coverage. Target >= 70% branch coverage.

### TypeScript / React (dashboard)

- **Strict mode:** TypeScript strict mode is enabled.
- **Styling:** Tailwind CSS utility classes.
- **Components:** Functional components with hooks.

## Project Structure

```
cppulse/
  analyzer-core/   C++17 static analysis engine (libclang)
  cli/             C++17 CLI orchestrator (CLI11)
  git-miner/       Python git history analyzer
  predictor/       Python ML pipeline (XGBoost)
  report-engine/   Python FastAPI + WeasyPrint PDF
  dashboard/       React + TypeScript UI
  docs/            ADRs, specs, architecture
```

See `docs/architecture.md` for the full system design.

## Submitting Changes

1. **Create a branch** from `main` with a descriptive name:
   `feat/add-new-rule`, `fix/windows-path-handling`, `docs/update-readme`.

2. **Write tests** for any new or changed functionality.

3. **Run all tests** in the affected components before pushing.

4. **Open a merge request** on GitLab with:
   - A clear title describing the change.
   - A description of what was changed and why.
   - Link to any related issues.

5. **Architectural changes** require an ADR in `docs/adr/`. See existing
   ADRs for the template.

## Per-Project Configuration

When working on a repository that uses cppulse, you can customize analysis
via a `.cppulserc.yml` file in the repo root. See `.cppulserc.example.yml`
for the full schema.

## Getting Help

- Open an issue on GitLab for bug reports or feature requests.
- Read `docs/adr/` for past architectural decisions and their rationale.
