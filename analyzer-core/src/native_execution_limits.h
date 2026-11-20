/** @file native_execution_limits.h
 * @brief Native resource guards and finite selected-source validation.
 */
#ifndef CPPULSE_NATIVE_EXECUTION_LIMITS_H
#define CPPULSE_NATIVE_EXECUTION_LIMITS_H

#include <cstdint>
#include <filesystem>
#include <nlohmann/json.hpp>
#include <optional>
#include <vector>

namespace cppulse {
/** @brief Requested per-native-process limits, applied before AST initialization. */
struct NativeExecutionLimits {
    std::optional<std::uint64_t> address_space_bytes;
    std::optional<std::uint64_t> cpu_seconds;
    std::optional<std::uint64_t> file_size_bytes;
};

/** @brief Apply qualified Linux POSIX limits or reject an unsupported request.
 * @return Observed requested/applied guard report; CPU/RSS usage is not measured here.
 */
[[nodiscard]] nlohmann::json apply_native_execution_limits(const NativeExecutionLimits& limits);

/** @brief Check nonempty canonical relative files without following source symlinks.
 * @return Absolute selected file paths in declared order.
 */
[[nodiscard]] std::vector<std::filesystem::path> validate_selected_files(
    const std::filesystem::path& source_root,
    const std::vector<std::filesystem::path>& selected_files);

/** @brief Read a bounded JSON-array file selection and reject invalid source identities.
 * @return Validated repository-relative identities in declared order.
 */
[[nodiscard]] std::vector<std::filesystem::path> read_selected_files(
    const std::filesystem::path& source_root, const std::filesystem::path& selection_file);
}  // namespace cppulse
#endif  // CPPULSE_NATIVE_EXECUTION_LIMITS_H
