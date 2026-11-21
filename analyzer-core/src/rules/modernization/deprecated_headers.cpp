/**
 * @file deprecated_headers.cpp
 * @brief CPP-MOD-002 implementation.
 */

#include "deprecated_headers.h"

#include <clang-c/Index.h>

#include <set>
#include <string>
#include <string_view>

namespace cppulse {

namespace {

/// @brief C headers that have direct C++ replacements.
const std::set<std::string> kDeprecatedHeaders{
    "assert.h", "complex.h", "ctype.h",  "errno.h",  "fenv.h",   "float.h",  "inttypes.h",
    "iso646.h", "limits.h",  "locale.h", "math.h",   "setjmp.h", "signal.h", "stdalign.h",
    "stdarg.h", "stdbool.h", "stddef.h", "stdint.h", "stdio.h",  "stdlib.h", "string.h",
    "time.h",   "uchar.h",   "wchar.h",  "wctype.h"};

/** @brief Require a literal angle operand rather than a macro-expanded header name. */
bool has_direct_operand(CXCursor cursor, std::string_view operand) {
    const CXTranslationUnit unit = clang_Cursor_getTranslationUnit(cursor);
    if (unit == nullptr) {
        return false;
    }
    const CXSourceRange extent = clang_getCursorExtent(cursor);
    CXFile begin_file = nullptr;
    CXFile end_file = nullptr;
    unsigned begin = 0;
    unsigned end = 0;
    clang_getSpellingLocation(clang_getRangeStart(extent), &begin_file, nullptr, nullptr, &begin);
    clang_getSpellingLocation(clang_getRangeEnd(extent), &end_file, nullptr, nullptr, &end);
    if (begin_file == nullptr || end_file == nullptr ||
        clang_File_isEqual(begin_file, end_file) == 0 || end <= begin) {
        return false;
    }
    std::size_t size = 0;
    const char* bytes = clang_getFileContents(unit, begin_file, &size);
    if (bytes == nullptr || end > size) {
        return false;
    }
    std::string_view directive{bytes + begin, end - begin};
    const auto skip_space = [&directive]() {
        const auto first = directive.find_first_not_of(" \t");
        directive.remove_prefix(first == std::string_view::npos ? directive.size() : first);
    };
    skip_space();
    if (directive.empty() || directive.front() != '#') {
        return false;
    }
    directive.remove_prefix(1);
    skip_space();
    constexpr std::string_view include_keyword = "include";
    if (directive.substr(0, include_keyword.size()) != include_keyword) {
        return false;
    }
    directive.remove_prefix(include_keyword.size());
    skip_space();
    if (directive.empty() || directive.front() != '<') {
        return false;
    }
    const auto closing = directive.find('>');
    return closing != std::string_view::npos && directive.substr(1, closing - 1) == operand;
}

}  // namespace

void DeprecatedHeadersRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_InclusionDirective) {
        return;
    }

    CXFile included_file = clang_getIncludedFile(cursor);
    if (included_file == nullptr) {
        return;
    }

    CXString file_name = clang_getCursorSpelling(cursor);
    const char* raw_name = clang_getCString(file_name);
    std::string header_name = (raw_name != nullptr) ? raw_name : "";
    clang_disposeString(file_name);

    if (kDeprecatedHeaders.count(header_name) == 0 || !has_direct_operand(cursor, header_name)) {
        return;
    }
    // The same bare operand can resolve to a project shadow through -I. Trust
    // the compiler's system classification, not the resolved file's basename.
    const CXTranslationUnit unit = clang_Cursor_getTranslationUnit(cursor);
    if (unit == nullptr ||
        clang_Location_isInSystemHeader(clang_getLocation(unit, included_file, 1, 1)) == 0) {
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
