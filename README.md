# AoA Session Memory

`.aoa` is the local working root for the portable session-memory bundle.

The first implementation target is Codex session capture:

```text
raw transcript jsonl
  -> compaction-interval Markdown segments
  -> segment indexes
  -> session index
  -> diagnostics
  -> later reviewed distillation
```

The archive layer is intentionally non-distilling. It keeps raw material
available so later passes can extract process lessons, patterns, skill changes,
and automation candidates without losing evidence.

## Local Root

The bundle can run in two shapes:

```text
standalone repository root
workspace/.aoa
```

In another workspace, install the same kernel under that workspace's `.aoa`
root. When checked out as a standalone repository, the repository root is the
AoA root. Local AoA/Tree of Sophia meaning should remain an overlay, not a hard
dependency of the portable kernel.

## Hook Shape

Existing Codex hooks call into this layer on:

- `SessionStart`
- `UserPromptSubmit`
- `PreCompact`
- `PostCompact`
- `Stop`

The hook path is fail-open. If raw session access fails, it writes an incident
and diagnostic record instead of blocking the active Codex session.

## Session Shape

```text
sessions/
  2026-05-12__001__short-title/
    AGENTS.md
    SESSION.md
    session.index.json
    session.manifest.json
    hooks/
      events.jsonl
    raw/
      session.raw.jsonl
      source.json
    segments/
      000__initial-to-latest.md
      000__initial-to-latest.index.json
    incidents/
    distillation/
```

`sessions/<date>__<number>__<short-title>` is the canonical evidence
directory. Codex transcript identity remains inside `session.manifest.json` as
`session_id`. `codex-sessions/` is legacy-only and should be empty after
migration.

Naming rules live in `NAMING.md` and `config/naming-policy.json`.

The operational route lives in `PIPELINE.md`.

Current readiness and unfinished gates live in `READINESS.md`.

## Portable Route

Generate hook config for the current install:

```bash
python3 scripts/aoa_session_memory.py hooks-config \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Run the local e2e gate:

```bash
python3 scripts/aoa_session_memory.py validate \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Inspect native Codex hook trust:

```bash
python3 scripts/aoa_session_memory.py codex-hooks-status \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

Run the live compaction hook probe:

```bash
python3 scripts/aoa_session_memory.py codex-compact-probe \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --trust-hooks
```

Run the completion audit:

```bash
python3 scripts/aoa_session_memory.py audit \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

`audit` is intentionally stricter than `doctor`: it can return non-zero when
the local kernel is healthy but the end-to-end objective still has remaining
gates.

Stress-test a large archive without opening bulk raw material:

```bash
python3 scripts/aoa_session_memory.py stress-pass latest \
  --aoa-root /path/to/workspace/.aoa \
  --compactions 100 \
  --write
```

Export a clean portable bundle without session archives:

```bash
python3 scripts/aoa_session_memory.py export-bundle \
  --target-dir /tmp/aoa-session-memory-bundle \
  --source-aoa-root . \
  --force
```

Install into another workspace:

```bash
python3 scripts/aoa_session_memory.py install \
  --workspace-root /path/to/workspace \
  --source-aoa-root . \
  --force
```

Detailed install rules live in `INSTALL.md`.

## Skill Shape

Portable bundle skills live under `skills/`.

The top-level router is `aoa-session-memory-global-route`. Install it into
`~/.codex/skills` with `install-user-skill` when the current user should have
`.aoa` session-memory guidance in every Codex session. The remaining skills stay
inside the bundle as the narrow routes for archive init, raw archiving,
diagnostics, rehydration, first-pass distillation, stress checks, audit, doctor,
hook trust, and compact probe work.

## Core Rule

```text
Raw JSONL is the evidence source.
Segment Markdown is the readable archive.
Segment index is the event map.
Session index is the atlas.
Distillation is a later reviewed act.
```
