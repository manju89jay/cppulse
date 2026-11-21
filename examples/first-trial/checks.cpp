#include <string_view>

#include "clamp.h"

int main(int argc, char** argv) {
  if (argc != 2) return 2;
  const std::string_view name{argv[1]};
  if (name == "negative") return clamp_nonnegative(-7) == 0 ? 0 : 1;
  if (name == "zero") return clamp_nonnegative(0) == 0 ? 0 : 1;
  if (name == "positive") return clamp_nonnegative(7) == 7 ? 0 : 1;
  return 2;
}
