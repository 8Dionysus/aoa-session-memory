# Provenance-Preserving Fork Lineage Consolidation

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0005
- Original date: 2026-07-15
- Owner surfaces: `scripts/aoa_session_memory.py`, `DESIGN.AGENTS.md`, `docs/decisions/`
- Surface classes: evidence provenance, episode formation, query routing
- Projection layers: session lineage, task episode, episode retrieval
- Guard families: raw preservation, structural fork boundary, transport-intent separation, exact replay match, local work attribution
- Posture: accepted

## Context

A forked runtime session may physically contain a prefix replayed from its
parent. Raw preservation must retain that prefix because it records what the
child runtime received. Treating every replayed event as newly performed child
work, however, duplicates semantic candidates and can falsely attribute the
parent's actions or outcomes to the child.

The organ therefore needs a retrieval-level consolidation rule that reduces
proved replay noise without deleting physical evidence or merging merely
similar work.

## Options Considered

- Discard the replayed prefix from the child archive. Rejected because it
  destroys evidence of the child's actual runtime input.
- Index every physical copy as independent work. Rejected because it increases
  semantic noise and can attribute parent work to the child.
- Deduplicate by fuzzy text similarity. Rejected because similar evidence may
  describe distinct actions, outcomes, or later corrections.
- Preserve every physical copy, classify the structural fork boundary, and
  consolidate only an exact, unambiguous parent-evidence match at retrieval
  time.

## Decision

Preserve fork replay physically and consolidate it conservatively in episode
retrieval.

The adapter records declared parent identity and a structural boundary between
the replay candidate and local child work. A pre-boundary episode is only a
replay candidate. It may share one retrieval group with a parent episode only
when the fork is explicitly declared, the episode is wholly before the local
child-work boundary, relevant supporting evidence matches exactly after
conservative normalization, and the parent match is unambiguous.

The parent episode represents the consolidated retrieval group while the
packet retains every member session, segment, and raw ref. Local child work,
missing parents, ambiguous matches, and merely similar evidence remain
separate and expose their diagnostic posture.

## Rationale

This route separates physical provenance from semantic presentation. Raw
evidence remains complete, while a proved replay does not occupy several
independent semantic result slots or become child-authored history. Exact and
unambiguous matching fails closed: unresolved duplicates cost some retrieval
space, but distinct experience is not silently merged.

## Consequences

- Fork archives retain their full replayed input and remain independently
  inspectable.
- Episode retrieval can reduce exact replay duplication without losing member
  refs.
- Local child work is never collapsed merely because it resembles parent work.
- Missing or ambiguous parent evidence leaves duplicate candidates visible and
  requires downstream handling rather than a guessed merge.
- Consumers must treat `pre_child_task_history_candidate` as candidate
  attribution and `local_fork_work` as child-local scope.

## Boundaries

This decision governs declared session lineage, task-episode scope, and
episode-result consolidation. It does not infer lineage for adapters without
explicit structural evidence, delete raw events, prove that replayed content
is true, or authorize equivalent graph or narrative consolidation. Those
projections require their own evidence and review before adopting the rule.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.AGENTS.md`

## Follow-Up Route

Keep graph and narrative projections separate until manual fork cases prove
that an equivalent lineage-aware consolidation improves their intended query
lanes without erasing physical refs or local child work.

## Verification

Focused owner tests cover structural parent/boundary extraction, separation of
replayed and local task episodes, exact parent-evidence consolidation, member
ref retention, ambiguous or near-match refusal, and local-work non-collapse.
Manual provenance review remains required before extending this policy to a
new adapter or projection layer.

## Review Amendment — 2026-07-19

Manual review of a real declared subagent fork exposed two coordinates that
must not be collapsed into one semantic boundary:

- the adapter's developer bootstrap is a transport/control coordinate and
  remains the final physical prefix coordinate when present;
- the following structured child `task_started` event begins child-local work,
  but does not by itself contain the delegated task semantics.

A structurally parsed inter-agent `NEW_TASK` message may contribute a local
intent ref. When its task body is encrypted or otherwise unavailable, the
projection records only the clear delegation envelope and an explicit
unavailable-content status; it must not infer task details.

Repeated `NEW_TASK` envelopes belong to the same episode only while that
lifecycle remains open. Their physical refs may remain visible, while the
transition retains the first admitted initiating delegation ref. A structured
`task_complete` is terminal for that delegated lifecycle. A later
`task_started` opens a new structural lifecycle coordinate and its following
`NEW_TASK` supplies the observable delegated intent. If the runtime omits that
coordinate, a `NEW_TASK` observed after a terminal episode is the bounded
semantic fallback for starting a new lifecycle. Matching task names or
transport identities, especially with encrypted bodies, do not prove that two
delegations are semantic replays of the same task.

This clarification preserves the original decision: physical replay,
bootstrap control, each runtime lifecycle start, each terminal completion, and
delegated intent remain distinct evidence coordinates. Focused regressions and
an independently sealed real-session fork case verify the separation; the
private refs and transcript content remain in session-local provenance rather
than this decision record.
