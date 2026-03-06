# Analyzer-Core CMake Setup -- Implementation Tasks

Each task is atomic and should result in a single, testable change.

## Tasks

1. **Create the `analyzer-core/` directory structure.**
   Create the directories: `src/`, `src/rules/`, `include/cppulse/`, `tests/`. Remove the existing `.gitkeep` placeholder once real files exist.

2. **Create a minimal `src/main.cpp`.**
   Write a stub `main()` that returns 0. This is needed so the executable target has a source file and the build can be validated end-to-end.

3. **Create a minimal library source file `src/analyzer.cpp` and `src/analyzer.h`.**
   Write a stub function (e.g., `int run_analysis()`) so the static library target has at least one compilation unit.

4. **Create a minimal test file `tests/test_analyzer.cpp`.**
   Write one GoogleTest test case that calls the stub function from task 3 and asserts the expected return value. This validates the test target links correctly.

5. **Write `analyzer-core/CMakeLists.txt` with project-level settings.**
   Set `cmake_minimum_required(VERSION 3.16)`, `project(cppulse-analyzer LANGUAGES CXX)`, C++17 standard variables, and `CMAKE_EXPORT_COMPILE_COMMANDS ON`.

6. **Add `find_package` calls for all dependencies.**
   Add `find_package(Clang REQUIRED CONFIG)`, `find_package(nlohmann_json REQUIRED CONFIG)`, `find_package(spdlog REQUIRED CONFIG)`, `find_package(CLI11 REQUIRED CONFIG)`, and `find_package(GTest REQUIRED CONFIG)` with `include(GoogleTest)`.

7. **Define the `cppulse-analyzer-lib` static library target.**
   Use a `file(GLOB ...)` or explicit source list for `src/*.cpp` excluding `src/main.cpp`. Set `target_compile_features(cppulse-analyzer-lib PRIVATE cxx_std_17)`. Add `target_compile_options` with `-Wall -Wextra -Werror`. Link all four runtime dependencies.

8. **Define the `cppulse-analyzer` executable target.**
   Add executable from `src/main.cpp`, link against `cppulse-analyzer-lib`, and set `OUTPUT_NAME` to `cppulse-analyzer`.

9. **Define the `cppulse-analyzer-tests` test target.**
   Add executable from `tests/*.cpp`, link against `cppulse-analyzer-lib`, `GTest::gtest`, and `GTest::gtest_main`. Call `gtest_discover_tests(cppulse-analyzer-tests)`.

10. **Add `build/` to `analyzer-core/.gitignore`.**
    Ensure the out-of-source build directory is not tracked by git.

11. **Validate the build end-to-end.**
    Run `cd analyzer-core && cmake -B build && cmake --build build` and confirm `build/cppulse-analyzer` exists. Run `cd analyzer-core/build && ctest --output-on-failure` and confirm the stub test passes. Verify `build/compile_commands.json` is generated.
