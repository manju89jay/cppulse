// Test fixture: memory safety rule violations.
// Expected findings: CPP-MEM-001 (raw new), CPP-MEM-002 (delete), CPP-MEM-003 (C-array param)

#include <cstddef>

// CPP-MEM-001: raw new without smart pointer
void raw_new_example() {
    int* ptr = new int(42);
    static_cast<void>(ptr);
    // Intentionally not deleted to also demonstrate a leak.
}

// CPP-MEM-002: explicit delete
void raw_delete_example() {
    int* ptr = new int(7);
    delete ptr;
}

// CPP-MEM-003: C-style array as function parameter
void process_buffer(int buf[], std::size_t len) {
    static_cast<void>(buf);
    static_cast<void>(len);
}

// CPP-MEM-003: another C-style array param
void read_bytes(unsigned char data[], int count) {
    static_cast<void>(data);
    static_cast<void>(count);
}
