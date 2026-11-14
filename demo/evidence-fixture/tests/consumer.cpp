#include "cppulse_demo/sum.hpp"

int main() {
#if CPPULSE_DEMO_FAIL_TEST
    return 1;  // Deliberate failure selected by the synthetic demo configuration.
#else
    return cppulse_demo::sum(2, 3) == 5 ? 0 : 1;
#endif
}
