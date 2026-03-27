// Test fixture: MISRA rule violations.
// Expected findings: MISRA-001 (goto), MISRA-003 (union), MISRA-004 (malloc/free),
//                    MISRA-005 (recursion), MISRA-006 (multiple returns)

#include <cstdlib>

// MISRA-003: union declaration
union DataUnion {
    int   integer_val;
    float float_val;
    char  bytes[4];
};

// MISRA-001: goto statement
void goto_example(int value) {
    if (value > 0) {
        goto done;
    }
    value = 0;
done:
    static_cast<void>(value);
}

// MISRA-004: malloc and free
void malloc_example() {
    void* ptr = malloc(128);
    static_cast<void>(ptr);
    free(ptr);
}

// MISRA-005: recursive function
int factorial(int n) {
    if (n <= 1) {
        return 1;
    }
    return n * factorial(n - 1);  // MISRA-005: recursion
}

// MISRA-006: multiple return statements
int multiple_returns(int x) {
    if (x < 0) {
        return -1;   // First return
    }
    if (x == 0) {
        return 0;    // Second return
    }
    return 1;        // Third return
}
