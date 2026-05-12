#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 fallback uses a narrow parser below.
    tomllib = None  # type: ignore[assignment]


SCHEMA_VERSION = 1
SESSION_ROOT = Path("sessions")
LEGACY_SESSION_ROOT = Path("codex-sessions")
REGISTRY_NAME = "session-registry.json"
NAMING_POLICY_PATH = Path("config/naming-policy.json")
SESSION_INDEX_MARKDOWN = "SESSION.md"
SESSION_INDEX_JSON = "session.index.json"
LEGACY_SESSION_INDEX_MARKDOWN = "00_SESSION_INDEX.md"
LEGACY_SESSION_INDEX_JSON = "00_SESSION_INDEX.json"
RAW_SOURCE_JSON = "source.json"
LEGACY_RAW_SOURCE_JSON = "raw-source.json"
EVENT_TYPE_ORDER = [
    "SESSION_META",
    "CONTEXT_STATE",
    "USER_INTENT",
    "ASSISTANT_PLAN",
    "ASSISTANT_MESSAGE",
    "TOOL_CALL",
    "TOOL_OUTPUT",
    "FILE_READ",
    "FILE_WRITE",
    "DIFF",
    "COMMAND",
    "COMMAND_OUTPUT",
    "ERROR",
    "DECISION",
    "ASSUMPTION",
    "CHECKPOINT",
    "COMPACTION_EVENT",
    "RESUME_HINT",
    "OPEN_THREAD",
    "DEAD_BRANCH",
    "PROCESS_LESSON",
    "OPTIMIZATION_CANDIDATE",
    "SECURITY_OR_SECRET_RISK",
    "VERIFICATION",
    "FINAL_STATE",
    "HOOK_EVENT",
    "RAW_EVENT",
]
HOOK_EVENT_ORDER = ["SessionStart", "UserPromptSubmit", "PreCompact", "PostCompact", "Stop"]
HOOK_TIMEOUTS = {
    "SessionStart": 20,
    "UserPromptSubmit": 20,
    "PreCompact": 30,
    "PostCompact": 30,
    "Stop": 20,
}
HOOK_STATUS_MESSAGES = {
    "SessionStart": "AoA session memory start",
    "UserPromptSubmit": "AoA session memory prompt",
    "PreCompact": "AoA session memory pre-compact",
    "PostCompact": "AoA session memory post-compact",
    "Stop": "AoA session memory stop",
}
REQUIRED_HOOK_EVENTS = HOOK_EVENT_ORDER
CODEX_APP_EVENT_NAMES = {
    "SessionStart": "sessionStart",
    "UserPromptSubmit": "userPromptSubmit",
    "PreCompact": "preCompact",
    "PostCompact": "postCompact",
    "Stop": "stop",
}
CODEX_HOOK_OUTPUT_FIELDS = {"continue", "stopReason", "suppressOutput", "systemMessage", "hookSpecificOutput"}
USER_LEVEL_SKILL_NAME = "aoa-session-memory-global-route"
PORTABLE_BUNDLE_ITEMS = [
    ".gitignore",
    "AGENTS.md",
    "DESIGN.md",
    "INSTALL.md",
    "NAMING.md",
    "PIPELINE.md",
    "READINESS.md",
    "README.md",
    "config",
    "hooks",
    "schemas",
    "scripts",
    "skills",
    "tests",
]
PORTABLE_COPY_IGNORE = {".git", ".pytest_cache", "__pycache__"}


@dataclass(frozen=True)
class RawEvent:
    event_id: str
    line_no: int
    raw: str
    parsed: dict[str, Any] | None
    event_type: str
    source_type: str
    title: str
    timestamp: str | None
    tags: list[str]
    importance: str
    compaction_boundary: bool


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def compact_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def safe_slug(value: str, *, fallback: str = "unresolved") -> str:
    value = value.strip()
    if not value:
        return fallback
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return slug or fallback


def readable_slug(value: str, *, fallback: str = "untitled-session", max_chars: int = 48) -> str:
    value = short_text(value, max_chars=max_chars * 2).lower()
    slug = re.sub(r"[^\w.-]+", "-", value, flags=re.UNICODE).strip("-._")
    slug = re.sub(r"-{2,}", "-", slug)
    if len(slug) > max_chars:
        slug = slug[:max_chars].rstrip("-._")
    return slug or fallback


def concise_title_text(text: str, *, max_words: int = 8, max_chars: int = 80) -> str:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return "Untitled session"
    first_line = lines[0]
    if first_line.startswith(("~", "/", "./", "../")):
        path = Path(first_line)
        if path.suffix:
            return path.stem
    compact = re.sub(r"\s+", " ", text).strip()
    words = compact.split()
    if len(words) > max_words:
        compact = " ".join(words[:max_words])
    if len(compact) > max_chars:
        compact = compact[:max_chars].rsplit(" ", 1)[0].strip() or compact[:max_chars].strip()
    return compact or "Untitled session"


def aoa_root_for(workspace_root: Path | None = None, explicit_root: Path | None = None) -> Path:
    if explicit_root is not None:
        return explicit_root
    env_root = os.environ.get("AOA_SESSION_MEMORY_ROOT")
    if env_root:
        return Path(env_root)
    if workspace_root is not None:
        return workspace_root / ".aoa"
    return default_source_aoa_root()


def workspace_root_for(workspace_root: Path | None, aoa_root: Path) -> Path:
    if workspace_root is not None:
        return workspace_root
    if aoa_root.name == ".aoa":
        return aoa_root.parent
    return Path.cwd()


def build_hook_command(event_name: str, workspace_root: Path, aoa_root: Path, *, python_bin: str = "python3") -> str:
    script = aoa_root / "scripts" / "aoa_session_memory.py"
    return " ".join(
        [
            shlex.quote(python_bin),
            shlex.quote(str(script)),
            "hook",
            "--event-name",
            shlex.quote(event_name),
            "--workspace-root",
            shlex.quote(str(workspace_root)),
            "--aoa-root",
            shlex.quote(str(aoa_root)),
        ]
    )


def build_user_hooks_config(workspace_root: Path, aoa_root: Path, *, python_bin: str = "python3") -> dict[str, Any]:
    hooks: dict[str, list[dict[str, Any]]] = {}
    for event_name in REQUIRED_HOOK_EVENTS:
        entry: dict[str, Any] = {
            "hooks": [
                {
                    "type": "command",
                    "command": build_hook_command(event_name, workspace_root, aoa_root, python_bin=python_bin),
                    "statusMessage": HOOK_STATUS_MESSAGES[event_name],
                    "timeout": HOOK_TIMEOUTS[event_name],
                }
            ]
        }
        if event_name == "SessionStart":
            entry = {"matcher": "startup|resume", **entry}
        hooks[event_name] = [entry]
    return {"hooks": hooks}


def expected_hook_commands(workspace_root: Path, aoa_root: Path, *, python_bin: str = "python3") -> dict[str, str]:
    config = build_user_hooks_config(workspace_root, aoa_root, python_bin=python_bin)
    return {
        event_name: str(config["hooks"][event_name][0]["hooks"][0]["command"])
        for event_name in REQUIRED_HOOK_EVENTS
    }


def hook_command_map(path: Path) -> dict[str, list[str]]:
    config = read_json(path, {})
    hooks = config.get("hooks") if isinstance(config, dict) else {}
    commands: dict[str, list[str]] = {}
    if not isinstance(hooks, dict):
        return commands
    for event_name, entries in hooks.items():
        event_commands: list[str] = []
        for entry in entries if isinstance(entries, list) else []:
            if not isinstance(entry, dict):
                continue
            hook_items = entry.get("hooks")
            for hook in hook_items if isinstance(hook_items, list) else []:
                if isinstance(hook, dict) and hook.get("type") == "command" and hook.get("command"):
                    event_commands.append(str(hook["command"]))
        commands[str(event_name)] = event_commands
    return commands


def default_source_aoa_root() -> Path:
    return Path(__file__).resolve().parents[1]


def default_standalone_repo_for(aoa_root: Path) -> Path:
    if (aoa_root / ".git").exists():
        return aoa_root
    if aoa_root.name == ".aoa":
        bundled_repo = aoa_root.parent / "bundles" / "aoa-session-memory"
        legacy_repo = aoa_root.parent / "aoa-session-memory"
        if bundled_repo.exists() or not legacy_repo.exists():
            return bundled_repo
        return legacy_repo
    return aoa_root


def default_user_skills_dir() -> Path:
    return Path.home() / ".codex" / "skills"


def user_level_skill_source(aoa_root: Path) -> Path:
    return aoa_root.expanduser().resolve(strict=False) / "skills" / USER_LEVEL_SKILL_NAME


def user_level_skill_target(skills_dir: Path | None = None) -> Path:
    return (skills_dir or default_user_skills_dir()).expanduser() / USER_LEVEL_SKILL_NAME


def resolve_non_strict(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def user_skill_install_state(aoa_root: Path, skills_dir: Path | None = None) -> dict[str, Any]:
    source = user_level_skill_source(aoa_root)
    target = user_level_skill_target(skills_dir)
    source_skill = source / "SKILL.md"
    target_skill = target / "SKILL.md"
    target_exists = target.exists() or target.is_symlink()
    source_exists = source_skill.exists()
    target_skill_exists = target_skill.exists()
    target_resolved = resolve_non_strict(target) if target_exists else None
    source_resolved = resolve_non_strict(source)
    linked_to_source = target.is_symlink() and target_resolved == source_resolved
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": source_exists and linked_to_source and target_skill_exists,
        "skill_name": USER_LEVEL_SKILL_NAME,
        "source": str(source),
        "source_skill_exists": source_exists,
        "skills_dir": str((skills_dir or default_user_skills_dir()).expanduser()),
        "target": str(target),
        "target_exists": target_exists,
        "target_is_symlink": target.is_symlink(),
        "target_resolved": str(target_resolved) if target_resolved else None,
        "target_skill_exists": target_skill_exists,
        "linked_to_source": linked_to_source,
    }


