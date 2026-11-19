// No nodiscard attributes: these are configured clang-tidy return-value checks.
namespace qualified {
int status();
struct Error {
  int code;
};
Error make_error();
}  // namespace qualified

#if defined(CASE_IGNORED_FUNCTION)
void ignored_function() {
  qualified::status();  // EXPECT: bugprone-unused-return-value
}
#elif defined(CASE_VOID_CAST)
void void_cast() {
  (void)qualified::status();  // Positive unless AllowCastToVoid is explicitly true.
}
#elif defined(CASE_USED_FUNCTION)
int used_function() { return qualified::status(); }
#elif defined(CASE_IGNORED_TYPE)
void ignored_error_type() {
  qualified::make_error();  // EXPECT: bugprone-unused-return-value with CheckedReturnTypes
}
#elif defined(CASE_USED_TYPE)
int used_error_type() {
  const auto error = qualified::make_error();
  return error.code;
}
#else
#error Select exactly one qualification CASE
#endif
