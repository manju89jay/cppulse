// Synthetic regression fixture: explicit iterator declarations and already-deduced types.
struct VeryVerboseForwardIteratorForTests {};
VeryVerboseForwardIteratorForTests make_iterator();

void iterator_declarations() {
    VeryVerboseForwardIteratorForTests explicit_iterator = make_iterator();
    auto deduced_iterator = make_iterator();
    const auto const_iterator = make_iterator();
    auto&& reference_iterator = make_iterator();
    decltype(auto) decltype_iterator = make_iterator();
#define DEDUCED_TYPE auto
    DEDUCED_TYPE macro_iterator = make_iterator();
#undef DEDUCED_TYPE
    VeryVerboseForwardIteratorForTests explicit_with_auto_initializer = [] {
        auto nested_deduced_iterator = make_iterator();
        return nested_deduced_iterator;
    }();
}
