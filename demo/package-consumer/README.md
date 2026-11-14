# Selected installed-package consumer

This fixture consumes the pinned fmt10.2.1 compiled archive and utfcpp4.0.5
headers after packaging, rather than adding the original source directories to
the consumer build. The driver retains actual archive-member linker-map and
header dependency-file observations before making a scoped use claim.

The `cppulse_seed` header is explicitly synthetic. Its intentional throw makes
an actual `-fno-exceptions` consumer compilation fail; it is not a reported bug
in either upstream library. The positive consumer call does not execute the
negative throwing path. The separate minimal header translation unit supports
one requested self-containment check, not exhaustive template coverage.

No library or application acquires a cppulse runtime dependency. Any resulting
evidence describes the selected Linux/GCC contexts, cases and finite inputs;
it does not establish all upstream tests, other platforms, ABI compatibility,
production readiness or producer authenticity.
