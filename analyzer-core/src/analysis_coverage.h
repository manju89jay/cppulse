/**
 * @file analysis_coverage.h
 * @brief Records what the analyzer could actually inspect.
 */
#ifndef CPPULSE_ANALYSIS_COVERAGE_H
#define CPPULSE_ANALYSIS_COVERAGE_H

#include <string>
#include <vector>

namespace cppulse {

/** @brief Parse outcome for one discovered file, including unsuccessful attempts. */
struct FileCoverage {
    std::string path;
    std::string status{"failed"};
    std::string compile_context{"none"};
    int error_count{0};
};

/** @brief Rule execution scope; database flags may be interpolated for headers. */
struct AnalysisCoverage {
    std::vector<std::string> enabled_rules;
    std::vector<FileCoverage> files;
};

}  // namespace cppulse

#endif  // CPPULSE_ANALYSIS_COVERAGE_H
