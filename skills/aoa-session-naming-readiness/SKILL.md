---
name: aoa-session-naming-readiness
description: Use before broad session renaming or semantic naming work to classify `.aoa` session archives by naming readiness, lower-layer blockers, and phase-discovery needs.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-naming-readiness

Use this before applying session names, semantic aliases, or physical relabels.

Naming is a pressure test of lower layers. Do not start by naming everything.
Start by asking which sessions are ready, which need phase/topic discovery, and
which must be repaired at raw/index level first.

## Trigger Boundary

- The user asks to rename sessions or improve session names.
- `SESSION_NAMES.md` or `sessions/INDEX.md` feels too weak to navigate.
- A long session needs a future continuation route.
- A session has a custom semantic name proposal but no raw evidence anchor yet.
- The agent needs a queue before running `name-session`.

## Procedure

Refresh the generated readiness maps:

```bash
python3 scripts/aoa_session_memory.py naming-readiness all \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --refresh-indexes \
  --write-report
```

For a bounded window:

```bash
python3 scripts/aoa_session_memory.py naming-readiness all \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --since-days 21 \
  --refresh-indexes \
  --write-report
```

For one target:

```bash
python3 scripts/aoa_session_memory.py naming-readiness <session-label-or-id> \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --write-report
```

## Reading The Result

- `blocked`: repair missing or unrecoverable raw/index state before naming.
- `diagnostic_only`: leave the raw-unavailable diagnostic visible unless a
  transcript candidate appears.
- `needs_reindex`: refresh generated segments/indexes from preserved raw before
  choosing a semantic name.
- `needs_phase_discovery`: inspect segments and create phase/topic candidates
  before assigning a whole-session name.
- `phase_discovery_ready`: review the generated phase/topic candidate artifact
  before applying a whole-session name.
- `ready_for_semantic_name`: apply a semantic session name with raw evidence
  refs, not a blind folder rename.
- `readable_label`: keep the canonical label unless review finds a better
  semantic name.
- `low_signal`: likely probe or tiny session; leave it unless it matters.
- `named`: verify or refine the existing semantic name.

## Verification

- Every scoped session has one readiness class, evidence refs, and an exact
  next route.
- Index/title freshness and owner-resolution blockers remain visible.
- The readiness pass changes no semantic session name.

## Stop Line

Do not use readiness as reviewed truth. It is a routing index for the next
pass. Every applied semantic name still needs raw refs and bridge anchors.

## Phase Discovery

For a session routed to `phase_topic_discovery_before_session_name`, generate
open candidates first:

```bash
python3 scripts/aoa_session_memory.py phase-discovery <session-label-or-id> \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --write \
  --write-report
```

This writes `naming/phase-discovery.json` and `.md` inside the session. Treat
those files as review input, not applied names.
