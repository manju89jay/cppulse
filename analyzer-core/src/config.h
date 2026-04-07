/**
 * @file config.h
 * @brief Per-project configuration (.cppulserc.yml / .cppulserc.json) support.
 */

#ifndef CPPULSE_CONFIG_H
#define CPPULSE_CONFIG_H

#include <filesystem>
#include <map>
#include <optional>
#include <string>
#include <vector>

namespace cppulse {

/**
 * @brief Per-rule configuration overrides.
 *
 * Users can disable rules or adjust numeric thresholds (e.g., cyclomatic
 * complexity warning/error thresholds) via the config file.
 */
struct RuleConfig {
    bool enabled{true};
    std::optional<int> warning_threshold;
    std::optional<int> error_threshold;
};

/**
 * @brief Project-level configuration loaded from .cppulserc.yml or .json.
 *
 * Config example (.cppulserc.yml):
 * @code
 *   profile: safety-critical
 *   exclude_paths:
 *     - "vendor/\*\*"
 *     - "third_party/\*\*"
 *   rules:
 *     CPP-CX-001:
 *       warning_threshold: 20
 *     CPP-MEM-001:
 *       enabled: false
 * @endcode
 */
struct ProjectConfig {
    /** @brief Analysis profile: "default" or "safety-critical". */
    std::string profile{"default"};

    /** @brief Glob patterns for paths to exclude from analysis. */
    std::vector<std::string> exclude_paths;

    /** @brief Per-rule overrides keyed by rule ID (e.g., "CPP-CX-001"). */
    std::map<std::string, RuleConfig> rules;
};

/**
 * @brief Load a ProjectConfig from a YAML (.yml) or JSON (.json) config file.
 *
 * Supports two formats:
 *  - YAML: simple subset parser for the cppulserc schema.
 *  - JSON: parsed with nlohmann/json.
 *
 * @param config_path  Path to the configuration file.
 * @return Loaded configuration.
 * @throws std::runtime_error if the file cannot be read or parsed.
 */
[[nodiscard]] ProjectConfig load_config(const std::filesystem::path& config_path);

/**
 * @brief Search for a config file in the given directory.
 *
 * Search order: .cppulserc.yml, .cppulserc.yaml, .cppulserc.json
 *
 * @param dir  Directory to search (typically the repository root).
 * @return Path to the found config file, or std::nullopt if none found.
 */
[[nodiscard]] std::optional<std::filesystem::path> find_config(const std::filesystem::path& dir);

/**
 * @brief Test whether a relative path matches any of the exclude glob patterns.
 *
 * Supports simple glob patterns:
 *  - '*' matches any sequence of non-separator characters.
 *  - '**' matches any sequence of characters including path separators.
 *
 * @param relative_path  Path relative to the repository root.
 * @param patterns       List of glob patterns from ProjectConfig::exclude_paths.
 * @return true if the path matches at least one pattern and should be excluded.
 */
[[nodiscard]] bool matches_exclude_pattern(const std::filesystem::path& relative_path,
                                           const std::vector<std::string>& patterns);

}  // namespace cppulse

#endif  // CPPULSE_CONFIG_H
