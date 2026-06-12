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
# Search order: caller hints (CMAKE_PREFIX_PATH / LIBCLANG_ROOT),
# MSYS2/MinGW prefixes (Windows), then Ubuntu LLVM layouts.
set(_LIBCLANG_HINT_PATHS "")
if(DEFINED ENV{LIBCLANG_ROOT})
    list(APPEND _LIBCLANG_HINT_PATHS "$ENV{LIBCLANG_ROOT}/lib")
endif()
if(DEFINED ENV{MINGW_PREFIX})
    list(APPEND _LIBCLANG_HINT_PATHS "$ENV{MINGW_PREFIX}/lib")
endif()
if(WIN32)
    list(APPEND _LIBCLANG_HINT_PATHS "C:/msys64/mingw64/lib" "C:/msys64/clang64/lib")
endif()

find_library(LIBCLANG_LIBRARY NAMES clang libclang
    PATHS ${_LIBCLANG_HINT_PATHS} /usr/lib/llvm-18/lib /usr/lib/llvm-17/lib /usr/lib)

set(_LIBCLANG_INCLUDE_HINTS "")
foreach(_lib_dir ${_LIBCLANG_HINT_PATHS})
    get_filename_component(_prefix "${_lib_dir}" DIRECTORY)
    list(APPEND _LIBCLANG_INCLUDE_HINTS "${_prefix}/include")
endforeach()

find_path(LIBCLANG_INCLUDE_DIR NAMES clang-c/Index.h
    PATHS ${_LIBCLANG_INCLUDE_HINTS} /usr/lib/llvm-18/include /usr/lib/llvm-17/include /usr/include)
if(NOT LIBCLANG_LIBRARY OR NOT LIBCLANG_INCLUDE_DIR)
    message(FATAL_ERROR
        "libclang not found. Install libclang-dev (Ubuntu) or mingw-w64-x86_64-clang (MSYS2), "
        "or set LIBCLANG_ROOT to an LLVM install prefix.")
endif()
message(STATUS "libclang library: ${LIBCLANG_LIBRARY}")
message(STATUS "libclang include: ${LIBCLANG_INCLUDE_DIR}")
# UNKNOWN: links the found library path directly; avoids needing the DLL vs
# import-lib (IMPORTED_IMPLIB) split on Windows.
add_library(libclang UNKNOWN IMPORTED)
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

# Discovery launches the test binary at build time; first launch can exceed the
# 5s default on Windows (libclang DLL load + AV scan), so allow more headroom.
gtest_discover_tests(cppulse-analyzer-tests DISCOVERY_TIMEOUT 30)
