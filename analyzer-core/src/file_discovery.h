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
 * Accepted extensions: .cpp, .cxx, .cc, .h, .hpp, .hxx
 * Symbolic links are followed.  Non-existent or non-directory roots return an
 * empty vector.
 *
 * @param root  Directory to search.
 * @return      Sorted list of absolute paths to C++ source files.
 */
[[nodiscard]] std::vector<std::filesystem::path> discover_cpp_files(
    const std::filesystem::path& root);

}  // namespace cppulse

#endif  // CPPULSE_FILE_DISCOVERY_H
