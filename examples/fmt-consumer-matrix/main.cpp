#include <fmt/format.h>

#include <iostream>
#include <string_view>

int main(int argc, char* argv[]) {
    if (argc != 2) {
        std::cerr << "Usage: fmt-consumer <expected output>\n";
        return 2;
    }

    const auto actual = fmt::format("answer={:04d}", 42);
    const std::string_view expected(argv[1]);
    if (std::string_view(actual) != expected) {
        std::cerr << "Expected '" << expected << "', got '" << actual << "'\n";
        return 1;
    }

    std::cout << actual << '\n';
    return 0;
}
