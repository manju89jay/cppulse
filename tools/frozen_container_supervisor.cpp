// Keep a finite native observation's tmpfs output alive until owned cleanup.
// This helper does not establish a runtime closure or aggregate resource limits.
#include <cerrno>
#include <algorithm>
#include <array>
#include <dirent.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <limits.h>
#include <signal.h>
#include <string>
#include <vector>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

namespace {
void terminate(int number) { _exit(128 + number); }

bool write_all(int fd, const char* data, size_t size) {
    while (size != 0) {
        const ssize_t count = write(fd, data, size);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) return false;
        data += count;
        size -= static_cast<size_t>(count);
    }
    return true;
}

int open_parent(const char* path, char* name) {
    const std::string selected(path);
    if (selected.empty() || selected[0] != '/' || selected.back() == '/' ||
        selected.find("//") != std::string::npos || selected.size() >= PATH_MAX) return -1;
    char copied[PATH_MAX];
    std::strcpy(copied, path + 1);
    int fd = open("/", O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    char* save = nullptr;
    char* token = strtok_r(copied, "/", &save);
    if (!token) { close(fd); return -1; }
    while (token) {
        if (!std::strcmp(token, ".") || !std::strcmp(token, "..")) {
            close(fd); return -1;
        }
        char* next = strtok_r(nullptr, "/", &save);
        if (!next) { std::strcpy(name, token); return fd; }
        const int selected = openat(fd, token, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
        close(fd);
        if (selected < 0) return -1;
        fd = selected;
        token = next;
    }
    close(fd);
    return -1;
}

bool same(const struct stat& left, const struct stat& right) {
    return left.st_dev == right.st_dev && left.st_ino == right.st_ino &&
        left.st_mode == right.st_mode && left.st_size == right.st_size &&
        left.st_mtim.tv_sec == right.st_mtim.tv_sec && left.st_mtim.tv_nsec == right.st_mtim.tv_nsec &&
        left.st_ctim.tv_sec == right.st_ctim.tv_sec && left.st_ctim.tv_nsec == right.st_ctim.tv_nsec;
}

int read_status(const char* path) {
    char name[PATH_MAX];
    const int parent = open_parent(path, name);
    if (parent < 0) return 74;
    struct stat selected_parent{};
    if (fstat(parent, &selected_parent) != 0) { close(parent); return 74; }
    const int fd = openat(parent, name, O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC);
    if (fd < 0) { const int code = errno == ENOENT ? 1 : 74; close(parent); return code; }
    struct stat before{}, after{}, current{};
    std::array<char, 4096> buffer{};
    int code = 74;
    if (fstat(fd, &before) == 0 && S_ISREG(before.st_mode) && before.st_size >= 2 && before.st_size <= 4096) {
        size_t used = 0;
        while (used < static_cast<size_t>(before.st_size)) {
            const ssize_t count = read(fd, buffer.data() + used, static_cast<size_t>(before.st_size) - used);
            if (count < 0 && errno == EINTR) continue;
            if (count <= 0) break;
            used += static_cast<size_t>(count);
        }
        char current_name[PATH_MAX];
        const int current_parent = open_parent(path, current_name);
        struct stat parent_after{};
        const bool parent_matches = current_parent >= 0 && fstat(current_parent, &parent_after) == 0 &&
            same(selected_parent, parent_after);
        if (current_parent >= 0) close(current_parent);
        if (parent_matches && used == static_cast<size_t>(before.st_size) && fstat(fd, &after) == 0 && same(before, after) &&
            fstatat(parent, name, &current, AT_SYMLINK_NOFOLLOW) == 0 && same(before, current) &&
            write_all(STDOUT_FILENO, buffer.data(), used)) code = 0;
    }
    close(fd); close(parent);
    return code;
}

struct OutputEntry { std::string name; struct stat selected; };

bool inventory(int directory, const std::string& prefix, unsigned depth,
               std::vector<OutputEntry>& entries, size_t& payload) {
    if (depth > 32) return false;
    const int copied = dup(directory);
    if (copied < 0) return false;
    DIR* stream = fdopendir(copied);
    if (!stream) { close(copied); return false; }
    bool valid = true;
    errno = 0;
    while (const auto* row = readdir(stream)) {
        const std::string name(row->d_name);
        if (name == "." || name == "..") continue;
        const std::string relative = prefix + name;
        struct stat selected{};
        if (relative.size() > 99 || entries.size() >= 512 ||
            std::any_of(name.begin(), name.end(), [](unsigned char c) { return c < 32 || c > 126 || c == '\\'; }) ||
            fstatat(directory, name.c_str(), &selected, AT_SYMLINK_NOFOLLOW) != 0 ||
            (!S_ISREG(selected.st_mode) && !S_ISDIR(selected.st_mode)) || selected.st_mtim.tv_sec < 0) {
            valid = false; break;
        }
        entries.push_back({relative, selected});
        if (S_ISREG(selected.st_mode)) {
            if (selected.st_size < 0 || static_cast<unsigned long long>(selected.st_size) > 8 * 1024 * 1024 - payload) {
                valid = false; break;
            }
            payload += static_cast<size_t>(selected.st_size);
        } else {
            const int child = openat(directory, name.c_str(), O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
            if (child < 0) { valid = false; break; }
            struct stat actual{};
            valid = fstat(child, &actual) == 0 && same(selected, actual) &&
                inventory(child, relative + "/", depth + 1, entries, payload);
            close(child);
            if (!valid) break;
        }
        errno = 0;
    }
    if (errno != 0) valid = false;
    closedir(stream);
    return valid;
}

int open_output_entry(int root, const std::string& relative) {
    int parent = dup(root);
    size_t start = 0;
    while (parent >= 0) {
        const size_t slash = relative.find('/', start);
        const auto piece = relative.substr(start, slash == std::string::npos ? slash : slash - start);
        const int next = openat(parent, piece.c_str(), O_RDONLY | O_NOFOLLOW | O_NONBLOCK | O_CLOEXEC |
                                (slash == std::string::npos ? 0 : O_DIRECTORY));
        close(parent);
        if (slash == std::string::npos) return next;
        parent = next; start = slash + 1;
    }
    return -1;
}

bool octal(char* field, size_t width, unsigned long long value) {
    return std::snprintf(field, width, "%0*llo", static_cast<int>(width - 1), value) == static_cast<int>(width - 1);
}

int archive_output(const char* path) {
    char basename[PATH_MAX];
    const int parent = open_parent(path, basename);
    if (parent < 0) return 74;
    const int root = openat(parent, basename, O_RDONLY | O_DIRECTORY | O_NOFOLLOW | O_CLOEXEC);
    close(parent);
    if (root < 0) return 74;
    struct stat selected_root{};
    std::vector<OutputEntry> entries;
    size_t payload = 0;
    bool valid = fstat(root, &selected_root) == 0 && inventory(root, "", 0, entries, payload);
    std::sort(entries.begin(), entries.end(), [](const auto& a, const auto& b) { return a.name < b.name; });
    const std::array<char, 1024> zeros{};
    for (const auto& entry : entries) {
        if (!valid) break;
        const int fd = open_output_entry(root, entry.name);
        struct stat before{}, after{};
        if (fd < 0 || fstat(fd, &before) != 0 || !same(before, entry.selected)) {
            if (fd >= 0) close(fd);
            valid = false; break;
        }
        std::array<char, 512> header{};
        std::memcpy(header.data(), entry.name.data(), entry.name.size());
        const bool regular = S_ISREG(before.st_mode);
        valid = octal(header.data()+100, 8, before.st_mode & 0777) && octal(header.data()+108, 8, 1000) &&
            octal(header.data()+116, 8, 1000) && octal(header.data()+124, 12, regular ? before.st_size : 0) &&
            octal(header.data()+136, 12, before.st_mtim.tv_sec);
        header[156] = regular ? '0' : '5';
        std::memcpy(header.data()+257, "ustar", 5);
        std::memcpy(header.data()+263, "00", 2);
        std::memset(header.data()+148, ' ', 8);
        unsigned checksum = 0;
        for (unsigned char byte : header) checksum += byte;
        std::snprintf(header.data()+148, 7, "%06o", checksum); header[155] = ' ';
        valid = valid && write_all(STDOUT_FILENO, header.data(), header.size());
        std::array<char, 65536> buffer{};
        size_t remaining = regular ? static_cast<size_t>(before.st_size) : 0;
        while (valid && remaining) {
            const ssize_t count = read(fd, buffer.data(), std::min(remaining, buffer.size()));
            if (count < 0 && errno == EINTR) continue;
            if (count <= 0) { valid = false; break; }
            valid = write_all(STDOUT_FILENO, buffer.data(), static_cast<size_t>(count));
            remaining -= static_cast<size_t>(count);
        }
        valid = valid && fstat(fd, &after) == 0 && same(before, after);
        close(fd);
        const size_t padding = regular ? (512 - (static_cast<size_t>(before.st_size) % 512)) % 512 : 0;
        valid = valid && write_all(STDOUT_FILENO, zeros.data(), padding);
    }
    struct stat final_root{};
    for (const auto& entry : entries) {
        if (!valid) break;
        const int current = open_output_entry(root, entry.name);
        struct stat selected{};
        valid = current >= 0 && fstat(current, &selected) == 0 && same(entry.selected, selected);
        if (current >= 0) close(current);
    }
    char final_name[PATH_MAX];
    const int final_parent = open_parent(path, final_name);
    valid = valid && fstat(root, &final_root) == 0 && same(selected_root, final_root) && final_parent >= 0;
    if (final_parent >= 0) {
        struct stat current{};
        valid = valid && fstatat(final_parent, final_name, &current, AT_SYMLINK_NOFOLLOW) == 0 && same(selected_root, current);
        close(final_parent);
    }
    close(root);
    return valid && write_all(STDOUT_FILENO, zeros.data(), zeros.size()) ? 0 : 74;
}
} // namespace

int main(int argc, char** argv) {
    if (argc < 3 || argv[2][0] != '/') return 64;
    if (!std::strcmp(argv[1], "--read-status")) return argc == 3 ? read_status(argv[2]) : 64;
    if (!std::strcmp(argv[1], "--archive-output")) return argc == 3 ? archive_output(argv[2]) : 64;
    // PID 1 otherwise ignores default terminating signals in a container.
    struct sigaction action{};
    action.sa_handler = terminate;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGTERM, &action, nullptr) != 0 ||
        sigaction(SIGINT, &action, nullptr) != 0) return 71;
    char name[PATH_MAX];
    const int parent = open_parent(argv[1], name);
    if (parent < 0) return 73;
    struct stat selected_parent{};
    if (fstat(parent, &selected_parent) != 0) { close(parent); return 73; }
    auto parent_bound = [&]() {
        char current_name[PATH_MAX];
        const int current = open_parent(argv[1], current_name);
        if (current < 0) return false;
        struct stat observed{};
        const bool matches = fstat(current, &observed) == 0 &&
            observed.st_dev == selected_parent.st_dev && observed.st_ino == selected_parent.st_ino;
        close(current);
        return matches;
    };
    struct stat existing{};
    if (fstatat(parent, name, &existing, AT_SYMLINK_NOFOLLOW) == 0 || errno != ENOENT) {
        close(parent); return 73;
    }
    char partial[PATH_MAX];
    if (std::snprintf(partial, sizeof(partial), "%s.partial.%ld", name,
                      static_cast<long>(getpid())) >= static_cast<int>(sizeof(partial))) {
        close(parent); return 73;
    }
    const int output = openat(parent, partial, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (output < 0) { close(parent); return 73; }
    const int native_stdout = openat(parent, ".cppulse-native.stdout", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    const int native_stderr = openat(parent, ".cppulse-native.stderr", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC, 0600);
    if (native_stdout < 0 || native_stderr < 0) return 73;
    int error_pipe[2];
    if (pipe2(error_pipe, O_CLOEXEC) != 0) { close(output); close(parent); return 71; }
    const pid_t supervisor = getpid();
    const pid_t child = fork();
    if (child < 0) return 71;
    if (child == 0) {
        close(error_pipe[0]);
        if (dup2(native_stdout, STDOUT_FILENO) < 0 || dup2(native_stderr, STDERR_FILENO) < 0) _exit(126);
        // Also protects the finite host-side tests if their supervisor is killed.
        if (prctl(PR_SET_PDEATHSIG, SIGKILL) != 0 || getppid() != supervisor) _exit(126);
        execv(argv[2], argv + 2);
        const int selected_errno = errno;
        (void)write_all(error_pipe[1], reinterpret_cast<const char*>(&selected_errno), sizeof(selected_errno));
        _exit(127);
    }
    close(error_pipe[1]);
    close(native_stdout); close(native_stderr);
    int exec_errno = 0;
    ssize_t error_size;
    do { error_size = read(error_pipe[0], &exec_errno, sizeof(exec_errno)); }
    while (error_size < 0 && errno == EINTR);
    close(error_pipe[0]);
    int status = 0;
    pid_t waited;
    do { waited = waitpid(child, &status, 0); } while (waited < 0 && errno == EINTR);
    if (waited != child || error_size < 0 || (error_size != 0 && error_size != sizeof(exec_errno))) return 71;
    char exit_code[32], native_signal[32], exec_error[32], document[256];
    if (WIFEXITED(status)) std::snprintf(exit_code, sizeof(exit_code), "%d", WEXITSTATUS(status));
    else std::strcpy(exit_code, "null");
    if (WIFSIGNALED(status)) std::snprintf(native_signal, sizeof(native_signal), "%d", WTERMSIG(status));
    else std::strcpy(native_signal, "null");
    if (error_size != 0) std::snprintf(exec_error, sizeof(exec_error), "%d", exec_errno);
    else std::strcpy(exec_error, "null");
    const int length = std::snprintf(document, sizeof(document),
        "{\"version\":\"0.1.0\",\"native_exit_code\":%s,\"native_signal\":%s,\"native_exec_errno\":%s}\n",
        exit_code, native_signal, exec_error);
    if (length <= 0 || length >= static_cast<int>(sizeof(document)) ||
        !write_all(output, document, static_cast<size_t>(length)) ||
        fchmod(output, 0400) != 0 || fsync(output) != 0) return 74;
    struct stat retained{}, witness{};
    if (fstat(output, &retained) != 0 ||
        fstatat(parent, partial, &witness, AT_SYMLINK_NOFOLLOW) != 0 ||
        retained.st_dev != witness.st_dev || retained.st_ino != witness.st_ino ||
        retained.st_size != length || retained.st_nlink != 1 ||
        !parent_bound()) return 74;
    char descriptor_path[64];
    std::snprintf(descriptor_path, sizeof(descriptor_path), "/proc/self/fd/%d", output);
    // Publish the held descriptor's bytes, never a second lookup of partial.
    if (linkat(AT_FDCWD, descriptor_path, parent, name, AT_SYMLINK_FOLLOW) != 0) return 74;
    struct stat published{};
    const bool final_owned = fstatat(parent, name, &published, AT_SYMLINK_NOFOLLOW) == 0 &&
        retained.st_dev == published.st_dev && retained.st_ino == published.st_ino;
    const bool witness_owned = fstatat(parent, partial, &witness, AT_SYMLINK_NOFOLLOW) == 0 &&
        retained.st_dev == witness.st_dev && retained.st_ino == witness.st_ino;
    if (!final_owned || !witness_owned || !parent_bound() || fsync(parent) != 0) {
        // Roll back only this descriptor's link; preserve any foreign replacement.
        if (final_owned) (void)unlinkat(parent, name, 0);
        return 74;
    }
    close(output);
    close(parent);
    // The hardlink witness is retained. The controller copies output while alive.
    for (;;) pause();
}
