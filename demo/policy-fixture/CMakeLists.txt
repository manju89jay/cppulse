cmake_minimum_required(VERSION 3.16)
project(cppulse-policy-fixture LANGUAGES CXX)
option(CPPULSE_DEMO_TRIGGER_RULE "Select intentional raw-pointer rule triggers" OFF)
option(CPPULSE_DEMO_PARSE_ERROR "Select an intentionally missing include" OFF)
option(CPPULSE_DEMO_TEST_FAILURE "Select a deliberate test failure" OFF)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
add_executable(cppulse-policy-demo main.cpp)
target_compile_options(cppulse-policy-demo PRIVATE -Wall -Wextra -Werror)
target_compile_definitions(cppulse-policy-demo PRIVATE
    CPPULSE_DEMO_TRIGGER_RULE=$<BOOL:${CPPULSE_DEMO_TRIGGER_RULE}>
    CPPULSE_DEMO_PARSE_ERROR=$<BOOL:${CPPULSE_DEMO_PARSE_ERROR}>
    CPPULSE_DEMO_TEST_FAILURE=$<BOOL:${CPPULSE_DEMO_TEST_FAILURE}>)
enable_testing()
add_test(NAME selected-policy-consumer COMMAND cppulse-policy-demo)
