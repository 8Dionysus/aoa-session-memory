# Session Freshness Obligations Close on Watermark Proof

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0090
- Original date: 2026-08-21
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: freshness, scheduling, recovery, observability, session projection
- Projection layers: raw capture, session projection, maintenance retry queue
- Guard families: persistent obligation, capture watermark, bounded retry, heavy lane, explicit convergence
- Posture: accepted

## Context

Raw capture and stable session projection intentionally advance independently.
An oversized or actively growing transcript can therefore have a complete
preserved capture while the last-good stable projection remains behind. The
periodic sweep previously recognized only a closed list of older freshness
reasons. A capture-specific reason could fall through as
`skipped_unhandled_freshness`, and the ordinary resource retry queue could
discard a still-required repair after its bounded attempt count. Green timer
and process results therefore did not guarantee eventual session convergence.

## Options Considered

- Keep extending the sweep reason allowlist. Rejected because the next new
  non-current state could again become an unowned fallthrough.
- Treat successful resource or timer execution as completion. Rejected because
  execution success does not prove that a captured raw watermark was published.
- Run every large session projection synchronously from the sweep. Rejected
  because it would make recurring capture depend on one long, memory-heavy
  rebuild and would bypass resumable resource admission.
- Persist one session-scoped freshness obligation, route it through the
  resumable projection lane, and retire it only after watermark proof.

## Decision

Every selected non-current sweep record follows a repair route even when its
freshness reason is not in the declared reason vocabulary. When raw preservation
finishes ahead of stable projection, the sweep atomically upserts one
session-scoped persistent freshness obligation in the owner retry queue. The
obligation binds the strongest preserved capture epoch, byte watermark, digest,
and session identity.

Backlog or deep maintenance targets that exact session. A preserved capture
ahead of an otherwise compatible last-good projection is itself sufficient to
enter the resumable session-projection lane; route-generation drift is not a
prerequisite.

Bounded attempt limits remain execution-cycle limits. They can increase delay
and expose an exhaustion cycle, but they cannot delete a persistent freshness
obligation. A resource process, timer, fallback, or checkpoint closes the
obligation only when the published manifest proves coverage of the required
capture watermark. Append-only capture epochs admit a same-epoch published byte
watermark at or beyond the requirement; monolithic captures require the exact
byte count and digest.

## Rationale

The obligation converts an observation into durable convergence ownership
without putting unbounded work back into foreground capture. Binding closure to
raw authority prevents green process state from masquerading as fresh session
evidence. Targeted backlog/deep routing preserves fairness, checkpoints,
resource admission, last-good readability, and future decomposition of derived
consumers. Unknown freshness states remain visible but no longer disappear
through a closed switch.

## Consequences

- Positive: a captured session-projection gap cannot silently vanish after a
  sweep or bounded retry cycle.
- Positive: current maintenance status exposes obligation count, due count,
  oldest age, and the exact dispatcher route.
- Positive: small and large capture-ahead sessions share the same convergence
  contract while retaining profile-appropriate resource envelopes.
- Tradeoff: an unavailable source, repeated resource denial, or incompatible
  projection may leave a visibly blocked obligation for multiple cycles.
- Tradeoff: stable session publication does not by itself make search, episode,
  entity, or graph consumers current; their existing component receipts and
  queues remain independent.

## Boundaries

This decision does not make the retry queue, timer state, live overlay, search,
or graph an evidence authority. It does not permit deletion of raw captures,
last-good projections, or resumable work. It proves only that the named stable
session projection covers the obligation's preserved capture watermark; newer
source growth creates or advances a later obligation.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Keep component-outbox consumers independently receipt-bound, and extend the
same explicit-obligation model only where a generated consumer can currently
lose ownership without a terminal proof or visible blocked state.

## Verification

Focused tests cover sweep-to-obligation creation, persistent survival after
bounded retry exhaustion, queue age metrics, exact watermark closure, and
compatibility with the existing sweep, retry, and heavy-lane contracts. Owner
validation regenerates decision indexes, runs source and portable checks, and
requires a live sweep to create an obligation for a real capture-ahead session
before runtime convergence is claimed.
