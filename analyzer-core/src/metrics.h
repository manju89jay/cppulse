/** @file metrics.h
 * @brief Measurements extracted from live libclang translation units.
 */
#ifndef CPPULSE_METRICS_H
#define CPPULSE_METRICS_H

#include <clang-c/Index.h>

#include <cstdint>
#include <filesystem>
#include <nlohmann/json.hpp>

#include "analysis_coverage.h"

namespace cppulse {

/** @brief Measure source bytes, lexical tokens, callable definitions and include edges.
 * @param unit Live translation unit; its main-file buffer is the measured source.
 * @param source Absolute main-file path passed to libclang.
 * @param repo_root Root for project-relative identities and include classification.
 * @param outcome Actual parse outcome; errors preserve partial observations.
 * @param max_token_records Positive per-file record retention bound.
 */
[[nodiscard]] nlohmann::json measure_native_file(CXTranslationUnit unit,
                                                 const std::filesystem::path& source,
                                                 const std::filesystem::path& repo_root,
                                                 const FileCoverage& outcome,
                                                 std::uint64_t max_token_records);

/** @brief Serialize all native observations, retaining unavailable inventory rows. */
[[nodiscard]] nlohmann::json native_metrics_document(const AnalysisCoverage& coverage);

}  // namespace cppulse
#endif
