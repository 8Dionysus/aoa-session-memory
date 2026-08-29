# Explicit Context Additions Continue Open Task Episodes

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0036
- Original date: 2026-07-28
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: episode formation, conversation acts, evidence granularity, projection generation
- Projection layers: task episodes, segment indexes, semantic representations, evidence packets
- Guard families: semantic boundary, explicit operator signal, evidence refs, generation compatibility, fork isolation
- Posture: accepted

## Context

Task episodes represent work lifecycles rather than transport turns. The
episode builder already keeps corrections, failure observations, resume
requests, exact replayed intent, runtime envelopes, and structured skill
selection with an open lifecycle when their typed evidence proves
continuation.

An explicit operator addition such as a new constraint or a refinement of the
agreed research scope did not have a corresponding conversation act.
Consequently, every such canonical user message closed the active episode and
opened another one. That false split separated one initiating intent from the
constraints governing its execution and weakened later provenance,
failure/recovery review, and role-aware retrieval.

Merging successive prompts because they are adjacent, lexically similar, or
close in embedding space would create the opposite error: unrelated tasks
could be collapsed into one lifecycle.

## Options Considered

- Keep every otherwise unclassified canonical user message as a new task
  episode. Rejected because explicit additive constraints fragment one
  evidenced work lifecycle.
- Merge successive prompts using adjacency or semantic similarity. Rejected
  because neither proves shared task identity and the result would be
  non-specific semantic noise.
- Use an opaque model classifier to decide whether every prompt continues the
  task. Rejected because boundary generation would become difficult to
  reproduce, explain, and migrate safely.
- Admit a conservative typed context-addition act only for explicit additive
  language, and continue it only while a task episode is still open.

## Decision

The conversation-act classifier recognizes a bounded
`operator_context_addition` act when the operator explicitly marks a statement
as an additional constraint, refinement, or consideration. The signal is
lexically explicit, multilingual only where declared, and rejects questions
and clear task-switch language such as a new or different task.

An `operator_context_addition` continues the current task episode when that
episode is open. Its canonical raw ref is added to intent evidence, its
semantic representation records `context_addition`, and the continuation
records `typed_operator_conversation_act` as its admission basis.

A Codex `task_complete` followed by `task_started` is a runtime turn boundary,
not sufficient evidence of a new semantic task. A typed user continuation may
bridge one immediately adjacent runtime-started episode only when that bridge
contains no user intent, agent response, action, result, verification, or
correlation evidence and the preceding episode contains the corresponding
runtime completion. Eligible typed relations are context addition, correction,
failure observation, resume, and an exact replay whose text carries enough
specific intent to distinguish it from a generic approval. Short approvals
such as `Давай` or `go ahead` are not replay evidence merely because the same
words appeared in a prior episode. The runtime boundary ref remains in
transition evidence, and the prior episode is reopened until subsequent
lifecycle evidence closes it again.

If the first canonical user message after the empty runtime boundary is not a
typed continuation of the preceding episode, that message becomes the first
semantic intent of the runtime-started episode. The transport boundary is
retained as its coordinate, but the builder does not close an empty episode
and create a second episode for the same new prompt.

Structural lineage and automatic goal-continuation boundaries remain
stronger. A context-addition message with no prior episode starts a lifecycle
rather than being attached backward. An unrelated prompt after a runtime
boundary remains a new task. Fork-local boundaries, delegated task starts,
replay handling, and runtime envelope rules otherwise remain unchanged.

The conversation-act schema and task-episode boundary policy each advance
their generation version. Projections built with the prior classifier or
boundary policy must not be admitted as compatible current episode state.

## Rationale

The chosen rule uses the operator's explicit discourse signal instead of
guessing shared meaning from proximity. It repairs a demonstrated false split
while keeping unrelated-task separation conservative and deterministic.

Preserving the raw ref and typed admission basis makes the merge reviewable.
Advancing both generation components ensures that segment indexes, task
episodes, search joins, and downstream semantic projections can detect the
changed interpretation and rebuild rather than silently mix policies.

## Consequences

- Explicit new constraints remain connected to their initiating work
  lifecycle and its later actions, results, failures, and verification.
- Exact raw coordinates and semantic representations expose why the message
  was treated as a continuation.
- Empty runtime turn envelopes do not create false semantic episodes when
  typed continuation evidence follows them.
- A genuine new prompt adopts its preceding empty runtime envelope instead of
  leaving a no-intent episode behind.
- Clear task switches, questions, structural lineage boundaries, and
  evidence-bearing intervening episodes do not inherit this continuation
  rule.
- Repeated generic approvals remain separate task intents instead of being
  mislabeled as exact replay.
- Additive phrasing outside the declared patterns may remain conservatively
  split until real evidence justifies another typed rule.
- A classifier or boundary-policy upgrade makes older affected projections
  incompatible and requires generation-aware catch-up or rebuild.

## Boundaries

This decision does not merge prompts through embeddings, infer task identity
from turn adjacency alone, bridge an episode containing work evidence,
classify follow-up questions, weaken fork isolation, or make derived episode
text authoritative. Runtime completion remains preserved evidence; it is
merely insufficient by itself to defeat a later explicit continuation. This
decision does not claim complete natural language coverage. Raw session events
remain the evidence authority, and an episode remains a rebuildable
projection.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Rebuild episode and dependent search projections under the new generation,
then inspect independently selected positive and negative raw refs. Extend the
typed rule only after a sealed false-split case demonstrates a missing
explicit form; do not broaden it from synthetic phrase coverage alone.

## Verification

Focused regressions require an independently selected real-shaped additive
prompt to bridge an otherwise empty `task_complete → task_started` transport
boundary and stay in one episode with resolvable initiating-intent,
runtime-boundary, and continuation refs. Negative cases require explicit task
switches and evidence-bearing intervening episodes to remain separate, while
standalone additions begin their own lifecycle. Deterministic double proof
must produce the same semantic packet from the same raw bytes and producer
generation. Full repository, migration, portable-export, and
generation-incompatibility checks remain required before landing.
