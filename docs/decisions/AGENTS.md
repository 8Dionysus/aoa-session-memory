# AGENTS.md

## Role

Decision records preserve why durable archive, projection, query-route,
freshness, orchestration, portability, evidence-boundary, or storage choices
were made in `aoa-session-memory`.

They do not make current behavior by themselves. Current behavior remains in
the owning source, schema, configuration, route, and pipeline surfaces.

## Task routes

The root card is inherited; do not reread it.

- Author or supersede: `TEMPLATE.md`, nearest accepted decision, owning source.
- Repair indexes: source record and `scripts/generate_decision_indexes.py`.
- Human orientation: `README.md`, then source; indexes are navigation.

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
