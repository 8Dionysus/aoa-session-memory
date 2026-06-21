---
name: aoa-session-search
description: Use when an agent needs to build or query the portable `.aoa` SQLite search index for archived Codex sessions, with evidence refs and freshness checks.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-search

Use this when the archive needs fast retrieval across many sessions without
turning search hits into authority.

## Trigger Boundary

- The agent needs to find hook timeouts, naming complaints, raw-unavailable
  incidents, commit/push/merge sessions, technique sessions, sync needs, or
  other cross-session evidence.
- The archive has been reindexed and needs a fresh portable retrieval layer.
- A search result must show session, segment, raw block, raw line, and
  freshness refs before the agent opens heavier material.
- The agent wants to check whether optional host retrieval tools can be used
  without replacing `.aoa` raw/segment authority.
- The agent needs a bounded continuation or investigation packet for a long
  session before opening raw or segment files.

## Procedure

Build or rebuild the runtime search database:

```bash
python3 scripts/aoa_session_memory.py search-index all \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --write-report
```

Query with explanations:

```bash
python3 scripts/aoa_session_memory.py search \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --query "hook timed out" \
  --explain
```

Use local accelerators when semantic recall or reranking helps orientation:

```bash
python3 scripts/aoa_session_memory.py search \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --query "hook timeout route" \
  --include-semantic-context \
  --rerank-local \
  --allow-host-warnings \
  --host-timeout 120 \
  --explain
```

The embedding overlay and reranker are host read-model accelerators. They may
make the first route cheaper, but the returned `.aoa` raw/segment refs remain
the only archive evidence to promote or cite.

Use filters when the route is known:

```bash
python3 scripts/aoa_session_memory.py search \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --query "имена общие" \
  --conversation-act operator_correction \
  --explain
```

When the question is specifically about assistant answers, closeouts, progress
updates, or reasoning windows on a materialized archive, prefer the dedicated
agent-event route with shards:

```bash
python3 scripts/aoa_session_memory.py agent-responses \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --agent-event assistant_answer \
  --use-shards \
  --explain
```

Check optional provider status before using host overlays:

```bash
python3 scripts/aoa_session_memory.py search-provider-status \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --include-host
```

When using `--provider abyss_machine_nervous`, keep the returned `.aoa` hits as
the authoritative route. The host overlay is context only and should be ignored
for promotion unless its claim is reopened through raw/segment refs.

Build a recipe packet when search alone is too thin:

```bash
python3 scripts/aoa_session_memory.py retrieve continue-techniques-session \
  --workspace-root /srv/AbyssOS \
  --aoa-root /srv/AbyssOS/.aoa \
  --query "aoa-techniques continuation" \
  --write-report
```

Use retrieval packets before continuing a long session, investigating hook
failure, reviewing a naming candidate, collecting process lessons, comparing
repeated errors, or preparing manual review.

## Verification

- Search hits include `session_label`, `segment_id` or `event_id`, refs, and a
  `freshness` block.
- `freshness.status` is `fresh` before treating the hit as current routing
  evidence. If it is `stale` or `unverifiable`, re-run `reindex-sessions` or
  inspect the raw archive before using the hit.
- Open the returned raw/segment refs for any claim that will become a decision,
  name, distillation note, or promoted automation.
- If host provider status is `ready_with_warnings`, use `portable_sqlite`
  results as the only reliable `.aoa` route and record the warning as
  capability state rather than failure of archive search.
- Retrieval packets must include `evidence_hits`, `continuation_signals`,
  `phase_discovery`, and `next_routes`; if any of these are empty, treat the
  packet as an orientation gap and refine the query or run lower-layer repair.

## Stop Line

Search is a routing layer. It does not replace raw JSONL, segment indexes, or
reviewed distillation.
