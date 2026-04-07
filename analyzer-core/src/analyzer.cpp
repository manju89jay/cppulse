/**
 * @file analyzer.cpp
 * @brief FileAnalyzer implementation — orchestrates rule dispatch over a repository.
 */

#include "analyzer.h"

#include <clang-c/Index.h>
#include <spdlog/spdlog.h>

#include <fstream>
#include <string>
#include <vector>

#include "config.h"
#include "file_discovery.h"
#include "rule_engine.h"

namespace cppulse {

namespace {

/// @brief Maximum file size in bytes before a file is skipped.
constexpr std::uintmax_t kMaxFileSizeBytes = 500ULL * 1024ULL;  // 500 KB

/// @brief Count the number of newlines in a file (approximate LOC).
int count_lines(const std::filesystem::path& file_path) {
    std::ifstream ifs(file_path, std::ios::binary);
    if (!ifs) {
        return 0;
    }
    int lines = 0;
    char ch = '\0';
    while (ifs.get(ch)) {
        if (ch == '\n') {
            ++lines;
        }
    }
    return lines + 1;  // Include last line if file doesn't end with newline.
}

/// @brief Check if a rule is enabled per the project config.
bool is_rule_enabled(const std::string& rule_id, const std::optional<ProjectConfig>& config) {
    if (!config.has_value()) return true;
    const auto it = config->rules.find(rule_id);
    if (it == config->rules.end()) return true;
    return it->second.enabled;
}

/// @brief Apply threshold overrides from config to a complexity rule.
template <typename Rule>
void apply_thresholds(Rule& rule, const std::optional<ProjectConfig>& config) {
    if (!config.has_value()) return;
    const std::string id{rule.rule_id()};
    const auto it = config->rules.find(id);
    if (it == config->rules.end()) return;
    if (it->second.warning_threshold.has_value()) {
        rule.set_warn_threshold(it->second.warning_threshold.value());
    }
    if (it->second.error_threshold.has_value()) {
        rule.set_error_threshold(it->second.error_threshold.value());
    }
}

/// @brief Build the set of analysis rules, applying config overrides.
std::vector<AnyRule> make_rules(const std::optional<ProjectConfig>& config) {
    std::vector<AnyRule> rules;
    rules.reserve(22);

    // Helper lambda to conditionally add a rule.
    auto add_rule = [&](auto rule) {
        const std::string id{rule.rule_id()};
        if (is_rule_enabled(id, config)) {
            rules.emplace_back(std::move(rule));
        } else {
            spdlog::info("Rule {} disabled by config", id);
        }
    };

    // Memory Safety
    add_rule(RawPointerOwnershipRule{});
    add_rule(ManualMemoryMgmtRule{});
    add_rule(UnsafeArrayAccessRule{});

    // Modernization
    add_rule(CStyleCastRule{});
    add_rule(DeprecatedHeadersRule{});
    add_rule(MissingOverrideRule{});
    add_rule(RawStringLiteralRule{});
    add_rule(AutoUsageRule{});
    add_rule(RangeForRule{});
    add_rule(NullptrUsageRule{});
    add_rule(EnumClassRule{});
    add_rule(UsingVsTypedefRule{});

    // Complexity — apply threshold overrides.
    {
        CyclomaticComplexityRule r;
        apply_thresholds(r, config);
        add_rule(std::move(r));
    }
    {
        FunctionLengthRule r;
        apply_thresholds(r, config);
        add_rule(std::move(r));
    }
    {
        ParameterCountRule r;
        apply_thresholds(r, config);
        add_rule(std::move(r));
    }

    // MISRA
    add_rule(NoGotoRule{});
    add_rule(NoImplicitConversionRule{});
    add_rule(NoUnionRule{});
    add_rule(NoDynamicAllocRule{});
    add_rule(NoRecursionRule{});
    add_rule(SingleExitRule{});
    add_rule(InitAllVarsRule{});

    return rules;
}

/**
 * @brief Visitor callback data passed to clang_visitChildren.
 */
struct VisitorData {
    std::vector<AnyRule>* rules;
    const std::string* file_path;
};

/**
 * @brief AST visitor: dispatches each cursor to all rules.
 */
CXChildVisitResult ast_visitor(CXCursor cursor, CXCursor /*parent*/, CXClientData client_data) {
    auto* data = static_cast<VisitorData*>(client_data);

    // Only process cursors in the main file.
    CXSourceLocation loc = clang_getCursorLocation(cursor);
    if (clang_Location_isInSystemHeader(loc)) {
        return CXChildVisit_Continue;  // Skip but don't recurse into sys headers.
    }

    CheckVisitor checker{cursor, *data->file_path};
    for (auto& rule : *data->rules) {
        std::visit(checker, rule);
    }

    return CXChildVisit_Recurse;
}

}  // namespace

FileAnalyzer::FileAnalyzer(std::filesystem::path repo_root, std::optional<ProjectConfig> config)
    : repo_root_(std::move(repo_root)), config_(std::move(config)) {}

void FileAnalyzer::run() {
    findings_.clear();
    file_count_ = 0;
    total_loc_ = 0;

    const std::vector<std::filesystem::path> files = discover_cpp_files(repo_root_);
    spdlog::info("FileAnalyzer: found {} file(s) under {}", files.size(), repo_root_.string());

    const auto& exclude_patterns =
        config_.has_value() ? config_->exclude_paths : std::vector<std::string>{};
    int skipped = 0;

    for (const auto& file_path : files) {
        // Apply exclude_paths from config.
        if (!exclude_patterns.empty()) {
            const auto rel = std::filesystem::relative(file_path, repo_root_);
            if (matches_exclude_pattern(rel, exclude_patterns)) {
                spdlog::debug("FileAnalyzer: excluding '{}' (matched exclude pattern)",
                              file_path.string());
                ++skipped;
                continue;
            }
        }
        analyze_file(file_path);
    }
    if (skipped > 0) {
        spdlog::info("FileAnalyzer: excluded {} file(s) by config", skipped);
    }

    spdlog::info("FileAnalyzer: analysis complete — {} file(s), {} finding(s)", file_count_,
                 findings_.size());
}

void FileAnalyzer::analyze_file(const std::filesystem::path& file_path) {
    // Skip oversized files.
    std::error_code ec;
    const std::uintmax_t file_size = std::filesystem::file_size(file_path, ec);
    if (ec || file_size > kMaxFileSizeBytes) {
        spdlog::warn("FileAnalyzer: skipping large/unreadable file: {}", file_path.string());
        return;
    }

    const std::string path_str = file_path.string();
    spdlog::debug("FileAnalyzer: analyzing '{}'", path_str);

    CXIndex index = clang_createIndex(/*excludeDeclarationsFromPCH=*/0,
                                      /*displayDiagnostics=*/0);
    if (index == nullptr) {
        spdlog::error("FileAnalyzer: clang_createIndex failed for '{}'", path_str);
        return;
    }

    // Parse with C++17 so modern features are recognized.
    const char* cmd_args[] = {"-std=c++17", "-x", "c++"};
    constexpr int kNumArgs = 3;

    CXTranslationUnit tu =
        clang_parseTranslationUnit(index, path_str.c_str(), cmd_args, kNumArgs, nullptr, 0,
                                   CXTranslationUnit_DetailedPreprocessingRecord);

    if (tu == nullptr) {
        spdlog::warn("FileAnalyzer: failed to parse '{}'", path_str);
        clang_disposeIndex(index);
        return;
    }

    // Count LOC.
    const int loc = count_lines(file_path);
    total_loc_ += loc;
    ++file_count_;

    // Build a fresh rule set for this file, applying config overrides.
    std::vector<AnyRule> rules = make_rules(config_);

    VisitorData visitor_data{&rules, &path_str};
    CXCursor root = clang_getTranslationUnitCursor(tu);
    clang_visitChildren(root, ast_visitor, &visitor_data);

    // Harvest findings from all rules.
    FindingsVisitor harvester{findings_};
    for (const auto& rule : rules) {
        std::visit(harvester, rule);
    }

    clang_disposeTranslationUnit(tu);
    clang_disposeIndex(index);
}

}  // namespace cppulse
