# Historical showcase data and integration provenance

The six older `examples/*` datasets and `assets/*` cards are historical,
incomplete-context outputs. They are not results of the reviewer-fix candidate.
Earlier independent inspection found finding-record/summary mismatches in the
old fmt/json snapshots, zero Git file-metric rows and missing provenance/PDFs.
Those snapshots must not support current marketing numbers, ownership claims,
calibrated probabilities or upstream readiness verdicts.

The integration deliberately preserves the smaller tested-side working copies.
The approximately96MB regenerated main-side datasets remain losslessly reachable
in the immutable main parent, rather than materialized as a second active copy.
No corpus refresh was run. The original full commits and Git blobs remain in
both preserved histories; the resolution does not label them verified today.

| Project | Original main-side historical bytes | Tested-side historical bytes |
| --- | --- | --- |
| fmt | [main82120d26](https://github.com/manju89jay/cppulse/tree/82120d26b51f99b64068f9d66f6e000fcaee97c2/examples/fmt) | [tested e5b6db6](https://github.com/manju89jay/cppulse/tree/e5b6db6da16b8f567c0fb21aa00f1d17739a4938/examples/fmt) |
| grpc | [main82120d26](https://github.com/manju89jay/cppulse/tree/82120d26b51f99b64068f9d66f6e000fcaee97c2/examples/grpc) | [tested e5b6db6](https://github.com/manju89jay/cppulse/tree/e5b6db6da16b8f567c0fb21aa00f1d17739a4938/examples/grpc) |
| json | [main82120d26](https://github.com/manju89jay/cppulse/tree/82120d26b51f99b64068f9d66f6e000fcaee97c2/examples/json) | [tested e5b6db6](https://github.com/manju89jay/cppulse/tree/e5b6db6da16b8f567c0fb21aa00f1d17739a4938/examples/json) |
| leveldb | [main82120d26](https://github.com/manju89jay/cppulse/tree/82120d26b51f99b64068f9d66f6e000fcaee97c2/examples/leveldb) | [tested e5b6db6](https://github.com/manju89jay/cppulse/tree/e5b6db6da16b8f567c0fb21aa00f1d17739a4938/examples/leveldb) |
| poco | [main82120d26](https://github.com/manju89jay/cppulse/tree/82120d26b51f99b64068f9d66f6e000fcaee97c2/examples/poco) | [tested e5b6db6](https://github.com/manju89jay/cppulse/tree/e5b6db6da16b8f567c0fb21aa00f1d17739a4938/examples/poco) |
| protobuf | [main82120d26](https://github.com/manju89jay/cppulse/tree/82120d26b51f99b64068f9d66f6e000fcaee97c2/examples/protobuf) | [tested e5b6db6](https://github.com/manju89jay/cppulse/tree/e5b6db6da16b8f567c0fb21aa00f1d17739a4938/examples/protobuf) |

The main-side density arithmetic is retained in
[historical ADR-007](../adr/ADR-007-health-score-formula.md). Its original
[independent legacy checker](https://github.com/manju89jay/cppulse/blob/82120d26b51f99b64068f9d66f6e000fcaee97c2/scripts/verify_scores.py)
is preserved in that pinned history. Its `max(total_loc,1)` and empty-frame100
behavior must not be used to qualify new measured-context output. Current
source/output gates retain explicit unknown prerequisites and versioned models;
there is no automatic migration of old scores or blanket legacy arithmetic over
new output. The old CI's legacy-formula-only addition is not transplanted over
the tested shared CI/contract facade, whose current scoring/unknown tests remain.
No check was removed or loosened to claim a green integration.

Showcase regeneration now refuses absent analyzers, floating revisions and
inconsistent raw counters before generating derived cards. Module calls use
canonical installed entrypoints. It does not fetch/reset a user's dirty cache,
forge history, or qualify arbitrary unverified scan contexts. The old registry
has no immutable revisions, so it cannot silently produce a fresh showcase.
Use the finite first-trial example instead of bulk refreshing those datasets.

For the separately audited native-only historical OSS demonstration, see
[the LevelDB record](leveldb/README.md), which includes actual record counts,
revision, configuration and analyzer identity. Its measurements are historical,
not qualification of these new source changes.
