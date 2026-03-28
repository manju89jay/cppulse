/**
 * @file deprecated_headers.cpp
 * @brief CPP-MOD-002 implementation.
 */

#include "deprecated_headers.h"

#include <clang-c/Index.h>

#include <set>
#include <string>

namespace cppulse {

namespace {

/// @brief C headers that have direct C++ replacements.
const std::set<std::string> kDeprecatedHeaders{
    "assert.h", "complex.h", "ctype.h",  "errno.h",  "fenv.h",   "float.h",  "inttypes.h",
    "iso646.h", "limits.h",  "locale.h", "math.h",   "setjmp.h", "signal.h", "stdalign.h",
    "stdarg.h", "stdbool.h", "stddef.h", "stdint.h", "stdio.h",  "stdlib.h", "string.h",
    "time.h",   "uchar.h",   "wchar.h",  "wctype.h"};

}  // namespace

void DeprecatedHeadersRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_InclusionDirective) {
        return;
    }

    CXFile included_file = clang_getIncludedFile(cursor);
    if (included_file == nullptr) {
        return;
    }

    CXString file_name = clang_getFileName(included_file);
    const char* raw_name = clang_getCString(file_name);
    std::string header_name = (raw_name != nullptr) ? raw_name : "";
    clang_disposeString(file_name);

    // Extract the basename for comparison.
    const auto slash_pos = header_name.rfind('/');
    if (slash_pos != std::string::npos) {
        header_name = header_name.substr(slash_pos + 1);
    }

    if (kDeprecatedHeaders.count(header_name) == 0) {
        return;
    }

    // Derive the C++ replacement name (prepend 'c', drop the '.h').
    const std::string basename = header_name.substr(0, header_name.size() - 2);  // drop ".h"
    const std::string replacement = "<c" + basename + ">";

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    add_finding(Finding{
        .rule_id = "CPP-MOD-002",
        .category = "modernization",
        .severity = "warning",
        .file = file_path,
        .line = static_cast<int>(line),
        .column = static_cast<int>(column),
        .message = "Deprecated C header <" + header_name + "> included; prefer the C++ equivalent",
        .suggestion = "Replace <" + header_name + "> with " + replacement,
        .confidence = 1.0});
}

}  // namespace cppulse
