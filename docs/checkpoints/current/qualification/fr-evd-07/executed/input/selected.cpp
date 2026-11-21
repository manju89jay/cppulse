#include "demo.hpp"

static_assert(SELECTED_MACRO == 7);
static_assert(selected<int>(35) == 42);

int main(int argc, char**) {
    const int supplied = 34 + argc;
    return selected<int>(supplied) == 42 ? 0 : 1;
}
