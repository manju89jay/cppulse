/**
 * @file output_writer.cpp
 * @brief Implementation of JSON findings serialization.
 */

#include "output_writer.h"

#include <spdlog/spdlog.h>

#include <atomic>
#include <cerrno>
#include <chrono>
#include <fstream>
#include <iomanip>
#include <nlohmann/json.hpp>
#include <sstream>

#include "metrics.h"

#ifdef _WIN32
#include <process.h>
#include <windows.h>
#else
#include <sys/stat.h>
#include <unistd.h>
#endif

namespace cppulse {

namespace {

/// @brief Format the current UTC time as ISO-8601 (e.g. "2026-03-25T14:30:00Z").
std::string utc_timestamp() {
    const auto now = std::chrono::system_clock::now();
    const std::time_t tt = std::chrono::system_clock::to_time_t(now);
    std::tm utc_tm{};
#ifdef _WIN32
    gmtime_s(&utc_tm, &tt);
#else
    gmtime_r(&tt, &utc_tm);
#endif
    std::ostringstream oss;
    oss << std::put_time(&utc_tm, "%Y-%m-%dT%H:%M:%SZ");
    return oss.str();
}

std::filesystem::path pending_path(const std::filesystem::path& output) {
    static std::atomic<std::uint64_t> sequence{0};
#ifdef _WIN32
    const auto process = _getpid();
#else
    const auto process = getpid();
#endif
    return output /
           (".findings.json.partial." + std::to_string(process) + "." + std::to_string(++sequence));
}

// Exclusive directory creation establishes ownership before opening any file.
// Existing staging symlinks/directories are collisions, never cleanup targets.
struct PendingReport {
    std::filesystem::path directory;
    std::filesystem::path path;

    explicit PendingReport(const std::filesystem::path& output) {
        for (unsigned attempt = 0; attempt < 64; ++attempt) {
            auto candidate = pending_path(output);
#ifdef _WIN32
            std::error_code error;
            if (!std::filesystem::create_directory(candidate, error)) {
                if (!error || error == std::errc::file_exists)
                    continue;
                return;
            }
#else
            // mkdir is exclusive and applies owner-only permissions atomically.
            if (::mkdir(candidate.c_str(), S_IRWXU) != 0) {
                if (errno == EEXIST)
                    continue;
                return;
            }
#endif
            directory = std::move(candidate);
            try {
                path = directory / "report.json";
            } catch (...) {
                std::error_code ignored;
                std::filesystem::remove(directory, ignored);
                throw;
            }
            return;
        }
    }
    PendingReport(const PendingReport&) = delete;
    PendingReport& operator=(const PendingReport&) = delete;
    ~PendingReport() noexcept {
        if (!directory.empty()) {
            std::error_code ignored;
            std::filesystem::remove(path, ignored);
            std::filesystem::remove(directory, ignored);
        }
    }
};

bool publish_report(const std::filesystem::path& pending, const std::filesystem::path& final) {
#ifdef _WIN32
    // Windows rename does not replace an existing target; retain atomic replacement.
    if (MoveFileExW(pending.c_str(), final.c_str(),
                    MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
        return true;
    spdlog::error("write_findings_json: cannot publish {}: Windows error {}", final.string(),
                  GetLastError());
    return false;
#else
    std::error_code error;
    std::filesystem::rename(pending, final, error);
    if (!error)
        return true;
    spdlog::error("write_findings_json: cannot publish {}: {}", final.string(), error.message());
    return false;
#endif
}

// The small envelope remains a JSON object; the large metrics inventory is
// streamed directly from its retained rows instead of being copied into it.
void stream_report(std::ostream& stream, const nlohmann::json& root,
                   const AnalysisCoverage* coverage) {
    using Json = nlohmann::json;
    stream << '{';
    bool first = true;
    for (const auto& member : root.items()) {
        if (!first)
            stream << ',';
        first = false;
        stream << Json(member.key()) << ':';
        if (member.key() != "metadata" || coverage == nullptr) {
            stream << member.value();
            continue;
        }
        stream << '{';
        bool first_metadata = true;
        for (const auto& metadata : member.value().items()) {
            if (!first_metadata)
                stream << ',';
            first_metadata = false;
            stream << Json(metadata.key()) << ':';
            if (metadata.key() != "analysis") {
                stream << metadata.value();
                continue;
            }
            stream << '{';
            for (const auto& analysis : metadata.value().items())
                stream << Json(analysis.key()) << ':' << analysis.value() << ',';
            stream << "\"native_metrics\":";
            write_native_metrics(stream, *coverage);
            stream << '}';
        }
        stream << '}';
    }
    stream << "}\n";
}

}  // namespace

bool write_findings_json(const std::vector<Finding>& findings, const std::string& repo_path,
                         int file_count, int total_loc, const std::filesystem::path& output_dir,
                         const AnalysisCoverage* coverage) {
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
    if (coverage != nullptr) {
        auto files = nlohmann::json::array();
        for (const auto& file : coverage->files) {
            nlohmann::json item{{"path", file.path},
                                {"status", file.status},
                                {"compile_context", file.compile_context},
                                {"error_count", file.error_count},
                                {"parse_arguments", nullptr},
                                {"working_directory", nullptr}};
            if (file.parse_arguments.has_value()) {
                item["parse_arguments"] = file.parse_arguments.value();
            }
            if (file.working_directory.has_value()) {
                item["working_directory"] = file.working_directory.value();
            }
            if (file.reason.has_value()) {
                item["reason"] = file.reason.value();
            }
            files.push_back(std::move(item));
        }
        root["metadata"]["analysis"] = {{"enabled_rules", coverage->enabled_rules},
                                        {"files", std::move(files)}};
        if (!coverage->parser_version.empty()) {
            root["metadata"]["analysis"]["parser"] = {{"name", "libclang"},
                                                      {"version", coverage->parser_version}};
        }
    }
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
    const PendingReport pending{output_dir};
    if (pending.path.empty()) {
        spdlog::error("write_findings_json: cannot exclusively create staging directory in {}",
                      output_dir.string());
        return false;
    }
    std::ofstream ofs(pending.path, std::ios::binary | std::ios::trunc);
    if (!ofs) {
        spdlog::error("write_findings_json: cannot open {} for writing", out_file.string());
        return false;
    }
    stream_report(ofs, root, coverage);
    ofs.flush();
    ofs.close();
    if (!ofs) {
        spdlog::error("write_findings_json: write error on {}", out_file.string());
        return false;
    }
    if (!publish_report(pending.path, out_file))
        return false;
    spdlog::info("write_findings_json: wrote {} finding(s) to {}", findings.size(),
                 out_file.string());
    return true;
}

}  // namespace cppulse
