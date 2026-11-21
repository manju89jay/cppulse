// Finite modernization precision controls; no claim of overall detector accuracy.
using Discard = void;
typedef void OtherDiscard;

void cast_cases(double value, int* pointer, unsigned long long address) {
    (void)value;
    (Discard)value;
    (OtherDiscard)value;
    static_cast<void>(value);
    const int numeric = (int)value;  // EXPECT_CAST
    const auto pointer_address = (unsigned long long)pointer;  // EXPECT_CAST
    auto* converted = (int*)address;  // EXPECT_CAST
    (void)(int)value;  // EXPECT_CAST: inspect the nested non-void cast
    (Discard)(int)value;  // EXPECT_CAST: canonical void alias does not hide a child
    static_cast<void>((int)value);  // EXPECT_CAST: named outer cast stays unchanged
    (void)numeric;
    (void)pointer_address;
    (void)converted;
}

int fixed_array_sum() {
    const int values[] = {1, 2, 3};
    int total = 0;
    for (int index = 0; index < 3; ++index) {  // EXPECT_RANGE
        total += values[index];
    }
    return total;
}

int fixed_array_postfix_sum() {
    const int values[] = {1, 2, 3};
    int total = 0;
    for (unsigned index = 0; index < 3; index++)  // EXPECT_RANGE
        total += values[index];
    return total;
}

void record_argument(int index, const char* argument);

void argv_index_is_required(int argc, char** argv) {
    for (int index = 0; index < argc; ++index) {
        record_argument(index, argv[index]);
    }
}

int pointer_bound_is_not_a_range(const int* values, int count) {
    int total = 0;
    for (int index = 0; index < count; ++index) {
        total += values[index];
    }
    return total;
}

int literal_pointer_bound_is_not_an_array(const int* values) {
    int total = 0;
    for (int index = 0; index < 3; ++index) {
        total += values[index];
    }
    return total;
}

int array_parameter_decays(int values[3]) {
    int total = 0;
    for (int index = 0; index < 3; ++index) {
        total += values[index];
    }
    return total;
}

int extra_index_use() {
    const int values[] = {1, 2, 3};
    int total = 0;
    for (int index = 0; index < 3; ++index) {
        total += values[index] + index;
    }
    return total;
}

int nonunit_stride() {
    const int values[] = {1, 2, 3};
    int total = 0;
    for (int index = 0; index < 3; index += 2) {
        total += values[index];
    }
    return total;
}

int index_mutates_in_the_body() {
    const int values[] = {1, 2, 3};
    int total = 0;
    for (int index = 0; index < 3; ++index) {
        total += values[index++];
    }
    return total;
}

int index_is_not_the_subscript() {
    const int values[] = {1, 2, 3};
    int total = 0;
    for (int index = 0; index < 3; ++index) {
        total += values[0];
    }
    return total;
}

int partial_array_bound() {
    const int values[] = {1, 2, 3};
    int total = 0;
    for (int index = 0; index < 2; ++index) {
        total += values[index];
    }
    return total;
}

int zero_inside_nonzero_initializer() {
    const int values[] = {1, 2, 3};
    int total = 0;
    for (int index = 1 + 0; index < 3; ++index) {
        total += values[index];
    }
    return total;
}

void element_is_written() {
    int values[] = {1, 2, 3};
    for (int index = 0; index < 3; ++index) {
        values[index] += 1;
    }
}

int volatile_array_is_not_a_const_reference_rewrite() {
    volatile int values[] = {1, 2, 3};
    int total = 0;
    for (int index = 0; index < 3; ++index) {
        total += values[index];
    }
    return total;
}

int alias_accumulator_is_not_proven() {
    int values[] = {1, 2, 3};
    int& total = values[0];
    for (int index = 0; index < 3; ++index) {
        total += values[index];
    }
    return total;
}

void unknown_side_effects_in_body() {
    const int values[] = {1, 2, 3};
    for (int index = 0; index < 3; ++index) {
        record_argument(values[index], "unknown");
    }
}
