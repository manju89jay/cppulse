/**
 * @file config.cpp
 * @brief Implementation of .cppulserc.yml / .cppulserc.json config loading.
 */

#include "config.h"

#include <nlohmann/json.hpp>
#include <spdlog/spdlog.h>

#include <algorithm>
#include <fstream>
#include <regex>
#include <sstream>
#include <stdexcept>

namespace cppulse {

namespace {

// -----------------------------------------------------------------------
// Simple YAML parser for the cppulserc schema
// -----------------------------------------------------------------------

/// @brief Trim leading and trailing whitespace.
std::string trim(const std::string& s) {
    const auto start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos) return "";
    const auto end = s.find_last_not_of(" \t\r\n");
    return s.substr(start, end - start + 1);
}

/// @brief Count leading spaces (not tabs, for simplicity).
std::size_t indent_level(const std::string& line) {
    std::size_t n = 0;
    for (char ch : line) {
        if (ch == ' ') {
            ++n;
        } else {
            break;
        }
    }
    return n;
}

/// @brief Strip surrounding quotes from a YAML value.
std::string strip_quotes(const std::string& s) {
    if (s.size() >= 2) {
        if ((s.front() == '"' && s.back() == '"') ||
            (s.front() == '\'' && s.back() == '\'')) {
            return s.substr(1, s.size() - 2);
        }
    }
    return s;
}

/// @brief Parse a .cppulserc.yml file into a ProjectConfig.
ProjectConfig parse_yaml(const std::string& content) {
    ProjectConfig config;
    std::istringstream stream(content);
    std::string line;

    enum class Section { kNone, kExcludePaths, kRules };
    Section section = Section::kNone;
    std::string current_rule_id;

    while (std::getline(stream, line)) {
        // Strip comments (but not inside quotes — good enough for our schema).
        const auto comment_pos = line.find('#');
        if (comment_pos != std::string::npos) {
            line = line.substr(0, comment_pos);
        }

        const std::string trimmed = trim(line);
        if (trimmed.empty()) continue;

        const std::size_t indent = indent_level(line);

        // Top-level keys (indent == 0)
        if (indent == 0) {
            const auto colon = trimmed.find(':');
            if (colon == std::string::npos) continue;

            const std::string key = trim(trimmed.substr(0, colon));
            const std::string value = trim(trimmed.substr(colon + 1));

            if (key == "profile") {
                config.profile = strip_quotes(value);
                section = Section::kNone;
            } else if (key == "exclude_paths") {
                section = Section::kExcludePaths;
            } else if (key == "rules") {
                section = Section::kRules;
                current_rule_id.clear();
            } else {
                section = Section::kNone;
            }
            continue;
        }

        // List items under exclude_paths (indent >= 2, starts with "- ")
        if (section == Section::kExcludePaths && trimmed.size() > 2 &&
            trimmed[0] == '-') {
            config.exclude_paths.push_back(strip_quotes(trim(trimmed.substr(1))));
            continue;
        }

        // Rules section
        if (section == Section::kRules) {
            // Rule ID line (indent == 2): "CPP-CX-001:"
            if (indent == 2 || indent == 4) {
                const auto colon = trimmed.find(':');
                if (colon == std::string::npos) continue;

                const std::string key = trim(trimmed.substr(0, colon));
                const std::string value = trim(trimmed.substr(colon + 1));

                if (value.empty()) {
                    // This is a rule ID heading.
                    current_rule_id = key;
                    if (config.rules.find(current_rule_id) == config.rules.end()) {
                        config.rules[current_rule_id] = RuleConfig{};
                    }
                } else if (!current_rule_id.empty()) {
                    // Property of the current rule.
                    auto& rc = config.rules[current_rule_id];
                    if (key == "enabled") {
                        rc.enabled = (value == "true" || value == "yes" || value == "1");
                    } else if (key == "warning_threshold") {
                        rc.warning_threshold = std::stoi(value);
                    } else if (key == "error_threshold") {
                        rc.error_threshold = std::stoi(value);
                    }
                } else {
                    // This might be a rule ID with an inline value — treat as heading.
                    current_rule_id = key;
                    if (config.rules.find(current_rule_id) == config.rules.end()) {
                        config.rules[current_rule_id] = RuleConfig{};
                    }
                    // Parse inline property if value is meaningful.
                }
            } else if (indent >= 4 && !current_rule_id.empty()) {
                // Deeper indent — property of the current rule.
                const auto colon = trimmed.find(':');
                if (colon == std::string::npos) continue;

                const std::string key = trim(trimmed.substr(0, colon));
                const std::string value = trim(trimmed.substr(colon + 1));

                auto& rc = config.rules[current_rule_id];
                if (key == "enabled") {
                    rc.enabled = (value == "true" || value == "yes" || value == "1");
                } else if (key == "warning_threshold") {
                    rc.warning_threshold = std::stoi(value);
                } else if (key == "error_threshold") {
                    rc.error_threshold = std::stoi(value);
                }
            }
        }
    }

    return config;
}

/// @brief Parse a .cppulserc.json file into a ProjectConfig.
ProjectConfig parse_json(const std::string& content) {
    ProjectConfig config;
    const auto doc = nlohmann::json::parse(content);

    if (doc.contains("profile") && doc["profile"].is_string()) {
        config.profile = doc["profile"].get<std::string>();
    }

    if (doc.contains("exclude_paths") && doc["exclude_paths"].is_array()) {
        for (const auto& item : doc["exclude_paths"]) {
            if (item.is_string()) {
                config.exclude_paths.push_back(item.get<std::string>());
            }
        }
    }

    if (doc.contains("rules") && doc["rules"].is_object()) {
        for (const auto& [rule_id, props] : doc["rules"].items()) {
            RuleConfig rc;
            if (props.contains("enabled") && props["enabled"].is_boolean()) {
                rc.enabled = props["enabled"].get<bool>();
            }
            if (props.contains("warning_threshold") && props["warning_threshold"].is_number_integer()) {
                rc.warning_threshold = props["warning_threshold"].get<int>();
            }
            if (props.contains("error_threshold") && props["error_threshold"].is_number_integer()) {
                rc.error_threshold = props["error_threshold"].get<int>();
            }
            config.rules[rule_id] = rc;
        }
    }

    return config;
}

/// @brief Read the entire contents of a file into a string.
std::string read_file(const std::filesystem::path& path) {
    std::ifstream ifs(path, std::ios::binary);
    if (!ifs) {
        throw std::runtime_error("Cannot open config file: " + path.string());
    }
    std::ostringstream oss;
    oss << ifs.rdbuf();
    return oss.str();
}

// -----------------------------------------------------------------------
// Glob matching
// -----------------------------------------------------------------------

/// @brief Convert a glob pattern to a regex pattern string.
std::string glob_to_regex(const std::string& glob) {
    std::string regex;
    regex.reserve(glob.size() * 2);

    for (std::size_t i = 0; i < glob.size(); ++i) {
        const char ch = glob[i];
        if (ch == '*') {
            if (i + 1 < glob.size() && glob[i + 1] == '*') {
                // "**" matches everything including path separators.
                regex += ".*";
                ++i;  // skip second '*'
                // Skip an optional trailing '/' after "**".
                if (i + 1 < glob.size() && (glob[i + 1] == '/' || glob[i + 1] == '\\')) {
                    regex += "[/\\\\]?";
                    ++i;
                }
            } else {
                // Single "*" matches anything except path separator.
                regex += "[^/\\\\]*";
            }
        } else if (ch == '?') {
            regex += "[^/\\\\]";
        } else if (ch == '.') {
            regex += "\\.";
        } else if (ch == '/' || ch == '\\') {
            regex += "[/\\\\]";
        } else {
            regex += ch;
        }
    }

    return regex;
}

}  // namespace

