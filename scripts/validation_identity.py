#!/usr/bin/env python3
"""Exact local source and interpreter identities for validation evidence."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]


class IdentityError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: Any) -> str:
    return sha256_bytes(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(root: Path, args: Sequence[str]) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise IdentityError(f"git {' '.join(args)} failed: {detail or completed.returncode}")
    return completed.stdout


def _untracked_content_identity(root: Path, raw_paths: bytes) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    unreadable: list[str] = []
    for raw_path in sorted(item for item in raw_paths.split(b"\0") if item):
        relative = os.fsdecode(raw_path)
        path = root / relative
        try:
            metadata = path.lstat()
            if stat.S_ISREG(metadata.st_mode):
                content = sha256_file(path)
                kind = "file"
            elif stat.S_ISLNK(metadata.st_mode):
                content = sha256_bytes(os.fsencode(os.readlink(path)))
                kind = "symlink"
            else:
                content = sha256_bytes(str(metadata.st_mode).encode("ascii"))
                kind = "special"
            entries.append(
                {
                    "path_sha256": sha256_bytes(raw_path),
                    "kind": kind,
                    "content_sha256": content,
                }
            )
        except OSError:
            unreadable.append(sha256_bytes(raw_path))
    return {
        "count": len(entries),
        "entries_sha256": canonical_sha256(entries),
        "unreadable_path_sha256": unreadable,
    }


def repository_identity(root: Path = REPO_ROOT) -> dict[str, Any]:
    root = root.resolve()
    top_level = Path(
        _git(root, ("rev-parse", "--show-toplevel")).decode().strip()
    ).resolve()
    if top_level != root:
        raise IdentityError(
            f"repository root must equal Git top-level: requested={root} actual={top_level}"
        )
    status = _git(root, ("status", "--porcelain=v1", "-z", "--untracked-files=all"))
    patch = _git(root, ("diff", "--binary", "HEAD", "--", "."))
    untracked_paths = _git(root, ("ls-files", "--others", "--exclude-standard", "-z"))
    untracked = _untracked_content_identity(root, untracked_paths)
    if untracked["unreadable_path_sha256"]:
        raise IdentityError("one or more untracked source inputs became unreadable")
    identity: dict[str, Any] = {
        "git_commit": _git(root, ("rev-parse", "HEAD")).decode().strip(),
        "git_tree": _git(root, ("rev-parse", "HEAD^{tree}")).decode().strip(),
        "dirty": bool(status),
        "status_sha256": sha256_bytes(status),
        "worktree_patch_sha256": sha256_bytes(patch),
        "untracked": untracked,
    }
    identity["identity_sha256"] = canonical_sha256(identity)
    return identity


def environment_identity() -> dict[str, Any]:
    packages: dict[str, str | None] = {}
    for distribution in ("pytest", "pytest-xdist", "pluggy"):
        try:
            packages[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            packages[distribution] = None
    identity: dict[str, Any] = {
        "python_executable": str(Path(sys.executable).resolve()),
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "packages": packages,
        "runtime": {
            "ci": os.environ.get("CI"),
            "github_actions": os.environ.get("GITHUB_ACTIONS") == "true",
            "github_runner_arch": os.environ.get("RUNNER_ARCH"),
            "github_runner_os": os.environ.get("RUNNER_OS"),
            "github_runner_environment": os.environ.get("RUNNER_ENVIRONMENT"),
        },
    }
    identity["identity_sha256"] = canonical_sha256(identity)
    return identity
