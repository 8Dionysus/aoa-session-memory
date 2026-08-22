# Independent Validation Nodes and Bounded Proof Kernels

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0088
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/benchmarks/`, `docs/decisions/`
- Surface classes: validation graph, privacy, incremental maintenance, performance
- Projection layers: derived-text redaction, event classification, segment index, semantic component receipt
- Guard families: exact semantic parity, process-local cache, raw-block identity, structural marker, streaming fallback, fail-closed admission
- Posture: accepted

## Context

A forced session-projection migration repeated three proofs whose inputs were
already stable at a narrower scope. Recursive derived-text redaction evaluated
the same short field/value pairs thousands of times inside one policy-bound
build. Each segment receipt streamed canonical JSON through a Python function
call for every scalar even when the component was small. A privacy structural
marker with its own schema and exact raw-block identity was discarded whenever
the unrelated event-classification generation changed, causing another full
raw scan.

These are validation costs, so removing the proofs or trusting their generated
outputs was not an admissible optimization. The question was whether their
execution could follow the actual claim/evidence graph instead of the broader
pipeline generation.

## Options Considered

- Recompute every proof at every consumer. Rejected because identical bounded
  inputs make the repeated work non-evidentiary.
- Persist redaction results or trust stored semantic hashes across processes.
  Rejected because raw-derived values and unverified generated receipts would
  cross their authority boundary.
- Make one global classification generation own the privacy marker. Rejected
  because it adds an edge absent from the data flow and turns unrelated
  classifier changes into raw privacy rescans.
- Share one cache across classification blocks by changing worker/checkpoint
  topology. Rejected after a real paired comparison showed only `1.032x`
  median improvement, insufficient for the larger failure and rollback
  surface.
- Use independent guard nodes, process-local bounded memoization, and an
  adaptive canonical-hash kernel with an exact fallback.

## Decision

Recursive derived-text redaction may memoize results only inside one process,
one literal policy, and one bounded build. The key includes field context and
source text. Only strings of at most `4096` characters enter the cache, it
holds at most `65536` entries, and neither keys nor values are serialized.
Disabling or omitting the cache executes the complete existing redaction path.

A segment-index semantic receipt may materialize the already-defined canonical
JSON normalization only when the exact artifact is at most `8 MiB`. Larger
components retain the streaming hash. Both kernels implement the same volatile
key exclusions and semantic mode, and their hashes must compare equal before
the bounded kernel is admitted.

The sensitive-literal structural marker is a separate validation node. A
candidate classification index may contribute that marker across an
incompatible classification generation only when the marker is covered by the
current records root, has the current marker schema, and belongs to the exact
raw block record. The classification artifact itself remains incompatible.
A positive marker merely narrows the raw ranges: the current process rereads
those exact raw lines and applies the current privacy detector. A negative
marker skips a block only inside an exact published raw prefix.

The four exact core generations published immediately before this change enter
the existing reuse-then-restamp predecessor bridge for classification,
segments, task episodes, and session index. Admission still reconstructs the
stored identity, validates raw/input and artifact receipts, sanitizes where the
stage contract requires it, publishes a migration receipt, and rejects every
unknown generation. This prevents a proved execution-only change from becoming
a cold core rebuild without pretending that the producer generation stayed
unchanged.

## Rationale

Each optimization reuses a deterministic computation at the narrowest scope
that proves its inputs unchanged. No generated value becomes authority, no raw
literal leaves the process, and every large or incompatible case retains the
original complete path. Separating the privacy marker from classification is a
real DAG correction: marker schema and raw identity, rather than a downstream
classifier implementation, determine its reuse.

The same-source real-session crossover produced one semantic root in all four
runs and reduced median forced-migration time from `4.758 s` to `3.868 s`
(`1.230x`). The bounded hash alone matched all `44` component roots and was
`5.305x` faster than scalar streaming for those components. Slower field-LRU
and early-cache variants, and the low-yield cross-block cache, were rejected
rather than inferred useful from profiles.

## Consequences

- Positive: forced migrations retain complete privacy and semantic proof while
  avoiding repeated regex, canonical-scalar, and full-raw work.
- Positive: an unrelated classification change no longer invalidates a
  current raw-bound privacy marker.
- Positive: the installed predecessor crosses through an explicit migration
  receipt instead of an unbounded cold rebuild.
- Positive: exact uncached and streaming paths remain executable semantic
  oracles and rollback references.
- Tradeoff: bounded process memory can retain short raw-derived strings until
  the current command exits; the cache limits and no-persistence rule are part
  of the contract.
- Tradeoff: changes to sensitive-literal candidate discovery must advance the
  structural-marker schema when old ranges are no longer complete.
- Follow-up: keep measuring larger sessions and leave worker topology unchanged
  until a separately paired method shows material gain.

## Boundaries

This decision does not make classification artifacts compatible across unknown
generations, persist a cross-process cache, admit stored hashes without
artifact receipts, change raw authority, or define a whole-AbyssOS validation
SLO. It does not claim that every session fits the measured execution envelope.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/benchmarks/session-projection-validation-dag-actual-7mb-20260813.json`
- `docs/benchmarks/session-projection-validation-dag-actual-7mb-20260813.md`
- `docs/decisions/`

## Follow-Up Route

Run source and portable validation, install only through the owner artifact
route, then compare post-install live maintenance receipts. Carry the same
claim/evidence-node method to other AbyssOS owners only after their own source,
tests, and validators identify an equivalent repeated proof.

## Verification

Focused tests compare cached and uncached projection semantic roots, parallel
and serial roots, bounded and streaming component hashes, stale-classification
marker reuse, unknown-generation classification refusal, candidate-range raw
reads, captured-tail behavior, privacy non-persistence, and search-store byte
parity. The benchmark records same-source crossover timing, exact semantic
parity, resource peak, rejected methods, and scope limits.
