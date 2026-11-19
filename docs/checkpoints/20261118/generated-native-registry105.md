# Generated native rule registration: accepted maintenance criterion

NFR-MNT-03 is verified against its unchanged full original requirement. The
canonical row references `work/installed-rule105/nfr-mnt03-canonical-proof.json`
(SHA256 `c859117e8c3b2f4c8ed6466b0bc89c6649c0ff0fa18d5eadaf923f638961ce80`).
Independent review is `work/memory-review82/installed105/review.json`
(`176e80697e1da39b648e41abf5d367914400b6d43f5d8fe323c884662bbdbe62`).
Only this row changed from active to verified; all186 other rows and all187
definitions/P0–P14 remain unchanged. Counts:22 verified,105 open,58 active,2 blocked.

The authoritative registry generates real native rule types/constructors,
configuration capabilities/defaults, reference documentation and example
configuration. The public v2 metadata view serves installed MCP consumers.
All22 detector implementations and constructor ordering remain intact. Python
and native configuration now reject unsupported per-rule options; strict integer
tokens agree at both boundaries. MCP uses the public metadata projection rather
than leaking private native bindings.

Actual qualification:

- `work/heavyweight-jobs/native-rule102-component-targets/`:45 compile/link
  commands, all30 production and13 test translation units, actual0/stable.
- `work/heavyweight-jobs/native105-all-gtests/`:149 tests, no filter/skips,
  including the original >32MiB streaming report and4095-symlink controls.
- `work/heavyweight-jobs/config105-native-public-pinned/`:actual0; supported
  threshold changes findings and unsupported memory-rule threshold is refused.
- `work/heavyweight-jobs/config105-installed-ram/`:87 public configuration
  cases and actual MCP metadata for all22 rules plus unknown-ID rejection.
- Independent review:9385 assertions,749 ROOT pins and7 explicit system hashes.

Pinned artifacts:

- Wheel: `work/installed-rule105/wheels/cppulse-0.2.0.dev2-py3-none-any.whl`,
  SHA256 `17c52c2dfcad73b3f137af69ed27db232c3b5e34c996c3aad7a89b8e9be0d193`;
  all237 payloads match the frozen current source.
- Native component: `work/native-rule102/run-targets/cppulse-analyzer`,
  SHA256 `1a34a3ad2a344728af729ec6d54c0277e01bac9503435e7462982d06f45d17c1`.
- Freeze: `work/installed-rule105/candidate-source-freeze.json`,
  SHA256 `168ccd271351be5add2e7ff5bf2b8bbe2701a0c8448fbc10c37c996ebbee013e`,
 266 Python/test and102 native/editor source bindings.
- Full source/build and installed-prefix archives, byte/metadata indexes and
  actual installed command logs remain under `work/installed-rule105/` and
  `work/installed-config105/`. All1385 archive members/1097 file bodies were
  independently checked. Directory names/data received an actual fsync seal.

RAM scratch is private to an exec session. The installed-prefix journey ran
before that namespace ended; its complete durable archive remains. There is no
claim that the RAM installation is currently live. A fresh installation uses the
retained wheel with the declared core dependencies, then the normal public
`cppulse config --repo PATH --output PATH` and `python -m cppulse.mcp_server`
interfaces. The native executable is a tested explicit analyzer override;
portable native-kit/CMake/editor/platform qualification remains separate.

Failures remain distinct and retained: unsupported per-rule C93 settings,
integral-float mismatch, initial missing-store test fixture, MCP private metadata
leak, omitted Python seal constant names, misapplied test-target warning flags,
wrong expected binary hash, and the first missing-RAM-lifetime assumption. The
native warning flags now match the original CMake target definitions; library
warnings still fail builds and every test assertion remains. Linux object seals
are enforced by the kernel with readback and an actual rejected-write control.

FR-UX-04 remains active for its C++ CLI/Docker entry-point gates. M1-07, broader
memory/scale, all external obligations and P14 remain unclosed. The unchanged
strict command after this closure was:

```sh
.venv/bin/python scripts/verify_delivery.py --require-complete \
  --output work/installed-rule105/require-complete-after-nfr03.json
```

Actual exit2: `Stale source evidence: analyzer-core/src/analyzer.cpp`. The prior21
C93 profiles require the current full-map refresh; their old logs are not
relabeled as105. Full-program completion is not claimed. All changes remain
uncommitted; no commit, push, remote-ref update or publication occurred.
