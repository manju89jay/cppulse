// Synthetic external diagnostics input; no result is an attributed upstream bug.
int main() {
#if CPPULSE_DEMO_GCC_WARNING
    int intentionally_unused = 7;
#endif
#if CPPULSE_DEMO_GCC_ERROR
    return intentionally_missing_symbol;
#else
    return 0;
#endif
}
