#pragma once

/// @brief Authored finite example; clamp a selected integer to zero or above.
constexpr int clamp_nonnegative(int value) noexcept {
  return value < 0 ? 0 : value;
}
