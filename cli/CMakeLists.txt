cmake_minimum_required(VERSION 3.16)
project(cppulse-cli LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

find_package(spdlog REQUIRED CONFIG)
find_package(CLI11 REQUIRED CONFIG)
find_package(GTest REQUIRED CONFIG)
include(GoogleTest)
enable_testing()

# CLI library (without main)
add_library(cppulse-cli-lib STATIC src/orchestrator.cpp)
target_include_directories(cppulse-cli-lib PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_compile_options(cppulse-cli-lib PRIVATE -Wall -Wextra -Werror)
target_link_libraries(cppulse-cli-lib PUBLIC spdlog::spdlog CLI11::CLI11)

# CLI executable
add_executable(cppulse src/main.cpp)
target_link_libraries(cppulse PRIVATE cppulse-cli-lib)
set_target_properties(cppulse PROPERTIES OUTPUT_NAME "cppulse")

# Tests
file(GLOB_RECURSE TEST_SOURCES CONFIGURE_DEPENDS "tests/*.cpp")
if(TEST_SOURCES)
    add_executable(cppulse-cli-tests ${TEST_SOURCES})
    target_include_directories(cppulse-cli-tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
    target_link_libraries(cppulse-cli-tests PRIVATE cppulse-cli-lib GTest::gtest GTest::gtest_main)
    gtest_discover_tests(cppulse-cli-tests)
endif()
