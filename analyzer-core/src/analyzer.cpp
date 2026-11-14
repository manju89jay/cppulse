/**
 * @file analyzer.cpp
 * @brief FileAnalyzer implementation — orchestrates rule dispatch over a repository.
 */

#include "analyzer.h"

#include <clang-c/CXCompilationDatabase.h>
#include <clang-c/Index.h>
#include <spdlog/spdlog.h>

#include <algorithm>
#include <fstream>
#include <set>
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
    std::string line;
    while (std::getline(ifs, line)) {
        ++lines;
    }
    return lines;
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
    if (!clang_Location_isFromMainFile(loc)) {
        return CXChildVisit_Continue;  // Each discovered header is analyzed in its own unit.
    }

    CheckVisitor checker{cursor, *data->file_path};
    for (auto& rule : *data->rules) {
        std::visit(checker, rule);
    }

    return CXChildVisit_Recurse;
}

}  // namespace

FileAnalyzer::FileAnalyzer(std::filesystem::path repo_root, std::optional<ProjectConfig> config,
                           std::optional<std::filesystem::path> compilation_database,
                           std::optional<std::filesystem::path> resource_directory)
    : repo_root_(std::move(repo_root)),
      config_(std::move(config)),
      compilation_database_(std::move(compilation_database)),
      resource_directory_(std::move(resource_directory)) {}

