#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
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
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 fallback uses a narrow parser below.
    tomllib = None  # type: ignore[assignment]


SCHEMA_VERSION = 1
SESSION_ROOT = Path("sessions")
DIAGNOSTICS_ROOT = Path("diagnostics")
LEGACY_SESSION_ROOT = Path("codex-sessions")
REGISTRY_NAME = "session-registry.json"
SESSION_NAME_INDEX_JSON = "session-name-index.json"
SESSION_NAME_INDEX_MARKDOWN = "SESSION_NAMES.md"
NAMING_POLICY_PATH = Path("config/naming-policy.json")
DEFAULT_BANNED_DURABLE_NAME_TERMS = {"unknown", "misc", "tmp", "new", "old", "stuff", "placeholder"}
GENERIC_TITLE_PREFIXES = (
    "files mentioned by the user",
    "context from my ide setup",
    "context from my ide",
    "<workspace_context>",
)
BATCH_DISTILLATION_POLICY_PATH = Path("config/batch-distillation-policy.json")
DEFAULT_PROJECT_GROUNDING_FILE_NAMES = ["AGENTS.md", "DESIGN.md", "README.md"]
SESSION_INDEX_MARKDOWN = "SESSION.md"
SESSION_INDEX_JSON = "session.index.json"
SESSIONS_INDEX_MARKDOWN = "INDEX.md"
SESSIONS_INDEX_JSON = "index.json"
SESSIONS_AGENTS_MARKDOWN = "AGENTS.md"
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
    "SECURITY_TOUCHPOINT",
    "SECURITY_OR_SECRET_RISK",
    "VERIFICATION",
    "FINAL_STATE",
    "HOOK_EVENT",
    "RAW_EVENT",
]

