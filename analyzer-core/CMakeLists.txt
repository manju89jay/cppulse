# --------------------------------------------------------------------------
# cppulse-analyzer -- CMake build configuration
# --------------------------------------------------------------------------
cmake_minimum_required(VERSION 3.16)
project(cppulse-analyzer LANGUAGES CXX)

# -- C++17 settings --------------------------------------------------------
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# -- Generate compile_commands.json for clang-tidy -------------------------
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# --------------------------------------------------------------------------
# Dependencies
# --------------------------------------------------------------------------
# libclang — Ubuntu ships libclang-dev without CMake config files,
# so we locate the library and headers manually.
find_library(LIBCLANG_LIBRARY NAMES clang PATHS /usr/lib/llvm-18/lib /usr/lib/llvm-17/lib /usr/lib)
find_path(LIBCLANG_INCLUDE_DIR NAMES clang-c/Index.h PATHS /usr/lib/llvm-18/include /usr/lib/llvm-17/include /usr/include)
if(NOT LIBCLANG_LIBRARY OR NOT LIBCLANG_INCLUDE_DIR)
    message(FATAL_ERROR "libclang not found. Install libclang-dev.")
endif()
add_library(libclang SHARED IMPORTED)
set_target_properties(libclang PROPERTIES
    IMPORTED_LOCATION "${LIBCLANG_LIBRARY}"
    INTERFACE_INCLUDE_DIRECTORIES "${LIBCLANG_INCLUDE_DIR}"
)

find_package(nlohmann_json REQUIRED CONFIG)
find_package(spdlog REQUIRED CONFIG)
find_package(CLI11 REQUIRED CONFIG)
find_package(GTest REQUIRED CONFIG)
include(GoogleTest)
enable_testing()

# --------------------------------------------------------------------------
# Target: cppulse-analyzer-lib (STATIC library)
# --------------------------------------------------------------------------
# Collect all .cpp files under src/, then remove main.cpp so the library
# contains only the analysis engine (no entry-point).
file(GLOB_RECURSE LIB_SOURCES CONFIGURE_DEPENDS "src/*.cpp")
list(FILTER LIB_SOURCES EXCLUDE REGEX "src/main\\.cpp$")

add_library(cppulse-analyzer-lib STATIC ${LIB_SOURCES})

target_include_directories(cppulse-analyzer-lib
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src
    PUBLIC  ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_options(cppulse-analyzer-lib PRIVATE -Wall -Wextra -Werror)

target_link_libraries(cppulse-analyzer-lib
    PUBLIC
        libclang
        nlohmann_json::nlohmann_json
        spdlog::spdlog
        CLI11::CLI11
)

# --------------------------------------------------------------------------
# Target: cppulse-analyzer (executable)
# --------------------------------------------------------------------------
add_executable(cppulse-analyzer src/main.cpp)

target_link_libraries(cppulse-analyzer PRIVATE cppulse-analyzer-lib)

set_target_properties(cppulse-analyzer PROPERTIES
    OUTPUT_NAME "cppulse-analyzer"
)

# --------------------------------------------------------------------------
# Target: cppulse-analyzer-tests (test executable)
# --------------------------------------------------------------------------
# Collect test sources, excluding fixture files (sample C++ for analysis).
file(GLOB_RECURSE TEST_SOURCES CONFIGURE_DEPENDS "tests/*.cpp")
list(FILTER TEST_SOURCES EXCLUDE REGEX "tests/fixtures/")

add_executable(cppulse-analyzer-tests ${TEST_SOURCES})

target_include_directories(cppulse-analyzer-tests
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src
)

target_link_libraries(cppulse-analyzer-tests
    PRIVATE
        cppulse-analyzer-lib
        GTest::gtest
        GTest::gtest_main
)

gtest_discover_tests(cppulse-analyzer-tests)
