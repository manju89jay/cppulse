# Pinned real-library consumer

This application links compiled fmt 10.2.1 and uses header-only utfcpp v4.0.5.
The exact source commits are recorded in demo/corpus-lock.json. The integration
assertion checks valid UTF-8, character count and formatting. This is a selected
consumer test, not the full upstream test suites or a general accuracy benchmark.

Configure with CPPULSE_CORPUS_ROOT pointing to checkouts containing fmt/ and
utfcpp/. The corpus runner records source/configuration identity and actual
results without committing or changing this project's Git references.
