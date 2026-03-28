/**
 * @file analyzer.h
 * @brief FileAnalyzer orchestrates file discovery, AST traversal, and rule dispatch.
 */

#ifndef CPPULSE_ANALYZER_H
#define CPPULSE_ANALYZER_H

#include <filesystem>
#include <string>
#include <vector>

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
     */
    explicit FileAnalyzer(std::filesystem::path repo_root);

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

   private:
    /**
     * @brief Analyze a single translation unit and collect findings.
     *
     * @param file_path  Absolute path to the C++ source file.
     */
    void analyze_file(const std::filesystem::path& file_path);

    std::filesystem::path repo_root_;
    std::vector<Finding> findings_;
    int file_count_{0};
    int total_loc_{0};
};

}  // namespace cppulse

#endif  // CPPULSE_ANALYZER_H
