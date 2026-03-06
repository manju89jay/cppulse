/**
 * @file main.cpp
 * @brief Entry point for the cppulse-analyzer executable.
 */

#include <CLI/CLI.hpp>
#include <spdlog/spdlog.h>

#include "hello_libclang.h"

/**
 * @brief Application entry point.
 *
 * Parses command-line arguments and runs libclang analysis on the target file.
 *
 * @return 0 on success, non-zero on failure.
 */
int main(int argc, char* argv[])
{
    CLI::App app{"cppulse-analyzer — C++ codebase health analyzer"};

    std::string file_path;
    app.add_option("file", file_path, "C++ source file to analyze")->required();

    CLI11_PARSE(app, argc, argv);

    spdlog::info("cppulse-analyzer: analyzing '{}'", file_path);

    auto result = cppulse::extract_function_names(file_path);

    if (!result) {
        spdlog::error("cppulse-analyzer: failed to parse '{}'", file_path);
        return 1;
    }

    for (const auto& name : *result) {
        spdlog::info("  function: {}", name);
    }

    return 0;
}
