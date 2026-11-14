// Intentionally compiled without instrumentation for the explicit library-gap
// negative scenario. A clean test cannot establish sanitizer coverage here.
int cppulse_prebuilt_read(const int* value) {
    return *value;
}
