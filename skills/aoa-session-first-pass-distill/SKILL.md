---
name: aoa-session-first-pass-distill
description: Use when an indexed `.aoa` session needs provisional first-pass distillation into lessons, decisions, failures, and automation candidates without promoting them to reviewed truth.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-first-pass-distill

Use when an archived `.aoa` session needs a provisional event-to-experience
route map without promoting raw material into reviewed truth.

## Trigger Boundary

- A session archive is already indexed.
- The user asks what lessons, failures, decisions, or automation candidates can
  be extracted.
- A later agent needs a route map before doing reviewed distillation.

## Inputs

- `.aoa` root
- session label, session id, title fragment, or `latest`
- optional maximum candidate events per type

## Procedure

1. Read root `AGENTS.md`, `DESIGN.md`, `DESIGN.AGENTS.md`, and `PIPELINE.md`.
2. Resolve the target session through `session-registry.json`.
3. Read `session.manifest.json` and each segment index. Reject stale or
   incompatible session/segment generations before selecting candidates.
4. Count event types and distillation routes.
5. Select high-value candidate events by type, importance, and route.
6. Run `distill-first-pass`; it rebuilds the session projection and publishes
   the manifest, session/segment indexes, candidate index, and rendered map as
   one recoverable generation.
7. Read `distillation/distillation.index.json` and require a compatible
   `generation_identity`, matching `source_fingerprint`,
   `freshness.status=current`, and `evidence_integrity.status=current`.
8. Open the cited raw and segment refs before interpreting a candidate.

## Verification

- Distillation files exist under the target session `distillation/`.
- `first_pass_distillation_state` is `current`; stale candidate maps must be
  rebuilt, not treated as historical proof.
- Candidate entries cite `md_anchor` and `raw_ref`.
- Session manifest, session index, and registry reflect first-pass status.
- A failed publish preserves the prior complete projection and leaves no
  partially visible candidate map.
- No skill, pattern, or automation is promoted without review.

## Stop Line

First-pass distillation is a versioned map for review, not a verdict. A map
with stale generation, unresolved refs, or missing freshness is navigation
only and cannot support promotion.
