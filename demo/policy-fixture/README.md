# Synthetic single-translation-unit policy input

This input separates a clean case, intentional static rule triggers, an
intentionally missing include and a deliberate test failure. The raw-pointer
case releases its allocation; a finding demonstrates a selected rule/policy,
not a proven runtime defect. No result is a benchmark or attributed upstream bug.

The CMake project exports actual compile commands. Verification/normalization
and policy assessment are tested separately before any public workflow is
advertised. Builtin resource inputs belong outside the selected source scope
and are explicitly excluded from recursive project analysis by the demo driver.
