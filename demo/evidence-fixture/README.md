# Synthetic collection input

This tiny static library and selected consumer are collection fixtures, not a
library quality benchmark. The default configuration builds and checks `2+3=5`.
`CPPULSE_DEMO_COMPILE_ERROR=ON` and `CPPULSE_DEMO_FAIL_TEST=ON` explicitly inject
separate compilation and test failures. No fault is attributed to fmt, utfcpp
or any other upstream project.

Build/test collection is implemented and verified separately from this input.
The original two-file analysis demonstration remains in `demo/fixture`.
