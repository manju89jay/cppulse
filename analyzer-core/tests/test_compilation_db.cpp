/**
 * @file test_compilation_db.cpp
 * @brief Tests for compile_commands.json support in FileAnalyzer.
 *
 * The fixture source hides a goto statement behind #ifdef USE_GOTO. Only a
 * compilation database entry providing -DUSE_GOTO makes MISRA-001 fire, which
 * proves the recorded compile arguments were actually used for parsing.
 */

#include <gtest/gtest.h>

#include <algorithm>
#include <filesystem>
#include <fstream>
#include <string>

#include "analyzer.h"

namespace {

constexpr const char* kGuardedGotoSource =
    "#ifdef USE_GOTO\n"             // line 1
    "void buggy() {\n"              // line 2
    "    int counter = 0;\n"        // line 3
    "target_label:\n"               // line 4
    "    ++counter;\n"              // line 5
    "    if (counter < 3) {\n"      // line 6
    "        goto target_label;\n"  // line 7 — expected MISRA-001 location
    "    }\n"
    "}\n"
    "#else\n"
    "void clean_function() {}\n"
    "#endif\n";

constexpr int kExpectedGotoLine = 7;

/// @brief RAII fixture directory holding sample.cpp (and optionally a DB).
class CompilationDbFixture {
   public:
    explicit CompilationDbFixture(const std::string& dir_name) {
        dir_ = std::filesystem::temp_directory_path() / dir_name;
        std::filesystem::remove_all(dir_);
        std::filesystem::create_directories(dir_);

        source_path_ = dir_ / "sample.cpp";
        std::ofstream source_stream(source_path_);
        source_stream << kGuardedGotoSource;
    }

    ~CompilationDbFixture() {
        std::error_code ec;
        std::filesystem::remove_all(dir_, ec);  // Best-effort cleanup.
    }

    CompilationDbFixture(const CompilationDbFixture&) = delete;
    CompilationDbFixture& operator=(const CompilationDbFixture&) = delete;

    /// @brief Write compile_commands.json recording -DUSE_GOTO for the given file.
    void write_database_for(const std::filesystem::path& recorded_file) const {
        const std::string dir_json = dir_.generic_string();
        const std::string file_json = recorded_file.generic_string();
        std::ofstream db_stream(dir_ / "compile_commands.json");
        db_stream << "[{\"directory\": \"" << dir_json << "\", \"file\": \"" << file_json
                  << "\", \"arguments\": [\"clang++\", \"-std=c++17\", \"-DUSE_GOTO\", \"-c\", \""
                  << file_json << "\"]}]\n";
    }

    [[nodiscard]] const std::filesystem::path& dir() const noexcept {
        return dir_;
    }

    [[nodiscard]] const std::filesystem::path& source_path() const noexcept {
        return source_path_;
    }

   private:
    std::filesystem::path dir_;
    std::filesystem::path source_path_;
};

/// @brief Count findings with the given rule id.
int count_rule(const std::vector<cppulse::Finding>& findings, const std::string& rule_id) {
    return static_cast<int>(
        std::count_if(findings.begin(), findings.end(),
                      [&rule_id](const cppulse::Finding& f) { return f.rule_id == rule_id; }));
}

TEST(CompilationDbTest, UsesRecordedArgsAndDetectsGuardedGoto) {
    const CompilationDbFixture fixture{"cppulse_test_compdb_used"};
    fixture.write_database_for(fixture.source_path());

    cppulse::FileAnalyzer analyzer{fixture.dir()};
    analyzer.run();

    EXPECT_EQ(analyzer.db_parsed_count(), 1);
    EXPECT_EQ(analyzer.fallback_parsed_count(), 0);

    ASSERT_EQ(count_rule(analyzer.findings(), "MISRA-001"), 1)
        << "-DUSE_GOTO from compile_commands.json was not applied";
    const auto goto_finding =
        std::find_if(analyzer.findings().begin(), analyzer.findings().end(),
                     [](const cppulse::Finding& f) { return f.rule_id == "MISRA-001"; });
    EXPECT_EQ(goto_finding->line, kExpectedGotoLine);
}

TEST(CompilationDbTest, FallsBackToDefaultFlagsWithoutDatabase) {
    const CompilationDbFixture fixture{"cppulse_test_compdb_absent"};

    cppulse::FileAnalyzer analyzer{fixture.dir()};
    analyzer.run();

    EXPECT_EQ(analyzer.db_parsed_count(), 0);
    EXPECT_EQ(analyzer.fallback_parsed_count(), 1);

    // Without -DUSE_GOTO the #else branch (clean code) is compiled.
    EXPECT_EQ(count_rule(analyzer.findings(), "MISRA-001"), 0);
}

TEST(CompilationDbTest, InterpolatesArgsForFileMissingFromDatabase) {
    const CompilationDbFixture fixture{"cppulse_test_compdb_other"};
    // Database records a different file. libclang's interpolating wrapper
    // transfers the closest entry's flags (incl. -DUSE_GOTO) to our file —
    // the behavior that gives headers and new files plausible arguments.
    fixture.write_database_for(fixture.dir() / "unrelated.cpp");

    cppulse::FileAnalyzer analyzer{fixture.dir()};
    analyzer.run();

    EXPECT_EQ(analyzer.db_parsed_count(), 1);
    EXPECT_EQ(analyzer.fallback_parsed_count(), 0);
    EXPECT_EQ(count_rule(analyzer.findings(), "MISRA-001"), 1);
}

TEST(CompilationDbTest, MalformedDatabaseFallsBackWithoutCrashing) {
    const CompilationDbFixture fixture{"cppulse_test_compdb_malformed"};
    {
        std::ofstream db_stream(fixture.dir() / "compile_commands.json");
        db_stream << "this is not json{{{\n";
    }

    cppulse::FileAnalyzer analyzer{fixture.dir()};
    analyzer.run();

    EXPECT_EQ(analyzer.db_parsed_count(), 0);
    EXPECT_EQ(analyzer.fallback_parsed_count(), 1);
    EXPECT_EQ(count_rule(analyzer.findings(), "MISRA-001"), 0);
}

}  // namespace
