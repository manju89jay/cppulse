// Executable positive control: original fixed-array accumulation.
namespace metrics {
constexpr int readings[] = {1, 2, 3};
}

int main() {
    const int values[] = {2, 3, 5, 7};
    int total = 0;
    for (int index = 0; index < 4; ++index) {  // EXPECT_RANGE
        total += values[index];
    }
    if (total != 17) {
        return 1;
    }

    const int readings[] = {10, 20, 30};
    int element = 0;
    for (int index = 0; index < 3; ++index) {  // EXPECT_RANGE
        element += metrics::readings[index];
    }
    return element == 6 && readings[0] == 10 ? 0 : 1;
}
