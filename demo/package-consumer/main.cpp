// Selected consumer of pinned installed packages, not an upstream test suite.
#include <cppulse_seed/checked.hpp>
#include <fmt/format.h>
#include <utf8.h>

#include <string>

int main() {
  const std::string greeting{"Hello, C++"};
  if (!utf8::is_valid(greeting.begin(), greeting.end())) {
    return 1;
  }
  const auto length = utf8::distance(greeting.begin(), greeting.end());
  if (cppulse_seed::checked_positive(10) != 10) {
    return 1;
  }
  return fmt::format("{}:{}", greeting, length) == "Hello, C++:10" ? 0 : 1;
}
