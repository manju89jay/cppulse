/**
 * @file parameter_count.cpp
 * @brief CPP-CX-003 implementation.
 */

#include "parameter_count.h"

#include <clang-c/Index.h>

namespace cppulse {

void ParameterCountRule::check_impl(CXCursor cursor, const std::string& file_path) {
    const CXCursorKind kind = clang_getCursorKind(cursor);
    if (kind != CXCursor_FunctionDecl && kind != CXCursor_CXXMethod &&
        kind != CXCursor_Constructor) {
        return;
    }

    const int num_params = clang_Cursor_getNumArguments(cursor);
    if (num_params < 0) {
        return;  // Not a function-type cursor.
    }

    if (num_params <= warn_params_) {
        return;
    }

    const std::string severity = (num_params > error_params_) ? "error" : "warning";

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    CXString spelling = clang_getCursorSpelling(cursor);
    const char* func_name = clang_getCString(spelling);
    std::string name_str = (func_name != nullptr) ? func_name : "<unnamed>";
    clang_disposeString(spelling);

    add_finding(Finding{
        .rule_id = "CPP-CX-003",
        .category = "complexity",
        .severity = severity,
        .file = file_path,
        .line = static_cast<int>(line),
        .column = static_cast<int>(column),
        .message = "Function '" + name_str + "' has " + std::to_string(num_params) +
                   " parameters (threshold: warning>" + std::to_string(warn_params_) + ", error>" +
                   std::to_string(error_params_) + ")",
        .suggestion = "Introduce a parameter struct or builder pattern to reduce parameter count",
        .confidence = 1.0});
}

}  // namespace cppulse
