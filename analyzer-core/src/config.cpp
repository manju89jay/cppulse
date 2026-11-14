/**
 * @file config.cpp
 * @brief Implementation of .cppulserc.yml / .cppulserc.json config loading.
 */

#include "config.h"

#include <spdlog/spdlog.h>

#include <algorithm>
#include <cctype>
#include <fstream>
#include <limits>
#include <nlohmann/json.hpp>
#include <regex>
#include <set>
#include <sstream>
#include <stdexcept>

#include "rule_engine.h"

namespace cppulse {

namespace {

// -----------------------------------------------------------------------
// Simple YAML parser for the cppulserc schema
// -----------------------------------------------------------------------

/// @brief Trim leading and trailing whitespace.
std::string trim(const std::string& s) {
    const auto start = s.find_first_not_of(" \t\r\n");
    if (start == std::string::npos)
        return "";
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

/// @brief Reject unsupported settings instead of turning them into defaults.
void require_keys(const nlohmann::json& value, const std::set<std::string>& allowed,
                  const std::string& scope) {
    if (!value.is_object()) {
        throw std::runtime_error(scope + " must be an object");
    }
    for (const auto& [key, ignored] : value.items()) {
        static_cast<void>(ignored);
        if (allowed.count(key) == 0) {
            throw std::runtime_error("Unknown " + scope + " key: " + key);
        }
    }
}

/// @brief Obtain known IDs from the compiled rule variant, without another ID list.
template <std::size_t Index = 0>
bool known_rule(const std::string& id) {
    if constexpr (Index < std::variant_size_v<AnyRule>) {
        const std::variant_alternative_t<Index, AnyRule> rule;
        return rule.rule_id() == id || known_rule<Index + 1>(id);
    }
    return false;
}

/// @brief Validate the common JSON/simple-YAML representation and build settings.
ProjectConfig parse_settings(const nlohmann::json& doc) {
    require_keys(doc, {"profile", "exclude_paths", "rules", "max_file_bytes", "max_token_records"},
                 "configuration");
    ProjectConfig config;
    if (doc.contains("profile")) {
        if (!doc["profile"].is_string() ||
            (doc["profile"] != "default" && doc["profile"] != "safety-critical")) {
            throw std::runtime_error("profile must be 'default' or 'safety-critical'");
        }
        config.profile = doc["profile"].get<std::string>();
    }
    if (doc.contains("max_file_bytes")) {
        const auto& limit = doc["max_file_bytes"];
        if (!limit.is_number_integer() || limit < 1 ||
            limit > std::numeric_limits<std::int64_t>::max()) {
            throw std::runtime_error(
                "max_file_bytes must be an integer from 1 to 9223372036854775807");
        }
        config.max_file_bytes = limit.get<std::uintmax_t>();
    }
    if (doc.contains("max_token_records")) {
        const auto& limit = doc["max_token_records"];
        if (!limit.is_number_integer() || limit < 1 ||
            limit > std::numeric_limits<std::int64_t>::max()) {
            throw std::runtime_error(
                "max_token_records must be an integer from 1 to 9223372036854775807");
        }
        config.max_token_records = limit.get<std::uint64_t>();
    }
    if (doc.contains("exclude_paths")) {
        if (!doc["exclude_paths"].is_array()) {
            throw std::runtime_error("exclude_paths must be an array of nonempty unique strings");
        }
        std::set<std::string> paths;
        for (const auto& item : doc["exclude_paths"]) {
            if (!item.is_string() || item.get<std::string>().empty() ||
                !paths.insert(item.get<std::string>()).second) {
                throw std::runtime_error("exclude_paths must contain nonempty unique strings");
            }
            config.exclude_paths.push_back(item.get<std::string>());
        }
    }
    if (doc.contains("rules")) {
        if (!doc["rules"].is_object()) {
            throw std::runtime_error("rules must be an object keyed by known rule IDs");
        }
        for (const auto& [id, props] : doc["rules"].items()) {
            if (!known_rule(id)) {
                throw std::runtime_error("Unknown rule ID: " + id);
            }
            require_keys(props, {"enabled", "warning_threshold", "error_threshold"}, "rule " + id);
            RuleConfig rule;
            if (props.contains("enabled")) {
                if (!props["enabled"].is_boolean()) {
                    throw std::runtime_error(id + ".enabled must be a boolean");
                }
                rule.enabled = props["enabled"].get<bool>();
            }
            for (const auto* key : {"warning_threshold", "error_threshold"}) {
                if (!props.contains(key)) {
                    continue;
                }
                const auto& threshold = props[key];
                if (!threshold.is_number_integer() || threshold < 0 ||
                    threshold > std::numeric_limits<int>::max()) {
                    throw std::runtime_error(id + "." + key +
                                             " must be an integer from 0 to 2147483647");
                }
                if (std::string_view{key} == "warning_threshold") {
                    rule.warning_threshold = threshold.get<int>();
                } else {
                    rule.error_threshold = threshold.get<int>();
                }
            }
            config.rules.emplace(id, rule);
        }
    }
    return config;
}

/// @brief Parse JSON while rejecting duplicate keys at every object depth.
ProjectConfig parse_json(const std::string& content) {
    std::vector<std::set<std::string>> object_keys;
    const auto callback = [&object_keys](int, nlohmann::json::parse_event_t event,
                                         nlohmann::json& parsed) {
        if (event == nlohmann::json::parse_event_t::object_start) {
            object_keys.emplace_back();
        } else if (event == nlohmann::json::parse_event_t::object_end) {
            object_keys.pop_back();
        } else if (event == nlohmann::json::parse_event_t::key &&
                   !object_keys.back().insert(parsed.get<std::string>()).second) {
            throw std::runtime_error("Duplicate JSON key: " + parsed.get<std::string>());
        }
        return true;
    };
    return parse_settings(nlohmann::json::parse(content, callback));
}

/// @brief Keep hashes inside quoted values instead of truncating paths.
std::string yaml_without_comment(const std::string& line) {
    char quote = '\0';
    bool escaped = false;
    bool scalar_start = true;
    for (std::size_t index = 0; index < line.size(); ++index) {
        const char value = line[index];
        if (quote == '"' && escaped) {
            escaped = false;
            continue;
        }
        if (quote == '"' && value == '\\') {
            escaped = true;
            continue;
        }
        if (quote != '\0') {
            if (value == quote) {
                if (quote == '\'' && index + 1 < line.size() && line[index + 1] == '\'') {
                    ++index;
                } else {
                    quote = '\0';
                }
            }
        } else if ((value == '"' || value == '\'') && scalar_start) {
            quote = value;
            scalar_start = false;
        } else if (value == '#' &&
                   (index == 0 || std::isspace(static_cast<unsigned char>(line[index - 1])))) {
            return line.substr(0, index);
        } else if (value == ':' && (index + 1 == line.size() ||
                                    std::isspace(static_cast<unsigned char>(line[index + 1])))) {
            scalar_start = true;
        } else if (value == '-' && scalar_start && index + 1 < line.size() &&
                   std::isspace(static_cast<unsigned char>(line[index + 1]))) {
            // A block-list marker starts a scalar; an apostrophe later in an
            // unquoted path is ordinary content rather than a quote delimiter.
            continue;
        } else if (!std::isspace(static_cast<unsigned char>(value))) {
            scalar_start = false;
        }
    }
    if (quote != '\0') {
        throw std::runtime_error("Unterminated quoted YAML scalar");
    }
    return line;
}

/// @brief Parse the explicitly supported scalar subset, rejecting YAML execution-like tags.
nlohmann::json yaml_scalar(const std::string& value) {
    if (value.empty()) {
        throw std::runtime_error("Expected a YAML scalar value");
    }
    if (value.front() == '"') {
        auto parsed = nlohmann::json::parse(value);
        if (!parsed.is_string()) {
            throw std::runtime_error("Expected a quoted YAML string");
        }
        return parsed;
    }
    if (value.front() == '\'') {
        if (value.size() < 2 || value.back() != '\'') {
            throw std::runtime_error("Unterminated quoted YAML string");
        }
        std::string result;
        for (std::size_t index = 1; index + 1 < value.size(); ++index) {
            if (value[index] == '\'') {
                if (index + 2 >= value.size() || value[index + 1] != '\'') {
                    throw std::runtime_error("Unsupported trailing YAML scalar content");
                }
                ++index;
            }
            result += value[index];
        }
        return result;
    }
    if (value == "[]") {
        return nlohmann::json::array();
    }
    if (value == "{}") {
        return nlohmann::json::object();
    }
    if (std::string{"&*!|>{[}"}.find(value.front()) != std::string::npos ||
        value.find(": ") != std::string::npos) {
        throw std::runtime_error(
            "Unsupported YAML syntax; use ordinary block mappings/lists or JSON");
    }
    std::string lower = value;
    std::transform(lower.begin(), lower.end(), lower.begin(),
                   [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
    if (lower == "true" || lower == "yes" || lower == "on") {
        return true;
    }
    if (lower == "false" || lower == "no" || lower == "off") {
        return false;
    }
    if (lower == "null" || value == "~") {
        return nullptr;
    }
    const auto first_digit = value.front() == '-' ? 1u : 0u;
    if (first_digit < value.size() && std::all_of(
                                          value.begin() + first_digit, value.end(),
                                          [](unsigned char ch) { return std::isdigit(ch); })) {
        return nlohmann::json::parse(value);
    }
    return value;
}

/// @brief Split block mapping keys; these keys never contain colon separators.
std::pair<std::string, std::string> yaml_mapping(const std::string& line) {
    const auto colon = line.find(':');
    if (colon == std::string::npos) {
        throw std::runtime_error("Expected a YAML mapping entry");
    }
    const auto key_value = yaml_scalar(trim(line.substr(0, colon)));
    if (!key_value.is_string() || key_value.get<std::string>().empty()) {
        throw std::runtime_error("YAML mapping keys must be nonempty strings");
    }
    return {key_value.get<std::string>(), trim(line.substr(colon + 1))};
}

/// @brief Parse documented block YAML through the same strict representation as JSON.
ProjectConfig parse_yaml(const std::string& content) {
    auto doc = nlohmann::json::object();
    std::istringstream stream(content);
    std::string line;
    std::string section;
    std::string current_rule;
    std::size_t section_indent = 0;
    std::size_t property_indent = 0;
    bool document_seen = false;
    bool document_ended = false;
    while (std::getline(stream, line)) {
        line = yaml_without_comment(line);
        const auto trimmed = trim(line);
        if (trimmed.empty()) {
            continue;
        }
        if (line.find('\t') != std::string::npos || document_ended) {
            throw std::runtime_error("Unsupported YAML indentation or additional document");
        }
        if (trimmed == "---") {
            if (document_seen || !doc.empty()) {
                throw std::runtime_error("Only one YAML document is supported");
            }
            document_seen = true;
            continue;
        }
        if (trimmed == "...") {
            document_ended = true;
            continue;
        }
        const auto indent = indent_level(line);
        if (indent == 0) {
            const auto [key, value] = yaml_mapping(trimmed);
            if (doc.contains(key)) {
                throw std::runtime_error("Duplicate YAML key: " + key);
            }
            section.clear();
            current_rule.clear();
            section_indent = 0;
            property_indent = 0;
            if (value.empty()) {
                if (key == "exclude_paths") {
                    doc[key] = nlohmann::json::array();
                } else if (key == "rules") {
                    doc[key] = nlohmann::json::object();
                } else {
                    throw std::runtime_error("Unsupported empty YAML mapping: " + key);
                }
                section = key;
            } else {
                doc[key] = yaml_scalar(value);
            }
            continue;
        }
        if (section.empty()) {
            throw std::runtime_error("Unexpected indented YAML content");
        }
        if (section_indent == 0) {
            section_indent = indent;
        }
        if (section == "exclude_paths") {
            if (indent != section_indent || trimmed.size() < 3 || trimmed.substr(0, 2) != "- ") {
                throw std::runtime_error("exclude_paths requires one scalar per block list item");
            }
            doc[section].push_back(yaml_scalar(trim(trimmed.substr(2))));
        } else if (indent == section_indent) {
            const auto [key, value] = yaml_mapping(trimmed);
            if (doc[section].contains(key) || (!value.empty() && value != "{}")) {
                throw std::runtime_error("Duplicate or unsupported YAML rule mapping: " + key);
            }
            current_rule = key;
            property_indent = 0;
            doc[section][key] = nlohmann::json::object();
        } else if (indent > section_indent && !current_rule.empty()) {
            if (property_indent != 0 && indent != property_indent) {
                throw std::runtime_error("Inconsistent YAML rule-property indentation");
            }
            property_indent = indent;
            const auto [key, value] = yaml_mapping(trimmed);
            if (doc[section][current_rule].contains(key)) {
                throw std::runtime_error("Duplicate YAML rule property: " + key);
            }
            doc[section][current_rule][key] = yaml_scalar(value);
        } else {
            throw std::runtime_error("Unsupported YAML nesting");
        }
    }
    return parse_settings(doc);
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

    try {
        const std::string content = read_file(config_path);
        const std::string ext = config_path.extension().string();
        ProjectConfig config;
        if (ext == ".json") {
            config = parse_json(content);
        } else if (ext == ".yml" || ext == ".yaml") {
            config = parse_yaml(content);
        } else {
            throw std::runtime_error(
                "Unsupported configuration extension; use .json, .yml or .yaml");
        }
        spdlog::info(
            "Config loaded: profile={}, exclude_paths={}, rule_overrides={}, max_file_bytes={}",
            config.profile, config.exclude_paths.size(), config.rules.size(),
            config.max_file_bytes);
        return config;
    } catch (const std::exception& error) {
        throw std::runtime_error("Invalid project configuration '" + config_path.string() +
                                 "': " + error.what());
    }
}

std::optional<std::filesystem::path> find_config(const std::filesystem::path& dir) {
    static const std::vector<std::string> kConfigNames = {
        ".cppulserc.yml",
        ".cppulserc.yaml",
        ".cppulserc.json",
    };

    std::optional<std::filesystem::path> found;
    for (const auto& name : kConfigNames) {
        auto candidate = dir / name;
        if (std::filesystem::exists(candidate)) {
            if (found.has_value()) {
                throw std::runtime_error("Ambiguous configuration discovery: '" + found->string() +
                                         "' and '" + candidate.string() +
                                         "'; select one explicitly with --config");
            }
            spdlog::debug("Found config file: {}", candidate.string());
            found = candidate;
        }
    }
    return found;
}

bool matches_exclude_pattern(const std::filesystem::path& relative_path,
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
