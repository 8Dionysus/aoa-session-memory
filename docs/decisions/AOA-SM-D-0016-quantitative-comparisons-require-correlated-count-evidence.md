# Quantitative Comparisons Require Correlated Count Evidence

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0016
- Original date: 2026-07-17
- Owner surfaces: `scripts/aoa_session_memory.py`, `tests/test_session_memory.py`, `DESIGN.AGENTS.md`, `docs/decisions/`
- Surface classes: query routing, semantic retrieval, evidence reading, answer admission
- Projection layers: semantic episode, query-time raw hydration, action-result chain
- Guard families: quantitative comparison, subject-context-baseline match, correlation ownership, numeric result, bounded raw scan, abstention
- Posture: accepted

## Context

A comparative question such as which parts changed most is stronger than a
request for semantically related work. Episode ranking can find a highly
similar task without finding the measurement that answers the comparison.
Version mentions and current-tree counts can also resemble the query while
failing to measure changes from the requested baseline.

Admitting the top lexical or semantic neighbor in this lane therefore turns a
navigation score into an unsupported quantitative claim. The evidence reader
needs a typed way to recover an available measurement without treating every
ordinary episode query as a raw-transcript scan.

## Options Considered

- Admit the highest lexical or reranked episode when its terms closely match
  the subject and baseline. Rejected because similarity does not prove that a
  comparative measurement was performed or returned.
- Fail closed whenever the episode projection lacks a complete quantitative
  representation. This is safe but discards an already recorded structured
  action and result that can be recovered within a bounded session scope.
- Add a persistent quantitative index before admitting this query family.
  Rejected until repeated demand and storage evidence justify another
  projection and freshness dependency.
- Hydrate only an explicitly recognized quantitative-comparison query from
  bounded raw evidence, then admit a result only through one matching
  structured action-result chain.

## Decision

An episode candidate does not answer a quantitative comparative question by
lexical, dense, fusion, or reranking strength alone.

For a session-scoped comparison of changes, the query-time reader may inspect
bounded archived raw evidence. It qualifies a candidate only when it finds:

- a structured counting or ranking action whose command and work context match
  the requested subject, context, and baseline;
- a successful result owned by the same correlation identity and occurring
  after the action;
- at least two parseable numeric result rows in the requested rank direction;
  and
- one unambiguous action-result chain inside the candidate episode.

The qualified action and result refs become the leading supporting evidence.
If the chain is missing, ambiguous, mismatched, failed, truncated beyond the
required evidence, or outside the bounded scope, the answer reader abstains.
Current-size counts, version mentions, and nearby foreign results do not
satisfy the gate.

## Rationale

The selected route makes the evidence shape match the claim shape. Subject,
context, and baseline matching prevents a valid measurement of the wrong
thing from winning through shared vocabulary. Correlation ownership prevents
parallel or adjacent outputs from becoming consequences of the wrong action.
Numeric rows and successful status prove that the requested measurement
produced a usable ranked result rather than merely being discussed.

Query-time hydration avoids a new persistent projection and its storage and
freshness burden while demand remains narrow. Explicit byte, line, action, and
chain limits keep the escalation reviewable. Preserving raw, segment, and
session refs keeps the result navigational and auditable rather than promoting
session evidence into owner truth.

## Consequences

- Quantitative comparison questions can abstain even when ordinary episode
  retrieval has a strong semantic neighbor.
- A matching archived counting chain can recover precision without becoming a
  default raw scan for unrelated semantic queries.
- The bounded raw read adds latency to this specific lane and exposes its
  scanned scope and truncation state.
- Additional command shapes or result formats require manual evidence before
  widening the parser or introducing a persistent projection.
- Global comparative questions still require a separately bounded seed and
  global/narrative evidence route; this session-scoped gate does not claim
  archive-wide completeness.

## Boundaries

This decision governs answer admission for a narrow quantitative-comparison
query family. It does not make session measurements current repository truth,
define a general analytics engine, prove the meaning of arbitrary numeric
output, authorize an unbounded archive scan, or replace global narrative
retrieval. It does not change raw authority or permit a stale projection to be
presented as current. Session-specific queries, commands, counts, seeds,
coordinates, and timings remain in session provenance.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `tests/test_session_memory.py`
- `DESIGN.AGENTS.md`

## Follow-Up Route

Continue independently seeded multilingual, wrong-subject, wrong-baseline,
current-size, foreign-correlation, ambiguous-chain, failed-result, and
truncation trials. Reopen this decision if those trials show lost supported
recall, an admitted mismatched measurement, or enough recurring global demand
to justify a separate quantitative projection.

## Verification

A gold-first archived-session trial exposed a strong semantic answer whose
support did not contain the requested baseline comparison. The corrected route
recovers the matching structured counting action and its correlation-owned
successful numeric result, while a wrong-subject variant abstains. An
owner-neutral regression reproduces the broken admission, covers Russian and
English query forms plus negative measurements, and passes with the selected
gate. The complete source test suite and source validation remain supporting
mechanical checks rather than semantic proof.
