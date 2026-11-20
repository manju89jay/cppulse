typedef unsigned long Count;
static_assert(__is_same(Count, unsigned long), "type");
int main() { Count count = 7; return count == 7 ? 0 : 1; }
