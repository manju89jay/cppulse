# Experimental ranking availability

`file-eligibility-1` adds explicit per-file availability to the unreleased
prototype and v2 risk documents. It does not change the frozen original v1
contract or establish prediction accuracy. Existing supported documents without
the extension remain readable.

`file_risks` contains numeric experimental rankings only for files with usable
declared analysis and Git-history inputs. It never inserts zero for a missing
prediction. `unranked_files` accounts for the remaining non-excluded scope,
including skipped and failed units that have no feature row. Each record has
`file`, `availability`, machine-readable `reason_codes` and readable `reasons`.
An unranked record has no numeric score, probability or risk-level label.

`metadata.ranking_scope` records its version and the declared/ranked/unranked
counts. Validation rejects duplicate or overlapping file identities and counts
that disagree with the inventories. Prototype-to-v2 conversion preserves this
information. Original legacy export is still rejected when the richer semantics
cannot be represented honestly.

Ranking requires an error-free analyzed file, at least one enabled detector and
available selected Git history for that file. Inferred parse arguments remain
inferred: an eligible experimental rank does not establish an observed consumer
build, complete language support or library verification. Partial/missing parse
inventory and partial/unavailable/unverified history are exposed as unavailable
inputs, rather than zero findings or zero change activity. Model training uses
only eligible observations. Full-scope health retains its separate prerequisites
and current versioned formula.

Renderers should display the unranked inventory and its reasons, retain observed
findings, and show history limitations beside knowledge conclusions. A missing
rank is not evidence of a low-risk file, and an empty silo list with incomplete
history is not evidence of adequate knowledge distribution.

This is an additive change to unreleased development contracts. Consumers using
an older strict v2 schema may reject the new optional fields and should upgrade
together with the candidate; no published-package compatibility qualification is
claimed by source tests alone.


## Repository and training-label provenance

Before joining nonempty Git metrics, declared repository roots must agree after
lexical path-flavor/separator normalization. This comparison performs no current
filesystem resolution and proves no producer authenticity. Missing identity
keeps ranking unverified; empty history does not constrain independent static
analysis. Public unranked rows retain their reasons and no numeric/LOW rank.

The feature frame records `szz_observed_files` from raw Git field presence,
separately from zero-filled convenience columns. Declared zero SZZ counts remain
zero labels even when no positive exists. Missing counts use explicitly disclosed
feature-derived heuristics; mixed cohorts retain their per-file sources. Only
eligible files enter training. Bare calculation frames with an explicit non-null
SZZ column declare those proxy observations; a frame that synthesized defaults
must retain the absence marker.

Risk metadata retains the original producer `szz` object when supplied, including
cutoff, profile, label kind, scope and limitations. `training_label_provenance`
names the exact eligible training files and their SZZ/feature-derived subsets.
These are declared experimental proxy labels, not authenticated timestamps,
confirmed defects or calibrated future probabilities. A cutoff on bug-fix labels
does not filter every feature to that date. Empty eligible cohorts are explicitly
unavailable; unavailable evaluation metrics remain null.
