# AGENTS.md

## Applies to

This card applies to `docs/decisions/` and the durable decision records inside
it.

## Role

Decision records preserve why durable archive, projection, query-route,
freshness, orchestration, portability, evidence-boundary, or storage choices
were made in `aoa-session-memory`.

They do not make current behavior by themselves. Current behavior remains in
the owning source, schema, configuration, route, and pipeline surfaces.

## Read before editing

Read:

1. repository root `AGENTS.md`;
2. `docs/decisions/README.md`;
3. `docs/decisions/TEMPLATE.md`;
4. the nearest existing decision for the same projection or guard;
5. the source surface whose rationale the decision records.

## Boundaries

- Give every decision a canonical `Decision ID: AOA-SM-D-####`; the filename
  prefix must match the ID exactly.
- Give every decision an `## Index Metadata` block so lookup indexes can be
  regenerated from source records.
- Keep raw transcripts, session-specific gold, experiment diaries, private
  paths, runtime diagnostics, and operator evidence out of public decision
  records. Preserve those in their stronger evidence surfaces.
- Treat `indexes/` as generated navigation read models, not rationale or
  runtime authority.
- A decision may explain source-to-portable behavior, but generated bundles
  must still be produced through the owner export route.
- Do not copy stronger owner law from MCP, host, eval, or reviewed-memory
  repositories. Name the handoff and authority limit instead.

## Amendment route

Use a dated review entry for a small clarification of the same decision. When
the chosen route is materially replaced, preserve the old record and add a new
decision with explicit supersession metadata and prose.

## Validation

After adding or editing decision metadata, run:

```bash
python3 scripts/generate_decision_indexes.py
python3 scripts/generate_decision_indexes.py --check
git diff --check
```

Also run the owner checks for every source, export, query, projection, or
orchestration surface changed by the decision.

## Closeout

Report the source decision path, affected owner surfaces, regenerated indexes,
portable-export posture, validation performed, and any runtime proof that is
still pending. Do not present a generated index or decision-graph node as the
source decision.
