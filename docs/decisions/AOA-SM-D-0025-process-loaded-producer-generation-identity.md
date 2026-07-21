# Process-Loaded Producer Generation Identity

## Status

Accepted.

## Index Metadata

- Decision ID: AOA-SM-D-0025
- Original date: 2026-07-19
- Owner surfaces: `scripts/aoa_session_memory.py`, `PIPELINE.md`, `READINESS.md`, `tests/test_session_memory.py`, `docs/decisions/`
- Surface classes: projection freshness, reproducibility, migration, maintenance coordination
- Projection layers: session index, segment index, episode source, search, episode semantic, dense, entity registry, graph, Atlas, operational rollups
- Guard families: generation compatibility, producer identity, atomic publication, before-after drift
- Posture: accepted

## Context

Projection generation identity must describe the code that actually produced
the rows. A long-running writer may start from one source snapshot while the
script path is replaced during its work. Hashing that path again while
constructing rows can falsely label old in-memory code as a newer producer.
Conversely, publishing after the source changed leaves a process whose
generation is reproducible but whose executable path no longer identifies the
loaded implementation.

This ambiguity affects session and segment indexes as well as every dependent
search, episode, registry, graph, Atlas, dense, and operational projection. A
schema version alone cannot distinguish the two implementations.

## Options Considered

- Read the producer file whenever a generation identity is requested.
  Rejected because a running process can silently switch the identity it
  reports without switching the code it executes.
- Use only the repository commit or package version. Rejected because dirty,
  installed, standalone, and portable source snapshots can execute outside a
  matching Git checkout.
- Hash the producer bytes loaded at process start, use that identity for the
  whole process, and refuse atomic publication if the source path changes
  before the publish gate.

## Decision

Every projection generation produced by the portable kernel is pinned to the
producer bytes loaded by that process.

At module load, the kernel records the resolved producer path and its SHA-256.
Generation identities use that immutable process-loaded digest rather than
rehashing a mutable path. A writer rechecks the producer path immediately
before each atomic publication. Missing, unreadable, or changed source refuses
publication and preserves the last-good projection.

Dependent generation identities include the pinned producer identity. Old,
unknown, or incompatible generations remain physically readable only where an
explicit stale-readable contract allows it; they do not become answer
candidates.

## Rationale

The loaded byte snapshot is the narrowest reproducible identity of the code
that performed the work across source, installed, and portable execution. The
pre-publish stability gate prevents that reproducibility identity from
becoming detached from the executable source operators will inspect or rerun.

This preserves atomic last-good behavior without requiring a repository to be
clean or a Git commit to exist. It also keeps generation changes explicit when
the portable kernel changes even if higher-level schemas do not.

## Consequences

- Positive: a single process cannot stamp projections with code it did not
  load.
- Positive: source replacement during a long build produces a visible
  no-publish result and leaves readers on the last-good generation.
- Positive: source, installed, and standalone producers can prove parity by
  byte identity without making Git a runtime authority.
- Tradeoff: any kernel-byte change creates new expected projection
  generations and requires bounded catch-up or an explicit full rebuild.
- Tradeoff: a writer whose source path changes must rerun from the new producer
  even when its staged semantic output would otherwise be valid.

## Boundaries

The producer digest proves implementation identity, not semantic correctness,
freshness, evidence quality, or repository current state. Raw evidence and
external owner sources remain stronger than every projection.

The stability gate is defense in depth inside one writer. Serialization of
multiple goal turns and ownership of mutable experiment roots remain duties of
the stronger agent-runtime scheduler.

## Source Surfaces

- `scripts/aoa_session_memory.py`
- `PIPELINE.md`
- `READINESS.md`
- `tests/test_session_memory.py`
- `docs/decisions/`

## Follow-Up Route

After a producer change, install the exact final kernel into the target,
preserve raw-source digests, rebuild dependent projections in declared order,
and compare their stored producer identities before admitting evaluation
results.

## Verification

Focused contracts change the producer path during session, search, graph, and
entity-registry builds and require refusal without partial publication. A
sealed multi-session rebuild verifies that every session and segment row names
one process-loaded producer digest. Release proof also requires the full suite,
source-to-portable parity, and a deterministic double rebuild from the final
installed producer.
