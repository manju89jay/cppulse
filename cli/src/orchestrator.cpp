/**
 * @file orchestrator.cpp
 * @brief Implementation of the cppulse pipeline orchestrator.
 */

#include "orchestrator.h"

#include <spdlog/spdlog.h>

#include <array>
#include <cstdio>
#include <filesystem>
#include <string>

namespace cppulse {

namespace {

/// @brief Maximum number of bytes to read from a subprocess's stderr/stdout.
constexpr std::size_t kReadBufferSize = 256;

/**
 * @brief Execute a shell command and return its exit code plus any stderr output.
 *
 * Uses popen() so that the subprocess output can be captured for error reporting.
 *
 * @param command Shell command string.
 * @return Pair of {exit_code, captured_output}.
 */
std::pair<int, std::string> execute_shell(const std::string& command) {
    // Redirect stderr into stdout so we capture error messages.
    const std::string full_cmd = command + " 2>&1";

    // NOLINTNEXTLINE(cert-env33-c) — intentional subprocess execution
    std::FILE* pipe = popen(full_cmd.c_str(), "r");
    if (pipe == nullptr) {
        return {-1, "popen() failed to start subprocess"};
    }

    std::string output;
    std::array<char, kReadBufferSize> buffer{};
    while (std::fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) != nullptr) {
        output += buffer.data();
    }

    const int raw_status = pclose(pipe);
    // WEXITSTATUS extracts the real exit code from the wait-status integer.
    const int exit_code = WEXITSTATUS(raw_status);  // NOLINT(hicpp-signed-bitwise)
    return {exit_code, output};
}

}  // namespace

Orchestrator::Orchestrator(std::filesystem::path repo_path, std::filesystem::path output_dir)
    : repo_path_{std::move(repo_path)}, output_dir_{std::move(output_dir)} {}

PipelineResult Orchestrator::run_command(const std::string& command,
                                         const std::string& stage_name) {
    spdlog::info("[{}] running: {}", stage_name, command);

    auto [exit_code, captured_output] = execute_shell(command);

    if (exit_code != 0) {
        spdlog::error("[{}] failed with exit code {}. Output:\n{}", stage_name, exit_code,
                      captured_output);
        return PipelineResult{false, captured_output, exit_code};
    }

    spdlog::info("[{}] completed successfully", stage_name);
    return PipelineResult{true, {}, 0};
}

PipelineResult Orchestrator::run_analyzer() {
    const std::string command =
        "cppulse-analyzer --repo " + repo_path_.string() + " --output " + output_dir_.string();
    return run_command(command, "analyzer");
}

PipelineResult Orchestrator::run_git_miner() {
    // Derive the git-miner directory relative to this binary's installed location.
    // When running from the project root the component lives at ./git-miner/.
    const std::string command = "cd git-miner && python3 -m src.main --repo " +
                                repo_path_.string() + " --output " + output_dir_.string();
    return run_command(command, "git-miner");
}

PipelineResult Orchestrator::run_predictor() {
    const std::string command = "cd predictor && python3 -m src.main --input " +
                                output_dir_.string() + " --output " + output_dir_.string();
    return run_command(command, "predictor");
}

PipelineResult Orchestrator::run_report_generator() {
    const std::string input_str = output_dir_.string();
    const std::string output_pdf = (output_dir_ / "report.pdf").string();
    const std::string command =
        "python3 -c \"from src.pdf_generator import PDFGenerator; "
        "PDFGenerator('" +
        input_str + "').generate('" + output_pdf + "')\"";
    return run_command(command, "report-generator");
}

PipelineResult Orchestrator::run_full_pipeline() {
    spdlog::info("cppulse: starting full pipeline for repo '{}'", repo_path_.string());

    // Ensure output directory exists before any stage writes to it.
    std::error_code ec;
    std::filesystem::create_directories(output_dir_, ec);
    if (ec) {
        const std::string msg = "failed to create output directory: " + ec.message();
        spdlog::error("cppulse: {}", msg);
        return PipelineResult{false, msg, 1};
    }

    // --- Stage 1: static analysis ---
    if (auto result = run_analyzer(); !result.success) {
        spdlog::error("cppulse: pipeline aborted at analyzer stage");
        return result;
    }

    // --- Stage 2: git history mining ---
    if (auto result = run_git_miner(); !result.success) {
        spdlog::error("cppulse: pipeline aborted at git-miner stage");
        return result;
    }

    // --- Stage 3: ML prediction ---
    if (auto result = run_predictor(); !result.success) {
        spdlog::error("cppulse: pipeline aborted at predictor stage");
        return result;
    }

    // --- Stage 4: report generation ---
    if (auto result = run_report_generator(); !result.success) {
        spdlog::error("cppulse: pipeline aborted at report-generator stage");
        return result;
    }

    spdlog::info("cppulse: full pipeline completed successfully. Output in '{}'",
                 output_dir_.string());
    return PipelineResult{true, {}, 0};
}

}  // namespace cppulse
