/** @file test_output_streaming.cpp
 * @brief Regression coverage for bounded and atomic report publication.
 */
#include <gtest/gtest.h>

#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>

#include "analysis_coverage.h"
#include "metrics.h"
#include "output_writer.h"
#include "test_temp_directory.h"

#if defined(__linux__)
#include <sys/resource.h>
#include <unistd.h>

#include <csignal>
#endif

namespace {
class StreamingOutputFixture : public ::testing::Test {
   protected:
    void SetUp() override {
        root_ = cppulse::test::make_test_directory("cppulse_streaming");
    }
    void TearDown() override {
        std::error_code ignored;
        std::filesystem::remove_all(root_, ignored);
    }
    std::filesystem::path root_;
};

TEST_F(StreamingOutputFixture, StreamMatchesDocumentForPresentAndUnavailableFacts) {
    cppulse::AnalysisCoverage coverage;
    cppulse::FileCoverage available;
    available.path = "source.cpp";
    available.metrics = {{"payload", "quotes: \"; newline: \n; unicode: é"}};
    coverage.files.push_back(std::move(available));
    cppulse::FileCoverage missing;
    missing.path = "missing.hpp";
    missing.reason = "Not attempted";
    coverage.files.push_back(std::move(missing));
    std::ostringstream stream;
    cppulse::write_native_metrics(stream, coverage);
    EXPECT_EQ(nlohmann::json::parse(stream.str()), cppulse::native_metrics_document(coverage));
}

TEST_F(StreamingOutputFixture, PreexistingStagingPathsAreNeverWrittenOrRemoved) {
#if defined(__linux__)
    const auto victim = root_ / "protected.txt";
    const std::string previous = "protected bytes";
    std::ofstream(victim) << previous;
    const auto prefix = ".findings.json.partial." + std::to_string(getpid()) + ".";
    const auto existing_directory = root_ / (prefix + "1");
    std::filesystem::create_directory(existing_directory);
    // Cover the process-local sequence even when the binary runs its whole suite.
    for (unsigned index = 2; index <= 4096; ++index)
        std::filesystem::create_symlink(victim, root_ / (prefix + std::to_string(index)));
    EXPECT_FALSE(cppulse::write_findings_json({}, "/repo", 0, 0, root_));
    EXPECT_TRUE(std::filesystem::is_directory(existing_directory));
    std::ifstream stream(victim);
    EXPECT_EQ(std::string(std::istreambuf_iterator<char>{stream}, {}), previous);
#else
    GTEST_SKIP() << "Untrusted staging-symlink regression is Linux qualified";
#endif
}

TEST_F(StreamingOutputFixture, FailedWritePreservesPreviouslyPublishedReport) {
#if defined(__linux__)
    const std::string previous = "{\"previous\":\"valid report\"}\n";
    std::ofstream(root_ / "findings.json") << previous;
    cppulse::AnalysisCoverage coverage;
    cppulse::FileCoverage file;
    file.path = "source.cpp";
    file.metrics = {{"payload", std::string(128 * 1024, 'x')}};
    coverage.files.push_back(std::move(file));
    rlimit old{};
    ASSERT_EQ(getrlimit(RLIMIT_FSIZE, &old), 0);
    const auto old_signal = std::signal(SIGXFSZ, SIG_IGN);
    const rlimit bounded{64 * 1024, old.rlim_max};
    ASSERT_EQ(setrlimit(RLIMIT_FSIZE, &bounded), 0);
    const bool written = cppulse::write_findings_json({}, "/repo", 1, 1, root_, &coverage);
    EXPECT_EQ(setrlimit(RLIMIT_FSIZE, &old), 0);
    std::signal(SIGXFSZ, old_signal);
    EXPECT_FALSE(written);
    std::ifstream stream(root_ / "findings.json");
    const std::string actual{std::istreambuf_iterator<char>{stream}, {}};
    EXPECT_EQ(actual, previous);
    EXPECT_EQ(std::distance(std::filesystem::directory_iterator(root_),
                            std::filesystem::directory_iterator{}),
              1);
#else
    GTEST_SKIP() << "Finite output-limit regression is Linux qualified";
#endif
}

TEST_F(StreamingOutputFixture, StreamsRetainedFactsWithinFiniteAdditionalMemory) {
#if defined(__linux__)
    cppulse::AnalysisCoverage coverage;
    cppulse::FileCoverage file;
    file.path = "source.cpp";
    file.metrics = {{"payload", std::string(32 * 1024 * 1024, 'x')}};
    coverage.files.push_back(std::move(file));
    std::ifstream statm{"/proc/self/statm"};
    std::uint64_t pages = 0;
    ASSERT_TRUE(statm >> pages);
    const auto initial = pages * static_cast<std::uint64_t>(sysconf(_SC_PAGESIZE));
    rlimit old{};
    ASSERT_EQ(getrlimit(RLIMIT_AS, &old), 0);
    const rlimit bounded{initial + 24 * 1024 * 1024, old.rlim_max};
    ASSERT_EQ(setrlimit(RLIMIT_AS, &bounded), 0);
    bool written = false;
    try {
        written = cppulse::write_findings_json({}, "/repo", 1, 1, root_, &coverage);
    } catch (...) {
        EXPECT_EQ(setrlimit(RLIMIT_AS, &old), 0);
        throw;
    }
    EXPECT_EQ(setrlimit(RLIMIT_AS, &old), 0);
    EXPECT_TRUE(written);
    ASSERT_TRUE(std::filesystem::is_regular_file(root_ / "findings.json"));
    EXPECT_GT(std::filesystem::file_size(root_ / "findings.json"), 32u * 1024u * 1024u);
    std::ifstream stream(root_ / "findings.json");
    const auto report = nlohmann::json::parse(stream);
    EXPECT_EQ(report["metadata"]["analysis"]["native_metrics"]["files"][0],
              *coverage.files[0].metrics);
#else
    GTEST_SKIP() << "Finite memory regression is Linux qualified";
#endif
}
}  // namespace
