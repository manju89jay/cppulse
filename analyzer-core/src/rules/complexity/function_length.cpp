/**
 * @file function_length.cpp
 * @brief CPP-CX-002 implementation.
 */

#include "function_length.h"

#include <clang-c/Index.h>

namespace cppulse {

namespace {

constexpr int kWarnLines = 80;
constexpr int kErrorLines = 150;

}  // namespace

void FunctionLengthRule::check_impl(CXCursor cursor, const std::string& file_path) {
    const CXCursorKind kind = clang_getCursorKind(cursor);
    if (kind != CXCursor_FunctionDecl && kind != CXCursor_CXXMethod &&
        kind != CXCursor_Constructor && kind != CXCursor_Destructor) {
        return;
    }

    if (!clang_isCursorDefinition(cursor)) {
        return;
    }

    CXSourceRange extent = clang_getCursorExtent(cursor);
    CXSourceLocation start = clang_getRangeStart(extent);
    CXSourceLocation end = clang_getRangeEnd(extent);

    unsigned int start_line = 0;
    unsigned int end_line = 0;
    clang_getSpellingLocation(start, nullptr, &start_line, nullptr, nullptr);
    clang_getSpellingLocation(end, nullptr, &end_line, nullptr, nullptr);

    const int line_count = static_cast<int>(end_line) - static_cast<int>(start_line) + 1;

    if (line_count <= kWarnLines) {
        return;
    }

    const std::string severity = (line_count > kErrorLines) ? "error" : "warning";

    CXString spelling = clang_getCursorSpelling(cursor);
    const char* func_name = clang_getCString(spelling);
    std::string name_str = (func_name != nullptr) ? func_name : "<unnamed>";
    clang_disposeString(spelling);

    unsigned int col = 0;
    clang_getSpellingLocation(start, nullptr, nullptr, &col, nullptr);

    add_finding(Finding{.rule_id = "CPP-CX-002",
                        .category = "complexity",
                        .severity = severity,
                        .file = file_path,
                        .line = static_cast<int>(start_line),
                        .column = static_cast<int>(col),
                        .end_line = static_cast<int>(end_line),
                        .message = "Function '" + name_str + "' is " + std::to_string(line_count) +
                                   " lines long (threshold: warning>" + std::to_string(kWarnLines) +
                                   ", error>" + std::to_string(kErrorLines) + ")",
                        .suggestion = "Decompose into smaller helper functions",
                        .confidence = 1.0});
}

}  // namespace cppulse
