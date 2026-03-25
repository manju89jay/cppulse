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

/// @brief Build the default set of 22 analysis rules.
std::vector<AnyRule> make_rules() {
    std::vector<AnyRule> rules;
    rules.reserve(22);

    // Memory Safety
    rules.emplace_back(RawPointerOwnershipRule{});
    rules.emplace_back(ManualMemoryMgmtRule{});
    rules.emplace_back(UnsafeArrayAccessRule{});

    // Modernization
    rules.emplace_back(CStyleCastRule{});
    rules.emplace_back(DeprecatedHeadersRule{});
    rules.emplace_back(MissingOverrideRule{});
    rules.emplace_back(RawStringLiteralRule{});
    rules.emplace_back(AutoUsageRule{});
    rules.emplace_back(RangeForRule{});
    rules.emplace_back(NullptrUsageRule{});
    rules.emplace_back(EnumClassRule{});
    rules.emplace_back(UsingVsTypedefRule{});

    // Complexity
    rules.emplace_back(CyclomaticComplexityRule{});
    rules.emplace_back(FunctionLengthRule{});
    rules.emplace_back(ParameterCountRule{});

    // MISRA
    rules.emplace_back(NoGotoRule{});
    rules.emplace_back(NoImplicitConversionRule{});
    rules.emplace_back(NoUnionRule{});
    rules.emplace_back(NoDynamicAllocRule{});
    rules.emplace_back(NoRecursionRule{});
    rules.emplace_back(SingleExitRule{});
    rules.emplace_back(InitAllVarsRule{});

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

FileAnalyzer::FileAnalyzer(std::filesystem::path repo_root) : repo_root_(std::move(repo_root)) {}

void FileAnalyzer::run() {
    findings_.clear();
    file_count_ = 0;
    total_loc_ = 0;

    const std::vector<std::filesystem::path> files = discover_cpp_files(repo_root_);
    spdlog::info("FileAnalyzer: found {} file(s) under {}", files.size(), repo_root_.string());

    for (const auto& file_path : files) {
        analyze_file(file_path);
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

    // Build a fresh rule set for this file.
    std::vector<AnyRule> rules = make_rules();

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
