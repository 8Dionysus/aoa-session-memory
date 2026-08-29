---
name: aoa-session-memory-evidence-route
description: Use when an agent needs evidence from prior `.aoa` sessions about how a skill, MCP, hook, tool, API, goal, eval, test, validator, script, decision, error, receipt, or other recurring operational entity was used, what happened nearby, and which raw or segment refs prove it.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: evidence-router
---

# aoa-session-memory-evidence-route

## Trigger Boundary

Use this skill for a historical behavior question whose answer must come from
prior session evidence. Do not use it to replace current repository source,
live runtime state, decision authority, eval verdicts, or durable promotion.

The route finds and qualifies evidence. It never upgrades mention, prompt
visibility, selection, loading, or a `SKILL.md` read into invocation or
effectiveness.

## Procedure

1. Resolve the logical `<aoa-root>` and the entity kind. Start with the
   smallest typed route:

   - source identity or “does it exist”: `entity-registry --lookup`;
   - behavior and nearby consequence: `usage-chain <anchor> --kind <kind>`;
   - goal lifecycle: `goal-lifecycles`;
   - task-to-answer chain: `task-answer-chain`;
   - exact text, command, path, error, or session id: `literal-query-plan`;
   - relation between two entities: `graph-bridge`;
   - current route quality: `live-scenario-corpus check`.

2. Prefer the read-only session-memory MCP equivalent when it is actually
   available. If transport or registry freshness blocks it, name the CLI
   fallback and run the same typed route from `<aoa-root>`. A missing MCP tool
   is a transport/runtime issue, not permission for unbounded raw search.

3. Read applicability before score. Inspect freshness, ambiguity, truncation,
   omitted counts, cost profile, and the exact next expansion before opening
   another layer.

4. For a skill anchor, read `skill_evidence` explicitly:

   - `prompt_visible`, `selected`, `skill_read`, `edited`, `mentioned`,
     `cooccurrence`, and `deflected` are candidate states only;
   - `procedure_observed`, `verified`, and `completed` require an owner receipt
     or reviewed task episode;
   - `task_episode_refs` are join keys, not proof;
   - `invocation_claim_allowed=false` is a hard claim boundary;
   - foreign-correlation results remain auditable context, never consequence.

5. For a comparative skill audit about successful, failed, or
   procedure-deviating applications:

   - start from `usage-chain <skill> --kind skill --full` and keep its
     `task_episode_refs` only as bounded join candidates;
   - for each selected candidate, run `task-answer-chain --session <session>
     --task-episode-id <episode> --allow-missing-reasoning
     --allow-missing-answer` before attributing a result to the skill; the
     explicit flags preserve failed, interrupted, and receipt-bearing episodes
     that have no ordinary final answer;
   - route exact reviewed receipt, error, status, or failure-class anchors
     through `literal-query-plan` with the same session and episode scope, then
     open the proposed bounded evidence window;
   - call an application successful only when reviewed result or verification
     evidence belongs to the same procedure and correlation chain;
   - treat missing positive proof as `unresolved`, not as a failed application,
     and never turn a bounded set of failures into an archive-wide absence
     claim.

6. Expand only the missing evidence class. Use raw or segment refs to verify an
   important claim, exact error, or bounded interval. Keep private bodies,
   hidden reasoning, and unrelated context outside the packet.

7. Return the evidence packet to the source owner, decision owner,
   `aoa-evals`, or another named authority. Do not write that owner from
   session evidence alone.

For a specialized route, open exactly one shallow reference:

- [consumer-profiles.md](references/consumer-profiles.md) for typed query
  selection and packet interpretation;
- [maintenance-and-graph.md](references/maintenance-and-graph.md) for search
  pressure, graph pressure, rollups, and shrink/prune stop-lines;
- [mcp-fallback.md](references/mcp-fallback.md) for exact MCP tools,
  preflight, and equivalent CLI commands.

## Authority Boundary

Session-memory packets are generated navigation and evidence surfaces. They
are weaker than current owner source, repository decisions, canonical skills,
central eval verdicts, and reviewed promotion surfaces. Route counts and
semantic proximity do not establish correctness, causality, invocation, or
benefit.

## Verification

- Name the first route and why it matched the question.
- Name MCP or explicit CLI fallback.
- Report freshness, ambiguity, truncation, and privacy posture.
- Cite at least one resolvable raw, segment, session, receipt, or owner ref for
  each important historical claim.
- For skill behavior, name exact package version/fingerprint when a reviewed
  receipt provides it and list alternative explanations that remain.
- For candidate-semantics regression, run the reviewed
  `skill_candidate_semantics_contract` corpus case and label its synthetic
  evidence origin.

## Stop Line

Stop when the bounded packet answers the question with resolvable refs, or
when it exposes one exact next expansion and the claim remains honestly
unresolved. Never compensate for a stale provider, closed transport,
unavailable receipt, or missing authority by widening into an unbounded
transcript scan.
