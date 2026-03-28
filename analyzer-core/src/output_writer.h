/**
 * @file output_writer.h
 * @brief Serializes a collection of findings to a findings.json file.
 *
 * The output format matches docs/schemas/findings.schema.json version 1.0.0.
 */

#ifndef CPPULSE_OUTPUT_WRITER_H
#define CPPULSE_OUTPUT_WRITER_H

#include <filesystem>
#include <string>
#include <vector>

#include "finding.h"

namespace cppulse {

/**
 * @brief Write findings to a JSON file conforming to findings.schema.json.
 *
 * Creates the output directory if it does not exist.  Overwrites any
 * existing findings.json in that directory.
 *
 * @param findings      All findings from the analysis run.
 * @param repo_path     The root path that was analyzed (stored in metadata).
 * @param file_count    Number of source files analyzed.
 * @param total_loc     Total lines of code across all analyzed files.
 * @param output_dir    Directory where findings.json will be written.
 * @return              true on success, false on I/O error.
 */
[[nodiscard]] bool write_findings_json(const std::vector<Finding>& findings,
                                       const std::string& repo_path, int file_count, int total_loc,
                                       const std::filesystem::path& output_dir);

}  // namespace cppulse

#endif  // CPPULSE_OUTPUT_WRITER_H
