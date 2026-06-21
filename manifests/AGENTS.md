# Manifests AGENTS.md

## Purpose

This directory owns portable, public-safe artifact manifests for the
session-memory kernel.

## Rules

- Keep manifests free of raw transcripts, session archives, diagnostics
  payloads, search databases, graph sidecars, secrets, and host-local evidence.
- Bundle manifests describe portable kernel subjects and hand off trust policy
  to `abyss-machine`; they do not make `.aoa` a trust-policy authority.
- If export behavior changes, validate the source root and standalone bundle.

