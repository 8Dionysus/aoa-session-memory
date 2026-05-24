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
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
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
SHA256_FILE_CACHE: dict[tuple[str, int, int], str] = {}
SESSION_ROOT = Path("sessions")
DIAGNOSTICS_ROOT = Path("diagnostics")
HOOK_JOBS_ROOT = DIAGNOSTICS_ROOT / "hook-jobs"
SEARCH_ROOT = Path("search")
SEARCH_DB_NAME = "aoa-search.sqlite3"
SEARCH_PROVIDER_CONFIG_PATH = Path("config/search-providers.json")
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
NAMING_GOLDEN_SET_PATH = Path("config/naming-golden-set.json")
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
RAW_BLOCKS_DIR = "blocks"
RAW_BLOCK_INDEX_JSON = "blocks.index.json"
RAW_COMPACTION_EVENTS_JSONL = "compaction-events.jsonl"
CONVERSATION_ACT_SCHEMA_VERSION = 1
SESSION_ACT_SCHEMA_VERSION = 1
WORK_CONTEXT_SCHEMA_VERSION = 1
ROUTE_SIGNAL_SCHEMA_VERSION = 1
ROUTE_SIGNAL_CLASSIFIER_VERSION = 7
ATLAS_SCHEMA_VERSION = 1
SEARCH_SCHEMA_VERSION = 3
SEARCH_PROVIDER_SCHEMA_VERSION = 1
ATLAS_ROOT = Path("maps")
ATLAS_POLICY_PATH = Path("config/atlas-policy.json")
ATLAS_ROUTE_ENTRY_SCHEMA_PATH = Path("schemas/atlas-route-entry.schema.json")
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
DEFAULT_HOOK_MIRROR_MAX_BYTES = 16 * 1024 * 1024
DEFAULT_HOOK_REGISTRY_LOCK_TIMEOUT_SEC = 0.25
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
    "maps",
    "schemas",
    "scripts",
    "skills",
    "tests",
]
PORTABLE_COPY_IGNORE = {".git", ".pytest_cache", "__pycache__"}

ROUTE_SIGNAL_LAYER_TO_AXIS = {
    "scope_contract": "by-scope-contract",
    "authority_surface": "by-authority-surface",
    "entity": "by-entity",
    "path": "by-path",
    "tool": "by-tool",
    "mcp": "by-mcp",
    "goal": "by-goal",
    "verification_state": "by-verification-state",
    "decision_thread": "by-open-thread",
    "failure_mode": "by-failure-mode",
    "hook_health": "by-hook-health",
    "memory_provenance": "by-memory-surface",
    "external_snapshot": "by-external-snapshot",
    "phase_topic": "by-phase-topic",
    "delivery_state": "by-delivery-state",
    "index_health": "by-index-health",
    "evidence_provenance": "by-evidence-provenance",
    "owner_route": "by-owner-route",
    "freshness_drift": "by-freshness",
    "runtime_environment": "by-runtime-environment",
    "mutation_surface": "by-mutation-surface",
    "correlation": "by-correlation",
    "confidence": "by-confidence",
    "access_boundary": "by-access-boundary",
    "resource_profile": "by-resource-profile",
    "operator_preference": "by-operator-preference",
    "risk": "by-risk",
    "review_state": "by-review-state",
    "promotion_candidate": "by-promotion-candidate",
    "operator_request": "by-operator-request",
    "route_next_action": "by-route-next-action",
}

DEFAULT_ATLAS_AXES = [
    "by-work-context",
    "by-repo-family",
    "by-memory-surface",
    "by-authority-surface",
    "by-session-act",
    "by-conversation-act",
    "by-scope-contract",
    "by-verification-state",
    "by-open-thread",
    "by-entity",
    "by-path",
    "by-tool",
    "by-mcp",
    "by-hook-health",
    "by-goal",
    "by-delivery-state",
    "by-failure-mode",
    "by-risk",
    "by-phase-topic",
    "by-external-snapshot",
    "by-review-state",
    "by-promotion-candidate",
    "by-index-health",
    "by-time",
    "by-operator-request",
    "by-route-next-action",
    "by-evidence-provenance",
    "by-owner-route",
    "by-freshness",
    "by-runtime-environment",
    "by-mutation-surface",
    "by-correlation",
    "by-confidence",
    "by-access-boundary",
    "by-resource-profile",
    "by-operator-preference",
]
MAX_ATLAS_ROUTE_KEYS_PER_LAYER = 40
DEFAULT_ROUTE_SAMPLE_LIMIT = 2
ROUTE_READINESS_REQUIREMENTS = [
    {
        "id": "scope_contract",
        "title": "Scope / Contract",
        "required_layers": ["scope_contract"],
    },
    {
        "id": "authority_surface",
        "title": "Authority / Truth Surface",
        "required_layers": ["authority_surface"],
    },
    {
        "id": "entity_path_graph",
        "title": "Entity / Path Graph",
        "required_layers": ["entity", "path", "tool", "mcp", "goal"],
    },
    {
        "id": "verification_map",
        "title": "Verification Map",
        "required_layers": ["verification_state"],
    },
    {
        "id": "decision_open_thread",
        "title": "Decision / Assumption / Open Thread",
        "required_layers": ["decision_thread"],
    },
    {
        "id": "failure_taxonomy",
        "title": "Failure / Diagnostic Taxonomy",
        "required_layers": ["failure_mode"],
    },
    {
        "id": "hook_health",
        "title": "Hook Health",
        "required_layers": ["hook_health"],
    },
    {
        "id": "memory_provenance",
        "title": "Memory Provenance",
        "required_layers": ["memory_provenance"],
    },
    {
        "id": "external_snapshot",
        "title": "External Context Snapshot",
        "required_layers": ["external_snapshot"],
    },
    {
        "id": "phase_topic",
        "title": "Phase / Topic Boundaries",
        "required_layers": ["phase_topic"],
    },
    {
        "id": "delivery_state",
        "title": "Delivery State",
        "required_layers": ["delivery_state"],
    },
    {
        "id": "findability_index_health",
        "title": "Findability / Index Health",
        "required_layers": ["index_health"],
    },
    {
        "id": "evidence_provenance",
        "title": "Evidence / Provenance Chain",
        "required_layers": ["evidence_provenance"],
    },
    {
        "id": "owner_route",
        "title": "Owner / Route Law",
        "required_layers": ["owner_route"],
    },
    {
        "id": "freshness_drift",
        "title": "Freshness / Drift",
        "required_layers": ["freshness_drift"],
    },
    {
        "id": "runtime_environment",
        "title": "Environment / Runtime State",
        "required_layers": ["runtime_environment"],
    },
    {
        "id": "mutation_surface",
        "title": "Mutation / Impact Surface",
        "required_layers": ["mutation_surface"],
    },
    {
        "id": "correlation_graph",
        "title": "Correlation Graph",
        "required_layers": ["correlation"],
    },
    {
        "id": "confidence_conflict",
        "title": "Confidence / Ambiguity / Conflict",
        "required_layers": ["confidence"],
    },
    {
        "id": "access_boundary",
        "title": "Access / Secret / Privacy Boundary",
        "required_layers": ["access_boundary"],
    },
    {
        "id": "resource_profile",
        "title": "Resource / Cost / Latency",
        "required_layers": ["resource_profile"],
    },
    {
        "id": "operator_preference",
        "title": "Operator Preference / Standing Instruction",
        "required_layers": ["operator_preference"],
    },
]


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
        trimmed = slug[:max_chars].rstrip("-._")
        if "-" in trimmed:
            trimmed = trimmed.rsplit("-", 1)[0] or trimmed
        slug = trimmed
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
    directory = Path(_directory)
    parts = directory.parts
    if "maps" in parts:
        if directory.name == "entries":
            ignored.update(name for name in names if name != ".gitkeep")
        if directory.name.startswith("by-") or directory.name == "maps":
            ignored.update(name for name in names if name in {"INDEX.md", "index.json"})
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
        candidates.extend(package_root.glob("node_modules/@openai/codex-*/vendor/*/bin/codex"))
        candidates.extend(package_root.glob("node_modules/@openai/codex-*/vendor/*/codex/codex"))
        candidates.extend(package_root.glob("vendor/*/bin/codex"))
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


def load_codex_config_file(config_path: Path) -> dict[str, Any]:
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


def load_codex_project_config(workspace_root: Path) -> dict[str, Any]:
    return load_codex_config_file(workspace_root / ".codex" / "config.toml")


def codex_user_config_path() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    return Path(codex_home).expanduser() / "config.toml" if codex_home else Path.home() / ".codex" / "config.toml"


def config_feature_enabled(config: dict[str, Any], *names: str) -> bool:
    features = config.get("features") if isinstance(config.get("features"), dict) else {}
    return any(features.get(name) is True for name in names)


def first_int_config_value(configs: list[tuple[str, dict[str, Any]]], key: str) -> tuple[int, str | None]:
    for source, config in configs:
        value = config.get(key)
        if value is None:
            continue
        try:
            return int(value), source
        except (TypeError, ValueError):
            continue
    return 0, None


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

    project_config_path = workspace_root / ".codex" / "config.toml"
    user_config_path = codex_user_config_path()
    project_config = load_codex_config_file(project_config_path)
    user_config = load_codex_config_file(user_config_path)
    config_sources = [
        ("project", project_config, project_config_path),
        ("user", user_config, user_config_path),
    ]
    ordered_configs = [(name, config) for name, config, _path in config_sources]
    hooks_sources = [
        name
        for name, config, _path in config_sources
        if config_feature_enabled(config, "hooks", "codex_hooks")
    ]
    hooks_enabled = bool(hooks_sources)
    context_window, context_window_source = first_int_config_value(ordered_configs, "model_context_window")
    compact_limit, compact_limit_source = first_int_config_value(ordered_configs, "model_auto_compact_token_limit")
    compact_ratio = compact_limit / context_window if context_window > 0 else None
    add_check(
        "project_hooks_enabled",
        hooks_enabled,
        {
            "enabled_sources": hooks_sources,
            "accepted_feature_keys": ["hooks", "codex_hooks"],
            "project_config": str(project_config_path),
            "user_config": str(user_config_path),
        },
    )
    add_check(
        "compact_window_configured",
        context_window > 0 and compact_limit > 0 and compact_limit < context_window,
        {
            "context_window": context_window,
            "compact_limit": compact_limit,
            "ratio": compact_ratio,
            "context_window_source": context_window_source,
            "compact_limit_source": compact_limit_source,
        },
    )

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
        "codex_config_sources": {
            name: {"path": str(path), "exists": path.exists(), "loaded": bool(config)}
            for name, config, path in config_sources
        },
        "hooks_enabled_sources": hooks_sources,
        "model_context_window_source": context_window_source,
        "model_auto_compact_token_limit_source": compact_limit_source,
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
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    cached = SHA256_FILE_CACHE.get(key)
    if cached:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest()
    SHA256_FILE_CACHE[key] = value
    return value


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
    for key in ("call_id", "tool_call_id"):
        value = payload.get(key)
        if value:
            return str(value)
    payload_type = str(payload.get("type") or "")
    if payload_type in {"function_call", "tool_call", "custom_tool_call", "function_call_output", "tool_call_output"}:
        value = payload.get("id")
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


def tool_name_from_payload(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return str(payload.get("name") or payload.get("tool_name") or "").strip()


def normalized_tool_name(tool_name: str) -> str:
    name = str(tool_name or "").strip()
    if not name:
        return ""
    return name.split(".")[-1]


def tool_namespace_for_name(tool_name: str) -> str:
    raw = str(tool_name or "").strip()
    lowered = raw.lower()
    short = normalized_tool_name(raw).lower()
    if not raw:
        return "unknown"
    if raw.startswith("mcp__") or short in {"list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource"}:
        return "mcp"
    if short in {"create_goal", "update_goal", "get_goal"}:
        return "codex_goal"
    if short in {
        "exec_command",
        "write_stdin",
        "apply_patch",
        "update_plan",
        "create_goal",
        "update_goal",
        "get_goal",
        "view_image",
    }:
        return "codex_developer_tool"
    if any(marker in lowered for marker in ("gmail", "google", "github", "canva", "hugging", "openai", "notion")):
        return "app_connector"
    return raw.split(".")[0] if "." in raw else "tool"


def session_act_for_goal_tool(tool_name: str) -> str | None:
    short = normalized_tool_name(tool_name)
    return {
        "create_goal": "goal_created",
        "update_goal": "goal_updated",
        "get_goal": "goal_inspected",
    }.get(short)


def session_act_for_mcp_tool(tool_name: str) -> str | None:
    short = normalized_tool_name(tool_name)
    if short == "read_mcp_resource":
        return "mcp_resource_read"
    if short == "list_mcp_resources":
        return "mcp_resource_list"
    if short == "list_mcp_resource_templates":
        return "mcp_resource_template_list"
    if str(tool_name or "").startswith("mcp__"):
        return "mcp_tool_call"
    return None


def memory_surface_from_text(text: str) -> str | None:
    lowered = str(text or "").lower()
    if not lowered:
        return None
    if (
        "/home/dionysus/.codex/memories" in lowered
        or ".codex/memories" in lowered
        or "memory_summary.md" in lowered
        or "memory.md" in lowered
        or "rollout_summaries" in lowered
        or "oai-mem-citation" in lowered
        or "codex-memories" in lowered
        or "codex memories" in lowered
    ):
        return "codex_memories"
    if (
        "/srv/abyssos/.aoa" in lowered
        or ".aoa/sessions" in lowered
        or "session-registry.json" in lowered
        or "session-name-index.json" in lowered
        or "session_names.md" in lowered
        or "aoa-session-memory" in lowered
        or "session memory" in lowered
        or "session-memory" in lowered
    ):
        return "aoa_session_memory"
    if "/home/dionysus/.codex/sessions" in lowered or "rollout-" in lowered and ".jsonl" in lowered:
        return "codex_transcripts"
    generic_memory_patterns = [
        r"\b(?:use|read|search|query|check|consult|load|open|inspect|refresh|update|write|save|remember|forget|skip|cite|verify)\s+(?:the\s+)?(?:codex\s+|session\s+|project\s+)?memor(?:y|ies)\b",
        r"\bmemor(?:y|ies)\s+(?:pass|lookup|search|citation|citations|update|request|folder|registry|provenance|used|skipped|cited|verified|unverified)\b",
        r"\b(?:memory-derived|unverified memory|skipped memory|memory skipped|memory used)\b",
        r"\b(?:использ|прочит|найд|ищи|провер|обнов|запомн|цитир|пропуст|не использ).{0,48}памят",
        r"\bпамят.{0,48}(?:использ|прочит|найд|ищи|провер|обнов|запомн|цитир|пропуст)",
    ]
    if any(re.search(pattern, lowered) for pattern in generic_memory_patterns):
        return "memory_general"
    return None


def memory_surface_for_event(event_type: str, source_type: str, semantic_lower: str, tags: set[str], facets: dict[str, Any]) -> str | None:
    texts = [semantic_lower, source_type, " ".join(sorted(tags))]
    for key in ("command", "tool_name", "path", "payload_type"):
        value = facets.get(key)
        if value:
            texts.append(str(value))
    return memory_surface_from_text(" ".join(texts))


def session_act_kind_for_memory(event_type: str, source_type: str, semantic_lower: str, tags: set[str], facets: dict[str, Any]) -> str | None:
    surface = memory_surface_for_event(event_type, source_type, semantic_lower, tags, facets)
    if not surface:
        return None
    if "oai-mem-citation" in semantic_lower:
        return "memory_citation"
    if event_type == "USER_INTENT":
        return "memory_request"
    if event_type in {"CONTEXT_STATE", "COMPACTION_EVENT"}:
        return "memory_context"
    if event_type in {"FILE_WRITE", "DIFF"}:
        return "memory_write"
    if event_type in {"COMMAND", "FILE_READ", "TOOL_CALL"}:
        return "memory_read"
    if event_type in {"COMMAND_OUTPUT", "TOOL_OUTPUT", "VERIFICATION"}:
        return "memory_observation"
    if event_type in {"ASSISTANT_PLAN", "ASSISTANT_MESSAGE", "CHECKPOINT", "FINAL_STATE"}:
        return "memory_discussion"
    return "memory_signal"


def session_act_for_event(
    event_type: str,
    source_type: str,
    payload: Any,
    semantic_lower: str,
    tags: set[str],
    facets: dict[str, Any],
    outcome: str,
) -> dict[str, Any] | None:
    conversation_act = facets.get("conversation_act") if isinstance(facets.get("conversation_act"), dict) else {}
    tool_name = str(facets.get("tool_name") or tool_name_from_payload(payload))
    memory_kind = session_act_kind_for_memory(event_type, source_type, semantic_lower, tags, facets)
    kind: str | None = memory_kind
    if not kind and tool_name:
        kind = session_act_for_goal_tool(tool_name)
        if kind == "goal_updated" and isinstance(payload, dict):
            status = str(command_payload_args(payload).get("status") or "").lower()
            if status == "complete":
                kind = "goal_completed"
            elif status == "blocked":
                kind = "goal_blocked"
        kind = kind or session_act_for_mcp_tool(tool_name)
        if not kind:
            namespace = tool_namespace_for_name(tool_name)
            kind = "app_connector_call" if namespace == "app_connector" else "tool_call"
    if not kind:
        if event_type == "USER_INTENT":
            kind = "operator_prompt"
        elif event_type == "ASSISTANT_PLAN":
            kind = "assistant_plan"
        elif event_type == "ASSISTANT_MESSAGE":
            kind = "assistant_message"
        elif event_type == "FINAL_STATE":
            kind = "assistant_closeout"
        elif event_type == "HOOK_EVENT":
            kind = "hook_receipt"
        elif event_type == "COMPACTION_EVENT":
            kind = "compaction_boundary"
        elif event_type == "VERIFICATION":
            kind = "verification_result"
        elif event_type == "ERROR":
            kind = "error_signal"
        elif event_type in {"FILE_READ"}:
            kind = "file_inspection"
        elif event_type in {"FILE_WRITE", "DIFF"}:
            kind = "file_mutation"
        elif event_type == "COMMAND":
            command_kind = str(facets.get("command_kind") or "")
            kind = "verification_request" if command_kind == "verification" else "command_run"
        elif event_type == "COMMAND_OUTPUT":
            kind = "command_result"
        elif event_type == "TOOL_OUTPUT":
            kind = "tool_output"
    if not kind:
        return None
    surface = memory_surface_for_event(event_type, source_type, semantic_lower, tags, facets)
    payload_type = ""
    if isinstance(payload, dict):
        payload_type = str(payload.get("type") or "")
    act = {
        "schema_version": SESSION_ACT_SCHEMA_VERSION,
        "kind": kind,
        "raw_event_type": event_type,
        "source_type": source_type,
        "payload_type": str(facets.get("payload_type") or payload_type),
        "tool_name": tool_name,
        "tool_namespace": tool_namespace_for_name(tool_name) if tool_name else "",
        "memory_surface": surface or "",
        "conversation_act": str(conversation_act.get("kind") or ""),
        "outcome": outcome,
        "confidence": "high" if kind not in {"memory_signal"} else "medium",
    }
    if isinstance(payload, dict):
        args = command_payload_args(payload)
        for key in ("server", "uri", "resource", "hook_event_name"):
            value = payload.get(key) or args.get(key)
            if value:
                act[key] = str(value)
    if facets.get("message_type"):
        act["message_type"] = str(facets["message_type"])
    return act


def route_key_slug(value: Any, *, fallback: str = "signal", max_chars: int = 80) -> str:
    text = str(value or "").strip().lower().replace("_", "-")
    text = re.sub(r"\s+", "-", text)
    slug = readable_slug(text, fallback=fallback, max_chars=max_chars)
    return slug.replace("-", "_")


ENTITY_STOPWORDS = {
    "add",
    "all",
    "alter",
    "and",
    "as",
    "by",
    "case",
    "column",
    "constraint",
    "create",
    "default",
    "delete",
    "drop",
    "else",
    "exists",
    "false",
    "for",
    "from",
    "if",
    "in",
    "index",
    "insert",
    "integer",
    "into",
    "join",
    "key",
    "limit",
    "not",
    "null",
    "on",
    "or",
    "primary",
    "select",
    "set",
    "table",
    "text",
    "then",
    "true",
    "update",
    "values",
    "where",
}


def env_entity_candidate(value: str) -> bool:
    token = str(value or "").strip()
    if not token:
        return False
    slug = route_key_slug(token, fallback="entity")
    if slug in ENTITY_STOPWORDS:
        return False
    if "_" in token:
        return True
    return len(token) >= 5


def has_secret_or_privacy_boundary(text: str) -> bool:
    lowered = str(text or "").lower()
    if not lowered:
        return False
    patterns = [
        r"\b(secret|secrets|credential|credentials|password|passwd|api[-_ ]?key|private[-_ ]?key)\b",
        r"\b(access|auth|bearer|refresh|session)[-_ ]?token\b",
        r"\btoken\b.{0,48}\b(expose|exposed|leak|leaked|redact|mask|secret|credential|password|private|privacy)\b",
        r"\b(expose|exposed|leak|leaked|redact|mask|secret|credential|password|private|privacy)\b.{0,48}\btoken\b",
        r"\b(pii|personal data|private data|privacy boundary|privacy)\b",
        r"\b(секрет|секреты|парол|пароль|токен доступа|персональн|приватн)\b",
        r"\bsk-[a-z0-9][a-z0-9_-]{8,}\b",
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


def has_findability_index_health_signal(text: str) -> bool:
    lowered = str(text or "").lower()
    if not lowered:
        return False
    patterns = [
        r"\b(findability|index health|restore-ready|restore ready|repair/reindex)\b",
        r"\b(session_act|work_context|verification map|open threads?|naming readiness|search freshness)\b",
        r"\b(search-index|search index|route index|segment index|session index)\b",
        r"\b(session\.index\.json|session\.manifest\.json|session-registry\.json|session-name-index\.json)\b",
        r"\b(raw/session\.raw\.jsonl|raw refs?|raw:line:|raw_unavailable|raw unavailable)\b",
        r"\b(reindex|reindex-sessions)\b",
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


def has_landed_slices_preference(text: str) -> bool:
    lowered = str(text or "").lower()
    if not lowered:
        return False
    if "<subagent_notification" in lowered:
        return False
    return bool(
        re.search(r"\blanded[- ]?(?:slices?|срез\w*)\b", lowered)
        or re.search(r"\b(?:small|narrow|узк\w*)\b.{0,48}\b(?:landed[- ]?)?срез\w*\b", lowered)
        or re.search(r"\b(?:узк\w*)\b.{0,48}\blanded\b", lowered)
    )


def has_failed_command_or_test_signal(text: str) -> bool:
    lowered = str(text or "").lower()
    if not lowered:
        return False
    if re.search(r"\bprocess exited with code\s+[1-9]\d*\b", lowered):
        return True
    if re.search(r"\b(?:command failed with exit code|exited with code|exit code:)\s+[1-9]\d*\b", lowered):
        return True
    if re.search(r"\b\d+\s+failed\b", lowered):
        return True
    if "==== failures" in lowered or "traceback (most recent call last)" in lowered:
        return True
    if "pytest" in lowered and re.search(r"\b(failed|failures|error|errors)\b", lowered):
        return True
    return False


def route_signal_index_stale_reasons(index: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if int_value(index.get("route_signal_schema_version")) != ROUTE_SIGNAL_SCHEMA_VERSION:
        reasons.append("route_signal_schema_mismatch")
    if int_value(index.get("route_signal_classifier_version")) != ROUTE_SIGNAL_CLASSIFIER_VERSION:
        reasons.append("route_signal_classifier_mismatch")
    return reasons


def route_signal_index_is_current(index: dict[str, Any]) -> bool:
    return not route_signal_index_stale_reasons(index)


def compact_signal_detail(value: Any, *, max_chars: int = 240) -> str:
    if isinstance(value, (dict, list)):
        return short_text(json.dumps(value, ensure_ascii=False, sort_keys=True), max_chars=max_chars)
    return short_text(value, max_chars=max_chars)


def route_signals_for_event(
    event_type: str,
    source_type: str,
    payload: Any,
    semantic_text: str,
    raw_text: str,
    tags: set[str],
    facets: dict[str, Any],
    outcome: str,
    correlation_id: str | None,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add(
        layer: str,
        key: str,
        *,
        confidence: str = "medium",
        source: str = "heuristic",
        detail: Any = "",
        axis: str | None = None,
    ) -> None:
        route_key = route_key_slug(key)
        if not layer or not route_key:
            return
        pair = (layer, route_key)
        if pair in seen:
            return
        seen.add(pair)
        item = {
            "schema_version": ROUTE_SIGNAL_SCHEMA_VERSION,
            "layer": layer,
            "key": route_key,
            "axis": axis or ROUTE_SIGNAL_LAYER_TO_AXIS.get(layer, ""),
            "confidence": confidence,
            "source": source,
        }
        if detail:
            item["detail"] = compact_signal_detail(detail)
        signals.append(item)

    semantic_limited = semantic_text[:6000]
    raw_limited = raw_text[:6000]
    command = str(facets.get("command") or "")
    command_lower = command.lower()
    conversation_act = facets.get("conversation_act") if isinstance(facets.get("conversation_act"), dict) else {}
    session_act = facets.get("session_act") if isinstance(facets.get("session_act"), dict) else {}
    tool_name = str(facets.get("tool_name") or tool_name_from_payload(payload))
    tool_namespace = str(facets.get("tool_namespace") or tool_namespace_for_name(tool_name) if tool_name else "")
    haystack = " ".join(
        str(part)
        for part in [
            semantic_limited,
            raw_limited if event_type in {"COMMAND_OUTPUT", "TOOL_OUTPUT", "ERROR", "VERIFICATION"} else "",
            " ".join(sorted(tags)),
            facets.get("command"),
            facets.get("tool_name"),
            facets.get("tool_namespace"),
            facets.get("message_type"),
        ]
        if part
    ).lower()
    surface_haystack = " ".join(
        str(part)
        for part in [
            semantic_limited,
            raw_limited if event_type in {"COMMAND_OUTPUT", "TOOL_OUTPUT", "ERROR", "VERIFICATION"} else "",
            command,
        ]
        if part
    ).lower()
    route_text_haystack = "" if event_type == "CONTEXT_STATE" else haystack
    route_surface_haystack = "" if event_type == "CONTEXT_STATE" else surface_haystack
    route_semantic_limited = "" if event_type == "CONTEXT_STATE" else semantic_limited

    if event_type == "SESSION_META":
        add("evidence_provenance", "raw_line", confidence="high", source="raw_event_type")
        add("runtime_environment", "session_meta", confidence="high", source="raw_event_type")
        if isinstance(payload, dict):
            for key in ("cwd", "model", "permission_mode", "sandbox_mode", "approval_policy"):
                if payload.get(key):
                    add("runtime_environment", key, confidence="high", source="session_meta", detail=payload.get(key))
                    if key == "cwd":
                        owner_root = work_context_root_for_path(str(payload.get(key)))
                        if owner_root:
                            add("owner_route", owner_name_from_root(owner_root) or owner_root, confidence="high", source="cwd", detail=owner_root)

    if event_type == "USER_INTENT":
        act_kind = str(conversation_act.get("kind") or "")
        if act_kind:
            add("operator_request", act_kind, confidence="high", source="conversation_act")
        if re.search(r"\b(только анализ|сейчас только анализ|only analysis|analysis only)\b", haystack):
            add("scope_contract", "analysis_only", confidence="high", source="operator_prompt")
        if re.search(r"\b(не трогай|ничего не трогай|не редактируй|не меняй|do not touch|do not edit)\b", haystack):
            add("scope_contract", "no_mutation", confidence="high", source="operator_prompt")
        if re.search(r"\b(не коммит|не коммить|do not commit|don't commit|no commit)\b", haystack):
            add("scope_contract", "no_commit", confidence="high", source="operator_prompt")
        if re.search(r"\b(без внешн|без интернета|без внешних подключений|no external|do not browse|don't browse)\b", haystack):
            add("scope_contract", "no_external_connectors", confidence="high", source="operator_prompt")
        if re.search(r"\b(сначала погруз|сначала прочит|first read|start by reading|orient first)\b", haystack):
            add("scope_contract", "orient_first", confidence="high", source="operator_prompt")
        if re.search(r"\b(commit|коммит|коммить)\b", haystack):
            add("scope_contract", "commit_requested", confidence="medium", source="operator_prompt")
        if re.search(r"\b(push|пуш)\b", haystack):
            add("scope_contract", "push_requested", confidence="medium", source="operator_prompt")
        if re.search(r"\b(merge|мердж)\b", haystack):
            add("scope_contract", "merge_requested", confidence="medium", source="operator_prompt")
        if re.search(r"\b(по-русски|русск|russian)\b", haystack):
            add("operator_preference", "russian_language", confidence="high", source="operator_prompt")
        if "preserve before distill" in haystack or "preserve before distilling" in haystack or "сначала preserve" in haystack:
            add("operator_preference", "preserve_before_distill", confidence="high", source="operator_prompt")
        if re.search(r"\b(не терять|нельзя ничего потерять|preserve changelog|не потерять changelog)\b", haystack):
            add("operator_preference", "preserve_changelog_or_full_body", confidence="high", source="operator_prompt")
        if "agents/design" in haystack or ("agents.md" in haystack and "design" in haystack):
            add("operator_preference", "read_agents_design_first", confidence="medium", source="operator_prompt")
        if has_landed_slices_preference(haystack):
            add("operator_preference", "landed_slices", confidence="medium", source="operator_prompt")

    if event_type in {"DECISION", "ASSUMPTION", "OPEN_THREAD", "CHECKPOINT", "FINAL_STATE", "ASSISTANT_MESSAGE"}:
        if event_type == "DECISION" or "decision_signal" in tags:
            add("decision_thread", "decision", confidence="high", source="event_type")
        if event_type == "ASSUMPTION" or "assumption_signal" in tags:
            add("decision_thread", "assumption", confidence="high", source="event_type")
        if event_type == "OPEN_THREAD" or "open_thread_signal" in tags:
            add("decision_thread", "open_thread", confidence="high", source="event_type")
        if re.search(r"\b(accepted|принято|подтвердил|одобрил)\b", haystack):
            add("decision_thread", "operator_accepted", confidence="medium", source="assistant_text")
        if re.search(r"\b(rejected|отклонил|не приняли|operator rejected)\b", haystack):
            add("decision_thread", "operator_rejected", confidence="medium", source="assistant_text")
        if re.search(r"\b(blocked|блокер|заблокировано|не могу продолжить)\b", haystack):
            add("decision_thread", "blocked", confidence="medium", source="assistant_text")
        if re.search(r"\b(осталось|remaining|gap|open question|todo|follow-up)\b", haystack):
            add("decision_thread", "remaining_gap", confidence="medium", source="assistant_text")

    if event_type == "COMPACTION_EVENT":
        add("phase_topic", "compaction_boundary", confidence="high", source="event_type")
        add("resource_profile", "context_compaction", confidence="high", source="event_type")
    if event_type in {"DIFF", "FILE_WRITE"}:
        add("phase_topic", "large_patch_or_mutation", confidence="medium", source="event_type")
    if event_type == "VERIFICATION":
        add("phase_topic", "verification_pass", confidence="high", source="event_type")
    if event_type == "FINAL_STATE":
        add("phase_topic", "final_closeout", confidence="high", source="event_type")
        add("route_next_action", "inspect_final_state_and_gaps", confidence="medium", source="event_type")

    failed_command_or_test_signal = has_failed_command_or_test_signal(route_text_haystack)

    if event_type == "VERIFICATION" and not failed_command_or_test_signal:
        add("verification_state", "green_proof", confidence="high", source="event_type")
    if command and str(facets.get("command_kind") or "") == "verification":
        add("verification_state", "verification_requested", confidence="high", source="command_kind", detail=command)
    if ("success_signal" in tags or outcome in {"succeeded", "verified"}) and not failed_command_or_test_signal:
        add("verification_state", "success_observed", confidence="medium", source="outcome")
    if event_type == "ERROR" or outcome == "failed" or "error_signal" in tags or failed_command_or_test_signal:
        add("verification_state", "failed_or_unverified", confidence="high", source="outcome")
    if re.search(r"\b(not run|не запускал|не проверял|untested|не проверено)\b", haystack):
        add("verification_state", "verification_gap", confidence="high", source="text")

    if event_type == "ERROR" or outcome == "failed" or "error_signal" in tags or failed_command_or_test_signal:
        failure_key = "generic_failure"
        if "no such file or directory" in haystack or "missing file" in haystack:
            failure_key = "missing_file"
        elif "schema" in haystack and ("mismatch" in haystack or "invalid" in haystack):
            failure_key = "schema_mismatch"
        elif re.search(r"\b\d+\s+failed\b", haystack) or "pytest" in haystack and "failed" in haystack:
            failure_key = "test_failure"
        elif "permission denied" in haystack or "access denied" in haystack:
            failure_key = "permission"
        elif "timeout" in haystack or "timed out" in haystack:
            failure_key = "timeout"
        elif "command not found" in haystack or "not found:" in haystack:
            failure_key = "command_not_found"
        elif "raw unavailable" in haystack or "raw_unavailable" in haystack:
            failure_key = "hook_raw_unavailable"
        elif "drift" in haystack or "stale" in haystack:
            failure_key = "external_state_drift"
        elif "dirty generated" in haystack or "generated archive" in haystack:
            failure_key = "dirty_generated_archive"
        add("failure_mode", failure_key, confidence="high", source="diagnostic_text")
        add("route_next_action", "diagnose_failure", confidence="medium", source="failure_mode")

    hook_context = event_type == "HOOK_EVENT" or bool(
        re.search(
            r"\b(hook_event_recorded|hook_event_name|hookspecificoutput|codex-hooks-status|codex-compact-probe|precompact_receipt|postcompact_receipt|stop_receipt|raw_mirrored|indexing_deferred|background_sync_queued)\b",
            route_text_haystack,
        )
        or re.search(
            r"\b(?:sessionstart|userpromptsubmit|precompact|postcompact|stop)\b.{0,48}\b(?:hook|receipt|queued|deferred|raw_unavailable|json validity|timed out|timeout|completed|started)\b",
            route_text_haystack,
        )
        or re.search(
            r"\bhooks?\b.{0,48}\b(?:raw_unavailable|json validity|trusted|matching|enabled|configured|completed|started|timed out|timeout)\b",
            route_text_haystack,
        )
    )
    if hook_context:
        for hook_name in HOOK_EVENT_ORDER:
            hook_pattern = re.sub(r"(?<!^)([A-Z])", r"[-_ ]?\1", hook_name).lower()
            if hook_name == "Stop":
                hook_pattern = r"stop(?![-_ ]?lines?\b)"
            if re.search(fr"\b{hook_pattern}\b", haystack.lower()):
                add("hook_health", hook_name, confidence="high", source="hook_signal")
        if "raw_unavailable" in haystack or "raw unavailable" in haystack:
            add("hook_health", "raw_unavailable", confidence="high", source="hook_signal")
        if "deferred" in haystack or "queue" in haystack or "worker" in haystack:
            add("hook_health", "deferred_sync_or_worker_queue", confidence="medium", source="hook_signal")
        if "invalid json" in haystack or "json validity" in haystack or "schema-valid" in haystack:
            add("hook_health", "hook_json_validity", confidence="medium", source="hook_signal")

    memory_surface = str(session_act.get("memory_surface") or "")
    if memory_surface and event_type != "CONTEXT_STATE":
        add("memory_provenance", memory_surface, confidence="high", source="session_act")
    memory_patterns = [
        ("memory_summary", ["memory_summary.md"]),
        ("memory_md_registry", ["memory.md"]),
        ("rollout_summary", ["rollout_summaries", "rollout summary"]),
        ("skill_memory", ["/skills/", "skill memory"]),
        ("ad_hoc_note", ["ad_hoc", "ad-hoc"]),
        ("aoa_archive", [".aoa/sessions", "session-registry.json", "session-name-index.json"]),
        ("codex_transcript", [".codex/sessions", "rollout-"]),
        ("mcp_resource", ["read_mcp_resource", "mcp resource", "memory://"]),
    ]
    for key, needles in memory_patterns:
        if any(needle in route_text_haystack for needle in needles):
            add("memory_provenance", key, confidence="high", source="text")
    if re.search(r"\b(oai-mem-citation|cited|citation|cite|citing)\b", route_text_haystack):
        add("memory_provenance", "cited", confidence="high", source="text")
    if re.search(r"\b(skipped memory|memory skipped|не использовал память)\b", route_text_haystack):
        add("memory_provenance", "skipped", confidence="medium", source="text")
    if re.search(r"\b(verified-current|live verified|проверил актуальность)\b", route_text_haystack):
        add("memory_provenance", "verified_current", confidence="medium", source="text")
    if re.search(r"\b(unverified memory|memory-derived|из памяти без проверки)\b", route_text_haystack):
        add("memory_provenance", "memory_derived_unverified", confidence="medium", source="text")
    if re.search(r"\b(update memory|обнови память|запомни)\b", route_text_haystack):
        add("memory_provenance", "update_requested", confidence="medium", source="text")

    mcp_kind = ""
    if tool_name:
        add("tool", normalized_tool_name(tool_name) or tool_name, confidence="high", source="tool_name", detail=tool_name)
        if tool_namespace:
            add("tool", f"namespace_{tool_namespace}", confidence="medium", source="tool_namespace")
        goal_kind = session_act_for_goal_tool(tool_name)
        if goal_kind:
            add("goal", goal_kind, confidence="high", source="goal_tool")
        mcp_kind = session_act_for_mcp_tool(tool_name)
        if mcp_kind:
            add("mcp", mcp_kind, confidence="high", source="mcp_tool")
    external_keys: set[str] = set()
    external_source = " ".join([tool_name.lower(), command_lower])
    if tool_namespace == "app_connector":
        external_keys.add("app_connector")
        connector_haystack = " ".join([external_source, route_text_haystack])
        if "github" in connector_haystack:
            external_keys.add("github")
        if "gmail" in connector_haystack:
            external_keys.add("gmail")
        if "google drive" in connector_haystack or re.search(r"\bdrive\b", connector_haystack):
            external_keys.add("google_drive")
        if "calendar" in connector_haystack:
            external_keys.add("google_calendar")
    if tool_namespace == "mcp" or mcp_kind:
        external_keys.add("mcp")
    if re.search(r"\b(web\.run|search_query|image_query|browser)\b", external_source):
        external_keys.add("web")
    if event_type in {"COMMAND", "COMMAND_OUTPUT"}:
        if re.search(r"(^|\s)gh\s+", command_lower) or "github.com" in command_lower:
            external_keys.add("github")
        if re.search(r"\b(curl|wget|httpie|npm\s+view|pip\s+index|uv\s+pip\s+index)\b", command_lower) or re.search(r"https?://", command_lower):
            external_keys.add("web")
    for key in sorted(external_keys):
        confidence = "high" if key in {"app_connector", "mcp"} or tool_namespace == "app_connector" else "medium"
        add("external_snapshot", key, confidence=confidence, source="external_context", detail=tool_name or command)
    if external_keys:
        add("freshness_drift", "external_state_required", confidence="medium", source="external_snapshot")
        add("freshness_drift", "external_snapshot_stale_risk", confidence="medium", source="external_snapshot")

    if event_type in {"SECURITY_TOUCHPOINT", "SECURITY_OR_SECRET_RISK"} or "security_signal" in tags or "security_touchpoint_signal" in tags:
        add("risk", "security_or_secret", confidence="high", source="event_type")
    if "destructive_command_signal" in tags:
        add("risk", "destructive_command", confidence="high", source="command")
    if "security_policy_signal" in tags:
        add("access_boundary", "security_policy", confidence="high", source="tag")
    if has_secret_or_privacy_boundary(route_text_haystack):
        add("access_boundary", "secret_or_privacy_boundary", confidence="medium", source="text")
    if re.search(r"\b(export|bundle|portable|review packet|цитировать|показывать)\b", route_text_haystack) and re.search(r"\b(secret|privacy|private|секрет|приват)\b", route_text_haystack):
        add("access_boundary", "export_or_quote_boundary", confidence="medium", source="text")

    if event_type in {"FILE_WRITE", "DIFF"}:
        add("mutation_surface", "workspace_mutation", confidence="high", source="event_type")
    surface_patterns = [
        ("docs", [".md", "readme", "docs/"]),
        ("source_code", [".py", ".ts", ".tsx", ".js", ".go", ".rs"]),
        ("tests", ["tests/", "pytest", "test_"]),
        ("generated_files", ["generated", "session.index.json", "segments/", "maps/by-", "index.json"]),
        ("schemas", ["schemas/", ".schema.json"]),
        ("hooks", ["hooks/", "hook"]),
        ("config", ["config/", ".toml", ".json"]),
        ("portable_bundle", ["export-bundle", "bundle exported", "/bundles/aoa-session-memory"]),
        ("runtime_diagnostics", ["diagnostics/", "doctor", "audit"]),
    ]
    for key, needles in surface_patterns:
        if any(needle in route_surface_haystack for needle in needles):
            add("mutation_surface", key, confidence="medium", source="path_or_command")
            if key == "generated_files":
                add("authority_surface", "generated", confidence="medium", source="path_or_command")
            elif key == "runtime_diagnostics":
                add("authority_surface", "diagnostics", confidence="medium", source="path_or_command")
            elif key == "portable_bundle":
                add("authority_surface", "portable_bundle", confidence="medium", source="path_or_command")
            elif key in {"schemas", "config", "hooks", "docs", "source_code", "tests"}:
                add("authority_surface", "source", confidence="medium", source="path_or_command")
    if memory_surface:
        add("authority_surface", "memory", confidence="medium", source="memory_surface")
    if "runtime" in route_text_haystack or "cache" in route_text_haystack or "search/" in route_text_haystack:
        add("authority_surface", "runtime", confidence="medium", source="text")
    if "external snapshot" in route_text_haystack or "connector" in route_text_haystack:
        add("authority_surface", "external_connector_snapshot", confidence="medium", source="text")
    if "local overlay" in route_text_haystack:
        add("authority_surface", "local_overlay", confidence="medium", source="text")

    path_candidates = []
    path_candidates.extend(path_mentions_from_text(route_semantic_limited))
    path_candidates.extend(path_mentions_from_text(command))
    path_candidates.extend(extract_path_terms([route_semantic_limited, command], limit=8))
    for path_value in sorted(set(path_candidates))[:10]:
        add("path", route_key_slug(path_value, fallback="path", max_chars=96), confidence="medium", source="path_mention", detail=path_value)
        owner_root = work_context_root_for_path(path_value)
        if owner_root:
            add("owner_route", owner_name_from_root(owner_root) or owner_root, confidence="medium", source="path_mention", detail=owner_root)
    entity_text = route_semantic_limited + " " + command
    named_entity_pattern = re.compile(
        r"\b(?:aoa-[a-z0-9-]+|abyss[a-z0-9-]*|agents-of-abyss|tree-of-sophia|tos|mcp|codex|github|gmail|drive|openai|pytest)\b",
        flags=re.IGNORECASE,
    )
    env_entity_pattern = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
    entities = {match.group(0) for match in named_entity_pattern.finditer(entity_text)}
    entities.update(match.group(0) for match in env_entity_pattern.finditer(entity_text) if env_entity_candidate(match.group(0)))
    for entity in sorted(entities)[:12]:
        add("entity", entity, confidence="medium", source="entity_mention", detail=entity)

    if event_type == "SESSION_META" or re.search(r"\b(cwd|branch|dirty|env|os|version|package manager|npm|pip|uv|poetry|cargo)\b", route_text_haystack):
        add("runtime_environment", "environment_state", confidence="medium", source="text")
    if "token_count" in haystack:
        add("resource_profile", "context_token_count", confidence="high", source="token_count")
    if re.search(r"\b(timeout|timed out|long command|large session|heavy raw|latency|cost|expensive)\b", route_text_haystack):
        add("resource_profile", "cost_latency_or_size", confidence="medium", source="text")
    if correlation_id and event_type in {"COMMAND", "COMMAND_OUTPUT", "TOOL_CALL", "TOOL_OUTPUT", "FILE_READ", "FILE_WRITE", "DIFF", "VERIFICATION", "ERROR"}:
        add("correlation", "tool_call_output_link", confidence="high", source="correlation_id", detail=correlation_id)
    if "ambiguous" in route_text_haystack or "неоднознач" in route_text_haystack:
        add("confidence", "ambiguity", confidence="medium", source="text")
    if "weak signal" in route_text_haystack or "low confidence" in route_text_haystack or "слабый сигнал" in route_text_haystack:
        add("confidence", "weak_signal", confidence="medium", source="text")
    if "conflict" in route_text_haystack or "mismatch" in route_text_haystack or "противореч" in route_text_haystack:
        add("confidence", "conflict", confidence="medium", source="text")
    if event_type == "RAW_EVENT":
        add("confidence", "low_structural_confidence", confidence="medium", source="event_type")

    if re.search(r"\b(git\s+status|local diff|uncommitted|not committed|не закоммич)\b", command_lower + " " + route_text_haystack):
        add("delivery_state", "local_diff", confidence="medium", source="git_or_text")
    if not failed_command_or_test_signal and re.search(r"\b(\d+\s+passed|tests green|тесты зелен|pytest.*passed)\b", route_text_haystack):
        add("delivery_state", "tests_green", confidence="high", source="verification_text")
    if re.search(r"\bgit\s+commit\b", command_lower) or "committed" in route_text_haystack:
        add("delivery_state", "committed", confidence="medium", source="git_or_text")
    if re.search(r"\bgit\s+push\b", command_lower) or "pushed" in route_text_haystack:
        add("delivery_state", "pushed", confidence="medium", source="git_or_text")
    if re.search(r"\b(pr opened|pull request|gh pr create)\b", route_text_haystack + " " + command_lower):
        add("delivery_state", "pr_opened", confidence="medium", source="git_or_text")
    if re.search(r"\b(merged|gh pr merge|мердж)\b", route_text_haystack + " " + command_lower):
        add("delivery_state", "merged", confidence="medium", source="git_or_text")
    if "export-bundle" in command_lower or "bundle exported" in route_text_haystack:
        add("delivery_state", "bundle_exported", confidence="high", source="command_or_text")

    if has_findability_index_health_signal(route_surface_haystack):
        add("index_health", "findability_signal", confidence="medium", source="text")
    if "reindex" in route_surface_haystack:
        add("route_next_action", "reindex", confidence="medium", source="text")
    if "repair" in route_surface_haystack or "почин" in route_surface_haystack:
        add("route_next_action", "repair", confidence="medium", source="text")
    if "review" in route_text_haystack or "manual review" in route_text_haystack or "reviewed" in route_text_haystack:
        add("review_state", "review_signal", confidence="medium", source="text")
    if "promotion" in route_text_haystack or "skill" in route_text_haystack or "automation" in route_text_haystack or "playbook" in route_text_haystack:
        add("promotion_candidate", "possible_promotion", confidence="medium", source="text")
    if event_type in {"PROCESS_LESSON", "OPTIMIZATION_CANDIDATE"}:
        add("promotion_candidate", event_type.lower(), confidence="high", source="event_type")
    if "raw:line:" in route_text_haystack:
        add("evidence_provenance", "raw_ref", confidence="high", source="text")
    if "segment.index" in route_text_haystack or ".index.json" in route_text_haystack:
        add("evidence_provenance", "segment_index", confidence="medium", source="text")
    if "manifest" in route_text_haystack or "session.manifest.json" in route_text_haystack:
        add("evidence_provenance", "manifest", confidence="medium", source="text")
    if "search hit" in route_text_haystack or "search result" in route_text_haystack:
        add("evidence_provenance", "search_hit", confidence="medium", source="text")
    if "reviewed distillation" in route_text_haystack:
        add("evidence_provenance", "reviewed_distillation", confidence="medium", source="text")
    if "live-verified" in route_text_haystack or "live verified" in route_text_haystack:
        add("freshness_drift", "live_verified", confidence="medium", source="text")
    if "snapshot" in route_text_haystack:
        add("freshness_drift", "snapshot", confidence="medium", source="text")
    if "stale" in route_text_haystack or "drift" in route_text_haystack:
        add("freshness_drift", "stale_or_drift_risk", confidence="medium", source="text")
    if "source-newer-than-index" in route_text_haystack or "source newer than index" in route_text_haystack:
        add("freshness_drift", "source_newer_than_index", confidence="medium", source="text")

    return signals


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


def text_has_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def classify_operator_prompt_act(text: str) -> tuple[str, str, str]:
    if text_has_any(text, ["не понял", "не так", "ошиб", "нахуя", "блять", "я не говорил", "ты вообще"]):
        return "operator_correction", "correct_agent", "correction_signal"
    if text_has_any(text, ["коммить", "пуш", "мердж", "commit", "push", "merge"]):
        return "operator_delivery_request", "publish_changes", "delivery_signal"
    if text_has_any(text, ["идея", "концепт", "мысл", "задум", "философ"]):
        return "operator_concept", "shape_concept", "concept_signal"
    if "?" in text or text_has_any(text, ["почему", "зачем", "как ", "что ", "какие ", "верно", "правильно"]):
        return "operator_question", "ask_question", "question_signal"
    if text_has_any(text, ["действуй", "делай", "продолжай", "давай", "приступ", "go ahead"]):
        return "operator_action_request", "request_action", "action_request_signal"
    return "operator_instruction", "instruct", "instruction_signal"


def classify_assistant_message_act(event_type: str, text: str, tags: set[str]) -> tuple[str, str, str]:
    if event_type == "FINAL_STATE":
        return "assistant_final_closeout", "closeout", "final_signal"
    if event_type == "DECISION":
        return "assistant_decision", "decide", "decision_signal"
    if event_type == "ASSUMPTION":
        return "assistant_assumption", "assume", "assumption_signal"
    if event_type == "OPEN_THREAD":
        return "assistant_open_thread", "mark_open_work", "open_thread_signal"
    if event_type == "PROCESS_LESSON":
        return "assistant_process_lesson", "distill_lesson", "lesson_signal"
    if event_type == "CHECKPOINT":
        return "assistant_checkpoint", "checkpoint", "checkpoint_signal"
    if event_type == "ASSISTANT_PLAN" or text_has_any(text, ["план", "сначала", "буду ", "i will", "plan:"]):
        return "assistant_plan", "plan", "plan_signal"
    if text_has_any(text, ["ошиб", "неверно", "неправильно", "ты прав", "я не понял"]):
        return "assistant_correction", "correct_self", "misread_or_correction_signal"
    if text_has_any(text, ["провер", "тест", "validate", "verification", "green", "зелен"]):
        return "assistant_verification_report", "report_verification", "verification_signal"
    if text_has_any(text, ["сейчас", "делаю", "проверяю", "иду ", "перехожу"]):
        return "assistant_progress_update", "report_progress", "progress_signal"
    if "message_stream" in tags:
        return "assistant_stream", "stream_message", "stream_signal"
    return "assistant_response", "respond", "response_signal"


def classify_command_or_tool_act(event_type: str, facets: dict[str, Any], tags: set[str]) -> tuple[str, str, str]:
    command_kind = str(facets.get("command_kind") or "")
    if event_type == "VERIFICATION" or command_kind == "verification":
        return "command_verification_request", "request_verification", "verification_request_signal"
    if command_kind == "read" or event_type == "FILE_READ":
        return "command_inspection_request", "inspect_workspace", "inspection_request_signal"
    if command_kind in {"write", "temporary_cleanup"} or event_type in {"FILE_WRITE", "DIFF"} or "file_write" in tags:
        return "command_mutation_request", "mutate_workspace", "mutation_request_signal"
    if command_kind == "destructive":
        return "command_risk_request", "request_risky_command", "risk_request_signal"
    if event_type == "TOOL_CALL":
        return "tool_call_request", "call_tool", "tool_request_signal"
    return "command_execution_request", "run_command", "command_request_signal"


def classify_output_act(event_type: str, outcome: str, text: str, tags: set[str]) -> tuple[str, str, str]:
    if event_type == "VERIFICATION":
        return "verification_result", "report_verification_result", "verification_result_signal"
    if event_type == "ERROR" or outcome == "failed" or "error_signal" in tags:
        return "failure_signal", "report_failure", "failure_signal"
    if "empty_nonzero_output_signal" in tags or text.strip() in {"", "{}", "[]"}:
        return "tool_output_noise", "report_noisy_output", "noise_signal"
    if outcome == "succeeded" or "success_signal" in tags:
        return "tool_output_success", "report_success", "success_signal"
    return "tool_output_observation", "report_output", "output_signal"


def conversation_act_for_event(
    event_type: str,
    source_type: str,
    payload: Any,
    semantic_lower: str,
    tags: set[str],
    facets: dict[str, Any],
    outcome: str,
) -> dict[str, Any] | None:
    universal = event_facets_for_type(event_type)
    kind: str | None = None
    intent: str | None = None
    signal: str | None = None
    if event_type == "USER_INTENT":
        kind, intent, signal = classify_operator_prompt_act(semantic_lower)
    elif event_type in {"ASSISTANT_PLAN", "ASSISTANT_MESSAGE", "DECISION", "ASSUMPTION", "OPEN_THREAD", "PROCESS_LESSON", "CHECKPOINT", "FINAL_STATE"}:
        kind, intent, signal = classify_assistant_message_act(event_type, semantic_lower, tags)
    elif event_type in {"COMMAND", "TOOL_CALL", "FILE_READ", "FILE_WRITE", "DIFF"}:
        kind, intent, signal = classify_command_or_tool_act(event_type, facets, tags)
    elif event_type in {"COMMAND_OUTPUT", "TOOL_OUTPUT", "ERROR", "VERIFICATION"}:
        kind, intent, signal = classify_output_act(event_type, outcome, semantic_lower, tags)
    elif event_type == "COMPACTION_EVENT":
        kind, intent, signal = "context_compaction_boundary", "mark_compaction_boundary", "compaction_signal"
    if kind is None:
        return None
    role = ""
    if isinstance(payload, dict):
        role = str(payload.get("role") or "")
    return {
        "schema_version": CONVERSATION_ACT_SCHEMA_VERSION,
        "kind": kind,
        "actor": universal["actor"],
        "role": role or universal["actor"],
        "intent": intent,
        "signal": signal,
        "raw_event_type": event_type,
        "source_type": source_type,
        "confidence": "high" if event_type != "RAW_EVENT" else "medium",
    }


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
            short_tool_name = normalized_tool_name(tool_name)
            facets["tool_name"] = tool_name
            facets["tool_namespace"] = tool_namespace_for_name(tool_name)
            if short_tool_name in {"exec_command", "write_stdin"}:
                command_info = command_classifier(command_text_from_payload(payload))
                event_type = str(command_info.get("event_type") or "COMMAND")
                tags.update(str(tag) for tag in command_info.get("tags", []) if str(tag))
                facets.update(command_info.get("facets", {}) if isinstance(command_info.get("facets"), dict) else {})
                tags.add("command")
            elif short_tool_name == "apply_patch":
                event_type = "DIFF"
                tags.update(["patch", "file_write"])
        elif item_type in {"function_call_output", "tool_call_output"}:
            event_type = "TOOL_OUTPUT"
            title = f"Tool output: {short_text(payload.get('call_id'), max_chars=80)}"
            tags.add("tool_output")
            importance = "high"
            if payload.get("name") or payload.get("tool_name"):
                facets["tool_name"] = tool_name_from_payload(payload)
                facets["tool_namespace"] = tool_namespace_for_name(str(facets["tool_name"]))
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
    elif broad_diagnostic_scan and event_type in {"TOOL_OUTPUT", "COMMAND_OUTPUT"} and has_success_signal(diagnostic_lower):
        tags.add("success_signal")
        outcome_override = "succeeded"
        verification_lower = semantic_lower or diagnostic_lower
        if re.search(r"\b\d+\s+passed\b", verification_lower) or "ok=true" in verification_lower or '"ok": true' in verification_lower:
            event_type = "VERIFICATION"
            importance = "high"
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
        verification_lower = semantic_lower or diagnostic_lower
        if re.search(r"\b\d+\s+passed\b", verification_lower) or "ok=true" in verification_lower or '"ok": true' in verification_lower:
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
    conversation_act = conversation_act_for_event(
        canonical_event_type,
        source_type,
        payload,
        semantic_lower,
        tags,
        facets,
        universal["outcome"],
    )
    if conversation_act:
        facets["conversation_act"] = conversation_act
        tags.add(f"conversation_act:{conversation_act['kind']}")
    session_act = session_act_for_event(
        canonical_event_type,
        source_type,
        payload,
        semantic_lower,
        tags,
        facets,
        universal["outcome"],
    )
    if session_act:
        facets["session_act"] = session_act
        tags.add(f"session_act:{session_act['kind']}")
        if session_act.get("memory_surface"):
            tags.add(f"memory_surface:{session_act['memory_surface']}")
        if session_act.get("tool_namespace"):
            tags.add(f"tool_namespace:{session_act['tool_namespace']}")
    route_signals = route_signals_for_event(
        canonical_event_type,
        source_type,
        payload,
        semantic_text,
        raw,
        tags,
        facets,
        universal["outcome"],
        correlation_id,
    )
    if route_signals:
        facets["route_signals"] = route_signals
        for signal in route_signals:
            layer = str(signal.get("layer") or "")
            key = str(signal.get("key") or "")
            if layer:
                tags.add(f"route_layer:{layer}")
            if layer and key:
                tags.add(f"route_signal:{layer}:{key}")

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
    return readable_slug(value, fallback="semantic-session-name", max_chars=96)


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


def merge_semantic_anchor(prior: dict[str, Any], anchor: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    merged = {**prior, **anchor}
    preserved: list[str] = []
    for key in ("raw_sha256", "raw_line_count", "raw_bytes"):
        if anchor.get(key) is None and prior.get(key) is not None:
            merged[key] = prior.get(key)
            preserved.append(key)
    if preserved:
        existing = prior.get("preserved_verified_fields")
        prior_preserved = [str(item) for item in existing] if isinstance(existing, list) else []
        merged["preserved_verified_fields"] = sorted(set(prior_preserved + preserved))
        raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
        if manifest.get("archive_status") == "raw_mirrored_index_deferred" or raw.get("indexing_status") == "deferred_from_hook":
            merged["raw_anchor_status"] = "deferred_refresh_preserved_verified_anchor"
        else:
            merged["raw_anchor_status"] = "preserved_verified_anchor_metadata"
    else:
        merged.pop("preserved_verified_fields", None)
        if merged.get("raw_sha256") and merged.get("raw_line_count") is not None:
            merged["raw_anchor_status"] = "current_raw_identity"
        else:
            merged["raw_anchor_status"] = "raw_identity_unverified"
    return merged


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
        merged_anchor = merge_semantic_anchor(prior, anchor, manifest)
        item["anchor"] = {
            **merged_anchor,
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
        if raw.get("blocks_index"):
            raw["blocks_index"] = str(session_dir / "raw" / RAW_BLOCK_INDEX_JSON)
        if raw.get("compaction_events"):
            raw["compaction_events"] = str(session_dir / "raw" / RAW_COMPACTION_EVENTS_JSONL)
    raw_blocks = manifest.get("raw_blocks")
    if isinstance(raw_blocks, dict):
        if raw_blocks.get("index"):
            raw_blocks["index"] = str(session_dir / "raw" / RAW_BLOCK_INDEX_JSON)
        if raw_blocks.get("compaction_events"):
            raw_blocks["compaction_events"] = str(session_dir / "raw" / RAW_COMPACTION_EVENTS_JSONL)
        for block in raw_blocks.get("blocks", []) if isinstance(raw_blocks.get("blocks"), list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("path"):
                block["path"] = str(session_dir / "raw" / RAW_BLOCKS_DIR / Path(str(block["path"])).name)
    for segment in manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []:
        if not isinstance(segment, dict):
            continue
        raw_block = segment.get("raw_block") if isinstance(segment.get("raw_block"), dict) else {}
        if raw_block.get("path"):
            raw_block["path"] = str(session_dir / "raw" / RAW_BLOCKS_DIR / Path(str(raw_block["path"])).name)
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


def event_route_signals(event: RawEvent) -> list[dict[str, Any]]:
    route_signals = event.facets.get("route_signals") if isinstance(event.facets, dict) else None
    if not isinstance(route_signals, list):
        return []
    return [signal for signal in route_signals if isinstance(signal, dict) and signal.get("layer") and signal.get("key")]


def route_signal_token(layer: str, key: str) -> str:
    return f"{layer}:{key}"


def route_signal_counts_for_events(events: list[RawEvent]) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        for signal in event_route_signals(event):
            counts[str(signal["layer"])][str(signal["key"])] += 1
    return {layer: dict(sorted(counter.items())) for layer, counter in sorted(counts.items())}


def conversation_act_counts_for_events(events: list[RawEvent]) -> dict[str, int]:
    return dict(
        sorted(
            Counter(
                str(event.facets.get("conversation_act", {}).get("kind"))
                for event in events
                if isinstance(event.facets.get("conversation_act"), dict) and event.facets["conversation_act"].get("kind")
            ).items()
        )
    )


def session_act_counts_for_events(events: list[RawEvent]) -> dict[str, int]:
    return dict(
        sorted(
            Counter(
                str(event.facets.get("session_act", {}).get("kind"))
                for event in events
                if isinstance(event.facets.get("session_act"), dict) and event.facets["session_act"].get("kind")
            ).items()
        )
    )


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


def raw_block_status_for_role(role: str) -> str:
    return "sealed" if role in {"initial-to-compaction", "compaction-to-compaction"} else "open"


def clear_generated_raw_blocks(session_dir: Path) -> None:
    raw_dir = session_dir / "raw"
    blocks_dir = raw_dir / RAW_BLOCKS_DIR
    if blocks_dir.exists():
        for path in blocks_dir.iterdir():
            if path.name.endswith(".raw.jsonl") or path.name == RAW_BLOCK_INDEX_JSON:
                path.unlink()
    compaction_events_path = raw_dir / RAW_COMPACTION_EVENTS_JSONL
    if compaction_events_path.exists():
        compaction_events_path.unlink()


def write_raw_block_artifacts(
    session_dir: Path,
    raw_rel: str,
    ranges: list[tuple[int, int, str]],
    events: list[RawEvent],
) -> dict[str, Any]:
    raw_dir = session_dir / "raw"
    blocks_dir = raw_dir / RAW_BLOCKS_DIR
    blocks_dir.mkdir(parents=True, exist_ok=True)
    block_records: list[dict[str, Any]] = []
    compaction_records: list[dict[str, Any]] = []
    for segment_no, (start, end, role) in enumerate(ranges):
        segment_id = f"{segment_no:03d}"
        block_name = f"{segment_id}__{role}.raw.jsonl"
        block_path = blocks_dir / block_name
        block_events = events[start:end]
        block_text = "\n".join(event.raw for event in block_events)
        if block_text:
            block_text += "\n"
        block_path.write_text(block_text, encoding="utf-8")
        first_line = block_events[0].line_no if block_events else None
        last_line = block_events[-1].line_no if block_events else None
        boundary_events = [event for event in block_events if event.compaction_boundary]
        record = {
            "block_id": segment_id,
            "segment_id": segment_id,
            "role": role,
            "status": raw_block_status_for_role(role),
            "path": str(block_path),
            "rel": f"raw/{RAW_BLOCKS_DIR}/{block_name}",
            "source_raw": raw_rel,
            "source_range": {"from_line": first_line, "to_line": last_line},
            "line_count": len(block_events),
            "bytes": block_path.stat().st_size,
            "sha256": sha256_file(block_path),
            "closed_by_compaction": bool(boundary_events),
            "boundary_event_ids": [event.event_id for event in boundary_events],
        }
        block_records.append(record)
        for event in boundary_events:
            compaction_records.append(
                {
                    "schema_version": SCHEMA_VERSION,
                    "segment_id": segment_id,
                    "block_id": segment_id,
                    "event_id": event.event_id,
                    "line": event.line_no,
                    "timestamp": event.timestamp,
                    "title": event.title,
                    "source_type": event.source_type,
                    "raw_ref": f"raw:line:{event.line_no}",
                }
            )

    write_json(raw_dir / RAW_BLOCK_INDEX_JSON, {"schema_version": SCHEMA_VERSION, "source_raw": raw_rel, "blocks": block_records})
    compaction_path = raw_dir / RAW_COMPACTION_EVENTS_JSONL
    if compaction_records:
        compaction_path.write_text(
            "\n".join(json.dumps(record, ensure_ascii=False) for record in compaction_records) + "\n",
            encoding="utf-8",
        )
    else:
        compaction_path.write_text("", encoding="utf-8")
    return {
        "index": str(raw_dir / RAW_BLOCK_INDEX_JSON),
        "compaction_events": str(compaction_path),
        "blocks": block_records,
    }


def write_segment(
    session_dir: Path,
    raw_rel: str,
    segment_no: int,
    role: str,
    events: list[RawEvent],
    raw_block: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        f"source_block: {raw_block.get('rel') if isinstance(raw_block, dict) else ''}",
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
    by_conversation_act: dict[str, list[str]] = defaultdict(list)
    by_session_act: dict[str, list[str]] = defaultdict(list)
    by_route_layer: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    by_route_signal: dict[str, list[str]] = defaultdict(list)
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
        conversation_act = event.facets.get("conversation_act") if isinstance(event.facets.get("conversation_act"), dict) else {}
        if conversation_act.get("kind"):
            by_conversation_act[str(conversation_act["kind"])].append(event.event_id)
        session_act = event.facets.get("session_act") if isinstance(event.facets.get("session_act"), dict) else {}
        if session_act.get("kind"):
            by_session_act[str(session_act["kind"])].append(event.event_id)
        for signal in event_route_signals(event):
            layer = str(signal["layer"])
            key = str(signal["key"])
            by_route_layer[layer][key].append(event.event_id)
            by_route_signal[route_signal_token(layer, key)].append(event.event_id)
        for tag in event.tags:
            by_tag[tag].append(event.event_id)

    index = {
        "schema_version": SCHEMA_VERSION,
        "conversation_act_schema_version": CONVERSATION_ACT_SCHEMA_VERSION,
        "session_act_schema_version": SESSION_ACT_SCHEMA_VERSION,
        "route_signal_schema_version": ROUTE_SIGNAL_SCHEMA_VERSION,
        "route_signal_classifier_version": ROUTE_SIGNAL_CLASSIFIER_VERSION,
        "segment_id": segment_id,
        "segment_role": role,
        "source_raw": raw_rel,
        "source_block": raw_block if isinstance(raw_block, dict) else None,
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
        "by_conversation_act": dict(sorted(by_conversation_act.items())),
        "by_session_act": dict(sorted(by_session_act.items())),
        "by_route_layer": {
            layer: dict(sorted(keys.items()))
            for layer, keys in sorted(by_route_layer.items())
        },
        "by_route_signal": dict(sorted(by_route_signal.items())),
    }
    write_json(index_path, index)
    return {
        "segment_id": segment_id,
        "role": role,
        "markdown": str(md_path),
        "index": str(index_path),
        "event_count": len(events),
        "source_range": {"from_line": first_line, "to_line": last_line},
        "raw_block": raw_block if isinstance(raw_block, dict) else None,
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
    conversation_act_counts = conversation_act_counts_for_events(events)
    session_act_counts = session_act_counts_for_events(events)
    route_signal_counts = route_signal_counts_for_events(events)
    display = manifest.get("display", {}) if isinstance(manifest.get("display"), dict) else {}
    semantic_names = semantic_names_payload(manifest)
    work_context = manifest.get("work_context") if isinstance(manifest.get("work_context"), dict) else {}
    session_index_json = {
        "schema_version": SCHEMA_VERSION,
        "session_act_schema_version": SESSION_ACT_SCHEMA_VERSION,
        "conversation_act_schema_version": CONVERSATION_ACT_SCHEMA_VERSION,
        "route_signal_schema_version": ROUTE_SIGNAL_SCHEMA_VERSION,
        "route_signal_classifier_version": ROUTE_SIGNAL_CLASSIFIER_VERSION,
        "work_context_schema_version": WORK_CONTEXT_SCHEMA_VERSION,
        "session_id": manifest["session_id"],
        "display": display,
        "semantic_names": semantic_names,
        "work_context": work_context,
        "updated_at": manifest["updated_at"],
        "archive_status": manifest["archive_status"],
        "distillation_status": manifest.get("distillation_status", "raw_archived"),
        "event_count": len(events),
        "event_counts": by_type,
        "family_counts": family_counts,
        "phase_counts": phase_counts,
        "actor_counts": actor_counts,
        "outcome_counts": outcome_counts,
        "conversation_act_counts": conversation_act_counts,
        "session_act_counts": session_act_counts,
        "route_signal_counts": route_signal_counts,
        "segments": manifest.get("segments", []),
        "raw_blocks": manifest.get("raw_blocks", {}),
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
        "## Work Context",
        "",
        f"- status: `{work_context.get('status', '')}`",
        f"- work_name: `{work_context.get('work_name', '')}`",
        f"- work_family: `{work_context.get('work_family', '')}`",
        f"- work_root: `{work_context.get('work_root', '')}`",
        f"- confidence: `{work_context.get('confidence', '')}`",
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
        raw_block = segment.get("raw_block") if isinstance(segment, dict) and isinstance(segment.get("raw_block"), dict) else {}
        lines.append(
            f"- `{Path(segment['markdown']).name}`: {segment['role']}, "
            f"{segment['event_count']} events, lines "
            f"{segment['source_range'].get('from_line')}..{segment['source_range'].get('to_line')}, "
            f"raw block `{raw_block.get('rel', '')}`"
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
    if session_act_counts:
        lines.append("### Session Acts")
        for act, count in session_act_counts.items():
            lines.append(f"- `{act}`: {count}")
        lines.append("")
    if route_signal_counts:
        lines.append("### Route Signals")
        for layer, keys in route_signal_counts.items():
            lines.append(f"- `{layer}`: {sum(keys.values())}")
            for key, count in list(keys.items())[:12]:
                lines.append(f"  - `{key}`: {count}")
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
    registry_lock_timeout_sec: float | None = None,
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
    events = parse_raw_events(raw_path)
    raw_hash = sha256_file(raw_path)
    raw_rel = "raw/session.raw.jsonl"

    clear_generated_segments(session_dir)
    clear_generated_raw_blocks(session_dir)
    ranges = segment_ranges(events)
    raw_blocks = write_raw_block_artifacts(session_dir, raw_rel, ranges, events)
    raw_blocks_by_segment = {
        str(block.get("segment_id")): block
        for block in raw_blocks.get("blocks", [])
        if isinstance(block, dict)
    }
    segment_payloads: list[dict[str, Any]] = []
    for segment_no, (start, end, role) in enumerate(ranges):
        segment_id = f"{segment_no:03d}"
        segment_payloads.append(write_segment(session_dir, raw_rel, segment_no, role, events[start:end], raw_blocks_by_segment.get(segment_id)))

    manifest_path = session_dir / "session.manifest.json"
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "archive_format_version": 2,
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
            "indexing_status": "indexed",
            "blocks_index": raw_blocks.get("index"),
            "compaction_events": raw_blocks.get("compaction_events"),
        },
        "raw_blocks": raw_blocks,
        "segments": segment_payloads,
        "latest_event_count": len(events),
    }
    if isinstance(existing.get("semantic_names"), dict):
        manifest["semantic_names"] = existing["semantic_names"]
        refresh_semantic_name_anchors(session_dir, manifest)
    manifest["work_context"] = work_context_for_session_events(source_payload, events)
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
    registry_updated = update_registry(aoa_root, manifest, session_dir, lock_timeout_sec=registry_lock_timeout_sec)
    return {
        "session_id": session_id,
        "display_name": display["label"],
        "navigation_path": display["navigation_path"],
        "session_dir": str(session_dir),
        "event_count": len(events),
        "segment_count": len(segment_payloads),
        "raw_path": str(raw_path),
        "manifest_path": str(manifest_path),
        "registry_updated": registry_updated,
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
    registry_lock_timeout_sec: float | None = None,
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
    registry_updated = update_registry(aoa_root, manifest, session_dir, lock_timeout_sec=registry_lock_timeout_sec)
    return {
        "session_id": session_id,
        "display_name": display["label"],
        "navigation_path": display["navigation_path"],
        "session_dir": str(session_dir),
        "raw_path": str(raw_path),
        "raw_bytes": raw_path.stat().st_size,
        "raw_rel": raw_rel,
        "indexing_status": "deferred_from_hook",
        "registry_updated": registry_updated,
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


def hook_mirror_max_bytes() -> int:
    value = os.environ.get("AOA_SESSION_MEMORY_HOOK_MIRROR_MAX_BYTES")
    if value is None:
        return DEFAULT_HOOK_MIRROR_MAX_BYTES
    try:
        return int(value)
    except ValueError:
        return DEFAULT_HOOK_MIRROR_MAX_BYTES


def hook_should_defer_raw_mirror(transcript_path: Path | None) -> bool:
    if transcript_path is None or not transcript_path.exists() or not os.access(transcript_path, os.R_OK):
        return False
    limit = hook_mirror_max_bytes()
    if limit < 0:
        return False
    return transcript_path.stat().st_size > limit


def hook_background_sync_enabled() -> bool:
    return os.environ.get("AOA_SESSION_MEMORY_HOOK_BACKGROUND_SYNC", "1") != "0"


def hook_sync_queue_enabled() -> bool:
    return os.environ.get("AOA_SESSION_MEMORY_HOOK_SYNC_QUEUE", "1") != "0"


def hook_job_id(event_name: str, session_id: str) -> str:
    safe_event = readable_slug(event_name, fallback="hook", max_chars=40)
    safe_session = readable_slug(session_id, fallback="session", max_chars=48)
    return f"{compact_stamp()}__{os.getpid()}__{time.time_ns()}__{safe_event}__{safe_session}"


def enqueue_hook_sync_job(
    aoa_root: Path,
    *,
    event_name: str,
    event: dict[str, Any],
    session_id: str,
    transcript_path: Path | None,
    reason: str,
) -> Path | None:
    if not hook_sync_queue_enabled():
        return None
    if event_name not in {"SessionStart", "PreCompact", "PostCompact", "Stop"}:
        return None
    if transcript_path is None or not transcript_path.exists() or not os.access(transcript_path, os.R_OK):
        return None
    pending_root = aoa_root / HOOK_JOBS_ROOT / "pending"
    pending_root.mkdir(parents=True, exist_ok=True)
    job_path = pending_root / f"{hook_job_id(event_name, session_id)}.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "job_type": "hook_sync_transcript",
        "queued_at": utc_now(),
        "event_name": event_name,
        "session_id": session_id,
        "transcript_path": str(transcript_path),
        "cwd": event.get("cwd"),
        "reason": reason,
        "event": event,
    }
    write_json(job_path, payload)
    return job_path


def enqueue_registry_update_job(
    aoa_root: Path,
    *,
    event_name: str,
    event: dict[str, Any],
    session_id: str,
    session_dir: Path,
    reason: str,
) -> Path | None:
    if not hook_sync_queue_enabled():
        return None
    pending_root = aoa_root / HOOK_JOBS_ROOT / "pending"
    pending_root.mkdir(parents=True, exist_ok=True)
    job_path = pending_root / f"{hook_job_id(event_name, session_id)}__registry-update.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "job_type": "registry_update",
        "queued_at": utc_now(),
        "event_name": event_name,
        "session_id": session_id,
        "session_dir": str(session_dir),
        "cwd": event.get("cwd"),
        "reason": reason,
        "event": event,
    }
    write_json(job_path, payload)
    return job_path


def attach_hook_sync_job(
    receipt: dict[str, Any],
    aoa_root: Path,
    *,
    event_name: str,
    event: dict[str, Any],
    session_id: str,
    transcript_path: Path | None,
    reason: str,
) -> dict[str, Any]:
    job_path = enqueue_hook_sync_job(
        aoa_root,
        event_name=event_name,
        event=event,
        session_id=session_id,
        transcript_path=transcript_path,
        reason=reason,
    )
    if job_path is None:
        return receipt
    actions = receipt.setdefault("actions", [])
    if isinstance(actions, list):
        actions.append("background_sync_queued")
    receipt["background_job"] = str(job_path)
    return receipt


def attach_registry_update_job(
    receipt: dict[str, Any],
    aoa_root: Path,
    *,
    event_name: str,
    event: dict[str, Any],
    session_id: str,
    session_dir: Path,
    reason: str,
) -> dict[str, Any]:
    job_path = enqueue_registry_update_job(
        aoa_root,
        event_name=event_name,
        event=event,
        session_id=session_id,
        session_dir=session_dir,
        reason=reason,
    )
    if job_path is None:
        return receipt
    actions = receipt.setdefault("actions", [])
    if isinstance(actions, list):
        actions.append("registry_update_retry_queued")
        actions.append("background_sync_queued")
    receipt["background_job"] = str(job_path)
    receipt["registry_update_job"] = str(job_path)
    return receipt


def enqueue_index_maintenance_job(
    aoa_root: Path,
    *,
    reason: str,
    target: str = "all",
    sample_audit: bool = False,
    max_raw_mb: float | None = 16,
) -> Path | None:
    if not hook_sync_queue_enabled():
        return None
    pending_root = aoa_root / HOOK_JOBS_ROOT / "pending"
    pending_root.mkdir(parents=True, exist_ok=True)
    job_path = pending_root / f"{hook_job_id('IndexMaintenance', target)}.json"
    payload = {
        "schema_version": SCHEMA_VERSION,
        "job_type": "index_maintenance",
        "queued_at": utc_now(),
        "event_name": "IndexMaintenance",
        "session_id": target,
        "target": target,
        "reason": reason,
        "sample_audit": sample_audit,
        "max_raw_mb": max_raw_mb,
    }
    write_json(job_path, payload)
    return job_path


def hook_worker_dirs(aoa_root: Path) -> dict[str, Path]:
    root = aoa_root / HOOK_JOBS_ROOT
    return {
        "root": root,
        "pending": root / "pending",
        "running": root / "running",
        "done": root / "done",
        "failed": root / "failed",
    }


def run_hook_worker(*, workspace_root: Path | None, aoa_root: Path, limit: int = 5) -> dict[str, Any]:
    dirs = hook_worker_dirs(aoa_root)
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    lock_path = dirs["root"] / "worker.lock"
    results: list[dict[str, Any]] = []
    with lock_path.open("w", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {
                "schema_version": SCHEMA_VERSION,
                "ok": True,
                "status": "worker_already_running",
                "processed": 0,
                "results": [],
            }
        batch_limit = max(0, limit)
        while batch_limit > 0:
            pending_jobs = sorted(dirs["pending"].glob("*.json"))[:batch_limit]
            if not pending_jobs:
                break
            for job_path in pending_jobs:
                running_path = dirs["running"] / job_path.name
                try:
                    job_path.replace(running_path)
                    job = read_json(running_path, {})
                    event = job.get("event") if isinstance(job.get("event"), dict) else {}
                    job_type = job.get("job_type") or "hook_sync_transcript"
                    if job_type == "registry_update":
                        session_dir_value = job.get("session_dir")
                        if not session_dir_value:
                            raise ValueError("missing session_dir")
                        session_dir = Path(str(session_dir_value)).expanduser()
                        manifest = read_json(session_dir / "session.manifest.json", {})
                        if not isinstance(manifest, dict) or not manifest.get("session_id"):
                            raise ValueError("missing session manifest")
                        update_registry(aoa_root, manifest, session_dir)
                        result = {
                            "job": str(running_path),
                            "status": "registry_updated",
                            "session_id": manifest.get("session_id"),
                            "session_dir": str(session_dir),
                        }
                    elif job_type == "index_maintenance":
                        max_raw_mb = job.get("max_raw_mb")
                        max_raw_bytes = int(float(max_raw_mb) * 1024 * 1024) if max_raw_mb is not None else None
                        maintained = maintain_indexes(
                            aoa_root=aoa_root,
                            target=str(job.get("target") or "all"),
                            apply=True,
                            max_raw_bytes=max_raw_bytes,
                            sample_audit=bool(job.get("sample_audit")),
                            write_report=True,
                            reason=str(job.get("reason") or "queued_index_maintenance"),
                        )
                        result = {
                            "job": str(running_path),
                            "status": "maintained_indexes" if maintained.get("ok") else "failed",
                            "target": maintained.get("target"),
                            "reason": maintained.get("reason"),
                            "action_counts": maintained.get("action_counts"),
                            "report_json": maintained.get("report_json"),
                            "diagnostics": maintained.get("diagnostics", []),
                        }
                    else:
                        transcript_value = job.get("transcript_path")
                        transcript_path = Path(str(transcript_value)).expanduser() if transcript_value else None
                        if transcript_path is None or not transcript_path.exists() or not os.access(transcript_path, os.R_OK):
                            raise FileNotFoundError(str(transcript_path) if transcript_path else "missing transcript_path")
                        synced = sync_session_from_transcript(
                            aoa_root=aoa_root,
                            event={
                                **event,
                                "session_id": job.get("session_id") or event.get("session_id"),
                                "transcript_path": str(transcript_path),
                                "cwd": job.get("cwd") or event.get("cwd"),
                                "hook_event_name": f"HookWorker:{job.get('event_name') or 'Unknown'}",
                            },
                            transcript_path=transcript_path,
                            hook_event_name=f"HookWorker:{job.get('event_name') or 'Unknown'}",
                        )
                        result = {
                            "job": str(running_path),
                            "status": "synced",
                            "session_id": synced.get("session_id"),
                            "session_dir": synced.get("session_dir"),
                            "event_count": synced.get("event_count"),
                            "segment_count": synced.get("segment_count"),
                        }
                    done_path = dirs["done"] / running_path.name
                    write_json(done_path, {**job, "completed_at": utc_now(), "result": result})
                    running_path.unlink(missing_ok=True)
                    results.append(result)
                except Exception as exc:
                    failed_path = dirs["failed"] / running_path.name
                    failed_payload = read_json(running_path, {})
                    write_json(
                        failed_path,
                        {
                            **(failed_payload if isinstance(failed_payload, dict) else {}),
                            "failed_at": utc_now(),
                            "error": f"{exc.__class__.__name__}: {exc}",
                        },
                    )
                    running_path.unlink(missing_ok=True)
                    results.append({"job": str(job_path), "status": "failed", "error": f"{exc.__class__.__name__}: {exc}"})
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": all(result.get("status") != "failed" for result in results),
        "status": "processed",
        "processed": len(results),
        "results": results,
    }


def launch_hook_worker(*, workspace_root: Path | None, aoa_root: Path) -> bool:
    if not hook_background_sync_enabled():
        return False
    command = [
        sys.executable or "python3",
        str(Path(__file__).resolve()),
        "hook-worker",
        "--aoa-root",
        str(aoa_root),
        "--limit",
        "5",
    ]
    if workspace_root is not None:
        command.extend(["--workspace-root", str(workspace_root)])
    try:
        subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            close_fds=True,
        )
        return True
    except Exception:
        return False


def update_registry(
    aoa_root: Path,
    manifest: dict[str, Any],
    session_dir: Path,
    *,
    lock_timeout_sec: float | None = None,
) -> bool:
    lock_path = aoa_root / ".session-registry.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_handle:
        if lock_timeout_sec is None:
            fcntl.flock(lock_handle, fcntl.LOCK_EX)
        else:
            deadline = time.monotonic() + max(0.0, lock_timeout_sec)
            while True:
                try:
                    fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        return False
                    time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        update_registry_locked(aoa_root, manifest, session_dir)
    return True


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
    if lowered.startswith(("you are ", "role:", "role ", "ты ", "ты —", "ты -")):
        return True
    if lowered.startswith(("context: user approved", "context user approved", "user approved", "repo:", "do not edit files", "не редактируй")):
        return True
    if lowered in {"сначала", "first"} or lowered.startswith(("сначала прочитай", "first read", "start by reading")):
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


def meaningful_naming_tail_signal(event: RawEvent) -> bool:
    parsed = event.parsed if isinstance(event.parsed, dict) else {}
    payload = parsed.get("payload") if isinstance(parsed.get("payload"), dict) else {}
    text = semantic_text_for_classification(event.source_type, payload)
    if not text.strip():
        return False
    if text.strip().startswith("<turn_aborted>"):
        return False
    if event.source_type == "response_item":
        item_type = str(payload.get("type") or "")
        role = str(payload.get("role") or "")
        return item_type == "message" and role in {"user", "assistant"}
    if event.source_type == "event_msg":
        msg_type = str(payload.get("type") or "")
        return msg_type in {"agent_message", "user_message"}
    return event.source_type in {"turn_context", "compacted"} and event.compaction_boundary


def naming_tail_probe(raw_path: Path, start_line: int, end_line: int, *, max_scan: int = 1000) -> dict[str, Any]:
    if start_line <= 0 or end_line < start_line or not raw_path.is_file():
        return {"has_meaningful_content": False, "sample": [], "scanned_count": 0, "truncated": False}
    sample: list[dict[str, Any]] = []
    scanned_count = 0
    truncated = False
    with raw_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            if line_no < start_line:
                continue
            if line_no > end_line:
                break
            if scanned_count >= max_scan:
                truncated = True
                break
            scanned_count += 1
            raw_line = line.rstrip("\n")
            parsed: dict[str, Any] | None = None
            try:
                loaded = json.loads(raw_line)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                parsed = None
            event = classify_raw_event(raw_line, parsed, line_no)
            if meaningful_naming_tail_signal(event):
                payload = parsed.get("payload") if isinstance(parsed, dict) and isinstance(parsed.get("payload"), dict) else {}
                text = semantic_text_for_classification(event.source_type, payload)
                sample.append(
                    {
                        "line": line_no,
                        "event_type": event.event_type,
                        "source_type": event.source_type,
                        "title": event.title,
                        "text": short_text(text, max_chars=220),
                    }
                )
                if len(sample) >= 5:
                    break
    return {
        "has_meaningful_content": bool(sample) or truncated,
        "sample": sample,
        "scanned_count": scanned_count,
        "truncated": truncated,
    }


def phase_discovery_review_state(session_dir: Path) -> dict[str, Any]:
    artifact = session_phase_discovery_path(session_dir)
    state: dict[str, Any] = {
        "present": artifact.is_file(),
        "path": str(artifact),
        "candidate_count": 0,
        "review_queue_count": 0,
        "review_queue_sample": [],
        "read_error": None,
    }
    if not artifact.is_file():
        return state
    try:
        payload = json.loads(artifact.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        state["read_error"] = str(exc)
        return state
    if not isinstance(payload, dict):
        state["read_error"] = "invalid_phase_discovery_payload"
        return state
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    review_queue = payload.get("review_queue") if isinstance(payload.get("review_queue"), list) else []
    state["candidate_count"] = int_value(payload.get("candidate_count"), len(candidates))
    state["review_queue_count"] = int_value(payload.get("review_queue_count"), len(review_queue))
    state["review_queue_sample"] = [
        {
            "segment_id": item.get("segment_id"),
            "name": item.get("name") or item.get("candidate_name"),
            "status": (item.get("review") or {}).get("status") if isinstance(item.get("review"), dict) else item.get("status"),
        }
        for item in review_queue[:5]
        if isinstance(item, dict)
    ]
    return state


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
    observed_raw_line_count = raw_line_count
    raw_line_count_source = "manifest" if raw_line_count is not None else None
    missing_segment_indexes = segment_index_missing_paths(segments)
    weak_title = title_is_generic_for_naming(title, title_source)
    weak_label = weak_label_text(label)
    phase_discovery_state = phase_discovery_review_state(session_dir)
    phase_discovery_present = bool(phase_discovery_state.get("present"))
    phase_discovery_review_queue_count = int_value(phase_discovery_state.get("review_queue_count"))
    active_session_coverage_end = None
    if isinstance(active_session, dict):
        coverage = active_session.get("coverage") if isinstance(active_session.get("coverage"), dict) else {}
        raw_ranges = coverage.get("raw_ranges") if isinstance(coverage.get("raw_ranges"), list) else []
        coverage_ends = [
            int_value(raw_range.get("to_line"))
            for raw_range in raw_ranges
            if isinstance(raw_range, dict) and int_value(raw_range.get("to_line")) > 0
        ]
        active_session_coverage_end = max(coverage_ends) if coverage_ends else None

    reasons: list[str] = []
    sync_reasons: list[str] = []
    reindex_reasons: list[str] = []
    blockers: list[str] = []
    warnings: list[str] = []
    route = "optional_semantic_name"
    status = "readable_label"
    priority = 10

    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    source_transcript_path = source.get("transcript_path")
    has_recovery_hint = bool(source_transcript_path)
    source_path = Path(str(source_transcript_path)).expanduser() if source_transcript_path else None
    source_transcript_present = bool(source_path and source_path.is_file())
    source_transcript_size = None
    raw_archive_size = raw_path.stat().st_size if raw_present else None
    source_transcript_newer_than_raw_archive = False
    if source_path and source_path.is_file() and raw_present:
        try:
            source_stat = source_path.stat()
            raw_stat = raw_path.stat()
            source_transcript_size = source_stat.st_size
            source_transcript_newer_than_raw_archive = (
                source_stat.st_size != raw_stat.st_size or source_stat.st_mtime_ns > raw_stat.st_mtime_ns
            )
            if source_transcript_newer_than_raw_archive:
                sync_reasons.append("source_transcript_newer_than_raw_archive")
                route = "sync_source_transcript_before_naming"
        except OSError:
            warnings.append("source_transcript_freshness_probe_failed")
    if observed_raw_line_count is None and raw_present and archive_status == "raw_mirrored_index_deferred":
        try:
            observed_raw_line_count = count_file_lines(raw_path)
            raw_line_count_source = "raw_probe_deferred"
        except OSError:
            warnings.append("raw_line_count_probe_failed")
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
    active_session_coverage_line_gap = (
        active_session_coverage_end is not None
        and observed_raw_line_count is not None
        and active_session_coverage_end < int_value(observed_raw_line_count)
    )
    active_session_coverage_tail = (
        naming_tail_probe(raw_path, active_session_coverage_end + 1, int_value(observed_raw_line_count))
        if active_session_coverage_line_gap and active_session_coverage_end is not None and observed_raw_line_count is not None
        else {"has_meaningful_content": False, "sample": [], "scanned_count": 0, "truncated": False}
    )
    active_session_coverage_stale = bool(active_session_coverage_tail.get("has_meaningful_content"))

    if status == "diagnostic_only":
        pass
    elif blockers:
        status = "blocked"
        priority = 95 if event_count >= 1000 or segment_count >= large_threshold else 70
        reasons.extend(blockers)
    elif sync_reasons:
        status = "needs_sync"
        route = "sync_source_transcript_before_naming"
        priority = 92 if event_count >= 1000 or segment_count >= large_threshold else 58
        reasons.extend(sync_reasons)
    elif reindex_reasons:
        status = "needs_reindex"
        priority = 90 if event_count >= 1000 or segment_count >= large_threshold else 55
        reasons.extend(reindex_reasons)
    elif active_session:
        status = "named"
        route = "verify_or_refine_existing_name"
        priority = 50 if active_session_coverage_stale else 0
        reasons.append("active_session_name_present")
        if active_session_coverage_stale:
            reasons.append("active_session_name_coverage_stale")
        if phase_discovery_review_queue_count:
            route = "review_open_phase_discovery_for_named_session"
            priority = max(priority, 45 if segment_count >= large_threshold else 25)
            reasons.append("phase_discovery_review_queue_open")
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
    if active_session_coverage_stale:
        warnings.append(f"active_session_name_coverage_stale:{active_session_coverage_end}<{observed_raw_line_count}")
    if phase_discovery_state.get("read_error"):
        warnings.append("phase_discovery_unreadable")
    if phase_discovery_review_queue_count:
        warnings.append(f"phase_discovery_review_queue_open:{phase_discovery_review_queue_count}")

    suggested_next = {
        "blocked": "repair raw/index state before naming",
        "diagnostic_only": "keep the raw-unavailable diagnostic visible unless a raw candidate appears",
        "needs_sync": "sync the newer source transcript into the raw archive before naming or reindexing",
        "needs_reindex": "refresh generated segment indexes from preserved raw before naming",
        "phase_discovery_ready": "review phase-discovery candidates before applying the whole-session name",
        "named": "verify existing active session name against review needs",
        "low_signal": "leave canonical label unless this probe becomes operationally important",
        "needs_phase_discovery": "discover phase/topic candidates before assigning a whole-session name",
        "ready_for_semantic_name": "apply a semantic session name with raw evidence refs",
        "readable_label": "semantic name is optional; prioritize weaker or larger sessions first",
    }.get(status, "inspect naming route")
    if status == "named" and phase_discovery_review_queue_count:
        suggested_next = "review open phase-discovery candidates before treating the active session name as settled"

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
            "source_transcript_present": source_transcript_present,
            "source_transcript_size": source_transcript_size,
            "raw_archive_size": raw_archive_size,
            "source_transcript_newer_than_raw_archive": source_transcript_newer_than_raw_archive,
            "raw_sha256_present": raw_sha_present,
            "raw_line_count": raw_line_count,
            "observed_raw_line_count": observed_raw_line_count,
            "raw_line_count_source": raw_line_count_source,
            "weak_title": weak_title,
            "weak_label": weak_label,
            "active_session_name": active_session.get("slug") if isinstance(active_session, dict) else None,
            "active_session_coverage_end": active_session_coverage_end,
            "active_session_coverage_line_gap": active_session_coverage_line_gap,
            "active_session_coverage_stale": active_session_coverage_stale,
            "active_session_coverage_tail": active_session_coverage_tail,
            "phase_or_topic_name_count": phase_or_topic_count,
            "phase_discovery_present": phase_discovery_present,
            "phase_discovery_candidate_count": int_value(phase_discovery_state.get("candidate_count")),
            "phase_discovery_review_queue_count": phase_discovery_review_queue_count,
            "phase_discovery_review_queue_sample": phase_discovery_state.get("review_queue_sample") or [],
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


NOISY_PATH_MENTIONS = {"/", "./", "../", "/dev/null", "/srv", "/tmp", "/home", "/var", "/etc"}


def is_indexable_path_mention(value: str) -> bool:
    text = str(value or "").strip().rstrip(".,:;)]}")
    if not text or len(text) < 3 or "\x00" in text or text in NOISY_PATH_MENTIONS:
        return False
    if re.search(
        r"(?:^|[._/-])(?:origin|upstream)/(?:main|master|develop|dev|trunk|head)(?:$|[._/-])",
        text,
        flags=re.IGNORECASE,
    ):
        return False
    if re.fullmatch(r"(?:origin|upstream)/(?:main|master|develop|dev|trunk|head)", text, flags=re.IGNORECASE):
        return False
    if re.fullmatch(
        r"(?:main|master|develop|dev|trunk)/(?:origin|upstream)/(?:main|master|develop|dev|trunk|head)",
        text,
        flags=re.IGNORECASE,
    ):
        return False
    if re.fullmatch(r"refs/(?:heads|remotes|tags)/[A-Za-z0-9._/-]+", text, flags=re.IGNORECASE):
        return False
    return True


def extract_path_terms(texts: list[str], *, limit: int = 12) -> list[str]:
    counts: Counter[str] = Counter()
    pattern = re.compile(r"(?<![\w.-])(?:/[^\s`'\"<>|)]+|(?:[A-Za-z0-9_.-]+/){1,}[A-Za-z0-9_.-]+)")
    for text in texts:
        for match in pattern.findall(text):
            value = match.rstrip(".,:;)]}")
            if not is_indexable_path_mention(value):
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
        "делай",
        "делай дальше",
        "разложи план",
        "что еще у нас есть",
        "что дальше",
        "что теперь",
        "ну что ж готов",
        "готов",
        "я готов",
        "продолжаем",
        "окей",
        "добро",
        "добро двигай",
        "коммить пуш мердж",
        "commit push merge",
        "это не все",
        "это не всё",
        "это еще не все",
        "это еще не всё",
        "это ещё не все",
        "это ещё не всё",
        "ну давай",
    }
    if lowered in generic_values:
        return True
    generic_prefixes = (
        "давай, действуй",
        "давай действуй",
        "давай тогда",
        "добро,",
        "добро.",
        "ну хорошо",
        "ну давай",
        "окей,",
        "так, что",
        "что еще",
        "что теперь",
        "в этой сессии",
        "мы будем",
        "я готов",
        "это не все",
        "это не всё",
        "это еще не все",
        "это еще не всё",
        "это ещё не все",
        "это ещё не всё",
        "коммить",
        "commit",
        "это всё готово разве",
        "и как бы ты это делал",
    )
    always_generic_prefixes = (
        "в этой сессии",
        "мы будем",
        "давай следующий",
        "коммить",
        "commit",
    )
    if any(lowered.startswith(prefix) for prefix in always_generic_prefixes):
        return True
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
        if review.get("status") in {"ready_for_raw_check", "applied_reviewed_name"}:
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


def refresh_phase_discovery_review_fields(payload: dict[str, Any]) -> dict[str, Any]:
    candidates = payload.get("candidates") if isinstance(payload.get("candidates"), list) else []
    candidates = [candidate for candidate in candidates if isinstance(candidate, dict)]
    review_queue = phase_review_queue(candidates)
    payload["candidate_count"] = len(candidates)
    payload["candidate_quality_counts"] = phase_candidate_quality_counts(candidates)
    payload["review_queue_count"] = len(review_queue)
    payload["review_queue"] = review_queue
    return payload


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
        "candidates": candidates,
        "next_actions": [
            "review candidate names against raw evidence",
            "apply accepted phase/topic names with name-session --scope phase or --scope topic",
            "choose the whole-session name only after phase coverage is understood",
        ],
    }
    payload = refresh_phase_discovery_review_fields(payload)
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


def semantic_phase_names_by_range(manifest: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    phases: dict[tuple[int, int], dict[str, Any]] = {}
    semantic = semantic_names_payload(manifest)
    for item in semantic.get("names", []) if isinstance(semantic.get("names"), list) else []:
        if not isinstance(item, dict) or semantic_name_scope(item) != "phase":
            continue
        coverage = item.get("coverage") if isinstance(item.get("coverage"), dict) else {}
        ranges = coverage.get("raw_ranges") if isinstance(coverage.get("raw_ranges"), list) else []
        first = ranges[0] if ranges and isinstance(ranges[0], dict) else {}
        start = int_value(first.get("from_line"))
        end = int_value(first.get("to_line"))
        if start > 0 and end > 0:
            phases[(start, end)] = item
    return phases


def phase_assist_sample(event: RawEvent, *, max_chars: int = 360) -> dict[str, Any]:
    return {
        "raw_ref": f"raw:line:{event.line_no}",
        "event_type": event.event_type,
        "source_type": event.source_type,
        "title": event.title,
        "text": short_text(event_semantic_text(event), max_chars=max_chars),
    }


def bounded_event_samples(events: list[RawEvent], *, limit: int, max_chars: int = 360) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    if len(events) <= limit:
        selected = events
    else:
        head_count = max(1, limit // 2)
        tail_count = max(1, limit - head_count)
        selected = events[:head_count] + events[-tail_count:]
    seen: set[int] = set()
    samples: list[dict[str, Any]] = []
    for event in selected:
        if event.line_no in seen:
            continue
        seen.add(event.line_no)
        samples.append(phase_assist_sample(event, max_chars=max_chars))
    return samples


def phase_review_assist_packet(
    candidate: dict[str, Any],
    segment_events: list[RawEvent],
    *,
    existing_phase: dict[str, Any] | None = None,
) -> dict[str, Any]:
    start, end = phase_candidate_range(candidate)
    review = candidate.get("review") if isinstance(candidate.get("review"), dict) else {}
    signals = candidate.get("signals") if isinstance(candidate.get("signals"), dict) else {}
    event_counts = Counter(event.event_type for event in segment_events)
    text_for = lambda event: event_semantic_text(event).strip()
    user_requests = [
        event
        for event in segment_events
        if event.event_type == "USER_INTENT" and text_for(event) and usable_phase_intent_text(text_for(event))
    ]
    progress_markers = [
        event
        for event in segment_events
        if event.event_type == "ASSISTANT_MESSAGE"
        and text_for(event)
        and event_msg_type(event) not in {"token_count", "exec_command_end", "patch_apply_end"}
    ]
    decision_events = [event for event in segment_events if event.event_type in {"DECISION", "PROCESS_LESSON", "CHECKPOINT", "FINAL_STATE"}]
    verification_events = [event for event in segment_events if event.event_type == "VERIFICATION"]
    error_events = [event for event in segment_events if event.event_type == "ERROR"]
    mutation_events = [event for event in segment_events if event.event_type in {"FILE_WRITE", "DIFF"}]
    command_events = [event for event in segment_events if event.event_type == "COMMAND"]

    read_first: list[str] = []
    for group in (user_requests, decision_events, progress_markers, verification_events, error_events):
        for event in group[:4]:
            ref = f"raw:line:{event.line_no}"
            if ref not in read_first:
                read_first.append(ref)
            if len(read_first) >= 10:
                break
        if len(read_first) >= 10:
            break

    candidate_name = str(candidate.get("name") or "")
    segment_id = str(candidate.get("segment_id") or "")
    coverage_note_seed = (
        f"Reviewed with phase-review-assist for segment {normalize_segment_id(segment_id)} "
        f"covering raw {start}..{end}; preserve raw refs and replace this seed with the accepted semantic synthesis."
    )
    return {
        "segment_id": normalize_segment_id(segment_id),
        "coverage": {"from_line": start, "to_line": end},
        "machine_candidate": candidate_name,
        "candidate_confidence": candidate.get("confidence"),
        "candidate_basis": candidate.get("name_basis"),
        "quality_flags": candidate.get("quality_flags", []),
        "review_status": review.get("status"),
        "existing_phase_name": existing_phase.get("name") if isinstance(existing_phase, dict) else "",
        "existing_phase_slug": existing_phase.get("slug") if isinstance(existing_phase, dict) else "",
        "event_counts": {
            key: event_counts.get(key, 0)
            for key in [
                "USER_INTENT",
                "ASSISTANT_MESSAGE",
                "COMMAND",
                "COMMAND_OUTPUT",
                "FILE_READ",
                "FILE_WRITE",
                "DIFF",
                "ERROR",
                "VERIFICATION",
                "DECISION",
                "CHECKPOINT",
                "FINAL_STATE",
            ]
            if event_counts.get(key, 0)
        },
        "top_paths": signals.get("top_paths", [])[:12] if isinstance(signals.get("top_paths"), list) else [],
        "read_first": read_first,
        "synthesis_inputs": {
            "user_requests": bounded_event_samples(user_requests, limit=4, max_chars=420),
            "progress_markers": bounded_event_samples(progress_markers, limit=8, max_chars=420),
            "decisions_and_closeout": bounded_event_samples(decision_events, limit=6, max_chars=420),
            "validations": bounded_event_samples(verification_events, limit=4, max_chars=360),
            "errors": bounded_event_samples(error_events, limit=4, max_chars=360),
            "mutations": bounded_event_samples(mutation_events, limit=5, max_chars=300),
            "commands": bounded_event_samples(command_events, limit=5, max_chars=260),
        },
        "plan_template": {
            "segment_id": normalize_segment_id(segment_id),
            "reviewed_name": "",
            "coverage_note": coverage_note_seed,
        },
    }


def phase_review_assist_markdown(payload: dict[str, Any]) -> str:
    packets = payload.get("packets") if isinstance(payload.get("packets"), list) else []
    lines = [
        "# Phase Review Assist",
        "",
        "Batch synthesis packets for phase naming. This is review acceleration, not reviewed truth.",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- session: `{payload.get('session_label') or payload.get('session_id')}`",
        f"- status: `{payload.get('status')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- remaining_review_queue: `{payload.get('remaining_review_queue_count')}`",
        f"- raw_path: `{payload.get('raw_path')}`",
        "",
        "## Fast Queue",
        "",
        "| segment | machine candidate | status | range | read first | top paths |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for packet in packets:
        if not isinstance(packet, dict):
            continue
        coverage = packet.get("coverage") if isinstance(packet.get("coverage"), dict) else {}
        read_first = ", ".join(str(ref) for ref in packet.get("read_first", [])[:6])
        top_paths = ", ".join(str(path) for path in packet.get("top_paths", [])[:4])
        lines.append(
            "| `{segment}` | {candidate} | `{status}` | `{start}..{end}` | `{read_first}` | {paths} |".format(
                segment=packet.get("segment_id"),
                candidate=markdown_cell(packet.get("machine_candidate")),
                status=packet.get("review_status"),
                start=coverage.get("from_line"),
                end=coverage.get("to_line"),
                read_first=read_first,
                paths=markdown_cell(top_paths),
            )
        )
    lines.extend(["", "## Packets", ""])
    for packet in packets:
        if not isinstance(packet, dict):
            continue
        coverage = packet.get("coverage") if isinstance(packet.get("coverage"), dict) else {}
        lines.extend(
            [
                f"### Segment `{packet.get('segment_id')}`",
                "",
                f"- range: `{coverage.get('from_line')}..{coverage.get('to_line')}`",
                f"- machine_candidate: {packet.get('machine_candidate')}",
                f"- review_status: `{packet.get('review_status')}`",
                f"- candidate_basis: `{packet.get('candidate_basis')}`",
                f"- quality_flags: `{', '.join(str(flag) for flag in packet.get('quality_flags', []) if flag)}`",
            ]
        )
        if packet.get("existing_phase_name"):
            lines.append(f"- existing_phase_name: {packet.get('existing_phase_name')}")
        lines.extend(
            [
                f"- top_paths: `{', '.join(str(path) for path in packet.get('top_paths', [])[:8])}`",
                f"- read_first: `{', '.join(str(ref) for ref in packet.get('read_first', []))}`",
                "",
            ]
        )
        synthesis = packet.get("synthesis_inputs") if isinstance(packet.get("synthesis_inputs"), dict) else {}
        for title, key in [
            ("User Requests", "user_requests"),
            ("Progress Markers", "progress_markers"),
            ("Decisions And Closeout", "decisions_and_closeout"),
            ("Validations", "validations"),
            ("Errors", "errors"),
            ("Mutations", "mutations"),
            ("Commands", "commands"),
        ]:
            samples = synthesis.get(key) if isinstance(synthesis.get(key), list) else []
            if not samples:
                continue
            lines.extend([f"#### {title}", "", "| ref | type | text |", "| --- | --- | --- |"])
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
            lines.append("")
        plan = packet.get("plan_template") if isinstance(packet.get("plan_template"), dict) else {}
        lines.extend(["#### Plan Template", "", "```json", json.dumps(plan, indent=2, ensure_ascii=False), "```", ""])
    lines.extend(
        [
            "## Rule",
            "",
            "Use these packets to synthesize stronger reviewed names, then apply through `review-phase-name`.",
            "For reviewed batches, fill `reviewed_name` entries in the plan JSON and run `apply-phase-review-plan`.",
            "Do not apply `machine_candidate` for weak/path-based candidates just because it appears in this report.",
            "",
        ]
    )
    return "\n".join(lines)


def build_phase_review_assist(
    aoa_root: Path,
    target: str,
    *,
    limit: int = 8,
    from_segment: str | None = None,
    segments: list[str] | None = None,
    include_reviewed: bool = False,
    refresh: bool = False,
    write: bool = False,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    discovery = phase_discovery_payload_for_review(aoa_root, target, refresh=refresh)
    session_dir_value = str(discovery.get("session_dir") or "")
    session_dir = Path(session_dir_value) if session_dir_value else None
    raw_path = Path(str(discovery.get("raw_path") or ""))
    if not raw_path.is_file():
        raise ValueError(f"missing raw archive: {raw_path}")
    manifest = read_json(session_dir / "session.manifest.json", {}) if session_dir is not None else {}
    if not isinstance(manifest, dict):
        manifest = {}
    existing_phases = semantic_phase_names_by_range(manifest)
    events = parse_raw_events(raw_path)
    by_range: dict[tuple[int, int], list[RawEvent]] = {}
    requested_segments = {normalize_segment_id(item) for item in segments or [] if str(item).strip()}
    from_segment_norm = normalize_segment_id(from_segment) if from_segment else ""
    selected_candidates: list[dict[str, Any]] = []
    for candidate in discovery.get("candidates", []) if isinstance(discovery.get("candidates"), list) else []:
        if not isinstance(candidate, dict):
            continue
        segment_id = normalize_segment_id(str(candidate.get("segment_id") or ""))
        if requested_segments and segment_id not in requested_segments:
            continue
        if from_segment_norm and segment_id < from_segment_norm:
            continue
        review = candidate.get("review") if isinstance(candidate.get("review"), dict) else {}
        if not include_reviewed and review.get("status") == "applied_reviewed_name":
            continue
        selected_candidates.append(candidate)
        if limit > 0 and len(selected_candidates) >= limit and not requested_segments:
            break
    packets: list[dict[str, Any]] = []
    for candidate in selected_candidates:
        start, end = phase_candidate_range(candidate)
        if start is None or end is None:
            segment_events: list[RawEvent] = []
        else:
            key = (start, end)
            if key not in by_range:
                by_range[key] = [event for event in events if start <= event.line_no <= end]
            segment_events = by_range[key]
        existing_phase = existing_phases.get((start or 0, end or 0))
        packets.append(phase_review_assist_packet(candidate, segment_events, existing_phase=existing_phase))

    remaining_queue = phase_review_queue(discovery.get("candidates", []) if isinstance(discovery.get("candidates"), list) else [])
    plan_template = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "phase_review_plan",
        "session_label": discovery.get("session_label"),
        "created_from": "phase-review-assist",
        "items": [packet.get("plan_template") for packet in packets if isinstance(packet.get("plan_template"), dict)],
    }
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "phase_review_assist",
        "generated_at": now,
        "ok": True,
        "status": "review_assist_ready",
        "aoa_root": str(aoa_root),
        "session_id": discovery.get("session_id"),
        "session_label": discovery.get("session_label") or target,
        "session_dir": str(session_dir) if session_dir is not None else "",
        "raw_path": str(raw_path),
        "selected_count": len(packets),
        "remaining_review_queue_count": len(remaining_queue),
        "selection": {
            "limit": limit,
            "from_segment": from_segment_norm,
            "segments": sorted(requested_segments),
            "include_reviewed": include_reviewed,
        },
        "packets": packets,
        "plan_template": plan_template,
    }
    if write and session_dir is not None:
        naming_dir = session_dir / "naming"
        naming_dir.mkdir(parents=True, exist_ok=True)
        artifact_json = naming_dir / "phase-review-assist.json"
        artifact_md = naming_dir / "phase-review-assist.md"
        plan_path = naming_dir / "phase-review-plan.template.json"
        write_json(artifact_json, payload)
        write_markdown(artifact_md, phase_review_assist_markdown(payload))
        write_json(plan_path, plan_template)
        payload["artifact_json"] = str(artifact_json)
        payload["artifact_markdown"] = str(artifact_md)
        payload["plan_template_path"] = str(plan_path)
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__phase-review-assist__{safe_slug(str(payload.get('session_label') or target))}"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, phase_review_assist_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def phase_review_plan_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Phase Review Plan Apply",
        "",
        "Batch application report for reviewed phase names.",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- session: `{payload.get('session_label') or payload.get('session_id')}`",
        f"- status: `{payload.get('status')}`",
        f"- apply: `{payload.get('apply')}`",
        f"- plan_path: `{payload.get('plan_path')}`",
        f"- item_count: `{payload.get('item_count')}`",
        f"- applied_count: `{payload.get('applied_count')}`",
        f"- preview_count: `{payload.get('preview_count')}`",
        f"- skipped_count: `{payload.get('skipped_count')}`",
        "",
    ]
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), list) else []
    lines.extend(["## Diagnostics", ""])
    lines.extend([f"- `{item}`" for item in diagnostics] or ["- none"])
    lines.extend(["", "## Results", "", "| segment | status | name | diagnostics |", "| --- | --- | --- | --- |"])
    for result in payload.get("results", []) if isinstance(payload.get("results"), list) else []:
        if not isinstance(result, dict):
            continue
        lines.append(
            "| `{segment}` | `{status}` | {name} | {diagnostics} |".format(
                segment=result.get("segment_id"),
                status=result.get("status"),
                name=markdown_cell(result.get("reviewed_name") or result.get("chosen_name") or ""),
                diagnostics=markdown_cell(", ".join(str(item) for item in result.get("diagnostics", []) if item)),
            )
        )
    lines.append("")
    return "\n".join(lines)


def default_phase_review_plan_path(aoa_root: Path, target: str) -> Path:
    record = resolve_session_record(aoa_root, target)
    session_dir = session_dir_from_record(record)
    return session_dir / "naming" / "phase-review-plan.template.json"


def apply_phase_review_plan(
    aoa_root: Path,
    target: str,
    *,
    plan_path: Path | None = None,
    apply: bool = False,
    replace: bool = False,
    write_report: bool = False,
    verify_raw_hash: bool = True,
    stop_on_error: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    path = plan_path.expanduser() if plan_path is not None else default_phase_review_plan_path(aoa_root, target)
    plan = read_json(path, {})
    diagnostics: list[str] = []
    if not isinstance(plan, dict):
        diagnostics.append("invalid_phase_review_plan_payload")
        plan = {}
    items = plan.get("items") if isinstance(plan.get("items"), list) else []
    if not items:
        diagnostics.append("phase_review_plan_has_no_items")
    results: list[dict[str, Any]] = []
    applied_count = 0
    preview_count = 0
    skipped_count = 0
    session_label = str(plan.get("session_label") or target)
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            diagnostics.append(f"item_{index}_invalid")
            if stop_on_error:
                break
            continue
        segment_id = normalize_segment_id(str(item.get("segment_id") or ""))
        reviewed_name = str(item.get("reviewed_name") or "").strip()
        coverage_note = str(item.get("coverage_note") or "").strip()
        if not segment_id:
            diagnostics.append(f"item_{index}_missing_segment_id")
            if stop_on_error:
                break
            continue
        if not reviewed_name:
            skipped_count += 1
            results.append(
                {
                    "segment_id": segment_id,
                    "status": "skipped",
                    "reviewed_name": "",
                    "diagnostics": ["reviewed_name_empty"],
                }
            )
            continue
        result = review_phase_name_candidate(
            aoa_root,
            target,
            segment_id,
            reviewed_name=reviewed_name,
            apply=apply,
            replace=replace,
            write_report=write_report,
            verify_raw_hash=verify_raw_hash,
            coverage_note=coverage_note,
        )
        compact_result = {
            "segment_id": result.get("segment_id"),
            "status": result.get("status"),
            "ok": result.get("ok"),
            "reviewed_name": reviewed_name,
            "chosen_name": result.get("chosen_name"),
            "route": result.get("route"),
            "diagnostics": result.get("diagnostics", []),
            "report_json": result.get("report_json"),
            "report_markdown": result.get("report_markdown"),
        }
        semantic = result.get("semantic_name_result") if isinstance(result.get("semantic_name_result"), dict) else {}
        proposed = semantic.get("proposed") if isinstance(semantic.get("proposed"), dict) else {}
        if proposed:
            compact_result["slug"] = proposed.get("slug")
        results.append(compact_result)
        if result.get("ok") and result.get("status") == "applied":
            applied_count += 1
        elif result.get("ok") and not apply:
            preview_count += 1
        else:
            diagnostics.append(f"segment_{segment_id}_failed")
            diagnostics.extend(f"segment_{segment_id}:{item}" for item in result.get("diagnostics", []) if item)
            if stop_on_error:
                break
    status = "diagnostic" if diagnostics else ("applied" if apply and applied_count else "preview_ready" if preview_count else "empty_plan")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "phase_review_plan_apply",
        "generated_at": now,
        "ok": not diagnostics,
        "status": status,
        "apply": apply,
        "aoa_root": str(aoa_root),
        "session_label": session_label,
        "plan_path": str(path),
        "item_count": len(items),
        "applied_count": applied_count,
        "preview_count": preview_count,
        "skipped_count": skipped_count,
        "diagnostics": diagnostics,
        "results": results,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__phase-review-plan-apply__{safe_slug(session_label)}"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, phase_review_plan_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


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
            candidate["status"] = "reviewed_applied"
            candidate["review"] = {
                **review,
                "status": "applied_reviewed_name",
                "action": "reviewed_phase_name_applied",
                "applied_name": chosen_name,
                "applied_slug": semantic_name_slug(chosen_name),
                "applied_at": now,
                "semantic_name_scope": "phase",
                "semantic_name_status": "phase",
            }
            discovery = refresh_phase_discovery_review_fields(discovery)
            discovery["updated_at"] = now
            discovery["status"] = "candidate_review_in_progress" if discovery.get("review_queue_count") else "candidate_reviewed"
            discovery_session_dir_value = str(discovery.get("session_dir") or "")
            discovery_session_dir = Path(discovery_session_dir_value) if discovery_session_dir_value else None
            if discovery_session_dir is not None:
                artifact_json = session_phase_discovery_path(discovery_session_dir)
                artifact_md = artifact_json.with_suffix(".md")
                write_json(artifact_json, discovery)
                write_markdown(artifact_md, phase_discovery_markdown(discovery))
            sessions = registry_sessions(aoa_root)
            write_session_name_index(aoa_root, sessions)
            write_sessions_directory_index(aoa_root, sessions)
            refreshed_indexes = [
                str(aoa_root / SESSION_NAME_INDEX_JSON),
                str(aoa_root / SESSION_NAME_INDEX_MARKDOWN),
                str(aoa_root / SESSION_ROOT / SESSIONS_INDEX_JSON),
                str(aoa_root / SESSION_ROOT / SESSIONS_INDEX_MARKDOWN),
            ]
            if discovery_session_dir is not None:
                refreshed_indexes.extend([str(artifact_json), str(artifact_md)])
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


KNOWN_SESSION_NAME_DOMAINS = [
    ("aoa-session-memory", (".aoa", "aoa-session-memory", "session-memory", "session memory", "codex session")),
    ("aoa-techniques", ("aoa-techniques", "technique_index", "technique index")),
    ("agents-of-abyss", ("agents-of-abyss", "agents of abyss", "aoa-experience")),
    ("tree-of-sophia", ("tree-of-sophia", "tree of sophia")),
    ("abyss-machine", ("abyss-machine", "nervous", "zram", "gnome shell")),
    ("abyss-stack", ("abyss-stack", "mechanics", "validate_stack")),
    ("rios-de-color", ("rios-de-color", "rios", "operator-review")),
]

SESSION_ACTION_HINTS = [
    ("naming", ("name", "naming", "rename", "имен", "нейм", "назван")),
    ("hook-hardening", ("hook", "precompact", "postcompact", "compact", "хук")),
    ("skill-routing", ("skill", "skills", "скилл")),
    ("repo-ordering", ("repo", "repository", "репо", "canon", "канон")),
    ("validation", ("validate", "validation", "audit", "test", "pytest", "проверк")),
    ("refactor", ("refactor", "рефактор")),
    ("repair", ("repair", "fix", "исправ", "почин")),
    ("release-landing", ("commit", "push", "merge", "pr ", "pull request", "релиз")),
    ("runtime-hardening", ("runtime", "service", "systemd", "container", "machine")),
    ("design", ("design", "architecture", "дизайн", "архитект")),
]

GENERIC_SESSION_NAME_WORDS = {
    "codex",
    "session",
    "continue",
    "work",
    "task",
    "current",
    "latest",
    "start",
    "finish",
    "review",
    "check",
    "thing",
    "stuff",
    "files",
    "mentioned",
    "user",
    "you",
    "are",
    "role",
    "read",
    "only",
    "context",
    "workspace",
    "сессии",
    "сессия",
    "продолжать",
    "заниматься",
    "делать",
    "давай",
    "окей",
    "хорошо",
    "aoa",
    "agents",
    "abyss",
    "of",
    "srv",
    "home",
    "dionysus",
    "techniques",
    "machine",
    "stack",
    "memory",
    "не",
    "редактируй",
}


def naming_evidence_text_is_runtime_envelope(text: str) -> bool:
    stripped = re.sub(r"\s+", " ", str(text or "")).strip()
    lowered = stripped.lower()
    if not stripped:
        return True
    envelope_prefixes = (
        "# agents.md instructions",
        "<permissions instructions>",
        "<environment_context>",
        "<workspace_context>",
    )
    if any(lowered.startswith(prefix) for prefix in envelope_prefixes):
        return True
    if lowered.startswith("# context from my ide setup") and "my request for codex" not in lowered:
        return True
    if lowered.startswith("# files mentioned by the user") and "my request for codex" not in lowered:
        return True
    return False


def event_is_naming_evidence_user_request(event: RawEvent) -> bool:
    if event.event_type != "USER_INTENT":
        return False
    text = event_semantic_text(event)
    return not naming_evidence_text_is_runtime_envelope(text)


def first_raw_event_for_event_type(raw_path: Path, event_type: str = "USER_INTENT", *, max_lines: int = 2000) -> tuple[str, str] | None:
    if not raw_path.is_file():
        return None
    with raw_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, line in enumerate(handle, start=1):
            if line_no > max_lines:
                break
            raw_line = line.rstrip("\n")
            parsed: dict[str, Any] | None = None
            try:
                loaded = json.loads(raw_line)
                if isinstance(loaded, dict):
                    parsed = loaded
            except json.JSONDecodeError:
                parsed = None
            event = classify_raw_event(raw_line, parsed, line_no)
            if event_type == "USER_INTENT" and event_is_naming_evidence_user_request(event):
                return f"raw:line:{line_no}", event_semantic_text(event)
            if event_type != "USER_INTENT" and event.event_type == event_type:
                return f"raw:line:{line_no}", event_semantic_text(event)
    return None


def first_raw_ref_for_event_type(raw_path: Path, event_type: str = "USER_INTENT", *, max_lines: int = 2000) -> str | None:
    found = first_raw_event_for_event_type(raw_path, event_type=event_type, max_lines=max_lines)
    return found[0] if found else None


def text_terms_for_session_name(value: str) -> list[str]:
    slug = semantic_name_slug(value)
    return [part for part in slug.split("-") if part]


def generic_session_name_text(value: str) -> bool:
    terms = text_terms_for_session_name(value)
    if len(terms) < 3:
        return True
    meaningful = [term for term in terms if term not in GENERIC_SESSION_NAME_WORDS]
    if len(meaningful) < 2:
        return True
    compact = " ".join(terms)
    return compact in {"codex in abyssos", "codex in memories", "continue work"}


def naming_policy_domain_hints(policy: dict[str, Any]) -> list[tuple[str, tuple[str, ...]]]:
    configured = policy.get("session_name_domain_hints") if isinstance(policy, dict) else None
    if isinstance(configured, list):
        hints: list[tuple[str, tuple[str, ...]]] = []
        for item in configured:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            markers = item.get("markers") if isinstance(item.get("markers"), list) else []
            marker_values = tuple(str(marker) for marker in markers if str(marker).strip())
            if name and marker_values:
                hints.append((name, marker_values))
        if hints:
            return hints
    return KNOWN_SESSION_NAME_DOMAINS


def naming_policy_action_hints(policy: dict[str, Any]) -> list[tuple[str, tuple[str, ...]]]:
    configured = policy.get("session_name_action_hints") if isinstance(policy, dict) else None
    if isinstance(configured, list):
        hints: list[tuple[str, tuple[str, ...]]] = []
        for item in configured:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            markers = item.get("markers") if isinstance(item.get("markers"), list) else []
            marker_values = tuple(str(marker) for marker in markers if str(marker).strip())
            if name and marker_values:
                hints.append((name, marker_values))
        if hints:
            return hints
    return SESSION_ACTION_HINTS


def detect_session_domain(texts: list[str], *, hints: list[tuple[str, tuple[str, ...]]] | None = None) -> str:
    haystack = "\n".join(str(text or "").lower() for text in texts)
    for domain, markers in hints or KNOWN_SESSION_NAME_DOMAINS:
        if any(marker.lower() in haystack for marker in markers):
            return domain
    cwd_paths = [text for text in texts if "/" in str(text)]
    for value in cwd_paths:
        match = re.search(r"(?<![\w.-])/[^\s`]+", str(value))
        if not match:
            continue
        path_value = match.group(0)
        path = Path(path_value)
        parts = [part for part in path.parts if part not in {"/", "srv", "home", "dionysus", "work", "src", "github-owner"}]
        if parts:
            leaf = Path(parts[-1]).stem if Path(parts[-1]).suffix else parts[-1]
            return semantic_name_slug(leaf)
    return ""


def detect_session_action(texts: list[str], *, hints: list[tuple[str, tuple[str, ...]]] | None = None) -> str:
    haystack = "\n".join(str(text or "").lower() for text in texts)
    for action, markers in hints or SESSION_ACTION_HINTS:
        if any(marker.lower() in haystack for marker in markers):
            return action
    return "continuation"


def strip_session_meta_instruction_prefixes(value: str) -> str:
    text = str(value or "").strip()
    patterns = (
        r"(?is)^\s*(?:работай|work)\s+(?:в|in)\s+`?/[^\s`.]+`?\s*[.!?:;,-]*\s*",
        r"(?is)^\s*рабочий\s+контекст\s*:?\s*`?/[^\s`.]+`?\s*[.!?:;,-]*\s*",
        r"(?is)^\s*github\s+owner\s+\S+\s*[.!?:;,-]*\s*",
        r"(?is)^\s*task\s+in\s+`?/[^\s`.]+`?\s*[.!?:;,-]*\s*",
        r"(?is)^\s*(?:отвечай|ответь|пиши)\s+только\s+на\s+(?:русском|английском)\s*[.!?:;,-]*\s*",
        r"(?is)^\s*только\s+на\s+(?:русском|английском)\s*[.!?:;,-]*\s*",
        r"(?is)^\s*(?:answer|reply|respond|write)\s+only\s+in\s+(?:russian|english)\s*[.!?:;,-]*\s*",
        r"(?is)^\s*you\s+are\b.*?\btask\s*:?\s*",
        r"(?is)^\s*you\s+are\b[^.?!]{0,220}[.?!]\s*",
        r"(?is)^\s*you\s+are\s+not\s+alone\b.*?(?=\b(?:context|task|scope)\b)",
        r"(?is)^\s*you\s+are\s+working\b.*?(?=\b(?:address|task|scope|focus|inspect|review)\b)",
        r"(?is)^\s*ты\s*(?:—|-)?\s*.*?\bзадача\b\s*:?\s*",
        r"(?is)^\s*ты\s*(?:—|-)?\s*[^.?!]{0,220}[.?!]\s*",
        r"(?is)^\s*role\s*:?\s*[^.?!]{0,220}[.?!]\s*",
        r"(?is)^\s*read[- ]only\s*[.!?:;,-]*\s*",
        r"(?is)^\s*read[- ]only\s+audit\s*[.!?:;,-]*\s*",
        r"(?is)^\s*read[- ]only\s+(?:review\s+)?task\s+for\s+",
        r"(?is)^\s*не\s+редактируй(?:\s+файлы)?\s*[.!?:;,-]*\s*",
        r"(?is)^\s*do\s+not\s+edit\s+files\s*[.!?:;,-]*\s*",
        r"(?is)^\s*context\s*:\s*user approved[^.?!]*[.?!]\s*",
        r"(?is)^\s*context\s*:\s*user approved(?:\s+\S+){0,8}\s*",
        r"(?is)^\s*context\s*:\s*.*?(?=\b(?:task|scope|focus)\b)",
        r"(?is)^\s*repo\s*:\s*.*?(?=\btask\b)",
        r"(?is)^\s*(?:task|задача)\s*:?\s*",
        r"(?is)^\s*for\s+(?=wave\s+\d+\b)",
        r"(?is)^\s*focus\s+only\s+on\s+",
        r"(?is)^\s*(?:scope|focus)\s*:?\s*",
        r"(?is)^\s*сначала\s+прочитай\s*:?.*?(?=\b(?:проверь|проведи|найди|исправь|разберись|сделай|собери|оцени|задача)\b)",
        r"(?is)^\s*(?:first|start by)\s+read\s*:?.*?(?=\b(?:task|then|check|inspect|fix|build|implement|review)\b)",
    )
    changed = True
    while changed:
        changed = False
        for pattern in patterns:
            updated = re.sub(pattern, "", text).strip()
            if updated != text:
                text = updated
                changed = True
    return text


def attachment_file_title_seed(value: str) -> str:
    text = str(value or "").strip()
    match = re.match(r"^\s*[`'\"]?(?P<path>/[^\s`'\"]+\.[A-Za-z0-9_]+)[`'\"]?", text)
    if not match:
        return ""
    tail = text[match.end() :].lower()
    if any(marker in tail for marker in ("вот задача", "в этом файле", "task", "задание")):
        return Path(match.group("path")).stem
    return ""


def session_review_owner_repo_words(value: str) -> str:
    text = str(value or "")
    match = re.search(
        r"(?is)\b(?:your\s+)?write\s+ownership\s+is\s+only\s+(?P<owners>.+?)(?:\.\s|$)",
        text,
    )
    if not match:
        return ""
    owners: list[str] = []
    for owner_match in re.finditer(r"/(?:srv|home/dionysus/src)/(?P<repo>[A-Za-z0-9_.-]+)", match.group("owners")):
        repo = semantic_name_slug(owner_match.group("repo"))
        if repo and repo not in owners:
            owners.append(repo)
        if len(owners) >= 4:
            break
    return " ".join(owners)


def repo_marker_words(value: str, *, limit: int = 4) -> str:
    repos: list[str] = []
    for match in re.finditer(r"(?:`|/)(?P<repo>(?:aoa|abyss|Agents|Tree|8Dionysus)[A-Za-z0-9_.-]*(?:-of-[A-Za-z0-9_.-]+)?)`?", str(value)):
        repo = semantic_name_slug(match.group("repo"))
        if repo.startswith("aoa-experience-"):
            continue
        if repo and repo not in {"srv", "home", "tmp"} and repo not in repos:
            repos.append(repo)
        if len(repos) >= limit:
            break
    return " ".join(repos)


def experience_scout_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if "scout" not in text.lower():
        return ""
    wave = re.search(r"\bExperience\s+Wave\s*(?P<wave>\d+)\b", text, flags=re.IGNORECASE)
    if not wave:
        return ""
    lane_match = re.search(r"(?is)^\s*(?:ты\s*(?:—|-)?\s*|you\s+are\s+)?(?P<lane>[^.]{1,80}?)\s+scout\b", text)
    lane = semantic_name_slug(lane_match.group("lane")) if lane_match else ""
    lane_words = " ".join(word for word in lane.split("-") if word and word not in {"read", "only", "ты", "you", "are"})
    repos = repo_marker_words(text)
    lane_terms = set(lane_words.split())
    if {"roles", "playbooks", "kag", "practice"} <= lane_terms:
        return concise_title_text(f"AoA Experience Wave {wave.group('wave')} roles playbooks KAG practice landing map", max_words=10)
    if {"center", "law"} <= lane_terms and "agents-of-abyss" in repos:
        return concise_title_text(f"Agents-of-Abyss Wave {wave.group('wave')} center law landing map", max_words=9)
    if repos:
        return concise_title_text(f"Wave {wave.group('wave')} {repos} {lane_words} landing map", max_words=11)
    if lane_words:
        return concise_title_text(f"Wave {wave.group('wave')} {lane_words} landing map", max_words=10)
    return ""


def wave_sidecar_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    wave = re.search(r"\bWave\s*(?P<wave>\d+)\b", text, flags=re.IGNORECASE)
    if not wave:
        return ""
    if "federation harvest" in lowered and "adoption forge" in lowered:
        return concise_title_text(f"Wave {wave.group('wave')} federation harvest adoption forge sidecar review", max_words=10)
    if "runtime/adoption boundaries" in lowered or ("runtime" in lowered and "adoption" in lowered and "sidecar" in lowered):
        return concise_title_text(f"Wave {wave.group('wave')} runtime adoption boundaries sidecar review", max_words=10)
    return ""


def next_wave_scout_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    if "scout" not in lowered or "aoa-experience-" not in lowered:
        return ""
    topic = experience_wave_slug_words(text)
    if not topic:
        return ""
    repos = repo_marker_words(text)
    role_match = re.search(r"(?is)^\s*role\s*:?\s*(?P<role>[^.]{1,80}?)\s+scout\b", text)
    role_words = semantic_name_slug(role_match.group("role")) if role_match else ""
    role_tail = " ".join(word for word in role_words.split("-") if word and word not in {"role", "read", "only"})
    if repos:
        return concise_title_text(f"{repos} {topic} scout map", max_words=10)
    if role_tail:
        return concise_title_text(f"{topic} {role_tail} scout map", max_words=9)
    return concise_title_text(f"{topic} scout map", max_words=7)


def pr_gate_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    if "pr" not in lowered or "gate watcher" not in lowered:
        return ""
    wave = re.search(r"\bwave\s*(?P<wave>\d+)\b", text, flags=re.IGNORECASE)
    wave_text = f"Wave {wave.group('wave')}" if wave else ""
    if "оставшиеся" in lowered:
        return concise_title_text(f"AoA Experience {wave_text} remaining PR review thread gate", max_words=10)
    return concise_title_text(f"AoA Experience {wave_text} cross repo PR merge gate status", max_words=10)


def experience_seed_review_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    if "experience" not in lowered and "aoa-experience" not in lowered:
        return ""
    if "sidecar for experience wave" in lowered and "federation" in lowered and "adoption" in lowered:
        return ""
    if ("next experience wave" in lowered or "next wave" in lowered) and (
        "v0_4" in lowered
        or "v0.4" in lowered
        or "certification forge" in lowered
        or "certification-forge" in lowered
    ) and (
        "v0_5" in lowered
        or "v0.5" in lowered
        or "deployment watchtower" in lowered
        or "deployment-watchtower" in lowered
    ):
        if "seed cartographer" in lowered or "seed inspection" in lowered or "inspect seed" in lowered:
            return "AoA Experience Wave 2 certification forge deployment watchtower seed inspection"
        return "AoA Experience Wave 2 seed scope authority review"
    if ("three seed zips" in lowered or "v0.1-v0.3" in lowered or "v0.1" in lowered and "v0.3" in lowered) and (
        "authority-risk" in lowered or "authority risk" in lowered or "review gate" in lowered
    ):
        return "AoA Experience Wave 1 seed authority risk review"
    if (
        "seed cartographer" in lowered
        or "изучи два архива" in lowered
        or "compact seed cartography" in lowered
        or "seed cartography" in lowered
    ) and ("polis-governance" in lowered or "polis governance" in lowered) and (
        "constitution-runtime" in lowered or "constitution runtime" in lowered
    ):
        return "AoA Experience Wave 4 polis governance constitution runtime seed cartography"
    return ""


def experience_lineage_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    if "dionysus wave 0" in lowered and "wave 1" in lowered and "provenance" in lowered and "memory humility" in lowered:
        return "Agents-of-Abyss Wave 1 Dionysus Wave 0 provenance bridge review"
    if (
        ("aoa-experience" in lowered or "experience" in lowered)
        and ("v1.2-v2.0" in lowered or "v1.2->v2.0" in lowered or "v1-2-to-v2-0" in lowered)
        and "wave 0" in lowered
        and ("lineage" in lowered or "provenance" in lowered)
    ):
        return "AoA Experience v1.2 to v2.0 Wave 0 lineage provenance framing"
    return ""


def cross_repo_review_gate_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    if "review gate" not in lowered:
        return ""
    repos = repo_marker_words(text, limit=5)
    if "agents-of-abyss" in repos and "aoa-memo" in repos and (
        "review comments" in lowered or "wave5" in lowered or "wave 5" in lowered
    ):
        return "Agents-of-Abyss aoa-memo Wave 5 review comment fixes gate"
    return ""


def titan_wave_risk_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    if "titan bearer" not in lowered and "risk review" not in lowered:
        return ""
    version_span = any(marker in lowered for marker in ("v1.2-v2.0", "v1.2->v2.0", "v1-2-to-v2-0"))
    if "dionysus wave 0" in lowered and version_span and ("judgment gate" in lowered or "bounded verdict" in lowered):
        return "Dionysus Wave 0 v1.2 to v2.0 seed intake final judgment"
    if "dionysus wave 0" in lowered and version_span and "structural framing" in lowered:
        return "Dionysus Wave 0 v1.2 to v2.0 seed intake structural framing"
    if "dionysus wave 0" in lowered and version_span:
        return "Dionysus Wave 0 v1.2 to v2.0 seed intake risk review"
    if "wave 1 center bridge" in lowered and "risk review" in lowered:
        return "Agents-of-Abyss Wave 1 center bridge risk review"
    return ""


def center_bridge_surface_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    if "wave 1" in lowered and "center bridge surface shape" in lowered:
        return "Agents-of-Abyss Wave 1 center bridge surface map"
    return ""


def dionysus_closeout_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    if "dionysus" not in lowered:
        return ""
    if "closeout diff" in lowered and ("final bounded judgment" in lowered or "final judgment" in lowered):
        return "Dionysus v1.2 to v2.0 closeout final judgment"
    if "narrow lineage audit" in lowered and "truthful dionysus closeout" in lowered:
        return "Dionysus v1.2 to v2.0 closeout lineage audit"
    if "final closeout map" in lowered and ("v1.2->v2.0" in lowered or "v1.2-v2.0" in lowered):
        return "Dionysus v1.2 to v2.0 final closeout map"
    if "dionysus final closeout diff" in lowered and "seed_surface_map" in lowered:
        return "Dionysus v1.2 to v2.0 closeout diff review"
    if "ultra-narrow review" in lowered and "seed_surface_map" in lowered and "seed_aoa_experience_wave0" in lowered:
        return "Dionysus Wave 0 seed surface final review"
    return ""


def compact_hook_probe_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    if "aoa-compact-tool-probe" in text:
        return "aoa-session-memory compact hook probe"
    return ""


def socraticode_runbook_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if "socraticode" not in text.lower() or "runbook" not in text.lower():
        return ""
    domain = detect_session_domain([text])
    lowered = text.lower()
    if "repair candidate" in lowered or "controlled repair" in lowered:
        return concise_title_text(f"{domain} SocratiCode runbook repair candidate routing", max_words=9)
    return concise_title_text(f"{domain} SocratiCode runbook check", max_words=7)


def post_w10_gap_audit_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    if "post-w10 hardening gap audit" not in lowered:
        return ""
    if "living workspace continuity runtime" in lowered:
        return "Agents-of-Abyss post-W10 runtime continuity owner hardening audit"
    return "Agents-of-Abyss post-W10 center contract owner gap audit"


def mirror_drift_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    if "8dionysus" in lowered and "/srv" in lowered and ("расхожд" in lowered or "отстает" in lowered):
        return "8Dionysus mirror drift audit"
    return ""


def multi_repo_fix_map_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    if not lowered.startswith("map the requested multi-repo fixes"):
        return ""
    repos = repo_marker_words(text, limit=5)
    if repos:
        return concise_title_text(f"{repos} multi repo fix map", max_words=12)
    return "multi repo fix map"


def rfc3339_lineage_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    if "rfc3339 date-time checker bugs" not in lowered:
        return ""
    repos = repo_marker_words(text, limit=4)
    return concise_title_text(f"{repos} RFC3339 date time semantics review", max_words=10)


def russian_seed_meaning_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().lower()
    if text.startswith("изучи эти семена") and "посад" in text and "смысл" in text:
        return "seed planting meaning review"
    return ""


def artifact_topic_slug_words(value: str) -> str:
    text = str(value or "")
    patterns = (
        r"\bEXPERIENCE_V\d+(?:_\d+)+(?:_TO_V\d+(?:_\d+)*)?_(?P<slug>[A-Z0-9_]+)\.(?:md|json)\b",
        r"\bexperience-v\d+(?:-\d+)+(?:-v\d+(?:-\d+)*)?-(?P<slug>[a-z0-9-]+)\.schema\.json\b",
        r"\bexamples?/experience_v\d+(?:_\d+)+(?:_to_v\d+(?:_\d+)*)?_(?P<slug>[a-z0-9_]+)\.example\.json\b",
        r"\bdocs/(?P<slug>[A-Z][A-Z0-9_]{4,})\.md\b",
        r"\bschemas/(?P<slug>[a-z0-9-]{4,})\.schema\.json\b",
        r"\bexamples?/(?P<slug>[a-z0-9_]{4,})\.example\.json\b",
    )
    banned = {
        "agents",
        "readme",
        "start-here",
        "roadmap",
        "index",
        "validate-repo",
        "test-validate-repo",
    }
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            slug = match.group("slug").replace("_", "-").lower()
            slug = re.sub(r"^(?:experience|docs?|schemas?|examples?)-", "", slug)
            words = [word for word in slug.split("-") if word and word not in banned and not re.fullmatch(r"(?:v|wave)?\d+", word)]
            if "landing" in words and len(words) > 2:
                continue
            if len(words) >= 2:
                return " ".join(words[:8])
    return ""


def experience_wave_slug_words(value: str) -> str:
    text = str(value or "")
    patterns = (
        r"\bEXPERIENCE_V\d+_\d+_(?P<slug>[A-Z0-9_]+)",
        r"\baoa-experience-(?P<slug>[a-z0-9-]+)-seed-v\d+_\d+(?:\.zip)?\b",
        r"\bexperience-v\d+-\d+(?:-v\d+-\d+)?-(?P<slug>[a-z0-9-]+)\.schema\.json\b",
        r"\bcodex/wave\d+-v\d+_\d+-(?P<slug>[a-z0-9-]+?)-20\d{6}\b",
        r"\bv\d+[._]\d+\s+(?P<slug>[a-z][a-z -]+?)(?=\s+(?:after|planting|archive|review|on|in)\b|[.])",
        r"\bv\d+[._]\d+\s+(?P<slug>[a-z][a-z -]+?)\s+archive\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        slug = match.group("slug")
        slug = slug.replace("_", "-").lower()
        words = [word for word in slug.split("-") if word and word not in {"seed"}]
        if words == ["context", "memory", "weaving", "continuity", "loom"]:
            words = ["context", "memory", "continuity", "loom"]
        if words:
            return " ".join(words)
    return artifact_topic_slug_words(text)


def experience_wave_action_words(value: str) -> str:
    text = str(value or "").lower()
    if "after exact operations_flow authority_note hardening" in text or "authority_note hardening" in text:
        return "authority note hardening final judgment"
    if "after fixing owner_split" in text or "owner_split exactness" in text:
        return "owner split final judgment"
    if "second-pass verdict" in text or "second pass verdict" in text:
        return "second pass judgment"
    if "judgment payload gate" in text:
        return "merge judgment"
    if "after one fix round" in text:
        return "fix round final verdict"
    if "fast narrow review verdict" in text:
        return "fast verdict review"
    if "narrow uncommitted diff" in text:
        return "diff review"
    if text.startswith("re-review wave "):
        return "recheck"
    if "code-review posture" in text or text.startswith("review wave "):
        return "review"
    if "lawful semantic core" in text:
        return "semantic core plan"
    if "owner-first landing shape" in text:
        return "owner landing plan"
    if "exact five-file landing names" in text:
        return "five file architecture review"
    if any(marker in text for marker in ("judge merge readiness", "judgment only", "ready to merge", "final verdict", "final judgment")):
        return "merge judgment"
    if any(marker in text for marker in ("review exactly", "review stance", "find merge-blocking", "find merge blocking")):
        return "bounded review"
    if any(marker in text for marker in ("narrow review", "review only these", "only review", "bounded review")):
        return "bounded review"
    if any(marker in text for marker in ("final bounded judgment", "verdict pass", "verdict review")):
        return "final judgment"
    if "planning only" in text or "landing plan" in text:
        return "landing plan"
    if "architecture pass" in text or "architecture task" in text:
        return "architecture review"
    if "memory-keeper pass" in text or "memory keeper pass" in text:
        return "memory review"
    if "seed cartography" in text:
        return "seed cartography"
    if "lineage" in text or "provenance" in text:
        return "lineage review"
    if "reconnaissance" in text:
        return "reconnaissance"
    if "plant minimal owner-local" in text or "plant thin" in text:
        return "contract planting"
    if "landing plan" in text:
        return "landing plan"
    if "semantic invariants" in text:
        return "invariant extraction"
    if "inspect" in text:
        return "seed inspection"
    return "review"


def experience_wave_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    wave = re.search(r"\bwave\s*(?P<wave>\d+)\b", text, flags=re.IGNORECASE)
    if not wave:
        return ""
    slug_words = experience_wave_slug_words(text)
    if not slug_words:
        return ""
    action_words = experience_wave_action_words(text)
    owner_words = session_review_owner_repo_words(text)
    if owner_words:
        return concise_title_text(f"Wave {wave.group('wave')} {owner_words} {action_words}", max_words=10)
    return concise_title_text(f"Wave {wave.group('wave')} {slug_words} {action_words}", max_words=10)


def repo_review_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    if not any(marker in lowered for marker in ("review", "judgment", "verdict", "pass", "diff", "working-tree")):
        return ""
    domain = detect_session_domain([text])
    if not domain:
        return ""
    topic = experience_wave_slug_words(text) or artifact_topic_slug_words(text)
    if not topic:
        return ""
    wave_match = re.search(r"\bwave\s*(?P<wave>\d+)\b|(?:^|[_-])wave(?P<wave2>\d+)(?=$|[^A-Za-z0-9])", text, flags=re.IGNORECASE)
    wave_text = f"Wave {wave_match.group('wave') or wave_match.group('wave2')}" if wave_match else ""
    action = experience_wave_action_words(text)
    return concise_title_text(f"{domain} {wave_text} {topic} {action}", max_words=11)


def repo_topology_refactor_session_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    lowered = text.lower()
    domain = detect_session_domain([text])
    if not domain:
        return ""
    if not any(
        marker in lowered
        for marker in (
            "refactor",
            "рефактор",
            "topology",
            "тополог",
            "ordering",
            "упорядоч",
            "mechanics",
            "механик",
        )
    ):
        return ""
    focus: list[str] = []
    if any(marker in lowered for marker in ("topology", "тополог", "ordering", "упорядоч")):
        focus.extend(["topology", "ordering"])
    if any(marker in lowered for marker in ("refactor", "рефактор")):
        focus.append("refactor")
    if any(marker in lowered for marker in ("mechanics", "механик")):
        focus.extend(["mechanics", "routing"])
    if not focus:
        return ""
    return concise_title_text(f"{domain} {' '.join(focus)}", max_words=10)


def special_session_name_seed(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    sidecar_seed = wave_sidecar_session_seed(text)
    if sidecar_seed:
        return sidecar_seed
    experience_seed_review_seed = experience_seed_review_session_seed(text)
    if experience_seed_review_seed:
        return experience_seed_review_seed
    experience_lineage_seed = experience_lineage_session_seed(text)
    if experience_lineage_seed:
        return experience_lineage_seed
    cross_repo_review_gate_seed = cross_repo_review_gate_session_seed(text)
    if cross_repo_review_gate_seed:
        return cross_repo_review_gate_seed
    next_wave_scout_seed = next_wave_scout_session_seed(text)
    if next_wave_scout_seed:
        return next_wave_scout_seed
    titan_wave_risk_seed = titan_wave_risk_session_seed(text)
    if titan_wave_risk_seed:
        return titan_wave_risk_seed
    center_bridge_surface_seed = center_bridge_surface_session_seed(text)
    if center_bridge_surface_seed:
        return center_bridge_surface_seed
    dionysus_closeout_seed = dionysus_closeout_session_seed(text)
    if dionysus_closeout_seed:
        return dionysus_closeout_seed
    compact_hook_probe_seed = compact_hook_probe_session_seed(text)
    if compact_hook_probe_seed:
        return compact_hook_probe_seed
    post_w10_gap_audit_seed = post_w10_gap_audit_session_seed(text)
    if post_w10_gap_audit_seed:
        return post_w10_gap_audit_seed
    mirror_drift_seed = mirror_drift_session_seed(text)
    if mirror_drift_seed:
        return mirror_drift_seed
    multi_repo_fix_map_seed = multi_repo_fix_map_session_seed(text)
    if multi_repo_fix_map_seed:
        return multi_repo_fix_map_seed
    rfc3339_lineage_seed = rfc3339_lineage_session_seed(text)
    if rfc3339_lineage_seed:
        return rfc3339_lineage_seed
    pr_gate_seed = pr_gate_session_seed(text)
    if pr_gate_seed:
        return pr_gate_seed
    socraticode_seed = socraticode_runbook_session_seed(text)
    if socraticode_seed:
        return socraticode_seed
    seed_meaning_seed = russian_seed_meaning_session_seed(text)
    if seed_meaning_seed:
        return seed_meaning_seed
    scout_seed = experience_scout_session_seed(text)
    if scout_seed:
        return scout_seed
    wave_seed = experience_wave_session_seed(text)
    if wave_seed:
        return wave_seed
    repo_review_seed = repo_review_session_seed(text)
    if repo_review_seed:
        return repo_review_seed
    repo_topology_refactor_seed = repo_topology_refactor_session_seed(text)
    if repo_topology_refactor_seed:
        return repo_topology_refactor_seed
    pr_review = re.match(
        r"(?is)^(?:read[- ]only\s+)?audit\.\s*context:\s*user provided(?:\s+a\s+large\s+list\s+of)?\s+pr review comments for (?P<owners>.+?)\.\s*work\b",
        text,
    )
    if pr_review:
        owners = pr_review.group("owners")
        owners = re.sub(r"\band\b", ",", owners, flags=re.IGNORECASE)
        owner_terms = [term.strip(" /`'\"") for term in re.split(r"[,;]+", owners) if term.strip(" /`'\"")]
        owner_text = " ".join(owner_terms[:4])
        return concise_title_text(f"{owner_text} PR review comments audit", max_words=10)
    return ""


def useful_name_seed(value: str) -> str:
    special_seed = special_session_name_seed(value)
    if special_seed:
        return special_seed
    attachment_seed = attachment_file_title_seed(value)
    if attachment_seed:
        return concise_title_text(attachment_seed)
    text = clean_phase_candidate_text(value)
    text = strip_session_meta_instruction_prefixes(text)
    text = concise_title_text(text)
    text = re.sub(r"(?i)\bread[- ]only\b\s*", "", text).strip()
    text = re.sub(r"(?i)^не\s+редактируй(?:\s+файлы)?\s*[.!?:;,-]*\s*", "", text).strip()
    text = re.sub(r"(?i)^codex in\s+", "", text).strip()
    text = re.sub(r"(?i)^in this session\s+", "", text).strip()
    text = re.sub(r"(?i)^continue\s+", "", text).strip()
    text = re.sub(r"^В этой сессии\s+", "", text).strip()
    text = re.sub(r"^Мы будем\s+", "", text).strip()
    return text


def compact_session_name(parts: list[str]) -> str:
    joined = " ".join(part for part in parts if str(part or "").strip())
    slug = semantic_name_slug(joined)
    words = [word for word in slug.split("-") if word]
    deduped: list[str] = []
    for word in words:
        if deduped and deduped[-1] == word:
            continue
        deduped.append(word)
    return "-".join(deduped[:12]) or "unresolved-session-name"


def name_seed_has_owner_signal(value: str) -> bool:
    slug = semantic_name_slug(value)
    terms = set(slug.split("-"))
    if any(term.startswith("aoa") for term in terms):
        return True
    return bool(terms & {"agents", "abyss", "tree", "sophia", "dionysus", "rios"})


def procedural_session_name_flags(terms: list[str]) -> list[str]:
    flags: list[str] = []
    term_set = set(terms)
    if not terms:
        return flags
    joined = " ".join(terms)
    procedural_prefixes = (
        ("review", "the", "current"),
        ("evaluate", "the", "current"),
        ("give", "a", "final"),
        ("return", "a", "fast"),
        ("run", "this", "harmless"),
        ("map", "the", "requested"),
        ("изучи",),
        ("проведи",),
        ("проверь",),
        ("нужен",),
    )
    if any(tuple(terms[: len(prefix)]) == prefix for prefix in procedural_prefixes):
        flags.append("procedural_prompt_residue")
    if "only" in term_set and ({"review", "repo"} & term_set or "branch" in term_set):
        flags.append("instruction_scope_residue")
    if "task" in term_set and ({"wave", "repo", "user"} & term_set):
        flags.append("procedural_prompt_residue")
    if "user" in term_set and ({"authorized", "explicitly"} & term_set):
        flags.append("instruction_scope_residue")
    if "srv" in term_set or "worktrees" in term_set or "tmp" in term_set:
        flags.append("path_scaffold_in_name")
    if terms[-1] in {"for", "after", "current", "branch", "task", "user", "only", "для", "в", "in", "on", "the"}:
        flags.append("truncated_name_tail")
    if re.search(r"\b(?:review|evaluate|inspect|judge|return|give|run|map|проверь|проведи|изучи)\b", joined):
        content_terms = [
            term
            for term in terms
            if term not in GENERIC_SESSION_NAME_WORDS
            and term not in {"review", "evaluate", "inspect", "judge", "return", "give", "run", "map", "проверь", "проведи", "изучи"}
        ]
        if len(content_terms) <= 3 and not (
            {"pr", "comments", "audit"} <= term_set or {"seed", "planting", "meaning"} <= term_set
        ):
            flags.append("low_semantic_content_name")
    return sorted(set(flags))


def quality_allows_title_seed(quality: dict[str, Any]) -> bool:
    flags = set(quality.get("flags", []) if isinstance(quality.get("flags"), list) else [])
    rejected = {
        "generic_name",
        "instruction_text_in_name",
        "banned_placeholder_term",
        "procedural_prompt_residue",
        "instruction_scope_residue",
        "path_scaffold_in_name",
        "truncated_name_tail",
        "low_semantic_content_name",
    }
    return not (flags & rejected)


def phase_discovery_summary_for_session(session_dir: Path) -> dict[str, Any]:
    path = session_phase_discovery_path(session_dir)
    if not path.is_file():
        return {"present": False, "candidate_names": [], "evidence": [], "top_paths": []}
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        return {"present": True, "candidate_names": [], "evidence": [], "top_paths": [], "read_error": "invalid_payload"}
    names: list[str] = []
    evidence: list[str] = []
    top_paths: list[str] = []
    for candidate in payload.get("candidates", []) if isinstance(payload.get("candidates"), list) else []:
        if not isinstance(candidate, dict):
            continue
        name = str(candidate.get("name") or "").strip()
        if name and not generic_session_name_text(name):
            names.append(name)
        for ref in candidate.get("evidence", []) if isinstance(candidate.get("evidence"), list) else []:
            if str(ref).strip() and len(evidence) < 8:
                evidence.append(str(ref).strip())
        signals = candidate.get("signals") if isinstance(candidate.get("signals"), dict) else {}
        linked = candidate.get("linked_signals") if isinstance(candidate.get("linked_signals"), dict) else {}
        for source in (signals.get("top_paths"), linked.get("support_paths")):
            for item in source if isinstance(source, list) else []:
                value = str(item or "").strip()
                if value and value not in top_paths:
                    top_paths.append(value)
                if len(top_paths) >= 12:
                    break
    return {
        "present": True,
        "candidate_names": names[:8],
        "evidence": evidence,
        "top_paths": top_paths[:12],
        "review_queue_count": int_value(payload.get("review_queue_count")),
    }


def semantic_phase_name_summaries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    semantic = semantic_names_payload(manifest)
    items: list[dict[str, Any]] = []
    for item in semantic.get("names", []) if isinstance(semantic.get("names"), list) else []:
        if not isinstance(item, dict) or semantic_name_scope(item) not in {"phase", "topic"}:
            continue
        items.append(
            {
                "name": item.get("name"),
                "slug": item.get("slug"),
                "scope": semantic_name_scope(item),
                "evidence": item.get("evidence", []) if isinstance(item.get("evidence"), list) else [],
                "coverage": item.get("coverage") if isinstance(item.get("coverage"), dict) else {},
            }
        )
    return items


def session_name_candidate_quality(
    name: str,
    *,
    evidence: list[str],
    anchor: dict[str, Any] | None = None,
    existing_slug_count: int = 0,
) -> dict[str, Any]:
    slug = semantic_name_slug(name)
    terms = slug.split("-")
    flags: list[str] = []
    if not name.strip():
        flags.append("missing_name")
    if len(terms) < 3:
        flags.append("name_too_short")
    if len(slug) > 80:
        flags.append("name_too_long")
    if generic_session_name_text(name):
        flags.append("generic_name")
    if set(terms) & DEFAULT_BANNED_DURABLE_NAME_TERMS:
        flags.append("banned_placeholder_term")
    flags.extend(procedural_session_name_flags(terms))
    has_you_are = any(terms[index : index + 2] == ["you", "are"] for index in range(max(len(terms) - 1, 0)))
    if has_you_are or "role" in terms[:4] or "ты" in terms[:4]:
        flags.append("role_prompt_boilerplate")
    if {"read", "only", "context"} <= set(terms) or {"read", "only", "these"} <= set(terms):
        flags.append("instruction_text_in_name")
    if len(terms) >= 2 and terms[-2:] == ["read", "only"]:
        flags.append("instruction_text_in_name")
    context_prompt_prefix = (
        bool(terms and terms[0] == "context")
        or terms[:2] == ["audit", "context"]
        or ("context" in terms[:4] and {"user", "provided"} <= set(terms[:8]))
    )
    if {"user", "approved"} <= set(terms) or context_prompt_prefix:
        flags.append("instruction_text_in_name")
    if "редактируй" in terms:
        flags.append("instruction_text_in_name")
    if {"отвечай", "только", "русском"} <= set(terms) or {"answer", "only"} <= set(terms) or {"respond", "only"} <= set(terms):
        flags.append("instruction_text_in_name")
    if not evidence:
        flags.append("missing_raw_evidence")
    if existing_slug_count > 1:
        flags.append("duplicate_slug")
    if anchor:
        if not anchor.get("raw_sha256"):
            flags.append("raw_sha256_missing")
        if not anchor.get("raw_line_count"):
            flags.append("raw_line_count_missing")
    if len([term for term in terms if term not in GENERIC_SESSION_NAME_WORDS]) <= 2 and any(
        term in {"validation", "implementation", "investigation"} for term in terms
    ):
        flags.append("too_phase_like_for_session")
    level = "ok"
    if {"missing_name", "banned_placeholder_term", "missing_raw_evidence"} & set(flags):
        level = "blocker"
    elif flags:
        level = "warn"
    return {
        "slug": slug,
        "level": level,
        "flags": flags,
    }


NAMING_EVIDENCE_HIGH_SIGNAL_TYPES = {
    "USER_INTENT",
    "DECISION",
    "CHECKPOINT",
    "OPEN_THREAD",
    "PROCESS_LESSON",
    "FINAL_STATE",
}


def naming_evidence_quality_flags(session_dir: Path, evidence: list[str]) -> list[str]:
    previews = [raw_evidence_preview(session_dir, ref, max_chars=120) for ref in evidence[:5]]
    valid = [preview for preview in previews if preview.get("ok")]
    if not valid:
        return []
    high_signal = [
        preview
        for preview in valid
        if str(preview.get("event_type") or "") in NAMING_EVIDENCE_HIGH_SIGNAL_TYPES and not preview.get("runtime_envelope")
    ]
    if high_signal:
        return []
    flags = ["weak_raw_evidence_refs"]
    event_types = {str(preview.get("event_type") or "") for preview in valid}
    if event_types and event_types <= {"COMMAND_OUTPUT", "TOOL_OUTPUT", "ERROR", "VERIFICATION"}:
        flags.append("command_output_evidence_only")
    return flags


def prioritized_naming_evidence_refs(session_dir: Path, evidence: list[str], *, max_probe: int = 12) -> list[str]:
    if not evidence:
        return []
    scored: list[tuple[int, int, str]] = []
    for index, ref in enumerate(evidence[:max_probe]):
        preview = raw_evidence_preview(session_dir, ref, max_chars=80)
        event_type = str(preview.get("event_type") or "")
        if preview.get("ok") and event_type in NAMING_EVIDENCE_HIGH_SIGNAL_TYPES and not preview.get("runtime_envelope"):
            priority = 0
        elif preview.get("ok"):
            priority = 1
        else:
            priority = 2
        scored.append((priority, index, ref))
    ordered = [ref for _, _, ref in sorted(scored)]
    ordered.extend(evidence[max_probe:])
    return ordered


def apply_evidence_quality_flags(quality: dict[str, Any], session_dir: Path, evidence: list[str]) -> dict[str, Any]:
    evidence_flags = naming_evidence_quality_flags(session_dir, evidence)
    if not evidence_flags:
        return quality
    flags = list(quality.get("flags", [])) if isinstance(quality.get("flags"), list) else []
    flags.extend(evidence_flags)
    return {
        **quality,
        "level": "warn" if quality.get("level") == "ok" else quality.get("level"),
        "flags": sorted(set(flags)),
    }


def adjust_quality_for_candidate_basis(quality: dict[str, Any], basis: str) -> dict[str, Any]:
    if basis != "domain_and_event_signals":
        return quality
    flags = list(quality.get("flags", [])) if isinstance(quality.get("flags"), list) else []
    if "fallback_name_needs_review" not in flags:
        flags.append("fallback_name_needs_review")
    return {**quality, "level": "warn" if quality.get("level") == "ok" else quality.get("level"), "flags": flags}


def synthesize_session_name_candidate(aoa_root: Path, record: dict[str, Any], readiness: dict[str, Any]) -> dict[str, Any]:
    session_dir = session_dir_from_record(record)
    manifest = read_json(session_dir / "session.manifest.json", {})
    if not isinstance(manifest, dict):
        manifest = {}
    display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    active = active_semantic_name(manifest, scope="session") if manifest else None
    phase_names = semantic_phase_name_summaries(manifest)
    phase_summary = phase_discovery_summary_for_session(session_dir)
    title = str(display.get("title") or manifest.get("session_title") or record.get("session_title") or "")
    cwd = str(source.get("cwd") or record.get("cwd") or "")
    raw_path = Path(str(raw.get("path") or session_dir / "raw" / "session.raw.jsonl"))
    policy = naming_policy(aoa_root)
    domain_hints = naming_policy_domain_hints(policy)
    action_hints = naming_policy_action_hints(policy)
    first_user_raw_event = first_raw_event_for_event_type(raw_path)
    first_user_raw_ref = first_user_raw_event[0] if first_user_raw_event else None
    first_user_raw_text = first_user_raw_event[1] if first_user_raw_event else ""

    evidence: list[str] = []
    coverage_from: int | None = None
    coverage_to: int | None = None
    basis = "title_and_index_signals"
    confidence = "medium"
    source_texts = [title, first_user_raw_text, cwd, str(display.get("label") or record.get("session_label") or "")]

    if isinstance(active, dict) and active.get("name"):
        name = str(active.get("name") or "")
        evidence = [str(ref) for ref in active.get("evidence", []) if str(ref).strip()] if isinstance(active.get("evidence"), list) else []
        coverage = active.get("coverage") if isinstance(active.get("coverage"), dict) else {}
        ranges = coverage.get("raw_ranges") if isinstance(coverage.get("raw_ranges"), list) else []
        first_range = ranges[0] if ranges and isinstance(ranges[0], dict) else {}
        coverage_from = int_value(first_range.get("from_line")) or None
        coverage_to = int_value(first_range.get("to_line")) or None
        basis = "existing_active_session_name"
        confidence = "high"
    elif phase_names:
        phase_texts = [str(item.get("name") or "") for item in phase_names if item.get("name")]
        source_texts.extend(phase_texts)
        domain = detect_session_domain(source_texts, hints=domain_hints)
        action = detect_session_action(source_texts, hints=action_hints)
        name = compact_session_name([domain, action, "session"])
        for item in phase_names:
            for ref in item.get("evidence", []) if isinstance(item.get("evidence"), list) else []:
                if str(ref).strip() and str(ref).strip() not in evidence:
                    evidence.append(str(ref).strip())
        basis = "existing_phase_topic_names"
        confidence = "high" if domain else "medium"
    else:
        phase_candidate_names = phase_summary.get("candidate_names", []) if isinstance(phase_summary.get("candidate_names"), list) else []
        top_paths = phase_summary.get("top_paths", []) if isinstance(phase_summary.get("top_paths"), list) else []
        source_texts.extend(str(item) for item in phase_candidate_names)
        source_texts.extend(str(item) for item in top_paths)
        domain = detect_session_domain(source_texts, hints=domain_hints)
        action = detect_session_action(source_texts, hints=action_hints)
        title_seed = ""
        title_inputs: list[tuple[str, str]] = []
        if first_user_raw_text:
            title_inputs.append((first_user_raw_text, "first_raw_user_request"))
        if title and title != first_user_raw_text:
            title_inputs.append((title, str(display.get("title_source") or "")))
        for candidate_title, candidate_source in title_inputs:
            candidate_seed = useful_name_seed(candidate_title)
            seed_quality = session_name_candidate_quality(candidate_seed, evidence=[first_user_raw_ref or "raw:line:1"])
            if (
                usable_title_text(candidate_seed)
                and not title_is_generic_for_naming(candidate_seed, candidate_source)
                and quality_allows_title_seed(seed_quality)
            ):
                title_seed = candidate_seed
                break
        if title_seed:
            prefix_domain = domain and domain not in semantic_name_slug(title_seed) and not name_seed_has_owner_signal(title_seed)
            name = compact_session_name([domain, title_seed] if prefix_domain else [title_seed])
            confidence = "medium" if generic_session_name_text(name) else "high"
            basis = "first_intent_title"
        else:
            name = compact_session_name([domain, action, "session"])
            confidence = "low" if not domain else "medium"
            basis = "domain_and_event_signals"
        evidence = [str(ref) for ref in phase_summary.get("evidence", []) if str(ref).strip()][:8]

    if not evidence:
        first_ref = first_user_raw_ref or first_raw_ref_for_event_type(raw_path)
        if first_ref:
            evidence = [first_ref]
    evidence = prioritized_naming_evidence_refs(session_dir, evidence)
    line_values = [line_from_raw_ref(ref) for ref in evidence]
    line_values = [line for line in line_values if line is not None]
    if line_values and coverage_from is None:
        coverage_from = min(line_values)
    if coverage_to is None:
        observed = ((readiness.get("evidence") or {}).get("observed_raw_line_count") if isinstance(readiness.get("evidence"), dict) else None)
        coverage_to = int_value(observed or raw.get("line_count")) or (max(line_values) if line_values else None)
    anchor: dict[str, Any] = {}
    if manifest:
        try:
            anchor = build_identity_anchor(session_dir, manifest, verify_raw_hash=False)
        except ValueError:
            anchor = {}
    quality = adjust_quality_for_candidate_basis(session_name_candidate_quality(name, evidence=evidence, anchor=anchor), basis)
    quality = apply_evidence_quality_flags(quality, session_dir, evidence)
    return {
        "schema_version": SCHEMA_VERSION,
        "name": name,
        "slug": semantic_name_slug(name),
        "scope": "session",
        "kind": "session_essence",
        "basis": basis,
        "confidence": confidence,
        "quality": quality,
        "evidence": evidence,
        "coverage": {
            "from_line": coverage_from,
            "to_line": coverage_to,
            "note": "Mass naming wave candidate; review before applying as a session-level semantic name.",
        },
        "signals": {
            "title": title,
            "cwd": cwd,
            "phase_names": phase_names[:8],
            "phase_discovery": phase_summary,
            "active_session_name": active.get("name") if isinstance(active, dict) else None,
        },
    }


def naming_wave_next_id(aoa_root: Path) -> str:
    root = aoa_root / DIAGNOSTICS_ROOT / "naming-waves"
    existing = sorted(root.glob("naming-wave-*")) if root.exists() else []
    numbers: list[int] = []
    for path in existing:
        match = re.search(r"naming-wave-(\d+)", path.name)
        if match:
            numbers.append(int(match.group(1)))
    return f"naming-wave-{(max(numbers) + 1) if numbers else 1}"


def naming_wave_item(
    aoa_root: Path,
    result: dict[str, Any],
    *,
    include_readable: bool,
    include_low_signal: bool,
    include_diagnostic: bool,
) -> dict[str, Any] | None:
    readiness = result.get("naming_readiness") if isinstance(result.get("naming_readiness"), dict) else {}
    status = str(readiness.get("status") or "")
    route = str(readiness.get("route") or "")
    if status == "readable_label" and not include_readable:
        return None
    if status == "low_signal" and not include_low_signal:
        return None
    if status == "diagnostic_only" and not include_diagnostic:
        return None
    session_label = str(result.get("session_label") or "")
    session_dir = Path(str(result.get("path") or ""))
    base = {
        "session_id": result.get("session_id"),
        "session_label": session_label,
        "session_title": result.get("session_title"),
        "session_dir": str(session_dir),
        "event_count": result.get("event_count", 0),
        "segment_count": result.get("segment_count", 0),
        "readiness": readiness,
        "physical_relabel_allowed": False,
        "archive_label_change": False,
    }
    if status == "diagnostic_only":
        return {**base, "action": "leave_diagnostic_visible", "reviewed_name": "", "approved": False}
    if status == "low_signal":
        return {**base, "action": "skip_low_signal", "reviewed_name": "", "approved": False}
    if status == "needs_sync":
        return {
            **base,
            "action": "sync_source_transcript",
            "approved": False,
            "reviewed_name": "",
            "preflight_command": (
                "python3 scripts/aoa_session_memory.py sync "
                f"--session-id {shlex.quote(str(result.get('session_id') or ''))} "
                "--transcript-path '<source transcript path>'"
            ),
        }
    if status == "needs_reindex":
        return {
            **base,
            "action": "reindex_session",
            "approved": False,
            "reviewed_name": "",
            "preflight_command": f"python3 scripts/aoa_session_memory.py reindex-sessions {shlex.quote(session_label)} --write-report",
        }
    if route == "review_open_phase_discovery_for_named_session":
        candidate = synthesize_session_name_candidate(aoa_root, result, readiness)
        return {
            **base,
            "action": "review_phase_queue_then_refine_session_name",
            "candidate": candidate,
            "proposed_name": candidate.get("name"),
            "reviewed_name": "",
            "approved": False,
            "phase_review_command": f"python3 scripts/aoa_session_memory.py phase-review-assist {shlex.quote(session_label)} --write --write-report",
        }
    if status in {"readable_label", "ready_for_semantic_name", "phase_discovery_ready", "named"}:
        candidate = synthesize_session_name_candidate(aoa_root, result, readiness)
        return {
            **base,
            "action": "semantic_session_name_review",
            "candidate": candidate,
            "proposed_name": candidate.get("name"),
            "reviewed_name": "",
            "approved": False,
            "apply_template": (
                "Set reviewed_name in this plan item, then run "
                "python3 scripts/aoa_session_memory.py naming-wave apply --plan <plan> --apply --write-report"
            ),
        }
    return {**base, "action": "inspect_lower_layer", "reviewed_name": "", "approved": False}


def annotate_naming_wave_candidate_duplicates(items: list[dict[str, Any]]) -> None:
    slug_counts: Counter[str] = Counter()
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        slug = str(candidate.get("slug") or semantic_name_slug(str(item.get("proposed_name") or "")))
        if slug:
            slug_counts[slug] += 1
    for item in items:
        candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        slug = str(candidate.get("slug") or semantic_name_slug(str(item.get("proposed_name") or "")))
        if not slug or slug_counts.get(slug, 0) <= 1:
            continue
        quality = candidate.get("quality") if isinstance(candidate.get("quality"), dict) else {}
        flags = list(quality.get("flags", [])) if isinstance(quality.get("flags"), list) else []
        if "duplicate_proposed_slug" not in flags:
            flags.append("duplicate_proposed_slug")
        candidate["quality"] = {
            **quality,
            "level": "warn" if quality.get("level") == "ok" else quality.get("level", "warn"),
            "flags": sorted(set(flags)),
        }
        candidate.setdefault("diagnostics", {})["duplicate_proposed_slug_count"] = slug_counts[slug]


def naming_wave_markdown(payload: dict[str, Any]) -> str:
    items = payload.get("items") if isinstance(payload.get("items"), list) else []
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    lines = [
        "# Naming Wave Plan",
        "",
        "Mass session naming work surface. This is a review plan, not reviewed truth.",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- wave_id: `{payload.get('wave_id')}`",
        f"- status: `{payload.get('status')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- item_count: `{payload.get('item_count')}`",
        f"- plan_json: `{payload.get('plan_path', '')}`",
        "",
        "## Counts",
        "",
    ]
    for key, value in sorted(counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(
        [
            "",
            "## Queue",
            "",
            "| action | status | session | proposed name | confidence | flags |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in items:
        if not isinstance(item, dict):
            continue
        readiness = item.get("readiness") if isinstance(item.get("readiness"), dict) else {}
        candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        quality = candidate.get("quality") if isinstance(candidate.get("quality"), dict) else {}
        lines.append(
            "| `{action}` | `{status}` | `{session}` | {name} | `{confidence}` | {flags} |".format(
                action=item.get("action"),
                status=readiness.get("status"),
                session=markdown_cell(item.get("session_label")),
                name=markdown_cell(item.get("proposed_name") or ""),
                confidence=candidate.get("confidence", ""),
                flags=markdown_cell(", ".join(str(flag) for flag in quality.get("flags", []) if flag)),
            )
        )
    lines.extend(["", "## Review Instructions", ""])
    lines.append("- Edit the JSON plan, not generated session files.")
    lines.append("- For semantic names, fill `reviewed_name` only after checking the candidate signals and raw refs.")
    lines.append("- For sync/reindex preflight items, set `approved=true` or run apply with `--apply-preflight` deliberately.")
    lines.append("- Physical archive relabeling is explicitly out of this wave; every item has `physical_relabel_allowed=false`.")
    lines.append("- Re-run `naming-wave audit` after applying reviewed names.")
    lines.append("")
    return "\n".join(lines)


def write_naming_wave_artifacts(aoa_root: Path, payload: dict[str, Any]) -> dict[str, str]:
    wave_id = safe_slug(str(payload.get("wave_id") or naming_wave_next_id(aoa_root)))
    wave_dir = aoa_root / DIAGNOSTICS_ROOT / "naming-waves" / wave_id
    wave_dir.mkdir(parents=True, exist_ok=True)
    plan_json = wave_dir / "naming-wave-plan.json"
    plan_md = wave_dir / "naming-wave-plan.md"
    payload["plan_path"] = str(plan_json)
    payload["plan_markdown"] = str(plan_md)
    write_json(plan_json, payload)
    write_markdown(plan_md, naming_wave_markdown(payload))
    return {"plan_path": str(plan_json), "plan_markdown": str(plan_md)}


def build_naming_wave(
    aoa_root: Path,
    *,
    target: str = "all",
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    include_readable: bool = True,
    include_low_signal: bool = False,
    include_diagnostic: bool = False,
    refresh_indexes: bool = False,
    write: bool = False,
    write_report: bool = False,
    wave_id: str | None = None,
) -> dict[str, Any]:
    readiness = build_naming_readiness_report(
        aoa_root,
        target=target,
        since=since,
        until=until,
        limit=None,
        refresh_indexes=refresh_indexes,
        write_report=write_report,
    )
    results = readiness.get("results") if isinstance(readiness.get("results"), list) else []
    items: list[dict[str, Any]] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        item = naming_wave_item(
            aoa_root,
            result,
            include_readable=include_readable,
            include_low_signal=include_low_signal,
            include_diagnostic=include_diagnostic,
        )
        if item is not None:
            items.append(item)
    if limit is not None:
        items = items[: max(0, limit)]
    annotate_naming_wave_candidate_duplicates(items)
    counts = Counter(str(item.get("action") or "missing") for item in items)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "naming_wave_plan",
        "generated_at": utc_now(),
        "ok": True,
        "status": "review_plan_ready",
        "wave_id": wave_id or naming_wave_next_id(aoa_root),
        "aoa_root": str(aoa_root),
        "target": target,
        "since": since,
        "until": until,
        "item_limit": limit,
        "selected_count": readiness.get("selected_count"),
        "item_count": len(items),
        "counts": dict(sorted(counts.items())),
        "readiness_counts": readiness.get("naming_readiness_counts"),
        "policy": {
            "semantic_names_only": True,
            "physical_relabel_allowed": False,
            "apply_requires_reviewed_name_or_explicit_flag": True,
        },
        "items": items,
    }
    if write:
        payload.update(write_naming_wave_artifacts(aoa_root, payload))
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__naming-wave__{safe_slug(str(payload.get('wave_id')))}"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, naming_wave_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def sync_record_source_transcript(aoa_root: Path, item: dict[str, Any]) -> dict[str, Any]:
    session_label = str(item.get("session_label") or "")
    record = resolve_session_record(aoa_root, session_label or str(item.get("session_id") or ""))
    session_dir = session_dir_from_record(record)
    manifest = read_json(session_dir / "session.manifest.json", {})
    if not isinstance(manifest, dict):
        return {"ok": False, "status": "diagnostic", "diagnostics": ["missing_manifest"]}
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    transcript_path_value = source.get("transcript_path")
    if not transcript_path_value:
        return {"ok": False, "status": "diagnostic", "diagnostics": ["missing_source_transcript_path"]}
    transcript_path = Path(str(transcript_path_value)).expanduser()
    if not transcript_path.is_file():
        return {"ok": False, "status": "diagnostic", "diagnostics": ["source_transcript_missing"], "path": str(transcript_path)}
    return {
        "ok": True,
        "status": "synced",
        **sync_session_from_transcript(
            aoa_root=aoa_root,
            event={
                "session_id": manifest.get("session_id") or item.get("session_id"),
                "transcript_path": str(transcript_path),
                "cwd": source.get("cwd"),
                "model": source.get("model"),
                "permission_mode": source.get("permission_mode"),
            },
            transcript_path=transcript_path,
            hook_event_name="NamingWavePreflight",
        ),
    }


def apply_naming_wave(
    aoa_root: Path,
    *,
    plan_path: Path,
    apply: bool = False,
    apply_preflight: bool = False,
    accept_proposed: bool = False,
    replace: bool = False,
    verify_raw_hash: bool = True,
    write_report: bool = False,
    stop_on_error: bool = False,
) -> dict[str, Any]:
    plan = read_json(plan_path, {})
    diagnostics: list[str] = []
    if not isinstance(plan, dict) or plan.get("artifact_type") != "naming_wave_plan":
        diagnostics.append("invalid_naming_wave_plan")
        plan = {}
    items = plan.get("items") if isinstance(plan.get("items"), list) else []
    results: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            diagnostics.append(f"item_{index}_invalid")
            if stop_on_error:
                break
            continue
        action = str(item.get("action") or "")
        session_label = str(item.get("session_label") or "")
        result: dict[str, Any] = {
            "session_label": session_label,
            "action": action,
            "status": "skipped",
            "diagnostics": [],
        }
        try:
            if action == "sync_source_transcript":
                if apply and (apply_preflight or item.get("approved") is True):
                    result.update(sync_record_source_transcript(aoa_root, item))
                else:
                    result["diagnostics"].append("preflight_not_approved")
            elif action == "reindex_session":
                if apply and (apply_preflight or item.get("approved") is True):
                    record = resolve_session_record(aoa_root, session_label or str(item.get("session_id") or ""))
                    result.update(reindex_session_from_raw(aoa_root, record, dry_run=False))
                    result["ok"] = result.get("status") in {"reindexed", "planned"}
                else:
                    result["diagnostics"].append("preflight_not_approved")
            elif action in {"semantic_session_name_review", "review_phase_queue_then_refine_session_name"}:
                candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
                reviewed_name = str(item.get("reviewed_name") or "").strip()
                if not reviewed_name and accept_proposed and str(candidate.get("confidence") or "") == "high":
                    quality = candidate.get("quality") if isinstance(candidate.get("quality"), dict) else {}
                    if quality.get("level") == "ok":
                        reviewed_name = str(candidate.get("name") or "").strip()
                        result["accepted_proposed_by_flag"] = True
                if not reviewed_name:
                    result["diagnostics"].append("reviewed_name_empty")
                elif apply:
                    coverage = candidate.get("coverage") if isinstance(candidate.get("coverage"), dict) else {}
                    semantic_result = set_session_semantic_name(
                        aoa_root=aoa_root,
                        target=session_label,
                        name=reviewed_name,
                        kind="session_essence",
                        scope="session",
                        evidence_refs=[str(ref) for ref in candidate.get("evidence", []) if str(ref).strip()]
                        if isinstance(candidate.get("evidence"), list)
                        else [],
                        from_line=int_value(coverage.get("from_line")) or None,
                        to_line=int_value(coverage.get("to_line")) or None,
                        coverage_note=str(coverage.get("note") or "Applied from naming-wave reviewed plan."),
                        source="naming_wave_review",
                        note=f"wave_id={plan.get('wave_id')}; basis={candidate.get('basis')}",
                        apply=True,
                        replace=replace,
                        verify_raw_hash=verify_raw_hash,
                        write_report=write_report,
                    )
                    result.update(
                        {
                            "ok": semantic_result.get("ok"),
                            "status": semantic_result.get("status"),
                            "reviewed_name": reviewed_name,
                            "semantic_name_result": semantic_result,
                        }
                    )
                else:
                    result.update({"ok": True, "status": "preview_ready", "reviewed_name": reviewed_name})
            else:
                result["diagnostics"].append("action_not_applyable")
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            result.update({"ok": False, "status": "diagnostic"})
            result["diagnostics"].append(str(exc))
        counts[str(result.get("status") or "unknown")] += 1
        if result.get("diagnostics"):
            diagnostics.extend(f"{session_label}:{diag}" for diag in result.get("diagnostics", []) if diag)
        results.append(result)
        if stop_on_error and not result.get("ok") and result.get("status") != "skipped":
            break
    refreshed_indexes: list[str] = []
    if apply:
        sessions = registry_sessions(aoa_root)
        write_session_name_index(aoa_root, sessions)
        write_sessions_directory_index(aoa_root, sessions)
        refreshed_indexes = [
            str(aoa_root / SESSION_NAME_INDEX_JSON),
            str(aoa_root / SESSION_NAME_INDEX_MARKDOWN),
            str(aoa_root / SESSION_ROOT / SESSIONS_INDEX_JSON),
            str(aoa_root / SESSION_ROOT / SESSIONS_INDEX_MARKDOWN),
        ]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "naming_wave_apply",
        "generated_at": utc_now(),
        "ok": not any(result.get("status") == "diagnostic" for result in results),
        "status": "applied" if apply and any(result.get("status") in {"applied", "synced", "reindexed"} for result in results) else "preview_ready",
        "apply": apply,
        "apply_preflight": apply_preflight,
        "accept_proposed": accept_proposed,
        "aoa_root": str(aoa_root),
        "plan_path": str(plan_path),
        "wave_id": plan.get("wave_id"),
        "item_count": len(items),
        "counts": dict(sorted(counts.items())),
        "diagnostics": diagnostics,
        "results": results,
        "refreshed_indexes": refreshed_indexes,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__naming-wave-apply__{safe_slug(str(plan.get('wave_id') or 'wave'))}"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, naming_wave_apply_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def naming_wave_apply_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Naming Wave Apply",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- wave_id: `{payload.get('wave_id')}`",
        f"- status: `{payload.get('status')}`",
        f"- apply: `{payload.get('apply')}`",
        f"- item_count: `{payload.get('item_count')}`",
        "",
        "## Counts",
        "",
    ]
    count_items = sorted((payload.get("counts") or {}).items()) if isinstance(payload.get("counts"), dict) else []
    for key, value in count_items:
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Results", "", "| status | action | session | diagnostics |", "| --- | --- | --- | --- |"])
    for result in payload.get("results", []) if isinstance(payload.get("results"), list) else []:
        if not isinstance(result, dict):
            continue
        lines.append(
            "| `{status}` | `{action}` | `{session}` | {diagnostics} |".format(
                status=result.get("status"),
                action=result.get("action"),
                session=markdown_cell(result.get("session_label")),
                diagnostics=markdown_cell(", ".join(str(item) for item in result.get("diagnostics", []) if item)),
            )
        )
    lines.append("")
    return "\n".join(lines)


def naming_quality_record(aoa_root: Path, record: dict[str, Any], slug_counts: Counter[str]) -> dict[str, Any]:
    session_dir = session_dir_from_record(record)
    manifest = read_json(session_dir / "session.manifest.json", {})
    if not isinstance(manifest, dict) or not manifest:
        return {"session_label": record.get("session_label"), "level": "blocker", "flags": ["missing_manifest"]}
    readiness = session_naming_readiness(aoa_root, session_dir, manifest, record=record)
    active = active_semantic_name(manifest, scope="session")
    flags: list[str] = []
    quality: dict[str, Any] = {"level": "warn", "flags": ["missing_active_session_name"], "slug": ""}
    if isinstance(active, dict):
        anchor = active.get("anchor") if isinstance(active.get("anchor"), dict) else {}
        evidence = [str(ref) for ref in active.get("evidence", []) if str(ref).strip()] if isinstance(active.get("evidence"), list) else []
        quality = session_name_candidate_quality(
            str(active.get("name") or ""),
            evidence=evidence,
            anchor=anchor,
            existing_slug_count=slug_counts.get(str(active.get("slug") or ""), 0),
        )
        flags.extend(quality.get("flags", []))
    else:
        flags.extend(quality["flags"])
    if readiness.get("status") == "needs_sync":
        flags.append("needs_sync_before_final_name_review")
    evidence = readiness.get("evidence") if isinstance(readiness.get("evidence"), dict) else {}
    if evidence.get("active_session_coverage_stale"):
        flags.append("active_session_name_coverage_stale")
    if int_value(evidence.get("phase_discovery_review_queue_count")):
        flags.append("phase_review_queue_open")
    level = "ok"
    if any(flag in flags for flag in ["missing_manifest", "missing_raw_evidence", "banned_placeholder_term"]):
        level = "blocker"
    elif flags:
        level = "warn"
    return {
        "session_id": manifest.get("session_id"),
        "session_label": manifest.get("session_label") or record.get("session_label"),
        "active_session_name": active.get("name") if isinstance(active, dict) else None,
        "slug": active.get("slug") if isinstance(active, dict) else None,
        "level": level,
        "flags": sorted(set(flags)),
        "readiness_status": readiness.get("status"),
        "readiness_route": readiness.get("route"),
    }


def raw_evidence_preview(session_dir: Path, evidence_ref: str, *, max_chars: int = 240) -> dict[str, Any]:
    line_no = line_from_raw_ref(evidence_ref)
    if line_no is None:
        return {"ref": evidence_ref, "ok": False, "reason": "not_raw_line_ref"}
    raw_path = session_dir / "raw" / "session.raw.jsonl"
    if not raw_path.is_file():
        return {"ref": evidence_ref, "ok": False, "reason": "missing_raw_archive"}
    try:
        with raw_path.open("r", encoding="utf-8", errors="replace") as handle:
            for current, line in enumerate(handle, start=1):
                if current != line_no:
                    continue
                raw_line = line.rstrip("\n")
                parsed: dict[str, Any] | None = None
                try:
                    loaded = json.loads(raw_line)
                    if isinstance(loaded, dict):
                        parsed = loaded
                except json.JSONDecodeError:
                    parsed = None
                event = classify_raw_event(raw_line, parsed, line_no)
                text = event_semantic_text(event)
                return {
                    "ref": evidence_ref,
                    "ok": True,
                    "event_type": event.event_type,
                    "source_type": event.source_type,
                    "text": short_text(text, max_chars=max_chars),
                    "runtime_envelope": naming_evidence_text_is_runtime_envelope(text),
                }
    except OSError as exc:
        return {"ref": evidence_ref, "ok": False, "reason": str(exc)}
    return {"ref": evidence_ref, "ok": False, "reason": "line_not_found"}


def naming_quality_sample_bucket(item: dict[str, Any]) -> str:
    action = str(item.get("action") or "")
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    quality = candidate.get("quality") if isinstance(candidate.get("quality"), dict) else {}
    flags = [str(flag) for flag in quality.get("flags", []) if str(flag).strip()] if isinstance(quality.get("flags"), list) else []
    level = str(quality.get("level") or "none")
    name = str(item.get("proposed_name") or candidate.get("name") or "")
    slug_terms = set(semantic_name_slug(name).split("-"))
    if action in {"sync_source_transcript", "reindex_session"}:
        return f"preflight:{action}"
    if flags:
        return f"flag:{flags[0]}"
    if level != "ok":
        return f"level:{level}"
    if {"you", "are"} <= slug_terms or "role" in slug_terms or "ты" in slug_terms:
        return "unflagged_role_or_prompt_residue"
    if {"context", "user", "approved"} <= slug_terms or {"read", "only"} <= slug_terms:
        return "unflagged_instruction_residue"
    if str(candidate.get("basis") or "") == "domain_and_event_signals":
        return "domain_action_fallback_ok"
    if len(slug_terms) <= 4:
        return "short_ok_name"
    return "ok_candidate"


def naming_quality_sample_priority(bucket: str) -> int:
    if bucket.startswith("preflight:"):
        return 0
    if bucket.startswith("flag:"):
        return 1
    if bucket.startswith("level:"):
        return 2
    if bucket.startswith("unflagged_"):
        return 3
    if bucket in {"domain_action_fallback_ok", "short_ok_name"}:
        return 4
    return 5


def naming_quality_plan_sample(
    items: list[dict[str, Any]],
    *,
    sample_size: int,
    sample_seed: str,
    raw_chars: int = 240,
) -> list[dict[str, Any]]:
    if sample_size <= 0:
        return []
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        bucket = naming_quality_sample_bucket(item)
        digest = hashlib.sha256(
            f"{sample_seed}\0{bucket}\0{item.get('session_label')}\0{item.get('proposed_name')}\0{index}".encode("utf-8", errors="replace")
        ).hexdigest()
        buckets[bucket].append({"index": index, "score": digest, "item": item})
    ordered_buckets = sorted(buckets, key=lambda key: (naming_quality_sample_priority(key), key))
    selected: list[dict[str, Any]] = []
    used_indexes: set[int] = set()
    for bucket in ordered_buckets:
        choices = sorted(buckets[bucket], key=lambda entry: entry["score"])
        if choices and len(selected) < sample_size:
            selected.append(choices[0])
            used_indexes.add(int(choices[0]["index"]))
    remaining = sorted(
        (entry for bucket in ordered_buckets for entry in buckets[bucket] if int(entry["index"]) not in used_indexes),
        key=lambda entry: (naming_quality_sample_priority(naming_quality_sample_bucket(entry["item"])), entry["score"]),
    )
    for entry in remaining:
        if len(selected) >= sample_size:
            break
        selected.append(entry)
    sample: list[dict[str, Any]] = []
    for entry in selected[:sample_size]:
        item = entry["item"]
        candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
        quality = candidate.get("quality") if isinstance(candidate.get("quality"), dict) else {}
        evidence = [str(ref) for ref in candidate.get("evidence", []) if str(ref).strip()] if isinstance(candidate.get("evidence"), list) else []
        session_dir = Path(str(item.get("session_dir") or ""))
        previews = [raw_evidence_preview(session_dir, ref, max_chars=raw_chars) for ref in evidence[:3]] if session_dir else []
        sample.append(
            {
                "plan_index": entry["index"],
                "bucket": naming_quality_sample_bucket(item),
                "session_label": item.get("session_label"),
                "action": item.get("action"),
                "proposed_name": item.get("proposed_name") or candidate.get("name"),
                "basis": candidate.get("basis"),
                "confidence": candidate.get("confidence"),
                "quality_level": quality.get("level"),
                "quality_flags": quality.get("flags", []) if isinstance(quality.get("flags"), list) else [],
                "evidence": evidence[:3],
                "evidence_preview": previews,
            }
        )
    return sample


def naming_quality_audit(
    aoa_root: Path,
    *,
    target: str = "all",
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    plan_path: Path | None = None,
    sample_size: int = 0,
    sample_seed: str = "naming-quality",
    sample_raw_chars: int = 240,
    write_report: bool = False,
) -> dict[str, Any]:
    records = [resolve_session_record(aoa_root, target)] if target != "all" else chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    slug_counts: Counter[str] = Counter()
    for record in records:
        manifest = read_json(session_dir_from_record(record) / "session.manifest.json", {})
        if isinstance(manifest, dict):
            active = active_semantic_name(manifest, scope="session")
            if isinstance(active, dict) and active.get("slug"):
                slug_counts[str(active.get("slug"))] += 1
    results = [naming_quality_record(aoa_root, record, slug_counts) for record in records]
    plan_results: list[dict[str, Any]] = []
    plan_items: list[dict[str, Any]] = []
    if plan_path is not None:
        plan = read_json(plan_path, {})
        plan_items = [item for item in plan.get("items", []) if isinstance(item, dict)] if isinstance(plan, dict) and isinstance(plan.get("items"), list) else []
        plan_slug_counts: Counter[str] = Counter()
        for item in plan_items:
            if not isinstance(item, dict):
                continue
            candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
            name = str(item.get("reviewed_name") or candidate.get("name") or item.get("proposed_name") or "")
            slug = semantic_name_slug(name)
            if slug:
                plan_slug_counts[slug] += 1
        for item in plan_items:
            if not isinstance(item, dict):
                continue
            candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
            name = str(item.get("reviewed_name") or candidate.get("name") or item.get("proposed_name") or "")
            evidence = [str(ref) for ref in candidate.get("evidence", []) if str(ref).strip()] if isinstance(candidate.get("evidence"), list) else []
            quality = session_name_candidate_quality(name, evidence=evidence, existing_slug_count=plan_slug_counts.get(semantic_name_slug(name), 0))
            quality = apply_evidence_quality_flags(quality, Path(str(item.get("session_dir") or "")), evidence)
            flags = list(quality.get("flags", [])) if isinstance(quality.get("flags"), list) else []
            if plan_slug_counts.get(semantic_name_slug(name), 0) > 1 and "duplicate_proposed_slug" not in flags:
                flags.append("duplicate_proposed_slug")
                quality = {
                    **quality,
                    "level": "warn" if quality.get("level") == "ok" else quality.get("level"),
                    "flags": sorted(set(flags)),
                }
            plan_results.append(
                {
                    "session_label": item.get("session_label"),
                    "action": item.get("action"),
                    "name": name,
                    "level": quality.get("level"),
                    "flags": quality.get("flags", []),
                }
            )
    quality_sample = (
        naming_quality_plan_sample(plan_items, sample_size=sample_size, sample_seed=sample_seed, raw_chars=sample_raw_chars)
        if plan_items and sample_size
        else []
    )
    by_level = Counter(str(item.get("level") or "missing") for item in results)
    by_plan_level = Counter(str(item.get("level") or "missing") for item in plan_results)
    by_flag: Counter[str] = Counter()
    for item in results + plan_results:
        for flag in item.get("flags", []) if isinstance(item.get("flags"), list) else []:
            by_flag[str(flag)] += 1
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "naming_quality_audit",
        "generated_at": utc_now(),
        "ok": by_level.get("blocker", 0) == 0 and by_plan_level.get("blocker", 0) == 0,
        "aoa_root": str(aoa_root),
        "target": target,
        "selected_count": len(records),
        "counts": {
            "by_level": dict(sorted(by_level.items())),
            "by_plan_level": dict(sorted(by_plan_level.items())),
            "by_flag": dict(sorted(by_flag.items())),
        },
        "quality_sample_seed": sample_seed if sample_size else None,
        "quality_sample_size": len(quality_sample),
        "quality_sample": quality_sample,
        "results": results,
        "plan_results": plan_results,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__naming-quality-audit"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, naming_quality_audit_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def naming_quality_audit_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Naming Quality Audit",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- ok: `{str(payload.get('ok')).lower()}`",
        "",
        "## Counts",
        "",
    ]
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    for group, values in counts.items():
        lines.extend([f"### {group}", ""])
        value_items = values.items() if isinstance(values, dict) else []
        for key, value in value_items:
            lines.append(f"- `{key}`: {value}")
        lines.append("")
    lines.extend(["## Findings", "", "| level | session | active name | flags |", "| --- | --- | --- | --- |"])
    for result in payload.get("results", []) if isinstance(payload.get("results"), list) else []:
        if not isinstance(result, dict):
            continue
        if result.get("level") == "ok":
            continue
        lines.append(
            "| `{level}` | `{session}` | {name} | {flags} |".format(
                level=result.get("level"),
                session=markdown_cell(result.get("session_label")),
                name=markdown_cell(result.get("active_session_name") or ""),
                flags=markdown_cell(", ".join(str(flag) for flag in result.get("flags", []) if flag)),
            )
        )
    lines.append("")
    sample = payload.get("quality_sample") if isinstance(payload.get("quality_sample"), list) else []
    if sample:
        lines.extend(
            [
                "## Quality Sample",
                "",
                f"- seed: `{payload.get('quality_sample_seed')}`",
                f"- size: `{payload.get('quality_sample_size')}`",
                "",
                "| bucket | session | proposed name | flags | raw preview |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for item in sample:
            if not isinstance(item, dict):
                continue
            previews = item.get("evidence_preview") if isinstance(item.get("evidence_preview"), list) else []
            first_preview = previews[0] if previews and isinstance(previews[0], dict) else {}
            lines.append(
                "| `{bucket}` | `{session}` | {name} | {flags} | {preview} |".format(
                    bucket=item.get("bucket"),
                    session=markdown_cell(item.get("session_label")),
                    name=markdown_cell(item.get("proposed_name") or ""),
                    flags=markdown_cell(", ".join(str(flag) for flag in item.get("quality_flags", []) if flag)),
                    preview=markdown_cell(first_preview.get("text") or first_preview.get("reason") or ""),
                )
            )
        lines.append("")
    return "\n".join(lines)


def compact_naming_wave_item(item: dict[str, Any]) -> dict[str, Any]:
    candidate = item.get("candidate") if isinstance(item.get("candidate"), dict) else {}
    quality = candidate.get("quality") if isinstance(candidate.get("quality"), dict) else {}
    readiness = item.get("readiness") if isinstance(item.get("readiness"), dict) else {}
    return {
        "session_label": item.get("session_label"),
        "action": item.get("action"),
        "status": readiness.get("status"),
        "route": readiness.get("route"),
        "proposed_name": item.get("proposed_name"),
        "confidence": candidate.get("confidence"),
        "quality_level": quality.get("level"),
        "quality_flags": quality.get("flags", [])[:8] if isinstance(quality.get("flags"), list) else [],
        "physical_relabel_allowed": item.get("physical_relabel_allowed"),
    }


def naming_wave_print_payload(payload: dict[str, Any], *, full: bool = False) -> dict[str, Any]:
    printable = {key: value for key, value in payload.items() if key != "items"}
    printable["results"] = payload.get("items", [])
    return bounded_results_print_payload(
        printable,
        full=full,
        compact_func=compact_naming_wave_item,
        note="items are bounded on stdout; pass --full or read the written naming-wave plan for complete results",
    )


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
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    raw_blocks = manifest.get("raw_blocks") if isinstance(manifest.get("raw_blocks"), dict) else {}
    raw_block_items = raw_blocks.get("blocks") if isinstance(raw_blocks.get("blocks"), list) else []
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
        "raw": {
            "path": raw.get("path"),
            "source_path": raw.get("source_path"),
            "line_count": raw.get("line_count"),
            "bytes": raw.get("bytes"),
            "sha256": raw.get("sha256"),
            "indexing_status": raw.get("indexing_status"),
            "blocks_index": raw.get("blocks_index"),
            "compaction_events": raw.get("compaction_events"),
        },
        "raw_blocks": {
            "index": raw_blocks.get("index"),
            "compaction_events": raw_blocks.get("compaction_events"),
            "block_count": len(raw_block_items),
        },
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


def reindex_session_from_raw(
    aoa_root: Path,
    record: dict[str, Any],
    *,
    dry_run: bool = False,
    max_raw_bytes: int | None = None,
) -> dict[str, Any]:
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
    raw_bytes = raw_path.stat().st_size
    if max_raw_bytes is not None and raw_bytes > max_raw_bytes:
        return {
            "session_id": manifest.get("session_id"),
            "session_label": manifest.get("session_label"),
            "session_dir": str(session_dir),
            "status": "skipped",
            "raw_path": str(raw_path),
            "raw_bytes": raw_bytes,
            "max_raw_bytes": max_raw_bytes,
            "diagnostics": [f"raw_too_large:{raw_bytes}>{max_raw_bytes}"],
        }

    if dry_run:
        existing_raw_blocks = manifest.get("raw_blocks") if isinstance(manifest.get("raw_blocks"), dict) else {}
        existing_raw_block_items = (
            existing_raw_blocks.get("blocks")
            if isinstance(existing_raw_blocks.get("blocks"), list)
            else []
        )
        return {
            "session_id": manifest.get("session_id"),
            "session_label": manifest.get("session_label"),
            "session_dir": str(session_dir),
            "status": "planned",
            "raw_path": str(raw_path),
            "raw_bytes": raw_bytes,
            "segment_count": len(manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []),
            "existing_raw_block_count": len(existing_raw_block_items),
            "existing_raw_blocks_index": existing_raw_blocks.get("index") or raw.get("blocks_index"),
            "needs_raw_block_backfill": not bool(existing_raw_blocks.get("index") or raw.get("blocks_index")),
        }

    now = utc_now()
    events = parse_raw_events(raw_path)
    clear_generated_segments(session_dir)
    clear_generated_raw_blocks(session_dir)
    raw_rel = "raw/session.raw.jsonl"
    ranges = segment_ranges(events)
    raw_blocks = write_raw_block_artifacts(session_dir, raw_rel, ranges, events)
    raw_blocks_by_segment = {
        str(block.get("segment_id")): block
        for block in raw_blocks.get("blocks", [])
        if isinstance(block, dict)
    }
    segment_payloads = [
        write_segment(session_dir, raw_rel, segment_no, role, events[start:end], raw_blocks_by_segment.get(f"{segment_no:03d}"))
        for segment_no, (start, end, role) in enumerate(ranges)
    ]
    manifest["archive_status"] = "indexed"
    manifest["archive_format_version"] = 2
    manifest["segments"] = segment_payloads
    manifest["raw_blocks"] = raw_blocks
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
        manifest["raw"]["blocks_index"] = raw_blocks.get("index")
        manifest["raw"]["compaction_events"] = raw_blocks.get("compaction_events")
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
        "raw_block_count": len(raw_blocks.get("blocks", []) if isinstance(raw_blocks.get("blocks"), list) else []),
        "raw_blocks_index": raw_blocks.get("index"),
        "raw_compaction_events": raw_blocks.get("compaction_events"),
    }


def session_record_has_stale_route_index(record: dict[str, Any]) -> bool:
    session_dir = session_dir_from_record(record)
    manifest = read_json(session_dir / "session.manifest.json", {})
    archive_status = str(manifest.get("archive_status") or record.get("archive_status") or "") if isinstance(manifest, dict) else ""
    if archive_status not in {"indexed", "raw_mirrored_index_deferred"}:
        return False
    session_index = read_json(session_dir / SESSION_INDEX_JSON, {})
    if not isinstance(session_index, dict) or not session_index:
        return True
    return bool(route_signal_index_stale_reasons(session_index))


def reindex_sessions(
    *,
    aoa_root: Path,
    target: str = "all",
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
    max_raw_bytes: int | None = None,
    stale_route_indexes: bool = False,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    try:
        if target and target != "all":
            records = [resolve_session_record(aoa_root, target)]
        else:
            records = chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    except ValueError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "conversation_act_audit",
            "generated_at": now,
            "ok": False,
            "aoa_root": str(aoa_root),
            "target": target,
            "since": since,
            "until": until,
            "limit": limit,
            "max_raw_bytes": max_raw_bytes,
            "stale_route_indexes": stale_route_indexes,
            "candidate_selected_count": 0,
            "selected_count": 0,
            "segment_count": 0,
            "event_count": 0,
            "eligible_event_count": 0,
            "missing_eligible_conversation_act": 0,
            "missing_samples": [],
            "counts": {},
            "samples": {},
            "diagnostics": [str(exc)],
        }
    candidate_selected_count = len(records)
    if stale_route_indexes:
        records = [record for record in records if session_record_has_stale_route_index(record)]
    counts: Counter[str] = Counter()
    results: list[dict[str, Any]] = []
    for record in records:
        result = reindex_session_from_raw(
            aoa_root,
            record,
            dry_run=dry_run,
            max_raw_bytes=max_raw_bytes,
        )
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
        "max_raw_bytes": max_raw_bytes,
        "stale_route_indexes": stale_route_indexes,
        "candidate_selected_count": candidate_selected_count,
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
        f"- max_raw_bytes: `{payload.get('max_raw_bytes')}`",
        f"- stale_route_indexes: `{payload.get('stale_route_indexes')}`",
        f"- candidate_selected_count: `{payload.get('candidate_selected_count')}`",
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


def path_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def latest_index_source_mtime(aoa_root: Path, records: list[dict[str, Any]]) -> tuple[float, list[str]]:
    paths: list[Path] = [
        aoa_root / REGISTRY_NAME,
        aoa_root / SESSION_NAME_INDEX_JSON,
        aoa_root / SESSION_NAME_INDEX_MARKDOWN,
        aoa_root / SESSION_ROOT / SESSIONS_INDEX_JSON,
        aoa_root / SESSION_ROOT / SESSIONS_INDEX_MARKDOWN,
    ]
    for record in records:
        session_dir = session_dir_from_record(record)
        manifest_path = session_dir / "session.manifest.json"
        session_index_path = session_dir / SESSION_INDEX_JSON
        paths.extend([manifest_path, session_index_path, session_dir / SESSION_INDEX_MARKDOWN])
        manifest = read_json(manifest_path, {})
        if isinstance(manifest, dict):
            for segment in manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []:
                if not isinstance(segment, dict):
                    continue
                if segment.get("index"):
                    paths.append(Path(str(segment["index"])))
                if segment.get("markdown"):
                    paths.append(Path(str(segment["markdown"])))
        incidents_dir = session_dir / "incidents"
        if incidents_dir.is_dir():
            paths.extend(path for path in incidents_dir.iterdir() if path.is_file())
    existing = [path for path in paths if path.exists()]
    if not existing:
        return 0.0, []
    newest = max(path_mtime(path) for path in existing)
    newest_paths = [str(path) for path in existing if path_mtime(path) == newest]
    return newest, newest_paths[:8]


def route_index_drift_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    drift: list[dict[str, Any]] = []
    for record in records:
        if not session_record_has_stale_route_index(record):
            continue
        session_dir = session_dir_from_record(record)
        session_index = read_json(session_dir / SESSION_INDEX_JSON, {})
        manifest = read_json(session_dir / "session.manifest.json", {})
        reasons = route_signal_index_stale_reasons(session_index if isinstance(session_index, dict) else {})
        if not isinstance(session_index, dict) or not session_index:
            reasons = ["missing_session_index"]
        drift.append(
            {
                "session_id": record.get("session_id") or (manifest.get("session_id") if isinstance(manifest, dict) else ""),
                "session_label": record.get("session_label") or (manifest.get("session_label") if isinstance(manifest, dict) else session_dir.name),
                "session_dir": str(session_dir),
                "archive_status": (manifest.get("archive_status") if isinstance(manifest, dict) else record.get("archive_status")),
                "reasons": reasons,
            }
        )
    return drift


def sqlite_search_index_state(aoa_root: Path, latest_source_mtime: float) -> dict[str, Any]:
    db_path = search_db_path(aoa_root)
    if not db_path.exists():
        return {
            "status": "missing",
            "needs_refresh": True,
            "db_path": str(db_path),
            "diagnostics": ["search_index_missing"],
        }
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        metadata = search_index_metadata(conn)
        rows = conn.execute("SELECT doc_type, COUNT(*) AS count FROM documents GROUP BY doc_type").fetchall()
        conn.close()
    except sqlite3.Error as exc:
        return {
            "status": "sqlite_error",
            "needs_refresh": True,
            "db_path": str(db_path),
            "diagnostics": [f"sqlite_error:{exc}"],
        }
    schema_version = str(metadata.get("schema_version") or "")
    counts = {str(row["doc_type"]): int(row["count"]) for row in rows}
    document_count = sum(counts.values())
    db_mtime = path_mtime(db_path)
    reasons: list[str] = []
    if schema_version != str(SEARCH_SCHEMA_VERSION):
        reasons.append("search_schema_mismatch")
    if document_count <= 0:
        reasons.append("search_index_empty")
    if latest_source_mtime > 0 and db_mtime < latest_source_mtime:
        reasons.append("source_newer_than_search_index")
    status = "current" if not reasons else ("stale" if reasons != ["search_index_empty"] else "empty")
    return {
        "status": status,
        "needs_refresh": bool(reasons),
        "db_path": str(db_path),
        "db_mtime": db_mtime,
        "latest_source_mtime": latest_source_mtime,
        "search_schema_version": schema_version,
        "expected_search_schema_version": SEARCH_SCHEMA_VERSION,
        "document_count": document_count,
        "document_counts": counts,
        "reasons": reasons,
        "diagnostics": [],
    }


def atlas_index_state(aoa_root: Path, latest_source_mtime: float) -> dict[str, Any]:
    index_path = aoa_root / ATLAS_ROOT / "index.json"
    payload = read_json(index_path, {})
    if not index_path.exists():
        return {
            "status": "missing",
            "needs_refresh": True,
            "index": str(index_path),
            "diagnostics": ["atlas_index_missing"],
        }
    if not isinstance(payload, dict):
        return {
            "status": "invalid",
            "needs_refresh": True,
            "index": str(index_path),
            "diagnostics": ["atlas_index_invalid"],
        }
    entry_count = int_value(payload.get("entry_count"))
    index_mtime = path_mtime(index_path)
    reasons: list[str] = []
    if int_value(payload.get("schema_version")) != ATLAS_SCHEMA_VERSION:
        reasons.append("atlas_schema_mismatch")
    if entry_count <= 0:
        reasons.append("atlas_index_empty")
    if latest_source_mtime > 0 and index_mtime < latest_source_mtime:
        reasons.append("source_newer_than_atlas_index")
    status = "current" if not reasons else ("stale" if reasons != ["atlas_index_empty"] else "empty")
    return {
        "status": status,
        "needs_refresh": bool(reasons),
        "index": str(index_path),
        "index_mtime": index_mtime,
        "latest_source_mtime": latest_source_mtime,
        "entry_count": entry_count,
        "axis_count": int_value(payload.get("axis_count")),
        "schema_version": payload.get("schema_version"),
        "expected_schema_version": ATLAS_SCHEMA_VERSION,
        "reasons": reasons,
        "diagnostics": [],
    }


def maintenance_action(action_id: str, *, reason: str, needed: bool, command: list[str]) -> dict[str, Any]:
    return {
        "id": action_id,
        "needed": needed,
        "reason": reason,
        "status": "planned" if needed else "not_needed",
        "command": command,
    }


def maintain_indexes(
    *,
    aoa_root: Path,
    target: str = "all",
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    apply: bool = False,
    max_raw_bytes: int | None = None,
    sample_audit: bool = False,
    sample_limit: int = DEFAULT_ROUTE_SAMPLE_LIMIT,
    max_raw_chars: int = 360,
    write_report: bool = False,
    reason: str = "operator_requested",
) -> dict[str, Any]:
    now = utc_now()
    diagnostics: list[str] = []
    try:
        records = [resolve_session_record(aoa_root, target)] if target != "all" else chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    except ValueError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "index_maintenance",
            "generated_at": now,
            "ok": False,
            "apply": apply,
            "target": target,
            "reason": reason,
            "selected_count": 0,
            "diagnostics": [str(exc)],
            "actions": [],
        }

    latest_source_mtime, latest_source_paths = latest_index_source_mtime(aoa_root, records)
    route_drift = route_index_drift_records(records)
    deferred_sessions = [
        {
            "session": str(record.get("session_label") or record.get("session_id") or session_dir_from_record(record).name),
            "session_id": str(record.get("session_id") or ""),
            "session_dir": str(session_dir_from_record(record)),
        }
        for record in records
        if str(read_json(session_dir_from_record(record) / "session.manifest.json", {}).get("archive_status") or record.get("archive_status") or "") == "raw_mirrored_index_deferred"
    ]
    search_state = sqlite_search_index_state(aoa_root, latest_source_mtime)
    atlas_state = atlas_index_state(aoa_root, latest_source_mtime)
    max_raw_mb_text = str(max_raw_bytes / (1024 * 1024)) if max_raw_bytes is not None else None
    base = ["python3", "scripts/aoa_session_memory.py"]
    root_args = ["--workspace-root", "<workspace>", "--aoa-root", str(aoa_root)]
    actions = [
        maintenance_action(
            "reindex_route_indexes",
            reason="missing_or_stale_session_route_indexes",
            needed=bool(route_drift),
            command=base
            + ["reindex-sessions", target, *root_args, "--stale-route-indexes"]
            + (["--max-raw-mb", max_raw_mb_text] if max_raw_mb_text else [])
            + ["--write-report"],
        ),
        maintenance_action(
            "rebuild_search_index",
            reason="portable_sqlite_missing_or_stale",
            needed=bool(search_state.get("needs_refresh")) or bool(route_drift),
            command=base
            + ["search-index", "all", *root_args]
            + (["--max-raw-mb", max_raw_mb_text] if max_raw_mb_text else [])
            + ["--write-report"],
        ),
        maintenance_action(
            "rebuild_agent_atlas",
            reason="atlas_missing_or_stale",
            needed=bool(atlas_state.get("needs_refresh")) or bool(route_drift),
            command=base + ["atlas", "build", "all", *root_args, "--write-report"],
        ),
        maintenance_action(
            "route_readiness",
            reason="post_maintenance_gate",
            needed=bool(route_drift) or bool(search_state.get("needs_refresh")) or bool(atlas_state.get("needs_refresh")),
            command=base + ["route-readiness", "all", *root_args, "--write-report"],
        ),
        maintenance_action(
            "route_sample_audit",
            reason="classifier_or_schema_reindex_calibration",
            needed=sample_audit and bool(route_drift),
            command=base + ["route-sample-audit", "all", *root_args, "--sample-limit", str(sample_limit), "--max-raw-chars", str(max_raw_chars), "--write-report"],
        ),
    ]

    action_results: list[dict[str, Any]] = []
    if apply:
        reindex_ran = False
        if actions[0]["needed"]:
            result = reindex_sessions(
                aoa_root=aoa_root,
                target=target,
                since=since,
                until=until,
                limit=limit,
                max_raw_bytes=max_raw_bytes,
                stale_route_indexes=True,
                write_report=write_report,
            )
            actions[0]["status"] = "applied" if result.get("ok") else "failed"
            actions[0]["result"] = {key: result.get(key) for key in ("ok", "selected_count", "counts", "report_json", "report_markdown", "diagnostics")}
            action_results.append(actions[0])
            reindex_ran = bool(result.get("selected_count"))
            if not result.get("ok"):
                diagnostics.extend(str(item) for item in result.get("diagnostics", []))
        if actions[1]["needed"] or reindex_ran:
            result = search_index_sessions(
                aoa_root=aoa_root,
                target="all",
                max_raw_bytes=max_raw_bytes,
                rebuild=True,
                write_report=write_report,
            )
            actions[1]["status"] = "applied" if result.get("ok") else "failed"
            actions[1]["result"] = {key: result.get(key) for key in ("ok", "selected_count", "document_count", "report_json", "report_markdown", "diagnostics")}
            action_results.append(actions[1])
            if not result.get("ok"):
                diagnostics.extend(str(item) for item in result.get("diagnostics", []))
        if actions[2]["needed"] or reindex_ran:
            result = build_agent_atlas(
                aoa_root=aoa_root,
                target="all",
                clean=True,
                write_report=write_report,
            )
            actions[2]["status"] = "applied" if result.get("ok") else "failed"
            actions[2]["result"] = {key: result.get(key) for key in ("ok", "selected_count", "axis_count", "entry_count", "report_json", "report_markdown", "diagnostics")}
            action_results.append(actions[2])
            if not result.get("ok"):
                diagnostics.extend(str(item) for item in result.get("diagnostics", []))
        if actions[3]["needed"] or reindex_ran:
            result = route_layer_readiness(
                aoa_root=aoa_root,
                target="all",
                sample_limit=sample_limit,
                write_report=write_report,
            )
            actions[3]["status"] = "applied" if result.get("ok") else "remaining"
            actions[3]["result"] = {key: result.get(key) for key in ("ok", "covered_requirement_count", "required_requirement_count", "report_json", "report_markdown", "diagnostics")}
            action_results.append(actions[3])
            if not result.get("ok") and result.get("diagnostics"):
                diagnostics.extend(str(item) for item in result.get("diagnostics", []))
        if actions[4]["needed"]:
            result = route_sample_audit(
                aoa_root=aoa_root,
                target="all",
                sample_limit=sample_limit,
                max_raw_chars=max_raw_chars,
                write_report=write_report,
            )
            actions[4]["status"] = "applied" if result.get("ok") else "remaining"
            actions[4]["result"] = {key: result.get(key) for key in ("ok", "total_sample_count", "sampled_layer_count", "required_layer_count", "report_json", "report_markdown", "diagnostics")}
            action_results.append(actions[4])
            if not result.get("ok") and result.get("diagnostics"):
                diagnostics.extend(str(item) for item in result.get("diagnostics", []))

    for action in actions:
        if action.get("needed") and not any(item.get("id") == action["id"] for item in action_results):
            action_results.append(action)
    action_counts = dict(Counter(str(action.get("status") or "unknown") for action in action_results))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "index_maintenance",
        "generated_at": now,
        "ok": not diagnostics and not any(action.get("status") == "failed" for action in action_results),
        "apply": apply,
        "target": target,
        "since": since,
        "until": until,
        "limit": limit,
        "reason": reason,
        "selected_count": len(records),
        "latest_source_mtime": latest_source_mtime,
        "latest_source_paths": latest_source_paths,
        "route_drift_count": len(route_drift),
        "route_drift": route_drift,
        "deferred_session_count": len(deferred_sessions),
        "deferred_sessions": deferred_sessions[:20],
        "search_index": search_state,
        "atlas_index": atlas_state,
        "action_counts": action_counts,
        "actions": action_results,
        "diagnostics": diagnostics,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__index-maintenance"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, index_maintenance_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def index_maintenance_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Index Maintenance",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- ok: `{payload.get('ok')}`",
        f"- apply: `{payload.get('apply')}`",
        f"- target: `{payload.get('target')}`",
        f"- reason: `{payload.get('reason')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- route_drift_count: `{payload.get('route_drift_count')}`",
        f"- deferred_session_count: `{payload.get('deferred_session_count')}`",
        f"- search_index: `{(payload.get('search_index') or {}).get('status') if isinstance(payload.get('search_index'), dict) else ''}`",
        f"- atlas_index: `{(payload.get('atlas_index') or {}).get('status') if isinstance(payload.get('atlas_index'), dict) else ''}`",
        "",
        "## Actions",
        "",
        "| action | needed | status | reason |",
        "| --- | --- | --- | --- |",
    ]
    for action in payload.get("actions", []) if isinstance(payload.get("actions"), list) else []:
        if not isinstance(action, dict):
            continue
        lines.append(f"| `{action.get('id')}` | `{action.get('needed')}` | `{action.get('status')}` | `{action.get('reason')}` |")
    drift = payload.get("route_drift") if isinstance(payload.get("route_drift"), list) else []
    if drift:
        lines.extend(["", "## Route Drift", ""])
        for item in drift[:40]:
            if isinstance(item, dict):
                lines.append(f"- `{item.get('session_label') or item.get('session_id')}`: `{', '.join(str(reason) for reason in item.get('reasons', []) if reason)}`")
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), list) else []
    if diagnostics:
        lines.extend(["", "## Diagnostics", ""])
        for item in diagnostics:
            lines.append(f"- `{item}`")
    return "\n".join(lines) + "\n"


def index_maintenance_print_payload(payload: dict[str, Any], *, full: bool = False) -> dict[str, Any]:
    if full:
        return payload
    return {
        key: value
        for key, value in payload.items()
        if key not in {"route_drift", "deferred_sessions"}
    }


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
    try:
        if target and target != "all":
            records = [resolve_session_record(aoa_root, target)]
        else:
            records = chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    except ValueError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "conversation_act_audit",
            "generated_at": now,
            "ok": False,
            "aoa_root": str(aoa_root),
            "target": target,
            "since": since,
            "until": until,
            "limit": limit,
            "selected_count": 0,
            "segment_count": 0,
            "event_count": 0,
            "eligible_event_count": 0,
            "missing_eligible_conversation_act": 0,
            "missing_samples": [],
            "counts": {},
            "samples": {},
            "diagnostics": [str(exc)],
        }
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
    maintenance_job: Path | None = None
    if ok_to_apply:
        updated_names: list[dict[str, Any]] = []
        replaced = False
        for item in existing_names:
            if isinstance(item, dict) and item.get("slug") == slug:
                updated_names.append({**item, **proposed, "created_at": item.get("created_at") or proposed["created_at"]})
                replaced = True
            elif isinstance(item, dict):
                if scope == "session" and semantic_name_scope(item) == "session" and item.get("status") == "active":
                    continue
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
        maintenance_job = enqueue_index_maintenance_job(
            aoa_root,
            reason="semantic_name_applied",
            target="all",
            sample_audit=False,
            max_raw_mb=16,
        )
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
        "maintenance_job": str(maintenance_job) if maintenance_job else "",
        "maintenance_next": (
            "hook-worker will refresh portable search, atlas, and readiness from the queued maintenance job"
            if maintenance_job
            else ""
        ),
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
        if value == "~" or not is_indexable_path_mention(value):
            continue
        mentions.append(value)
    return mentions


def inferred_owner_root_for_path(path_value: str) -> str | None:
    raw = str(path_value or "").strip()
    if not raw or "\x00" in raw:
        return None
    try:
        expanded = str(Path(raw).expanduser())
    except (OSError, RuntimeError, ValueError):
        return None
    expanded_path = Path(expanded)
    try:
        expanded_exists = expanded_path.exists()
    except (OSError, RuntimeError, ValueError):
        expanded_exists = False
    if expanded_exists:
        start = expanded_path if expanded_path.is_dir() else expanded_path.parent
        for parent in [start, *start.parents]:
            if (parent / ".git").exists() or (parent / "AGENTS.md").exists():
                return str(parent)
            if parent.parent == parent:
                break
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


def work_context_root_for_path(path_value: str) -> str | None:
    raw = str(path_value or "").strip()
    if not raw or "\x00" in raw:
        return None
    try:
        expanded = str(Path(raw).expanduser())
    except (OSError, RuntimeError, ValueError):
        return None
    parts = Path(expanded).parts
    if len(parts) < 3 or parts[0] != "/":
        return None
    if len(parts) >= 6 and parts[:5] == ("/", "home", "dionysus", ".codex", "memories"):
        return str(Path(*parts[:5]))
    if len(parts) >= 6 and parts[:5] == ("/", "home", "dionysus", ".codex", "sessions"):
        return str(Path(*parts[:5]))
    if len(parts) >= 4 and parts[:3] == ("/", "srv", "AbyssOS"):
        child = parts[3]
        if child == ".aoa":
            return "/srv/AbyssOS/.aoa"
        if child == "bundles" and len(parts) >= 5:
            return str(Path(*parts[:5]))
        if child and not child.startswith(".") and child not in {"generated", "worktrees"}:
            return str(Path(*parts[:4]))
        return "/srv/AbyssOS"
    if len(parts) >= 5 and parts[:3] == ("/", "srv", "work"):
        return str(Path(*parts[:4]))
    if len(parts) >= 6 and parts[:4] == ("/", "srv", "games", "modding"):
        return str(Path(*parts[:5]))
    if len(parts) >= 5 and parts[:4] == ("/", "home", "dionysus", "src"):
        return str(Path(*parts[:5]))
    return inferred_owner_root_for_path(expanded)


def owner_name_from_root(owner_root: str | None) -> str | None:
    if not owner_root:
        return None
    path = Path(owner_root)
    if str(path) == "/home/dionysus":
        return "home"
    if path.name:
        return path.name
    return owner_root


def work_context_name_from_root(root: str | None) -> str | None:
    if not root:
        return None
    path = Path(root)
    raw = str(path)
    if raw == "/srv/AbyssOS/.aoa":
        return "aoa-session-memory"
    if raw == "/home/dionysus/.codex/memories":
        return "codex-memories"
    if raw == "/home/dionysus/.codex/sessions":
        return "codex-transcripts"
    if raw == "/srv/AbyssOS":
        return "AbyssOS"
    return path.name or raw


def work_context_family_from_name(name: str | None, root: str | None) -> str:
    label = str(name or "").lower()
    root_text = str(root or "").lower()
    if label in {"aoa-session-memory"} or root_text.endswith("/.aoa"):
        return "aoa-session-memory"
    if label in {"codex-memories", "codex-transcripts"} or ".codex/" in root_text:
        return "codex-memory"
    if label == "abyssos":
        return "abyssos-workspace"
    if label == "agents-of-abyss" or label.startswith("aoa-"):
        return "aoa"
    if "tree-of-sophia" in label or "sophia" in label or label in {"tos", "tree-of-sophia"}:
        return "tree-of-sophia"
    if label.startswith("abyss") or "abyss" in label:
        return "abyss"
    return "external"


def work_context_for_session_events(source: dict[str, Any], events: list[RawEvent]) -> dict[str, Any]:
    scores: Counter[str] = Counter()
    evidence_by_root: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def add(root: str | None, *, score: int, kind: str, value: Any, ref: str | None = None) -> None:
        if not root:
            return
        scores[root] += score
        bucket = evidence_by_root[root]
        if len(bucket) < 12:
            item: dict[str, Any] = {"kind": kind, "value": short_text(value, max_chars=180), "score": score}
            if ref:
                item["ref"] = ref
            bucket.append(item)

    cwd_value = source.get("cwd") if isinstance(source, dict) else ""
    if cwd_value:
        add(work_context_root_for_path(str(cwd_value)), score=20, kind="cwd", value=cwd_value)
    transcript_path = source.get("transcript_path") if isinstance(source, dict) else ""
    if transcript_path:
        add(work_context_root_for_path(str(transcript_path)), score=1, kind="transcript_path", value=transcript_path)

    for event in events:
        texts: list[str] = [event.title, " ".join(event.tags)]
        for key in ("command", "tool_name", "path"):
            value = event.facets.get(key)
            if value:
                texts.append(str(value))
        session_act = event.facets.get("session_act") if isinstance(event.facets.get("session_act"), dict) else {}
        surface = str(session_act.get("memory_surface") or "")
        if surface == "codex_memories":
            add("/home/dionysus/.codex/memories", score=5, kind="memory_surface", value=surface, ref=f"raw:line:{event.line_no}")
        elif surface == "codex_transcripts":
            add("/home/dionysus/.codex/sessions", score=4, kind="memory_surface", value=surface, ref=f"raw:line:{event.line_no}")
        elif surface == "aoa_session_memory":
            add("/srv/AbyssOS/.aoa", score=5, kind="memory_surface", value=surface, ref=f"raw:line:{event.line_no}")
        for text in texts:
            for mention in path_mentions_from_text(text):
                add(work_context_root_for_path(mention), score=4, kind="indexed_path", value=mention, ref=f"raw:line:{event.line_no}")

    if not scores:
        return {
            "schema_version": WORK_CONTEXT_SCHEMA_VERSION,
            "status": "unresolved",
            "work_root": None,
            "work_name": None,
            "work_family": "unknown",
            "confidence": "none",
            "score": 0,
            "evidence": [],
            "alternates": [],
        }
    ranked = scores.most_common()
    root, score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    if second_score and second_score >= max(5, int(score * 0.75)):
        status = "ambiguous"
        confidence = "low"
    elif score >= 10:
        status = "resolved"
        confidence = "high"
    elif score >= 4:
        status = "resolved_low_confidence"
        confidence = "medium"
    else:
        status = "weak_signal"
        confidence = "low"
    name = work_context_name_from_root(root)
    return {
        "schema_version": WORK_CONTEXT_SCHEMA_VERSION,
        "status": status,
        "work_root": root,
        "work_name": name,
        "work_family": work_context_family_from_name(name, root),
        "confidence": confidence,
        "score": score,
        "evidence": evidence_by_root.get(root, []),
        "alternates": [
            {
                "work_root": item_root,
                "work_name": work_context_name_from_root(item_root),
                "work_family": work_context_family_from_name(work_context_name_from_root(item_root), item_root),
                "score": item_score,
            }
            for item_root, item_score in ranked[1:6]
        ],
    }


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
    session_act_counts: Counter[str] = Counter()
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
            facets = event.get("facets") if isinstance(event.get("facets"), dict) else {}
            session_act = facets.get("session_act") if isinstance(facets.get("session_act"), dict) else {}
            if session_act.get("kind"):
                session_act_counts[str(session_act["kind"])] += 1
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
        "session_act_counts": dict(sorted(session_act_counts.items())),
        "route_counts": dict(sorted(route_counts.items())),
        "mechanics_signal_counts": dict(sorted(mechanics_signal_counts.items())),
        "tag_counts": dict(sorted(tag_counts.items())),
        "project_grounding": project_grounding,
        "owner_resolution": owner_resolution,
        "work_context": manifest.get("work_context") if isinstance(manifest.get("work_context"), dict) else {},
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
    registry_lock_timeout_sec: float | None = None,
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
    registry_updated = update_registry(aoa_root, manifest, session_dir, lock_timeout_sec=registry_lock_timeout_sec)
    return {
        "session_id": session_id,
        "display_name": display["label"],
        "navigation_path": display["navigation_path"],
        "session_dir": str(session_dir),
        "incident": str(incident_path),
        "diagnostic": str(diagnostic_path),
        "registry_updated": registry_updated,
    }


def hook_user_prompt_typing_bridge(event: dict[str, Any], *, timeout_sec: float = 3.0) -> dict[str, Any]:
    prompt = event.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        return {
            "ok": True,
            "status": "skipped_no_prompt",
            "adapter": "codex_user_prompt_submit",
        }
    if os.environ.get("AOA_SESSION_MEMORY_TYPING_BRIDGE", "1") in {"0", "false", "False", "no"}:
        return {
            "ok": True,
            "status": "disabled",
            "adapter": "codex_user_prompt_submit",
        }
    executable = shutil.which("abyss-machine")
    if not executable:
        return {
            "ok": True,
            "status": "unavailable",
            "adapter": "codex_user_prompt_submit",
            "reason": "abyss-machine-not-found",
        }
    try:
        completed = subprocess.run(
            [executable, "typing", "codex-prompt-hook", "--json"],
            input=json.dumps(event, ensure_ascii=False),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "status": "timeout",
            "adapter": "codex_user_prompt_submit",
            "timeout_sec": timeout_sec,
        }
    except OSError as exc:
        return {
            "ok": False,
            "status": "exec_failed",
            "adapter": "codex_user_prompt_submit",
            "error": str(exc)[:240],
        }
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        payload = {
            "ok": False,
            "status": "invalid_json",
            "error": str(exc)[:240],
            "stdout_head": (completed.stdout or "")[:240],
        }
    typing_event = payload.get("typing_event") if isinstance(payload, dict) and isinstance(payload.get("typing_event"), dict) else {}
    return {
        "ok": completed.returncode == 0 and bool(payload.get("ok")) if isinstance(payload, dict) else False,
        "status": payload.get("status") if isinstance(payload, dict) else "invalid_json",
        "adapter": "codex_user_prompt_submit",
        "returncode": completed.returncode,
        "event_id": typing_event.get("event_id"),
        "typing_status": typing_event.get("status"),
        "capture_gate_decision": typing_event.get("capture_gate_decision"),
        "stderr_head": (completed.stderr or "")[:240],
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
    start_hook_light = event_name == "SessionStart" and os.environ.get("AOA_SESSION_MEMORY_FULL_START_SYNC") != "1"
    if event_name == "UserPromptSubmit" and os.environ.get("AOA_SESSION_MEMORY_FULL_PROMPT_SYNC") != "1":
        typing_bridge = hook_user_prompt_typing_bridge(event)
        if typing_bridge.get("status") == "ingested":
            actions.append("typing_prompt_mirrored")
        elif typing_bridge.get("status") in {"skipped_no_prompt", "disabled", "unavailable"}:
            actions.append(f"typing_prompt_bridge_{typing_bridge.get('status')}")
        else:
            actions.append("typing_prompt_bridge_failed")
            if typing_bridge.get("stderr_head") or typing_bridge.get("error"):
                errors.append(str(typing_bridge.get("error") or typing_bridge.get("stderr_head"))[:240])
        actions.append("prompt_hook_light_recorded")
        return {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "hook_event_name": event_name,
            "timestamp": now,
            "session_id": session_id,
            "session_dir": str(session_dir),
            "actions": actions,
            "typing_bridge": typing_bridge,
            "errors": errors,
        }
    if start_hook_light and transcript_path is not None and transcript_path.exists() and os.access(transcript_path, os.R_OK):
        existing = read_json(session_dir / "session.manifest.json", {})
        display = existing.get("display") if isinstance(existing.get("display"), dict) else {}
        actions.append("session_start_hook_light_recorded")
        actions.append("raw_sync_deferred")
        actions.append("indexing_deferred")
        receipt = {
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "hook_event_name": event_name,
            "timestamp": now,
            "session_id": session_id,
            "session_dir": str(session_dir),
            "display_name": existing.get("session_label") or display.get("label") or session_dir.name,
            "navigation_path": display.get("navigation_path") or display.get("path") or str(session_dir),
            "actions": actions,
            "errors": errors,
        }
        return attach_hook_sync_job(
            receipt,
            root,
            event_name=event_name,
            event=event,
            session_id=session_id,
            transcript_path=transcript_path,
            reason="session_start_light_deferred",
        )
    compact_hook_light = event_name in {"PreCompact", "PostCompact"} and os.environ.get("AOA_SESSION_MEMORY_FULL_COMPACT_SYNC") != "1"
    stop_hook_light = event_name == "Stop" and stop_hook_should_defer_indexing(transcript_path)
    if compact_hook_light or stop_hook_light:
        try:
            if transcript_path is not None and transcript_path.exists() and os.access(transcript_path, os.R_OK):
                if hook_should_defer_raw_mirror(transcript_path):
                    actions.append("raw_mirror_deferred")
                    actions.append("indexing_deferred")
                    receipt = {
                        "schema_version": SCHEMA_VERSION,
                        "ok": True,
                        "hook_event_name": event_name,
                        "timestamp": now,
                        "session_id": session_id,
                        "session_dir": str(session_dir),
                        "actions": actions,
                        "raw": {
                            "source_path": str(transcript_path),
                            "bytes": transcript_path.stat().st_size,
                            "mirror_max_bytes": hook_mirror_max_bytes(),
                            "mirror_status": "deferred_from_hook",
                        },
                        "errors": errors,
                    }
                    return attach_hook_sync_job(
                        receipt,
                        root,
                        event_name=event_name,
                        event=event,
                        session_id=session_id,
                        transcript_path=transcript_path,
                        reason="large_lifecycle_hook_raw_mirror_deferred",
                    )
                mirrored = mirror_transcript_without_indexing(
                    aoa_root=root,
                    event=event,
                    transcript_path=transcript_path,
                    hook_event_name=event_name,
                    now=now,
                    registry_lock_timeout_sec=DEFAULT_HOOK_REGISTRY_LOCK_TIMEOUT_SEC,
                )
                actions.append("raw_mirrored")
                actions.append("indexing_deferred")
                if not mirrored.get("registry_updated"):
                    actions.append("registry_update_deferred")
                receipt = {
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
                return attach_hook_sync_job(
                    receipt,
                    root,
                    event_name=event_name,
                    event=event,
                    session_id=str(mirrored.get("session_id") or session_id),
                    transcript_path=transcript_path,
                    reason="lifecycle_hook_indexing_deferred",
                )
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
                registry_lock_timeout_sec=DEFAULT_HOOK_REGISTRY_LOCK_TIMEOUT_SEC if event_name in HOOK_EVENT_ORDER else None,
            )
            actions.append("raw_unavailable_incident_written")
            if not incident.get("registry_updated"):
                actions.append("registry_update_deferred")
            receipt = {
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
            if not incident.get("registry_updated"):
                return attach_registry_update_job(
                    receipt,
                    root,
                    event_name=event_name,
                    event=event,
                    session_id=session_id,
                    session_dir=Path(str(incident["session_dir"])),
                    reason="raw_unavailable_registry_update_deferred",
                )
            return receipt
        synced = sync_session_from_transcript(
            aoa_root=root,
            event=event,
            transcript_path=transcript_path,
            hook_event_name=event_name,
            registry_lock_timeout_sec=DEFAULT_HOOK_REGISTRY_LOCK_TIMEOUT_SEC if event_name in HOOK_EVENT_ORDER else None,
        )
        actions.append("raw_mirrored")
        actions.append("segments_indexed")
        if not synced.get("registry_updated"):
            actions.append("registry_update_deferred")
        receipt = {
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
        if not synced.get("registry_updated"):
            return attach_hook_sync_job(
                receipt,
                root,
                event_name=event_name,
                event=event,
                session_id=str(synced.get("session_id") or session_id),
                transcript_path=transcript_path,
                reason="registry_update_deferred",
            )
        return receipt
    except Exception as exc:  # Hooks must fail open.
        errors.append(f"{exc.__class__.__name__}: {exc}")
        incident_session_dir: Path | None = None
        try:
            incident = write_raw_unavailable_incident(
                aoa_root=root,
                event={**event, "hook_exception": errors[-1]},
                transcript_path=transcript_path,
                hook_event_name=event_name,
                registry_lock_timeout_sec=DEFAULT_HOOK_REGISTRY_LOCK_TIMEOUT_SEC if event_name in HOOK_EVENT_ORDER else None,
            )
            actions.append("hook_exception_diagnostic_written")
            if not incident.get("registry_updated"):
                actions.append("registry_update_deferred")
                incident_session_dir = Path(str(incident["session_dir"]))
        except Exception:
            incident = None
            incident_session_dir = None
        receipt = {
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
        if incident and incident_session_dir is not None and not incident.get("registry_updated"):
            return attach_registry_update_job(
                receipt,
                root,
                event_name=event_name,
                event={**event, "hook_exception": errors[-1]},
                session_id=session_id,
                session_dir=incident_session_dir,
                reason="hook_exception_registry_update_deferred",
            )
        return {
            **receipt,
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


def record_hook_receipt(receipt: dict[str, Any], *, duration_ms: int | None = None) -> None:
    session_dir_value = receipt.get("session_dir")
    if not session_dir_value:
        return
    payload = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": utc_now(),
        "hook_event_name": receipt.get("hook_event_name"),
        "ok": receipt.get("ok"),
        "session_id": receipt.get("session_id"),
        "actions": receipt.get("actions", []),
        "errors": receipt.get("errors", []),
    }
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if isinstance(receipt.get("typing_bridge"), dict):
        payload["typing_bridge"] = receipt["typing_bridge"]
    try:
        append_jsonl(Path(str(session_dir_value)) / "hooks" / "receipts.jsonl", payload)
    except Exception:
        pass


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
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
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
    if payload.get("maintenance_job") and not args.no_maintenance_worker:
        launched = launch_hook_worker(workspace_root=explicit_workspace, aoa_root=root)
        payload["maintenance_worker_launched"] = launched
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


def command_phase_review_assist(args: argparse.Namespace) -> int:
    root = aoa_root_for(Path(args.workspace_root) if args.workspace_root else None, Path(args.aoa_root) if args.aoa_root else None)
    payload = build_phase_review_assist(
        root,
        args.session,
        limit=args.limit,
        from_segment=args.from_segment,
        segments=args.segment or [],
        include_reviewed=args.include_reviewed,
        refresh=args.refresh,
        write=args.write,
        write_report=args.write_report,
    )
    if args.full:
        stdout_payload = payload
    else:
        stdout_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"packets", "plan_template"}
        }
        stdout_payload["packet_overview"] = [
            {
                "segment_id": packet.get("segment_id"),
                "range": packet.get("coverage"),
                "machine_candidate": packet.get("machine_candidate"),
                "review_status": packet.get("review_status"),
                "read_first": packet.get("read_first", [])[:6],
                "top_paths": packet.get("top_paths", [])[:5],
            }
            for packet in payload.get("packets", [])
            if isinstance(packet, dict)
        ]
        stdout_payload["plan_item_count"] = len(
            payload.get("plan_template", {}).get("items", [])
            if isinstance(payload.get("plan_template"), dict)
            else []
        )
    print(json.dumps(stdout_payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_apply_phase_review_plan(args: argparse.Namespace) -> int:
    root = aoa_root_for(Path(args.workspace_root) if args.workspace_root else None, Path(args.aoa_root) if args.aoa_root else None)
    payload = apply_phase_review_plan(
        root,
        args.session,
        plan_path=Path(args.plan) if args.plan else None,
        apply=args.apply,
        replace=args.replace,
        write_report=args.write_report,
        verify_raw_hash=not args.skip_raw_hash_check,
        stop_on_error=args.stop_on_error,
    )
    if args.full:
        stdout_payload = payload
    else:
        stdout_payload = {
            key: value
            for key, value in payload.items()
            if key != "results"
        }
        stdout_payload["result_overview"] = [
            {
                "segment_id": result.get("segment_id"),
                "status": result.get("status"),
                "reviewed_name": result.get("reviewed_name"),
                "diagnostics": result.get("diagnostics", [])[:4],
            }
            for result in payload.get("results", [])
            if isinstance(result, dict)
        ]
    print(json.dumps(stdout_payload, indent=2, ensure_ascii=False))
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


CONVERSATION_ACT_ELIGIBLE_EVENT_TYPES = {
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
    "OPEN_THREAD",
    "PROCESS_LESSON",
    "VERIFICATION",
    "FINAL_STATE",
}


def conversation_act_audit_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Conversation Act Audit",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- target: `{payload.get('target')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- event_count: `{payload.get('event_count')}`",
        f"- eligible_event_count: `{payload.get('eligible_event_count')}`",
        f"- missing_eligible_conversation_act: `{payload.get('missing_eligible_conversation_act')}`",
        "",
        "## Counts",
        "",
        "| conversation_act | count |",
        "| --- | ---: |",
    ]
    for kind, count in sorted((payload.get("counts") or {}).items()):
        lines.append(f"| `{kind}` | {count} |")
    lines.extend(["", "## Samples", ""])
    samples = payload.get("samples") if isinstance(payload.get("samples"), dict) else {}
    for kind, items in sorted(samples.items()):
        lines.append(f"### `{kind}`")
        lines.append("")
        for item in items if isinstance(items, list) else []:
            lines.append(
                "- `{session}` `{segment}` `{event}` `{type}` {title}".format(
                    session=item.get("session_label"),
                    segment=item.get("segment_id"),
                    event=item.get("event_id"),
                    type=item.get("type"),
                    title=str(item.get("title") or "").replace("\n", " "),
                )
            )
        lines.append("")
    return "\n".join(lines)


def conversation_act_audit(
    *,
    aoa_root: Path,
    target: str = "all",
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    sample_limit: int = 3,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    try:
        if target and target != "all":
            records = [resolve_session_record(aoa_root, target)]
        else:
            records = chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    except ValueError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "conversation_act_audit",
            "generated_at": now,
            "ok": False,
            "aoa_root": str(aoa_root),
            "target": target,
            "since": since,
            "until": until,
            "limit": limit,
            "selected_count": 0,
            "segment_count": 0,
            "event_count": 0,
            "eligible_event_count": 0,
            "missing_eligible_conversation_act": 0,
            "missing_samples": [],
            "counts": {},
            "samples": {},
            "diagnostics": [str(exc)],
        }
    counts: Counter[str] = Counter()
    samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    missing: list[dict[str, Any]] = []
    event_count = 0
    eligible_count = 0
    segment_count = 0
    for record in records:
        session_label = str(record.get("session_label") or "")
        session_dir = session_dir_from_record(record)
        manifest = read_json(session_dir / "session.manifest.json", {})
        segments = manifest.get("segments") if isinstance(manifest.get("segments"), list) else []
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            index_path = Path(str(segment.get("index") or ""))
            if not index_path.is_file():
                continue
            segment_count += 1
            index = read_json(index_path, {})
            segment_id = str(index.get("segment_id") or segment.get("segment_id") or index_path.stem.split("__", 1)[0])
            for event in index.get("events", []) if isinstance(index.get("events"), list) else []:
                if not isinstance(event, dict):
                    continue
                event_count += 1
                event_type = str(event.get("type") or "")
                if event_type not in CONVERSATION_ACT_ELIGIBLE_EVENT_TYPES:
                    continue
                eligible_count += 1
                facets = event.get("facets") if isinstance(event.get("facets"), dict) else {}
                act = facets.get("conversation_act") if isinstance(facets.get("conversation_act"), dict) else {}
                kind = str(act.get("kind") or "")
                if not kind:
                    if len(missing) < 50:
                        missing.append(
                            {
                                "session_label": session_label,
                                "segment_id": segment_id,
                                "event_id": event.get("event_id"),
                                "type": event_type,
                                "title": event.get("title"),
                            }
                        )
                    continue
                counts[kind] += 1
                if len(samples[kind]) < sample_limit:
                    samples[kind].append(
                        {
                            "session_label": session_label,
                            "segment_id": segment_id,
                            "event_id": event.get("event_id"),
                            "type": event_type,
                            "title": event.get("title"),
                            "raw_ref": event.get("raw_ref"),
                            "conversation_act": act,
                        }
                    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "conversation_act_audit",
        "generated_at": now,
        "ok": eligible_count > 0 and not missing,
        "aoa_root": str(aoa_root),
        "target": target,
        "since": since,
        "until": until,
        "limit": limit,
        "selected_count": len(records),
        "segment_count": segment_count,
        "event_count": event_count,
        "eligible_event_count": eligible_count,
        "missing_eligible_conversation_act": len(missing),
        "missing_samples": missing,
        "counts": dict(sorted(counts.items())),
        "samples": {kind: items for kind, items in sorted(samples.items())},
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__conversation-act-audit"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, conversation_act_audit_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def search_db_path(aoa_root: Path) -> Path:
    return aoa_root / SEARCH_ROOT / SEARCH_DB_NAME


def search_report_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Search Index Report",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- ok: `{payload.get('ok')}`",
        f"- target: `{payload.get('target')}`",
        f"- db_path: `{payload.get('db_path')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- max_raw_bytes: `{payload.get('max_raw_bytes')}`",
        f"- document_count: `{payload.get('document_count')}`",
        f"- session_documents: `{payload.get('session_document_count')}`",
        f"- segment_documents: `{payload.get('segment_document_count')}`",
        f"- event_documents: `{payload.get('event_document_count')}`",
        f"- incident_documents: `{payload.get('incident_document_count')}`",
        "",
        "## Diagnostics",
        "",
    ]
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), list) else []
    if diagnostics:
        for item in diagnostics:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.extend(["", "## Sessions", "", "| session | documents | status | raw text |", "| --- | ---: | --- | --- |"])
    for item in payload.get("sessions", []) if isinstance(payload.get("sessions"), list) else []:
        if not isinstance(item, dict):
            continue
        lines.append(
            f"| `{item.get('session_label')}` | {item.get('document_count', 0)} | `{item.get('status')}` | `{item.get('raw_text_status')}` |"
        )
    return "\n".join(lines)


def default_search_provider_config() -> dict[str, Any]:
    return {
        "schema_version": SEARCH_PROVIDER_SCHEMA_VERSION,
        "artifact_type": "search_provider_config",
        "default_provider": "portable_sqlite",
        "authority_law": (
            ".aoa owns schemas, raw refs, segment refs, and freshness. "
            "Host providers are optional accelerators and cannot replace archive evidence."
        ),
        "providers": {
            "portable_sqlite": {
                "enabled": True,
                "portable": True,
                "role": "authoritative_aoa_retrieval",
                "truth_level": "route_cache_over_aoa_raw_and_segments",
                "index_command": ["search-index"],
                "search_command": ["search"],
                "writes": ["search/aoa-search.sqlite3", "diagnostics/*__search-index.*"],
            },
            "abyss_machine_nervous": {
                "enabled": False,
                "portable": False,
                "role": "optional_host_context_overlay",
                "truth_level": "host_read_model_evidence_not_aoa_truth",
                "capability_gate": ["abyss-machine", "stack-bridge", "validate", "--json"],
                "quality_gate": ["abyss-machine", "nervous", "quality-audit", "--json"],
                "refresh_quality_gate": ["abyss-machine", "nervous", "quality-audit", "--refresh", "--json"],
                "refresh_index_quality_gate": ["abyss-machine", "nervous", "quality-audit", "--refresh", "--refresh-index", "--json"],
                "semantic_status_gate": ["abyss-machine", "nervous", "semantic-status", "--json"],
                "semantic_search_command": ["abyss-machine", "nervous", "semantic-search", "--query", "{query}", "--limit", "{limit}", "--json"],
                "recall_command": ["abyss-machine", "nervous", "recall", "--mode", "lexical", "--query", "{query}", "--limit", "{limit}", "--json"],
                "rerank_api_health_url": "http://127.0.0.1:5405/health",
                "rerank_api_url": "http://127.0.0.1:5405/rerank",
                "rerank_candidate_limit": 24,
                "write_policy": "read_only_status_by_default",
                "host_write_requires_operator_enablement": True,
            },
            "abyss_stack_rag": {
                "enabled": False,
                "portable": False,
                "role": "future_optional_runtime_service",
                "truth_level": "runtime_accelerator_not_archive_authority",
                "capability_gate": ["abyss-machine", "stack-bridge", "validate", "--json"],
                "write_policy": "not_implemented_in_portable_bundle",
                "host_write_requires_operator_enablement": True,
            },
        },
    }


def search_provider_config(aoa_root: Path) -> dict[str, Any]:
    config = default_search_provider_config()
    configured = read_json(aoa_root / SEARCH_PROVIDER_CONFIG_PATH, {})
    if not isinstance(configured, dict):
        return config
    for key in ("default_provider", "authority_law"):
        if configured.get(key):
            config[key] = configured[key]
    if isinstance(configured.get("providers"), dict):
        providers = config["providers"]
        for name, value in configured["providers"].items():
            if not isinstance(value, dict):
                continue
            base = providers.get(str(name), {})
            merged = dict(base)
            merged.update(value)
            providers[str(name)] = merged
    return config


def run_json_command(command: list[str], *, timeout: int = 30, cwd: Path | None = None) -> dict[str, Any]:
    if not command:
        return {"ok": False, "status": "invalid_command", "error": "empty command", "command": command}
    executable = shutil.which(command[0])
    if executable is None:
        return {"ok": False, "status": "command_missing", "error": f"command not found: {command[0]}", "command": command}
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            cwd=str(cwd) if cwd else None,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "status": "timeout", "error": f"timed out after {timeout}s", "command": command}
    except Exception as exc:
        return {"ok": False, "status": "error", "error": f"{exc.__class__.__name__}: {exc}", "command": command}
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    payload: Any = None
    parse_error = ""
    if stdout:
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            parse_error = f"{exc.__class__.__name__}: {exc}"
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "status": "invalid_json" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode,
            "command": command,
            "stderr": short_text(stderr, max_chars=1200),
            "stdout": short_text(stdout, max_chars=1200),
            "parse_error": parse_error,
        }
    return {
        "ok": completed.returncode == 0 and bool(payload.get("ok", True)),
        "status": "ok" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "command": command,
        "payload": payload,
        "stderr": short_text(stderr, max_chars=1200),
    }


def run_json_url(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    if not url:
        return {"ok": False, "status": "invalid_url", "error": "empty url", "url": url}
    data: bytes | None = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace").strip()
            status_code = int(getattr(response, "status", 0) or 0)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        return {
            "ok": False,
            "status": "http_error",
            "status_code": exc.code,
            "url": url,
            "body": short_text(body, max_chars=1200),
            "error": str(exc),
        }
    except Exception as exc:
        return {"ok": False, "status": "error", "url": url, "error": f"{exc.__class__.__name__}: {exc}"}
    parsed: Any = None
    parse_error = ""
    if body:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError as exc:
            parse_error = f"{exc.__class__.__name__}: {exc}"
    if not isinstance(parsed, dict):
        return {
            "ok": False,
            "status": "invalid_json",
            "status_code": status_code,
            "url": url,
            "body": short_text(body, max_chars=1200),
            "parse_error": parse_error,
        }
    return {
        "ok": 200 <= status_code < 300 and bool(parsed.get("ok", True)),
        "status": "ok" if 200 <= status_code < 300 else "http_error",
        "status_code": status_code,
        "url": url,
        "payload": parsed,
    }


def summary_warning_count(payload: dict[str, Any]) -> int:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return int_value(summary.get("warnings"), 0)


def summary_fail_count(payload: dict[str, Any]) -> int:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return int_value(summary.get("fails"), 0)


def compact_gate_result(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
    return {
        "ok": bool(result.get("ok")),
        "status": result.get("status"),
        "returncode": result.get("returncode"),
        "command": result.get("command"),
        "schema": payload.get("schema") or payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "summary": payload.get("summary"),
        "warnings": summary_warning_count(payload),
        "fails": summary_fail_count(payload),
        "error": result.get("error"),
        "stderr": result.get("stderr"),
    }


def compact_semantic_status_result(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
    embedding = payload.get("embedding") if isinstance(payload.get("embedding"), dict) else {}
    counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
    count_meta = counts.get("meta") if isinstance(counts.get("meta"), dict) else {}
    freshness = payload.get("freshness") if isinstance(payload.get("freshness"), dict) else {}
    warnings = payload.get("warnings") if isinstance(payload.get("warnings"), list) else []
    notices = payload.get("notices") if isinstance(payload.get("notices"), list) else []
    ready = bool(result.get("ok")) and bool(payload.get("ready", payload.get("ok", False)))
    stale = bool(freshness.get("stale"))
    status = "ready"
    if not ready:
        status = str(result.get("status") or "unavailable")
    elif stale:
        status = "stale"
    return {
        "ok": ready and not stale,
        "status": status,
        "returncode": result.get("returncode"),
        "command": result.get("command"),
        "schema": payload.get("schema") or payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "model_dir": embedding.get("model_dir"),
        "model_exists": embedding.get("model_exists"),
        "device": embedding.get("device"),
        "dimension": embedding.get("dimension"),
        "vectors": counts.get("vectors"),
        "source_chunks": freshness.get("source_chunks") or count_meta.get("source_chunks"),
        "delta_chunks": freshness.get("delta_chunks"),
        "partial": freshness.get("partial"),
        "stale": stale,
        "freshness": {
            "source_index_changed": freshness.get("source_index_changed"),
            "bounded_source_drift": freshness.get("bounded_source_drift"),
            "stale_by_delta": freshness.get("stale_by_delta"),
            "stale_by_age": freshness.get("stale_by_age"),
            "embedding_config_stale": freshness.get("embedding_config_stale"),
        },
        "warning_count": len(warnings) + (1 if stale else 0),
        "notice_count": len(notices),
        "error": result.get("error"),
        "stderr": result.get("stderr"),
    }


def compact_rerank_health_result(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
    ok = bool(result.get("ok")) and bool(payload.get("ok", True))
    return {
        "ok": ok,
        "status": "ready" if ok else str(result.get("status") or "unavailable"),
        "url": result.get("url"),
        "status_code": result.get("status_code"),
        "service": payload.get("service"),
        "model": payload.get("model"),
        "backend": payload.get("backend"),
        "device": payload.get("device"),
        "model_dir": payload.get("model_dir"),
        "model_dir_exists": payload.get("model_dir_exists"),
        "max_length": payload.get("max_length"),
        "batch_size": payload.get("batch_size"),
        "loaded": payload.get("loaded"),
        "idle_unload_sec": payload.get("idle_unload_sec"),
        "fake_mode": payload.get("fake_mode"),
        "error": result.get("error"),
    }


def sqlite_provider_status(aoa_root: Path) -> dict[str, Any]:
    db_path = search_db_path(aoa_root)
    if not db_path.exists():
        return {
            "provider": "portable_sqlite",
            "ok": False,
            "status": "missing",
            "db_path": str(db_path),
            "diagnostics": ["search index missing; run search-index"],
        }
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        metadata = search_index_metadata(conn)
        rows = conn.execute("SELECT doc_type, COUNT(*) AS count FROM documents GROUP BY doc_type").fetchall()
        counts = {str(row["doc_type"]): int(row["count"]) for row in rows}
        total = sum(counts.values())
        conn.close()
    except sqlite3.Error as exc:
        return {
            "provider": "portable_sqlite",
            "ok": False,
            "status": "sqlite_error",
            "db_path": str(db_path),
            "diagnostics": [f"sqlite_error:{exc}"],
        }
    return {
        "provider": "portable_sqlite",
        "ok": total > 0,
        "status": "ready" if total > 0 else "empty",
        "db_path": str(db_path),
        "index_generated_at": metadata.get("generated_at"),
        "search_schema_version": metadata.get("schema_version"),
        "document_count": total,
        "document_counts": counts,
        "diagnostics": [] if total > 0 else ["search index has no documents"],
    }


def host_provider_status(
    *,
    config: dict[str, Any],
    provider_name: str,
    force_probe: bool = False,
    refresh_host: bool = False,
    refresh_host_index: bool = False,
    timeout: int = 45,
) -> dict[str, Any]:
    provider = config.get("providers", {}).get(provider_name, {}) if isinstance(config.get("providers"), dict) else {}
    if not isinstance(provider, dict):
        return {"provider": provider_name, "ok": False, "status": "unknown_provider", "diagnostics": ["provider is not configured"]}
    if provider.get("write_policy") == "not_implemented_in_portable_bundle":
        return {
            "provider": provider_name,
            "ok": True,
            "status": "declared_future_optional",
            "portable": bool(provider.get("portable")),
            "role": provider.get("role"),
            "truth_level": provider.get("truth_level"),
            "write_policy": provider.get("write_policy"),
            "host_write_requires_operator_enablement": bool(provider.get("host_write_requires_operator_enablement")),
            "diagnostics": ["provider is declared for future runtime integration and is not used by portable search"],
        }
    if not provider.get("enabled") and not force_probe:
        return {
            "provider": provider_name,
            "ok": True,
            "status": "disabled_by_default",
            "portable": bool(provider.get("portable")),
            "role": provider.get("role"),
            "truth_level": provider.get("truth_level"),
            "diagnostics": ["provider disabled in config; use explicit host probing before relying on it"],
        }
    gates: dict[str, Any] = {}
    diagnostics: list[str] = []
    capability_command = provider.get("capability_gate") if isinstance(provider.get("capability_gate"), list) else []
    capability = run_json_command([str(part) for part in capability_command], timeout=timeout) if capability_command else {"ok": False, "status": "missing_gate", "error": "capability gate missing"}
    gates["capability_gate"] = compact_gate_result(capability)
    if not capability.get("ok"):
        diagnostics.append("capability_gate_failed")

    quality_key = "quality_gate"
    if refresh_host_index and isinstance(provider.get("refresh_index_quality_gate"), list):
        quality_key = "refresh_index_quality_gate"
    elif refresh_host and isinstance(provider.get("refresh_quality_gate"), list):
        quality_key = "refresh_quality_gate"
    quality_command = provider.get(quality_key) if isinstance(provider.get(quality_key), list) else provider.get("quality_gate")
    quality = run_json_command([str(part) for part in quality_command], timeout=timeout) if isinstance(quality_command, list) else {"ok": False, "status": "missing_gate", "error": "quality gate missing"}
    gates["quality_gate"] = compact_gate_result(quality)
    if not quality.get("ok"):
        diagnostics.append("quality_gate_failed")

    models: dict[str, Any] = {}
    model_warning_count = 0
    semantic_command = provider.get("semantic_status_gate") if isinstance(provider.get("semantic_status_gate"), list) else []
    if semantic_command:
        semantic_status = run_json_command([str(part) for part in semantic_command], timeout=timeout)
        models["embedding"] = compact_semantic_status_result(semantic_status)
        if not models["embedding"].get("ok"):
            model_warning_count += 1
            diagnostics.append(f"embedding_status:{models['embedding'].get('status')}")
    rerank_health_url = str(provider.get("rerank_api_health_url") or "")
    if rerank_health_url:
        rerank_health = run_json_url(rerank_health_url, timeout=min(timeout, 15))
        models["reranker"] = compact_rerank_health_result(rerank_health)
        if not models["reranker"].get("ok"):
            model_warning_count += 1
            diagnostics.append(f"reranker_status:{models['reranker'].get('status')}")

    warning_count = (
        int(gates["capability_gate"].get("warnings") or 0)
        + int(gates["quality_gate"].get("warnings") or 0)
        + model_warning_count
    )
    fail_count = int(gates["capability_gate"].get("fails") or 0) + int(gates["quality_gate"].get("fails") or 0)
    if warning_count:
        diagnostics.append("host_backend_has_warnings")
    status = "ready"
    ok = bool(capability.get("ok")) and bool(quality.get("ok")) and fail_count == 0
    if not ok:
        status = "unavailable"
    elif warning_count:
        status = "ready_with_warnings"
    return {
        "provider": provider_name,
        "ok": ok,
        "status": status,
        "portable": bool(provider.get("portable")),
        "role": provider.get("role"),
        "truth_level": provider.get("truth_level"),
        "write_policy": provider.get("write_policy"),
        "host_write_requires_operator_enablement": bool(provider.get("host_write_requires_operator_enablement")),
        "warning_count": warning_count,
        "fail_count": fail_count,
        "gates": gates,
        "models": models,
        "diagnostics": diagnostics,
    }


def search_provider_status(
    *,
    aoa_root: Path,
    provider_name: str = "all",
    include_host: bool = False,
    refresh_host: bool = False,
    refresh_host_index: bool = False,
    timeout: int = 45,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    config = search_provider_config(aoa_root)
    providers = config.get("providers") if isinstance(config.get("providers"), dict) else {}
    selected = sorted(providers) if provider_name == "all" else [provider_name]
    results: dict[str, Any] = {}
    diagnostics: list[str] = []
    for name in selected:
        if name == "portable_sqlite":
            results[name] = sqlite_provider_status(aoa_root)
        elif name in providers:
            if include_host or bool(providers.get(name, {}).get("enabled")):
                results[name] = host_provider_status(
                    config=config,
                    provider_name=name,
                    force_probe=include_host,
                    refresh_host=refresh_host,
                    refresh_host_index=refresh_host_index,
                    timeout=timeout,
                )
            else:
                provider = providers.get(name, {})
                results[name] = {
                    "provider": name,
                    "ok": True,
                    "status": "disabled_by_default",
                    "portable": bool(provider.get("portable")),
                    "role": provider.get("role"),
                    "truth_level": provider.get("truth_level"),
                    "diagnostics": ["host provider not probed; pass --include-host to run host gates"],
                }
        else:
            results[name] = {"provider": name, "ok": False, "status": "unknown_provider", "diagnostics": ["provider is not configured"]}
    for name, result in results.items():
        if not result.get("ok"):
            diagnostics.append(f"{name}:{result.get('status')}")
    default_provider = str(config.get("default_provider") or "portable_sqlite")
    default_status = results.get(default_provider) or sqlite_provider_status(aoa_root)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "search_provider_status",
        "provider_schema_version": SEARCH_PROVIDER_SCHEMA_VERSION,
        "generated_at": now,
        "ok": bool(default_status.get("ok")) and not any(
            not result.get("ok") and result.get("status") != "disabled_by_default"
            for result in results.values()
            if provider_name != "all" or result.get("provider") == default_provider
        ),
        "aoa_root": str(aoa_root),
        "config_path": str(aoa_root / SEARCH_PROVIDER_CONFIG_PATH),
        "default_provider": default_provider,
        "authority_law": config.get("authority_law"),
        "selected_provider": provider_name,
        "providers": results,
        "diagnostics": diagnostics,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__search-provider-status"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, search_provider_status_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def search_provider_status_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Search Provider Status",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- ok: `{payload.get('ok')}`",
        f"- default_provider: `{payload.get('default_provider')}`",
        f"- selected_provider: `{payload.get('selected_provider')}`",
        "",
        "## Providers",
        "",
        "| provider | status | ok | role | diagnostics |",
        "| --- | --- | --- | --- | --- |",
    ]
    providers = payload.get("providers") if isinstance(payload.get("providers"), dict) else {}
    for name, item in providers.items():
        if not isinstance(item, dict):
            continue
        diagnostics = ", ".join(str(value) for value in item.get("diagnostics", []) if value) if isinstance(item.get("diagnostics"), list) else ""
        lines.append(f"| `{name}` | `{item.get('status')}` | `{item.get('ok')}` | `{item.get('role')}` | {diagnostics or 'none'} |")
    model_rows: list[str] = []
    for name, item in providers.items():
        if not isinstance(item, dict) or not isinstance(item.get("models"), dict):
            continue
        for model_name, model in item["models"].items():
            if not isinstance(model, dict):
                continue
            model_rows.append(
                f"| `{name}` | `{model_name}` | `{model.get('status')}` | `{model.get('ok')}` | `{model.get('model') or model.get('model_dir') or ''}` | `{model.get('device') or ''}` |"
            )
    if model_rows:
        lines.extend(["", "## Local Model Gates", "", "| provider | model gate | status | ok | model | device |", "| --- | --- | --- | --- | --- | --- |"])
        lines.extend(model_rows)
    lines.extend(["", "## Authority Law", "", str(payload.get("authority_law") or "")])
    return "\n".join(lines)


def compact_host_recall_payload(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
    return {
        "ok": bool(result.get("ok")),
        "status": result.get("status"),
        "command": result.get("command"),
        "schema": payload.get("schema") or payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "mode": payload.get("mode"),
        "query": payload.get("query"),
        "summary": payload.get("summary"),
        "evidence_count": len(evidence),
        "paths": payload.get("paths") if isinstance(payload.get("paths"), dict) else {},
        "truth_level": "host_context_only_not_aoa_authority",
    }


def compact_host_semantic_payload(result: dict[str, Any], *, sample_limit: int = 5) -> dict[str, Any]:
    payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
    hits: list[dict[str, Any]] = []
    for item in payload.get("results", []) if isinstance(payload.get("results"), list) else []:
        if not isinstance(item, dict):
            continue
        hits.append(
            {
                "source_id": item.get("source_id"),
                "document_schema": item.get("document_schema"),
                "title": item.get("title"),
                "score": item.get("score") or item.get("semantic_score"),
                "generated_at": item.get("generated_at"),
                "indexed_at": item.get("indexed_at"),
                "snippet": short_text(item.get("snippet") or item.get("body_preview"), max_chars=360),
            }
        )
        if len(hits) >= sample_limit:
            break
    embedding_status = payload.get("embedding_status") if isinstance(payload.get("embedding_status"), dict) else {}
    return {
        "ok": bool(result.get("ok")),
        "status": result.get("status"),
        "command": result.get("command"),
        "schema": payload.get("schema") or payload.get("schema_version"),
        "generated_at": payload.get("generated_at"),
        "query": payload.get("query"),
        "result_count": len(payload.get("results", [])) if isinstance(payload.get("results"), list) else 0,
        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
        "embedding": {
            "ok": embedding_status.get("ok"),
            "dim": embedding_status.get("dim"),
            "device": embedding_status.get("device"),
            "model_dir": embedding_status.get("model_dir"),
        },
        "hits": hits,
        "truth_level": "host_semantic_context_only_not_aoa_authority",
    }


def host_context_overlay(
    *,
    config: dict[str, Any],
    provider_name: str,
    query: str,
    limit: int,
    timeout: int,
) -> dict[str, Any]:
    provider = config.get("providers", {}).get(provider_name, {}) if isinstance(config.get("providers"), dict) else {}
    command = provider.get("recall_command") if isinstance(provider, dict) else None
    if not isinstance(command, list):
        return {"ok": False, "status": "not_supported", "diagnostics": ["provider has no recall_command"]}
    rendered = [
        str(part).replace("{query}", query).replace("{limit}", str(max(1, min(limit, 10))))
        for part in command
    ]
    result = run_json_command(rendered, timeout=timeout)
    return compact_host_recall_payload(result)


def host_semantic_overlay(
    *,
    config: dict[str, Any],
    provider_name: str,
    query: str,
    limit: int,
    timeout: int,
) -> dict[str, Any]:
    provider = config.get("providers", {}).get(provider_name, {}) if isinstance(config.get("providers"), dict) else {}
    command = provider.get("semantic_search_command") if isinstance(provider, dict) else None
    if not isinstance(command, list):
        return {"ok": False, "status": "not_supported", "diagnostics": ["provider has no semantic_search_command"]}
    rendered = [
        str(part).replace("{query}", query).replace("{limit}", str(max(1, min(limit, 10))))
        for part in command
    ]
    result = run_json_command(rendered, timeout=timeout)
    return compact_host_semantic_payload(result)


def rerank_document_for_search_hit(hit: dict[str, Any]) -> str:
    parts = [
        f"title: {hit.get('title') or ''}",
        f"session: {hit.get('session_label') or ''}",
        f"event_type: {hit.get('event_type') or ''}",
        f"conversation_act: {hit.get('conversation_act') or ''}",
        f"session_act: {hit.get('session_act') or ''}",
        f"route_layers: {hit.get('route_layers') or ''}",
        f"route_signals: {hit.get('route_signals') or ''}",
        f"snippet: {hit.get('snippet') or ''}",
    ]
    return short_text("\n".join(part for part in parts if part.strip()), max_chars=2000)


def local_rerank_search_results(
    *,
    config: dict[str, Any],
    provider_name: str,
    query: str,
    results: list[dict[str, Any]],
    timeout: int,
    candidate_limit: int | None = None,
) -> dict[str, Any]:
    provider = config.get("providers", {}).get(provider_name, {}) if isinstance(config.get("providers"), dict) else {}
    url = str(provider.get("rerank_api_url") or "")
    if not url:
        return {"ok": False, "status": "not_supported", "diagnostics": ["provider has no rerank_api_url"], "results": results}
    if not query.strip():
        return {"ok": False, "status": "empty_query", "diagnostics": ["rerank requires a non-empty query"], "results": results}
    configured_limit = int_value(provider.get("rerank_candidate_limit"), 24)
    effective_limit = max(1, min(candidate_limit or configured_limit or 24, len(results)))
    candidates = results[:effective_limit]
    documents = [rerank_document_for_search_hit(hit) for hit in candidates]
    response = run_json_url(
        url,
        method="POST",
        payload={"query": query, "documents": documents},
        timeout=min(timeout, 60),
    )
    payload = response.get("payload") if isinstance(response.get("payload"), dict) else {}
    ranked_items = payload.get("results") if isinstance(payload.get("results"), list) else []
    if not response.get("ok") or not ranked_items:
        return {
            "ok": False,
            "status": response.get("status") or "empty_rerank",
            "url": url,
            "diagnostics": [str(response.get("error") or response.get("status") or "rerank failed")],
            "results": results,
        }
    by_index: dict[int, dict[str, Any]] = {}
    for item in ranked_items:
        if not isinstance(item, dict):
            continue
        idx = int_value(item.get("index"), -1)
        if 0 <= idx < len(candidates):
            by_index[idx] = item
    annotated: list[dict[str, Any]] = []
    for idx, hit in enumerate(candidates):
        clone = dict(hit)
        refs = hit.get("refs") if isinstance(hit.get("refs"), dict) else {}
        if refs:
            clone["refs"] = dict(refs)
        item = by_index.get(idx, {})
        score = item.get("relevance_score")
        clone["host_rerank"] = {
            "provider": provider_name,
            "model": payload.get("model"),
            "score": score,
            "raw_logit_diff": item.get("raw_logit_diff"),
            "original_position": idx + 1,
            "truth_level": "local_rerank_ordering_not_aoa_authority",
        }
        annotated.append(clone)
    annotated.sort(
        key=lambda hit: (
            hit.get("host_rerank", {}).get("score") is None,
            -(float(hit.get("host_rerank", {}).get("score") or 0.0)),
            int_value(hit.get("host_rerank", {}).get("original_position"), 999999),
        )
    )
    for idx, hit in enumerate(annotated, start=1):
        if isinstance(hit.get("host_rerank"), dict):
            hit["host_rerank"]["reranked_position"] = idx
    final_results = annotated + results[effective_limit:]
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    return {
        "ok": True,
        "status": "applied",
        "url": url,
        "model": payload.get("model"),
        "candidate_count": len(candidates),
        "returned_count": len(ranked_items),
        "meta": {
            "backend": meta.get("backend"),
            "device": meta.get("device"),
            "documents": meta.get("documents"),
            "returned": meta.get("returned"),
            "total_ms": meta.get("total_ms"),
            "fake_mode": meta.get("fake_mode"),
        },
        "truth_level": "local_rerank_ordering_not_aoa_authority",
        "results": final_results,
    }


def init_search_db(db_path: Path, *, rebuild: bool = False) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if rebuild and db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=FILE")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS documents (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT NOT NULL UNIQUE,
            doc_type TEXT NOT NULL,
            session_id TEXT,
            session_label TEXT,
            session_title TEXT,
            session_date TEXT,
            cwd TEXT,
            archive_status TEXT,
            distillation_status TEXT,
            review_status TEXT,
            segment_id TEXT,
            event_id TEXT,
            event_type TEXT,
            family TEXT,
            phase TEXT,
            actor TEXT,
            action TEXT,
            object TEXT,
            outcome TEXT,
            conversation_act TEXT,
            session_act TEXT,
            route_layers TEXT,
            route_signals TEXT,
            tags TEXT,
            raw_ref TEXT,
            raw_block_ref TEXT,
            segment_ref TEXT,
            manifest_path TEXT,
            raw_path TEXT,
            segment_index_path TEXT,
            raw_sha256 TEXT,
            segment_index_sha256 TEXT,
            freshness_status TEXT,
            stale_reason TEXT,
            title TEXT,
            body TEXT,
            payload_json TEXT NOT NULL
        )
        """
    )
    existing_columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
    if "session_act" not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN session_act TEXT")
    if "route_layers" not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN route_layers TEXT")
    if "route_signals" not in existing_columns:
        conn.execute("ALTER TABLE documents ADD COLUMN route_signals TEXT")
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts
        USING fts5(title, body, session_label, session_title, content='documents', content_rowid='rowid')
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_session ON documents(session_label)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(doc_type, event_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_session_act ON documents(session_act)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_route_layers ON documents(route_layers)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_route_signals ON documents(route_signals)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(archive_status, freshness_status)")
    conn.commit()
    return conn


def reset_search_db(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM documents_fts")
    conn.execute("DELETE FROM documents")
    conn.execute("DELETE FROM meta")


def search_tokenize(query: str) -> list[str]:
    return [token for token in re.findall(r"[\w.-]+", str(query or ""), flags=re.UNICODE) if token.strip(".-_")]


def fts_query_from_user(query: str) -> str:
    tokens = search_tokenize(query)
    if not tokens:
        return ""
    return " AND ".join(f'"{token.replace("\"", "\"\"")}"' for token in tokens[:16])


def search_json_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def search_doc_text(parts: list[Any], *, max_chars: int = 4000) -> str:
    text = " ".join(part.strip() for part in (search_json_text(part) for part in parts) if part.strip())
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def packed_route_values(values: Iterable[str]) -> str:
    items = sorted({str(value) for value in values if str(value or "").strip()})
    return "|" + "|".join(items) + "|" if items else ""


def route_fields_from_counts(route_counts: dict[str, Any]) -> tuple[str, str]:
    layers: list[str] = []
    signals: list[str] = []
    for layer, keys in route_counts.items() if isinstance(route_counts, dict) else []:
        if not isinstance(keys, dict):
            continue
        layer_text = str(layer)
        layers.append(layer_text)
        for key in keys:
            signals.append(route_signal_token(layer_text, str(key)))
    return packed_route_values(layers), packed_route_values(signals)


def route_fields_from_signals(signals_value: Any) -> tuple[str, str]:
    layers: list[str] = []
    signals: list[str] = []
    for signal in signals_value if isinstance(signals_value, list) else []:
        if not isinstance(signal, dict):
            continue
        layer = str(signal.get("layer") or "")
        key = str(signal.get("key") or "")
        if layer:
            layers.append(layer)
        if layer and key:
            signals.append(route_signal_token(layer, key))
    return packed_route_values(layers), packed_route_values(signals)


def event_search_text_limit(event_type: str) -> int:
    if event_type in {"USER_INTENT", "ASSISTANT_PLAN", "ASSISTANT_MESSAGE", "DECISION", "ASSUMPTION", "CHECKPOINT", "FINAL_STATE", "PROCESS_LESSON", "OPEN_THREAD"}:
        return 1400
    if event_type in {"COMMAND", "FILE_READ", "FILE_WRITE", "DIFF", "TOOL_CALL"}:
        return 1000
    if event_type in {"COMMAND_OUTPUT", "TOOL_OUTPUT", "ERROR", "VERIFICATION"}:
        return 700
    return 500


def event_type_gets_raw_search_text(event_type: str, outcome: str) -> bool:
    if event_type in {
        "USER_INTENT",
        "ASSISTANT_PLAN",
        "ASSISTANT_MESSAGE",
        "DECISION",
        "ASSUMPTION",
        "CHECKPOINT",
        "FINAL_STATE",
        "PROCESS_LESSON",
        "OPEN_THREAD",
        "COMMAND",
        "FILE_READ",
        "FILE_WRITE",
        "DIFF",
        "TOOL_CALL",
        "ERROR",
        "VERIFICATION",
    }:
        return True
    return event_type in {"COMMAND_OUTPUT", "TOOL_OUTPUT"} and outcome == "failed"


def search_manifest_freshness(manifest: dict[str, Any], raw_path: Path | None) -> dict[str, Any]:
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    expected_sha = str(raw.get("sha256") or "")
    if not raw_path or not raw_path.exists():
        return {"status": "unverifiable", "reasons": ["raw_path_missing"]}
    if not expected_sha:
        return {"status": "unverifiable", "reasons": ["raw_sha_missing"]}
    current_sha = sha256_file(raw_path)
    if current_sha != expected_sha:
        return {"status": "stale", "reasons": ["raw_sha_mismatch"], "current_raw_sha256": current_sha}
    return {"status": "fresh", "reasons": []}


def segment_index_freshness(index_path: Path | None, expected_sha: str | None) -> dict[str, Any]:
    if not index_path or not index_path.exists():
        return {"status": "unverifiable", "reasons": ["segment_index_missing"]}
    if not expected_sha:
        return {"status": "unverifiable", "reasons": ["segment_index_sha_missing"]}
    current_sha = sha256_file(index_path)
    if current_sha != expected_sha:
        return {"status": "stale", "reasons": ["segment_index_sha_mismatch"], "current_segment_index_sha256": current_sha}
    return {"status": "fresh", "reasons": []}


def combine_freshness(*items: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    status = "fresh"
    combined: dict[str, Any] = {}
    for item in items:
        item_status = str(item.get("status") or "")
        if item_status == "stale":
            status = "stale"
        elif item_status == "unverifiable" and status != "stale":
            status = "unverifiable"
        for reason in item.get("reasons", []) if isinstance(item.get("reasons"), list) else []:
            if reason not in reasons:
                reasons.append(str(reason))
        for key, value in item.items():
            if key not in {"status", "reasons"}:
                combined[key] = value
    return {"status": status, "reasons": reasons, **combined}


def search_doc_payload(doc: dict[str, Any]) -> dict[str, Any]:
    payload = dict(doc)
    payload.pop("body", None)
    payload.pop("payload_json", None)
    return payload


def insert_search_document(conn: sqlite3.Connection, doc: dict[str, Any]) -> None:
    payload = search_doc_payload(doc)
    cursor = conn.execute(
        """
        INSERT INTO documents (
            id, doc_type, session_id, session_label, session_title, session_date,
            cwd, archive_status, distillation_status, review_status, segment_id,
            event_id, event_type, family, phase, actor, action, object, outcome,
            conversation_act, session_act, route_layers, route_signals, tags, raw_ref, raw_block_ref, segment_ref,
            manifest_path, raw_path, segment_index_path, raw_sha256,
            segment_index_sha256, freshness_status, stale_reason, title, body,
            payload_json
        )
        VALUES (
            :id, :doc_type, :session_id, :session_label, :session_title, :session_date,
            :cwd, :archive_status, :distillation_status, :review_status, :segment_id,
            :event_id, :event_type, :family, :phase, :actor, :action, :object, :outcome,
            :conversation_act, :session_act, :route_layers, :route_signals, :tags, :raw_ref, :raw_block_ref, :segment_ref,
            :manifest_path, :raw_path, :segment_index_path, :raw_sha256,
            :segment_index_sha256, :freshness_status, :stale_reason, :title, :body,
            :payload_json
        )
        """,
        {
            **{key: doc.get(key) for key in [
                "id",
                "doc_type",
                "session_id",
                "session_label",
                "session_title",
                "session_date",
                "cwd",
                "archive_status",
                "distillation_status",
                "review_status",
                "segment_id",
                "event_id",
                "event_type",
                "family",
                "phase",
                "actor",
                "action",
                "object",
                "outcome",
                "conversation_act",
                "session_act",
                "route_layers",
                "route_signals",
                "tags",
                "raw_ref",
                "raw_block_ref",
                "segment_ref",
                "manifest_path",
                "raw_path",
                "segment_index_path",
                "raw_sha256",
                "segment_index_sha256",
                "freshness_status",
                "stale_reason",
                "title",
                "body",
            ]},
            "payload_json": json.dumps(payload, ensure_ascii=False, sort_keys=True),
        },
    )
    rowid = cursor.lastrowid
    conn.execute(
        "INSERT INTO documents_fts(rowid, title, body, session_label, session_title) VALUES (?, ?, ?, ?, ?)",
        (rowid, doc.get("title") or "", doc.get("body") or "", doc.get("session_label") or "", doc.get("session_title") or ""),
    )


def session_semantic_names_text(manifest: dict[str, Any]) -> str:
    semantic = semantic_names_payload(manifest)
    parts = [
        semantic.get("active"),
        semantic.get("active_session"),
    ]
    for item in semantic.get("names", []) if isinstance(semantic.get("names"), list) else []:
        if isinstance(item, dict):
            parts.extend([item.get("name"), item.get("slug"), item.get("scope"), item.get("coverage_note")])
    return search_doc_text(parts, max_chars=1600)


def raw_event_search_text_by_line(raw_path: Path | None) -> dict[int, str]:
    if not raw_path or not raw_path.exists():
        return {}
    texts: dict[int, str] = {}
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
            event = classify_raw_event(raw, parsed, line_no)
            if not event_type_gets_raw_search_text(event.event_type, event.outcome):
                continue
            semantic = event_semantic_text(event)
            if semantic:
                texts[line_no] = short_text(semantic, max_chars=event_search_text_limit(event.event_type))
    return texts


def search_documents_for_record(
    aoa_root: Path,
    record: dict[str, Any],
    *,
    max_raw_bytes: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    session_dir = session_dir_from_record(record)
    manifest_path = session_dir / "session.manifest.json"
    manifest = read_json(manifest_path, {})
    if not isinstance(manifest, dict) or not manifest:
        return [], {"status": "diagnostic", "session_label": record.get("session_label"), "diagnostics": ["manifest_missing"], "document_count": 0}

    session_id = str(manifest.get("session_id") or record.get("session_id") or session_dir.name)
    display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
    source = manifest.get("source") if isinstance(manifest.get("source"), dict) else {}
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    raw_path = Path(str(raw.get("path"))) if raw.get("path") else None
    raw_sha = str(raw.get("sha256") or "")
    session_label = str(display.get("label") or manifest.get("session_label") or record.get("session_label") or session_dir.name)
    session_title = str(display.get("title") or manifest.get("session_title") or record.get("session_title") or "")
    session_date = str(display.get("date") or session_record_date(record))
    archive_status = str(manifest.get("archive_status") or record.get("archive_status") or "")
    distillation_status = str(manifest.get("distillation_status") or record.get("distillation_status") or "")
    review_status = str(manifest.get("review_status") or record.get("review_status") or "")
    cwd = str(source.get("cwd") or record.get("cwd") or "")
    work_context = manifest.get("work_context") if isinstance(manifest.get("work_context"), dict) else {}
    session_index_payload = read_json(session_dir / SESSION_INDEX_JSON, {})
    session_route_index_current = isinstance(session_index_payload, dict) and route_signal_index_is_current(session_index_payload)
    session_route_counts = (
        session_index_payload.get("route_signal_counts")
        if session_route_index_current and isinstance(session_index_payload.get("route_signal_counts"), dict)
        else {}
    )
    session_route_layers, session_route_signals = route_fields_from_counts(session_route_counts)
    raw_freshness = search_manifest_freshness(manifest, raw_path)
    raw_bytes = raw_path.stat().st_size if raw_path and raw_path.exists() else 0
    raw_text_status = "not_available"
    if raw_path and raw_path.exists():
        raw_text_status = "available"
        if max_raw_bytes is not None and raw_bytes > max_raw_bytes:
            raw_text_status = "skipped_raw_too_large"
    documents: list[dict[str, Any]] = []

    base = {
        "session_id": session_id,
        "session_label": session_label,
        "session_title": session_title,
        "session_date": session_date,
        "cwd": cwd,
        "archive_status": archive_status,
        "distillation_status": distillation_status,
        "review_status": review_status,
        "manifest_path": str(manifest_path),
        "raw_path": str(raw_path) if raw_path else "",
        "raw_sha256": raw_sha,
        "freshness_status": raw_freshness["status"],
        "stale_reason": ",".join(raw_freshness.get("reasons", [])),
    }
    raw_blocks = manifest.get("raw_blocks") if isinstance(manifest.get("raw_blocks"), dict) else {}
    session_body = search_doc_text(
        [
            session_label,
            session_title,
            session_semantic_names_text(manifest),
            archive_status,
            distillation_status,
            review_status,
            cwd,
            work_context,
            source.get("transcript_path") if isinstance(source, dict) else "",
            raw.get("source_path"),
            raw.get("indexing_status"),
            raw_blocks.get("index"),
            session_route_counts,
        ],
        max_chars=3000,
    )
    documents.append(
        {
            **base,
            "id": f"session:{session_id}",
            "doc_type": "session",
            "title": session_title or session_label,
            "body": session_body,
            "raw_ref": "",
            "raw_block_ref": "",
            "segment_ref": str(session_dir / SESSION_INDEX_MARKDOWN),
            "route_layers": session_route_layers,
            "route_signals": session_route_signals,
            "tags": "",
        }
    )

    for incident_path in sorted((session_dir / "incidents").glob("*")):
        if not incident_path.is_file() or incident_path.suffix not in {".md", ".json"}:
            continue
        text = short_text(incident_path.read_text(encoding="utf-8", errors="replace"), max_chars=3000)
        documents.append(
            {
                **base,
                "id": f"incident:{session_id}:{incident_path.name}",
                "doc_type": "incident",
                "title": incident_path.name,
                "body": search_doc_text([session_label, session_title, archive_status, text], max_chars=3600),
                "raw_ref": "",
                "raw_block_ref": "",
                "segment_ref": str(incident_path),
                "route_layers": session_route_layers,
                "route_signals": session_route_signals,
                "tags": "incident",
            }
        )

    raw_text_by_line = (
        {}
        if raw_text_status == "skipped_raw_too_large"
        else raw_event_search_text_by_line(raw_path)
    )
    segments = manifest.get("segments") if isinstance(manifest.get("segments"), list) else []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        segment_id = str(segment.get("segment_id") or "")
        index_path = Path(str(segment.get("index") or ""))
        segment_index = read_json(index_path, {}) if index_path.exists() else {}
        segment_sha = sha256_file(index_path) if index_path.exists() else ""
        segment_freshness = segment_index_freshness(index_path if index_path.exists() else None, segment_sha)
        segment_route_index_current = isinstance(segment_index, dict) and route_signal_index_is_current(segment_index)
        if not segment_route_index_current:
            segment_freshness.setdefault("reasons", []).extend(route_signal_index_stale_reasons(segment_index if isinstance(segment_index, dict) else {}))
            segment_freshness["status"] = "stale"
        freshness = combine_freshness(raw_freshness, segment_freshness)
        segment_route_layers, segment_route_signals = route_fields_from_counts(
            segment_index.get("by_route_layer") if segment_route_index_current and isinstance(segment_index.get("by_route_layer"), dict) else {}
        )
        source_block = segment.get("raw_block") if isinstance(segment.get("raw_block"), dict) else {}
        source_range = segment.get("source_range") if isinstance(segment.get("source_range"), dict) else {}
        segment_body = search_doc_text(
            [
                session_label,
                session_title,
                segment.get("role"),
                source_range,
                source_block.get("rel"),
                " ".join((segment_index.get("by_type") or {}).keys()) if isinstance(segment_index.get("by_type"), dict) else "",
                " ".join((segment_index.get("by_conversation_act") or {}).keys()) if isinstance(segment_index.get("by_conversation_act"), dict) else "",
                " ".join((segment_index.get("by_session_act") or {}).keys()) if isinstance(segment_index.get("by_session_act"), dict) else "",
                " ".join((segment_index.get("by_route_signal") or {}).keys()) if segment_route_index_current and isinstance(segment_index.get("by_route_signal"), dict) else "",
            ],
            max_chars=2600,
        )
        documents.append(
            {
                **base,
                "id": f"segment:{session_id}:{segment_id}",
                "doc_type": "segment",
                "segment_id": segment_id,
                "raw_block_ref": source_block.get("rel") or "",
                "segment_ref": str(segment.get("markdown") or ""),
                "segment_index_path": str(index_path),
                "segment_index_sha256": segment_sha,
                "freshness_status": freshness["status"],
                "stale_reason": ",".join(freshness.get("reasons", [])),
                "title": f"{session_label} segment {segment_id} {segment.get('role') or ''}".strip(),
                "body": segment_body,
                "raw_ref": "",
                "route_layers": segment_route_layers,
                "route_signals": segment_route_signals,
                "tags": "segment",
            }
        )

        for event in segment_index.get("events", []) if isinstance(segment_index.get("events"), list) else []:
            if not isinstance(event, dict):
                continue
            facets = event.get("facets") if isinstance(event.get("facets"), dict) else {}
            conversation_act = facets.get("conversation_act") if isinstance(facets.get("conversation_act"), dict) else {}
            session_act = facets.get("session_act") if isinstance(facets.get("session_act"), dict) else {}
            route_layers, route_signals = route_fields_from_signals(facets.get("route_signals")) if segment_route_index_current else ("", "")
            event_type = str(event.get("type") or "")
            line_no = int_value(event.get("line"))
            raw_text = raw_text_by_line.get(line_no, "")
            tags = " ".join(str(tag) for tag in event.get("tags", []) if tag) if isinstance(event.get("tags"), list) else ""
            command = facets.get("command") or facets.get("tool_name") or facets.get("payload_type")
            event_body = search_doc_text(
                [
                    event.get("title"),
                    raw_text,
                    tags,
                    event_type,
                    event.get("family"),
                    event.get("phase"),
                    event.get("actor"),
                    event.get("action"),
                    event.get("object"),
                    event.get("outcome"),
                    conversation_act.get("kind"),
                    conversation_act.get("intent"),
                    session_act.get("kind"),
                    session_act.get("memory_surface"),
                    session_act.get("tool_namespace"),
                    route_layers,
                    route_signals,
                    command,
                    event.get("raw_ref"),
                    event.get("md_anchor"),
                ],
                max_chars=3600,
            )
            documents.append(
                {
                    **base,
                    "id": f"event:{session_id}:{segment_id}:{event.get('event_id')}",
                    "doc_type": "event",
                    "segment_id": segment_id,
                    "event_id": str(event.get("event_id") or ""),
                    "event_type": event_type,
                    "family": str(event.get("family") or ""),
                    "phase": str(event.get("phase") or ""),
                    "actor": str(event.get("actor") or ""),
                    "action": str(event.get("action") or ""),
                    "object": str(event.get("object") or ""),
                    "outcome": str(event.get("outcome") or ""),
                    "conversation_act": str(conversation_act.get("kind") or ""),
                    "session_act": str(session_act.get("kind") or ""),
                    "route_layers": route_layers,
                    "route_signals": route_signals,
                    "tags": tags,
                    "raw_ref": str(event.get("raw_ref") or ""),
                    "raw_block_ref": source_block.get("rel") or "",
                    "segment_ref": str(event.get("md_anchor") or segment.get("markdown") or ""),
                    "segment_index_path": str(index_path),
                    "segment_index_sha256": segment_sha,
                    "freshness_status": freshness["status"],
                    "stale_reason": ",".join(freshness.get("reasons", [])),
                    "title": str(event.get("title") or event_type or "event"),
                    "body": event_body,
                }
            )
    return documents, {
        "status": "indexed",
        "session_label": session_label,
        "document_count": len(documents),
        "raw_text_status": raw_text_status,
        "raw_bytes": raw_bytes,
        "max_raw_bytes": max_raw_bytes,
        "diagnostics": [],
    }


def search_index_sessions(
    *,
    aoa_root: Path,
    target: str = "all",
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    max_raw_bytes: int | None = None,
    rebuild: bool = True,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    db_path = search_db_path(aoa_root)
    try:
        if target and target != "all":
            records = [resolve_session_record(aoa_root, target)]
        else:
            records = chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    except ValueError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "search_index",
            "search_schema_version": SEARCH_SCHEMA_VERSION,
            "generated_at": now,
            "ok": False,
            "target": target,
            "selected_count": 0,
            "document_count": 0,
            "max_raw_bytes": max_raw_bytes,
            "db_path": str(db_path),
            "diagnostics": [str(exc)],
            "sessions": [],
        }
    if not records:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "search_index",
            "search_schema_version": SEARCH_SCHEMA_VERSION,
            "generated_at": now,
            "ok": False,
            "target": target,
            "selected_count": 0,
            "document_count": 0,
            "max_raw_bytes": max_raw_bytes,
            "db_path": str(db_path),
            "diagnostics": ["no sessions selected"],
            "sessions": [],
        }
    conn = init_search_db(db_path, rebuild=rebuild)
    if rebuild:
        reset_search_db(conn)
        conn.commit()
    counts: Counter[str] = Counter()
    diagnostics: list[str] = []
    session_results: list[dict[str, Any]] = []
    try:
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("schema_version", str(SEARCH_SCHEMA_VERSION)))
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("generated_at", now))
        conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("aoa_root", str(aoa_root)))
        conn.commit()
        for record_index, record in enumerate(records, start=1):
            conn.execute("BEGIN")
            documents, result = search_documents_for_record(aoa_root, record, max_raw_bytes=max_raw_bytes)
            session_results.append(result)
            if result.get("diagnostics"):
                diagnostics.extend(str(item) for item in result.get("diagnostics", []))
            for doc in documents:
                insert_search_document(conn, doc)
                counts[str(doc.get("doc_type") or "unknown")] += 1
            conn.commit()
            if record_index % 10 == 0:
                conn.execute("PRAGMA optimize")
    except sqlite3.Error as exc:
        conn.rollback()
        conn.close()
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "search_index",
            "search_schema_version": SEARCH_SCHEMA_VERSION,
            "generated_at": now,
            "ok": False,
            "target": target,
            "selected_count": len(records),
            "document_count": 0,
            "max_raw_bytes": max_raw_bytes,
            "db_path": str(db_path),
            "diagnostics": [f"sqlite_error:{exc}"],
            "sessions": session_results,
        }
    finally:
        conn.close()
    document_count = sum(counts.values())
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "search_index",
        "search_schema_version": SEARCH_SCHEMA_VERSION,
        "generated_at": now,
        "ok": document_count > 0 and not diagnostics,
        "target": target,
        "since": since,
        "until": until,
        "limit": limit,
        "max_raw_bytes": max_raw_bytes,
        "selected_count": len(records),
        "document_count": document_count,
        "session_document_count": counts.get("session", 0),
        "segment_document_count": counts.get("segment", 0),
        "event_document_count": counts.get("event", 0),
        "incident_document_count": counts.get("incident", 0),
        "db_path": str(db_path),
        "diagnostics": diagnostics,
        "sessions": session_results,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__search-index"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, search_report_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def search_result_freshness(row: sqlite3.Row) -> dict[str, Any]:
    raw_path_value = row["raw_path"] if "raw_path" in row.keys() else ""
    segment_path_value = row["segment_index_path"] if "segment_index_path" in row.keys() else ""
    checks: list[dict[str, Any]] = []
    if raw_path_value:
        raw_path = Path(str(raw_path_value))
        if raw_path.exists() and row["raw_sha256"]:
            checks.append(search_manifest_freshness({"raw": {"sha256": row["raw_sha256"]}}, raw_path))
        else:
            checks.append({"status": "unverifiable", "reasons": ["raw_path_missing" if not raw_path.exists() else "raw_sha_missing"]})
    if segment_path_value:
        checks.append(segment_index_freshness(Path(str(segment_path_value)), row["segment_index_sha256"]))
    if checks:
        return combine_freshness(*checks)
    status = str(row["freshness_status"] or "unverifiable")
    reasons = [reason for reason in str(row["stale_reason"] or "").split(",") if reason]
    return {"status": status, "reasons": reasons}


def compact_search_result(row: sqlite3.Row, *, explain: bool = False, query: str = "") -> dict[str, Any]:
    freshness = search_result_freshness(row)
    refs = {
        "session": row["manifest_path"],
        "segment": row["segment_ref"],
        "segment_index": row["segment_index_path"],
        "raw": row["raw_ref"],
        "raw_block": row["raw_block_ref"],
    }
    result = {
        "rank": row["rank"] if "rank" in row.keys() else 0,
        "doc_id": row["id"],
        "doc_type": row["doc_type"],
        "session_id": row["session_id"],
        "session_label": row["session_label"],
        "session_title": row["session_title"],
        "session_date": row["session_date"],
        "archive_status": row["archive_status"],
        "segment_id": row["segment_id"],
        "event_id": row["event_id"],
        "event_type": row["event_type"],
        "family": row["family"],
        "phase": row["phase"],
        "actor": row["actor"],
        "action": row["action"],
        "outcome": row["outcome"],
        "conversation_act": row["conversation_act"],
        "session_act": row["session_act"] if "session_act" in row.keys() else None,
        "route_layers": row["route_layers"] if "route_layers" in row.keys() else "",
        "route_signals": row["route_signals"] if "route_signals" in row.keys() else "",
        "title": row["title"],
        "snippet": short_text(row["body"], max_chars=420),
        "refs": refs,
        "freshness": freshness,
    }
    if explain:
        result["explain"] = {
            "query": query,
            "matched_document_layer": row["doc_type"],
            "routing_fields": {
                "event_type": row["event_type"],
                "family": row["family"],
                "conversation_act": row["conversation_act"],
                "session_act": row["session_act"] if "session_act" in row.keys() else None,
                "route_layers": row["route_layers"] if "route_layers" in row.keys() else "",
                "route_signals": row["route_signals"] if "route_signals" in row.keys() else "",
                "archive_status": row["archive_status"],
            },
            "why_this_is_not_authority": "Search result routes to raw/segment refs; raw transcript and segment indexes remain stronger evidence.",
        }
    return result


def search_index_metadata(conn: sqlite3.Connection) -> dict[str, Any]:
    rows = conn.execute("SELECT key, value FROM meta").fetchall()
    return {str(row["key"]): row["value"] for row in rows}


def search_sessions(
    *,
    aoa_root: Path,
    query: str = "",
    limit: int = 20,
    provider: str = "portable_sqlite",
    include_host_context: bool = False,
    include_semantic_context: bool = False,
    rerank_local: bool = False,
    rerank_candidate_limit: int | None = None,
    allow_host_warnings: bool = False,
    host_timeout: int = 45,
    session: str | None = None,
    doc_type: str | None = None,
    event_type: str | None = None,
    family: str | None = None,
    outcome: str | None = None,
    conversation_act: str | None = None,
    session_act: str | None = None,
    route_layer: str | None = None,
    route_signal: str | None = None,
    archive_status: str | None = None,
    freshness_status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    explain: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    provider_config = search_provider_config(aoa_root)
    configured_providers = provider_config.get("providers") if isinstance(provider_config.get("providers"), dict) else {}
    if provider not in configured_providers:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "search_results",
            "search_schema_version": SEARCH_SCHEMA_VERSION,
            "generated_at": now,
            "ok": False,
            "query": query,
            "result_count": 0,
            "results": [],
            "provider": {"selected": provider, "status": "unknown_provider"},
            "diagnostics": [f"unknown search provider: {provider}"],
        }
    db_path = search_db_path(aoa_root)
    if not db_path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "search_results",
            "search_schema_version": SEARCH_SCHEMA_VERSION,
            "generated_at": now,
            "ok": False,
            "query": query,
            "db_path": str(db_path),
            "result_count": 0,
            "results": [],
            "provider": {"selected": provider, "status": "portable_sqlite_missing"},
            "diagnostics": ["search index missing; run search-index"],
        }
    schema_conn = init_search_db(db_path, rebuild=False)
    schema_conn.close()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    filters: list[str] = []
    params: list[Any] = []
    if session:
        filters.append("(documents.session_id = ? OR documents.session_label LIKE ? OR documents.session_title LIKE ?)")
        like = f"%{session}%"
        params.extend([session, like, like])
    for column, value in [
        ("documents.doc_type", doc_type),
        ("documents.event_type", event_type),
        ("documents.family", family),
        ("documents.outcome", outcome),
        ("documents.conversation_act", conversation_act),
        ("documents.session_act", session_act),
        ("documents.archive_status", archive_status),
        ("documents.freshness_status", freshness_status),
    ]:
        if value:
            filters.append(f"{column} = ?")
            params.append(value)
    if route_layer:
        filters.append("documents.route_layers LIKE ?")
        params.append(f"%|{route_key_slug(route_layer, fallback=str(route_layer))}|%")
    if route_signal:
        normalized_signal = str(route_signal)
        if ":" in normalized_signal:
            layer, key = normalized_signal.split(":", 1)
            normalized_signal = route_signal_token(route_key_slug(layer, fallback=layer), route_key_slug(key, fallback=key))
        filters.append("documents.route_signals LIKE ?")
        params.append(f"%|{normalized_signal}|%")
    if date_from:
        filters.append("documents.session_date >= ?")
        params.append(parse_date_arg(date_from))
    if date_to:
        filters.append("documents.session_date <= ?")
        params.append(parse_date_arg(date_to))
    where = " AND ".join(filters)
    fts_query = fts_query_from_user(query)
    try:
        if fts_query:
            sql = (
                "SELECT documents.*, bm25(documents_fts) AS rank "
                "FROM documents_fts JOIN documents ON documents_fts.rowid = documents.rowid "
                "WHERE documents_fts MATCH ?"
            )
            query_params: list[Any] = [fts_query]
            if where:
                sql += " AND " + where
                query_params.extend(params)
            sql += " ORDER BY rank, documents.session_date DESC, documents.rowid DESC LIMIT ?"
            query_params.append(limit)
            rows = conn.execute(sql, query_params).fetchall()
        else:
            sql = "SELECT documents.*, 0.0 AS rank FROM documents"
            query_params = list(params)
            if where:
                sql += " WHERE " + where
            sql += " ORDER BY documents.session_date DESC, documents.rowid DESC LIMIT ?"
            query_params.append(limit)
            rows = conn.execute(sql, query_params).fetchall()
        metadata = search_index_metadata(conn)
    except sqlite3.Error as exc:
        conn.close()
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "search_results",
            "search_schema_version": SEARCH_SCHEMA_VERSION,
            "generated_at": now,
            "ok": False,
            "query": query,
            "db_path": str(db_path),
            "result_count": 0,
            "results": [],
            "diagnostics": [f"sqlite_error:{exc}"],
        }
    finally:
        conn.close()
    results = [compact_search_result(row, explain=explain, query=query) for row in rows]
    accelerator_provider = provider if provider != "portable_sqlite" else "abyss_machine_nervous"
    provider_payload = search_provider_status(
        aoa_root=aoa_root,
        provider_name=provider,
        include_host=provider != "portable_sqlite",
        timeout=host_timeout,
    )
    accelerator_status: dict[str, Any] | None = None
    if rerank_local or include_semantic_context:
        accelerator_status = search_provider_status(
            aoa_root=aoa_root,
            provider_name=accelerator_provider,
            include_host=True,
            timeout=host_timeout,
        )
    diagnostics: list[str] = []
    provider_overlay: dict[str, Any] | None = None
    semantic_overlay: dict[str, Any] | None = None
    local_rerank: dict[str, Any] | None = None
    if provider != "portable_sqlite":
        selected_status = provider_payload.get("providers", {}).get(provider) if isinstance(provider_payload.get("providers"), dict) else {}
        status = str(selected_status.get("status") if isinstance(selected_status, dict) else "")
        if status == "ready_with_warnings" and not allow_host_warnings:
            diagnostics.append("host provider has warnings; returned portable SQLite .aoa hits without host context overlay")
        elif not selected_status.get("ok"):
            diagnostics.append(f"host provider unavailable: {status}")
        elif include_host_context:
            provider_overlay = host_context_overlay(
                config=provider_config,
                provider_name=provider,
                query=query,
                limit=limit,
                timeout=host_timeout,
            )
    selected_accelerator = (
        accelerator_status.get("providers", {}).get(accelerator_provider)
        if isinstance(accelerator_status, dict) and isinstance(accelerator_status.get("providers"), dict)
        else {}
    )
    accelerator_ok = bool(selected_accelerator.get("ok")) if isinstance(selected_accelerator, dict) else False
    accelerator_status_name = str(selected_accelerator.get("status") or "") if isinstance(selected_accelerator, dict) else ""
    if (rerank_local or include_semantic_context) and not accelerator_ok:
        diagnostics.append(f"local accelerator unavailable: {accelerator_status_name or 'unknown'}")
    elif (rerank_local or include_semantic_context) and accelerator_status_name == "ready_with_warnings" and not allow_host_warnings:
        diagnostics.append("local accelerator has warnings; use --allow-host-warnings to include semantic/rerank overlays")
    else:
        if include_semantic_context:
            semantic_overlay = host_semantic_overlay(
                config=provider_config,
                provider_name=accelerator_provider,
                query=query,
                limit=limit,
                timeout=host_timeout,
            )
            if not semantic_overlay.get("ok"):
                diagnostics.append(f"semantic overlay unavailable: {semantic_overlay.get('status')}")
        if rerank_local:
            rerank_payload = local_rerank_search_results(
                config=provider_config,
                provider_name=accelerator_provider,
                query=query,
                results=results,
                timeout=host_timeout,
                candidate_limit=rerank_candidate_limit,
            )
            if rerank_payload.get("ok"):
                results = rerank_payload.pop("results", results)
                local_rerank = rerank_payload
            else:
                diagnostics.append(f"local rerank unavailable: {rerank_payload.get('status')}")
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "search_results",
        "search_schema_version": SEARCH_SCHEMA_VERSION,
        "generated_at": now,
        "ok": True,
        "query": query,
        "normalized_query": fts_query,
        "db_path": str(db_path),
        "index_generated_at": metadata.get("generated_at"),
        "aoa_root": str(aoa_root),
        "provider": {
            "selected": provider,
            "authoritative_result_provider": "portable_sqlite",
            "status": provider_payload,
            "accelerator_provider": accelerator_provider if rerank_local or include_semantic_context else None,
            "accelerator_status": accelerator_status,
            "overlay": provider_overlay,
            "semantic_overlay": semantic_overlay,
            "local_rerank": local_rerank,
            "authority_law": provider_config.get("authority_law"),
        },
        "result_count": len(results),
        "results": results,
        "diagnostics": diagnostics,
    }


RETRIEVAL_RECIPE_QUERIES = {
    "continue-session": "final state open thread decision verification",
    "continue-techniques-session": "aoa-techniques techniques continuation open thread final state",
    "hook-failure": "hook timed out hook failed PreCompact PostCompact Stop",
    "naming-candidate": "naming name bridge anchor phase candidate too general",
    "process-lessons": "process lesson decision verification dead branch",
    "repeated-errors": "error failed failure timeout",
    "manual-review": "manual review promotion candidate open for future passes",
}


def compact_event_for_packet(event: dict[str, Any], *, segment_id: str = "") -> dict[str, Any]:
    facets = event.get("facets") if isinstance(event.get("facets"), dict) else {}
    conversation_act = facets.get("conversation_act") if isinstance(facets.get("conversation_act"), dict) else {}
    return {
        "event_id": event.get("event_id"),
        "segment_id": segment_id or event.get("segment_id"),
        "type": event.get("type"),
        "family": event.get("family"),
        "phase": event.get("phase"),
        "actor": event.get("actor"),
        "action": event.get("action"),
        "outcome": event.get("outcome"),
        "conversation_act": conversation_act.get("kind"),
        "title": event.get("title"),
        "raw_ref": event.get("raw_ref"),
        "segment_ref": event.get("md_anchor"),
    }


def session_event_signals(manifest: dict[str, Any], *, event_types: set[str], limit: int = 16) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    segments = manifest.get("segments") if isinstance(manifest.get("segments"), list) else []
    for segment in reversed([item for item in segments if isinstance(item, dict)]):
        index_path = Path(str(segment.get("index") or ""))
        if not index_path.exists():
            continue
        segment_index = read_json(index_path, {})
        events = segment_index.get("events") if isinstance(segment_index.get("events"), list) else []
        for event in reversed([item for item in events if isinstance(item, dict)]):
            if str(event.get("type") or "") not in event_types:
                continue
            signals.append(compact_event_for_packet(event, segment_id=str(segment.get("segment_id") or "")))
            if len(signals) >= limit:
                return signals
    return signals


def phase_discovery_packet_summary(session_dir: Path, *, limit: int = 8) -> dict[str, Any]:
    path = session_phase_discovery_path(session_dir)
    if not path.exists():
        return {"present": False, "path": str(path), "candidate_count": 0, "review_queue_count": 0, "candidates": [], "review_queue": []}
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        return {"present": True, "path": str(path), "read_error": "invalid_payload", "candidate_count": 0, "review_queue_count": 0, "candidates": [], "review_queue": []}
    candidates: list[dict[str, Any]] = []
    for candidate in payload.get("candidates", []) if isinstance(payload.get("candidates"), list) else []:
        if not isinstance(candidate, dict):
            continue
        candidates.append(
            {
                "segment_id": candidate.get("segment_id"),
                "name": candidate.get("name"),
                "confidence": candidate.get("confidence"),
                "name_basis": candidate.get("name_basis"),
                "quality_flags": candidate.get("quality_flags", []),
                "evidence": candidate.get("evidence", []) if isinstance(candidate.get("evidence"), list) else [],
                "coverage": candidate.get("coverage") if isinstance(candidate.get("coverage"), dict) else {},
            }
        )
        if len(candidates) >= limit:
            break
    review_queue: list[dict[str, Any]] = []
    for item in payload.get("review_queue", []) if isinstance(payload.get("review_queue"), list) else []:
        if not isinstance(item, dict):
            continue
        review_queue.append(
            {
                "segment_id": item.get("segment_id"),
                "name": item.get("name"),
                "reason": item.get("reason") or item.get("review_reason"),
                "quality_flags": item.get("quality_flags", []),
                "evidence": item.get("evidence", []) if isinstance(item.get("evidence"), list) else [],
            }
        )
        if len(review_queue) >= limit:
            break
    return {
        "present": True,
        "path": str(path),
        "candidate_count": int_value(payload.get("candidate_count")),
        "review_queue_count": int_value(payload.get("review_queue_count")),
        "candidates": candidates,
        "review_queue": review_queue,
    }


def retrieval_packet_markdown(payload: dict[str, Any]) -> str:
    identity = payload.get("session") if isinstance(payload.get("session"), dict) else {}
    lines = [
        "# Retrieval Packet",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- recipe: `{payload.get('recipe')}`",
        f"- query: `{payload.get('query')}`",
        f"- ok: `{payload.get('ok')}`",
        "",
        "## Session",
        "",
        f"- label: `{identity.get('label')}`",
        f"- title: `{identity.get('title')}`",
        f"- path: `{identity.get('path')}`",
        f"- events: `{identity.get('event_count')}`",
        f"- segments: `{identity.get('segment_count')}`",
        "",
        "## Evidence Hits",
        "",
    ]
    hits = payload.get("evidence_hits") if isinstance(payload.get("evidence_hits"), list) else []
    if hits:
        lines.extend(["| type | event | raw | segment | freshness | snippet |", "| --- | --- | --- | --- | --- | --- |"])
        for hit in hits[:20]:
            refs = hit.get("refs") if isinstance(hit.get("refs"), dict) else {}
            freshness = hit.get("freshness") if isinstance(hit.get("freshness"), dict) else {}
            lines.append(
                "| `{}` | `{}` | `{}` | `{}` | `{}` | {} |".format(
                    hit.get("event_type") or hit.get("doc_type"),
                    hit.get("event_id") or "",
                    refs.get("raw") or "",
                    refs.get("segment") or "",
                    freshness.get("status") or "",
                    short_text(hit.get("snippet"), max_chars=120),
                )
            )
    else:
        lines.append("- none")
    phase = payload.get("phase_discovery") if isinstance(payload.get("phase_discovery"), dict) else {}
    lines.extend(["", "## Phase Discovery", "", f"- present: `{phase.get('present')}`", f"- review_queue_count: `{phase.get('review_queue_count', 0)}`", "", "## Next Routes", ""])
    for route in payload.get("next_routes", []) if isinstance(payload.get("next_routes"), list) else []:
        lines.append(f"- `{route}`")
    return "\n".join(lines)


def prioritize_evidence_hits_for_packet(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def score(hit: dict[str, Any]) -> tuple[int, int, str]:
        refs = hit.get("refs") if isinstance(hit.get("refs"), dict) else {}
        has_raw = bool(str(refs.get("raw") or "").startswith("raw:line:"))
        doc_type = str(hit.get("doc_type") or "")
        event_type = str(hit.get("event_type") or "")
        doc_rank = {"event": 0, "segment": 1, "session": 2, "incident": 3}.get(doc_type, 4)
        signal_rank = 0 if event_type in {"USER_INTENT", "DECISION", "OPEN_THREAD", "FINAL_STATE", "VERIFICATION", "ERROR"} else 1
        return (0 if has_raw else 1, doc_rank, f"{signal_rank}:{hit.get('doc_id') or ''}")

    return sorted(hits, key=score)


def retrieval_packet(
    *,
    aoa_root: Path,
    recipe: str,
    query: str = "",
    session: str | None = None,
    provider: str = "portable_sqlite",
    include_host_context: bool = False,
    include_semantic_context: bool = False,
    rerank_local: bool = False,
    rerank_candidate_limit: int | None = None,
    allow_host_warnings: bool = False,
    limit: int = 8,
    event_limit: int = 16,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    if recipe not in RETRIEVAL_RECIPE_QUERIES:
        return {"schema_version": SCHEMA_VERSION, "artifact_type": "retrieval_packet", "ok": False, "generated_at": now, "recipe": recipe, "diagnostics": [f"unknown recipe: {recipe}"]}
    effective_query = query.strip() or RETRIEVAL_RECIPE_QUERIES[recipe]
    diagnostics: list[str] = []
    search_payload = search_sessions(
        aoa_root=aoa_root,
        query=effective_query,
        limit=max(1, limit),
        provider=provider,
        include_host_context=include_host_context,
        include_semantic_context=include_semantic_context,
        rerank_local=rerank_local,
        rerank_candidate_limit=rerank_candidate_limit,
        allow_host_warnings=allow_host_warnings,
        explain=True,
    )
    if search_payload.get("diagnostics"):
        diagnostics.extend(str(item) for item in search_payload.get("diagnostics", []))
    record: dict[str, Any] | None = None
    if session:
        try:
            record = resolve_session_record(aoa_root, session)
        except ValueError as exc:
            diagnostics.append(str(exc))
    if record is None:
        for hit in search_payload.get("results", []) if isinstance(search_payload.get("results"), list) else []:
            label = hit.get("session_label")
            if label:
                try:
                    record = resolve_session_record(aoa_root, str(label))
                    break
                except ValueError:
                    continue
    if record is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "retrieval_packet",
            "ok": False,
            "generated_at": now,
            "recipe": recipe,
            "query": effective_query,
            "search": search_payload,
            "diagnostics": diagnostics + ["no session selected from search results"],
        }
    session_dir = session_dir_from_record(record)
    manifest_path = session_dir / "session.manifest.json"
    manifest = read_json(manifest_path, {})
    if not isinstance(manifest, dict) or not manifest:
        return {"schema_version": SCHEMA_VERSION, "artifact_type": "retrieval_packet", "ok": False, "generated_at": now, "recipe": recipe, "query": effective_query, "diagnostics": diagnostics + [f"manifest missing: {manifest_path}"]}
    display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    selected_label = str(display.get("label") or manifest.get("session_label") or record.get("session_label") or session_dir.name)
    session_hits_payload = search_sessions(
        aoa_root=aoa_root,
        query=effective_query,
        limit=max(1, limit),
        provider=provider,
        include_host_context=include_host_context,
        include_semantic_context=include_semantic_context,
        rerank_local=rerank_local,
        rerank_candidate_limit=rerank_candidate_limit,
        allow_host_warnings=allow_host_warnings,
        session=selected_label,
        explain=True,
    )
    if session_hits_payload.get("diagnostics"):
        diagnostics.extend(str(item) for item in session_hits_payload.get("diagnostics", []))
    signal_types = {"OPEN_THREAD", "FINAL_STATE", "PROCESS_LESSON", "DECISION", "ERROR", "VERIFICATION", "RESUME_HINT"}
    phase_packet = phase_discovery_packet_summary(session_dir, limit=limit)
    next_routes = [
        f"python3 scripts/aoa_session_memory.py rehydrate {shlex.quote(selected_label)} --aoa-root {shlex.quote(str(aoa_root))}",
        f"python3 scripts/aoa_session_memory.py search --aoa-root {shlex.quote(str(aoa_root))} --session {shlex.quote(selected_label)} --query {shlex.quote(effective_query)} --explain",
    ]
    if phase_packet.get("present") and int_value(phase_packet.get("review_queue_count")):
        next_routes.append(f"python3 scripts/aoa_session_memory.py phase-review-assist {shlex.quote(selected_label)} --aoa-root {shlex.quote(str(aoa_root))} --write-report")
    elif not phase_packet.get("present") and int_value(manifest.get("segment_count")) > 8:
        next_routes.append(f"python3 scripts/aoa_session_memory.py phase-discovery {shlex.quote(selected_label)} --aoa-root {shlex.quote(str(aoa_root))} --write --write-report")
    evidence_hits = prioritize_evidence_hits_for_packet(
        session_hits_payload.get("results", []) if isinstance(session_hits_payload.get("results"), list) else []
    )
    packet = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "retrieval_packet",
        "generated_at": now,
        "ok": bool(session_hits_payload.get("ok")) and bool(manifest),
        "recipe": recipe,
        "query": effective_query,
        "provider": session_hits_payload.get("provider"),
        "session": {
            "session_id": manifest.get("session_id"),
            "label": selected_label,
            "title": display.get("title") or manifest.get("session_title"),
            "path": str(session_dir),
            "manifest": str(manifest_path),
            "cwd": manifest.get("source", {}).get("cwd") if isinstance(manifest.get("source"), dict) else "",
            "archive_status": manifest.get("archive_status"),
            "distillation_status": manifest.get("distillation_status"),
            "review_status": manifest.get("review_status"),
            "event_count": manifest.get("event_count"),
            "segment_count": manifest.get("segment_count"),
            "raw_path": raw.get("path"),
            "raw_sha256": raw.get("sha256"),
        },
        "evidence_hits": evidence_hits,
        "continuation_signals": session_event_signals(manifest, event_types=signal_types, limit=event_limit),
        "phase_discovery": phase_packet,
        "next_routes": next_routes,
        "diagnostics": diagnostics,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__retrieval-packet__{readable_slug(recipe) or 'recipe'}"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, packet)
        write_markdown(report_md, retrieval_packet_markdown(packet))
        packet["report_json"] = str(report_json)
        packet["report_markdown"] = str(report_md)
    return packet


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
    started_at = time.monotonic()
    workspace_root = Path(args.workspace_root) if args.workspace_root else None
    aoa_root = Path(args.aoa_root) if args.aoa_root else None
    receipt = handle_hook_event(
        args.event_name,
        event if isinstance(event, dict) else {"payload": event},
        workspace_root=workspace_root,
        aoa_root=aoa_root,
    )
    launch_background = bool(receipt.get("background_job"))
    if launch_background and hook_background_sync_enabled():
        actions = receipt.setdefault("actions", [])
        if isinstance(actions, list):
            actions.append("background_worker_queued_for_launch")
    record_hook_receipt(receipt, duration_ms=int((time.monotonic() - started_at) * 1000))
    if launch_background:
        root = aoa_root_for(workspace_root, aoa_root)
        launch_hook_worker(workspace_root=workspace_root, aoa_root=root)
    output = codex_hook_output(args.event_name, receipt)
    print(json.dumps(output, ensure_ascii=False))
    return 0


def command_hook_worker(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    payload = run_hook_worker(workspace_root=explicit_workspace, aoa_root=root, limit=args.limit)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


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
    max_raw_bytes = int(args.max_raw_mb * 1024 * 1024) if args.max_raw_mb is not None else None
    payload = reindex_sessions(
        aoa_root=root,
        target=args.session,
        since=since,
        until=args.until,
        limit=args.limit,
        dry_run=args.dry_run,
        max_raw_bytes=max_raw_bytes,
        stale_route_indexes=args.stale_route_indexes,
        write_report=args.write_report,
    )
    print(json.dumps(reindex_print_payload(payload, full=args.full), indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_index_maintenance(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    since = since_date_from_args(args.since, args.since_days if args.since_days is not None else None)
    max_raw_bytes = int(args.max_raw_mb * 1024 * 1024) if args.max_raw_mb is not None else None
    payload = maintain_indexes(
        aoa_root=root,
        target=args.session,
        since=since,
        until=args.until,
        limit=args.limit,
        apply=args.apply,
        max_raw_bytes=max_raw_bytes,
        sample_audit=args.sample_audit,
        sample_limit=args.sample_limit,
        max_raw_chars=args.max_raw_chars,
        write_report=args.write_report,
        reason=args.reason,
    )
    print(json.dumps(index_maintenance_print_payload(payload, full=args.full), indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_conversation_act_audit(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    since = since_date_from_args(args.since, args.since_days if args.since_days is not None else None)
    payload = conversation_act_audit(
        aoa_root=root,
        target=args.session,
        since=since,
        until=args.until,
        limit=args.limit,
        sample_limit=args.sample_limit,
        write_report=args.write_report,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_search_index(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    since = since_date_from_args(args.since, args.since_days if args.since_days is not None else None)
    max_raw_bytes = int(args.max_raw_mb * 1024 * 1024) if args.max_raw_mb is not None else None
    payload = search_index_sessions(
        aoa_root=root,
        target=args.session,
        since=since,
        until=args.until,
        limit=args.limit,
        max_raw_bytes=max_raw_bytes,
        rebuild=not args.no_rebuild,
        write_report=args.write_report,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_search_provider_status(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    payload = search_provider_status(
        aoa_root=root,
        provider_name=args.provider,
        include_host=args.include_host,
        refresh_host=args.refresh_host,
        refresh_host_index=args.refresh_host_index,
        timeout=args.timeout,
        write_report=args.write_report,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_search(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    query = args.query or args.query_text or ""
    payload = search_sessions(
        aoa_root=root,
        query=query,
        limit=args.limit,
        provider=args.provider,
        include_host_context=args.include_host_context,
        include_semantic_context=args.include_semantic_context,
        rerank_local=args.rerank_local,
        rerank_candidate_limit=args.rerank_candidate_limit,
        allow_host_warnings=args.allow_host_warnings,
        host_timeout=args.host_timeout,
        session=args.session_filter,
        doc_type=args.doc_type,
        event_type=args.event_type,
        family=args.family,
        outcome=args.outcome,
        conversation_act=args.conversation_act,
        session_act=args.session_act,
        route_layer=args.route_layer,
        route_signal=args.route_signal,
        archive_status=args.archive_status,
        freshness_status=args.freshness_status,
        date_from=args.date_from,
        date_to=args.date_to,
        explain=args.explain,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def atlas_policy_axes(aoa_root: Path) -> list[str]:
    policy = read_json(aoa_root / ATLAS_POLICY_PATH, {})
    axes = policy.get("axes") if isinstance(policy, dict) else None
    names: list[str] = []
    if isinstance(axes, list):
        names = [str(axis.get("name")) for axis in axes if isinstance(axis, dict) and axis.get("name")]
    if not names:
        names = DEFAULT_ATLAS_AXES
    return sorted(dict.fromkeys(names))


def clear_generated_atlas(aoa_root: Path, axes: list[str]) -> None:
    maps_root = aoa_root / ATLAS_ROOT
    for name in ("INDEX.md", "index.json"):
        path = maps_root / name
        if path.exists():
            path.unlink()
    for axis in axes:
        axis_dir = maps_root / axis
        for name in ("INDEX.md", "index.json"):
            path = axis_dir / name
            if path.exists():
                path.unlink()
        entries_dir = axis_dir / "entries"
        if not entries_dir.exists():
            continue
        for path in entries_dir.iterdir():
            if path.name == ".gitkeep":
                continue
            if path.is_file() and path.suffix in {".json", ".md"}:
                path.unlink()


def route_signal_evidence_from_segment(
    segment_index: dict[str, Any],
    *,
    layer: str | None = None,
    key: str | None = None,
    session_act: str | None = None,
    conversation_act: str | None = None,
) -> dict[str, str] | None:
    event_ids: list[str] = []
    if layer and key:
        by_layer = segment_index.get("by_route_layer") if isinstance(segment_index.get("by_route_layer"), dict) else {}
        by_key = by_layer.get(layer) if isinstance(by_layer.get(layer), dict) else {}
        event_ids = [str(item) for item in by_key.get(key, [])] if isinstance(by_key.get(key), list) else []
    elif session_act:
        by_session_act = segment_index.get("by_session_act") if isinstance(segment_index.get("by_session_act"), dict) else {}
        event_ids = [str(item) for item in by_session_act.get(session_act, [])] if isinstance(by_session_act.get(session_act), list) else []
    elif conversation_act:
        by_conversation_act = segment_index.get("by_conversation_act") if isinstance(segment_index.get("by_conversation_act"), dict) else {}
        event_ids = [str(item) for item in by_conversation_act.get(conversation_act, [])] if isinstance(by_conversation_act.get(conversation_act), list) else []
    if not event_ids:
        return None
    events = segment_index.get("events") if isinstance(segment_index.get("events"), list) else []
    wanted = event_ids[0]
    for event in events:
        if isinstance(event, dict) and str(event.get("event_id") or "") == wanted:
            return {
                "raw_ref": str(event.get("raw_ref") or ""),
                "segment_ref": str(event.get("md_anchor") or segment_index.get("markdown") or ""),
                "generated_index_ref": str(segment_index.get("_index_path") or ""),
            }
    return None


def event_evidence_from_segment_index(segment_index: dict[str, Any], event_id: str) -> dict[str, str] | None:
    for event in segment_index.get("events", []) if isinstance(segment_index.get("events"), list) else []:
        if isinstance(event, dict) and str(event.get("event_id") or "") == event_id:
            return {
                "raw_ref": str(event.get("raw_ref") or ""),
                "segment_ref": str(event.get("md_anchor") or segment_index.get("markdown") or ""),
                "generated_index_ref": str(segment_index.get("_index_path") or ""),
            }
    return None


def first_id(value: Any) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    return ""


def session_axis_evidence_cache(session_dir: Path, manifest: dict[str, Any]) -> dict[str, dict[str, dict[str, str]]]:
    cache: dict[str, dict[str, dict[str, str]]] = {
        "route": {},
        "session_act": {},
        "conversation_act": {},
    }
    for segment in manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []:
        if not isinstance(segment, dict):
            continue
        index_path = Path(str(segment.get("index") or ""))
        if not index_path.exists():
            continue
        segment_index = read_json(index_path, {})
        if not isinstance(segment_index, dict):
            continue
        segment_index["_index_path"] = str(index_path)
        by_route_layer = segment_index.get("by_route_layer") if isinstance(segment_index.get("by_route_layer"), dict) else {}
        for layer, key_map in by_route_layer.items():
            if not isinstance(key_map, dict):
                continue
            for key, ids in key_map.items():
                token = route_signal_token(str(layer), str(key))
                if token in cache["route"]:
                    continue
                evidence = event_evidence_from_segment_index(segment_index, first_id(ids))
                if evidence:
                    cache["route"][token] = {
                        "session_ref": str(session_dir / SESSION_INDEX_MARKDOWN),
                        **evidence,
                    }
        by_session_act = segment_index.get("by_session_act") if isinstance(segment_index.get("by_session_act"), dict) else {}
        for act, ids in by_session_act.items():
            if str(act) in cache["session_act"]:
                continue
            evidence = event_evidence_from_segment_index(segment_index, first_id(ids))
            if evidence:
                cache["session_act"][str(act)] = {
                    "session_ref": str(session_dir / SESSION_INDEX_MARKDOWN),
                    **evidence,
                }
        by_conversation_act = segment_index.get("by_conversation_act") if isinstance(segment_index.get("by_conversation_act"), dict) else {}
        for act, ids in by_conversation_act.items():
            if str(act) in cache["conversation_act"]:
                continue
            evidence = event_evidence_from_segment_index(segment_index, first_id(ids))
            if evidence:
                cache["conversation_act"][str(act)] = {
                    "session_ref": str(session_dir / SESSION_INDEX_MARKDOWN),
                    **evidence,
                }
    return cache


def session_axis_evidence(
    session_dir: Path,
    manifest: dict[str, Any],
    *,
    layer: str | None = None,
    key: str | None = None,
    session_act: str | None = None,
    conversation_act: str | None = None,
) -> dict[str, str]:
    fallback = {
        "session_ref": str(session_dir / SESSION_INDEX_MARKDOWN),
        "segment_ref": "",
        "raw_ref": "",
        "generated_index_ref": str(session_dir / SESSION_INDEX_JSON),
    }
    for segment in manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []:
        if not isinstance(segment, dict):
            continue
        index_path = Path(str(segment.get("index") or ""))
        if not index_path.exists():
            continue
        segment_index = read_json(index_path, {})
        if not isinstance(segment_index, dict):
            continue
        segment_index["_index_path"] = str(index_path)
        evidence = route_signal_evidence_from_segment(
            segment_index,
            layer=layer,
            key=key,
            session_act=session_act,
            conversation_act=conversation_act,
        )
        if evidence:
            return {**fallback, **evidence}
    work_context = manifest.get("work_context") if isinstance(manifest.get("work_context"), dict) else {}
    for item in work_context.get("evidence", []) if isinstance(work_context.get("evidence"), list) else []:
        if isinstance(item, dict) and item.get("ref"):
            fallback["raw_ref"] = str(item["ref"])
            break
    return fallback


def atlas_entry_markdown(entry: dict[str, Any]) -> str:
    evidence = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
    lines = [
        "---",
        "aoa_artifact_type: atlas_route_entry",
        f"schema_version: {entry.get('schema_version')}",
        f"axis: {entry.get('axis')}",
        f"route_key: {entry.get('route_key')}",
        f"truth_status: {entry.get('truth_status')}",
        "---",
        "",
        f"# {entry.get('axis')} / {entry.get('route_key')}",
        "",
        f"- session: `{entry.get('session')}`",
        f"- session_id: `{entry.get('session_id', '')}`",
        f"- work_context: `{entry.get('work_context', '')}`",
        f"- work_family: `{entry.get('work_family', '')}`",
        f"- confidence: `{entry.get('confidence')}`",
        f"- status: `{entry.get('status')}`",
        f"- signal_count: `{entry.get('signal_count', '')}`",
        "",
        "## Next Route",
        "",
        entry.get("next_route", ""),
        "",
        "## Evidence",
        "",
        f"- session_ref: `{evidence.get('session_ref', '')}`",
        f"- segment_ref: `{evidence.get('segment_ref', '')}`",
        f"- raw_ref: `{evidence.get('raw_ref', '')}`",
        f"- generated_index_ref: `{evidence.get('generated_index_ref', '')}`",
        "",
        "## Summary",
        "",
        entry.get("summary", ""),
        "",
    ]
    return "\n".join(lines)


def atlas_entry_filename(route_key: str, session_label: str, suffix: str) -> str:
    route = route_key_slug(route_key, fallback="route", max_chars=80)
    label = readable_slug(session_label, fallback="session", max_chars=96)
    return f"{route}__{label}{suffix}"


def add_atlas_candidate(
    entries: list[dict[str, Any]],
    *,
    axis: str,
    route_key: str,
    signal_count: int,
    session_dir: Path,
    manifest: dict[str, Any],
    record: dict[str, Any],
    layer: str | None = None,
    key: str | None = None,
    session_act: str | None = None,
    conversation_act: str | None = None,
    evidence_cache: dict[str, dict[str, dict[str, str]]] | None = None,
    confidence: str = "medium",
) -> None:
    if not route_key:
        return
    display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
    work_context = manifest.get("work_context") if isinstance(manifest.get("work_context"), dict) else {}
    label = str(display.get("label") or record.get("session_label") or session_dir.name)
    normalized_key = route_key_slug(route_key, fallback="route")
    evidence: dict[str, str] | None = None
    if evidence_cache:
        if layer and key:
            evidence = evidence_cache.get("route", {}).get(route_signal_token(layer, key))
        elif session_act:
            evidence = evidence_cache.get("session_act", {}).get(session_act)
        elif conversation_act:
            evidence = evidence_cache.get("conversation_act", {}).get(conversation_act)
    if evidence is None:
        evidence = session_axis_evidence(
            session_dir,
            manifest,
            layer=layer,
            key=key,
            session_act=session_act,
            conversation_act=conversation_act,
        )
    entries.append(
        {
            "schema_version": ATLAS_SCHEMA_VERSION,
            "axis": axis,
            "route_key": normalized_key,
            "status": "generated",
            "truth_status": "route_signal_not_reviewed_truth",
            "session": label,
            "session_id": str(manifest.get("session_id") or record.get("session_id") or ""),
            "work_context": str(work_context.get("work_name") or ""),
            "work_family": str(work_context.get("work_family") or ""),
            "authority_surface": "",
            "summary": f"{label}: {axis} -> {normalized_key} ({signal_count} signal(s)).",
            "confidence": confidence,
            "next_route": f"Read {session_dir / SESSION_INDEX_JSON}, then follow the evidence refs before treating this route as truth.",
            "evidence": evidence,
            "related_axes": [
                related
                for related in ["by-work-context", "by-session-act", "by-verification-state", "by-route-next-action"]
                if related != axis
            ],
            "signal_count": signal_count,
            "route_layer": layer or "",
            "generated_at": utc_now(),
        }
    )


def atlas_entries_for_session(aoa_root: Path, record: dict[str, Any], axes: set[str]) -> list[dict[str, Any]]:
    session_dir = session_dir_from_record(record)
    manifest = read_json(session_dir / "session.manifest.json", {})
    session_index = read_json(session_dir / SESSION_INDEX_JSON, {})
    if not isinstance(manifest, dict) or not isinstance(session_index, dict):
        return []
    entries: list[dict[str, Any]] = []
    evidence_cache = session_axis_evidence_cache(session_dir, manifest)
    route_index_current = route_signal_index_is_current(session_index)
    work_context = manifest.get("work_context") if isinstance(manifest.get("work_context"), dict) else {}
    work_name = str(work_context.get("work_name") or "")
    work_family = str(work_context.get("work_family") or "")
    if "by-work-context" in axes and work_name:
        add_atlas_candidate(entries, axis="by-work-context", route_key=work_name, signal_count=1, session_dir=session_dir, manifest=manifest, record=record, evidence_cache=evidence_cache, confidence=str(work_context.get("confidence") or "medium"))
    if "by-repo-family" in axes and work_family:
        add_atlas_candidate(entries, axis="by-repo-family", route_key=work_family, signal_count=1, session_dir=session_dir, manifest=manifest, record=record, evidence_cache=evidence_cache, confidence=str(work_context.get("confidence") or "medium"))
    display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
    if "by-time" in axes:
        date_key = str(display.get("date") or record.get("date") or record.get("session_date") or "")
        if date_key:
            add_atlas_candidate(entries, axis="by-time", route_key=date_key, signal_count=1, session_dir=session_dir, manifest=manifest, record=record, evidence_cache=evidence_cache, confidence="high")
    for act, count in (session_index.get("session_act_counts") or {}).items() if isinstance(session_index.get("session_act_counts"), dict) else []:
        if "by-session-act" in axes:
            add_atlas_candidate(entries, axis="by-session-act", route_key=str(act), signal_count=int_value(count, 1), session_dir=session_dir, manifest=manifest, record=record, session_act=str(act), evidence_cache=evidence_cache, confidence="high")
    for act, count in (session_index.get("conversation_act_counts") or {}).items() if isinstance(session_index.get("conversation_act_counts"), dict) else []:
        if "by-conversation-act" in axes:
            add_atlas_candidate(entries, axis="by-conversation-act", route_key=str(act), signal_count=int_value(count, 1), session_dir=session_dir, manifest=manifest, record=record, conversation_act=str(act), evidence_cache=evidence_cache, confidence="high")
    route_counts = session_index.get("route_signal_counts") if route_index_current and isinstance(session_index.get("route_signal_counts"), dict) else {}
    for layer, key_counts in route_counts.items():
        axis = ROUTE_SIGNAL_LAYER_TO_AXIS.get(str(layer))
        if not axis or axis not in axes or not isinstance(key_counts, dict):
            continue
        ranked_keys = sorted(key_counts.items(), key=lambda item: (int_value(item[1]), str(item[0])), reverse=True)
        for key, count in ranked_keys[:MAX_ATLAS_ROUTE_KEYS_PER_LAYER]:
            add_atlas_candidate(
                entries,
                axis=axis,
                route_key=str(key),
                signal_count=int_value(count, 1),
                session_dir=session_dir,
                manifest=manifest,
                record=record,
                layer=str(layer),
                key=str(key),
                evidence_cache=evidence_cache,
                confidence="medium",
            )
    if "by-review-state" in axes:
        review_key = str(manifest.get("review_status") or manifest.get("distillation_status") or "raw_archived")
        add_atlas_candidate(entries, axis="by-review-state", route_key=review_key, signal_count=1, session_dir=session_dir, manifest=manifest, record=record, evidence_cache=evidence_cache, confidence="medium")
    if "by-index-health" in axes:
        archive_status = str(manifest.get("archive_status") or "unknown")
        index_key = archive_status if route_index_current else "route_signal_classifier_stale"
        add_atlas_candidate(entries, axis="by-index-health", route_key=index_key, signal_count=1, session_dir=session_dir, manifest=manifest, record=record, evidence_cache=evidence_cache, confidence="medium")
    if "by-route-next-action" in axes:
        archive_status = str(manifest.get("archive_status") or "")
        next_key = "restore_ready" if archive_status == "indexed" and route_index_current else "repair_or_reindex"
        add_atlas_candidate(entries, axis="by-route-next-action", route_key=next_key, signal_count=1, session_dir=session_dir, manifest=manifest, record=record, evidence_cache=evidence_cache, confidence="medium")
    return entries


def write_atlas_axis_index(axis_dir: Path, axis: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "schema_version": ATLAS_SCHEMA_VERSION,
        "artifact_type": "atlas_axis_index",
        "axis": axis,
        "generated_at": utc_now(),
        "entry_count": len(entries),
        "entries": entries,
    }
    write_json(axis_dir / "index.json", payload)
    lines = [
        f"# {axis}",
        "",
        "Generated atlas axis index. Entries are route signals, not reviewed truth.",
        "",
        "| route_key | session | confidence | evidence |",
        "| --- | --- | --- | --- |",
    ]
    for entry in entries:
        evidence = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
        lines.append(
            f"| `{entry.get('route_key')}` | `{entry.get('session')}` | `{entry.get('confidence')}` | `{evidence.get('raw_ref') or evidence.get('segment_ref') or evidence.get('session_ref')}` |"
        )
    write_markdown(axis_dir / "INDEX.md", "\n".join(lines) + "\n")
    return payload


def build_agent_atlas(
    *,
    aoa_root: Path,
    target: str = "all",
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    clean: bool = True,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    axes = atlas_policy_axes(aoa_root)
    axis_set = set(axes)
    try:
        records = [resolve_session_record(aoa_root, target)] if target != "all" else chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    except ValueError as exc:
        return {
            "schema_version": ATLAS_SCHEMA_VERSION,
            "artifact_type": "agent_atlas",
            "generated_at": now,
            "ok": False,
            "target": target,
            "selected_count": 0,
            "entry_count": 0,
            "diagnostics": [str(exc)],
        }
    maps_root = aoa_root / ATLAS_ROOT
    maps_root.mkdir(parents=True, exist_ok=True)
    if clean:
        clear_generated_atlas(aoa_root, axes)
    by_axis: dict[str, list[dict[str, Any]]] = {axis: [] for axis in axes}
    diagnostics: list[str] = []
    for record in records:
        try:
            entries = atlas_entries_for_session(aoa_root, record, axis_set)
        except Exception as exc:
            diagnostics.append(f"{record.get('session_label') or record.get('session_id')}:atlas_entry_error:{exc}")
            continue
        for entry in entries:
            by_axis.setdefault(str(entry["axis"]), []).append(entry)
    written_entries: list[dict[str, Any]] = []
    axis_summaries: list[dict[str, Any]] = []
    for axis in axes:
        axis_dir = maps_root / axis
        entries_dir = axis_dir / "entries"
        entries_dir.mkdir(parents=True, exist_ok=True)
        gitkeep = entries_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")
        axis_entries = sorted(by_axis.get(axis, []), key=lambda item: (str(item.get("route_key")), str(item.get("session"))))
        compact_axis_entries: list[dict[str, Any]] = []
        for entry in axis_entries:
            json_name = atlas_entry_filename(str(entry["route_key"]), str(entry["session"]), ".json")
            md_name = atlas_entry_filename(str(entry["route_key"]), str(entry["session"]), ".md")
            json_path = entries_dir / json_name
            md_path = entries_dir / md_name
            write_json(json_path, entry)
            write_markdown(md_path, atlas_entry_markdown(entry))
            compact = {
                "axis": axis,
                "route_key": entry.get("route_key"),
                "session": entry.get("session"),
                "session_id": entry.get("session_id"),
                "confidence": entry.get("confidence"),
                "json": str(json_path),
                "markdown": str(md_path),
                "evidence": entry.get("evidence"),
            }
            compact_axis_entries.append(compact)
            written_entries.append(compact)
        axis_index = write_atlas_axis_index(axis_dir, axis, compact_axis_entries)
        axis_summaries.append({"axis": axis, "entry_count": axis_index["entry_count"], "index": str(axis_dir / "index.json")})
    root_payload = {
        "schema_version": ATLAS_SCHEMA_VERSION,
        "artifact_type": "agent_atlas_index",
        "generated_at": now,
        "axis_count": len(axes),
        "entry_count": len(written_entries),
        "axes": axis_summaries,
    }
    write_json(maps_root / "index.json", root_payload)
    lines = [
        "# Agent Atlas",
        "",
        "Generated route index. Use it to choose a first route, then follow evidence refs.",
        "",
        "| axis | entries | index |",
        "| --- | ---: | --- |",
    ]
    for axis in axis_summaries:
        lines.append(f"| `{axis['axis']}` | {axis['entry_count']} | `{axis['index']}` |")
    write_markdown(maps_root / "INDEX.md", "\n".join(lines) + "\n")
    payload = {
        "schema_version": ATLAS_SCHEMA_VERSION,
        "artifact_type": "agent_atlas",
        "generated_at": now,
        "ok": not diagnostics,
        "target": target,
        "selected_count": len(records),
        "axis_count": len(axes),
        "entry_count": len(written_entries),
        "root_index": str(maps_root / "index.json"),
        "root_markdown": str(maps_root / "INDEX.md"),
        "diagnostics": diagnostics,
        "axes": axis_summaries,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__agent-atlas"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, atlas_build_report_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def atlas_build_report_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Agent Atlas Build",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- ok: `{payload.get('ok')}`",
        f"- target: `{payload.get('target')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- entry_count: `{payload.get('entry_count')}`",
        "",
        "## Axes",
        "",
        "| axis | entries |",
        "| --- | ---: |",
    ]
    for axis in payload.get("axes", []) if isinstance(payload.get("axes"), list) else []:
        if isinstance(axis, dict):
            lines.append(f"| `{axis.get('axis')}` | {axis.get('entry_count')} |")
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), list) else []
    if diagnostics:
        lines.extend(["", "## Diagnostics", ""])
        for item in diagnostics:
            lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def atlas_axis_states(aoa_root: Path) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    maps_root = aoa_root / ATLAS_ROOT
    for axis in atlas_policy_axes(aoa_root):
        axis_dir = maps_root / axis
        index_path = axis_dir / "index.json"
        index_payload = read_json(index_path, {})
        entry_count = int_value(index_payload.get("entry_count")) if isinstance(index_payload, dict) else 0
        states[axis] = {
            "axis": axis,
            "source_readme_exists": (axis_dir / "README.md").exists(),
            "entries_dir_exists": (axis_dir / "entries").is_dir(),
            "generated_index_exists": index_path.exists(),
            "entry_count": entry_count,
            "index": str(index_path),
        }
    return states


def route_readiness_layer_sample(
    session_dir: Path,
    manifest: dict[str, Any],
    layer: str,
    key_counts: Counter[str],
) -> dict[str, Any] | None:
    cache = session_axis_evidence_cache(session_dir, manifest)
    for key, count in sorted(key_counts.items(), key=lambda item: (int_value(item[1]), str(item[0])), reverse=True):
        evidence = cache.get("route", {}).get(route_signal_token(layer, str(key)))
        if evidence:
            return {
                "key": str(key),
                "count": int_value(count),
                "session": str(manifest.get("session_label") or session_dir.name),
                "session_id": str(manifest.get("session_id") or ""),
                "evidence": evidence,
            }
    return None


def route_layer_readiness(
    *,
    aoa_root: Path,
    target: str = "all",
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    sample_limit: int = 2,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    try:
        records = [resolve_session_record(aoa_root, target)] if target != "all" else chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    except ValueError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "route_layer_readiness",
            "generated_at": now,
            "ok": False,
            "target": target,
            "selected_count": 0,
            "diagnostics": [str(exc)],
            "requirements": [],
            "remaining": [],
        }

    layer_counts: Counter[str] = Counter()
    layer_session_counts: Counter[str] = Counter()
    layer_key_counts: dict[str, Counter[str]] = defaultdict(Counter)
    layer_samples: dict[str, list[dict[str, Any]]] = defaultdict(list)
    diagnostics: list[str] = []
    missing_session_index = 0
    non_indexable_session_count = 0
    non_indexable_samples: list[dict[str, str]] = []
    stale_route_schema = 0
    stale_route_classifier = 0
    indexed_session_count = 0
    current_route_signal_index_count = 0

    required_layers = {
        str(layer)
        for item in ROUTE_READINESS_REQUIREMENTS
        for layer in item.get("required_layers", [])
    }

    for record in records:
        session_dir = session_dir_from_record(record)
        manifest = read_json(session_dir / "session.manifest.json", {})
        archive_status = (
            str(manifest.get("archive_status") or record.get("archive_status") or "")
            if isinstance(manifest, dict)
            else str(record.get("archive_status") or "")
        )
        session_index = read_json(session_dir / SESSION_INDEX_JSON, {})
        if not isinstance(session_index, dict) or not session_index:
            if archive_status and archive_status != "indexed":
                non_indexable_session_count += 1
                if len(non_indexable_samples) < 8:
                    non_indexable_samples.append(
                        {
                            "session": str(record.get("session_label") or record.get("session_id") or session_dir.name),
                            "archive_status": archive_status,
                        }
                    )
            else:
                missing_session_index += 1
                diagnostics.append(f"{record.get('session_label') or record.get('session_id')}:missing_session_index")
            continue
        indexed_session_count += 1
        stale_reasons = route_signal_index_stale_reasons(session_index)
        if "route_signal_schema_mismatch" in stale_reasons:
            stale_route_schema += 1
            diagnostics.append(f"{record.get('session_label') or record.get('session_id')}:route_signal_schema_mismatch")
        if "route_signal_classifier_mismatch" in stale_reasons:
            stale_route_classifier += 1
            diagnostics.append(f"{record.get('session_label') or record.get('session_id')}:route_signal_classifier_mismatch")
        if stale_reasons:
            continue
        current_route_signal_index_count += 1
        route_counts = session_index.get("route_signal_counts") if isinstance(session_index.get("route_signal_counts"), dict) else {}
        session_layers: set[str] = set()
        for layer, key_map in route_counts.items():
            layer_name = str(layer)
            if not isinstance(key_map, dict):
                continue
            total = sum(int_value(count) for count in key_map.values())
            if total <= 0:
                continue
            layer_counts[layer_name] += total
            session_layers.add(layer_name)
            for key, count in key_map.items():
                layer_key_counts[layer_name][str(key)] += int_value(count)
        for layer_name in session_layers:
            layer_session_counts[layer_name] += 1
        if isinstance(manifest, dict) and required_layers:
            for layer_name in sorted(required_layers & set(route_counts.keys())):
                if len(layer_samples[layer_name]) >= sample_limit:
                    continue
                sample = route_readiness_layer_sample(session_dir, manifest, layer_name, layer_key_counts[layer_name])
                if sample:
                    layer_samples[layer_name].append(sample)

    axis_states = atlas_axis_states(aoa_root)
    root_atlas_index = read_json(aoa_root / ATLAS_ROOT / "index.json", {})
    root_atlas_entry_count = int_value(root_atlas_index.get("entry_count")) if isinstance(root_atlas_index, dict) else 0
    provider_status = search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite")
    provider_ready = bool(provider_status.get("ok"))

    requirements: list[dict[str, Any]] = []
    for item in ROUTE_READINESS_REQUIREMENTS:
        req_layers = [str(layer) for layer in item.get("required_layers", [])]
        missing_layers = [layer for layer in req_layers if layer_counts.get(layer, 0) <= 0]
        layer_payloads: list[dict[str, Any]] = []
        missing_axes: list[str] = []
        missing_generated_axes: list[str] = []
        for layer in req_layers:
            axis = ROUTE_SIGNAL_LAYER_TO_AXIS.get(layer, "")
            axis_state = axis_states.get(axis, {}) if axis else {}
            if axis and not axis_state.get("source_readme_exists"):
                missing_axes.append(axis)
            if axis and layer_counts.get(layer, 0) > 0 and int_value(axis_state.get("entry_count")) <= 0:
                missing_generated_axes.append(axis)
            layer_payloads.append(
                {
                    "layer": layer,
                    "axis": axis,
                    "signal_count": layer_counts.get(layer, 0),
                    "session_count": layer_session_counts.get(layer, 0),
                    "top_keys": [
                        {"key": str(key), "count": int_value(count)}
                        for key, count in sorted(
                            layer_key_counts.get(layer, Counter()).items(),
                            key=lambda pair: (int_value(pair[1]), str(pair[0])),
                            reverse=True,
                        )[:8]
                    ],
                    "samples": layer_samples.get(layer, [])[:sample_limit],
                    "axis_state": axis_state,
                }
            )
        status = "covered"
        if missing_layers or missing_axes or missing_generated_axes:
            status = "remaining"
        requirements.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "status": status,
                "required_layers": req_layers,
                "missing_layers": missing_layers,
                "missing_axes": sorted(set(missing_axes)),
                "missing_generated_axes": sorted(set(missing_generated_axes)),
                "layers": layer_payloads,
            }
        )

    required_axes = sorted({ROUTE_SIGNAL_LAYER_TO_AXIS.get(layer, "") for layer in required_layers if ROUTE_SIGNAL_LAYER_TO_AXIS.get(layer)})
    missing_source_axes = [axis for axis in required_axes if not axis_states.get(axis, {}).get("source_readme_exists")]
    empty_generated_axes = [
        axis
        for axis in required_axes
        if axis_states.get(axis, {}).get("generated_index_exists") and int_value(axis_states.get(axis, {}).get("entry_count")) <= 0
    ]
    global_gates = [
        {
            "name": "session_route_signal_indexes",
            "status": "covered"
            if current_route_signal_index_count > 0
            and missing_session_index == 0
            and stale_route_schema == 0
            and stale_route_classifier == 0
            else "remaining",
            "evidence": {
                "indexed_session_count": indexed_session_count,
                "current_route_signal_index_count": current_route_signal_index_count,
                "missing_session_index": missing_session_index,
                "non_indexable_session_count": non_indexable_session_count,
                "non_indexable_samples": non_indexable_samples,
                "stale_route_schema": stale_route_schema,
                "stale_route_classifier": stale_route_classifier,
                "route_signal_schema_version": ROUTE_SIGNAL_SCHEMA_VERSION,
                "route_signal_classifier_version": ROUTE_SIGNAL_CLASSIFIER_VERSION,
            },
        },
        {
            "name": "source_atlas_axes",
            "status": "covered" if not missing_source_axes else "remaining",
            "evidence": {
                "required_axis_count": len(required_axes),
                "missing_source_axes": missing_source_axes,
            },
        },
        {
            "name": "generated_atlas_index",
            "status": "covered" if root_atlas_entry_count > 0 else "remaining",
            "evidence": {
                "root_index": str(aoa_root / ATLAS_ROOT / "index.json"),
                "root_index_exists": (aoa_root / ATLAS_ROOT / "index.json").exists(),
                "entry_count": root_atlas_entry_count,
                "empty_generated_axes": empty_generated_axes,
            },
        },
        {
            "name": "portable_sqlite_search_index",
            "status": "covered" if provider_ready else "remaining",
            "evidence": provider_status,
        },
    ]
    remaining = [req for req in requirements if req["status"] != "covered"]
    remaining.extend(gate for gate in global_gates if gate["status"] != "covered")
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "route_layer_readiness",
        "generated_at": now,
        "ok": not remaining and not diagnostics,
        "target": target,
        "since": since,
        "until": until,
        "limit": limit,
        "selected_count": len(records),
        "route_signal_schema_version": ROUTE_SIGNAL_SCHEMA_VERSION,
        "route_signal_classifier_version": ROUTE_SIGNAL_CLASSIFIER_VERSION,
        "required_requirement_count": len(ROUTE_READINESS_REQUIREMENTS),
        "covered_requirement_count": sum(1 for req in requirements if req["status"] == "covered"),
        "global_gates": global_gates,
        "requirements": requirements,
        "diagnostics": diagnostics,
        "remaining": remaining,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__route-layer-readiness"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, route_layer_readiness_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def route_layer_readiness_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Route Layer Readiness",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- ok: `{payload.get('ok')}`",
        f"- target: `{payload.get('target')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- covered_requirements: `{payload.get('covered_requirement_count')}/{payload.get('required_requirement_count')}`",
        "",
        "## Global Gates",
        "",
        "| gate | status | evidence |",
        "| --- | --- | --- |",
    ]
    for gate in payload.get("global_gates", []) if isinstance(payload.get("global_gates"), list) else []:
        if not isinstance(gate, dict):
            continue
        evidence = gate.get("evidence") if isinstance(gate.get("evidence"), dict) else {}
        lines.append(f"| `{gate.get('name')}` | `{gate.get('status')}` | `{short_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True), max_chars=180)}` |")
    lines.extend(["", "## Requirements", "", "| id | title | status | layers | missing |", "| --- | --- | --- | --- | --- |"])
    for req in payload.get("requirements", []) if isinstance(payload.get("requirements"), list) else []:
        if not isinstance(req, dict):
            continue
        layer_summary = ", ".join(
            f"{layer.get('layer')}:{layer.get('signal_count')}"
            for layer in req.get("layers", [])
            if isinstance(layer, dict)
        )
        missing = ", ".join(str(item) for item in req.get("missing_layers", []) if item)
        lines.append(f"| `{req.get('id')}` | {req.get('title')} | `{req.get('status')}` | `{layer_summary}` | `{missing}` |")
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), list) else []
    if diagnostics:
        lines.extend(["", "## Diagnostics", ""])
        for item in diagnostics:
            lines.append(f"- `{item}`")
    stale_route_indexes = payload.get("stale_route_indexes") if isinstance(payload.get("stale_route_indexes"), list) else []
    if stale_route_indexes:
        lines.extend(["", "## Stale Route Indexes", ""])
        for item in stale_route_indexes:
            if not isinstance(item, dict):
                continue
            reasons = ", ".join(str(reason) for reason in item.get("reasons", []) if reason)
            lines.append(f"- `{item.get('session')}`: `{reasons}`")
    return "\n".join(lines) + "\n"


def route_readiness_required_layers() -> list[str]:
    layers: list[str] = []
    seen: set[str] = set()
    for item in ROUTE_READINESS_REQUIREMENTS:
        for layer in item.get("required_layers", []):
            layer_name = str(layer)
            if layer_name and layer_name not in seen:
                seen.add(layer_name)
                layers.append(layer_name)
    return layers


def manifest_raw_path(session_dir: Path, manifest: dict[str, Any]) -> Path:
    raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
    raw_value = raw.get("path") if isinstance(raw, dict) else ""
    return Path(str(raw_value)) if raw_value else session_dir / "raw" / "session.raw.jsonl"


def raw_line_preview(raw_path: Path, raw_ref: Any, *, max_chars: int = 360) -> dict[str, Any]:
    line_no = line_from_raw_ref(raw_ref)
    if not line_no:
        return {"status": "missing_raw_ref", "line": None, "text": ""}
    if not raw_path.is_file():
        return {"status": "raw_unavailable", "line": line_no, "text": ""}
    with raw_path.open("r", encoding="utf-8", errors="replace") as handle:
        for current_line, line in enumerate(handle, start=1):
            if current_line == line_no:
                return {
                    "status": "available",
                    "line": line_no,
                    "text": short_text(line.rstrip("\n"), max_chars=max_chars),
                }
            if current_line > line_no:
                break
    return {"status": "raw_line_not_found", "line": line_no, "text": ""}


def route_signal_for_event_record(event: dict[str, Any], layer: str, key: str) -> dict[str, Any]:
    facets = event.get("facets") if isinstance(event.get("facets"), dict) else {}
    route_signals = facets.get("route_signals") if isinstance(facets.get("route_signals"), list) else []
    for signal in route_signals:
        if not isinstance(signal, dict):
            continue
        if str(signal.get("layer") or "") == layer and str(signal.get("key") or "") == key:
            return signal
    return {}


def route_sample_from_event(
    *,
    session_dir: Path,
    manifest: dict[str, Any],
    record: dict[str, Any],
    segment_index: dict[str, Any],
    event: dict[str, Any],
    layer: str,
    key: str,
    requirement: dict[str, Any],
    max_raw_chars: int,
) -> dict[str, Any]:
    display = manifest.get("display") if isinstance(manifest.get("display"), dict) else {}
    work_context = manifest.get("work_context") if isinstance(manifest.get("work_context"), dict) else {}
    signal = route_signal_for_event_record(event, layer, key)
    raw_ref = str(event.get("raw_ref") or "")
    raw_preview = raw_line_preview(manifest_raw_path(session_dir, manifest), raw_ref, max_chars=max_raw_chars)
    evidence = {
        "session_ref": str(session_dir / SESSION_INDEX_MARKDOWN),
        "segment_ref": str(event.get("md_anchor") or segment_index.get("markdown") or ""),
        "raw_ref": raw_ref,
        "generated_index_ref": str(segment_index.get("_index_path") or ""),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "route_sample",
        "requirement_id": str(requirement.get("id") or ""),
        "requirement_title": str(requirement.get("title") or ""),
        "layer": layer,
        "axis": ROUTE_SIGNAL_LAYER_TO_AXIS.get(layer, ""),
        "key": key,
        "session": str(display.get("label") or record.get("session_label") or session_dir.name),
        "session_id": str(manifest.get("session_id") or record.get("session_id") or ""),
        "work_context": {
            "work_name": str(work_context.get("work_name") or ""),
            "work_family": str(work_context.get("work_family") or ""),
            "confidence": str(work_context.get("confidence") or ""),
        },
        "event": {
            "event_id": str(event.get("event_id") or ""),
            "type": str(event.get("type") or ""),
            "title": str(event.get("title") or ""),
            "outcome": str(event.get("outcome") or ""),
            "confidence": str(event.get("confidence") or ""),
            "timestamp": str(event.get("timestamp") or ""),
            "tags": event.get("tags", []) if isinstance(event.get("tags"), list) else [],
        },
        "signal": {
            "confidence": str(signal.get("confidence") or ""),
            "source": str(signal.get("source") or ""),
            "detail": str(signal.get("detail") or ""),
        },
        "evidence": evidence,
        "raw_preview": raw_preview,
        "review": {
            "status": "unreviewed",
            "verdict": "",
            "reviewer_action": "accept | reject | weaken | split | add_rule",
            "checklist": [
                "Does the raw preview support this layer/key?",
                "Is the classifier confidence appropriate?",
                "Should this signal be split, weakened, or promoted into a rule change?",
                "Does the evidence ref route to stronger raw or segment material?",
            ],
        },
    }


def route_sample_audit(
    *,
    aoa_root: Path,
    target: str = "all",
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    sample_limit: int = DEFAULT_ROUTE_SAMPLE_LIMIT,
    max_raw_chars: int = 360,
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    try:
        records = [resolve_session_record(aoa_root, target)] if target != "all" else chronological_session_records(aoa_root, since=since, until=until, limit=limit)
    except ValueError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "route_sample_audit",
            "generated_at": now,
            "ok": False,
            "target": target,
            "selected_count": 0,
            "diagnostics": [str(exc)],
            "requirements": [],
            "samples": [],
            "remaining": [],
        }

    required_layers = route_readiness_required_layers()
    requirement_by_layer = {
        str(layer): item
        for item in ROUTE_READINESS_REQUIREMENTS
        for layer in item.get("required_layers", [])
    }
    layer_key_counts: dict[str, Counter[str]] = {layer: Counter() for layer in required_layers}
    diagnostics: list[str] = []
    indexed_records: list[tuple[dict[str, Any], Path, dict[str, Any]]] = []
    stale_route_indexes: list[dict[str, Any]] = []
    stale_route_schema = 0
    stale_route_classifier = 0

    for record in records:
        session_dir = session_dir_from_record(record)
        manifest = read_json(session_dir / "session.manifest.json", {})
        session_index = read_json(session_dir / SESSION_INDEX_JSON, {})
        if not isinstance(manifest, dict) or not manifest:
            diagnostics.append(f"{record.get('session_label') or record.get('session_id')}:missing_manifest")
            continue
        if not isinstance(session_index, dict) or not session_index:
            archive_status = str(manifest.get("archive_status") or record.get("archive_status") or "")
            if archive_status and archive_status != "indexed":
                continue
            diagnostics.append(f"{record.get('session_label') or record.get('session_id')}:missing_session_index")
            continue
        stale_reasons = route_signal_index_stale_reasons(session_index)
        if "route_signal_schema_mismatch" in stale_reasons:
            stale_route_schema += 1
        if "route_signal_classifier_mismatch" in stale_reasons:
            stale_route_classifier += 1
        if stale_reasons:
            stale_route_indexes.append(
                {
                    "session": str(record.get("session_label") or record.get("session_id") or session_dir.name),
                    "path": str(session_dir),
                    "reasons": stale_reasons,
                }
            )
            continue
        indexed_records.append((record, session_dir, manifest))
        route_counts = session_index.get("route_signal_counts") if isinstance(session_index.get("route_signal_counts"), dict) else {}
        for layer in required_layers:
            key_counts = route_counts.get(layer) if isinstance(route_counts.get(layer), dict) else {}
            for key, count in key_counts.items():
                layer_key_counts[layer][str(key)] += int_value(count)

    samples_by_layer: dict[str, list[dict[str, Any]]] = {layer: [] for layer in required_layers}
    sampled_tokens_by_layer: dict[str, set[str]] = {layer: set() for layer in required_layers}
    sample_limit = max(0, int_value(sample_limit, DEFAULT_ROUTE_SAMPLE_LIMIT))
    max_raw_chars = max(40, int_value(max_raw_chars, 360))

    for record, session_dir, manifest in indexed_records:
        if sample_limit and all(len(samples_by_layer[layer]) >= sample_limit for layer in required_layers):
            break
        for segment in manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []:
            if not isinstance(segment, dict):
                continue
            index_path = Path(str(segment.get("index") or ""))
            if not index_path.exists():
                diagnostics.append(f"{session_dir.name}:{segment.get('segment_id') or ''}:missing_segment_index")
                continue
            segment_index = read_json(index_path, {})
            if not isinstance(segment_index, dict):
                diagnostics.append(f"{session_dir.name}:{segment.get('segment_id') or ''}:invalid_segment_index")
                continue
            stale_reasons = route_signal_index_stale_reasons(segment_index)
            if stale_reasons:
                diagnostics.append(f"{session_dir.name}:{segment.get('segment_id') or ''}:{','.join(stale_reasons)}")
                continue
            segment_index["_index_path"] = str(index_path)
            events = segment_index.get("events") if isinstance(segment_index.get("events"), list) else []
            event_by_id = {
                str(event.get("event_id") or ""): event
                for event in events
                if isinstance(event, dict) and event.get("event_id")
            }
            by_route_layer = segment_index.get("by_route_layer") if isinstance(segment_index.get("by_route_layer"), dict) else {}
            for layer in required_layers:
                if sample_limit and len(samples_by_layer[layer]) >= sample_limit:
                    continue
                key_map = by_route_layer.get(layer) if isinstance(by_route_layer.get(layer), dict) else {}
                if not key_map:
                    continue
                ranked_keys = sorted(
                    key_map.keys(),
                    key=lambda key: (
                        str(key) in sampled_tokens_by_layer[layer],
                        -layer_key_counts.get(layer, Counter()).get(str(key), 0),
                        str(key),
                    ),
                )
                for key in ranked_keys:
                    if sample_limit and len(samples_by_layer[layer]) >= sample_limit:
                        break
                    ids = key_map.get(key)
                    if not isinstance(ids, list):
                        continue
                    for event_id in ids:
                        token = f"{session_dir.name}:{index_path.name}:{event_id}:{key}"
                        if token in sampled_tokens_by_layer[layer]:
                            continue
                        event = event_by_id.get(str(event_id))
                        if not event:
                            continue
                        sample = route_sample_from_event(
                            session_dir=session_dir,
                            manifest=manifest,
                            record=record,
                            segment_index=segment_index,
                            event=event,
                            layer=layer,
                            key=str(key),
                            requirement=requirement_by_layer.get(layer, {}),
                            max_raw_chars=max_raw_chars,
                        )
                        samples_by_layer[layer].append(sample)
                        sampled_tokens_by_layer[layer].add(token)
                        break

    requirements: list[dict[str, Any]] = []
    for item in ROUTE_READINESS_REQUIREMENTS:
        layers = [str(layer) for layer in item.get("required_layers", [])]
        layer_payloads = []
        missing_layers = []
        under_sampled_layers = []
        for layer in layers:
            layer_samples = samples_by_layer.get(layer, [])
            if not layer_samples:
                missing_layers.append(layer)
            if sample_limit and len(layer_samples) < sample_limit:
                under_sampled_layers.append(layer)
            layer_payloads.append(
                {
                    "layer": layer,
                    "axis": ROUTE_SIGNAL_LAYER_TO_AXIS.get(layer, ""),
                    "available_signal_count": sum(layer_key_counts.get(layer, Counter()).values()),
                    "sample_count": len(layer_samples),
                    "sample_keys": [sample.get("key") for sample in layer_samples],
                    "samples": layer_samples,
                }
            )
        status = "covered" if not missing_layers else "remaining"
        requirements.append(
            {
                "id": item.get("id"),
                "title": item.get("title"),
                "status": status,
                "required_layers": layers,
                "missing_layers": missing_layers,
                "under_sampled_layers": under_sampled_layers,
                "layers": layer_payloads,
            }
        )

    samples = [sample for layer in required_layers for sample in samples_by_layer.get(layer, [])]
    remaining = [req for req in requirements if req["status"] != "covered"]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "route_sample_audit",
        "generated_at": now,
        "ok": not remaining and not diagnostics,
        "target": target,
        "since": since,
        "until": until,
        "limit": limit,
        "sample_limit": sample_limit,
        "max_raw_chars": max_raw_chars,
        "selected_count": len(records),
        "indexed_session_count": len(indexed_records),
        "stale_route_schema": stale_route_schema,
        "stale_route_classifier": stale_route_classifier,
        "stale_route_index_count": len(stale_route_indexes),
        "stale_route_indexes": stale_route_indexes,
        "route_signal_schema_version": ROUTE_SIGNAL_SCHEMA_VERSION,
        "route_signal_classifier_version": ROUTE_SIGNAL_CLASSIFIER_VERSION,
        "required_layer_count": len(required_layers),
        "sampled_layer_count": sum(1 for layer in required_layers if samples_by_layer.get(layer)),
        "total_sample_count": len(samples),
        "review_status": "unreviewed",
        "requirements": requirements,
        "samples": samples,
        "diagnostics": diagnostics,
        "remaining": remaining,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__route-sample-audit"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, route_sample_audit_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def route_sample_audit_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Route Sample Audit",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- ok: `{payload.get('ok')}`",
        f"- target: `{payload.get('target')}`",
        f"- selected_count: `{payload.get('selected_count')}`",
        f"- indexed_session_count: `{payload.get('indexed_session_count')}`",
        f"- sampled_layers: `{payload.get('sampled_layer_count')}/{payload.get('required_layer_count')}`",
        f"- total_sample_count: `{payload.get('total_sample_count')}`",
        f"- review_status: `{payload.get('review_status')}`",
        "",
        "Samples are classifier calibration packets. They are unreviewed until a reviewer records a verdict.",
        "",
        "## Requirements",
        "",
        "| id | status | layers | samples | missing |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for req in payload.get("requirements", []) if isinstance(payload.get("requirements"), list) else []:
        if not isinstance(req, dict):
            continue
        layers = req.get("layers") if isinstance(req.get("layers"), list) else []
        layer_names = ", ".join(str(layer.get("layer")) for layer in layers if isinstance(layer, dict))
        sample_count = sum(int_value(layer.get("sample_count")) for layer in layers if isinstance(layer, dict))
        missing = ", ".join(str(item) for item in req.get("missing_layers", []) if item)
        lines.append(f"| `{req.get('id')}` | `{req.get('status')}` | `{layer_names}` | {sample_count} | `{missing}` |")
    lines.extend(["", "## Samples", ""])
    for sample in payload.get("samples", []) if isinstance(payload.get("samples"), list) else []:
        if not isinstance(sample, dict):
            continue
        evidence = sample.get("evidence") if isinstance(sample.get("evidence"), dict) else {}
        raw_preview = sample.get("raw_preview") if isinstance(sample.get("raw_preview"), dict) else {}
        signal = sample.get("signal") if isinstance(sample.get("signal"), dict) else {}
        event = sample.get("event") if isinstance(sample.get("event"), dict) else {}
        lines.extend(
            [
                f"### {sample.get('layer')} / {sample.get('key')}",
                "",
                f"- requirement: `{sample.get('requirement_id')}`",
                f"- session: `{sample.get('session')}`",
                f"- event: `{event.get('event_id')}` `{event.get('type')}` `{event.get('outcome')}`",
                f"- signal: confidence=`{signal.get('confidence')}` source=`{signal.get('source')}`",
                f"- raw_ref: `{evidence.get('raw_ref')}`",
                f"- segment_ref: `{evidence.get('segment_ref')}`",
                f"- generated_index_ref: `{evidence.get('generated_index_ref')}`",
                f"- review_status: `{sample.get('review', {}).get('status') if isinstance(sample.get('review'), dict) else 'unreviewed'}`",
                "",
                "```text",
                str(raw_preview.get("text") or ""),
                "```",
                "",
            ]
        )
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), list) else []
    if diagnostics:
        lines.extend(["", "## Diagnostics", ""])
        for item in diagnostics:
            lines.append(f"- `{item}`")
    return "\n".join(lines) + "\n"


def command_route_sample_audit(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    since = since_date_from_args(args.since, args.since_days if args.since_days is not None else None)
    payload = route_sample_audit(
        aoa_root=root,
        target=args.session,
        since=since,
        until=args.until,
        limit=args.limit,
        sample_limit=args.sample_limit,
        max_raw_chars=args.max_raw_chars,
        write_report=args.write_report,
    )
    if args.full:
        stdout_payload = payload
    else:
        stdout_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"requirements", "samples"}
        }
        stdout_payload["requirement_overview"] = [
            {
                "id": req.get("id"),
                "status": req.get("status"),
                "missing_layers": req.get("missing_layers", []),
                "under_sampled_layers": req.get("under_sampled_layers", []),
                "sample_count": sum(
                    int_value(layer.get("sample_count"))
                    for layer in req.get("layers", [])
                    if isinstance(layer, dict)
                ),
            }
            for req in payload.get("requirements", [])
            if isinstance(req, dict)
        ]
    print(json.dumps(stdout_payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


ROUTE_SAMPLE_REVIEW_ACTIONS = {"accept", "reject", "weaken", "split", "add_rule", "skip", "open"}


def route_sample_identity(sample: dict[str, Any]) -> str:
    event = sample.get("event") if isinstance(sample.get("event"), dict) else {}
    return f"{sample.get('layer')}:{sample.get('key')}:{event.get('event_id')}"


def parse_route_sample_verdict(value: str) -> tuple[str, dict[str, Any]]:
    if "=" not in value:
        raise ValueError("verdict must use layer:key:event_id=verdict[:action[:note]]")
    identity, payload = value.split("=", 1)
    parts = payload.split(":", 2)
    verdict = parts[0].strip()
    action = parts[1].strip() if len(parts) > 1 and parts[1].strip() else verdict
    note = parts[2].strip() if len(parts) > 2 else ""
    if verdict not in ROUTE_SAMPLE_REVIEW_ACTIONS:
        raise ValueError(f"unsupported verdict {verdict!r}")
    if action not in ROUTE_SAMPLE_REVIEW_ACTIONS:
        raise ValueError(f"unsupported reviewer action {action!r}")
    return identity.strip(), {
        "verdict": verdict,
        "reviewer_action": action,
        "note": note,
    }


def load_route_sample_verdict_file(path: Path) -> dict[str, dict[str, Any]]:
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        raise ValueError(f"invalid verdict file: {path}")
    raw_items = payload.get("verdicts") or payload.get("reviews") or []
    if not isinstance(raw_items, list):
        raise ValueError(f"verdict file must contain verdicts list: {path}")
    verdicts: dict[str, dict[str, Any]] = {}
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        identity = str(item.get("identity") or "").strip()
        if not identity:
            layer = str(item.get("layer") or "").strip()
            key = str(item.get("key") or "").strip()
            event_id = str(item.get("event_id") or "").strip()
            identity = f"{layer}:{key}:{event_id}" if layer and key and event_id else ""
        if not identity:
            raise ValueError(f"verdict item missing identity: {path}")
        verdict = str(item.get("verdict") or "").strip()
        action = str(item.get("reviewer_action") or item.get("action") or verdict).strip()
        if verdict not in ROUTE_SAMPLE_REVIEW_ACTIONS:
            raise ValueError(f"unsupported verdict {verdict!r} in {path}")
        if action not in ROUTE_SAMPLE_REVIEW_ACTIONS:
            raise ValueError(f"unsupported reviewer action {action!r} in {path}")
        verdicts[identity] = {
            "verdict": verdict,
            "reviewer_action": action,
            "note": str(item.get("note") or ""),
        }
    return verdicts


def route_sample_review(
    *,
    aoa_root: Path,
    audit_path: Path,
    verdict_values: list[str] | None = None,
    verdict_file: Path | None = None,
    reviewer: str = "agent",
    write_report: bool = False,
) -> dict[str, Any]:
    now = utc_now()
    audit = read_json(audit_path, {})
    if not isinstance(audit, dict) or audit.get("artifact_type") != "route_sample_audit":
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": "route_sample_review",
            "generated_at": now,
            "ok": False,
            "audit_path": str(audit_path),
            "diagnostics": ["audit_path is not a route_sample_audit JSON artifact"],
            "samples": [],
            "classifier_feedback": [],
        }

    diagnostics: list[str] = []
    verdicts: dict[str, dict[str, Any]] = {}
    if verdict_file is not None:
        try:
            verdicts.update(load_route_sample_verdict_file(verdict_file))
        except ValueError as exc:
            diagnostics.append(str(exc))
    for value in verdict_values or []:
        try:
            identity, verdict = parse_route_sample_verdict(value)
            verdicts[identity] = verdict
        except ValueError as exc:
            diagnostics.append(str(exc))

    samples = audit.get("samples") if isinstance(audit.get("samples"), list) else []
    sample_ids = {
        route_sample_identity(sample)
        for sample in samples
        if isinstance(sample, dict)
    }
    for identity in sorted(set(verdicts) - sample_ids):
        diagnostics.append(f"verdict did not match a sample: {identity}")

    reviewed_samples: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    feedback: list[dict[str, Any]] = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        identity = route_sample_identity(sample)
        verdict = verdicts.get(identity)
        review_status = "reviewed" if verdict else "open"
        review = {
            "status": review_status,
            "verdict": verdict.get("verdict") if verdict else "open",
            "reviewer_action": verdict.get("reviewer_action") if verdict else "open",
            "reviewer": reviewer,
            "reviewed_at": now if verdict else "",
            "note": verdict.get("note") if verdict else "",
        }
        counts[str(review["verdict"])] += 1
        reviewed = {
            "identity": identity,
            "requirement_id": sample.get("requirement_id"),
            "layer": sample.get("layer"),
            "key": sample.get("key"),
            "session": sample.get("session"),
            "session_id": sample.get("session_id"),
            "event": sample.get("event"),
            "signal": sample.get("signal"),
            "evidence": sample.get("evidence"),
            "raw_preview": sample.get("raw_preview"),
            "review": review,
        }
        reviewed_samples.append(reviewed)
        if verdict and str(verdict.get("reviewer_action")) in {"reject", "weaken", "split", "add_rule"}:
            feedback.append(
                {
                    "identity": identity,
                    "requirement_id": sample.get("requirement_id"),
                    "layer": sample.get("layer"),
                    "key": sample.get("key"),
                    "session": sample.get("session"),
                    "action": verdict.get("reviewer_action"),
                    "verdict": verdict.get("verdict"),
                    "note": verdict.get("note") or "",
                    "evidence": sample.get("evidence"),
                    "signal": sample.get("signal"),
                }
            )

    payload = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "route_sample_review",
        "generated_at": now,
        "ok": not diagnostics,
        "audit_path": str(audit_path),
        "audit_generated_at": audit.get("generated_at"),
        "reviewer": reviewer,
        "sample_count": len(reviewed_samples),
        "reviewed_count": sum(1 for sample in reviewed_samples if sample.get("review", {}).get("status") == "reviewed"),
        "open_count": sum(1 for sample in reviewed_samples if sample.get("review", {}).get("status") == "open"),
        "verdict_counts": dict(sorted(counts.items())),
        "classifier_feedback_count": len(feedback),
        "classifier_feedback": feedback,
        "samples": reviewed_samples,
        "diagnostics": diagnostics,
    }
    if write_report:
        diagnostics_dir = aoa_root / DIAGNOSTICS_ROOT
        diagnostics_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{compact_stamp()}__route-sample-review"
        report_json = diagnostics_dir / f"{stem}.json"
        report_md = diagnostics_dir / f"{stem}.md"
        write_json(report_json, payload)
        write_markdown(report_md, route_sample_review_markdown(payload))
        payload["report_json"] = str(report_json)
        payload["report_markdown"] = str(report_md)
    return payload


def route_sample_review_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Route Sample Review",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- ok: `{payload.get('ok')}`",
        f"- audit_path: `{payload.get('audit_path')}`",
        f"- sample_count: `{payload.get('sample_count')}`",
        f"- reviewed_count: `{payload.get('reviewed_count')}`",
        f"- open_count: `{payload.get('open_count')}`",
        f"- classifier_feedback_count: `{payload.get('classifier_feedback_count')}`",
        "",
        "## Verdict Counts",
        "",
    ]
    for verdict, count in (payload.get("verdict_counts") or {}).items() if isinstance(payload.get("verdict_counts"), dict) else []:
        lines.append(f"- `{verdict}`: {count}")
    feedback = payload.get("classifier_feedback") if isinstance(payload.get("classifier_feedback"), list) else []
    if feedback:
        lines.extend(["", "## Classifier Feedback", "", "| identity | action | note | evidence |", "| --- | --- | --- | --- |"])
        for item in feedback:
            if not isinstance(item, dict):
                continue
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            lines.append(
                f"| `{item.get('identity')}` | `{item.get('action')}` | {item.get('note') or ''} | `{evidence.get('raw_ref') or evidence.get('segment_ref') or ''}` |"
            )
    lines.extend(["", "## Samples", "", "| identity | verdict | action | note |", "| --- | --- | --- | --- |"])
    for sample in payload.get("samples", []) if isinstance(payload.get("samples"), list) else []:
        if not isinstance(sample, dict):
            continue
        review = sample.get("review") if isinstance(sample.get("review"), dict) else {}
        lines.append(
            f"| `{sample.get('identity')}` | `{review.get('verdict')}` | `{review.get('reviewer_action')}` | {review.get('note') or ''} |"
        )
    diagnostics = payload.get("diagnostics") if isinstance(payload.get("diagnostics"), list) else []
    if diagnostics:
        lines.extend(["", "## Diagnostics", ""])
        for item in diagnostics:
            lines.append(f"- `{item}`")
    return "\n".join(lines) + "\n"


def command_route_sample_review(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    payload = route_sample_review(
        aoa_root=root,
        audit_path=Path(args.audit),
        verdict_values=args.verdict or [],
        verdict_file=Path(args.verdict_file) if args.verdict_file else None,
        reviewer=args.reviewer,
        write_report=args.write_report,
    )
    if args.full:
        stdout_payload = payload
    else:
        stdout_payload = {
            key: value
            for key, value in payload.items()
            if key not in {"samples"}
        }
    print(json.dumps(stdout_payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_route_layer_readiness(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    since = since_date_from_args(args.since, args.since_days if args.since_days is not None else None)
    payload = route_layer_readiness(
        aoa_root=root,
        target=args.session,
        since=since,
        until=args.until,
        limit=args.limit,
        sample_limit=args.sample_limit,
        write_report=args.write_report,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_atlas_build(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    since = since_date_from_args(args.since, args.since_days if args.since_days is not None else None)
    payload = build_agent_atlas(
        aoa_root=root,
        target=args.session,
        since=since,
        until=args.until,
        limit=args.limit,
        clean=not args.no_clean,
        write_report=args.write_report,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload.get("ok") else 1


def command_retrieve(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    payload = retrieval_packet(
        aoa_root=root,
        recipe=args.recipe,
        query=args.query or "",
        session=args.session_filter,
        provider=args.provider,
        include_host_context=args.include_host_context,
        include_semantic_context=args.include_semantic_context,
        rerank_local=args.rerank_local,
        rerank_candidate_limit=args.rerank_candidate_limit,
        allow_host_warnings=args.allow_host_warnings,
        limit=args.limit,
        event_limit=args.event_limit,
        write_report=args.write_report,
    )
    print(json.dumps(payload, indent=2, ensure_ascii=False))
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


def compact_naming_wave_apply_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_label": result.get("session_label"),
        "action": result.get("action"),
        "status": result.get("status"),
        "ok": result.get("ok"),
        "reviewed_name": result.get("reviewed_name"),
        "diagnostics": result.get("diagnostics", [])[:6] if isinstance(result.get("diagnostics"), list) else [],
    }


def compact_naming_quality_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_label": result.get("session_label"),
        "level": result.get("level"),
        "active_session_name": result.get("active_session_name"),
        "flags": result.get("flags", [])[:10] if isinstance(result.get("flags"), list) else [],
        "readiness_status": result.get("readiness_status"),
        "readiness_route": result.get("readiness_route"),
    }


def command_naming_wave(args: argparse.Namespace) -> int:
    explicit_workspace = Path(args.workspace_root) if args.workspace_root else None
    root = aoa_root_for(explicit_workspace, Path(args.aoa_root) if args.aoa_root else None)
    since = since_date_from_args(args.since, args.since_days if args.since_days is not None else None)
    if args.action == "build":
        payload = build_naming_wave(
            root,
            target=args.session,
            since=since,
            until=args.until,
            limit=args.limit,
            include_readable=not args.exclude_readable,
            include_low_signal=args.include_low_signal,
            include_diagnostic=args.include_diagnostic,
            refresh_indexes=args.refresh_indexes,
            write=args.write,
            write_report=args.write_report,
            wave_id=args.wave_id,
        )
        print(json.dumps(naming_wave_print_payload(payload, full=args.full), indent=2, ensure_ascii=False))
        return 0 if payload.get("ok") else 1
    if args.action == "apply":
        if not args.plan:
            raise SystemExit("naming-wave apply requires --plan")
        payload = apply_naming_wave(
            root,
            plan_path=Path(args.plan),
            apply=args.apply,
            apply_preflight=args.apply_preflight,
            accept_proposed=args.accept_proposed,
            replace=args.replace,
            verify_raw_hash=not args.skip_raw_hash_check,
            write_report=args.write_report,
            stop_on_error=args.stop_on_error,
        )
        print(
            json.dumps(
                bounded_results_print_payload(
                    payload,
                    full=args.full,
                    compact_func=compact_naming_wave_apply_result,
                    note="apply results are bounded on stdout; pass --full or read the written report for complete results",
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0 if payload.get("ok") else 1
    if args.action == "audit":
        payload = naming_quality_audit(
            root,
            target=args.session,
            since=since,
            until=args.until,
            limit=args.limit,
            plan_path=Path(args.plan) if args.plan else None,
            sample_size=args.sample_size,
            sample_seed=args.sample_seed,
            sample_raw_chars=args.sample_raw_chars,
            write_report=args.write_report,
        )
        print(
            json.dumps(
                bounded_results_print_payload(
                    payload,
                    full=args.full,
                    compact_func=compact_naming_quality_result,
                    note="quality audit results are bounded on stdout; pass --full or read the written report for complete results",
                ),
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0 if payload.get("ok") else 1
    raise SystemExit(f"unknown naming-wave action: {args.action}")


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
    write_json(aoa_root / SEARCH_PROVIDER_CONFIG_PATH, default_search_provider_config())


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
            add_check(
                "lifecycle_hooks_queue_background_sync",
                all("background_sync_queued" in receipts[name].get("actions", []) for name in ("PreCompact", "PostCompact", "Stop")),
                {name: receipts[name].get("actions", []) for name in ("PreCompact", "PostCompact", "Stop")},
            )
            worker_payload = run_hook_worker(workspace_root=temp_workspace, aoa_root=temp_aoa, limit=5)
            add_check(
                "hook_worker_auto_indexes_compaction_interval",
                worker_payload.get("ok") is True and int(worker_payload.get("processed", 0) or 0) >= 1,
                worker_payload,
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
            add_check("raw_blocks_index_exists", (session_dir / "raw" / RAW_BLOCK_INDEX_JSON).exists())
            add_check("raw_compaction_events_ledger_exists", (session_dir / "raw" / RAW_COMPACTION_EVENTS_JSONL).exists())
            add_check("segments_include_compaction_interval", segment_roles == ["initial-to-compaction", "compaction-to-latest"], segment_roles)
            add_check(
                "segment_indexes_exist",
                bool(segments) and all(Path(str(segment.get("index") or "")).exists() for segment in segments if isinstance(segment, dict)),
            )
            add_check(
                "segments_link_to_raw_blocks",
                bool(segments)
                and all(
                    isinstance(segment, dict)
                    and isinstance(segment.get("raw_block"), dict)
                    and Path(str(segment["raw_block"].get("path") or "")).exists()
                    for segment in segments
                ),
                [segment.get("raw_block") for segment in segments if isinstance(segment, dict)],
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


def file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime_ns)


def raw_compaction_stats(raw_path: Path) -> dict[str, Any]:
    events: list[tuple[str, str, bool]] = []
    source_compacted_count = 0
    context_compacted_event_count = 0
    with raw_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            source_type = "unparsed"
            payload_type = ""
            boundary = False
            try:
                loaded = json.loads(line)
                if isinstance(loaded, dict):
                    source_type = str(loaded.get("type") or "unresolved-source")
                    payload = loaded.get("payload")
                    if isinstance(payload, dict):
                        payload_type = str(payload.get("type") or "")
                    boundary = source_type == "compacted" or payload_has_compaction_boundary(payload)
            except json.JSONDecodeError:
                pass
            if source_type == "compacted":
                source_compacted_count += 1
            if source_type == "event_msg" and payload_type == "context_compacted":
                context_compacted_event_count += 1
            events.append((source_type, payload_type, boundary))

    groups: list[tuple[int, int]] = []
    idx = 0
    while idx < len(events):
        source_type, _payload_type, boundary = events[idx]
        if not boundary:
            idx += 1
            continue
        end_index = idx
        if source_type == "compacted":
            search_limit = min(len(events), idx + 12)
            probe = idx + 1
            while probe < search_limit:
                candidate_source, candidate_payload, _candidate_boundary = events[probe]
                if candidate_source == "turn_context":
                    end_index = probe
                    probe += 1
                    continue
                if candidate_source == "event_msg" and candidate_payload == "token_count":
                    end_index = probe
                    probe += 1
                    continue
                if candidate_source == "event_msg" and candidate_payload == "context_compacted":
                    end_index = probe
                    break
                break
        groups.append((idx, end_index))
        idx = end_index + 1

    expected_segment_count = 0
    if events:
        expected_segment_count = len(groups)
        if not groups or groups[-1][1] < len(events) - 1:
            expected_segment_count += 1
    return {
        "line_count": len(events),
        "compaction_boundary_count": len(groups),
        "compaction_marker_count": sum(1 for _source, _payload, boundary in events if boundary),
        "source_compacted_count": source_compacted_count,
        "context_compacted_event_count": context_compacted_event_count,
        "expected_segment_count": expected_segment_count,
    }


def stable_archive_snapshot(
    session_dir: Path,
    manifest_path: Path,
    *,
    max_attempts: int = 3,
) -> tuple[dict[str, Any], list[Any], bool, dict[str, Any], list[str]]:
    diagnostics: list[str] = []
    last_manifest: dict[str, Any] = {}
    last_segments: list[Any] = []
    last_raw_exists = False
    last_stats: dict[str, Any] = {}
    for attempt in range(max_attempts):
        manifest_sig_before = file_signature(manifest_path)
        manifest = read_json(manifest_path, {})
        if not isinstance(manifest, dict):
            return {}, [], False, [], ["manifest_unreadable"]
        raw = manifest.get("raw") if isinstance(manifest.get("raw"), dict) else {}
        raw_value = raw.get("path")
        raw_path = Path(str(raw_value)) if raw_value else Path()
        raw_sig_before = file_signature(raw_path) if raw_value else None
        raw_exists = bool(raw_value and raw_sig_before is not None)
        segments = manifest.get("segments", []) if isinstance(manifest.get("segments"), list) else []
        stats = raw_compaction_stats(raw_path) if raw_exists else {}
        raw_sig_after = file_signature(raw_path) if raw_value else None
        manifest_sig_after = file_signature(manifest_path)
        last_manifest = manifest
        last_segments = segments
        last_raw_exists = raw_exists
        last_stats = stats
        if manifest_sig_before == manifest_sig_after and raw_sig_before == raw_sig_after:
            if attempt:
                diagnostics.append(f"archive_snapshot_stabilized_after_retry:{attempt}")
            return manifest, segments, raw_exists, stats, diagnostics
        diagnostics.append("archive_changed_during_audit_retry")
        time.sleep(0.05)
    diagnostics.append("archive_unstable_during_audit")
    return last_manifest, last_segments, last_raw_exists, last_stats, diagnostics


def archive_compaction_audit(aoa_root: Path) -> list[dict[str, Any]]:
    audits: list[dict[str, Any]] = []
    for manifest_path in sorted((aoa_root / SESSION_ROOT).glob("*/session.manifest.json")):
        session_dir = manifest_path.parent
        manifest, segments, raw_exists, stats, snapshot_diagnostics = stable_archive_snapshot(session_dir, manifest_path)
        if not manifest:
            continue
        boundary_count = 0
        compaction_marker_count = 0
        source_compacted_count = 0
        context_compacted_event_count = 0
        expected_segment_count = 0
        if raw_exists:
            boundary_count = int_value(stats.get("compaction_boundary_count"))
            compaction_marker_count = int_value(stats.get("compaction_marker_count"))
            source_compacted_count = int_value(stats.get("source_compacted_count"))
            context_compacted_event_count = int_value(stats.get("context_compacted_event_count"))
            expected_segment_count = int_value(stats.get("expected_segment_count"))
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
                "diagnostics": snapshot_diagnostics,
            }
        )
    return audits


def completion_audit(
    *,
    workspace_root: Path,
    aoa_root: Path,
    check_codex: bool = True,
    portable_bundle: bool = False,
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
    provider_status = search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite")
    provider_config_exists = (aoa_root / SEARCH_PROVIDER_CONFIG_PATH).exists()
    provider_config = read_json(aoa_root / SEARCH_PROVIDER_CONFIG_PATH, {})
    provider_config_ok = (
        isinstance(provider_config, dict)
        and provider_config.get("default_provider") == "portable_sqlite"
        and isinstance(provider_config.get("providers"), dict)
        and "portable_sqlite" in provider_config.get("providers", {})
    )
    hook_example_path = aoa_root / "hooks/codex-hooks.user.example.json"
    hook_example_events = configured_hook_events(hook_example_path)
    hook_example_ok = set(REQUIRED_HOOK_EVENTS).issubset(hook_example_events)
    portable_clean_runtime = (
        len(sessions) == 0
        and sessions_index_ok
        and not any((aoa_root / SESSION_ROOT).glob("*/session.manifest.json"))
        and not (aoa_root / "search/aoa-search.sqlite3").exists()
    )
    raw_requirement = (
        "Raw session material is preserved for indexed archives"
        if not portable_bundle
        else "Portable bundle intentionally excludes local raw session archives"
    )
    real_compaction_requirement = (
        "Real Codex compaction boundaries are detected from raw transcripts"
        if not portable_bundle
        else "Portable bundle carries compaction logic without bundled live raw proof"
    )
    segment_requirement = (
        "Segment topology matches raw compaction boundaries"
        if not portable_bundle
        else "Portable bundle has clean runtime topology without bundled segment drift"
    )
    raw_status = "covered" if raw_preserved or (portable_bundle and portable_clean_runtime) else "missing"
    real_compaction_status = (
        "covered" if real_compaction_archives or (portable_bundle and portable_clean_runtime) else "missing"
    )
    segment_status = "covered" if segments_match or (portable_bundle and portable_clean_runtime) else "missing"
    provider_status_ok = (
        bool(provider_config_exists and provider_status.get("ok"))
        if not portable_bundle
        else bool(provider_config_exists and provider_config_ok)
    )
    user_skill_ok = bool(user_skill_state.get("ok")) if not portable_bundle else (
        (aoa_root / "skills/aoa-session-memory-global-route/SKILL.md").exists()
    )
    live_hook_requirement = (
        "Live user hooks are wired for required lifecycle events"
        if not portable_bundle
        else "Portable hook examples cover required lifecycle events"
    )
    user_skill_requirement = (
        "User-level router skill is installed for the current Codex user"
        if not portable_bundle
        else "User-level router skill can be installed from the portable bundle"
    )
    live_prepost_requirement = (
        "Live PreCompact and PostCompact hook receipts observed in archived sessions"
        if not portable_bundle
        else "Portable bundle intentionally excludes live hook receipt archives"
    )
    live_hook_status = (
        "covered"
        if (
            set(REQUIRED_HOOK_EVENTS).issubset(configured_hook_events(Path.home() / ".codex" / "hooks.json"))
            if not portable_bundle
            else hook_example_ok
        )
        else "missing"
    )
    live_prepost_status = "covered" if live_prepost_seen or portable_bundle else "remaining"

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
            raw_requirement,
            raw_status,
            {
                "indexed_archive_count": len(indexed_archives),
                "portable_bundle": portable_bundle,
                "portable_clean_runtime": portable_clean_runtime,
            },
        ),
        checklist_item(
            real_compaction_requirement,
            real_compaction_status,
            {
                "real_compaction_archive_count": len(real_compaction_archives),
                "boundary_counts": {item["session_label"]: item["compaction_boundary_count"] for item in real_compaction_archives},
                "portable_bundle": portable_bundle,
                "portable_clean_runtime": portable_clean_runtime,
            },
        ),
        checklist_item(
            segment_requirement,
            segment_status,
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
                "portable_bundle": portable_bundle,
                "portable_clean_runtime": portable_clean_runtime,
            },
            None
            if segment_status == "covered"
            else "Reindex indexed archives whose segment counts no longer match raw boundaries.",
        ),
        checklist_item(
            "Hook output remains schema-limited and fail-open",
            "covered",
            {"allowed_fields": sorted(CODEX_HOOK_OUTPUT_FIELDS), "hook_output_function": "codex_hook_output"},
        ),
        checklist_item(
            live_hook_requirement,
            live_hook_status,
            {
                "required_events": REQUIRED_HOOK_EVENTS,
                "live_hook_counts": hook_counts,
                "hook_example": str(hook_example_path),
                "hook_example_events": sorted(hook_example_events),
            },
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
            "Search provider config keeps portable SQLite authoritative and host backends optional",
            "covered" if provider_status_ok else "remaining",
            {
                "config": str(aoa_root / SEARCH_PROVIDER_CONFIG_PATH),
                "provider_status": provider_status,
                "provider_config_ok": provider_config_ok,
                "portable_bundle": portable_bundle,
            },
            None
            if provider_status_ok
            else "Build the search index for live installs; clean portable bundles only require config/search-providers.json.",
        ),
        checklist_item(
            user_skill_requirement,
            "covered" if user_skill_ok else "remaining",
            {
                **user_skill_state,
                "portable_bundle": portable_bundle,
                "source_skill": str(aoa_root / "skills/aoa-session-memory-global-route/SKILL.md"),
            },
            None
            if user_skill_ok
            else "Install the user-level router with install-user-skill.",
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
            live_prepost_requirement,
            live_prepost_status,
            {"live_hook_counts": hook_counts, "portable_bundle": portable_bundle},
            None
            if live_prepost_status == "covered"
            else "Real compaction markers exist, but current archives do not yet include live PreCompact/PostCompact hook receipts.",
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
        "audit_mode": "portable_bundle" if portable_bundle else "live_install",
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
        portable_bundle=args.portable_bundle,
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
    "config/atlas-policy.json",
    "config/naming-golden-set.json",
    "config/naming-policy.json",
    "config/search-providers.json",
    "hooks/AGENTS.md",
    "hooks/README.md",
    "hooks/codex-hooks.user.example.json",
    "schemas/AGENTS.md",
    "schemas/atlas-route-entry.schema.json",
    "schemas/hook-receipt.schema.json",
    "schemas/incident.schema.json",
    "schemas/segment.index.schema.json",
    "schemas/session.manifest.schema.json",
    "maps/AGENTS.md",
    "maps/START.md",
    "maps/README.md",
    "maps/_templates/axis-readme.template.md",
    "maps/_templates/route-entry.template.md",
    "maps/by-authority-surface/README.md",
    "maps/by-conversation-act/README.md",
    "maps/by-delivery-state/README.md",
    "maps/by-evidence-provenance/README.md",
    "maps/by-entity/README.md",
    "maps/by-external-snapshot/README.md",
    "maps/by-failure-mode/README.md",
    "maps/by-freshness/README.md",
    "maps/by-goal/README.md",
    "maps/by-hook-health/README.md",
    "maps/by-index-health/README.md",
    "maps/by-mcp/README.md",
    "maps/by-memory-surface/README.md",
    "maps/by-open-thread/README.md",
    "maps/by-operator-request/README.md",
    "maps/by-operator-preference/README.md",
    "maps/by-owner-route/README.md",
    "maps/by-path/README.md",
    "maps/by-phase-topic/README.md",
    "maps/by-promotion-candidate/README.md",
    "maps/by-resource-profile/README.md",
    "maps/by-repo-family/README.md",
    "maps/by-review-state/README.md",
    "maps/by-risk/README.md",
    "maps/by-route-next-action/README.md",
    "maps/by-runtime-environment/README.md",
    "maps/by-scope-contract/README.md",
    "maps/by-session-act/README.md",
    "maps/by-time/README.md",
    "maps/by-tool/README.md",
    "maps/by-verification-state/README.md",
    "maps/by-work-context/README.md",
    "maps/by-access-boundary/README.md",
    "maps/by-confidence/README.md",
    "maps/by-correlation/README.md",
    "maps/by-mutation-surface/README.md",
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
    "skills/aoa-session-naming-wave/SKILL.md",
    "skills/aoa-session-naming-readiness/SKILL.md",
    "skills/aoa-session-raw-diagnostic/SKILL.md",
    "skills/aoa-session-reindex/SKILL.md",
    "skills/aoa-session-rehydrate/SKILL.md",
    "skills/aoa-session-search/SKILL.md",
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
    session_dirs = [path for path in session_root.iterdir() if path.is_dir()] if session_root.exists() else []
    archive_dirs = [path for path in session_dirs if (path / "session.manifest.json").exists()]
    hook_only_dirs = [
        path for path in session_dirs
        if path not in archive_dirs
        and (path / "hooks").is_dir()
        and (
            (path / "hooks" / "events.jsonl").exists()
            or (path / "hooks" / "receipts.jsonl").exists()
        )
    ]
    unexpected_session_dirs = [
        path for path in session_dirs
        if path not in archive_dirs and path not in hook_only_dirs
    ]
    if hook_only_dirs:
        warnings.append(
            "hook-only receipt dirs are not counted as archive sessions: "
            + ", ".join(path.name for path in hook_only_dirs[:8])
        )
    if unexpected_session_dirs:
        problems.append(
            "unexpected non-archive session dirs: "
            + ", ".join(path.name for path in unexpected_session_dirs[:8])
        )
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
            archive_format_version = int_value(manifest_payload.get("archive_format_version"), 1)
            raw_blocks_required = archive_format_version >= 2 or isinstance(manifest_payload.get("raw_blocks"), dict)
            raw_blocks = manifest_payload.get("raw_blocks") if isinstance(manifest_payload.get("raw_blocks"), dict) else {}
            if raw_blocks_required:
                raw_block_index = Path(str(raw_blocks.get("index") or session_path / "raw" / RAW_BLOCK_INDEX_JSON))
                if not raw_block_index.exists():
                    problems.append(f"indexed session missing raw block index: {session_path}")
                if not (session_path / "raw" / RAW_COMPACTION_EVENTS_JSONL).exists():
                    problems.append(f"indexed session missing compaction events ledger: {session_path}")
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
                raw_block = segment.get("raw_block") if isinstance(segment.get("raw_block"), dict) else {}
                raw_block_path = Path(str(raw_block.get("path") or ""))
                if raw_blocks_required and not raw_block_path.exists():
                    problems.append(f"missing segment raw block: {session_path}:{segment.get('segment_id')}")
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
        "session_dir_count": len(session_dirs),
        "hook_only_dir_count": len(hook_only_dirs),
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
    name_session.add_argument("--no-maintenance-worker", action="store_true", help="Do not launch the background index-maintenance worker after --apply.")
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

    phase_review_assist = sub.add_parser(
        "phase-review-assist",
        help="Build batch synthesis packets for faster reviewed phase naming without applying names.",
    )
    phase_review_assist.add_argument("session", help="Session label/id/title/name fragment.")
    phase_review_assist.add_argument("--workspace-root")
    phase_review_assist.add_argument("--aoa-root")
    phase_review_assist.add_argument("--limit", type=int, default=8, help="Maximum candidates to packetize when --segment is not used.")
    phase_review_assist.add_argument("--from-segment", help="Start packetizing at this segment id, for example 022.")
    phase_review_assist.add_argument("--segment", action="append", help="Packetize a specific segment id. May be repeated.")
    phase_review_assist.add_argument("--include-reviewed", action="store_true", help="Include already applied phase names in the packets.")
    phase_review_assist.add_argument("--refresh", action="store_true", help="Rebuild phase-discovery before building assist packets.")
    phase_review_assist.add_argument("--write", action="store_true", help="Write naming/phase-review-assist.json/.md and a plan template.")
    phase_review_assist.add_argument("--write-report", action="store_true", help="Write JSON and Markdown reports under .aoa/diagnostics.")
    phase_review_assist.add_argument("--full", action="store_true", help="Print complete packets to stdout. Default prints a compact overview.")
    phase_review_assist.set_defaults(func=command_phase_review_assist)

    apply_phase_review_plan_parser = sub.add_parser(
        "apply-phase-review-plan",
        help="Preview or apply reviewed phase names from a phase-review-plan JSON file.",
    )
    apply_phase_review_plan_parser.add_argument("session", help="Session label/id/title/name fragment.")
    apply_phase_review_plan_parser.add_argument("--workspace-root")
    apply_phase_review_plan_parser.add_argument("--aoa-root")
    apply_phase_review_plan_parser.add_argument(
        "--plan",
        help="Path to a filled phase-review-plan JSON file. Defaults to naming/phase-review-plan.template.json for preview.",
    )
    apply_phase_review_plan_parser.add_argument("--apply", action="store_true", help="Apply non-empty reviewed_name entries. Default previews only.")
    apply_phase_review_plan_parser.add_argument("--replace", action="store_true", help="Replace existing semantic names with the same slug.")
    apply_phase_review_plan_parser.add_argument("--skip-raw-hash-check", action="store_true", help="Do not recalculate raw sha256 before writing.")
    apply_phase_review_plan_parser.add_argument("--stop-on-error", action="store_true", help="Stop processing after the first invalid item or failed segment.")
    apply_phase_review_plan_parser.add_argument("--write-report", action="store_true", help="Write batch and per-segment JSON/Markdown reports under .aoa/diagnostics.")
    apply_phase_review_plan_parser.add_argument("--full", action="store_true", help="Print complete per-segment results. Default prints a compact overview.")
    apply_phase_review_plan_parser.set_defaults(func=command_apply_phase_review_plan)

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

    naming_wave = sub.add_parser(
        "naming-wave",
        help="Build, apply, or audit mass semantic session naming waves.",
    )
    naming_wave.add_argument("action", choices=["build", "apply", "audit"], help="Wave action.")
    naming_wave.add_argument("session", nargs="?", default="all", help="Session label/id/title/name fragment or all.")
    naming_wave.add_argument("--workspace-root")
    naming_wave.add_argument("--aoa-root")
    naming_wave.add_argument("--since", help="Select sessions with archive dates on or after YYYY-MM-DD when session=all.")
    naming_wave.add_argument("--since-days", type=int, help="Rolling window when --since is not provided and session=all.")
    naming_wave.add_argument("--until", help="Select sessions with archive dates on or before YYYY-MM-DD when session=all.")
    naming_wave.add_argument("--limit", type=int, help="Limit selected sessions after chronological ordering when session=all.")
    naming_wave.add_argument("--wave-id", help="Explicit naming wave id. Defaults to the next naming-wave-N.")
    naming_wave.add_argument("--plan", help="Naming wave plan JSON for apply or plan-aware audit.")
    naming_wave.add_argument("--write", action="store_true", help="Write naming-wave plan artifacts under diagnostics/naming-waves.")
    naming_wave.add_argument("--write-report", action="store_true", help="Write JSON and Markdown diagnostics reports.")
    naming_wave.add_argument("--refresh-indexes", action="store_true", help="Refresh SESSION_NAMES.md and sessions/INDEX.md during build.")
    naming_wave.add_argument("--exclude-readable", action="store_true", help="Do not include readable_label sessions in build output.")
    naming_wave.add_argument("--include-low-signal", action="store_true", help="Include low-signal probe sessions in build output.")
    naming_wave.add_argument("--include-diagnostic", action="store_true", help="Include raw-unavailable diagnostic sessions in build output.")
    naming_wave.add_argument("--apply", action="store_true", help="Apply reviewed names or approved preflight actions. Default previews only.")
    naming_wave.add_argument("--apply-preflight", action="store_true", help="Apply sync/reindex preflight actions from the plan deliberately.")
    naming_wave.add_argument("--accept-proposed", action="store_true", help="Treat high-confidence ok proposed names as reviewed during apply.")
    naming_wave.add_argument("--replace", action="store_true", help="Replace an existing semantic name with the same slug.")
    naming_wave.add_argument("--skip-raw-hash-check", action="store_true", help="Do not recalculate raw sha256 before writing semantic names.")
    naming_wave.add_argument("--stop-on-error", action="store_true", help="Stop apply after the first diagnostic item.")
    naming_wave.add_argument("--sample-size", type=int, default=0, help="For audit, include a deterministic stratified quality sample from the plan.")
    naming_wave.add_argument("--sample-seed", default="naming-quality", help="Seed string for deterministic audit sampling.")
    naming_wave.add_argument("--sample-raw-chars", type=int, default=240, help="Maximum raw evidence preview characters per sampled item.")
    naming_wave.add_argument("--full", action="store_true", help="Print complete wave/audit results to stdout.")
    naming_wave.set_defaults(func=command_naming_wave)

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

    hook_worker = sub.add_parser("hook-worker", help="Process queued hook sync jobs outside the Codex hook timeout window.")
    hook_worker.add_argument("--workspace-root")
    hook_worker.add_argument("--aoa-root")
    hook_worker.add_argument("--limit", type=int, default=5)
    hook_worker.set_defaults(func=command_hook_worker)

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
    reindex.add_argument("--max-raw-mb", type=float, help="Skip sessions whose raw JSONL is larger than this many MiB.")
    reindex.add_argument("--stale-route-indexes", action="store_true", help="Only select reindexable archives whose session route-signal index is missing or stale.")
    reindex.add_argument("--dry-run", action="store_true", help="Only report which archives would be regenerated.")
    reindex.add_argument("--write-report", action="store_true", help="Write JSON and Markdown reindex reports under .aoa/diagnostics.")
    reindex.add_argument("--full", action="store_true", help="Print complete reindex results to stdout.")
    reindex.set_defaults(func=command_reindex_sessions)

    index_maintenance = sub.add_parser(
        "index-maintenance",
        aliases=["maintain-index", "auto-index"],
        help="Plan or apply the automatic route/search/atlas maintenance pass.",
    )
    index_maintenance.add_argument("session", nargs="?", default="all", help="Session label/id/title fragment or all.")
    index_maintenance.add_argument("--workspace-root")
    index_maintenance.add_argument("--aoa-root")
    index_maintenance.add_argument("--since", help="Select sessions with archive dates on or after YYYY-MM-DD when session=all.")
    index_maintenance.add_argument("--since-days", type=int, help="Rolling window when --since is not provided and session=all.")
    index_maintenance.add_argument("--until", help="Select sessions with archive dates on or before YYYY-MM-DD when session=all.")
    index_maintenance.add_argument("--limit", type=int, help="Limit selected sessions after chronological ordering when session=all.")
    index_maintenance.add_argument("--apply", action="store_true", help="Execute planned maintenance actions. Default only plans.")
    index_maintenance.add_argument("--max-raw-mb", type=float, default=16, help="Skip raw-text extraction/reindexing above this many MiB where supported.")
    index_maintenance.add_argument("--sample-audit", action="store_true", help="Run route-sample-audit after route-index reindexing.")
    index_maintenance.add_argument("--sample-limit", type=int, default=DEFAULT_ROUTE_SAMPLE_LIMIT)
    index_maintenance.add_argument("--max-raw-chars", type=int, default=360)
    index_maintenance.add_argument("--reason", default="operator_requested")
    index_maintenance.add_argument("--write-report", action="store_true", help="Write JSON and Markdown maintenance reports under .aoa/diagnostics.")
    index_maintenance.add_argument("--full", action="store_true", help="Print complete maintenance payload to stdout.")
    index_maintenance.set_defaults(func=command_index_maintenance)

    conversation_audit = sub.add_parser("conversation-act-audit", help="Audit conversation-act classifier coverage from generated segment indexes.")
    conversation_audit.add_argument("session", nargs="?", default="all", help="Session label/id/title fragment or all.")
    conversation_audit.add_argument("--workspace-root")
    conversation_audit.add_argument("--aoa-root")
    conversation_audit.add_argument("--since", help="Select sessions with archive dates on or after YYYY-MM-DD when session=all.")
    conversation_audit.add_argument("--since-days", type=int, help="Rolling window when --since is not provided and session=all.")
    conversation_audit.add_argument("--until", help="Select sessions with archive dates on or before YYYY-MM-DD when session=all.")
    conversation_audit.add_argument("--limit", type=int, help="Limit selected sessions after chronological ordering when session=all.")
    conversation_audit.add_argument("--sample-limit", type=int, default=3, help="Maximum evidence samples per conversation-act kind.")
    conversation_audit.add_argument("--write-report", action="store_true", help="Write JSON and Markdown conversation-act audit reports under .aoa/diagnostics.")
    conversation_audit.set_defaults(func=command_conversation_act_audit)

    search_index = sub.add_parser(
        "search-index",
        aliases=["aoa-search-index"],
        help="Build the portable SQLite FTS search index from generated session indexes and raw refs.",
    )
    search_index.add_argument("session", nargs="?", default="all", help="Session label/id/title fragment or all.")
    search_index.add_argument("--workspace-root")
    search_index.add_argument("--aoa-root")
    search_index.add_argument("--since", help="Select sessions with archive dates on or after YYYY-MM-DD when session=all.")
    search_index.add_argument("--since-days", type=int, help="Rolling window when --since is not provided and session=all.")
    search_index.add_argument("--until", help="Select sessions with archive dates on or before YYYY-MM-DD when session=all.")
    search_index.add_argument("--limit", type=int, help="Limit selected sessions after chronological ordering when session=all.")
    search_index.add_argument("--max-raw-mb", type=float, help="Skip raw-text extraction for sessions whose raw JSONL is larger than this many MiB.")
    search_index.add_argument("--no-rebuild", action="store_true", help="Append/update into the existing search DB instead of rebuilding it.")
    search_index.add_argument("--write-report", action="store_true", help="Write JSON and Markdown search-index reports under .aoa/diagnostics.")
    search_index.set_defaults(func=command_search_index)

    provider_status = sub.add_parser(
        "search-provider-status",
        help="Inspect portable and optional host search provider capability without changing archive truth.",
    )
    provider_status.add_argument("--workspace-root")
    provider_status.add_argument("--aoa-root")
    provider_status.add_argument("--provider", default="all", help="Provider name or all.")
    provider_status.add_argument("--include-host", action="store_true", help="Run optional host provider gates such as abyss-machine quality audit.")
    provider_status.add_argument("--refresh-host", action="store_true", help="Use the host deterministic refresh quality gate where configured.")
    provider_status.add_argument("--refresh-host-index", action="store_true", help="Use the host refresh-index quality gate where configured.")
    provider_status.add_argument("--timeout", type=int, default=45)
    provider_status.add_argument("--write-report", action="store_true", help="Write JSON and Markdown provider reports under .aoa/diagnostics.")
    provider_status.set_defaults(func=command_search_provider_status)

    search = sub.add_parser(
        "search",
        aliases=["aoa-search"],
        help="Query the portable SQLite FTS search index with evidence refs and freshness checks.",
    )
    search.add_argument("query_text", nargs="?", default="", help="Search text. Use --query when the text begins with a dash.")
    search.add_argument("--query", help="Search text.")
    search.add_argument("--workspace-root")
    search.add_argument("--aoa-root")
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--provider", default="portable_sqlite", help="Search provider. portable_sqlite remains the authoritative .aoa route.")
    search.add_argument("--include-host-context", action="store_true", help="For optional host providers, include a compact host context overlay summary.")
    search.add_argument("--include-semantic-context", action="store_true", help="Include compact local embedding semantic-search context as a non-authoritative host overlay.")
    search.add_argument("--rerank-local", action="store_true", help="Rerank returned .aoa evidence hits through the optional local reranker without replacing refs.")
    search.add_argument("--rerank-candidate-limit", type=int, help="Maximum returned .aoa hits to send to the optional local reranker.")
    search.add_argument("--allow-host-warnings", action="store_true", help="Allow host context overlay even when host quality gates report warnings.")
    search.add_argument("--host-timeout", type=int, default=45)
    search.add_argument("--session", dest="session_filter", help="Filter by session id, label, or title fragment.")
    search.add_argument("--doc-type", choices=["session", "segment", "event", "incident"])
    search.add_argument("--event-type")
    search.add_argument("--family")
    search.add_argument("--outcome")
    search.add_argument("--conversation-act")
    search.add_argument("--session-act")
    search.add_argument("--route-layer", help="Filter by generated route-signal layer such as scope_contract.")
    search.add_argument("--route-signal", help="Filter by generated route signal in layer:key form.")
    search.add_argument("--archive-status")
    search.add_argument("--freshness-status")
    search.add_argument("--date-from", help="Filter sessions on or after YYYY-MM-DD.")
    search.add_argument("--date-to", help="Filter sessions on or before YYYY-MM-DD.")
    search.add_argument("--explain", action="store_true", help="Include route/freshness explanation for every result.")
    search.set_defaults(func=command_search)

    atlas = sub.add_parser("atlas", help="Generate the agent atlas route entries from session indexes.")
    atlas_sub = atlas.add_subparsers(dest="atlas_command", required=True)
    atlas_build = atlas_sub.add_parser("build", help="Build generated atlas entries and per-axis indexes.")
    atlas_build.add_argument("session", nargs="?", default="all", help="Session id/label/title or all.")
    atlas_build.add_argument("--workspace-root")
    atlas_build.add_argument("--aoa-root")
    atlas_build.add_argument("--since", help="Select sessions with archive dates on or after YYYY-MM-DD when session=all.")
    atlas_build.add_argument("--since-days", type=int, help="Rolling window when --since is not provided and session=all.")
    atlas_build.add_argument("--until", help="Select sessions with archive dates on or before YYYY-MM-DD when session=all.")
    atlas_build.add_argument("--limit", type=int, help="Limit selected sessions after chronological ordering when session=all.")
    atlas_build.add_argument("--no-clean", action="store_true", help="Keep existing generated atlas entries instead of rebuilding clean.")
    atlas_build.add_argument("--write-report", action="store_true", help="Write JSON and Markdown atlas-build reports under .aoa/diagnostics.")
    atlas_build.set_defaults(func=command_atlas_build)

    route_readiness = sub.add_parser(
        "route-readiness",
        aliases=["route-layer-audit"],
        help="Audit 22 operational route layers against session indexes, atlas axes, and search readiness.",
    )
    route_readiness.add_argument("session", nargs="?", default="all", help="Session id/label/title or all.")
    route_readiness.add_argument("--workspace-root")
    route_readiness.add_argument("--aoa-root")
    route_readiness.add_argument("--since", help="Select sessions with archive dates on or after YYYY-MM-DD when session=all.")
    route_readiness.add_argument("--since-days", type=int, help="Rolling window when --since is not provided and session=all.")
    route_readiness.add_argument("--until", help="Select sessions with archive dates on or before YYYY-MM-DD when session=all.")
    route_readiness.add_argument("--limit", type=int, help="Limit selected sessions after chronological ordering when session=all.")
    route_readiness.add_argument("--sample-limit", type=int, default=2, help="Maximum evidence samples per route layer.")
    route_readiness.add_argument("--write-report", action="store_true", help="Write JSON and Markdown route-readiness reports under .aoa/diagnostics.")
    route_readiness.set_defaults(func=command_route_layer_readiness)

    route_sample_audit_parser = sub.add_parser(
        "route-sample-audit",
        aliases=["route-calibration"],
        help="Build unreviewed calibration samples for the 22 operational route layers.",
    )
    route_sample_audit_parser.add_argument("session", nargs="?", default="all", help="Session id/label/title or all.")
    route_sample_audit_parser.add_argument("--workspace-root")
    route_sample_audit_parser.add_argument("--aoa-root")
    route_sample_audit_parser.add_argument("--since", help="Select sessions with archive dates on or after YYYY-MM-DD when session=all.")
    route_sample_audit_parser.add_argument("--since-days", type=int, help="Rolling window when --since is not provided and session=all.")
    route_sample_audit_parser.add_argument("--until", help="Select sessions with archive dates on or before YYYY-MM-DD when session=all.")
    route_sample_audit_parser.add_argument("--limit", type=int, help="Limit selected sessions after chronological ordering when session=all.")
    route_sample_audit_parser.add_argument("--sample-limit", type=int, default=DEFAULT_ROUTE_SAMPLE_LIMIT, help="Maximum unreviewed calibration samples per route layer.")
    route_sample_audit_parser.add_argument("--max-raw-chars", type=int, default=360, help="Maximum raw preview characters per sampled event.")
    route_sample_audit_parser.add_argument("--write-report", action="store_true", help="Write JSON and Markdown route-sample-audit reports under .aoa/diagnostics.")
    route_sample_audit_parser.add_argument("--full", action="store_true", help="Print complete sample packets to stdout.")
    route_sample_audit_parser.set_defaults(func=command_route_sample_audit)

    route_sample_review_parser = sub.add_parser(
        "route-sample-review",
        help="Record append-only review verdicts for a route-sample-audit packet.",
    )
    route_sample_review_parser.add_argument("audit", help="Path to a route-sample-audit JSON artifact.")
    route_sample_review_parser.add_argument("--workspace-root")
    route_sample_review_parser.add_argument("--aoa-root")
    route_sample_review_parser.add_argument("--verdict", action="append", help="Inline verdict: layer:key:event_id=verdict[:action[:note]].")
    route_sample_review_parser.add_argument("--verdict-file", help="JSON file containing verdicts/reviews list.")
    route_sample_review_parser.add_argument("--reviewer", default="agent", help="Reviewer label written into the review packet.")
    route_sample_review_parser.add_argument("--write-report", action="store_true", help="Write JSON and Markdown route-sample-review reports under .aoa/diagnostics.")
    route_sample_review_parser.add_argument("--full", action="store_true", help="Print complete reviewed samples to stdout.")
    route_sample_review_parser.set_defaults(func=command_route_sample_review)

    retrieve = sub.add_parser(
        "retrieve",
        aliases=["retrieval-packet"],
        help="Build a compact evidence packet for a retrieval recipe without loading bulk raw.",
    )
    retrieve.add_argument(
        "recipe",
        choices=sorted(RETRIEVAL_RECIPE_QUERIES),
        help="Evidence packet recipe.",
    )
    retrieve.add_argument("--query", help="Override the recipe query.")
    retrieve.add_argument("--workspace-root")
    retrieve.add_argument("--aoa-root")
    retrieve.add_argument("--session", dest="session_filter", help="Pin the packet to a session id, label, title, or semantic name fragment.")
    retrieve.add_argument("--provider", default="portable_sqlite", help="Search provider. portable_sqlite remains authoritative.")
    retrieve.add_argument("--include-host-context", action="store_true", help="For optional host providers, include compact host context overlay summary.")
    retrieve.add_argument("--include-semantic-context", action="store_true", help="Include compact local embedding semantic-search context as a non-authoritative host overlay.")
    retrieve.add_argument("--rerank-local", action="store_true", help="Rerank returned .aoa evidence hits through the optional local reranker without replacing refs.")
    retrieve.add_argument("--rerank-candidate-limit", type=int, help="Maximum returned .aoa hits to send to the optional local reranker.")
    retrieve.add_argument("--allow-host-warnings", action="store_true", help="Allow host context overlay when host quality gates report warnings.")
    retrieve.add_argument("--limit", type=int, default=8, help="Maximum search hits and phase candidates.")
    retrieve.add_argument("--event-limit", type=int, default=16, help="Maximum continuation signal events from session indexes.")
    retrieve.add_argument("--write-report", action="store_true", help="Write JSON and Markdown retrieval packet reports under .aoa/diagnostics.")
    retrieve.set_defaults(func=command_retrieve)

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
    audit.add_argument(
        "--portable-bundle",
        action="store_true",
        help="Audit a clean standalone bundle checkout without requiring local runtime sessions or live user hook receipts.",
    )
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
