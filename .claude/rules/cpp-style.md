---
paths:
  - analyzer-core/**/*.cpp
  - analyzer-core/**/*.hpp
  - analyzer-core/**/*.h
  - cli/**/*.cpp
  - cli/**/*.hpp
---

# C++ Style Rules for analyzer-core and cli

## Standard
- C++17. Compiler flags: `-std=c++17 -Wall -Wextra -Werror`

## Memory Management
- NEVER use raw `new` or `delete` — use `std::unique_ptr` / `std::shared_ptr`
- Prefer `std::make_unique<T>()` over `new T()`
- Every resource acquisition must have a corresponding RAII release

## Formatting
- clang-format with Google style (`.clang-format` in repo root)
- Run clang-format before every commit — the auto-lint.sh hook handles this

## Logging
- Use `spdlog` for all logging — NEVER `std::cout` or `printf`
- Log levels: trace (hot loops), debug (per-file), info (per-stage), warn/error (problems)

## Documentation
- Doxygen `@brief` on every public function and class
- `@param` and `@return` for non-obvious parameters
- Implementation comments explain WHY, not WHAT

## Error Handling
- Return `std::expected<T, Error>` for fallible operations (or `std::optional<T>` for simpler cases)
- Never use exceptions across component boundaries
- Handle every error path — no silent failures

## Modern C++ Patterns
- `[[nodiscard]]` on functions whose return value must not be ignored
- `noexcept` on move constructors and destructors
- `constexpr` for compile-time constants
- `std::string_view` for read-only string parameters (avoid copies)
- `std::filesystem::path` for all path operations
