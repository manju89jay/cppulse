# Retained used SDK inputs

`used_sdk_inputs` v2 retains builtin compiler-resource bytes separately from
selected project source. The bounded publisher captures only include targets
reported by an actual TU within the selected canonical resource root. A copied
SDK inventory containing hashes alone is not a byte capture.

Each unit pins its original request digest, original native-report artifact and
SHA256, exact native-report JSON bytes, and original SDK-inventory digest. The
original inventory JSON is deduplicated by digest. Each available buffer must
agree in SHA256 and byte size with both the original inventory and every actual
TU include-buffer observation for that path. Its separate immutable artifact is
addressed by `sdk-buffer-<SHA256>`. Unknown and changed buffers retain reasons,
null byte identities and no invented artifact link.

The producer bounds an individual SDK buffer to8MiB, distinct retained SDK
buffers to64MiB, and the typed proof to64MiB. Budget exhaustion leaves affected
units without qualified SDK input evidence. The pure bundle kernel checks actual
artifact descriptors, captured-byte accounting, original report/resource roles,
and a qualified inventory's explicit SDK proof reference. The reader hashes the
stored proof and buffer bytes, compares exact original unit inputs, and uses one
proof/index/content cache per normalization. SDK paths never enter the project
source manifest or count as selected project LOC.

This evidence still does not establish general dependency closure. The
normalizer scans the retained actual source/header bytes and macro arguments
for unsupported filesystem/time queries, opaque constructs and embed input.
An inactive `__has_include_next` in actual Clang19 stddef.h remains unknown.
Ordinary continued directives are joined before scanning; a line-spliced query
remains detectable across raw read boundaries. A positive actual
`__stddef_size_t.h` case and the actual stddef.h negative case are retained in
the independent bridge checkpoint. Qualified warm reuse remains disabled.

Legacy opaque v1 SDK capture artifacts remain readable as historical material;
they are not interpreted as current checked buffers. Missing or invalid SDK
proof cannot be waived by inferred-parse opt-in. Fresh v4 maintenance scoring
also requires the complete declared source scope, original successful unit
receipts and all other measurement prerequisites. This contract does not attest
producer identity, source authenticity, target tests or policy approval.

Current producer/normalizer proofs are in
`docs/checkpoints/20261116/bounded-typed-analysis.md` and
`docs/checkpoints/20261116/bridge-independent-review2/`.
Full P5 memory, configuration enumeration, atomic public journey, installed
artifact, representative-scale and broader production acceptance remain open.
