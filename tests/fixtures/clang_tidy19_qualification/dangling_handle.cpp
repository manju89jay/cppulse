// Only the default std::basic_string_view handle class is qualified here.
#include <string>
#include <string_view>

#if defined(CASE_TEMPORARY_OWNER)
unsigned long temporary_owner() {
  std::string_view view = std::string("temporary");  // EXPECT: bugprone-dangling-handle
  return view.size();
}
#elif defined(CASE_PERSISTENT_OWNER)
unsigned long persistent_owner() {
  std::string owner("persistent");
  std::string_view view(owner);
  return view.size();
}
#elif defined(CASE_CUSTOM_HANDLE)
struct UnqualifiedHandle {
  explicit UnqualifiedHandle(const std::string &);
  unsigned long size() const;
};
unsigned long custom_handle_not_qualified() {
  UnqualifiedHandle view{std::string("temporary")};
  return view.size();
}
#else
#error Select exactly one qualification CASE
#endif
