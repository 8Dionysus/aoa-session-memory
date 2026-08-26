# Schemas AGENTS.md

## Purpose

This directory holds JSON schema contracts for portable archive artifacts.

Schemas define machine shape. They do not decide runtime truth, review status,
or naming semantics by themselves.

## Authority

- `atlas-route-entry.schema.json` describes generated atlas route entries.
- `hook-receipt.schema.json` describes persisted hook receipts.
- `incident.schema.json` describes diagnostic incidents.
- `live-tail.postings.schema.json` describes the compact manifest for bounded
  persistent live-tail posting shards.
- `live-tail.postings-shard.schema.json` describes one bounded, redacted
  posting shard used for exact candidate selection before raw verification.
- `raw-capture-state.schema.json` distinguishes preserved-but-unindexed raw
  evidence from a capture committed with one session projection generation.
- `segment.index.schema.json` describes generated segment event indexes.
  It includes immutable segment component identity, index-first render mode,
  and route-signal projections such as `by_route_layer` and `by_route_signal`.
- `identity-bound-session-telemetry.schema.json` describes public-safe typed
  validation-owner receipts, session-memory identity packets, and
  admission-only pair results. It does not grant validation or evaluation
  authority.
- `epistemic-action-event-chain.schema.json` describes the append-only,
  digest-bound prediction/action/observation chain and its shadow-only
  model-update candidate. It contains no raw prompt or tool payload fields.
- `session.manifest.schema.json` describes session archive manifests.
- `skill-usage-receipt.schema.json` describes one immutable, owner-reviewed
  positive skill-use evidence packet. It may admit invocation, verification,
  deflection, and an effect-attribution candidate, but never a benefit or
  promotion verdict; those remain with `aoa-evals`.
- `inference-economy-session-contribution.schema.json` describes an opt-in,
  count-only session-memory contribution for token and compaction evidence.
  It is adapted into the central `aoa-stats` economy observation and carries
  no lifecycle or acceptance authority.
- `token-accounting.schema.json` describes count-only token observations and
  aggregate ledgers. Provider-reported, exact-tokenizer, and estimated counts
  are separate ledgers.

## Rules

- Keep schema changes backward-aware. Existing archives may outlive the code
  version that created them.
- Do not relax required evidence fields just to make bad data pass.
- If a schema changes, update writer code and regression tests together.
- Generated archives should be repairable from raw evidence or explicit
  diagnostics, not by silently weakening schemas.

## Checks

Run:

```bash
python3 -m py_compile scripts/aoa_session_memory.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_session_memory.py
```
