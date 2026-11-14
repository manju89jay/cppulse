/**
 * @file main.cpp
 * @brief Entry point for the cppulse-analyzer executable.
 */

#include <spdlog/spdlog.h>

#include <CLI/CLI.hpp>
#include <filesystem>
#include <optional>
#include <string>

#include "analyzer.h"
#include "config.h"
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
    std::string config_path;
    std::string single_file;
    std::string compilation_database;
    std::string resource_directory;

    app.add_option("--repo", repo_path, "Repository root directory to analyze recursively");
    app.add_option("--output", output_dir, "Output directory for findings.json")
        ->default_val("output");
    app.add_option("--compilation-database", compilation_database,
                   "compile_commands.json file or directory (overrides discovery)");
    app.add_option("--resource-dir", resource_directory,
                   "libclang resource directory containing include/stddef.h; "
                   "also CPPULSE_CLANG_RESOURCE_DIR")
        ->envname("CPPULSE_CLANG_RESOURCE_DIR");
    app.add_option(
        "--config", config_path,
        "Path to .cppulserc.yml/.json config file (auto-discovered from repo root if omitted)");
    // Backward-compatible positional argument for single-file analysis.
    app.add_option("file", single_file, "C++ source file to analyze (single-file mode)")
        ->required(false);

    CLI11_PARSE(app, argc, argv);

    std::optional<std::filesystem::path> resource_path;
    if (!resource_directory.empty()) {
        std::error_code resource_error;
        resource_path = std::filesystem::absolute(resource_directory);
        if (!std::filesystem::is_directory(*resource_path, resource_error) || resource_error ||
            !std::filesystem::is_regular_file(*resource_path / "include" / "stddef.h",
                                              resource_error) ||
            resource_error) {
            spdlog::error("Invalid libclang resource directory '{}': expected include/stddef.h",
                          resource_directory);
            return 2;
        }
        spdlog::info("cppulse-analyzer: builtin resource directory '{}'", resource_path->string());
    }

    if (!repo_path.empty()) {
        // Use one canonical subject identity before changing paths or loading config.
        std::error_code repo_error;
        const auto canonical_repo = std::filesystem::canonical(repo_path, repo_error);
        if (repo_error || !std::filesystem::is_directory(canonical_repo, repo_error) ||
            repo_error) {
            spdlog::error("Invalid repository directory '{}': {}", repo_path,
                          repo_error ? repo_error.message() : "expected a directory");
            return 2;
        }
        repo_path = canonical_repo.generic_string();
        // Full repo analysis mode.
        spdlog::info("cppulse-analyzer: analyzing repo '{}'", repo_path);

        // Load config: explicit --config, auto-discover from repo root, or none.
        std::optional<cppulse::ProjectConfig> config;
        if (!config_path.empty()) {
            config = cppulse::load_config(std::filesystem::path{config_path});
        } else {
            auto found = cppulse::find_config(std::filesystem::path{repo_path});
            if (found.has_value()) {
                config = cppulse::load_config(found.value());
            }
        }

        std::optional<std::filesystem::path> database_path;
        if (!compilation_database.empty()) {
            database_path = compilation_database;
        }
        cppulse::FileAnalyzer analyzer{std::filesystem::path{repo_path}, config, database_path,
                                       resource_path};
        analyzer.run();

        const bool ok = cppulse::write_findings_json(
            analyzer.findings(), repo_path, analyzer.file_count(), analyzer.total_loc(),
            std::filesystem::path{output_dir}, &analyzer.coverage());

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

        auto result = cppulse::extract_function_names(single_file, resource_directory);

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
