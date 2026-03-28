/**
 * @file missing_override.cpp
 * @brief CPP-MOD-003 implementation.
 */

#include "missing_override.h"

#include <clang-c/Index.h>

namespace cppulse {

void MissingOverrideRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_CXXMethod) {
        return;
    }

    // Only interested in methods that override a base-class virtual.
    if (!clang_CXXMethod_isVirtual(cursor)) {
        return;
    }

    // clang_CXXMethod_isOverride is not in all libclang versions; we check
    // whether the method has at least one overridden cursor instead.
    unsigned int num_overridden = 0;
    CXCursor* overridden = nullptr;
    clang_getOverriddenCursors(cursor, &overridden, &num_overridden);

    const bool has_base_method = (num_overridden > 0);
    if (overridden != nullptr) {
        clang_disposeOverriddenCursors(overridden);
    }

    if (!has_base_method) {
        return;  // Base virtual declaration — not an override.
    }

    // Check for the override specifier via cursor attributes.
    // libclang does not expose a direct CXCursor_OverrideAttr on all versions;
    // we use the display name check as a pragmatic heuristic: if the method
    // overrides a base but its spelling does NOT include "override" in its
    // annotation attributes, report it.
    // We rely on clang_CXXMethod_isOverride if present, otherwise on attribute
    // token scanning (version-safe approach via CXCursor_AnnotateAttr not
    // reliable here).  Instead, we check the raw cursor attribute cursor kind:
    // clang provides CXCursor_attribute and specific ones, but the simplest
    // approach is iterating over child attribute cursors.

    struct OverrideCheck {
        bool found_override = false;
    } oc;

    clang_visitChildren(
        cursor,
        [](CXCursor child, CXCursor /*parent*/, CXClientData data) -> CXChildVisitResult {
            auto* check = static_cast<OverrideCheck*>(data);
            const CXCursorKind kind = clang_getCursorKind(child);
            if (kind == CXCursor_CXXOverrideAttr) {
                check->found_override = true;
                return CXChildVisit_Break;
            }
            return CXChildVisit_Continue;
        },
        &oc);

    if (oc.found_override) {
        return;  // Correctly marked with override.
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    CXString spelling = clang_getCursorSpelling(cursor);
    const char* method_name = clang_getCString(spelling);
    std::string name_str = (method_name != nullptr) ? method_name : "<unnamed>";
    clang_disposeString(spelling);

    add_finding(Finding{
        .rule_id = "CPP-MOD-003",
        .category = "modernization",
        .severity = "warning",
        .file = file_path,
        .line = static_cast<int>(line),
        .column = static_cast<int>(column),
        .message = "Virtual method '" + name_str +
                   "' overrides a base class method but is missing the 'override' specifier",
        .suggestion = "Add 'override' to the method declaration",
        .confidence = 0.95});
}

}  // namespace cppulse
