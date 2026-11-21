/**
 * @file file_discovery.cpp
 * @brief Implementation of recursive C++ file discovery.
 */

#include "file_discovery.h"

#include <spdlog/spdlog.h>

#include <algorithm>
#include <cctype>
#include <set>

namespace cppulse {

namespace {

/// @brief Known C++ source-file extensions (lowercase).
const std::set<std::string> kCppExtensions{".cpp", ".c++", ".cxx", ".cc",  ".h",  ".hh",
                                           ".hpp", ".hxx", ".ipp", ".inl", ".tpp"};

bool ends_with(const std::string& value, const std::string& suffix) {
    return value.size() >= suffix.size() &&
           value.compare(value.size() - suffix.size(), suffix.size(), suffix) == 0;
}

bool starts_with(const std::string& value, const std::string& prefix) {
    return value.size() >= prefix.size() && value.compare(0, prefix.size(), prefix) == 0;
}

}  // namespace

bool has_supported_cpp_extension(const std::filesystem::path& path) {
    auto extension = path.extension().string();
    std::transform(extension.begin(), extension.end(), extension.begin(),
                   [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
    return kCppExtensions.count(extension) > 0;
}

bool is_generated_source(const std::filesystem::path& path) {
    auto name = path.filename().string();
    std::transform(name.begin(), name.end(), name.begin(),
                   [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });
    if (ends_with(name, ".pb.h") || ends_with(name, ".pb.cc") || ends_with(name, ".pb.cpp") ||
        ends_with(name, ".pb.c") || name.find(".upb.") != std::string::npos ||
        name.find(".upbdefs.") != std::string::npos ||
        name.find(".upb_minitable.") != std::string::npos || ends_with(name, "_generated.h") ||
        starts_with(name, "moc_") || starts_with(name, "qrc_") || starts_with(name, "ui_")) {
        return true;
    }
    for (const auto& component : path) {
        if (component == "upb-gen" || component == "upbdefs-gen") {
            return true;
        }
    }
    return false;
}

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
        if (has_supported_cpp_extension(it->path())) {
            results.push_back(std::filesystem::absolute(it->path()));
        }
    }

    std::sort(results.begin(), results.end());
    spdlog::debug("discover_cpp_files: found {} file(s) under {}", results.size(), root.string());
    return results;
}

}  // namespace cppulse