void FileAnalyzer::load_compilation_database() {
    compile_db_ = nullptr;
    recorded_files_.clear();

    const std::vector<std::filesystem::path> candidates =
        compilation_database_.has_value()
            ? std::vector<std::filesystem::path>{*compilation_database_}
            : std::vector<std::filesystem::path>{repo_root_, repo_root_ / "build"};
    for (const auto& supplied_path : candidates) {
        std::error_code ec;
        const auto candidate = std::filesystem::is_regular_file(supplied_path, ec)
                                   ? supplied_path.parent_path()
                                   : supplied_path;
        if (!std::filesystem::exists(candidate / "compile_commands.json", ec) || ec) {
            continue;
        }
        CXCompilationDatabase_Error db_error = CXCompilationDatabase_NoError;
        CXCompilationDatabase db =
            clang_CompilationDatabase_fromDirectory(candidate.string().c_str(), &db_error);
        if (db_error == CXCompilationDatabase_NoError && db != nullptr) {
            spdlog::info("FileAnalyzer: using compilation database from '{}'", candidate.string());
            compile_db_ = db;
            // The exact database inventory distinguishes observed commands from
            // libclang's interpolated commands for otherwise unrecorded files.
            CXCompileCommands recorded = clang_CompilationDatabase_getAllCompileCommands(db);
            for (unsigned index = 0; index < clang_CompileCommands_getSize(recorded); ++index) {
                CXCompileCommand command = clang_CompileCommands_getCommand(recorded, index);
                const std::filesystem::path directory{
                    to_string_and_dispose(clang_CompileCommand_getDirectory(command))};
                std::filesystem::path file{
                    to_string_and_dispose(clang_CompileCommand_getFilename(command))};
                if (file.is_relative()) {
                    file = directory / file;
                }
                recorded_files_.push_back(std::filesystem::absolute(file).lexically_normal());
            }
            clang_CompileCommands_dispose(recorded);
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
        // Interpret relative include paths in the build directory recorded by CMake.
        const std::string directory =
            to_string_and_dispose(clang_CompileCommand_getDirectory(command));
        if (!directory.empty()) {
            args.push_back("-working-directory=" + directory);
        }
        const auto input_path = std::filesystem::absolute(file_path).lexically_normal();
        const std::set<std::string> options_with_value{
            "-include",  "-imacros",  "-I",      "-isystem", "-iquote", "-idirafter",
            "-isysroot", "--sysroot", "-target", "--target", "-x",      "-D",
            "-U",        "-MF",       "-MT",     "-MQ",      "-Xclang"};
        const unsigned num_args = clang_CompileCommand_getNumArgs(command);

        // Skip argv[0] (the compiler executable). Strip -c, -o <out>, and the
        // source file itself: clang_parseTranslationUnit receives the file
        // separately and chokes on output/source positional arguments.
        for (unsigned i = 1; i < num_args; ++i) {
            std::string arg = to_string_and_dispose(clang_CompileCommand_getArg(command, i));
            if (arg == "-c" || arg == "--") {
                // libclang supplies an interpolated source after "--". The source
                // operand is passed separately, so retain no option barrier that
                // would turn later explicit overrides into positional filenames.
                continue;
            }
            if (arg == "-o") {
                ++i;  // Also skip the output path that follows.
                continue;
            }
            if (options_with_value.count(arg) > 0) {
                args.push_back(std::move(arg));
                if (i + 1 < num_args) {
                    args.push_back(
                        to_string_and_dispose(clang_CompileCommand_getArg(command, ++i)));
                }
                continue;
            }
            std::filesystem::path argument_path{arg};
            if (argument_path.is_relative()) {
                argument_path = std::filesystem::path{directory} / argument_path;
            }
            const bool is_source_arg =
                !arg.empty() && arg.front() != '-' &&
                std::filesystem::absolute(argument_path).lexically_normal() == input_path;
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
    coverage_ = {};
    coverage_.parser_version = to_string_and_dispose(clang_getClangVersion());
    for (const auto& rule : make_rules(config_)) {
        coverage_.enabled_rules.push_back(
            std::visit([](const auto& value) { return std::string{value.rule_id()}; }, rule));
    }

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
                coverage_.files.push_back(
                    FileCoverage{file_path.generic_string(), "excluded", "none", 0});
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
    coverage_.files.push_back(FileCoverage{file_path.generic_string()});
    auto& outcome = coverage_.files.back();
    // Skip oversized files.
    std::error_code ec;
    const std::uintmax_t file_size = std::filesystem::file_size(file_path, ec);
    if (ec || file_size > kMaxFileSizeBytes) {
        outcome.status = "skipped";
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
    const auto normalized_file = std::filesystem::absolute(file_path).lexically_normal();
    const bool exact_command = std::find(recorded_files_.begin(), recorded_files_.end(),
                                         normalized_file) != recorded_files_.end();
    outcome.compile_context =
        db_args.empty() ? "fallback" : (exact_command ? "database" : "inferred");
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

    std::string resource_argument;
    if (resource_directory_.has_value()) {
        resource_argument = "-resource-dir=" + resource_directory_->string();
        cmd_args.push_back(resource_argument.c_str());
        spdlog::debug("FileAnalyzer: using builtin resource directory '{}'",
                      resource_directory_->string());
    }

    // Record the exact C API inputs, including repeated flags and explicit overrides.
    // The process cwd is distinct from any -working-directory argument Clang resolves.
    outcome.parse_arguments = std::vector<std::string>{};
    outcome.parse_arguments->reserve(cmd_args.size());
    for (const auto* argument : cmd_args) {
        outcome.parse_arguments->emplace_back(argument);
    }
    std::error_code directory_error;
    const auto process_directory = std::filesystem::current_path(directory_error);
    if (!directory_error) {
        outcome.working_directory = process_directory.generic_string();
    } else {
        spdlog::warn("FileAnalyzer: process cwd unavailable for '{}': {}", path_str,
                     directory_error.message());
    }

    CXTranslationUnit tu = clang_parseTranslationUnit(
        index, path_str.c_str(), cmd_args.data(), static_cast<int>(cmd_args.size()), nullptr, 0,
        CXTranslationUnit_DetailedPreprocessingRecord);

    if (tu == nullptr) {
        spdlog::warn("FileAnalyzer: failed to parse '{}'", path_str);
        clang_disposeIndex(index);
        return;
    }

    const unsigned diagnostic_count = clang_getNumDiagnostics(tu);
    for (unsigned i = 0; i < diagnostic_count; ++i) {
        CXDiagnostic diagnostic = clang_getDiagnostic(tu, i);
        if (clang_getDiagnosticSeverity(diagnostic) >= CXDiagnostic_Error) {
            ++outcome.error_count;
            spdlog::warn("FileAnalyzer: partial AST for '{}': {}", path_str,
                         to_string_and_dispose(clang_formatDiagnostic(
                             diagnostic, clang_defaultDiagnosticDisplayOptions())));
        }
        clang_disposeDiagnostic(diagnostic);
    }
    outcome.status = outcome.error_count == 0 ? "analyzed" : "partial";

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
    std::vector<Finding> file_findings;
    FindingsVisitor harvester{file_findings};
    for (const auto& rule : rules) {
        std::visit(harvester, rule);
    }

    for (auto& finding : file_findings) {
        finding.file = std::filesystem::relative(finding.file, repo_root_).generic_string();
        findings_.push_back(std::move(finding));
    }

    clang_disposeTranslationUnit(tu);
    clang_disposeIndex(index);
}

}  // namespace cppulse