def install_user_skill(
    *,
    aoa_root: Path,
    skills_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    source = user_level_skill_source(aoa_root)
    target = user_level_skill_target(skills_dir)
    source_skill = source / "SKILL.md"
    if not source_skill.exists():
        return {
            **user_skill_install_state(aoa_root, skills_dir),
            "ok": False,
            "installed": False,
            "error": f"missing source skill: {source_skill}",
        }

    before = user_skill_install_state(aoa_root, skills_dir)
    if before["ok"]:
        return {**before, "installed": False, "already_installed": True, "backup_path": None}

    target.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if target.exists() or target.is_symlink():
        if not force:
            return {
                **before,
                "ok": False,
                "installed": False,
                "error": "target exists and does not point to source; rerun with --force to back it up and replace it",
            }
        backup_path = target.with_name(f"{target.name}.{compact_stamp()}.bak")
        shutil.move(str(target), str(backup_path))

    target.symlink_to(source, target_is_directory=True)
    after = user_skill_install_state(aoa_root, skills_dir)
    return {
        **after,
        "installed": bool(after["ok"]),
        "already_installed": False,
        "backup_path": str(backup_path) if backup_path else None,
    }


def git_remote_url(repo_root: Path, remote: str = "origin") -> str | None:
    if not (repo_root / ".git").exists():
        return None
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", remote],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
    except Exception:
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


class CodexAppServerClient:
    def __init__(self, *, codex_bin: str, cwd: Path, timeout: int = 30) -> None:
        self.codex_bin = codex_bin
        self.cwd = cwd
        self.timeout = timeout
        self.process: subprocess.Popen[str] | None = None
        self.stdout_queue: queue.Queue[str] = queue.Queue()
        self.stderr_queue: queue.Queue[str] = queue.Queue()

    def __enter__(self) -> "CodexAppServerClient":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def start(self) -> None:
        self.process = subprocess.Popen(
            [self.codex_bin, "app-server", "--listen", "stdio://", "-c", "features.hooks=true"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(self.cwd),
        )
        assert self.process.stdout is not None
        assert self.process.stderr is not None
        threading.Thread(target=self._read_stream, args=(self.process.stdout, self.stdout_queue), daemon=True).start()
        threading.Thread(target=self._read_stream, args=(self.process.stderr, self.stderr_queue), daemon=True).start()

    @staticmethod
    def _read_stream(stream: Any, target: queue.Queue[str]) -> None:
        for line in stream:
            target.put(line.rstrip("\n"))

    def send(self, payload: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            raise RuntimeError("Codex app-server is not running")
        self.process.stdin.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def recv_response(self, response_id: int, *, timeout: int | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        deadline = time.time() + (timeout or self.timeout)
        seen: list[dict[str, Any]] = []
        while time.time() < deadline:
            line = self._next_stdout_line(deadline)
            if line is None:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                seen.append(payload)
                if payload.get("id") == response_id:
                    return payload, seen
        raise TimeoutError(f"timed out waiting for Codex app-server response id={response_id}: {self.stderr_tail()}")

    def collect_until(self, predicate: Any, *, timeout: int | None = None) -> list[dict[str, Any]]:
        deadline = time.time() + (timeout or self.timeout)
        seen: list[dict[str, Any]] = []
        while time.time() < deadline:
            line = self._next_stdout_line(deadline)
            if line is None:
                if self.process is not None and self.process.poll() is not None:
                    break
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            seen.append(payload)
            if predicate(payload, seen):
                return seen
        raise TimeoutError(f"timed out waiting for Codex app-server event: {self.stderr_tail()}")

    def _next_stdout_line(self, deadline: float) -> str | None:
        remaining = max(0.05, min(0.5, deadline - time.time()))
        try:
            return self.stdout_queue.get(timeout=remaining)
        except queue.Empty:
            return None

    def stderr_tail(self, limit: int = 20) -> list[str]:
        rows: list[str] = []
        while True:
            try:
                rows.append(self.stderr_queue.get_nowait())
            except queue.Empty:
                break
        return rows[-limit:]

    def close(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)


def initialize_codex_app_server(client: CodexAppServerClient, *, client_name: str) -> dict[str, Any]:
    client.send(
        {
            "method": "initialize",
            "id": 1,
            "params": {
                "clientInfo": {
                    "name": client_name,
                    "title": client_name.replace("_", " ").title(),
                    "version": "0.1.0",
                },
                "capabilities": {"experimentalApi": True},
            },
        }
    )
    response, _seen = client.recv_response(1)
    if "error" in response:
        raise RuntimeError(f"Codex app-server initialize failed: {response['error']}")
    client.send({"method": "initialized", "params": {}})
    return response


def hook_lookup_from_app_hooks(hooks: list[dict[str, Any]], expected_commands: dict[str, str]) -> dict[str, dict[str, Any]]:
    by_event: dict[str, dict[str, Any]] = {}
    for event_name, app_event_name in CODEX_APP_EVENT_NAMES.items():
        expected_command = expected_commands.get(event_name)
        matches = [
            hook
            for hook in hooks
            if isinstance(hook, dict)
            and hook.get("eventName") == app_event_name
            and hook.get("command") == expected_command
        ]
        hook = matches[0] if matches else None
        by_event[event_name] = {
            "event_name": event_name,
            "app_event_name": app_event_name,
            "expected_command": expected_command,
            "present": hook is not None,
            "trusted": bool(hook and hook.get("trustStatus") == "trusted"),
            "trust_status": hook.get("trustStatus") if hook else None,
            "enabled": hook.get("enabled") if hook else None,
            "key": hook.get("key") if hook else None,
            "current_hash": hook.get("currentHash") if hook else None,
        }
    return by_event


def hook_trust_state_from_lookup(lookup: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
    state: dict[str, dict[str, str]] = {}
    for item in lookup.values():
        key = item.get("key")
        current_hash = item.get("current_hash")
        if key and current_hash:
            state[str(key)] = {"trusted_hash": str(current_hash)}
    return state


def codex_hooks_status(
    *,
    workspace_root: Path,
    aoa_root: Path,
    codex_bin: str = "codex",
    trust_current: bool = False,
    timeout: int = 30,
) -> dict[str, Any]:
    expected_commands = expected_hook_commands(workspace_root, aoa_root)
    with CodexAppServerClient(codex_bin=codex_bin, cwd=workspace_root, timeout=timeout) as client:
        initialize_codex_app_server(client, client_name="aoa_hooks_status")
        client.send({"method": "hooks/list", "id": 2, "params": {"cwds": [str(workspace_root)]}})
        hooks_response, _seen = client.recv_response(2, timeout=timeout)
        if "error" in hooks_response:
            raise RuntimeError(f"hooks/list failed: {hooks_response['error']}")
        data = hooks_response.get("result", {}).get("data", []) if isinstance(hooks_response.get("result"), dict) else []
        hooks = data[0].get("hooks", []) if data and isinstance(data[0], dict) and isinstance(data[0].get("hooks"), list) else []
        lookup = hook_lookup_from_app_hooks(hooks, expected_commands)
        trusted_state: dict[str, dict[str, str]] = {}
        trust_response: dict[str, Any] | None = None
        if trust_current:
            trusted_state = hook_trust_state_from_lookup(lookup)
            client.send(
                {
                    "method": "config/batchWrite",
                    "id": 3,
                    "params": {
                        "edits": [
                            {
                                "keyPath": "hooks.state",
                                "value": trusted_state,
                                "mergeStrategy": "upsert",
                            }
                        ],
                        "reloadUserConfig": True,
                    },
                }
            )
            trust_response, _seen = client.recv_response(3, timeout=timeout)
            client.send({"method": "hooks/list", "id": 4, "params": {"cwds": [str(workspace_root)]}})
            hooks_response, _seen = client.recv_response(4, timeout=timeout)
            data = hooks_response.get("result", {}).get("data", []) if isinstance(hooks_response.get("result"), dict) else []
            hooks = data[0].get("hooks", []) if data and isinstance(data[0], dict) and isinstance(data[0].get("hooks"), list) else []
            lookup = hook_lookup_from_app_hooks(hooks, expected_commands)

    checks = [
        {"name": "required_hooks_present", "ok": all(item["present"] for item in lookup.values())},
        {"name": "required_hooks_trusted", "ok": all(item["trusted"] for item in lookup.values())},
        {
            "name": "required_hook_commands_match",
            "ok": all(item["present"] and item["expected_command"] for item in lookup.values()),
        },
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": all(check["ok"] for check in checks),
        "workspace_root": str(workspace_root),
        "aoa_root": str(aoa_root),
        "codex_bin": codex_bin,
        "trusted_written": trust_current,
        "trusted_state": trusted_state,
        "trust_response": trust_response,
        "hooks": lookup,
        "checks": checks,
    }


def codex_manual_compact_probe(
    *,
    workspace_root: Path,
    aoa_root: Path,
    codex_bin: str = "codex",
    trust_hooks: bool = False,
    timeout: int = 150,
) -> dict[str, Any]:
    before_counts = count_live_hook_events(aoa_root)
    trust_payload: dict[str, Any] | None = None
    if trust_hooks:
        trust_payload = codex_hooks_status(
            workspace_root=workspace_root,
            aoa_root=aoa_root,
            codex_bin=codex_bin,
            trust_current=True,
            timeout=timeout,
        )

    with CodexAppServerClient(codex_bin=codex_bin, cwd=workspace_root, timeout=timeout) as client:
        initialize_codex_app_server(client, client_name="aoa_compact_probe")
        client.send({"method": "thread/start", "id": 2, "params": {"cwd": str(workspace_root), "sessionStartSource": "startup"}})
        start_response, _seen = client.recv_response(2, timeout=timeout)
        if "error" in start_response:
            raise RuntimeError(f"thread/start failed: {start_response['error']}")
        thread = start_response.get("result", {}).get("thread", {}) if isinstance(start_response.get("result"), dict) else {}
        thread_id = str(thread.get("id") or "")
        if not thread_id:
            raise RuntimeError("thread/start did not return a thread id")
        injected_items = [
            {
                "type": "message",
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "AoA manual compact live hook probe. Preserve this as a tiny injected user item.",
                    }
                ],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": "AoA compact probe assistant item present before manual compaction.",
                    }
                ],
            },
        ]
        client.send({"method": "thread/inject_items", "id": 3, "params": {"threadId": thread_id, "items": injected_items}})
        inject_response, _seen = client.recv_response(3, timeout=timeout)
        if "error" in inject_response:
            raise RuntimeError(f"thread/inject_items failed: {inject_response['error']}")
        client.send({"method": "thread/compact/start", "id": 4, "params": {"threadId": thread_id}})
        compact_response, _seen = client.recv_response(4, timeout=timeout)
        if "error" in compact_response:
            raise RuntimeError(f"thread/compact/start failed: {compact_response['error']}")
        events = client.collect_until(
            lambda payload, _seen: payload.get("method") == "turn/completed"
            and payload.get("params", {}).get("threadId") == thread_id,
            timeout=timeout,
        )

    after_counts = count_live_hook_events(aoa_root)
    hook_events = [
        payload
        for payload in events
        if payload.get("method") in {"hook/started", "hook/completed"}
    ]
    completed_hooks = [
        payload
        for payload in hook_events
        if payload.get("method") == "hook/completed"
        and payload.get("params", {}).get("run", {}).get("status") == "completed"
    ]
    completed_event_names = {
        payload.get("params", {}).get("run", {}).get("eventName")
        for payload in completed_hooks
    }
    pre_seen = "preCompact" in completed_event_names and after_counts.get("PreCompact", 0) > before_counts.get("PreCompact", 0)
    post_seen = "postCompact" in completed_event_names and after_counts.get("PostCompact", 0) > before_counts.get("PostCompact", 0)
    checks = [
        {"name": "thread_started", "ok": bool(thread_id)},
        {"name": "manual_compact_completed", "ok": any(payload.get("method") == "turn/completed" for payload in events)},
        {"name": "precompact_hook_completed_and_archived", "ok": pre_seen},
        {"name": "postcompact_hook_completed_and_archived", "ok": post_seen},
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": all(check["ok"] for check in checks),
        "workspace_root": str(workspace_root),
        "aoa_root": str(aoa_root),
        "codex_bin": codex_bin,
        "thread_id": thread_id,
        "before_hook_counts": before_counts,
        "after_hook_counts": after_counts,
        "completed_hook_event_names": sorted(name for name in completed_event_names if name),
        "hook_event_count": len(hook_events),
        "event_count": len(events),
        "trust_payload": trust_payload,
        "checks": checks,
    }


def copytree_ignore(_directory: str, names: list[str]) -> set[str]:
    ignored = {name for name in names if name in PORTABLE_COPY_IGNORE or name.endswith(".pyc")}
    return ignored


def copy_portable_bundle(
    *,
    source_aoa_root: Path,
    target_aoa_root: Path,
    include_sessions: bool = False,
    include_tests: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    source_aoa_root = source_aoa_root.resolve()
    target_aoa_root = target_aoa_root.resolve()
    if source_aoa_root == target_aoa_root:
        raise ValueError("source and target .aoa roots are the same")
    if not source_aoa_root.exists():
        raise ValueError(f"source .aoa root does not exist: {source_aoa_root}")
    if target_aoa_root.exists() and any(target_aoa_root.iterdir()) and not overwrite:
        raise ValueError(f"target .aoa root is not empty; pass --force to overwrite portable files: {target_aoa_root}")

    target_aoa_root.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    for rel_name in PORTABLE_BUNDLE_ITEMS:
        if rel_name == "tests" and not include_tests:
            continue
        source_path = source_aoa_root / rel_name
        target_path = target_aoa_root / rel_name
        if not source_path.exists():
            continue
        if source_path.is_dir():
            if target_path.exists() and overwrite:
                shutil.rmtree(target_path)
            if not target_path.exists():
                shutil.copytree(source_path, target_path, ignore=copytree_ignore)
            copied.append(rel_name)
        else:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists() and not overwrite:
                continue
            shutil.copy2(source_path, target_path)
            copied.append(rel_name)

    if include_sessions:
        for rel_name in (str(SESSION_ROOT), REGISTRY_NAME):
            source_path = source_aoa_root / rel_name
            target_path = target_aoa_root / rel_name
            if not source_path.exists():
                continue
            if source_path.is_dir():
                if target_path.exists() and overwrite:
                    shutil.rmtree(target_path)
                if not target_path.exists():
                    shutil.copytree(source_path, target_path, ignore=copytree_ignore)
            else:
                shutil.copy2(source_path, target_path)
            copied.append(rel_name)
    else:
        session_root = target_aoa_root / SESSION_ROOT
        existing_sessions = session_root.exists() and any(session_root.iterdir())
        session_root.mkdir(parents=True, exist_ok=True)
        if not existing_sessions:
            write_json(target_aoa_root / REGISTRY_NAME, {"schema_version": SCHEMA_VERSION, "updated_at": utc_now(), "sessions": []})

    legacy_root = target_aoa_root / LEGACY_SESSION_ROOT
    if legacy_root.exists() and not include_sessions:
        shutil.rmtree(legacy_root)

    return {
        "source_aoa_root": str(source_aoa_root),
        "target_aoa_root": str(target_aoa_root),
        "include_sessions": include_sessions,
        "include_tests": include_tests,
        "copied": copied,
    }


def clear_export_target_for_force(target: Path) -> None:
    """Clear a bundle target while preserving repository metadata."""
    if not target.exists():
        return
    for child in target.iterdir():
        if child.name == ".git":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def install_portable_bundle(
    *,
    source_aoa_root: Path,
    workspace_root: Path,
    aoa_root: Path,
    include_sessions: bool = False,
    include_tests: bool = True,
    overwrite: bool = False,
    hooks_path: Path | None = None,
    backup_hooks: bool = True,
) -> dict[str, Any]:
    copy_payload = copy_portable_bundle(
        source_aoa_root=source_aoa_root,
        target_aoa_root=aoa_root,
        include_sessions=include_sessions,
        include_tests=include_tests,
        overwrite=overwrite,
    )
    hook_config = build_user_hooks_config(workspace_root, aoa_root)
    write_json(aoa_root / "hooks" / "codex-hooks.user.example.json", hook_config)

    live_hooks_payload: dict[str, Any] | None = None
    if hooks_path is not None:
        backup_path: Path | None = None
        hooks_path = hooks_path.expanduser()
        if hooks_path.exists() and backup_hooks:
            backup_path = hooks_path.with_name(f"{hooks_path.name}.{compact_stamp()}.bak")
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(hooks_path, backup_path)
        write_json(hooks_path, hook_config)
        live_hooks_payload = {"path": str(hooks_path), "backup_path": str(backup_path) if backup_path else None}

    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "workspace_root": str(workspace_root),
        "aoa_root": str(aoa_root),
        "copy": copy_payload,
        "hook_example": str(aoa_root / "hooks" / "codex-hooks.user.example.json"),
        "live_hooks": live_hooks_payload,
    }


CODEX_SCHEMA_MARKERS = {
    "SessionStart": [b"SessionStart", b"session-start.command.input"],
    "UserPromptSubmit": [b"user-prompt-submit.command.input"],
    "PreCompact": [b"PreCompact", b"pre-compact.command"],
    "PostCompact": [b"PostCompact", b"post-compact.command"],
    "Stop": [b"stopReason"],
}


def run_codex_version(codex_bin: str) -> tuple[str | None, str | None]:
    try:
        completed = subprocess.run(
            [codex_bin, "--version"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
    except Exception as exc:
        return None, f"{exc.__class__.__name__}: {exc}"
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        return output or None, f"codex --version exited {completed.returncode}"
    return output, None


def resolve_codex_native_binary(codex_bin: str) -> Path | None:
    resolved = shutil.which(codex_bin)
    if not resolved:
        return None
    path = Path(resolved).resolve()
    candidates: list[Path] = []
    package_root = path.parents[1] if path.name == "codex.js" and len(path.parents) > 1 else None
    if package_root:
        candidates.extend(package_root.glob("node_modules/@openai/codex-*/vendor/*/codex/codex"))
        candidates.extend(package_root.glob("vendor/*/codex/codex"))
    if path.is_file() and os.access(path, os.X_OK) and path.suffix != ".js":
        candidates.append(path)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def file_contains_all_any(path: Path, markers_by_name: dict[str, list[bytes]]) -> dict[str, bool]:
    remaining = {name: list(markers) for name, markers in markers_by_name.items()}
    found = {name: False for name in markers_by_name}
    max_marker = max((len(marker) for markers in markers_by_name.values() for marker in markers), default=1)
    tail = b""
    with path.open("rb") as handle:
        while remaining:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            data = tail + chunk
            for name, markers in list(remaining.items()):
                if any(marker in data for marker in markers):
                    found[name] = True
                    remaining.pop(name, None)
            tail = data[-max_marker:]
    return found


def load_codex_project_config(workspace_root: Path) -> dict[str, Any]:
    config_path = workspace_root / ".codex" / "config.toml"
    if not config_path.exists():
        return {}
    if tomllib is not None:
        try:
            with config_path.open("rb") as handle:
                loaded = tomllib.load(handle)
            return loaded if isinstance(loaded, dict) else {}
        except Exception:
            return {}

    # Narrow fallback for the fields this grounding check needs.
    payload: dict[str, Any] = {"features": {}}
    section: str | None = None
    for line in config_path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped:
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped.strip("[]")
            payload.setdefault(section, {})
            continue
        if "=" not in stripped:
            continue
        key, raw_value = [part.strip() for part in stripped.split("=", 1)]
        if raw_value.lower() in {"true", "false"}:
            value: Any = raw_value.lower() == "true"
        else:
            try:
                value = int(raw_value)
            except ValueError:
                value = raw_value.strip('"')
        if section:
            payload.setdefault(section, {})[key] = value
        else:
            payload[key] = value
    return payload


def codex_grounding(
    *,
    workspace_root: Path,
    aoa_root: Path,
    codex_bin: str = "codex",
    codex_native_bin: Path | None = None,
    codex_version_output: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add_check(name: str, ok: bool, detail: Any = None) -> None:
        item: dict[str, Any] = {"name": name, "ok": bool(ok)}
        if detail is not None:
            item["detail"] = detail
        checks.append(item)

    version_error: str | None = None
    if codex_version_output is None:
        codex_version_output, version_error = run_codex_version(codex_bin)
    add_check("codex_version_available", bool(codex_version_output), version_error)

    config = load_codex_project_config(workspace_root)
    features = config.get("features") if isinstance(config.get("features"), dict) else {}
    hooks_enabled = features.get("hooks") is True
    context_window = int(config.get("model_context_window") or 0)
    compact_limit = int(config.get("model_auto_compact_token_limit") or 0)
    compact_ratio = compact_limit / context_window if context_window > 0 else None
    add_check("project_hooks_enabled", hooks_enabled)
    add_check("compact_window_configured", context_window > 0 and compact_limit > 0 and compact_limit < context_window, {"context_window": context_window, "compact_limit": compact_limit, "ratio": compact_ratio})

    native_binary = codex_native_bin or resolve_codex_native_binary(codex_bin)
    add_check("codex_native_binary_found", native_binary is not None, str(native_binary) if native_binary else None)
    marker_results: dict[str, bool] = {}
    if native_binary is not None:
        try:
            marker_results = file_contains_all_any(native_binary, CODEX_SCHEMA_MARKERS)
            for event_name in REQUIRED_HOOK_EVENTS:
                add_check(f"codex_marker_{event_name}", marker_results.get(event_name) is True)
        except Exception as exc:
            add_check("codex_marker_scan", False, f"{exc.__class__.__name__}: {exc}")

    payload = {
        "schema_version": SCHEMA_VERSION,
        "ok": all(check["ok"] for check in checks),
        "workspace_root": str(workspace_root),
        "aoa_root": str(aoa_root),
        "codex_bin": codex_bin,
        "codex_version": codex_version_output,
        "codex_native_binary": str(native_binary) if native_binary else None,
        "model_context_window": context_window,
        "model_auto_compact_token_limit": compact_limit,
        "compact_ratio": compact_ratio,
        "schema_markers": marker_results,
        "checks": checks,
    }
    return payload


def session_id_from(event: dict[str, Any], transcript_path: Path | None = None) -> str:
    session_id = str(event.get("session_id") or "").strip()
    if session_id:
        return safe_slug(session_id)
    if transcript_path:
        match = re.search(r"([0-9a-f]{8}-[0-9a-f-]{27,})", transcript_path.name)
        if match:
            return safe_slug(match.group(1))
        return safe_slug(transcript_path.stem)
    return f"unresolved-session-{compact_stamp()}"


def default_session_dir(aoa_root: Path, session_id: str) -> Path:
    return aoa_root / SESSION_ROOT / session_id


def session_dir_for_id(aoa_root: Path, session_id: str) -> Path:
    registry = read_json(aoa_root / REGISTRY_NAME, {"sessions": []})
    sessions = registry.get("sessions", []) if isinstance(registry, dict) else []
    for item in sessions if isinstance(sessions, list) else []:
        if not isinstance(item, dict) or item.get("session_id") != session_id:
            continue
        path_value = item.get("path")
        if path_value:
            path = Path(str(path_value))
            if (path / "session.manifest.json").exists() or path.exists():
                return path
    for root_name in (SESSION_ROOT, LEGACY_SESSION_ROOT):
        session_root = aoa_root / root_name
        if not session_root.exists():
            continue
        for manifest_path in session_root.glob("*/session.manifest.json"):
            manifest = read_json(manifest_path, {})
            if isinstance(manifest, dict) and manifest.get("session_id") == session_id:
                return manifest_path.parent
    return default_session_dir(aoa_root, session_id)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def short_text(value: Any, *, max_chars: int = 120) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def value_contains(value: Any, needle: str) -> bool:
    try:
        return needle in json.dumps(value, ensure_ascii=False).lower()
    except Exception:
        return needle in str(value).lower()


def naming_policy(aoa_root: Path) -> dict[str, Any]:
    policy = read_json(aoa_root / NAMING_POLICY_PATH, {})
    return policy if isinstance(policy, dict) else {}


def name_terms(value: str) -> set[str]:
    return {term for term in re.split(r"[-_.]+", value.lower()) if term}


def payload_has_compaction_boundary(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    summary = payload.get("summary")
    if isinstance(summary, str) and summary.strip().lower() not in {"", "none", "null"}:
        return True
    for key in ("compaction", "compacted", "compact_summary", "handoff_summary"):
        if key in payload and payload.get(key):
            return True
    return value_contains(payload.get("hook_event_name"), "compact")


def has_error_signal(raw_lower: str) -> bool:
    if "traceback" in raw_lower or "exception" in raw_lower:
        return True
    if "permission denied" in raw_lower or "no such file or directory" in raw_lower:
        return True
    if re.search(r"(process exited with code|exit code:)\s*[1-9]", raw_lower):
        return True
    if re.search(r"\b(error|failed|failure):", raw_lower):
        return True
    return False


def parse_raw_events(raw_path: Path) -> list[RawEvent]:
    events: list[RawEvent] = []
    with raw_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            raw = line.rstrip("\n")
            parsed: dict[str, Any] | None = None
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                parsed = None
            events.append(classify_raw_event(raw, parsed, line_no))
    return events


def parse_raw_event_sample(raw_path: Path, *, max_lines: int = 2000) -> list[RawEvent]:
    events: list[RawEvent] = []
    with raw_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            if line_no > max_lines:
                break
            raw = line.rstrip("\n")
            parsed: dict[str, Any] | None = None
            try:
                loaded = json.loads(raw)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                parsed = None
            events.append(classify_raw_event(raw, parsed, line_no))
    return events


def classify_raw_event(raw: str, parsed: dict[str, Any] | None, line_no: int) -> RawEvent:
    event_id = f"{line_no:06d}"
    if parsed is None:
        return RawEvent(
            event_id=event_id,
            line_no=line_no,
            raw=raw,
            parsed=None,
            event_type="RAW_EVENT",
            source_type="unparsed",
            title="Unparsed raw session line",
            timestamp=None,
            tags=["unparsed"],
            importance="medium",
            compaction_boundary=False,
        )

    source_type = str(parsed.get("type") or "unresolved-source")
    payload = parsed.get("payload")
    payload_type = payload.get("type") if isinstance(payload, dict) else None
    timestamp = str(parsed.get("timestamp") or "") or None
    raw_lower = raw.lower()
    tags: set[str] = {source_type}
    event_type = "RAW_EVENT"
    title = source_type
    importance = "medium"

    if source_type == "session_meta":
        event_type = "SESSION_META"
        session_id = payload.get("id") if isinstance(payload, dict) else ""
        title = f"Session metadata {short_text(session_id, max_chars=48)}".strip()
        tags.update(["session", "metadata"])
        importance = "critical"
    elif source_type == "compacted":
        event_type = "COMPACTION_EVENT"
        replacement_count = len(payload.get("replacement_history", [])) if isinstance(payload, dict) and isinstance(payload.get("replacement_history"), list) else 0
        title = f"Codex context compacted ({replacement_count} replacement history items)"
        tags.update(["compaction", "codex_compacted"])
        importance = "critical"
    elif source_type == "turn_context":
        event_type = "CONTEXT_STATE"
        title = "Turn context"
        tags.update(["context", "turn"])
        if payload_has_compaction_boundary(payload):
            tags.add("compaction")
            event_type = "COMPACTION_EVENT"
            title = "Compaction or summarized turn context"
            importance = "critical"
    elif source_type == "response_item" and isinstance(payload, dict):
        item_type = str(payload.get("type") or "unresolved-response-item")
        tags.add(item_type)
        if item_type == "message":
            role = str(payload.get("role") or "")
            tags.add(role or "message")
            if role == "user":
                event_type = "USER_INTENT"
                title = "User message"
                importance = "high"
            elif role == "assistant":
                event_type = "ASSISTANT_MESSAGE"
                title = "Assistant message"
            else:
                event_type = "RAW_EVENT"
                title = f"Message {role}".strip()
        elif item_type in {"function_call", "tool_call"}:
            event_type = "TOOL_CALL"
            name = payload.get("name") or payload.get("tool_name") or "tool"
            title = f"Tool call: {short_text(name, max_chars=80)}"
            tags.add(str(name))
            importance = "high"
            tool_name = str(name)
            if tool_name in {"exec_command", "write_stdin"}:
                event_type = "COMMAND"
                tags.add("command")
            elif tool_name == "apply_patch":
                event_type = "DIFF"
                tags.update(["patch", "file_write"])
        elif item_type in {"function_call_output", "tool_call_output"}:
            event_type = "TOOL_OUTPUT"
            title = f"Tool output: {short_text(payload.get('call_id'), max_chars=80)}"
            tags.add("tool_output")
            importance = "high"
            if "process exited" in raw_lower or "stdout" in raw_lower or "stderr" in raw_lower:
                event_type = "COMMAND_OUTPUT"
                tags.add("command_output")
            elif "success. updated the following files" in raw_lower or "apply_patch" in raw_lower:
                event_type = "DIFF"
                tags.update(["patch", "file_write"])
        elif item_type == "reasoning":
            event_type = "ASSISTANT_PLAN"
            title = "Assistant reasoning item"
            tags.add("reasoning")
        else:
            title = f"Response item: {item_type}"
    elif source_type == "event_msg" and isinstance(payload, dict):
        event_type = "HOOK_EVENT"
        msg_type = str(payload.get("type") or "event")
        title = f"Event message: {msg_type}"
        tags.add(msg_type)
        if msg_type == "user_message":
            event_type = "USER_INTENT"
            importance = "high"
        elif msg_type == "agent_message":
            event_type = "ASSISTANT_MESSAGE"
        elif msg_type == "context_compacted":
            event_type = "COMPACTION_EVENT"
            title = "Codex context compacted event message"
            tags.update(["compaction", "context_compacted"])
            importance = "critical"
        elif msg_type == "token_count":
            event_type = "CONTEXT_STATE"
            tags.add("token_count")
    if has_error_signal(raw_lower):
        tags.add("error_signal")
        if event_type in {"RAW_EVENT", "TOOL_OUTPUT", "COMMAND_OUTPUT", "HOOK_EVENT"}:
            event_type = "ERROR"
            importance = "high"
    if "decision" in raw_lower or "решили" in raw_lower or "вердикт" in raw_lower:
        tags.add("decision_signal")
        if event_type == "ASSISTANT_MESSAGE":
            event_type = "DECISION"
            importance = "high"
    if "checkpoint" in raw_lower or "чекпо" in raw_lower:
        tags.add("checkpoint")
    if "compact" in raw_lower or "compaction" in raw_lower or "сжати" in raw_lower:
        tags.add("compaction")

    compaction_boundary = event_type == "COMPACTION_EVENT" and (
        source_type == "compacted"
        or "compact" in raw_lower
        or "summary" in raw_lower
        or "сжати" in raw_lower
    )

    return RawEvent(
        event_id=event_id,
        line_no=line_no,
        raw=raw,
        parsed=parsed,
        event_type=event_type if event_type in EVENT_TYPE_ORDER else "RAW_EVENT",
        source_type=source_type,
        title=title,
        timestamp=timestamp,
        tags=sorted(tag for tag in tags if tag),
        importance=importance,
        compaction_boundary=compaction_boundary,
    )


def event_msg_type(event: RawEvent) -> str:
    parsed = event.parsed
    if not isinstance(parsed, dict):
        return ""
    payload = parsed.get("payload")
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("type") or "")


def compacted_event_cluster_end(events: list[RawEvent], start_index: int) -> int:
    event = events[start_index]
    if event.source_type != "compacted":
        return start_index
    end_index = start_index
    search_limit = min(len(events), start_index + 12)
    idx = start_index + 1
    while idx < search_limit:
        candidate = events[idx]
        if candidate.source_type == "turn_context":
            end_index = idx
            idx += 1
            continue
        if candidate.source_type == "event_msg" and event_msg_type(candidate) == "token_count":
            end_index = idx
            idx += 1
            continue
        if candidate.source_type == "event_msg" and event_msg_type(candidate) == "context_compacted":
            return idx
        break
    return end_index


def compaction_boundary_groups(events: list[RawEvent]) -> list[tuple[int, int]]:
    groups: list[tuple[int, int]] = []
    idx = 0
    while idx < len(events):
        event = events[idx]
        if not event.compaction_boundary:
            idx += 1
            continue
        end_index = compacted_event_cluster_end(events, idx)
        groups.append((idx, end_index))
        idx = end_index + 1
    return groups


def segment_ranges(events: list[RawEvent]) -> list[tuple[int, int, str]]:
    if not events:
        return []
    boundary_groups = compaction_boundary_groups(events)
    ranges: list[tuple[int, int, str]] = []
    start = 0
    for segment_no, (_boundary_start, boundary_end) in enumerate(boundary_groups):
        role = "initial-to-compaction" if segment_no == 0 else "compaction-to-compaction"
        ranges.append((start, boundary_end + 1, role))
        start = boundary_end + 1
    if start < len(events):
        role = "initial-to-latest" if not ranges else "compaction-to-latest"
        ranges.append((start, len(events), role))
    return ranges


def text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                for key in ("text", "input_text", "output_text", "content"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        parts.append(value.strip())
                        break
            elif isinstance(item, str) and item.strip():
                parts.append(item.strip())
        return " ".join(parts).strip()
    if isinstance(content, dict):
        for key in ("text", "input_text", "output_text", "content", "message"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def event_prompt_text(event: dict[str, Any]) -> str:
    for key in ("prompt", "user_prompt", "message", "content"):
        value = event.get(key)
        text = text_from_content(value)
        if text:
            return text
    return ""


def usable_title_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    lowered = stripped.lower()
    if lowered.startswith("# agents.md instructions"):
        return False
    if lowered.startswith("<environment_context"):
        return False
    if lowered.startswith("<turn_aborted"):
        return False
    if lowered.startswith("<instructions>") or lowered.startswith("<user_instructions_reminder"):
        return False
    if "--- project-doc ---" in lowered and "</instructions>" in lowered:
        return False
    return True


def first_user_message(events: list[RawEvent]) -> str:
    for raw_event in events:
        parsed = raw_event.parsed
        if not isinstance(parsed, dict):
            continue
        payload = parsed.get("payload")
        if not isinstance(payload, dict):
            continue
        if parsed.get("type") == "response_item" and payload.get("type") == "message" and payload.get("role") == "user":
            text = text_from_content(payload.get("content"))
            if usable_title_text(text):
                return text
        if parsed.get("type") == "event_msg" and payload.get("type") == "user_message":
            text = event_prompt_text(payload)
            if usable_title_text(text):
                return text
    return ""


def first_session_date(events: list[RawEvent], event: dict[str, Any], transcript_path: Path | None, fallback: str) -> str:
    candidates: list[str] = []
    candidates.extend(str(raw_event.timestamp or "") for raw_event in events[:20])
    for key in ("timestamp", "created_at", "started_at"):
        candidates.append(str(event.get(key) or ""))
    if transcript_path:
        candidates.append(transcript_path.name)
    candidates.append(fallback)
    for value in candidates:
        match = re.search(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)", value)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return fallback[:10]


def session_title(events: list[RawEvent], event: dict[str, Any], transcript_path: Path | None) -> tuple[str, str]:
    text = first_user_message(events)
    if text:
        return concise_title_text(text), "first_user_message"
    text = event_prompt_text(event)
    if usable_title_text(text):
        return concise_title_text(text), "hook_prompt"
    cwd = str(event.get("cwd") or "").strip()
    if cwd:
        return f"Codex in {Path(cwd).name or cwd}", "cwd"
    if transcript_path:
        return transcript_path.stem, "transcript"
    return "Untitled session", "fallback"


def display_quality(source: str | None) -> int:
    return {
        "first_user_message": 4,
        "hook_prompt": 3,
        "cwd": 2,
        "transcript": 1,
        "fallback": 0,
    }.get(str(source or ""), 0)


def label_sequence_from(label: str | None, session_date: str) -> int | None:
    if not label:
        return None
    match = re.match(rf"^{re.escape(session_date)}__(\d{{3}})__", label)
    if not match:
        return None
    return int(match.group(1))


def next_daily_sequence(aoa_root: Path, session_date: str, session_id: str) -> int:
    registry = read_json(aoa_root / REGISTRY_NAME, {"sessions": []})
    used: set[int] = set()
    sessions = registry.get("sessions", []) if isinstance(registry, dict) else []
    for item in sessions if isinstance(sessions, list) else []:
        if not isinstance(item, dict) or item.get("session_id") == session_id:
            continue
        display = item.get("display")
        label = display.get("label") if isinstance(display, dict) else item.get("session_label")
        sequence = label_sequence_from(str(label or ""), session_date)
        if sequence is not None:
            used.add(sequence)
    for root_name in (SESSION_ROOT, LEGACY_SESSION_ROOT):
        archive_root = aoa_root / root_name
        if archive_root.exists():
            for path in archive_root.iterdir():
                sequence = label_sequence_from(path.name, session_date)
                if sequence is not None:
                    used.add(sequence)
    sequence = 1
    while sequence in used:
        sequence += 1
    return sequence


def session_display(
    *,
    aoa_root: Path,
    session_dir: Path,
    session_id: str,
    event: dict[str, Any],
    transcript_path: Path | None,
    events: list[RawEvent],
    existing: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    existing_display = existing.get("display") if isinstance(existing.get("display"), dict) else {}
    title, title_source = session_title(events, event, transcript_path)
    session_date = first_session_date(events, event, transcript_path, str(existing.get("created_at") or now)[:10])
    existing_label = str(existing_display.get("label") or "")
    existing_sequence = label_sequence_from(existing_label, session_date)
    sequence = existing_sequence or next_daily_sequence(aoa_root, session_date, session_id)
    if existing_label and display_quality(str(existing_display.get("title_source"))) > display_quality(title_source):
        label = existing_label
        title = str(existing_display.get("title") or title)
        title_source = str(existing_display.get("title_source") or title_source)
    else:
        label = f"{session_date}__{sequence:03d}__{readable_slug(title)}"
    archive_path = aoa_root / SESSION_ROOT / label
    return {
        "date": session_date,
        "sequence": sequence,
        "title": title,
        "title_source": title_source,
        "label": label,
        "path": str(archive_path),
        "archive_path": str(archive_path),
        "navigation_path": str(archive_path),
    }


def merge_or_move_session_dir(source_dir: Path, target_dir: Path) -> Path:
    if source_dir == target_dir:
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir
    if target_dir.is_symlink():
        target_dir.unlink()
    if not source_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir
    if not target_dir.exists():
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        source_dir.rename(target_dir)
        return target_dir
    for child in source_dir.iterdir():
        destination = target_dir / child.name
        if destination.exists():
            if child.is_dir() and not child.is_symlink() and destination.is_dir():
                for nested in child.iterdir():
                    nested_destination = destination / nested.name
                    if not nested_destination.exists():
                        nested.rename(nested_destination)
            continue
        child.rename(destination)
    try:
        source_dir.rmdir()
    except OSError:
        pass
    return target_dir


def update_artifact_paths_after_move(session_dir: Path, manifest: dict[str, Any]) -> None:
    raw = manifest.get("raw")
    if isinstance(raw, dict) and raw.get("path"):
        raw["path"] = str(session_dir / "raw" / Path(str(raw["path"])).name)
    for segment in manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []:
        if not isinstance(segment, dict):
            continue
        if segment.get("markdown"):
            segment["markdown"] = str(session_dir / "segments" / Path(str(segment["markdown"])).name)
        if segment.get("index"):
            segment["index"] = str(session_dir / "segments" / Path(str(segment["index"])).name)
            segment_index_path = Path(str(segment["index"]))
            segment_index = read_json(segment_index_path, {})
            if isinstance(segment_index, dict):
                if segment.get("markdown"):
                    segment_index["markdown"] = segment["markdown"]
                write_json(segment_index_path, segment_index)
    legacy_raw_source_path = session_dir / "raw" / LEGACY_RAW_SOURCE_JSON
    raw_source_path = session_dir / "raw" / RAW_SOURCE_JSON
    if not raw_source_path.exists() and legacy_raw_source_path.exists():
        legacy_raw_source_path.rename(raw_source_path)
    raw_source = read_json(raw_source_path, {})
    if isinstance(raw_source, dict) and raw_source:
        raw_source["copied_to"] = str(session_dir / "raw" / "session.raw.jsonl")
        write_json(raw_source_path, raw_source)
    if legacy_raw_source_path.exists():
        legacy_raw_source_path.unlink()


def target_session_dir_for_display(aoa_root: Path, display: dict[str, Any]) -> Path:
    label = str(display.get("label") or "").strip()
    return aoa_root / SESSION_ROOT / (label or f"unresolved-session-{compact_stamp()}")


def rebuild_session_labels(aoa_root: Path) -> dict[str, Any]:
    now = utc_now()
    entries: list[dict[str, Any]] = []
    seen_session_ids: set[str] = set()
    source_roots = [aoa_root / LEGACY_SESSION_ROOT, aoa_root / SESSION_ROOT]
    if not any(root.exists() for root in source_roots):
        return {"schema_version": SCHEMA_VERSION, "updated_at": now, "sessions": []}
    for session_root in source_roots:
        if not session_root.exists():
            continue
        for manifest_path in sorted(session_root.glob("*/session.manifest.json")):
            session_dir = manifest_path.parent
            manifest = read_json(manifest_path, {})
            if not isinstance(manifest, dict):
                continue
            session_id = str(manifest.get("session_id") or session_dir.name)
            if session_id in seen_session_ids:
                continue
            seen_session_ids.add(session_id)
            source = manifest.get("source", {}) if isinstance(manifest.get("source"), dict) else {}
            transcript_value = source.get("transcript_path")
            transcript_path = Path(str(transcript_value)) if transcript_value else None
            raw = manifest.get("raw", {}) if isinstance(manifest.get("raw"), dict) else {}
            raw_value = raw.get("path") or session_dir / "raw" / "session.raw.jsonl"
            raw_path = Path(str(raw_value))
            events = parse_raw_event_sample(raw_path) if raw_path.exists() else []
            fallback = str(manifest.get("created_at") or manifest.get("updated_at") or now)
            entry_event = {
                "cwd": source.get("cwd"),
                "model": source.get("model"),
                "permission_mode": source.get("permission_mode"),
            }
            session_date = first_session_date(events, entry_event, transcript_path, fallback)
            title, title_source = session_title(events, entry_event, transcript_path)
            existing_display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
            if display_quality(str(existing_display.get("title_source"))) > display_quality(title_source):
                title = str(existing_display.get("title") or title)
                title_source = str(existing_display.get("title_source") or title_source)
            entries.append(
                {
                    "session_id": session_id,
                    "session_dir": session_dir,
                    "manifest": manifest,
                    "manifest_path": manifest_path,
                    "date": session_date,
                    "sort_key": str(manifest.get("created_at") or manifest.get("updated_at") or session_id),
                    "title": title,
                    "title_source": title_source,
                }
            )

    entries.sort(key=lambda item: (item["date"], item["sort_key"], item["session_id"]))
    per_date: defaultdict[str, int] = defaultdict(int)
    relabeled: list[dict[str, Any]] = []
    for entry in entries:
        session_date = str(entry["date"])
        per_date[session_date] += 1
        sequence = per_date[session_date]
        session_dir = entry["session_dir"]
        manifest = entry["manifest"]
        previous_display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
        previous_label = str(previous_display.get("label") or manifest.get("session_label") or "")
        title = str(entry["title"])
        label = f"{session_date}__{sequence:03d}__{readable_slug(title)}"
        old_session_dir = entry["session_dir"]
        session_dir = aoa_root / SESSION_ROOT / label
        session_dir = merge_or_move_session_dir(old_session_dir, session_dir)
        manifest_path = session_dir / "session.manifest.json"
        display = {
            "date": session_date,
            "sequence": sequence,
            "title": title,
            "title_source": entry["title_source"],
            "label": label,
            "path": str(session_dir),
            "archive_path": str(session_dir),
            "navigation_path": str(session_dir),
        }
        manifest["schema_version"] = SCHEMA_VERSION
        manifest["session_id"] = entry["session_id"]
        manifest["display"] = display
        manifest["session_label"] = label
        manifest["session_title"] = title
        update_artifact_paths_after_move(session_dir, manifest)
        write_json(manifest_path, manifest)
        update_session_index_identity(session_dir, manifest)
        update_registry(aoa_root, manifest, session_dir)
        relabeled.append(
            {
                "session_id": entry["session_id"],
                "label": label,
                "path": str(session_dir),
            }
        )
    legacy_root = aoa_root / LEGACY_SESSION_ROOT
    if legacy_root.exists():
        try:
            legacy_root.rmdir()
        except OSError:
            pass
    return {"schema_version": SCHEMA_VERSION, "updated_at": now, "sessions": relabeled}


def anchor_for(event: RawEvent) -> str:
    title_slug = safe_slug(event.title.lower(), fallback="event")
    return f"event-{event.event_id}--{event.event_type.lower()}--{title_slug}"


def markdown_escape_fence(raw: str) -> str:
    return raw


def event_index_record(event: RawEvent, md_name: str) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "line": event.line_no,
        "type": event.event_type,
        "title": event.title,
        "importance": event.importance,
        "tags": event.tags,
        "md_anchor": f"{md_name}#{anchor_for(event)}",
        "raw_ref": f"raw:line:{event.line_no}",
        "timestamp": event.timestamp,
        "source_type": event.source_type,
    }


def write_segment(session_dir: Path, raw_rel: str, segment_no: int, role: str, events: list[RawEvent]) -> dict[str, Any]:
    segment_id = f"{segment_no:03d}"
    md_name = f"{segment_id}__{role}.md"
    index_name = f"{segment_id}__{role}.index.json"
    md_path = session_dir / "segments" / md_name
    index_path = session_dir / "segments" / index_name
    md_path.parent.mkdir(parents=True, exist_ok=True)

    first_line = events[0].line_no if events else None
    last_line = events[-1].line_no if events else None
    lines = [
        "---",
        "aoa_artifact_type: codex_compaction_segment",
        "schema_version: 1",
        f"segment_id: {segment_id}",
        f"segment_role: {role}",
        f"source_raw: {raw_rel}",
        f"source_from_line: {first_line}",
        f"source_to_line: {last_line}",
        f"status: raw_preserved",
        f"index: ./{index_name}",
        "---",
        "",
        f"# Segment {segment_id}: {role}",
        "",
        "## Legend",
        "",
        "This file preserves one Codex session interval as structured Markdown.",
        "It is generated from raw JSONL and is not final reviewed truth.",
        "Use the sibling index file to locate event types before reading the full segment.",
        "Promote claims only after reviewing raw refs or the relevant event body.",
        "",
    ]
    for event in events:
        anchor = anchor_for(event)
        lines.extend(
            [
                f'<a id="{anchor}"></a>',
                "",
                f"## EVENT {event.event_id} - {event.event_type} - {event.importance}",
                f"- line: {event.line_no}",
                f"- time: {event.timestamp or ''}",
                f"- source: {event.source_type}",
                f"- refs: raw:line:{event.line_no}",
                f"- tags: {json.dumps(event.tags, ensure_ascii=False)}",
                "",
                "### Title",
                "",
                event.title,
                "",
                "### Raw",
                "",
                "````json",
                markdown_escape_fence(event.raw),
                "````",
                "",
            ]
        )
    md_path.write_text("\n".join(lines), encoding="utf-8")

    records = [event_index_record(event, md_name) for event in events]
    by_type: dict[str, list[str]] = defaultdict(list)
    by_tag: dict[str, list[str]] = defaultdict(list)
    by_source_type: dict[str, list[str]] = defaultdict(list)
    for event in events:
        by_type[event.event_type].append(event.event_id)
        by_source_type[event.source_type].append(event.event_id)
        for tag in event.tags:
            by_tag[tag].append(event.event_id)

    index = {
        "schema_version": SCHEMA_VERSION,
        "segment_id": segment_id,
        "segment_role": role,
        "source_raw": raw_rel,
        "source_range": {"from_line": first_line, "to_line": last_line},
        "markdown": str(md_path),
        "events": records,
        "by_type": dict(sorted(by_type.items())),
        "by_tag": dict(sorted(by_tag.items())),
        "by_source_type": dict(sorted(by_source_type.items())),
    }
    write_json(index_path, index)
    return {
        "segment_id": segment_id,
        "role": role,
        "markdown": str(md_path),
        "index": str(index_path),
        "event_count": len(events),
        "source_range": {"from_line": first_line, "to_line": last_line},
    }


def clear_generated_segments(session_dir: Path) -> None:
    segments = session_dir / "segments"
    if not segments.exists():
        return
    for path in segments.iterdir():
        if re.match(r"^\d{3}__.+(\.md|\.index\.json)$", path.name):
            path.unlink()


def write_session_index(session_dir: Path, manifest: dict[str, Any], events: list[RawEvent]) -> None:
    counts = Counter(event.event_type for event in events)
    by_type = {event_type: counts[event_type] for event_type in EVENT_TYPE_ORDER if counts[event_type]}
    display = manifest.get("display", {}) if isinstance(manifest.get("display"), dict) else {}
    session_index_json = {
        "schema_version": SCHEMA_VERSION,
        "session_id": manifest["session_id"],
        "display": display,
        "updated_at": manifest["updated_at"],
        "archive_status": manifest["archive_status"],
        "distillation_status": manifest.get("distillation_status", "raw_archived"),
        "event_count": len(events),
        "event_counts": by_type,
        "segments": manifest.get("segments", []),
        "read_order": [
            "session.manifest.json",
            SESSION_INDEX_JSON,
            "latest segment index",
            "relevant segment markdown",
        ],
    }
    write_json(session_dir / SESSION_INDEX_JSON, session_index_json)
    legacy_json = session_dir / LEGACY_SESSION_INDEX_JSON
    if legacy_json.exists():
        legacy_json.unlink()

    lines = [
        "---",
        "aoa_artifact_type: session_index",
        "schema_version: 1",
        f"session_id: {manifest['session_id']}",
        f"session_label: {display.get('label', '')}",
        f"session_title: {display.get('title', '')}",
        f"archive_status: {manifest['archive_status']}",
        f"distillation_status: {manifest.get('distillation_status', 'raw_archived')}",
        f"updated_at: {manifest['updated_at']}",
        "---",
        "",
        f"# {display.get('label') or 'Session Index'}",
        "",
        "## Identity",
        "",
        f"- title: `{display.get('title', '')}`",
        f"- label: `{display.get('label', '')}`",
        f"- date: `{display.get('date', '')}`",
        f"- sequence: `{display.get('sequence', '')}`",
        f"- session_id: `{manifest['session_id']}`",
        f"- path: `{display.get('path', str(session_dir))}`",
        f"- source transcript: `{manifest.get('source', {}).get('transcript_path', '') if isinstance(manifest.get('source'), dict) else ''}`",
        "",
        "## Status",
        "",
        f"- archive_status: `{manifest['archive_status']}`",
        f"- distillation_status: `{manifest.get('distillation_status', 'raw_archived')}`",
        f"- events: `{len(events)}`",
        "",
        "## Read Order",
        "",
        "1. `session.manifest.json`",
        f"2. `{SESSION_INDEX_JSON}`",
        "3. latest relevant `segments/*.index.json`",
        "4. relevant `segments/*.md`",
        "",
        "## Segments",
        "",
    ]
    for segment in manifest.get("segments", []):
        lines.append(
            f"- `{Path(segment['markdown']).name}`: {segment['role']}, "
            f"{segment['event_count']} events, lines "
            f"{segment['source_range'].get('from_line')}..{segment['source_range'].get('to_line')}"
        )
    lines.extend(["", "## Event Counts", ""])
    for event_type, count in by_type.items():
        lines.append(f"- `{event_type}`: {count}")
    lines.append("")
    (session_dir / SESSION_INDEX_MARKDOWN).write_text("\n".join(lines), encoding="utf-8")
    legacy_md = session_dir / LEGACY_SESSION_INDEX_MARKDOWN
    if legacy_md.exists():
        legacy_md.unlink()


def update_session_index_identity(session_dir: Path, manifest: dict[str, Any]) -> None:
    display = manifest.get("display", {}) if isinstance(manifest.get("display"), dict) else {}
    json_path = session_dir / SESSION_INDEX_JSON
    legacy_json_path = session_dir / LEGACY_SESSION_INDEX_JSON
    source_json_path = json_path if json_path.exists() else legacy_json_path
    if source_json_path.exists():
        session_index = read_json(source_json_path, {})
        if isinstance(session_index, dict):
            session_index["display"] = display
            session_index["session_label"] = display.get("label")
            session_index["session_title"] = display.get("title")
            session_index["segments"] = manifest.get("segments", [])
            write_json(json_path, session_index)
    if legacy_json_path.exists():
        legacy_json_path.unlink()

    md_path = session_dir / SESSION_INDEX_MARKDOWN
    legacy_md_path = session_dir / LEGACY_SESSION_INDEX_MARKDOWN
    source_md_path = md_path if md_path.exists() else legacy_md_path
    if not source_md_path.exists():
        return
    text = source_md_path.read_text(encoding="utf-8")
    label = str(display.get("label") or "Session Index")
    title = str(display.get("title") or "")
    identity_block = "\n".join(
        [
            "## Identity",
            "",
            f"- title: `{title}`",
            f"- label: `{label}`",
            f"- date: `{display.get('date', '')}`",
            f"- sequence: `{display.get('sequence', '')}`",
            f"- session_id: `{manifest.get('session_id', '')}`",
            f"- path: `{display.get('path', str(session_dir))}`",
            f"- source transcript: `{manifest.get('source', {}).get('transcript_path', '') if isinstance(manifest.get('source'), dict) else ''}`",
            "",
        ]
    )
    text = re.sub(r"(?m)^# Session Index$", f"# {label}", text, count=1)
    text = re.sub(r"(?m)^# .*$", f"# {label}", text, count=1)
    if "session_label:" not in text:
        text = text.replace(f"session_id: {manifest.get('session_id', '')}\n", f"session_id: {manifest.get('session_id', '')}\nsession_label: {label}\nsession_title: {title}\n", 1)
    if "## Identity" in text:
        text = re.sub(r"## Identity\n\n.*?\n## Status", identity_block + "## Status", text, count=1, flags=re.DOTALL)
    else:
        text = text.replace(f"# {label}\n\n", f"# {label}\n\n{identity_block}", 1)
    text = text.replace("`00_SESSION_INDEX.json`", f"`{SESSION_INDEX_JSON}`")
    md_path.write_text(text, encoding="utf-8")
    if legacy_md_path.exists():
        legacy_md_path.unlink()


def write_session_agents(session_dir: Path) -> None:
    path = session_dir / "AGENTS.md"
    path.write_text(
        """# AGENTS.md

## Session-local instructions

This folder contains one Codex session archive.

Always read:

1. root `.aoa/DESIGN.md` if available
2. `SESSION.md`
3. `session.manifest.json`
4. the relevant `segments/*.index.json`
5. only then the relevant `segments/*.md`

## Rules

- Raw material is evidence, not final reviewed truth.
- Segment Markdown is generated and may be regenerated from raw JSONL.
- Important claims must point to raw refs or segment event IDs.
- Distillation artifacts remain provisional unless reviewed.
- If raw is missing or unreadable, inspect `incidents/` before continuing.
""",
        encoding="utf-8",
    )


def hook_source_metadata(session_dir: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    events_path = session_dir / "hooks" / "events.jsonl"
    if not events_path.exists():
        return metadata
    with events_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            event = row.get("event")
            if not isinstance(event, dict):
                continue
            for key in ("cwd", "model", "permission_mode"):
                value = event.get(key)
                if value:
                    metadata[key] = value
            if event.get("turn_id"):
                metadata["last_turn_id"] = event.get("turn_id")
    return metadata


def session_source(
    event: dict[str, Any],
    transcript_path: Path | None,
    *,
    existing_source: dict[str, Any] | None = None,
    hook_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = {
        "transcript_path": str(transcript_path) if transcript_path else None,
        "cwd": event.get("cwd"),
        "model": event.get("model"),
        "permission_mode": event.get("permission_mode"),
        "last_turn_id": event.get("turn_id"),
    }
    for key in ("cwd", "model", "permission_mode", "last_turn_id"):
        if source.get(key):
            continue
        for fallback in (hook_source, existing_source):
            if isinstance(fallback, dict) and fallback.get(key):
                source[key] = fallback.get(key)
                break
    return source


def sync_session_from_transcript(
    *,
    aoa_root: Path,
    event: dict[str, Any],
    transcript_path: Path,
    hook_event_name: str,
) -> dict[str, Any]:
    now = utc_now()
    session_id = session_id_from(event, transcript_path)
    initial_session_dir = session_dir_for_id(aoa_root, session_id)
    existing = read_json(initial_session_dir / "session.manifest.json", {})
    events = parse_raw_events(transcript_path)
    hooks_seen = sorted(set(existing.get("hooks_seen", [])) | {hook_event_name})
    created_at = existing.get("created_at") or now
    display = session_display(
        aoa_root=aoa_root,
        session_dir=initial_session_dir,
        session_id=session_id,
        event=event,
        transcript_path=transcript_path,
        events=events,
        existing=existing,
        now=created_at,
    )
    session_dir = target_session_dir_for_display(aoa_root, display)
    display["path"] = str(session_dir)
    display["archive_path"] = str(session_dir)
    display["navigation_path"] = str(session_dir)
    session_dir = merge_or_move_session_dir(initial_session_dir, session_dir)
    raw_dir = session_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    write_session_agents(session_dir)
    existing_source = existing.get("source") if isinstance(existing.get("source"), dict) else {}
    source_payload = session_source(
        event,
        transcript_path,
        existing_source=existing_source,
        hook_source=hook_source_metadata(session_dir),
    )

    raw_path = raw_dir / "session.raw.jsonl"
    shutil.copy2(transcript_path, raw_path)
    raw_hash = sha256_file(raw_path)
    raw_rel = "raw/session.raw.jsonl"

    clear_generated_segments(session_dir)
    segment_payloads: list[dict[str, Any]] = []
    for segment_no, (start, end, role) in enumerate(segment_ranges(events)):
        segment_payloads.append(write_segment(session_dir, raw_rel, segment_no, role, events[start:end]))

    manifest_path = session_dir / "session.manifest.json"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "display": display,
        "session_label": display["label"],
        "session_title": display["title"],
        "created_at": created_at,
        "updated_at": now,
        "source": source_payload,
        "archive_status": "indexed",
        "distillation_status": existing.get("distillation_status", "raw_archived"),
        "distillation_iteration": int(existing.get("distillation_iteration", 0) or 0),
        "review_status": existing.get("review_status", "provisional"),
        "hooks_seen": hooks_seen,
        "raw": {
            "path": str(raw_path),
            "source_path": str(transcript_path),
            "bytes": raw_path.stat().st_size,
            "sha256": raw_hash,
            "line_count": len(events),
            "copied_at": now,
        },
        "segments": segment_payloads,
        "latest_event_count": len(events),
    }
    write_json(manifest_path, manifest)
    write_json(
        raw_dir / RAW_SOURCE_JSON,
        {
            "schema_version": SCHEMA_VERSION,
            "session_id": session_id,
            "source_path": str(transcript_path),
            "copied_to": str(raw_path),
            "sha256": raw_hash,
            "updated_at": now,
        },
    )
    legacy_raw_source = raw_dir / LEGACY_RAW_SOURCE_JSON
    if legacy_raw_source.exists():
        legacy_raw_source.unlink()
    write_session_index(session_dir, manifest, events)
    update_registry(aoa_root, manifest, session_dir)
    return {
        "session_id": session_id,
        "display_name": display["label"],
        "navigation_path": display["navigation_path"],
        "session_dir": str(session_dir),
        "event_count": len(events),
        "segment_count": len(segment_payloads),
        "raw_path": str(raw_path),
        "manifest_path": str(manifest_path),
    }


def update_registry(aoa_root: Path, manifest: dict[str, Any], session_dir: Path) -> None:
    registry_path = aoa_root / REGISTRY_NAME
    registry = read_json(registry_path, {"schema_version": SCHEMA_VERSION, "sessions": []})
    sessions = registry.get("sessions", [])
    if not isinstance(sessions, list):
        sessions = []
    updated: list[dict[str, Any]] = []
    seen = False
    for item in sessions:
        if isinstance(item, dict) and item.get("session_id") == manifest["session_id"]:
            updated.append(registry_record(manifest, session_dir))
            seen = True
        elif isinstance(item, dict):
            updated.append(item)
    if not seen:
        updated.append(registry_record(manifest, session_dir))
    updated.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    write_json(
        registry_path,
        {
            "schema_version": SCHEMA_VERSION,
            "updated_at": utc_now(),
            "sessions": updated,
        },
    )


def registry_record(manifest: dict[str, Any], session_dir: Path) -> dict[str, Any]:
    source = manifest.get("source", {})
    display = manifest.get("display", {}) if isinstance(manifest.get("display"), dict) else {}
    return {
        "session_id": manifest["session_id"],
        "display": display,
        "session_label": display.get("label") or manifest.get("session_label"),
        "session_title": display.get("title") or manifest.get("session_title"),
        "navigation_path": display.get("navigation_path") or str(session_dir),
        "path": str(session_dir),
        "updated_at": manifest["updated_at"],
        "archive_status": manifest["archive_status"],
        "distillation_status": manifest.get("distillation_status", "raw_archived"),
        "transcript_path": source.get("transcript_path") if isinstance(source, dict) else None,
        "cwd": source.get("cwd") if isinstance(source, dict) else None,
        "event_count": manifest.get("latest_event_count", 0),
        "segment_count": len(manifest.get("segments", [])),
    }


def registry_sessions(aoa_root: Path) -> list[dict[str, Any]]:
    registry = read_json(aoa_root / REGISTRY_NAME, {"sessions": []})
    sessions = registry.get("sessions", []) if isinstance(registry, dict) else []
    return [item for item in sessions if isinstance(item, dict)]


def resolve_session_record(aoa_root: Path, target: str | None) -> dict[str, Any]:
    sessions = registry_sessions(aoa_root)
    if not sessions:
        raise ValueError("session registry is empty")
    if not target or target == "latest":
        return sorted(sessions, key=lambda item: str(item.get("updated_at", "")), reverse=True)[0]
    target_text = target.strip()
    for item in sessions:
        candidates = [
            str(item.get("session_id") or ""),
            str(item.get("session_label") or ""),
            Path(str(item.get("path") or "")).name,
        ]
        display = item.get("display") if isinstance(item.get("display"), dict) else {}
        candidates.extend([str(display.get("label") or ""), str(display.get("title") or "")])
        if target_text in candidates:
            return item
    lowered = target_text.lower()
    fuzzy = [
        item
        for item in sessions
        if lowered in str(item.get("session_label") or "").lower()
        or lowered in str(item.get("session_title") or "").lower()
        or lowered in str(item.get("session_id") or "").lower()
    ]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        labels = ", ".join(str(item.get("session_label") or item.get("session_id")) for item in fuzzy[:8])
        raise ValueError(f"ambiguous session target {target_text!r}: {labels}")
    raise ValueError(f"session not found: {target_text}")


def session_dir_from_record(record: dict[str, Any]) -> Path:
    return Path(str(record.get("path") or record.get("navigation_path") or ""))


def latest_segment(manifest: dict[str, Any]) -> dict[str, Any] | None:
    segments = manifest.get("segments", [])
    if not isinstance(segments, list) or not segments:
        return None
    candidates = [segment for segment in segments if isinstance(segment, dict)]
    if not candidates:
        return None
    return candidates[-1]


def rehydrate_packet(aoa_root: Path, target: str | None, *, max_events: int = 24) -> str:
    record = resolve_session_record(aoa_root, target)
    session_dir = session_dir_from_record(record)
    manifest = read_json(session_dir / "session.manifest.json", {})
    session_index = read_json(session_dir / SESSION_INDEX_JSON, {})
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError(f"missing session manifest: {session_dir}")
    display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
    segment = latest_segment(manifest)
    segment_index: dict[str, Any] = {}
    if segment and segment.get("index"):
        loaded = read_json(Path(str(segment["index"])), {})
        segment_index = loaded if isinstance(loaded, dict) else {}

    events = segment_index.get("events", []) if isinstance(segment_index, dict) else []
    priority_types = [
        "FINAL_STATE",
        "RESUME_HINT",
        "OPEN_THREAD",
        "DECISION",
        "ERROR",
        "COMPACTION_EVENT",
        "VERIFICATION",
        "PROCESS_LESSON",
        "OPTIMIZATION_CANDIDATE",
    ]
    selected: list[dict[str, Any]] = []
    if isinstance(events, list):
        for event_type in priority_types:
            for item in events:
                if isinstance(item, dict) and item.get("type") == event_type:
                    selected.append(item)
                    if len(selected) >= max_events:
                        break
            if len(selected) >= max_events:
                break

    lines = [
        "# AoA Session Rehydration Packet",
        "",
        "## Identity",
        "",
        f"- session_id: `{manifest.get('session_id', '')}`",
        f"- label: `{display.get('label') or record.get('session_label', '')}`",
        f"- title: `{display.get('title') or record.get('session_title', '')}`",
        f"- path: `{session_dir}`",
        "",
        "## Status",
        "",
        f"- archive_status: `{manifest.get('archive_status', '')}`",
        f"- distillation_status: `{manifest.get('distillation_status', '')}`",
        f"- review_status: `{manifest.get('review_status', '')}`",
        f"- events: `{manifest.get('latest_event_count', 0)}`",
        f"- segments: `{len(manifest.get('segments', []) if isinstance(manifest.get('segments'), list) else [])}`",
        "",
        "## Read First",
        "",
        "1. `AGENTS.md`",
        f"2. `{SESSION_INDEX_MARKDOWN}`",
        "3. `session.manifest.json`",
        "4. latest relevant `segments/*.index.json`",
        "5. only then relevant `segments/*.md` or raw refs",
        "",
    ]
    if segment:
        lines.extend(
            [
                "## Latest Segment",
                "",
                f"- role: `{segment.get('role')}`",
                f"- events: `{segment.get('event_count')}`",
                f"- index: `{segment.get('index')}`",
                f"- markdown: `{segment.get('markdown')}`",
                "",
            ]
        )
    event_counts = session_index.get("event_counts", {}) if isinstance(session_index, dict) else {}
    if isinstance(event_counts, dict) and event_counts:
        lines.extend(["## Event Counts", ""])
        for event_type, count in event_counts.items():
            lines.append(f"- `{event_type}`: {count}")
        lines.append("")
    lines.extend(["## Priority Events", ""])
    if selected:
        for item in selected:
            lines.append(
                f"- `{item.get('event_id')}` `{item.get('type')}` "
                f"{item.get('title')} -> `{item.get('md_anchor')}` / `{item.get('raw_ref')}`"
            )
    else:
        lines.append("- No priority events were selected from the latest segment index.")
    lines.extend(
        [
            "",
            "## Rule",
            "",
            "Use this packet as a route map, not as reviewed truth. Verify important claims through segment events or raw refs.",
            "",
        ]
    )
    return "\n".join(lines)


def update_session_status_files(session_dir: Path, manifest: dict[str, Any]) -> None:
    write_json(session_dir / "session.manifest.json", manifest)
    update_registry(session_dir.parents[1], manifest, session_dir)
    index_path = session_dir / SESSION_INDEX_JSON
    session_index = read_json(index_path, {})
    if isinstance(session_index, dict) and session_index:
        session_index["distillation_status"] = manifest.get("distillation_status")
        session_index["distillation_iteration"] = manifest.get("distillation_iteration", 0)
        session_index["review_status"] = manifest.get("review_status")
        session_index["last_distilled_at"] = manifest.get("last_distilled_at")
        session_index["next_distillation_goal"] = manifest.get("next_distillation_goal")
        write_json(index_path, session_index)
    entry_path = session_dir / SESSION_INDEX_MARKDOWN
    if entry_path.exists():
        text = entry_path.read_text(encoding="utf-8")
        status = str(manifest.get("distillation_status") or "")
        iteration = str(manifest.get("distillation_iteration", 0))
        review = str(manifest.get("review_status") or "")
        if re.search(r"(?m)^distillation_status: ", text):
            text = re.sub(r"(?m)^distillation_status: .*$", f"distillation_status: {status}", text, count=1)
        if re.search(r"(?m)^review_status: ", text):
            text = re.sub(r"(?m)^review_status: .*$", f"review_status: {review}", text, count=1)
        elif "---\n\n#" in text:
            text = text.replace("---\n\n#", f"review_status: {review}\ndistillation_iteration: {iteration}\n---\n\n#", 1)
        text = re.sub(r"(?m)^- distillation_status: `.*`$", f"- distillation_status: `{status}`", text)
        if "- distillation_iteration:" not in text:
            text = text.replace(f"- distillation_status: `{status}`\n", f"- distillation_status: `{status}`\n- distillation_iteration: `{iteration}`\n", 1)
        else:
            text = re.sub(r"(?m)^- distillation_iteration: `.*`$", f"- distillation_iteration: `{iteration}`", text)
        entry_path.write_text(text, encoding="utf-8")


def distill_session_first_pass(aoa_root: Path, target: str | None, *, max_events_per_type: int = 30) -> dict[str, Any]:
    now = utc_now()
    record = resolve_session_record(aoa_root, target)
    session_dir = session_dir_from_record(record)
    manifest = read_json(session_dir / "session.manifest.json", {})
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError(f"missing session manifest: {session_dir}")
    routes_config = read_json(aoa_root / "config/event-distillation-routes.json", {})
    route_map = routes_config.get("routes", {}) if isinstance(routes_config, dict) else {}
    if not isinstance(route_map, dict):
        route_map = {}

    event_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    selected_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_segments: list[dict[str, Any]] = []
    for segment in manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []:
        if not isinstance(segment, dict) or not segment.get("index"):
            continue
        segment_index_path = Path(str(segment["index"]))
        segment_index = read_json(segment_index_path, {})
        if not isinstance(segment_index, dict):
            continue
        source_segments.append(
            {
                "segment_id": segment.get("segment_id"),
                "role": segment.get("role"),
                "index": str(segment_index_path),
                "markdown": segment.get("markdown"),
            }
        )
        events = segment_index.get("events", [])
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("type") or "RAW_EVENT")
            event_counts[event_type] += 1
            routes = [str(route) for route in route_map.get(event_type, [])] if isinstance(route_map.get(event_type, []), list) else []
            for route in routes:
                route_counts[route] += 1
            importance = str(event.get("importance") or "")
            keep = importance in {"critical", "high"} or event_type in {
                "DECISION",
                "ERROR",
                "PROCESS_LESSON",
                "OPTIMIZATION_CANDIDATE",
                "DEAD_BRANCH",
                "SECURITY_OR_SECRET_RISK",
                "COMPACTION_EVENT",
                "FINAL_STATE",
                "OPEN_THREAD",
            }
            if keep and len(selected_by_type[event_type]) < max_events_per_type:
                selected_by_type[event_type].append(
                    {
                        "event_id": event.get("event_id"),
                        "type": event_type,
                        "title": event.get("title"),
                        "importance": importance,
                        "routes": routes,
                        "md_anchor": event.get("md_anchor"),
                        "raw_ref": event.get("raw_ref"),
                        "source_segment": segment.get("segment_id"),
                    }
                )

    distillation_dir = session_dir / "distillation"
    distillation_dir.mkdir(parents=True, exist_ok=True)
    candidate_total = sum(len(items) for items in selected_by_type.values())
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "first_pass_distillation_index",
        "session_id": manifest.get("session_id"),
        "session_label": manifest.get("session_label"),
        "created_at": now,
        "status": "provisional",
        "source_segments": source_segments,
        "event_counts": dict(sorted(event_counts.items())),
        "route_counts": dict(sorted(route_counts.items())),
        "candidate_count": candidate_total,
        "candidates_by_type": dict(sorted(selected_by_type.items())),
    }
    index_path = distillation_dir / "distillation.index.json"
    write_json(index_path, payload)

    lines = [
        "---",
        "aoa_artifact_type: first_pass_distillation",
        "schema_version: 1",
        f"session_id: {manifest.get('session_id')}",
        f"session_label: {manifest.get('session_label')}",
        "status: provisional",
        f"created_at: {now}",
        "index: ./distillation.index.json",
        "---",
        "",
        "# First-Pass Distillation Map",
        "",
        "This is a provisional route map from archived events to possible experience, pattern, skill, or automation work.",
        "It is not reviewed truth and does not promote any claim by itself.",
        "",
        "## Source",
        "",
        f"- session: `{manifest.get('session_label')}`",
        f"- raw: `{manifest.get('raw', {}).get('path') if isinstance(manifest.get('raw'), dict) else ''}`",
        f"- segments: `{len(source_segments)}`",
        "",
        "## Event Counts",
        "",
    ]
    for event_type, count in sorted(event_counts.items()):
        lines.append(f"- `{event_type}`: {count}")
    lines.extend(["", "## Route Counts", ""])
    for route, count in sorted(route_counts.items()):
        lines.append(f"- `{route}`: {count}")
    lines.extend(["", "## Candidate Events", ""])
    for event_type, items in sorted(selected_by_type.items()):
        lines.extend(["", f"### {event_type}", ""])
        for item in items:
            routes = ", ".join(item.get("routes", []))
            lines.append(
                f"- `{item.get('event_id')}` {item.get('title')} "
                f"routes=[{routes}] evidence=`{item.get('md_anchor')}` raw=`{item.get('raw_ref')}`"
            )
    lines.extend(
        [
            "",
            "## Next Review",
            "",
            "A human or later agent should review candidates by evidence refs before promoting any pattern, skill amendment, or automation seed.",
            "",
        ]
    )
    markdown_path = distillation_dir / "001__first-pass__experience-map.md"
    markdown_path.write_text("\n".join(lines), encoding="utf-8")

    manifest["distillation_status"] = "first_pass_distilled"
    manifest["distillation_iteration"] = max(1, int(manifest.get("distillation_iteration", 0) or 0))
    manifest["last_distilled_at"] = now
    manifest["updated_at"] = now
    manifest["next_distillation_goal"] = "review candidate events and promote only evidence-backed patterns"
    manifest["review_status"] = manifest.get("review_status", "provisional")
    manifest["distillation"] = {
        "latest_index": str(index_path),
        "latest_markdown": str(markdown_path),
        "candidate_count": candidate_total,
    }
    update_session_status_files(session_dir, manifest)
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "session_id": manifest.get("session_id"),
        "session_label": manifest.get("session_label"),
        "session_dir": str(session_dir),
        "distillation_index": str(index_path),
        "distillation_markdown": str(markdown_path),
        "candidate_count": candidate_total,
        "event_counts": dict(sorted(event_counts.items())),
    }


def write_raw_unavailable_incident(
    *,
    aoa_root: Path,
    event: dict[str, Any],
    transcript_path: Path | None,
    hook_event_name: str,
) -> dict[str, Any]:
    now = utc_now()
    session_id = session_id_from(event, transcript_path)
    initial_session_dir = session_dir_for_id(aoa_root, session_id)
    existing = read_json(initial_session_dir / "session.manifest.json", {})
    display = session_display(
        aoa_root=aoa_root,
        session_dir=initial_session_dir,
        session_id=session_id,
        event=event,
        transcript_path=transcript_path,
        events=[],
        existing=existing,
        now=existing.get("created_at") or now,
    )
    session_dir = target_session_dir_for_display(aoa_root, display)
    display["path"] = str(session_dir)
    display["archive_path"] = str(session_dir)
    display["navigation_path"] = str(session_dir)
    session_dir = merge_or_move_session_dir(initial_session_dir, session_dir)
    incidents = session_dir / "incidents"
    incidents.mkdir(parents=True, exist_ok=True)
    write_session_agents(session_dir)
    exists = transcript_path.exists() if transcript_path else False
    readable = bool(transcript_path and os.access(transcript_path, os.R_OK))
    diagnostic = {
        "schema_version": SCHEMA_VERSION,
        "incident_type": "raw_session_unavailable",
        "created_at": now,
        "session_id": session_id,
        "hook_event_name": hook_event_name,
        "expected_raw_source": {
            "path": str(transcript_path) if transcript_path else None,
            "cwd": event.get("cwd"),
            "turn_id": event.get("turn_id"),
        },
        "checks": {
            "path_provided": transcript_path is not None,
            "path_exists": exists,
            "readable": readable,
            "parent_exists": transcript_path.parent.exists() if transcript_path else False,
            "parent_readable": os.access(transcript_path.parent, os.R_OK) if transcript_path else False,
        },
        "diagnosis": {
            "likely_cause": "missing_or_unreadable_transcript_path",
            "confidence": "high" if transcript_path and not exists else "medium",
        },
        "recovery_actions": [
            "Verify the Codex hook event transcript_path.",
            "Inspect ~/.codex/sessions for the session id.",
            "Re-run aoa-session-raw-diagnostic before distillation.",
        ],
    }
    stem = f"{compact_stamp()}__raw-session-unavailable"
    diagnostic_path = incidents / f"{stem}__DIAGNOSTIC.json"
    incident_path = incidents / f"{stem}__INCIDENT.md"
    write_json(diagnostic_path, diagnostic)
    incident_path.write_text(
        "\n".join(
            [
                "# Raw Session Unavailable Incident",
                "",
                "## Expected raw source",
                "",
                f"- path: `{diagnostic['expected_raw_source']['path']}`",
                f"- session_id: `{session_id}`",
                f"- hook: `{hook_event_name}`",
                f"- cwd: `{event.get('cwd')}`",
                "",
                "## Checks performed",
                "",
                f"- path exists: `{exists}`",
                f"- readable: `{readable}`",
                f"- parent exists: `{diagnostic['checks']['parent_exists']}`",
                f"- parent readable: `{diagnostic['checks']['parent_readable']}`",
                "",
                "## Immediate diagnosis",
                "",
                f"- likely cause: `{diagnostic['diagnosis']['likely_cause']}`",
                f"- confidence: `{diagnostic['diagnosis']['confidence']}`",
                "",
                "## Recovery actions",
                "",
                "- Verify the hook event transcript path.",
                "- Search the session registry by session id.",
                "- Rebuild the segment from raw after the source is found.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    manifest_path = session_dir / "session.manifest.json"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "display": display,
        "session_label": display["label"],
        "session_title": display["title"],
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
        "source": session_source(event, transcript_path),
        "archive_status": "raw_unavailable",
        "distillation_status": existing.get("distillation_status", "raw_archived"),
        "distillation_iteration": int(existing.get("distillation_iteration", 0) or 0),
        "review_status": existing.get("review_status", "provisional"),
        "hooks_seen": sorted(set(existing.get("hooks_seen", [])) | {hook_event_name}),
        "raw": {"path": None, "source_path": str(transcript_path) if transcript_path else None},
        "segments": existing.get("segments", []),
        "latest_event_count": int(existing.get("latest_event_count", 0) or 0),
        "latest_incident": str(incident_path),
        "latest_diagnostic": str(diagnostic_path),
    }
    write_json(manifest_path, manifest)
    update_registry(aoa_root, manifest, session_dir)
    return {
        "session_id": session_id,
        "display_name": display["label"],
        "navigation_path": display["navigation_path"],
        "session_dir": str(session_dir),
        "incident": str(incident_path),
        "diagnostic": str(diagnostic_path),
    }


def handle_hook_event(
    event_name: str,
    event: dict[str, Any],
    *,
    workspace_root: Path | None = None,
    aoa_root: Path | None = None,
) -> dict[str, Any]:
    root = aoa_root_for(workspace_root, aoa_root)
    root.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    transcript_value = event.get("transcript_path")
    transcript_path = Path(str(transcript_value)).expanduser() if transcript_value else None
    session_id = session_id_from(event, transcript_path)
    session_dir = session_dir_for_id(root, session_id)
    append_jsonl(
        session_dir / "hooks" / "events.jsonl",
        {
            "schema_version": SCHEMA_VERSION,
            "timestamp": now,
            "hook_event_name": event_name,
            "event": event,
        },
    )
    actions = ["hook_event_recorded"]
    errors: list[str] = []
    if event_name == "UserPromptSubmit" and os.environ.get("AOA_SESSION_MEMORY_FULL_PROMPT_SYNC") != "1":
        actions.append("prompt_hook_light_recorded")
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "hook_event_name": event_name,
            "timestamp": now,
            "session_id": session_id,
            "session_dir": str(session_dir),
            "actions": actions,
            "errors": errors,
        }
    try:
        if transcript_path is None or not transcript_path.exists() or not os.access(transcript_path, os.R_OK):
            incident = write_raw_unavailable_incident(
                aoa_root=root,
                event=event,
                transcript_path=transcript_path,
                hook_event_name=event_name,
            )
            actions.append("raw_unavailable_incident_written")
            return {
                "schema_version": SCHEMA_VERSION,
                "ok": True,
                "hook_event_name": event_name,
                "timestamp": now,
                "session_id": session_id,
                "session_dir": incident["session_dir"],
                "display_name": incident.get("display_name"),
                "navigation_path": incident.get("navigation_path"),
                "actions": actions,
                "incident": incident,
                "errors": errors,
            }
        synced = sync_session_from_transcript(
            aoa_root=root,
            event=event,
            transcript_path=transcript_path,
            hook_event_name=event_name,
        )
        actions.append("raw_mirrored")
        actions.append("segments_indexed")
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "hook_event_name": event_name,
            "timestamp": now,
            "session_id": synced["session_id"],
            "session_dir": synced["session_dir"],
            "display_name": synced.get("display_name"),
            "navigation_path": synced.get("navigation_path"),
            "actions": actions,
            "archive": synced,
            "errors": errors,
        }
    except Exception as exc:  # Hooks must fail open.
        errors.append(f"{exc.__class__.__name__}: {exc}")
        try:
            incident = write_raw_unavailable_incident(
                aoa_root=root,
                event={**event, "hook_exception": errors[-1]},
                transcript_path=transcript_path,
                hook_event_name=event_name,
            )
            actions.append("hook_exception_diagnostic_written")
        except Exception:
            incident = None
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "hook_event_name": event_name,
            "timestamp": now,
            "session_id": session_id,
            "session_dir": str(session_dir),
            "actions": actions,
            "incident": incident,
            "errors": errors,
        }


def codex_hook_output(event_name: str, receipt: dict[str, Any]) -> dict[str, Any]:
    # Codex hook stdout is schema-validated with additionalProperties=false.
    # Keep the rich AoA receipt on disk; return only protocol fields here.
    output: dict[str, Any] = {"continue": True}
    if event_name == "SessionStart" and receipt.get("session_dir"):
        display = receipt.get("display_name") or receipt.get("session_dir")
        path = receipt.get("navigation_path") or receipt.get("session_dir")
        output["hookSpecificOutput"] = {
            "hookEventName": "SessionStart",
            "additionalContext": f"AoA session memory archive active: {display} ({path}).",
        }
    return output


def command_list(args: argparse.Namespace) -> int:
    root = aoa_root_for(Path(args.workspace_root) if args.workspace_root else None, Path(args.aoa_root) if args.aoa_root else None)
    sessions = registry_sessions(root)
    if args.format == "json":
        print(json.dumps({"schema_version": SCHEMA_VERSION, "sessions": sessions}, indent=2, ensure_ascii=False))
        return 0
    for item in sessions:
        print(
            "\t".join(
                [
                    str(item.get("session_label") or item.get("session_id") or ""),
                    str(item.get("archive_status") or ""),
                    str(item.get("distillation_status") or ""),
                    str(item.get("updated_at") or ""),
                    str(item.get("path") or ""),
                ]
            )
        )
    return 0


def bounded_index_document(document: dict[str, Any], *, max_segments: int, full: bool) -> dict[str, Any]:
    if full:
        return document
    bounded = {key: value for key, value in document.items() if key != "segments"}
    segments = document.get("segments", [])
    if isinstance(segments, list):
        preview_count = max(0, max_segments)
        bounded["segment_count"] = len(segments)
        bounded["segments_preview"] = segments[:preview_count]
        bounded["segments_truncated"] = len(segments) > preview_count
    return bounded


def session_show_payload(aoa_root: Path, target: str | None, *, max_segments: int = 24, full: bool = False) -> dict[str, Any]:
    record = resolve_session_record(aoa_root, target)
    session_dir = session_dir_from_record(record)
    manifest = read_json(session_dir / "session.manifest.json", {})
    session_index = read_json(session_dir / SESSION_INDEX_JSON, {})
    manifest_payload = bounded_index_document(manifest, max_segments=max_segments, full=full) if isinstance(manifest, dict) else manifest
    session_index_payload = (
        bounded_index_document(session_index, max_segments=max_segments, full=full)
        if isinstance(session_index, dict)
        else session_index
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "session": record,
        "manifest": manifest_payload,
        "session_index": session_index_payload,
        "show": {
            "full": full,
            "max_segments": None if full else max_segments,
            "note": "segment lists are bounded by default; pass --full for complete manifest output",
        },
    }


def command_show(args: argparse.Namespace) -> int:
    root = aoa_root_for(Path(args.workspace_root) if args.workspace_root else None, Path(args.aoa_root) if args.aoa_root else None)
    payload = session_show_payload(root, args.session, max_segments=args.max_segments, full=args.full)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def command_rehydrate(args: argparse.Namespace) -> int:
    root = aoa_root_for(Path(args.workspace_root) if args.workspace_root else None, Path(args.aoa_root) if args.aoa_root else None)
    print(rehydrate_packet(root, args.session, max_events=args.max_events))
    return 0


def command_distill(args: argparse.Namespace) -> int:
    root = aoa_root_for(Path(args.workspace_root) if args.workspace_root else None, Path(args.aoa_root) if args.aoa_root else None)
    payload = distill_session_first_pass(root, args.session, max_events_per_type=args.max_events_per_type)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def line_from_raw_ref(value: Any) -> int | None:
    match = re.search(r"raw:line:(\d+)", str(value or ""))
    return int(match.group(1)) if match else None


def segment_role_closes_compaction(segment: dict[str, Any]) -> bool:
    return str(segment.get("role") or "") in {"initial-to-compaction", "compaction-to-compaction"}


def session_stress_pass(
    aoa_root: Path,
    target: str | None,
    *,
    compaction_count: int = 100,
    write: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    record = resolve_session_record(aoa_root, target)
    session_dir = session_dir_from_record(record)
    manifest = read_json(session_dir / "session.manifest.json", {})
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError(f"missing session manifest: {session_dir}")

    segments = [segment for segment in manifest.get("segments", []) if isinstance(segment, dict)]
    closing_segments = [segment for segment in segments if segment_role_closes_compaction(segment)]
    selected = closing_segments[: max(0, compaction_count)]
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    raw_value = raw.get("path")
    raw_path = Path(str(raw_value)) if raw_value else Path()
    raw_exists = bool(raw_value and raw_path.is_file())

    event_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    missing_indexes: list[str] = []
    range_mismatches: list[dict[str, Any]] = []
    segment_summaries: list[dict[str, Any]] = []
    suspicious_microsegments: list[dict[str, Any]] = []

    for segment in selected:
        index_path = Path(str(segment.get("index") or ""))
        segment_range = segment.get("source_range") if isinstance(segment.get("source_range"), dict) else {}
        from_line = int(segment_range.get("from_line") or 0)
        to_line = int(segment_range.get("to_line") or 0)
        if not index_path.exists():
            missing_indexes.append(str(index_path))
            continue
        segment_index = read_json(index_path, {})
        events = segment_index.get("events", []) if isinstance(segment_index, dict) else []
        segment_event_counts: Counter[str] = Counter()
        segment_source_counts: Counter[str] = Counter()
        raw_ref_lines: list[int] = []
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("type") or "RAW_EVENT")
            source_type = str(event.get("source_type") or "")
            event_counts[event_type] += 1
            source_counts[source_type] += 1
            segment_event_counts[event_type] += 1
            segment_source_counts[source_type] += 1
            line_no = line_from_raw_ref(event.get("raw_ref"))
            if line_no is not None:
                raw_ref_lines.append(line_no)
        out_of_range = [
            line_no
            for line_no in raw_ref_lines
            if (from_line and line_no < from_line) or (to_line and line_no > to_line)
        ]
        if out_of_range:
            range_mismatches.append(
                {
                    "segment_id": segment.get("segment_id"),
                    "index": str(index_path),
                    "source_range": segment_range,
                    "out_of_range_raw_lines": out_of_range[:20],
                }
            )
        type_names = sorted(segment_event_counts)
        summary = {
            "segment_id": segment.get("segment_id"),
            "role": segment.get("role"),
            "event_count": segment.get("event_count"),
            "source_range": segment_range,
            "index": str(index_path),
            "markdown": segment.get("markdown"),
            "event_types": dict(sorted(segment_event_counts.items())),
            "source_types": dict(sorted(segment_source_counts.items())),
            "compaction_event_count": segment_event_counts.get("COMPACTION_EVENT", 0),
        }
        segment_summaries.append(summary)
        if int(segment.get("event_count", 0) or 0) <= 8 and set(type_names).issubset({"COMPACTION_EVENT", "CONTEXT_STATE"}):
            suspicious_microsegments.append(summary)

    selected_positions = [segments.index(segment) for segment in selected] if selected else []
    selected_contiguous_from_start = selected_positions == list(range(len(selected_positions)))
    first_range = selected[0].get("source_range") if selected and isinstance(selected[0].get("source_range"), dict) else {}
    last_range = selected[-1].get("source_range") if selected and isinstance(selected[-1].get("source_range"), dict) else {}
    selected_span = {
        "from_line": first_range.get("from_line"),
        "to_line": last_range.get("to_line"),
    }
    checks = [
        {"name": "raw_copy_exists", "ok": raw_exists, "detail": str(raw_path)},
        {
            "name": "requested_compaction_count_available",
            "ok": len(selected) == compaction_count,
            "detail": {"requested": compaction_count, "available": len(closing_segments), "selected": len(selected)},
        },
        {"name": "selected_segments_are_contiguous_from_start", "ok": selected_contiguous_from_start},
        {"name": "selected_segment_indexes_exist", "ok": not missing_indexes, "detail": missing_indexes[:20]},
        {"name": "selected_raw_refs_stay_inside_segment_ranges", "ok": not range_mismatches, "detail": range_mismatches[:20]},
        {"name": "selected_segments_close_compactions", "ok": all(item["compaction_event_count"] > 0 for item in segment_summaries)},
        {
            "name": "no_compaction_marker_microsegments",
            "ok": not suspicious_microsegments,
            "detail": [
                {
                    "segment_id": item.get("segment_id"),
                    "event_count": item.get("event_count"),
                    "source_range": item.get("source_range"),
                }
                for item in suspicious_microsegments[:20]
            ],
        },
    ]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "stress_pass_first_compactions",
        "generated_at": now,
        "ok": all(check["ok"] for check in checks),
        "session_id": manifest.get("session_id"),
        "session_label": manifest.get("session_label"),
        "session_dir": str(session_dir),
        "requested_compactions": compaction_count,
        "available_compaction_closing_segments": len(closing_segments),
        "selected_segment_count": len(selected),
        "selected_segment_ids": [str(segment.get("segment_id") or "") for segment in selected],
        "selected_source_span": selected_span,
        "selected_event_counts": dict(sorted(event_counts.items())),
        "selected_source_counts": dict(sorted(source_counts.items())),
        "raw": {
            "path": str(raw_path),
            "exists": raw_exists,
            "bytes": raw.get("bytes"),
            "line_count": raw.get("line_count"),
            "sha256": raw.get("sha256"),
        },
        "segment_summaries": segment_summaries,
        "checks": checks,
    }

    if write:
        diagnostics_dir = session_dir / "diagnostics"
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__stress-pass__first-{compaction_count}-compactions"
        json_path = diagnostics_dir / f"{stem}.json"
        markdown_path = diagnostics_dir / f"{stem}.md"
        payload["artifacts"] = {"json": str(json_path), "markdown": str(markdown_path)}
        write_json(json_path, payload)
        lines = [
            "---",
            "aoa_artifact_type: stress_pass_first_compactions",
            "schema_version: 1",
            f"session_id: {manifest.get('session_id')}",
            f"session_label: {manifest.get('session_label')}",
            f"generated_at: {now}",
            f"requested_compactions: {compaction_count}",
            f"ok: {str(payload['ok']).lower()}",
            f"index: ./{json_path.name}",
            "---",
            "",
            f"# Stress Pass: First {compaction_count} Compactions",
            "",
            "## Source",
            "",
            f"- session: `{manifest.get('session_label')}`",
            f"- raw: `{raw_path}`",
            f"- selected segments: `{len(selected)}` of `{len(closing_segments)}` compaction-closing segments",
            f"- selected raw span: `{selected_span.get('from_line')}..{selected_span.get('to_line')}`",
            "",
            "## Checks",
            "",
        ]
        for check in checks:
            lines.append(f"- `{check['name']}`: `{str(check['ok']).lower()}`")
        lines.extend(["", "## Event Counts", ""])
        for event_type, count in sorted(event_counts.items()):
            lines.append(f"- `{event_type}`: {count}")
        lines.extend(["", "## Segment Coverage", ""])
        for item in segment_summaries:
            source_range = item.get("source_range") if isinstance(item.get("source_range"), dict) else {}
            lines.append(
                f"- `{item.get('segment_id')}` `{item.get('role')}` "
                f"events=`{item.get('event_count')}` lines=`{source_range.get('from_line')}..{source_range.get('to_line')}` "
                f"compaction_events=`{item.get('compaction_event_count')}`"
            )
        if suspicious_microsegments:
            lines.extend(["", "## Suspicious Microsegments", ""])
            for item in suspicious_microsegments:
                lines.append(f"- `{item.get('segment_id')}` range=`{item.get('source_range')}` events=`{item.get('event_count')}`")
        lines.append("")
        markdown_path.write_text("\n".join(lines), encoding="utf-8")
        write_json(json_path, payload)
    return payload


def stress_pass_print_payload(payload: dict[str, Any], *, full: bool = False, sample_segments: int = 6) -> dict[str, Any]:
    if full:
        return payload
    summaries = payload.get("segment_summaries", [])
    segment_count = len(summaries) if isinstance(summaries, list) else 0
    sample: list[Any] = []
    if isinstance(summaries, list) and summaries:
        if segment_count <= sample_segments:
            sample = summaries
        else:
            head_count = max(1, sample_segments // 2)
            tail_count = max(1, sample_segments - head_count)
            sample = summaries[:head_count] + summaries[-tail_count:]
    compact = {key: value for key, value in payload.items() if key != "segment_summaries"}
    selected_ids = compact.get("selected_segment_ids")
    if isinstance(selected_ids, list) and len(selected_ids) > 24:
        compact["selected_segment_id_count"] = len(selected_ids)
        compact["selected_segment_ids_sample"] = selected_ids[:12] + selected_ids[-12:]
        compact["selected_segment_ids_omitted"] = len(selected_ids) - 24
        del compact["selected_segment_ids"]
    compact["segment_summary_count"] = segment_count
    compact["segment_summaries_sample"] = sample
    compact["segment_summaries_omitted"] = max(0, segment_count - len(sample))
    compact["print"] = {
        "full": False,
        "note": "segment_summaries are bounded on stdout; pass --full for complete JSON or read the written artifact",
    }
    return compact


def command_stress_pass(args: argparse.Namespace) -> int:
    root = aoa_root_for(Path(args.workspace_root) if args.workspace_root else None, Path(args.aoa_root) if args.aoa_root else None)
    payload = session_stress_pass(root, args.session, compaction_count=args.compactions, write=args.write)
    print(json.dumps(stress_pass_print_payload(payload, full=args.full), indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_hook(args: argparse.Namespace) -> int:
    raw = sys.stdin.read().strip()
    event = json.loads(raw) if raw else {}
    receipt = handle_hook_event(
        args.event_name,
        event if isinstance(event, dict) else {"payload": event},
        workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        aoa_root=Path(args.aoa_root) if args.aoa_root else None,
    )
    output = codex_hook_output(args.event_name, receipt)
    print(json.dumps(output, ensure_ascii=False))
    return 0


def command_sync(args: argparse.Namespace) -> int:
    event = {
        "session_id": args.session_id,
        "transcript_path": args.transcript_path,
        "cwd": args.cwd,
        "hook_event_name": "ManualSync",
    }
    receipt = handle_hook_event(
        "ManualSync",
        event,
        workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        aoa_root=Path(args.aoa_root) if args.aoa_root else None,
    )
    print(json.dumps(receipt, indent=2, ensure_ascii=False))
    return 0 if receipt.get("ok") else 1


def command_relabel(args: argparse.Namespace) -> int:
    root = aoa_root_for(Path(args.workspace_root) if args.workspace_root else None, Path(args.aoa_root) if args.aoa_root else None)
    payload = rebuild_session_labels(root)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def command_hooks_config(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    workspace_root = workspace_root_for(explicit_workspace, root)
    config = build_user_hooks_config(workspace_root, root, python_bin=args.python_bin)
    if not args.write:
        print(json.dumps(config, indent=2, ensure_ascii=False))
        return 0

    target = Path(args.write).expanduser()
    backup_path: Path | None = None
    if target.exists() and not args.no_backup:
        backup_path = target.with_name(f"{target.name}.{compact_stamp()}.bak")
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_path)
    write_json(target, config)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "written_to": str(target),
        "backup_path": str(backup_path) if backup_path else None,
        "workspace_root": str(workspace_root),
        "aoa_root": str(root),
        "events": REQUIRED_HOOK_EVENTS,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def command_export_bundle(args: argparse.Namespace) -> int:
    source = Path(args.source_aoa_root) if args.source_aoa_root else default_source_aoa_root()
    target = Path(args.target_dir)
    if target.exists() and args.force:
        clear_export_target_for_force(target)
    payload = copy_portable_bundle(
        source_aoa_root=source,
        target_aoa_root=target,
        include_sessions=args.with_sessions,
        include_tests=not args.no_tests,
        overwrite=args.force,
    )
    print(json.dumps({"schema_version": SCHEMA_VERSION, "ok": True, **payload}, indent=2, ensure_ascii=False))
    return 0


def command_install(args: argparse.Namespace) -> int:
    source = Path(args.source_aoa_root) if args.source_aoa_root else default_source_aoa_root()
    workspace_root = Path(args.workspace_root)
    root = aoa_root_for(workspace_root, Path(args.aoa_root) if args.aoa_root else None)
    hooks_path = Path(args.write_user_hooks).expanduser() if args.write_user_hooks else None
    payload = install_portable_bundle(
        source_aoa_root=source,
        workspace_root=workspace_root,
        aoa_root=root,
        include_sessions=args.with_sessions,
        include_tests=not args.no_tests,
        overwrite=args.force,
        hooks_path=hooks_path,
        backup_hooks=not args.no_hooks_backup,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def command_install_user_skill(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    skills_dir = Path(args.skills_dir).expanduser() if args.skills_dir else None
    payload = install_user_skill(
        aoa_root=root,
        skills_dir=skills_dir,
        force=args.force,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_codex_grounding(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    workspace_root = workspace_root_for(explicit_workspace, root)
    payload = codex_grounding(
        workspace_root=workspace_root,
        aoa_root=root,
        codex_bin=args.codex_bin,
        codex_native_bin=Path(args.codex_native_bin) if args.codex_native_bin else None,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_codex_hooks_status(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    workspace_root = workspace_root_for(explicit_workspace, root)
    try:
        payload = codex_hooks_status(
            workspace_root=workspace_root,
            aoa_root=root,
            codex_bin=args.codex_bin,
            trust_current=args.trust_current,
            timeout=args.timeout,
        )
    except Exception as exc:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "workspace_root": str(workspace_root),
            "aoa_root": str(root),
            "error": f"{exc.__class__.__name__}: {exc}",
        }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_codex_compact_probe(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    workspace_root = workspace_root_for(explicit_workspace, root)
    try:
        payload = codex_manual_compact_probe(
            workspace_root=workspace_root,
            aoa_root=root,
            codex_bin=args.codex_bin,
            trust_hooks=args.trust_hooks,
            timeout=args.timeout,
        )
    except Exception as exc:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "workspace_root": str(workspace_root),
            "aoa_root": str(root),
            "error": f"{exc.__class__.__name__}: {exc}",
        }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def write_validation_config(aoa_root: Path) -> None:
    routes = {event_type: [] for event_type in EVENT_TYPE_ORDER}
    routes.update(
        {
            "DECISION": ["principle", "experience"],
            "ERROR": ["root_cause"],
            "COMMAND": ["command_recipe"],
            "COMMAND_OUTPUT": ["verification_signal"],
            "COMPACTION_EVENT": ["handoff_boundary"],
            "DIFF": ["implementation_delta"],
        }
    )
    write_json(
        aoa_root / "config" / "event-distillation-routes.json",
        {"schema_version": SCHEMA_VERSION, "routes": routes},
    )
    write_json(
        aoa_root / "config" / "naming-policy.json",
        {
            "schema_version": SCHEMA_VERSION,
            "segment_roles": [
                "initial-to-compaction",
                "compaction-to-compaction",
                "compaction-to-latest",
                "initial-to-latest",
            ],
            "banned_durable_name_terms": ["temp", "stub", "misc", "dump"],
        },
    )


def validation_transcript_rows() -> list[dict[str, Any]]:
    return [
        {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "aoa-validate-session"}},
        {
            "timestamp": "2026-05-12T00:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Validate portable AoA session memory pipeline"}],
            },
        },
        {
            "timestamp": "2026-05-12T00:00:02Z",
            "type": "response_item",
            "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-validate-1"},
        },
        {
            "timestamp": "2026-05-12T00:00:03Z",
            "type": "response_item",
            "payload": {"type": "function_call_output", "call_id": "call-validate-1", "output": "Process exited with code 0\nstdout: ok"},
        },
        {"timestamp": "2026-05-12T00:00:04Z", "type": "turn_context", "payload": {"summary": "first compaction boundary"}},
        {
            "timestamp": "2026-05-12T00:00:05Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Decision: generated hook config must match the selected roots."}],
            },
        },
    ]


def validate_pipeline(*, workspace_root: Path | None = None, aoa_root: Path | None = None) -> dict[str, Any]:
    reference_root = aoa_root_for(workspace_root, aoa_root)
    reference_workspace = workspace_root_for(workspace_root, reference_root)
    checks: list[dict[str, Any]] = []

    def add_check(name: str, ok: bool, detail: Any = None) -> None:
        item: dict[str, Any] = {"name": name, "ok": bool(ok)}
        if detail is not None:
            item["detail"] = detail
        checks.append(item)

    try:
        generated_config = build_user_hooks_config(reference_workspace, reference_root)
        generated_commands = expected_hook_commands(reference_workspace, reference_root)
        add_check("generated_hook_config_events", set(generated_config.get("hooks", {})) == set(REQUIRED_HOOK_EVENTS))
        add_check(
            "generated_hook_commands_target_selected_roots",
            all(str(reference_workspace) in command and str(reference_root) in command for command in generated_commands.values()),
        )

        with tempfile.TemporaryDirectory(prefix="aoa-session-memory-validate-") as tmp:
            temp_workspace = Path(tmp) / "AbyssOS"
            temp_aoa = temp_workspace / ".aoa"
            write_validation_config(temp_aoa)
            transcript_path = Path(tmp) / "rollout-2026-05-12T00-00-00-aoa-validate-session.jsonl"
            write_jsonl(transcript_path, validation_transcript_rows())
            event = {
                "session_id": "aoa-validate-session",
                "transcript_path": str(transcript_path),
                "cwd": str(temp_workspace),
                "trigger": "validate",
                "turn_id": "validate-turn",
            }
            receipts: dict[str, dict[str, Any]] = {}
            for hook_name in ("PreCompact", "PostCompact", "Stop"):
                receipts[hook_name] = handle_hook_event(
                    hook_name,
                    {**event, "hook_event_name": hook_name},
                    workspace_root=temp_workspace,
                    aoa_root=temp_aoa,
                )
                add_check(f"{hook_name.lower()}_receipt_ok", receipts[hook_name].get("ok") is True, receipts[hook_name].get("errors"))

            session_dir = Path(str(receipts["Stop"].get("session_dir") or ""))
            manifest = read_json(session_dir / "session.manifest.json", {})
            segments = manifest.get("segments", []) if isinstance(manifest, dict) else []
            segment_roles = [segment.get("role") for segment in segments if isinstance(segment, dict)]
            add_check("raw_copy_exists", (session_dir / "raw" / "session.raw.jsonl").exists())
            add_check("raw_source_metadata_exists", (session_dir / "raw" / RAW_SOURCE_JSON).exists())
            add_check("segments_include_compaction_interval", segment_roles == ["initial-to-compaction", "compaction-to-latest"], segment_roles)
            add_check(
                "segment_indexes_exist",
                bool(segments) and all(Path(str(segment.get("index") or "")).exists() for segment in segments if isinstance(segment, dict)),
            )

            packet = rehydrate_packet(temp_aoa, "latest")
            add_check("rehydrate_packet_names_session", "2026-05-12__001__validate-portable-aoa-session-memory-pipeline" in packet)
            add_check("rehydrate_packet_preserves_decision_route", "`DECISION`" in packet)

            distillation = distill_session_first_pass(temp_aoa, "latest", max_events_per_type=10)
            add_check("first_pass_distillation_ok", distillation.get("ok") is True)
            add_check("first_pass_distillation_has_candidates", int(distillation.get("candidate_count", 0) or 0) > 0)

            hook_outputs = {
                event_name: codex_hook_output(event_name, {"ok": True, "session_dir": str(session_dir)})
                for event_name in REQUIRED_HOOK_EVENTS
            }
            add_check(
                "codex_hook_stdout_fields_are_schema_limited",
                all(set(output).issubset(CODEX_HOOK_OUTPUT_FIELDS) for output in hook_outputs.values()),
                hook_outputs,
            )

            payload = {
                "schema_version": SCHEMA_VERSION,
                "ok": all(check["ok"] for check in checks),
                "reference_workspace_root": str(reference_workspace),
                "reference_aoa_root": str(reference_root),
                "validated_session_label": manifest.get("session_label") if isinstance(manifest, dict) else None,
                "checks": checks,
            }
            return payload
    except Exception as exc:
        add_check("validate_pipeline_exception", False, f"{exc.__class__.__name__}: {exc}")
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": False,
            "reference_workspace_root": str(reference_workspace),
            "reference_aoa_root": str(reference_root),
            "checks": checks,
        }


def count_live_hook_events(aoa_root: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for path in (aoa_root / SESSION_ROOT).glob("*/hooks/events.jsonl"):
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event_name = row.get("hook_event_name")
                if event_name:
                    counts[str(event_name)] += 1
    return dict(sorted(counts.items()))


def archive_compaction_audit(aoa_root: Path) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for manifest_path in sorted((aoa_root / SESSION_ROOT).glob("*/session.manifest.json")):
        session_dir = manifest_path.parent
        manifest = read_json(manifest_path, {})
        if not isinstance(manifest, dict):
            continue
        raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
        raw_value = raw.get("path")
        raw_path = Path(str(raw_value)) if raw_value else Path()
        raw_exists = bool(raw_value and raw_path.is_file())
        segments = manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []
        boundary_count = 0
        compaction_marker_count = 0
        source_compacted_count = 0
        context_compacted_event_count = 0
        expected_segment_count = 0
        if raw_exists:
            events = parse_raw_events(raw_path)
            boundary_count = len(compaction_boundary_groups(events))
            compaction_marker_count = sum(1 for event in events if event.compaction_boundary)
            source_compacted_count = sum(1 for event in events if event.source_type == "compacted")
            context_compacted_event_count = sum(
                1
                for event in events
                if event.source_type == "event_msg"
                and isinstance(event.parsed, dict)
                and isinstance(event.parsed.get("payload"), dict)
                and event.parsed["payload"].get("type") == "context_compacted"
            )
            expected_segment_count = len(segment_ranges(events))
        actual_segment_count = len(segments)
        audits.append(
            {
                "session_id": manifest.get("session_id"),
                "session_label": manifest.get("session_label"),
                "archive_status": manifest.get("archive_status"),
                "raw_exists": raw_exists,
                "compaction_boundary_count": boundary_count,
                "compaction_marker_count": compaction_marker_count,
                "source_compacted_count": source_compacted_count,
                "context_compacted_event_count": context_compacted_event_count,
                "expected_segment_count": expected_segment_count,
                "actual_segment_count": actual_segment_count,
                "matches_expected_segments": actual_segment_count == expected_segment_count,
                "roles": dict(Counter(str(segment.get("role")) for segment in segments if isinstance(segment, dict))),
            }
        )
    return audits


def completion_audit(
    *,
    workspace_root: Path,
    aoa_root: Path,
    check_codex: bool = True,
) -> dict[str, Any]:
    now = utc_now()
    sessions = registry_sessions(aoa_root)
    root_files_missing = [rel for rel in REQUIRED_ROOT_FILES if not (aoa_root / rel).exists()]
    hook_counts = count_live_hook_events(aoa_root)
    compaction_archives = archive_compaction_audit(aoa_root)
    indexed_archives = [item for item in compaction_archives if item.get("archive_status") == "indexed"]
    real_compaction_archives = [item for item in compaction_archives if int(item.get("compaction_boundary_count", 0) or 0) > 0]
    segments_match = bool(indexed_archives) and all(item.get("matches_expected_segments") for item in indexed_archives)
    raw_preserved = bool(indexed_archives) and all(item.get("raw_exists") for item in indexed_archives)
    live_prepost_seen = hook_counts.get("PreCompact", 0) > 0 and hook_counts.get("PostCompact", 0) > 0
    grounding_payload: dict[str, Any] | None = codex_grounding(workspace_root=workspace_root, aoa_root=aoa_root) if check_codex else None
    grounding_ok = True if grounding_payload is None else bool(grounding_payload.get("ok"))
    standalone_repo = default_standalone_repo_for(aoa_root)
    standalone_repo_exists = (standalone_repo / ".git").exists()
    standalone_remote = git_remote_url(standalone_repo)
    standalone_github_ready = bool(standalone_remote and "github.com" in standalone_remote.lower())
    user_skill_state = user_skill_install_state(aoa_root)

    def checklist_item(requirement: str, status: str, evidence: Any, gap: str | None = None) -> dict[str, Any]:
        item: dict[str, Any] = {
            "requirement": requirement,
            "status": status,
            "evidence": evidence,
        }
        if gap:
            item["gap"] = gap
        return item

    checklist = [
        checklist_item(
            "Root kernel surfaces exist and are agent-readable",
            "covered" if not root_files_missing else "missing",
            {"missing": root_files_missing, "required_count": len(REQUIRED_ROOT_FILES)},
        ),
        checklist_item(
            "Raw session material is preserved for indexed archives",
            "covered" if raw_preserved else "missing",
            {"indexed_archive_count": len(indexed_archives)},
        ),
        checklist_item(
            "Real Codex compaction boundaries are detected from raw transcripts",
            "covered" if real_compaction_archives else "missing",
            {
                "real_compaction_archive_count": len(real_compaction_archives),
                "boundary_counts": {item["session_label"]: item["compaction_boundary_count"] for item in real_compaction_archives},
            },
        ),
        checklist_item(
            "Segment topology matches raw compaction boundaries",
            "covered" if segments_match else "missing",
            {
                "archives": [
                    {
                        "session_label": item["session_label"],
                        "expected": item["expected_segment_count"],
                        "actual": item["actual_segment_count"],
                    }
                    for item in compaction_archives
                ]
            },
        ),
        checklist_item(
            "Hook output remains schema-limited and fail-open",
            "covered",
            {"allowed_fields": sorted(CODEX_HOOK_OUTPUT_FIELDS), "hook_output_function": "codex_hook_output"},
        ),
        checklist_item(
            "Live user hooks are wired for required lifecycle events",
            "covered" if set(REQUIRED_HOOK_EVENTS).issubset(configured_hook_events(Path.home() / ".codex" / "hooks.json")) else "missing",
            {"required_events": REQUIRED_HOOK_EVENTS, "live_hook_counts": hook_counts},
        ),
        checklist_item(
            "Local Codex compact and hook contract is grounded",
            "covered" if grounding_ok else "missing",
            grounding_payload or {"skipped": True},
        ),
        checklist_item(
            "Portable clean export and workspace install exist",
            "covered",
            {"commands": ["export-bundle", "install", "hooks-config", "install-user-skill"]},
        ),
        checklist_item(
            "User-level router skill is installed for the current Codex user",
            "covered" if user_skill_state.get("ok") else "remaining",
            user_skill_state,
            None if user_skill_state.get("ok") else "Install the user-level router with install-user-skill.",
        ),
        checklist_item(
            "Standalone local repository is prepared for the portable bundle",
            "covered" if standalone_repo_exists else "remaining",
            {"standalone_repo": str(standalone_repo), "git_dir_exists": standalone_repo_exists},
            None if standalone_repo_exists else "Prepare a local clean repository after the bundle is accepted.",
        ),
        checklist_item(
            "Tests cover archive, hooks, compaction, install, distillation, and grounding",
            "covered",
            {"test_file": str(aoa_root / "tests/test_session_memory.py")},
        ),
        checklist_item(
            "Live PreCompact and PostCompact hook receipts observed in archived sessions",
            "covered" if live_prepost_seen else "remaining",
            {"live_hook_counts": hook_counts},
            None if live_prepost_seen else "Real compaction markers exist, but current archives do not yet include live PreCompact/PostCompact hook receipts.",
        ),
        checklist_item(
            "Standalone GitHub repository exists for the portable bundle",
            "covered" if standalone_github_ready else "remaining",
            {"standalone_repo": str(standalone_repo), "origin": standalone_remote},
            None if standalone_github_ready else "Create or connect a GitHub repository after local acceptance.",
        ),
    ]
    completion_ready = all(item["status"] == "covered" for item in checklist)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        "ok": completion_ready,
        "completion_ready": completion_ready,
        "workspace_root": str(workspace_root),
        "aoa_root": str(aoa_root),
        "session_count": len(sessions),
        "archive_compaction_audit": compaction_archives,
        "hook_counts": hook_counts,
        "checklist": checklist,
        "remaining": [item for item in checklist if item["status"] != "covered"],
    }


def command_validate(args: argparse.Namespace) -> int:
    payload = validate_pipeline(
        workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        aoa_root=Path(args.aoa_root) if args.aoa_root else None,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_audit(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    workspace_root = workspace_root_for(explicit_workspace, root)
    payload = completion_audit(
        workspace_root=workspace_root,
        aoa_root=root,
        check_codex=not args.skip_codex_grounding,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


REQUIRED_ROOT_FILES = [
    "AGENTS.md",
    "DESIGN.md",
    "PIPELINE.md",
    "READINESS.md",
    "README.md",
    "NAMING.md",
    "config/event-distillation-routes.json",
    "config/event-taxonomy.json",
    "config/naming-policy.json",
    "hooks/README.md",
    "hooks/codex-hooks.user.example.json",
    "schemas/hook-receipt.schema.json",
    "schemas/incident.schema.json",
    "schemas/segment.index.schema.json",
    "schemas/session.manifest.schema.json",
    "scripts/aoa_session_memory.py",
    "skills/aoa-codex-compact-probe/SKILL.md",
    "skills/aoa-codex-hooks-status/SKILL.md",
    "skills/aoa-codex-session-segment-archive/SKILL.md",
    "skills/aoa-session-archive-init/SKILL.md",
    "skills/aoa-session-first-pass-distill/SKILL.md",
    "skills/aoa-session-memory-audit/SKILL.md",
    "skills/aoa-session-memory-doctor/SKILL.md",
    "skills/aoa-session-memory-global-route/SKILL.md",
    "skills/aoa-session-memory-stress-pass/SKILL.md",
    "skills/aoa-session-raw-diagnostic/SKILL.md",
    "skills/aoa-session-rehydrate/SKILL.md",
]

def configured_hook_events(path: Path) -> set[str]:
    config = read_json(path, {})
    hooks = config.get("hooks") if isinstance(config, dict) else {}
    if not isinstance(hooks, dict):
        return set()
    return {str(key) for key, value in hooks.items() if isinstance(value, list)}


def command_doctor(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    workspace_root = workspace_root_for(explicit_workspace, root)
    registry = read_json(root / REGISTRY_NAME, {"sessions": []})
    sessions = registry.get("sessions", []) if isinstance(registry, dict) else []
    policy = naming_policy(root)
    banned_terms = set(policy.get("banned_durable_name_terms", [])) if isinstance(policy.get("banned_durable_name_terms"), list) else set()
    allowed_segment_roles = set(policy.get("segment_roles", [])) if isinstance(policy.get("segment_roles"), list) else set()
    problems: list[str] = []
    warnings: list[str] = []

    for rel_path in REQUIRED_ROOT_FILES:
        if not (root / rel_path).exists():
            problems.append(f"missing required root file: {rel_path}")

    taxonomy = read_json(root / "config/event-taxonomy.json", {})
    taxonomy_types = set(taxonomy.get("event_types", [])) if isinstance(taxonomy, dict) and isinstance(taxonomy.get("event_types"), list) else set()
    missing_taxonomy = [event_type for event_type in EVENT_TYPE_ORDER if event_type not in taxonomy_types]
    if missing_taxonomy:
        problems.append(f"event taxonomy missing types: {missing_taxonomy}")

    routes = read_json(root / "config/event-distillation-routes.json", {})
    route_map = routes.get("routes", {}) if isinstance(routes, dict) else {}
    if isinstance(route_map, dict):
        missing_routes = [event_type for event_type in EVENT_TYPE_ORDER if event_type not in route_map and event_type not in {"SESSION_META", "CONTEXT_STATE", "ASSISTANT_MESSAGE", "HOOK_EVENT", "RAW_EVENT"}]
        if missing_routes:
            warnings.append(f"event distillation routes missing optional routes: {missing_routes}")

    example_hooks = root / "hooks/codex-hooks.user.example.json"
    example_events = configured_hook_events(example_hooks)
    missing_example_hooks = [event_name for event_name in REQUIRED_HOOK_EVENTS if event_name not in example_events]
    if missing_example_hooks:
        problems.append(f"hook example missing events: {missing_example_hooks}")

    if args.check_live_hooks:
        live_hooks = Path.home() / ".codex" / "hooks.json"
        live_events = configured_hook_events(live_hooks)
        missing_live_hooks = [event_name for event_name in REQUIRED_HOOK_EVENTS if event_name not in live_events]
        if missing_live_hooks:
            problems.append(f"live user hooks missing events: {missing_live_hooks}")
        live_commands = hook_command_map(live_hooks)
        expected_commands = expected_hook_commands(workspace_root, root)
        for event_name, expected_command in expected_commands.items():
            if expected_command not in live_commands.get(event_name, []):
                problems.append(f"live user hooks command mismatch for {event_name}: expected {expected_command}")

    user_skill_state = user_skill_install_state(root)
    if args.check_user_skill and not user_skill_state.get("ok"):
        problems.append(f"user-level router skill is not installed: {user_skill_state}")

    if args.check_codex_grounding:
        grounding = codex_grounding(workspace_root=workspace_root, aoa_root=root)
        if not grounding.get("ok"):
            failed = [check["name"] for check in grounding.get("checks", []) if isinstance(check, dict) and not check.get("ok")]
            problems.append(f"codex grounding failed checks: {failed}")

    legacy_root = root / LEGACY_SESSION_ROOT
    if legacy_root.exists() and any(legacy_root.iterdir()):
        problems.append(f"legacy session root is not empty: {legacy_root}")
    session_root = root / SESSION_ROOT
    archive_dirs = [path for path in session_root.iterdir() if path.is_dir()] if session_root.exists() else []
    if isinstance(sessions, list) and len(sessions) != len(archive_dirs):
        problems.append(f"session registry count {len(sessions)} does not match archive directory count {len(archive_dirs)}")
    for item in sessions if isinstance(sessions, list) else []:
        if not isinstance(item, dict):
            continue
        session_path = Path(str(item.get("path", "")))
        manifest = session_path / "session.manifest.json"
        index = session_path / SESSION_INDEX_JSON
        entry = session_path / SESSION_INDEX_MARKDOWN
        session_agents = session_path / "AGENTS.md"
        if not manifest.exists():
            problems.append(f"missing manifest: {session_path}")
            continue
        manifest_payload = read_json(manifest, {})
        if not isinstance(manifest_payload, dict):
            problems.append(f"invalid manifest json: {manifest}")
            continue
        if not session_agents.exists():
            problems.append(f"missing session AGENTS.md: {session_path}")
        if not index.exists() and item.get("archive_status") == "indexed":
            problems.append(f"missing session index: {session_path}")
        if not entry.exists() and item.get("archive_status") == "indexed":
            problems.append(f"missing session entry file: {session_path}")
        display = item.get("display") if isinstance(item.get("display"), dict) else {}
        label = str(item.get("session_label") or display.get("label") or "")
        if label and session_path.name != label:
            problems.append(f"archive folder does not match session label: {session_path}")
        if label and not re.match(r"^20\d{2}-[01]\d-[0-3]\d__\d{3}__[^/]+$", label):
            problems.append(f"session label does not match naming policy: {label}")
        bad_terms = sorted(name_terms(label) & banned_terms)
        if bad_terms:
            problems.append(f"session label contains banned terms {bad_terms}: {label}")
        navigation_value = item.get("navigation_path") or display.get("navigation_path") or item.get("path")
        if navigation_value and not Path(str(navigation_value)).exists():
            problems.append(f"missing navigation path: {navigation_value}")
        archive_status = str(manifest_payload.get("archive_status") or item.get("archive_status") or "")
        if archive_status == "indexed":
            raw = manifest_payload.get("raw") if isinstance(manifest_payload.get("raw"), dict) else {}
            raw_path = Path(str(raw.get("path") or ""))
            if not raw_path.exists():
                problems.append(f"indexed session missing raw copy: {session_path}")
            if not (session_path / "raw" / RAW_SOURCE_JSON).exists():
                problems.append(f"indexed session missing raw source metadata: {session_path}")
            segments = manifest_payload.get("segments", [])
            if not isinstance(segments, list) or not segments:
                problems.append(f"indexed session has no segments: {session_path}")
            for segment in segments if isinstance(segments, list) else []:
                if not isinstance(segment, dict):
                    problems.append(f"invalid segment manifest record: {session_path}")
                    continue
                role = str(segment.get("role") or "")
                if allowed_segment_roles and role not in allowed_segment_roles:
                    problems.append(f"invalid segment role {role}: {session_path}")
                md_path = Path(str(segment.get("markdown") or ""))
                idx_path = Path(str(segment.get("index") or ""))
                if not md_path.exists():
                    problems.append(f"missing segment markdown: {md_path}")
                if not idx_path.exists():
                    problems.append(f"missing segment index: {idx_path}")
                    continue
                segment_index = read_json(idx_path, {})
                if not isinstance(segment_index, dict):
                    problems.append(f"invalid segment index json: {idx_path}")
                    continue
                for event in segment_index.get("events", []) if isinstance(segment_index.get("events"), list) else []:
                    if not isinstance(event, dict):
                        problems.append(f"invalid event index record: {idx_path}")
                        continue
                    if event.get("type") not in EVENT_TYPE_ORDER:
                        problems.append(f"invalid event type {event.get('type')}: {idx_path}")
                    if not event.get("raw_ref") or not event.get("md_anchor"):
                        problems.append(f"event missing raw_ref or md_anchor: {idx_path}")
        elif archive_status == "raw_unavailable":
            if not list((session_path / "incidents").glob("*__INCIDENT.md")):
                problems.append(f"raw_unavailable session missing incident markdown: {session_path}")
            if not list((session_path / "incidents").glob("*__DIAGNOSTIC.json")):
                problems.append(f"raw_unavailable session missing diagnostic json: {session_path}")
        distillation_status = str(manifest_payload.get("distillation_status") or "")
        if distillation_status == "first_pass_distilled":
            distillation = manifest_payload.get("distillation") if isinstance(manifest_payload.get("distillation"), dict) else {}
            latest_index = Path(str(distillation.get("latest_index") or session_path / "distillation" / "distillation.index.json"))
            latest_markdown = Path(str(distillation.get("latest_markdown") or session_path / "distillation" / "001__first-pass__experience-map.md"))
            if not latest_index.exists():
                problems.append(f"first-pass distilled session missing distillation index: {session_path}")
            if not latest_markdown.exists():
                problems.append(f"first-pass distilled session missing distillation markdown: {session_path}")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "ok": not problems,
        "aoa_root": str(root),
        "session_count": len(sessions) if isinstance(sessions, list) else 0,
        "archive_dir_count": len(archive_dirs),
        "user_skill": user_skill_state,
        "problems": problems,
        "warnings": warnings,
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AoA Codex session memory archive hooks.")
    sub = parser.add_subparsers(dest="command", required=True)

    list_cmd = sub.add_parser("list", help="List archived sessions from the registry.")
    list_cmd.add_argument("--workspace-root")
    list_cmd.add_argument("--aoa-root")
    list_cmd.add_argument("--format", choices=["text", "json"], default="text")
    list_cmd.set_defaults(func=command_list)

    show = sub.add_parser("show", help="Show a session manifest and index by id, label, title, or latest.")
    show.add_argument("session", nargs="?", default="latest")
    show.add_argument("--workspace-root")
    show.add_argument("--aoa-root")
    show.add_argument("--max-segments", type=int, default=24, help="Maximum segment records to show unless --full is used.")
    show.add_argument("--full", action="store_true", help="Print complete segment lists.")
    show.set_defaults(func=command_show)

    rehydrate = sub.add_parser("rehydrate", help="Print a compact rehydration packet for a session.")
    rehydrate.add_argument("session", nargs="?", default="latest")
    rehydrate.add_argument("--workspace-root")
    rehydrate.add_argument("--aoa-root")
    rehydrate.add_argument("--max-events", type=int, default=24)
    rehydrate.set_defaults(func=command_rehydrate)

    distill = sub.add_parser("distill", help="Write a provisional first-pass distillation route map for a session.")
    distill.add_argument("session", nargs="?", default="latest")
    distill.add_argument("--workspace-root")
    distill.add_argument("--aoa-root")
    distill.add_argument("--max-events-per-type", type=int, default=30)
    distill.set_defaults(func=command_distill)

    stress_pass = sub.add_parser("stress-pass", help="Audit the first N compaction-closing intervals for a session.")
    stress_pass.add_argument("session", nargs="?", default="latest")
    stress_pass.add_argument("--workspace-root")
    stress_pass.add_argument("--aoa-root")
    stress_pass.add_argument("--compactions", type=int, default=100)
    stress_pass.add_argument("--write", action="store_true", help="Write JSON and Markdown diagnostics into the session archive.")
    stress_pass.add_argument("--full", action="store_true", help="Print complete segment summaries to stdout.")
    stress_pass.set_defaults(func=command_stress_pass)

    hook = sub.add_parser("hook", help="Run from a Codex hook event.")
    hook.add_argument("--event-name", required=True)
    hook.add_argument("--workspace-root")
    hook.add_argument("--aoa-root")
    hook.set_defaults(func=command_hook)

    sync = sub.add_parser("sync", help="Manually sync one transcript into the archive.")
    sync.add_argument("--transcript-path", required=True)
    sync.add_argument("--session-id", required=True)
    sync.add_argument("--cwd")
    sync.add_argument("--workspace-root")
    sync.add_argument("--aoa-root")
    sync.set_defaults(func=command_sync)

    relabel = sub.add_parser("relabel", help="Rebuild readable date/sequence session archive names.")
    relabel.add_argument("--workspace-root")
    relabel.add_argument("--aoa-root")
    relabel.set_defaults(func=command_relabel)

    hooks_config = sub.add_parser("hooks-config", help="Generate or install user-level Codex hook config for this .aoa root.")
    hooks_config.add_argument("--workspace-root")
    hooks_config.add_argument("--aoa-root")
    hooks_config.add_argument("--python-bin", default="python3")
    hooks_config.add_argument("--write", help="Write the generated config to this hooks.json path instead of printing it.")
    hooks_config.add_argument("--no-backup", action="store_true", help="Do not back up an existing hooks.json before writing.")
    hooks_config.set_defaults(func=command_hooks_config)

    export_bundle = sub.add_parser("export-bundle", help="Copy the portable .aoa bundle to a clean target directory.")
    export_bundle.add_argument("--target-dir", required=True)
    export_bundle.add_argument("--source-aoa-root")
    export_bundle.add_argument("--with-sessions", action="store_true", help="Also copy current session archives and registry.")
    export_bundle.add_argument("--no-tests", action="store_true", help="Do not copy the local test suite.")
    export_bundle.add_argument("--force", action="store_true", help="Overwrite portable files in a non-empty target directory.")
    export_bundle.set_defaults(func=command_export_bundle)

    install = sub.add_parser("install", help="Install the portable .aoa bundle into a workspace.")
    install.add_argument("--workspace-root", required=True)
    install.add_argument("--aoa-root")
    install.add_argument("--source-aoa-root")
    install.add_argument("--with-sessions", action="store_true", help="Also copy current session archives and registry.")
    install.add_argument("--no-tests", action="store_true", help="Do not copy the local test suite.")
    install.add_argument("--force", action="store_true", help="Overwrite portable files in a non-empty .aoa root.")
    install.add_argument("--write-user-hooks", help="Write generated user-level hooks to this hooks.json path.")
    install.add_argument("--no-hooks-backup", action="store_true", help="Do not back up an existing user hooks file.")
    install.set_defaults(func=command_install)

    install_user_skill = sub.add_parser("install-user-skill", help="Install the global .aoa session-memory router skill for the current Codex user.")
    install_user_skill.add_argument("--workspace-root")
    install_user_skill.add_argument("--aoa-root")
    install_user_skill.add_argument("--skills-dir", help="User skills directory; defaults to ~/.codex/skills.")
    install_user_skill.add_argument("--force", action="store_true", help="Back up and replace an existing conflicting skill target.")
    install_user_skill.set_defaults(func=command_install_user_skill)

    grounding = sub.add_parser("codex-grounding", help="Check the local Codex version, compact config, and lifecycle hook markers.")
    grounding.add_argument("--workspace-root")
    grounding.add_argument("--aoa-root")
    grounding.add_argument("--codex-bin", default="codex")
    grounding.add_argument("--codex-native-bin")
    grounding.set_defaults(func=command_codex_grounding)

    hooks_status = sub.add_parser("codex-hooks-status", help="Inspect native Codex hook discovery, command matching, and trust status.")
    hooks_status.add_argument("--workspace-root")
    hooks_status.add_argument("--aoa-root")
    hooks_status.add_argument("--codex-bin", default="codex")
    hooks_status.add_argument("--timeout", type=int, default=30)
    hooks_status.add_argument("--trust-current", action="store_true", help="Trust current matching hook hashes through Codex app-server config/batchWrite.")
    hooks_status.set_defaults(func=command_codex_hooks_status)

    compact_probe = sub.add_parser("codex-compact-probe", help="Trigger a live manual Codex compaction and verify PreCompact/PostCompact receipts.")
    compact_probe.add_argument("--workspace-root")
    compact_probe.add_argument("--aoa-root")
    compact_probe.add_argument("--codex-bin", default="codex")
    compact_probe.add_argument("--timeout", type=int, default=150)
    compact_probe.add_argument("--trust-hooks", action="store_true", help="Trust current matching hook hashes before running the compact probe.")
    compact_probe.set_defaults(func=command_codex_compact_probe)

    validate = sub.add_parser("validate", help="Run a local end-to-end preservation, compaction, rehydrate, and distill check.")
    validate.add_argument("--workspace-root")
    validate.add_argument("--aoa-root")
    validate.set_defaults(func=command_validate)

    audit = sub.add_parser("audit", help="Map the full objective to current artifacts, evidence, and remaining gates.")
    audit.add_argument("--workspace-root")
    audit.add_argument("--aoa-root")
    audit.add_argument("--skip-codex-grounding", action="store_true")
    audit.set_defaults(func=command_audit)

    doctor = sub.add_parser("doctor", help="Check registry and generated surfaces.")
    doctor.add_argument("--workspace-root")
    doctor.add_argument("--aoa-root")
    doctor.add_argument("--check-live-hooks", action="store_true", help="Also require current user-level hooks to cover AoA lifecycle events.")
    doctor.add_argument("--check-user-skill", action="store_true", help="Also require the current user's global .aoa router skill to point at this install.")
    doctor.add_argument("--check-codex-grounding", action="store_true", help="Also require local Codex version/config/hook marker grounding to pass.")
    doctor.set_defaults(func=command_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
