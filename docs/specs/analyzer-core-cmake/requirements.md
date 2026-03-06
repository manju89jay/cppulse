# Analyzer-Core CMake Setup -- Requirements

## Functional Requirements

### FR-1: Project Configuration
The CMake project shall define `cppulse-analyzer` as the top-level project with a minimum CMake version of 3.16.

### FR-2: C++17 Standard
All targets shall compile with the C++17 standard (`CMAKE_CXX_STANDARD 17`) with extensions disabled (`CMAKE_CXX_EXTENSIONS OFF`).

### FR-3: Dependency Resolution
The build system shall locate and link the following external dependencies:

| Dependency     | CMake mechanism              | Required |
|----------------|------------------------------|----------|
| libclang       | `find_package(Clang)`        | Yes      |
| nlohmann/json  | `find_package(nlohmann_json)`| Yes      |
| spdlog         | `find_package(spdlog)`       | Yes      |
| CLI11          | `find_package(CLI11)`        | Yes      |
| GoogleTest     | `find_package(GTest)`        | Yes (test builds only) |

### FR-4: Library Target
A static library target (`cppulse-analyzer-lib`) shall be built from all source files under `src/` (excluding `main.cpp`). This library encapsulates the analysis engine and all 22 detection rules so that both the executable and the test suite can link against it.

### FR-5: Executable Target
An executable target named `cppulse-analyzer` shall be built from `src/main.cpp` and linked against `cppulse-analyzer-lib`. The output binary name must be exactly `cppulse-analyzer` to match the docker-compose service command.

### FR-6: Test Target
A test executable (`cppulse-analyzer-tests`) shall be built from all source files under `tests/`. It shall link against `cppulse-analyzer-lib` and GoogleTest. Tests shall be registered with CTest via `gtest_discover_tests()` so that `ctest --output-on-failure` works as documented in CLAUDE.md.

### FR-7: Build Directory Convention
The build system shall support the out-of-source build pattern `cmake -B build && cmake --build build` as specified in CLAUDE.md.

## Non-Functional Requirements

### NFR-1: Compiler Warning Flags
All targets shall compile with the flags: `-Wall -Wextra -Werror` as mandated by the C++ style rules.

### NFR-2: Clang-Tidy Compatibility
The build must produce a `compile_commands.json` (via `CMAKE_EXPORT_COMPILE_COMMANDS ON`) so that `clang-tidy src/*.cpp -- -std=c++17` works without manual flag specification.

### NFR-3: Cross-Platform Consideration
The CMake configuration shall work on Linux (primary -- Docker container) and should not use platform-specific commands. Local development on macOS and Windows is secondary but should not be explicitly broken.

### NFR-4: Build Performance
The library target shall be compiled once and linked into both the executable and test targets to avoid redundant compilation.

## Acceptance Criteria

1. Running `cd analyzer-core && cmake -B build` completes without errors when all dependencies are installed.
2. Running `cmake --build build` produces the binary `build/cppulse-analyzer`.
3. Running `cd analyzer-core/build && ctest --output-on-failure` discovers and runs all GoogleTest tests.
4. `build/compile_commands.json` is generated and contains entries with `-std=c++17`.
5. Compilation fails if any `-Wall -Wextra -Werror` warning is triggered (warnings are treated as errors).
6. The binary name is exactly `cppulse-analyzer` (matches docker-compose command path `/usr/local/bin/cppulse-analyzer`).

## Out of Scope

- Dockerfile for analyzer-core (separate spec).
- Install targets or `cmake --install` rules.
- CPack packaging.
- FetchContent or vendored dependency management (dependencies are assumed pre-installed in the Docker image and discoverable by CMake).
- IDE-specific generator configurations (Xcode, Visual Studio).
- Sanitizer or coverage build variants (future spec).
