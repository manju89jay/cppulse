#pragma once

// Clearly synthetic policy input. This intentional throw is not attributed to
// fmt or utfcpp; -fno-exceptions must expose an observed compilation failure.
namespace cppulse_seed {
inline int checked_positive(int value) {
  if (value < 0) {
    throw value;
  }
  return value;
}
}  // namespace cppulse_seed
