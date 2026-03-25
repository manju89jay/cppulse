// Test fixture: clean modern C++17 code.
// Expected findings: ZERO (this file should produce no findings from any rule).

#include <array>
#include <memory>
#include <string>
#include <variant>
#include <vector>

namespace cppulse::test {

/// @brief A scoped enum — compliant with CPP-MOD-008.
enum class Status { Ok, Error, Pending };

/// @brief A type alias using 'using' — compliant with CPP-MOD-009.
using Buffer = std::vector<std::uint8_t>;

/// @brief Base class with virtual interface.
class Processor {
public:
    virtual ~Processor() = default;
    virtual Status process(const Buffer& data) = 0;
    virtual int get_count() const = 0;
};

/// @brief Derived class with correct 'override' — compliant with CPP-MOD-003.
class ConcreteProcessor : public Processor {
public:
    Status process(const Buffer& data) override {
        count_ += static_cast<int>(data.size());
        return Status::Ok;
    }

    int get_count() const override {
        return count_;
    }

private:
    int count_{0};
};

/// @brief Smart-pointer factory — compliant with CPP-MEM-001/002.
std::unique_ptr<Processor> make_processor() {
    return std::make_unique<ConcreteProcessor>();
}

/// @brief Function using range-based for — compliant with CPP-MOD-006.
int sum_elements(const std::vector<int>& values) {
    int total = 0;
    for (const int val : values) {
        total += val;
    }
    return total;
}

/// @brief Function with nullptr — compliant with CPP-MOD-007.
bool is_valid(const int* ptr) {
    return ptr != nullptr;
}

/// @brief Simple function with few parameters — compliant with CPP-CX-003.
int add(int left, int right) {
    return left + right;
}

/// @brief std::variant usage instead of union — compliant with MISRA-003.
using DataValue = std::variant<int, float, std::string>;

/// @brief Iterative function — compliant with MISRA-005.
int iterative_sum(int n) {
    int result = 0;
    for (int idx = 1; idx <= n; ++idx) {
        result += idx;
    }
    return result;
}

} // namespace cppulse::test
