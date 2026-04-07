#pragma once

#include <filesystem>
#include <optional>
#include <string>

namespace cppulse {

/**
 * @brief Result of running a single pipeline stage.
 */
struct PipelineResult {
    bool success{false};
    std::string error_message;
    int exit_code{0};
};

/**
 * @brief Orchestrates the full cppulse analysis pipeline.
 *
 * Each stage (analyzer, git-miner, predictor, report-generator) is launched
 * as a subprocess. Results are collected via PipelineResult.
 */
class Orchestrator {
   public:
    /**
     * @brief Construct an Orchestrator for the given repository and output directory.
     *
     * @param repo_path     Absolute or relative path to the C++ repository root.
     * @param output_dir    Directory where pipeline outputs (JSON, PDF) are written.
     * @param project_root  Root of the cppulse installation where component
     *                      directories (git-miner/, predictor/, etc.) live.
     *                      Defaults to the current working directory.
     * @param config_path   Optional path to a .cppulserc.yml/.json config file.
     * @param profile       Optional analysis profile override ("default" or "safety-critical").
     */
    explicit Orchestrator(std::filesystem::path repo_path, std::filesystem::path output_dir,
                          std::filesystem::path project_root = std::filesystem::current_path(),
                          std::optional<std::filesystem::path> config_path = std::nullopt,
                          std::string profile = "default");

    /**
     * @brief Run the cppulse-analyzer static analysis stage.
     *
     * Invokes `cppulse-analyzer --repo <repo_path> --output <output_dir>`.
     *
     * @return PipelineResult indicating success or failure with exit code.
     */
    [[nodiscard]] PipelineResult run_analyzer();

    /**
     * @brief Run the git-miner Python stage.
     *
     * Invokes `python3 -m src.main` inside the git-miner component directory.
     *
     * @return PipelineResult indicating success or failure with exit code.
     */
    [[nodiscard]] PipelineResult run_git_miner();

    /**
     * @brief Run the predictor Python stage.
     *
     * Invokes `python3 -m src.main` inside the predictor component directory.
     *
     * @return PipelineResult indicating success or failure with exit code.
     */
    [[nodiscard]] PipelineResult run_predictor();

    /**
     * @brief Run the report-generator Python stage to produce a PDF report.
     *
     * Invokes the PDFGenerator from the report-engine component.
     *
     * @return PipelineResult indicating success or failure with exit code.
     */
    [[nodiscard]] PipelineResult run_report_generator();

    /**
     * @brief Run the complete analysis pipeline in sequence.
     *
     * Executes: analyzer -> git-miner -> predictor -> report-generator.
     * Stops on the first stage failure.
     *
     * @return PipelineResult from the first failed stage, or success if all pass.
     */
    [[nodiscard]] PipelineResult run_full_pipeline();

    /**
     * @brief Run a shell command and capture its exit status.
     *
     * Exposed as public to allow unit testing of subprocess execution.
     *
     * @param command     Shell command string to execute.
     * @param stage_name  Human-readable stage name used in log messages.
     * @return PipelineResult with exit code and error message on failure.
     */
    [[nodiscard]] PipelineResult run_command(const std::string& command,
                                             const std::string& stage_name);

   private:
    std::filesystem::path repo_path_;
    std::filesystem::path output_dir_;
    std::filesystem::path project_root_;
    std::optional<std::filesystem::path> config_path_;
    std::string profile_;
};

}  // namespace cppulse
