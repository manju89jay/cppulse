/**
 * @file main.cpp
 * @brief Entry point for the cppulse CLI orchestrator.
 *
 * Provides three sub-commands:
 *   analyze  — run the full static-analysis + git-mining + prediction pipeline
 *   report   — generate a PDF/JSON report from existing pipeline output
 *   watch    — run the analyze pipeline repeatedly at a configurable interval
 */

#include <spdlog/spdlog.h>

#include <CLI/CLI.hpp>
#include <chrono>
#include <filesystem>
#include <optional>
#include <string>
#include <thread>
#include <vector>

#include "orchestrator.h"

int main(int argc, char* argv[]) {
    CLI::App app{"cppulse — C++ codebase health analyzer"};
    app.require_subcommand(1);

    // -----------------------------------------------------------------------
    // Sub-command: analyze
    // -----------------------------------------------------------------------
    auto* analyze_cmd = app.add_subcommand("analyze", "Run the full analysis pipeline");

    std::string analyze_repo;
    std::string analyze_output = "./output";
    std::string analyze_config;
    std::string analyze_profile = "default";

    analyze_cmd->add_option("--repo", analyze_repo, "Path to the C++ repository root")->required();
    analyze_cmd->add_option("--output", analyze_output, "Output directory for pipeline artifacts")
        ->default_val("./output");
    analyze_cmd->add_option(
        "--config", analyze_config,
        "Path to .cppulserc.yml/.json (auto-discovered from repo root if omitted)");
    analyze_cmd
        ->add_option("--profile", analyze_profile, "Analysis profile: default or safety-critical")
        ->default_val("default")
        ->check(CLI::IsMember({"default", "safety-critical"}));

    analyze_cmd->callback([&]() {
        const std::filesystem::path repo{analyze_repo};
        const std::filesystem::path output{analyze_output};

        if (!std::filesystem::exists(repo)) {
            spdlog::error("analyze: repo path does not exist: {}", repo.string());
            std::exit(1);
        }
        if (!std::filesystem::is_directory(repo)) {
            spdlog::error("analyze: repo path is not a directory: {}", repo.string());
            std::exit(1);
        }

        std::error_code ec;
        std::filesystem::create_directories(output, ec);
        if (ec) {
            spdlog::error("analyze: cannot create output directory '{}': {}", output.string(),
                          ec.message());
            std::exit(1);
        }

        // Discover or use explicit config file.
        std::optional<std::filesystem::path> config_path;
        std::string profile = analyze_profile;
        if (!analyze_config.empty()) {
            config_path = std::filesystem::path{analyze_config};
        } else {
            // Auto-discover .cppulserc.yml in repo root.
            static const std::vector<std::string> kConfigNames = {
                ".cppulserc.yml", ".cppulserc.yaml", ".cppulserc.json"};
            for (const auto& name : kConfigNames) {
                auto candidate = repo / name;
                if (std::filesystem::exists(candidate)) {
                    config_path = candidate;
                    spdlog::info("analyze: found config file: {}", candidate.string());
                    break;
                }
            }
        }

        cppulse::Orchestrator orch{repo, output, std::filesystem::current_path(), config_path,
                                   profile};
        const auto result = orch.run_full_pipeline();

        if (!result.success) {
            spdlog::error("analyze: pipeline failed (exit {}): {}", result.exit_code,
                          result.error_message);
            std::exit(result.exit_code != 0 ? result.exit_code : 1);
        }
    });

    // -----------------------------------------------------------------------
    // Sub-command: report
    // -----------------------------------------------------------------------
    auto* report_cmd = app.add_subcommand("report", "Generate a report from pipeline output");

    std::string report_input = "./output";
    std::string report_format = "pdf";

    report_cmd->add_option("--input", report_input, "Directory containing pipeline output files")
        ->default_val("./output");
    report_cmd->add_option("--format", report_format, "Report format: pdf or json")
        ->default_val("pdf")
        ->check(CLI::IsMember({"pdf", "json"}));

    report_cmd->callback([&]() {
        const std::filesystem::path input{report_input};

        if (!std::filesystem::exists(input)) {
            spdlog::error("report: input directory does not exist: {}", input.string());
            std::exit(1);
        }

        // Use a temporary Orchestrator with an empty repo path — only
        // run_report_generator() is needed here.
        cppulse::Orchestrator orch{std::filesystem::path{}, input};
        const auto result = orch.run_report_generator();

        if (!result.success) {
            spdlog::error("report: generation failed (exit {}): {}", result.exit_code,
                          result.error_message);
            std::exit(result.exit_code != 0 ? result.exit_code : 1);
        }
    });

    // -----------------------------------------------------------------------
    // Sub-command: watch
    // -----------------------------------------------------------------------
    auto* watch_cmd =
        app.add_subcommand("watch", "Continuously analyze a repo at a fixed interval");

    std::string watch_repo;
    std::string watch_output = "./output";
    std::string watch_config;
    std::string watch_profile = "default";
    int watch_interval = 300;

    watch_cmd->add_option("--repo", watch_repo, "Path to the C++ repository root")->required();
    watch_cmd->add_option("--output", watch_output, "Output directory for pipeline artifacts")
        ->default_val("./output");
    watch_cmd->add_option(
        "--config", watch_config,
        "Path to .cppulserc.yml/.json (auto-discovered from repo root if omitted)");
    watch_cmd
        ->add_option("--profile", watch_profile, "Analysis profile: default or safety-critical")
        ->default_val("default")
        ->check(CLI::IsMember({"default", "safety-critical"}));
    watch_cmd
        ->add_option("--interval", watch_interval, "Seconds between analysis runs (default 300)")
        ->default_val(300);

    watch_cmd->callback([&]() {
        const std::filesystem::path repo{watch_repo};
        const std::filesystem::path output{watch_output};

        if (!std::filesystem::exists(repo)) {
            spdlog::error("watch: repo path does not exist: {}", repo.string());
            std::exit(1);
        }
        if (!std::filesystem::is_directory(repo)) {
            spdlog::error("watch: repo path is not a directory: {}", repo.string());
            std::exit(1);
        }

        // Discover config.
        std::optional<std::filesystem::path> config_path;
        if (!watch_config.empty()) {
            config_path = std::filesystem::path{watch_config};
        } else {
            static const std::vector<std::string> kConfigNames = {
                ".cppulserc.yml", ".cppulserc.yaml", ".cppulserc.json"};
            for (const auto& name : kConfigNames) {
                auto candidate = repo / name;
                if (std::filesystem::exists(candidate)) {
                    config_path = candidate;
                    break;
                }
            }
        }

        spdlog::info("watch: starting continuous analysis of '{}' every {}s", repo.string(),
                     watch_interval);

        while (true) {
            cppulse::Orchestrator orch{repo, output, std::filesystem::current_path(), config_path,
                                       watch_profile};
            const auto result = orch.run_full_pipeline();

            if (!result.success) {
                spdlog::warn("watch: pipeline run failed (exit {}), will retry in {}s",
                             result.exit_code, watch_interval);
            }

            spdlog::info("watch: sleeping {}s before next run", watch_interval);
            std::this_thread::sleep_for(std::chrono::seconds(watch_interval));
        }
    });

    CLI11_PARSE(app, argc, argv);
    return 0;
}
