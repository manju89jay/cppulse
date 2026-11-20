# Bounded result streams and derived indexes

This private producer contract supports NFR-SCL-05, M2-05 and FR-UX-08. The
remaining transactional index, public paging and scale acceptance remain open.
It does not replace run verification, report contracts or the production plan.

`cppulse.json_stream.iter_json_array(stream, member, *, expected_sha256,
expected_size, limits=JsonStreamLimits())` accepts a binary readable stream.
It yields UTF-8 **bytes**, each representing one complete selected top-level
array element, retaining JSON scalar meaning and numeric lexemes. Whitespace
between tokens may be normalized. No schema or producer authenticity is implied.

The root must be one object with the selected member present exactly once as
an array. Every ignored member is structurally parsed. Duplicate object keys,
invalid JSON/UTF-8, unpaired Unicode surrogates, invalid escapes or numbers,
nonfinite JSON extensions, trailing material and truncated input fail with a
cppulse ContractError or IntegrityError. Duplicate keys compare decoded string
identities. Repeated array values are distinct occurrences and are preserved.
Caller member names must be nonempty valid Unicode strings without NUL.

Expected SHA256 is exactly 64 lowercase hexadecimal characters. Expected size
is an exact nonnegative integer (bool and integral floats are rejected), no
larger than the configured maximum. The entire consumed stream must match both.
All reads are bounded by chunk_bytes and max_bytes, even if the stream lies
about its size or returns too much data. A read failure is reported explicitly.

**Every yielded row is provisional.** Success requires draining the iterator
through validated EOF, complete JSON structure, SHA and size checks. Closing or
abandoning it is not successful validation. A transactional index must roll
back after any parser, source-identity or publication failure and must never
serve partially indexed rows. A later consumer must hold and verify original
source descriptors/paths and bind an index to exact run/manifest/artifact pins.

JsonStreamLimits is the frozen private API. Its token/item/depth/object-key and
array/record budgets include ignored metadata; no whole ignored object or array
may be buffered. Simultaneous live keys are bounded by decoded UTF-8 bytes.
Selected item byte counts exclude inter-token whitespace. Exceeding any budget
is an explicit unsupported/incomplete result, not a smaller passing result.

Required producer checks include chunk splits inside multibyte UTF-8, escaped
quotes/backslashes and surrogate pairs; nested objects/arrays; decoded duplicate
keys; every malformed delimiter/number/string/EOF shape; max budgets and exact
boundaries; ignored malformed/oversized metadata; hash/size mismatch after
provisional rows; over-returning/erroring streams; repeat occurrences; and
bounded memory with large ignored arrays. Lead will run original large retained
artifact scans after focused checks and independent review pass.
