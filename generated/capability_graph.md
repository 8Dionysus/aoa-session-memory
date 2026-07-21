# Capability graph

Derived from `capabilities/families/*.yaml`. This file is a read model, not capability authority.

Source content hash: `b65694714f8e40a82e0f0829efc460349efcdd54cdaf6f4c7d12ffa011090704`

## Semantic tree

- `aoa-session-memory` (capability, internal, healthy)
  - `session-memory.adapters` (capability, internal, healthy)
    - `session-memory.adapters.codex` (adapter, internal, healthy)
      - `skill.aoa-codex-compact-probe` (skill, deferred, challenger)
      - `skill.aoa-codex-hooks-status` (skill, deferred, challenger)
      - `skill.aoa-codex-session-segment-archive` (skill, deferred, challenger)
  - `session-memory.stewardship` (capability, internal, healthy)
    - `session-memory.stewardship.assure` (capability, internal, healthy)
      - `skill.aoa-session-memory-audit` (skill, deferred, challenger)
      - `skill.aoa-session-memory-doctor` (skill, deferred, challenger)
      - `skill.aoa-session-memory-stress-pass` (skill, deferred, challenger)
    - `session-memory.stewardship.capture` (capability, internal, healthy)
      - `skill.aoa-session-archive-init` (skill, deferred, challenger)
      - `skill.aoa-session-history-import` (skill, deferred, challenger)
      - `skill.aoa-session-raw-diagnostic` (skill, deferred, challenger)
    - `session-memory.stewardship.curate` (capability, internal, healthy)
      - `skill.aoa-session-batch-distill` (skill, deferred, challenger)
      - `skill.aoa-session-first-pass-distill` (skill, deferred, challenger)
      - `skill.aoa-session-manual-review` (skill, deferred, challenger)
    - `session-memory.stewardship.name` (capability, internal, healthy)
      - `skill.aoa-session-naming-readiness` (skill, deferred, challenger)
      - `skill.aoa-session-naming-wave` (skill, deferred, challenger)
      - `skill.aoa-session-phase-discovery` (skill, deferred, challenger)
    - `session-memory.stewardship.project` (capability, internal, healthy)
      - `skill.aoa-session-reindex` (skill, deferred, challenger)
  - `session-memory.use` (capability, internal, healthy)
    - `session-memory.use.query` (capability, internal, healthy)
      - `skill.aoa-session-memory-evidence-route` (skill, advertised, challenger)
      - `skill.aoa-session-rehydrate` (skill, deferred, challenger)
      - `skill.aoa-session-search` (skill, deferred, challenger)
    - `session-memory.use.route` (capability, internal, healthy)
      - `skill.aoa-session-memory-global-route` (skill, advertised, challenger)

## Typed relations

