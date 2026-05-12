# AoA Session Memory Install

## Role

`INSTALL.md` is the operator route for moving the portable `.aoa` session-memory
kernel into another workspace or preparing a clean bundle for a future
repository.

Read `DESIGN.md` and `PIPELINE.md` first. This file is about installation, not
memory doctrine.

## Clean Bundle Export

Export only the portable kernel, without current session archives:

```bash
python3 scripts/aoa_session_memory.py export-bundle \
  --target-dir /tmp/aoa-session-memory-bundle \
  --source-aoa-root . \
  --force
```

This writes an empty `sessions/` directory and an empty
`session-registry.json`. It does not copy raw transcripts unless
`--with-sessions` is explicitly used.

Use this path when preparing a standalone GitHub repository.
When the target is already a Git repository, `--force` refreshes the portable
bundle files but preserves `.git`.

## Workspace Install

Install the bundle into another workspace:

```bash
python3 scripts/aoa_session_memory.py install \
  --workspace-root /path/to/workspace \
  --source-aoa-root . \
  --force
```

The target root defaults to `/path/to/workspace/.aoa`.

The installer regenerates `hooks/codex-hooks.user.example.json` for the selected
workspace and `.aoa` root. Do not copy hook JSON by hand between machines.

To install user-level Codex hooks at the same time:

```bash
python3 scripts/aoa_session_memory.py install \
  --workspace-root /path/to/workspace \
  --source-aoa-root . \
  --write-user-hooks ~/.codex/hooks.json \
  --force
```

Existing user hooks are backed up unless `--no-hooks-backup` is set.

## User-Level Skill Entrypoint

To make `.aoa` session-memory guidance available in every Codex session for
the current user, expose the global router skill from the selected install
root:

```bash
mkdir -p ~/.codex/skills
ln -sfn /path/to/workspace/.aoa/skills/aoa-session-memory-global-route \
  ~/.codex/skills/aoa-session-memory-global-route
```

The user-level skill is only a router. It should point agents back to the
installed bundle instead of duplicating bundle logic. Keep the narrow operating
skills inside the bundle.

## Verification

After install, run the target script from the target root:

```bash
python3 /path/to/workspace/.aoa/scripts/aoa_session_memory.py validate \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa

python3 /path/to/workspace/.aoa/scripts/aoa_session_memory.py codex-grounding \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa

python3 /path/to/workspace/.aoa/scripts/aoa_session_memory.py doctor \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

If user-level hooks were installed, add `--check-live-hooks` to `doctor`.

Then verify the native Codex hook trust state:

```bash
python3 /path/to/workspace/.aoa/scripts/aoa_session_memory.py codex-hooks-status \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa
```

If matching hooks are present but untrusted, trust the current hashes through
Codex app-server:

```bash
python3 /path/to/workspace/.aoa/scripts/aoa_session_memory.py codex-hooks-status \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --trust-current
```

To prove the compaction hook path on a live Codex install:

```bash
python3 /path/to/workspace/.aoa/scripts/aoa_session_memory.py codex-compact-probe \
  --workspace-root /path/to/workspace \
  --aoa-root /path/to/workspace/.aoa \
  --trust-hooks
```

This uses Codex app-server `thread/compact/start`, records a small persisted
probe thread, and requires archived `PreCompact` and `PostCompact` receipts.

## Rules

- Export is clean by default.
- Session archives and raw transcripts move only with `--with-sessions`.
- Hook commands are generated from selected absolute roots.
- A green `validate` proves the temporary PreCompact/PostCompact/Stop archive
  route works.
- A green `codex-grounding` proves the local Codex version, compact config, and
  expected hook markers are visible on this host.
- A green `codex-hooks-status` proves native Codex hook discovery, command
  matching, and trust state are coherent.
- A green `codex-compact-probe` proves live `PreCompact` and `PostCompact`
  receipts reach the archive.
- A green `doctor` proves the installed filesystem contract is coherent.
