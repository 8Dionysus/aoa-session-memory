# Generation-Bound Segment Privacy Admission

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0052
- Original date: 2026-08-11
- Owner surfaces: `scripts/aoa_session_memory.py`, `DESIGN.md`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/benchmarks/`, `docs/decisions/`
- Surface classes: session indexing, incremental maintenance, privacy, performance, resource control
- Projection layers: raw event classification cache, session segments
- Guard families: privacy, content identity, stage-scoped generation, deterministic parity, raw authority
- Posture: accepted

## Context

Block-addressed classification already redacts every persisted metadata record
under the current whole-session sensitive-literal policy and binds that result
to an exact producer generation and raw block. Segment construction nevertheless
recursively privacy-scanned the same large event and route-signal trees again.
On one actual event-dense segment with 1,610 events, this duplicate work
dominated the writer profile. A paired component benchmark measured a
`3.883127 s` median for the ordinary complete pass.

## Options Considered

- Keep rescanning every classification field in every downstream segment.
  Rejected because it discards a valid upstream privacy proof and makes stable
  projection cost proportional to repeated metadata traversal.
- Trust all caller-provided `RawEvent` values. Rejected because direct callers,
  raw parsing, and stale or corrupt caches do not carry the required proof.
- Persist sensitive literal values or a reversible policy token for reuse.
  Rejected because it expands the credential surface.
- Admit only exact generation-bound classification containers, separately
  redact values newly derived from parsed raw, and preserve the ordinary full
  pass for unattested callers and context-sensitive maps.

## Decision

The segment writer has an explicit internal admission mode used only after the
classification loader verifies cache generation, raw block identity, artifact
receipt, and payload shape. In that mode, classification-derived event
metadata is treated as already redacted under the current whole-session policy.

Token-accounting observations are not part of the persisted classification
payload and may be derived from parsed raw during segment rehydration. They are
therefore redacted before joining an admitted event container. Facet maps remain
inside the ordinary recursive pass because their derived dictionary keys
provide field context to the established redaction policy. Direct or
unattested `write_segment` calls retain the complete recursive pass.

The admission implementation lives inside the segment producer contract. It
changes the segment generation while leaving the raw-event-classification
generation unchanged, so the optimization invalidates only its owning stage.

## Rationale

Privacy proof should compose across an integrity-checked projection boundary
instead of being recomputed blindly. The narrow admission keeps raw-derived
values and contextual redaction fail closed, preserves exact emitted JSON, and
avoids persisting secret material. Keeping the source change inside the segment
producer ABI also prevents an optimization from forcing needless historical
reclassification.

## Consequences

- Positive: repeated traversal of the dominant event/facet container is
  removed from admitted segment workers.
- Positive: paired output remains byte-identical while the measured median
  improves from `3.883127 s` to `1.067364 s` (`3.638x`).
- Positive: the classification generation and its reusable checkpoints remain
  stable.
- Tradeoff: the writer now has two explicit privacy routes whose equivalence
  requires regression coverage.
- Tradeoff: context-sensitive facet maps continue to pay the full policy cost.

## Boundaries

Admission is not a general trusted-data marker and does not apply to raw or
parsed payloads, unverified caches, arbitrary callers, review rendering, or
downstream semantic correctness. Classification metadata remains a rebuildable
derived projection, not raw authority. This decision does not prove complete
cold-projection latency or authorize live deployment.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.md`
- `PIPELINE.md`
- `docs/benchmarks/session-projection-segment-privacy-admission-actual-430mb-20260811.json`
- `docs/benchmarks/session-projection-incremental-core-actual-430mb-stress-resume-20260811.json`
- `docs/decisions/`

## Follow-Up Route

Run a clean resource-admitted 430 MB cold projection without a competing heavy
lane, then use stage timings to choose the next bottleneck rather than
increasing timeouts.

## Verification

Regression tests compare ordinary and admitted segment JSON exactly, inject a
credential-shaped value into classification metadata and raw-derived token
accounting, and cover serial/parallel semantic parity plus classification-cache
reuse. The paired actual-segment receipt records exact output SHA-256 parity,
stage-scoped generation identity, and measured speedup. A completed nonexclusive
430 MB stress-resume additionally proves `455/455` classification-block reuse,
full atomic publication, and zero cgroup swap, but exceeds the clean cold upper
bound by `12.742 s`. Full suite, clean cold SLO, portable export, and
installation proof remain separate gates.