| kind | source | target | condition |
|---|---|---|---|
| conflicts-with | `skill.aoa-session-naming-wave` | `skill.aoa-session-reindex` | Do not mutate names and rebuild projections for the same session set concurrently. |
| conflicts-with | `skill.aoa-session-reindex` | `skill.aoa-session-naming-wave` | Do not rebuild projections and mutate names for the same session set concurrently. |
| generalizes | `skill.aoa-session-first-pass-distill` | `skill.aoa-session-batch-distill` | Single-session extraction is the reusable procedure generalized by bounded batch orchestration. |
| hands-off-to | `skill.aoa-codex-hooks-status` | `skill.aoa-codex-compact-probe` | Current trusted hook runtime status is required before the behavioral compact probe. |
| hands-off-to | `skill.aoa-codex-session-segment-archive` | `skill.aoa-session-reindex` | Newly archived sessions may be projected only after raw preservation validates. |
| hands-off-to | `skill.aoa-session-archive-init` | `skill.aoa-codex-hooks-status` | The initialized root emits the memory-root binding consumed by Codex hook inspection. |
| hands-off-to | `skill.aoa-session-batch-distill` | `skill.aoa-session-manual-review` | The batch candidate queue remains provisional and enters bounded manual review. |
| hands-off-to | `skill.aoa-session-first-pass-distill` | `skill.aoa-session-manual-review` | Provisional candidates require owner-aware manual disposition before any promotion. |
| hands-off-to | `skill.aoa-session-history-import` | `skill.aoa-session-reindex` | The bounded import set is complete and raw-preserving before projection rebuild. |
| hands-off-to | `skill.aoa-session-naming-readiness` | `skill.aoa-session-phase-discovery` | A readiness record explicitly classifies the session as requiring phase discovery. |
| hands-off-to | `skill.aoa-session-naming-wave` | `skill.aoa-session-memory-audit` | Applied naming receipts require quality and readiness audit. |
| hands-off-to | `skill.aoa-session-phase-discovery` | `skill.aoa-session-naming-wave` | Phase candidates were reviewed and provide the naming-wave input ABI. |
| hands-off-to | `skill.aoa-session-search` | `skill.aoa-session-memory-evidence-route` | A bounded search packet answers the historical entity question and preserves source refs. |
| primary-parent | `session-memory.adapters` | `aoa-session-memory` | - |
| primary-parent | `session-memory.adapters.codex` | `session-memory.adapters` | - |
| primary-parent | `session-memory.stewardship` | `aoa-session-memory` | - |
| primary-parent | `session-memory.stewardship.assure` | `session-memory.stewardship` | - |
| primary-parent | `session-memory.stewardship.capture` | `session-memory.stewardship` | - |
| primary-parent | `session-memory.stewardship.curate` | `session-memory.stewardship` | - |
| primary-parent | `session-memory.stewardship.name` | `session-memory.stewardship` | - |
| primary-parent | `session-memory.stewardship.project` | `session-memory.stewardship` | - |
| primary-parent | `session-memory.use` | `aoa-session-memory` | - |
| primary-parent | `session-memory.use.query` | `session-memory.use` | - |
| primary-parent | `session-memory.use.route` | `session-memory.use` | - |
| primary-parent | `skill.aoa-codex-compact-probe` | `session-memory.adapters.codex` | - |
| primary-parent | `skill.aoa-codex-hooks-status` | `session-memory.adapters.codex` | - |
| primary-parent | `skill.aoa-codex-session-segment-archive` | `session-memory.adapters.codex` | - |
| primary-parent | `skill.aoa-session-archive-init` | `session-memory.stewardship.capture` | - |
| primary-parent | `skill.aoa-session-batch-distill` | `session-memory.stewardship.curate` | - |
| primary-parent | `skill.aoa-session-first-pass-distill` | `session-memory.stewardship.curate` | - |
| primary-parent | `skill.aoa-session-history-import` | `session-memory.stewardship.capture` | - |
| primary-parent | `skill.aoa-session-manual-review` | `session-memory.stewardship.curate` | - |
| primary-parent | `skill.aoa-session-memory-audit` | `session-memory.stewardship.assure` | - |
| primary-parent | `skill.aoa-session-memory-doctor` | `session-memory.stewardship.assure` | - |
| primary-parent | `skill.aoa-session-memory-evidence-route` | `session-memory.use.query` | - |
| primary-parent | `skill.aoa-session-memory-global-route` | `session-memory.use.route` | - |
| primary-parent | `skill.aoa-session-memory-stress-pass` | `session-memory.stewardship.assure` | - |
| primary-parent | `skill.aoa-session-naming-readiness` | `session-memory.stewardship.name` | - |
| primary-parent | `skill.aoa-session-naming-wave` | `session-memory.stewardship.name` | - |
| primary-parent | `skill.aoa-session-phase-discovery` | `session-memory.stewardship.name` | - |
| primary-parent | `skill.aoa-session-raw-diagnostic` | `session-memory.stewardship.capture` | - |
| primary-parent | `skill.aoa-session-rehydrate` | `session-memory.use.query` | - |
| primary-parent | `skill.aoa-session-reindex` | `session-memory.stewardship.project` | - |
| primary-parent | `skill.aoa-session-search` | `session-memory.use.query` | - |
| produces | `skill.aoa-session-reindex` | `skill.aoa-session-search` | Current indexed-session output supplies the optional search projection input. |
| specializes | `skill.aoa-session-batch-distill` | `skill.aoa-session-first-pass-distill` | Batch distillation repeats the same provisional extraction across a bounded reviewed set with completeness receipts. |
| verified-by | `skill.aoa-session-archive-init` | `skill.aoa-session-memory-doctor` | Root initialization completes only after doctor validates the selected root. |
| verified-by | `skill.aoa-session-history-import` | `skill.aoa-session-memory-doctor` | Imported archives complete only after registry and root health checks. |
| verified-by | `skill.aoa-session-naming-wave` | `skill.aoa-session-memory-audit` | Naming mutation completes only after receipt and quality audit. |
| verified-by | `skill.aoa-session-reindex` | `skill.aoa-session-memory-doctor` | Projection rebuild completes only after current provider and root health checks. |
| verifies | `skill.aoa-session-memory-audit` | `skill.aoa-session-naming-wave` | Audit verifies naming receipts without authoring names. |
| verifies | `skill.aoa-session-memory-doctor` | `skill.aoa-session-archive-init` | Doctor verifies initialization postconditions without acquiring install authority. |
| verifies | `skill.aoa-session-memory-doctor` | `skill.aoa-session-history-import` | Doctor verifies import postconditions without rewriting archives. |
| verifies | `skill.aoa-session-memory-doctor` | `skill.aoa-session-reindex` | Doctor verifies rebuilt projections without becoming projection authority. |
