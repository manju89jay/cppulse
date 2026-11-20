cmake_minimum_required(VERSION 3.16)
project(cppulse-sanitizer-fixture LANGUAGES NONE)

# Compilation/linking are separate explicit GCC recipe steps. This file only
# registers the selected actual binary for CTest command-identity observation.
set(CPPULSE_SANITIZER_BINARY "" CACHE FILEPATH "Selected direct executable")
set(CPPULSE_SANITIZER_CASE "clean" CACHE STRING "clean or bad fixture branch")
option(CPPULSE_REGISTER_TESTS "Register the selected synthetic test" ON)
option(CPPULSE_SKIP_TEST "Select the explicit skip-return-code case" OFF)
if(NOT CPPULSE_SANITIZER_BINARY)
    message(FATAL_ERROR "Select CPPULSE_SANITIZER_BINARY explicitly")
endif()
# Bind both automatically read CTest customization paths as known inert bytes.
configure_file(CTestCustom.cmake "${CMAKE_CURRENT_BINARY_DIR}/CTestCustom.cmake" COPYONLY)
configure_file(CTestCustom.ctest "${CMAKE_CURRENT_BINARY_DIR}/CTestCustom.ctest" COPYONLY)
enable_testing()
if(CPPULSE_REGISTER_TESTS)
    if(CPPULSE_SKIP_TEST)
        set(CPPULSE_SANITIZER_CASE "skip")
    endif()
    add_test(NAME selected-sanitizer-case
        COMMAND "${CPPULSE_SANITIZER_BINARY}" "${CPPULSE_SANITIZER_CASE}")
    set_tests_properties(selected-sanitizer-case PROPERTIES
        WORKING_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
    if(CPPULSE_SKIP_TEST)
        set_tests_properties(selected-sanitizer-case PROPERTIES SKIP_RETURN_CODE 77)
    endif()
endif()
