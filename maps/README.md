# Agent Atlas Skeleton

`maps/` is the agent-facing atlas skeleton for `.aoa`.

It is intentionally empty of real session claims at source time. The directory
names and templates define where future generated route entries should land.

## Shape

```text
maps/
  START.md
  README.md
  AGENTS.md
  _templates/
  by-work-context/
  by-repo-family/
  by-memory-surface/
  by-authority-surface/
  by-session-act/
  by-conversation-act/
  by-scope-contract/
  by-verification-state/
  by-open-thread/
  by-entity/
  by-path/
  by-tool/
  by-mcp/
  by-hook-health/
  by-goal/
  by-delivery-state/
  by-failure-mode/
  by-risk/
  by-phase-topic/
  by-external-snapshot/
  by-review-state/
  by-promotion-candidate/
  by-index-health/
  by-time/
  by-operator-request/
  by-route-next-action/
  by-evidence-provenance/
  by-owner-route/
  by-freshness/
  by-runtime-environment/
  by-mutation-surface/
  by-correlation/
  by-confidence/
  by-access-boundary/
  by-resource-profile/
  by-operator-preference/
```

## Expansion Rule

Add a new axis only when it gives agents a faster route to evidence than the
current axes. An axis should answer one concrete question:

- where did this work happen?
- what memory surface was used?
- what authority layer did this event touch?
- what was changed and how was it verified?
- what remains open?
- what should the next agent do first?

Generated atlas entries should be short, uniform, and evidence-routed. They may
summarize the route, but they must point back to session, segment, and raw refs.

## Source And Generated Boundary

Source-owned:

- `AGENTS.md`
- `START.md`
- `README.md`
- `_templates/`
- axis directories and their route purpose
- placeholder `.gitkeep` files

Generated later:

- `by-*/entries/*.md`
- `by-*/entries/*.json`
- per-axis `index.json`
- per-axis `INDEX.md`
- root atlas index files
