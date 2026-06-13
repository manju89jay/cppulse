/**
 * @file file_discovery.h
 * @brief Utility for recursively finding C++ source files in a directory tree.
 */

#ifndef CPPULSE_FILE_DISCOVERY_H
#define CPPULSE_FILE_DISCOVERY_H

#include <filesystem>
#include <vector>

namespace cppulse {

/**
 * @brief Recursively discover all C++ source files under a root directory.
 *
 * Accepted extensions: .cpp, .cxx, .cc, .h, .hpp, .hxx
 * Symbolic links are followed.  Non-existent or non-directory roots return an
 * empty vector.  Machine-generated sources (see is_generated_source) are
 * skipped — health metrics describe hand-written code, and pathologically
 * large generated translation units (e.g. protobuf/upb headers) can stall the
 * libclang parser.
 *
 * @param root  Directory to search.
 * @return      Sorted list of absolute paths to C++ source files.
 */
[[nodiscard]] std::vector<std::filesystem::path> discover_cpp_files(
    const std::filesystem::path& root);

/**
 * @brief Heuristically decide whether a path is a machine-generated source.
 *
 * Recognizes common code generators: protobuf (`*.pb.h/.cc`), gRPC/upb
 * (`*.upb.h`, `*.upbdefs.*`, `*.upb_minitable.*`, `upb-gen/` dirs),
 * flatbuffers (`*_generated.h`), and Qt (`moc_*`, `qrc_*`, `ui_*`).
 *
 * @param path  File path to classify.
 * @return      True if the file looks generated and should not be analyzed.
 */
[[nodiscard]] bool is_generated_source(const std::filesystem::path& path);

}  // namespace cppulse

#endif  // CPPULSE_FILE_DISCOVERY_H
