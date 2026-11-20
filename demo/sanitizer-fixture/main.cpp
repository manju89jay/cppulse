// Explicitly synthetic selected-input checks. They are deliberate runtime
// violations in the "bad" branch, not attributed upstream defects.
#include <climits>

#ifndef CPPULSE_SANITIZER_KIND
#error "Select 1=ASan, 2=UBSan or 3=TSan in the explicit compile recipe"
#endif

#if CPPULSE_SANITIZER_KIND == 3
#include <mutex>
#include <thread>

namespace {
int shared_count = 0;
std::mutex shared_mutex;

void increment(bool unsafe) {
    for (int index = 0; index < 10000; ++index) {
        if (unsafe) {
            shared_count = shared_count + 1;  // Deliberate data race.
        } else {
            const std::lock_guard<std::mutex> lock{shared_mutex};
            shared_count = shared_count + 1;
        }
    }
}
}  // namespace
#endif

#if CPPULSE_USE_PREBUILT
extern int cppulse_prebuilt_read(const int* value);
#endif

int main(int argc, char** argv) {
    if (argc > 1 && argv[1][0] == 's') {
        return 77;  // The driver must retain this as skipped, never a clean pass.
    }
    const bool unsafe = argc > 1 && argv[1][0] == 'b';

#if CPPULSE_USE_PREBUILT
    const int selected_value = 42;
    if (cppulse_prebuilt_read(&selected_value) != 42) {
        return 2;
    }
#endif

#if CPPULSE_SANITIZER_KIND == 1
    int* values = new int[2]{10, 20};
    const volatile int selected_index = unsafe ? 7 : 1;
    const volatile int observed = values[selected_index];  // Deliberate heap overflow if bad.
    (void)observed;
    delete[] values;
#elif CPPULSE_SANITIZER_KIND == 2
    const volatile int left = unsafe ? INT_MAX : 1;
    const volatile int right = 1;
    const volatile int observed = left + right;  // Recovery must not hide this diagnostic.
    (void)observed;
#elif CPPULSE_SANITIZER_KIND == 3
    std::thread first{increment, unsafe};
    std::thread second{increment, unsafe};
    first.join();
    second.join();
#else
#error "Unsupported synthetic sanitizer kind"
#endif
    return 0;
}
