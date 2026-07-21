# Skill Usage Evidence Demonstration

This runbook prepares a separate session to demonstrate how
`aoa-session-memory` finds and qualifies evidence of skill use. It does not
turn retrieval proximity into proof and it does not authorize mutation of a
session archive, owner repository, receipt store, or eval verdict.

## 1. Pre-register the evidence target

Before using the retriever, independently choose one permitted archived
session and one skill whose source evidence can be opened. Record outside the
test output:

- the session id and approximate date or interval;
- expected raw, segment, event, or owner refs;
- the minimum expected state, such as `prompt_visible`, `selected`,
  `skill_read`, or `procedure_observed`;
- forbidden claims, especially unsupported invocation, consequence, benefit,
  causality, and current-source claims;
- query budgets and any expected alias or collision.

Do not select the target from the ranked output being evaluated. Keep private
session text and machine paths outside public artifacts.

## 2. Check projection state

From the installed `.aoa` root, inspect both projection and maintenance
status before asking a historical question:

```bash
python3 scripts/aoa_session_memory.py projection-status \
  --workspace-root WORKSPACE --aoa-root AOA_ROOT
python3 scripts/aoa_session_memory.py maintenance-status \
  --workspace-root WORKSPACE --aoa-root AOA_ROOT --full
```

Record the reported generation identities, source watermark, global and
scoped freshness, omissions, and fallback state. A completed worker or a
successful timer is not semantic freshness.

## 3. Start exact and session-bounded

Plan an independently known literal, skill name, command, or session id. Add
date bounds when they are part of the pre-registered target:

```bash
python3 scripts/aoa_session_memory.py literal-query-plan "KNOWN_LITERAL" \
  --session SESSION_ID --date-from YYYY-MM-DD --date-to YYYY-MM-DD \
  --workspace-root WORKSPACE --aoa-root AOA_ROOT

python3 scripts/aoa_session_memory.py usage-chain SKILL_NAME --kind skill \
  --session SESSION_ID \
  --workspace-root WORKSPACE --aoa-root AOA_ROOT --full
```

Read route selection, freshness, ambiguity, truncation, rejected
correlations, candidate ids, and the exact next expansion before widening the
search. Open returned raw, segment, session, receipt, or owner refs for every
important claim. A packet without a resolvable evidence ref is navigation,
not proof.

Use an episode or a graph route only when the exact packet leaves a specific
question open. Graph traversal must begin from typed anchors and remain within
the reported node, edge, depth, evidence, time, and context budgets.

## 4. Evaluate the evidence ladder

Keep these states separate:

1. `prompt_visible` or `mentioned`;
2. `selected`;
3. `skill_read`;
4. `procedure_observed`;
5. `invoked` or `completed`;
6. `verified`;
7. `consequence-producing`;
8. benefit or promotion.

A skill read alone does not prove invocation. Invocation, verification, and a
consequence require evidence for that state and sufficient correlation. A
foreign correlation id remains rejected context. Benefit and promotion stay
with the eval or promotion owner, never the retriever.

`identity_status=drift` may prove invocation of an explicitly matched
historical selected/executed version. It must still report
`source_current=false` and `promotion_identity_eligible=false`; it cannot
prove use of the current source.

## 5. Compare access planes

When the read-only session-memory MCP is configured, run the equivalent typed
route with the same anchor, session, and budgets. Compare CLI and MCP evidence
packets for candidate ids, refs, freshness, truncation, rejected
correlations, and next actions. MCP is an access plane, not mutation or proof
authority. If MCP transport is unavailable, name the failure and use the
equivalent CLI route without widening scope.

## 6. Optional reviewed receipt

Only an independently approved reviewer may prepare a skill-use receipt.
Validate and preview it first:

```bash
python3 scripts/aoa_session_memory.py skill-usage-receipt validate RECEIPT.json
python3 scripts/aoa_session_memory.py skill-usage-receipt record RECEIPT.json
```

The second command is still non-mutating. Use `record --apply` only when the
owner explicitly authorizes admission. An admitted receipt has a claim
ceiling; it never establishes benefit by itself.

## 7. Manual randomized scenarios

Seal expected refs and forbidden claims before each run, then vary order and
seed while retaining the same budgets:

- an exact known skill and session;
- a paraphrase and mixed code/text query;
- the same evidence through a date-bounded route;
- an alias collision or ambiguous skill name;
- a skill that was only prompt-visible or read;
- a result with a foreign correlation identity;
- a stale or incompatible projection/provider;
- exact retrieval with and without bounded graph expansion;
- a negative or insufficient-evidence question;
- a superseded historical skill version where current-source claims must be
  withheld.

For important hits, open the sealed raw/segment refs and record false
positives, omissions, unsupported states, abstentions, latency, and expansion
cost. Repeat the same cases after cleanup, migration, or reindexing.

## Completion checklist

The demonstration is complete only when:

- expected refs resolve and forbidden claims remain blocked;
- exact recall is not displaced by semantic or graph ranking;
- source, installed, selected, and executed identities are distinguished;
- global and scoped freshness, truncation, fallback, and omissions are
  visible;
- invocation, correlation, consequence, and benefit boundaries remain
  separate;
- CLI and configured MCP return contract-equivalent evidence packets;
- unresolved evidence returns abstention plus one bounded next route;
- no private session body, secret, host path, or runtime database enters the
  portable/public result.

The durable ownership and receipt lifecycle are recorded in
`AOA-SM-D-0018`. This runbook is a consumer procedure, not a second decision
or evidence authority.
