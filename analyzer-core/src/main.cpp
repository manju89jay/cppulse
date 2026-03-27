/**
 * @file main.cpp
 * @brief Entry point for the cppulse-analyzer executable.
 */

#include <spdlog/spdlog.h>

#include <CLI/CLI.hpp>
#include <filesystem>
#include <string>

#include "analyzer.h"
#include "hello_libclang.h"
#include "output_writer.h"

/**
 * @brief Application entry point.
 *
 * Supports two modes:
 *  1. Repo mode (--repo):  Discover and analyze all C++ files under a directory.
 *  2. File mode (positional arg):  Analyze a single file using function extraction.
 *
 * Findings are written to findings.json under the --output directory.
 *
 * @return 0 on success, non-zero on failure.
 */
int main(int argc, char* argv[]) {
    CLI::App app{"cppulse-analyzer — C++ codebase health analyzer"};

    std::string repo_path;
    std::string output_dir = "output";
    std::string single_file;

    app.add_option("--repo", repo_path, "Repository root directory to analyze recursively");
    app.add_option("--output", output_dir, "Output directory for findings.json")
        ->default_val("output");
    // Backward-compatible positional argument for single-file analysis.
    app.add_option("file", single_file, "C++ source file to analyze (single-file mode)")
        ->required(false);

    CLI11_PARSE(app, argc, argv);

    if (!repo_path.empty()) {
        // Full repo analysis mode.
        spdlog::info("cppulse-analyzer: analyzing repo '{}'", repo_path);

        cppulse::FileAnalyzer analyzer{std::filesystem::path{repo_path}};
        analyzer.run();

        const bool ok =
            cppulse::write_findings_json(analyzer.findings(), repo_path, analyzer.file_count(),
                                         analyzer.total_loc(), std::filesystem::path{output_dir});

        if (!ok) {
            spdlog::error("cppulse-analyzer: failed to write findings.json");
            return 1;
        }

        spdlog::info("cppulse-analyzer: {} finding(s) written to {}/findings.json",
                     analyzer.findings().size(), output_dir);
        return 0;
    }

    if (!single_file.empty()) {
        // Single-file backward-compatible mode.
        spdlog::info("cppulse-analyzer: analyzing '{}'", single_file);

        auto result = cppulse::extract_function_names(single_file);

        if (!result) {
            spdlog::error("cppulse-analyzer: failed to parse '{}'", single_file);
            return 1;
        }

        for (const auto& name : *result) {
            spdlog::info("  function: {}", name);
        }
        return 0;
    }

    spdlog::error("cppulse-analyzer: specify --repo <dir> or a source file");
    return 1;
}
