/**
 * @file raw_string_literal.cpp
 * @brief CPP-MOD-004 implementation.
 */

#include "raw_string_literal.h"

#include <clang-c/Index.h>

namespace cppulse {

namespace {

/// @brief Minimum number of backslash sequences before we suggest a raw literal.
constexpr int kMinBackslashCount = 3;

}  // namespace

void RawStringLiteralRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_StringLiteral) {
        return;
    }

    // Retrieve the token text to count actual backslashes in the source.
    CXTranslationUnit tu = clang_Cursor_getTranslationUnit(cursor);
    CXSourceRange range = clang_getCursorExtent(cursor);

    CXToken* tokens = nullptr;
    unsigned int num_tokens = 0;
    clang_tokenize(tu, range, &tokens, &num_tokens);

    int backslash_count = 0;
    for (unsigned int idx = 0; idx < num_tokens; ++idx) {
        CXString tok_spelling = clang_getTokenSpelling(tu, tokens[idx]);
        const char* tok_str = clang_getCString(tok_spelling);
        if (tok_str != nullptr) {
            // Count '\\' pairs (each pair represents one escaped backslash).
            std::string_view sv{tok_str};
            for (std::size_t pos = 0; pos + 1 < sv.size(); ++pos) {
                if (sv[pos] == '\\' && sv[pos + 1] != '\0') {
                    ++backslash_count;
                    ++pos;  // Skip next char (it is the escaped char).
                }
            }
        }
        clang_disposeString(tok_spelling);
    }

    if (tokens != nullptr) {
        clang_disposeTokens(tu, tokens, num_tokens);
    }

    if (backslash_count < kMinBackslashCount) {
        return;
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    add_finding(
        Finding{.rule_id = "CPP-MOD-004",
                .category = "modernization",
                .severity = "info",
                .file = file_path,
                .line = static_cast<int>(line),
                .column = static_cast<int>(column),
                .message = "String literal contains " + std::to_string(backslash_count) +
                           " escape sequences; consider a raw string literal for readability",
                .suggestion = "Replace escaped string with R\"(...)\" raw string literal",
                .confidence = 0.9});
}

}  // namespace cppulse
