# Independent C++ proposal rationale

I authored this proposal from the selected original source and tests, rather than from a supplied replacement. It replaces only main.cpp; source, protected tests.cpp/CMakeLists.txt and the before RunStore were not modified. No builds, test commands, providers, network operations, commits or pushes were performed by this proposal author.

Observed main.cpp SHA-256: 4ad9e05f91f3bf43b3f4b6548e7dbc8845ebce33b235ad760d11f8f9ef4b755c.
Before run: 152b591fbb9847a5891eb267ab93ab82.
Pinned manifest SHA-256: 4e6e4f8922da5a82581df4602dfdbcbbcf9368d8384847eaf933944e57d34d54.
Selected source digest: 3ccc8abe1df847b54b51f7f2c977700bbc3a2da5f65f5f1d9bd42f7b14098e89.

I independently opened the pinned run through RunStore.open_existing(...).open_run(...), read its documents with read_documents and verified the snapshot with s.verify(). Evidence native-tests has failed status and usable usability, receipt_id tests, and scope main.cpp. The tests receipt reports exit code 8, total 3, passed 2, failed 1, skipped 0, errors 0. Retained JUnit and LastTest.log agree that lower and inside passed while upper failed. JUnit SHA-256: 409a6eb34a09f553ffdd39590fa043edc145f4c4331cdfb3b91a080a4e55fac4. LastTest.log SHA-256: bf67eebdbc07707f49ee04312dee821df15758be935ffabf8188f17064dd8b64.

The selected tests assert lower: clamp_value(-3,0,10)==0; inside: clamp_value(5,0,10)==5; upper: clamp_value(14,0,10)==10. CMake registers those three names. The original function only tests the lower bound, so upper returns 14.

The proposal keeps the existing lower-bound branch and adds an upper-bound comparison in the remaining branch. For valid lower<=upper, values below lower still return lower, values within the inclusive interval still return value, and values above upper now return upper. Equal bounds return that bound; comparisons introduce no arithmetic overflow. The change uses C++17-compatible expressions and preserves the function signature without new dependencies.

This is an intentional behavior correction, not semantic equivalence. These three observed cases are finite evidence; no after execution has been performed by this author. Reversed bounds are outside the requested valid-bounds contract, and unchanged behavior for that invalid input domain is not claimed. The retained evidence carries explicit scope, imported-report and executable/runtime-closure limitations; snapshot hash verification does not establish producer authenticity or universal correctness.
