# Agent Atlas Start

Use this atlas when you need to find session-memory evidence quickly.

## First Route

1. Choose the axis that matches your question.
2. Open the axis directory.
3. Prefer generated entries and indexes before heavy session Markdown.
4. Follow evidence refs into `sessions/<label>/SESSION.md`,
   `session.index.json`, segment indexes, and raw refs.
5. Treat atlas entries as route signals, not reviewed truth.

## Axis Questions

| Question | Route |
| --- | --- |
| Which repo or workspace was active? | `by-work-context/` |
| Which AoA/ToS/Abyss family does it belong to? | `by-repo-family/` |
| Which memory layer was touched? | `by-memory-surface/` |
| Was this source, generated, runtime, diagnostics, or external? | `by-authority-surface/` |
| What kind of session activity happened? | `by-session-act/` |
| What conversational move happened? | `by-conversation-act/` |
| What user scope or delivery contract was active? | `by-scope-contract/` |
| What was verified or left unverified? | `by-verification-state/` |
| What remains open? | `by-open-thread/` |
| Which named object, file, tool, hook, MCP resource, or goal matters? | `by-entity/`, `by-path/`, `by-tool/`, `by-mcp/`, `by-hook-health/`, `by-goal/` |
| Was work landed, pushed, merged, exported, or only local? | `by-delivery-state/` |
| What failed? | `by-failure-mode/` |
| What carries risk? | `by-risk/` |
| Which phase or topic did this belong to? | `by-phase-topic/` |
| Which outside snapshot was used? | `by-external-snapshot/` |
| Is review or promotion still pending? | `by-review-state/`, `by-promotion-candidate/` |
| How healthy is the index? | `by-index-health/` |
| When did it happen? | `by-time/` |
| What did the operator ask for? | `by-operator-request/` |
| What should the next agent do? | `by-route-next-action/` |
| Why can the agent believe or doubt this route? | `by-evidence-provenance/`, `by-confidence/` |
| Who owns the surface and what is fresh or stale? | `by-owner-route/`, `by-freshness/` |
| What runtime, mutation, access, or cost boundary matters? | `by-runtime-environment/`, `by-mutation-surface/`, `by-access-boundary/`, `by-resource-profile/` |
| Which events are linked together? | `by-correlation/` |
| Which standing operator preference applies? | `by-operator-preference/` |
