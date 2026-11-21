/**
 * @file main.cpp
 * @brief Entry point for the cppulse-analyzer executable.
 */

#include <spdlog/sinks/stdout_color_sinks.h>
#include <spdlog/spdlog.h>

#include <CLI/CLI.hpp>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <optional>
#include <string>

#include "analyzer.h"
#include "config.h"
#include "hello_libclang.h"
#include "native_execution_limits.h"
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
    spdlog::set_default_logger(spdlog::stderr_color_mt("cppulse-analyzer"));
    CLI::App app{"cppulse-analyzer — C++ codebase health analyzer"};

    std::string repo_path;
    std::string output_dir = "output";
    std::string config_path;
    std::string profile;
    std::string single_file;
    std::string compilation_database;
    std::string resource_directory;
    std::string file_list;
    std::string limits_report;
    std::optional<std::uint64_t> address_space_bytes;
    std::optional<std::uint64_t> cpu_seconds;
    std::optional<std::uint64_t> file_size_bytes;

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
    const auto* profile_option =
        app.add_option("--profile", profile,
                       "Legacy scoring-profile config override: default or safety-critical; "
                       "native detector enablement is independent (use per-rule enabled settings)")
            ->check(CLI::IsMember({"default", "safety-critical"}));
    // Backward-compatible positional argument for single-file analysis.
    app.add_option("file", single_file, "C++ source file to analyze (single-file mode)")
        ->required(false);

    app.add_option("--file-list", file_list,
                   "Finite JSON array of canonical repository-relative C++ files");
    app.add_option("--address-space-bytes", address_space_bytes,
                   "Native Linux per-process address-space limit before AST work");
    app.add_option("--cpu-seconds", cpu_seconds,
                   "Native Linux per-process CPU hard limit before AST work");
    app.add_option("--execution-limits-report", limits_report,
                   "Write observed native limit capabilities as JSON");

    app.add_option("--file-size-bytes", file_size_bytes,
                   "Native Linux per-file output size hard limit");

    CLI11_PARSE(app, argc, argv);

    try {
        const auto guards = cppulse::apply_native_execution_limits(
            {address_space_bytes, cpu_seconds, file_size_bytes});
        if (!limits_report.empty()) {
            std::ofstream stream{limits_report, std::ios::binary | std::ios::trunc};
            stream << guards.dump(2) << "\n";
            stream.flush();
            if (!stream)
                throw std::runtime_error("Cannot write native execution-limits report");
        }
        if (!file_list.empty() && repo_path.empty())
            throw std::runtime_error("--file-list requires --repo");
        if (profile_option->count() > 0 && repo_path.empty())
            throw std::runtime_error("--profile requires --repo");
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
            spdlog::info("cppulse-analyzer: builtin resource directory '{}'",
                         resource_path->string());
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
            // Validate selected config first. Never filter completed findings:
            // effective rule options and the retained execution identity must agree.
            if (profile_option->count() > 0) {
                if (!config.has_value())
                    config = cppulse::ProjectConfig{};
                config->profile = profile;
                spdlog::warn(
                    "Legacy --profile '{}' sets the configuration's scoring profile; "
                    "the native component performs no scoring and does not filter detectors. "
                    "Use explicit rule enabled settings; score with the public cppulse pipeline.",
                    profile);
            }

            std::optional<std::filesystem::path> database_path;
            if (!compilation_database.empty()) {
                database_path = compilation_database;
            }
            std::optional<std::vector<std::filesystem::path>> selected_files;
            if (!file_list.empty())
                selected_files = cppulse::read_selected_files(repo_path, file_list);
            cppulse::FileAnalyzer analyzer{std::filesystem::path{repo_path}, config, database_path,
                                           resource_path, selected_files};
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
        return 2;
    } catch (const std::exception& error) {
        spdlog::error("cppulse-analyzer: {}", error.what());
        return 2;
    }
}
