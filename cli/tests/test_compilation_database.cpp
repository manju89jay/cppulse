/** @file test_compilation_database.cpp
 * @brief End-to-end CLI option regression using a local argv-capturing analyzer.
 */
#include <gtest/gtest.h>

#include <chrono>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

#include "orchestrator.h"

#ifndef _WIN32
namespace {

/** @brief Quote test paths for the POSIX command runner without PATH changes. */
std::string quote_path(const std::filesystem::path& path) {
    std::string quoted{"'"};
    for (const auto character : path.string()) {
        quoted += character == '\'' ? "'\\''" : std::string(1, character);
    }
    return quoted + "'";
}

/** @brief Isolated local executable and source paths for CLI contract tests. */
class CompilationDatabaseCliTest : public ::testing::Test {
   protected:
    void SetUp() override {
        const auto nonce = std::chrono::steady_clock::now().time_since_epoch().count();
        root_ = std::filesystem::temp_directory_path() /
                ("cppulse_cli_database_" + std::to_string(nonce));
        project_ = root_ / "checkout with spaces";
        repo_ = root_ / "source with spaces";
        output_ = root_ / "output with spaces";
        capture_ = root_ / "captured arguments.txt";
        std::filesystem::create_directories(project_ / "analyzer-core/build");
        std::filesystem::create_directories(repo_);
        const auto analyzer = project_ / "analyzer-core/build/cppulse-analyzer";
        std::ofstream script(analyzer);
        script << "#!/bin/sh\nprintf '%s\\n' \"$@\" > " << quote_path(capture_) << "\n";
        script.close();
        std::filesystem::permissions(analyzer, std::filesystem::perms::owner_exec |
                                                   std::filesystem::perms::owner_read |
                                                   std::filesystem::perms::owner_write);
    }

    void TearDown() override {
        std::error_code error;
        std::filesystem::remove_all(root_, error);
    }

    std::vector<std::string> captured_arguments() const {
        std::ifstream stream(capture_);
        std::vector<std::string> result;
        std::string line;
        while (std::getline(stream, line)) {
            result.push_back(line);
        }
        return result;
    }

    std::filesystem::path root_;
    std::filesystem::path project_;
    std::filesystem::path repo_;
    std::filesystem::path output_;
    std::filesystem::path capture_;
};

TEST_F(CompilationDatabaseCliTest, AnalyzeForwardsDatabaseFileAsOneArgument) {
    const auto database = root_ / "build with 'quotes'" / "compile_commands.json";
    std::filesystem::create_directories(database.parent_path());
    std::ofstream(database) << "[]\n";
    const auto caller_relative = std::filesystem::relative(database);
    cppulse::Orchestrator command_runner{{}, {}};
    const auto result = command_runner.run_command(
        quote_path(CPPULSE_CLI_EXECUTABLE) + " --project-root " + quote_path(project_) +
            " analyze --repo " + quote_path(repo_) + " --output " + quote_path(output_) +
            " --compilation-database " + quote_path(caller_relative),
        "test-compilation-database");
    // The missing fake git-miner intentionally ends the pipeline. The local
    // analyzer must still receive exact argv without using a global analyzer.
    EXPECT_FALSE(result.success);
    const auto arguments = captured_arguments();
    ASSERT_EQ(arguments.size(), 6u);
    EXPECT_EQ(arguments[0], "--repo");
    EXPECT_EQ(arguments[1], repo_.string());
    EXPECT_EQ(arguments[2], "--output");
    EXPECT_EQ(arguments[3], output_.string());
    EXPECT_EQ(arguments[4], "--compilation-database");
    EXPECT_EQ(arguments[5], database.string());
}

TEST_F(CompilationDatabaseCliTest, WatchHelpExposesDatabaseOption) {
    cppulse::Orchestrator command_runner{{}, {}};
    const auto result = command_runner.run_command(
        quote_path(CPPULSE_CLI_EXECUTABLE) + " watch --help", "test-watch-database-help");
    EXPECT_TRUE(result.success);
    // run_command logs successful output; ask the shell to require the option
    // without parsing any source files or starting the indefinite watch loop.
    const auto help_file = root_ / "watch-help.txt";
    ASSERT_TRUE(command_runner
                    .run_command(quote_path(CPPULSE_CLI_EXECUTABLE) + " watch --help > " +
                                     quote_path(help_file),
                                 "test-watch-help-capture")
                    .success);
    std::ifstream stream(help_file);
    const std::string help{std::istreambuf_iterator<char>(stream),
                           std::istreambuf_iterator<char>()};
    EXPECT_NE(help.find("--compilation-database"), std::string::npos);
}

}  // namespace
#endif

#ifndef _WIN32
namespace {
TEST_F(CompilationDatabaseCliTest, AnalyzerForwardsCallerRelativeDirectoryAndConfig) {
    const auto database_dir = root_ / "external build with spaces";
    std::filesystem::create_directories(database_dir);
    const auto config = root_ / "config with spaces.json";
    std::ofstream(config) << "{}\n";
    cppulse::Orchestrator orchestrator{
        repo_,  output_,           project_,
        config, "safety-critical", std::filesystem::relative(database_dir)};
    ASSERT_TRUE(orchestrator.run_analyzer().success);
    const auto arguments = captured_arguments();
    ASSERT_EQ(arguments.size(), 8u);
    EXPECT_EQ(arguments[4], "--config");
    EXPECT_EQ(arguments[5], config.string());
    EXPECT_EQ(arguments[6], "--compilation-database");
    EXPECT_EQ(arguments[7], database_dir.string());
}
}  // namespace
#endif
