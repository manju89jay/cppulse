# Independent integration contract review

Current scoped gate: **179 passed, no skips,119.96s**, exit0. Reviewed changed
production/test sources, all selected v2/prototype contracts, and the three shared
store modules/private store schemas were hash-stable before and after. The check
retains238 immutable run-manifest pins. Compiler path/version/hash and selected
actual C++11/14/17/20 before/after compile/run artifacts are retained. This is
scoped integration evidence, not the full source suite or full production
acceptance.

The gate includes all original58 finding/repair consumer checks,22 native
contract/assessment/profile-presentation checks,87 public workflow/CLI/contract
checks and12 independent new compatibility/lineage controls. Original positive
and negative assertions remain intact.

The parent's initial broad diagnostic run had2429 passes and44 failures before
its own workspace disk guard interrupted it; source changes prevented a stable
whole-suite qualification. These repairs were independently reviewed:

- Stored assessments and snapshot displays use the same optional exact
  `native_input_binding` constraint. Legacy absence remains valid and altered
  values or raw/display disagreement remain invalid.
- Public/documentation and packaged prototype findings schemas match again,
  while legacy reports remain readable.
- A native transform result retains mandatory inventory and observations,
  optionally exposes measured-metric artifacts, and uses null logical IDs only
  for the two document families without a logical document ID.
- Local synthetic finding/repair fixtures explicitly declare parsed source
  identity while leaving every normalized metric unavailable/null. The shared
  legacy fixture still has no parsed-buffer evidence. Unverified collection
  facts remain refused before normalization.

Independent review found two problems in the initial result-family extension:
metric output was wrongly mandatory for legacy results and metric documents
were wrongly required to have a logical ID. The parent repaired those. New
independent controls then exposed duplicate metric-family entries accepted with
different artifact IDs. The meaningful one-failure/eleven-pass red is retained;
the parent added kind uniqueness alongside existing artifact-ID uniqueness.

The first combined new-control run also contained one reviewer fixture mistake:
unverified normalization correctly raises CompatibilityError before constructing
inventory, so that new test was corrected to require the existing stronger
refusal. This was not a production defect or a weakened prerequisite.

The four developer-facade failures in the earlier broad run came from selecting
an inside-checkout temporary output location that the real output policy rejects.
The parent's unchanged16-case suite passed with an outside-checkout basetemp.
Those tests were not weakened or relabeled as product fixes.

All materials remain uncommitted. Current broader source-suite completion,
installed artifacts after subsequent changes, store-recovery follow-up and all
remaining full-plan requirements remain separate gates.
