# Decision Records Index

This directory is the durable decision-rationale surface for
`aoa-session-memory`.

Use it when a future contributor needs to recover why an archive boundary,
projection contract, query route, freshness rule, orchestration posture,
portable boundary, or storage tradeoff was selected. Ordinary implementation
notes, runtime diagnostics, generated output, private session evidence, and
one-off experiment logs remain in their owning surfaces.

## Operating Card

| Field | Route |
| --- | --- |
| role | durable decision rationale and agent-facing index chooser |
| input | changed owner surface, rejected alternative, projection boundary, freshness failure, or portability pressure |
| output | canonical decision record, generated lookup indexes, and route back to current source |
| owner | `docs/decisions/AGENTS.md` for lane law; decision records for rationale; generated indexes for lookup only |
| next route | current source first, then root `AGENTS.md`, `DESIGN.md`, `DESIGN.AGENTS.md`, `PIPELINE.md`, or the affected schema/config/script owner |
| validation | decision-index regeneration/check plus the affected owner checks |

## Authority

Decision records explain why a route was chosen. They are weaker than the
source surface they describe:

- raw transcript JSONL remains evidence authority;
- session manifests, raw block ledgers, segments, and session indexes remain
  evidence-preserving derived surfaces;
- query, semantic, graph, registry, diagnostics, and narrative projections
  remain rebuildable read models;
- current executable behavior stays in `scripts/aoa_session_memory.py` and its
  source-owned configuration and schemas;
- operational lifecycle and recovery stay in `PIPELINE.md`;
- MCP remains a read-only access plane owned by its stack package;
- the standalone bundle is generated through the portable export route.

Generated decision indexes and the workspace decision graph are navigation
read models. They do not own rationale.

## Index Shape

Every decision has:

- a canonical `Decision ID: AOA-SM-D-####`;
- a full canonical-ID filename such as `AOA-SM-D-0001-*.md`;
- an `## Index Metadata` block naming original date, owner surfaces, surface
  classes, projection layers, guard families, and posture.

Generated indexes under [indexes](indexes/README.md) provide lookup:

- [by canonical ID and number](indexes/by-number.md);
- [by date](indexes/by-date.md);
- [by surface class](indexes/by-surface.md);
- [by projection layer](indexes/by-projection-layer.md);
- [by guard family](indexes/by-guard.md).

Use an index to find a source decision, then return to the current owner
surface before changing behavior.

## Addressing

Active source paths use the full canonical ID:

- `docs/decisions/AOA-SM-D-0001-*.md`;
- `docs/decisions/AOA-SM-D-####-*.md`.

IDs and filenames are never renumbered. Historical paths belong to Git, PR, or
release history, not to a compatibility lookup layer.

## Template

Start from [TEMPLATE.md](TEMPLATE.md). A decision should explain a real choice,
its alternatives, rationale, tradeoffs, boundaries, source surfaces, and
verification route. If the note would only repeat a diff, do not create it.
