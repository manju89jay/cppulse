// Executable positive control: the suggested equivalent read-only traversal.
namespace metrics {
constexpr int readings[] = {1, 2, 3};
}

int main() {
    const int values[] = {2, 3, 5, 7};
    int total = 0;
    for (const auto& element : values) {
        total += element;
    }
    if (total != 17) {
        return 1;
    }

    const int readings[] = {10, 20, 30};
    int element = 0;
    for (const auto& reading : metrics::readings) {
        element += reading;
    }
    return element == 6 && readings[0] == 10 ? 0 : 1;
}
