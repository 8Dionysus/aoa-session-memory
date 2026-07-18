# Correlated Agent Activity Status Relation

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0009
- Original date: 2026-07-16
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: event taxonomy, graph semantics, evidence provenance
- Projection layers: segment relationships, task episode, typed graph
- Guard families: exact correlation, status-output separation, foreign-correlation rejection, raw-ref preservation
- Posture: accepted

## Context

A runtime can emit a structured agent-activity status between an operational
call and that call's eventual output. The status is neither ordinary prose nor
the output itself. Treating it as generic timeline context loses the explicit
association when linear event-sequence edges are omitted from the graph.
Treating it as a tool result instead overstates the observation as completion
or consequence.

Parallel activity makes adjacency unsafe. A nearby status can belong to a
different call, so position alone cannot establish the association. The
runtime-provided correlation identity is the stronger bounded join key.

## Options Considered

- Keep agent-activity status only in the event timeline. This preserves the
  observation but leaves topology consumers without a typed route from the
  call once ordinary sequence edges are omitted.
- Reuse `answered_by` and `responds_to`. This avoids a new edge type but
  collapses status and output semantics and invites unsupported success or
  consequence claims.
- Associate a status with the nearest call. This improves apparent recall but
  admits foreign parallel activity whenever event streams interleave.
- Classify structured activity separately and add a directed status relation
  only when call and status carry the same non-empty correlation identity.

## Decision

Represent a correlated structured agent-activity message as an operational
status distinct from both generic event-stream context and tool output.

A structured agent-activity message with a non-empty correlation identity is
classified as `CONTEXT_STATE`, carries the `agent_activity_status`
conversation/session act, and uses the
`structured_agent_activity_status` source lane. For a call with the same exact
correlation identity, the segment relationship and typed graph projection add
one directed `has_correlated_status` edge from the call event to the status
event.

Actual call output continues to use `answered_by` and `responds_to` separately.
An uncorrelated status, or a status correlated to another call, does not gain
the edge. The status node and edge retain resolvable raw, segment, and session
evidence refs.

`has_correlated_status` means only that the runtime reported that activity
state for the correlated operation. It does not mean that a recipient read or
applied a message, that the operation completed, or that it produced a
successful consequence.

## Rationale

An exact correlation join preserves the strongest structured evidence without
turning event adjacency into semantics. A dedicated edge keeps status and
result claims separate, remains useful when generic sequence edges are absent,
and gives typed bridge and timeline consumers a bounded path with direct
provenance.

The projection adds only the relation observed for the matching call/status
pair. It does not introduce broad mention, namespace, or session fanout, and a
foreign status remains auditable context rather than an accepted relation.

## Consequences

- Topology queries can recover a call-to-status path without relying on
  generic event sequence or high-degree discovery nodes.
- Episode and evidence readers can retain the status as a bounded observation
  without promoting it to success or consequence.
- Tool output remains independently queryable and may coexist with the status
  for the same correlation identity.
- New structured runtime status kinds require their own evidence semantics;
  this decision does not automatically admit every correlated event message.

## Boundaries

This decision does not prove delivery, recipient behavior, completion,
causality, or owner truth. It does not make graph packets proof authority,
authorize graph pruning, define MCP transport behavior, or upgrade a stale
global graph. Session-specific anchors, payloads, seeds, timings, and
experimental history remain in session provenance.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.AGENTS.md`
- `PIPELINE.md`

## Follow-Up Route

Keep the relation visible through bounded graph bridge and timeline routes,
then verify source, portable bundle, and configured read-only access-plane
parity. Reopen the decision if randomized parallel-agent cases expose false
correlation, or if another representation preserves equal relation precision
and provenance at materially lower graph cost.

## Verification

The decision follows a gold-first archived positive case and a neighboring
foreign-correlation negative case whose raw and segment refs were inspected
manually. Owner-neutral regression coverage checks classification, exact
same-correlation admission, foreign-status rejection, graph edge direction,
and raw-ref preservation. Typed bridge and event-centered timeline packets are
then compared against the same evidence span; private coordinates and measured
latency remain in session provenance.