FIRST_PASS_CANDIDATE_EVENT_TYPES = {
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
FIRST_PASS_SUPPORTING_EVENT_TYPES = {
    "USER_INTENT",
    "FILE_WRITE",
    "DIFF",
    "VERIFICATION",
}

EVENT_FACETS: dict[str, dict[str, str]] = {
    "SESSION_META": {"family": "session_lifecycle", "phase": "start", "actor": "codex_runtime", "action": "initialize", "object": "session", "outcome": "observed"},
    "CONTEXT_STATE": {"family": "context_memory", "phase": "observe", "actor": "codex_runtime", "action": "report_context", "object": "context", "outcome": "observed"},
    "USER_INTENT": {"family": "communication", "phase": "request", "actor": "user", "action": "request", "object": "task", "outcome": "requested"},
    "ASSISTANT_PLAN": {"family": "agent_cognition", "phase": "plan", "actor": "assistant", "action": "reason", "object": "plan", "outcome": "planned"},
    "ASSISTANT_MESSAGE": {"family": "communication", "phase": "respond", "actor": "assistant", "action": "respond", "object": "message", "outcome": "observed"},
    "TOOL_CALL": {"family": "tool_interaction", "phase": "act", "actor": "assistant", "action": "call_tool", "object": "tool", "outcome": "requested"},
    "TOOL_OUTPUT": {"family": "tool_interaction", "phase": "observe", "actor": "tool", "action": "return_output", "object": "tool_output", "outcome": "observed"},
    "FILE_READ": {"family": "workspace_navigation", "phase": "inspect", "actor": "tool", "action": "read", "object": "file", "outcome": "observed"},
    "FILE_WRITE": {"family": "workspace_mutation", "phase": "mutate", "actor": "tool", "action": "write", "object": "file", "outcome": "changed"},
    "DIFF": {"family": "workspace_mutation", "phase": "mutate", "actor": "tool", "action": "patch", "object": "diff", "outcome": "changed"},
    "COMMAND": {"family": "command_execution", "phase": "act", "actor": "assistant", "action": "run_command", "object": "command", "outcome": "requested"},
    "COMMAND_OUTPUT": {"family": "command_execution", "phase": "observe", "actor": "tool", "action": "return_command_output", "object": "command_output", "outcome": "observed"},
    "ERROR": {"family": "failure_signal", "phase": "diagnose", "actor": "tool", "action": "report_failure", "object": "failure", "outcome": "failed"},
    "DECISION": {"family": "decision_signal", "phase": "decide", "actor": "assistant", "action": "decide", "object": "decision", "outcome": "decided"},
    "ASSUMPTION": {"family": "agent_cognition", "phase": "assume", "actor": "assistant", "action": "assume", "object": "assumption", "outcome": "provisional"},
    "CHECKPOINT": {"family": "memory_state", "phase": "checkpoint", "actor": "assistant", "action": "checkpoint", "object": "state", "outcome": "checkpointed"},
    "COMPACTION_EVENT": {"family": "context_memory", "phase": "compact", "actor": "codex_runtime", "action": "compact", "object": "context", "outcome": "compacted"},
    "RESUME_HINT": {"family": "memory_state", "phase": "rehydrate", "actor": "assistant", "action": "hint_resume", "object": "state", "outcome": "resumable"},
    "OPEN_THREAD": {"family": "progress_state", "phase": "plan", "actor": "assistant", "action": "open_thread", "object": "work", "outcome": "unresolved"},
    "DEAD_BRANCH": {"family": "progress_state", "phase": "diagnose", "actor": "assistant", "action": "abandon_branch", "object": "work", "outcome": "stopped"},
    "PROCESS_LESSON": {"family": "distillation", "phase": "distill", "actor": "assistant", "action": "learn", "object": "process", "outcome": "candidate"},
    "OPTIMIZATION_CANDIDATE": {"family": "optimization", "phase": "improve", "actor": "assistant", "action": "propose_optimization", "object": "system", "outcome": "candidate"},
    "SECURITY_TOUCHPOINT": {"family": "risk_signal", "phase": "guard", "actor": "tool", "action": "detect_touchpoint", "object": "secret_or_security", "outcome": "observed"},
    "SECURITY_OR_SECRET_RISK": {"family": "risk_signal", "phase": "guard", "actor": "assistant", "action": "detect_risk", "object": "secret_or_security", "outcome": "risk"},
    "VERIFICATION": {"family": "verification", "phase": "verify", "actor": "tool", "action": "verify", "object": "claim_or_system", "outcome": "verified"},
    "FINAL_STATE": {"family": "progress_state", "phase": "close", "actor": "assistant", "action": "closeout", "object": "work", "outcome": "completed"},
    "HOOK_EVENT": {"family": "session_lifecycle", "phase": "hook", "actor": "codex_runtime", "action": "emit_event", "object": "hook", "outcome": "observed"},
    "RAW_EVENT": {"family": "raw_evidence", "phase": "observe", "actor": "unknown", "action": "preserve", "object": "raw_event", "outcome": "observed"},
}
HOOK_EVENT_ORDER = ["SessionStart", "UserPromptSubmit", "PreCompact", "PostCompact", "Stop"]
HOOK_TIMEOUTS = {
    "SessionStart": 20,
    "UserPromptSubmit": 20,
    "PreCompact": 30,
    "PostCompact": 30,
    "Stop": 20,
}
DEFAULT_STOP_SYNC_MAX_BYTES = 4 * 1024 * 1024
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
    "DESIGN.AGENTS.md",
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
    family: str = "raw_evidence"
    phase: str = "observe"
    actor: str = "unknown"
    action: str = "preserve"
    object_ref: str = "raw_event"
    outcome: str = "observed"
    confidence: str = "medium"
    correlation_id: str | None = None
    facets: dict[str, Any] = field(default_factory=dict)


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
    slug_parts = [part for part in re.split(r"[-_.]+", slug) if part and part not in DEFAULT_BANNED_DURABLE_NAME_TERMS]
    slug = "-".join(slug_parts)
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
        for rel_name in (str(SESSION_ROOT), REGISTRY_NAME, SESSION_NAME_INDEX_JSON, SESSION_NAME_INDEX_MARKDOWN):
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
        existing_archive_dirs = session_root.exists() and any(child.is_dir() for child in session_root.iterdir())
        session_root.mkdir(parents=True, exist_ok=True)
        if existing_archive_dirs:
            existing_records = registry_sessions(target_aoa_root)
            write_session_name_index(target_aoa_root, existing_records)
            write_sessions_directory_index(target_aoa_root, existing_records)
        else:
            write_json(target_aoa_root / REGISTRY_NAME, {"schema_version": SCHEMA_VERSION, "updated_at": utc_now(), "sessions": []})
            write_session_name_index(target_aoa_root, [])
            write_sessions_directory_index(target_aoa_root, [])

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
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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


def is_empty_nonzero_command_output(raw_lower: str) -> bool:
    if not re.search(r"(process exited with code|exit code:)\s*[1-9]", raw_lower):
        return False
    if any(marker in raw_lower for marker in ("traceback", "exception", "permission denied", "no such file or directory")):
        return False
    if re.search(r"\b(error|failed|failure):", raw_lower):
        return False
    output_match = re.search(r"\boutput:\s*(.*)\Z", raw_lower, flags=re.DOTALL)
    if output_match is None:
        return False
    output = output_match.group(1).strip()
    if not output:
        return True
    return output in {"<empty>", "(empty)", "none"}


def has_success_signal(raw_lower: str) -> bool:
    if re.search(r"(process exited with code|exit code:)\s*0", raw_lower):
        return True
    if re.search(r"\b\d+\s+passed\b", raw_lower):
        return True
    if "ok=true" in raw_lower or '"ok": true' in raw_lower:
        return True
    if "success. updated the following files" in raw_lower:
        return True
    return False


def structured_payload_outcome(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    exit_code = payload.get("exit_code")
    if isinstance(exit_code, int):
        return "succeeded" if exit_code == 0 else "failed"
    if isinstance(exit_code, str) and re.fullmatch(r"-?\d+", exit_code.strip()):
        return "succeeded" if int(exit_code.strip()) == 0 else "failed"
    success = payload.get("success")
    if isinstance(success, bool):
        return "succeeded" if success else "failed"
    status = str(payload.get("status") or "").strip().lower()
    if status in {"ok", "success", "succeeded", "completed", "complete"}:
        return "succeeded"
    if status in {"error", "failed", "failure", "timeout", "cancelled", "canceled"}:
        return "failed"
    return None


def rm_rf_targets(cmd: str) -> list[str]:
    try:
        words = shlex.split(cmd)
    except ValueError:
        words = cmd.split()
    targets: list[str] = []
    idx = 0
    shell_operators = {"&&", "||", ";", "|"}
    while idx < len(words):
        if words[idx] != "rm":
            idx += 1
            continue
        idx += 1
        has_recursive_force = False
        current: list[str] = []
        while idx < len(words) and words[idx] not in shell_operators:
            word = words[idx]
            if word.startswith("-"):
                if "r" in word and "f" in word:
                    has_recursive_force = True
            else:
                current.append(word)
            idx += 1
        if has_recursive_force:
            targets.extend(current)
    return targets


def is_temporary_cleanup_command(cmd: str) -> bool:
    lowered = cmd.lower()
    cache_names = {"__pycache__", ".pytest_cache"}
    if (
        re.search(r"\bfind\b", lowered)
        and re.search(r"-exec\s+rm\s+-[a-z]*r[a-z]*f[a-z]*\s+\{\}\s+\+", lowered)
        and any(name in lowered for name in cache_names)
    ):
        return True
    targets = rm_rf_targets(cmd)
    if not targets:
        return False
    safe_prefixes = ("/tmp/", "/var/tmp/", "tmp/")
    return all(target.startswith(safe_prefixes) or Path(target.rstrip("/")).name in cache_names for target in targets)


def has_destructive_command_signal(cmd: str) -> bool:
    lowered = cmd.lower().strip()
    if re.search(r"\bgit\s+reset\s+--hard\b", lowered):
        return True
    if re.search(r"\bgit\s+checkout\s+--\b", lowered):
        return True
    return bool(rm_rf_targets(cmd)) and not is_temporary_cleanup_command(cmd)


SECURITY_POLICY_CONTEXT_PHRASES = [
    "leak check",
    "secret-leak check",
    "secret/data leak check",
    "secret leak check",
    "redaction check",
    "sanitize",
    "sanitized",
    "do not write secrets",
    "do not print or commit real secrets",
    "do not read or expose secret",
    "do not publish rendered config",
    "do not commit private host-facts",
    "no tokens",
    "no passwords",
    "not shown",
    "redacted",
    "public-safe",
    "secret-bearing",
    "нет токен",
    "нет парол",
    "не допускаются",
    "не писать секрет",
]


def is_security_policy_line(line_lower: str) -> bool:
    if not line_lower:
        return False
    if any(phrase in line_lower for phrase in SECURITY_POLICY_CONTEXT_PHRASES):
        return True
    if not re.search(r"\b(secret|api key|token|credential|password|секрет)s?\b", line_lower):
        return False
    policy_markers = [
        "do not ",
        "don't ",
        "never ",
        "must not ",
        "should not ",
        "without explicit",
        "avoid ",
        "hard no",
        "review guidelines",
        "treat the following as",
        "policy",
        "checklist",
        "не ",
        "нельзя",
        "без явн",
    ]
    return any(marker in line_lower for marker in policy_markers)


def has_security_risk_signal(text_lower: str) -> bool:
    if not text_lower:
        return False
    direct_secret_patterns = [
        r"\bsk-[a-z0-9_-]{20,}\b",
        r"\bghp_[a-z0-9_]{20,}\b",
        r"\bgithub_pat_[a-z0-9_]{20,}\b",
        r"\bxox[baprs]-[a-z0-9-]{20,}\b",
    ]
    if any(re.search(pattern, text_lower) for pattern in direct_secret_patterns):
        return True
    sensitive_terms = r"(secret|api key|token|credential|password|секрет)"
    leak_terms = r"(leak|leaked|exposed|expose|printed|dumped|committed|plaintext|plain text|утек|утеч|раскрыт)"
    log_terms = r"(console\.log|logger\.|log\(|print\(|printf\()"
    assignment_terms = r"(secret|api key|token|credential|password)\s*[:=]\s*['\"]?[a-z0-9_./+=-]{12,}"
    safe_sensitive_log_phrases = [
        "present",
        "missing",
        "configured",
        "not shown",
        "hashed",
        "hash",
        "expires",
        "expira",
    ]
    for line in text_lower.splitlines():
        if is_security_policy_line(line):
            continue
        if re.search(fr"\b{sensitive_terms}s?\b.{{0,48}}\b{leak_terms}\b", line):
            return True
        if re.search(fr"\b{leak_terms}\b.{{0,48}}\b{sensitive_terms}s?\b", line):
            return True
        if (
            re.search(log_terms, line)
            and re.search(fr"\b{sensitive_terms}s?\b", line)
            and not any(phrase in line for phrase in safe_sensitive_log_phrases)
        ):
            return True
        if re.search(assignment_terms, line):
            return True
    return False


def has_security_touchpoint_signal(text_lower: str) -> bool:
    if not text_lower:
        return False
    identifier_pattern = (
        r"\b(?:[a-z0-9]+_)+(?:secret|token|password|credential|key)\b"
        r"|\b[a-z0-9_]*(?:api_key|apikey|secret_key|client_secret|private_key|password_hash)[a-z0-9_]*\b"
        r"|\b(?:secret|token|password|credential|key)_[a-z0-9_]+\b"
    )
    phrase_pattern = (
        r"\b(api key|secret key|client secret|access token|refresh token|bearer token|session token|"
        r"email token|recovery token|password|credential|secret-bearing)s?\b"
    )
    return bool(re.search(identifier_pattern, text_lower) or re.search(phrase_pattern, text_lower))


def json_object_from_string(value: Any) -> dict[str, Any]:
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def payload_correlation_id(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    for key in ("call_id", "id", "tool_call_id"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def command_payload_args(payload: dict[str, Any]) -> dict[str, Any]:
    return json_object_from_string(payload.get("arguments"))


def command_text_from_payload(payload: dict[str, Any]) -> str:
    args = command_payload_args(payload)
    for key in ("cmd", "command", "shell_command"):
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def command_classifier(cmd: str) -> dict[str, Any]:
    lowered = cmd.lower().strip()
    tags: set[str] = set()
    facets: dict[str, Any] = {"command": cmd} if cmd else {}
    if not lowered:
        return {"event_type": "COMMAND", "tags": [], "facets": facets}

    first = lowered.split(maxsplit=1)[0]
    tags.add(f"command:{first}")
    read_patterns = [
        r"^(rg|grep|sed|cat|head|tail|nl|wc|jq|find|ls|tree)\b",
        r"^git\s+(status|diff|show|log|grep|ls-files)\b",
        r"^python3?\s+.*\b(show|list|audit|doctor|codex-hooks-status)\b",
    ]
    write_patterns = [
        r"^(mkdir|cp|mv|touch)\b",
        r"^git\s+(add|commit|push|mv|rm)\b",
    ]
    verify_patterns = [
        r"\b(pytest|unittest|py_compile|mypy|ruff|eslint|tsc|vitest|cargo\s+test|go\s+test)\b",
        r"\bdoctor\b",
        r"\baudit\b",
        r"\bcodex-hooks-status\b",
        r"\bgit\s+diff\s+--check\b",
    ]
    if rm_rf_targets(cmd) and is_temporary_cleanup_command(cmd):
        tags.add("temporary_cleanup_command")
        return {"event_type": "FILE_WRITE", "tags": sorted(tags), "facets": {**facets, "command_kind": "temporary_cleanup"}}
    if has_destructive_command_signal(cmd):
        tags.add("destructive_command_signal")
        return {"event_type": "SECURITY_OR_SECRET_RISK", "tags": sorted(tags), "facets": {**facets, "command_kind": "destructive"}}
    if any(re.search(pattern, lowered) for pattern in verify_patterns):
        tags.add("verification_command")
        return {"event_type": "COMMAND", "tags": sorted(tags), "facets": {**facets, "command_kind": "verification"}}
    if any(re.search(pattern, lowered) for pattern in read_patterns):
        tags.add("file_read_command")
        return {"event_type": "FILE_READ", "tags": sorted(tags), "facets": {**facets, "command_kind": "read"}}
    if any(re.search(pattern, lowered) for pattern in write_patterns):
        tags.add("file_write_command")
        return {"event_type": "FILE_WRITE", "tags": sorted(tags), "facets": {**facets, "command_kind": "write"}}
    return {"event_type": "COMMAND", "tags": sorted(tags), "facets": {**facets, "command_kind": "generic"}}


def event_facets_for_type(event_type: str) -> dict[str, str]:
    return dict(EVENT_FACETS.get(event_type, EVENT_FACETS["RAW_EVENT"]))


def is_first_pass_candidate_event_record(event: dict[str, Any]) -> bool:
    event_type = str(event.get("type") or "RAW_EVENT")
    if event_type in FIRST_PASS_CANDIDATE_EVENT_TYPES or event_type in FIRST_PASS_SUPPORTING_EVENT_TYPES:
        return True
    tags = {str(tag) for tag in event.get("tags", [])} if isinstance(event.get("tags"), list) else set()
    if event_type == "COMMAND" and "verification_command" in tags:
        return True
    if event_type == "COMMAND_OUTPUT" and str(event.get("outcome") or "") == "failed":
        return True
    return False


def semantic_text_for_classification(source_type: str, payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    if source_type == "session_meta":
        return ""
    if source_type == "compacted":
        return text_from_content(payload.get("summary")) or "context compacted"
    if source_type == "turn_context":
        return text_from_content(payload.get("summary"))
    if source_type == "event_msg":
        for key in ("prompt", "user_prompt", "message", "content", "summary"):
            text = text_from_content(payload.get(key))
            if text:
                return text
        return str(payload.get("type") or "")
    if source_type == "response_item":
        item_type = str(payload.get("type") or "")
        if item_type == "message":
            return text_from_content(payload.get("content"))
        if item_type in {"function_call", "tool_call"}:
            return command_text_from_payload(payload) or str(payload.get("name") or payload.get("tool_name") or "")
        if item_type in {"function_call_output", "tool_call_output"}:
            return text_from_content(payload.get("output"))
        if item_type == "reasoning":
            return text_from_content(payload.get("summary")) or text_from_content(payload.get("content"))
    return ""


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
    semantic_text = semantic_text_for_classification(source_type, payload)
    semantic_lower = semantic_text.lower()
    tags: set[str] = {source_type}
    event_type = "RAW_EVENT"
    title = source_type
    importance = "medium"
    facets: dict[str, Any] = {}
    outcome_override: str | None = None
    correlation_id = payload_correlation_id(payload)
    structured_outcome = structured_payload_outcome(payload)

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
        facets["payload_type"] = item_type
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
            elif role in {"developer", "system"}:
                event_type = "CONTEXT_STATE"
                title = f"{role.title()} instruction"
                tags.update(["instruction", "context"])
                importance = "high"
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
                command_info = command_classifier(command_text_from_payload(payload))
                event_type = str(command_info.get("event_type") or "COMMAND")
                tags.update(str(tag) for tag in command_info.get("tags", []) if str(tag))
                facets.update(command_info.get("facets", {}) if isinstance(command_info.get("facets"), dict) else {})
                tags.add("command")
            elif tool_name == "apply_patch":
                event_type = "DIFF"
                tags.update(["patch", "file_write"])
        elif item_type in {"function_call_output", "tool_call_output"}:
            event_type = "TOOL_OUTPUT"
            title = f"Tool output: {short_text(payload.get('call_id'), max_chars=80)}"
            tags.add("tool_output")
            importance = "high"
            output_lower = semantic_lower or raw_lower
            if "process exited" in output_lower or "stdout" in output_lower or "stderr" in output_lower:
                event_type = "COMMAND_OUTPUT"
                tags.add("command_output")
                if has_success_signal(output_lower):
                    outcome_override = "succeeded"
            elif "success. updated the following files" in output_lower or "apply_patch" in output_lower:
                event_type = "DIFF"
                tags.update(["patch", "file_write"])
                outcome_override = "changed"
        elif item_type == "reasoning":
            event_type = "ASSISTANT_PLAN"
            title = "Assistant reasoning item"
            tags.add("reasoning")
        else:
            title = f"Response item: {item_type}"
    elif source_type == "event_msg" and isinstance(payload, dict):
        event_type = "HOOK_EVENT"
        msg_type = str(payload.get("type") or "event")
        facets["message_type"] = msg_type
        title = f"Event message: {msg_type}"
        tags.add(msg_type)
        if msg_type == "user_message":
            event_type = "USER_INTENT"
            importance = "high"
        elif msg_type == "agent_message":
            event_type = "ASSISTANT_MESSAGE"
            tags.add("message_stream")
        elif msg_type == "exec_command_begin":
            event_type = "COMMAND"
            title = "Command started"
            tags.update(["command", "command_lifecycle"])
            command = payload.get("command")
            if isinstance(command, list):
                facets["command"] = " ".join(str(part) for part in command)
            importance = "medium"
        elif msg_type == "exec_command_end":
            event_type = "COMMAND_OUTPUT"
            title = "Command finished"
            tags.update(["command_output", "command_lifecycle"])
            if structured_outcome == "succeeded":
                tags.add("success_signal")
                outcome_override = "succeeded"
            elif structured_outcome == "failed":
                tags.add("error_signal")
                outcome_override = "failed"
            importance = "medium"
        elif msg_type == "patch_apply_begin":
            event_type = "DIFF"
            title = "Patch apply started"
            tags.update(["patch", "file_write", "patch_lifecycle"])
            importance = "medium"
        elif msg_type == "patch_apply_end":
            event_type = "DIFF"
            title = "Patch apply finished"
            tags.update(["patch", "file_write", "patch_lifecycle"])
            if structured_outcome == "succeeded":
                tags.add("success_signal")
                outcome_override = "changed"
            elif structured_outcome == "failed":
                tags.add("error_signal")
                outcome_override = "failed"
            importance = "medium"
        elif msg_type == "context_compacted":
            event_type = "COMPACTION_EVENT"
            title = "Codex context compacted event message"
            tags.update(["compaction", "context_compacted"])
            importance = "critical"
        elif msg_type == "token_count":
            event_type = "CONTEXT_STATE"
            tags.add("token_count")
    broad_diagnostic_scan = source_type == "response_item" and payload_type in {"function_call_output", "tool_call_output"}
    diagnostic_lower = raw_lower if broad_diagnostic_scan else semantic_lower
    if broad_diagnostic_scan and event_type in {"TOOL_OUTPUT", "COMMAND_OUTPUT"} and is_empty_nonzero_command_output(semantic_lower or diagnostic_lower):
        tags.add("empty_nonzero_output_signal")
        event_type = "COMMAND_OUTPUT"
        outcome_override = "failed"
    elif structured_outcome == "failed" and broad_diagnostic_scan:
        tags.add("error_signal")
        if event_type in {"RAW_EVENT", "TOOL_OUTPUT", "COMMAND_OUTPUT"}:
            event_type = "ERROR"
            importance = "high"
            outcome_override = "failed"
    elif has_error_signal(diagnostic_lower):
        tags.add("error_signal")
        if event_type in {"RAW_EVENT", "TOOL_OUTPUT", "COMMAND_OUTPUT", "HOOK_EVENT"}:
            event_type = "ERROR"
            importance = "high"
            outcome_override = "failed"
    elif event_type in {"COMMAND_OUTPUT", "TOOL_OUTPUT"} and has_success_signal(diagnostic_lower):
        tags.add("success_signal")
        outcome_override = "succeeded"
        if re.search(r"\b\d+\s+passed\b", diagnostic_lower) or "ok=true" in diagnostic_lower or '"ok": true' in diagnostic_lower:
            event_type = "VERIFICATION"
            importance = "high"
    signal_lower = semantic_lower
    semantic_signal_promotable = (
        source_type == "response_item"
        and isinstance(payload, dict)
        and str(payload.get("type") or "") == "message"
        and str(payload.get("role") or "") == "assistant"
    )
    semantic_signal_taggable = False
    user_intent_taggable = False
    if isinstance(payload, dict):
        payload_kind = str(payload.get("type") or "")
        payload_role = str(payload.get("role") or "")
        semantic_signal_taggable = (
            source_type == "response_item"
            and payload_kind == "message"
            and payload_role == "assistant"
        ) or (
            source_type == "event_msg"
            and payload_kind == "agent_message"
        )
        user_intent_taggable = (
            source_type == "response_item"
            and payload_kind == "message"
            and payload_role == "user"
        ) or (
            source_type == "event_msg"
            and payload_kind == "user_message"
        )
    if semantic_signal_taggable and ("decision" in signal_lower or "решили" in signal_lower or "вердикт" in signal_lower):
        tags.add("decision_signal")
        if semantic_signal_promotable and event_type == "ASSISTANT_MESSAGE":
            event_type = "DECISION"
            importance = "high"
    if semantic_signal_taggable and ("assumption" in signal_lower or "предполож" in signal_lower):
        tags.add("assumption_signal")
        if semantic_signal_promotable and event_type == "ASSISTANT_MESSAGE":
            event_type = "ASSUMPTION"
            importance = "high"
    if semantic_signal_taggable and ("open thread" in signal_lower or "follow-up" in signal_lower or "todo" in signal_lower or "осталось" in signal_lower):
        tags.add("open_thread_signal")
        if semantic_signal_promotable and event_type == "ASSISTANT_MESSAGE":
            event_type = "OPEN_THREAD"
            importance = "high"
    if semantic_signal_taggable and ("process lesson" in signal_lower or "lesson" in signal_lower or "вывод" in signal_lower):
        tags.add("lesson_signal")
        if semantic_signal_promotable and event_type == "ASSISTANT_MESSAGE":
            event_type = "PROCESS_LESSON"
            importance = "high"
    security_risk = has_security_risk_signal(signal_lower)
    if security_risk:
        tags.add("security_signal")
        if event_type in {"ASSISTANT_MESSAGE", "TOOL_OUTPUT", "COMMAND_OUTPUT", "RAW_EVENT"}:
            event_type = "SECURITY_OR_SECRET_RISK"
            importance = "critical"
    security_policy_taggable = semantic_signal_taggable or user_intent_taggable or (
        source_type == "response_item"
        and isinstance(payload, dict)
        and str(payload.get("type") or "") == "message"
        and str(payload.get("role") or "") in {"developer", "system"}
    )
    security_touchpoint_taggable = (
        source_type == "response_item"
        and isinstance(payload, dict)
        and str(payload.get("type") or "") in {"message", "function_call_output", "tool_call_output"}
    )
    if not security_risk and security_policy_taggable and (
        "secret" in signal_lower
        or "api key" in signal_lower
        or "token" in signal_lower
        or "credential" in signal_lower
        or "секрет" in signal_lower
    ):
        tags.add("security_policy_signal")
    if not security_risk and security_touchpoint_taggable and has_security_touchpoint_signal(signal_lower):
        tags.add("security_touchpoint_signal")
        if event_type in {"ASSISTANT_MESSAGE", "TOOL_OUTPUT", "COMMAND_OUTPUT", "RAW_EVENT"}:
            event_type = "SECURITY_TOUCHPOINT"
            importance = "high"
    if semantic_signal_taggable and ("checkpoint" in signal_lower or "чекпо" in signal_lower):
        tags.add("checkpoint")
        if semantic_signal_promotable and event_type == "ASSISTANT_MESSAGE":
            event_type = "CHECKPOINT"
            importance = "high"
    if semantic_signal_taggable and ("final" in signal_lower or "итог" in signal_lower or "готово" in signal_lower):
        tags.add("final_state_signal")
        if semantic_signal_promotable and event_type == "ASSISTANT_MESSAGE":
            event_type = "FINAL_STATE"
            importance = "high"
    if source_type == "compacted" or payload_has_compaction_boundary(payload):
        tags.add("compaction")

    compaction_boundary = event_type == "COMPACTION_EVENT" and (
        source_type == "compacted"
        or payload_has_compaction_boundary(payload)
        or "compact" in signal_lower
        or "summary" in signal_lower
        or "сжати" in signal_lower
    )

    canonical_event_type = event_type if event_type in EVENT_TYPE_ORDER else "RAW_EVENT"
    universal = event_facets_for_type(canonical_event_type)
    if outcome_override:
        universal["outcome"] = outcome_override
    confidence = "high" if canonical_event_type != "RAW_EVENT" else "medium"

    return RawEvent(
        event_id=event_id,
        line_no=line_no,
        raw=raw,
        parsed=parsed,
        event_type=canonical_event_type,
        source_type=source_type,
        title=title,
        timestamp=timestamp,
        tags=sorted(tag for tag in tags if tag),
        importance=importance,
        compaction_boundary=compaction_boundary,
        family=universal["family"],
        phase=universal["phase"],
        actor=universal["actor"],
        action=universal["action"],
        object_ref=universal["object"],
        outcome=universal["outcome"],
        confidence=confidence,
        correlation_id=correlation_id,
        facets=facets,
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
    if weak_title_text(stripped):
        return False
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


def weak_title_text(text: str) -> bool:
    compact = re.sub(r"\s+", " ", text.strip())
    if not compact:
        return True
    lowered = compact.lower()
    normalized = re.sub(r"^[#>\-\s]+", "", lowered).strip()
    first_line = text.strip().splitlines()[0].strip().lower()
    normalized_first_line = re.sub(r"^[#>\-\s]+", "", first_line).strip()
    if any(lowered.startswith(prefix) or first_line.startswith(prefix) for prefix in GENERIC_TITLE_PREFIXES):
        return True
    if any(normalized.startswith(prefix) or normalized_first_line.startswith(prefix) for prefix in GENERIC_TITLE_PREFIXES):
        return True
    if first_line in {"untitled session", "codex session", "new session"}:
        return True
    return False


def weak_label_text(label: str) -> bool:
    lowered = label.lower()
    return any(readable_slug(prefix, max_chars=80) in lowered for prefix in GENERIC_TITLE_PREFIXES)


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


def semantic_name_slug(value: str) -> str:
    return readable_slug(value, fallback="semantic-session-name", max_chars=80)


def semantic_name_scope(item: dict[str, Any]) -> str:
    scope = str(item.get("scope") or "").strip()
    if scope in {"session", "phase", "topic", "alias"}:
        return scope
    kind = str(item.get("kind") or "")
    if kind in {"session_essence", "operator_name"}:
        return "session"
    if kind in {"dominant_topic", "continuation_name"}:
        return "phase"
    return "topic"


def semantic_name_status_for_scope(scope: str) -> str:
    return "active" if scope == "session" else scope


def count_file_lines(path: Path) -> int:
    count = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            count += chunk.count(b"\n")
    return count


def semantic_names_payload(manifest: dict[str, Any]) -> dict[str, Any]:
    payload = manifest.get("semantic_names")
    if not isinstance(payload, dict):
        return {"schema_version": SCHEMA_VERSION, "active": None, "active_session": None, "names": []}
    names = [item for item in payload.get("names", []) if isinstance(item, dict)]
    active = payload.get("active")
    if not active and names:
        active = names[0].get("slug")
    active_session = payload.get("active_session")
    if not active_session:
        for item in names:
            if semantic_name_scope(item) == "session" and item.get("status") == "active":
                active_session = item.get("slug")
                break
    if not active_session and active:
        for item in names:
            if item.get("slug") == active and semantic_name_scope(item) == "session":
                active_session = active
                break
    return {
        "schema_version": int(payload.get("schema_version", SCHEMA_VERSION) or SCHEMA_VERSION),
        "active": str(active) if active else None,
        "active_session": str(active_session) if active_session else None,
        "names": names,
    }


def active_semantic_name(manifest: dict[str, Any], *, scope: str | None = None) -> dict[str, Any] | None:
    payload = semantic_names_payload(manifest)
    active = payload.get("active_session") if scope == "session" else payload.get("active")
    names = payload.get("names", [])
    for item in names:
        if item.get("slug") == active and (scope is None or semantic_name_scope(item) == scope):
            return item
    if scope is not None:
        scoped = [item for item in names if semantic_name_scope(item) == scope]
        return scoped[0] if scoped else None
    return names[0] if names else None


def semantic_name_summary(manifest: dict[str, Any], *, scope: str | None = None) -> dict[str, Any] | None:
    active = active_semantic_name(manifest, scope=scope)
    if not active:
        return None
    return {
        "name": active.get("name"),
        "slug": active.get("slug"),
        "scope": semantic_name_scope(active),
        "kind": active.get("kind"),
        "status": active.get("status"),
        "source": active.get("source"),
    }


def build_identity_anchor(
    session_dir: Path,
    manifest: dict[str, Any],
    *,
    verify_raw_hash: bool = False,
) -> dict[str, Any]:
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
    raw_path_value = raw.get("path") or session_dir / "raw" / "session.raw.jsonl"
    raw_path = Path(str(raw_path_value))
    raw_sha256 = raw.get("sha256")
    raw_bytes = raw.get("bytes")
    raw_line_count = raw.get("line_count")
    verified_at: str | None = None
    if verify_raw_hash:
        if not raw_path.exists():
            raise ValueError(f"raw archive is missing: {raw_path}")
        actual_sha = sha256_file(raw_path)
        if raw_sha256 and str(raw_sha256) != actual_sha:
            raise ValueError(f"raw sha256 mismatch for {raw_path}")
        raw_sha256 = actual_sha
        raw_bytes = raw_path.stat().st_size
        if raw_line_count is None:
            raw_line_count = count_file_lines(raw_path)
        verified_at = utc_now()
    elif raw_path.exists():
        raw_bytes = raw_bytes if raw_bytes is not None else raw_path.stat().st_size

    anchor = {
        "schema_version": SCHEMA_VERSION,
        "session_id": manifest.get("session_id"),
        "canonical_label": display.get("label") or manifest.get("session_label") or session_dir.name,
        "archive_path": str(session_dir),
        "raw_path": str(raw_path),
        "source_transcript_path": source.get("transcript_path"),
        "raw_sha256": raw_sha256,
        "raw_bytes": raw_bytes,
        "raw_line_count": raw_line_count,
    }
    if verified_at:
        anchor["verified_at"] = verified_at
    return anchor


def semantic_name_identity_lines(manifest: dict[str, Any]) -> list[str]:
    payload = semantic_names_payload(manifest)
    names = payload.get("names", [])
    if not names:
        return []
    active = str(payload.get("active") or "")
    active_session = str(payload.get("active_session") or "")
    lines = [f"- semantic_active_session: `{active_session}`"]
    if active and active != active_session:
        lines.append(f"- semantic_active: `{active}`")
    for item in names:
        status = str(item.get("status") or "")
        kind = str(item.get("kind") or "")
        scope = semantic_name_scope(item)
        slug = str(item.get("slug") or "")
        name = str(item.get("name") or "")
        if slug == active_session:
            prefix = "active session name"
        elif slug == active:
            prefix = "active semantic name"
        else:
            prefix = "semantic name"
        coverage = item.get("coverage") if isinstance(item.get("coverage"), dict) else {}
        coverage_note = str(coverage.get("note") or "")
        coverage_suffix = f" - {coverage_note}" if coverage_note else ""
        lines.append(f"- {prefix}: `{slug}` ({scope}, {kind}, {status}) - {name}{coverage_suffix}")
    return lines


def refresh_semantic_name_anchors(
    session_dir: Path,
    manifest: dict[str, Any],
    *,
    verify_raw_hash: bool = False,
) -> None:
    payload = semantic_names_payload(manifest)
    names = payload.get("names", [])
    if not names:
        return
    anchor = build_identity_anchor(session_dir, manifest, verify_raw_hash=verify_raw_hash)
    refreshed_at = utc_now()
    for item in names:
        prior = item.get("anchor") if isinstance(item.get("anchor"), dict) else {}
        item["anchor"] = {
            **prior,
            **anchor,
            "anchored_at": prior.get("anchored_at") or item.get("created_at") or refreshed_at,
            "refreshed_at": refreshed_at,
        }
    manifest["semantic_names"] = payload


def validate_semantic_name_record(
    manifest: dict[str, Any],
    session_dir: Path,
    item: dict[str, Any],
    *,
    banned_terms: set[str] | None = None,
) -> list[str]:
    problems: list[str] = []
    name = str(item.get("name") or "").strip()
    slug = str(item.get("slug") or "").strip()
    scope = semantic_name_scope(item)
    if not name:
        problems.append("semantic_name_missing_name")
    if not slug:
        problems.append("semantic_name_missing_slug")
    elif slug != semantic_name_slug(name):
        problems.append(f"semantic_name_slug_mismatch:{slug}")
    raw_name_terms = {term for term in re.split(r"[^\w]+", name.lower(), flags=re.UNICODE) if term}
    bad_terms = (name_terms(slug) | raw_name_terms) & banned_terms if banned_terms else set()
    if bad_terms:
        problems.append(f"semantic_name_banned_terms:{sorted(bad_terms)}")
    if scope not in {"session", "phase", "topic", "alias"}:
        problems.append(f"semantic_name_invalid_scope:{scope}")
    coverage = item.get("coverage") if isinstance(item.get("coverage"), dict) else {}
    raw_ranges = coverage.get("raw_ranges") if isinstance(coverage.get("raw_ranges"), list) else []
    evidence = item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        problems.append(f"semantic_name_missing_evidence:{slug or name}")
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    raw_line_count = raw.get("line_count")
    for ref in evidence if isinstance(evidence, list) else []:
        ref_text = str(ref)
        match = re.fullmatch(r"raw:line:(\d+)(?:-(\d+))?", ref_text)
        if not match:
            problems.append(f"semantic_name_invalid_evidence_ref:{ref_text}")
            continue
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start <= 0 or end < start:
            problems.append(f"semantic_name_invalid_evidence_range:{ref_text}")
        if raw_line_count is not None and end > int(raw_line_count):
            problems.append(f"semantic_name_evidence_out_of_range:{ref_text}>{raw_line_count}")
    for raw_range in raw_ranges:
        if not isinstance(raw_range, dict):
            problems.append(f"semantic_name_invalid_coverage_range:{slug or name}")
            continue
        start = int(raw_range.get("from_line") or 0)
        end = int(raw_range.get("to_line") or 0)
        if start <= 0 or end < start:
            problems.append(f"semantic_name_invalid_coverage_range:{slug or name}")
        if raw_line_count is not None and end > int(raw_line_count):
            problems.append(f"semantic_name_coverage_out_of_range:{slug or name}:{end}>{raw_line_count}")
    anchor = item.get("anchor") if isinstance(item.get("anchor"), dict) else {}
    if not anchor:
        problems.append(f"semantic_name_missing_anchor:{slug or name}")
    else:
        if anchor.get("session_id") != manifest.get("session_id"):
            problems.append(f"semantic_name_anchor_session_mismatch:{slug or name}")
        display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
        label = display.get("label") or manifest.get("session_label") or session_dir.name
        if anchor.get("canonical_label") != label:
            problems.append(f"semantic_name_anchor_label_mismatch:{slug or name}")
        raw_path = str(raw.get("path") or session_dir / "raw" / "session.raw.jsonl")
        if anchor.get("raw_path") != raw_path:
            problems.append(f"semantic_name_anchor_raw_path_mismatch:{slug or name}")
        raw_sha = raw.get("sha256")
        if raw_sha and anchor.get("raw_sha256") and anchor.get("raw_sha256") != raw_sha:
            problems.append(f"semantic_name_anchor_raw_sha_mismatch:{slug or name}")
    return problems


def transcript_probe(raw_path: Path) -> dict[str, Any]:
    sample_events = parse_raw_event_sample(raw_path, max_lines=400)
    event: dict[str, Any] = {"transcript_path": str(raw_path)}
    for raw_event in sample_events[:40]:
        parsed = raw_event.parsed
        if not isinstance(parsed, dict):
            continue
        payload = parsed.get("payload")
        if parsed.get("type") == "session_meta" and isinstance(payload, dict):
            if payload.get("id"):
                event["session_id"] = payload.get("id")
            if payload.get("cwd"):
                event["cwd"] = payload.get("cwd")
            if payload.get("timestamp"):
                event["timestamp"] = payload.get("timestamp")
            for key in ("model", "model_provider", "cli_version"):
                if payload.get(key):
                    event[key] = payload.get(key)
            break
    fallback = datetime.fromtimestamp(raw_path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%d")
    session_date = first_session_date(sample_events, event, raw_path, fallback)
    title, title_source = session_title(sample_events, event, raw_path)
    session_id = session_id_from(event, raw_path)
    return {
        "session_id": session_id,
        "transcript_path": str(raw_path),
        "session_date": session_date,
        "title": title,
        "title_source": title_source,
        "cwd": event.get("cwd"),
        "timestamp": event.get("timestamp"),
        "model": event.get("model"),
        "model_provider": event.get("model_provider"),
        "cli_version": event.get("cli_version"),
        "bytes": raw_path.stat().st_size,
        "mtime": datetime.fromtimestamp(raw_path.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def parse_date_arg(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)", value)
    if not match:
        raise ValueError(f"expected date like YYYY-MM-DD, got {value!r}")
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def since_date_from_args(since: str | None, since_days: int | None) -> str | None:
    explicit = parse_date_arg(since)
    if explicit:
        return explicit
    if since_days is None:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%d")


def discover_codex_transcripts(
    *,
    source_root: Path,
    since: str | None = None,
    until: str | None = None,
) -> list[dict[str, Any]]:
    source_root = source_root.expanduser()
    if not source_root.exists():
        return []
    since_date = parse_date_arg(since)
    until_date = parse_date_arg(until)
    records: list[dict[str, Any]] = []
    for raw_path in sorted(source_root.rglob("*.jsonl")):
        if not raw_path.is_file():
            continue
        record = transcript_probe(raw_path)
        session_date = str(record.get("session_date") or "")
        if since_date and session_date < since_date:
            continue
        if until_date and session_date > until_date:
            continue
        records.append(record)
    records.sort(key=lambda item: (str(item.get("session_date") or ""), str(item.get("timestamp") or ""), str(item.get("transcript_path") or "")))
    return records


def existing_archive_by_session_id(aoa_root: Path) -> dict[str, dict[str, Any]]:
    registry = read_json(aoa_root / REGISTRY_NAME, {"sessions": []})
    sessions = registry.get("sessions", []) if isinstance(registry, dict) else []
    by_id: dict[str, dict[str, Any]] = {}
    for item in sessions if isinstance(sessions, list) else []:
        if isinstance(item, dict) and item.get("session_id"):
            by_id[str(item["session_id"])] = item
    return by_id


def import_codex_sessions(
    *,
    aoa_root: Path,
    source_root: Path,
    since: str | None = None,
    until: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    limit: int | None = None,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    records = discover_codex_transcripts(source_root=source_root, since=since, until=until)
    existing = existing_archive_by_session_id(aoa_root)
    results: list[dict[str, Any]] = []
    selected = records[:limit] if limit is not None else records
    counts: Counter[str] = Counter()
    for record in selected:
        session_id = str(record["session_id"])
        prior = existing.get(session_id)
        should_skip = bool(prior and prior.get("archive_status") == "indexed" and not force)
        if should_skip:
            status = "skipped_existing"
            result = {**record, "status": status, "archive_path": prior.get("path"), "segment_count": prior.get("segment_count")}
        elif dry_run:
            status = "planned"
            result = {**record, "status": status}
        else:
            event = {
                "session_id": session_id,
                "transcript_path": record["transcript_path"],
                "cwd": record.get("cwd"),
                "timestamp": record.get("timestamp"),
                "model": record.get("model"),
                "hook_event_name": "HistoricalImport",
            }
            try:
                sync_payload = sync_session_from_transcript(
                    aoa_root=aoa_root,
                    event=event,
                    transcript_path=Path(str(record["transcript_path"])),
                    hook_event_name="HistoricalImport",
                )
                status = "imported"
                result = {**record, "status": status, **sync_payload}
                existing[session_id] = {"archive_status": "indexed", "path": sync_payload.get("session_dir")}
            except Exception as exc:
                status = "error"
                result = {**record, "status": status, "error": f"{exc.__class__.__name__}: {exc}"}
        counts[status] += 1
        results.append(result)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now,
        "ok": counts.get("error", 0) == 0,
        "aoa_root": str(aoa_root),
        "source_root": str(source_root.expanduser()),
        "since": since,
        "until": until,
        "dry_run": dry_run,
        "force": force,
        "limit": limit,
        "discovered_count": len(records),
        "selected_count": len(selected),
        "counts": dict(counts),
        "results": results,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        report_json = diagnostics_dir / f"{compact_stamp()}__codex-session-import.json"
        report_md = report_json.with_suffix(".md")
        write_json(report_json, payload)
        write_markdown(report_md, codex_session_import_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def codex_session_import_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Codex Session Import",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- source_root: `{payload.get('source_root')}`",
        f"- aoa_root: `{payload.get('aoa_root')}`",
        f"- since: `{payload.get('since')}`",
        f"- until: `{payload.get('until')}`",
        f"- dry_run: `{payload.get('dry_run')}`",
        f"- discovered_count: `{payload.get('discovered_count')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- counts: `{json.dumps(payload.get('counts', {}), ensure_ascii=False)}`",
        "",
        "| status | date | session | title | archive |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in payload.get("results", []) if isinstance(payload.get("results"), list) else []:
        if not isinstance(result, dict):
            continue
        archive = result.get("session_dir") or result.get("archive_path") or ""
        lines.append(
            "| {status} | {date} | `{session}` | {title} | `{archive}` |".format(
                status=str(result.get("status") or ""),
                date=str(result.get("session_date") or ""),
                session=str(result.get("session_id") or ""),
                title=str(result.get("title") or "").replace("|", "\\|"),
                archive=str(archive),
            )
        )
    lines.append("")
    return "\n".join(lines)


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
    refresh_semantic_name_anchors(session_dir, manifest)


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


def event_relationships(events: list[RawEvent]) -> dict[str, list[dict[str, Any]]]:
    relationships: dict[str, list[dict[str, Any]]] = {event.event_id: [] for event in events}
    by_correlation: dict[str, list[RawEvent]] = defaultdict(list)
    for idx, event in enumerate(events):
        if idx > 0:
            relationships[event.event_id].append({"rel": "previous_event", "event_id": events[idx - 1].event_id})
        if idx + 1 < len(events):
            relationships[event.event_id].append({"rel": "next_event", "event_id": events[idx + 1].event_id})
        if event.correlation_id:
            by_correlation[event.correlation_id].append(event)

    for correlation_id, related in by_correlation.items():
        calls = [
            event
            for event in related
            if event.facets.get("payload_type") in {"function_call", "tool_call"}
        ]
        outputs = [
            event
            for event in related
            if event.facets.get("payload_type") in {"function_call_output", "tool_call_output"}
        ]
        for call in calls:
            for output in outputs:
                if call.event_id == output.event_id:
                    continue
                relationships[call.event_id].append({"rel": "answered_by", "event_id": output.event_id, "correlation_id": correlation_id})
                relationships[output.event_id].append({"rel": "responds_to", "event_id": call.event_id, "correlation_id": correlation_id})
    return relationships


def event_index_record(event: RawEvent, md_name: str, relationships: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    record = {
        "event_id": event.event_id,
        "line": event.line_no,
        "type": event.event_type,
        "family": event.family,
        "phase": event.phase,
        "actor": event.actor,
        "action": event.action,
        "object": event.object_ref,
        "outcome": event.outcome,
        "confidence": event.confidence,
        "title": event.title,
        "importance": event.importance,
        "tags": event.tags,
        "md_anchor": f"{md_name}#{anchor_for(event)}",
        "raw_ref": f"raw:line:{event.line_no}",
        "timestamp": event.timestamp,
        "source_type": event.source_type,
    }
    if event.correlation_id:
        record["correlation_id"] = event.correlation_id
    if event.facets:
        record["facets"] = event.facets
    if relationships:
        record["relationships"] = relationships
    return record


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
                f"- family: {event.family}",
                f"- phase: {event.phase}",
                f"- actor: {event.actor}",
                f"- action: {event.action}",
                f"- object: {event.object_ref}",
                f"- outcome: {event.outcome}",
                f"- refs: raw:line:{event.line_no}",
                f"- correlation_id: {event.correlation_id or ''}",
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

    relationship_map = event_relationships(events)
    records = [event_index_record(event, md_name, relationship_map.get(event.event_id, [])) for event in events]
    by_type: dict[str, list[str]] = defaultdict(list)
    by_tag: dict[str, list[str]] = defaultdict(list)
    by_source_type: dict[str, list[str]] = defaultdict(list)
    by_family: dict[str, list[str]] = defaultdict(list)
    by_phase: dict[str, list[str]] = defaultdict(list)
    by_actor: dict[str, list[str]] = defaultdict(list)
    by_action: dict[str, list[str]] = defaultdict(list)
    by_outcome: dict[str, list[str]] = defaultdict(list)
    by_correlation: dict[str, list[str]] = defaultdict(list)
    for event in events:
        by_type[event.event_type].append(event.event_id)
        by_source_type[event.source_type].append(event.event_id)
        by_family[event.family].append(event.event_id)
        by_phase[event.phase].append(event.event_id)
        by_actor[event.actor].append(event.event_id)
        by_action[event.action].append(event.event_id)
        by_outcome[event.outcome].append(event.event_id)
        if event.correlation_id:
            by_correlation[event.correlation_id].append(event.event_id)
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
        "by_family": dict(sorted(by_family.items())),
        "by_phase": dict(sorted(by_phase.items())),
        "by_actor": dict(sorted(by_actor.items())),
        "by_action": dict(sorted(by_action.items())),
        "by_outcome": dict(sorted(by_outcome.items())),
        "by_correlation": dict(sorted(by_correlation.items())),
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
    family_counts = dict(sorted(Counter(event.family for event in events).items()))
    phase_counts = dict(sorted(Counter(event.phase for event in events).items()))
    actor_counts = dict(sorted(Counter(event.actor for event in events).items()))
    outcome_counts = dict(sorted(Counter(event.outcome for event in events).items()))
    display = manifest.get("display", {}) if isinstance(manifest.get("display"), dict) else {}
    semantic_names = semantic_names_payload(manifest)
    session_index_json = {
        "schema_version": SCHEMA_VERSION,
        "session_id": manifest["session_id"],
        "display": display,
        "semantic_names": semantic_names,
        "updated_at": manifest["updated_at"],
        "archive_status": manifest["archive_status"],
        "distillation_status": manifest.get("distillation_status", "raw_archived"),
        "event_count": len(events),
        "event_counts": by_type,
        "family_counts": family_counts,
        "phase_counts": phase_counts,
        "actor_counts": actor_counts,
        "outcome_counts": outcome_counts,
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
        *semantic_name_identity_lines(manifest),
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
    lines.extend(["", "## Universal Facets", ""])
    lines.append("### Families")
    for family, count in family_counts.items():
        lines.append(f"- `{family}`: {count}")
    lines.append("")
    lines.append("### Phases")
    for phase, count in phase_counts.items():
        lines.append(f"- `{phase}`: {count}")
    lines.append("")
    lines.append("### Outcomes")
    for outcome, count in outcome_counts.items():
        lines.append(f"- `{outcome}`: {count}")
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
            session_index["semantic_names"] = semantic_names_payload(manifest)
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
            *semantic_name_identity_lines(manifest),
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
    if isinstance(existing.get("semantic_names"), dict):
        manifest["semantic_names"] = existing["semantic_names"]
        refresh_semantic_name_anchors(session_dir, manifest)
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


def light_hook_display(
    *,
    aoa_root: Path,
    session_id: str,
    event: dict[str, Any],
    transcript_path: Path | None,
    existing: dict[str, Any],
    now: str,
) -> dict[str, Any]:
    existing_display = existing.get("display") if isinstance(existing.get("display"), dict) else {}
    if existing_display.get("label"):
        return dict(existing_display)
    title, title_source = session_title([], event, transcript_path)
    session_date = first_session_date([], event, transcript_path, now[:10])
    sequence = next_daily_sequence(aoa_root, session_date, session_id)
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


def mirror_transcript_without_indexing(
    *,
    aoa_root: Path,
    event: dict[str, Any],
    transcript_path: Path,
    hook_event_name: str,
    now: str,
) -> dict[str, Any]:
    session_id = session_id_from(event, transcript_path)
    initial_session_dir = session_dir_for_id(aoa_root, session_id)
    existing = read_json(initial_session_dir / "session.manifest.json", {})
    display = light_hook_display(
        aoa_root=aoa_root,
        session_id=session_id,
        event=event,
        transcript_path=transcript_path,
        existing=existing,
        now=now,
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
    raw_rel = "raw/session.raw.jsonl"
    raw_source = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "source_path": str(transcript_path),
        "copied_to": str(raw_path),
        "sha256": None,
        "updated_at": now,
        "indexing_status": "deferred_from_hook",
    }
    write_json(raw_dir / RAW_SOURCE_JSON, raw_source)
    legacy_raw_source = raw_dir / LEGACY_RAW_SOURCE_JSON
    if legacy_raw_source.exists():
        legacy_raw_source.unlink()

    hooks_seen = sorted(set(existing.get("hooks_seen", [])) | {hook_event_name})
    segments = existing.get("segments", []) if isinstance(existing.get("segments"), list) else []
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "display": display,
        "session_label": display["label"],
        "session_title": display["title"],
        "created_at": existing.get("created_at") or now,
        "updated_at": now,
        "source": source_payload,
        "archive_status": "raw_mirrored_index_deferred",
        "distillation_status": existing.get("distillation_status", "raw_archived"),
        "distillation_iteration": int(existing.get("distillation_iteration", 0) or 0),
        "review_status": existing.get("review_status", "provisional"),
        "hooks_seen": hooks_seen,
        "raw": {
            "path": str(raw_path),
            "source_path": str(transcript_path),
            "bytes": raw_path.stat().st_size,
            "sha256": None,
            "line_count": None,
            "copied_at": now,
            "indexing_status": "deferred_from_hook",
        },
        "segments": segments,
        "latest_event_count": existing.get("latest_event_count", 0),
    }
    if isinstance(existing.get("semantic_names"), dict):
        manifest["semantic_names"] = existing["semantic_names"]
        refresh_semantic_name_anchors(session_dir, manifest)
    write_json(session_dir / "session.manifest.json", manifest)
    if (session_dir / SESSION_INDEX_JSON).exists():
        update_session_index_identity(session_dir, manifest)
    update_registry(aoa_root, manifest, session_dir)
    return {
        "session_id": session_id,
        "display_name": display["label"],
        "navigation_path": display["navigation_path"],
        "session_dir": str(session_dir),
        "raw_path": str(raw_path),
        "raw_bytes": raw_path.stat().st_size,
        "raw_rel": raw_rel,
        "indexing_status": "deferred_from_hook",
    }


def stop_hook_should_defer_indexing(transcript_path: Path | None) -> bool:
    if os.environ.get("AOA_SESSION_MEMORY_FULL_STOP_SYNC") == "1":
        return False
    if transcript_path is None or not transcript_path.exists() or not os.access(transcript_path, os.R_OK):
        return False
    threshold_value = os.environ.get("AOA_SESSION_MEMORY_STOP_SYNC_MAX_BYTES")
    try:
        threshold = int(threshold_value) if threshold_value is not None else DEFAULT_STOP_SYNC_MAX_BYTES
    except ValueError:
        threshold = DEFAULT_STOP_SYNC_MAX_BYTES
    return transcript_path.stat().st_size > threshold


def update_registry(aoa_root: Path, manifest: dict[str, Any], session_dir: Path) -> None:
    lock_path = aoa_root / ".session-registry.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle, fcntl.LOCK_EX)
        update_registry_locked(aoa_root, manifest, session_dir)


def update_registry_locked(aoa_root: Path, manifest: dict[str, Any], session_dir: Path) -> None:
    registry_path = aoa_root / REGISTRY_NAME
    registry = read_json(registry_path, {"schema_version": SCHEMA_VERSION, "sessions": []})
    sessions = registry.get("sessions", [])
    if not isinstance(sessions, list):
        sessions = []
    manifest_paths = sorted((aoa_root / SESSION_ROOT).glob("*/session.manifest.json"))
    if registry_path.exists() and not sessions and len(manifest_paths) > 1:
        sessions = registry_records_from_manifests(aoa_root)
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
    write_session_name_index(aoa_root, updated)
    write_sessions_directory_index(aoa_root, updated)


def registry_records_from_manifests(aoa_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for manifest_path in sorted((aoa_root / SESSION_ROOT).glob("*/session.manifest.json")):
        manifest = read_json(manifest_path, {})
        if isinstance(manifest, dict) and manifest:
            records.append(registry_record(manifest, manifest_path.parent))
    records.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
    return records


def semantic_name_index_item(item: dict[str, Any]) -> dict[str, Any]:
    coverage = item.get("coverage") if isinstance(item.get("coverage"), dict) else {}
    anchor = item.get("anchor") if isinstance(item.get("anchor"), dict) else {}
    return {
        "name": item.get("name"),
        "slug": item.get("slug"),
        "scope": semantic_name_scope(item),
        "kind": item.get("kind"),
        "status": item.get("status"),
        "source": item.get("source"),
        "evidence": item.get("evidence", []) if isinstance(item.get("evidence"), list) else [],
        "coverage": coverage,
        "anchor": {
            "session_id": anchor.get("session_id"),
            "canonical_label": anchor.get("canonical_label"),
            "raw_sha256": anchor.get("raw_sha256"),
            "raw_line_count": anchor.get("raw_line_count"),
        },
    }


def int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def title_is_generic_for_naming(title: str, source: str | None) -> bool:
    compact = re.sub(r"\s+", " ", title.strip())
    lowered = compact.lower()
    if weak_title_text(compact):
        return True
    if str(source or "") in {"cwd", "transcript", "fallback"}:
        return True
    if lowered.startswith("codex in "):
        return True
    if lowered.startswith("reply exactly:"):
        return True
    return False


def segment_index_missing_paths(segments: list[Any]) -> list[str]:
    missing: list[str] = []
    for segment in segments:
        if not isinstance(segment, dict):
            missing.append("invalid-segment-record")
            continue
        index_path = segment.get("index")
        if not index_path:
            missing.append(f"{segment.get('segment_id') or 'segment'}:missing-index-field")
            continue
        if not Path(str(index_path)).exists():
            missing.append(str(index_path))
    return missing


def session_naming_readiness(
    aoa_root: Path,
    session_dir: Path,
    manifest: dict[str, Any],
    *,
    record: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = policy if isinstance(policy, dict) else batch_distillation_policy(aoa_root)
    large_threshold = int_value(policy.get("large_session_segment_threshold"), 24)
    huge_threshold = int_value(policy.get("huge_session_segment_threshold"), 100)
    display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    segments = manifest.get("segments") if isinstance(manifest.get("segments"), list) else []
    semantic = semantic_names_payload(manifest)
    active_session = active_semantic_name(manifest, scope="session")
    phase_or_topic_count = sum(
        1
        for item in semantic.get("names", [])
        if isinstance(item, dict) and semantic_name_scope(item) in {"phase", "topic"}
    )

    event_count = int_value(
        manifest.get("latest_event_count"),
        int_value(record.get("event_count") if isinstance(record, dict) else None),
    )
    segment_count = len(segments)
    archive_status = str(manifest.get("archive_status") or (record or {}).get("archive_status") or "")
    distillation_status = str(manifest.get("distillation_status") or (record or {}).get("distillation_status") or "")
    label = str(display.get("label") or manifest.get("session_label") or session_dir.name)
    title = str(display.get("title") or manifest.get("session_title") or "")
    title_source = str(display.get("title_source") or "")
    raw_path = Path(str(raw.get("path") or session_dir / "raw" / "session.raw.jsonl"))
    raw_present = raw_path.exists()
    raw_sha_present = bool(raw.get("sha256"))
    raw_line_count = raw.get("line_count")
    missing_segment_indexes = segment_index_missing_paths(segments)
    weak_title = title_is_generic_for_naming(title, title_source)
    weak_label = weak_label_text(label)
    phase_discovery_present = session_phase_discovery_path(session_dir).is_file()

    reasons: list[str] = []
    reindex_reasons: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    route = "optional_semantic_name"
    status = "readable_label"
    priority = 10

    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    source_transcript_path = source.get("transcript_path")
    has_recovery_hint = bool(source_transcript_path)
    if archive_status == "raw_unavailable":
        if has_recovery_hint:
            blockers.append("raw_unavailable")
            route = "recover_raw_before_naming"
        else:
            status = "diagnostic_only"
            route = "leave_raw_unavailable_diagnostic"
            priority = 0
            reasons.append("raw_unavailable_without_transcript_path")
    elif archive_status == "raw_mirrored_index_deferred":
        if raw_present:
            reindex_reasons.append("raw_mirrored_index_deferred")
            route = "reindex_before_naming"
        else:
            blockers.append("raw_mirrored_index_deferred_without_raw")
            route = "recover_raw_before_naming"
    elif archive_status != "indexed":
        blockers.append(f"archive_status_not_indexed:{archive_status or 'missing'}")
        route = "reindex_before_naming"
    if archive_status != "raw_unavailable" and not raw_present:
        blockers.append("raw_archive_missing")
        route = "recover_raw_before_naming"
    if archive_status == "indexed" and not segments:
        reindex_reasons.append("indexed_session_has_no_segments")
        route = "reindex_before_naming"
    if archive_status == "indexed" and missing_segment_indexes:
        reindex_reasons.append("segment_index_missing")
        route = "reindex_before_naming"

    if status == "diagnostic_only":
        pass
    elif blockers:
        status = "blocked"
        priority = 95 if event_count >= 1000 or segment_count >= large_threshold else 70
        reasons.extend(blockers)
    elif reindex_reasons:
        status = "needs_reindex"
        priority = 90 if event_count >= 1000 or segment_count >= large_threshold else 55
        reasons.extend(reindex_reasons)
    elif active_session:
        status = "named"
        route = "verify_or_refine_existing_name"
        priority = 0
        reasons.append("active_session_name_present")
        if phase_or_topic_count:
            reasons.append("phase_or_topic_names_present")
    elif event_count <= 20 and segment_count <= 2:
        status = "low_signal"
        route = "skip_or_wait_for_more_evidence"
        priority = 5
        reasons.append("small_or_probe_session")
    elif phase_or_topic_count:
        status = "ready_for_semantic_name"
        route = "semantic_name_from_existing_phase_topic_names"
        priority = 65
        reasons.append("phase_or_topic_names_present")
    elif phase_discovery_present:
        status = "phase_discovery_ready"
        route = "review_phase_discovery_before_session_name"
        priority = 70
        reasons.append("phase_discovery_present")
    elif segment_count >= huge_threshold:
        status = "needs_phase_discovery"
        route = "phase_topic_discovery_before_session_name"
        priority = 95
        reasons.append("huge_session")
    elif segment_count >= large_threshold:
        status = "needs_phase_discovery"
        route = "phase_topic_discovery_before_session_name"
        priority = 80
        reasons.append("large_session")
    elif weak_title or weak_label:
        status = "ready_for_semantic_name"
        route = "direct_semantic_name_from_index_and_raw_refs"
        priority = 60
        if weak_title:
            reasons.append("weak_or_generic_title")
        if weak_label:
            reasons.append("weak_or_generic_label")
    else:
        reasons.append("canonical_label_readable")

    if distillation_status != "first_pass_distilled":
        warnings.append(f"distillation_not_first_pass:{distillation_status or 'missing'}")
    if raw_present and not raw_sha_present and archive_status == "indexed":
        warnings.append("raw_sha256_missing")
    if raw_line_count is None and raw_present and archive_status == "indexed":
        warnings.append("raw_line_count_missing")

    suggested_next = {
        "blocked": "repair raw/index state before naming",
        "diagnostic_only": "keep the raw-unavailable diagnostic visible unless a raw candidate appears",
        "needs_reindex": "refresh generated segment indexes from preserved raw before naming",
        "phase_discovery_ready": "review phase-discovery candidates before applying the whole-session name",
        "named": "verify existing active session name against review needs",
        "low_signal": "leave canonical label unless this probe becomes operationally important",
        "needs_phase_discovery": "discover phase/topic candidates before assigning a whole-session name",
        "ready_for_semantic_name": "apply a semantic session name with raw evidence refs",
        "readable_label": "semantic name is optional; prioritize weaker or larger sessions first",
    }.get(status, "inspect naming route")

    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "route": route,
        "priority": priority,
        "reasons": reasons,
        "blockers": blockers,
        "warnings": warnings,
        "suggested_next": suggested_next,
        "evidence": {
            "session_label": label,
            "title": title,
            "title_source": title_source,
            "archive_status": archive_status,
            "distillation_status": distillation_status,
            "event_count": event_count,
            "segment_count": segment_count,
            "large_segment_threshold": large_threshold,
            "huge_segment_threshold": huge_threshold,
            "raw_present": raw_present,
            "source_transcript_path_present": has_recovery_hint,
            "raw_sha256_present": raw_sha_present,
            "raw_line_count": raw_line_count,
            "weak_title": weak_title,
            "weak_label": weak_label,
            "active_session_name": active_session.get("slug") if isinstance(active_session, dict) else None,
            "phase_or_topic_name_count": phase_or_topic_count,
            "phase_discovery_present": phase_discovery_present,
            "missing_segment_index_count": len(missing_segment_indexes),
            "missing_segment_indexes_sample": missing_segment_indexes[:8],
        },
    }


def naming_readiness_counts(records: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    by_status: Counter[str] = Counter()
    by_route: Counter[str] = Counter()
    for record in records:
        readiness = record.get("naming_readiness") if isinstance(record.get("naming_readiness"), dict) else {}
        by_status[str(readiness.get("status") or "missing")] += 1
        by_route[str(readiness.get("route") or "missing")] += 1
    return {
        "by_status": dict(sorted(by_status.items())),
        "by_route": dict(sorted(by_route.items())),
    }


def naming_work_queue(records: list[dict[str, Any]], *, limit: int = 50) -> list[dict[str, Any]]:
    queue = [
        {
            "session_id": record.get("session_id"),
            "session_label": record.get("session_label"),
            "session_title": record.get("session_title") or record.get("title"),
            "path": record.get("path"),
            "event_count": record.get("event_count", 0),
            "segment_count": record.get("segment_count", 0),
            "naming_readiness": record.get("naming_readiness"),
        }
        for record in records
        if isinstance(record.get("naming_readiness"), dict)
        and int_value(record["naming_readiness"].get("priority")) > 0
        and record["naming_readiness"].get("status") not in {"low_signal", "readable_label"}
    ]
    queue.sort(
        key=lambda item: (
            int_value((item.get("naming_readiness") or {}).get("priority")),
            int_value(item.get("segment_count")),
            int_value(item.get("event_count")),
            str(item.get("session_label") or ""),
        ),
        reverse=True,
    )
    return queue[:limit]


def session_phase_discovery_path(session_dir: Path) -> Path:
    return session_dir / "naming" / "phase-discovery.json"


def event_semantic_text(event: RawEvent) -> str:
    if not isinstance(event.parsed, dict):
        return ""
    return semantic_text_for_classification(event.source_type, event.parsed.get("payload"))


def extract_path_terms(texts: list[str], *, limit: int = 12) -> list[str]:
    counts: Counter[str] = Counter()
    pattern = re.compile(r"(?<![\w.-])(?:/[^\s`'\"<>|)]+|(?:[A-Za-z0-9_.-]+/){1,}[A-Za-z0-9_.-]+)")
    for text in texts:
        for match in pattern.findall(text):
            value = match.rstrip(".,:;)]}")
            if len(value) < 3 or value in {"/", "./", "../", "/dev/null", "/srv", "/tmp", "/home", "/var", "/etc"}:
                continue
            counts[value] += 1
    return [path for path, _count in counts.most_common(limit)]


def generic_phase_intent_text(text: str) -> bool:
    lowered = clean_phase_candidate_text(text).lower().strip(" .!?…")
    if not lowered:
        return True
    generic_values = {
        "давай",
        "давай действуй",
        "действуй",
        "разложи план",
        "что еще у нас есть",
        "ну что ж готов",
        "готов",
        "продолжаем",
        "окей",
        "добро двигай",
    }
    if lowered in generic_values:
        return True
    generic_prefixes = (
        "давай, действуй",
        "давай действуй",
        "давай тогда",
        "ну хорошо",
        "окей,",
        "так, что",
        "что еще",
        "и как бы ты это делал",
    )
    if len(lowered) > 80 and any(lowered.startswith(prefix) for prefix in generic_prefixes):
        return False
    return any(lowered.startswith(prefix) for prefix in generic_prefixes)


def phase_action_word(event_counts: Counter[str]) -> str:
    if event_counts.get("VERIFICATION"):
        return "validation"
    if event_counts.get("DIFF") or event_counts.get("FILE_WRITE"):
        return "implementation"
    if event_counts.get("ERROR"):
        return "failure diagnosis"
    if event_counts.get("FILE_READ") or event_counts.get("COMMAND"):
        return "investigation"
    return "session phase"


def path_based_phase_name(top_paths: list[str], event_counts: Counter[str]) -> str:
    action = phase_action_word(event_counts)
    if top_paths:
        path_name = Path(top_paths[0]).name or top_paths[0].strip("/").split("/")[-1]
        if path_name:
            return f"{path_name} {action}"
    return f"Segment phase {action}"


def phase_candidate_name(
    segment_id: str,
    user_texts: list[str],
    top_paths: list[str],
    event_counts: Counter[str],
) -> dict[str, Any]:
    quality_flags: list[str] = []
    specific_user_texts = [text for text in user_texts if not generic_phase_intent_text(text)]
    if len(specific_user_texts) < len(user_texts):
        quality_flags.append("generic_user_intent_present")
    if not specific_user_texts:
        quality_flags.append("no_specific_user_intent")
    for text in user_texts:
        candidate = short_text(clean_phase_candidate_text(text), max_chars=96)
        if text in specific_user_texts and candidate and usable_title_text(candidate):
            return {
                "name": candidate,
                "basis": "specific_user_intent",
                "quality_flags": quality_flags,
            }
    quality_flags.append("path_or_event_based_name")
    return {
        "name": path_based_phase_name(top_paths, event_counts),
        "basis": "linked_path_event_signals",
        "quality_flags": quality_flags,
    }


def clean_phase_candidate_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    cleaned = re.sub(r"^/[^\s`]+(?:\s+|$)", "", cleaned).strip()
    cleaned = re.sub(r"^`/[^\s`]+`(?:\s+|$)", "", cleaned).strip()
    return cleaned


def usable_phase_intent_text(text: str) -> bool:
    return usable_title_text(short_text(clean_phase_candidate_text(text), max_chars=200))


def phase_candidate_review(
    *,
    session_label: str,
    segment_id: str,
    candidate_name: str,
    confidence: str,
    name_basis: str,
    quality_flags: list[str],
    coverage: dict[str, Any],
    evidence_refs: list[str],
    linked_signals: dict[str, Any],
) -> dict[str, Any]:
    hard_flags = {"no_specific_user_intent", "path_or_event_based_name"}
    weak = bool(hard_flags & set(quality_flags)) or confidence == "low" or name_basis != "specific_user_intent"
    if weak:
        status = "needs_semantic_synthesis"
        action = "synthesize_reviewed_name_from_linked_signals"
        suggested_next = (
            "Run review-phase-name for this segment, inspect raw samples, then pass --reviewed-name before applying."
        )
        name_arg = "--reviewed-name '<reviewed phase name>'"
    else:
        status = "ready_for_raw_check"
        action = "verify_raw_refs_then_apply"
        suggested_next = "Run review-phase-name for this segment; apply with --use-candidate only after checking raw samples."
        name_arg = "--use-candidate"
    apply_template = (
        "python3 scripts/aoa_session_memory.py review-phase-name "
        f"{shlex.quote(session_label)} --segment {shlex.quote(str(segment_id))} "
        f"{name_arg} --apply --write-report"
    )
    return {
        "status": status,
        "action": action,
        "suggested_next": suggested_next,
        "apply_template": apply_template,
        "review_inputs": {
            "segment_id": segment_id,
            "candidate_name": candidate_name,
            "confidence": confidence,
            "name_basis": name_basis,
            "quality_flags": quality_flags,
            "coverage": coverage,
            "evidence": evidence_refs,
            "primary_user_intent": linked_signals.get("primary_user_intent"),
            "support_paths": linked_signals.get("support_paths", []),
            "support_event_types": linked_signals.get("support_event_types", {}),
        },
    }


def phase_candidate_from_segment(segment: dict[str, Any], events: list[RawEvent], *, session_label: str = "") -> dict[str, Any]:
    segment_id = str(segment.get("segment_id") or "")
    source_range = segment.get("source_range") if isinstance(segment.get("source_range"), dict) else {}
    event_counts: Counter[str] = Counter(event.event_type for event in events)
    family_counts: Counter[str] = Counter(event.family for event in events)
    outcome_counts: Counter[str] = Counter(event.outcome for event in events)
    user_events = [event for event in events if event.event_type == "USER_INTENT"]
    user_texts_all = [event_semantic_text(event) for event in user_events]
    user_texts = [text for text in user_texts_all if text.strip() and usable_phase_intent_text(text)]
    high_signal_events = [
        event
        for event in events
        if event.event_type in {"USER_INTENT", "DECISION", "CHECKPOINT", "OPEN_THREAD", "PROCESS_LESSON", "FINAL_STATE", "VERIFICATION", "ERROR"}
        and (event.event_type != "USER_INTENT" or usable_phase_intent_text(event_semantic_text(event)))
    ]
    signal_texts = [event_semantic_text(event) for event in high_signal_events]
    signal_texts = [text for text in signal_texts if text.strip()]
    path_events = [
        event
        for event in events
        if event.event_type in {"COMMAND", "COMMAND_OUTPUT", "FILE_READ", "FILE_WRITE", "DIFF", "VERIFICATION"}
        or (event.event_type == "USER_INTENT" and usable_phase_intent_text(event_semantic_text(event)))
    ]
    path_texts = [event_semantic_text(event) for event in path_events]
    path_texts = [text for text in path_texts if text.strip()]
    top_paths = extract_path_terms(path_texts)
    name_payload = phase_candidate_name(segment_id, user_texts, top_paths, event_counts)
    name = str(name_payload.get("name") or "")
    evidence_events = high_signal_events[:8] or events[:3]
    evidence_refs = [f"raw:line:{event.line_no}" for event in evidence_events]
    confidence = "medium"
    quality_flags = [str(flag) for flag in name_payload.get("quality_flags", []) if str(flag)]
    if "no_specific_user_intent" in quality_flags:
        confidence = "low"
    elif user_texts and (event_counts.get("DIFF") or event_counts.get("VERIFICATION") or event_counts.get("FINAL_STATE")):
        confidence = "high"
    elif not user_texts:
        confidence = "low"
    linked_signal_summary = {
        "basis": name_payload.get("basis"),
        "quality_flags": quality_flags,
        "primary_user_intent": short_text(clean_phase_candidate_text(user_texts[0]), max_chars=180) if user_texts else "",
        "specific_user_intent_count": len([text for text in user_texts if not generic_phase_intent_text(text)]),
        "support_paths": top_paths[:5],
        "support_event_types": {
            key: event_counts.get(key, 0)
            for key in ["USER_INTENT", "COMMAND", "COMMAND_OUTPUT", "FILE_READ", "DIFF", "ERROR", "VERIFICATION", "FINAL_STATE"]
            if event_counts.get(key, 0)
        },
    }
    coverage = {
        "raw_ranges": [
            {
                "from_line": int_value(source_range.get("from_line")),
                "to_line": int_value(source_range.get("to_line")),
            }
        ],
        "note": f"Generated from segment {segment_id}; review before applying.",
    }
    review = phase_candidate_review(
        session_label=session_label,
        segment_id=segment_id,
        candidate_name=name,
        confidence=confidence,
        name_basis=str(name_payload.get("basis") or ""),
        quality_flags=quality_flags,
        coverage=coverage,
        evidence_refs=evidence_refs,
        linked_signals=linked_signal_summary,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "segment_id": segment_id,
        "segment_role": segment.get("role"),
        "scope": "phase",
        "kind": "dominant_topic",
        "status": "candidate_unreviewed",
        "name": name,
        "slug": semantic_name_slug(name),
        "confidence": confidence,
        "coverage": coverage,
        "evidence": evidence_refs,
        "name_basis": name_payload.get("basis"),
        "quality_flags": quality_flags,
        "linked_signals": linked_signal_summary,
        "review": review,
        "signals": {
            "event_count": len(events),
            "event_counts": dict(sorted(event_counts.items())),
            "family_counts": dict(sorted(family_counts.items())),
            "outcome_counts": dict(sorted(outcome_counts.items())),
            "user_intent_count": len(user_texts),
            "raw_user_intent_count": len(user_events),
            "command_count": event_counts.get("COMMAND", 0),
            "mutation_count": event_counts.get("DIFF", 0) + event_counts.get("FILE_WRITE", 0),
            "error_count": event_counts.get("ERROR", 0),
            "verification_count": event_counts.get("VERIFICATION", 0),
            "top_paths": top_paths,
            "user_intent_samples": [short_text(clean_phase_candidate_text(text), max_chars=160) for text in user_texts[:4]],
            "high_signal_samples": [short_text(text, max_chars=160) for text in signal_texts[:6]],
        },
    }


def phase_candidate_quality_counts(candidates: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    by_confidence: Counter[str] = Counter()
    by_basis: Counter[str] = Counter()
    by_review_status: Counter[str] = Counter()
    by_quality_flag: Counter[str] = Counter()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        by_confidence[str(candidate.get("confidence") or "missing")] += 1
        by_basis[str(candidate.get("name_basis") or "missing")] += 1
        review = candidate.get("review") if isinstance(candidate.get("review"), dict) else {}
        by_review_status[str(review.get("status") or "missing")] += 1
        for flag in candidate.get("quality_flags", []) if isinstance(candidate.get("quality_flags"), list) else []:
            by_quality_flag[str(flag)] += 1
    return {
        "by_confidence": dict(sorted(by_confidence.items())),
        "by_basis": dict(sorted(by_basis.items())),
        "by_review_status": dict(sorted(by_review_status.items())),
        "by_quality_flag": dict(sorted(by_quality_flag.items())),
    }


def phase_review_queue(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        review = candidate.get("review") if isinstance(candidate.get("review"), dict) else {}
        if review.get("status") == "ready_for_raw_check":
            continue
        coverage = candidate.get("coverage") if isinstance(candidate.get("coverage"), dict) else {}
        queue.append(
            {
                "segment_id": candidate.get("segment_id"),
                "candidate_name": candidate.get("name"),
                "confidence": candidate.get("confidence"),
                "name_basis": candidate.get("name_basis"),
                "quality_flags": candidate.get("quality_flags", []),
                "coverage": coverage,
                "evidence": candidate.get("evidence", []),
                "review": review,
            }
        )
    queue.sort(
        key=lambda item: (
            0 if item.get("confidence") == "low" else 1,
            str(item.get("segment_id") or ""),
        )
    )
    return queue


def discover_session_phases(
    aoa_root: Path,
    target: str,
    *,
    write: bool = False,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    record = resolve_session_record(aoa_root, target)
    session_dir = session_dir_from_record(record)
    manifest = read_json(session_dir / "session.manifest.json", {})
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError(f"missing session manifest: {session_dir}")
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    raw_path = Path(str(raw.get("path") or session_dir / "raw" / "session.raw.jsonl"))
    if not raw_path.is_file():
        raise ValueError(f"missing raw archive: {raw_path}")
    segments = manifest.get("segments") if isinstance(manifest.get("segments"), list) else []
    if not segments:
        raise ValueError(f"missing generated segments: {session_dir}")
    events = parse_raw_events(raw_path)
    candidates: list[dict[str, Any]] = []
    display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
    session_label = str(display.get("label") or manifest.get("session_label") or record.get("session_label") or target)
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        source_range = segment.get("source_range") if isinstance(segment.get("source_range"), dict) else {}
        start = int_value(source_range.get("from_line"))
        end = int_value(source_range.get("to_line"))
        if start <= 0 or end <= 0:
            continue
        segment_events = [event for event in events if start <= event.line_no <= end]
        if not segment_events:
            continue
        candidates.append(phase_candidate_from_segment(segment, segment_events, session_label=session_label))
    review_queue = phase_review_queue(candidates)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "session_phase_discovery",
        "generated_at": now,
        "ok": True,
        "status": "candidate_unreviewed",
        "aoa_root": str(aoa_root),
        "session_id": manifest.get("session_id"),
        "session_label": session_label,
        "session_title": display.get("title") or manifest.get("session_title"),
        "session_dir": str(session_dir),
        "raw_path": str(raw_path),
        "archive_status": manifest.get("archive_status"),
        "event_count": len(events),
        "segment_count": len(segments),
        "candidate_count": len(candidates),
        "candidate_quality_counts": phase_candidate_quality_counts(candidates),
        "review_queue_count": len(review_queue),
        "review_queue": review_queue,
        "candidates": candidates,
        "next_actions": [
            "review candidate names against raw evidence",
            "apply accepted phase/topic names with name-session --scope phase or --scope topic",
            "choose the whole-session name only after phase coverage is understood",
        ],
    }
    if write:
        artifact_json = session_phase_discovery_path(session_dir)
        artifact_md = artifact_json.with_suffix(".md")
        write_json(artifact_json, payload)
        write_markdown(artifact_md, phase_discovery_markdown(payload))
        payload["artifact_json"] = str(artifact_json)
        payload["artifact_markdown"] = str(artifact_md)
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__phase-discovery__{safe_slug(str(payload.get('session_label') or target))}"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, phase_discovery_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def phase_discovery_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Session Phase Discovery",
        "",
        "Generated candidate phase/topic names. This is open evidence for review, not applied naming truth.",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- session: `{payload.get('session_label') or payload.get('session_id')}`",
        f"- archive_status: `{payload.get('archive_status')}`",
        f"- events: `{payload.get('event_count')}`",
        f"- segments: `{payload.get('segment_count')}`",
        f"- candidates: `{payload.get('candidate_count')}`",
        f"- review_queue: `{payload.get('review_queue_count', 0)}`",
        f"- raw_path: `{payload.get('raw_path')}`",
        "",
        "## Quality Counts",
        "",
    ]
    quality_counts = payload.get("candidate_quality_counts") if isinstance(payload.get("candidate_quality_counts"), dict) else {}
    for key, value in quality_counts.items():
        lines.append(f"- `{key}`: `{json.dumps(value, ensure_ascii=False)}`")
    lines.extend(
        [
            "",
            "## Review Queue",
            "",
        ]
    )
    review_queue = payload.get("review_queue") if isinstance(payload.get("review_queue"), list) else []
    if review_queue:
        lines.extend(["| segment | action | candidate | quality | next |", "| --- | --- | --- | --- | --- |"])
        for item in review_queue[:25]:
            if not isinstance(item, dict):
                continue
            review = item.get("review") if isinstance(item.get("review"), dict) else {}
            lines.append(
                "| `{segment}` | `{action}` | {candidate} | {quality} | {next} |".format(
                    segment=item.get("segment_id"),
                    action=markdown_cell(review.get("action")),
                    candidate=markdown_cell(item.get("candidate_name")),
                    quality=markdown_cell(", ".join(str(flag) for flag in item.get("quality_flags", []) if flag)),
                    next=markdown_cell(review.get("suggested_next")),
                )
            )
        lines.extend(["", "## Review Apply Templates", ""])
        for item in review_queue[:25]:
            if not isinstance(item, dict):
                continue
            review = item.get("review") if isinstance(item.get("review"), dict) else {}
            template = str(review.get("apply_template") or "").strip()
            if not template:
                continue
            lines.extend([f"### Segment `{item.get('segment_id')}`", "", "```bash", template, "```", ""])
    else:
        lines.append("- No candidates require semantic synthesis before raw-check review.")
    lines.extend(
        [
            "",
        "## Candidates",
        "",
        "| segment | confidence | basis | candidate | coverage | evidence | signals | quality |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for candidate in payload.get("candidates", []) if isinstance(payload.get("candidates"), list) else []:
        if not isinstance(candidate, dict):
            continue
        coverage = candidate.get("coverage") if isinstance(candidate.get("coverage"), dict) else {}
        raw_ranges = coverage.get("raw_ranges") if isinstance(coverage.get("raw_ranges"), list) else []
        range_text = ""
        if raw_ranges and isinstance(raw_ranges[0], dict):
            range_text = f"{raw_ranges[0].get('from_line')}..{raw_ranges[0].get('to_line')}"
        signals = candidate.get("signals") if isinstance(candidate.get("signals"), dict) else {}
        signal_text = "users:{users} commands:{commands} mutations:{mutations} errors:{errors} checks:{checks}".format(
            users=signals.get("user_intent_count", 0),
            commands=signals.get("command_count", 0),
            mutations=signals.get("mutation_count", 0),
            errors=signals.get("error_count", 0),
            checks=signals.get("verification_count", 0),
        )
        lines.append(
            "| `{segment}` | `{confidence}` | `{basis}` | {name} | `{coverage}` | `{evidence}` | {signals} | {quality} |".format(
                segment=candidate.get("segment_id"),
                confidence=candidate.get("confidence"),
                basis=markdown_cell(candidate.get("name_basis")),
                name=markdown_cell(candidate.get("name")),
                coverage=range_text,
                evidence=", ".join(str(ref) for ref in candidate.get("evidence", [])[:4]),
                signals=markdown_cell(signal_text),
                quality=markdown_cell(", ".join(str(flag) for flag in candidate.get("quality_flags", []) if flag)),
            )
        )
    lines.extend(
        [
            "",
            "## Review Rule",
            "",
            "Apply phase/topic names through `review-phase-name`; use `name-session` only as the lower-level writer.",
            "",
        ]
    )
    return "\n".join(lines)


def normalize_segment_id(value: str) -> str:
    text = str(value or "").strip()
    if text.isdigit():
        return f"{int(text):03d}"
    return text


def phase_discovery_payload_for_review(aoa_root: Path, target: str, *, refresh: bool = False) -> dict[str, Any]:
    record = resolve_session_record(aoa_root, target)
    session_dir = session_dir_from_record(record)
    artifact_json = session_phase_discovery_path(session_dir)
    if refresh or not artifact_json.is_file():
        return discover_session_phases(aoa_root, target, write=True)
    payload = read_json(artifact_json, {})
    if not isinstance(payload, dict) or payload.get("artifact_type") != "session_phase_discovery":
        return discover_session_phases(aoa_root, target, write=True)
    return payload


def phase_candidate_by_segment(payload: dict[str, Any], segment_id: str) -> dict[str, Any]:
    normalized = normalize_segment_id(segment_id)
    for candidate in payload.get("candidates", []) if isinstance(payload.get("candidates"), list) else []:
        if isinstance(candidate, dict) and normalize_segment_id(str(candidate.get("segment_id") or "")) == normalized:
            return candidate
    raise ValueError(f"phase candidate not found for segment: {segment_id}")


def phase_candidate_range(candidate: dict[str, Any]) -> tuple[int | None, int | None]:
    coverage = candidate.get("coverage") if isinstance(candidate.get("coverage"), dict) else {}
    ranges = coverage.get("raw_ranges") if isinstance(coverage.get("raw_ranges"), list) else []
    first = ranges[0] if ranges and isinstance(ranges[0], dict) else {}
    start = int_value(first.get("from_line")) or None
    end = int_value(first.get("to_line")) or None
    return start, end


def raw_event_sample(event: RawEvent) -> dict[str, Any]:
    return {
        "raw_ref": f"raw:line:{event.line_no}",
        "event_type": event.event_type,
        "source_type": event.source_type,
        "title": event.title,
        "text": short_text(event_semantic_text(event), max_chars=260),
    }


def phase_candidate_raw_samples(payload: dict[str, Any], candidate: dict[str, Any], *, max_samples: int = 12) -> list[dict[str, Any]]:
    raw_path_value = str(payload.get("raw_path") or "")
    raw_path = Path(raw_path_value) if raw_path_value else Path()
    if not raw_path.is_file():
        return []
    events = parse_raw_events(raw_path)
    by_line = {event.line_no: event for event in events}
    start, end = phase_candidate_range(candidate)
    selected_lines: list[int] = []
    for ref in candidate.get("evidence", []) if isinstance(candidate.get("evidence"), list) else []:
        line = line_from_raw_ref(ref)
        if line is not None:
            selected_lines.append(line)
    if start is not None:
        selected_lines.append(start)
    if end is not None:
        selected_lines.append(end)
    if start is not None and end is not None:
        high_signal_types = {"USER_INTENT", "DECISION", "CHECKPOINT", "PROCESS_LESSON", "FINAL_STATE", "VERIFICATION", "ERROR"}
        for event in events:
            if len(selected_lines) >= max_samples:
                break
            if start <= event.line_no <= end and event.event_type in high_signal_types:
                selected_lines.append(event.line_no)
    seen: set[int] = set()
    samples: list[dict[str, Any]] = []
    for line in selected_lines:
        if line in seen:
            continue
        seen.add(line)
        event = by_line.get(line)
        if event is None:
            continue
        samples.append(raw_event_sample(event))
        if len(samples) >= max_samples:
            break
    return samples


def phase_name_review_markdown(payload: dict[str, Any]) -> str:
    candidate = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else {}
    review = candidate.get("review") if isinstance(candidate.get("review"), dict) else {}
    lines = [
        "# Phase Name Review",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- status: `{payload.get('status')}`",
        f"- apply: `{payload.get('apply')}`",
        f"- session: `{payload.get('session_label') or payload.get('session_id')}`",
        f"- segment: `{payload.get('segment_id')}`",
        f"- candidate: {candidate.get('name')}",
        f"- candidate_status: `{review.get('status')}`",
        f"- chosen_name: {payload.get('chosen_name') or ''}",
        f"- route: `{payload.get('route')}`",
        "",
        "## Diagnostics",
        "",
    ]
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), list) else []
    lines.extend([f"- `{item}`" for item in diagnostics] or ["- none"])
    lines.extend(["", "## Raw Samples", ""])
    samples = payload.get("raw_samples") if isinstance(payload.get("raw_samples"), list) else []
    if samples:
        lines.extend(["| ref | type | text |", "| --- | --- | --- |"])
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            lines.append(
                "| `{ref}` | `{event_type}` | {text} |".format(
                    ref=sample.get("raw_ref"),
                    event_type=sample.get("event_type"),
                    text=markdown_cell(sample.get("text")),
                )
            )
    else:
        lines.append("- No raw samples available.")
    if payload.get("next_command"):
        lines.extend(["", "## Next Command", "", "```bash", str(payload.get("next_command")), "```"])
    if isinstance(payload.get("semantic_name_result"), dict):
        proposed = payload["semantic_name_result"].get("proposed") if isinstance(payload["semantic_name_result"].get("proposed"), dict) else {}
        lines.extend(
            [
                "",
                "## Applied Name",
                "",
                f"- name: {proposed.get('name')}",
                f"- slug: `{proposed.get('slug')}`",
                f"- scope: `{proposed.get('scope')}`",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def review_phase_name_candidate(
    aoa_root: Path,
    target: str,
    segment_id: str,
    *,
    reviewed_name: str | None = None,
    use_candidate: bool = False,
    apply: bool = False,
    replace: bool = False,
    refresh: bool = False,
    write_report: bool = False,
    verify_raw_hash: bool = False,
    coverage_note: str | None = None,
) -> dict[str, Any]:
    now = utc_now()
    discovery = phase_discovery_payload_for_review(aoa_root, target, refresh=refresh)
    candidate = phase_candidate_by_segment(discovery, segment_id)
    review = candidate.get("review") if isinstance(candidate.get("review"), dict) else {}
    review_status = str(review.get("status") or "")
    candidate_name = str(candidate.get("name") or "").strip()
    chosen_name = str(reviewed_name or "").strip()
    diagnostics: list[str] = []
    if use_candidate:
        if review_status == "needs_semantic_synthesis":
            diagnostics.append("weak_candidate_requires_reviewed_name")
        elif chosen_name:
            diagnostics.append("choose_either_reviewed_name_or_use_candidate")
        else:
            chosen_name = candidate_name
    if apply and not chosen_name and not use_candidate:
        diagnostics.append("apply_requires_reviewed_name_or_use_candidate")
    if review_status == "needs_semantic_synthesis" and chosen_name and semantic_name_slug(chosen_name) == semantic_name_slug(candidate_name):
        diagnostics.append("reviewed_name_matches_weak_machine_candidate")
    start, end = phase_candidate_range(candidate)
    evidence_refs = [str(ref) for ref in candidate.get("evidence", []) if str(ref).strip()] if isinstance(candidate.get("evidence"), list) else []
    if not evidence_refs and start:
        evidence_refs = [f"raw:line:{start}"]
    route = "apply_reviewed_phase_name" if apply else "review_phase_candidate"
    if review_status == "needs_semantic_synthesis" and not chosen_name:
        route = "synthesize_reviewed_name_before_apply"
    next_command = ""
    session_label = str(discovery.get("session_label") or target)
    if not apply:
        if review_status == "needs_semantic_synthesis":
            next_command = (
                "python3 scripts/aoa_session_memory.py review-phase-name "
                f"{shlex.quote(session_label)} --segment {shlex.quote(normalize_segment_id(segment_id))} "
                "--reviewed-name '<reviewed phase name>' --apply --write-report"
            )
        else:
            next_command = (
                "python3 scripts/aoa_session_memory.py review-phase-name "
                f"{shlex.quote(session_label)} --segment {shlex.quote(normalize_segment_id(segment_id))} "
                "--use-candidate --apply --write-report"
            )
    semantic_result: dict[str, Any] | None = None
    refreshed_indexes: list[str] = []
    status = "diagnostic" if diagnostics else str(review_status or "preview")
    if apply and not diagnostics:
        semantic_result = set_session_semantic_name(
            aoa_root=aoa_root,
            target=session_label,
            name=chosen_name,
            kind="dominant_topic",
            scope="phase",
            evidence_refs=evidence_refs,
            from_line=start,
            to_line=end,
            coverage_note=coverage_note
            or f"Reviewed phase name for segment {normalize_segment_id(segment_id)} from phase-discovery.",
            source="phase_discovery_review",
            note=f"candidate={candidate_name}; review_status={review_status}",
            apply=True,
            replace=replace,
            verify_raw_hash=verify_raw_hash,
            write_report=write_report,
        )
        if semantic_result.get("ok"):
            sessions = registry_sessions(aoa_root)
            write_session_name_index(aoa_root, sessions)
            write_sessions_directory_index(aoa_root, sessions)
            refreshed_indexes = [
                str(aoa_root / SESSION_NAME_INDEX_JSON),
                str(aoa_root / SESSION_NAME_INDEX_MARKDOWN),
                str(aoa_root / SESSION_ROOT / SESSIONS_INDEX_JSON),
                str(aoa_root / SESSION_ROOT / SESSIONS_INDEX_MARKDOWN),
            ]
            status = "applied"
        else:
            diagnostics.extend(str(item) for item in semantic_result.get("diagnostics", []) if item)
            status = "diagnostic"
    out = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "phase_name_review",
        "generated_at": now,
        "ok": not diagnostics,
        "status": status,
        "apply": apply,
        "aoa_root": str(aoa_root),
        "session_id": discovery.get("session_id"),
        "session_label": session_label,
        "segment_id": normalize_segment_id(segment_id),
        "route": route,
        "chosen_name": chosen_name,
        "candidate": candidate,
        "raw_samples": phase_candidate_raw_samples(discovery, candidate),
        "diagnostics": diagnostics,
        "next_command": next_command,
        "refreshed_indexes": refreshed_indexes,
    }
    if semantic_result is not None:
        out["semantic_name_result"] = semantic_result
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = (
            f"{compact_stamp()}__phase-name-review__"
            f"{safe_slug(session_label)}__{safe_slug(normalize_segment_id(segment_id))}"
        )
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, out)
        write_markdown(report_md, phase_name_review_markdown(out))
        out["report_json"] = str(report_json)
        out["report_markdown"] = str(report_md)
    return out


def build_session_name_index(aoa_root: Path, sessions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    sessions = sessions if sessions is not None else registry_sessions(aoa_root)
    policy = batch_distillation_policy(aoa_root)
    records: list[dict[str, Any]] = []
    slug_index: dict[str, list[dict[str, str]]] = defaultdict(list)
    for record in sessions:
        if not isinstance(record, dict):
            continue
        session_dir = session_dir_from_record(record)
        manifest = read_json(session_dir / "session.manifest.json", {})
        if not isinstance(manifest, dict) or not manifest:
            continue
        display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
        semantic_names = semantic_names_payload(manifest)
        names = [semantic_name_index_item(item) for item in semantic_names.get("names", []) if isinstance(item, dict)]
        readiness = session_naming_readiness(aoa_root, session_dir, manifest, record=record, policy=policy)
        for name_item in names:
            slug = str(name_item.get("slug") or "")
            if slug:
                slug_index[slug].append(
                    {
                        "session_id": str(manifest.get("session_id") or ""),
                        "session_label": str(display.get("label") or manifest.get("session_label") or session_dir.name),
                        "scope": str(name_item.get("scope") or ""),
                    }
                )
        records.append(
            {
                "session_id": manifest.get("session_id"),
                "session_label": display.get("label") or manifest.get("session_label") or session_dir.name,
                "session_title": display.get("title") or manifest.get("session_title"),
                "path": str(session_dir),
                "event_count": manifest.get("latest_event_count", 0),
                "segment_count": len(manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []),
                "naming_readiness": readiness,
                "semantic_names": {
                    "active": semantic_names.get("active"),
                    "active_session": semantic_names.get("active_session"),
                    "names": names,
                },
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "session_name_index",
        "generated_at": utc_now(),
        "session_count": len(records),
        "named_session_count": sum(1 for item in records if item["semantic_names"]["names"]),
        "naming_readiness_counts": naming_readiness_counts(records),
        "naming_work_queue": naming_work_queue(records),
        "sessions": records,
        "slug_index": dict(sorted(slug_index.items())),
    }


def write_session_name_index(aoa_root: Path, sessions: list[dict[str, Any]] | None = None) -> None:
    payload = build_session_name_index(aoa_root, sessions)
    write_json(aoa_root / SESSION_NAME_INDEX_JSON, payload)
    write_markdown(aoa_root / SESSION_NAME_INDEX_MARKDOWN, session_name_index_markdown(payload))


def session_name_index_markdown(payload: dict[str, Any]) -> str:
    readiness_counts = payload.get("naming_readiness_counts") if isinstance(payload.get("naming_readiness_counts"), dict) else {}
    by_status = readiness_counts.get("by_status") if isinstance(readiness_counts.get("by_status"), dict) else {}
    by_route = readiness_counts.get("by_route") if isinstance(readiness_counts.get("by_route"), dict) else {}
    lines = [
        "# Session Name Index",
        "",
        "Lightweight map of canonical session labels, mutable session names, phase/topic names, and raw anchors.",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- session_count: `{payload.get('session_count')}`",
        f"- named_session_count: `{payload.get('named_session_count')}`",
        "",
        "## Naming Readiness",
        "",
        "This is a routing layer, not a naming verdict. It tells the next agent whether a session can be named directly, needs phase discovery, or must be repaired first.",
        "",
        "### By Status",
        "",
    ]
    for status, count in by_status.items():
        lines.append(f"- `{status}`: {count}")
    lines.extend(["", "### By Route", ""])
    for route, count in by_route.items():
        lines.append(f"- `{route}`: {count}")
    queue = payload.get("naming_work_queue") if isinstance(payload.get("naming_work_queue"), list) else []
    lines.extend(["", "## Naming Work Queue", ""])
    if queue:
        lines.extend(["| priority | status | route | session | size | reasons |", "| --- | --- | --- | --- | --- | --- |"])
        for item in queue[:25]:
            if not isinstance(item, dict):
                continue
            readiness = item.get("naming_readiness") if isinstance(item.get("naming_readiness"), dict) else {}
            lines.append(
                "| `{priority}` | `{status}` | `{route}` | `{session}` | `{events}` / `{segments}` | {reasons} |".format(
                    priority=readiness.get("priority", 0),
                    status=markdown_cell(readiness.get("status")),
                    route=markdown_cell(readiness.get("route")),
                    session=markdown_cell(item.get("session_label")),
                    events=item.get("event_count", 0),
                    segments=item.get("segment_count", 0),
                    reasons=markdown_cell(", ".join(str(reason) for reason in readiness.get("reasons", []) if reason)),
                )
            )
    else:
        lines.append("- No naming work is currently queued.")
    lines.extend(
        [
            "",
            "## All Session Names",
            "",
            "| session | readiness | active session name | phase/topic names |",
            "| --- | --- | --- | --- |",
        ]
    )
    for record in payload.get("sessions", []) if isinstance(payload.get("sessions"), list) else []:
        if not isinstance(record, dict):
            continue
        semantic = record.get("semantic_names") if isinstance(record.get("semantic_names"), dict) else {}
        readiness = record.get("naming_readiness") if isinstance(record.get("naming_readiness"), dict) else {}
        active_session = str(semantic.get("active_session") or "")
        names = semantic.get("names", []) if isinstance(semantic.get("names"), list) else []
        phase_names = [
            f"`{item.get('slug')}`"
            for item in names
            if isinstance(item, dict) and item.get("slug") != active_session
        ]
        active_label = active_session
        for item in names:
            if isinstance(item, dict) and item.get("slug") == active_session:
                active_name_text = str(item.get("name") or "").replace("|", "\\|")
                active_label = f"`{item.get('slug')}` - {active_name_text}"
                break
        lines.append(
            "| `{session}` | `{readiness}` | {active} | {phases} |".format(
                session=str(record.get("session_label") or record.get("session_id") or ""),
                readiness=str(readiness.get("status") or ""),
                active=active_label or "",
                phases=", ".join(phase_names),
            )
        )
    lines.append("")
    return "\n".join(lines)


def markdown_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def session_directory_record(item: dict[str, Any]) -> dict[str, Any]:
    session_dir = session_dir_from_record(item)
    manifest = read_json(session_dir / "session.manifest.json", {})
    if not isinstance(manifest, dict):
        manifest = {}
    semantic = item.get("semantic_names") if isinstance(item.get("semantic_names"), dict) else {}
    if isinstance(manifest.get("semantic_names"), dict):
        semantic = semantic_names_payload(manifest)
    names = semantic.get("names", []) if isinstance(semantic.get("names"), list) else []
    active_session = str(semantic.get("active_session") or "")
    active_name = item.get("active_session_name") if isinstance(item.get("active_session_name"), dict) else {}
    if manifest:
        active_name = semantic_name_summary(manifest, scope="session") or active_name
    phase_names = [
        {
            "slug": name.get("slug"),
            "name": name.get("name"),
            "scope": name.get("scope"),
            "kind": name.get("kind"),
        }
        for name in names
        if isinstance(name, dict) and name.get("slug") != active_session
    ]
    label = str(item.get("session_label") or "")
    if manifest:
        display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
        label = str(display.get("label") or manifest.get("session_label") or label)
    date = label[:10] if re.match(r"^20\d{2}-[01]\d-[0-3]\d__", label) else ""
    readiness = session_naming_readiness(item.get("aoa_root", Path(".")) if isinstance(item.get("aoa_root"), Path) else session_dir.parents[1], session_dir, manifest, record=item) if manifest else {}
    return {
        "session_id": item.get("session_id"),
        "session_label": label,
        "date": date,
        "title": (manifest.get("display") if isinstance(manifest.get("display"), dict) else {}).get("title") if manifest else item.get("session_title"),
        "active_session_name": active_name,
        "phase_names": phase_names,
        "naming_readiness": readiness,
        "archive_status": item.get("archive_status"),
        "distillation_status": item.get("distillation_status"),
        "event_count": manifest.get("latest_event_count", item.get("event_count", 0)) if manifest else item.get("event_count", 0),
        "segment_count": len(manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []) if manifest else item.get("segment_count", 0),
        "cwd": item.get("cwd"),
        "updated_at": item.get("updated_at"),
        "path": item.get("path"),
        "entry": f"{label}/{SESSION_INDEX_MARKDOWN}" if label else None,
    }


def build_sessions_directory_index(aoa_root: Path, sessions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    sessions = sessions if sessions is not None else registry_sessions(aoa_root)
    records = [session_directory_record({**item, "aoa_root": aoa_root}) for item in sessions if isinstance(item, dict)]
    records.sort(key=lambda item: (str(item.get("date") or ""), str(item.get("session_label") or "")), reverse=True)
    by_date: dict[str, list[str]] = defaultdict(list)
    for record in records:
        by_date[str(record.get("date") or "undated")].append(str(record.get("session_label") or ""))
    largest = sorted(records, key=lambda item: int(item.get("event_count") or 0), reverse=True)[:25]
    named = [
        record
        for record in records
        if (record.get("active_session_name") if isinstance(record.get("active_session_name"), dict) else {}).get("slug")
        or record.get("phase_names")
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "sessions_directory_index",
        "generated_at": utc_now(),
        "session_count": len(records),
        "named_session_count": len(named),
        "naming_readiness_counts": naming_readiness_counts(records),
        "naming_work_queue": naming_work_queue(records),
        "sessions_root": str(aoa_root / SESSION_ROOT),
        "read_order": [
            SESSIONS_AGENTS_MARKDOWN,
            SESSIONS_INDEX_MARKDOWN,
            "../SESSION_NAMES.md",
            "../session-registry.json",
            "<session>/AGENTS.md",
            "<session>/SESSION.md",
            "<session>/session.index.json",
            "<session>/session.manifest.json",
            "<session>/segments/*.index.json",
        ],
        "by_date": dict(sorted(by_date.items(), reverse=True)),
        "largest_sessions": largest,
        "named_sessions": named,
        "sessions": records,
    }


def write_sessions_directory_index(aoa_root: Path, sessions: list[dict[str, Any]] | None = None) -> None:
    session_root = aoa_root / SESSION_ROOT
    session_root.mkdir(parents=True, exist_ok=True)
    write_sessions_directory_agents(session_root)
    payload = build_sessions_directory_index(aoa_root, sessions)
    write_json(session_root / SESSIONS_INDEX_JSON, payload)
    write_markdown(session_root / SESSIONS_INDEX_MARKDOWN, sessions_directory_index_markdown(payload))


def write_sessions_directory_agents(session_root: Path) -> None:
    lines = [
        "# Sessions AGENTS.md",
        "",
        "## Purpose",
        "",
        "This directory is the archive district for preserved Codex sessions.",
        "",
        "It contains generated archive-local navigation plus one directory per",
        "session. Do not treat a raw filesystem listing as the route. Start from",
        "this card, then use the generated indexes and session-local cards.",
        "",
        "## Read Order",
        "",
        "1. `AGENTS.md`",
        f"2. `{SESSIONS_INDEX_MARKDOWN}`",
        "3. `../SESSION_NAMES.md`",
        "4. `../session-registry.json`",
        "5. `<session>/AGENTS.md`",
        f"6. `<session>/{SESSION_INDEX_MARKDOWN}`",
        "7. `<session>/session.manifest.json`",
        f"8. `<session>/{SESSION_INDEX_JSON}`",
        "9. `<session>/segments/*.index.json` before opening segment Markdown",
        "10. `<session>/raw/session.raw.jsonl` only for exact verification,",
        "    recovery, or durable evidence anchors",
        "",
        "## Authority",
        "",
        f"- `{SESSIONS_INDEX_MARKDOWN}` and `{SESSIONS_INDEX_JSON}` are generated",
        "  tables of contents for navigation.",
        "- `../SESSION_NAMES.md`, `../session-name-index.json`, and",
        "  `../session-registry.json` are root-level generated maps.",
        "- `<session>/session.manifest.json` owns technical identity and archive",
        "  status for a single session.",
        "- `<session>/raw/session.raw.jsonl` is preserved evidence.",
        "- Review, distillation, naming, and promotion outputs remain provisional",
        "  until their own reviewed route says otherwise.",
        "",
        "## Rules",
        "",
        "- Do not manually rename archive directories without following",
        "  `../NAMING.md` and preserving the `session_id` bridge.",
        "- Prefer semantic `name-session` entries before physical relabels when",
        "  the archive already has stable raw provenance.",
        "- Treat `raw_unavailable` and `raw_mirrored_index_deferred` as explicit",
        "  states, not as understood sessions.",
        "- Do not open bulk raw before checking the target session indexes.",
        "- Keep generated indexes reproducible from raw evidence or explicit",
        "  review artifacts.",
        "",
    ]
    write_markdown(session_root / SESSIONS_AGENTS_MARKDOWN, "\n".join(lines))


def sessions_directory_index_markdown(payload: dict[str, Any]) -> str:
    readiness_counts = payload.get("naming_readiness_counts") if isinstance(payload.get("naming_readiness_counts"), dict) else {}
    by_status = readiness_counts.get("by_status") if isinstance(readiness_counts.get("by_status"), dict) else {}
    queue = payload.get("naming_work_queue") if isinstance(payload.get("naming_work_queue"), list) else []
    lines = [
        "# Sessions Directory Index",
        "",
        "Generated table of contents for the session archive directory.",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- session_count: `{payload.get('session_count')}`",
        f"- named_session_count: `{payload.get('named_session_count')}`",
        f"- machine index: `./{SESSIONS_INDEX_JSON}`",
        f"- name map: `../{SESSION_NAME_INDEX_MARKDOWN}`",
        "",
        "## Read Order",
        "",
    ]
    for index, item in enumerate(payload.get("read_order", []), start=1):
        lines.append(f"{index}. `{item}`")
    lines.extend(["", "## Naming Readiness", ""])
    if by_status:
        for status, count in by_status.items():
            lines.append(f"- `{status}`: {count}")
    else:
        lines.append("- No readiness data generated.")
    lines.extend(["", "## Naming Work Queue", ""])
    if queue:
        lines.extend(["| priority | status | route | session | size | reasons |", "| --- | --- | --- | --- | --- | --- |"])
        for item in queue[:25]:
            if not isinstance(item, dict):
                continue
            readiness = item.get("naming_readiness") if isinstance(item.get("naming_readiness"), dict) else {}
            entry = f"{item.get('session_label')}/{SESSION_INDEX_MARKDOWN}" if item.get("session_label") else ""
            lines.append(
                "| `{priority}` | `{status}` | `{route}` | [{label}](./{entry}) | `{events}` / `{segments}` | {reasons} |".format(
                    priority=readiness.get("priority", 0),
                    status=markdown_cell(readiness.get("status")),
                    route=markdown_cell(readiness.get("route")),
                    label=markdown_cell(item.get("session_label")),
                    entry=markdown_cell(entry),
                    events=item.get("event_count", 0),
                    segments=item.get("segment_count", 0),
                    reasons=markdown_cell(", ".join(str(reason) for reason in readiness.get("reasons", []) if reason)),
                )
            )
    else:
        lines.append("- No naming work is currently queued.")
    lines.extend(["", "## Named Sessions", ""])
    named = payload.get("named_sessions", []) if isinstance(payload.get("named_sessions"), list) else []
    if named:
        lines.extend(["| session | active session name | phase/topic names | size |", "| --- | --- | --- | --- |"])
        for record in named:
            active = record.get("active_session_name") if isinstance(record.get("active_session_name"), dict) else {}
            active_text = active.get("slug") or active.get("name") or ""
            phases = record.get("phase_names") if isinstance(record.get("phase_names"), list) else []
            phase_text = ", ".join(f"`{item.get('slug')}`" for item in phases if isinstance(item, dict) and item.get("slug"))
            lines.append(
                "| [{label}](./{entry}) | {active} | {phases} | `{events}` events / `{segments}` segments |".format(
                    label=markdown_cell(record.get("session_label")),
                    entry=markdown_cell(record.get("entry") or ""),
                    active=markdown_cell(active_text),
                    phases=phase_text,
                    events=record.get("event_count", 0),
                    segments=record.get("segment_count", 0),
                )
            )
    else:
        lines.append("- No semantic session names have been attached yet.")
    lines.extend(["", "## Largest Sessions", ""])
    largest = payload.get("largest_sessions", []) if isinstance(payload.get("largest_sessions"), list) else []
    if largest:
        lines.extend(["| session | name/title | size | status |", "| --- | --- | --- | --- |"])
        for record in largest:
            active = record.get("active_session_name") if isinstance(record.get("active_session_name"), dict) else {}
            name_text = active.get("name") or record.get("title") or ""
            status = f"{record.get('archive_status')}/{record.get('distillation_status')}"
            lines.append(
                "| [{label}](./{entry}) | {name} | `{events}` events / `{segments}` segments | `{status}` |".format(
                    label=markdown_cell(record.get("session_label")),
                    entry=markdown_cell(record.get("entry") or ""),
                    name=markdown_cell(name_text),
                    events=record.get("event_count", 0),
                    segments=record.get("segment_count", 0),
                    status=markdown_cell(status),
                )
            )
    lines.extend(["", "## All Sessions By Date", ""])
    by_date = payload.get("by_date", {}) if isinstance(payload.get("by_date"), dict) else {}
    records_by_label = {
        str(record.get("session_label") or ""): record
        for record in payload.get("sessions", [])
        if isinstance(record, dict)
    }
    for date, labels in by_date.items():
        lines.extend([f"### {date}", ""])
        lines.extend(["| session | name/title | readiness | size | cwd |", "| --- | --- | --- | --- | --- |"])
        for label in labels if isinstance(labels, list) else []:
            record = records_by_label.get(str(label), {})
            active = record.get("active_session_name") if isinstance(record.get("active_session_name"), dict) else {}
            readiness = record.get("naming_readiness") if isinstance(record.get("naming_readiness"), dict) else {}
            name_text = active.get("name") or record.get("title") or ""
            lines.append(
                "| [{label}](./{entry}) | {name} | `{readiness}` | `{events}` / `{segments}` | `{cwd}` |".format(
                    label=markdown_cell(record.get("session_label")),
                    entry=markdown_cell(record.get("entry") or ""),
                    name=markdown_cell(name_text),
                    readiness=markdown_cell(readiness.get("status")),
                    events=record.get("event_count", 0),
                    segments=record.get("segment_count", 0),
                    cwd=markdown_cell(record.get("cwd")),
                )
            )
        lines.append("")
    return "\n".join(lines)


def build_naming_readiness_report(
    aoa_root: Path,
    *,
    target: str = "all",
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    refresh_indexes: bool = False,
    write_report: bool = False,
) -> dict[str, Any]:
    if target == "all":
        records = chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    else:
        records = [resolve_session_record(aoa_root, target)]
    policy = batch_distillation_policy(aoa_root)
    results: list[dict[str, Any]] = []
    for record in records:
        session_dir = session_dir_from_record(record)
        manifest = read_json(session_dir / "session.manifest.json", {})
        if not isinstance(manifest, dict) or not manifest:
            results.append(
                {
                    "session_id": record.get("session_id"),
                    "session_label": record.get("session_label"),
                    "path": str(session_dir),
                    "naming_readiness": {
                        "schema_version": SCHEMA_VERSION,
                        "status": "blocked",
                        "route": "repair_manifest_before_naming",
                        "priority": 100,
                        "reasons": ["missing_manifest"],
                        "blockers": ["missing_manifest"],
                        "warnings": [],
                        "suggested_next": "repair manifest before naming",
                        "evidence": {},
                    },
                }
            )
            continue
        readiness = session_naming_readiness(aoa_root, session_dir, manifest, record=record, policy=policy)
        display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
        results.append(
            {
                "session_id": manifest.get("session_id") or record.get("session_id"),
                "session_label": display.get("label") or manifest.get("session_label") or record.get("session_label"),
                "session_title": display.get("title") or manifest.get("session_title") or record.get("session_title"),
                "path": str(session_dir),
                "event_count": manifest.get("latest_event_count", record.get("event_count", 0)),
                "segment_count": len(manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []),
                "cwd": (manifest.get("source") if isinstance(manifest.get("source"), dict) else {}).get("cwd")
                or record.get("cwd"),
                "naming_readiness": readiness,
            }
        )
    results.sort(
        key=lambda item: (
            int_value((item.get("naming_readiness") or {}).get("priority")),
            int_value(item.get("segment_count")),
            int_value(item.get("event_count")),
            str(item.get("session_label") or ""),
        ),
        reverse=True,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "naming_readiness_report",
        "generated_at": utc_now(),
        "ok": True,
        "aoa_root": str(aoa_root),
        "target": target,
        "selected_count": len(results),
        "naming_readiness_counts": naming_readiness_counts(results),
        "naming_work_queue": naming_work_queue(results, limit=100),
        "results": results,
    }
    if refresh_indexes:
        sessions = registry_sessions(aoa_root)
        write_session_name_index(aoa_root, sessions)
        write_sessions_directory_index(aoa_root, sessions)
        payload["refreshed_indexes"] = [
            str(aoa_root / SESSION_NAME_INDEX_JSON),
            str(aoa_root / SESSION_NAME_INDEX_MARKDOWN),
            str(aoa_root / SESSION_ROOT / SESSIONS_INDEX_JSON),
            str(aoa_root / SESSION_ROOT / SESSIONS_INDEX_MARKDOWN),
        ]
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__naming-readiness"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, naming_readiness_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def naming_readiness_markdown(payload: dict[str, Any]) -> str:
    counts = payload.get("naming_readiness_counts") if isinstance(payload.get("naming_readiness_counts"), dict) else {}
    by_status = counts.get("by_status") if isinstance(counts.get("by_status"), dict) else {}
    by_route = counts.get("by_route") if isinstance(counts.get("by_route"), dict) else {}
    lines = [
        "# Naming Readiness Report",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- target: `{payload.get('target')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        "",
        "## Status Counts",
        "",
    ]
    for status, count in by_status.items():
        lines.append(f"- `{status}`: {count}")
    lines.extend(["", "## Route Counts", ""])
    for route, count in by_route.items():
        lines.append(f"- `{route}`: {count}")
    queue = payload.get("naming_work_queue") if isinstance(payload.get("naming_work_queue"), list) else []
    lines.extend(["", "## Queue", ""])
    if queue:
        lines.extend(["| priority | status | route | session | size | reasons |", "| --- | --- | --- | --- | --- | --- |"])
        for item in queue:
            if not isinstance(item, dict):
                continue
            readiness = item.get("naming_readiness") if isinstance(item.get("naming_readiness"), dict) else {}
            lines.append(
                "| `{priority}` | `{status}` | `{route}` | `{session}` | `{events}` / `{segments}` | {reasons} |".format(
                    priority=readiness.get("priority", 0),
                    status=markdown_cell(readiness.get("status")),
                    route=markdown_cell(readiness.get("route")),
                    session=markdown_cell(item.get("session_label")),
                    events=item.get("event_count", 0),
                    segments=item.get("segment_count", 0),
                    reasons=markdown_cell(", ".join(str(reason) for reason in readiness.get("reasons", []) if reason)),
                )
            )
    else:
        lines.append("- No naming work queued.")
    lines.append("")
    return "\n".join(lines)


def registry_record(manifest: dict[str, Any], session_dir: Path) -> dict[str, Any]:
    source = manifest.get("source", {})
    display = manifest.get("display", {}) if isinstance(manifest.get("display"), dict) else {}
    semantic_names = semantic_names_payload(manifest)
    active_name = semantic_name_summary(manifest)
    active_session_name = semantic_name_summary(manifest, scope="session")
    return {
        "session_id": manifest["session_id"],
        "display": display,
        "semantic_names": semantic_names,
        "active_semantic_name": active_name,
        "active_session_name": active_session_name,
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
        semantic_names = item.get("semantic_names") if isinstance(item.get("semantic_names"), dict) else {}
        candidates.append(str(semantic_names.get("active") or ""))
        candidates.append(str(semantic_names.get("active_session") or ""))
        for semantic in semantic_names.get("names", []) if isinstance(semantic_names.get("names"), list) else []:
            if isinstance(semantic, dict):
                candidates.extend([str(semantic.get("slug") or ""), str(semantic.get("name") or "")])
        if target_text in candidates:
            return item
    lowered = target_text.lower()
    fuzzy = [
        item
        for item in sessions
        if lowered in str(item.get("session_label") or "").lower()
        or lowered in str(item.get("session_title") or "").lower()
        or lowered in str(item.get("session_id") or "").lower()
        or any(
            lowered in str(semantic.get("slug") or "").lower()
            or lowered in str(semantic.get("name") or "").lower()
            for semantic in (
                item.get("semantic_names", {}).get("names", [])
                if isinstance(item.get("semantic_names"), dict)
                and isinstance(item.get("semantic_names", {}).get("names"), list)
                else []
            )
            if isinstance(semantic, dict)
        )
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
    semantic_names = semantic_names_payload(manifest)
    active_session_name = active_semantic_name(manifest, scope="session")
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
    ]
    if active_session_name:
        anchor = active_session_name.get("anchor") if isinstance(active_session_name.get("anchor"), dict) else {}
        evidence = active_session_name.get("evidence") if isinstance(active_session_name.get("evidence"), list) else []
        coverage = active_session_name.get("coverage") if isinstance(active_session_name.get("coverage"), dict) else {}
        lines.extend(
            [
                "## Session Name Anchor",
                "",
                f"- active_session: `{semantic_names.get('active_session')}`",
                f"- name: {active_session_name.get('name')}",
                f"- kind: `{active_session_name.get('kind')}`",
                f"- evidence: `{', '.join(str(ref) for ref in evidence)}`",
                f"- coverage: `{json.dumps(coverage, ensure_ascii=False)}`",
                f"- raw_sha256: `{anchor.get('raw_sha256', '')}`",
                f"- raw_path: `{anchor.get('raw_path', '')}`",
                f"- source transcript: `{anchor.get('source_transcript_path', '')}`",
                "",
            ]
        )
    other_names = [
            item
            for item in semantic_names.get("names", [])
            if isinstance(item, dict) and item.get("slug") != semantic_names.get("active_session")
    ]
    if other_names:
        lines.extend(["## Phase And Topic Names", ""])
        for item in other_names:
            coverage = item.get("coverage") if isinstance(item.get("coverage"), dict) else {}
            coverage_note = str(coverage.get("note") or "")
            coverage_suffix = f" - {coverage_note}" if coverage_note else ""
            lines.append(
                f"- `{item.get('slug')}` ({semantic_name_scope(item)}, {item.get('kind')}, {item.get('status')}) - {item.get('name')}{coverage_suffix}"
            )
        lines.append("")
    lines.extend(
        [
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
    )
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
            importance = str(event.get("importance") or "")
            event_counts[event_type] += 1
            routes = [str(route) for route in route_map.get(event_type, [])] if isinstance(route_map.get(event_type, []), list) else []
            for route in routes:
                route_counts[route] += 1
            keep = is_first_pass_candidate_event_record(event)
            if keep and len(selected_by_type[event_type]) < max_events_per_type:
                selected_by_type[event_type].append(
                    {
                        "event_id": event.get("event_id"),
                        "type": event_type,
                        "family": event.get("family"),
                        "phase": event.get("phase"),
                        "actor": event.get("actor"),
                        "action": event.get("action"),
                        "outcome": event.get("outcome"),
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


def reindex_session_from_raw(aoa_root: Path, record: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    session_dir = session_dir_from_record(record)
    manifest_path = session_dir / "session.manifest.json"
    manifest = read_json(manifest_path, {})
    if not isinstance(manifest, dict) or not manifest:
        return {
            "session_id": record.get("session_id"),
            "session_label": record.get("session_label"),
            "session_dir": str(session_dir),
            "status": "diagnostic",
            "diagnostics": ["missing_session_manifest"],
        }
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    raw_path = Path(str(raw.get("path") or ""))
    archive_status = str(manifest.get("archive_status") or "")
    if archive_status not in {"indexed", "raw_mirrored_index_deferred"}:
        return {
            "session_id": manifest.get("session_id"),
            "session_label": manifest.get("session_label"),
            "session_dir": str(session_dir),
            "status": "skipped",
            "diagnostics": [f"archive_status:{archive_status or 'missing'}"],
        }
    if not raw_path.is_file():
        return {
            "session_id": manifest.get("session_id"),
            "session_label": manifest.get("session_label"),
            "session_dir": str(session_dir),
            "status": "diagnostic",
            "diagnostics": ["raw_missing"],
        }

    if dry_run:
        return {
            "session_id": manifest.get("session_id"),
            "session_label": manifest.get("session_label"),
            "session_dir": str(session_dir),
            "status": "planned",
            "raw_path": str(raw_path),
            "segment_count": len(manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []),
        }

    now = utc_now()
    events = parse_raw_events(raw_path)
    clear_generated_segments(session_dir)
    raw_rel = "raw/session.raw.jsonl"
    segment_payloads = [
        write_segment(session_dir, raw_rel, segment_no, role, events[start:end])
        for segment_no, (start, end, role) in enumerate(segment_ranges(events))
    ]
    manifest["archive_status"] = "indexed"
    manifest["segments"] = segment_payloads
    manifest["latest_event_count"] = len(events)
    manifest["updated_at"] = now
    manifest["index_schema"] = {
        "universal_event_facets": True,
        "relationships": True,
        "reindexed_at": now,
    }
    if isinstance(manifest.get("raw"), dict):
        manifest["raw"]["line_count"] = len(events)
        manifest["raw"]["bytes"] = raw_path.stat().st_size
        manifest["raw"]["sha256"] = sha256_file(raw_path)
        manifest["raw"]["indexing_status"] = "indexed"
    refresh_semantic_name_anchors(session_dir, manifest)
    write_json(manifest_path, manifest)
    raw_source_path = session_dir / "raw" / RAW_SOURCE_JSON
    raw_source = read_json(raw_source_path, {})
    if isinstance(raw_source, dict) and raw_source:
        raw_source["sha256"] = manifest.get("raw", {}).get("sha256") if isinstance(manifest.get("raw"), dict) else raw_source.get("sha256")
        raw_source["updated_at"] = now
        raw_source["indexing_status"] = "indexed"
        write_json(raw_source_path, raw_source)
    write_session_index(session_dir, manifest, events)
    update_registry(aoa_root, manifest, session_dir)
    return {
        "session_id": manifest.get("session_id"),
        "session_label": manifest.get("session_label"),
        "session_dir": str(session_dir),
        "status": "reindexed",
        "event_count": len(events),
        "segment_count": len(segment_payloads),
    }


def reindex_sessions(
    *,
    aoa_root: Path,
    target: str = "all",
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    if target and target != "all":
        records = [resolve_session_record(aoa_root, target)]
    else:
        records = chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    counts: Counter[str] = Counter()
    results: list[dict[str, Any]] = []
    for record in records:
        result = reindex_session_from_raw(aoa_root, record, dry_run=dry_run)
        counts[str(result.get("status") or "unknown")] += 1
        results.append(result)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "session_reindex",
        "generated_at": now,
        "ok": counts.get("diagnostic", 0) == 0,
        "aoa_root": str(aoa_root),
        "target": target,
        "since": since,
        "until": until,
        "limit": limit,
        "dry_run": dry_run,
        "selected_count": len(records),
        "counts": dict(counts),
        "results": results,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__reindex-sessions"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, reindex_sessions_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def reindex_sessions_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Session Reindex",
        "",
        "Regenerates generated segment Markdown and segment indexes from preserved raw JSONL.",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- aoa_root: `{payload.get('aoa_root')}`",
        f"- target: `{payload.get('target')}`",
        f"- since: `{payload.get('since')}`",
        f"- until: `{payload.get('until')}`",
        f"- dry_run: `{payload.get('dry_run')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- counts: `{json.dumps(payload.get('counts', {}), ensure_ascii=False)}`",
        "",
        "| status | session | events | segments | diagnostics |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for result in payload.get("results", []) if isinstance(payload.get("results"), list) else []:
        if not isinstance(result, dict):
            continue
        lines.append(
            "| {status} | `{session}` | {events} | {segments} | {diagnostics} |".format(
                status=str(result.get("status") or ""),
                session=str(result.get("session_label") or result.get("session_id") or ""),
                events=str(result.get("event_count") or ""),
                segments=str(result.get("segment_count") or ""),
                diagnostics=", ".join(str(item) for item in result.get("diagnostics", [])),
            )
        )
    lines.append("")
    return "\n".join(lines)


def title_repair_candidate(aoa_root: Path, record: dict[str, Any]) -> dict[str, Any]:
    session_dir = session_dir_from_record(record)
    manifest = read_json(session_dir / "session.manifest.json", {})
    if not isinstance(manifest, dict) or not manifest:
        return {
            "session_id": record.get("session_id"),
            "session_label": record.get("session_label"),
            "session_dir": str(session_dir),
            "status": "diagnostic",
            "diagnostics": ["missing_session_manifest"],
        }
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    raw_path = Path(str(raw.get("path") or "")) if raw.get("path") else session_dir / "raw" / "session.raw.jsonl"
    if not raw_path.is_file():
        return {
            "session_id": manifest.get("session_id"),
            "session_label": manifest.get("session_label"),
            "session_dir": str(session_dir),
            "status": "diagnostic",
            "diagnostics": ["raw_missing"],
        }

    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    transcript_value = source.get("transcript_path")
    transcript_path = Path(str(transcript_value)) if transcript_value else None
    events = parse_raw_event_sample(raw_path, max_lines=5000)
    fallback = str(manifest.get("created_at") or manifest.get("updated_at") or utc_now())
    entry_event = {
        "cwd": source.get("cwd") or record.get("cwd"),
        "model": source.get("model"),
        "permission_mode": source.get("permission_mode"),
    }
    proposed_date = first_session_date(events, entry_event, transcript_path, fallback)
    proposed_title, proposed_source = session_title(events, entry_event, transcript_path)
    display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
    current_title = str(display.get("title") or manifest.get("session_title") or "")
    current_label = str(display.get("label") or manifest.get("session_label") or session_dir.name)
    current_source = str(display.get("title_source") or "")
    sequence = label_sequence_from(current_label, proposed_date) or int(display.get("sequence") or 0) or next_daily_sequence(aoa_root, proposed_date, str(manifest.get("session_id") or ""))
    base_label = f"{proposed_date}__{sequence:03d}__{readable_slug(proposed_title)}"
    reasons: list[str] = []
    if not current_title.strip():
        reasons.append("missing_title")
    if weak_title_text(current_title):
        reasons.append("weak_title")
    if weak_label_text(current_label):
        reasons.append("weak_label")
    if display_quality(current_source) < display_quality(proposed_source):
        reasons.append(f"title_source_upgrade:{current_source or 'missing'}->{proposed_source}")
    if current_label != base_label and reasons:
        reasons.append("label_would_change")
    repair_needed = bool(reasons) and bool(proposed_title.strip()) and not weak_title_text(proposed_title)
    return {
        "session_id": manifest.get("session_id"),
        "session_label": current_label,
        "session_dir": str(session_dir),
        "status": "candidate" if repair_needed else "unchanged",
        "repair_needed": repair_needed,
        "reasons": reasons,
        "current": {
            "title": current_title,
            "title_source": current_source,
            "label": current_label,
            "path": str(session_dir),
        },
        "proposed": {
            "date": proposed_date,
            "sequence": sequence,
            "title": proposed_title,
            "title_source": proposed_source,
            "label": base_label,
            "path": str(aoa_root / SESSION_ROOT / base_label),
        },
    }


def unique_session_label(aoa_root: Path, base_label: str, session_id: str, current_dir: Path) -> str:
    label = base_label
    for suffix in ["", *[f"-{idx:02d}" for idx in range(2, 100)]]:
        label = f"{base_label}{suffix}"
        target_dir = aoa_root / SESSION_ROOT / label
        if target_dir == current_dir or not target_dir.exists():
            return label
        target_manifest = read_json(target_dir / "session.manifest.json", {})
        if isinstance(target_manifest, dict) and target_manifest.get("session_id") == session_id:
            return label
    return f"{base_label}-{safe_slug(session_id)[:10]}"


def apply_title_repair(aoa_root: Path, candidate: dict[str, Any]) -> dict[str, Any]:
    session_dir = Path(str(candidate.get("session_dir") or ""))
    manifest_path = session_dir / "session.manifest.json"
    manifest = read_json(manifest_path, {})
    if not isinstance(manifest, dict) or not manifest:
        return {**candidate, "status": "diagnostic", "diagnostics": ["missing_session_manifest"]}
    proposed = candidate.get("proposed") if isinstance(candidate.get("proposed"), dict) else {}
    session_id = str(manifest.get("session_id") or candidate.get("session_id") or "")
    label = unique_session_label(aoa_root, str(proposed.get("label") or session_dir.name), session_id, session_dir)
    target_dir = aoa_root / SESSION_ROOT / label
    session_dir = merge_or_move_session_dir(session_dir, target_dir)
    display = {
        "date": proposed.get("date"),
        "sequence": proposed.get("sequence"),
        "title": proposed.get("title"),
        "title_source": proposed.get("title_source"),
        "label": label,
        "path": str(session_dir),
        "archive_path": str(session_dir),
        "navigation_path": str(session_dir),
    }
    now = utc_now()
    manifest["display"] = display
    manifest["session_label"] = label
    manifest["session_title"] = proposed.get("title")
    manifest["updated_at"] = now
    update_artifact_paths_after_move(session_dir, manifest)
    write_json(session_dir / "session.manifest.json", manifest)
    update_session_index_identity(session_dir, manifest)
    update_registry(aoa_root, manifest, session_dir)
    repaired = {**candidate, "status": "repaired", "session_label": label, "session_dir": str(session_dir)}
    repaired["proposed"] = {**proposed, "label": label, "path": str(session_dir)}
    return repaired


def repair_session_titles(
    *,
    aoa_root: Path,
    target: str = "all",
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    apply: bool = False,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    if target and target != "all":
        records = [resolve_session_record(aoa_root, target)]
    else:
        records = chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for record in records:
        candidate = title_repair_candidate(aoa_root, record)
        if candidate.get("status") == "diagnostic":
            result = candidate
        elif candidate.get("repair_needed"):
            result = apply_title_repair(aoa_root, candidate) if apply else {**candidate, "status": "planned"}
        else:
            result = candidate
        counts[str(result.get("status") or "unknown")] += 1
        results.append(result)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "session_title_repair",
        "generated_at": now,
        "ok": counts.get("diagnostic", 0) == 0,
        "aoa_root": str(aoa_root),
        "target": target,
        "since": since,
        "until": until,
        "limit": limit,
        "apply": apply,
        "selected_count": len(records),
        "counts": dict(counts),
        "results": results,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__repair-session-titles"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, repair_session_titles_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def repair_session_titles_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Session Title Repair",
        "",
        "Repairs weak generated session titles without changing preserved raw evidence.",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- aoa_root: `{payload.get('aoa_root')}`",
        f"- target: `{payload.get('target')}`",
        f"- since: `{payload.get('since')}`",
        f"- until: `{payload.get('until')}`",
        f"- apply: `{payload.get('apply')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- counts: `{json.dumps(payload.get('counts', {}), ensure_ascii=False)}`",
        "",
        "| status | session | current | proposed | reasons |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in payload.get("results", []) if isinstance(payload.get("results"), list) else []:
        if not isinstance(result, dict):
            continue
        current = result.get("current") if isinstance(result.get("current"), dict) else {}
        proposed = result.get("proposed") if isinstance(result.get("proposed"), dict) else {}
        lines.append(
            "| {status} | `{session}` | {current} | {proposed} | {reasons} |".format(
                status=str(result.get("status") or ""),
                session=str(result.get("session_label") or result.get("session_id") or ""),
                current=str(current.get("label") or current.get("title") or "").replace("|", "\\|"),
                proposed=str(proposed.get("label") or proposed.get("title") or "").replace("|", "\\|"),
                reasons=", ".join(str(item) for item in result.get("reasons", [])),
            )
        )
    lines.append("")
    return "\n".join(lines)


def set_session_semantic_name(
    *,
    aoa_root: Path,
    target: str,
    name: str,
    kind: str = "semantic_alias",
    scope: str = "session",
    evidence_refs: list[str] | None = None,
    from_line: int | None = None,
    to_line: int | None = None,
    coverage_note: str | None = None,
    source: str = "operator",
    note: str | None = None,
    apply: bool = False,
    replace: bool = False,
    verify_raw_hash: bool = False,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    record = resolve_session_record(aoa_root, target)
    session_dir = session_dir_from_record(record)
    manifest_path = session_dir / "session.manifest.json"
    manifest = read_json(manifest_path, {})
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError(f"missing session manifest: {session_dir}")
    if scope not in {"session", "phase", "topic", "alias"}:
        raise ValueError(f"invalid semantic name scope: {scope}")
    slug = semantic_name_slug(name)
    payload = semantic_names_payload(manifest)
    existing_names = payload.get("names", [])
    evidence = [str(ref).strip() for ref in evidence_refs or [] if str(ref).strip()]
    raw_ranges: list[dict[str, int]] = []
    if from_line is not None or to_line is not None:
        start = int(from_line or 0)
        end = int(to_line or from_line or 0)
        raw_ranges.append({"from_line": start, "to_line": end})
    anchor: dict[str, Any] = {}
    diagnostics: list[str] = []
    try:
        anchor = build_identity_anchor(session_dir, manifest, verify_raw_hash=verify_raw_hash)
    except ValueError as exc:
        diagnostics.append(str(exc))
        anchor = build_identity_anchor(session_dir, manifest, verify_raw_hash=False)
    proposed = {
        "schema_version": SCHEMA_VERSION,
        "name": name.strip(),
        "slug": slug,
        "scope": scope,
        "kind": kind,
        "status": semantic_name_status_for_scope(scope),
        "source": source,
        "created_at": now,
        "updated_at": now,
        "note": note or "",
        "evidence": evidence,
        "coverage": {
            "scope": scope,
            "raw_ranges": raw_ranges,
            "note": coverage_note or "",
        },
        "anchor": {**anchor, "anchored_at": now, "refreshed_at": now},
    }
    policy = naming_policy(aoa_root)
    banned_terms = (
        set(policy.get("banned_durable_name_terms", []))
        if isinstance(policy.get("banned_durable_name_terms"), list)
        else set(DEFAULT_BANNED_DURABLE_NAME_TERMS)
    )
    diagnostics.extend(validate_semantic_name_record(manifest, session_dir, proposed, banned_terms=banned_terms))
    duplicate = next((item for item in existing_names if isinstance(item, dict) and item.get("slug") == slug), None)
    if duplicate and not replace:
        diagnostics.append(f"semantic_name_already_exists:{slug}")

    ok_to_apply = apply and not diagnostics
    result_status = "planned"
    if ok_to_apply:
        updated_names: list[dict[str, Any]] = []
        replaced = False
        for item in existing_names:
            if isinstance(item, dict) and item.get("slug") == slug:
                updated_names.append({**item, **proposed, "created_at": item.get("created_at") or proposed["created_at"]})
                replaced = True
            elif isinstance(item, dict):
                if scope == "session" and semantic_name_scope(item) == "session" and item.get("status") == "active":
                    item = {**item, "status": "alias", "updated_at": now}
                updated_names.append(item)
        if not replaced:
            updated_names.append(proposed)
        payload["active"] = slug
        if scope == "session":
            payload["active_session"] = slug
        payload["names"] = updated_names
        manifest["semantic_names"] = payload
        refresh_semantic_name_anchors(session_dir, manifest, verify_raw_hash=verify_raw_hash)
        manifest["updated_at"] = now
        write_json(manifest_path, manifest)
        update_session_index_identity(session_dir, manifest)
        update_registry(aoa_root, manifest, session_dir)
        result_status = "applied"
    elif diagnostics:
        result_status = "diagnostic"

    out = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "session_semantic_name",
        "generated_at": now,
        "ok": not diagnostics,
        "status": result_status,
        "apply": apply,
        "aoa_root": str(aoa_root),
        "session_id": manifest.get("session_id"),
        "session_label": (manifest.get("display") if isinstance(manifest.get("display"), dict) else {}).get("label")
        or manifest.get("session_label"),
        "session_dir": str(session_dir),
        "proposed": proposed,
        "diagnostics": diagnostics,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__session-semantic-name__{slug}"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, out)
        write_markdown(report_md, session_semantic_name_markdown(out))
        out["report_json"] = str(report_json)
        out["report_markdown"] = str(report_md)
    return out


def session_semantic_name_markdown(payload: dict[str, Any]) -> str:
    proposed = payload.get("proposed") if isinstance(payload.get("proposed"), dict) else {}
    anchor = proposed.get("anchor") if isinstance(proposed.get("anchor"), dict) else {}
    coverage = proposed.get("coverage") if isinstance(proposed.get("coverage"), dict) else {}
    lines = [
        "# Session Semantic Name",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- status: `{payload.get('status')}`",
        f"- apply: `{payload.get('apply')}`",
        f"- session: `{payload.get('session_label') or payload.get('session_id')}`",
        f"- name: {proposed.get('name')}",
        f"- slug: `{proposed.get('slug')}`",
        f"- scope: `{proposed.get('scope')}`",
        f"- kind: `{proposed.get('kind')}`",
        f"- evidence: `{', '.join(str(ref) for ref in proposed.get('evidence', []) if ref)}`",
        f"- coverage: `{json.dumps(coverage, ensure_ascii=False)}`",
        f"- raw_sha256: `{anchor.get('raw_sha256', '')}`",
        f"- raw_path: `{anchor.get('raw_path', '')}`",
        f"- source transcript: `{anchor.get('source_transcript_path', '')}`",
        "",
    ]
    diagnostics = payload.get("diagnostics", [])
    if diagnostics:
        lines.extend(["## Diagnostics", ""])
        for item in diagnostics if isinstance(diagnostics, list) else []:
            lines.append(f"- `{item}`")
        lines.append("")
    return "\n".join(lines)


def default_batch_distillation_policy() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "review_layers": [
            "machine_index_layer",
            "agent_project_grounded_layer",
            "operator_sampling_layer",
            "promotion_review_layer",
        ],
        "promotion_limit": "automatic layers may write provisional artifacts only",
        "operator_reading_strategy": "sample evidence and review promoted claims, not reread every raw transcript",
        "project_grounding_file_names": DEFAULT_PROJECT_GROUNDING_FILE_NAMES,
        "large_session_segment_threshold": 24,
        "huge_session_segment_threshold": 100,
        "manual_review_priority_thresholds": {
            "deep": 100,
            "standard": 20,
            "sample": 1,
        },
        "manual_review_weights": {
            "huge_session": 100,
            "large_session": 30,
            "SECURITY_OR_SECRET_RISK": 12,
            "ERROR": 2,
            "DEAD_BRANCH": 8,
            "PROCESS_LESSON": 6,
            "ASSUMPTION": 4,
            "DECISION": 3,
            "OPEN_THREAD": 2,
            "FINAL_STATE": 1,
        },
        "manual_review_event_types": [
            "DECISION",
            "ASSUMPTION",
            "ERROR",
            "OPEN_THREAD",
            "DEAD_BRANCH",
            "PROCESS_LESSON",
            "SECURITY_OR_SECRET_RISK",
            "FINAL_STATE",
        ],
        "mechanics_routes": [
            "automation_macro",
            "automation_seed",
            "preflight_candidate",
            "safe_runner_rule",
            "parser_candidate",
            "detector",
            "regression_test",
            "skill_amendment",
            "playbook_patch",
            "archive_trigger_tuning",
            "resume_template_improvement",
            "hook_contract_update",
        ],
        "mechanics_signal_event_types": [
            "ERROR",
            "PROCESS_LESSON",
            "OPTIMIZATION_CANDIDATE",
            "SECURITY_OR_SECRET_RISK",
            "DEAD_BRANCH",
        ],
        "mechanics_signal_tags": [
            "destructive_command_signal",
        ],
        "mechanics_signal_outcomes": [
            "failed",
            "risk",
        ],
        "auto_actions": ["write_provisional_first_pass_distillation"],
    }


def batch_distillation_policy(aoa_root: Path) -> dict[str, Any]:
    policy = default_batch_distillation_policy()
    configured = read_json(aoa_root / BATCH_DISTILLATION_POLICY_PATH, {})
    if isinstance(configured, dict):
        for key, value in configured.items():
            if key == "schema_version":
                continue
            policy[key] = value
    return policy


def find_project_grounding_files(start: Path, names: list[str]) -> list[dict[str, str]]:
    if start.is_file():
        start = start.parent
    files: list[dict[str, str]] = []
    for parent in [start, *start.parents]:
        for name in names:
            candidate = parent / name
            if candidate.is_file():
                files.append({"name": name, "path": str(candidate)})
        if files:
            break
        if parent.parent == parent:
            break
    return files


ABSOLUTE_PATH_RE = re.compile(r"(?<![\w])(?:~|/)[^\s`\"'<>|),;]+")


def path_mentions_from_text(text: str) -> list[str]:
    mentions: list[str] = []
    for match in ABSOLUTE_PATH_RE.finditer(text or ""):
        value = match.group(0).rstrip(".,:;)]}")
        if value in {"/", "~"}:
            continue
        mentions.append(value)
    return mentions


def inferred_owner_root_for_path(path_value: str) -> str | None:
    raw = str(path_value or "").strip()
    if not raw:
        return None
    try:
        expanded = str(Path(raw).expanduser())
    except RuntimeError:
        expanded = raw
    parts = Path(expanded).parts
    if len(parts) < 3 or parts[0] != "/":
        return None
    if len(parts) >= 5 and parts[:3] == ("/", "srv", "work"):
        return str(Path(*parts[:4]))
    if len(parts) >= 6 and parts[:4] == ("/", "srv", "games", "modding"):
        return str(Path(*parts[:5]))
    if len(parts) >= 3 and parts[:2] == ("/", "srv"):
        return str(Path(*parts[:3]))
    if len(parts) >= 5 and parts[:4] == ("/", "home", "dionysus", "src"):
        return str(Path(*parts[:5]))
    if len(parts) >= 6 and parts[:5] == ("/", "home", "dionysus", ".codex", "memories"):
        return str(Path(*parts[:5]))
    if len(parts) >= 3 and parts[:3] == ("/", "home", "dionysus"):
        return "/home/dionysus"
    return None


def owner_name_from_root(owner_root: str | None) -> str | None:
    if not owner_root:
        return None
    path = Path(owner_root)
    if str(path) == "/home/dionysus":
        return "home"
    if path.name:
        return path.name
    return owner_root


def owner_resolution_for_session(
    manifest: dict[str, Any],
    record: dict[str, Any],
    project_grounding: dict[str, Any],
) -> dict[str, Any]:
    scores: Counter[str] = Counter()
    evidence_by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def add_evidence(owner_root: str | None, *, score: int, kind: str, value: Any, ref: str | None = None) -> None:
        if not owner_root:
            return
        scores[owner_root] += score
        bucket = evidence_by_root[owner_root]
        if len(bucket) < 12:
            item: dict[str, Any] = {"kind": kind, "value": short_text(value, max_chars=160), "score": score}
            if ref:
                item["ref"] = ref
            bucket.append(item)

    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    cwd_value = source.get("cwd") or record.get("cwd") or project_grounding.get("cwd")
    if cwd_value:
        cwd_path = Path(str(cwd_value)).expanduser()
        add_evidence(inferred_owner_root_for_path(str(cwd_value)), score=8 if cwd_path.exists() else 1, kind="cwd", value=cwd_value)

    for file_record in project_grounding.get("files", []) if isinstance(project_grounding.get("files"), list) else []:
        if isinstance(file_record, dict) and file_record.get("path"):
            score = 1 if project_grounding.get("fallback_used") else 4
            add_evidence(inferred_owner_root_for_path(str(file_record["path"])), score=score, kind="grounding_file", value=file_record.get("path"))

    for segment in manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []:
        if not isinstance(segment, dict) or not segment.get("index"):
            continue
        segment_index = read_json(Path(str(segment["index"])), {})
        events = segment_index.get("events", []) if isinstance(segment_index, dict) else []
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            texts: list[str] = [str(event.get("title") or "")]
            facets = event.get("facets") if isinstance(event.get("facets"), dict) else {}
            for key in ("command", "object", "path"):
                if facets.get(key):
                    texts.append(str(facets[key]))
            for text in texts:
                for mention in path_mentions_from_text(text):
                    add_evidence(
                        inferred_owner_root_for_path(mention),
                        score=4,
                        kind="indexed_path",
                        value=mention,
                        ref=str(event.get("md_anchor") or event.get("raw_ref") or ""),
                    )

    if not scores:
        return {
            "status": "unresolved",
            "owner_root": None,
            "owner_name": None,
            "confidence": "none",
            "score": 0,
            "fallback_grounding_used": bool(project_grounding.get("fallback_used")),
            "evidence": [],
            "alternates": [],
        }

    ranked = scores.most_common()
    owner_root, score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if second_score and second_score >= max(4, int(score * 0.75)):
        status = "ambiguous"
        confidence = "low"
    elif score >= 10:
        status = "resolved_from_evidence" if project_grounding.get("fallback_used") else "resolved"
        confidence = "high"
    elif score >= 4:
        status = "resolved_from_evidence" if project_grounding.get("fallback_used") else "resolved_low_confidence"
        confidence = "medium"
    else:
        status = "weak_signal"
        confidence = "low"
    fallback_root = None
    fallback_workspace = project_grounding.get("fallback_workspace_root")
    if fallback_workspace:
        fallback_root = inferred_owner_root_for_path(str(fallback_workspace))
    if project_grounding.get("fallback_used") and owner_root == fallback_root and score <= 4:
        status = "fallback_only"
        confidence = "low"

    return {
        "status": status,
        "owner_root": owner_root,
        "owner_name": owner_name_from_root(owner_root),
        "confidence": confidence,
        "score": score,
        "fallback_grounding_used": bool(project_grounding.get("fallback_used")),
        "evidence": evidence_by_root.get(owner_root, []),
        "alternates": [
            {"owner_root": root, "owner_name": owner_name_from_root(root), "score": item_score}
            for root, item_score in ranked[1:6]
        ],
    }


def project_grounding_for_session(
    manifest: dict[str, Any],
    record: dict[str, Any],
    policy: dict[str, Any],
    *,
    fallback_workspace_root: Path | None = None,
) -> dict[str, Any]:
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    cwd_value = source.get("cwd") or record.get("cwd")
    grounding: dict[str, Any] = {
        "cwd": cwd_value,
        "files": [],
        "status": "not_found",
    }
    configured_names = policy.get("project_grounding_file_names", DEFAULT_PROJECT_GROUNDING_FILE_NAMES)
    names = [str(item) for item in configured_names if str(item)] if isinstance(configured_names, list) else DEFAULT_PROJECT_GROUNDING_FILE_NAMES

    files: list[dict[str, str]] = []
    if cwd_value:
        start = Path(str(cwd_value)).expanduser()
        if start.exists():
            files = find_project_grounding_files(start, names)
        else:
            grounding["status"] = "cwd_not_found"
    else:
        grounding["status"] = "cwd_missing"

    if not files and fallback_workspace_root and fallback_workspace_root.exists():
        files = find_project_grounding_files(fallback_workspace_root.expanduser(), names)
        if files:
            grounding["fallback_workspace_root"] = str(fallback_workspace_root)
            grounding["fallback_used"] = True
    grounding["files"] = files
    if files:
        grounding["status"] = "workspace_fallback_grounded" if grounding.get("fallback_used") else "grounded"
    elif grounding["status"] == "not_found":
        grounding["status"] = "no_project_files_found"
    return grounding


def session_record_date(record: dict[str, Any]) -> str:
    display = record.get("display") if isinstance(record.get("display"), dict) else {}
    for value in (display.get("date"), record.get("session_label"), record.get("updated_at")):
        if not value:
            continue
        match = re.search(r"(20\d{2})-([01]\d)-([0-3]\d)", str(value))
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return ""


def session_record_sequence(record: dict[str, Any]) -> int:
    label = str(record.get("session_label") or "")
    match = re.match(r"20\d{2}-[01]\d-[0-3]\d__(\d{3})__", label)
    return int(match.group(1)) if match else 0


def chronological_session_records(
    aoa_root: Path,
    *,
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    since_date = parse_date_arg(since)
    until_date = parse_date_arg(until)
    records: list[dict[str, Any]] = []
    for record in registry_sessions(aoa_root):
        record_date = session_record_date(record)
        if since_date and record_date < since_date:
            continue
        if until_date and record_date > until_date:
            continue
        records.append(record)
    records.sort(
        key=lambda item: (
            session_record_date(item),
            session_record_sequence(item),
            str(item.get("session_label") or ""),
            str(item.get("session_id") or ""),
        )
    )
    return records[:limit] if limit is not None else records


def route_map_for_distillation(aoa_root: Path) -> dict[str, list[str]]:
    routes_config = read_json(aoa_root / "config/event-distillation-routes.json", {})
    raw_routes = routes_config.get("routes", {}) if isinstance(routes_config, dict) else {}
    if not isinstance(raw_routes, dict):
        return {}
    route_map: dict[str, list[str]] = {}
    for event_type, routes in raw_routes.items():
        if isinstance(routes, list):
            route_map[str(event_type)] = [str(route) for route in routes]
    return route_map


def first_wave_session_profile(
    aoa_root: Path,
    record: dict[str, Any],
    *,
    policy: dict[str, Any],
    route_map: dict[str, list[str]],
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    session_dir = session_dir_from_record(record)
    manifest_path = session_dir / "session.manifest.json"
    manifest = read_json(manifest_path, {})
    event_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    mechanics_signal_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    phase_counts: Counter[str] = Counter()
    actor_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    missing_indexes: list[str] = []
    diagnostics: list[str] = []
    manual_review_reasons: list[str] = []
    mechanics_reasons: list[str] = []
    candidate_event_count = 0

    if not isinstance(manifest, dict) or not manifest:
        diagnostics.append("missing_session_manifest")
        manifest = {}

    archive_status = str(manifest.get("archive_status") or record.get("archive_status") or "")
    distillation_status = str(manifest.get("distillation_status") or record.get("distillation_status") or "raw_archived")
    segments = manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    raw_path = Path(str(raw.get("path") or "")) if raw.get("path") else None
    raw_exists = bool(raw_path and raw_path.exists())
    project_grounding = project_grounding_for_session(manifest, record, policy, fallback_workspace_root=workspace_root)
    owner_resolution = owner_resolution_for_session(manifest, record, project_grounding)

    if archive_status != "indexed":
        diagnostics.append(f"archive_status:{archive_status or 'missing'}")
    if raw_path and not raw_exists:
        diagnostics.append("raw_missing")
    if not segments and archive_status == "indexed":
        diagnostics.append("no_segments")

    mechanics_event_types = {
        str(item)
        for item in policy.get("mechanics_signal_event_types", [])
        if str(item)
    }
    mechanics_tags = {
        str(item)
        for item in policy.get("mechanics_signal_tags", [])
        if str(item)
    }
    mechanics_outcomes = {
        str(item)
        for item in policy.get("mechanics_signal_outcomes", [])
        if str(item)
    }

    for segment in segments:
        if not isinstance(segment, dict) or not segment.get("index"):
            missing_indexes.append(str(segment.get("segment_id") or "unknown"))
            continue
        index_path = Path(str(segment["index"]))
        if not index_path.exists():
            missing_indexes.append(str(index_path))
            continue
        segment_index = read_json(index_path, {})
        events = segment_index.get("events", []) if isinstance(segment_index, dict) else []
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("type") or "RAW_EVENT")
            event_counts[event_type] += 1
            if is_first_pass_candidate_event_record(event):
                candidate_event_count += 1
            family_counts[str(event.get("family") or "unclassified")] += 1
            phase_counts[str(event.get("phase") or "unclassified")] += 1
            actor_counts[str(event.get("actor") or "unclassified")] += 1
            outcome_counts[str(event.get("outcome") or "unclassified")] += 1
            tags = [str(tag) for tag in event.get("tags", [])] if isinstance(event.get("tags"), list) else []
            routes = route_map.get(event_type, [])
            for route in routes:
                route_counts[route] += 1
            for tag in tags:
                tag_counts[tag] += 1
            mechanics_relevant = (
                event_type in mechanics_event_types
                or bool(mechanics_tags.intersection(tags))
                or str(event.get("outcome") or "") in mechanics_outcomes
            )
            if mechanics_relevant:
                for route in routes:
                    mechanics_signal_counts[route] += 1

    if missing_indexes:
        diagnostics.append("missing_segment_indexes")

    large_threshold = int(policy.get("large_session_segment_threshold", 24) or 24)
    huge_threshold = int(policy.get("huge_session_segment_threshold", 100) or 100)
    segment_count = len(segments)
    review_score = 0
    review_weights = policy.get("manual_review_weights", {})
    if not isinstance(review_weights, dict):
        review_weights = {}
    if segment_count >= huge_threshold:
        manual_review_reasons.append("huge_session")
        review_score += int(review_weights.get("huge_session", 100) or 100)
    elif segment_count >= large_threshold:
        manual_review_reasons.append("large_session")
        review_score += int(review_weights.get("large_session", 30) or 30)

    manual_types = [str(item) for item in policy.get("manual_review_event_types", []) if str(item)]
    for event_type in manual_types:
        count = event_counts.get(event_type, 0)
        if count:
            manual_review_reasons.append(f"{event_type}:{count}")
            review_score += min(count, 50) * int(review_weights.get(event_type, 1) or 1)

    thresholds = policy.get("manual_review_priority_thresholds", {})
    if not isinstance(thresholds, dict):
        thresholds = {}
    deep_threshold = int(thresholds.get("deep", 100) or 100)
    standard_threshold = int(thresholds.get("standard", 20) or 20)
    sample_threshold = int(thresholds.get("sample", 1) or 1)
    if review_score >= deep_threshold:
        review_priority = "deep"
    elif review_score >= standard_threshold:
        review_priority = "standard"
    elif review_score >= sample_threshold:
        review_priority = "sample"
    else:
        review_priority = "none"

    mechanics_routes = [str(item) for item in policy.get("mechanics_routes", []) if str(item)]
    for route in mechanics_routes:
        count = mechanics_signal_counts.get(route, 0)
        if count:
            mechanics_reasons.append(f"{route}:{count}")

    lanes: list[str] = []
    if diagnostics:
        lanes.append("diagnostic")
    else:
        lanes.append("auto_first_pass")
    if manual_review_reasons:
        lanes.append("manual_review")
        lanes.append(f"manual_review_{review_priority}")
    if mechanics_reasons:
        lanes.append("mechanics_candidate")
    if not diagnostics and not manual_review_reasons and not mechanics_reasons:
        lanes.append("low_risk_indexed")

    return {
        "session_id": record.get("session_id") or manifest.get("session_id"),
        "session_label": record.get("session_label") or manifest.get("session_label"),
        "session_dir": str(session_dir),
        "session_date": session_record_date(record),
        "archive_status": archive_status,
        "distillation_status": distillation_status,
        "segment_count": segment_count,
        "event_count": sum(event_counts.values()) or int(record.get("event_count", 0) or 0),
        "candidate_event_count": candidate_event_count,
        "event_counts": dict(sorted(event_counts.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "phase_counts": dict(sorted(phase_counts.items())),
        "actor_counts": dict(sorted(actor_counts.items())),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "route_counts": dict(sorted(route_counts.items())),
        "mechanics_signal_counts": dict(sorted(mechanics_signal_counts.items())),
        "tag_counts": dict(sorted(tag_counts.items())),
        "project_grounding": project_grounding,
        "owner_resolution": owner_resolution,
        "raw_exists": raw_exists,
        "missing_index_count": len(missing_indexes),
        "missing_indexes_sample": missing_indexes[:12],
        "diagnostics": diagnostics,
        "manual_review_reasons": manual_review_reasons,
        "manual_review_score": review_score,
        "manual_review_priority": review_priority,
        "mechanics_reasons": mechanics_reasons,
        "lanes": lanes,
        "auto_actions": [] if diagnostics else list(policy.get("auto_actions", [])),
    }


def batch_distillation_improvements(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing_index_sessions = [item for item in results if int(item.get("missing_index_count", 0) or 0)]
    raw_missing_sessions = [item for item in results if "raw_missing" in item.get("diagnostics", [])]
    no_candidate_sessions = [
        item
        for item in results
        if item.get("action_status") in {"planned", "distilled"}
        and int(item.get("candidate_event_count", 0) or 0) == 0
        and "low_risk_indexed" not in item.get("lanes", [])
        and int(item.get("event_count", 0) or 0) > 1
    ]
    mechanics_sessions = [item for item in results if "mechanics_candidate" in item.get("lanes", [])]
    improvements: list[dict[str, Any]] = []
    if missing_index_sessions:
        improvements.append(
            {
                "kind": "repair",
                "title": "Repair missing segment indexes before review",
                "session_count": len(missing_index_sessions),
            }
        )
    if raw_missing_sessions:
        improvements.append(
            {
                "kind": "diagnostic",
                "title": "Run raw-unavailable recovery before distillation",
                "session_count": len(raw_missing_sessions),
            }
        )
    if no_candidate_sessions:
        improvements.append(
            {
                "kind": "classifier",
                "title": "Improve event classification for sessions with zero first-wave candidates",
                "session_count": len(no_candidate_sessions),
            }
        )
    if mechanics_sessions:
        improvements.append(
            {
                "kind": "review_queue",
                "title": "Review mechanics candidates for possible tests, skills, hooks, or CLI changes",
                "session_count": len(mechanics_sessions),
            }
        )
    return improvements


def batch_distill_sessions(
    *,
    aoa_root: Path,
    workspace_root: Path | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    apply: bool = False,
    force: bool = False,
    include_distilled: bool = False,
    write_report: bool = False,
    max_events_per_type: int = 30,
) -> dict[str, Any]:
    now = utc_now()
    policy = batch_distillation_policy(aoa_root)
    route_map = route_map_for_distillation(aoa_root)
    records = chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    counts: Counter[str] = Counter()
    lane_counts: Counter[str] = Counter()
    results: list[dict[str, Any]] = []

    for record in records:
        profile = first_wave_session_profile(aoa_root, record, policy=policy, route_map=route_map, workspace_root=workspace_root)
        for lane in profile.get("lanes", []):
            lane_counts[str(lane)] += 1
        if profile.get("diagnostics"):
            action_status = "diagnostic"
        elif profile.get("distillation_status") == "first_pass_distilled" and not force and not include_distilled:
            action_status = "skipped_distilled"
        elif apply:
            try:
                distilled = distill_session_first_pass(
                    aoa_root,
                    str(profile.get("session_label") or profile.get("session_id") or ""),
                    max_events_per_type=max_events_per_type,
                )
                action_status = "distilled"
                profile["distillation_index"] = distilled.get("distillation_index")
                profile["distillation_markdown"] = distilled.get("distillation_markdown")
                profile["distilled_candidate_count"] = distilled.get("candidate_count")
            except Exception as exc:
                action_status = "error"
                profile["error"] = f"{exc.__class__.__name__}: {exc}"
        else:
            action_status = "planned"
        profile["action_status"] = action_status
        counts[action_status] += 1
        results.append(profile)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "first_wave_batch_distillation",
        "generated_at": now,
        "ok": counts.get("error", 0) == 0,
        "aoa_root": str(aoa_root),
        "workspace_root": str(workspace_root) if workspace_root else None,
        "since": since,
        "until": until,
        "limit": limit,
        "apply": apply,
        "force": force,
        "include_distilled": include_distilled,
        "selected_count": len(records),
        "counts": dict(counts),
        "lane_counts": dict(lane_counts),
        "policy": policy,
        "improvement_candidates": batch_distillation_improvements(results),
        "results": results,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__batch-distill__first-wave"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, batch_distillation_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def batch_distillation_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# First-Wave Batch Distillation",
        "",
        "This report is a conveyor map, not reviewed truth.",
        "Automatic action is limited to provisional first-pass distillation.",
        "`manual_review` means a responsible review layer, not that the operator must reread every raw transcript.",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- aoa_root: `{payload.get('aoa_root')}`",
        f"- workspace_root: `{payload.get('workspace_root')}`",
        f"- since: `{payload.get('since')}`",
        f"- until: `{payload.get('until')}`",
        f"- apply: `{payload.get('apply')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- counts: `{json.dumps(payload.get('counts', {}), ensure_ascii=False)}`",
        f"- lane_counts: `{json.dumps(payload.get('lane_counts', {}), ensure_ascii=False)}`",
        "",
        "## Review Layers",
        "",
    ]
    policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
    for layer in policy.get("review_layers", []) if isinstance(policy.get("review_layers"), list) else []:
        lines.append(f"- `{layer}`")
    if policy.get("promotion_limit"):
        lines.append(f"- promotion_limit: `{policy.get('promotion_limit')}`")
    if policy.get("operator_reading_strategy"):
        lines.append(f"- operator_reading_strategy: `{policy.get('operator_reading_strategy')}`")
    lines.extend(
        [
            "",
            "## Project Grounding",
            "",
            "Each session profile keeps the originating `cwd` and nearest project guidance files when available.",
            "Later review agents should use those files before promoting project-specific claims.",
            "Owner resolution is a separate evidence pass: it may recover the real project root from cwd, grounding files, or indexed path mentions when workspace fallback was used.",
            "",
        ]
    )
    lines.extend(
        [
        "## Improvement Candidates",
        "",
        ]
    )
    improvements = payload.get("improvement_candidates", [])
    if improvements:
        for item in improvements if isinstance(improvements, list) else []:
            if isinstance(item, dict):
                lines.append(f"- `{item.get('kind')}` {item.get('title')} sessions=`{item.get('session_count')}`")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Session Queue",
            "",
            "| action | lanes | date | session | owner | segments | candidates | manual reasons | mechanics reasons |",
            "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for result in payload.get("results", []) if isinstance(payload.get("results"), list) else []:
        if not isinstance(result, dict):
            continue
        owner = result.get("owner_resolution") if isinstance(result.get("owner_resolution"), dict) else {}
        lines.append(
            "| {action} | {lanes} | {date} | `{session}` | `{owner}` | {segments} | {candidates} | {manual} | {mechanics} |".format(
                action=str(result.get("action_status") or ""),
                lanes=", ".join(str(item) for item in result.get("lanes", [])),
                date=str(result.get("session_date") or ""),
                session=str(result.get("session_label") or result.get("session_id") or ""),
                owner=str(owner.get("owner_root") or owner.get("status") or ""),
                segments=str(result.get("segment_count") or 0),
                candidates=str(result.get("candidate_event_count") or 0),
                manual=", ".join(str(item) for item in result.get("manual_review_reasons", [])) or "",
                mechanics=", ".join(str(item) for item in result.get("mechanics_reasons", [])) or "",
            )
        )
    lines.append("")
    return "\n".join(lines)


def collect_review_events(
    manifest: dict[str, Any],
    *,
    policy: dict[str, Any],
    route_map: dict[str, list[str]],
    max_per_type: int = 20,
) -> dict[str, Any]:
    manual_types = {str(item) for item in policy.get("manual_review_event_types", []) if str(item)}
    mechanics_types = {str(item) for item in policy.get("mechanics_signal_event_types", []) if str(item)}
    selected_types = manual_types | mechanics_types | FIRST_PASS_CANDIDATE_EVENT_TYPES | FIRST_PASS_SUPPORTING_EVENT_TYPES
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
            routes = [str(route) for route in route_map.get(event_type, [])]
            for route in routes:
                route_counts[route] += 1
            if event_type not in selected_types and not is_first_pass_candidate_event_record(event):
                continue
            if len(selected_by_type[event_type]) >= max_per_type:
                continue
            selected_by_type[event_type].append(
                {
                    "event_id": event.get("event_id"),
                    "type": event_type,
                    "family": event.get("family"),
                    "phase": event.get("phase"),
                    "actor": event.get("actor"),
                    "action": event.get("action"),
                    "outcome": event.get("outcome"),
                    "title": event.get("title"),
                    "importance": event.get("importance"),
                    "tags": event.get("tags", []) if isinstance(event.get("tags"), list) else [],
                    "routes": routes,
                    "md_anchor": event.get("md_anchor"),
                    "raw_ref": event.get("raw_ref"),
                    "source_segment": segment.get("segment_id"),
                }
            )
    return {
        "event_counts": dict(sorted(event_counts.items())),
        "route_counts": dict(sorted(route_counts.items())),
        "source_segments": source_segments,
        "selected_by_type": dict(sorted(selected_by_type.items())),
        "selected_count": sum(len(items) for items in selected_by_type.values()),
    }


def promotion_action_for_event(event_type: str, routes: list[str]) -> str:
    if routes:
        if "skill_amendment" in routes:
            return "skill_or_playbook_review"
        if "automation_seed" in routes or "automation_macro" in routes:
            return "automation_review"
        if "root_cause" in routes:
            return "root_cause_review"
        if "adr" in routes or "principle" in routes:
            return "decision_review"
        return f"route_review:{routes[0]}"
    return {
        "DECISION": "decision_review",
        "PROCESS_LESSON": "skill_or_playbook_review",
        "ERROR": "root_cause_review",
        "SECURITY_OR_SECRET_RISK": "risk_gate_review",
        "OPEN_THREAD": "handoff_review",
        "FINAL_STATE": "closeout_review",
    }.get(event_type, "evidence_review")


def promotion_candidates_from_review_events(review_events: dict[str, Any], *, max_candidates: int = 200) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    by_type = review_events.get("selected_by_type") if isinstance(review_events.get("selected_by_type"), dict) else {}
    for event_type, events in by_type.items():
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict):
                continue
            routes = [str(route) for route in event.get("routes", [])] if isinstance(event.get("routes"), list) else []
            candidate_id = f"{event_type}:{event.get('event_id')}"
            candidates.append(
                {
                    "candidate_id": candidate_id,
                    "status": "needs_review",
                    "promoted": False,
                    "event_type": event_type,
                    "action": promotion_action_for_event(str(event_type), routes),
                    "title": event.get("title"),
                    "routes": routes,
                    "evidence": {
                        "md_anchor": event.get("md_anchor"),
                        "raw_ref": event.get("raw_ref"),
                        "source_segment": event.get("source_segment"),
                    },
                }
            )
            if len(candidates) >= max_candidates:
                return candidates
    return candidates


def manual_review_packet_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Manual Review Packet",
        "",
        "This packet is agent-assisted review material, not reviewed truth.",
        "",
        f"- session: `{payload.get('session_label')}`",
        f"- created_at: `{payload.get('created_at')}`",
        f"- wave: `{payload.get('wave_id')}`",
        f"- priority: `{payload.get('manual_review_priority')}`",
        f"- review_truth_status: `{payload.get('review_truth_status')}`",
        f"- promotion_candidate_count: `{payload.get('promotion_candidate_count')}`",
        "",
        "## Owner Resolution",
        "",
    ]
    owner = payload.get("owner_resolution") if isinstance(payload.get("owner_resolution"), dict) else {}
    lines.extend(
        [
            f"- status: `{owner.get('status')}`",
            f"- owner_root: `{owner.get('owner_root')}`",
            f"- confidence: `{owner.get('confidence')}`",
            "",
            "## Review Reasons",
            "",
        ]
    )
    reasons = payload.get("manual_review_reasons", [])
    if reasons:
        for reason in reasons if isinstance(reasons, list) else []:
            lines.append(f"- `{reason}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Evidence Sample", ""])
    review_events = payload.get("review_events") if isinstance(payload.get("review_events"), dict) else {}
    by_type = review_events.get("selected_by_type") if isinstance(review_events.get("selected_by_type"), dict) else {}
    for event_type, events in by_type.items():
        lines.extend(["", f"### {event_type}", ""])
        for event in events[:12] if isinstance(events, list) else []:
            if isinstance(event, dict):
                lines.append(
                    f"- `{event.get('event_id')}` {event.get('title')} "
                    f"routes={event.get('routes', [])} evidence=`{event.get('md_anchor')}` raw=`{event.get('raw_ref')}`"
                )
    lines.extend(
        [
            "",
            "## Promotion Gate",
            "",
            "All candidates remain `needs_review`. This packet does not promote claims into skills, doctrine, or automation.",
            "",
        ]
    )
    return "\n".join(lines)


def promotion_index_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Promotion Review Index",
        "",
        "Candidates listed here are not promoted. They are queued for reviewed distillation.",
        "",
        f"- session: `{payload.get('session_label')}`",
        f"- created_at: `{payload.get('created_at')}`",
        f"- status: `{payload.get('status')}`",
        f"- candidate_count: `{payload.get('candidate_count')}`",
        f"- promoted_claim_count: `{payload.get('promoted_claim_count')}`",
        "",
        "| status | action | event | evidence |",
        "| --- | --- | --- | --- |",
    ]
    for candidate in payload.get("candidates", []) if isinstance(payload.get("candidates"), list) else []:
        if not isinstance(candidate, dict):
            continue
        evidence = candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else {}
        lines.append(
            "| {status} | {action} | `{event}` | `{evidence}` |".format(
                status=str(candidate.get("status") or ""),
                action=str(candidate.get("action") or ""),
                event=str(candidate.get("candidate_id") or ""),
                evidence=str(evidence.get("md_anchor") or evidence.get("raw_ref") or ""),
            )
        )
    lines.append("")
    return "\n".join(lines)


def wave_number_from_id(wave_id: str | None) -> int | None:
    match = re.search(r"(?:^|[-_])wave[-_]?(\d+)(?:$|[-_])", str(wave_id or "").lower())
    return int(match.group(1)) if match else None


def packet_wave_entry(packet_path: Path) -> dict[str, Any] | None:
    packet = read_json(packet_path, {})
    if not isinstance(packet, dict) or not packet:
        return None
    return {
        "wave_id": str(packet.get("wave_id") or packet_path.name),
        "wave_sequence": int(packet.get("wave_sequence", 0) or 0) or sequence_from_wave_filename(packet_path),
        "packet": str(packet_path),
        "markdown": str(packet_path.with_suffix(".md")),
        "status": str(packet.get("status") or "agent_assisted_review_packet"),
        "review_truth_status": str(packet.get("review_truth_status") or "not_reviewed_truth"),
        "promotion_candidate_count": int(packet.get("promotion_candidate_count", 0) or 0),
        "created_at": packet.get("created_at"),
    }


def sequence_from_wave_filename(path: Path) -> int:
    match = re.match(r"^(\d{3})__", path.name)
    return int(match.group(1)) if match else 0


def manual_review_packet_paths(session_dir: Path) -> list[Path]:
    review_dir = session_dir / "distillation" / "manual-review"
    paths: list[Path] = []
    for directory in (review_dir, review_dir / "waves"):
        if directory.exists():
            paths.extend(sorted(directory.glob("*__manual-review-packet.json")))
    return sorted({path.resolve(): path for path in paths}.values(), key=lambda path: (sequence_from_wave_filename(path), path.name))


def promotion_index_paths(session_dir: Path, manifest: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    promotion = manifest.get("promotion") if isinstance(manifest.get("promotion"), dict) else {}
    waves = promotion.get("waves") if isinstance(promotion.get("waves"), list) else []
    for wave in waves:
        if isinstance(wave, dict) and wave.get("index"):
            paths.append(Path(str(wave["index"])))
    latest = promotion.get("latest_index")
    if latest:
        paths.append(Path(str(latest)))
    legacy = session_dir / "distillation" / "promotion" / "promotion.index.json"
    if legacy.exists():
        paths.append(legacy)
    wave_dir = session_dir / "distillation" / "promotion" / "waves"
    if wave_dir.exists():
        paths.extend(sorted(wave_dir.glob("*__promotion.index.json")))
    unique: dict[str, Path] = {}
    for path in paths:
        unique[str(path)] = path
    return sorted(unique.values(), key=lambda path: (sequence_from_wave_filename(path), path.name))


def next_session_wave_sequence(session_dir: Path) -> int:
    sequences = [sequence_from_wave_filename(path) for path in manual_review_packet_paths(session_dir)]
    return max(sequences, default=0) + 1


def next_manual_review_wave_id(aoa_root: Path) -> str:
    max_wave = 0
    for record in registry_sessions(aoa_root):
        session_dir = session_dir_from_record(record)
        for packet_path in manual_review_packet_paths(session_dir):
            entry = packet_wave_entry(packet_path)
            wave_no = wave_number_from_id(entry.get("wave_id") if entry else packet_path.name)
            if wave_no is not None:
                max_wave = max(max_wave, wave_no)
    return f"manual-review-wave{max_wave + 1}"


def legacy_wave_entries_from_manifest(session_dir: Path, manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manual = manifest.get("manual_review") if isinstance(manifest.get("manual_review"), dict) else {}
    promotion = manifest.get("promotion") if isinstance(manifest.get("promotion"), dict) else {}
    manual_waves = [item for item in manual.get("waves", []) if isinstance(item, dict)] if isinstance(manual.get("waves"), list) else []
    promotion_waves = [item for item in promotion.get("waves", []) if isinstance(item, dict)] if isinstance(promotion.get("waves"), list) else []

    if not manual_waves:
        latest_packet = manual.get("latest_packet")
        if latest_packet and Path(str(latest_packet)).exists():
            entry = packet_wave_entry(Path(str(latest_packet)))
            if entry:
                manual_waves.append(entry)
    if not promotion_waves:
        latest_index = promotion.get("latest_index")
        if latest_index and Path(str(latest_index)).exists():
            index = read_json(Path(str(latest_index)), {})
            if isinstance(index, dict) and index:
                promotion_waves.append(
                    {
                        "wave_id": str(index.get("wave_id") or "manual-review-wave1"),
                        "wave_sequence": sequence_from_wave_filename(Path(str(latest_index))) or 1,
                        "index": str(latest_index),
                        "markdown": str(Path(str(latest_index)).with_suffix(".md")),
                        "status": str(index.get("status") or "promotion_candidates_unreviewed"),
                        "candidate_count": int(index.get("candidate_count", 0) or 0),
                        "promoted_claim_count": int(index.get("promoted_claim_count", 0) or 0),
                        "created_at": index.get("created_at"),
                    }
                )
    return manual_waves, promotion_waves


def review_index_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Review Wave Index",
        "",
        "This index keeps review waves open and append-only. It is not reviewed truth.",
        "",
        f"- session: `{payload.get('session_label')}`",
        f"- status: `{payload.get('status')}`",
        f"- manual_wave_count: `{payload.get('manual_wave_count')}`",
        f"- promotion_wave_count: `{payload.get('promotion_wave_count')}`",
        f"- promoted_claim_count: `{payload.get('promoted_claim_count')}`",
        "",
        "## Manual Review Waves",
        "",
        "| wave | status | packet | candidates |",
        "| --- | --- | --- | ---: |",
    ]
    for wave in payload.get("manual_review_waves", []) if isinstance(payload.get("manual_review_waves"), list) else []:
        if isinstance(wave, dict):
            lines.append(
                f"| `{wave.get('wave_id')}` | `{wave.get('status')}` | `{wave.get('packet')}` | {wave.get('promotion_candidate_count', 0)} |"
            )
    lines.extend(["", "## Promotion Waves", "", "| wave | status | index | candidates | promoted |", "| --- | --- | --- | ---: | ---: |"])
    for wave in payload.get("promotion_waves", []) if isinstance(payload.get("promotion_waves"), list) else []:
        if isinstance(wave, dict):
            lines.append(
                f"| `{wave.get('wave_id')}` | `{wave.get('status')}` | `{wave.get('index')}` | {wave.get('candidate_count', 0)} | {wave.get('promoted_claim_count', 0)} |"
            )
    lines.append("")
    return "\n".join(lines)


def write_review_wave_index(session_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    manual = manifest.get("manual_review") if isinstance(manifest.get("manual_review"), dict) else {}
    promotion = manifest.get("promotion") if isinstance(manifest.get("promotion"), dict) else {}
    manual_waves = [item for item in manual.get("waves", []) if isinstance(item, dict)] if isinstance(manual.get("waves"), list) else []
    promotion_waves = [item for item in promotion.get("waves", []) if isinstance(item, dict)] if isinstance(promotion.get("waves"), list) else []
    promoted = sum(int(item.get("promoted_claim_count", 0) or 0) for item in promotion_waves if isinstance(item, dict))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "review_wave_index",
        "session_id": manifest.get("session_id"),
        "session_label": manifest.get("session_label"),
        "updated_at": utc_now(),
        "status": "open_for_future_passes",
        "review_truth_status": "not_reviewed_truth",
        "manual_wave_count": len(manual_waves),
        "promotion_wave_count": len(promotion_waves),
        "promoted_claim_count": promoted,
        "manual_review_waves": manual_waves,
        "promotion_waves": promotion_waves,
    }
    index_json = session_dir / "distillation" / "review.index.json"
    index_md = session_dir / "distillation" / "review.index.md"
    write_json(index_json, payload)
    write_markdown(index_md, review_index_markdown(payload))
    return {"latest_index": str(index_json), "latest_markdown": str(index_md), "status": payload["status"]}


def write_manual_review_packet(
    aoa_root: Path,
    profile: dict[str, Any],
    *,
    policy: dict[str, Any],
    route_map: dict[str, list[str]],
    wave_id: str,
    max_events_per_type: int = 20,
) -> dict[str, Any]:
    now = utc_now()
    session_dir = Path(str(profile.get("session_dir") or ""))
    manifest = read_json(session_dir / "session.manifest.json", {})
    if not isinstance(manifest, dict) or not manifest:
        return {**profile, "status": "diagnostic", "diagnostics": ["missing_session_manifest"]}
    review_events = collect_review_events(manifest, policy=policy, route_map=route_map, max_per_type=max_events_per_type)
    candidates = promotion_candidates_from_review_events(review_events)
    review_dir = session_dir / "distillation" / "manual-review"
    promotion_dir = session_dir / "distillation" / "promotion"
    review_waves_dir = review_dir / "waves"
    promotion_waves_dir = promotion_dir / "waves"
    review_waves_dir.mkdir(parents=True, exist_ok=True)
    promotion_waves_dir.mkdir(parents=True, exist_ok=True)
    wave_sequence = next_session_wave_sequence(session_dir)
    wave_slug = safe_slug(wave_id)

    packet = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "manual_review_packet",
        "session_id": manifest.get("session_id"),
        "session_label": manifest.get("session_label"),
        "created_at": now,
        "wave_id": wave_id,
        "wave_sequence": wave_sequence,
        "status": "agent_assisted_review_packet",
        "open_status": "open_for_future_passes",
        "review_truth_status": "not_reviewed_truth",
        "operator_review_required": True,
        "manual_review_priority": profile.get("manual_review_priority"),
        "manual_review_score": profile.get("manual_review_score"),
        "manual_review_reasons": profile.get("manual_review_reasons", []),
        "project_grounding": profile.get("project_grounding"),
        "owner_resolution": profile.get("owner_resolution"),
        "review_events": review_events,
        "promotion_candidate_count": len(candidates),
    }
    packet_json = review_waves_dir / f"{wave_sequence:03d}__{wave_slug}__manual-review-packet.json"
    packet_md = review_waves_dir / f"{wave_sequence:03d}__{wave_slug}__manual-review-packet.md"
    write_json(packet_json, packet)
    write_markdown(packet_md, manual_review_packet_markdown(packet))

    for candidate in candidates:
        candidate["wave_id"] = wave_id
        candidate["wave_sequence"] = wave_sequence
        candidate["review_status"] = "open"
        candidate["closed"] = False

    promotion_index = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "promotion_review_index",
        "session_id": manifest.get("session_id"),
        "session_label": manifest.get("session_label"),
        "created_at": now,
        "wave_id": wave_id,
        "wave_sequence": wave_sequence,
        "status": "promotion_candidates_unreviewed",
        "open_status": "open_for_future_passes",
        "review_truth_status": "not_reviewed_truth",
        "candidate_count": len(candidates),
        "promoted_claim_count": 0,
        "candidates": candidates,
        "source_manual_review_packet": str(packet_json),
    }
    promotion_json = promotion_waves_dir / f"{wave_sequence:03d}__{wave_slug}__promotion.index.json"
    promotion_md = promotion_waves_dir / f"{wave_sequence:03d}__{wave_slug}__promotion.index.md"
    write_json(promotion_json, promotion_index)
    write_markdown(promotion_md, promotion_index_markdown(promotion_index))

    existing_manual_waves, existing_promotion_waves = legacy_wave_entries_from_manifest(session_dir, manifest)
    manual_entry = {
        "wave_id": wave_id,
        "wave_sequence": wave_sequence,
        "packet": str(packet_json),
        "markdown": str(packet_md),
        "status": "agent_assisted_review_packet",
        "review_truth_status": "not_reviewed_truth",
        "promotion_candidate_count": len(candidates),
        "created_at": now,
    }
    promotion_entry = {
        "wave_id": wave_id,
        "wave_sequence": wave_sequence,
        "index": str(promotion_json),
        "markdown": str(promotion_md),
        "status": "promotion_candidates_unreviewed",
        "candidate_count": len(candidates),
        "promoted_claim_count": 0,
        "created_at": now,
    }
    manual_waves = [item for item in existing_manual_waves if str(item.get("packet")) != str(packet_json)]
    promotion_waves = [item for item in existing_promotion_waves if str(item.get("index")) != str(promotion_json)]
    manual_waves.append(manual_entry)
    promotion_waves.append(promotion_entry)

    manifest["review_status"] = "manual_review_open"
    manifest["manual_review"] = {
        "latest_packet": str(packet_json),
        "latest_markdown": str(packet_md),
        "wave_id": wave_id,
        "latest_wave_id": wave_id,
        "wave_count": len(manual_waves),
        "review_truth_status": "not_reviewed_truth",
        "open_status": "open_for_future_passes",
        "promotion_candidate_count": len(candidates),
        "waves": manual_waves,
    }
    manifest["promotion"] = {
        "latest_index": str(promotion_json),
        "latest_markdown": str(promotion_md),
        "status": "promotion_candidates_unreviewed",
        "open_status": "open_for_future_passes",
        "promoted_claim_count": 0,
        "candidate_count": len(candidates),
        "latest_wave_id": wave_id,
        "wave_count": len(promotion_waves),
        "waves": promotion_waves,
    }
    manifest["review_index"] = write_review_wave_index(session_dir, manifest)
    manifest["updated_at"] = now
    update_session_status_files(session_dir, manifest)
    return {
        "session_id": manifest.get("session_id"),
        "session_label": manifest.get("session_label"),
        "session_dir": str(session_dir),
        "status": "packet_written",
        "wave_id": wave_id,
        "wave_sequence": wave_sequence,
        "review_open_status": "open_for_future_passes",
        "manual_review_priority": profile.get("manual_review_priority"),
        "manual_review_score": profile.get("manual_review_score"),
        "manual_review_reasons": profile.get("manual_review_reasons", []),
        "owner_resolution": profile.get("owner_resolution"),
        "manual_review_packet": str(packet_json),
        "manual_review_markdown": str(packet_md),
        "promotion_index": str(promotion_json),
        "promotion_markdown": str(promotion_md),
        "promotion_candidate_count": len(candidates),
        "manual_review_wave_count": len(manual_waves),
        "promotion_wave_count": len(promotion_waves),
    }


def manual_review_priority_rank(value: str | None) -> int:
    return {"none": 0, "sample": 1, "standard": 2, "deep": 3}.get(str(value or "none"), 0)


def manual_review_wave(
    *,
    aoa_root: Path,
    workspace_root: Path | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    priority: str = "deep",
    apply: bool = False,
    write_report: bool = False,
    max_events_per_type: int = 20,
    wave_id: str | None = None,
) -> dict[str, Any]:
    now = utc_now()
    wave_id = wave_id or next_manual_review_wave_id(aoa_root)
    policy = batch_distillation_policy(aoa_root)
    route_map = route_map_for_distillation(aoa_root)
    records = chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    selected: list[dict[str, Any]] = []
    min_rank = manual_review_priority_rank(priority)
    for record in records:
        profile = first_wave_session_profile(aoa_root, record, policy=policy, route_map=route_map, workspace_root=workspace_root)
        if "manual_review" not in profile.get("lanes", []):
            continue
        if manual_review_priority_rank(str(profile.get("manual_review_priority") or "none")) < min_rank:
            continue
        selected.append(profile)

    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for profile in selected:
        if profile.get("diagnostics"):
            result = {
                "session_id": profile.get("session_id"),
                "session_label": profile.get("session_label"),
                "session_dir": profile.get("session_dir"),
                "status": "diagnostic",
                "diagnostics": profile.get("diagnostics", []),
            }
        elif apply:
            result = write_manual_review_packet(
                aoa_root,
                profile,
                policy=policy,
                route_map=route_map,
                wave_id=wave_id,
                max_events_per_type=max_events_per_type,
            )
        else:
            result = {
                "session_id": profile.get("session_id"),
                "session_label": profile.get("session_label"),
                "session_dir": profile.get("session_dir"),
                "status": "planned",
                "wave_id": wave_id,
                "review_open_status": "open_for_future_passes",
                "manual_review_priority": profile.get("manual_review_priority"),
                "manual_review_score": profile.get("manual_review_score"),
                "manual_review_reasons": profile.get("manual_review_reasons", []),
                "owner_resolution": profile.get("owner_resolution"),
            }
        counts[str(result.get("status") or "unknown")] += 1
        results.append(result)

    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "manual_review_wave",
        "generated_at": now,
        "ok": counts.get("diagnostic", 0) == 0,
        "aoa_root": str(aoa_root),
        "workspace_root": str(workspace_root) if workspace_root else None,
        "since": since,
        "until": until,
        "limit": limit,
        "priority": priority,
        "wave_id": wave_id,
        "apply": apply,
        "selected_count": len(selected),
        "counts": dict(counts),
        "results": results,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__{safe_slug(wave_id)}"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, manual_review_wave_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def manual_review_wave_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Manual Review Wave",
        "",
        "This is a review packet queue. It does not promote reviewed truth.",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- wave_id: `{payload.get('wave_id')}`",
        f"- priority: `{payload.get('priority')}`",
        f"- apply: `{payload.get('apply')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- counts: `{json.dumps(payload.get('counts', {}), ensure_ascii=False)}`",
        "",
        "| status | session | priority | packet | promotion |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in payload.get("results", []) if isinstance(payload.get("results"), list) else []:
        if not isinstance(result, dict):
            continue
        lines.append(
            "| {status} | `{session}` | `{priority}` | `{packet}` | `{promotion}` |".format(
                status=str(result.get("status") or ""),
                session=str(result.get("session_label") or result.get("session_id") or ""),
                priority=str(result.get("manual_review_priority") or ""),
                packet=str(result.get("manual_review_packet") or ""),
                promotion=str(result.get("promotion_index") or ""),
            )
        )
    lines.append("")
    return "\n".join(lines)


def build_promotion_review_layer(
    *,
    aoa_root: Path,
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    records = chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    results: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    candidate_total = 0
    raw_candidate_total = 0
    promoted_total = 0
    for record in records:
        session_dir = session_dir_from_record(record)
        manifest = read_json(session_dir / "session.manifest.json", {})
        if not isinstance(manifest, dict):
            continue
        index_paths = [path for path in promotion_index_paths(session_dir, manifest) if path.exists()]
        if not index_paths:
            continue
        candidate_by_id: dict[str, dict[str, Any]] = {}
        promoted_count = 0
        statuses: Counter[str] = Counter()
        for index_path in index_paths:
            index = read_json(index_path, {})
            if not isinstance(index, dict) or not index:
                status_counts["missing_index"] += 1
                continue
            status = str(index.get("status") or "unknown")
            statuses[status] += 1
            status_counts[status] += 1
            promoted_count += int(index.get("promoted_claim_count", 0) or 0)
            for candidate in index.get("candidates", []) if isinstance(index.get("candidates"), list) else []:
                if not isinstance(candidate, dict):
                    continue
                candidate_id = str(candidate.get("candidate_id") or "")
                if not candidate_id:
                    continue
                existing = candidate_by_id.setdefault(
                    candidate_id,
                    {
                        "candidate_id": candidate_id,
                        "status": candidate.get("status"),
                        "event_type": candidate.get("event_type"),
                        "action": candidate.get("action"),
                        "title": candidate.get("title"),
                        "seen_in_waves": [],
                        "latest_wave_id": None,
                        "latest_index": str(index_path),
                    },
                )
                wave_id = str(index.get("wave_id") or candidate.get("wave_id") or "")
                if wave_id and wave_id not in existing["seen_in_waves"]:
                    existing["seen_in_waves"].append(wave_id)
                existing["latest_wave_id"] = wave_id or existing.get("latest_wave_id")
                existing["latest_index"] = str(index_path)
        candidate_count = len(candidate_by_id)
        raw_candidate_count = sum(len(item.get("seen_in_waves", [])) or 1 for item in candidate_by_id.values())
        candidate_total += candidate_count
        raw_candidate_total += raw_candidate_count
        promoted_total += promoted_count
        results.append(
            {
                "session_id": manifest.get("session_id"),
                "session_label": manifest.get("session_label"),
                "session_dir": str(session_dir),
                "promotion_index": str(index_paths[-1]),
                "promotion_indexes": [str(path) for path in index_paths],
                "status": "promotion_candidates_open",
                "status_counts": dict(statuses),
                "wave_count": len(index_paths),
                "candidate_count": candidate_count,
                "raw_candidate_count": raw_candidate_count,
                "promoted_claim_count": promoted_count,
            }
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "promotion_review_layer",
        "generated_at": now,
        "ok": True,
        "aoa_root": str(aoa_root),
        "since": since,
        "until": until,
        "limit": limit,
        "selected_count": len(results),
        "candidate_count": candidate_total,
        "raw_candidate_count": raw_candidate_total,
        "promoted_claim_count": promoted_total,
        "status_counts": dict(status_counts),
        "results": results,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__promotion-review-layer"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, promotion_review_layer_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def promotion_review_layer_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Promotion Review Layer",
        "",
        "This aggregates unreviewed promotion candidates. It does not promote them.",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- candidate_count: `{payload.get('candidate_count')}`",
        f"- raw_candidate_count: `{payload.get('raw_candidate_count')}`",
        f"- promoted_claim_count: `{payload.get('promoted_claim_count')}`",
        f"- status_counts: `{json.dumps(payload.get('status_counts', {}), ensure_ascii=False)}`",
        "",
        "| status | session | waves | candidates | raw candidates | promoted | index |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in payload.get("results", []) if isinstance(payload.get("results"), list) else []:
        if not isinstance(result, dict):
            continue
        lines.append(
            "| {status} | `{session}` | {waves} | {candidates} | {raw_candidates} | {promoted} | `{index}` |".format(
                status=str(result.get("status") or ""),
                session=str(result.get("session_label") or result.get("session_id") or ""),
                waves=str(result.get("wave_count") or 0),
                candidates=str(result.get("candidate_count") or 0),
                raw_candidates=str(result.get("raw_candidate_count") or 0),
                promoted=str(result.get("promoted_claim_count") or 0),
                index=str(result.get("promotion_index") or ""),
            )
        )
    lines.append("")
    return "\n".join(lines)


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
    compact_hook_light = event_name in {"PreCompact", "PostCompact"} and os.environ.get("AOA_SESSION_MEMORY_FULL_COMPACT_SYNC") != "1"
    stop_hook_light = event_name == "Stop" and stop_hook_should_defer_indexing(transcript_path)
    if compact_hook_light or stop_hook_light:
        try:
            if transcript_path is not None and transcript_path.exists() and os.access(transcript_path, os.R_OK):
                mirrored = mirror_transcript_without_indexing(
                    aoa_root=root,
                    event=event,
                    transcript_path=transcript_path,
                    hook_event_name=event_name,
                    now=now,
                )
                actions.append("raw_mirrored")
                actions.append("indexing_deferred")
                return {
                    "schema_version": SCHEMA_VERSION,
                    "ok": True,
                    "hook_event_name": event_name,
                    "timestamp": now,
                    "session_id": mirrored["session_id"],
                    "session_dir": mirrored["session_dir"],
                    "display_name": mirrored.get("display_name"),
                    "navigation_path": mirrored.get("navigation_path"),
                    "actions": actions,
                    "archive": mirrored,
                    "errors": errors,
                }
        except Exception as exc:
            errors.append(f"{exc.__class__.__name__}: {exc}")
            actions.append("light_mirror_failed")
        else:
            # No readable transcript: fall through to the normal diagnostic path.
            pass
        if errors:
            actions.append(f"{event_name.lower()}_hook_light_recorded")
            actions.append("indexing_deferred")
            return {
                "schema_version": SCHEMA_VERSION,
                "ok": False,
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


def command_name_session(args: argparse.Namespace) -> int:
    root = aoa_root_for(Path(args.workspace_root) if args.workspace_root else None, Path(args.aoa_root) if args.aoa_root else None)
    payload = set_session_semantic_name(
        aoa_root=root,
        target=args.session,
        name=args.name,
        kind=args.kind,
        scope=args.scope,
        evidence_refs=args.evidence or [],
        from_line=args.from_line,
        to_line=args.to_line,
        coverage_note=args.coverage_note,
        source=args.source,
        note=args.note,
        apply=args.apply,
        replace=args.replace,
        verify_raw_hash=not args.skip_raw_hash_check,
        write_report=args.write_report,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_phase_discovery(args: argparse.Namespace) -> int:
    root = aoa_root_for(Path(args.workspace_root) if args.workspace_root else None, Path(args.aoa_root) if args.aoa_root else None)
    payload = discover_session_phases(
        root,
        args.session,
        write=args.write,
        write_report=args.write_report,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_review_phase_name(args: argparse.Namespace) -> int:
    root = aoa_root_for(Path(args.workspace_root) if args.workspace_root else None, Path(args.aoa_root) if args.aoa_root else None)
    payload = review_phase_name_candidate(
        root,
        args.session,
        args.segment,
        reviewed_name=args.reviewed_name,
        use_candidate=args.use_candidate,
        apply=args.apply,
        replace=args.replace,
        refresh=args.refresh,
        write_report=args.write_report,
        verify_raw_hash=not args.skip_raw_hash_check,
        coverage_note=args.coverage_note,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


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


def import_print_payload(payload: dict[str, Any], *, full: bool = False, sample_results: int = 20) -> dict[str, Any]:
    if full:
        return payload
    results = payload.get("results", [])
    result_count = len(results) if isinstance(results, list) else 0
    sample: list[Any] = []
    if isinstance(results, list) and results:
        if result_count <= sample_results:
            sample = results
        else:
            head_count = max(1, sample_results // 2)
            tail_count = max(1, sample_results - head_count)
            sample = results[:head_count] + results[-tail_count:]
    compact = {key: value for key, value in payload.items() if key != "results"}
    compact["result_count"] = result_count
    compact["results_sample"] = sample
    compact["results_omitted"] = max(0, result_count - len(sample))
    compact["print"] = {
        "full": False,
        "note": "results are bounded on stdout; pass --full for complete JSON or read the written report",
    }
    return compact


def reindex_print_payload(payload: dict[str, Any], *, full: bool = False, sample_results: int = 20) -> dict[str, Any]:
    if full:
        return payload
    results = payload.get("results", [])
    result_count = len(results) if isinstance(results, list) else 0
    sample: list[Any] = []
    if isinstance(results, list) and results:
        if result_count <= sample_results:
            sample = results
        else:
            head_count = max(1, sample_results // 2)
            tail_count = max(1, sample_results - head_count)
            sample = results[:head_count] + results[-tail_count:]
    compact = {key: value for key, value in payload.items() if key != "results"}
    compact["result_count"] = result_count
    compact["results_sample"] = sample
    compact["results_omitted"] = max(0, result_count - len(sample))
    compact["print"] = {
        "full": False,
        "note": "results are bounded on stdout; pass --full or read the written report for the complete reindex queue",
    }
    return compact


def compact_batch_distill_result(result: dict[str, Any]) -> dict[str, Any]:
    grounding = result.get("project_grounding") if isinstance(result.get("project_grounding"), dict) else {}
    owner = result.get("owner_resolution") if isinstance(result.get("owner_resolution"), dict) else {}
    family_counts = result.get("family_counts") if isinstance(result.get("family_counts"), dict) else {}
    outcome_counts = result.get("outcome_counts") if isinstance(result.get("outcome_counts"), dict) else {}
    return {
        "session_label": result.get("session_label"),
        "action_status": result.get("action_status"),
        "lanes": result.get("lanes", []),
        "segment_count": result.get("segment_count"),
        "candidate_event_count": result.get("candidate_event_count"),
        "family_counts_sample": dict(list(family_counts.items())[:8]),
        "outcome_counts_sample": dict(list(outcome_counts.items())[:8]),
        "project_grounding": {
            "cwd": grounding.get("cwd"),
            "status": grounding.get("status"),
            "files": grounding.get("files", [])[:3] if isinstance(grounding.get("files"), list) else [],
        },
        "owner_resolution": {
            "status": owner.get("status"),
            "owner_root": owner.get("owner_root"),
            "confidence": owner.get("confidence"),
            "score": owner.get("score"),
        },
        "manual_review_reasons": result.get("manual_review_reasons", [])[:8],
        "mechanics_reasons": result.get("mechanics_reasons", [])[:8],
        "diagnostics": result.get("diagnostics", [])[:8],
    }


def batch_distill_print_payload(payload: dict[str, Any], *, full: bool = False, sample_results: int = 20) -> dict[str, Any]:
    if full:
        return payload
    results = payload.get("results", [])
    result_count = len(results) if isinstance(results, list) else 0
    sample: list[Any] = []
    if isinstance(results, list) and results:
        if result_count <= sample_results:
            sample = results
        else:
            head_count = max(1, sample_results // 2)
            tail_count = max(1, sample_results - head_count)
            sample = results[:head_count] + results[-tail_count:]
    sample = [compact_batch_distill_result(item) for item in sample if isinstance(item, dict)]
    compact = {key: value for key, value in payload.items() if key != "results"}
    compact["result_count"] = result_count
    compact["results_sample"] = sample
    compact["results_omitted"] = max(0, result_count - len(sample))
    compact["print"] = {
        "full": False,
        "note": "results are bounded on stdout; pass --full or read the written report for the complete queue",
    }
    return compact


def compact_title_repair_result(result: dict[str, Any]) -> dict[str, Any]:
    current = result.get("current") if isinstance(result.get("current"), dict) else {}
    proposed = result.get("proposed") if isinstance(result.get("proposed"), dict) else {}
    return {
        "session_label": result.get("session_label"),
        "status": result.get("status"),
        "reasons": result.get("reasons", [])[:8],
        "current": {
            "title": current.get("title"),
            "title_source": current.get("title_source"),
            "label": current.get("label"),
        },
        "proposed": {
            "title": proposed.get("title"),
            "title_source": proposed.get("title_source"),
            "label": proposed.get("label"),
        },
        "diagnostics": result.get("diagnostics", [])[:8],
    }


def title_repair_print_payload(payload: dict[str, Any], *, full: bool = False, sample_results: int = 20) -> dict[str, Any]:
    if full:
        return payload
    results = payload.get("results", [])
    result_count = len(results) if isinstance(results, list) else 0
    sample: list[Any] = []
    if isinstance(results, list) and results:
        if result_count <= sample_results:
            sample = results
        else:
            head_count = max(1, sample_results // 2)
            tail_count = max(1, sample_results - head_count)
            sample = results[:head_count] + results[-tail_count:]
    compact = {key: value for key, value in payload.items() if key != "results"}
    compact["result_count"] = result_count
    compact["results_sample"] = [compact_title_repair_result(item) for item in sample if isinstance(item, dict)]
    compact["results_omitted"] = max(0, result_count - len(sample))
    compact["print"] = {
        "full": False,
        "note": "results are bounded on stdout; pass --full or read the written report for the complete title repair queue",
    }
    return compact


def compact_naming_readiness_result(result: dict[str, Any]) -> dict[str, Any]:
    readiness = result.get("naming_readiness") if isinstance(result.get("naming_readiness"), dict) else {}
    evidence = readiness.get("evidence") if isinstance(readiness.get("evidence"), dict) else {}
    return {
        "session_label": result.get("session_label"),
        "session_title": result.get("session_title"),
        "event_count": result.get("event_count"),
        "segment_count": result.get("segment_count"),
        "status": readiness.get("status"),
        "route": readiness.get("route"),
        "priority": readiness.get("priority"),
        "reasons": readiness.get("reasons", [])[:8] if isinstance(readiness.get("reasons"), list) else [],
        "blockers": readiness.get("blockers", [])[:8] if isinstance(readiness.get("blockers"), list) else [],
        "warnings": readiness.get("warnings", [])[:8] if isinstance(readiness.get("warnings"), list) else [],
        "active_session_name": evidence.get("active_session_name"),
    }


def naming_readiness_print_payload(payload: dict[str, Any], *, full: bool = False, sample_results: int = 20) -> dict[str, Any]:
    return bounded_results_print_payload(
        payload,
        full=full,
        sample_results=sample_results,
        compact_func=compact_naming_readiness_result,
        note="results are bounded on stdout; pass --full or read the written report for the complete naming-readiness queue",
    )


def compact_manual_review_result(result: dict[str, Any]) -> dict[str, Any]:
    owner = result.get("owner_resolution") if isinstance(result.get("owner_resolution"), dict) else {}
    return {
        "session_label": result.get("session_label"),
        "status": result.get("status"),
        "wave_id": result.get("wave_id"),
        "wave_sequence": result.get("wave_sequence"),
        "review_open_status": result.get("review_open_status"),
        "manual_review_priority": result.get("manual_review_priority"),
        "manual_review_score": result.get("manual_review_score"),
        "manual_review_reasons": result.get("manual_review_reasons", [])[:8],
        "owner_resolution": {
            "status": owner.get("status"),
            "owner_root": owner.get("owner_root"),
            "confidence": owner.get("confidence"),
        },
        "manual_review_packet": result.get("manual_review_packet"),
        "promotion_index": result.get("promotion_index"),
        "promotion_candidate_count": result.get("promotion_candidate_count"),
        "manual_review_wave_count": result.get("manual_review_wave_count"),
        "promotion_wave_count": result.get("promotion_wave_count"),
        "diagnostics": result.get("diagnostics", [])[:8],
    }


def bounded_results_print_payload(payload: dict[str, Any], *, full: bool = False, sample_results: int = 20, compact_func=None, note: str = "") -> dict[str, Any]:
    if full:
        return payload
    results = payload.get("results", [])
    result_count = len(results) if isinstance(results, list) else 0
    sample: list[Any] = []
    if isinstance(results, list) and results:
        if result_count <= sample_results:
            sample = results
        else:
            head_count = max(1, sample_results // 2)
            tail_count = max(1, sample_results - head_count)
            sample = results[:head_count] + results[-tail_count:]
    compact = {key: value for key, value in payload.items() if key != "results"}
    renderer = compact_func or (lambda item: item)
    compact["result_count"] = result_count
    compact["results_sample"] = [renderer(item) for item in sample if isinstance(item, dict)]
    compact["results_omitted"] = max(0, result_count - len(sample))
    compact["print"] = {"full": False, "note": note or "results are bounded on stdout; pass --full or read the written report for complete results"}
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


def command_import_codex_sessions(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    since = since_date_from_args(args.since, args.since_days)
    source_root = Path(args.source_root).expanduser() if args.source_root else Path.home() / ".codex" / "sessions"
    payload = import_codex_sessions(
        aoa_root=root,
        source_root=source_root,
        since=since,
        until=args.until,
        dry_run=args.dry_run,
        force=args.force,
        limit=args.limit,
        write_report=args.write_report,
    )
    print(json.dumps(import_print_payload(payload, full=args.full), indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_reindex_sessions(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    since = since_date_from_args(args.since, args.since_days if args.since_days is not None else None)
    payload = reindex_sessions(
        aoa_root=root,
        target=args.session,
        since=since,
        until=args.until,
        limit=args.limit,
        dry_run=args.dry_run,
        write_report=args.write_report,
    )
    print(json.dumps(reindex_print_payload(payload, full=args.full), indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_batch_distill(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    workspace_root = workspace_root_for(explicit_workspace, root)
    since = since_date_from_args(args.since, args.since_days if args.since_days is not None else None)
    payload = batch_distill_sessions(
        aoa_root=root,
        workspace_root=workspace_root,
        since=since,
        until=args.until,
        limit=args.limit,
        apply=args.apply,
        force=args.force,
        include_distilled=args.include_distilled,
        write_report=args.write_report,
        max_events_per_type=args.max_events_per_type,
    )
    print(json.dumps(batch_distill_print_payload(payload, full=args.full), indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_repair_session_titles(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    since = since_date_from_args(args.since, args.since_days if args.since_days is not None else None)
    payload = repair_session_titles(
        aoa_root=root,
        target=args.session,
        since=since,
        until=args.until,
        limit=args.limit,
        apply=args.apply,
        write_report=args.write_report,
    )
    print(json.dumps(title_repair_print_payload(payload, full=args.full), indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_naming_readiness(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    since = since_date_from_args(args.since, args.since_days if args.since_days is not None else None)
    payload = build_naming_readiness_report(
        root,
        target=args.session,
        since=since,
        until=args.until,
        limit=args.limit,
        refresh_indexes=args.refresh_indexes,
        write_report=args.write_report,
    )
    print(json.dumps(naming_readiness_print_payload(payload, full=args.full), indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_manual_review(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    workspace_root = workspace_root_for(explicit_workspace, root)
    since = since_date_from_args(args.since, args.since_days if args.since_days is not None else None)
    payload = manual_review_wave(
        aoa_root=root,
        workspace_root=workspace_root,
        since=since,
        until=args.until,
        limit=args.limit,
        priority=args.priority,
        apply=args.apply,
        write_report=args.write_report,
        max_events_per_type=args.max_events_per_type,
        wave_id=args.wave_id,
    )
    print(
        json.dumps(
            bounded_results_print_payload(
                payload,
                full=args.full,
                compact_func=compact_manual_review_result,
                note="results are bounded on stdout; pass --full or read the written report for the complete manual review queue",
            ),
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if payload.get("ok") else 1


def command_promotion_review(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    since = since_date_from_args(args.since, args.since_days if args.since_days is not None else None)
    payload = build_promotion_review_layer(
        aoa_root=root,
        since=since,
        until=args.until,
        limit=args.limit,
        write_report=args.write_report,
    )
    print(
        json.dumps(
            bounded_results_print_payload(
                payload,
                full=args.full,
                note="results are bounded on stdout; pass --full or read the written report for the complete promotion layer",
            ),
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if payload.get("ok") else 1


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
            old_stop_sync_max = os.environ.get("AOA_SESSION_MEMORY_STOP_SYNC_MAX_BYTES")
            os.environ["AOA_SESSION_MEMORY_STOP_SYNC_MAX_BYTES"] = "0"
            try:
                for hook_name in ("PreCompact", "PostCompact", "Stop"):
                    receipts[hook_name] = handle_hook_event(
                        hook_name,
                        {**event, "hook_event_name": hook_name},
                        workspace_root=temp_workspace,
                        aoa_root=temp_aoa,
                    )
                    add_check(f"{hook_name.lower()}_receipt_ok", receipts[hook_name].get("ok") is True, receipts[hook_name].get("errors"))
            finally:
                if old_stop_sync_max is None:
                    os.environ.pop("AOA_SESSION_MEMORY_STOP_SYNC_MAX_BYTES", None)
                else:
                    os.environ["AOA_SESSION_MEMORY_STOP_SYNC_MAX_BYTES"] = old_stop_sync_max

            add_check(
                "lifecycle_hooks_defer_indexing",
                all("indexing_deferred" in receipts[name].get("actions", []) for name in ("PreCompact", "PostCompact", "Stop")),
                {name: receipts[name].get("actions", []) for name in ("PreCompact", "PostCompact", "Stop")},
            )
            synced = sync_session_from_transcript(
                aoa_root=temp_aoa,
                event={**event, "hook_event_name": "ManualSync"},
                transcript_path=transcript_path,
                hook_event_name="ManualSync",
            )
            add_check("manual_full_sync_after_light_hooks", synced.get("segment_count") == 2, synced)

            session_dir = Path(str(synced.get("session_dir") or receipts["Stop"].get("session_dir") or ""))
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
    sessions_index_path = aoa_root / SESSION_ROOT / SESSIONS_INDEX_JSON
    sessions_index_markdown_path = aoa_root / SESSION_ROOT / SESSIONS_INDEX_MARKDOWN
    sessions_index_payload = read_json(sessions_index_path, {})
    sessions_index_ok = (
        isinstance(sessions_index_payload, dict)
        and sessions_index_payload.get("artifact_type") == "sessions_directory_index"
        and int(sessions_index_payload.get("session_count", -1)) == len(sessions)
        and sessions_index_markdown_path.exists()
    )
    hook_counts = count_live_hook_events(aoa_root)
    compaction_archives = archive_compaction_audit(aoa_root)
    indexed_archives = [item for item in compaction_archives if item.get("archive_status") == "indexed"]
    deferred_archives = [
        item for item in compaction_archives if item.get("archive_status") == "raw_mirrored_index_deferred"
    ]
    real_compaction_archives = [item for item in compaction_archives if int(item.get("compaction_boundary_count", 0) or 0) > 0]
    segment_mismatches = [item for item in indexed_archives if not item.get("matches_expected_segments")]
    segments_match = bool(indexed_archives) and not segment_mismatches
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
            "Session archive directory has a local table of contents",
            "covered" if sessions_index_ok else "missing",
            {
                "markdown": str(sessions_index_markdown_path),
                "json": str(sessions_index_path),
                "index_session_count": sessions_index_payload.get("session_count") if isinstance(sessions_index_payload, dict) else None,
                "registry_session_count": len(sessions),
            },
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
                "indexed_archive_count": len(indexed_archives),
                "mismatch_count": len(segment_mismatches),
                "mismatches": [
                    {
                        "session_label": item["session_label"],
                        "expected": item["expected_segment_count"],
                        "actual": item["actual_segment_count"],
                    }
                    for item in segment_mismatches
                ],
                "indexed_archives": [
                    {
                        "session_label": item["session_label"],
                        "expected": item["expected_segment_count"],
                        "actual": item["actual_segment_count"],
                    }
                    for item in indexed_archives
                ],
                "deferred_archives": [
                    {
                        "session_label": item["session_label"],
                        "expected_after_reindex": item["expected_segment_count"],
                        "current_actual": item["actual_segment_count"],
                        "archive_status": item["archive_status"],
                    }
                    for item in deferred_archives
                ],
            },
            None if segments_match else "Reindex indexed archives whose segment counts no longer match raw boundaries.",
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
    "DESIGN.AGENTS.md",
    "PIPELINE.md",
    "READINESS.md",
    "README.md",
    "NAMING.md",
    "config/AGENTS.md",
    "config/batch-distillation-policy.json",
    "config/event-distillation-routes.json",
    "config/event-taxonomy.json",
    "config/naming-policy.json",
    "hooks/AGENTS.md",
    "hooks/README.md",
    "hooks/codex-hooks.user.example.json",
    "schemas/AGENTS.md",
    "schemas/hook-receipt.schema.json",
    "schemas/incident.schema.json",
    "schemas/segment.index.schema.json",
    "schemas/session.manifest.schema.json",
    "scripts/AGENTS.md",
    "scripts/aoa_session_memory.py",
    "sessions/AGENTS.md",
    "skills/AGENTS.md",
    "skills/aoa-codex-compact-probe/SKILL.md",
    "skills/aoa-codex-hooks-status/SKILL.md",
    "skills/aoa-codex-session-segment-archive/SKILL.md",
    "skills/aoa-session-archive-init/SKILL.md",
    "skills/aoa-session-batch-distill/SKILL.md",
    "skills/aoa-session-first-pass-distill/SKILL.md",
    "skills/aoa-session-history-import/SKILL.md",
    "skills/aoa-session-manual-review/SKILL.md",
    "skills/aoa-session-memory-audit/SKILL.md",
    "skills/aoa-session-memory-doctor/SKILL.md",
    "skills/aoa-session-memory-global-route/SKILL.md",
    "skills/aoa-session-memory-stress-pass/SKILL.md",
    "skills/aoa-session-naming-readiness/SKILL.md",
    "skills/aoa-session-raw-diagnostic/SKILL.md",
    "skills/aoa-session-reindex/SKILL.md",
    "skills/aoa-session-rehydrate/SKILL.md",
    "tests/AGENTS.md",
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
    name_index = read_json(root / SESSION_NAME_INDEX_JSON, {})
    if isinstance(sessions, list) and sessions:
        if not isinstance(name_index, dict) or name_index.get("artifact_type") != "session_name_index":
            problems.append(f"missing or invalid session name index: {root / SESSION_NAME_INDEX_JSON}")
        elif int(name_index.get("session_count", -1)) != len(sessions):
            problems.append(f"session name index count {name_index.get('session_count')} does not match registry count {len(sessions)}")
        elif not isinstance(name_index.get("naming_readiness_counts"), dict):
            problems.append(f"session name index missing naming readiness counts: {root / SESSION_NAME_INDEX_JSON}")
        if not (root / SESSION_NAME_INDEX_MARKDOWN).exists():
            problems.append(f"missing session name index markdown: {root / SESSION_NAME_INDEX_MARKDOWN}")
    if session_root.exists():
        if not (session_root / SESSIONS_AGENTS_MARKDOWN).exists():
            problems.append(f"missing sessions AGENTS.md: {session_root / SESSIONS_AGENTS_MARKDOWN}")
        sessions_index = read_json(session_root / SESSIONS_INDEX_JSON, {})
        if not isinstance(sessions_index, dict) or sessions_index.get("artifact_type") != "sessions_directory_index":
            problems.append(f"missing or invalid sessions directory index: {session_root / SESSIONS_INDEX_JSON}")
        elif int(sessions_index.get("session_count", -1)) != len(sessions):
            problems.append(f"sessions directory index count {sessions_index.get('session_count')} does not match registry count {len(sessions)}")
        elif not isinstance(sessions_index.get("naming_readiness_counts"), dict):
            problems.append(f"sessions directory index missing naming readiness counts: {session_root / SESSIONS_INDEX_JSON}")
        if not (session_root / SESSIONS_INDEX_MARKDOWN).exists():
            problems.append(f"missing sessions directory index markdown: {session_root / SESSIONS_INDEX_MARKDOWN}")
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
        semantic_payload = semantic_names_payload(manifest_payload)
        semantic_items = semantic_payload.get("names", [])
        if semantic_items:
            active = semantic_payload.get("active")
            active_session = semantic_payload.get("active_session")
            slugs = {str(semantic.get("slug")) for semantic in semantic_items if isinstance(semantic, dict)}
            if active not in slugs:
                problems.append(f"semantic active name is not present in names: {session_path}")
            if active_session and active_session not in slugs:
                problems.append(f"semantic active session name is not present in names: {session_path}")
            registry_semantic = item.get("semantic_names") if isinstance(item.get("semantic_names"), dict) else {}
            if registry_semantic.get("active") != active:
                problems.append(f"registry semantic active name is stale: {session_path}")
            if registry_semantic.get("active_session") != active_session:
                problems.append(f"registry semantic active session name is stale: {session_path}")
            for semantic in semantic_items:
                if isinstance(semantic, dict):
                    for problem in validate_semantic_name_record(
                        manifest_payload,
                        session_path,
                        semantic,
                        banned_terms=banned_terms,
                    ):
                        problems.append(f"{problem}: {session_path}")
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

    name_session = sub.add_parser("name-session", help="Attach a semantic custom name to a session without renaming the archive.")
    name_session.add_argument("session", help="Session label/id/title/name fragment.")
    name_session.add_argument("--workspace-root")
    name_session.add_argument("--aoa-root")
    name_session.add_argument("--name", required=True, help="Human-readable semantic name for navigation.")
    name_session.add_argument(
        "--scope",
        choices=["session", "phase", "topic", "alias"],
        default="session",
        help="Name scope. session is the mutable umbrella name; phase/topic names are local anchors.",
    )
    name_session.add_argument(
        "--kind",
        choices=["session_essence", "semantic_alias", "dominant_topic", "continuation_name", "operator_name"],
        default="session_essence",
    )
    name_session.add_argument("--evidence", action="append", help="Raw evidence ref such as raw:line:123. Required for --apply.")
    name_session.add_argument("--from-line", type=int, help="Optional first raw line covered by this name.")
    name_session.add_argument("--to-line", type=int, help="Optional last raw line covered by this name.")
    name_session.add_argument("--coverage-note", default="", help="Short note explaining what the raw range covers.")
    name_session.add_argument("--source", default="operator")
    name_session.add_argument("--note", default="")
    name_session.add_argument("--apply", action="store_true", help="Write manifest, registry, and session index. Default only plans.")
    name_session.add_argument("--replace", action="store_true", help="Replace an existing semantic name with the same slug.")
    name_session.add_argument("--skip-raw-hash-check", action="store_true", help="Do not recalculate raw sha256 before writing.")
    name_session.add_argument("--write-report", action="store_true", help="Write JSON and Markdown reports under .aoa/diagnostics.")
    name_session.set_defaults(func=command_name_session)

    phase_discovery = sub.add_parser("phase-discovery", help="Build unreviewed phase/topic candidates from generated segment indexes and raw refs.")
    phase_discovery.add_argument("session", help="Session label/id/title/name fragment.")
    phase_discovery.add_argument("--workspace-root")
    phase_discovery.add_argument("--aoa-root")
    phase_discovery.add_argument("--write", action="store_true", help="Write naming/phase-discovery.json and .md inside the session archive.")
    phase_discovery.add_argument("--write-report", action="store_true", help="Write JSON and Markdown reports under .aoa/diagnostics.")
    phase_discovery.set_defaults(func=command_phase_discovery)

    review_phase_name = sub.add_parser(
        "review-phase-name",
        help="Review one phase-discovery candidate and optionally apply a reviewed phase name.",
    )
    review_phase_name.add_argument("session", help="Session label/id/title/name fragment.")
    review_phase_name.add_argument("--workspace-root")
    review_phase_name.add_argument("--aoa-root")
    review_phase_name.add_argument("--segment", required=True, help="Phase-discovery segment id, for example 003.")
    review_phase_name.add_argument("--reviewed-name", help="Reviewed semantic phase name to apply.")
    review_phase_name.add_argument(
        "--use-candidate",
        action="store_true",
        help="Use the generated candidate name. Rejected for candidates that need semantic synthesis.",
    )
    review_phase_name.add_argument("--coverage-note", default="", help="Optional reviewed coverage note.")
    review_phase_name.add_argument("--apply", action="store_true", help="Apply the reviewed phase name and refresh name indexes.")
    review_phase_name.add_argument("--replace", action="store_true", help="Replace an existing semantic name with the same slug.")
    review_phase_name.add_argument("--refresh", action="store_true", help="Rebuild phase-discovery before reviewing the candidate.")
    review_phase_name.add_argument("--skip-raw-hash-check", action="store_true", help="Do not recalculate raw sha256 before writing.")
    review_phase_name.add_argument("--write-report", action="store_true", help="Write JSON and Markdown reports under .aoa/diagnostics.")
    review_phase_name.set_defaults(func=command_review_phase_name)

    distill = sub.add_parser("distill", help="Write a provisional first-pass distillation route map for a session.")
    distill.add_argument("session", nargs="?", default="latest")
    distill.add_argument("--workspace-root")
    distill.add_argument("--aoa-root")
    distill.add_argument("--max-events-per-type", type=int, default=30)
    distill.set_defaults(func=command_distill)

    batch_distill = sub.add_parser("batch-distill", help="Build a first-wave distillation conveyor across many indexed sessions.")
    batch_distill.add_argument("--workspace-root")
    batch_distill.add_argument("--aoa-root")
    batch_distill.add_argument("--since", help="Select sessions with archive dates on or after YYYY-MM-DD.")
    batch_distill.add_argument("--since-days", type=int, help="Rolling window when --since is not provided.")
    batch_distill.add_argument("--until", help="Select sessions with archive dates on or before YYYY-MM-DD.")
    batch_distill.add_argument("--limit", type=int, help="Limit selected sessions after chronological ordering.")
    batch_distill.add_argument("--apply", action="store_true", help="Write provisional first-pass distillation artifacts. Default only plans.")
    batch_distill.add_argument("--force", action="store_true", help="Rebuild first-pass distillation even when it already exists.")
    batch_distill.add_argument("--include-distilled", action="store_true", help="Include already first-pass-distilled sessions in the queue.")
    batch_distill.add_argument("--write-report", action="store_true", help="Write JSON and Markdown conveyor reports under .aoa/diagnostics.")
    batch_distill.add_argument("--max-events-per-type", type=int, default=30)
    batch_distill.add_argument("--full", action="store_true", help="Print complete queue results to stdout.")
    batch_distill.set_defaults(func=command_batch_distill)

    repair_titles = sub.add_parser("repair-session-titles", help="Find and optionally repair weak generated session titles.")
    repair_titles.add_argument("session", nargs="?", default="all", help="Session label/id/title fragment or all.")
    repair_titles.add_argument("--workspace-root")
    repair_titles.add_argument("--aoa-root")
    repair_titles.add_argument("--since", help="Select sessions with archive dates on or after YYYY-MM-DD when session=all.")
    repair_titles.add_argument("--since-days", type=int, help="Rolling window when --since is not provided and session=all.")
    repair_titles.add_argument("--until", help="Select sessions with archive dates on or before YYYY-MM-DD when session=all.")
    repair_titles.add_argument("--limit", type=int, help="Limit selected sessions after chronological ordering when session=all.")
    repair_titles.add_argument("--apply", action="store_true", help="Move archives and rewrite generated identity surfaces. Default only plans.")
    repair_titles.add_argument("--write-report", action="store_true", help="Write JSON and Markdown repair reports under .aoa/diagnostics.")
    repair_titles.add_argument("--full", action="store_true", help="Print complete repair results to stdout.")
    repair_titles.set_defaults(func=command_repair_session_titles)

    naming_readiness = sub.add_parser("naming-readiness", help="Assess whether sessions are ready for semantic naming or need lower-layer repair first.")
    naming_readiness.add_argument("session", nargs="?", default="all", help="Session label/id/title/name fragment or all.")
    naming_readiness.add_argument("--workspace-root")
    naming_readiness.add_argument("--aoa-root")
    naming_readiness.add_argument("--since", help="Select sessions with archive dates on or after YYYY-MM-DD when session=all.")
    naming_readiness.add_argument("--since-days", type=int, help="Rolling window when --since is not provided and session=all.")
    naming_readiness.add_argument("--until", help="Select sessions with archive dates on or before YYYY-MM-DD when session=all.")
    naming_readiness.add_argument("--limit", type=int, help="Limit selected sessions after chronological ordering when session=all.")
    naming_readiness.add_argument("--refresh-indexes", action="store_true", help="Regenerate SESSION_NAMES.md and sessions/INDEX.md with readiness data.")
    naming_readiness.add_argument("--write-report", action="store_true", help="Write JSON and Markdown readiness reports under .aoa/diagnostics.")
    naming_readiness.add_argument("--full", action="store_true", help="Print complete readiness results to stdout.")
    naming_readiness.set_defaults(func=command_naming_readiness)

    manual_review = sub.add_parser("manual-review", help="Build manual review packets for first-wave review lanes.")
    manual_review.add_argument("--workspace-root")
    manual_review.add_argument("--aoa-root")
    manual_review.add_argument("--since", help="Select sessions with archive dates on or after YYYY-MM-DD.")
    manual_review.add_argument("--since-days", type=int, help="Rolling window when --since is not provided.")
    manual_review.add_argument("--until", help="Select sessions with archive dates on or before YYYY-MM-DD.")
    manual_review.add_argument("--limit", type=int, help="Limit selected sessions after chronological ordering.")
    manual_review.add_argument("--priority", choices=["sample", "standard", "deep"], default="deep", help="Minimum manual review priority to packetize.")
    manual_review.add_argument("--apply", action="store_true", help="Write manual review packets and promotion indexes. Default only plans.")
    manual_review.add_argument("--wave-id", help="Explicit append-only wave id. Defaults to the next manual-review-waveN.")
    manual_review.add_argument("--write-report", action="store_true", help="Write JSON and Markdown wave reports under .aoa/diagnostics.")
    manual_review.add_argument("--max-events-per-type", type=int, default=20)
    manual_review.add_argument("--full", action="store_true", help="Print complete manual-review results to stdout.")
    manual_review.set_defaults(func=command_manual_review)

    promotion_review = sub.add_parser("promotion-review", help="Aggregate unreviewed promotion candidates from manual review packets.")
    promotion_review.add_argument("--workspace-root")
    promotion_review.add_argument("--aoa-root")
    promotion_review.add_argument("--since", help="Select sessions with archive dates on or after YYYY-MM-DD.")
    promotion_review.add_argument("--since-days", type=int, help="Rolling window when --since is not provided.")
    promotion_review.add_argument("--until", help="Select sessions with archive dates on or before YYYY-MM-DD.")
    promotion_review.add_argument("--limit", type=int, help="Limit selected sessions after chronological ordering.")
    promotion_review.add_argument("--write-report", action="store_true", help="Write JSON and Markdown promotion reports under .aoa/diagnostics.")
    promotion_review.add_argument("--full", action="store_true", help="Print complete promotion-review results to stdout.")
    promotion_review.set_defaults(func=command_promotion_review)

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

    import_sessions = sub.add_parser("import-codex-sessions", help="Discover and sequentially import historical Codex JSONL sessions.")
    import_sessions.add_argument("--workspace-root")
    import_sessions.add_argument("--aoa-root")
    import_sessions.add_argument("--source-root", help="Codex sessions root; defaults to ~/.codex/sessions.")
    import_sessions.add_argument("--since", help="Import sessions with session dates on or after YYYY-MM-DD.")
    import_sessions.add_argument("--since-days", type=int, default=21, help="Default rolling window when --since is not provided.")
    import_sessions.add_argument("--until", help="Import sessions with session dates on or before YYYY-MM-DD.")
    import_sessions.add_argument("--limit", type=int, help="Limit selected sessions after chronological discovery.")
    import_sessions.add_argument("--dry-run", action="store_true", help="Only report planned imports and skips.")
    import_sessions.add_argument("--force", action="store_true", help="Rebuild already indexed archives instead of skipping them.")
    import_sessions.add_argument("--write-report", action="store_true", help="Write JSON and Markdown import reports under .aoa/diagnostics.")
    import_sessions.add_argument("--full", action="store_true", help="Print complete import results to stdout.")
    import_sessions.set_defaults(func=command_import_codex_sessions)

    reindex = sub.add_parser("reindex-sessions", help="Regenerate generated segment Markdown and indexes from preserved raw JSONL.")
    reindex.add_argument("session", nargs="?", default="all", help="Session label/id/title fragment or all.")
    reindex.add_argument("--workspace-root")
    reindex.add_argument("--aoa-root")
    reindex.add_argument("--since", help="Select sessions with archive dates on or after YYYY-MM-DD when session=all.")
    reindex.add_argument("--since-days", type=int, help="Rolling window when --since is not provided and session=all.")
    reindex.add_argument("--until", help="Select sessions with archive dates on or before YYYY-MM-DD when session=all.")
    reindex.add_argument("--limit", type=int, help="Limit selected sessions after chronological ordering when session=all.")
    reindex.add_argument("--dry-run", action="store_true", help="Only report which archives would be regenerated.")
    reindex.add_argument("--write-report", action="store_true", help="Write JSON and Markdown reindex reports under .aoa/diagnostics.")
    reindex.add_argument("--full", action="store_true", help="Print complete reindex results to stdout.")
    reindex.set_defaults(func=command_reindex_sessions)

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
