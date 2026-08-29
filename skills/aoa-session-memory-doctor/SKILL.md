---
name: aoa-session-memory-doctor
description: Use when the `.aoa` session-memory filesystem contract, registry, generated indexes, naming policy, live hooks, or Codex grounding need health checks.
license: Apache-2.0
metadata:
  aoa_scope: session-memory
  aoa_invocation_mode: manual
---

# aoa-session-memory-doctor

Use this for local health and repair orientation. `doctor` checks consistency;
it does not replace `audit`.

## Trigger Boundary

- A session archive looks inconsistent.
- Required root files, indexes, manifests, or registry entries may be missing.
- Live hook wiring or Codex grounding needs a health check.
- The user-level router skill needs to be checked for the current Codex user.
- A change touched bundle structure, naming, schemas, hooks, or generated
  surfaces.

## Procedure

Run the narrow filesystem and metadata doctor first:

```bash
python3 scripts/aoa_session_memory.py doctor \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root>
```

The default route is intentionally fast on large live archives. It checks
required surfaces, manifests, registry and generated-surface presence without
parsing every event in every segment index.

When required test files are absent, inspect `runtime_install_profile` in the
doctor result before repairing the root:

- a valid profile with `include_tests=false` admits runtime health with
  `truth_status=doctor_runtime_filesystem_contract_with_tests_excluded`; do not
  reinstall only to add tests, and report that source/export completion still
  requires the full portable test tree;
- a valid profile with `include_tests=true` plus missing test files is
  accidental loss and remains a failed doctor result;
- an absent, invalid, or differently bound profile does not prove intentional
  exclusion; route installation repair through `aoa-session-archive-init`
  rather than guessing or immediately forcing a full reinstall.

A partial test tree is never treated as an intentional runtime-only install.

When live hooks and Codex grounding matter, run:

```bash
python3 scripts/aoa_session_memory.py doctor \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --check-live-hooks \
  --check-user-skill \
  --check-codex-grounding
```

When the task is specifically to validate event payloads inside segment index
files, use the explicit deep route:

```bash
python3 scripts/aoa_session_memory.py doctor \
  --workspace-root <workspace-root> \
  --aoa-root <aoa-root> \
  --deep-segment-indexes
```

## Verification

- `ok=true`
- `status=current` or an explicitly deferred live-tail status
- `truth_status` matches the declared installation shape; a runtime-only pass
  does not claim source/export readiness
- no `problems`
- warnings are reported, not hidden
- if live checks were requested, hook and grounding subreports are green
- if `--check-user-skill` was requested, the global router points at this
  install

## Stop Line

Do not treat a green doctor as completion readiness. Use `audit` for that.
