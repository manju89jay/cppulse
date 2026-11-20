/**
 * @file file_discovery.cpp
 * @brief Implementation of recursive C++ file discovery.
 */

#include "file_discovery.h"

#include <spdlog/spdlog.h>

#include <algorithm>
#include <set>

namespace cppulse {

namespace {

/// @brief Known C++ source-file extensions (lowercase).
const std::set<std::string> kCppExtensions{".cpp", ".cxx", ".cc",  ".h",   ".hh",
                                           ".hpp", ".hxx", ".ipp", ".inl", ".tpp"};

}  // namespace

std::vector<std::filesystem::path> discover_cpp_files(const std::filesystem::path& root) {
    if (!std::filesystem::exists(root)) {
        spdlog::warn("discover_cpp_files: path does not exist: {}", root.string());
        return {};
    }
    if (!std::filesystem::is_directory(root)) {
        spdlog::warn("discover_cpp_files: path is not a directory: {}", root.string());
        return {};
    }

    std::vector<std::filesystem::path> results;

    std::error_code ec;
    for (auto it = std::filesystem::recursive_directory_iterator(
             root, std::filesystem::directory_options::skip_permission_denied, ec);
         it != std::filesystem::recursive_directory_iterator(); it.increment(ec)) {
        if (ec) {
            spdlog::warn("discover_cpp_files: iterator error at {}: {}", it->path().string(),
                         ec.message());
            ec.clear();
            continue;
        }
        // Avoid implicit traversal outside the selected scope and symlink cycles.
        if (it->is_symlink(ec)) {
            it.disable_recursion_pending();
            ec.clear();
            continue;
        }
        if (!it->is_regular_file(ec)) {
            ec.clear();
            continue;
        }
        const std::string ext = it->path().extension().string();
        // Convert extension to lowercase for comparison.
        std::string lower_ext = ext;
        std::transform(lower_ext.begin(), lower_ext.end(), lower_ext.begin(),
                       [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
        if (kCppExtensions.count(lower_ext) > 0) {
            results.push_back(std::filesystem::absolute(it->path()));
        }
    }

    std::sort(results.begin(), results.end());
    spdlog::debug("discover_cpp_files: found {} file(s) under {}", results.size(), root.string());
    return results;
}

}  // namespace cppulse
