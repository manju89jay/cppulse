/**
 * @file unsafe_array_access.cpp
 * @brief CPP-MEM-003 implementation.
 */

#include "unsafe_array_access.h"

#include <clang-c/Index.h>

namespace cppulse {

void UnsafeArrayAccessRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_ParmDecl) {
        return;
    }

    CXType param_type = clang_getCursorType(cursor);
    if (param_type.kind != CXType_ConstantArray && param_type.kind != CXType_IncompleteArray &&
        param_type.kind != CXType_VariableArray) {
        return;
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    CXString spelling = clang_getCursorSpelling(cursor);
    const char* param_name = clang_getCString(spelling);
    std::string name_str = (param_name != nullptr) ? param_name : "<unnamed>";
    clang_disposeString(spelling);

    add_finding(
        Finding{.rule_id = "CPP-MEM-003",
                .category = "memory_safety",
                .severity = "warning",
                .file = file_path,
                .line = static_cast<int>(line),
                .column = static_cast<int>(column),
                .message = "C-style array parameter '" + name_str +
                           "' decays to a raw pointer with no bounds information",
                .suggestion = "Replace C-style array parameter with std::span<T> or std::vector<T>",
                .confidence = 1.0});
}

}  // namespace cppulse
