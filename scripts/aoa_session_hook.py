#!/usr/bin/env python3
"""Small, fail-open Codex hook ingress for AoA session memory.

This file intentionally uses only the Python standard library and never
imports the large session-memory implementation on the foreground hook path.
The exact stdin bytes are durably queued for the owner worker.  Lifecycle
events wake one background worker; prompt events wait for the next lifecycle
or scheduled maintenance pass.
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "aoa_session_memory_hook_ingress_v1"
INGRESS_RELATIVE_ROOT = Path("diagnostics") / "hook-ingress"
URGENT_EVENTS = {"SessionStart", "PreCompact", "PostCompact", "Stop"}
FALSE_VALUES = {"0", "false", "no", "off"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def env_enabled(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().casefold() not in FALSE_VALUES


def resolved(path: str) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def ingress_dirs(aoa_root: Path) -> dict[str, Path]:
    root = aoa_root / INGRESS_RELATIVE_ROOT
    return {
        "root": root,
        "pending": root / "pending",
        "running": root / "running",
        "done": root / "done",
        "failed": root / "failed",
    }


def fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def event_digest(event_name: str, raw_event: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(event_name.encode("utf-8"))
    digest.update(b"\0")
    digest.update(raw_event)
    return digest.hexdigest()


def enqueue_event(
    *,
    event_name: str,
    raw_event: bytes,
    workspace_root: Path,
    aoa_root: Path,
) -> tuple[Path, dict[str, Any]]:
    dirs = ingress_dirs(aoa_root)
    for directory in dirs.values():
        created = not directory.exists()
        directory.mkdir(parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
        if created:
            fsync_directory(directory.parent)
    digest = event_digest(event_name, raw_event)
    path = dirs["pending"] / f"hook-ingress__{digest}.json"
    lock_path = dirs["root"] / "enqueue.lock"
    now = utc_now()
    exact_fields = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "codex_hook_ingress",
        "ingress_id": f"hook-ingress:{digest}",
        "event_name": event_name,
        "event_bytes": len(raw_event),
        "event_sha256": f"sha256:{hashlib.sha256(raw_event).hexdigest()}",
        "event_b64": base64.b64encode(raw_event).decode("ascii"),
        "workspace_root": str(workspace_root),
        "aoa_root": str(aoa_root),
        "source": "codex_hook_stdin",
        "privacy": "owner_private_runtime_evidence",
    }
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        os.chmod(lock_path, 0o600)
        fcntl.flock(lock_handle, fcntl.LOCK_EX)
        existing = read_json(path)
        if path.exists():
            mismatched = sorted(
                key
                for key, expected in exact_fields.items()
                if existing.get(key) != expected
            )
            if mismatched:
                raise ValueError(
                    "existing hook ingress envelope failed exact identity: "
                    + ", ".join(mismatched)
                )
            existing_count = existing.get("signal_count")
            if (
                isinstance(existing_count, bool)
                or not isinstance(existing_count, int)
                or existing_count < 1
            ):
                raise ValueError(
                    "existing hook ingress envelope has invalid signal_count"
                )
            payload = {
                **exact_fields,
                "queued_at": existing.get("queued_at") or now,
                "first_seen_at": existing.get("first_seen_at") or now,
                "last_seen_at": now,
                "signal_count": existing_count + 1,
            }
        else:
            payload = {
                **exact_fields,
                "queued_at": now,
                "first_seen_at": now,
                "last_seen_at": now,
                "signal_count": 1,
            }
        atomic_write_json(path, payload)
    return path, payload


def legacy_exec(
    *,
    event_name: str,
    workspace_root: Path,
    aoa_root: Path,
) -> None:
    full_script = Path(__file__).resolve().with_name("aoa_session_memory.py")
    os.execv(
        sys.executable or "python3",
        [
            sys.executable or "python3",
            str(full_script),
            "hook",
            "--event-name",
            event_name,
            "--workspace-root",
            str(workspace_root),
            "--aoa-root",
            str(aoa_root),
        ],
    )


def legacy_run(
    *,
    event_name: str,
    raw_event: bytes,
    workspace_root: Path,
    aoa_root: Path,
) -> int:
    full_script = Path(__file__).resolve().with_name("aoa_session_memory.py")
    try:
        completed = subprocess.run(
            [
                sys.executable or "python3",
                str(full_script),
                "hook",
                "--event-name",
                event_name,
                "--workspace-root",
                str(workspace_root),
                "--aoa-root",
                str(aoa_root),
            ],
            input=raw_event,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        output = json.loads(completed.stdout.decode("utf-8"))
        if isinstance(output, dict) and output.get("continue") is True:
            print(json.dumps(output, ensure_ascii=False))
            return 0
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        pass
    print(
        json.dumps(
            {
                "continue": True,
                "systemMessage": (
                    "AoA session memory capture failed open; "
                    "runtime recovery is required."
                ),
            },
            ensure_ascii=False,
        )
    )
    return 0


def launch_dispatcher(
    *,
    workspace_root: Path,
    aoa_root: Path,
) -> bool:
    if not env_enabled("AOA_SESSION_MEMORY_HOOK_BACKGROUND_SYNC", True):
        return False
    command = [
        sys.executable or "python3",
        str(Path(__file__).resolve()),
        "dispatch",
        "--workspace-root",
        str(workspace_root),
        "--aoa-root",
        str(aoa_root),
    ]
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
    except OSError:
        return False
    return True


def hook_output(
    *,
    event_name: str,
    event: dict[str, Any],
    queued: bool,
) -> dict[str, Any]:
    output: dict[str, Any] = {"continue": True}
    if event_name == "SessionStart" and queued:
        session_id = str(event.get("session_id") or "current-session")
        output["hookSpecificOutput"] = {
            "hookEventName": "SessionStart",
            "additionalContext": (
                "AoA session memory capture queued: "
                f"{session_id}."
            ),
        }
    return output


def command_enqueue(args: argparse.Namespace) -> int:
    workspace_root = resolved(args.workspace_root)
    aoa_root = resolved(args.aoa_root)
    if not env_enabled("AOA_SESSION_MEMORY_HOOK_FAST_INGRESS", True):
        legacy_exec(
            event_name=args.event_name,
            workspace_root=workspace_root,
            aoa_root=aoa_root,
        )
    raw_event = sys.stdin.buffer.read()
    try:
        parsed = json.loads(raw_event.decode("utf-8")) if raw_event.strip() else {}
        event = parsed if isinstance(parsed, dict) else {"payload": parsed}
    except (UnicodeDecodeError, json.JSONDecodeError):
        event = {}
    queued = False
    try:
        enqueue_event(
            event_name=args.event_name,
            raw_event=raw_event,
            workspace_root=workspace_root,
            aoa_root=aoa_root,
        )
        queued = True
    except Exception:
        # Preserve before degrading: a failed spool retries the existing
        # synchronous owner route. Only a second failure becomes fail-open.
        return legacy_run(
            event_name=args.event_name,
            raw_event=raw_event,
            workspace_root=workspace_root,
            aoa_root=aoa_root,
        )
    if queued and args.event_name in URGENT_EVENTS:
        launch_dispatcher(
            workspace_root=workspace_root,
            aoa_root=aoa_root,
        )
    print(
        json.dumps(
            hook_output(
                event_name=args.event_name,
                event=event,
                queued=queued,
            ),
            ensure_ascii=False,
        )
    )
    return 0


def command_dispatch(args: argparse.Namespace) -> int:
    workspace_root = resolved(args.workspace_root)
    aoa_root = resolved(args.aoa_root)
    root = ingress_dirs(aoa_root)["root"]
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    lock_path = root / "launch.lock"
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    os.fchmod(descriptor, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        full_script = Path(__file__).resolve().with_name(
            "aoa_session_memory.py"
        )
        if not full_script.is_file():
            return 0
        os.set_inheritable(descriptor, True)
        os.execv(
            sys.executable or "python3",
            [
                sys.executable or "python3",
                str(full_script),
                "hook-ingress-worker",
                "--workspace-root",
                str(workspace_root),
                "--aoa-root",
                str(aoa_root),
                "--ingress-limit",
                "20",
                "--job-limit",
                "5",
            ],
        )
    finally:
        os.close(descriptor)
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description="Thin AoA session-memory Codex hook ingress."
    )
    sub = root.add_subparsers(dest="command", required=True)
    enqueue = sub.add_parser("enqueue")
    enqueue.add_argument("--event-name", required=True)
    enqueue.add_argument("--workspace-root", required=True)
    enqueue.add_argument("--aoa-root", required=True)
    enqueue.set_defaults(func=command_enqueue)
    dispatch = sub.add_parser("dispatch")
    dispatch.add_argument("--workspace-root", required=True)
    dispatch.add_argument("--aoa-root", required=True)
    dispatch.set_defaults(func=command_dispatch)
    return root


def main() -> int:
    args = parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
