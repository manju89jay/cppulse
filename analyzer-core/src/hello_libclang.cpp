/**
 * @file hello_libclang.cpp
 * @brief Minimal libclang integration — extracts function names from a C++ file.
 */

#include "hello_libclang.h"

#include <clang-c/Index.h>
#include <spdlog/spdlog.h>

namespace cppulse {

namespace {

/**
 * @brief Visitor callback for clang_visitChildren.
 *
 * Collects function declaration names into the client-data vector.
 */
CXChildVisitResult visitor(CXCursor cursor, CXCursor /*parent*/, CXClientData client_data) {
    auto* names = static_cast<std::vector<std::string>*>(client_data);

    if (clang_getCursorKind(cursor) == CXCursor_FunctionDecl) {
        CXString spelling = clang_getCursorSpelling(cursor);
        const char* name = clang_getCString(spelling);
        if (name != nullptr && name[0] != '\0') {
            names->emplace_back(name);
        }
        clang_disposeString(spelling);
    }

    return CXChildVisit_Recurse;
}

} // namespace

std::optional<std::vector<std::string>> extract_function_names(std::string_view file_path) {
    std::string path_str(file_path);

    CXIndex index = clang_createIndex(/*excludeDeclarationsFromPCH=*/0,
                                      /*displayDiagnostics=*/0);
    if (index == nullptr) {
        spdlog::error("extract_function_names: clang_createIndex failed");
        return std::nullopt;
    }

    CXTranslationUnit tu = clang_parseTranslationUnit(
        index,
        path_str.c_str(),
        nullptr, // command_line_args
        0,       // num_command_line_args
        nullptr, // unsaved_files
        0,       // num_unsaved_files
        CXTranslationUnit_None);

    if (tu == nullptr) {
        spdlog::warn("extract_function_names: failed to parse '{}'", path_str);
        clang_disposeIndex(index);
        return std::nullopt;
    }

    std::vector<std::string> names;
    CXCursor root = clang_getTranslationUnitCursor(tu);
    clang_visitChildren(root, visitor, &names);

    spdlog::info("extract_function_names: found {} function(s) in '{}'",
                 names.size(), path_str);

    clang_disposeTranslationUnit(tu);
    clang_disposeIndex(index);

    return names;
}

} // namespace cppulse