ProjectConfig load_config(const std::filesystem::path& config_path) {
    spdlog::info("Loading config from: {}", config_path.string());

    const std::string content = read_file(config_path);
    const std::string ext = config_path.extension().string();

    ProjectConfig config;
    if (ext == ".json") {
        config = parse_json(content);
    } else {
        // Default to YAML parser for .yml, .yaml, or any other extension.
        config = parse_yaml(content);
    }

    spdlog::info("Config loaded: profile={}, exclude_paths={}, rule_overrides={}",
                 config.profile, config.exclude_paths.size(), config.rules.size());
    return config;
}

std::optional<std::filesystem::path> find_config(const std::filesystem::path& dir) {
    static const std::vector<std::string> kConfigNames = {
        ".cppulserc.yml",
        ".cppulserc.yaml",
        ".cppulserc.json",
    };

    for (const auto& name : kConfigNames) {
        auto candidate = dir / name;
        if (std::filesystem::exists(candidate)) {
            spdlog::debug("Found config file: {}", candidate.string());
            return candidate;
        }
    }

    return std::nullopt;
}

bool matches_exclude_pattern(
    const std::filesystem::path& relative_path,
    const std::vector<std::string>& patterns) {
    // Normalize the path to use forward slashes for matching.
    std::string path_str = relative_path.generic_string();

    for (const auto& pattern : patterns) {
        const std::string regex_str = glob_to_regex(pattern);
        try {
            const std::regex re(regex_str, std::regex::ECMAScript);
            if (std::regex_match(path_str, re)) {
                return true;
            }
        } catch (const std::regex_error&) {
            spdlog::warn("Invalid exclude pattern: {}", pattern);
        }
    }

    return false;
}

}  // namespace cppulse
