# Semantic Generation Pins for Evaluation Admission

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0024
- Original date: 2026-07-19
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `READINESS.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: evaluation, projection freshness, maintenance coordination, reproducibility, answer admission
- Projection layers: raw and session source identity, search, episode semantic, dense, entity registry, graph, Atlas, operational rollups
- Guard families: generation compatibility, semantic identity, maintenance lease, active-writer refusal, before-after drift, evaluation abstention
- Posture: accepted

## Context

An evaluation can issue several retrieval calls across independently published
search, episode, registry, dense, graph, and Atlas projections. Atomic
publication protects each store, but it does not by itself prove that every
candidate and score in one evaluation came from the same complete semantic
generation. A concurrent writer can advance one projection between lanes, and
an old or unknown generation can remain physically readable while no longer
being an admissible answer source.

Physical identity is not semantic identity. SQLite page layout, inode, mtime,
journals, publication clocks, and generated observation timestamps may change
across two semantically identical atomic rebuilds. Pinning those observations
would reject reproducible results for irrelevant physical differences, while
pinning only a producer version would miss stale rows, incompatible dependency
generations, or changed source content.

## Options Considered

- Trust the projection status observed at evaluation start. Rejected because a
  later lane can read a different generation and still produce individually
  valid packets.
- Pin database byte hashes, inode, mtime, and generated timestamps. Rejected
  because semantically identical atomic publication may legitimately change
  all of them.
- Pin only schema and current producer versions. Rejected because compatible
  producers do not prove that every selected source and persisted projection
  was actually rebuilt with those versions.
- Pin source and projection semantic identities, require current generation
  compatibility, hold the shared maintenance lease for the evaluation, and
  compare the complete snapshot before admitting results.

## Decision

Answer-bearing evaluations use a versioned semantic generation pin.

The pin records the sealed source scope, raw and manifest identities,
resolvable session and segment projection generations, current expected
producer and dependency generations, and semantic digests for every applicable
search, episode, registry, dense, graph, Atlas, and operational projection.
Semantic digests exclude observation clocks and physical publication details
that do not change query meaning. Physical file observations remain available
for race diagnosis, but they do not define evaluation identity.

Pin capture and check use the shared maintenance coordinator in read mode. An
active projection writer causes immediate refusal and no pin manifest is
published. A missing, incomplete, unreadable, unknown, or incompatible
generation also refuses capture before candidate generation.

A generation-pinned evaluation holds the same lease while it takes the initial
snapshot, executes its bounded routes, and takes the final snapshot. Results
and scores are admissible only when both snapshots are complete and compatible
and their semantic identities are identical. Drift, active-writer conflict, or
incompatibility returns an explicit abstention with no admitted score.

Two rebuilds from the same stronger sources, configuration, and generation
identity are considered the same evaluation generation when their semantic
projection digests match, even if SQLite bytes or atomic-publication
observations differ.

## Rationale

This boundary makes an A/B result reproducible at the level that affects
retrieval meaning while retaining enough physical observation to diagnose a
race. The maintenance lease prevents cross-projection mixing during one
evaluation, and the compatibility inventory prevents a readable legacy row
from entering a current score.

Failing before candidate generation is safer than attaching a warning to a
mixed result. Excluding volatile physical state avoids the opposite error:
discarding a valid deterministic comparison because an atomic writer produced
different filesystem or SQLite layout.

## Consequences

- Positive: every admitted multi-lane evaluation names one complete semantic
  source and projection generation.
- Positive: active writers, stale producer generations, and mid-run drift have
  distinct, machine-readable refusal states.
- Positive: deterministic double rebuild can be proved without requiring
  byte-identical SQLite files.
- Tradeoff: a full-scope snapshot hashes semantic projection content and can
  be expensive; sealed session scopes should be used when they are sufficient.
- Tradeoff: legacy or partially rebuilt installations cannot produce admitted
  scores until their affected projections catch up.
- Follow-up: keep evaluation consumers, portable source, skill, CLI, and MCP
  presentations aligned with the same refusal and freshness semantics.

## Boundaries

The generation pin is a reproducibility and admission guard, not evidence
authority and not proof that a retrieved claim is semantically correct. Raw
session evidence and external owner sources remain stronger than every pinned
projection.

The shared lease protects one process-local evaluation. Serialization of
automatic goal turns and ownership of mutable experiment roots remain duties
of the stronger agent-runtime scheduler. The pin is defense in depth and must
not be presented as solving scheduler ownership.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `READINESS.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

Run a sealed deterministic double rebuild, capture and recheck one pin across
the semantically identical rebuild, and execute the gold A/B and ablation
corpus under that pin. Reopen this decision if a query-relevant field is absent
from semantic identity or if an excluded physical field is shown to alter
retrieval behavior.

## Verification

Focused contracts cover active-writer refusal without manifest publication,
incompatible producer refusal, mid-run drift rejection, semantic artifact
drift, generationless operational rollups, and acceptance of semantically
identical atomic republish despite changed file observations and clocks.

Release proof additionally requires the full source suite, deterministic
double rebuild of a sealed real-session scope, manual evidence-ref review, and
generation-matched source, portable, CLI, skill, and MCP packets.
