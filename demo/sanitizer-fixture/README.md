# Synthetic direct-GCC sanitizer inputs

This fixture supplies deliberate heap-access, signed-overflow and data-race
branches for separate ASan, UBSan and TSan recipe jobs. The clean branches still
perform operations for which object-level sanitizer callsite relocations can be
observed. `bad` selects the intentional violation; `skip` returns 77.

`prebuilt.cpp` exists for an explicitly uninstrumented user-library gap. CMake
does not compile these files: it registers the actual selected binary for
CTest, or deliberately selects zero/all-skipped tests. Compilation, object and
ELF inspection, linking and test execution belong to explicit selected recipe
steps with retained identities and logs.

These are controlled inputs, not detector accuracy or performance measurements.
Runtime presence does not establish runtime usability. In particular, a TSan
startup/memory-mapping failure must remain unavailable rather than become a
reported data race or a clean verification result.

The two CTestCustom files are exact inert control sentinels copied into the fresh
build directory and retained as observed inputs to both inventory and tests.
They are part of the supported direct CTest configuration, not runtime test
results. Actual compiler/linker and file-inspection commands use the workspace
root; the final ELF inspection includes full symbols to reject known custom
sanitizer default-options/report hooks in this bounded configuration.
