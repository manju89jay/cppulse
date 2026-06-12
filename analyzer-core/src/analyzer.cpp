/**
 * @file analyzer.cpp
 * @brief FileAnalyzer implementation — orchestrates rule dispatch over a repository.
 */

#include "analyzer.h"

#include <clang-c/CXCompilationDatabase.h>
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

/// @brief Convert a CXString to std::string and dispose the original.
std::string to_string_and_dispose(CXString cx_str) {
    const char* c_str = clang_getCString(cx_str);
    std::string result = (c_str != nullptr) ? c_str : "";
    clang_disposeString(cx_str);
    return result;
}

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
    if (!config.has_value())
        return true;
    const auto it = config->rules.find(rule_id);
    if (it == config->rules.end())
        return true;
    return it->second.enabled;
}

/// @brief Apply threshold overrides from config to a complexity rule.
template <typename Rule>
void apply_thresholds(Rule& rule, const std::optional<ProjectConfig>& config) {
    if (!config.has_value())
        return;
    const std::string id{rule.rule_id()};
    const auto it = config->rules.find(id);
    if (it == config->rules.end())
        return;
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

void FileAnalyzer::load_compilation_database() {
    compile_db_ = nullptr;

    for (const auto& candidate : {repo_root_, repo_root_ / "build"}) {
        std::error_code ec;
        if (!std::filesystem::exists(candidate / "compile_commands.json", ec) || ec) {
            continue;
        }
        CXCompilationDatabase_Error db_error = CXCompilationDatabase_NoError;
        CXCompilationDatabase db =
            clang_CompilationDatabase_fromDirectory(candidate.string().c_str(), &db_error);
        if (db_error == CXCompilationDatabase_NoError && db != nullptr) {
            spdlog::info("FileAnalyzer: using compilation database from '{}'", candidate.string());
            compile_db_ = db;
            return;
        }
        if (db != nullptr) {
            clang_CompilationDatabase_dispose(db);
        }
        spdlog::warn("FileAnalyzer: failed to load compilation database from '{}'",
                     candidate.string());
    }
    spdlog::info(
        "FileAnalyzer: no compilation database found — parsing with default flags "
        "(type-dependent rules may degrade; generate compile_commands.json for best results)");
}

std::vector<std::string> FileAnalyzer::compile_args_for(
    const std::filesystem::path& file_path) const {
    if (compile_db_ == nullptr) {
        return {};
    }

    // Look up with the native spelling first, then the generic (forward-slash)
    // spelling — generators differ in which form they record on Windows.
    CXCompileCommands commands =
        clang_CompilationDatabase_getCompileCommands(compile_db_, file_path.string().c_str());
    if (clang_CompileCommands_getSize(commands) == 0) {
        clang_CompileCommands_dispose(commands);
        commands = clang_CompilationDatabase_getCompileCommands(compile_db_,
                                                                file_path.generic_string().c_str());
    }

    // Note: libclang wraps JSON databases in InterpolatingCompilationDatabase,
    // so files absent from the database (headers, new files) receive arguments
    // interpolated from the closest recorded entry rather than no arguments.
    std::vector<std::string> args;
    if (clang_CompileCommands_getSize(commands) > 0) {
        CXCompileCommand command = clang_CompileCommands_getCommand(commands, 0);
        const std::string file_name = file_path.filename().string();
        const unsigned num_args = clang_CompileCommand_getNumArgs(command);

        // Skip argv[0] (the compiler executable). Strip -c, -o <out>, and the
        // source file itself: clang_parseTranslationUnit receives the file
        // separately and chokes on output/source positional arguments.
        for (unsigned i = 1; i < num_args; ++i) {
            std::string arg = to_string_and_dispose(clang_CompileCommand_getArg(command, i));
            if (arg == "-c") {
                continue;
            }
            if (arg == "-o") {
                ++i;  // Also skip the output path that follows.
                continue;
            }
            const bool is_source_arg =
                arg == file_path.string() || arg == file_path.generic_string() ||
                (!arg.empty() && arg.front() != '-' &&
                 std::filesystem::path(arg).filename().string() == file_name);
            if (is_source_arg) {
                continue;
            }
            args.push_back(std::move(arg));
        }
    }
    clang_CompileCommands_dispose(commands);
    return args;
}

void FileAnalyzer::run() {
    findings_.clear();
    file_count_ = 0;
    total_loc_ = 0;
    db_parsed_count_ = 0;
    fallback_parsed_count_ = 0;

    load_compilation_database();

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

    if (compile_db_ != nullptr) {
        clang_CompilationDatabase_dispose(compile_db_);
        compile_db_ = nullptr;
        spdlog::info(
            "FileAnalyzer: parsed {} file(s) with compilation database args, {} with "
            "default flags",
            db_parsed_count_, fallback_parsed_count_);
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

    // Prefer the project's recorded compile arguments (include paths, defines,
    // language standard); fall back to bare C++17 flags when the file is not
    // covered by a compilation database.
    const std::vector<std::string> db_args = compile_args_for(file_path);
    std::vector<const char*> cmd_args;
    if (db_args.empty()) {
        cmd_args = {"-std=c++17", "-x", "c++"};
    } else {
        cmd_args.reserve(db_args.size());
        for (const auto& arg : db_args) {
            cmd_args.push_back(arg.c_str());
        }
        spdlog::debug("FileAnalyzer: '{}' parsed with {} compilation database arg(s)", path_str,
                      cmd_args.size());
    }

    CXTranslationUnit tu = clang_parseTranslationUnit(
        index, path_str.c_str(), cmd_args.data(), static_cast<int>(cmd_args.size()), nullptr, 0,
        CXTranslationUnit_DetailedPreprocessingRecord);

    if (tu == nullptr) {
        spdlog::warn("FileAnalyzer: failed to parse '{}'", path_str);
        clang_disposeIndex(index);
        return;
    }

    if (db_args.empty()) {
        ++fallback_parsed_count_;
    } else {
        ++db_parsed_count_;
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
