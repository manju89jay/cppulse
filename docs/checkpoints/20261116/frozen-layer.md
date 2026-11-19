# Retained input-layer prerequisite, current uncommitted slice

Scope: M2-03,NFR-SCL-03,NFR-SCL-06,NFR-SCL-10,AC-04,AC-06. Canonical acceptance states unchanged. This implements retained selected filesystem bytes, not qualified warm reuse, image execution or complete runtime closure.

`cppulse.frozen_layer.retain_frozen_layer(request,destination)` streams the same nofollow-checked selected file bytes into a deterministic PAX tar and retained gzip. It hashes both actual streams, retains exact integer nanosecond metadata and normalized ownership1000, checks selected root/directory memberships and identities before/after capture, and rejects symlinks, hardlinked source files, special files and mount crossings in this finite profile. Output is outside selected inputs in an owned private directory.

The final filename is exclusively linked from the checked descriptor through supported Linux procfs, with a retained `.partial` witness. Content, size, mtime, inode/link counts and current parent path are checked again. Failed publication removes only its own final link and preserves witnesses; foreign replacement or uncertain filesystem state is not called complete. This is not multi-artifact atomic publication or a physical power-loss guarantee.

`verify_frozen_layer(capture,path,request=request)` independently checks request identity, namespace mappings/budgets, compressed/raw hashes, bounded PAX/tar structure, exact paths, integer nanoseconds, ownership/modes and each file's bytes without extraction or looking up original source. Actual verification still succeeds after original source deletion; this is retained historical evidence, not fresh-source verification. Every capture forces cache_eligible:false/closure:unqualified.

Contracts precede production integration: current timestamps require signed64-bit bounds, and integer fields reject integral JSON floats that could authorize invalid PAX time syntax. Original meaningful reds are retained. Independent review reproduced invalid-deflate handling, producer/consumer parent replacement, missing-witness cleanup and same-inode corruption/growth; lead repaired them in a new epoch, preserving old candidates. Decimal context precision and producer-noncanonical path forms also have retained regressions.

- Actual production component gate:88passed.
- Combined production/query/input source-bound gate:139passed4.74seconds,exit0,source stable. Statement/branch coverage: frozen_layer86.1%, contracts.frozen_input94.1%, frozen_input88.4%, query_observation81.0%, its contract85.0%.
- Independent current-interface gate:18passed0.95seconds,source stable,47artifact pins; production producer copied byte-for-byte from reviewed module1257b621… .
- Baseline full3327pass source epoch predates these private changes; it is preserved separately and does not claim a full-suite pass for these later bytes. No new wheel or image proof is claimed yet.

Evidence copies/hashes: `frozen-layer-evidence/MANIFEST.json`. Original source/data/log artifacts remain at recorded paths. Next dependency gate: coherent installed candidate under the execution-board freeze, then reviewed runtime/image input contracts and actual native namespace controls. Full qualified cache equality/invalidation, scale, platforms, M8/M9 and P14 remain open.
