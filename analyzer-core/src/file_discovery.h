/**
 * @file file_discovery.h
 * @brief Utility for recursively finding C++ source files in a directory tree.
 */

#ifndef CPPULSE_FILE_DISCOVERY_H
#define CPPULSE_FILE_DISCOVERY_H

#include <filesystem>
#include <vector>

namespace cppulse {

/**
 * @brief Recursively discover all C++ source files under a root directory.
 *
 * Accepted extensions: .cpp, .c++, .cxx, .cc, .h, .hh, .hpp, .hxx, .ipp, .inl, .tpp.
 * Symbolic-link entries are skipped to avoid external scope and cycles.
 * Generated-looking files remain in the inventory; the analyzer records their
 * heuristic exclusion explicitly instead of hiding them during discovery.
 * Non-existent or non-directory roots return an
 * empty vector.
 *
 * @param root  Directory to search.
 * @return      Sorted list of absolute paths to C++ source files.
 */
[[nodiscard]] std::vector<std::filesystem::path> discover_cpp_files(
    const std::filesystem::path& root);

/** @brief Return whether a path has a supported C++ source/header extension. */
[[nodiscard]] bool has_supported_cpp_extension(const std::filesystem::path& path);

/**
 * @brief Classify common generated filenames and generator-output directories.
 *
 * Recognizes protobuf/gRPC, upb, flatbuffers and Qt naming conventions. This
 * heuristic is not evidence that a particular file was actually generated.
 *
 * @param path File path to classify.
 * @return True when the filename or directory matches a generated-source convention.
 */
[[nodiscard]] bool is_generated_source(const std::filesystem::path& path);

}  // namespace cppulse

#endif  // CPPULSE_FILE_DISCOVERY_H
