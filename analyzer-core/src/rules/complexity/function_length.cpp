/**
 * @file function_length.cpp
 * @brief CPP-CX-002 implementation.
 */

#include "function_length.h"

#include <clang-c/Index.h>

#include <limits>

namespace cppulse {

void FunctionLengthRule::check_impl(CXCursor cursor, const std::string& file_path) {
    const CXCursorKind kind = clang_getCursorKind(cursor);
    if (kind != CXCursor_FunctionDecl && kind != CXCursor_FunctionTemplate &&
        kind != CXCursor_CXXMethod && kind != CXCursor_Constructor && kind != CXCursor_Destructor) {
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
    unsigned int col = 0;
    CXFile start_file = nullptr;
    CXFile end_file = nullptr;
    CXFile cursor_file = nullptr;
    // An exported declaration can start with an attribute spelled in a header
    // macro. Its expansion, not that unrelated header line, bounds the function.
    clang_getExpansionLocation(start, &start_file, &start_line, &col, nullptr);
    clang_getExpansionLocation(end, &end_file, &end_line, nullptr, nullptr);
    clang_getExpansionLocation(clang_getCursorLocation(cursor), &cursor_file, nullptr, nullptr,
                               nullptr);
    if (start_file == nullptr || end_file == nullptr || cursor_file == nullptr ||
        !clang_File_isEqual(start_file, end_file) || !clang_File_isEqual(start_file, cursor_file) ||
        start_line == 0 || col == 0 || end_line < start_line ||
        end_line > static_cast<unsigned int>(std::numeric_limits<int>::max())) {
        return;
    }

    const int line_count = static_cast<int>(end_line) - static_cast<int>(start_line) + 1;

    if (line_count <= warn_lines_) {
        return;
    }

    const std::string severity = (line_count > error_lines_) ? "error" : "warning";

    CXString spelling = clang_getCursorSpelling(cursor);
    const char* func_name = clang_getCString(spelling);
    std::string name_str = (func_name != nullptr) ? func_name : "<unnamed>";
    clang_disposeString(spelling);

    add_finding(Finding{.rule_id = "CPP-CX-002",
                        .category = "complexity",
                        .severity = severity,
                        .file = file_path,
                        .line = static_cast<int>(start_line),
                        .column = static_cast<int>(col),
                        .end_line = static_cast<int>(end_line),
                        .message = "Function '" + name_str + "' is " + std::to_string(line_count) +
                                   " lines long (threshold: warning>" +
                                   std::to_string(warn_lines_) + ", error>" +
                                   std::to_string(error_lines_) + ")",
                        .suggestion = "Decompose into smaller helper functions",
                        .confidence = 1.0});
}

}  // namespace cppulse
