---
name: aoa-session-search
description: Use when an agent needs to build or query the portable `.aoa` SQLite search index for archived Codex sessions, with evidence refs and freshness checks.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-search

## Trigger Boundary

Use this skill for a bounded cross-session archive query or an explicitly
requested portable search-projection refresh. Do not use it when current owner
source, a typed entity route, or live runtime state already answers the
question.

Search results are navigation. Raw, segment, session, receipt, and owner refs
remain the evidence handoff.

## Procedure

1. Resolve logical `<workspace-root>` and `<aoa-root>`.
2. Inspect provider status and freshness before choosing query or maintenance.
3. Prefer the smallest typed query and bounded filters:

```bash
python3 scripts/aoa_session_memory.py search \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --query "<bounded-query>" \
  --explain
```

4. Use dedicated agent-event, entity, goal, or task routes when their typed
   contract fits better than general search. Keep literal raw-text timeout
   bounded; an explicit offline scan is a separate operator choice.
5. Open returned raw or segment refs before using a hit for a decision, name,
   distillation, automation candidate, or other owner mutation.
6. Rebuild or repair a projection only after explicit intent and a preview or
   gate packet. Query and maintenance share this package, but maintenance is a
   typed internal mode, not an automatic consequence of a stale hit.

Use exactly one shallow reference when needed:

- [query-modes.md](references/query-modes.md) for filters, shards, host
  overlays, dedicated response routes, and retrieval packets;
- [maintenance.md](references/maintenance.md) for index builds, dirty
  catch-up, entity sync, shrink gates, guarded apply, and recovery.

## Verification

- Every hit names `session_label`, an event or segment identity, resolvable
  evidence refs, and freshness.
- Treat only `fresh` hits as current routing evidence. Reindex or inspect raw
  when stale or unverifiable.
- Record provider warnings without replacing portable SQLite authority.
- A mutating mode reports preview/gates, exact scope, changed derived
  artifacts, postcondition status, and recovery route.
- Raw archives and segment evidence remain unchanged by search maintenance.

## Stop Line

Stop after a bounded result set, honest miss, or one exact stale-provider
recovery route. Do not widen from a successful typed route into broad FTS, run
maintenance implicitly, claim storage improvement without before/after
evidence, or treat a search hit as reviewed truth.
