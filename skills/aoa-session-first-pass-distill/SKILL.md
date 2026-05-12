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

1. Read root `AGENTS.md`, `DESIGN.md`, and `PIPELINE.md`.
2. Resolve the target session through `session-registry.json`.
3. Read `session.manifest.json` and each segment index.
4. Count event types and distillation routes.
5. Select high-value candidate events by type, importance, and route.
6. Write `distillation/distillation.index.json`.
7. Write `distillation/001__first-pass__experience-map.md`.
8. Mark the manifest as `distillation_status=first_pass_distilled` with
   `review_status=provisional`.

## Verification

- Distillation files exist under the target session `distillation/`.
- Candidate entries cite `md_anchor` and `raw_ref`.
- Session manifest, session index, and registry reflect first-pass status.
- No skill, pattern, or automation is promoted without review.

## Stop Line

First-pass distillation is a map for review, not a verdict.

