# AGENTS.md

## Applies To

This card applies to `aoa-session-memory/kag/` and every nested path until a
nearer card narrows the lane.

## Role

`kag/` is the local KAG provider home for the portable session-memory kernel.
It exposes compact, source-linked records over archive routes, session
manifests, atlas maps, and validation receipts for `aoa-kag` registry,
composition, and MCP consumers.

## Read Before Editing

Read the root `AGENTS.md`, this card, `kag/README.md`, `kag/manifest.json`,
`README.md`, `PIPELINE.md`, `READINESS.md`, and
`schemas/session.manifest.schema.json` before changing provider records.

## Owner Split

Archive meaning belongs to `aoa-session-memory` source surfaces. Shared KAG
schema, registry, composition, and provider validation belong to `aoa-kag`.
Runtime serving state belongs to `.aoa`, `abyss-stack`, or the runtime owner
named by the consumer.

## Validation

Use the owner validator named in `manifest.json`, then validate this provider
through the `aoa-kag` local subtree validator.

## Closeout

Report provider records changed, source-return route changed, owner validation,
`aoa-kag` validation, and the next MCP consumer route.
