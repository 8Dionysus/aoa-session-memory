# Session-Coherent Graph Queue Windows

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0068
- Original date: 2026-08-12
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: graph indexing, incremental maintenance, scheduling, performance, freshness
- Projection layers: graph source contributions, graph store, maintenance queue
- Guard families: bounded batch, session coherence, atomic mutation, cooperative deadline
- Posture: accepted

## Context

The graph maintenance queue is ordered by individual source cost, but graph
contributions are hydrated by archived session. A source-count prefix can
therefore split one ordinary session across several transactions. Each pass
then pays the same session parse and contribution reduction cost again. A
candidate window larger than the commit limit can also hydrate sources that
the transaction cannot commit, spending most of its cooperative budget before
semantic progress.

## Options Considered

- Keep source-key prefix selection and increase the cooperative budget.
  Rejected because it preserves repeated whole-session work and makes progress
  depend on a longer uninterrupted host window.
- Use only smaller fixed source batches. Rejected as the primary route because
  it bounds each pass but can parse the same session even more times.
- Pack complete session groups into the applying batch limit, skipping a group
  that does not fit the remaining capacity. Split only a single session whose
  source count exceeds the entire hard batch limit.

## Decision

An applying `--use-queue` graph-maintenance pass selects a session-coherent
source window whose total source count does not exceed `batch_limit`. It keeps
the existing queue priority order at the group boundary, greedily admits
complete session groups that fit, and reports skipped groups and any
unavoidable oversized-session split. Dry exact planning retains its declared
candidate-pool window because it does not publish a mutation.

## Rationale

Session is the natural contribution-hydration boundary. Aligning the queue
window with that boundary amortizes raw parsing and contribution reduction
across every source that the same transaction can commit. Keeping the hard
source limit preserves resource admission and atomic rollback. Skipping a
temporarily non-fitting group lets smaller complete sessions fill the pass
without reordering sources inside a session or claiming freshness from
selection alone.

## Consequences

- Positive: an ordinary multi-segment session is parsed once per applying
  queue pass instead of once per arbitrary source slice.
- Positive: the applying candidate window no longer hydrates more sources than
  the transaction's source-count commit limit.
- Positive: reports expose session counts, skipped groups, and unavoidable
  oversized splits for calibration.
- Tradeoff: strict cheapest-source ordering becomes cheapest-session-group
  ordering for applying queue consumers.
- Tradeoff: a session larger than the complete hard limit must still be split;
  that explicit heavy-tail case remains visible rather than starving the
  queue.
- Follow-up: calibrate the hard limit from committed live receipts and add a
  dedicated resumable per-session contribution cache only if oversized
  sessions become common.

## Boundaries

This decision changes queue scheduling, not graph relation semantics, source
authority, entity-registry dependency checks, freshness criteria, or the
full-rebuild boundary. A selected or parsed session is not progress without a
committed graph mutation and post-commit freshness evidence. Registry drift
during the transaction still fails closed and rolls back.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `PIPELINE.md`
- `docs/decisions/`

## Follow-Up Route

Drain a real queued tail through the normal resource-gated graph-maintenance
route, verify that complete session groups commit within the cooperative
budget, and use the standard freshness route for the remaining queue.

## Verification

Focused source tests require complete groups to be packed around a group that
does not fit and require an oversized single session to remain hard-bounded
with an explicit split diagnostic. Decision-index regeneration/check,
`py_compile`, the full source suite, portable parity, and live committed queue
receipts remain the release gates.
