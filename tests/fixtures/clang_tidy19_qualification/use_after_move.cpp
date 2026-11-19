// Controlled clang-tidy 19.1.7 cases; each CASE selects one observed context.
#include <utility>

struct Item {
  Item() = default;
  Item(Item &&) = default;
  Item &operator=(Item &&) = default;
  int read() const;
};
void consume(Item);

#if defined(CASE_POSITIVE)
int positive() {
  Item item;
  consume(std::move(item));
  return item.read();  // EXPECT: bugprone-use-after-move
}
#elif defined(CASE_REINITIALIZED)
int reinitialized() {
  Item item;
  consume(std::move(item));
  item = Item{};
  return item.read();
}
#elif defined(CASE_EXCLUSIVE_BRANCH)
int exclusive_branch(bool selected) {
  Item item;
  if (selected) {
    consume(std::move(item));
  } else {
    return item.read();
  }
  return 0;
}
#elif defined(CASE_CORRELATED_CONDITIONS)
int correlated_conditions(int selected) {
  Item item;
  if (selected == 1) consume(std::move(item));
  if (selected == 2) return item.read();  // KNOWN LIMIT: flow-, not path-sensitive
  return 0;
}
#elif defined(CASE_MEMBER_GLOBAL)
Item global_item;
int global_move() {
  consume(std::move(global_item));
  return global_item.read();  // Member/global moves are not covered by this check.
}
struct Holder {
  Item member;
  int member_move() {
    consume(std::move(member));
    return member.read();
  }
};
#else
#error Select exactly one qualification CASE
#endif
