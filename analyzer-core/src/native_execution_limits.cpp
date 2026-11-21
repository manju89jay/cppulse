/** @file native_execution_limits.cpp
 * @brief Native Linux limits and strict finite source-list validation.
 */
#include "native_execution_limits.h"

#include <algorithm>
#include <cctype>
#include <cerrno>
#include <cstring>
#include <fstream>
#include <limits>
#include <set>
#include <stdexcept>
#include <string>

#include "file_discovery.h"

#if defined(__linux__)
#include <sys/resource.h>
#include <unistd.h>
#endif

namespace cppulse {
namespace {
constexpr std::uintmax_t kSelectionBytes = 8 * 1024 * 1024;
constexpr std::size_t kSelectionFiles = 100000;

#if defined(__linux__)
void set_limit(int resource, std::uint64_t value) {
    if (value == 0 || value >= static_cast<std::uint64_t>(RLIM_INFINITY)) {
        throw std::runtime_error("Native resource limit must be a finite positive integer");
    }
    rlimit previous{};
    if (getrlimit(resource, &previous) != 0) {
        throw std::runtime_error(std::string{"Cannot inspect native resource limit: "} +
                                 std::strerror(errno));
    }
    if (previous.rlim_max != RLIM_INFINITY && value > previous.rlim_max) {
        throw std::runtime_error("Native requested resource limit exceeds inherited hard limit");
    }
    const rlimit requested{static_cast<rlim_t>(value), static_cast<rlim_t>(value)};
    if (setrlimit(resource, &requested) != 0) {
        throw std::runtime_error(std::string{"Cannot apply native resource limit: "} +
                                 std::strerror(errno));
    }
    rlimit observed{};
    if (getrlimit(resource, &observed) != 0 || observed.rlim_cur != requested.rlim_cur ||
        observed.rlim_max != requested.rlim_max) {
        throw std::runtime_error("Native resource limit could not be verified after application");
    }
}
#endif
}  // namespace

nlohmann::json apply_native_execution_limits(const NativeExecutionLimits& limits) {
    nlohmann::json report{
        {"version", "1.0.0"},
        {"platform", "unsupported"},
        {"requested",
         {{"address_space_bytes", limits.address_space_bytes
                                      ? nlohmann::json(*limits.address_space_bytes)
                                      : nlohmann::json(nullptr)},
          {"cpu_seconds",
           limits.cpu_seconds ? nlohmann::json(*limits.cpu_seconds) : nlohmann::json(nullptr)}}},
        {"applied", {{"address_space", false}, {"cpu_time", false}, {"file_size", false}}},
        {"initialized_before_guard", {"dynamic loader", "CLI parser", "logging"}},
        {"limitations",
         {"Address space is per native process, not RSS or aggregate system memory.",
          "CPU and peak memory usage are not measured by this guard."}}};
#if defined(__linux__)
    report["platform"] = "linux-posix-rlimit";
    if (limits.address_space_bytes) {
        std::ifstream statm{"/proc/self/statm"};
        std::uint64_t pages = 0;
        const long page_size = sysconf(_SC_PAGESIZE);
        if (!(statm >> pages) || page_size <= 0 ||
            pages >
                std::numeric_limits<std::uint64_t>::max() / static_cast<std::uint64_t>(page_size)) {
            throw std::runtime_error("Cannot establish native initial address-space requirement");
        }
        const auto initial_bytes = pages * static_cast<std::uint64_t>(page_size);
        constexpr std::uint64_t kStartupHeadroom = 16 * 1024 * 1024;
        if (*limits.address_space_bytes <= initial_bytes ||
            *limits.address_space_bytes - initial_bytes < kStartupHeadroom) {
            throw std::runtime_error(
                "Native address-space limit is below initial mappings plus 16-MiB guard headroom");
        }
        report["initial_address_space_bytes"] = initial_bytes;
        set_limit(RLIMIT_AS, *limits.address_space_bytes);
        report["applied"]["address_space"] = true;
    }
    if (limits.file_size_bytes) {
        set_limit(RLIMIT_FSIZE, *limits.file_size_bytes);
        report["applied"]["file_size"] = true;
    }
    if (limits.cpu_seconds) {
        set_limit(RLIMIT_CPU, *limits.cpu_seconds);
        report["applied"]["cpu_time"] = true;
    }
#else
    if (limits.address_space_bytes || limits.cpu_seconds || limits.file_size_bytes) {
        throw std::runtime_error(
            "Native CPU/address-space guards are qualified only on Linux POSIX");
    }
#endif
    return report;
}

std::vector<std::filesystem::path> validate_selected_files(
    const std::filesystem::path& source_root,
    const std::vector<std::filesystem::path>& selected_files) {
    if (selected_files.empty() || selected_files.size() > kSelectionFiles) {
        throw std::runtime_error("Selected files must contain between 1 and 100000 identities");
    }
    const auto root = std::filesystem::canonical(source_root);
    if (!std::filesystem::is_directory(root))
        throw std::runtime_error("Selected source root is not a directory");
    std::set<std::string> seen;
    std::vector<std::filesystem::path> result;
    result.reserve(selected_files.size());
    for (const auto& relative : selected_files) {
        const auto text = relative.generic_string();
        if (text.empty() || relative.is_absolute() || relative.has_root_name() ||
            relative.lexically_normal().generic_string() != text || text.back() == '/' ||
            text.find('\\') != std::string::npos || text.find(':') != std::string::npos ||
            std::any_of(text.begin(), text.end(),
                        [](unsigned char ch) { return ch < 32 || ch == 127; }) ||
            !seen.insert(text).second) {
            throw std::runtime_error("Selected identity is noncanonical or duplicated: " + text);
        }
        auto current = root;
        for (const auto& component : relative) {
            if (component == "." || component == ".." || component.empty())
                throw std::runtime_error("Selected identity escapes source root: " + text);
            current /= component;
            const auto info = std::filesystem::symlink_status(current);
            if (std::filesystem::is_symlink(info))
                throw std::runtime_error("Selected identity contains a symlink: " + text);
        }
        if (!std::filesystem::is_regular_file(std::filesystem::symlink_status(current)))
            throw std::runtime_error("Selected input is not an existing regular file: " + text);
        if (!has_supported_cpp_extension(current))
            throw std::runtime_error("Selected input has an unsupported C++ extension: " + text);
        result.push_back(current);
    }
    return result;
}

std::vector<std::filesystem::path> read_selected_files(
    const std::filesystem::path& source_root, const std::filesystem::path& selection_file) {
    const auto info = std::filesystem::symlink_status(selection_file);
    if (!std::filesystem::is_regular_file(info) ||
        std::filesystem::file_size(selection_file) > kSelectionBytes) {
        throw std::runtime_error("Selection must be a regular JSON file no larger than 8 MiB");
    }
    std::ifstream stream{selection_file, std::ios::binary};
    std::string content(kSelectionBytes + 1, '\0');
    stream.read(content.data(), static_cast<std::streamsize>(content.size()));
    const auto count = stream.gcount();
    if (stream.bad() || count > static_cast<std::streamsize>(kSelectionBytes)) {
        throw std::runtime_error("Selection exceeds its byte limit or cannot be read");
    }
    content.resize(static_cast<std::size_t>(count));
    const auto document = nlohmann::json::parse(content);
    if (!document.is_array())
        throw std::runtime_error("Selected file document must be a JSON array");
    std::vector<std::filesystem::path> selected;
    for (const auto& item : document) {
        if (!item.is_string())
            throw std::runtime_error("Selected file identities must be strings");
        const auto text = item.get<std::string>();
        // std::filesystem normalizes repeated separators, so reject them before construction.
        if (text.find("//") != std::string::npos)
            throw std::runtime_error("Selected identity contains repeated separators");
        selected.emplace_back(text);
    }
    static_cast<void>(validate_selected_files(source_root, selected));
    return selected;
}
}  // namespace cppulse
