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

include(GNUInstallDirs)
include(CTest)

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
    libclang-20.so.1 libclang-19.so.1 libclang-18.so.1 libclang-17.so.1
    PATHS ${_LIBCLANG_HINT_PATHS} /usr/lib/llvm-20/lib /usr/lib/llvm-19/lib /usr/lib/llvm-18/lib /usr/lib/llvm-17/lib /usr/lib)

set(_LIBCLANG_INCLUDE_HINTS "")
foreach(_lib_dir ${_LIBCLANG_HINT_PATHS})
    get_filename_component(_prefix "${_lib_dir}" DIRECTORY)
    list(APPEND _LIBCLANG_INCLUDE_HINTS "${_prefix}/include")
endforeach()

find_path(LIBCLANG_INCLUDE_DIR NAMES clang-c/Index.h
    PATHS ${_LIBCLANG_INCLUDE_HINTS} /usr/lib/llvm-20/include /usr/lib/llvm-19/include /usr/lib/llvm-18/include /usr/lib/llvm-17/include /usr/include)
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

# Counting semantic logical operators requires the binary-opcode API. Detect
# header/library mismatches at configure time rather than during a long build.
include(CheckCXXSourceCompiles)
include(CMakePushCheckState)
cmake_push_check_state(RESET)
set(CMAKE_REQUIRED_INCLUDES "${LIBCLANG_INCLUDE_DIR}")
set(CMAKE_REQUIRED_LIBRARIES "${LIBCLANG_LIBRARY}")
# A caller can change the selected pair in an existing build directory.
unset(CPPULSE_LIBCLANG_HAS_BINARY_OPCODE CACHE)
check_cxx_source_compiles("
#include <clang-c/Index.h>
int main() {
    return clang_Cursor_getBinaryOpcode(clang_getNullCursor()) == CX_BO_LAnd ? 0 : 1;
}" CPPULSE_LIBCLANG_HAS_BINARY_OPCODE)
cmake_pop_check_state()
if(NOT CPPULSE_LIBCLANG_HAS_BINARY_OPCODE)
    message(FATAL_ERROR
        "Selected libclang headers/library lack the required binary-opcode API "
        "(clang_Cursor_getBinaryOpcode / CX_BO_LAnd). Use a matching LLVM 19 or "
        "newer development/runtime pair, or set LIBCLANG_INCLUDE_DIR and "
        "LIBCLANG_LIBRARY explicitly. Headers: ${LIBCLANG_INCLUDE_DIR}; "
        "library: ${LIBCLANG_LIBRARY}")
endif()

find_package(nlohmann_json REQUIRED CONFIG)
find_package(spdlog REQUIRED CONFIG)
find_package(CLI11 REQUIRED CONFIG)
if(BUILD_TESTING)
    find_package(GTest REQUIRED CONFIG)
    include(GoogleTest)
endif()

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

# The installed binary resolves packaged logging libraries relative to itself.
# Keep build-tree dependency paths out of the installed RUNPATH.
if(UNIX AND NOT APPLE)
    file(RELATIVE_PATH _CPPULSE_RUNTIME_LIBRARY_PATH
        "/${CMAKE_INSTALL_LIBEXECDIR}/cppulse"
        "/${CMAKE_INSTALL_LIBDIR}/cppulse")
    set_target_properties(cppulse-analyzer PROPERTIES
        INSTALL_RPATH "$ORIGIN/${_CPPULSE_RUNTIME_LIBRARY_PATH}"
        INSTALL_RPATH_USE_LINK_PATH FALSE
    )
endif()
install(TARGETS cppulse-analyzer
    RUNTIME DESTINATION "${CMAKE_INSTALL_LIBEXECDIR}/cppulse"
)

# This finite Linux runtime profile uses the same declared host C++ runtime as
# the analyzer. The helper is dynamically linked in installed native kits.
set(_CPPULSE_RUNTIME_SUPERVISOR_DEFAULT OFF)
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    set(_CPPULSE_RUNTIME_SUPERVISOR_DEFAULT ON)
endif()
option(CPPULSE_BUILD_RUNTIME_SUPERVISOR
    "Build the bounded Linux runtime observation helper"
    ${_CPPULSE_RUNTIME_SUPERVISOR_DEFAULT})
if(CPPULSE_BUILD_RUNTIME_SUPERVISOR)
    if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
        message(FATAL_ERROR "The runtime observation helper currently requires Linux")
    endif()
    add_executable(cppulse-runtime-supervisor
        "${CMAKE_CURRENT_SOURCE_DIR}/../tools/frozen_container_supervisor.cpp")
    # Keep a primary-target build sufficient for the default installation.
    add_dependencies(cppulse-analyzer cppulse-runtime-supervisor)
    target_compile_options(cppulse-runtime-supervisor PRIVATE -Wall -Wextra -Werror)
    set_target_properties(cppulse-runtime-supervisor PROPERTIES
        INSTALL_RPATH ""
        INSTALL_RPATH_USE_LINK_PATH FALSE)
    install(TARGETS cppulse-runtime-supervisor
        RUNTIME DESTINATION "${CMAKE_INSTALL_LIBEXECDIR}/cppulse"
        COMPONENT runtime-supervisor)
endif()

# --------------------------------------------------------------------------
# Target: cppulse-analyzer-tests (test executable)
# --------------------------------------------------------------------------
if(BUILD_TESTING)
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

    add_test(NAME ConfigurationCli.profile_override
        COMMAND ${CMAKE_COMMAND}
            -DANALYZER_BIN=$<TARGET_FILE:cppulse-analyzer>
            -P ${CMAKE_CURRENT_SOURCE_DIR}/tests/check_profile_cli.cmake)

    add_test(NAME LibclangCapability.RejectsMissingBinaryOpcode
        COMMAND ${CMAKE_COMMAND}
            -DANALYZER_SOURCE=${CMAKE_CURRENT_SOURCE_DIR}
            -DLIBCLANG_LIBRARY=${LIBCLANG_LIBRARY}
            -P ${CMAKE_CURRENT_SOURCE_DIR}/tests/check_libclang_capability.cmake)

    # Resource-directory override must work for both parse modes and fail clearly
    # for invalid explicit/environment configuration.
    foreach(_resource_mode valid_fallback valid_db invalid_flag invalid_env relative_repo valid_inferred valid_barrier)
        add_test(NAME ResourceDirectoryCli.${_resource_mode}
            COMMAND ${CMAKE_COMMAND}
                -DANALYZER_BIN=$<TARGET_FILE:cppulse-analyzer>
                -DMODE=${_resource_mode}
                -P ${CMAKE_CURRENT_SOURCE_DIR}/tests/check_resource_dir_cli.cmake)
    endforeach()
    foreach(_config_mode unknown_key wrong_type ambiguous explicit)
        add_test(NAME ConfigurationCli.${_config_mode}
            COMMAND ${CMAKE_COMMAND}
                -DANALYZER_BIN=$<TARGET_FILE:cppulse-analyzer>
                -DMODE=${_config_mode}
                -P ${CMAKE_CURRENT_SOURCE_DIR}/tests/check_config_cli.cmake)
    endforeach()
endif()
