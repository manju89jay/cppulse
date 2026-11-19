/** @file test_temp_directory.h
 * @brief Exclusive test directories across parallel cases and test binaries.
 */
#ifndef CPPULSE_TEST_TEMP_DIRECTORY_H
#define CPPULSE_TEST_TEMP_DIRECTORY_H

#include <atomic>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <string>

#ifdef _WIN32
#include <process.h>
#else
#include <unistd.h>
#endif

namespace cppulse::test {

/** @brief Create an owned test directory without removing preexisting paths.
 * @param prefix Descriptive filename prefix for diagnostic artifact paths.
 * @return A newly and exclusively created directory; throws on creation failure.
 */
inline std::filesystem::path make_test_directory(const std::string& prefix) {
    static std::atomic<std::uint64_t> sequence{0};
#ifdef _WIN32
    const auto process = _getpid();
#else
    const auto process = getpid();
#endif
    const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
    const auto parent = std::filesystem::temp_directory_path();
    for (unsigned attempt = 0; attempt < 128; ++attempt) {
        const auto path = parent / (prefix + "-" + std::to_string(process) + "-" +
                                    std::to_string(stamp) + "-" + std::to_string(++sequence));
        std::error_code error;
        if (std::filesystem::create_directory(path, error))
            return path;
        if (error && error != std::errc::file_exists)
            throw std::filesystem::filesystem_error("Cannot create test directory", path, error);
    }
    throw std::filesystem::filesystem_error("Test directory collision limit", parent,
                                            std::make_error_code(std::errc::file_exists));
}

}  // namespace cppulse::test
#endif
