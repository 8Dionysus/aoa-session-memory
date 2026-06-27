# Config AGENTS.md

## Purpose

This directory holds portable policy and classification inputs for the
session-memory kernel.

Config files shape naming, event taxonomy, distillation routing, and batch
review lanes. They are machine-readable route law, not generated reports.

## Authority

- `naming-policy.json` defines durable label and semantic-name policy,
  including portable domain/action hints for mass naming waves.
- `event-taxonomy.json` defines universal event facets.
- `event-distillation-routes.json` maps event classes toward review lanes.
- `batch-distillation-policy.json` controls first-wave batch review routing.
- `atlas-policy.json` defines the source skeleton and generated-entry contract
  for the agent-facing atlas under `maps/`.
- `graph-quality-regression-corpus.json` defines source-owned graph-quality
  regression controls for pre-GraphRAG trust gates.
- `live-scenario-regression-corpus.json` defines source-owned live scenario
  route-quality controls for consumer-loop regressions; it is not memory truth.
- `naming-golden-set.json` defines portable naming-quality examples for
  mass naming wave regression checks.
- `search-providers.json` defines the portable SQLite default, optional host
  provider gates, and local embedding/reranker accelerator probes. Host
  providers are accelerators, not archive authority.

## Rules

- Keep config portable. Do not hard-code local AoA project facts unless the
  config is explicitly about portable defaults.
- Preserve `schema_version` and structured JSON shape.
- Do not hide policy changes inside generated indexes.
- After taxonomy, route-signal, naming, or atlas routing changes, reindex or
  validate the affected generated surfaces.
- Update tests and nearby docs when config semantics change.

## Checks

Run at least:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_session_memory.py
python3 scripts/aoa_session_memory.py doctor --workspace-root /srv/AbyssOS --aoa-root /srv/AbyssOS/.aoa
```
