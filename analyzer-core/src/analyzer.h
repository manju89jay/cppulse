/**
 * @file analyzer.h
 * @brief FileAnalyzer orchestrates file discovery, AST traversal, and rule dispatch.
 */

#ifndef CPPULSE_ANALYZER_H
#define CPPULSE_ANALYZER_H

#include <clang-c/CXCompilationDatabase.h>

#include <filesystem>
#include <optional>
#include <string>
#include <vector>

#include "analysis_coverage.h"
#include "config.h"
#include "finding.h"

namespace cppulse {

/**
 * @brief Analyzes all C++ files under a repository root with all 22 rules.
 *
 * Usage:
 * @code
 *   FileAnalyzer analyzer("/path/to/repo");
 *   analyzer.run();
 *   const auto& findings = analyzer.findings();
 * @endcode
 */
class FileAnalyzer {
   public:
    /**
     * @brief Construct a FileAnalyzer targeting the given repository root.
     *
     * @param repo_root  Directory containing C++ source files to analyze.
     * @param config     Optional per-project configuration.
     * @param compilation_database compile_commands.json file or its directory, if explicit.
     * @param resource_directory Optional libclang builtin resource directory override.
     * @param selected_files Optional finite canonical repository-relative source selection.
     */
    explicit FileAnalyzer(
        std::filesystem::path repo_root, std::optional<ProjectConfig> config = std::nullopt,
        std::optional<std::filesystem::path> compilation_database = std::nullopt,
        std::optional<std::filesystem::path> resource_directory = std::nullopt,
        std::optional<std::vector<std::filesystem::path>> selected_files = std::nullopt);

    /**
     * @brief Discover all C++ files and apply every rule to each file.
     *
     * After this call, findings() and file_count() are populated.
     * Calling run() a second time resets and re-runs the analysis.
     */
    void run();

    /**
     * @brief Return all findings accumulated across all analyzed files.
     */
    [[nodiscard]] const std::vector<Finding>& findings() const noexcept {
        return findings_;
    }

    /**
     * @brief Return the number of source files analyzed in the last run().
     */
    [[nodiscard]] int file_count() const noexcept {
        return file_count_;
    }

    /**
     * @brief Return the total lines of code across all analyzed files.
     */
    [[nodiscard]] int total_loc() const noexcept {
        return total_loc_;
    }

    /**
     * @brief Return the repository root path this analyzer was constructed with.
     */
    [[nodiscard]] const std::filesystem::path& repo_root() const noexcept {
        return repo_root_;
    }

    /**
     * @brief Number parsed with exact or inferred database args (last run()).
     */
    [[nodiscard]] int db_parsed_count() const noexcept {
        return db_parsed_count_;
    }

    /**
     * @brief Number of files parsed with the built-in default flags (last run()).
     */
    [[nodiscard]] int fallback_parsed_count() const noexcept {
        return fallback_parsed_count_;
    }

    /** @brief Return parse outcomes and enabled rules, including analysis gaps. */
    [[nodiscard]] const AnalysisCoverage& coverage() const noexcept {
        return coverage_;
    }

   private:
    /**
     * @brief Analyze a single translation unit and collect findings.
     *
     * @param file_path  Absolute path to the C++ source file.
     */
    void analyze_file(const std::filesystem::path& file_path);

    /**
     * @brief Load compile_commands.json from the repo root (or its build/ dir).
     *
     * Sets compile_db_ to a valid handle or nullptr when no database exists.
     */
    void load_compilation_database();

    /**
     * @brief Look up the compile arguments recorded for a file.
     *
     * @param file_path  Absolute path of the translation unit.
     * @return Selected database arguments (compiler argv0, -c, -o and the source
     *         operand stripped), or empty without a usable command. libclang may
     *         interpolate unrecorded headers/files; coverage labels that inference.
     */
    [[nodiscard]] std::vector<std::string> compile_args_for(
        const std::filesystem::path& file_path) const;

    std::filesystem::path repo_root_;
    std::optional<ProjectConfig> config_;
    std::optional<std::filesystem::path> compilation_database_;
    std::vector<std::filesystem::path> recorded_files_;
    std::optional<std::filesystem::path> resource_directory_;
    std::optional<std::vector<std::filesystem::path>> selected_files_;
    AnalysisCoverage coverage_;
    std::vector<Finding> findings_;
    int file_count_{0};
    int total_loc_{0};
    CXCompilationDatabase compile_db_{nullptr};
    int db_parsed_count_{0};
    int fallback_parsed_count_{0};
};

}  // namespace cppulse

#endif  // CPPULSE_ANALYZER_H
