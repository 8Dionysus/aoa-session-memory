# Durable Thin Hook Ingress Before Projection

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0089
- Historical source decision ID: AOA-SM-D-0072 (unlanded hook line; current owner ID is already assigned to a different accepted decision)
- Original date: 2026-08-13
- Owner surfaces: `scripts/aoa_session_hook.py`, `scripts/aoa_session_memory.py`, `hooks/`, `PIPELINE.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: hooks, scheduling, evidence intake, recovery, performance, privacy
- Projection layers: hook ingress, hook receipts, session registry, hook worker queue
- Guard families: durable enqueue, exact-byte integrity, duplicate coalescing, single-flight execution, fail-open rollback, private runtime evidence
- Posture: accepted

## Context

Every Codex hook previously started the complete session-memory implementation,
whose projection and retrieval surface is intentionally large. Even a prompt
receipt therefore paid the import memory and latency of unrelated archive,
search, graph, and maintenance code. Raw-unavailable lifecycle events also
rebuilt all registry navigation derivatives in their synchronous path.
User-level and project-level hook discovery could repeat that cost for the same
runtime signal.

The hook boundary must become materially faster without dropping raw input,
receipts, incidents, recovery, or exact owner handling.

## Options Considered

- Keep the monolithic command and optimize individual handler branches.
  Rejected as the primary route because import cost remains on every event;
  derived-registry deferral alone removes only part of the latency.
- Store only selected hook metadata. Rejected because it weakens recovery and
  loses adapter fields that future owner handling may require.
- Fire an unrestricted background projection process for every event. Rejected
  because bursts and duplicate hook discovery can amplify memory and writer
  contention.
- Durably enqueue exact bytes through a small adapter, coalesce byte-identical
  signals with counts, and replay them through one bounded owner worker.

## Decision

Generated Codex hooks invoke the standard-library-only
`scripts/aoa_session_hook.py` ingress. Before returning it atomically persists
the exact stdin bytes, digest, byte count, event kind, selected roots, private
posture, and observation count under an owner-private runtime queue.

The event-kind and exact-byte digest is the active duplicate identity. A second
identical signal updates the count and observation window instead of creating
another projection execution. Different bytes remain distinct.

Lifecycle events wake one single-flight dispatcher. Outside foreground hook
latency, the full owner process validates the envelope and invokes the existing
handler, receipt writer, and bounded follow-up worker under the shared
maintenance lease. The scheduled retry route drains pending ingress after
contention. Raw-unavailable lifecycle replay preserves the exact incident,
diagnostic, manifest, and minimal session-registry record before deferring only
the derived name and directory indexes.

`AOA_SESSION_MEMORY_HOOK_FAST_INGRESS=0` selects the previous synchronous
handler. A durable-enqueue failure attempts that handler automatically before
the adapter fails open.

## Rationale

The foreground cost now scales with one small durable write rather than the
size of the complete projection engine. Exact bytes remain available to the
same owner semantics, so speed does not come from narrowing the evidence.
Single-flight launch and the existing maintenance lease prevent process and
writer amplification. Digest, byte-length, root, schema, and event checks make
the deferred boundary explicit rather than treating process exit as proof.

The name and directory indexes are rebuildable navigation views. Deferring
their complete refresh after the incident manifest and minimal registry record
exist preserves immediate session visibility and evidence authority while
removing work proportional to the whole archive from one session's hook.

## Consequences

- Positive: the active Codex session no longer imports the complete projection
  engine for every hook.
- Positive: identical global/project signals execute owner projection once and
  retain an observable count.
- Positive: exact private input, incident semantics, normal receipts, recovery,
  and an immediate synchronous rollback remain available.
- Tradeoff: successful queue admission means pending capture; projections may
  become current shortly afterward rather than before the hook returns.
- Tradeoff: a host with continuous maintenance-lock contention can delay replay;
  queue age and pending counts must remain visible and scheduled recovery must
  continue.

## Boundaries

Ingress success does not prove transcript availability, archive completeness,
projection freshness, registry currentness, or hook discovery correctness.
Coalescing applies only to byte-identical events and does not merge different
payloads. The adapter does not bypass the owner handler, maintenance lease,
resource controls, privacy rules, or fail-closed projection validation.

## Source Surfaces

- `scripts/aoa_session_hook.py`
- `scripts/aoa_session_memory.py`
- `hooks/`
- `PIPELINE.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Regenerate hook configuration only after source, portable, and live shadow
proof. Observe foreground wall/RSS, ingress age and counts, worker single-flight
behavior, exact replay, and current-generation archive state before broad
runtime rollout.

## Verification

Focused tests cover exact-byte round trip, owner-private modes, duplicate signal
counting both before and during owner replay, ordinary owner replay,
raw-unavailable incident and registry recovery, scheduled drain, durable
receipt counts, and generated command selection. The synchronous rollback is
kept as the explicit environment-controlled fallback rather than counted as
live rollout proof. The complete source suite passed all 1,178 then-existing
tests; the final late-arrival race and corrupted-envelope identity/quarantine
regressions then passed focused proofs. A clean portable export passed the
public-safety audit, installed into an isolated workspace, passed all 29
source-validation checks and doctor, and replayed two identical ingress signals
through one owner hook event with no pending, running, or failed work.
An isolated foreground A/B reduced the hook process from roughly 2.2--2.8
seconds and about 541 MiB RSS to roughly 0.05--0.09 seconds and about 22 MiB
RSS; these are bounded experiment observations, not a permanent host claim.
Actual user/project hook placement and post-rollout live-session observation
remain separate runtime gates.
