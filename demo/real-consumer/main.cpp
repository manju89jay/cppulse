// Real integration with pinned fmt (compiled) and utfcpp (header-only).
#include <fmt/format.h>
#include <utf8.h>

#include <string>

int main() {
    const std::string greeting = "Hello, C++";
    if (!utf8::is_valid(greeting.begin(), greeting.end())) {
        return 1;
    }
    const auto length = utf8::distance(greeting.begin(), greeting.end());
    return fmt::format("{}:{}", greeting, length) == "Hello, C++:10" ? 0 : 1;
}
