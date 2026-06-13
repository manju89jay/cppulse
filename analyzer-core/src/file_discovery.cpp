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
const std::set<std::string> kCppExtensions{".cpp", ".cxx", ".cc", ".h", ".hpp", ".hxx"};

/// @brief Return true if haystack ends with suffix.
bool ends_with(const std::string& haystack, const std::string& suffix) {
    return haystack.size() >= suffix.size() &&
           haystack.compare(haystack.size() - suffix.size(), suffix.size(), suffix) == 0;
}

/// @brief Return true if haystack starts with prefix.
bool starts_with(const std::string& haystack, const std::string& prefix) {
    return haystack.size() >= prefix.size() && haystack.compare(0, prefix.size(), prefix) == 0;
}

}  // namespace

bool is_generated_source(const std::filesystem::path& path) {
    std::string name = path.filename().string();
    std::transform(name.begin(), name.end(), name.begin(),
                   [](unsigned char ch) { return static_cast<char>(std::tolower(ch)); });

    // protobuf / gRPC generated (also matches *.grpc.pb.h, *.pb.cc).
    if (ends_with(name, ".pb.h") || ends_with(name, ".pb.cc") || ends_with(name, ".pb.cpp") ||
        ends_with(name, ".pb.c")) {
        return true;
    }
    // upb (gRPC's C protobuf backend) — the chief cause of parser stalls.
    if (name.find(".upb.") != std::string::npos || name.find(".upbdefs.") != std::string::npos ||
        name.find(".upb_minitable.") != std::string::npos) {
        return true;
    }
    // flatbuffers.
    if (ends_with(name, "_generated.h")) {
        return true;
    }
    // Qt meta-object / resource / ui generated files.
    if (starts_with(name, "moc_") || starts_with(name, "qrc_") || starts_with(name, "ui_")) {
        return true;
    }
    // Generator output directories (gRPC's upb-gen / upbdefs-gen).
    for (const auto& component : path) {
        const std::string dir = component.string();
        if (dir == "upb-gen" || dir == "upbdefs-gen") {
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
             root, std::filesystem::directory_options::follow_directory_symlink, ec);
         it != std::filesystem::recursive_directory_iterator(); it.increment(ec)) {
        if (ec) {
            spdlog::warn("discover_cpp_files: iterator error at {}: {}", it->path().string(),
                         ec.message());
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
        if (kCppExtensions.count(lower_ext) > 0 && !is_generated_source(it->path())) {
            results.push_back(std::filesystem::absolute(it->path()));
        }
    }

    std::sort(results.begin(), results.end());
    spdlog::debug("discover_cpp_files: found {} file(s) under {}", results.size(), root.string());
    return results;
}

}  // namespace cppulse
