/**
 * @file init_all_vars.cpp
 * @brief MISRA-007 implementation.
 */

#include "init_all_vars.h"

#include <clang-c/Index.h>

namespace cppulse {

void InitAllVarsRule::check_impl(CXCursor cursor, const std::string& file_path) {
    if (clang_getCursorKind(cursor) != CXCursor_VarDecl) {
        return;
    }

    // Only flag local variables (inside a function body), not globals/statics.
    CXCursor semantic_parent = clang_getCursorSemanticParent(cursor);
    const CXCursorKind parent_kind = clang_getCursorKind(semantic_parent);
    const bool is_local =
        (parent_kind == CXCursor_FunctionDecl || parent_kind == CXCursor_CXXMethod ||
         parent_kind == CXCursor_Constructor || parent_kind == CXCursor_Destructor);
    if (!is_local) {
        return;
    }

    // Check whether this VarDecl has an initializer child.
    struct HasInit {
        bool found = false;
    } hi;

    clang_visitChildren(
        cursor,
        [](CXCursor child, CXCursor /*parent*/, CXClientData data) -> CXChildVisitResult {
            auto* state = static_cast<HasInit*>(data);
            // Any child node means the variable has an initializer or is a
            // type reference — we count all non-TypeRef children as inits.
            const CXCursorKind ck = clang_getCursorKind(child);
            if (ck != CXCursor_TypeRef && ck != CXCursor_TemplateRef &&
                ck != CXCursor_NamespaceRef) {
                state->found = true;
                return CXChildVisit_Break;
            }
            return CXChildVisit_Continue;
        },
        &hi);

    if (hi.found) {
        return;  // Has initializer.
    }

    // Skip extern / static storage class — those may be intentionally uninit
    // (e.g., static int counter;).
    CXType var_type = clang_getCursorType(cursor);
    // Ignore reference types, function types, and record types with
    // default constructors — those are default-initialized by the compiler.
    if (var_type.kind == CXType_LValueReference || var_type.kind == CXType_RValueReference ||
        var_type.kind == CXType_Record || var_type.kind == CXType_Unexposed) {
        return;
    }

    CXSourceLocation loc = clang_getCursorLocation(cursor);
    unsigned int line = 0;
    unsigned int column = 0;
    clang_getSpellingLocation(loc, nullptr, &line, &column, nullptr);

    CXString spelling = clang_getCursorSpelling(cursor);
    const char* var_name = clang_getCString(spelling);
    std::string name_str = (var_name != nullptr) ? var_name : "<unnamed>";
    clang_disposeString(spelling);

    CXString type_spelling = clang_getTypeSpelling(var_type);
    const char* type_str = clang_getCString(type_spelling);
    std::string type_name = (type_str != nullptr) ? type_str : "?";
    clang_disposeString(type_spelling);

    add_finding(Finding{.rule_id = "MISRA-007",
                        .category = "misra",
                        .severity = "warning",
                        .file = file_path,
                        .line = static_cast<int>(line),
                        .column = static_cast<int>(column),
                        .message = "Variable '" + name_str + "' of type '" + type_name +
                                   "' declared without an initializer",
                        .suggestion = "Initialize '" + name_str + "' at the point of declaration",
                        .confidence = 0.9});
}

}  // namespace cppulse
