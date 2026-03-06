/**
 * @file hello_libclang.h
 * @brief Minimal libclang integration — extracts function names from a C++ file.
 */

#ifndef CPPULSE_HELLO_LIBCLANG_H
#define CPPULSE_HELLO_LIBCLANG_H

#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace cppulse {

/**
 * @brief Parse a C++ source file and extract all top-level and namespaced function names.
 *
 * Uses libclang to build an AST and walks it looking for FunctionDecl cursors.
 * Returns nullopt on parse failure or if the file does not exist.
 * Returns an empty vector if the file parses successfully but contains no functions.
 *
 * @param file_path Path to the C++ source file to parse.
 * @return Vector of function names, or nullopt on error.
 */
[[nodiscard]] std::optional<std::vector<std::string>> extract_function_names(std::string_view file_path);

} // namespace cppulse

#endif // CPPULSE_HELLO_LIBCLANG_H
