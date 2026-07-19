# Evidence consumer profiles

Use this card only after the main route has classified the question.

| Need | First route | Escalation |
|---|---|---|
| registered source identity | `entity-registry --lookup <anchor> --kind <kind>` | usage route only for behavior |
| entity use and nearby consequence | `usage-chain <anchor> --kind <kind>` | `entity-dossier`, then usage audit/neighborhood |
| hook health | `hook-receipts` | dossier or usage audit |
| goal lifecycle | `goal-lifecycles` | returned task/answer/closeout expansion |
| task to answer | `task-answer-chain` | one returned reasoning, answer, or closeout lane |
| agent answer or closeout | `agent-responses` or `agent-closeouts` | bounded answer neighborhood |
| exact literal, path, command, error, or id | `literal-query-plan` | its structured route, scoped FTS, then bounded raw |
| two-entity relation | `graph-bridge` | bounded graph neighborhood or shortest path |
| one dense entity neighborhood | `graph-cooccurrence` | bounded graph neighborhood |
| route-quality regression | `live-scenario-corpus check` | one case-specific audit |

## Skill evidence

`state_counts` is one canonical state per archived event.
`association_state_counts` may retain weaker projections of the same event;
do not add the two as independent evidence.

Use these claim classes:

| State | Allowed claim |
|---|---|
| `prompt_visible` | the exact skill entry was visible in bounded initial context |
| `selected` | the agent or structured route selected the named skill |
| `skill_read` | the named `SKILL.md` body was opened |
| `procedure_observed` | a reviewed receipt links named procedure checkpoints to the task episode |
| `verified` | a named verifier accepted declared postconditions |
| `completed` | procedure, verification, and terminal consequence are jointly receipted |
| `deflected` | selection or invocation was explicitly declined |
| `edited`, `mentioned`, `cooccurrence` | artifact or contextual association only |

A structured `loaded` action means the runtime embedded the skill payload. It
does not prove that the model followed it. Bare task ids are session-local
join keys. Open the reviewed episode or receipt before an invocation claim.

Validate, preview, and explicitly admit an owner-reviewed receipt with:

```bash
python3 scripts/aoa_session_memory.py skill-usage-receipt validate RECEIPT.json
python3 scripts/aoa_session_memory.py skill-usage-receipt record RECEIPT.json
```

The `record` command shown here is a non-mutating plan. This read-only evidence
skill must stop there. The owner CLI exposes a separate explicit apply action
for an authorized reviewer; it writes one immutable receipt below the logical
session-memory diagnostics root. Reusing the same receipt id with different
content fails closed. `list --skill <name>` returns only admission summaries
and claim ceilings, not a benefit verdict.

An admitted receipt must bind source, installed, prompt-visible, selected, and
executed versions; package and installed fingerprints; one task episode;
observed procedure sections; tools; checkpoints; a verifier; consequences;
review; and alternative explanations. `identity_status=drift` remains useful
diagnostic evidence but cannot prove invocation. Even a verified current
receipt exposes only an effect-attribution candidate until `aoa-evals`
resolves a controlled comparison.

If `quality.skill_text_fallback_deferred=true`, the bounded dispatch passes
found no candidate and deliberately avoided broad FTS. This is not proof of
absence. Follow the returned literal/raw expansion only when exact recall
matters.

Foreign correlated results must stay under rejection/context edges with both
source and rejected correlation ids.

## Literal and operational routes

Read `literal_route_strategy`, `cost_profile`, `fallback_plan`, and
`next_expansion_command` before opening raw. A concrete registered entity wins
over broad class vocabulary. For exact session ids, prefer the rehydrate or
session route.

`search-operational-route-rollup-query` and
`search-operational-direct-event-rollup-query` are compact navigation read
models. They do not rebuild maintenance, use FTS, hydrate raw bodies, or prove
behavior. Follow typed-lane or dedicated-route advice before fuzzy results.

## Packet reading

Prefer packets that preserve:

- normalized entity and route candidates;
- candidate, result, consequence, and rejection counts;
- freshness, ambiguity, truncation, and omitted counts;
- query cost and fallback position;
- raw, raw-block, segment, segment-index, session, and owner refs;
- exact next expansion.

Open raw only to verify a material claim, exact error, or bounded temporal
interval. An ordered endpoint pair is navigation until interval contents are
read through the source-aware bounded route.
