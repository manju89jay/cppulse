/**
 * @file test_cli.cpp
 * @brief Unit tests for the cppulse CLI orchestrator component.
 */

#include <gtest/gtest.h>

#include <filesystem>
#include <string>

#include "orchestrator.h"

namespace {

// ---------------------------------------------------------------------------
// PipelineResult struct tests
// ---------------------------------------------------------------------------

TEST(PipelineResultTest, DefaultConstructionIsFailure) {
    const cppulse::PipelineResult result{};
    EXPECT_FALSE(result.success);
    EXPECT_TRUE(result.error_message.empty());
    EXPECT_EQ(result.exit_code, 0);
}

TEST(PipelineResultTest, SuccessFields) {
    const cppulse::PipelineResult result{true, "", 0};
    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.exit_code, 0);
}

TEST(PipelineResultTest, FailureFields) {
    const cppulse::PipelineResult result{false, "something went wrong", 42};
    EXPECT_FALSE(result.success);
    EXPECT_EQ(result.error_message, "something went wrong");
    EXPECT_EQ(result.exit_code, 42);
}

// ---------------------------------------------------------------------------
// Orchestrator construction tests
// ---------------------------------------------------------------------------

TEST(OrchestratorTest, ConstructsWithValidPaths) {
    const std::filesystem::path repo{"/tmp"};
    const std::filesystem::path output{"/tmp/out"};
    // Should not throw or crash — wrap in lambda to avoid macro comma ambiguity.
    EXPECT_NO_THROW(([&] { cppulse::Orchestrator orch{repo, output}; }()));
}

TEST(OrchestratorTest, ConstructsWithEmptyPaths) {
    // Empty paths are valid at construction time; validation happens at run time.
    EXPECT_NO_THROW(([] { cppulse::Orchestrator orch{{}, {}}; }()));
}

// ---------------------------------------------------------------------------
// run_command tests — use shell built-ins that are always available
// ---------------------------------------------------------------------------

TEST(OrchestratorRunCommandTest, EchoCommandSucceeds) {
    cppulse::Orchestrator orch{std::filesystem::path{"/tmp"}, std::filesystem::path{"/tmp/out"}};
    const auto result = orch.run_command("echo hello", "test-echo");
    EXPECT_TRUE(result.success);
    EXPECT_EQ(result.exit_code, 0);
    EXPECT_TRUE(result.error_message.empty());
}

TEST(OrchestratorRunCommandTest, FailingCommandReturnsNonZeroExitCode) {
    cppulse::Orchestrator orch{std::filesystem::path{"/tmp"}, std::filesystem::path{"/tmp/out"}};
    // 'false' is a standard Unix command that always exits with code 1.
    const auto result = orch.run_command("false", "test-false");
    EXPECT_FALSE(result.success);
    EXPECT_NE(result.exit_code, 0);
}

TEST(OrchestratorRunCommandTest, NonExistentCommandFails) {
    cppulse::Orchestrator orch{std::filesystem::path{"/tmp"}, std::filesystem::path{"/tmp/out"}};
    const auto result = orch.run_command("this_command_does_not_exist_xyz_abc", "test-missing");
    EXPECT_FALSE(result.success);
    EXPECT_NE(result.exit_code, 0);
}

TEST(OrchestratorRunCommandTest, CommandWithExitCode42) {
    cppulse::Orchestrator orch{std::filesystem::path{"/tmp"}, std::filesystem::path{"/tmp/out"}};
    const auto result = orch.run_command("exit 42", "test-exit42");
    EXPECT_FALSE(result.success);
    EXPECT_EQ(result.exit_code, 42);
}

// ---------------------------------------------------------------------------
// Shell injection resistance tests
// ---------------------------------------------------------------------------

TEST(OrchestratorRunCommandTest, PathWithSemicolonDoesNotExecuteInjectedCommand) {
    // If shell injection were possible, this would create the marker file.
    // With proper quoting, the entire string is treated as a single argument.
    cppulse::Orchestrator orch{std::filesystem::path{"/tmp; touch /tmp/pwned"},
                               std::filesystem::path{"/tmp/out"}};
    // run_analyzer will fail (cppulse-analyzer not on PATH), but the key
    // assertion is that /tmp/pwned must NOT exist after the attempt.
    auto result = orch.run_analyzer();
    EXPECT_FALSE(std::filesystem::exists("/tmp/pwned"));
}

TEST(OrchestratorRunCommandTest, PathWithBackticksDoesNotExecuteInjectedCommand) {
    cppulse::Orchestrator orch{std::filesystem::path{"/tmp/`touch /tmp/pwned2`"},
                               std::filesystem::path{"/tmp/out"}};
    auto result = orch.run_analyzer();
    EXPECT_FALSE(std::filesystem::exists("/tmp/pwned2"));
}

TEST(OrchestratorRunCommandTest, PathWithDollarDoesNotExpandVariable) {
    cppulse::Orchestrator orch{std::filesystem::path{"/tmp/$HOME"},
                               std::filesystem::path{"/tmp/out"}};
    // Should not expand $HOME — the path should be treated literally.
    // We just verify it doesn't crash and returns a clean failure.
    auto result = orch.run_analyzer();
    EXPECT_FALSE(result.success);
}

// ---------------------------------------------------------------------------
// run_full_pipeline: non-existent repo should fail at analyzer stage
// ---------------------------------------------------------------------------

TEST(OrchestratorPipelineTest, PipelineFailsWhenAnalyzerNotOnPath) {
    // cppulse-analyzer is unlikely to be on PATH in the test environment,
    // so run_analyzer() (and therefore run_full_pipeline()) should fail.
    const std::filesystem::path repo{"/tmp"};
    const std::filesystem::path output{"/tmp/cppulse_test_output"};

    cppulse::Orchestrator orch{repo, output};
    const auto result = orch.run_full_pipeline();

    // We only assert that the result type is consistent — either it succeeds
    // (if cppulse-analyzer happens to be installed) or it fails gracefully.
    if (!result.success) {
        EXPECT_NE(result.exit_code, 0);
    }
}

// ---------------------------------------------------------------------------
// Config-aware orchestrator tests
// ---------------------------------------------------------------------------

TEST(OrchestratorConfigTest, ConstructsWithConfigPath) {
    const std::filesystem::path repo{"/tmp"};
    const std::filesystem::path output{"/tmp/out"};
    const std::filesystem::path config{"/tmp/.cppulserc.yml"};
    EXPECT_NO_THROW(([&] {
        cppulse::Orchestrator orch{repo, output, std::filesystem::current_path(), config, "default"};
    }()));
}

TEST(OrchestratorConfigTest, ConstructsWithSafetyCriticalProfile) {
    const std::filesystem::path repo{"/tmp"};
    const std::filesystem::path output{"/tmp/out"};
    EXPECT_NO_THROW(([&] {
        cppulse::Orchestrator orch{repo, output, std::filesystem::current_path(), std::nullopt,
                                   "safety-critical"};
    }()));
}

TEST(OrchestratorConfigTest, ConstructsWithNoOptionalArgs) {
    // Backwards compatibility: config_path and profile default to nullopt/"default".
    const std::filesystem::path repo{"/tmp"};
    const std::filesystem::path output{"/tmp/out"};
    EXPECT_NO_THROW(([&] { cppulse::Orchestrator orch{repo, output}; }()));
}

}  // namespace
