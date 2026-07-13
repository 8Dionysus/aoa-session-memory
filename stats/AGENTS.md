# Stats AGENTS.md

## Applies to

This card applies to `stats/` and all descendants.

## Role

`stats/` is the owner-local measurement port for the portable session-memory
kernel. It defines session-memory-domain questions, populations, evidence refs,
and authority ceilings while using the central `aoa-stats` grammar.

It does not own raw sessions, reviewed memory, retrieval truth, eval verdicts,
runtime maintenance, MCP behavior, user assessment, or cross-repository
aggregation.

## Read before editing

1. Root `AGENTS.md`, `DESIGN.md`, `PIPELINE.md`, and `READINESS.md`.
2. This district's `README.md` and `port.manifest.json`.
3. The source corpus, fixture contract, and executable consumer named by the
   measurement.
4. The central `aoa-stats` measurement and local-port contracts.

## Boundaries

- Derive only from portable, source-owned surfaces and keep evidence refs
  repository-relative.
- Never inspect or copy a live `.aoa` archive to refresh the committed packet.
- Keep executed, skipped, failed, and unknown scenario states distinct.
- Treat fixture coverage as portable proof capacity, not route correctness,
  memory quality, adoption, or live readiness.
- Keep the current export reference-only and free of raw content and session
  identifiers.

## Validation

```bash
python3 scripts/validate_local_stats_port.py
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q -p no:cacheprovider tests/test_session_memory.py -k local_stats
```

The full owner validation route remains in `scripts/AGENTS.md`.

## Closeout

Report the question, population, source revision, numerator and denominator,
reference posture, authority ceiling, central protocol result, and owner
derivation result.
