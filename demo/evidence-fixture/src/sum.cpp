#include "cppulse_demo/sum.hpp"

#if CPPULSE_DEMO_COMPILE_ERROR
#error "Intentional synthetic compilation failure selected by demo configuration"
#endif

namespace cppulse_demo {
int sum(int left, int right) noexcept {
    return left + right;
}
}  // namespace cppulse_demo
