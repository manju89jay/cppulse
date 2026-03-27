/**
 * @file output_writer.cpp
 * @brief Implementation of JSON findings serialization.
 */

#include "output_writer.h"

#include <spdlog/spdlog.h>

#include <chrono>
#include <fstream>
#include <iomanip>
#include <nlohmann/json.hpp>
#include <sstream>

namespace cppulse {

namespace {

/// @brief Format the current UTC time as ISO-8601 (e.g. "2026-03-25T14:30:00Z").
std::string utc_timestamp() {
    const auto now = std::chrono::system_clock::now();
    const std::time_t tt = std::chrono::system_clock::to_time_t(now);
    std::tm utc_tm{};
    gmtime_r(&tt, &utc_tm);
    std::ostringstream oss;
    oss << std::put_time(&utc_tm, "%Y-%m-%dT%H:%M:%SZ");
    return oss.str();
}

}  // namespace

bool write_findings_json(const std::vector<Finding>& findings, const std::string& repo_path,
                         int file_count, int total_loc, const std::filesystem::path& output_dir) {
    std::error_code ec;
    std::filesystem::create_directories(output_dir, ec);
    if (ec) {
        spdlog::error("write_findings_json: cannot create output dir {}: {}", output_dir.string(),
                      ec.message());
        return false;
    }

    // -- Build summary counters -------------------------------------------------
    int count_memory_safety = 0;
    int count_modernization = 0;
    int count_complexity = 0;
    int count_misra = 0;
    int count_error = 0;
    int count_warning = 0;
    int count_info = 0;

    nlohmann::json findings_array = nlohmann::json::array();
    for (const auto& f : findings) {
        nlohmann::json item;
        item["rule_id"] = f.rule_id;
        item["category"] = f.category;
        item["severity"] = f.severity;
        item["file"] = f.file;
        item["line"] = f.line;
        if (f.column > 0) {
            item["column"] = f.column;
        }
        if (f.end_line > 0) {
            item["end_line"] = f.end_line;
        }
        item["message"] = f.message;
        if (!f.suggestion.empty()) {
            item["suggestion"] = f.suggestion;
        }
        item["confidence"] = f.confidence;
        findings_array.push_back(std::move(item));

        // Category counters
        if (f.category == "memory_safety") {
            ++count_memory_safety;
        } else if (f.category == "modernization") {
            ++count_modernization;
        } else if (f.category == "complexity") {
            ++count_complexity;
        } else if (f.category == "misra") {
            ++count_misra;
        }

        // Severity counters
        if (f.severity == "error") {
            ++count_error;
        } else if (f.severity == "warning") {
            ++count_warning;
        } else if (f.severity == "info") {
            ++count_info;
        }
    }

    nlohmann::json root;
    root["version"] = "1.0.0";
    root["metadata"] = {{"repo_path", repo_path},
                        {"analyzed_at", utc_timestamp()},
                        {"file_count", file_count},
                        {"total_loc", total_loc}};
    root["findings"] = std::move(findings_array);
    root["summary"] = {
        {"total_findings", static_cast<int>(findings.size())},
        {"by_category",
         {{"memory_safety", count_memory_safety},
          {"modernization", count_modernization},
          {"complexity", count_complexity},
          {"misra", count_misra}}},
        {"by_severity",
         {{"error", count_error}, {"warning", count_warning}, {"info", count_info}}}};

    const std::filesystem::path out_file = output_dir / "findings.json";
    std::ofstream ofs(out_file);
    if (!ofs) {
        spdlog::error("write_findings_json: cannot open {} for writing", out_file.string());
        return false;
    }
    ofs << root.dump(2) << '\n';
    if (!ofs) {
        spdlog::error("write_findings_json: write error on {}", out_file.string());
        return false;
    }
    spdlog::info("write_findings_json: wrote {} finding(s) to {}", findings.size(),
                 out_file.string());
    return true;
}

}  // namespace cppulse
