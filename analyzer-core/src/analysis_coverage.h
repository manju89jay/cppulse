/**
 * @file analysis_coverage.h
 * @brief Records what the analyzer could actually inspect.
 */
#ifndef CPPULSE_ANALYSIS_COVERAGE_H
#define CPPULSE_ANALYSIS_COVERAGE_H

#include <cstdint>
#include <nlohmann/json.hpp>
#include <optional>
#include <string>
#include <vector>

namespace cppulse {

/** @brief Parse outcome for one discovered file, including unsuccessful attempts. */
struct FileCoverage {
    std::string path;
    std::string status{"failed"};
    std::string compile_context{"none"};
    int error_count{0};
    /** @brief Ordered strings actually passed to the parser; absent before any parse attempt. */
    std::optional<std::vector<std::string>> parse_arguments{std::nullopt};
    /** @brief Actual process cwd at the call, retaining working-directory overrides in argv. */
    std::optional<std::string> working_directory{std::nullopt};
    /** @brief Machine-readable explanation of an exclusion or incomplete attempt. */
    std::optional<std::string> reason{std::nullopt};
    /** @brief Observations extracted while this file's translation unit was alive. */
    std::optional<nlohmann::json> metrics{std::nullopt};
};

/** @brief Rule execution scope; database flags may be interpolated for headers. */
struct AnalysisCoverage {
    std::vector<std::string> enabled_rules;
    std::vector<FileCoverage> files;
    /** @brief Actual parser version returned by clang_getClangVersion, not a build compiler. */
    std::string parser_version;
    /** @brief Effective per-file token retention bound, including unattempted files. */
    std::uint64_t max_token_records{100000};
};

}  // namespace cppulse

#endif  // CPPULSE_ANALYSIS_COVERAGE_H
