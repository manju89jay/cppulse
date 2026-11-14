cmake_minimum_required(VERSION 3.16)
project(cppulse-evidence-fixture VERSION 1.0.0 LANGUAGES CXX)

# Explicitly synthetic input for collection failure/clean demonstrations.
option(CPPULSE_DEMO_COMPILE_ERROR "Inject a deliberate compilation failure" OFF)
option(CPPULSE_DEMO_FAIL_TEST "Inject a deliberate test failure" OFF)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

add_library(cppulse-demo STATIC src/sum.cpp)
target_include_directories(cppulse-demo PUBLIC include)
target_compile_options(cppulse-demo PRIVATE -Wall -Wextra -Werror)
target_compile_definitions(cppulse-demo PRIVATE
    CPPULSE_DEMO_COMPILE_ERROR=$<BOOL:${CPPULSE_DEMO_COMPILE_ERROR}>)
add_executable(cppulse-demo-consumer tests/consumer.cpp)
target_link_libraries(cppulse-demo-consumer PRIVATE cppulse-demo)
target_compile_options(cppulse-demo-consumer PRIVATE -Wall -Wextra -Werror)
target_compile_definitions(cppulse-demo-consumer PRIVATE
    CPPULSE_DEMO_FAIL_TEST=$<BOOL:${CPPULSE_DEMO_FAIL_TEST}>)
enable_testing()
add_test(NAME sum-consumer COMMAND cppulse-demo-consumer)
