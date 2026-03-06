# Analyzer-Core CMake Setup -- Design

## Directory Layout

```
analyzer-core/
├── CMakeLists.txt          # Top-level CMake configuration
├── src/
│   ├── main.cpp            # Entry point for cppulse-analyzer executable
│   ├── analyzer.cpp        # Core analysis orchestration
│   ├── analyzer.h
│   ├── rules/              # 22 detection rules (CRTP engine)
│   │   ├── rule_base.h     # CRTP base template
│   │   ├── memory_safety/  # CPP-MOD-001 through CPP-MOD-003
│   │   ├── modernization/  # CPP-MOD-004 through CPP-MOD-012
│   │   ├── complexity/     # CPP-MOD-013 through CPP-MOD-015
│   │   └── misra/          # MISRA-001 through MISRA-007
│   └── ...                 # Additional source files
├── include/                # Public headers (if needed for CLI component)
│   └── cppulse/
├── tests/
│   ├── test_main.cpp       # GoogleTest main (or gtest_main linkage)
│   ├── test_analyzer.cpp
│   └── rules/              # Per-rule test files
└── build/                  # Out-of-source build directory (gitignored)
```

## CMake Target Structure

The build defines three targets with a clear dependency graph:

```
                    ┌─────────────────────┐
                    │ cppulse-analyzer-lib│  (STATIC library)
                    │                     │
                    │ src/*.cpp           │
                    │ (excluding main.cpp)│
                    └──────┬──────┬───────┘
                           │      │
              links to     │      │     links to
                           │      │
                  ┌────────▼──┐ ┌─▼────────────────────┐
                  │ cppulse-  │ │ cppulse-analyzer-    │
                  │ analyzer  │ │ tests                │
                  │           │ │                      │
                  │ EXECUTABLE│ │ EXECUTABLE (test)    │
                  │ main.cpp  │ │ tests/*.cpp          │
                  └───────────┘ └──────────────────────┘
```

### Target: `cppulse-analyzer-lib` (STATIC)

- **Sources**: All `.cpp` files under `src/` except `src/main.cpp`.
- **Include directories**: `src/` (PRIVATE), `include/` (PUBLIC, if populated).
- **Linked libraries**: `libclang`, `nlohmann_json::nlohmann_json`, `spdlog::spdlog`, `CLI11::CLI11`.
- **Compile features**: `cxx_std_17`.
- **Compile options**: `-Wall -Wextra -Werror`.
- **Rationale**: Isolating the engine into a library avoids compiling sources twice (once for the binary, once for tests).

### Target: `cppulse-analyzer` (EXECUTABLE)

- **Sources**: `src/main.cpp`.
- **Linked libraries**: `cppulse-analyzer-lib`.
- **Output name**: `cppulse-analyzer` (set via `set_target_properties(... PROPERTIES OUTPUT_NAME "cppulse-analyzer")`).

### Target: `cppulse-analyzer-tests` (EXECUTABLE)

- **Sources**: All `.cpp` files under `tests/`.
- **Linked libraries**: `cppulse-analyzer-lib`, `GTest::gtest`, `GTest::gtest_main`.
- **CTest integration**: `gtest_discover_tests(cppulse-analyzer-tests)`.
- **Build condition**: Always built (no `BUILD_TESTING` gate for now -- tests are integral to the workflow).

## Dependency Resolution Details

### libclang

```cmake
find_package(Clang REQUIRED CONFIG)
```

Links via `libclang` imported target. The Clang package provides the `libclang` target when installed via system packages or LLVM distributions. Include directories are transitively propagated.

### nlohmann/json

```cmake
find_package(nlohmann_json REQUIRED CONFIG)
```

Links via `nlohmann_json::nlohmann_json`. Header-only library; no runtime linkage cost.

### spdlog

```cmake
find_package(spdlog REQUIRED CONFIG)
```

Links via `spdlog::spdlog`. Provides structured logging as mandated by project rules (no `std::cout`).

### CLI11

```cmake
find_package(CLI11 REQUIRED CONFIG)
```

Links via `CLI11::CLI11`. Header-only command-line parser used for `--repo` and `--output` flags.

### GoogleTest

```cmake
find_package(GTest REQUIRED CONFIG)
include(GoogleTest)
```

Links via `GTest::gtest` and `GTest::gtest_main`. The `GoogleTest` CMake module provides `gtest_discover_tests()` for automatic CTest registration.

## Global CMake Settings

```cmake
cmake_minimum_required(VERSION 3.16)
project(cppulse-analyzer LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
```

- **Minimum CMake 3.16**: Required for `gtest_discover_tests()` reliability and modern `find_package` behavior.
- **`CMAKE_EXPORT_COMPILE_COMMANDS`**: Generates `compile_commands.json` for clang-tidy integration.
