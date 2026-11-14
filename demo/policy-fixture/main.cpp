// Synthetic verification input; the switches deliberately select different cases.
#if CPPULSE_DEMO_PARSE_ERROR
#include "intentionally_missing_demo_header.hpp"
#endif

int main() {
#if CPPULSE_DEMO_TRIGGER_RULE
    int* value = new int(5);  // Intentional rule trigger; not a claimed runtime defect.
    const int result = *value;
    delete value;
    if (result != 5) {
        return 1;
    }
#endif
#if CPPULSE_DEMO_TEST_FAILURE
    return 1;
#else
    return 0;
#endif
}
