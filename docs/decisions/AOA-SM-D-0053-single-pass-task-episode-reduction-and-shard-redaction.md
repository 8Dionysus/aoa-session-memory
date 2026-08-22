# Single-Pass Task-Episode Reduction and Shard Redaction

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0053
- Original date: 2026-08-11
- Owner surfaces: `scripts/aoa_session_memory.py`, `DESIGN.md`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/benchmarks/`, `docs/decisions/`
- Surface classes: session indexing, incremental maintenance, privacy, performance, resource control
- Projection layers: task episode source, session index
- Guard families: privacy, stage-scoped generation, deterministic parity, raw authority
- Posture: accepted

## Context

After segment construction became bounded, the dominant cold session-index
cost was task-episode reduction and shard publication. A profile over the first
20,000 events of a stable read-only 430 MB snapshot found repeated semantic
normalization for the same event, linear lookup across 644 ordered segment
ranges, and two complete privacy projections for every newly written episode
shard. None of that repeated work added evidence or changed the persisted
result.

## Options Considered

- Keep repeated normalization, linear lookup, and parent-plus-worker privacy
  projection. Rejected because cost grows from repeated traversal rather than
  new evidence.
- Cache semantic text or redacted episodes as an unbound global side store.
  Rejected because it introduces ambiguous lifetime and privacy authority.
- Compute immutable event semantics once within the reducer, use the ordering
  contract already carried by generated segment manifests, and pass an exact
  already-redacted payload only across the existing parent-worker boundary.

## Decision

The task-episode builder computes normalized semantic text once for each
observed event and passes it explicitly to deterministic representation,
retrieval-control, role, and verification consumers. Public helper defaults
continue to compute their own value when no precomputed value is supplied.

Segment resolution uses binary search over the generated manifest's ordered,
non-overlapping source ranges. Missing ranges and gaps still return no segment.

A cold shard task reaches its worker without a pre-redacted payload and is
privacy-projected exactly once there. If a prior shard exists, the parent must
compute the expected redacted payload to compare its hash; that same payload is
then passed to any rewrite or restamp worker instead of being recursively
scanned a second time. A worker without that explicit payload performs the full
privacy pass.

For append-stable bounded replay, the declared reused sealed-episode prefix is
already hydrated from previously redacted shards. When an episode in that
prefix has the exact current component source identity, including privacy and
redaction generations, its hydrated payload is the expected redacted payload;
the parent must not recursively redact it again. A source-identity mismatch,
caused solely by comparing a pre-redaction identity with its hydrated redacted
form, may preserve the prior identity only when the canonical component key,
current generation, and exact redacted payload SHA all match. A changed safe
payload, tail episode, unknown provenance, or policy-generation change retains
the full privacy pass.

These source-contract changes invalidate task-episode source and dependent
session-index generations. Raw-event classification and segment-index producer
contracts remain byte-identical and their generations remain reusable.

Task-episode semantic producer identity covers episode construction and shard
envelope semantics, not shard materialization/reuse orchestration. Streaming
tail mode is fail-closed on task-episode generation admission as well as segment
topology and goal-lifecycle frontier admission. An incompatible task-episode
generation therefore performs one complete raw-backed replay instead of
publishing either a tail-only compatibility view or a metadata-only semantic
guess. The exact
pre-split generation `8670e45e...11d` is a declared reuse-then-restamp
predecessor; unknown generations are not admitted.

The checkpoint stage DAG separately binds a rehydration-plan version into the
correlation, segment, and task-episode work identities. Changing full-versus-
tail admission therefore invalidates and removes staged segment/raw-block and
session-component artifacts even when the umbrella raw publish identity is
unchanged. Crash resume may reuse classification evidence, but cannot publish
artifacts produced under a different rehydration plan.

The compact session-index root applies its recursive metadata redaction before
attaching immutable segment manifests and raw-block records. Segment-derived
text was already redacted at the segment boundary; raw-block records contain
refs, digests, ranges, and count-only metadata. Reprocessing both complete
historical collections at every append adds no privacy coverage and is outside
the root metadata pass.

## Rationale

The reducer already owns one event observation, the segment manifest already
owns range order, and the parent already owns the exact redacted payload needed
for prior-shard comparison. Reusing those bounded values within the same
producer transaction removes redundant CPU work without widening trust,
persisting a new cache, weakening redaction, or changing evidence authority.

## Consequences

- Positive: paired reduction output is exact while median time improves from
  `11.581046 s` to `6.586581 s` (`1.758x`) on a real 20,000-event slice.
- Positive: one paired 311-shard publication improves from `95.127284 s` to
  `33.562716 s` (`2.834x`) with exact payload SHA-256 parity.
- Positive: classification and segment checkpoints survive this change.
- Positive: root session-index redaction is independent of historical segment
  and raw-block manifest volume.
- Positive: an orchestration-only optimization no longer invalidates episode
  semantics, and an actual semantic incompatibility cannot silently truncate
  the historical episode projection to its replay tail.
- Tradeoff: a genuine unknown task-episode ABI forces one full raw replay; that
  is explicit migration cost, not the steady-state append route.
- Tradeoff: ordered-range lookup relies on the generated segment-manifest
  ordering contract; malformed external lists fail to match rather than being
  searched exhaustively.
- Tradeoff: a prior shard outside the explicitly bounded pre-redacted prefix,
  or with a different component source identity, still requires one complete
  expected-payload privacy projection before reuse or restamp.

## Boundaries

Precomputed semantic text and redacted payloads are internal values, not
general trust markers. This decision does not admit raw text, bypass the
whole-session sensitive-literal policy, change task-episode semantics, prove a
cold full-projection p95, or authorize live deployment. Raw transcript remains
evidence authority and all task-episode artifacts remain rebuildable.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.md`
- `PIPELINE.md`
- `docs/benchmarks/session-projection-task-episode-reduction-actual-430mb-20260811.json`
- `docs/decisions/`

## Follow-Up Route

Run the full regression suite and a clean no-swap 430 MB cold projection, then
use its stage timings to decide whether another bounded producer change is
warranted.

## Verification

Focused regressions prove one semantic derivation per observed event, boundary-
correct ordered range lookup, one cold top-level shard privacy pass, checkpoint
resume, manifest validation, bounded hydration, exact-current pre-redacted
prefix reuse without a second privacy pass, and semantic admission. Paired
real-snapshot benchmarks record exact output SHA-256 parity. Full-suite, cold
SLO, portable export, and installation proof remain separate gates. A later
clean actual-snapshot run completed the 430 MB cold projection in `843.960 s`
with zero cgroup swap and a `6,123,139,072` byte peak. The same receipt keeps a
large-epoch stable-projection append fallback explicit rather than treating the
cold result as proof of the separate append-read SLO.
