#pragma once

template <typename T>
constexpr T selected(T value) {
    return value + static_cast<T>(SELECTED_MACRO);
}
