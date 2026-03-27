/**
 * @file auto_usage.cpp
 * @brief CPP-MOD-005 implementation.
 */

#include "auto_usage.h"

#include <clang-c/Index.h>

#include <string>

namespace cppulse {

void AutoUsageRule::check_impl(CXCursor cursor, const std::string& file_path) {
    const CXCursorKind kind = clang_getCursorKind(cursor);
    if (kind != CXCursor_VarDecl) {
        return;
    }

    CXType var_type = clang_getCursorType(cursor);
    CXString type_spelling = clang_getTypeSpelling(var_type);
    const char* type_str = clang_getCString(type_spelling);
    std::string type_name = (type_str != nullptr) ? type_str : "";
    clang_disposeString(type_spelling);

    // Flag declarations whose canonical type spelling contains "iterator".
    if (type_name.find("iterator") == std::string::npos &&
        type_name.find("Iterator") == std::string::npos) {
        return;
    }

    // Only flag if the type spelling is verbose (longer than ~20 chars).
    constexpr std::size_t kVerboseThreshold = 20;
    if (type_name.size() <= kVerboseThreshold) {
        return;
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    add_finding(Finding{
        .rule_id = "CPP-MOD-005",
        .category = "modernization",
        .severity = "info",
        .file = file_path,
        .line = static_cast<int>(line),
        .column = static_cast<int>(column),
        .message = "Verbose iterator type '" + type_name + "' can be simplified with 'auto'",
        .suggestion = "Replace the explicit iterator type with 'auto'",
        .confidence = 0.9});
}

}  // namespace cppulse
