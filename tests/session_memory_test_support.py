"""Shared test loaders and focused fixture builders for session-memory tests."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "aoa_session_memory.py"
HOOK_SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "aoa_session_hook.py"
)
spec = importlib.util.spec_from_file_location("aoa_session_memory", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["aoa_session_memory"] = module
spec.loader.exec_module(module)
hook_spec = importlib.util.spec_from_file_location(
    "aoa_session_hook",
    HOOK_SCRIPT,
)
assert hook_spec and hook_spec.loader
hook_module = importlib.util.module_from_spec(hook_spec)
sys.modules["aoa_session_hook"] = hook_module
hook_spec.loader.exec_module(hook_module)


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def touch_old(path: Path, old_ts: float) -> None:
    os.utime(path, (old_ts, old_ts))


def build_doctor_root_with_missing_generated_segment(
    tmp_path: Path,
    *,
    recent_live: bool,
) -> tuple[Path, Path]:
    workspace = tmp_path / "AbyssOS"
    root = workspace / ".aoa"
    root.mkdir(parents=True)
    for rel_path in module.REQUIRED_ROOT_FILES:
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}\n" if path.suffix == ".json" else "\n", encoding="utf-8")
    write_json(
        root / "config" / "event-taxonomy.json",
        {"event_types": module.EVENT_TYPE_ORDER},
    )
    write_json(
        root / "config" / "event-distillation-routes.json",
        {
            "routes": {
                event_type: {"lane": "test"}
                for event_type in module.EVENT_TYPE_ORDER
            }
        },
    )
    write_json(
        root / "config" / "naming-policy.json",
        {
            "banned_durable_name_terms": [],
            "segment_roles": [
                "initial-to-latest",
                "initial-to-compaction",
                "compaction-to-compaction",
                "compaction-to-latest",
            ],
        },
    )
    write_json(
        root / "hooks" / "codex-hooks.user.example.json",
        {
            "hooks": {
                event_name: [{"command": "true"}]
                for event_name in module.REQUIRED_HOOK_EVENTS
            }
        },
    )
    sessions_root = root / module.SESSION_ROOT
    label = "2026-06-11__006__doctor-live-tail"
    session_dir = sessions_root / label
    (session_dir / "raw" / "blocks").mkdir(parents=True)
    (session_dir / "segments").mkdir(parents=True)
    (root / module.SESSION_NAME_INDEX_MARKDOWN).write_text(
        "# Session Names\n",
        encoding="utf-8",
    )
    (sessions_root / module.SESSIONS_INDEX_MARKDOWN).write_text(
        "# Sessions\n",
        encoding="utf-8",
    )
    (session_dir / "AGENTS.md").write_text("# Session\n", encoding="utf-8")
    (session_dir / module.SESSION_INDEX_MARKDOWN).write_text(
        "# Session\n",
        encoding="utf-8",
    )
    raw_path = session_dir / "raw" / "session.raw.jsonl"
    raw_path.write_text("{}\n", encoding="utf-8")
    live_transcript = (
        tmp_path
        / ".codex"
        / "sessions"
        / "2026"
        / "06"
        / "11"
        / "rollout-2026-06-11T16-22-32-live-tail.jsonl"
    )
    if recent_live:
        live_transcript.parent.mkdir(parents=True, exist_ok=True)
        live_transcript.write_text("{}\n", encoding="utf-8")
    raw_source_path = str(
        live_transcript if recent_live else tmp_path / "not-live.jsonl"
    )
    raw_block_record = {
        "block_id": "000",
        "segment_id": "000",
        "role": "initial-to-latest",
        "status": "open",
        "storage_mode": module.RAW_BLOCK_STORAGE_MODE_PLAIN,
        "path": str(
            session_dir / "raw" / "blocks" / "000__initial-to-latest.raw.jsonl"
        ),
        "rel": "raw/blocks/000__initial-to-latest.raw.jsonl",
        "plain_path": str(
            session_dir / "raw" / "blocks" / "000__initial-to-latest.raw.jsonl"
        ),
        "plain_rel": "raw/blocks/000__initial-to-latest.raw.jsonl",
    }
    segment_record = {
        "segment_id": "000",
        "role": "initial-to-latest",
        "markdown": str(session_dir / "segments" / "000__initial-to-latest.md"),
        "index": str(
            session_dir / "segments" / "000__initial-to-latest.index.json"
        ),
        "raw_block": raw_block_record,
    }
    manifest = {
        "schema_version": module.SCHEMA_VERSION,
        "archive_format_version": 2,
        "session_id": "doctor-live-tail",
        "session_label": label,
        "display": {"label": label, "date": "2026-06-11", "sequence": 6},
        "archive_status": "indexed",
        "distillation_status": "raw_archived",
        "raw": {
            "path": str(raw_path),
            "source_path": raw_source_path,
            "bytes": raw_path.stat().st_size,
            "line_count": 1,
            "sha256": "test",
            "indexing_status": "indexed",
        },
        "source": {"transcript_path": raw_source_path},
        "raw_blocks": {
            "index": str(session_dir / "raw" / module.RAW_BLOCK_INDEX_JSON),
            "compaction_events": str(
                session_dir / "raw" / module.RAW_COMPACTION_EVENTS_JSONL
            ),
            "blocks": [raw_block_record],
        },
        "segments": [segment_record],
    }
    write_json(
        session_dir / "raw" / module.RAW_SOURCE_JSON,
        {"source_path": raw_source_path},
    )
    write_json(
        session_dir / "raw" / module.RAW_BLOCK_INDEX_JSON,
        {"blocks": [raw_block_record]},
    )
    (session_dir / "raw" / module.RAW_COMPACTION_EVENTS_JSONL).write_text(
        "",
        encoding="utf-8",
    )
    write_json(session_dir / "session.manifest.json", manifest)
    write_json(session_dir / module.SESSION_INDEX_JSON, {"schema_version": 1, "events": []})
    write_json(
        root / module.REGISTRY_NAME,
        {
            "sessions": [
                {
                    "session_id": "doctor-live-tail",
                    "session_label": label,
                    "path": str(session_dir),
                    "archive_status": "indexed",
                    "display": {"label": label},
                }
            ]
        },
    )
    write_json(
        root / module.SESSION_NAME_INDEX_JSON,
        {
            "artifact_type": "session_name_index",
            "session_count": 1,
            "naming_readiness_counts": {},
        },
    )
    write_json(
        sessions_root / module.SESSIONS_INDEX_JSON,
        {
            "artifact_type": "sessions_directory_index",
            "session_count": 1,
            "naming_readiness_counts": {},
        },
    )
    old_ts = time.time() - module.GRAPH_HOT_LIVE_DEFER_SECONDS - 120
    if not recent_live:
        for path in [
            session_dir,
            session_dir / "raw",
            session_dir / "raw" / "blocks",
            session_dir / "segments",
        ]:
            touch_old(path, old_ts)
        for path in [
            raw_path,
            session_dir / "raw" / module.RAW_SOURCE_JSON,
            session_dir / "raw" / module.RAW_BLOCK_INDEX_JSON,
            session_dir / "raw" / module.RAW_COMPACTION_EVENTS_JSONL,
            session_dir / "session.manifest.json",
            session_dir / module.SESSION_INDEX_JSON,
            session_dir / module.SESSION_INDEX_MARKDOWN,
        ]:
            if path.exists():
                touch_old(path, old_ts)
    return workspace, root


def run_doctor_payload(workspace: Path, root: Path) -> tuple[int, dict[str, Any]]:
    args = SimpleNamespace(
        workspace_root=str(workspace),
        aoa_root=str(root),
        check_live_hooks=False,
        check_user_skill=False,
        check_installable_user_skills=False,
        check_codex_grounding=False,
        deep_segment_indexes=False,
    )
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = module.command_doctor(args)
    return code, json.loads(out.getvalue())


def complete_doctor_segment_fixture(
    root: Path,
    *,
    event: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    registry = module.read_json(root / module.REGISTRY_NAME, {})
    session_dir = Path(registry["sessions"][0]["path"])
    manifest = module.read_json(session_dir / "session.manifest.json", {})
    segment = manifest["segments"][0]
    raw_block = segment["raw_block"]
    markdown_path = Path(segment["markdown"])
    index_path = Path(segment["index"])
    raw_block_path = Path(raw_block["path"])
    markdown_path.write_text(
        "# Segment\n\n<a id=\"event-000001\"></a>\n",
        encoding="utf-8",
    )
    raw_block_path.write_text("{}\n", encoding="utf-8")
    module.write_json(
        index_path,
        {
            "schema_version": module.SCHEMA_VERSION,
            "segment_id": segment["segment_id"],
            "events": [
                event
                if event is not None
                else {
                    "event_id": "000001",
                    "type": "COMMAND",
                    "raw_ref": "raw:line:1",
                    "md_anchor": "event-000001",
                }
            ],
        },
    )
    return session_dir, index_path


def make_raw_unavailable_duplicate(
    root: Path,
    session_dir: Path,
    *,
    label: str,
    session_id: str | None = None,
) -> Path:
    duplicate = session_dir.parent / label
    shutil.copytree(session_dir, duplicate)
    manifest = module.read_json(duplicate / "session.manifest.json", {})
    manifest["session_id"] = session_id or manifest["session_id"]
    manifest["session_label"] = label
    manifest["archive_status"] = "raw_unavailable"
    manifest["display"] = {
        **(
            manifest.get("display")
            if isinstance(manifest.get("display"), dict)
            else {}
        ),
        "label": label,
        "navigation_path": str(duplicate),
    }
    module.write_json(duplicate / "session.manifest.json", manifest)
    incidents = duplicate / "incidents"
    incidents.mkdir(parents=True, exist_ok=True)
    (incidents / "20260822T000000Z__raw-session-unavailable__INCIDENT.md").write_text(
        "# preserved test incident\n",
        encoding="utf-8",
    )
    module.write_json(
        incidents / "20260822T000000Z__raw-session-unavailable__DIAGNOSTIC.json",
        {"session_id": manifest["session_id"], "incident_type": "raw_session_unavailable"},
    )
    return duplicate
