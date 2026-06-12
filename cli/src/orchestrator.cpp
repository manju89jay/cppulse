/**
 * @file orchestrator.cpp
 * @brief Implementation of the cppulse pipeline orchestrator.
 */

#include "orchestrator.h"

#include <spdlog/spdlog.h>

#include <array>
#include <cstdio>
#include <filesystem>
#include <future>
#include <string>

// Platform-specific subprocess API.
#ifdef _WIN32
#define cppulse_popen _popen
#define cppulse_pclose _pclose
#else
#include <sys/wait.h>
#define cppulse_popen popen
#define cppulse_pclose pclose
#endif

namespace cppulse {

namespace {

/// @brief Maximum number of bytes to read from a subprocess's stderr/stdout.
constexpr std::size_t kReadBufferSize = 256;

/// @brief Python interpreter command: Windows installs expose "python",
/// POSIX distributions expose "python3".
#ifdef _WIN32
constexpr const char* kPythonCommand = "python";
#else
constexpr const char* kPythonCommand = "python3";
#endif

/**
 * @brief Shell-quote a filesystem path to prevent shell injection.
 *
 * On POSIX: wraps in single quotes, escapes embedded single quotes with '\''.
 * On Windows: wraps in double quotes, escapes embedded double quotes with \".
 *
 * @param path Filesystem path to quote.
 * @return Shell-safe quoted string.
 */
std::string shell_quote(const std::filesystem::path& path) {
    std::string raw = path.string();
#ifdef _WIN32
    std::string result = "\"";
    for (char ch : raw) {
        if (ch == '"') {
            result += "\\\"";
        } else {
            result += ch;
        }
    }
    result += "\"";
#else
    std::string result = "'";
    for (char ch : raw) {
        if (ch == '\'') {
            result += "'\\''";
        } else {
            result += ch;
        }
    }
    result += "'";
#endif
    return result;
}

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
    std::FILE* pipe = cppulse_popen(full_cmd.c_str(), "r");
    if (pipe == nullptr) {
        return {-1, "popen() failed to start subprocess"};
    }

    std::string output;
    std::array<char, kReadBufferSize> buffer{};
    while (std::fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) != nullptr) {
        output += buffer.data();
    }

    const int raw_status = cppulse_pclose(pipe);
#ifdef _WIN32
    // On Windows, _pclose() returns the exit code directly.
    const int exit_code = raw_status;
#else
    // On POSIX, pclose() returns a wait-status that must be decoded.
    const int exit_code = WEXITSTATUS(raw_status);  // NOLINT(hicpp-signed-bitwise)
#endif
    return {exit_code, output};
}

}  // namespace

Orchestrator::Orchestrator(std::filesystem::path repo_path, std::filesystem::path output_dir,
                           std::filesystem::path project_root,
                           std::optional<std::filesystem::path> config_path, std::string profile)
    : repo_path_{std::move(repo_path)},
      output_dir_{std::move(output_dir)},
      project_root_{std::move(project_root)},
      config_path_{std::move(config_path)},
      profile_{std::move(profile)} {}

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
    std::string command = "cppulse-analyzer --repo " + shell_quote(repo_path_) + " --output " +
                          shell_quote(output_dir_);
    if (config_path_.has_value()) {
        command += " --config " + shell_quote(config_path_.value());
    }
    return run_command(command, "analyzer");
}

PipelineResult Orchestrator::run_git_miner() {
    const auto component_dir = shell_quote(project_root_ / "git-miner");
    const std::string command = "cd " + component_dir + " && " + kPythonCommand +
                                " -m src.main --repo " + shell_quote(repo_path_) + " --output " +
                                shell_quote(output_dir_);
    return run_command(command, "git-miner");
}

PipelineResult Orchestrator::run_predictor() {
    const auto component_dir = shell_quote(project_root_ / "predictor");
    std::string command = "cd " + component_dir + " && " + kPythonCommand +
                          " -m src.main --input " + shell_quote(output_dir_) + " --output " +
                          shell_quote(output_dir_);
    if (profile_ != "default") {
        command += " --profile " + shell_quote(std::filesystem::path{profile_});
    }
    return run_command(command, "predictor");
}

PipelineResult Orchestrator::run_report_generator() {
    const auto component_dir = shell_quote(project_root_ / "report-engine");
    const std::string quoted_input = shell_quote(output_dir_);
    const std::string quoted_pdf = shell_quote(output_dir_ / "report.pdf");
    // Invoke the module's CLI entry point instead of inline "python -c" code:
    // nesting quoted paths inside a -c string breaks on Windows (cmd.exe strips
    // the inner double quotes) and couples the CLI to PDFGenerator's API.
    const std::string command = "cd " + component_dir + " && " + kPythonCommand +
                                " -m src.pdf_generator --data " + quoted_input + " --output " +
                                quoted_pdf;
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

    // --- Stages 1 & 2: run analyzer and git-miner in parallel ---
    auto analyzer_future = std::async(std::launch::async, [this] { return run_analyzer(); });
    auto git_miner_future = std::async(std::launch::async, [this] { return run_git_miner(); });

    auto analyzer_result = analyzer_future.get();
    if (!analyzer_result.success) {
        spdlog::error("cppulse: pipeline aborted at analyzer stage");
        // Still wait for git-miner to finish before returning.
        git_miner_future.get();
        return analyzer_result;
    }

    auto git_miner_result = git_miner_future.get();
    if (!git_miner_result.success) {
        spdlog::error("cppulse: pipeline aborted at git-miner stage");
        return git_miner_result;
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
