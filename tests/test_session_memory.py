from __future__ import annotations

import importlib.util
import fcntl
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "aoa_session_memory.py"
spec = importlib.util.spec_from_file_location("aoa_session_memory", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
sys.modules["aoa_session_memory"] = module
spec.loader.exec_module(module)


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")


def test_default_standalone_repo_prefers_bundles_topology(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    aoa_root.mkdir(parents=True)

    assert module.default_standalone_repo_for(aoa_root) == workspace / "bundles" / "aoa-session-memory"

    legacy_repo = workspace / "aoa-session-memory"
    legacy_repo.mkdir()
    assert module.default_standalone_repo_for(aoa_root) == legacy_repo

    bundled_repo = workspace / "bundles" / "aoa-session-memory"
    bundled_repo.mkdir(parents=True)
    assert module.default_standalone_repo_for(aoa_root) == bundled_repo


def test_readable_slug_removes_banned_topology_terms() -> None:
    slug = module.readable_slug("Task in /tmp/aoa wave4 review fixes")

    assert "tmp" not in slug.split("-")
    assert slug == "task-in-aoa-wave4-review-fixes"
    assert module.weak_title_text("# Files mentioned by the user: ## seed.zip")
    assert module.phase_candidate_name(
        "000",
        ["# AGENTS.md instructions for /srv\n<INSTRUCTIONS>policy</INSTRUCTIONS>", "Continue real naming work"],
        [],
        module.Counter(),
    )["name"] == "Continue real naming work"
    assert module.phase_candidate_name(
        "000",
        ["/home/dionysus/Загрузки/aoa-session-dist-exp(идея).md Вот тут лежит диалог с важной идеей"],
        [],
        module.Counter(),
    )["name"] == "Вот тут лежит диалог с важной идеей"
    generic_payload = module.phase_candidate_name(
        "000",
        ["Давай, действуй!"],
        ["scripts/aoa_session_memory.py"],
        module.Counter({"VERIFICATION": 1}),
    )
    assert generic_payload["name"] == "aoa_session_memory.py validation"
    assert generic_payload["basis"] == "linked_path_event_signals"
    assert "generic_user_intent_present" in generic_payload["quality_flags"]
    commit_payload = module.phase_candidate_name(
        "005",
        ["Коммить, пуш, мердж"],
        ["docs/ROADMAP.md"],
        module.Counter({"VERIFICATION": 1}),
    )
    assert commit_payload["name"] == "ROADMAP.md validation"
    assert commit_payload["basis"] == "linked_path_event_signals"
    assert "generic_user_intent_present" in commit_payload["quality_flags"]
    continue_payload = module.phase_candidate_name(
        "006",
        ["Это ещё не всё"],
        ["scripts/validate_repo.py"],
        module.Counter({"COMMAND": 2}),
    )
    assert continue_payload["name"] == "validate_repo.py investigation"
    assert continue_payload["basis"] == "linked_path_event_signals"
    assert "generic_user_intent_present" in continue_payload["quality_flags"]
    intro_payload = module.phase_candidate_name(
        "007",
        ["В этой сессии мы будем продолжать заниматься машиной.", "У нас работает ембеддинг модель сейчас, так? А реранкер?"],
        ["abyss-machine"],
        module.Counter({"COMMAND": 3}),
    )
    assert intro_payload["name"] == "У нас работает ембеддинг модель сейчас, так? А реранкер?"
    assert intro_payload["basis"] == "specific_user_intent"
    assert "generic_user_intent_present" in intro_payload["quality_flags"]
    tail_payload = module.phase_candidate_name(
        "008",
        ["Что теперь?"],
        ["docs/ROOT_SURFACE_LAW.md"],
        module.Counter({"VERIFICATION": 1}),
    )
    assert tail_payload["name"] == "ROOT_SURFACE_LAW.md validation"
    assert tail_payload["basis"] == "linked_path_event_signals"


def test_phase_candidate_review_turns_weak_names_into_actionable_queue_items() -> None:
    coverage = {"raw_ranges": [{"from_line": 10, "to_line": 30}], "note": "fixture"}
    review = module.phase_candidate_review(
        session_label="2026-05-20__001__large-session",
        segment_id="003",
        candidate_name=".aoa validation",
        confidence="low",
        name_basis="linked_path_event_signals",
        quality_flags=["no_specific_user_intent", "path_or_event_based_name"],
        coverage=coverage,
        evidence_refs=["raw:line:12"],
        linked_signals={
            "primary_user_intent": "",
            "support_paths": ["/srv/AbyssOS/.aoa/scripts/aoa_session_memory.py"],
            "support_event_types": {"COMMAND": 4, "VERIFICATION": 2},
        },
    )
    candidate = {
        "segment_id": "003",
        "name": ".aoa validation",
        "confidence": "low",
        "name_basis": "linked_path_event_signals",
        "quality_flags": ["no_specific_user_intent", "path_or_event_based_name"],
        "coverage": coverage,
        "evidence": ["raw:line:12"],
        "review": review,
    }
    payload = {
        "generated_at": "2026-05-20T00:00:00Z",
        "session_label": "2026-05-20__001__large-session",
        "archive_status": "indexed",
        "event_count": 20,
        "segment_count": 1,
        "candidate_count": 1,
        "review_queue_count": 1,
        "raw_path": "/tmp/session.raw.jsonl",
        "candidate_quality_counts": module.phase_candidate_quality_counts([candidate]),
        "review_queue": module.phase_review_queue([candidate]),
        "candidates": [candidate],
    }
    markdown = module.phase_discovery_markdown(payload)

    assert review["status"] == "needs_semantic_synthesis"
    assert review["action"] == "synthesize_reviewed_name_from_linked_signals"
    assert "review-phase-name" in review["apply_template"]
    assert "--segment 003" in review["apply_template"]
    assert "--reviewed-name '<reviewed phase name>'" in review["apply_template"]
    assert payload["review_queue"][0]["review"]["review_inputs"]["support_paths"]
    assert "## Review Apply Templates" in markdown
    assert "python3 scripts/aoa_session_memory.py review-phase-name" in markdown


def test_hook_archives_raw_and_builds_segments(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-session-1.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "session-1", "cwd": "/workspace/AbyssOS"}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Start hooks now"}]}},
            {"timestamp": "2026-05-12T00:00:02Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-1"}},
            {"timestamp": "2026-05-12T00:00:03Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-1", "output": "stdout line"}},
            {"timestamp": "2026-05-12T00:00:04Z", "type": "turn_context", "payload": {"summary": "compacted prior work"}},
            {"timestamp": "2026-05-12T00:00:05Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done"}]}},
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "session-1",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    assert receipt["ok"] is True
    session_dir = aoa_root / "sessions" / "2026-05-12__001__start-hooks-now"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_status"] == "indexed"
    assert manifest["display"]["label"] == "2026-05-12__001__start-hooks-now"
    assert manifest["display"]["title"] == "Start hooks now"
    assert manifest["display"]["path"] == str(session_dir)
    assert manifest["display"]["navigation_path"] == str(session_dir)
    assert receipt["display_name"] == "2026-05-12__001__start-hooks-now"
    assert receipt["navigation_path"] == str(session_dir)
    assert not (aoa_root / "sessions" / "session-1").exists()
    assert manifest["latest_event_count"] == 6
    assert len(manifest["segments"]) == 2
    assert (session_dir / "raw" / "session.raw.jsonl").exists()
    segment_index_path = session_dir / "segments" / "000__initial-to-compaction.index.json"
    assert segment_index_path.exists()
    segment_index = json.loads(segment_index_path.read_text(encoding="utf-8"))
    assert "COMMAND" in segment_index["by_type"]
    assert "COMMAND_OUTPUT" in segment_index["by_type"]
    segment_md = (session_dir / "segments" / "000__initial-to-compaction.md").read_text(encoding="utf-8")
    assert "index: ./000__initial-to-compaction.index.json" in segment_md
    assert "stdout line" in segment_md
    registry = json.loads((aoa_root / "session-registry.json").read_text(encoding="utf-8"))
    registry_record = registry["sessions"][0]
    assert registry_record["session_label"] == "2026-05-12__001__start-hooks-now"
    assert registry_record["raw"]["path"] == str(session_dir / "raw" / "session.raw.jsonl")
    assert registry_record["raw"]["indexing_status"] == "indexed"
    assert registry_record["raw"]["blocks_index"] == str(session_dir / "raw" / "blocks.index.json")
    assert registry_record["raw_blocks"]["block_count"] == 2


def test_agent_event_taxonomy_task_episodes_and_search_routes(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-13T00-00-00-agent-events.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-13T00:00:00Z", "type": "session_meta", "payload": {"id": "agent-events", "cwd": str(workspace)}},
            {"timestamp": "2026-06-13T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Audit the session-memory MCP hook"}]}},
            {"timestamp": "2026-06-13T00:00:02Z", "type": "response_item", "payload": {"type": "reasoning", "summary": [{"type": "summary_text", "text": "Need inspect source before changing."}]}},
            {"timestamp": "2026-06-13T00:00:03Z", "type": "event_msg", "payload": {"type": "agent_message", "message": "Сейчас проверяю живой контур."}},
            {"timestamp": "2026-06-13T00:00:04Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Сейчас проверяю живой контур."}]}},
            {"timestamp": "2026-06-13T00:00:05Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-1", "arguments": "{\"cmd\":\"pytest -q\"}"}},
            {"timestamp": "2026-06-13T00:00:06Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-1", "output": "1 passed"}},
            {"timestamp": "2026-06-13T00:00:07Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Почти готово, сейчас прогоню еще одну проверку."}]}},
            {"timestamp": "2026-06-13T00:00:08Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Готово. Итог: проверка прошла."}]}},
            {"timestamp": "2026-06-13T00:00:09Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Осталось проверить open thread отдельно."}]}},
            {"timestamp": "2026-06-13T00:00:10Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Продолжай"}]}},
            {"timestamp": "2026-06-13T00:00:11Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Дальше беру второй сценарий."}]}},
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "agent-events",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = next(path for path in (aoa_root / "sessions").iterdir() if path.is_dir())
    segment_index = json.loads(next((session_dir / "segments").glob("*.index.json")).read_text(encoding="utf-8"))
    assert "assistant_reasoning_boundary" in segment_index["by_agent_event"]
    assert "assistant_progress_update" in segment_index["by_agent_event"]
    assert "assistant_final_closeout" in segment_index["by_agent_event"]
    assert "assistant_open_thread" in segment_index["by_agent_event"]

    reasoning_event = next(event for event in segment_index["events"] if event["type"] == "ASSISTANT_REASONING_BOUNDARY")
    assert reasoning_event["facets"]["conversation_act"]["kind"] == "assistant_reasoning_boundary"
    assert reasoning_event["facets"]["agent_event"]["class"] == "assistant_reasoning_boundary"
    assert reasoning_event["facets"]["agent_event"]["content_status"] == "boundary_only"

    false_closeout = next(event for event in segment_index["events"] if "Почти готово" in event["title"] or event["event_id"] == "000008")
    assert false_closeout["type"] != "FINAL_STATE"
    assert false_closeout["facets"]["agent_event"]["class"] == "assistant_progress_update"
    assert "final_marker_not_closeout" in false_closeout["facets"]["agent_event"]["ambiguity_flags"]

    final_closeout = next(event for event in segment_index["events"] if event["type"] == "FINAL_STATE")
    assert final_closeout["facets"]["agent_event"]["class"] == "assistant_final_closeout"

    open_thread = next(event for event in segment_index["events"] if event["type"] == "OPEN_THREAD")
    assert open_thread["facets"]["conversation_act"]["kind"] == "assistant_open_thread"
    assert open_thread["facets"]["agent_event"]["class"] == "assistant_open_thread"

    stream_event = next(event for event in segment_index["events"] if event.get("source_type") == "event_msg" and event["type"] == "ASSISTANT_MESSAGE")
    assert stream_event["facets"]["agent_event"]["canonical"] is False
    assert stream_event["facets"]["agent_event"]["source_lane"] == "event_msg_stream"

    session_index = json.loads((session_dir / "session.index.json").read_text(encoding="utf-8"))
    assert session_index["agent_event_counts"]["assistant_reasoning_boundary"] == 1
    assert session_index["task_episode_counts"]["total"] == 2
    first_episode = session_index["task_episodes"][0]
    assert first_episode["start_user_ref"]["raw_ref"] == "raw:line:2"
    assert first_episode["status"] == "closed"
    assert first_episode["reasoning_refs"]
    assert first_episode["progress_refs"]
    assert first_episode["verification_refs"]
    assert first_episode["closeout_refs"]
    assert session_index["task_episodes"][1]["transition"]["previous_episode_id"] == first_episode["episode_id"]
    recent_episode_route = module.task_episode_route_search(aoa_root=aoa_root, target="latest", limit=1)
    assert recent_episode_route["order"] == "recent"
    assert recent_episode_route["results"][0]["episode_id"] == "task-0002"
    chronological_episode_route = module.task_episode_route_search(
        aoa_root=aoa_root,
        target="latest",
        limit=1,
        order="chronological",
    )
    assert chronological_episode_route["order"] == "chronological"
    assert chronological_episode_route["results"][0]["episode_id"] == "task-0001"

    search_index = module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=True)
    assert search_index["ok"] is True
    audit = module.agent_event_audit(
        aoa_root=aoa_root,
        target="latest",
        sample_limit=2,
        probe_routes=True,
        route_probe_limit=2,
    )
    assert audit["stream_canonical_neighbor_pair_count"] >= 1
    assert audit["stream_canonical_retrieval_guard_ok"] is True
    assert audit["quality_ok"] is True
    assert audit["raw_shape_samples"]
    assert any(sample["raw_shape"]["payload_type"] == "message" for sample in audit["raw_shape_samples"])
    ordered_audit = module.agent_event_audit(
        aoa_root=aoa_root,
        target="all",
        order="longest",
        min_events=1,
        limit=1,
    )
    assert ordered_audit["order"] == "longest"
    assert ordered_audit["selected_count"] == 1
    assert ordered_audit["selected_sessions"][0]["event_count"] >= 1
    monkeypatch.setattr(module, "compact_stamp", lambda: "20260614T000000Z")
    first_report = module.agent_event_audit(aoa_root=aoa_root, target="latest", write_report=True)
    second_report = module.agent_event_audit(aoa_root=aoa_root, target="latest", write_report=True)
    assert first_report["quality_ok"] is True
    assert first_report["report_json"] != second_report["report_json"]
    assert first_report["report_json"].endswith("__agent-event-audit.json")
    assert second_report["report_json"].endswith("__agent-event-audit__01.json")
    assert Path(first_report["report_json"]).exists()
    assert Path(second_report["report_json"]).exists()
    closeouts = module.search_sessions(aoa_root=aoa_root, doc_type="event", agent_event="assistant_final_closeout", limit=5)
    assert closeouts["result_count"] == 1
    assert closeouts["results"][0]["agent_event"] == "assistant_final_closeout"
    assert closeouts["results"][0]["task_episode_id"] == "task-0001"
    assert closeouts["results"][0]["freshness"]["basis"] == "indexed_snapshot"
    default_response_route = module.agent_event_route_search(
        aoa_root=aoa_root,
        session=session_dir.name,
        limit=20,
    )
    assert default_response_route["result_count"] >= 1
    assert all(item["agent_event"] != "assistant_open_thread" for item in default_response_route["results"])
    open_thread_route = module.agent_event_route_search(
        aoa_root=aoa_root,
        session=session_dir.name,
        agent_events=["assistant_open_thread"],
        limit=5,
    )
    assert open_thread_route["result_count"] == 1
    assert open_thread_route["results"][0]["agent_event"] == "assistant_open_thread"
    assert open_thread_route["results"][0]["event_id"] == open_thread["event_id"]
    progress_route = module.agent_event_route_search(
        aoa_root=aoa_root,
        session=session_dir.name,
        agent_events=["assistant_progress_update"],
        limit=10,
    )
    assert progress_route["result_count"] == 2
    assert {item["event_id"] for item in progress_route["results"]} == {"000005", "000008"}
    assert all(item["agent_event_source"] != "event_msg_stream" for item in progress_route["results"])
    progress_hit = progress_route["results"][0]
    assert progress_hit["raw_ref"] == progress_hit["refs"]["raw"]
    assert progress_hit["raw_line"] == int(progress_hit["raw_ref"].split(":")[-1])
    assert progress_hit["segment_ref"] == progress_hit["refs"]["segment"]
    assert progress_hit["segment_index"] == progress_hit["refs"]["segment_index"]
    assert progress_hit["session_ref"] == progress_hit["refs"]["session"]
    assert progress_hit["preview"] == progress_hit["bounded_preview"]
    assert progress_hit["preview_source"] == "raw_semantic_text"
    assert "route_signal" not in progress_hit["bounded_preview"]
    assert progress_hit["bounded_preview"]
    assert any(text in progress_hit["bounded_preview"] for text in ["Сейчас проверяю", "Почти готово"])
    progress_with_stream = module.agent_event_route_search(
        aoa_root=aoa_root,
        session=session_dir.name,
        agent_events=["assistant_progress_update"],
        limit=10,
        include_stream_copies=True,
    )
    assert progress_with_stream["result_count"] == 3
    assert "event_msg_stream" in {item["agent_event_source"] for item in progress_with_stream["results"]}
    episodes = module.search_sessions(aoa_root=aoa_root, doc_type="task_episode", limit=5)
    assert episodes["result_count"] == 2
    windows = module.agent_event_windows(
        aoa_root=aoa_root,
        agent_events=["assistant_reasoning_boundary"],
        limit=1,
        before=1,
        after=2,
    )
    assert windows["window_count"] == 1
    assert windows["windows"][0]["ok"] is True
    reasoning_window = windows["windows"][0]
    assert reasoning_window["raw_ref"] == reasoning_window["refs"]["raw"]
    assert reasoning_window["raw_line"] == int(reasoning_window["raw_ref"].split(":")[-1])
    assert reasoning_window["segment_ref"] == reasoning_window["refs"]["segment"]
    assert reasoning_window["segment_index"] == reasoning_window["refs"]["segment_index"]
    assert reasoning_window["session_ref"] == reasoning_window["refs"]["session"]
    assert reasoning_window["anchor"]["event_id"] == reasoning_window["event_id"]
    assert reasoning_window["center"]["event_id"] == reasoning_window["event_id"]
    assert reasoning_window["preview_source"] == "raw_semantic_text"
    assert reasoning_window["bounded_preview"]
    assert "Need inspect source" in reasoning_window["bounded_preview"]


def test_agent_reasoning_windows_bridge_from_query_matched_agent_answer(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-13T00-00-00-reasoning-bridge.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-13T00:00:00Z", "type": "session_meta", "payload": {"id": "reasoning-bridge", "cwd": str(workspace)}},
            {"timestamp": "2026-06-13T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Проверь MCP"}]}},
            {"timestamp": "2026-06-13T00:00:02Z", "type": "response_item", "payload": {"type": "reasoning", "summary": [{"type": "summary_text", "text": "Need a bounded route check."}]}},
            {"timestamp": "2026-06-13T00:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "aoa-session-memory-mcp route checked."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "reasoning-bridge",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=True)

    direct = module.agent_event_route_search(
        aoa_root=aoa_root,
        query="aoa-session-memory-mcp",
        agent_events=["assistant_reasoning_boundary"],
        limit=3,
    )
    assert direct["result_count"] == 0

    windows = module.agent_event_windows(
        aoa_root=aoa_root,
        query="aoa-session-memory-mcp",
        agent_events=["assistant_reasoning_boundary"],
        limit=3,
        before=0,
        after=1,
    )
    assert windows["query_bridge"]["enabled"] is True
    assert windows["query_bridge"]["used"] is True
    assert windows["window_count"] == 1
    assert windows["windows"][0]["ok"] is True
    assert windows["windows"][0]["events"][0]["agent_event"] == "assistant_reasoning_boundary"
    assert windows["windows"][0]["bridge"]["source"] == "query_matched_agent_event_neighborhood"


def test_agent_event_windows_mark_encrypted_reasoning_boundary_preview(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-13T00-00-00-encrypted-reasoning.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-13T00:00:00Z", "type": "session_meta", "payload": {"id": "encrypted-reasoning", "cwd": str(workspace)}},
            {"timestamp": "2026-06-13T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Проверь reasoning boundary"}]}},
            {"timestamp": "2026-06-13T00:00:02Z", "type": "response_item", "payload": {"type": "reasoning", "summary": [], "encrypted_content": "opaque"}},
            {"timestamp": "2026-06-13T00:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Reasoning boundary checked."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "encrypted-reasoning",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=True)

    windows = module.agent_event_windows(
        aoa_root=aoa_root,
        agent_events=["assistant_reasoning_boundary"],
        limit=1,
        before=0,
        after=1,
    )
    assert windows["window_count"] == 1
    assert windows["windows"][0]["preview_source"] == "encrypted_reasoning_boundary"
    assert "summary empty" in windows["windows"][0]["bounded_preview"]


def test_prompt_only_task_episode_is_interrupted_not_quality_gap(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-13T00-00-00-prompt-only-tail.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-13T00:00:00Z", "type": "session_meta", "payload": {"id": "prompt-only-tail", "cwd": str(workspace)}},
            {"timestamp": "2026-06-13T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Continue"}]}},
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "prompt-only-tail",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = next(path for path in (aoa_root / "sessions").iterdir() if path.is_dir())
    session_index = json.loads((session_dir / "session.index.json").read_text(encoding="utf-8"))
    episode = session_index["task_episodes"][0]
    assert episode["status"] == "interrupted"
    assert "no_agent_response_seen" in episode["ambiguity_flags"]

    audit = module.agent_event_audit(aoa_root=aoa_root, target="latest")
    assert audit["zero_count_task_episode_count"] == 1
    assert audit["unexplained_zero_count_task_episode_count"] == 0
    assert audit["weak_spots"]["task_episode_gap"] == []
    assert audit["quality_ok"] is True


def test_agent_event_windows_resolve_renamed_latest_segment_refs(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-13T00-00-00-renamed-latest.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-13T00:00:00Z", "type": "session_meta", "payload": {"id": "renamed-latest", "cwd": str(workspace)}},
            {"timestamp": "2026-06-13T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Проверь reasoning window"}]}},
            {"timestamp": "2026-06-13T00:00:02Z", "type": "response_item", "payload": {"type": "reasoning", "summary": [{"type": "summary_text", "text": "Need a bounded live route check."}]}},
            {"timestamp": "2026-06-13T00:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Сейчас проверяю окно рассуждения."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "renamed-latest",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=True)

    session_dir = next(path for path in (aoa_root / "sessions").iterdir() if path.is_dir())
    old_index = next((session_dir / "segments").glob("*to-latest.index.json"))
    old_md = old_index.with_name(old_index.name.replace(".index.json", ".md"))
    old_raw_block = session_dir / "raw" / "blocks" / old_index.name.replace(".index.json", ".raw.jsonl")
    new_index = old_index.with_name(old_index.name.replace("to-latest", "to-compaction"))
    new_md = old_md.with_name(old_md.name.replace("to-latest", "to-compaction"))
    new_raw_block = old_raw_block.with_name(old_raw_block.name.replace("to-latest", "to-compaction"))

    old_index.rename(new_index)
    old_md.rename(new_md)
    old_raw_block.rename(new_raw_block)

    segment_index = json.loads(new_index.read_text(encoding="utf-8"))
    segment_index["markdown"] = str(segment_index.get("markdown", "")).replace(old_md.name, new_md.name)
    for event in segment_index.get("events", []):
        if isinstance(event, dict) and event.get("md_anchor"):
            event["md_anchor"] = str(event["md_anchor"]).replace(old_md.name, new_md.name)
    new_index.write_text(json.dumps(segment_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest_path = session_dir / "session.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for segment in manifest.get("segments", []):
        if isinstance(segment, dict) and str(segment.get("index") or "") == str(old_index):
            segment["index"] = str(new_index)
            segment["markdown"] = str(new_md)
            raw_block = segment.get("raw_block") if isinstance(segment.get("raw_block"), dict) else {}
            raw_block["path"] = str(new_raw_block)
            raw_block["rel"] = f"raw/blocks/{new_raw_block.name}"
            segment["raw_block"] = raw_block
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    route = module.agent_event_route_search(
        aoa_root=aoa_root,
        session=session_dir.name,
        agent_events=["assistant_reasoning_boundary"],
        limit=1,
    )
    assert route["result_count"] == 1
    hit = route["results"][0]
    assert hit["refs"]["segment_index"] == str(new_index)
    assert "segment_index_ref_resolved_by_segment_id" in hit["ref_resolution"]["diagnostics"]

    windows = module.agent_event_windows(
        aoa_root=aoa_root,
        session=session_dir.name,
        agent_events=["assistant_reasoning_boundary"],
        limit=1,
        before=1,
        after=1,
    )
    assert windows["windows"][0]["ok"] is True
    assert windows["windows"][0]["refs"]["segment_index"] == str(new_index)

    refs = module.evidence_ref_integrity_state(aoa_root, sample_limit=20)
    assert refs["ok"] is True


def test_agent_event_route_resolves_latest_and_filters_stream_copies_before_limit(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-13T00-00-00-agent-event-latest.jsonl"
    stream_rows = [
        {
            "timestamp": f"2026-06-13T00:00:{second:02d}Z",
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "Сейчас проверяю живой контур."},
        }
        for second in range(4, 20)
    ]
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-13T00:00:00Z", "type": "session_meta", "payload": {"id": "agent-event-latest", "cwd": str(workspace)}},
            {"timestamp": "2026-06-13T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Проверь живой контур"}]}},
            {"timestamp": "2026-06-13T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Сейчас проверяю живой контур."}]}},
            {"timestamp": "2026-06-13T00:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Почти готово, сейчас прогоню еще одну проверку."}]}},
            *stream_rows,
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "agent-event-latest",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=True)

    direct_latest = module.search_sessions(
        aoa_root=aoa_root,
        session="latest",
        doc_type="event",
        agent_event="assistant_progress_update",
        limit=5,
    )
    assert direct_latest["result_count"] == 5

    route = module.agent_event_route_search(
        aoa_root=aoa_root,
        session="latest",
        agent_events=["assistant_progress_update"],
        limit=2,
    )
    assert route["result_count"] == 2
    assert {item["event_id"] for item in route["results"]} == {"000003", "000004"}
    assert all(item["agent_event_source"] != "event_msg_stream" for item in route["results"])

    with_stream = module.agent_event_route_search(
        aoa_root=aoa_root,
        session="latest",
        agent_events=["assistant_progress_update"],
        limit=3,
        include_stream_copies=True,
    )
    assert with_stream["result_count"] == 3
    assert "event_msg_stream" in {item["agent_event_source"] for item in with_stream["results"]}


def test_latest_session_prefers_transcript_activity_over_generated_update_time(tmp_path: Path) -> None:
    aoa_root = tmp_path / ".aoa"
    old_dir = aoa_root / "sessions" / "2026-05-04__001__old-maintenance-rewrite"
    active_dir = aoa_root / "sessions" / "2026-06-04__001__active-transcript"
    old_raw = old_dir / "raw" / "session.raw.jsonl"
    active_raw = active_dir / "raw" / "session.raw.jsonl"
    old_transcript = tmp_path / "rollout-2026-05-04T00-00-00-old.jsonl"
    active_transcript = tmp_path / "rollout-2026-06-04T00-00-00-active.jsonl"
    for path, session_id in [(old_raw, "old-maintenance"), (active_raw, "active-transcript"), (old_transcript, "old-maintenance"), (active_transcript, "active-transcript")]:
        write_jsonl(path, [{"timestamp": "2026-06-01T00:00:00Z", "type": "session_meta", "payload": {"id": session_id}}])
    os.utime(old_transcript, (100.0, 100.0))
    os.utime(old_raw, (100.0, 100.0))
    os.utime(active_transcript, (200.0, 200.0))
    os.utime(active_raw, (150.0, 150.0))

    old_manifest = {
        "schema_version": 1,
        "session_id": "old-maintenance",
        "created_at": "2026-05-04T00:00:00Z",
        "updated_at": "2026-06-14T01:21:57Z",
        "source": {"transcript_path": str(old_transcript)},
        "archive_status": "indexed",
        "distillation_status": "raw_archived",
        "raw": {"path": str(old_raw), "source_path": str(old_transcript)},
        "segments": [],
        "latest_event_count": 1,
        "display": {"date": "2026-05-04", "sequence": 1, "label": old_dir.name, "navigation_path": str(old_dir)},
        "session_label": old_dir.name,
    }
    active_manifest = {
        **old_manifest,
        "session_id": "active-transcript",
        "created_at": "2026-06-04T00:00:00Z",
        "updated_at": "2026-06-13T00:00:00Z",
        "source": {"transcript_path": str(active_transcript)},
        "raw": {"path": str(active_raw), "source_path": str(active_transcript)},
        "display": {"date": "2026-06-04", "sequence": 1, "label": active_dir.name, "navigation_path": str(active_dir)},
        "session_label": active_dir.name,
    }
    old_dir.mkdir(parents=True, exist_ok=True)
    active_dir.mkdir(parents=True, exist_ok=True)
    module.write_json(old_dir / "session.manifest.json", old_manifest)
    module.write_json(active_dir / "session.manifest.json", active_manifest)
    module.update_registry(aoa_root, old_manifest, old_dir)
    module.update_registry(aoa_root, active_manifest, active_dir)

    latest = module.resolve_session_record(aoa_root, "latest")

    assert latest["session_id"] == "active-transcript"


def test_token_accounting_records_provider_usage_and_estimates(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-token-accounting.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "token-accounting", "cwd": str(workspace)}},
            {
                "timestamp": "2026-05-12T00:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Count the session tokens"}]},
            },
            {
                "timestamp": "2026-05-12T00:00:02Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "model": "gpt-5",
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cached_tokens": 2,
                    "total_tokens": 15,
                    "context_window_tokens": 100,
                },
            },
            {
                "timestamp": "2026-05-12T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Done"}]},
            },
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "token-accounting",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    record = module.resolve_session_record(aoa_root, "token-accounting")
    session_dir = Path(record["path"])
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    session_index = json.loads((session_dir / "session.index.json").read_text(encoding="utf-8"))
    segment_index = json.loads((session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8"))
    token_event = next(item for item in segment_index["events"] if item["type"] == "CONTEXT_STATE")

    assert manifest["token_accounting_schema_version"] == module.TOKEN_ACCOUNTING_SCHEMA_VERSION
    assert manifest["token_accounting"]["generator_version"] == module.TOKEN_ACCOUNTING_GENERATOR_VERSION
    assert manifest["token_accounting"]["totals_by_basis"]["provider_reported"]["total_tokens"] == 15
    assert manifest["token_accounting"]["totals_by_basis"]["provider_reported"]["cached_tokens"] == 2
    assert manifest["token_accounting"]["provider_reported_event_count"] == 1
    assert manifest["token_accounting"]["estimated_event_count"] >= 1
    assert session_index["token_accounting"]["totals_by_basis"]["provider_reported"]["input_tokens"] == 10
    assert segment_index["token_accounting"]["count_by_basis"]["provider_reported"] == 1
    assert token_event["token_accounting"]["count_basis"] == "provider_reported"
    assert token_event["token_accounting"]["privacy"]["prompt_text_logged"] is False
    assert "text" not in token_event["token_accounting"]
    estimated_events = [
        item for item in segment_index["events"]
        if isinstance(item.get("token_accounting"), dict)
        and item["token_accounting"].get("count_basis") == "estimated"
    ]
    assert estimated_events
    assert all(item["token_accounting"].get("tokenizer_id") == module.TOKEN_ACCOUNTING_ESTIMATOR_ID for item in estimated_events)

    raw_path = session_dir / "raw" / "session.raw.jsonl"
    raw_sha_before = module.sha256_file(raw_path)
    manifest.pop("token_accounting", None)
    manifest.pop("token_accounting_schema_version", None)
    for segment in manifest["segments"]:
        segment.pop("token_accounting", None)
    for block in manifest["raw_blocks"]["blocks"]:
        block.pop("token_accounting", None)
    (session_dir / "session.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    session_index.pop("token_accounting", None)
    session_index.pop("token_accounting_schema_version", None)
    (session_dir / "session.index.json").write_text(json.dumps(session_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    segment_index.pop("token_accounting", None)
    (session_dir / "segments" / "000__initial-to-latest.index.json").write_text(json.dumps(segment_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    raw_blocks_index_path = session_dir / "raw" / "blocks.index.json"
    raw_blocks_index = json.loads(raw_blocks_index_path.read_text(encoding="utf-8"))
    for block in raw_blocks_index["blocks"]:
        block.pop("token_accounting", None)
    raw_blocks_index_path.write_text(json.dumps(raw_blocks_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    maintenance_plan = module.maintain_indexes(
        aoa_root=aoa_root,
        target="token-accounting",
        max_raw_bytes=1,
        token_max_raw_bytes=raw_path.stat().st_size + 1024,
    )
    maintenance_actions = {item["id"]: item for item in maintenance_plan["actions"]}
    assert maintenance_plan["max_raw_bytes"] == 1
    assert maintenance_plan["token_max_raw_bytes"] == raw_path.stat().st_size + 1024
    assert maintenance_plan["token_backfill"]["counts"]["planned"] == 1
    assert maintenance_actions["token_accounting_backfill"]["needed"] is True

    dry_run = module.token_accounting_backfill(aoa_root=aoa_root, target="token-accounting", apply=False)
    assert dry_run["counts"]["planned"] == 1
    assert "manifest_missing_token_accounting" in dry_run["results"][0]["diagnostics"]
    assert "raw_blocks_manifest_missing_token_accounting" in dry_run["results"][0]["diagnostics"]

    applied = module.token_accounting_backfill(aoa_root=aoa_root, target="token-accounting", apply=True)
    assert applied["counts"]["backfilled"] == 1
    assert applied["results"][0]["raw_unchanged"] is True
    assert applied["results"][0]["raw_sha256_before"] == raw_sha_before
    assert applied["results"][0]["raw_sha256_after"] == raw_sha_before
    assert applied["results"][0]["after_diagnostics"] == []
    idempotent = module.token_accounting_backfill(aoa_root=aoa_root, target="token-accounting", apply=False)
    assert idempotent["counts"]["current"] == 1

    refreshed_manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    refreshed_session_index = json.loads((session_dir / "session.index.json").read_text(encoding="utf-8"))
    report = module.token_accounting_report(
        aoa_root=aoa_root,
        target="token-accounting",
        include_compaction_deltas=True,
    )
    assert refreshed_manifest["token_accounting"]["totals_by_basis"]["provider_reported"]["total_tokens"] == 15
    assert refreshed_session_index["token_accounting"]["totals_by_basis"]["provider_reported"]["input_tokens"] == 10
    assert report["sessions"][0]["compaction_deltas"][0]["delta_token_accounting"]["count_by_basis"]["provider_reported"] == 1

    report = module.token_accounting_report(aoa_root=aoa_root, target="latest", include_segments=True)
    assert report["ok"] is True
    assert report["aggregate"]["schema"] == module.TOKEN_ACCOUNTING_CONTRACT
    assert report["aggregate"]["totals_by_basis"]["provider_reported"]["total_tokens"] == 15
    assert report["sessions"][0]["context_pressure"]["available"] is True
    assert report["sessions"][0]["segments"]
    report_json = json.dumps(report, ensure_ascii=False)
    assert "Count the session tokens" not in report_json
    assert "Done" not in report_json


def test_token_accounting_uses_last_token_usage_not_cumulative_snapshots(tmp_path: Path) -> None:
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-token-count-snapshots.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-05-12T00:00:01Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 10,
                            "cached_input_tokens": 3,
                            "output_tokens": 5,
                            "reasoning_output_tokens": 2,
                            "total_tokens": 15,
                        },
                        "last_token_usage": {
                            "input_tokens": 10,
                            "cached_input_tokens": 3,
                            "output_tokens": 5,
                            "reasoning_output_tokens": 2,
                            "total_tokens": 15,
                        },
                        "model_context_window": 100,
                    },
                },
            },
            {
                "timestamp": "2026-05-12T00:00:02Z",
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 17,
                            "cached_input_tokens": 4,
                            "output_tokens": 13,
                            "reasoning_output_tokens": 3,
                            "total_tokens": 30,
                        },
                        "last_token_usage": {
                            "input_tokens": 7,
                            "cached_input_tokens": 1,
                            "output_tokens": 8,
                            "reasoning_output_tokens": 1,
                            "total_tokens": 15,
                        },
                        "model_context_window": 100,
                    },
                },
            },
        ],
    )

    events = module.parse_raw_events(transcript)
    summary = module.token_accounting_summary_for_session(events, session_id="token-count-snapshots", include_observations=True)
    provider = summary["totals_by_basis"]["provider_reported"]

    assert summary["generator_version"] == module.TOKEN_ACCOUNTING_GENERATOR_VERSION
    assert summary["provider_reported_event_count"] == 2
    assert summary["count_by_basis"]["provider_reported"] == 2
    assert provider["input_tokens"] == 17
    assert provider["output_tokens"] == 13
    assert provider["cached_tokens"] == 4
    assert provider["reasoning_tokens"] == 3
    assert provider["total_tokens"] == 30
    assert provider["context_tokens"] == 10
    assert provider["context_window_tokens"] == 100
    assert all(item["source_kind"] == "codex_last_token_usage" for item in summary["observations"])
    assert all(item["payload_path"] == "payload.info.last_token_usage" for item in summary["observations"])


def test_sync_indexes_copied_snapshot_when_transcript_grows_during_copy(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-growing.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "growing-session", "cwd": str(workspace)}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Growing transcript"}]}},
        ],
    )
    original_copy2 = module.shutil.copy2

    def copy_after_append(src: Path, dst: Path) -> Path:
        with Path(src).open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {
                        "timestamp": "2026-05-12T00:00:02Z",
                        "type": "response_item",
                        "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "appended"}]},
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        return original_copy2(src, dst)

    monkeypatch.setattr(module.shutil, "copy2", copy_after_append)

    payload = module.sync_session_from_transcript(
        aoa_root=aoa_root,
        event={"session_id": "growing-session", "transcript_path": str(transcript), "cwd": str(workspace)},
        transcript_path=transcript,
        hook_event_name="ManualSync",
    )

    session_dir = Path(payload["session_dir"])
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    raw_blocks = json.loads((session_dir / "raw" / "blocks.index.json").read_text(encoding="utf-8"))
    raw_line_count = len((session_dir / "raw" / "session.raw.jsonl").read_text(encoding="utf-8").splitlines())

    assert manifest["latest_event_count"] == 3
    assert manifest["raw"]["line_count"] == raw_line_count == 3
    assert sum(block["line_count"] for block in raw_blocks["blocks"]) == 3


def test_segment_index_records_universal_facets_and_relationships(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-universal-events.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-05-12T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "universal-events", "cwd": str(workspace), "model": "final-assumption-compact"},
            },
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Inspect the repo"}]}},
            {"timestamp": "2026-05-12T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: inspect before editing"}]}},
            {"timestamp": "2026-05-12T00:00:03Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-read", "arguments": json.dumps({"cmd": "rg -n TODO README.md"})}},
            {"timestamp": "2026-05-12T00:00:04Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-read", "output": "Chunk ID: a\nProcess exited with code 0\nOutput:\nREADME.md:1:TODO\n"}},
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "universal-events",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = aoa_root / "sessions" / "2026-05-12__001__inspect-the-repo"
    segment_index = json.loads((session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8"))
    records = {event["event_id"]: event for event in segment_index["events"]}

    assert "workspace_navigation" in segment_index["by_family"]
    assert "inspect" in segment_index["by_phase"]
    assert "succeeded" in segment_index["by_outcome"]
    read_event = records["000004"]
    output_event = records["000005"]
    assert read_event["type"] == "FILE_READ"
    assert read_event["family"] == "workspace_navigation"
    assert read_event["facets"]["command_kind"] == "read"
    assert "correlation_id" not in records["000001"]
    assert "assumption_signal" not in records["000001"]["tags"]
    assert "final_state_signal" not in records["000001"]["tags"]
    assert "compaction" not in records["000001"]["tags"]
    assert output_event["outcome"] == "succeeded"
    assert output_event["correlation_id"] == "call-read"
    assert {"rel": "responds_to", "event_id": "000004", "correlation_id": "call-read"} in output_event["relationships"]

    record = module.registry_sessions(aoa_root)[0]
    profile = module.first_wave_session_profile(
        aoa_root,
        record,
        policy=module.default_batch_distillation_policy(),
        route_map={"COMMAND_OUTPUT": ["parser_candidate"]},
        workspace_root=workspace,
    )
    assert "mechanics_candidate" not in profile["lanes"]


def test_segment_index_records_conversation_acts(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-conversation-acts.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "conversation-acts", "cwd": str(workspace)}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Важная идея: нужно индексировать мысли"}]}},
            {"timestamp": "2026-05-12T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "План: сначала проверю индекс"}]}},
            {"timestamp": "2026-05-12T00:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Ты не понял, это ошибка"}]}},
            {"timestamp": "2026-05-12T00:00:04Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-test", "arguments": json.dumps({"cmd": "pytest -q"})}},
            {"timestamp": "2026-05-12T00:00:05Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-test", "output": "Process exited with code 0\nOutput:\n2 passed\n"}},
            {"timestamp": "2026-05-12T00:00:06Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Готово: итог проверки зеленый"}]}},
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "conversation-acts",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = aoa_root / "sessions" / "2026-05-12__001__важная-идея-нужно-индексировать-мысли"
    segment_index = json.loads((session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8"))
    records = {event["event_id"]: event for event in segment_index["events"]}

    assert segment_index["conversation_act_schema_version"] == module.CONVERSATION_ACT_SCHEMA_VERSION
    assert records["000002"]["facets"]["conversation_act"]["kind"] == "operator_concept"
    assert records["000003"]["facets"]["conversation_act"]["kind"] == "assistant_plan"
    assert records["000004"]["facets"]["conversation_act"]["kind"] == "operator_correction"
    assert records["000005"]["facets"]["conversation_act"]["kind"] == "command_verification_request"
    assert records["000006"]["facets"]["conversation_act"]["kind"] == "verification_result"
    assert records["000007"]["facets"]["conversation_act"]["kind"] == "assistant_final_closeout"
    assert segment_index["by_conversation_act"]["operator_concept"] == ["000002"]
    assert segment_index["by_conversation_act"]["operator_correction"] == ["000004"]
    assert segment_index["by_conversation_act"]["verification_result"] == ["000006"]

    audit = module.conversation_act_audit(aoa_root=aoa_root, target="conversation-acts", write_report=True)
    assert audit["ok"] is True
    assert audit["missing_eligible_conversation_act"] == 0
    assert audit["counts"]["operator_concept"] == 1
    assert audit["counts"]["operator_correction"] == 1
    assert audit["counts"]["verification_result"] == 1
    assert Path(audit["report_json"]).exists()
    assert Path(audit["report_markdown"]).exists()
    monkeypatch.setattr(module, "compact_stamp", lambda: "20260614T000000Z")
    first_report = module.conversation_act_audit(aoa_root=aoa_root, target="conversation-acts", write_report=True)
    second_report = module.conversation_act_audit(aoa_root=aoa_root, target="conversation-acts", write_report=True)
    assert first_report["report_json"] != second_report["report_json"]
    assert first_report["report_json"].endswith("__conversation-act-audit.json")
    assert second_report["report_json"].endswith("__conversation-act-audit__01.json")
    assert Path(first_report["report_json"]).exists()
    assert Path(second_report["report_json"]).exists()


def test_segment_index_records_session_acts_and_work_context(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-techniques"
    repo.mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# aoa-techniques\n", encoding="utf-8")
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-24T00-00-00-session-acts.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-24T00:00:00Z", "type": "session_meta", "payload": {"id": "session-acts", "cwd": str(repo)}},
            {
                "timestamp": "2026-05-24T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Надо прочитать Codex MEMORY.md и понять goal этой работы"}],
                },
            },
            {
                "timestamp": "2026-05-24T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "read_mcp_resource",
                    "call_id": "call-mcp",
                    "arguments": json.dumps({"server": "codex_apps", "uri": "memory://session"}),
                },
            },
            {
                "timestamp": "2026-05-24T00:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "create_goal",
                    "call_id": "call-goal",
                    "arguments": json.dumps({"objective": "classify memory and repo context"}),
                },
            },
            {
                "timestamp": "2026-05-24T00:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-memory",
                    "arguments": json.dumps(
                        {
                            "cmd": (
                                "rg -n session /home/dionysus/.codex/memories/MEMORY.md "
                                f"{repo}/AGENTS.md"
                            )
                        }
                    ),
                },
            },
            {
                "timestamp": "2026-05-24T00:00:05Z",
                "type": "response_item",
                "payload": {"type": "function_call_output", "call_id": "call-memory", "output": "Process exited with code 0\nOutput:\nMEMORY.md:1:session\n"},
            },
            {"timestamp": "2026-05-24T00:00:06Z", "type": "event_msg", "payload": {"type": "context_compacted"}},
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "session-acts",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    record = module.resolve_session_record(aoa_root, "session-acts")
    session_dir = Path(record["path"])
    segment_index = json.loads((session_dir / "segments" / "000__initial-to-compaction.index.json").read_text(encoding="utf-8"))
    records = {event["event_id"]: event for event in segment_index["events"]}
    session_index = json.loads((session_dir / "session.index.json").read_text(encoding="utf-8"))
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))

    assert segment_index["session_act_schema_version"] == module.SESSION_ACT_SCHEMA_VERSION
    assert records["000002"]["facets"]["session_act"]["kind"] == "memory_request"
    assert records["000002"]["facets"]["session_act"]["memory_surface"] == "codex_memories"
    assert records["000003"]["facets"]["session_act"]["kind"] == "mcp_resource_read"
    assert records["000003"]["facets"]["session_act"]["tool_namespace"] == "mcp"
    assert records["000004"]["facets"]["session_act"]["kind"] == "goal_created"
    assert records["000005"]["facets"]["session_act"]["kind"] == "memory_read"
    assert records["000005"]["facets"]["session_act"]["memory_surface"] == "codex_memories"
    assert segment_index["by_session_act"]["memory_request"] == ["000002"]
    assert segment_index["by_session_act"]["mcp_resource_read"] == ["000003"]
    assert segment_index["by_session_act"]["goal_created"] == ["000004"]
    assert segment_index["by_session_act"]["memory_read"] == ["000005"]
    assert session_index["session_act_counts"]["memory_read"] == 1
    assert session_index["work_context"]["work_name"] == "aoa-techniques"
    assert session_index["work_context"]["work_family"] == "aoa"
    assert manifest["work_context"]["work_root"] == str(repo)

    index_payload = module.search_index_sessions(aoa_root=aoa_root, target="all")
    assert index_payload["ok"] is True
    search_payload = module.search_sessions(aoa_root=aoa_root, session_act="memory_read", limit=5)
    assert search_payload["ok"] is True
    assert search_payload["results"][0]["session_act"] == "memory_read"
    assert search_payload["results"][0]["session_label"] == record["session_label"]


def test_goal_lifecycle_indexes_search_graph_and_usage_routes(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# aoa-session-memory\n", encoding="utf-8")
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-18T00-00-00-goal-lifecycle.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-18T00:00:00Z", "type": "session_meta", "payload": {"id": "goal-lifecycle", "cwd": str(repo)}},
            {
                "timestamp": "2026-06-18T00:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Close goal lifecycle fully"}]},
            },
            {
                "timestamp": "2026-06-18T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "create_goal",
                    "call_id": "call-create-goal",
                    "arguments": json.dumps({"objective": "ship first class goal lifecycle", "token_budget": 500}),
                },
            },
            {
                "timestamp": "2026-06-18T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "function_call_output", "call_id": "call-create-goal", "output": json.dumps({"goal": {"status": "active", "tokensUsed": 3}})},
            },
            {
                "timestamp": "2026-06-18T00:00:04Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "get_goal", "call_id": "call-get-goal", "arguments": "{}"},
            },
            {
                "timestamp": "2026-06-18T00:00:05Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "update_goal", "call_id": "call-update-goal", "arguments": json.dumps({"status": "active"})},
            },
            {
                "timestamp": "2026-06-18T00:00:06Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "update_goal", "call_id": "call-complete-goal", "arguments": json.dumps({"status": "complete"})},
            },
            {
                "timestamp": "2026-06-18T00:00:07Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-complete-goal",
                    "output": json.dumps({"goal": {"status": "complete", "tokensUsed": 42, "timeUsedSeconds": 12}}),
                },
            },
            {
                "timestamp": "2026-06-18T00:00:08Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Now record blocked external goal"}]},
            },
            {
                "timestamp": "2026-06-18T00:00:09Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "update_goal", "call_id": "call-block-goal", "arguments": json.dumps({"status": "blocked"})},
            },
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "goal-lifecycle",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    record = module.resolve_session_record(aoa_root, "goal-lifecycle")
    session_dir = Path(record["path"])
    segment_index = json.loads((session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8"))
    events = {event["event_id"]: event for event in segment_index["events"]}
    session_index = json.loads((session_dir / module.SESSION_INDEX_JSON).read_text(encoding="utf-8"))

    complete_signals = {f"{signal['layer']}:{signal['key']}" for signal in events["000007"]["facets"]["route_signals"]}
    blocked_signals = {f"{signal['layer']}:{signal['key']}" for signal in events["000010"]["facets"]["route_signals"]}
    assert events["000007"]["facets"]["session_act"]["kind"] == "goal_completed"
    assert events["000010"]["facets"]["session_act"]["kind"] == "goal_blocked"
    assert {"goal:goal_updated", "goal:goal_completed"}.issubset(complete_signals)
    assert {"goal:goal_updated", "goal:goal_blocked"}.issubset(blocked_signals)

    assert session_index["goal_lifecycle_schema_version"] == module.GOAL_LIFECYCLE_SCHEMA_VERSION
    assert session_index["goal_lifecycle_counts"]["total"] == 2
    assert session_index["goal_event_counts"]["goal_created"] == 1
    assert session_index["goal_event_counts"]["goal_inspected"] == 1
    assert session_index["goal_event_counts"]["goal_updated"] == 1
    assert session_index["goal_event_counts"]["goal_completed"] == 1
    assert session_index["goal_event_counts"]["goal_blocked"] == 1
    first, second = session_index["goal_lifecycles"]
    assert first["goal_id"] == "goal-0001"
    assert first["status"] == "complete"
    assert first["objective"] == "ship first class goal lifecycle"
    assert first["created_ref"]["raw_ref"] == "raw:line:3"
    assert first["completed_ref"]["raw_ref"] == "raw:line:7"
    assert first["task_episode_ids"] == ["task-0001"]
    assert "missing_create" not in first["ambiguity_flags"]
    assert second["goal_id"] == "goal-0002"
    assert second["status"] == "blocked"
    assert "missing_create" in second["ambiguity_flags"]
    assert second["blocked_ref"]["raw_ref"] == "raw:line:10"
    assert second["task_episode_ids"] == ["task-0002"]
    assert session_index["route_signal_counts"]["goal"]["goal_completed"] == 1
    assert session_index["route_signal_counts"]["goal"]["goal_blocked"] == 1

    lifecycle_route = module.goal_lifecycle_route_search(aoa_root=aoa_root, target="latest", event_kind="goal_completed", limit=2)
    assert lifecycle_route["ok"] is True
    assert lifecycle_route["results"][0]["goal_id"] == "goal-0001"
    assert lifecycle_route["results"][0]["refs"]["completed"]["raw_ref"] == "raw:line:7"

    module.build_agent_atlas(aoa_root=aoa_root, target="all")
    by_goal = json.loads((aoa_root / "maps" / "by-goal" / "index.json").read_text(encoding="utf-8"))
    assert {"goal_completed", "goal_blocked"}.issubset({entry["route_key"] for entry in by_goal["entries"]})

    search_index = module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=True)
    assert search_index["ok"] is True
    lifecycle_search = module.search_sessions(aoa_root=aoa_root, doc_type="goal_lifecycle", route_signal="goal:goal_completed", limit=5)
    assert lifecycle_search["ok"] is True
    assert lifecycle_search["results"][0]["doc_type"] == "goal_lifecycle"
    event_search = module.search_sessions(aoa_root=aoa_root, doc_type="event", route_signal="goal:goal_completed", limit=5)
    assert event_search["ok"] is True
    assert event_search["results"][0]["session_act"] == "goal_completed"
    session_act_search = module.search_sessions(aoa_root=aoa_root, doc_type="event", session_act="goal_blocked", limit=5)
    assert session_act_search["ok"] is True
    assert session_act_search["results"][0]["session_act"] == "goal_blocked"

    graph = module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=True, export_sidecar=False)
    assert graph["ok"] is True
    node_ids = {node["id"] for node in graph["nodes"]}
    assert module.graph_route_node_id("goal", "goal_completed") in node_ids
    assert module.graph_goal_lifecycle_node_id("goal-lifecycle", "goal-0001") in node_ids
    assert any(edge["type"] == "goal_lifecycle_has_event" for edge in graph["edges"])
    timeline = module.graph_timeline(aoa_root=aoa_root, anchor="goal_completed", kind="goal", limit=10)
    assert timeline["ok"] is True
    assert any(event.get("session_act") == "goal_completed" for event in timeline["events"])

    usage_audit = module.entity_usage_audit(aoa_root=aoa_root, anchor="goal_completed", kind="goal", limit=5, per_route_limit=5)
    assert usage_audit["ok"] is True
    assert usage_audit["usage_event_count"] >= 1
    assert usage_audit["quality"]["direct_usage_present"] is True
    assert usage_audit["usage_events"][0]["session_act"] == "goal_completed"


def test_entity_registry_autodiscovers_skills_mcp_and_links_search_graph(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    codex_home = tmp_path / ".codex"
    skill_dir = codex_home / "skills" / "aoa-live-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: aoa-live-skill\ndescription: Live fixture skill.\n---\n# aoa-live-skill\n",
        encoding="utf-8",
    )
    codex_home.mkdir(exist_ok=True)
    (codex_home / "config.toml").write_text(
        "[mcp_servers.aoa-kag]\ncommand = \"python3\"\nargs = [\"-m\", \"aoa_kag\"]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    transcript = tmp_path / "rollout-2026-06-18T00-00-00-entity-registry.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-18T00:00:00Z", "type": "session_meta", "payload": {"id": "entity-registry-session", "cwd": str(workspace)}},
            {"timestamp": "2026-06-18T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Use skill: aoa-live-skill and mcp/services/aoa-kag-mcp for lookup."}]}},
            {"timestamp": "2026-06-18T00:00:02Z", "type": "response_item", "payload": {"type": "function_call", "name": "mcp__aoa_kag_mcp__lookup", "call_id": "call-1"}},
            {"timestamp": "2026-06-18T00:00:03Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-1", "output": "lookup ok"}},
            {"timestamp": "2026-06-18T00:00:04Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "aoa-live-skill and aoa-kag-mcp checked."}]}},
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "entity-registry-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    indexed = module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=True)
    registry = json.loads((aoa_root / module.ENTITY_REGISTRY_PATH).read_text(encoding="utf-8"))
    entries = {(entry["kind"], entry["canonical_key"]): entry for entry in registry["entries"]}

    assert indexed["ok"] is True
    assert indexed["entity_registry_document_count"] > 0
    assert entries[("skill", "aoa_live_skill")]["status"] == "active"
    assert entries[("mcp_service", "aoa_kag_mcp")]["status"] == "active"
    assert entries[("mcp_tool", "mcp_aoa_kag_mcp_lookup")]["status"] == "observed"

    skill_candidates = module.trace_route_candidates("aoa-live-skill", kind="skill")
    mcp_candidates = module.trace_route_candidates("aoa-kag-mcp", kind="mcp")
    assert any(candidate["route_signal"] == "skill:aoa_live_skill" for candidate in skill_candidates)
    assert any(candidate["route_signal"] == "mcp:aoa_kag_mcp" for candidate in mcp_candidates)

    registry_search = module.search_sessions(aoa_root=aoa_root, query="aoa-live-skill", doc_type="entity_registry", limit=5)
    assert registry_search["ok"] is True
    assert registry_search["results"][0]["doc_type"] == "entity_registry"

    graph = module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=True, export_sidecar=False)
    node_types = {node["type"] for node in graph["nodes"]}
    edge_types = {edge["type"] for edge in graph["edges"]}
    assert "entity_registry" in node_types
    assert "session_has_registered_entity" in edge_types
    assert "event_mentions_registered_entity" in edge_types
    neighborhood = module.graph_neighborhood(aoa_root=aoa_root, anchor="aoa-live-skill", kind="skill", depth=1, limit=20)
    assert neighborhood["ok"] is True
    assert any(node.get("type") == "entity_registry" for node in neighborhood["nodes"])

    lookup = module.entity_registry_lookup(aoa_root=aoa_root, anchor="aoa-kag-mcp", kind="mcp")
    assert lookup["agent_route_packet"]["registered"] is True
    assert lookup["entries"][0]["status"] == "active"

    unknown_lookup = module.entity_registry_lookup(aoa_root=aoa_root, anchor="aoa-never-seen-mcp", kind="mcp")
    assert unknown_lookup["agent_route_packet"]["registered"] is False
    assert unknown_lookup["agent_route_packet"]["status"] == "unknown"
    assert unknown_lookup["entries"][0]["kind"] == "mcp_service"

    filtered = module.build_entity_registry(
        aoa_root=aoa_root,
        write=True,
        kind="skill",
        query="aoa-live-skill",
        limit=1,
        route_terms_db_path=module.search_db_path(aoa_root),
    )
    filtered_snapshot = json.loads((aoa_root / module.ENTITY_REGISTRY_PATH).read_text(encoding="utf-8"))
    assert filtered["entity_count"] == 1
    assert filtered_snapshot["kind"] == "all"
    assert filtered_snapshot["entity_count"] >= 3
    assert filtered_snapshot["counts_by_kind"]["mcp_service"] >= 1
    assert filtered_snapshot["counts_by_kind"]["mcp_tool"] >= 1

    moved_codex_home = tmp_path / ".codex-moved"
    moved_codex_home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(moved_codex_home))
    stale_registry = module.build_entity_registry(
        aoa_root=aoa_root,
        write=True,
        route_terms_db_path=module.search_db_path(aoa_root),
    )
    stale_entries = {(entry["kind"], entry["canonical_key"]): entry for entry in stale_registry["entries"]}
    assert stale_entries[("skill", "aoa_live_skill")]["status"] == "stale"
    assert stale_entries[("mcp_service", "aoa_kag_mcp")]["status"] == "stale"

    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    (skill_dir / "SKILL.md").unlink()
    skill_dir.rmdir()
    (codex_home / "config.toml").write_text("# aoa-kag MCP removed\n", encoding="utf-8")
    removed_registry = module.build_entity_registry(
        aoa_root=aoa_root,
        write=True,
        route_terms_db_path=module.search_db_path(aoa_root),
    )
    removed_entries = {(entry["kind"], entry["canonical_key"]): entry for entry in removed_registry["entries"]}
    assert removed_entries[("skill", "aoa_live_skill")]["status"] == "removed"
    assert removed_entries[("mcp_service", "aoa_kag_mcp")]["status"] == "removed"
    assert removed_registry["counts_by_status"]["removed"] >= 2

    maintenance = module.entity_registry_maintenance_status(aoa_root)
    assert maintenance["needs_maintenance"] is False

    time.sleep(0.01)
    newer_skill_dir = codex_home / "skills" / "aoa-newer-skill"
    newer_skill_dir.mkdir(parents=True)
    (newer_skill_dir / "SKILL.md").write_text("---\nname: aoa-newer-skill\n---\n", encoding="utf-8")
    newer_maintenance = module.entity_registry_maintenance_status(aoa_root)
    assert newer_maintenance["needs_maintenance"] is True
    assert "source_newer_than_entity_registry" in newer_maintenance["diagnostics"]

    maintenance_plan = module.maintain_indexes(aoa_root=aoa_root, target="all", repair_graph=False, max_raw_bytes=1)
    planned_refresh = next(action for action in maintenance_plan["actions"] if action["id"] == "refresh_entity_registry")
    assert planned_refresh["needed"] is True
    assert "search-index" in planned_refresh["command"]
    assert "--no-rebuild" in planned_refresh["command"]
    assert "entity-registry" not in planned_refresh["command"]

    applied_maintenance = module.maintain_indexes(
        aoa_root=aoa_root,
        target="all",
        apply=True,
        repair_graph=False,
        max_raw_bytes=1,
    )
    assert applied_maintenance["ok"] is True
    applied_refresh = next(action for action in applied_maintenance["actions"] if action["id"] == "refresh_entity_registry")
    assert applied_refresh["status"] == "applied"
    refreshed_search = applied_refresh["result"]
    refreshed_registry = json.loads((aoa_root / module.ENTITY_REGISTRY_PATH).read_text(encoding="utf-8"))
    assert refreshed_search["ok"] is True
    assert refreshed_search["entity_registry_document_count"] == refreshed_registry["entity_count"]
    assert refreshed_search["removed_entity_registry_document_count"] >= filtered_snapshot["entity_count"]
    refreshed_maintenance = module.entity_registry_maintenance_status(aoa_root)
    assert refreshed_maintenance["needs_maintenance"] is False
    conn = sqlite3.connect(str(module.search_db_path(aoa_root)))
    registry_doc_count = conn.execute("SELECT COUNT(*) FROM documents WHERE doc_type = 'entity_registry'").fetchone()[0]
    conn.close()
    assert registry_doc_count == refreshed_registry["entity_count"]
    newer_search = module.search_sessions(aoa_root=aoa_root, query="aoa-newer-skill", doc_type="entity_registry", limit=5)
    assert newer_search["ok"] is True
    assert newer_search["results"][0]["doc_type"] == "entity_registry"


def test_auto_maintenance_refreshes_stale_entity_registry_search_docs(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    codex_home = tmp_path / ".codex"
    skill_dir = codex_home / "skills" / "aoa-auto-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: aoa-auto-skill\ndescription: Auto fixture skill.\n---\n# aoa-auto-skill\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    transcript = tmp_path / "rollout-2026-06-18T00-00-00-auto-entity-registry.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-18T00:00:00Z", "type": "session_meta", "payload": {"id": "auto-entity-registry-session", "cwd": str(workspace)}},
            {"timestamp": "2026-06-18T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Use skill: aoa-auto-skill."}]}},
            {"timestamp": "2026-06-18T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "aoa-auto-skill checked."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "auto-entity-registry-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    indexed = module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=True)
    assert indexed["ok"] is True
    atlas = module.build_agent_atlas(aoa_root=aoa_root, target="all", clean=True)
    assert atlas["ok"] is True

    time.sleep(0.01)
    newer_skill_dir = codex_home / "skills" / "aoa-auto-newer-skill"
    newer_skill_dir.mkdir(parents=True)
    (newer_skill_dir / "SKILL.md").write_text("---\nname: aoa-auto-newer-skill\n---\n", encoding="utf-8")

    freshness = module.route_cache_freshness_gates(aoa_root=aoa_root, target="all")
    assert freshness["ok"] is False
    assert freshness["needs_index_maintenance"] is True
    assert freshness["entity_registry"]["needs_maintenance"] is True
    assert "entity_registry_missing_or_stale" in freshness["diagnostics"]

    status = module.session_memory_maintenance_status(workspace_root=workspace, aoa_root=aoa_root, include_timers=False)
    assert status["recommendation"] == "run_maintenance"
    assert status["next_actions"][0]["id"] == "entity_registry_refresh"
    assert "search-index" in status["next_actions"][0]["command"]
    assert "--no-rebuild" in status["next_actions"][0]["command"]

    payload = module.auto_maintenance(
        workspace_root=workspace,
        aoa_root=aoa_root,
        profile="catchup",
        apply=True,
        max_raw_bytes=1,
        budget_seconds=30,
    )
    assert payload["ok"] is True
    refresh_action = next(action for action in payload["maintenance"]["actions"] if action["id"] == "refresh_entity_registry")
    assert refresh_action["status"] == "applied"

    refreshed_registry = json.loads((aoa_root / module.ENTITY_REGISTRY_PATH).read_text(encoding="utf-8"))
    conn = sqlite3.connect(str(module.search_db_path(aoa_root)))
    registry_doc_count = conn.execute("SELECT COUNT(*) FROM documents WHERE doc_type = 'entity_registry'").fetchone()[0]
    conn.close()
    assert registry_doc_count == refreshed_registry["entity_count"]

    lookup = module.entity_registry_lookup(aoa_root=aoa_root, anchor="aoa-auto-newer-skill", kind="skill")
    assert lookup["agent_route_packet"]["registered"] is True
    assert lookup["entries"][0]["status"] == "active"
    search = module.search_sessions(aoa_root=aoa_root, query="aoa-auto-newer-skill", doc_type="entity_registry", limit=5)
    assert search["ok"] is True
    assert search["results"][0]["doc_type"] == "entity_registry"


def test_performance_baseline_measures_core_routes_and_refresh_paths(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    codex_home = tmp_path / ".codex"
    codex_home.mkdir(parents=True)
    (codex_home / "config.toml").write_text(
        "[mcp_servers.aoa-kag]\ncommand = \"python3\"\nargs = [\"-m\", \"aoa_kag\"]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    transcript = tmp_path / "rollout-2026-06-18T00-00-00-performance-baseline.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-18T00:00:00Z", "type": "session_meta", "payload": {"id": "performance-baseline-session", "cwd": str(workspace)}},
            {"timestamp": "2026-06-18T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Use mcp/services/aoa-kag-mcp for lookup."}]}},
            {"timestamp": "2026-06-18T00:00:02Z", "type": "response_item", "payload": {"type": "function_call", "name": "mcp__aoa_kag_mcp__lookup", "call_id": "call-1"}},
            {"timestamp": "2026-06-18T00:00:03Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-1", "output": "lookup ok"}},
            {"timestamp": "2026-06-18T00:00:04Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "aoa-kag-mcp lookup completed."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "performance-baseline-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    assert module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=True)["ok"] is True
    assert module.build_agent_atlas(aoa_root=aoa_root, target="all", clean=True)["ok"] is True
    assert module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)["ok"] is True

    planned = module.performance_baseline(
        aoa_root=aoa_root,
        anchor="aoa-kag-mcp",
        kind="mcp",
        limit=2,
        per_route_limit=3,
        apply_refresh=False,
    )
    planned_steps = {step["id"]: step for step in planned["steps"]}
    assert planned["ok"] is True
    assert planned["mutates"] is False
    assert planned_steps["narrow_entity_registry_refresh"]["status"] == "skipped"
    assert planned_steps["narrow_search_index_refresh"]["status"] == "skipped"

    applied = module.performance_baseline(
        aoa_root=aoa_root,
        anchor="aoa-kag-mcp",
        kind="mcp",
        limit=2,
        per_route_limit=3,
        search_target="latest",
        max_raw_bytes=1,
        apply_refresh=True,
        refresh_budget_seconds=30,
        write_report=True,
    )
    steps = {step["id"]: step for step in applied["steps"]}
    assert applied["artifact_type"] == "session_memory_performance_baseline"
    assert applied["ok"] is True
    assert applied["mutates"] is True
    assert Path(applied["report_json"]).exists()
    assert Path(applied["report_markdown"]).exists()
    assert set(steps) == {
        "registry_lookup",
        "usage_audit",
        "usage_neighborhood",
        "graphrag_packet",
        "narrow_entity_registry_refresh",
        "narrow_search_index_refresh",
    }
    assert steps["registry_lookup"]["summary"]["registered"] is True
    assert steps["narrow_entity_registry_refresh"]["summary"]["selected_count"] == 0
    assert steps["narrow_entity_registry_refresh"]["summary"]["processed_count"] == 0
    assert steps["narrow_search_index_refresh"]["summary"]["selected_count"] == 1
    assert steps["narrow_search_index_refresh"]["summary"]["processed_count"] == 1
    assert applied["diagnosis"]["refresh_path"]["entity_registry_refresh_reindexes_session_docs"] is False
    assert applied["diagnosis"]["refresh_path"]["search_index_refresh_reindexes_session_docs"] is True


def test_entity_usage_audit_fetches_beyond_presentation_limit_for_direct_usage(tmp_path: Path, monkeypatch: Any) -> None:
    result_hits = [
        {
            "doc_id": f"event:session:001:{index:06d}",
            "event_type": "COMMAND_OUTPUT",
            "conversation_act": "tool_output_success",
            "session_act": "memory_observation",
            "title": f"Hook result {index}",
            "route_signals": "hook_health:userpromptsubmit",
            "refs": {"raw": f"raw:line:{index}", "segment": "001.md", "session": "session.manifest.json"},
        }
        for index in range(1, 7)
    ]
    usage_hit = {
        "doc_id": "event:session:001:000007",
        "event_type": "FILE_READ",
        "conversation_act": "command_inspection_request",
        "session_act": "memory_read",
        "title": "Hook receipt search",
        "route_signals": "hook:userpromptsubmit|hook_health:userpromptsubmit",
        "refs": {"raw": "raw:line:7", "segment": "001.md", "session": "session.manifest.json"},
    }
    candidate_hits = [*result_hits, usage_hit]
    called_limits: list[int] = []

    def fake_search_sessions(**kwargs: Any) -> dict[str, Any]:
        called_limits.append(int(kwargs.get("limit") or 0))
        limit = int(kwargs.get("limit") or 0)
        return {"ok": True, "result_count": min(limit, len(candidate_hits)), "results": candidate_hits[:limit], "diagnostics": []}

    def fake_provider_status(**_kwargs: Any) -> dict[str, Any]:
        return {
            "providers": {
                "portable_sqlite": {
                    "has_route_index": True,
                    "has_route_terms": True,
                    "route_index_count": 1,
                    "route_term_count": 1,
                }
            }
        }

    monkeypatch.setattr(module, "search_sessions", fake_search_sessions)
    monkeypatch.setattr(module, "search_provider_status", fake_provider_status)

    audit = module.entity_usage_audit(
        aoa_root=tmp_path / ".aoa",
        anchor="userpromptsubmit",
        kind="hook",
        limit=3,
        per_route_limit=3,
    )

    assert audit["ok"] is True
    assert max(called_limits) >= 12
    assert audit["quality"]["requested_per_route_limit"] == 3
    assert audit["quality"]["route_fetch_limit"] >= 12
    assert audit["event_count"] == 3
    assert audit["usage_event_count"] == 1
    assert audit["usage_events"][0]["doc_id"] == "event:session:001:000007"


def test_search_index_incremental_replaces_selected_session_documents(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-techniques"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-24T00-00-00-incremental-search.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-24T00:00:00Z", "type": "session_meta", "payload": {"id": "incremental-search", "cwd": str(repo)}},
            {"timestamp": "2026-05-24T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Update only this searchable session"}]}},
            {"timestamp": "2026-05-24T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Incremental search path ready."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "incremental-search",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    record = module.resolve_session_record(aoa_root, "incremental-search")
    full = module.search_index_sessions(aoa_root=aoa_root, target="all")
    assert full["ok"] is True

    conn = sqlite3.connect(str(module.search_db_path(aoa_root)))
    cursor = conn.execute(
        "INSERT INTO documents(id, doc_type, session_label, title, body, payload_json) VALUES (?, ?, ?, ?, ?, ?)",
        ("obsolete-doc", "event", record["session_label"], "obsolete", "obsolete stale body", "{}"),
    )
    rowid = cursor.lastrowid
    conn.execute(
        "INSERT OR IGNORE INTO route_terms(layer, key, route_signal) VALUES (?, ?, ?)",
        ("entity", "obsolete", "entity:obsolete"),
    )
    route_id = conn.execute("SELECT id FROM route_terms WHERE route_signal = ?", ("entity:obsolete",)).fetchone()[0]
    conn.execute(
        "INSERT INTO document_routes(doc_rowid, route_id) VALUES (?, ?)",
        (rowid, route_id),
    )
    conn.execute(
        "INSERT INTO documents_fts(rowid, title, body, session_label, session_title) VALUES (?, ?, ?, ?, ?)",
        (rowid, "obsolete", "obsolete stale body", record["session_label"], ""),
    )
    before_count = conn.execute("SELECT COUNT(*) FROM documents WHERE session_label = ?", (record["session_label"],)).fetchone()[0]
    conn.commit()
    conn.close()

    incremental = module.search_index_sessions(aoa_root=aoa_root, target=record["session_label"], rebuild=False)
    assert incremental["ok"] is True
    assert incremental["removed_document_count"] == before_count

    conn = sqlite3.connect(str(module.search_db_path(aoa_root)))
    assert conn.execute("SELECT COUNT(*) FROM documents WHERE id = 'obsolete-doc'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM documents_fts WHERE rowid = ?", (rowid,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM document_routes WHERE doc_rowid = ?", (rowid,)).fetchone()[0] == 0
    conn.close()


def test_atlas_no_clean_updates_selected_session_without_losing_other_entries(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-techniques"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    first_transcript = tmp_path / "rollout-2026-06-01T00-00-00-alpha-atlas.jsonl"
    second_transcript = tmp_path / "rollout-2026-06-01T00-05-00-beta-atlas.jsonl"
    write_jsonl(
        first_transcript,
        [
            {"timestamp": "2026-06-01T00:00:00Z", "type": "session_meta", "payload": {"id": "atlas-alpha", "cwd": str(repo)}},
            {"timestamp": "2026-06-01T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Alpha atlas incremental session"}]}},
        ],
    )
    write_jsonl(
        second_transcript,
        [
            {"timestamp": "2026-06-01T00:05:00Z", "type": "session_meta", "payload": {"id": "atlas-beta", "cwd": str(repo)}},
            {"timestamp": "2026-06-01T00:05:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Beta atlas preserved session"}]}},
        ],
    )
    for session_id, transcript in (("atlas-alpha", first_transcript), ("atlas-beta", second_transcript)):
        module.handle_hook_event(
            "Stop",
            {
                "session_id": session_id,
                "transcript_path": str(transcript),
                "cwd": str(repo),
                "hook_event_name": "Stop",
            },
            workspace_root=workspace,
            aoa_root=aoa_root,
        )

    alpha = module.resolve_session_record(aoa_root, "atlas-alpha")
    beta = module.resolve_session_record(aoa_root, "atlas-beta")
    full = module.build_agent_atlas(aoa_root=aoa_root, target="all", clean=True)
    assert full["ok"] is True
    before_count = full["entry_count"]
    by_time_before = module.read_json(aoa_root / "maps" / "by-time" / "index.json", {})
    assert any(entry.get("session") == beta["session_label"] for entry in by_time_before["entries"])

    incremental = module.build_agent_atlas(aoa_root=aoa_root, target="all", clean=False, selected_records=[alpha])

    assert incremental["ok"] is True
    assert incremental["selected_count"] == 1
    assert incremental["entry_count"] == before_count
    by_time_after = module.read_json(aoa_root / "maps" / "by-time" / "index.json", {})
    assert any(entry.get("session") == alpha["session_label"] for entry in by_time_after["entries"])
    assert any(entry.get("session") == beta["session_label"] for entry in by_time_after["entries"])


def test_reindex_backfills_work_context_for_existing_archives(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-techniques"
    repo.mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# aoa-techniques\n", encoding="utf-8")
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-24T00-00-00-work-context-reindex.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-24T00:00:00Z", "type": "session_meta", "payload": {"id": "work-context-reindex", "cwd": str(repo)}},
            {
                "timestamp": "2026-05-24T00:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Проверь repo routing для aoa-techniques"}]},
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "work-context-reindex",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    record = module.resolve_session_record(aoa_root, "work-context-reindex")
    session_dir = Path(record["path"])
    manifest_path = session_dir / "session.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.pop("work_context", None)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8")

    reindexed = module.reindex_session_from_raw(aoa_root, record)
    assert reindexed["status"] == "reindexed"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    session_index = json.loads((session_dir / "session.index.json").read_text(encoding="utf-8"))
    assert manifest["work_context"]["work_name"] == "aoa-techniques"
    assert manifest["work_context"]["work_family"] == "aoa"
    assert session_index["work_context"]["work_name"] == "aoa-techniques"

    atlas = module.build_agent_atlas(aoa_root=aoa_root, target="all")
    assert atlas["ok"] is True
    work_entries = sorted((aoa_root / "maps" / "by-work-context" / "entries").glob("aoa_techniques__*.json"))
    family_entries = sorted((aoa_root / "maps" / "by-repo-family" / "entries").glob("aoa__*.json"))
    assert work_entries
    assert family_entries


def test_route_signals_cover_operational_layers_and_search(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# route\n", encoding="utf-8")
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-24T00-00-00-route-signals.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-05-24T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "route-signals", "cwd": str(repo), "model": "gpt-5"},
            },
            {
                "timestamp": "2026-05-24T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Сначала погрузись. Сейчас только анализ, не трогай файлы, не коммить, "
                                "без внешних подключений. Отвечай по-русски, preserve before distill, "
                                "сначала AGENTS/DESIGN."
                            ),
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-05-24T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-read",
                    "arguments": json.dumps({"cmd": "sed -n '1,120p' AGENTS.md DESIGN.md"}),
                },
            },
            {
                "timestamp": "2026-05-24T00:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "apply_patch",
                    "call_id": "call-patch",
                    "arguments": "{}",
                },
            },
            {
                "timestamp": "2026-05-24T00:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-test",
                    "arguments": json.dumps({"cmd": "PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/test_session_memory.py"}),
                },
            },
            {
                "timestamp": "2026-05-24T00:00:05Z",
                "type": "response_item",
                "payload": {"type": "function_call_output", "call_id": "call-test", "output": "Process exited with code 0\nOutput:\n3 passed\n"},
            },
            {
                "timestamp": "2026-05-24T00:00:06Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-fail",
                    "output": "Process exited with code 1\nOutput:\npermission denied: raw_unavailable timeout\n",
                },
            },
            {
                "timestamp": "2026-05-24T00:00:07Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Готово: tests green, bundle exported, not pushed. Осталось открыть PR."}],
                },
            },
            {
                "timestamp": "2026-05-24T00:00:08Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Действуй: чини полноценно и делай landing."}],
                },
            },
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "route-signals",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    record = module.resolve_session_record(aoa_root, "route-signals")
    session_dir = Path(record["path"])
    segment_index = json.loads((session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8"))
    records = {event["event_id"]: event for event in segment_index["events"]}
    session_index = json.loads((session_dir / "session.index.json").read_text(encoding="utf-8"))

    assert segment_index["route_signal_schema_version"] == module.ROUTE_SIGNAL_SCHEMA_VERSION
    assert segment_index["route_signal_classifier_version"] == module.ROUTE_SIGNAL_CLASSIFIER_VERSION
    assert session_index["route_signal_classifier_version"] == module.ROUTE_SIGNAL_CLASSIFIER_VERSION
    prompt_signals = {
        f"{signal['layer']}:{signal['key']}"
        for signal in records["000002"]["facets"]["route_signals"]
    }
    assert "scope_contract:analysis_only" in prompt_signals
    assert "scope_contract:no_commit" in prompt_signals
    assert "scope_contract:no_external_connectors" in prompt_signals
    assert "operator_preference:russian_language" in prompt_signals
    assert "operator_preference:preserve_before_distill" in prompt_signals
    action_signals = {
        f"{signal['layer']}:{signal['key']}"
        for signal in records["000009"]["facets"]["route_signals"]
    }
    assert "scope_contract:implementation_requested" in action_signals
    assert "scope_contract:repair_requested" in action_signals
    assert "scope_contract:landing_requested" in action_signals
    assert segment_index["by_route_layer"]["scope_contract"]["analysis_only"] == ["000002"]
    assert segment_index["by_route_layer"]["scope_contract"]["implementation_requested"] == ["000009"]
    assert segment_index["by_route_layer"]["scope_contract"]["repair_requested"] == ["000009"]
    assert segment_index["by_route_layer"]["scope_contract"]["landing_requested"] == ["000009"]
    assert segment_index["by_route_layer"]["operator_preference"]["russian_language"] == ["000002"]
    assert segment_index["by_route_layer"]["verification_state"]["green_proof"] == ["000006"]
    assert "permission" in segment_index["by_route_layer"]["failure_mode"]
    assert module.env_entity_candidate("OPENAI_API_KEY") is True
    assert module.env_entity_candidate("ADD") is False
    assert module.env_entity_candidate("CREATE") is False
    assert session_index["route_signal_counts"]["scope_contract"]["analysis_only"] == 1
    assert session_index["route_signal_counts"]["scope_contract"]["implementation_requested"] == 1
    assert session_index["route_signal_counts"]["scope_contract"]["repair_requested"] == 1
    assert session_index["route_signal_counts"]["scope_contract"]["landing_requested"] == 1
    assert session_index["route_signal_counts"]["delivery_state"]["tests_green"] >= 1
    assert session_index["route_signal_counts"]["runtime_environment"]["model"] == 1

    index_payload = module.search_index_sessions(aoa_root=aoa_root, target="all")
    assert index_payload["ok"] is True
    conn = sqlite3.connect(str(module.search_db_path(aoa_root)))
    assert conn.execute("SELECT COUNT(*) FROM document_routes").fetchone()[0] > 0
    assert conn.execute(
        """
        SELECT COUNT(*)
        FROM document_routes JOIN route_terms ON route_terms.id = document_routes.route_id
        WHERE route_terms.layer = ? AND route_terms.key = ?
        """,
        ("scope_contract", "analysis_only"),
    ).fetchone()[0] > 0
    conn.close()
    search_payload = module.search_sessions(aoa_root=aoa_root, route_layer="scope_contract", route_signal="scope_contract:analysis_only")
    assert search_payload["ok"] is True
    assert search_payload["results"][0]["route_signals"]
    text_route_payload = module.search_sessions(
        aoa_root=aoa_root,
        query="preserve",
        route_layer="scope_contract",
        route_signal="scope_contract:analysis_only",
        explain=True,
    )
    assert text_route_payload["ok"] is True
    assert text_route_payload["results"]
    provider = module.search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite", freshness_mode="deep")
    assert provider["providers"]["portable_sqlite"]["route_term_count"] > 0


def test_graph_sidecar_and_graphrag_packets_preserve_evidence_refs(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# graph route\n", encoding="utf-8")
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-26T00-00-00-graph-rag.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-05-26T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "graph-rag", "cwd": str(repo), "model": "gpt-5"},
            },
            {
                "timestamp": "2026-05-26T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Надо отладить MCP aoa-session-memory-mcp и tool exec_command через GraphRAG evidence refs.",
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-05-26T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-graph",
                    "arguments": json.dumps({"cmd": "python3 scripts/aoa_session_memory.py graph-build --write"}),
                },
            },
            {
                "timestamp": "2026-05-26T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "function_call_output", "call_id": "call-graph", "output": "Process exited with code 0\nOutput:\ngraph built\n"},
            },
            {
                "timestamp": "2026-05-26T00:00:03.100Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "aoa_decisions_search",
                    "call_id": "call-decision-search",
                    "arguments": json.dumps({"query": "aoa-decision skill MCP usage"}),
                },
            },
            {
                "timestamp": "2026-05-26T00:00:03.150Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-decision-search",
                    "output": json.dumps({"ok": True, "refs": ["docs/decisions/README.md"]}),
                },
            },
            {
                "timestamp": "2026-05-26T00:00:03.200Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "spawn_agent",
                    "call_id": "call-unrelated-tool",
                    "arguments": json.dumps({"role": "reviewer"}),
                },
            },
            {
                "timestamp": "2026-05-26T00:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "GraphRAG packet keeps raw_ref and segment_ref."}],
                },
            },
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "graph-rag",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    search_index = module.search_index_sessions(aoa_root=aoa_root, target="all")
    graph = module.build_session_graph(aoa_root=aoa_root, target="all", write=True)
    streaming_graph = module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)
    atlas = module.build_agent_atlas(aoa_root=aoa_root, target="all", clean=True)
    conn = sqlite3.connect(str(module.search_db_path(aoa_root)))
    conn.execute("UPDATE meta SET value = ? WHERE key = ?", ("2999-01-01T00:00:00Z", "generated_at"))
    conn.commit()
    conn.close()

    assert search_index["ok"] is True
    assert graph["ok"] is True
    assert streaming_graph["ok"] is True
    assert streaming_graph["builder"] == "sqlite_graph_store"
    assert streaming_graph["nodes_sample"]
    assert streaming_graph["edges_sample"]
    assert "nodes" not in streaming_graph
    assert "edges" not in streaming_graph
    assert atlas["ok"] is True
    assert (aoa_root / "graph" / "nodes.jsonl").exists()
    assert (aoa_root / "graph" / "edges.jsonl").exists()
    assert (aoa_root / "graph" / "graph.sqlite3").exists()
    assert json.loads((aoa_root / "graph" / "index.json").read_text(encoding="utf-8"))["builder"] == "sqlite_graph_store"
    assert graph["node_type_counts"]["event"] >= 1
    assert graph["node_type_counts"]["raw_ref"] >= 1
    conn = sqlite3.connect(str(aoa_root / "graph" / "graph.sqlite3"))
    aggregate_edge = json.loads(conn.execute("SELECT payload_json FROM edges LIMIT 1").fetchone()[0])
    aggregate_node = json.loads(conn.execute("SELECT payload_json FROM nodes LIMIT 1").fetchone()[0])
    node_contrib_row = conn.execute("SELECT payload_json FROM node_contribs WHERE payload_json LIKE ? LIMIT 1", ('%"raw"%',)).fetchone()
    edge_contrib_row = conn.execute("SELECT payload_json FROM edge_contribs WHERE payload_json LIKE ? LIMIT 1", ('%"raw"%',)).fetchone()
    conn.close()
    assert aggregate_edge["aggregate_payload_mode"] == module.GRAPH_STORE_AGGREGATE_PAYLOAD_MODE
    assert aggregate_edge["evidence_refs_compacted"] is True
    assert "evidence_refs" not in aggregate_edge
    assert "refs" not in aggregate_edge
    assert aggregate_node["aggregate_payload_mode"] == module.GRAPH_STORE_AGGREGATE_PAYLOAD_MODE
    assert "refs" not in aggregate_node
    assert node_contrib_row is not None
    assert edge_contrib_row is not None
    node_contrib = json.loads(str(node_contrib_row[0]))
    edge_contrib = json.loads(str(edge_contrib_row[0]))
    for contrib in (node_contrib, edge_contrib):
        assert contrib["contrib_payload_mode"] == module.GRAPH_STORE_CONTRIB_PAYLOAD_MODE
        assert "session_index" not in contrib.get("refs", {})
        assert "segment_index" not in contrib.get("refs", {})
        assert contrib["evidence_refs"]
        compact_refs = contrib["evidence_refs"][0]["refs"]
        assert "session_index" not in compact_refs
        assert "segment_index" not in compact_refs
        assert compact_refs["session"].startswith("sessions/")
        assert compact_refs.get("raw") or compact_refs.get("segment")

    neighborhood = module.graph_neighborhood(aoa_root=aoa_root, anchor="aoa-session-memory-mcp", kind="mcp", depth=2)
    timeline = module.graph_timeline(aoa_root=aoa_root, anchor="aoa-session-memory-mcp", kind="mcp")
    config_alias_timeline = module.graph_timeline(aoa_root=aoa_root, anchor="mcp_servers.aoa_session_memory", kind="mcp")
    exact_tool_timeline = module.graph_timeline(aoa_root=aoa_root, anchor="aoa_decisions_search", kind="tool")
    usage_audit = module.entity_usage_audit(
        aoa_root=aoa_root,
        anchor="aoa-decisions-mcp",
        kind="mcp",
        limit=8,
        per_route_limit=8,
        consequence_window=4,
    )
    usage_neighborhood = module.entity_usage_neighborhood(
        aoa_root=aoa_root,
        anchor="aoa-decisions-mcp",
        kind="mcp",
        limit=2,
        per_route_limit=8,
        before=1,
        after=4,
        raw_preview_chars=500,
    )
    narrow_usage_audit = module.entity_usage_audit(
        aoa_root=aoa_root,
        anchor="aoa-decisions-mcp",
        kind="mcp",
        limit=1,
        per_route_limit=8,
        consequence_window=4,
    )
    narrow_usage_neighborhood = module.entity_usage_neighborhood(
        aoa_root=aoa_root,
        anchor="aoa-decisions-mcp",
        kind="mcp",
        limit=1,
        per_route_limit=1,
        before=1,
        after=4,
        raw_preview_chars=500,
    )
    scenario_audit = module.entity_usage_scenario_audit(
        aoa_root=aoa_root,
        sample_size=2,
        seed="fixture-usage-scenario",
        layers=["mcp", "tool"],
        limit=4,
        per_route_limit=4,
        consequence_window=4,
        raw_preview_limit=2,
    )
    typo_mcp_trace = module.trace_route(aoa_root=aoa_root, anchor="aoa-decsions-mcp", kind="mcp", limit=20, per_route_limit=5)
    query_state = module.graph_store_query_state(aoa_root)
    storage = module.storage_audit(aoa_root=aoa_root, deep_dbstat=True, row_counts=True, write_report=True)
    cooccurrence = module.graph_cooccurrence(aoa_root=aoa_root, anchor="exec_command", kind="tool")
    packet = module.graph_rag_packet(
        aoa_root=aoa_root,
        query="aoa-session-memory-mcp",
        anchor="aoa-session-memory-mcp",
        limit=4,
    )
    explain = module.graph_explain_packet(
        aoa_root=aoa_root,
        intent="debug aoa-session-memory-mcp",
        anchor="aoa-session-memory-mcp",
        limit=4,
    )
    eval_payload = module.graph_eval(aoa_root=aoa_root, limit=3)
    quality = module.graph_quality_audit(
        aoa_root=aoa_root,
        anchors=["mcp:aoa-session-memory-mcp", "tool:exec_command"],
        limit=3,
        sample_ref_limit=2,
        write_report=True,
    )

    assert neighborhood["ok"] is True
    assert neighborhood["graph"]["source"] == "sqlite_graph_store"
    assert neighborhood["evidence_refs"]
    assert any(item.get("refs", {}).get("raw") for item in neighborhood["evidence_refs"] if isinstance(item, dict))
    assert timeline["events"]
    assert config_alias_timeline["events"]
    assert "aoa_session_memory_mcp" in config_alias_timeline["resolved"]["aliases"]
    assert config_alias_timeline["resolved"]["resolver_strategy"] == "exact_route_node"
    assert exact_tool_timeline["resolved"]["start_node_ids"] == ["route:tool:tool:aoa_decisions_search"]
    assert any(event.get("title") == "Tool call: aoa_decisions_search" for event in exact_tool_timeline["events"])
    assert all(event.get("title") != "Tool call: spawn_agent" for event in exact_tool_timeline["events"])
    assert usage_audit["artifact_type"] == "session_memory_entity_usage_audit"
    assert usage_audit["ok"] is True
    assert usage_audit["usage_event_count"] >= 1
    assert any(event.get("title") == "Tool call: aoa_decisions_search" for event in usage_audit["usage_events"])
    assert all(event.get("title") != "Tool call: spawn_agent" for event in usage_audit["usage_events"])
    assert usage_audit["consequence_event_count"] >= 1
    assert any(
        item.get("kind") == "mentioned_path" and item.get("value") == "docs/decisions/README.md"
        for item in usage_audit["document_refs"]
    )
    assert usage_audit["quality"]["search_has_route_index"] is True
    assert usage_audit["quality"]["search_has_route_terms"] is True
    assert usage_audit["quality"]["fresh_event_count"] >= usage_audit["usage_event_count"]
    assert usage_audit["quality"]["stale_event_count"] == 0
    assert usage_audit["sessions"][0]["fresh_event_count"] >= usage_audit["usage_event_count"]
    assert usage_audit["sessions"][0]["stale_event_count"] == 0
    assert narrow_usage_audit["ok"] is True
    assert narrow_usage_audit["event_count"] == 1
    assert narrow_usage_audit["usage_event_count"] == 1
    assert narrow_usage_audit["usage_events"][0]["title"] == "Tool call: aoa_decisions_search"
    assert narrow_usage_audit["quality"]["candidate_usage_event_count"] >= 1
    assert usage_neighborhood["artifact_type"] == "session_memory_entity_usage_neighborhood"
    assert usage_neighborhood["ok"] is True
    assert usage_neighborhood["quality"]["usage_neighborhood_present"] is True
    assert usage_neighborhood["quality"]["consequence_present"] is True
    assert usage_neighborhood["quality"]["raw_preview_available"] is True
    first_neighborhood = usage_neighborhood["neighborhoods"][0]
    assert first_neighborhood["source_usage_event"]["title"] == "Tool call: aoa_decisions_search"
    assert first_neighborhood["source_usage_event"]["raw_preview"]["status"] == "available"
    assert isinstance(first_neighborhood["source_usage_event"]["route_signals"], list)
    assert first_neighborhood["source_usage_event"]["route_signal_count"] >= len(first_neighborhood["source_usage_event"]["route_signals"])
    assert any(event.get("relation") == "same_correlation_id" for event in first_neighborhood["consequence_events"])
    assert any(event.get("event_type") == "ASSISTANT_MESSAGE" for event in first_neighborhood["consequence_events"])
    assert any(
        item.get("kind") == "mentioned_path" and item.get("value") == "docs/decisions/README.md"
        for item in usage_neighborhood["document_refs"]
    )
    assert narrow_usage_neighborhood["ok"] is True
    assert narrow_usage_neighborhood["quality"]["requested_usage_limit"] == 1
    assert narrow_usage_neighborhood["quality"]["audit_per_route_limit"] > 1
    assert narrow_usage_neighborhood["quality"]["usage_neighborhood_present"] is True
    assert narrow_usage_neighborhood["quality"]["raw_preview_available"] is True
    assert narrow_usage_neighborhood["source_audit"]["usage_event_count"] >= 1
    assert narrow_usage_neighborhood["neighborhoods"][0]["source_usage_event"]["title"] == "Tool call: aoa_decisions_search"
    assert scenario_audit["artifact_type"] == "session_memory_entity_usage_scenario_audit"
    assert scenario_audit["ok"] is True
    assert scenario_audit["quality"]["sample_count"] == 2
    assert scenario_audit["quality"]["failed_count"] == 0
    assert scenario_audit["quality"]["raw_preview_counts"].get("available", 0) >= 1
    assert not any(
        item.get("key") == "namespace_tool"
        for item in exact_tool_timeline["resolved"].get("route_candidates", [])
        if isinstance(item, dict)
    )
    typo_routes = {
        f"{item.get('layer')}:{item.get('key')}"
        for item in typo_mcp_trace.get("route_candidates", [])
        if isinstance(item, dict) and item.get("key")
    }
    assert "mcp:aoa_decsions_mcp" in typo_routes
    assert "entity:aoa_decsions_mcp" in typo_routes
    assert not any("unknown_mcp_service_identity:aoa_decsions_mcp" in item for item in typo_mcp_trace["diagnostics"])
    assert query_state["query_scope"] == "lightweight_store_availability_not_full_dirty_audit"
    assert query_state["metadata"]["graph_store_aggregate_payload_mode"] == module.GRAPH_STORE_AGGREGATE_PAYLOAD_MODE
    assert query_state["metadata"]["graph_store_contrib_payload_mode"] == module.GRAPH_STORE_CONTRIB_PAYLOAD_MODE
    assert storage["artifact_type"] == "session_memory_storage_audit"
    assert storage["ok"] is True
    assert storage["graph_store"]["ok"] is True
    assert storage["graph_store"]["metadata"]["graph_store_aggregate_payload_mode"] == module.GRAPH_STORE_AGGREGATE_PAYLOAD_MODE
    assert storage["graph_store"]["deep_dbstat_status"] == "completed"
    assert storage["graph_store"]["row_count_status"] == "requested"
    assert storage["search_store"]["metadata"]["search_body_storage_mode"] == module.SEARCH_BODY_STORAGE_MODE
    assert storage["graph_store"]["table_sizes"]
    assert storage["graph_store"]["wal"]["size_bytes"] >= 0
    assert storage["graph_store"]["total_with_wal_bytes"] >= storage["graph_store"]["size_bytes"]
    assert storage["sessions"]["raw_block_duplication_candidate_bytes"] >= 0
    assert any(item.get("id") == "sqlite_wal_checkpoint" for item in storage["recommendations"])
    assert any(item.get("id") == "graph_compact_aggregate_payload" for item in storage["recommendations"])
    assert Path(storage["report_json"]).exists()
    assert cooccurrence["artifact_type"] == "session_memory_graph_cooccurrence"
    assert packet["ok"] is True
    assert packet["truth_status"] == "rag_graphrag_evidence_packet_not_reviewed_truth"
    assert packet["evidence_refs"]
    assert packet["answer_rules"]["status"] in {"needs_review", "evidence_ready"}
    assert packet["answer_rules"]["important_claim_allowed"] is True
    assert explain["artifact_type"] == "session_memory_graph_explain_packet"
    assert explain["evidence_refs"]
    assert explain["answer_rules"]["graph_rag_synthesis_allowed"] is True
    assert eval_payload["results"]
    assert quality["artifact_type"] == "session_memory_graph_quality_audit"
    assert quality["ok"] is True
    assert quality["sample_count"] == 2
    assert quality["ready_for_manual_verdict_count"] == 2
    assert all(sample["review_status"] == "ready_for_manual_verdict" for sample in quality["samples"])
    assert all(sample["evidence"]["has_raw_ref"] for sample in quality["samples"])
    assert any(
        ref.get("raw_preview", {}).get("status") == "available"
        for sample in quality["samples"]
        for ref in sample["evidence"]["sample_refs"]
    )
    assert Path(quality["report_json"]).exists()
    assert Path(quality["report_markdown"]).exists()

    first_identity = module.graph_quality_identity(quality["samples"][0])
    second_identity = module.graph_quality_identity(quality["samples"][1])
    review = module.graph_quality_review(
        aoa_root=aoa_root,
        audit_path=Path(quality["report_json"]),
        verdict_values=[
            f"{first_identity}=accept:accept:anchor evidence is specific",
            f"{second_identity}=reject:repair_classifier:tool anchor is too broad",
        ],
        reviewer="test-reviewer",
        write_report=True,
    )

    assert review["artifact_type"] == "session_memory_graph_quality_review"
    assert review["ok"] is True
    assert review["sample_count"] == 2
    assert review["reviewed_count"] == 2
    assert review["open_count"] == 0
    assert review["verdict_counts"]["accept"] == 1
    assert review["verdict_counts"]["reject"] == 1
    assert review["quality_feedback_count"] == 1
    assert review["quality_feedback"][0]["action"] == "repair_classifier"
    assert review["regression_candidate_count"] == 2
    assert Path(review["report_json"]).exists()
    assert Path(review["report_markdown"]).exists()

    corpus = module.graph_quality_corpus_from_review(
        aoa_root=aoa_root,
        review_paths=[Path(review["report_json"])],
        write_corpus=True,
        write_report=True,
    )
    corpus_check = module.graph_quality_corpus_check(
        aoa_root=aoa_root,
        corpus_path=Path(corpus["corpus_path"]),
        write_report=True,
    )
    gates = module.graph_freshness_gates(aoa_root=aoa_root, ref_sample_limit=20, write_report=True)
    dossier = module.entity_dossier(
        aoa_root=aoa_root,
        anchor="aoa-session-memory-mcp",
        kind="mcp",
        limit=4,
        write_report=True,
    )

    assert corpus["artifact_type"] == "session_memory_graph_quality_regression_corpus"
    assert corpus["case_count"] == 2
    assert corpus["polarity_counts"]["positive"] == 1
    assert corpus["polarity_counts"]["negative"] == 1
    assert Path(corpus["corpus_path"]).exists()
    assert Path(corpus["report_json"]).exists()
    assert corpus_check["artifact_type"] == "session_memory_graph_quality_regression_check"
    assert corpus_check["failed_count"] == 0
    assert "stale" in corpus_check["missing_polarities"]
    assert Path(corpus_check["report_json"]).exists()
    assert gates["artifact_type"] == "session_memory_graph_freshness_gates"
    assert gates["refs"]["ok"] is True
    assert gates["graph_store"]["status"] == "current"
    assert gates["graph_sidecar"]["status"] == "current"
    assert gates["graph_sidecar"]["search_vs_graph"] == "search_newer_than_graph"
    assert Path(gates["report_json"]).exists()
    assert dossier["artifact_type"] == "session_memory_entity_dossier"
    assert dossier["ok"] is True
    assert dossier["strong_refs"]
    assert dossier["read_first"]
    assert Path(dossier["report_json"]).exists()


def test_storage_maintenance_checkpoints_sqlite_wal(tmp_path: Path) -> None:
    aoa_root = tmp_path / ".aoa"
    search_path = module.search_db_path(aoa_root)
    graph_path = module.graph_paths(aoa_root)["store"]

    def open_wal_db(path: Path) -> sqlite3.Connection:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("CREATE TABLE payloads(value TEXT)")
        conn.executemany("INSERT INTO payloads(value) VALUES (?)", [("x" * 1000,) for _ in range(1000)])
        conn.commit()
        assert Path(str(path) + "-wal").exists()
        assert Path(str(path) + "-wal").stat().st_size > 0
        return conn

    search_conn = open_wal_db(search_path)
    graph_conn = open_wal_db(graph_path)
    try:
        payload = module.storage_maintenance(aoa_root=aoa_root, write_report=True)
        assert search_conn.execute("SELECT COUNT(*) FROM payloads").fetchone()[0] == 1000
        assert graph_conn.execute("SELECT COUNT(*) FROM payloads").fetchone()[0] == 1000
    finally:
        search_conn.close()
        graph_conn.close()

    assert payload["artifact_type"] == "session_memory_storage_maintenance"
    assert payload["ok"] is True
    assert payload["mutates"] is True
    assert payload["status"] == "checkpointed"
    assert payload["reclaimed_bytes"] > 0
    assert payload["actions"]["sqlite_wal_checkpoint_truncate"]["search_store"]["status"] == "checkpointed"
    assert payload["actions"]["sqlite_wal_checkpoint_truncate"]["graph_store"]["status"] == "checkpointed"
    assert module.path_total_size(Path(str(search_path) + "-wal")) == 0
    assert module.path_total_size(Path(str(graph_path) + "-wal")) == 0
    assert Path(payload["report_json"]).exists()
    assert Path(payload["report_markdown"]).exists()


def test_graph_store_rebuild_refreshes_duplicate_aggregate_evidence(tmp_path: Path) -> None:
    aoa_root = tmp_path / ".aoa"
    shared_node_id = module.graph_route_node_id("entity", "shared_graph_anchor")
    shared_edge_id = module.graph_edge_id("session:first", shared_node_id, "mentions_route_signal")

    def contribution(source_key: str, session_id: str, raw_ref: str, *, title: str = "") -> dict[str, Any]:
        refs = {"raw": raw_ref, "session": f"sessions/{session_id}/session.manifest.json"}
        node = {
            "id": shared_node_id,
            "type": "route_entity",
            "route_layer": "entity",
            "route_key": "shared_graph_anchor",
            "route_signal": "entity:shared_graph_anchor",
            "evidence_refs": [{"session_id": session_id, "refs": refs}],
        }
        if title:
            node["title"] = title
        return {
            "source": {
                "source_key": source_key,
                "source_type": "segment",
                "session_id": session_id,
                "session_label": session_id,
                "segment_id": "000",
                "source_path": f"sessions/{session_id}/segments/000.index.json",
                "source_paths": [f"sessions/{session_id}/segments/000.index.json"],
                "source_sha": f"sha-{session_id}",
                "source_mtime": 1,
                "graph_schema_version": module.GRAPH_SCHEMA_VERSION,
                "graph_store_schema_version": module.GRAPH_STORE_SCHEMA_VERSION,
                "route_signal_classifier_version": module.ROUTE_SIGNAL_CLASSIFIER_VERSION,
            },
            "nodes": [node],
            "edges": [
                {
                    "id": shared_edge_id,
                    "source": "session:first",
                    "target": shared_node_id,
                    "type": "mentions_route_signal",
                    "evidence_refs": [{"session_id": session_id, "refs": refs}],
                }
            ],
        }

    store = module.GraphSqliteStore(aoa_root, reset=True)
    try:
        rebuilt = store.rebuild(
            [
                contribution("segment:first:000", "first", "raw:line:1"),
                contribution("segment:second:000", "second", "raw:line:2", title="second anchor title"),
            ]
        )
        node_row = store.conn.execute("SELECT payload_json, count FROM nodes WHERE id = ?", (shared_node_id,)).fetchone()
        edge_row = store.conn.execute("SELECT payload_json, count FROM edges WHERE id = ?", (shared_edge_id,)).fetchone()
        node_contrib_row = store.conn.execute("SELECT payload_json FROM node_contribs WHERE node_id = ? LIMIT 1", (shared_node_id,)).fetchone()
        edge_contrib_row = store.conn.execute("SELECT payload_json FROM edge_contribs WHERE edge_id = ? LIMIT 1", (shared_edge_id,)).fetchone()
        assert node_row is not None
        assert edge_row is not None
        assert node_contrib_row is not None
        assert edge_contrib_row is not None
        stored_node = json.loads(str(node_row["payload_json"]))
        stored_edge = json.loads(str(edge_row["payload_json"]))
        node_contrib = json.loads(str(node_contrib_row["payload_json"]))
        edge_contrib = json.loads(str(edge_contrib_row["payload_json"]))
        hydrated_node = next(payload for payload in store.iter_payloads("nodes") if payload["id"] == shared_node_id)
        hydrated_edge = next(payload for payload in store.iter_payloads("edges") if payload["id"] == shared_edge_id)
    finally:
        store.close()

    assert rebuilt["duplicate_node_refresh"]["requested_count"] == 1
    assert rebuilt["duplicate_edge_refresh"]["requested_count"] == 1
    assert int(node_row["count"]) == 2
    assert int(edge_row["count"]) == 2
    assert stored_node["count"] == 2
    assert stored_node["evidence_ref_count"] == 2
    assert stored_node["title"] == "second anchor title"
    assert stored_edge["count"] == 2
    assert stored_edge["evidence_ref_count"] == 2
    assert node_contrib["contrib_payload_mode"] == module.GRAPH_STORE_CONTRIB_PAYLOAD_MODE
    assert edge_contrib["contrib_payload_mode"] == module.GRAPH_STORE_CONTRIB_PAYLOAD_MODE
    assert node_contrib["evidence_refs"][0]["refs"]["raw"] == "raw:line:1"
    assert edge_contrib["evidence_refs"][0]["refs"]["raw"] == "raw:line:1"
    assert "session_index" not in node_contrib["evidence_refs"][0]["refs"]
    assert "segment_index" not in edge_contrib["evidence_refs"][0]["refs"]
    assert {ref["session_id"] for ref in hydrated_node["evidence_refs"]} == {"first", "second"}
    assert {ref["session_id"] for ref in hydrated_edge["evidence_refs"]} == {"first", "second"}


def test_graph_maintenance_replaces_dirty_segment_contribution(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-26T00-10-00-incremental-graph.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-26T00:10:00Z", "type": "session_meta", "payload": {"id": "incremental-graph", "cwd": str(repo), "model": "gpt-5"}},
            {"timestamp": "2026-05-26T00:10:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Debug incremental graph maintenance."}]}},
            {"timestamp": "2026-05-26T00:10:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Incremental graph refs are preserved."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "incremental-graph",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    session_dir = aoa_root / "sessions" / "2026-05-26__001__debug-incremental-graph-maintenance"
    segment_index_path = next((session_dir / "segments").glob("*.index.json"))
    segment_index = json.loads(segment_index_path.read_text(encoding="utf-8"))
    assert segment_index["events"]
    old_signal = {"layer": "entity", "key": "alpha_incremental_anchor", "route_signal": "entity:alpha_incremental_anchor"}
    new_signal = {"layer": "entity", "key": "beta_incremental_anchor", "route_signal": "entity:beta_incremental_anchor"}
    segment_index["events"][0].setdefault("facets", {}).setdefault("route_signals", []).append(old_signal)
    segment_index_path.write_text(json.dumps(segment_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    built = module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)
    assert built["ok"] is True
    old_node_id = module.graph_route_node_id("entity", "alpha_incremental_anchor")
    new_node_id = module.graph_route_node_id("entity", "beta_incremental_anchor")
    conn = sqlite3.connect(str(aoa_root / "graph" / "graph.sqlite3"))
    assert conn.execute("SELECT COUNT(*) FROM nodes WHERE id = ?", (old_node_id,)).fetchone()[0] == 1
    conn.close()

    segment_index["events"][0]["facets"]["route_signals"] = [
        signal for signal in segment_index["events"][0]["facets"]["route_signals"]
        if signal.get("key") != "alpha_incremental_anchor"
    ] + [new_signal]
    segment_index_path.write_text(json.dumps(segment_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.utime(segment_index_path, None)

    states = module.graph_source_states(aoa_root=aoa_root)
    assert states["dirty_count"] >= 1
    assert states["reason_group_counts"]["source_sha_mismatch"] >= 1
    assert states["maintenance_recommendation"]["route"] in {"bounded_graph_maintenance", "budgeted_graph_maintenance"}
    assert any(item["status"] == "dirty" and item["source_type"] == "segment" for item in states["states"])

    dirty_gates = module.graph_freshness_gates(aoa_root=aoa_root, ref_sample_limit=20)
    assert dirty_gates["graph_store"]["status"] == "dirty"
    assert dirty_gates["graph_sidecar"]["status"] == "stale"
    assert dirty_gates["graph_sidecar"]["needs_snapshot_refresh"] is True
    assert dirty_gates["graph_sidecar"]["needs_offline_graph_build"] is False
    assert dirty_gates["needs_graph_maintenance"] is True
    assert dirty_gates["needs_sidecar_export"] is False
    assert dirty_gates["needs_offline_graph_build"] is False

    deferred = module.graph_maintenance(
        aoa_root=aoa_root,
        apply=True,
        batch_limit=10,
        max_refresh_nodes=1,
        max_refresh_edges=1,
        write_report=True,
    )
    assert deferred["ok"] is True
    assert deferred["selected_count"] == 0
    assert deferred["oversized_source_count"] >= 1
    assert deferred["remaining_count"] >= 1
    assert deferred["maintenance_detail"]["oversized_source_count"] >= 1
    assert any(item["status"] == "oversized_refresh_budget" for item in deferred["results"])
    conn = sqlite3.connect(str(aoa_root / "graph" / "graph.sqlite3"))
    assert conn.execute("SELECT COUNT(*) FROM nodes WHERE id = ?", (old_node_id,)).fetchone()[0] == 1
    conn.close()

    maintained = module.graph_maintenance(aoa_root=aoa_root, apply=True, batch_limit=10, write_report=True)
    assert maintained["ok"] is True
    assert maintained["selected_count"] >= 1
    assert maintained["state_window"] == "post_apply"
    assert maintained["pre_source_state"]["dirty_count"] >= 1
    assert maintained["post_source_state"]["dirty_count"] == 0
    assert maintained["pre_actionable_count"] >= 1
    assert maintained["post_actionable_count"] == 0
    assert maintained["remaining_count"] == 0
    assert maintained["maintenance_detail"]["post_source_state_refreshed"] is True
    assert Path(maintained["report_json"]).exists()
    conn = sqlite3.connect(str(aoa_root / "graph" / "graph.sqlite3"))
    assert conn.execute("SELECT COUNT(*) FROM nodes WHERE id = ?", (old_node_id,)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM nodes WHERE id = ?", (new_node_id,)).fetchone()[0] == 1
    conn.close()

    gates = module.graph_freshness_gates(aoa_root=aoa_root, ref_sample_limit=20)
    assert gates["graph_store"]["status"] == "current"
    assert gates["graph_sidecar"]["status"] == "stale"
    assert gates["graph_sidecar"]["needs_snapshot_refresh"] is True
    assert gates["graph_sidecar"]["needs_offline_graph_build"] is False
    assert gates["needs_sidecar_export"] is True
    assert gates["needs_offline_graph_build"] is False

    pruned = module.graph_prune_sidecar(aoa_root=aoa_root, apply=True, write_report=True)
    assert pruned["ok"] is True
    assert pruned["freed_bytes"] > 0
    assert Path(pruned["report_json"]).exists()
    assert not (aoa_root / "graph" / "nodes.jsonl").exists()
    assert not (aoa_root / "graph" / "edges.jsonl").exists()
    assert not (aoa_root / "graph" / "index.json").exists()
    assert (aoa_root / "graph" / "graph.sqlite3").exists()
    pruned_gates = module.graph_freshness_gates(aoa_root=aoa_root, ref_sample_limit=20)
    assert pruned_gates["graph_store"]["status"] == "current"
    assert pruned_gates["graph_sidecar"]["status"] == "not_exported"
    assert pruned_gates["graph_sidecar"]["needs_snapshot_refresh"] is False
    assert pruned_gates["needs_sidecar_export"] is False
    assert next(gate for gate in pruned_gates["gates"] if gate["name"] == "graph_sidecar_snapshot")["ok"] is True

    segment_index_path.unlink()
    record = module.resolve_session_record(aoa_root, "incremental-graph")
    contributions, diagnostics = module.graph_contributions_for_record(record)
    assert diagnostics == []
    blocked_contribution = next(
        contribution for contribution in contributions
        if contribution["source"]["source_type"] == "segment"
    )
    assert blocked_contribution["source"]["status"] == "blocked"
    store = module.GraphSqliteStore(aoa_root)
    try:
        blocked = store.replace_source(blocked_contribution)
        store.conn.commit()
    finally:
        store.close()
    assert blocked["status"] == "blocked"
    conn = sqlite3.connect(str(aoa_root / "graph" / "graph.sqlite3"))
    assert conn.execute("SELECT COUNT(*) FROM nodes WHERE id = ?", (new_node_id,)).fetchone()[0] == 0
    conn.close()


def test_graph_source_recommendation_routes_mass_classifier_drift_to_store_rebuild() -> None:
    recommendation = module.graph_source_maintenance_recommendation(
        source_count=4000,
        dirty_count=3900,
        missing_count=10,
        orphaned_count=0,
        blocked_count=50,
        reason_group_counts={
            "source_sha_mismatch": 3900,
            "route_signal_classifier_mismatch": 3800,
            "graph_source_missing": 10,
        },
    )

    assert recommendation["route"] == "store_only_rebuild"
    assert recommendation["reason"] == "route_signal_classifier_drift_dominates"
    assert "--store-only --in-place" in recommendation["command"]
    assert "blocked_sources_need_lower_layer_repair" in recommendation["notes"]


def test_graph_source_recommendation_routes_mass_missing_sources_to_store_rebuild() -> None:
    recommendation = module.graph_source_maintenance_recommendation(
        source_count=4200,
        dirty_count=0,
        missing_count=4100,
        orphaned_count=0,
        blocked_count=62,
        reason_group_counts={
            "graph_source_missing": 4100,
            "missing_graph_source_path": 62,
        },
    )

    assert recommendation["route"] == "store_only_rebuild"
    assert recommendation["reason"] == "graph_store_missing_sources_dominate"
    assert "--store-only --in-place" in recommendation["command"]
    assert "missing_sources_can_be_inserted_by_incremental_or_rebuild_route" in recommendation["notes"]
    assert "missing_graph_source_paths_are_blocked_evidence_sources" in recommendation["notes"]


def test_graph_maintenance_selects_cheap_sources_before_oversized_backlog(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    heavy_transcript = tmp_path / "rollout-2026-05-26T00-11-00-heavy-graph-source.jsonl"
    light_transcript = tmp_path / "rollout-2026-05-26T00-12-00-light-graph-source.jsonl"
    for session_id, transcript, prompt in (
        ("heavy-graph-source", heavy_transcript, "Create the heavy graph source."),
        ("light-graph-source", light_transcript, "Create the light graph source."),
    ):
        write_jsonl(
            transcript,
            [
                {"timestamp": "2026-05-26T00:11:00Z", "type": "session_meta", "payload": {"id": session_id, "cwd": str(repo), "model": "gpt-5"}},
                {"timestamp": "2026-05-26T00:11:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}]}},
                {"timestamp": "2026-05-26T00:11:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Graph source archived."}]}},
            ],
        )
        module.handle_hook_event(
            "Stop",
            {
                "session_id": session_id,
                "transcript_path": str(transcript),
                "cwd": str(repo),
                "hook_event_name": "Stop",
            },
            workspace_root=workspace,
            aoa_root=aoa_root,
        )

    built = module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)
    assert built["ok"] is True
    heavy_record = module.resolve_session_record(aoa_root, "heavy-graph-source")
    light_record = module.resolve_session_record(aoa_root, "light-graph-source")
    heavy_segment_index_path = next((Path(heavy_record["path"]) / "segments").glob("*.index.json"))
    light_segment_index_path = next((Path(light_record["path"]) / "segments").glob("*.index.json"))
    heavy_segment_index = json.loads(heavy_segment_index_path.read_text(encoding="utf-8"))
    light_segment_index = json.loads(light_segment_index_path.read_text(encoding="utf-8"))
    heavy_segment_id = str(heavy_segment_index["segment_id"])
    light_segment_id = str(light_segment_index["segment_id"])
    heavy_source_key = module.graph_source_key("segment", "heavy-graph-source", heavy_segment_id)
    light_source_key = module.graph_source_key("segment", "light-graph-source", light_segment_id)
    heavy_signals = [
        {"layer": "entity", "key": f"heavy_cost_anchor_{index}", "route_signal": f"entity:heavy_cost_anchor_{index}"}
        for index in range(80)
    ]
    light_signal = {"layer": "entity", "key": "light_cost_anchor", "route_signal": "entity:light_cost_anchor"}
    heavy_segment_index["events"][0].setdefault("facets", {}).setdefault("route_signals", []).extend(heavy_signals)
    light_segment_index["events"][0].setdefault("facets", {}).setdefault("route_signals", []).append(light_signal)
    heavy_segment_index_path.write_text(json.dumps(heavy_segment_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    light_segment_index_path.write_text(json.dumps(light_segment_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.utime(heavy_segment_index_path, None)
    os.utime(light_segment_index_path, None)

    contributions_by_key: dict[str, dict[str, Any]] = {}
    for record in (heavy_record, light_record):
        contributions, diagnostics = module.graph_contributions_for_record(record)
        assert diagnostics == []
        for contribution in contributions:
            source = contribution.get("source") if isinstance(contribution.get("source"), dict) else {}
            contributions_by_key[str(source.get("source_key") or "")] = contribution
    store = module.GraphSqliteStore(aoa_root)
    try:
        heavy_old_nodes, heavy_old_edges = store.source_contribution_ids(heavy_source_key)
        light_old_nodes, light_old_edges = store.source_contribution_ids(light_source_key)
    finally:
        store.close()
    heavy_new_nodes, heavy_new_edges = module.graph_contribution_id_sets(contributions_by_key[heavy_source_key])
    light_new_nodes, light_new_edges = module.graph_contribution_id_sets(contributions_by_key[light_source_key])
    heavy_node_cost = len(heavy_old_nodes | heavy_new_nodes)
    heavy_edge_cost = len(heavy_old_edges | heavy_new_edges)
    light_node_cost = len(light_old_nodes | light_new_nodes)
    light_edge_cost = len(light_old_edges | light_new_edges)
    assert heavy_node_cost > light_node_cost or heavy_edge_cost > light_edge_cost

    planned = module.graph_maintenance(
        aoa_root=aoa_root,
        apply=False,
        plan_refresh_costs=True,
        batch_limit=1,
        max_refresh_nodes=light_node_cost,
        max_refresh_edges=light_edge_cost,
        write_report=True,
    )
    assert planned["ok"] is True
    assert planned["apply"] is False
    assert planned["plan_refresh_costs"] is True
    assert planned["selected_count"] == 1
    assert planned["selected"][0]["source_key"] == light_source_key
    assert planned["maintenance_detail"]["planned_only"] is True
    assert planned["maintenance_detail"]["selection_strategy"] == "cheap_first_exact_refresh_cost_plan"
    assert heavy_source_key in planned["maintenance_detail"]["oversized_sources"]
    conn = sqlite3.connect(str(aoa_root / "graph" / "graph.sqlite3"))
    assert conn.execute("SELECT COUNT(*) FROM nodes WHERE id = ?", (module.graph_route_node_id("entity", "light_cost_anchor"),)).fetchone()[0] == 0
    conn.close()

    maintained = module.graph_maintenance(
        aoa_root=aoa_root,
        apply=True,
        batch_limit=1,
        max_refresh_nodes=light_node_cost,
        max_refresh_edges=light_edge_cost,
        write_report=True,
    )

    assert maintained["ok"] is True
    assert maintained["selected_count"] == 1
    assert maintained["selected"][0]["source_key"] == light_source_key
    assert maintained["oversized_source_count"] >= 1
    assert heavy_source_key in maintained["maintenance_detail"]["oversized_sources"]
    assert light_source_key in maintained["maintenance_detail"]["selected_sources"]
    assert maintained["maintenance_detail"]["selection_strategy"] == "cheap_first_exact_refresh_cost"
    assert any(item["source_key"] == light_source_key and item["status"] == "updated" for item in maintained["results"])
    assert not any(item["source_key"] == heavy_source_key and item["status"] == "updated" for item in maintained["results"])
    assert maintained["state_window"] == "post_apply"
    assert maintained["pre_actionable_count"] > maintained["post_actionable_count"]
    assert maintained["post_remaining_count"] == maintained["remaining_count"]
    assert maintained["maintenance_detail"]["post_source_state_refreshed"] is True
    conn = sqlite3.connect(str(aoa_root / "graph" / "graph.sqlite3"))
    assert conn.execute("SELECT COUNT(*) FROM nodes WHERE id = ?", (module.graph_route_node_id("entity", "light_cost_anchor"),)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM nodes WHERE id = ?", (module.graph_route_node_id("entity", "heavy_cost_anchor_0"),)).fetchone()[0] == 0
    conn.close()

    heavy_deferred = module.graph_maintenance(
        aoa_root=aoa_root,
        source_keys=[heavy_source_key],
        apply=True,
        batch_limit=10,
        max_refresh_nodes=max(1, heavy_node_cost - 1),
        max_refresh_edges=max(1, heavy_edge_cost - 1),
        write_report=True,
    )
    assert heavy_deferred["ok"] is True
    assert heavy_deferred["source_keys"] == [heavy_source_key]
    assert heavy_deferred["source_state"]["filtered_by_source_key"] is True
    assert heavy_deferred["source_state"]["source_count"] == 1
    assert heavy_deferred["selected_count"] == 0
    assert heavy_deferred["remaining_count"] == 1
    assert heavy_deferred["oversized_source_count"] == 1
    assert heavy_deferred["maintenance_detail"]["matched_source_keys"] == [heavy_source_key]
    assert heavy_deferred["maintenance_detail"]["oversized_plan"][0]["source_key"] == heavy_source_key
    assert heavy_deferred["unfiltered_source_state"]["source_count"] >= 2

    with monkeypatch.context() as time_patch:
        ticks = iter([0.0, 1.0, 2.0])
        time_patch.setattr(module.time, "monotonic", lambda: next(ticks, 2.0))
        timed_deferred = module.graph_maintenance(
            aoa_root=aoa_root,
            source_keys=[heavy_source_key],
            apply=True,
            batch_limit=10,
            budget_seconds=0.5,
            write_report=True,
        )
    assert timed_deferred["ok"] is True
    assert timed_deferred["budget_exhausted"] is True
    assert timed_deferred["selected_count"] == 0
    assert timed_deferred["remaining_count"] == 1
    assert timed_deferred["time_budget_deferred_source_count"] == 1
    assert timed_deferred["maintenance_detail"]["time_budget_deferred_sources"] == [heavy_source_key]
    assert any(item["source_key"] == heavy_source_key and item["status"] == "deferred_time_budget" for item in timed_deferred["results"])
    conn = sqlite3.connect(str(aoa_root / "graph" / "graph.sqlite3"))
    assert conn.execute("SELECT COUNT(*) FROM nodes WHERE id = ?", (module.graph_route_node_id("entity", "heavy_cost_anchor_0"),)).fetchone()[0] == 0
    conn.close()

    with monkeypatch.context() as rollback_patch:
        def exhausted_replace_sources(self: Any, contributions: Any, *, budget_deadline: float | None = None) -> dict[str, Any]:
            raise module.GraphMaintenanceBudgetExceeded("test budget exhausted")

        rollback_patch.setattr(module.GraphSqliteStore, "replace_sources", exhausted_replace_sources)
        rolled_back = module.graph_maintenance(
            aoa_root=aoa_root,
            source_keys=[heavy_source_key],
            apply=True,
            batch_limit=10,
            budget_seconds=60,
            write_report=True,
        )
    assert rolled_back["ok"] is True
    assert rolled_back["budget_exhausted"] is True
    assert rolled_back["mutation_rolled_back"] is True
    assert rolled_back["selected_count"] == 0
    assert rolled_back["maintenance_detail"]["selected_sources"] == []
    assert rolled_back["maintenance_detail"]["rolled_back_sources"] == [heavy_source_key]
    assert rolled_back["maintenance_detail"]["time_budget_deferred_sources"] == [heavy_source_key]
    conn = sqlite3.connect(str(aoa_root / "graph" / "graph.sqlite3"))
    assert conn.execute("SELECT COUNT(*) FROM nodes WHERE id = ?", (module.graph_route_node_id("entity", "heavy_cost_anchor_0"),)).fetchone()[0] == 0
    conn.close()

    missing_source = module.graph_maintenance(
        aoa_root=aoa_root,
        source_keys=["segment:missing-session:999"],
        apply=True,
        batch_limit=10,
    )
    assert missing_source["ok"] is False
    assert missing_source["source_state"]["source_count"] == 0
    assert missing_source["maintenance_detail"]["missing_source_keys"] == ["segment:missing-session:999"]
    assert "requested_graph_source_not_found:segment:missing-session:999" in missing_source["diagnostics"]

    heavy_maintained = module.graph_maintenance(
        aoa_root=aoa_root,
        source_keys=[heavy_source_key],
        apply=True,
        batch_limit=10,
        max_refresh_nodes=heavy_node_cost,
        max_refresh_edges=heavy_edge_cost,
        write_report=True,
    )
    assert heavy_maintained["ok"] is True
    assert heavy_maintained["selected_count"] == 1
    assert heavy_maintained["state_window"] == "post_apply"
    assert heavy_maintained["pre_actionable_count"] == 1
    assert heavy_maintained["pre_remaining_count"] == 0
    assert heavy_maintained["post_actionable_count"] == 0
    assert heavy_maintained["post_remaining_count"] == 0
    assert heavy_maintained["remaining_count"] == 0
    assert heavy_maintained["maintenance_detail"]["selected_sources"] == [heavy_source_key]
    assert any(item["source_key"] == heavy_source_key and item["status"] == "updated" for item in heavy_maintained["results"])
    conn = sqlite3.connect(str(aoa_root / "graph" / "graph.sqlite3"))
    assert conn.execute("SELECT COUNT(*) FROM nodes WHERE id = ?", (module.graph_route_node_id("entity", "heavy_cost_anchor_0"),)).fetchone()[0] == 1
    conn.close()


def test_graph_maintenance_apply_candidate_pool_scales_with_batch(tmp_path: Path, monkeypatch: Any) -> None:
    aoa_root = tmp_path / ".aoa"
    aoa_root.mkdir(parents=True)
    session_dir = aoa_root / "sessions" / "2026-06-13__001__graph-pool"
    session_dir.mkdir(parents=True)
    observed: dict[str, Any] = {}
    states = [
        {
            "source_key": f"segment:session-1:{index:03d}",
            "source_type": "segment",
            "session_id": "session-1",
            "session_label": "graph-pool",
            "segment_id": f"{index:03d}",
            "session_dir": str(session_dir),
            "status": "dirty",
            "stored_node_count": index,
            "stored_edge_count": index,
        }
        for index in range(20)
    ]

    class FakeConn:
        def commit(self) -> None:
            observed["committed"] = True

        def rollback(self) -> None:
            observed["rolled_back"] = True

    class FakeStore:
        def __init__(self, *_: Any, **__: Any) -> None:
            self.conn = FakeConn()

        def source_contribution_ids(self, source_key: str) -> tuple[set[str], set[str]]:
            return {f"old:{source_key}"}, set()

        def replace_sources(self, contributions: list[dict[str, Any]], *, budget_deadline: float | None = None) -> dict[str, Any]:
            return {
                "results": [
                    {"source_key": item["source"]["source_key"], "status": "updated", "diagnostics": []}
                    for item in contributions
                ],
                "refreshed_node_count": len(contributions),
                "refreshed_edge_count": 0,
                "node_refresh": {"requested_count": len(contributions), "chunk_count": 1, "row_count": len(contributions), "missing_count": 0},
                "edge_refresh": {"requested_count": 0, "chunk_count": 0, "row_count": 0, "missing_count": 0},
                "refresh_chunk_size": 64,
            }

        def close(self) -> None:
            observed["closed"] = True

    def fake_graph_source_states(**_: Any) -> dict[str, Any]:
        if observed.get("committed"):
            post_states = []
            for index, state in enumerate(states):
                post_state = dict(state)
                if index < 3:
                    post_state["status"] = "clean"
                post_states.append(post_state)
            return {"states": post_states, "diagnostics": [], "existing_source_count": len(post_states)}
        return {"states": states, "diagnostics": [], "existing_source_count": len(states)}

    def fake_graph_contributions_for_record(record: dict[str, Any], *, source_keys: set[str] | None = None) -> tuple[list[dict[str, Any]], list[str]]:
        keys = sorted(source_keys or [])
        observed["source_key_count"] = len(keys)
        return (
            [
                {
                    "source": {"source_key": source_key, "source_type": "segment"},
                    "nodes": [{"id": f"new:{source_key}"}],
                    "edges": [],
                }
                for source_key in keys
            ],
            [],
        )

    monkeypatch.setattr(module, "graph_source_states", fake_graph_source_states)
    monkeypatch.setattr(module, "GraphSqliteStore", FakeStore)
    monkeypatch.setattr(module, "graph_contributions_for_record", fake_graph_contributions_for_record)

    payload = module.graph_maintenance(aoa_root=aoa_root, apply=True, batch_limit=3)

    assert payload["ok"] is True
    assert payload["selected_count"] == 3
    assert payload["remaining_count"] == 17
    assert payload["state_window"] == "post_apply"
    assert payload["pre_actionable_count"] == 20
    assert payload["post_actionable_count"] == 17
    assert payload["pre_remaining_count"] == 17
    assert payload["post_remaining_count"] == 17
    assert payload["maintenance_detail"]["candidate_pool_count"] == 9
    assert payload["maintenance_detail"]["matched_source_key_count"] == 20
    assert payload["maintenance_detail"]["matched_source_key_sample"] == [
        f"segment:session-1:{index:03d}" for index in range(20)
    ]
    assert "matched_source_keys" not in payload["maintenance_detail"]
    assert observed["source_key_count"] == 9
    assert observed["committed"] is True
    assert observed["closed"] is True


def test_graph_freshness_stable_mode_defers_recent_live_session(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    stable_transcript = tmp_path / "rollout-2026-06-11T00-00-00-stable-quiescence-source.jsonl"
    live_transcript = tmp_path / "rollout-2026-06-11T00-05-00-live-quiescence-source.jsonl"
    write_jsonl(
        stable_transcript,
        [
            {"timestamp": "2026-06-11T00:00:00Z", "type": "session_meta", "payload": {"id": "stable-quiescence-source", "cwd": str(repo), "model": "gpt-5"}},
            {"timestamp": "2026-06-11T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Build stable quiescent graph freshness evidence."}]}},
            {"timestamp": "2026-06-11T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Stable source is indexed."}]}},
        ],
    )
    write_jsonl(
        live_transcript,
        [
            {"timestamp": "2026-06-11T00:05:00Z", "type": "session_meta", "payload": {"id": "live-quiescence-source", "cwd": str(repo), "model": "gpt-5"}},
            {"timestamp": "2026-06-11T00:05:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Build live quiescent graph freshness evidence."}]}},
            {"timestamp": "2026-06-11T00:05:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Live source is indexed."}]}},
        ],
    )
    for session_id, transcript in (("stable-quiescence-source", stable_transcript), ("live-quiescence-source", live_transcript)):
        module.handle_hook_event(
            "Stop",
            {
                "session_id": session_id,
                "transcript_path": str(transcript),
                "cwd": str(repo),
                "hook_event_name": "Stop",
            },
            workspace_root=workspace,
            aoa_root=aoa_root,
        )

    stable_record = module.resolve_session_record(aoa_root, "stable-quiescence-source")
    live_record = module.resolve_session_record(aoa_root, "live-quiescence-source")
    old_ts = time.time() - 7200
    for record in (stable_record, live_record):
        for source_path in module.index_source_paths_for_record(record):
            if source_path.exists():
                os.utime(source_path, (old_ts, old_ts))
        raw_path = Path(record["path"]) / "raw" / "session.raw.jsonl"
        if raw_path.exists():
            os.utime(raw_path, (old_ts, old_ts))

    assert module.search_index_sessions(aoa_root=aoa_root, target="all")["ok"] is True
    assert module.build_agent_atlas(aoa_root=aoa_root, target="all", clean=True)["ok"] is True
    assert module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)["ok"] is True
    baseline = module.graph_freshness_gates(aoa_root=aoa_root, ref_sample_limit=20)
    assert baseline["ok"] is True

    live_segment_index_path = next((Path(live_record["path"]) / "segments").glob("*.index.json"))
    live_segment_index = json.loads(live_segment_index_path.read_text(encoding="utf-8"))
    live_segment_index["events"][0].setdefault("facets", {}).setdefault("route_signals", []).append(
        {"layer": "entity", "key": "live_quiescence_anchor", "route_signal": "entity:live_quiescence_anchor"}
    )
    live_segment_index_path.write_text(json.dumps(live_segment_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.utime(live_segment_index_path, None)

    strict = module.graph_freshness_gates(aoa_root=aoa_root, ref_sample_limit=20)
    stable = module.graph_freshness_gates(
        aoa_root=aoa_root,
        ref_sample_limit=20,
        stable_quiet_seconds=60,
        now_ts=time.time(),
    )

    assert strict["ok"] is False
    assert strict["truth_status"] == "strict_full_selection_freshness_gate"
    assert strict["search_index"]["dirty_session_count"] == 1
    assert strict["graph_store"]["status"] == "dirty"
    assert strict["graph_store"]["source_state"]["reason_group_counts"]["source_sha_mismatch"] >= 1
    assert strict["graph_store"]["source_state"]["maintenance_recommendation"]["route"] in {"bounded_graph_maintenance", "budgeted_graph_maintenance"}
    assert strict["needs_index_maintenance"] is True
    assert strict["needs_graph_maintenance"] is True
    assert stable["ok"] is True
    assert stable["truth_status"] == "stable_quiescent_subset_gate_deferred_live_sessions_are_not_checked"
    assert stable["selected_count"] == 2
    assert stable["checked_count"] == 1
    assert stable["deferred_live_session_count"] == 1
    assert stable["quiescence"]["checked_count"] == 1
    assert stable["deferred_live_sessions"][0]["session_id"] == "live-quiescence-source"
    assert stable["search_index"]["status"] == "current"
    assert stable["atlas_index"]["status"] == "current"
    assert stable["graph_store"]["status"] == "current"
    assert stable["graph_store"]["source_state"]["selection_scope"] == "selected_sessions"
    assert stable["needs_index_maintenance"] is False
    assert stable["needs_graph_maintenance"] is False
    assert stable["latest_source_mtime"] < stable["selected_latest_source_mtime"]
    assert next(gate for gate in stable["gates"] if gate["name"] == "quiescent_session_subset")["ok"] is True
    assert next(gate for gate in stable["gates"] if gate["name"] == "live_sessions_deferred")["state"]["deferred_live_session_count"] == 1


def test_graph_freshness_stable_mode_defers_recent_codex_transcript_when_archive_projection_is_old(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    stable_transcript = tmp_path / "rollout-2026-06-15T00-00-00-stable-archive.jsonl"
    live_transcript = tmp_path / ".codex" / "sessions" / "2026" / "06" / "15" / "rollout-2026-06-15T00-05-00-live-archive.jsonl"
    live_transcript.parent.mkdir(parents=True)
    for session_id, transcript in (("stable-archive", stable_transcript), ("live-archive", live_transcript)):
        write_jsonl(
            transcript,
            [
                {"timestamp": "2026-06-15T00:00:00Z", "type": "session_meta", "payload": {"id": session_id, "cwd": str(repo), "model": "gpt-5"}},
                {"timestamp": "2026-06-15T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": f"Index {session_id}"}]}},
            ],
        )
        module.handle_hook_event(
            "Stop",
            {
                "session_id": session_id,
                "transcript_path": str(transcript),
                "cwd": str(repo),
                "hook_event_name": "Stop",
            },
            workspace_root=workspace,
            aoa_root=aoa_root,
        )

    stable_record = module.resolve_session_record(aoa_root, "stable-archive")
    live_record = module.resolve_session_record(aoa_root, "live-archive")
    old_ts = time.time() - 7200
    for record in (stable_record, live_record):
        for source_path in module.index_source_paths_for_record(record):
            if source_path.exists():
                os.utime(source_path, (old_ts, old_ts))
        raw_path = Path(record["path"]) / "raw" / "session.raw.jsonl"
        if raw_path.exists():
            os.utime(raw_path, (old_ts, old_ts))
    os.utime(live_transcript, None)

    assert module.search_index_sessions(aoa_root=aoa_root, target="all")["ok"] is True
    assert module.build_agent_atlas(aoa_root=aoa_root, target="all", clean=True)["ok"] is True
    assert module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)["ok"] is True

    stable = module.graph_freshness_gates(
        aoa_root=aoa_root,
        ref_sample_limit=20,
        stable_quiet_seconds=60,
        now_ts=time.time(),
    )

    assert stable["ok"] is True
    assert stable["checked_count"] == 1
    assert stable["deferred_live_session_count"] == 1
    assert stable["deferred_live_sessions"][0]["session_id"] == "live-archive"
    assert stable["deferred_live_sessions"][0]["reasons"] == ["recent_live_codex_transcript_not_yet_archived"]


def test_graph_maintenance_inserts_missing_session_and_removes_orphaned_sources(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"

    first_transcript = tmp_path / "rollout-2026-05-26T00-20-00-first-graph-source.jsonl"
    second_transcript = tmp_path / "rollout-2026-05-26T00-30-00-second-graph-source.jsonl"
    write_jsonl(
        first_transcript,
        [
            {"timestamp": "2026-05-26T00:20:00Z", "type": "session_meta", "payload": {"id": "first-graph-source", "cwd": str(repo), "model": "gpt-5"}},
            {"timestamp": "2026-05-26T00:20:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Create the first graph source."}]}},
            {"timestamp": "2026-05-26T00:20:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "First graph source archived."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "first-graph-source",
            "transcript_path": str(first_transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    built = module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)
    assert built["ok"] is True

    write_jsonl(
        second_transcript,
        [
            {"timestamp": "2026-05-26T00:30:00Z", "type": "session_meta", "payload": {"id": "second-graph-source", "cwd": str(repo), "model": "gpt-5"}},
            {"timestamp": "2026-05-26T00:30:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Create the second graph source."}]}},
            {"timestamp": "2026-05-26T00:30:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Second graph source archived."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "second-graph-source",
            "transcript_path": str(second_transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    states = module.graph_source_states(aoa_root=aoa_root)
    assert states["missing_count"] >= 2
    assert any(item["status"] == "missing" and item["session_id"] == "second-graph-source" for item in states["states"])

    contribution_calls: list[tuple[str, set[str] | None]] = []
    original_graph_contributions_for_record = module.graph_contributions_for_record

    def counted_graph_contributions_for_record(
        record: dict[str, Any],
        *,
        source_keys: set[str] | None = None,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        contribution_calls.append((str(record.get("session_id") or Path(str(record.get("path") or "")).name), source_keys))
        return original_graph_contributions_for_record(record, source_keys=source_keys)

    monkeypatch.setattr(module, "graph_contributions_for_record", counted_graph_contributions_for_record)
    inserted = module.graph_maintenance(aoa_root=aoa_root, apply=True, batch_limit=10, refresh_chunk_size=2)
    assert inserted["ok"] is True
    assert inserted["selected_count"] >= 2
    assert inserted["refresh_chunk_size"] == 2
    assert [session_id for session_id, _source_keys in contribution_calls].count("second-graph-source") == 1
    assert all(source_keys for session_id, source_keys in contribution_calls if session_id == "second-graph-source")
    assert inserted["maintenance_detail"]["refresh_chunk_size"] == 2
    assert inserted["maintenance_detail"]["replacement_group_count"] == 1
    assert inserted["maintenance_detail"]["replaced_node_refresh"]["requested_count"] >= 1
    assert inserted["maintenance_detail"]["replaced_node_refresh"]["chunk_count"] >= 1
    assert inserted["maintenance_detail"]["replaced_edge_refresh"]["requested_count"] >= 1
    assert inserted["maintenance_detail"]["replaced_edge_refresh"]["chunk_count"] >= 1
    conn = sqlite3.connect(str(aoa_root / "graph" / "graph.sqlite3"))
    assert conn.execute("SELECT COUNT(*) FROM nodes WHERE id = ?", ("session:second-graph-source",)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM graph_sources WHERE session_id = ?", ("second-graph-source",)).fetchone()[0] >= 2
    conn.close()

    scoped_states = module.graph_source_states(aoa_root=aoa_root, target="second-graph-source")
    assert scoped_states["orphaned_count"] == 0
    assert scoped_states["out_of_scope_existing_count"] >= 2
    assert scoped_states["orphan_scope"] == "selected_sessions"
    scoped_maintenance = module.graph_maintenance(aoa_root=aoa_root, target="second-graph-source", apply=True, batch_limit=10)
    assert scoped_maintenance["ok"] is True
    assert scoped_maintenance["selected_count"] == 0
    conn = sqlite3.connect(str(aoa_root / "graph" / "graph.sqlite3"))
    assert conn.execute("SELECT COUNT(*) FROM graph_sources WHERE session_id = ?", ("first-graph-source",)).fetchone()[0] >= 2
    assert conn.execute("SELECT COUNT(*) FROM graph_sources WHERE session_id = ?", ("second-graph-source",)).fetchone()[0] >= 2
    conn.close()

    registry_path = aoa_root / module.REGISTRY_NAME
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["sessions"] = [
        item for item in registry["sessions"]
        if item.get("session_id") != "second-graph-source"
    ]
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    orphaned_states = module.graph_source_states(aoa_root=aoa_root)
    assert orphaned_states["orphaned_count"] >= 2
    assert any(item["status"] == "orphaned" and item["session_id"] == "second-graph-source" for item in orphaned_states["states"])

    removed = module.graph_maintenance(aoa_root=aoa_root, apply=True, batch_limit=10, refresh_chunk_size=2)
    assert removed["ok"] is True
    assert removed["maintenance_detail"]["refresh_chunk_size"] == 2
    assert removed["maintenance_detail"]["removed_node_refresh"]["requested_count"] >= 1
    assert removed["maintenance_detail"]["removed_edge_refresh"]["requested_count"] >= 1
    conn = sqlite3.connect(str(aoa_root / "graph" / "graph.sqlite3"))
    assert conn.execute("SELECT COUNT(*) FROM graph_sources WHERE session_id = ?", ("second-graph-source",)).fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM nodes WHERE id = ?", ("session:second-graph-source",)).fetchone()[0] == 0
    assert conn.execute(
        "SELECT COUNT(*) FROM edges WHERE source_node = ? OR target_node = ?",
        ("session:second-graph-source", "session:second-graph-source"),
    ).fetchone()[0] == 0
    conn.close()

    final_state = module.graph_store_state(aoa_root=aoa_root)
    assert final_state["status"] == "current"


def test_graph_build_store_only_rebuilds_sqlite_without_sidecar(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-26T00-35-00-store-only-graph.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-26T00:35:00Z", "type": "session_meta", "payload": {"id": "store-only-graph", "cwd": str(repo), "model": "gpt-5"}},
            {"timestamp": "2026-05-26T00:35:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Find aoa-session-memory-mcp with store-only graph."}]}},
            {"timestamp": "2026-05-26T00:35:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "The aoa-session-memory-mcp route is in the SQLite graph store."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "store-only-graph",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    full = module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)
    assert full["ok"] is True
    assert (aoa_root / "graph" / "nodes.jsonl").exists()
    assert (aoa_root / "graph" / "edges.jsonl").exists()

    store_only = module.build_session_graph(
        aoa_root=aoa_root,
        target="all",
        write=True,
        include_rows=False,
        export_sidecar=False,
    )

    assert store_only["ok"] is True
    assert store_only["sidecar_exported"] is False
    assert store_only["atomic_store_rebuild"] is True
    assert store_only["in_place_rebuild"] is False
    assert store_only["sidecar_removed"]
    assert (aoa_root / "graph" / "graph.sqlite3").exists()
    assert not (aoa_root / "graph" / "nodes.jsonl").exists()
    assert not (aoa_root / "graph" / "edges.jsonl").exists()
    assert not (aoa_root / "graph" / "index.json").exists()
    sidecar_state = module.graph_sidecar_state(aoa_root)
    assert sidecar_state["status"] == "not_exported"
    neighborhood = module.graph_neighborhood(aoa_root=aoa_root, anchor="aoa-session-memory-mcp", kind="mcp", depth=1)
    assert neighborhood["ok"] is True
    assert neighborhood["graph"]["source"] == "sqlite_graph_store"

    in_place = module.build_session_graph(
        aoa_root=aoa_root,
        target="all",
        write=True,
        include_rows=False,
        export_sidecar=False,
        atomic_store_rebuild=False,
    )
    assert in_place["ok"] is True
    assert in_place["atomic_store_rebuild"] is False
    assert in_place["in_place_rebuild"] is True
    assert not (aoa_root / "graph" / "nodes.jsonl").exists()


def test_graph_build_store_only_keeps_sidecar_when_atomic_rebuild_is_not_promoted(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-26T00-36-00-store-only-diagnostic.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-26T00:36:00Z", "type": "session_meta", "payload": {"id": "store-only-diagnostic", "cwd": str(repo), "model": "gpt-5"}},
            {"timestamp": "2026-05-26T00:36:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Keep the old sidecar if the store rebuild is diagnostic-only."}]}},
            {"timestamp": "2026-05-26T00:36:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "The graph sidecar must survive a discarded atomic rebuild."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "store-only-diagnostic",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    full = module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)
    assert full["ok"] is True

    sidecars = module.graph_sidecar_artifact_paths(aoa_root)
    sidecar_snapshots = {name: path.read_bytes() for name, path in sidecars.items()}
    manifest_path = next((aoa_root / "sessions").glob("*/session.manifest.json"))
    manifest_path.unlink()

    store_only = module.build_session_graph(
        aoa_root=aoa_root,
        target="all",
        write=True,
        include_rows=False,
        export_sidecar=False,
    )

    assert store_only["ok"] is False
    assert any("missing session manifest" in item for item in store_only["diagnostics"])
    assert store_only["atomic_store_rebuild"] is True
    assert store_only["sidecar_removed"] == []
    for name, path in sidecars.items():
        assert path.exists(), name
        assert path.read_bytes() == sidecar_snapshots[name]


def test_graph_store_reports_blocked_sources_without_requesting_maintenance(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-26T00-40-00-indexed-graph-source.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-26T00:40:00Z", "type": "session_meta", "payload": {"id": "indexed-graph-source", "cwd": str(repo), "model": "gpt-5"}},
            {"timestamp": "2026-05-26T00:40:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Create an indexed graph source."}]}},
            {"timestamp": "2026-05-26T00:40:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Indexed graph source archived."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "indexed-graph-source",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    blocked_dir = aoa_root / "sessions" / "2026-05-26__002__raw-unavailable-graph-source"
    blocked_dir.mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "session_id": "blocked-graph-source",
        "session_label": blocked_dir.name,
        "session_title": "Raw unavailable graph source",
        "archive_status": "raw_unavailable",
        "segments": [],
        "display": {"label": blocked_dir.name, "title": "Raw unavailable graph source", "date": "2026-05-26"},
    }
    (blocked_dir / "session.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    registry_path = aoa_root / module.REGISTRY_NAME
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["sessions"].append(
        {
            "session_id": "blocked-graph-source",
            "session_label": blocked_dir.name,
            "session_title": "Raw unavailable graph source",
            "path": str(blocked_dir),
            "archive_status": "raw_unavailable",
            "display": manifest["display"],
        }
    )
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    built = module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)
    assert built["ok"] is True
    state = module.graph_store_state(aoa_root=aoa_root)
    assert state["status"] == "current_with_blocked_sources"
    assert state["needs_maintenance"] is False
    assert state["needs_full_rebuild"] is False
    assert state["source_state"]["blocked_count"] == 1

    gates = module.graph_freshness_gates(aoa_root=aoa_root, ref_sample_limit=20)
    assert gates["graph_store"]["status"] == "current_with_blocked_sources"
    assert next(gate for gate in gates["gates"] if gate["name"] == "graph_store_current")["ok"] is True
    assert gates["needs_graph_maintenance"] is False


def test_raw_unavailable_recovery_audit_retires_helper_sources(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-27T00-00-00-indexed-retired-base.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-27T00:00:00Z", "type": "session_meta", "payload": {"id": "retired-base", "cwd": str(repo), "model": "gpt-5"}},
            {"timestamp": "2026-05-27T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Create base graph nodes."}]}},
            {"timestamp": "2026-05-27T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Base graph nodes created."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "retired-base",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    def add_raw_unavailable(session_id: str, label: str, prompt: str, assistant: str = "") -> None:
        session_dir = aoa_root / "sessions" / label
        session_dir.mkdir(parents=True)
        manifest = {
            "schema_version": 1,
            "session_id": session_id,
            "session_label": label,
            "session_title": label,
            "created_at": "2026-05-27T00:10:00Z",
            "updated_at": "2026-05-27T00:10:01Z",
            "archive_status": "raw_unavailable",
            "source": {"transcript_path": None, "cwd": str(repo)},
            "raw": {"path": None, "source_path": None},
            "segments": [],
            "display": {"label": label, "title": label, "date": "2026-05-27"},
        }
        (session_dir / "session.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        write_jsonl(
            session_dir / "hooks" / "events.jsonl",
            [
                {"schema_version": 1, "timestamp": "2026-05-27T00:10:00Z", "hook_event_name": "UserPromptSubmit", "event": {"session_id": session_id, "prompt": prompt, "transcript_path": None, "cwd": str(repo)}},
                {"schema_version": 1, "timestamp": "2026-05-27T00:10:01Z", "hook_event_name": "Stop", "event": {"session_id": session_id, "last_assistant_message": assistant, "transcript_path": None, "cwd": str(repo)}},
            ],
        )
        registry_path = aoa_root / module.REGISTRY_NAME
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["sessions"].append(
            {
                "session_id": session_id,
                "session_label": label,
                "session_title": label,
                "path": str(session_dir),
                "archive_status": "raw_unavailable",
                "display": manifest["display"],
            }
        )
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    add_raw_unavailable(
        "retired-memory-writer-source",
        "2026-05-27__002__memory-writer-helper",
        "## Memory Writing Agent: Phase 2\n\nYou are a Memory Writing Agent.",
    )
    add_raw_unavailable(
        "retired-title-helper-source",
        "2026-05-27__003__title-helper",
        "You are a helpful assistant. You will be presented with a user prompt, and your job is to provide a short title for a task.",
        '{"title":"Check title"}',
    )

    built = module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)
    assert built["ok"] is True
    before = module.graph_store_state(aoa_root=aoa_root)
    assert before["status"] == "current_with_blocked_sources"
    assert before["source_state"]["blocked_count"] == 2

    audit = module.raw_unavailable_recovery_audit(aoa_root=aoa_root, write_ledger=True, write_report=True)
    assert audit["source_count"] == 2
    assert audit["classification_counts"] == {"memory_writer": 1, "title_helper": 1}
    assert Path(audit["report_json"]).exists()
    ledger = module.read_graph_source_state_ledger(aoa_root)
    assert ledger["sources"]["session:retired-memory-writer-source"]["status"] == "tombstoned_evidence_source"
    assert ledger["sources"]["session:retired-title-helper-source"]["classification"] == "title_helper"

    states = module.graph_source_states(aoa_root=aoa_root)
    assert states["blocked_count"] == 0
    assert states["retired_count"] == 2
    after = module.graph_store_state(aoa_root=aoa_root)
    assert after["status"] == "current_with_retired_sources"
    assert after["needs_maintenance"] is False


def test_graph_maintenance_queue_drives_hot_gate_and_bounded_update(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-27T00-20-00-queue-graph-source.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-27T00:20:00Z", "type": "session_meta", "payload": {"id": "queue-graph-source", "cwd": str(repo), "model": "gpt-5"}},
            {"timestamp": "2026-05-27T00:20:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Create queue alpha."}]}},
            {"timestamp": "2026-05-27T00:20:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Queue alpha created."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "queue-graph-source",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    session_dir = aoa_root / "sessions" / "2026-05-27__001__create-queue-alpha"
    segment_index_path = next((session_dir / "segments").glob("*.index.json"))
    built = module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)
    assert built["ok"] is True

    segment_index = json.loads(segment_index_path.read_text(encoding="utf-8"))
    segment_index["events"][0].setdefault("facets", {}).setdefault("route_signals", []).append(
        {"layer": "entity", "key": "queue_beta", "route_signal": "entity:queue_beta"}
    )
    segment_index_path.write_text(json.dumps(segment_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.utime(segment_index_path, None)

    planned = module.graph_maintenance(aoa_root=aoa_root, apply=False, write_queue=True, write_ledger=True)
    assert planned["ok"] is True
    assert planned["queue_update"]["queued_count"] >= 1
    hot_dirty = module.route_cache_freshness_gates(aoa_root=aoa_root)
    assert hot_dirty["graph_store"]["queue"]["queued_count"] >= 1
    assert hot_dirty["needs_graph_maintenance"] is True

    maintained = module.graph_maintenance(
        aoa_root=aoa_root,
        apply=True,
        use_queue=True,
        write_queue=True,
        write_ledger=True,
        batch_limit=5,
    )
    assert maintained["ok"] is True
    assert maintained["use_queue"] is True
    assert maintained["queue_update"]["queued_count"] == 0
    hot_clean = module.route_cache_freshness_gates(aoa_root=aoa_root)
    assert hot_clean["needs_graph_maintenance"] is False


def test_route_cache_hot_gate_uses_cached_states_without_source_scan(tmp_path: Path, monkeypatch: Any) -> None:
    aoa_root = tmp_path / ".aoa"
    aoa_root.mkdir(parents=True)

    def fail_source_scan(*_: Any, **__: Any) -> Any:
        raise AssertionError("broad hot route-cache gate must not scan session sources")

    monkeypatch.setattr(module, "chronological_session_records", fail_source_scan)
    monkeypatch.setattr(module, "latest_index_source_mtime", fail_source_scan)
    monkeypatch.setattr(module, "route_index_drift_records", fail_source_scan)
    monkeypatch.setattr(
        module,
        "sqlite_search_index_hot_state",
        lambda _aoa_root: {
            "status": "current",
            "needs_refresh": False,
            "indexed_session_state_count": 7,
            "diagnostics": [],
        },
    )
    monkeypatch.setattr(
        module,
        "atlas_index_hot_state",
        lambda _aoa_root: {
            "status": "current",
            "needs_refresh": False,
            "projection_session_count": 7,
            "diagnostics": [],
        },
    )
    monkeypatch.setattr(
        module,
        "graph_store_hot_state",
        lambda _aoa_root: {
            "status": "current_with_retired_sources",
            "needs_maintenance": False,
            "needs_full_rebuild": False,
            "diagnostics": [],
        },
    )
    monkeypatch.setattr(
        module,
        "entity_registry_maintenance_status",
        lambda _aoa_root: {"status": "current", "needs_maintenance": False, "entity_count": 7, "diagnostics": []},
    )

    payload = module.route_cache_freshness_gates(aoa_root=aoa_root)

    assert payload["ok"] is True
    assert payload["source_scan"] is False
    assert payload["truth_status"] == "hot_route_cache_cached_state_no_source_scan"
    assert payload["selection_source"] == "cached_projection_state"
    assert payload["selected_count"] == 7


def test_route_cache_hot_gate_scoped_filters_scan_selected_records(tmp_path: Path, monkeypatch: Any) -> None:
    aoa_root = tmp_path / ".aoa"
    session_dir = aoa_root / "sessions" / "2026-06-15__001__scoped-hot-gate"
    session_dir.mkdir(parents=True)
    record = {
        "session_id": "scoped-hot-gate",
        "session_label": "2026-06-15__001__scoped-hot-gate",
        "path": str(session_dir),
    }
    calls: dict[str, Any] = {}

    def fake_chronological_records(_aoa_root: Path, *, since: str | None = None, until: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        calls["chronological"] = {"since": since, "until": until, "limit": limit}
        return [record]

    def fail_hot_state(*_: Any, **__: Any) -> Any:
        raise AssertionError("scoped hot gate must not use all-archive cached state")

    monkeypatch.setattr(module, "chronological_session_records", fake_chronological_records)
    monkeypatch.setattr(module, "sqlite_search_index_hot_state", fail_hot_state)
    monkeypatch.setattr(module, "atlas_index_hot_state", fail_hot_state)
    monkeypatch.setattr(module, "latest_index_source_mtime", lambda _aoa_root, records: (12.0, [records[0]["path"]]))
    monkeypatch.setattr(module, "route_index_drift_records", lambda records: [])
    monkeypatch.setattr(module, "search_projection_fingerprints_for_records", lambda records: [{"session_id": records[0]["session_id"]}])
    monkeypatch.setattr(
        module,
        "sqlite_search_index_state",
        lambda _aoa_root, _mtime, records, projection_fingerprints=None: {
            "status": "current",
            "needs_refresh": False,
            "selected_session_state_count": len(records),
            "projection_fingerprints": projection_fingerprints,
            "diagnostics": [],
        },
    )
    monkeypatch.setattr(
        module,
        "atlas_index_state",
        lambda _aoa_root, _mtime, records, projection_fingerprints=None: {
            "status": "current",
            "needs_refresh": False,
            "projection_session_count": len(records),
            "diagnostics": [],
        },
    )
    monkeypatch.setattr(
        module,
        "graph_store_hot_state",
        lambda _aoa_root: {
            "status": "current_with_retired_sources",
            "needs_maintenance": False,
            "needs_full_rebuild": False,
            "diagnostics": [],
        },
    )
    monkeypatch.setattr(
        module,
        "entity_registry_maintenance_status",
        lambda _aoa_root: {"status": "current", "needs_maintenance": False, "entity_count": 1, "diagnostics": []},
    )

    payload = module.route_cache_freshness_gates(aoa_root=aoa_root, since="2026-06-15", limit=1)

    assert calls["chronological"] == {"since": "2026-06-15", "until": None, "limit": 1}
    assert payload["ok"] is True
    assert payload["source_scan"] is True
    assert payload["truth_status"] == "hot_route_cache_bounded_projection_scan"
    assert payload["selection_source"] == "target_filters"
    assert payload["selection_scope"] == {"mode": "target_filters", "source_filters_applied": True}
    assert payload["selected_count"] == 1


def test_graph_maintenance_use_queue_empty_is_noop_without_source_scan(tmp_path: Path, monkeypatch: Any) -> None:
    aoa_root = tmp_path / ".aoa"
    (aoa_root / "graph").mkdir(parents=True)
    module.write_graph_maintenance_queue(aoa_root, {"items": {}})

    def fail_source_scan(*_: Any, **__: Any) -> Any:
        raise AssertionError("empty queue pass must not scan graph sources")

    monkeypatch.setattr(module, "graph_source_states", fail_source_scan)
    monkeypatch.setattr(
        module,
        "graph_store_hot_state",
        lambda _aoa_root: {
            "status": "current_with_retired_sources",
            "needs_maintenance": False,
            "needs_full_rebuild": False,
            "source_count": 5,
            "ledger": {
                "source_count": 6,
                "status_counts": {"clean": 5, "retired_partial_evidence": 1},
                "retired_count": 1,
                "actionable_count": 0,
            },
            "queue": {"queued_count": 0},
            "diagnostics": [],
        },
    )

    payload = module.graph_maintenance(
        aoa_root=aoa_root,
        apply=True,
        use_queue=True,
        write_queue=True,
        write_ledger=True,
        batch_limit=5,
    )

    assert payload["ok"] is True
    assert payload["mutates"] is False
    assert payload["state_window"] == "queue_empty_hot_state"
    assert payload["selected_count"] == 0
    assert payload["remaining_count"] == 0
    assert payload["source_state"]["retired_count"] == 1
    assert payload["source_state"]["partial_evidence_count"] == 1
    assert payload["maintenance_detail"]["selection_strategy"] == "queue_empty_no_source_scan"


def test_graph_hot_state_defers_recent_live_queue_items(tmp_path: Path, monkeypatch: Any) -> None:
    aoa_root = tmp_path / ".aoa"
    graph_root = aoa_root / "graph"
    graph_root.mkdir(parents=True)
    (graph_root / "graph.sqlite3").write_text("", encoding="utf-8")
    session_dir = aoa_root / "sessions" / "2026-06-15__001__live"
    session_dir.mkdir(parents=True)
    (session_dir / "raw").mkdir(parents=True)
    codex_transcript = tmp_path / ".codex" / "sessions" / "2026" / "06" / "15" / "rollout-2026-06-15T00-00-00-live.jsonl"
    codex_transcript.parent.mkdir(parents=True)
    codex_transcript.write_text("{}\n", encoding="utf-8")
    source_path = tmp_path / "live-source.index.json"
    source_path.write_text("{}", encoding="utf-8")
    session_index_path = session_dir / module.SESSION_INDEX_JSON
    session_index_path.write_text("{}", encoding="utf-8")
    (session_dir / "raw" / module.RAW_SOURCE_JSON).write_text(
        json.dumps({"source_path": str(codex_transcript)}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    now_ts = time.time()
    os.utime(codex_transcript, (now_ts, now_ts))
    os.utime(source_path, (now_ts, now_ts))
    os.utime(session_index_path, (now_ts, now_ts))
    module.write_graph_maintenance_queue(
        aoa_root,
        {
            "items": {
                "segment:live:000": {
                    "source_key": "segment:live:000",
                    "source_type": "segment",
                    "session_id": "live",
                    "session_label": "live session",
                    "session_dir": str(session_dir),
                    "source_path": str(source_path),
                    "status": "dirty",
                },
                "segment:live:001": {
                    "source_key": "segment:live:001",
                    "source_type": "segment",
                    "session_id": "live",
                    "session_label": "live session",
                    "session_dir": str(session_dir),
                    "source_path": str(session_dir / "segments" / "001__compaction-to-latest.index.json"),
                    "status": "missing",
                }
            }
        },
    )

    class FakeStore:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def metadata(self) -> dict[str, str]:
            return {
                "graph_store_schema_version": str(module.GRAPH_STORE_SCHEMA_VERSION),
                "graph_schema_version": str(module.GRAPH_SCHEMA_VERSION),
            }

        def state_counts(self) -> dict[str, int]:
            raise AssertionError("hot graph state must not count aggregate nodes or edges")

        def source_count(self) -> int:
            return 1

        def close(self) -> None:
            pass

    monkeypatch.setattr(module, "GraphSqliteStore", FakeStore)

    state = module.graph_store_hot_state(aoa_root)

    assert state["status"] == "current_with_deferred_live_sources"
    assert state["needs_maintenance"] is False
    assert state["queue"]["queued_count"] == 2
    assert state["queue"]["actionable_count"] == 0
    assert state["queue"]["deferred_live_source_count"] == 2


def test_graph_hot_state_detects_stale_graph_source_versions_without_source_scan(tmp_path: Path, monkeypatch: Any) -> None:
    aoa_root = tmp_path / ".aoa"
    session_dir = aoa_root / "sessions" / "2026-06-17__001__goal-hot-drift"
    session_dir.mkdir(parents=True)
    source_path = session_dir / module.SESSION_INDEX_JSON
    source_path.write_text("{}", encoding="utf-8")
    source_key = "session:goal-hot-drift"
    store = module.GraphSqliteStore(aoa_root)
    try:
        store.replace_source(
            {
                "source": {
                    "source_key": source_key,
                    "source_type": "session",
                    "session_id": "goal-hot-drift",
                    "session_label": "2026-06-17__001__goal-hot-drift",
                    "segment_id": "",
                    "source_path": str(source_path),
                    "source_paths": [str(source_path)],
                    "source_sha": "fresh-session-index-sha",
                    "source_mtime": source_path.stat().st_mtime,
                    "graph_schema_version": module.GRAPH_SCHEMA_VERSION,
                    "graph_store_schema_version": module.GRAPH_STORE_SCHEMA_VERSION,
                    "route_signal_classifier_version": module.ROUTE_SIGNAL_CLASSIFIER_VERSION,
                },
                "nodes": [],
                "edges": [],
            }
        )
        store.conn.execute(
            "UPDATE graph_sources SET route_signal_classifier_version = ? WHERE source_key = ?",
            (module.ROUTE_SIGNAL_CLASSIFIER_VERSION - 1, source_key),
        )
        store.conn.commit()
    finally:
        store.close()
    module.write_graph_source_state_ledger(
        aoa_root,
        {
            "sources": {
                source_key: {
                    "source_key": source_key,
                    "status": "clean",
                    "source_path": str(source_path),
                    "session_id": "goal-hot-drift",
                    "session_label": "2026-06-17__001__goal-hot-drift",
                }
            }
        },
    )
    module.write_graph_maintenance_queue(aoa_root, {"items": {}})

    def fail_source_scan(*_: Any, **__: Any) -> Any:
        raise AssertionError("hot graph source version gate must not scan session sources")

    monkeypatch.setattr(module, "chronological_session_records", fail_source_scan)
    monkeypatch.setattr(module, "latest_index_source_mtime", fail_source_scan)
    monkeypatch.setattr(module, "route_index_drift_records", fail_source_scan)
    monkeypatch.setattr(
        module,
        "sqlite_search_index_hot_state",
        lambda _aoa_root: {
            "status": "current",
            "needs_refresh": False,
            "indexed_session_state_count": 1,
            "diagnostics": [],
        },
    )
    monkeypatch.setattr(
        module,
        "atlas_index_hot_state",
        lambda _aoa_root: {
            "status": "current",
            "needs_refresh": False,
            "projection_session_count": 1,
            "diagnostics": [],
        },
    )

    state = module.graph_store_hot_state(aoa_root)
    summary = module.graph_hot_source_state_summary(aoa_root, state)
    payload = module.route_cache_freshness_gates(aoa_root=aoa_root)

    assert state["status"] == "dirty"
    assert state["needs_maintenance"] is True
    assert state["source_version_state"]["version_mismatch_source_count"] == 1
    assert state["source_version_state"]["reason_group_counts"] == {"route_signal_classifier_mismatch": 1}
    assert summary["dirty_count"] == 1
    assert summary["maintenance_recommendation"]["route"] == "bounded_graph_maintenance"
    assert payload["ok"] is False
    assert payload["needs_graph_maintenance"] is True
    assert payload["graph_store"]["source_version_state"]["samples"][0]["source_key"] == source_key


def test_route_signal_classifier_avoids_lifecycle_and_failure_substring_noise() -> None:
    task_started = {
        "timestamp": "2026-05-24T00:00:00Z",
        "type": "event_msg",
        "payload": {"type": "task_started", "model_context_window": 400000},
    }
    event = module.classify_raw_event(json.dumps(task_started), task_started, 1)
    signals = {f"{signal['layer']}:{signal['key']}" for signal in event.facets.get("route_signals", [])}

    assert event.event_type == "HOOK_EVENT"
    assert "authority_surface:source" not in signals
    assert "mutation_surface:hooks" not in signals
    assert "index_health:findability_signal" not in signals

    session_meta = {
        "timestamp": "2026-05-24T00:00:01Z",
        "type": "session_meta",
        "payload": {"id": "session-id-is-not-a-tool-correlation", "cwd": "/srv/AbyssOS", "model": "gpt-5"},
    }
    session_meta_event = module.classify_raw_event(json.dumps(session_meta), session_meta, 2)
    session_meta_signals = {f"{signal['layer']}:{signal['key']}" for signal in session_meta_event.facets.get("route_signals", [])}

    assert session_meta_event.event_type == "SESSION_META"
    assert session_meta_event.correlation_id is None
    assert "correlation:tool_call_output_link" not in session_meta_signals

    developer_context = {
        "timestamp": "2026-05-24T00:00:02Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "developer",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Tooling context mentions GitHub, MEMORY.md, skills/foo/SKILL.md, "
                        "README.md, config/settings.json, scripts/tool.py, and connectors."
                    ),
                }
            ],
        },
    }
    developer_event = module.classify_raw_event(json.dumps(developer_context), developer_context, 3)
    developer_signals = {f"{signal['layer']}:{signal['key']}" for signal in developer_event.facets.get("route_signals", [])}

    assert developer_event.event_type == "CONTEXT_STATE"
    assert "authority_surface:source" not in developer_signals
    assert "authority_surface:external_connector_snapshot" not in developer_signals
    assert "external_snapshot:github" not in developer_signals
    assert "memory_provenance:codex_memories" not in developer_signals
    assert "memory_provenance:memory_general" not in developer_signals
    assert "memory_provenance:skill_memory" not in developer_signals
    assert "mutation_surface:docs" not in developer_signals
    assert "mutation_surface:source_code" not in developer_signals

    project_card = {
        "timestamp": "2026-05-24T00:00:02.500Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                        "text": (
                            "# AGENTS.md instructions\n"
                            "This ecosystem mentions continuity, memory, reflective revision, "
                            "and growth, but this is route-card prose rather than an archive request."
                        ),
                }
            ],
        },
    }
    project_card_event = module.classify_raw_event(json.dumps(project_card), project_card, 4)
    project_card_signals = {f"{signal['layer']}:{signal['key']}" for signal in project_card_event.facets.get("route_signals", [])}

    assert project_card_event.event_type == "USER_INTENT"
    assert "memory_provenance:memory_general" not in project_card_signals

    memory_request = {
        "timestamp": "2026-05-24T00:00:02.750Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Use memory for this pass and cite memory-derived facts."}],
        },
    }
    memory_request_event = module.classify_raw_event(json.dumps(memory_request), memory_request, 5)
    memory_request_signals = {f"{signal['layer']}:{signal['key']}" for signal in memory_request_event.facets.get("route_signals", [])}

    assert "memory_provenance:memory_general" in memory_request_signals
    assert "memory_provenance:cited" in memory_request_signals

    prompt = {
        "timestamp": "2026-05-24T00:00:03Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Review the hook pack snapshot seed without changing files."}],
        },
    }
    prompt_event = module.classify_raw_event(json.dumps(prompt), prompt, 6)
    prompt_signals = {f"{signal['layer']}:{signal['key']}" for signal in prompt_event.facets["route_signals"]}

    assert "hook_health:stop" not in prompt_signals

    stop_line_prompt = {
        "timestamp": "2026-05-24T00:00:04Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Seed mentions recovery-note hooks and Agon stop-lines."}],
        },
    }
    stop_line_event = module.classify_raw_event(json.dumps(stop_line_prompt), stop_line_prompt, 7)
    stop_line_signals = {f"{signal['layer']}:{signal['key']}" for signal in stop_line_event.facets["route_signals"]}

    assert "hook_health:stop" not in stop_line_signals

    source_output = {
        "timestamp": "2026-05-24T00:00:04.500Z",
        "type": "event_msg",
        "payload": {
            "type": "exec_command_end",
            "call_id": "call-source-output",
            "command": ["/usr/bin/zsh", "-lc", "sed -n '100,155p' src/aoa_sdk/recurrence/rollout.py"],
            "cwd": "/srv/aoa-sdk",
            "parsed_cmd": [{"type": "read", "cmd": "sed -n '100,155p' src/aoa_sdk/recurrence/rollout.py", "path": "src/aoa_sdk/recurrence/rollout.py"}],
            "aggregated_output": (
                'notes="Use this when SessionStart, UserPromptSubmit, or Stop recurrence snippets are missing or stale." '
                'notes="Use this when the session-stop path stops producing review queues."'
            ),
            "exit_code": 0,
            "status": "completed",
        },
    }
    source_output_event = module.classify_raw_event(json.dumps(source_output), source_output, 8)
    source_output_signals = {f"{signal['layer']}:{signal['key']}" for signal in source_output_event.facets["route_signals"]}

    assert source_output_event.event_type == "COMMAND_OUTPUT"
    assert "hook_health:stop" not in source_output_signals

    hook_discussion = {
        "timestamp": "2026-05-24T00:00:04.575Z",
        "type": "event_msg",
        "payload": {
            "type": "agent_message",
            "message": "Improve hook reports and stop/user_prompt_submit logs after this trace replay.",
            "phase": "final_answer",
        },
    }
    hook_discussion_event = module.classify_raw_event(json.dumps(hook_discussion), hook_discussion, 9)
    hook_discussion_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in hook_discussion_event.facets["route_signals"]
    }

    assert "hook_health:stop" not in hook_discussion_signals
    assert "hook_health:userpromptsubmit" not in hook_discussion_signals

    local_read_output = {
        "timestamp": "2026-05-24T00:00:04.650Z",
        "type": "event_msg",
        "payload": {
            "type": "exec_command_end",
            "call_id": "call-local-read",
            "command": ["/usr/bin/zsh", "-lc", "sed -n '1,220p' /srv/8Dionysus/README.md"],
            "cwd": "/srv",
            "parsed_cmd": [{"type": "read", "cmd": "sed -n '1,220p' /srv/8Dionysus/README.md", "path": "/srv/8Dionysus/README.md"}],
            "aggregated_output": "This local README mentions GitHub, Gmail, Google Drive, calendar, web search, browser, snapshot, stale risk.",
            "exit_code": 0,
            "status": "completed",
        },
    }
    local_read_event = module.classify_raw_event(json.dumps(local_read_output), local_read_output, 9)
    local_read_signals = {f"{signal['layer']}:{signal['key']}" for signal in local_read_event.facets["route_signals"]}

    assert local_read_event.event_type == "COMMAND_OUTPUT"
    assert "external_snapshot:github" not in local_read_signals
    assert "external_snapshot:gmail" not in local_read_signals
    assert "external_snapshot:google_drive" not in local_read_signals
    assert "external_snapshot:web" not in local_read_signals
    assert "freshness_drift:external_state_required" not in local_read_signals

    github_connector_call = {
        "timestamp": "2026-05-24T00:00:04.700Z",
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "github.get_pull_request",
            "call_id": "call-github",
            "arguments": json.dumps({"owner": "8Dionysus", "repo": "aoa-session-memory", "pullNumber": 1}),
        },
    }
    github_connector_event = module.classify_raw_event(json.dumps(github_connector_call), github_connector_call, 10)
    github_connector_signals = {f"{signal['layer']}:{signal['key']}" for signal in github_connector_event.facets["route_signals"]}

    assert "external_snapshot:app_connector" in github_connector_signals
    assert "external_snapshot:github" in github_connector_signals
    assert "freshness_drift:external_state_required" in github_connector_signals

    gh_command = {
        "timestamp": "2026-05-24T00:00:04.800Z",
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "exec_command",
            "call_id": "call-gh",
            "arguments": json.dumps({"cmd": "gh pr view 1 --json title,url", "workdir": "/srv/AbyssOS"}),
        },
    }
    gh_command_event = module.classify_raw_event(json.dumps(gh_command), gh_command, 11)
    gh_command_signals = {f"{signal['layer']}:{signal['key']}" for signal in gh_command_event.facets["route_signals"]}

    assert "external_snapshot:github" in gh_command_signals
    assert "freshness_drift:external_state_required" in gh_command_signals

    shell_redirect_command = {
        "timestamp": "2026-05-24T00:00:04.900Z",
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "exec_command",
            "call_id": "call-redirect",
            "arguments": json.dumps({"cmd": "rg --files /srv/aoa-sdk 2>/dev/null", "workdir": "/srv"}),
        },
    }
    shell_redirect_event = module.classify_raw_event(json.dumps(shell_redirect_command), shell_redirect_command, 12)
    shell_redirect_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in shell_redirect_event.facets["route_signals"]
    }

    assert "path:dev_null" not in shell_redirect_signals
    assert "path:srv_aoa_sdk" in shell_redirect_signals

    git_ref_output = {
        "timestamp": "2026-05-24T00:00:04.925Z",
        "type": "response_item",
        "payload": {
            "type": "function_call_output",
            "call_id": "call-required-check-audit",
            "output": (
                "Process exited with code 0\n"
                "Output:\n"
                "[info] target_repo=/srv/aoa-sdk\n"
                "[info] compare_ref=origin/main\n"
                "[info] merge_base=main/origin/main\n"
                "[info] diff_range=main...origin/main\n"
                "[info] name_only_range=origin/main..HEAD\n"
            ),
        },
    }
    git_ref_event = module.classify_raw_event(json.dumps(git_ref_output), git_ref_output, 13)
    git_ref_signals = {f"{signal['layer']}:{signal['key']}" for signal in git_ref_event.facets["route_signals"]}

    assert "path:srv_aoa_sdk" in git_ref_signals
    assert "path:origin_main" not in git_ref_signals
    assert "path:main_origin_main" not in git_ref_signals
    assert "path:origin_main_head" not in git_ref_signals

    output = {
        "timestamp": "2026-05-24T00:00:05Z",
        "type": "response_item",
        "payload": {
            "type": "function_call_output",
            "call_id": "call-ok",
            "output": "Process exited with code 0\nOutput:\nREADME.md: mentions failed checks as documentation text\n",
        },
    }
    output_event = module.classify_raw_event(json.dumps(output), output, 12)
    output_signals = {f"{signal['layer']}:{signal['key']}" for signal in output_event.facets["route_signals"]}

    assert output_event.event_type == "COMMAND_OUTPUT"
    assert output_event.outcome == "succeeded"
    assert "failure_mode:generic_failure" not in output_signals

    exit_code_doc_output = {
        "timestamp": "2026-05-24T00:00:05.075Z",
        "type": "event_msg",
        "payload": {
            "type": "exec_command_end",
            "call_id": "call-exit-code-doc",
            "command": ["/usr/bin/zsh", "-lc", "sed -n '1,220p' scripts/validate_recurrence_manifests.py"],
            "cwd": "/srv/aoa-sdk",
            "parsed_cmd": [
                {
                    "type": "read",
                    "cmd": "sed -n '1,220p' scripts/validate_recurrence_manifests.py",
                    "path": "scripts/validate_recurrence_manifests.py",
                }
            ],
            "aggregated_output": "Use exit code 30 for medium diagnostics. return exit_code",
            "exit_code": 0,
            "status": "completed",
        },
    }
    exit_code_doc_event = module.classify_raw_event(json.dumps(exit_code_doc_output), exit_code_doc_output, 13)
    exit_code_doc_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in exit_code_doc_event.facets["route_signals"]
    }

    assert exit_code_doc_event.event_type == "COMMAND_OUTPUT"
    assert exit_code_doc_event.outcome == "succeeded"
    assert "verification_state:failed_or_unverified" not in exit_code_doc_signals
    assert "failure_mode:generic_failure" not in exit_code_doc_signals

    failed_pytest_output = {
        "timestamp": "2026-05-24T00:00:05.125Z",
        "type": "response_item",
        "payload": {
            "type": "function_call_output",
            "call_id": "call-failed-pytest",
            "output": "Process exited with code 1\nOutput:\nFFF [100%]\n3 failed, 7 passed\n",
        },
    }
    failed_pytest_event = module.classify_raw_event(json.dumps(failed_pytest_output), failed_pytest_output, 13)
    failed_pytest_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in failed_pytest_event.facets["route_signals"]
    }

    assert "delivery_state:tests_green" not in failed_pytest_signals
    assert "verification_state:green_proof" not in failed_pytest_signals
    assert "verification_state:success_observed" not in failed_pytest_signals
    assert "verification_state:failed_or_unverified" in failed_pytest_signals
    assert "failure_mode:test_failure" in failed_pytest_signals

    token_accounting_output = {
        "timestamp": "2026-05-24T00:00:05.250Z",
        "type": "event_msg",
        "payload": {
            "type": "exec_command_end",
            "call_id": "call-token-count",
            "command": ["/usr/bin/zsh", "-lc", "ls -1 /srv"],
            "cwd": "/srv",
            "aggregated_output": "Original token count: 838\nOutput:\n/srv/abyss-stack/Configs/config-templates/README.md\n",
            "exit_code": 0,
            "status": "completed",
        },
    }
    token_accounting_event = module.classify_raw_event(json.dumps(token_accounting_output), token_accounting_output, 13)
    token_accounting_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in token_accounting_event.facets["route_signals"]
    }

    assert token_accounting_event.event_type == "COMMAND_OUTPUT"
    assert "access_boundary:secret_or_privacy_boundary" not in token_accounting_signals

    raw_path_doc_output = {
        "timestamp": "2026-05-24T00:00:05.375Z",
        "type": "event_msg",
        "payload": {
            "type": "exec_command_end",
            "call_id": "call-raw-path-doc",
            "command": ["/usr/bin/zsh", "-lc", "sed -n '1,220p' docs/versioning.md"],
            "cwd": "/srv/aoa-sdk",
            "parsed_cmd": [{"type": "read", "cmd": "sed -n '1,220p' docs/versioning.md", "path": "docs/versioning.md"}],
            "aggregated_output": "Routed reads must not fall back to raw path loads.",
            "exit_code": 0,
            "status": "completed",
        },
    }
    raw_path_doc_event = module.classify_raw_event(json.dumps(raw_path_doc_output), raw_path_doc_output, 14)
    raw_path_doc_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in raw_path_doc_event.facets["route_signals"]
    }

    assert raw_path_doc_event.event_type == "COMMAND_OUTPUT"
    assert "index_health:findability_signal" not in raw_path_doc_signals

    archive_repair_doc_output = {
        "timestamp": "2026-05-24T00:00:05.400Z",
        "type": "event_msg",
        "payload": {
            "type": "exec_command_end",
            "call_id": "call-archive-repair-doc",
            "command": ["/usr/bin/zsh", "-lc", "sed -n '1,140p' quests/AOA-PB-Q-0014.yaml"],
            "cwd": "/srv/aoa-playbooks",
            "parsed_cmd": [
                {"type": "read", "cmd": "sed -n '1,140p' quests/AOA-PB-Q-0014.yaml", "path": "quests/AOA-PB-Q-0014.yaml"}
            ],
            "aggregated_output": "Do not promote one archive repair session into a new playbook family.",
            "exit_code": 0,
            "status": "completed",
        },
    }
    archive_repair_doc_event = module.classify_raw_event(json.dumps(archive_repair_doc_output), archive_repair_doc_output, 15)
    archive_repair_doc_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in archive_repair_doc_event.facets["route_signals"]
    }

    assert "index_health:findability_signal" not in archive_repair_doc_signals

    reindex_command = {
        "timestamp": "2026-05-24T00:00:05.425Z",
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "exec_command",
            "call_id": "call-reindex",
            "arguments": json.dumps(
                {
                    "cmd": "python3 scripts/aoa_session_memory.py reindex-sessions all --write-report",
                    "workdir": "/srv/AbyssOS/.aoa",
                }
            ),
        },
    }
    reindex_event = module.classify_raw_event(json.dumps(reindex_command), reindex_command, 16)
    reindex_signals = {f"{signal['layer']}:{signal['key']}" for signal in reindex_event.facets["route_signals"]}

    assert "index_health:findability_signal" in reindex_signals

    secret_boundary_prompt = {
        "timestamp": "2026-05-24T00:00:05.500Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Do not export secrets, credentials, or access tokens."}],
        },
    }
    secret_boundary_event = module.classify_raw_event(json.dumps(secret_boundary_prompt), secret_boundary_prompt, 17)
    secret_boundary_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in secret_boundary_event.facets["route_signals"]
    }

    assert "access_boundary:secret_or_privacy_boundary" in secret_boundary_signals

    landed_status_prompt = {
        "timestamp": "2026-05-24T00:00:05.750Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Current landed surface appears only in aoa-sdk."}],
        },
    }
    landed_status_event = module.classify_raw_event(json.dumps(landed_status_prompt), landed_status_prompt, 18)
    landed_status_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in landed_status_event.facets["route_signals"]
    }

    assert "operator_preference:landed_slices" not in landed_status_signals

    landed_subagent_status_prompt = {
        "timestamp": "2026-05-24T00:00:05.875Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "<subagent_notification>\n"
                        '{"status":{"completed":"Remaining risk must be read as only the cited landed slices."}}\n'
                        "</subagent_notification>"
                    ),
                }
            ],
        },
    }
    landed_subagent_status_event = module.classify_raw_event(
        json.dumps(landed_subagent_status_prompt), landed_subagent_status_prompt, 19
    )
    landed_subagent_status_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in landed_subagent_status_event.facets["route_signals"]
    }

    assert "operator_preference:landed_slices" not in landed_subagent_status_signals

    landed_slices_prompt = {
        "timestamp": "2026-05-24T00:00:06Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Веди это узкими landed-срезами."}],
        },
    }
    landed_slices_event = module.classify_raw_event(json.dumps(landed_slices_prompt), landed_slices_prompt, 20)
    landed_slices_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in landed_slices_event.facets["route_signals"]
    }

    assert "operator_preference:landed_slices" in landed_slices_signals

    skill_alias_prompt = {
        "timestamp": "2026-05-24T00:00:06.250Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": "Use aoa_memo_writeback and inspect skills/aoa-memo-writeback/SKILL.md.",
                }
            ],
        },
    }
    skill_alias_event = module.classify_raw_event(json.dumps(skill_alias_prompt), skill_alias_prompt, 21)
    skill_alias_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in skill_alias_event.facets["route_signals"]
    }

    assert "entity:aoa_memo_writeback" in skill_alias_signals
    assert "skill:aoa_memo_writeback" in skill_alias_signals

    operational_entity_prompt = {
        "timestamp": "2026-05-24T00:00:06.375Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": (
                        "Use skill aoa-decision and skills/aoa-session-search/SKILL.md. "
                        "Audit aoa-session-memory-mcp, UserPromptSubmit hook, exec_command tool, "
                        "OpenAI Responses API, plugin://gmail@openai-curated, Codex sub-agent, "
                        "scripts/validate_stack.py validator, tests/test_session_memory.py with pytest, "
                        "inspect-ai eval in evals/session-quality.yaml, git commit and gh pr, "
                        "playbooks/session-audit.md playbook, techniques/entity-routing.md technique, "
                        "mechanics/route-maintenance.md mechanic, GraphRAG graph nodes, "
                        "imagegen skill, and aoa-session-memory memory."
                    ),
                }
            ],
        },
    }
    operational_entity_event = module.classify_raw_event(json.dumps(operational_entity_prompt), operational_entity_prompt, 21)
    operational_entity_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in operational_entity_event.facets["route_signals"]
    }

    assert "skill:aoa_decision" in operational_entity_signals
    assert "skill:aoa_session_search" in operational_entity_signals
    assert "skill:imagegen" in operational_entity_signals
    assert "mcp:aoa_session_memory_mcp" in operational_entity_signals
    assert "hook:userpromptsubmit" in operational_entity_signals
    assert "tool:exec_command" in operational_entity_signals
    assert "api:openai_responses" in operational_entity_signals
    assert "plugin:gmail_openai_curated" in operational_entity_signals
    assert "agent:sub_agent" in operational_entity_signals
    assert "script:validate_stack" in operational_entity_signals
    assert "validator:validate_stack" in operational_entity_signals
    assert "test:test_session_memory" in operational_entity_signals
    assert "test:pytest" in operational_entity_signals
    assert "eval:inspect_ai" in operational_entity_signals
    assert "eval:session_quality" in operational_entity_signals
    assert "git:git" in operational_entity_signals
    assert "git:gh" in operational_entity_signals
    assert "git:commit" in operational_entity_signals
    assert "git:pull_request" in operational_entity_signals
    assert "playbook:session_audit" in operational_entity_signals
    assert "technique:entity_routing" in operational_entity_signals
    assert "mechanic:route_maintenance" in operational_entity_signals
    assert "graph:graphrag" in operational_entity_signals
    assert "memory:aoa_session_memory" in operational_entity_signals

    operational_noise_prompt = {
        "timestamp": "2026-05-24T00:00:06.250Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": (
                        "This plugin and including plugin are generic prose, not plugin identities. "
                        "Do not index skills/AGENTS.md or exec_command skill as skills. "
                        "Do not index skill is, skill when, core skill, guard skill, or github.com skill. "
                        "Do not index Use this skill when: or This skill is: from SKILL.md prose. "
                        "Do not index metadata fields like aoa_source_skill_path: skills/aoa-decision/SKILL.md "
                        "or skills\\n  aoa_technique_dependencies: as skills. "
                        "Nested path skills/core/engineering/aoa-source-of-truth-check/SKILL.md is the skill, not core. "
                        "Traceback path aoa_sdk/skills/detector.py:307 is code, not a skill. "
                        "Diagnostic tags route_signal:skill:detector_py_307 and skill:discovery_py_206 are code locations, not skills. "
                        "Diagnostic signal dumps like skill:core:operational_entity_heuristic:core are route metadata, not skills. "
                        "Paths like aoa-skills/checkpoint-note.json and aoa-skills/post-commit-report.json are files, not skills. "
                        "Metadata values high_risk, codex_facing, host_visible, explicit_only, and technique id AOA-T-0102 are not skills. "
                        "Profile values public_safe, layer_request, self_contained, two_stage, phase_aware, workspace_visible, repo_local, and upstream_owned are not skills. "
                        "Repo or eval names aoa_evals, aoa_stats, and gemma4_e2b_eval_readiness are not skills. "
                        "Do not index README.md:10:4 plugin, AGENTS.md:194_these plugin, connectivity-report.js plugin, "
                        "aoa-local-plugin-pack.zip plugin, 2158 plugin, or catalog-first plugin as plugins. "
                        "Do not index truncated plugin URIs like plugin://gmail@op or plugin://gmail@open as plugins. "
                        "Keep openai-developers plugin and skills/aoa-decision/SKILL.md."
                    ),
                }
            ],
        },
    }
    operational_noise_event = module.classify_raw_event(json.dumps(operational_noise_prompt), operational_noise_prompt, 22)
    operational_noise_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in operational_noise_event.facets["route_signals"]
    }

    assert "plugin:this" not in operational_noise_signals
    assert "plugin:including" not in operational_noise_signals
    assert "plugin:readme_md_10_4" not in operational_noise_signals
    assert "plugin:agents_md_194_these" not in operational_noise_signals
    assert "plugin:connectivity_report_js" not in operational_noise_signals
    assert "plugin:aoa_local_plugin_pack_zip" not in operational_noise_signals
    assert "plugin:2158" not in operational_noise_signals
    assert "plugin:catalog_first" not in operational_noise_signals
    assert "plugin:gmail_op" not in operational_noise_signals
    assert "plugin:gmail_open" not in operational_noise_signals
    assert "skill:agents_md" not in operational_noise_signals
    assert "skill:exec_command" not in operational_noise_signals
    assert "skill:is" not in operational_noise_signals
    assert "skill:when" not in operational_noise_signals
    assert "skill:core" not in operational_noise_signals
    assert "skill:guard" not in operational_noise_signals
    assert "skill:github_com" not in operational_noise_signals
    assert "skill:aoa_source_skill_path" not in operational_noise_signals
    assert "skill:aoa_technique_dependencies" not in operational_noise_signals
    assert "skill:detector_py_307" not in operational_noise_signals
    assert "skill:discovery_py_206" not in operational_noise_signals
    assert "skill:core_operational_entity_heuristic_core" not in operational_noise_signals
    assert "skill:checkpoint_note_json" not in operational_noise_signals
    assert "skill:post_commit_report_json" not in operational_noise_signals
    assert "skill:high_risk" not in operational_noise_signals
    assert "skill:codex_facing" not in operational_noise_signals
    assert "skill:host_visible" not in operational_noise_signals
    assert "skill:explicit_only" not in operational_noise_signals
    assert "skill:aoa_t_0102" not in operational_noise_signals
    assert "skill:public_safe" not in operational_noise_signals
    assert "skill:layer_request" not in operational_noise_signals
    assert "skill:self_contained" not in operational_noise_signals
    assert "skill:two_stage" not in operational_noise_signals
    assert "skill:phase_aware" not in operational_noise_signals
    assert "skill:workspace_visible" not in operational_noise_signals
    assert "skill:repo_local" not in operational_noise_signals
    assert "skill:upstream_owned" not in operational_noise_signals
    assert "skill:aoa_evals" not in operational_noise_signals
    assert "skill:aoa_stats" not in operational_noise_signals
    assert "skill:gemma4_e2b_eval_readiness" not in operational_noise_signals
    assert "plugin:openai_developers" in operational_noise_signals
    assert "skill:aoa_decision" in operational_noise_signals
    assert "skill:aoa_source_of_truth_check" in operational_noise_signals

    mcp_service_command = {
        "timestamp": "2026-05-24T00:00:06.500Z",
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "exec_command",
            "call_id": "call-mcp-service",
            "arguments": json.dumps(
                {
                    "cmd": "sed -n '1,160p' mcp/services/aoa-memo-mcp/src/aoa_memo_mcp/core.py",
                    "workdir": "/srv/AbyssOS/aoa-memo",
                }
            ),
        },
    }
    mcp_service_event = module.classify_raw_event(json.dumps(mcp_service_command), mcp_service_command, 22)
    mcp_service_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in mcp_service_event.facets["route_signals"]
    }

    assert "entity:aoa_memo_mcp" in mcp_service_signals
    assert "mcp:aoa_memo_mcp" in mcp_service_signals

    mcp_test_command = {
        "timestamp": "2026-05-24T00:00:06.750Z",
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": "exec_command",
            "call_id": "call-mcp-test",
            "arguments": json.dumps(
                {
                    "cmd": "pytest mcp/services/aoa-memo-mcp/tests/test_memo_mcp.py::test_smoke_aoa_memo_mcp",
                    "workdir": "/srv/AbyssOS/aoa-memo",
                }
            ),
        },
    }
    mcp_test_event = module.classify_raw_event(json.dumps(mcp_test_command), mcp_test_command, 23)
    mcp_test_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in mcp_test_event.facets["route_signals"]
    }

    assert "mcp:aoa_memo_mcp" in mcp_test_signals
    assert "mcp:test_memo_mcp" not in mcp_test_signals
    assert "mcp:smoke_aoa_memo_mcp" not in mcp_test_signals

    derived_mcp_phrase = {
        "timestamp": "2026-05-24T00:00:07.000Z",
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "assistant",
            "content": [
                {
                    "type": "output_text",
                    "text": "Observed aoa_memo_mcp_under_stack_mcp and abyss_stack_aoa_memo_mcp labels in generated candidates.",
                }
            ],
        },
    }
    derived_mcp_event = module.classify_raw_event(json.dumps(derived_mcp_phrase), derived_mcp_phrase, 24)
    derived_mcp_signals = {
        f"{signal['layer']}:{signal['key']}" for signal in derived_mcp_event.facets["route_signals"]
    }

    assert "mcp:aoa_memo_mcp_under_stack_mcp" not in derived_mcp_signals
    assert "mcp:abyss_stack_aoa_memo_mcp" not in derived_mcp_signals


def test_route_classifier_bounds_large_tool_outputs_and_keeps_tail_signals() -> None:
    large_output = (
        "Process exited with code 0\n"
        "Output:\n"
        + ("noise " * 250_000)
        + "\n301 passed\nOpenAI Responses API tail marker\n"
    )
    record = {
        "timestamp": "2026-05-24T00:00:07.250Z",
        "type": "response_item",
        "payload": {
            "type": "function_call_output",
            "call_id": "call-large-output",
            "output": large_output,
        },
    }

    started = time.perf_counter()
    event = module.classify_raw_event(json.dumps(record), record, 25)
    elapsed = time.perf_counter() - started
    signals = {f"{signal['layer']}:{signal['key']}" for signal in event.facets["route_signals"]}

    assert elapsed < 2.0
    assert event.event_type == "VERIFICATION"
    assert event.outcome == "succeeded"
    assert "delivery_state:tests_green" in signals
    assert "api:openai_responses" in signals


def test_route_signals_ignore_null_byte_path_mentions(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-24T00-00-00-null-path.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-24T00:00:00Z", "type": "session_meta", "payload": {"id": "null-path", "cwd": str(repo)}},
            {
                "timestamp": "2026-05-24T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Check /srv/AbyssOS/bad\u0000path before reindex."}],
                },
            },
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "null-path",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    record = module.resolve_session_record(aoa_root, "null-path")
    session_dir = Path(record["path"])
    segment_index = json.loads((session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8"))

    assert module.work_context_root_for_path("/srv/AbyssOS/bad\x00path") is None
    for event in segment_index["events"]:
        for signal in event["facets"]["route_signals"]:
            assert "\x00" not in str(signal.get("detail", ""))


def test_agent_atlas_build_generates_route_entries(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-techniques"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-24T00-00-00-atlas-build.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-24T00:00:00Z", "type": "session_meta", "payload": {"id": "atlas-build", "cwd": str(repo)}},
            {
                "timestamp": "2026-05-24T00:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Только анализ, сначала погрузись в AGENTS.md"}]},
            },
            {
                "timestamp": "2026-05-24T00:00:02Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-test", "arguments": json.dumps({"cmd": "pytest -q"})},
            },
            {
                "timestamp": "2026-05-24T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "function_call_output", "call_id": "call-test", "output": "Process exited with code 0\nOutput:\n1 passed\n"},
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "atlas-build",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    payload = module.build_agent_atlas(aoa_root=aoa_root, target="all")
    assert payload["ok"] is True
    assert payload["entry_count"] > 0
    assert (aoa_root / "maps" / "INDEX.md").exists()
    scope_entries = sorted((aoa_root / "maps" / "by-scope-contract" / "entries").glob("analysis_only__*.json"))
    assert scope_entries
    entry = json.loads(scope_entries[0].read_text(encoding="utf-8"))
    assert entry["truth_status"] == "route_signal_not_reviewed_truth"
    assert entry["evidence"]["raw_ref"] == "raw:line:2"
    identity = entry["artifact_identity"]
    assert identity["artifact_class"] == "session_memory_atlas_route_entry"
    assert identity["owner_repo"] == "aoa-session-memory"
    assert identity["trust_layer"] == [
        "abi_contract_signature",
        "local_session_provenance",
        "w3c_prov_lineage",
    ]
    assert "raw refs before promoting any claim" in identity["consumer_expectation"]


def test_route_layer_readiness_audits_operational_layers(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-techniques"
    repo.mkdir(parents=True)
    (repo / "AGENTS.md").write_text("# route\n", encoding="utf-8")
    aoa_root = workspace / ".aoa"
    for axis in module.DEFAULT_ATLAS_AXES:
        axis_dir = aoa_root / "maps" / axis / "entries"
        axis_dir.mkdir(parents=True, exist_ok=True)
        (axis_dir / ".gitkeep").write_text("", encoding="utf-8")
        (axis_dir.parent / "README.md").write_text(f"# {axis}\n", encoding="utf-8")
    (aoa_root / "maps").mkdir(parents=True, exist_ok=True)
    (aoa_root / "maps" / "README.md").write_text("# maps\n", encoding="utf-8")

    transcript = tmp_path / "rollout-2026-05-24T00-00-00-route-readiness.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-05-24T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "route-readiness", "cwd": str(repo), "model": "gpt-5", "permission_mode": "danger-full-access"},
            },
            {
                "timestamp": "2026-05-24T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Сначала погрузись. Сейчас только анализ, не трогай файлы, не коммить, "
                                "без внешних подключений, потом commit push merge. Отвечай по-русски, "
                                "preserve before distill, не терять changelog, сначала AGENTS/DESIGN, "
                                "landed slices. Проверь source generated runtime diagnostics portable bundle "
                                "local overlay memory external snapshot. Entity path graph repo /srv/AbyssOS/aoa-techniques "
                                "tests skills hooks MCP issues PRs OPENAI_API_KEY package model. MEMORY.md memory_summary.md "
                                "Use skill aoa-decision and skills/aoa-session-search/SKILL.md. "
                                "OpenAI Responses API plugin://gmail@openai-curated Codex sub-agent "
                                "scripts/validate_stack.py validator tests/test_session_memory.py pytest GraphRAG graph nodes. "
                                "inspect-ai eval evals/session-quality.yaml git commit gh pr playbooks/session-audit.md "
                                "techniques/entity-routing.md mechanics/route-maintenance.md. "
                                "rollout_summaries skill memory ad_hoc .aoa/sessions .codex/sessions rollout-xyz "
                                "read_mcp_resource MCP resource cited skipped memory verified-current unverified memory update memory. "
                                "GitHub Gmail Google Drive calendar web search browser snapshot stale risk live verified. "
                                "findability raw segments session_act work_context search freshness manifest segment index search hit reviewed distillation. "
                                "Hook lifecycle SessionStart UserPromptSubmit PreCompact PostCompact Stop raw unavailable deferred queue worker JSON validity. "
                                "ambiguous weak signal conflict secret privacy export review packet long command large session cost latency timeout."
                            ),
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-05-24T00:00:02Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "get_goal", "call_id": "call-goal", "arguments": "{}"},
            },
            {
                "timestamp": "2026-05-24T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "read_mcp_resource", "call_id": "call-mcp", "arguments": json.dumps({"server": "memory", "uri": "memory://route"})},
            },
            {
                "timestamp": "2026-05-24T00:00:04Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "github.get_pull_request", "call_id": "call-github", "arguments": json.dumps({"owner": "8Dionysus", "repo": "aoa-session-memory", "pullNumber": 1})},
            },
            {
                "timestamp": "2026-05-24T00:00:05Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "apply_patch", "call_id": "call-patch", "arguments": "{}"},
            },
            {
                "timestamp": "2026-05-24T00:00:06Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-test", "arguments": json.dumps({"cmd": "pytest -q tests/test_session_memory.py"})},
            },
            {
                "timestamp": "2026-05-24T00:00:07Z",
                "type": "response_item",
                "payload": {"type": "function_call_output", "call_id": "call-test", "output": "Process exited with code 0\nOutput:\n3 passed\n"},
            },
            {
                "timestamp": "2026-05-24T00:00:08Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-fail",
                    "output": "Process exited with code 1\nOutput:\npermission denied timeout command not found raw_unavailable schema mismatch dirty generated archive\n",
                },
            },
            {
                "timestamp": "2026-05-24T00:00:09Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": (
                                "Decision accepted. Assumption recorded. Open question remains; remaining gap is not blocked. "
                                "Verification pass completed; tests green, bundle exported, local diff, committed, pushed, PR opened, merged. "
                                "Final closeout follows."
                            ),
                        }
                    ],
                },
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "route-readiness",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.build_agent_atlas(aoa_root=aoa_root, target="all")
    module.search_index_sessions(aoa_root=aoa_root, target="all")

    cache_calls = 0
    real_evidence_cache = module.session_axis_evidence_cache

    def counted_evidence_cache(session_dir: Path, manifest: dict[str, Any]) -> dict[str, dict[str, dict[str, str]]]:
        nonlocal cache_calls
        cache_calls += 1
        return real_evidence_cache(session_dir, manifest)

    monkeypatch.setattr(module, "session_axis_evidence_cache", counted_evidence_cache)
    payload = module.route_layer_readiness(aoa_root=aoa_root, target="all", sample_limit=1, write_report=True)

    assert payload["ok"] is True
    assert cache_calls == 1
    assert payload["covered_requirement_count"] == len(module.ROUTE_READINESS_REQUIREMENTS)
    assert {gate["name"]: gate["status"] for gate in payload["global_gates"]} == {
        "session_route_signal_indexes": "covered",
        "source_atlas_axes": "covered",
        "generated_atlas_index": "covered",
        "portable_sqlite_search_index": "covered",
    }
    by_id = {item["id"]: item for item in payload["requirements"]}
    assert by_id["entity_path_graph"]["status"] == "covered"
    assert by_id["resource_profile"]["layers"][0]["signal_count"] >= 1
    assert Path(payload["report_json"]).exists()
    assert Path(payload["report_markdown"]).exists()

    fast_payload = module.route_layer_readiness(aoa_root=aoa_root, target="all", sample_limit=0, write_report=False)
    assert fast_payload["ok"] is True
    assert cache_calls == 1
    for requirement in fast_payload["requirements"]:
        for layer in requirement["layers"]:
            assert layer["samples"] == []

    record = module.resolve_session_record(aoa_root, "route-readiness")
    session_dir = module.session_dir_from_record(record)
    session_index_path = session_dir / module.SESSION_INDEX_JSON
    session_index_payload = json.loads(session_index_path.read_text(encoding="utf-8"))
    session_index_payload["test_search_drift"] = "Generated route drift."
    session_index_path.write_text(json.dumps(session_index_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    stale_payload = module.route_layer_readiness(aoa_root=aoa_root, target="all", sample_limit=0, write_report=False)
    gates = {gate["name"]: gate for gate in stale_payload["global_gates"]}
    provider = gates["portable_sqlite_search_index"]["evidence"]["providers"]["portable_sqlite"]

    assert stale_payload["ok"] is False
    assert gates["portable_sqlite_search_index"]["status"] == "remaining"
    assert "session_projection_dirty" in provider["diagnostics"]
    assert provider["freshness"]["dirty_session_count"] == 1

    sample_payload = module.route_sample_audit(
        aoa_root=aoa_root,
        target="all",
        sample_limit=1,
        max_raw_chars=360,
        write_report=True,
    )

    assert sample_payload["ok"] is True
    assert sample_payload["sampled_layer_count"] == sample_payload["required_layer_count"]
    assert sample_payload["total_sample_count"] >= sample_payload["required_layer_count"]
    assert sample_payload["review_status"] == "unreviewed"
    sample_by_layer = {sample["layer"]: sample for sample in sample_payload["samples"]}
    assert sample_by_layer["scope_contract"]["review"]["status"] == "unreviewed"
    assert sample_by_layer["scope_contract"]["evidence"]["raw_ref"].startswith("raw:line:")
    assert sample_by_layer["scope_contract"]["raw_preview"]["status"] == "available"
    assert "Сначала погрузись" in sample_by_layer["scope_contract"]["raw_preview"]["text"]
    assert Path(sample_payload["report_json"]).exists()
    assert Path(sample_payload["report_markdown"]).exists()

    stale_transcript = tmp_path / "rollout-2026-05-24T00-10-00-route-stale.jsonl"
    write_jsonl(
        stale_transcript,
        [
            {
                "timestamp": "2026-05-24T00:10:00Z",
                "type": "session_meta",
                "payload": {"id": "route-stale", "cwd": str(repo), "model": "gpt-5"},
            },
            {
                "timestamp": "2026-05-24T00:10:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Сначала погрузись. route index and verification map."}],
                },
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "route-stale",
            "transcript_path": str(stale_transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    stale_record = module.resolve_session_record(aoa_root, "route-stale")
    stale_session_index_path = module.session_dir_from_record(stale_record) / module.SESSION_INDEX_JSON
    stale_session_index = json.loads(stale_session_index_path.read_text(encoding="utf-8"))
    stale_session_index["route_signal_classifier_version"] = module.ROUTE_SIGNAL_CLASSIFIER_VERSION - 1
    stale_session_index.pop("agent_event_schema_version", None)
    stale_session_index.pop("task_episode_schema_version", None)
    stale_session_index.pop("agent_event_counts", None)
    stale_session_index.pop("task_episode_counts", None)
    stale_session_index.pop("task_episodes", None)
    stale_session_index_path.write_text(json.dumps(stale_session_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    stale_sample_payload = module.route_sample_audit(
        aoa_root=aoa_root,
        target="all",
        sample_limit=1,
        max_raw_chars=360,
        write_report=False,
    )

    assert stale_sample_payload["ok"] is True
    assert stale_sample_payload["diagnostics"] == []
    assert stale_sample_payload["stale_route_classifier"] == 1
    assert stale_sample_payload["stale_route_index_count"] == 1
    assert "route_signal_classifier_mismatch" in stale_sample_payload["stale_route_indexes"][0]["reasons"]

    stale_reindex_plan = module.reindex_sessions(
        aoa_root=aoa_root,
        target="all",
        dry_run=True,
        stale_route_indexes=True,
    )
    assert stale_reindex_plan["candidate_selected_count"] == 2
    assert stale_reindex_plan["selected_count"] == 1
    assert stale_reindex_plan["counts"] == {"planned": 1}

    stale_reindex_payload = module.reindex_sessions(
        aoa_root=aoa_root,
        target="all",
        stale_route_indexes=True,
    )
    assert stale_reindex_payload["ok"] is True
    assert stale_reindex_payload["selected_count"] == 1
    assert stale_reindex_payload["counts"] == {"reindexed": 1}
    refreshed = json.loads(stale_session_index_path.read_text(encoding="utf-8"))
    assert refreshed["route_signal_classifier_version"] == module.ROUTE_SIGNAL_CLASSIFIER_VERSION
    assert refreshed["agent_event_schema_version"] == module.AGENT_EVENT_SCHEMA_VERSION
    assert refreshed["task_episode_schema_version"] == module.TASK_EPISODE_SCHEMA_VERSION
    assert isinstance(refreshed["agent_event_counts"], dict)
    assert isinstance(refreshed["task_episode_counts"], dict)
    assert isinstance(refreshed["task_episodes"], list)

    scope_identity = module.route_sample_identity(sample_by_layer["scope_contract"])
    authority_identity = module.route_sample_identity(sample_by_layer["authority_surface"])
    review_payload = module.route_sample_review(
        aoa_root=aoa_root,
        audit_path=Path(sample_payload["report_json"]),
        verdict_values=[
            f"{scope_identity}=accept:accept:raw prompt supports the scope contract",
            f"{authority_identity}=reject:weaken:sample is too generic for authority-surface truth",
        ],
        reviewer="test-reviewer",
        write_report=True,
    )

    assert review_payload["ok"] is True
    assert review_payload["sample_count"] == sample_payload["total_sample_count"]
    assert review_payload["reviewed_count"] == 2
    assert review_payload["open_count"] == sample_payload["total_sample_count"] - 2
    assert review_payload["verdict_counts"]["accept"] == 1
    assert review_payload["verdict_counts"]["reject"] == 1
    assert review_payload["classifier_feedback_count"] == 1
    assert review_payload["classifier_feedback"][0]["identity"] == authority_identity
    assert Path(review_payload["report_json"]).exists()
    assert Path(review_payload["report_markdown"]).exists()


def test_index_source_mtime_ignores_generated_root_aggregates(tmp_path: Path) -> None:
    aoa_root = tmp_path / ".aoa"
    session_dir = aoa_root / "sessions" / "2026-05-24__freshness"
    session_dir.mkdir(parents=True)
    record = {"path": str(session_dir), "session_id": "freshness-session"}

    generated_paths = [
        aoa_root / module.REGISTRY_NAME,
        aoa_root / module.SESSION_NAME_INDEX_JSON,
        aoa_root / module.SESSION_NAME_INDEX_MARKDOWN,
        aoa_root / module.SESSION_ROOT / module.SESSIONS_INDEX_JSON,
        aoa_root / module.SESSION_ROOT / module.SESSIONS_INDEX_MARKDOWN,
    ]
    for path in generated_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("generated\n", encoding="utf-8")
        os.utime(path, (200, 200))

    source_paths = [
        session_dir / "session.manifest.json",
        session_dir / module.SESSION_INDEX_JSON,
        session_dir / module.SESSION_INDEX_MARKDOWN,
    ]
    for path in source_paths:
        path.write_text("{}\n" if path.suffix == ".json" else "source\n", encoding="utf-8")
        os.utime(path, (100, 100))

    newest, newest_paths = module.latest_index_source_mtime(aoa_root, [record])
    assert newest == 100
    assert set(newest_paths) == {str(path) for path in source_paths}

    os.utime(session_dir / module.SESSION_INDEX_JSON, (300, 300))
    newest_after_source_change, newest_source_paths = module.latest_index_source_mtime(aoa_root, [record])
    assert newest_after_source_change == 300
    assert newest_source_paths == [str(session_dir / module.SESSION_INDEX_JSON)]


def test_index_maintenance_worker_refreshes_secondary_indexes_after_semantic_name(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-techniques"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    for axis in module.DEFAULT_ATLAS_AXES:
        axis_dir = aoa_root / "maps" / axis / "entries"
        axis_dir.mkdir(parents=True, exist_ok=True)
        (axis_dir / ".gitkeep").write_text("", encoding="utf-8")
        (axis_dir.parent / "README.md").write_text(f"# {axis}\n", encoding="utf-8")
    (aoa_root / "maps" / "README.md").write_text("# maps\n", encoding="utf-8")

    transcript = tmp_path / "rollout-2026-05-24T01-00-00-maintenance.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-24T01:00:00Z", "type": "session_meta", "payload": {"id": "maintenance-session", "cwd": str(repo)}},
            {"timestamp": "2026-05-24T01:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Build the route maintenance controller"}]}},
            {"timestamp": "2026-05-24T01:00:02Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-test", "arguments": json.dumps({"cmd": "pytest -q"})}},
            {"timestamp": "2026-05-24T01:00:03Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-test", "output": "Process exited with code 0\nOutput:\n1 passed\n"}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "maintenance-session",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")
    module.build_agent_atlas(aoa_root=aoa_root, target="all")
    db_path = module.search_db_path(aoa_root)
    atlas_index = aoa_root / module.ATLAS_ROOT / "index.json"
    os.utime(db_path, (1, 1))
    os.utime(atlas_index, (1, 1))

    semantic = module.set_session_semantic_name(
        aoa_root=aoa_root,
        target="maintenance-session",
        name="route maintenance automation",
        scope="session",
        kind="session_essence",
        evidence_refs=["raw:line:2"],
        from_line=1,
        to_line=4,
        apply=True,
        verify_raw_hash=True,
    )

    assert semantic["status"] == "applied"
    assert semantic["maintenance_job"]

    plan = module.maintain_indexes(aoa_root=aoa_root, target="all")
    planned = {action["id"]: action for action in plan["actions"]}
    assert planned["rebuild_search_index"]["status"] == "planned"
    assert planned["rebuild_agent_atlas"]["status"] == "planned"
    assert plan["search_index"]["status"] == "stale"
    assert plan["atlas_index"]["status"] == "stale"

    worker = module.run_hook_worker(workspace_root=workspace, aoa_root=aoa_root, limit=5)

    assert worker["ok"] is True
    assert worker["processed"] == 1
    assert worker["results"][0]["status"] == "maintained_indexes"
    assert worker["results"][0]["action_counts"]["applied"] >= 2
    assert worker["results"][0]["action_counts"]["remaining"] == 1
    assert Path(worker["results"][0]["report_json"]).exists()

    refreshed_plan = module.maintain_indexes(aoa_root=aoa_root, target="all")
    assert refreshed_plan["search_index"]["status"] == "current"
    assert refreshed_plan["atlas_index"]["status"] == "current"
    assert refreshed_plan["action_counts"] == {"skipped_clean": 1}
    assert refreshed_plan["actions"][0]["action_kind"] == "skipped_clean"
    search = module.search_sessions(aoa_root=aoa_root, query="route maintenance automation")
    assert search["ok"] is True
    assert search["result_count"] >= 1


def test_index_maintenance_uses_fingerprints_to_update_only_dirty_sessions(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-techniques"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcripts = []
    for session_id, minute, text in [
        ("dirty-alpha", 0, "Alpha dirty fingerprint session"),
        ("clean-beta", 5, "Beta clean fingerprint session"),
    ]:
        transcript = tmp_path / f"rollout-2026-06-02T00-{minute:02d}-00-{session_id}.jsonl"
        write_jsonl(
            transcript,
            [
                {"timestamp": f"2026-06-02T00:{minute:02d}:00Z", "type": "session_meta", "payload": {"id": session_id, "cwd": str(repo)}},
                {"timestamp": f"2026-06-02T00:{minute:02d}:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}},
                {"timestamp": f"2026-06-02T00:{minute:02d}:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Fingerprint route indexed."}]}},
            ],
        )
        transcripts.append((session_id, transcript))
    for session_id, transcript in transcripts:
        module.handle_hook_event(
            "Stop",
            {
                "session_id": session_id,
                "transcript_path": str(transcript),
                "cwd": str(repo),
                "hook_event_name": "Stop",
            },
            workspace_root=workspace,
            aoa_root=aoa_root,
        )

    module.search_index_sessions(aoa_root=aoa_root, target="all")
    module.build_agent_atlas(aoa_root=aoa_root, target="all")
    budgeted = module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=False, budget_seconds=0.000001)
    assert budgeted["processed_count"] == 1
    assert budgeted["remaining_count"] == 1
    assert budgeted["budget_exhausted"] is True
    clean_plan = module.maintain_indexes(aoa_root=aoa_root, target="all")
    assert clean_plan["search_dirty_session_count"] == 0
    assert clean_plan["atlas_dirty_session_count"] == 0

    semantic = module.set_session_semantic_name(
        aoa_root=aoa_root,
        target="dirty-alpha",
        name="dirty fingerprint route",
        scope="session",
        kind="session_essence",
        evidence_refs=["raw:line:2"],
        from_line=1,
        to_line=3,
        apply=True,
        verify_raw_hash=True,
    )
    assert semantic["status"] == "applied"

    dirty_plan = module.maintain_indexes(aoa_root=aoa_root, target="all")
    assert dirty_plan["search_dirty_session_count"] == 1
    assert dirty_plan["atlas_dirty_session_count"] == 1
    assert dirty_plan["search_dirty_sessions"][0]["session_id"] == "dirty-alpha"
    assert dirty_plan["atlas_dirty_sessions"][0]["session_id"] == "dirty-alpha"
    dirty_actions = {action["id"]: action for action in dirty_plan["actions"]}
    graph_command = dirty_actions["graph_maintenance"]["command"]
    assert "--max-refresh-nodes" in graph_command
    assert "--max-refresh-edges" in graph_command

    applied = module.maintain_indexes(aoa_root=aoa_root, target="all", apply=True, graph_batch_limit=10)
    actions = {action["id"]: action for action in applied["actions"]}
    assert actions["rebuild_search_index"]["result"]["selected_count"] == 1
    assert actions["rebuild_agent_atlas"]["result"]["selected_count"] == 1

    refreshed = module.maintain_indexes(aoa_root=aoa_root, target="all")
    assert refreshed["search_dirty_session_count"] == 0
    assert refreshed["atlas_dirty_session_count"] == 0
    assert refreshed["search_index"]["status"] == "current"
    assert refreshed["atlas_index"]["status"] == "current"


def test_index_maintenance_repair_limit_batches_dirty_sessions(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    session_ids = ["batch-alpha", "batch-beta", "batch-gamma"]
    for index, session_id in enumerate(session_ids):
        transcript = tmp_path / f"rollout-2026-06-03T00-0{index}-00-{session_id}.jsonl"
        write_jsonl(
            transcript,
            [
                {"timestamp": f"2026-06-03T00:0{index}:00Z", "type": "session_meta", "payload": {"id": session_id, "cwd": str(repo)}},
                {"timestamp": f"2026-06-03T00:0{index}:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": f"Batch repair {session_id}"}]}},
                {"timestamp": f"2026-06-03T00:0{index}:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Batch repair indexed."}]}},
            ],
        )
        module.handle_hook_event(
            "Stop",
            {
                "session_id": session_id,
                "transcript_path": str(transcript),
                "cwd": str(repo),
                "hook_event_name": "Stop",
            },
            workspace_root=workspace,
            aoa_root=aoa_root,
        )

    module.search_index_sessions(aoa_root=aoa_root, target="all")
    module.build_agent_atlas(aoa_root=aoa_root, target="all")
    for session_id in session_ids:
        semantic = module.set_session_semantic_name(
            aoa_root=aoa_root,
            target=session_id,
            name=f"{session_id} updated route",
            scope="session",
            kind="session_essence",
            evidence_refs=["raw:line:2"],
            from_line=1,
            to_line=3,
            apply=True,
            verify_raw_hash=True,
        )
        assert semantic["status"] == "applied"

    plan = module.maintain_indexes(aoa_root=aoa_root, target="all", repair_limit=1, repair_graph=False)
    assert plan["search_dirty_session_count"] == 3
    assert plan["search_reindex_candidate_count"] == 3
    assert plan["search_reindex_session_count"] == 1
    assert plan["search_repair_remaining_count"] == 2
    assert plan["search_repair_limited"] is True
    assert plan["atlas_dirty_session_count"] == 3
    assert plan["atlas_repair_session_count"] == 1
    assert plan["atlas_repair_remaining_count"] == 2
    assert plan["atlas_repair_limited"] is True

    applied = module.maintain_indexes(aoa_root=aoa_root, target="all", repair_limit=1, repair_graph=False, apply=True)
    actions = {action["id"]: action for action in applied["actions"]}
    assert actions["rebuild_search_index"]["result"]["selected_count"] == 1
    assert actions["rebuild_agent_atlas"]["result"]["selected_count"] == 1
    assert "reconcile_search_index" not in actions
    assert "reconcile_agent_atlas" not in actions

    remaining = module.maintain_indexes(aoa_root=aoa_root, target="all", repair_limit=1, repair_graph=False)
    assert remaining["search_dirty_session_count"] == 2
    assert remaining["atlas_dirty_session_count"] == 2


def test_index_maintenance_refreshes_search_state_without_reindexing_when_documents_are_current(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-02T00-00-00-search-state.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-02T00:00:00Z", "type": "session_meta", "payload": {"id": "search-state-refresh", "cwd": str(repo)}},
            {"timestamp": "2026-06-02T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Refresh search state"}]}},
            {"timestamp": "2026-06-02T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Search state should not rebuild."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "search-state-refresh",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")
    record = module.resolve_session_record(aoa_root, "search-state-refresh")

    old_full_projection = module.session_projection_fingerprint(record, include_rendered_markdown=True)
    conn = module.init_search_db(module.search_db_path(aoa_root), rebuild=False)
    module.upsert_search_session_state(
        conn,
        projection_state=old_full_projection,
        indexed_at=module.utc_now(),
        document_count=module.search_document_count_for_projection(conn, old_full_projection),
    )
    conn.commit()
    conn.close()

    def fail_per_projection_count(*_args: Any, **_kwargs: Any) -> int:
        raise AssertionError("refresh_search_projection_states should use bulk document counts")

    monkeypatch.setattr(module, "search_document_count_for_projection", fail_per_projection_count)

    plan = module.maintain_indexes(aoa_root=aoa_root, target="search-state-refresh", repair_graph=False)
    actions = {action["id"]: action for action in plan["actions"]}
    assert plan["search_dirty_session_count"] == 1
    assert plan["search_state_refresh_count"] == 1
    assert plan["search_reindex_session_count"] == 0
    assert actions["refresh_search_projection_state"]["needed"] is True
    assert "rebuild_search_index" not in actions

    applied = module.maintain_indexes(aoa_root=aoa_root, target="search-state-refresh", apply=True, repair_graph=False)
    applied_actions = {action["id"]: action for action in applied["actions"]}
    assert applied_actions["refresh_search_projection_state"]["status"] == "applied"
    assert applied_actions["refresh_search_projection_state"]["result"]["updated_count"] == 1
    assert "rebuild_search_index" not in applied_actions

    refreshed = module.maintain_indexes(aoa_root=aoa_root, target="search-state-refresh", repair_graph=False)
    assert refreshed["search_dirty_session_count"] == 0
    assert refreshed["final_search_index"]["status"] == "current"


def test_refresh_search_projection_states_skips_stale_document_refs(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-02T00-00-00-stale-search-docs.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-02T00:00:00Z", "type": "session_meta", "payload": {"id": "stale-search-docs", "cwd": str(repo)}},
            {"timestamp": "2026-06-02T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Stale search docs"}]}},
            {"timestamp": "2026-06-02T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Search docs must be rebuilt."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "stale-search-docs",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")
    record = module.resolve_session_record(aoa_root, "stale-search-docs")
    session_dir = module.session_dir_from_record(record)
    manifest = module.read_json(session_dir / "session.manifest.json", {})
    segment_index_path = Path(str(manifest["segments"][0]["index"]))
    segment_index = module.read_json(segment_index_path, {})
    segment_index["stale_marker"] = True
    module.write_json(segment_index_path, segment_index)

    projection = module.session_projection_fingerprint(record, include_rendered_markdown=False)
    conn = sqlite3.connect(str(module.search_db_path(aoa_root)))
    conn.row_factory = sqlite3.Row
    freshness_without_samples = module.search_projection_documents_freshness(conn, projection, sample_limit=0)
    conn.close()
    assert freshness_without_samples["ok"] is False
    assert freshness_without_samples["stale_ref_count"] >= 1
    assert freshness_without_samples["stale_refs"] == []

    result = module.refresh_search_projection_states(
        aoa_root,
        [projection],
        indexed_at=module.utc_now(),
    )

    assert result["ok"] is False
    assert result["updated_count"] == 0
    assert result["skipped_count"] == 1
    assert result["sessions"][0]["status"] == "skipped_stale_documents"
    assert "search_documents_stale_segment_refs" in result["diagnostics"]


def test_index_maintenance_rebuilds_search_when_documents_are_stale_even_if_db_is_newer(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-02T00-00-00-stale-doc-maintenance.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-02T00:00:00Z", "type": "session_meta", "payload": {"id": "stale-doc-maintenance", "cwd": str(repo)}},
            {"timestamp": "2026-06-02T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Stale docs maintenance"}]}},
            {"timestamp": "2026-06-02T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Maintenance must rebuild search docs."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "stale-doc-maintenance",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")
    record = module.resolve_session_record(aoa_root, "stale-doc-maintenance")
    session_dir = module.session_dir_from_record(record)
    manifest = module.read_json(session_dir / "session.manifest.json", {})
    segment_index_path = Path(str(manifest["segments"][0]["index"]))
    segment_index = module.read_json(segment_index_path, {})
    segment_index["stale_marker"] = True
    module.write_json(segment_index_path, segment_index)

    future = time.time() + 60
    os.utime(module.search_db_path(aoa_root), (future, future))

    plan = module.maintain_indexes(aoa_root=aoa_root, target="stale-doc-maintenance", repair_graph=False)
    actions = {action["id"]: action for action in plan["actions"]}
    assert plan["search_dirty_session_count"] == 1
    assert plan["search_state_refresh_count"] == 0
    assert plan["search_reindex_session_count"] == 1
    assert "refresh_search_projection_state" not in actions
    assert actions["rebuild_search_index"]["needed"] is True


def test_refresh_search_projection_states_respects_expired_budget(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-02T00-00-00-budget-refresh.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-02T00:00:00Z", "type": "session_meta", "payload": {"id": "budget-refresh", "cwd": str(repo)}},
            {"timestamp": "2026-06-02T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Budget refresh"}]}},
            {"timestamp": "2026-06-02T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Budget should stop."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "budget-refresh",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")
    record = module.resolve_session_record(aoa_root, "budget-refresh")
    projection = module.session_projection_fingerprint(record)

    result = module.refresh_search_projection_states(
        aoa_root,
        [projection],
        indexed_at=module.utc_now(),
        budget_deadline=time.monotonic() - 1,
    )

    assert result["ok"] is False
    assert result["budget_exhausted"] is True
    assert result["updated_count"] == 0
    assert result["skipped_count"] == 0


def test_reindex_sessions_defers_remaining_records_when_budget_expires(tmp_path: Path, monkeypatch: Any) -> None:
    aoa_root = tmp_path / ".aoa"
    records = []
    for index, label in enumerate(["2026-06-01__001__stale-route-one", "2026-06-01__002__stale-route-two"], start=1):
        session_dir = aoa_root / "sessions" / label
        raw_path = session_dir / "raw" / "session.raw.jsonl"
        write_jsonl(raw_path, [{"timestamp": f"2026-06-01T00:00:0{index}Z", "type": "session_meta", "payload": {"id": label}}])
        manifest = {
            "schema_version": module.SCHEMA_VERSION,
            "session_id": label,
            "created_at": f"2026-06-01T00:00:0{index}Z",
            "updated_at": f"2026-06-01T00:00:0{index}Z",
            "source": {"transcript_path": str(raw_path)},
            "archive_status": "indexed",
            "distillation_status": "raw_archived",
            "raw": {"path": str(raw_path), "source_path": str(raw_path)},
            "segments": [],
            "latest_event_count": 1,
            "display": {"date": "2026-06-01", "sequence": index, "label": label, "navigation_path": str(session_dir)},
            "session_label": label,
        }
        module.write_json(session_dir / "session.manifest.json", manifest)
        module.write_json(session_dir / module.SESSION_INDEX_JSON, {"route_signal_classifier_version": 0})
        module.update_registry(aoa_root, manifest, session_dir)
        records.append(label)

    calls: list[str] = []

    def fake_refresh(_aoa_root: Path, record: dict[str, Any], **_kwargs: Any) -> dict[str, Any]:
        calls.append(str(record["session_label"]))
        return {
            "session_id": record["session_id"],
            "session_label": record["session_label"],
            "session_dir": record["path"],
            "status": "reindexed",
            "event_count": 1,
            "segment_count": 1,
        }

    monkeypatch.setattr(module, "refresh_route_indexes_from_raw", fake_refresh)

    result = module.reindex_sessions(
        aoa_root=aoa_root,
        target="all",
        stale_route_indexes=True,
        budget_seconds=0.000001,
    )

    assert calls == [records[0]]
    assert result["selected_count"] == 2
    assert result["processed_count"] == 1
    assert result["remaining_count"] == 1
    assert result["budget_exhausted"] is True
    assert result["ok"] is False


def test_build_agent_atlas_defers_remaining_records_when_budget_expires(tmp_path: Path, monkeypatch: Any) -> None:
    aoa_root = tmp_path / ".aoa"
    records = []
    for label in ["atlas-budget-one", "atlas-budget-two"]:
        session_dir = aoa_root / "sessions" / label
        session_dir.mkdir(parents=True)
        module.write_json(
            session_dir / "session.manifest.json",
            {
                "schema_version": module.SCHEMA_VERSION,
                "session_id": label,
                "display": {"label": label},
                "work_context": {"work_name": label, "confidence": "high"},
                "segments": [],
            },
        )
        module.write_json(session_dir / module.SESSION_INDEX_JSON, {})
        records.append({"path": str(session_dir), "session_label": label, "session_id": label})

    def fake_atlas_entries(_aoa_root: Path, record: dict[str, Any], _axes: set[str]) -> list[dict[str, Any]]:
        label = str(record["session_label"])
        return [
            {
                "schema_version": module.ATLAS_SCHEMA_VERSION,
                "artifact_identity": module.atlas_route_entry_artifact_identity(),
                "axis": "by-work-context",
                "route_key": label,
                "status": "generated",
                "truth_status": "route_signal_not_reviewed_truth",
                "session": label,
                "session_id": label,
                "work_context": label,
                "work_family": "",
                "authority_surface": "",
                "summary": label,
                "confidence": "high",
                "next_route": "fixture",
                "evidence": {"session_ref": str(Path(record["path"]) / module.SESSION_INDEX_MARKDOWN)},
                "related_axes": [],
                "signal_count": 1,
                "route_layer": "",
                "generated_at": module.utc_now(),
            }
        ]

    ticks = iter([0.0, 0.5, 2.0, 2.5])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks, 2.5))
    monkeypatch.setattr(module, "atlas_entries_for_session", fake_atlas_entries)

    result = module.build_agent_atlas(
        aoa_root=aoa_root,
        target="all",
        clean=False,
        selected_records=records,
        budget_seconds=1,
    )

    assert result["ok"] is False
    assert result["budget_exhausted"] is True
    assert result["processed_count"] == 1
    assert result["remaining_count"] == 1
    assert result["projection_session_count"] == 1


def test_scoped_index_maintenance_readiness_uses_same_session_window(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    sessions = [
        ("old-stale", "2026-06-01T00:00:00Z", "Old session outside the hot maintenance window"),
        ("hot-dirty", "2026-06-02T00:00:00Z", "Hot session inside the maintenance window"),
    ]
    for session_id, timestamp, text in sessions:
        transcript = tmp_path / f"rollout-{timestamp.replace(':', '-')}-{session_id}.jsonl"
        write_jsonl(
            transcript,
            [
                {"timestamp": timestamp, "type": "session_meta", "payload": {"id": session_id, "cwd": str(repo)}},
                {"timestamp": timestamp, "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}},
                {"timestamp": timestamp, "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Indexed scoped maintenance fixture."}]}},
            ],
        )
        module.handle_hook_event(
            "Stop",
            {
                "session_id": session_id,
                "transcript_path": str(transcript),
                "cwd": str(repo),
                "hook_event_name": "Stop",
            },
            workspace_root=workspace,
            aoa_root=aoa_root,
        )

    module.search_index_sessions(aoa_root=aoa_root, target="all")
    module.build_agent_atlas(aoa_root=aoa_root, target="all")
    for session_id, name in [
        ("old-stale", "prior scoped control"),
        ("hot-dirty", "active scoped repair"),
    ]:
        semantic = module.set_session_semantic_name(
            aoa_root=aoa_root,
            target=session_id,
            name=name,
            scope="session",
            kind="session_essence",
            evidence_refs=["raw:line:2"],
            from_line=1,
            to_line=3,
            apply=True,
            verify_raw_hash=True,
        )
        assert semantic["status"] == "applied"

    applied = module.maintain_indexes(
        aoa_root=aoa_root,
        target="all",
        since="2026-06-02",
        apply=True,
        graph_batch_limit=10,
    )
    actions = {action["id"]: action for action in applied["actions"]}
    assert actions["rebuild_search_index"]["result"]["selected_count"] == 1
    assert actions["route_readiness"]["result"]["since"] == "2026-06-02"
    assert actions["route_readiness"]["result"]["sample_limit"] == 0
    assert actions["route_readiness"]["result"]["selected_count"] == 1

    full_provider = module.search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite", freshness_mode="deep")
    assert full_provider["providers"]["portable_sqlite"]["freshness"]["status"] == "stale"

    scoped_readiness = module.route_layer_readiness(aoa_root=aoa_root, target="all", since="2026-06-02")
    search_gate = next(gate for gate in scoped_readiness["global_gates"] if gate["name"] == "portable_sqlite_search_index")
    provider = search_gate["evidence"]["providers"]["portable_sqlite"]
    assert search_gate["status"] == "covered"
    assert provider["freshness"]["scope"] == "selected_records"
    assert provider["freshness"]["dirty_session_count"] == 0


def test_search_index_partial_update_reports_budget_exhausted_on_sqlite_interrupt(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-14T00-00-00-budgeted-search.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-14T00:00:00Z", "type": "session_meta", "payload": {"id": "budgeted-search", "cwd": str(repo)}},
            {
                "timestamp": "2026-06-14T00:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Index this session."}]},
            },
            {
                "timestamp": "2026-06-14T00:00:02Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Indexed."}]},
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "budgeted-search",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")

    def interrupting_delete(*_: Any, **__: Any) -> int:
        raise sqlite3.OperationalError("interrupted")

    ticks = iter([0.0, 1.0, 1.0])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks, 1.0))
    monkeypatch.setattr(module, "delete_search_documents_for_session", interrupting_delete)

    result = module.search_index_sessions(
        aoa_root=aoa_root,
        target="budgeted-search",
        rebuild=False,
        budget_seconds=0.1,
    )

    assert result["ok"] is False
    assert result["budget_exhausted"] is True
    assert result["partial"] is True
    assert result["processed_count"] == 0
    assert result["remaining_count"] == 1
    assert result["diagnostics"] == ["search_index_budget_exhausted"]


def test_auto_maintenance_profile_runs_session_memory_route_without_mcp_mutation(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    aoa_root.mkdir(parents=True)
    calls: dict[str, Any] = {"freshness": []}

    def fake_freshness(**kwargs: Any) -> dict[str, Any]:
        calls["freshness"].append(kwargs)
        if len(calls["freshness"]) == 1:
            return {
                "ok": False,
                "target": kwargs["target"],
                "selected_count": 1,
                "needs_index_maintenance": True,
                "needs_graph_maintenance": True,
                "diagnostics": ["preflight_dirty"],
            }
        return {
            "ok": True,
            "target": kwargs["target"],
            "selected_count": 1,
            "needs_index_maintenance": False,
            "needs_graph_maintenance": False,
            "diagnostics": [],
        }

    def fake_maintenance(**kwargs: Any) -> dict[str, Any]:
        calls["maintenance"] = kwargs
        return {
            "ok": True,
            "apply": kwargs["apply"],
            "target": kwargs["target"],
            "selected_count": 1,
            "route_drift_count": 0,
            "deferred_session_count": 0,
            "action_counts": {"applied": 2},
            "repair_indexes": kwargs["repair_indexes"],
            "repair_graph": kwargs["repair_graph"],
            "diagnostics": [],
        }

    monkeypatch.setattr(module, "graph_freshness_gates", fake_freshness)
    monkeypatch.setattr(module, "maintain_indexes", fake_maintenance)

    payload = module.auto_maintenance(
        workspace_root=workspace,
        aoa_root=aoa_root,
        profile="backlog",
        apply=True,
        write_report=True,
    )

    assert payload["ok"] is True
    assert payload["profile"] == "backlog"
    assert payload["mutates"] is True
    assert payload["graph_batch_limit"] == module.AUTO_MAINTENANCE_PROFILES["backlog"]["graph_batch_limit"]
    assert calls["maintenance"]["graph_batch_limit"] == module.AUTO_MAINTENANCE_PROFILES["backlog"]["graph_batch_limit"]
    assert payload["repair_indexes"] is True
    assert calls["maintenance"]["repair_indexes"] is True
    assert payload["repair_graph"] is True
    assert calls["maintenance"]["repair_graph"] is True
    assert calls["maintenance"]["reason"] == "auto_maintenance:backlog:timer"
    assert len(calls["freshness"]) == 2
    assert payload["resource_launcher"][:3] == ["abyss-machine", "resource", "launch"]
    assert "aoa_session_memory MCP remains read-only" in payload["mcp_boundary"]
    assert Path(payload["report_json"]).exists()
    assert Path(payload["report_markdown"]).exists()


def test_maintenance_status_returns_agent_route_without_mutating(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    aoa_root.mkdir(parents=True)
    calls: dict[str, Any] = {}

    def fake_search_provider_status(**kwargs: Any) -> dict[str, Any]:
        calls["search"] = kwargs
        return {
            "ok": True,
            "freshness_mode": "hot",
            "providers": {
                "portable_sqlite": {
                    "ok": True,
                    "status": "ready_with_deferred_live_updates",
                    "count_mode": "not_counted_hot",
                    "has_documents": True,
                    "has_route_index": True,
                    "has_route_terms": True,
                    "freshness": {
                        "status": "current_with_deferred_live_updates",
                        "actionable_dirty_session_count": 0,
                        "deferred_live_session_count": 2,
                        "dirty_session_count": 2,
                        "missing_freshness_state_count": 0,
                        "deferred_live_sessions": [
                            {
                                "session_id": "live-1",
                                "session_label": "2026-06-18__001__live-session",
                                "reason": "recent_live_projection_updates_deferred",
                            }
                        ],
                        "reasons": ["recent_live_projection_updates_deferred"],
                    },
                }
            },
        }

    def fake_route_cache_freshness_gates(**kwargs: Any) -> dict[str, Any]:
        calls["route"] = kwargs
        return {
            "ok": True,
            "source_scan": False,
            "needs_index_maintenance": False,
            "needs_graph_maintenance": False,
            "needs_sidecar_export": False,
            "needs_offline_graph_build": False,
            "route_drift_count": 0,
            "diagnostics": [],
            "graph_store": {
                "status": "current",
                "needs_maintenance": False,
                "needs_full_rebuild": False,
                "source_count": 3,
                "truth_status": "hot_gate_ledger_queue_summary_no_source_scan",
                "source_state": {
                    "source_count": 3,
                    "status_counts": {"clean": 3},
                    "dirty_count": 0,
                    "missing_count": 0,
                    "blocked_count": 0,
                },
                "ledger": {"actionable_count": 0, "retired_count": 0, "deferred_live_source_count": 0},
                "queue": {"actionable_count": 0, "deferred_live_source_count": 0},
                "diagnostics": [],
            },
        }

    monkeypatch.setattr(module, "search_provider_status", fake_search_provider_status)
    monkeypatch.setattr(module, "route_cache_freshness_gates", fake_route_cache_freshness_gates)
    monkeypatch.setattr(
        module,
        "entity_registry_maintenance_status",
        lambda _aoa_root: {
            "status": "current",
            "needs_maintenance": False,
            "entity_count": 3,
            "diagnostics": [],
        },
    )
    monkeypatch.setattr(module, "graph_freshness_gates", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("hot status should not run deep graph gates")))
    monkeypatch.setattr(module, "session_memory_timer_status", lambda: {"ok": True, "status": "available", "timer_count": 1, "timers": [], "diagnostics": []})
    monkeypatch.setattr(module, "latest_diagnostic_summary", lambda *_args, **_kwargs: {"exists": False})

    payload = module.session_memory_maintenance_status(workspace_root=workspace, aoa_root=aoa_root)
    compact = module.compact_maintenance_status_payload(payload)

    assert payload["ok"] is True
    assert payload["mutates"] is False
    assert payload["recommendation"] == "wait_live_catchup"
    assert payload["agent_route"]["action"] == "use_graph_search_for_stable_archive_wait_for_recent_live"
    assert payload["agent_route"]["can_use_graph_search"] is True
    assert payload["search"]["actionable_dirty_session_count"] == 0
    assert payload["search"]["deferred_live_session_count"] == 2
    assert payload["graph"]["actionable_count"] == 0
    assert calls["search"]["freshness_mode"] == "hot"
    assert calls["route"]["target"] == "all"
    assert "auto-maintenance hot all" in payload["exact_next_command"]
    assert compact["agent_route"]["live_catchup_pending"] is True
    assert compact["next_actions"][0]["id"] == "wait_live_catchup"


def test_catchup_auto_maintenance_batches_index_repair_without_graph(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    aoa_root.mkdir(parents=True)
    calls: dict[str, Any] = {}

    def fake_freshness(**kwargs: Any) -> dict[str, Any]:
        calls.setdefault("freshness", []).append(kwargs)
        return {
            "ok": False,
            "target": kwargs["target"],
            "selected_count": 3,
            "needs_index_maintenance": True,
            "needs_graph_maintenance": False,
            "diagnostics": ["index_maintenance_needed"],
        }

    def fake_maintenance(**kwargs: Any) -> dict[str, Any]:
        calls["maintenance"] = kwargs
        return {
            "ok": False,
            "apply": kwargs["apply"],
            "target": kwargs["target"],
            "selected_count": 3,
            "repair_indexes": kwargs["repair_indexes"],
            "repair_graph": kwargs["repair_graph"],
            "repair_limit": kwargs["repair_limit"],
            "index_repair_needed": True,
            "graph_repair_needed": False,
            "search_dirty_session_count": 3,
            "search_reindex_candidate_count": 3,
            "search_reindex_session_count": 1,
            "search_repair_remaining_count": 2,
            "search_repair_limited": True,
            "atlas_dirty_session_count": 3,
            "atlas_repair_session_count": 1,
            "atlas_repair_remaining_count": 2,
            "atlas_repair_limited": True,
            "action_counts": {"applied": 2, "remaining": 1, "deferred": 1},
            "diagnostics": ["2026-06-03__001__batch-alpha:route_signal_classifier_mismatch"],
        }

    monkeypatch.setattr(module, "route_cache_freshness_gates", fake_freshness)
    monkeypatch.setattr(module, "graph_freshness_gates", lambda **_: (_ for _ in ()).throw(AssertionError("catchup should use route-cache freshness")))
    monkeypatch.setattr(module, "maintain_indexes", fake_maintenance)

    payload = module.auto_maintenance(workspace_root=workspace, aoa_root=aoa_root, profile="catchup", apply=True)

    assert payload["profile"] == "catchup"
    assert payload["repair_limit"] == module.AUTO_MAINTENANCE_PROFILES["catchup"]["repair_limit"]
    assert payload["repair_graph"] is False
    assert payload["ok"] is True
    assert payload["status"] == "applied_with_remaining_backlog"
    assert payload["expected_catchup_remaining"] is True
    assert payload["hard_diagnostics"] == []
    assert "index_maintenance_needed" in payload["diagnostics"]
    assert calls["maintenance"]["repair_limit"] == module.AUTO_MAINTENANCE_PROFILES["catchup"]["repair_limit"]
    assert calls["maintenance"]["repair_graph"] is False
    assert len(calls["freshness"]) == 2


def test_catchup_auto_maintenance_does_not_hide_hard_failures(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    aoa_root.mkdir(parents=True)

    def fake_freshness(**kwargs: Any) -> dict[str, Any]:
        return {
            "ok": False,
            "target": kwargs["target"],
            "selected_count": 3,
            "needs_index_maintenance": True,
            "needs_graph_maintenance": False,
            "diagnostics": ["index_maintenance_needed"],
        }

    def fake_maintenance(**kwargs: Any) -> dict[str, Any]:
        return {
            "ok": False,
            "apply": kwargs["apply"],
            "target": kwargs["target"],
            "selected_count": 3,
            "repair_indexes": kwargs["repair_indexes"],
            "repair_graph": kwargs["repair_graph"],
            "repair_limit": kwargs["repair_limit"],
            "search_repair_limited": True,
            "search_repair_remaining_count": 2,
            "atlas_repair_limited": True,
            "atlas_repair_remaining_count": 2,
            "action_counts": {"applied": 1, "failed": 1},
            "diagnostics": ["search_index_failed"],
        }

    monkeypatch.setattr(module, "route_cache_freshness_gates", fake_freshness)
    monkeypatch.setattr(module, "maintain_indexes", fake_maintenance)

    payload = module.auto_maintenance(workspace_root=workspace, aoa_root=aoa_root, profile="catchup", apply=True)

    assert payload["ok"] is False
    assert payload["expected_catchup_remaining"] is False
    assert "search_index_failed" in payload["diagnostics"]


def test_hot_auto_maintenance_repairs_route_cache_and_advances_graph(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    aoa_root.mkdir(parents=True)
    calls: dict[str, Any] = {"freshness_count": 0}

    def fake_freshness(**kwargs: Any) -> dict[str, Any]:
        calls["freshness_count"] += 1
        if calls["freshness_count"] == 1:
            return {
                "ok": False,
                "target": kwargs["target"],
                "selected_count": 1,
                "needs_index_maintenance": True,
                "needs_graph_maintenance": True,
                "diagnostics": ["search_stale", "graph_dirty"],
            }
        return {
            "ok": False,
            "target": kwargs["target"],
            "selected_count": 1,
            "needs_index_maintenance": False,
            "needs_graph_maintenance": True,
            "diagnostics": ["graph_dirty"],
        }

    def fake_maintenance(**kwargs: Any) -> dict[str, Any]:
        calls["maintenance"] = kwargs
        return {
            "ok": True,
            "apply": kwargs["apply"],
            "target": kwargs["target"],
            "selected_count": 1,
            "route_drift_count": 0,
            "deferred_session_count": 0,
            "repair_indexes": kwargs["repair_indexes"],
            "repair_graph": kwargs["repair_graph"],
            "index_repair_needed": False,
            "graph_repair_needed": True,
            "action_counts": {"applied": 2, "deferred": 1},
            "diagnostics": [],
        }

    monkeypatch.setattr(module, "route_cache_freshness_gates", fake_freshness)
    monkeypatch.setattr(module, "graph_freshness_gates", lambda **_: (_ for _ in ()).throw(AssertionError("hot profile should use route-cache freshness")))
    monkeypatch.setattr(module, "maintain_indexes", fake_maintenance)

    payload = module.auto_maintenance(workspace_root=workspace, aoa_root=aoa_root, profile="hot", apply=True)

    assert payload["ok"] is True
    assert payload["status"] == "applied_with_deferred_graph"
    assert payload["repair_indexes"] is True
    assert payload["repair_graph"] is True
    assert payload["allow_deferred_graph"] is True
    assert payload["deferred_graph_after"] is True
    assert "search_stale" in payload["preflight_diagnostics"]
    assert payload["diagnostics"] == []
    assert payload["graph_batch_limit"] == module.AUTO_MAINTENANCE_PROFILES["hot"]["graph_batch_limit"]
    assert calls["maintenance"]["repair_indexes"] is True
    assert calls["maintenance"]["repair_graph"] is True
    assert calls["maintenance"]["graph_batch_limit"] == module.AUTO_MAINTENANCE_PROFILES["hot"]["graph_batch_limit"]


def test_hot_auto_maintenance_includes_old_session_with_fresh_activity_mtime(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    sessions_root = aoa_root / "sessions"
    sessions_root.mkdir(parents=True)
    now_ts = time.time()
    quiet_recent_ts = now_ts - module.GRAPH_HOT_LIVE_DEFER_SECONDS - 60
    cold_ts = now_ts - 10 * 86400

    def make_session(label: str, session_id: str, source_mtime: float) -> dict[str, Any]:
        session_dir = sessions_root / label
        raw_dir = session_dir / "raw"
        raw_dir.mkdir(parents=True)
        raw_path = raw_dir / "session.raw.jsonl"
        raw_path.write_text("{}\n", encoding="utf-8")
        manifest = {
            "session_id": session_id,
            "session_label": label,
            "session_title": label,
            "updated_at": "2020-01-01T00:00:00Z",
            "archive_status": "indexed",
            "distillation_status": "indexed",
            "display": {
                "label": label,
                "title": label,
                "date": label[:10],
                "navigation_path": str(session_dir),
            },
            "source": {"cwd": str(workspace)},
            "raw": {
                "path": str(raw_path),
                "source_path": str(raw_path),
                "line_count": 1,
                "bytes": raw_path.stat().st_size,
            },
            "segments": [],
        }
        record = {
            "session_id": session_id,
            "session_label": label,
            "session_title": label,
            "updated_at": "2020-01-01T00:00:00Z",
            "archive_status": "indexed",
            "distillation_status": "indexed",
            "path": str(session_dir),
            "display": manifest["display"],
            "raw": manifest["raw"],
        }
        module.write_json(session_dir / "session.manifest.json", manifest)
        module.write_json(session_dir / module.SESSION_INDEX_JSON, {"session_id": session_id, "session_label": label, "segments": []})
        (session_dir / module.SESSION_INDEX_MARKDOWN).write_text(f"# {label}\n", encoding="utf-8")
        for path in [raw_path, *[item for item in session_dir.iterdir() if item.is_file()]]:
            if path.is_file():
                os.utime(path, (source_mtime, source_mtime))
        return record

    active_old = make_session("2020-01-01__001__old-active", "old-active", quiet_recent_ts)
    cold_old = make_session("2020-01-02__001__old-cold", "old-cold", cold_ts)
    module.write_json(aoa_root / module.REGISTRY_NAME, {"sessions": [active_old, cold_old]})

    calls: dict[str, Any] = {"freshness": [], "maintenance": None}

    def fake_freshness(**kwargs: Any) -> dict[str, Any]:
        calls["freshness"].append(kwargs)
        selected = kwargs.get("selected_records") or []
        return {
            "ok": len(calls["freshness"]) > 1,
            "target": kwargs["target"],
            "selected_count": len(selected),
            "needs_index_maintenance": len(calls["freshness"]) == 1,
            "needs_graph_maintenance": False,
            "diagnostics": ["index_maintenance_needed"] if len(calls["freshness"]) == 1 else [],
        }

    def fake_maintenance(**kwargs: Any) -> dict[str, Any]:
        calls["maintenance"] = kwargs
        selected = kwargs.get("selected_records") or []
        return {
            "ok": True,
            "apply": kwargs["apply"],
            "target": kwargs["target"],
            "selected_count": len(selected),
            "repair_indexes": kwargs["repair_indexes"],
            "repair_graph": kwargs["repair_graph"],
            "index_repair_needed": False,
            "graph_repair_needed": False,
            "action_counts": {},
            "diagnostics": [],
        }

    monkeypatch.setattr(module, "route_cache_freshness_gates", fake_freshness)
    monkeypatch.setattr(module, "maintain_indexes", fake_maintenance)

    payload = module.auto_maintenance(
        workspace_root=workspace,
        aoa_root=aoa_root,
        profile="hot",
        apply=True,
        since_days=1,
    )

    maintenance_labels = [record["session_label"] for record in calls["maintenance"]["selected_records"]]
    freshness_labels = [record["session_label"] for record in calls["freshness"][0]["selected_records"]]
    assert payload["ok"] is True
    assert maintenance_labels == ["2020-01-01__001__old-active"]
    assert freshness_labels == maintenance_labels
    assert "2020-01-02__001__old-cold" not in maintenance_labels
    assert payload["selection_scope"]["mode"] == "date_window_plus_activity_mtime"
    assert payload["selection_scope"]["extra_activity_hot_session_count"] == 1


def test_hot_auto_maintenance_queues_bounded_graph_job_when_budget_starves_tick(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    aoa_root.mkdir(parents=True)
    calls: dict[str, Any] = {"freshness_count": 0}

    def fake_freshness(**kwargs: Any) -> dict[str, Any]:
        calls["freshness_count"] += 1
        return {
            "ok": calls["freshness_count"] > 1,
            "target": kwargs["target"],
            "selected_count": 1,
            "needs_index_maintenance": calls["freshness_count"] == 1,
            "needs_graph_maintenance": True,
            "diagnostics": ["index_maintenance_needed"] if calls["freshness_count"] == 1 else [],
        }

    def fake_maintenance(**kwargs: Any) -> dict[str, Any]:
        return {
            "ok": True,
            "apply": kwargs["apply"],
            "target": kwargs["target"],
            "selected_count": 1,
            "repair_indexes": kwargs["repair_indexes"],
            "repair_graph": kwargs["repair_graph"],
            "index_repair_needed": True,
            "graph_repair_needed": True,
            "budget_seconds": kwargs["budget_seconds"],
            "budget_exhausted": True,
            "action_counts": {"applied": 2, "deferred_budget_exhausted": 2},
            "diagnostics": [],
        }

    monkeypatch.setattr(module, "route_cache_freshness_gates", fake_freshness)
    monkeypatch.setattr(module, "maintain_indexes", fake_maintenance)

    payload = module.auto_maintenance(
        workspace_root=workspace,
        aoa_root=aoa_root,
        profile="hot",
        target="latest",
        apply=True,
        budget_seconds=1,
    )

    job_path = Path(payload["deferred_graph_job"])
    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["status"] == "applied_with_deferred_graph"
    assert payload["graph_deferred_by_budget"] is True
    assert payload["deferred_graph_next"]
    assert payload["deferred_graph_job_budget_seconds"] == 120
    assert job["job_type"] == "graph_maintenance"
    assert job["target"] == "latest"
    assert job["batch_limit"] == module.AUTO_MAINTENANCE_PROFILES["hot"]["graph_batch_limit"]
    assert job["refresh_chunk_size"] == module.AUTO_MAINTENANCE_PROFILES["hot"]["graph_refresh_chunk_size"]
    assert job["max_refresh_nodes"] == module.AUTO_MAINTENANCE_PROFILES["hot"]["graph_max_refresh_nodes"]
    assert job["max_refresh_edges"] == module.AUTO_MAINTENANCE_PROFILES["hot"]["graph_max_refresh_edges"]
    assert job["budget_seconds"] == 120


def test_auto_maintenance_skips_when_lock_is_held(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    lock_path = aoa_root / module.DIAGNOSTICS_ROOT / "auto-maintenance.lock"
    lock_path.parent.mkdir(parents=True)

    def fail_if_called(**_: Any) -> dict[str, Any]:
        raise AssertionError("freshness or maintenance should not run while lock is held")

    monkeypatch.setattr(module, "graph_freshness_gates", fail_if_called)
    monkeypatch.setattr(module, "maintain_indexes", fail_if_called)

    with lock_path.open("w", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        payload = module.auto_maintenance(workspace_root=workspace, aoa_root=aoa_root, profile="hot", apply=True)

    assert payload["ok"] is True
    assert payload["status"] == "skipped_lock_held"
    assert payload["mutates"] is False
    assert payload["lock_path"] == str(lock_path)


def test_graph_mutation_commands_report_shared_maintenance_lock(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    aoa_root.mkdir(parents=True)
    calls: dict[str, dict[str, Any]] = {}

    def fake_graph_build(**kwargs: Any) -> dict[str, Any]:
        calls["graph_build"] = kwargs
        return {"ok": True, "artifact_type": "session_memory_graph_index"}

    def fake_graph_maintenance(**kwargs: Any) -> dict[str, Any]:
        calls["graph_maintenance"] = kwargs
        return {"ok": True, "artifact_type": "session_memory_graph_maintenance"}

    def fake_index_maintenance(**kwargs: Any) -> dict[str, Any]:
        calls["index_maintenance"] = kwargs
        return {
            "ok": True,
            "artifact_type": "index_maintenance",
            "apply": kwargs["apply"],
            "target": kwargs["target"],
            "selected_count": 1,
            "diagnostics": [],
        }

    def fake_atlas_build(**kwargs: Any) -> dict[str, Any]:
        calls["atlas_build"] = kwargs
        return {"ok": True, "artifact_type": "session_memory_agent_atlas"}

    monkeypatch.setattr(module, "build_session_graph", fake_graph_build)
    monkeypatch.setattr(module, "graph_maintenance", fake_graph_maintenance)
    monkeypatch.setattr(module, "maintain_indexes", fake_index_maintenance)
    monkeypatch.setattr(module, "build_agent_atlas", fake_atlas_build)

    build_args = module.argparse.Namespace(
        workspace_root=str(workspace),
        aoa_root=str(aoa_root),
        since=None,
        since_days=None,
        in_place=True,
        store_only=True,
        write=True,
        session="all",
        until=None,
        limit=1,
        force_large_export=False,
        full=False,
        progress_every=0,
    )
    assert module.command_graph_build(build_args) == 0
    build_payload = json.loads(capsys.readouterr().out)

    maintenance_args = module.argparse.Namespace(
        workspace_root=str(workspace),
        aoa_root=str(aoa_root),
        since=None,
        since_days=None,
        session="all",
        until=None,
        limit=None,
        apply=True,
        batch_limit=1,
        refresh_chunk_size=8,
        max_refresh_nodes=None,
        max_refresh_edges=None,
        budget_seconds=12.0,
        export_sidecar=False,
        write_report=False,
    )
    assert module.command_graph_maintenance(maintenance_args) == 0
    maintenance_payload = json.loads(capsys.readouterr().out)

    index_args = module.argparse.Namespace(
        workspace_root=str(workspace),
        aoa_root=str(aoa_root),
        since=None,
        since_days=None,
        session="all",
        until=None,
        limit=None,
        apply=True,
        max_raw_mb=16,
        token_max_raw_mb=None,
        sample_audit=False,
        sample_limit=10,
        max_raw_chars=360,
        graph_batch_limit=1,
        graph_refresh_chunk_size=8,
        graph_max_refresh_nodes=None,
        graph_max_refresh_edges=None,
        skip_index_repair=False,
        skip_graph_repair=False,
        budget_seconds=None,
        progress_every=0,
        reason="test",
        write_report=False,
        full=False,
    )
    assert module.command_index_maintenance(index_args) == 0
    index_payload = json.loads(capsys.readouterr().out)

    atlas_args = module.argparse.Namespace(
        workspace_root=str(workspace),
        aoa_root=str(aoa_root),
        since=None,
        since_days=None,
        session="all",
        until=None,
        limit=None,
        no_clean=False,
        write_report=False,
    )
    assert module.command_atlas_build(atlas_args) == 0
    atlas_payload = json.loads(capsys.readouterr().out)

    assert build_payload["maintenance_lock_path"] == str(module.maintenance_lock_path(aoa_root))
    assert maintenance_payload["maintenance_lock_path"] == str(module.maintenance_lock_path(aoa_root))
    assert index_payload["maintenance_lock_path"] == str(module.maintenance_lock_path(aoa_root))
    assert atlas_payload["maintenance_lock_path"] == str(module.maintenance_lock_path(aoa_root))
    assert calls["graph_build"]["write"] is True
    assert calls["graph_build"]["export_sidecar"] is False
    assert calls["graph_build"]["atomic_store_rebuild"] is False
    assert calls["graph_maintenance"]["apply"] is True
    assert calls["graph_maintenance"]["budget_seconds"] == 12.0
    assert calls["index_maintenance"]["apply"] is True
    assert calls["atlas_build"]["clean"] is True


def test_conversation_act_audit_empty_registry_is_structured(tmp_path: Path) -> None:
    aoa_root = tmp_path / ".aoa"
    aoa_root.mkdir()

    audit = module.conversation_act_audit(aoa_root=aoa_root, target="latest")

    assert audit["ok"] is False
    assert audit["selected_count"] == 0
    assert audit["diagnostics"] == ["session registry is empty"]


def test_search_index_routes_queries_to_evidence_refs_and_freshness(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-search-index.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "search-index-session", "cwd": str(workspace)}},
            {
                "timestamp": "2026-05-12T00:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Важная мысль: имена должны держать мост-якорь"}]},
            },
            {
                "timestamp": "2026-05-12T00:00:02Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Ты не понял, имена слишком общие"}]},
            },
            {
                "timestamp": "2026-05-12T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-hook", "arguments": json.dumps({"cmd": "pytest -q"})},
            },
            {
                "timestamp": "2026-05-12T00:00:04Z",
                "type": "response_item",
                "payload": {"type": "function_call_output", "call_id": "call-hook", "output": "Stop hook failed: error: hook timed out after 20s"},
            },
            {
                "timestamp": "2026-05-12T00:00:05Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                            {
                                "type": "output_text",
                                "text": "План: сверю search-index по raw refs " + ("длинный-контекст " * 45) + "compressed_body_tail_anchor",
                            }
                    ],
                },
            },
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "search-index-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    missing = tmp_path / "missing.jsonl"
    module.handle_hook_event(
        "SessionStart",
        {
            "session_id": "raw-missing-session",
            "transcript_path": str(missing),
            "cwd": str(workspace),
            "hook_event_name": "SessionStart",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    bounded_indexed = module.search_index_sessions(aoa_root=aoa_root, target="all", max_raw_bytes=1)
    assert bounded_indexed["ok"] is True
    assert bounded_indexed["max_raw_bytes"] == 1
    assert bounded_indexed["event_document_count"] == 6
    assert any(item.get("raw_text_status") == "skipped_raw_too_large" for item in bounded_indexed["sessions"])

    indexed = module.search_index_sessions(aoa_root=aoa_root, target="all", write_report=True)

    assert indexed["ok"] is True
    assert indexed["session_document_count"] == 2
    assert indexed["event_document_count"] == 6
    assert indexed["incident_document_count"] >= 1
    assert Path(indexed["db_path"]).exists()
    assert Path(indexed["report_json"]).exists()
    conn = sqlite3.connect(str(module.search_db_path(aoa_root)))
    body_meta = conn.execute("SELECT value FROM meta WHERE key = ?", ("search_body_storage_mode",)).fetchone()[0]
    payload_meta = conn.execute("SELECT value FROM meta WHERE key = ?", ("search_payload_storage_mode",)).fetchone()[0]
    preview_len, compressed_count = conn.execute(
        "SELECT MAX(LENGTH(body)), COUNT(*) FROM documents JOIN document_bodies ON document_bodies.doc_rowid = documents.rowid"
    ).fetchone()
    route_preview_len, payload_len = conn.execute("SELECT MAX(LENGTH(route_signals)), MAX(LENGTH(payload_json)) FROM documents").fetchone()
    raw_unavailable_state = conn.execute(
        "SELECT status, reason FROM search_freshness_state WHERE session_id = ?",
        ("raw-missing-session",),
    ).fetchone()
    conn.close()
    assert body_meta == module.SEARCH_BODY_STORAGE_MODE
    assert payload_meta == module.SEARCH_PAYLOAD_STORAGE_MODE
    assert preview_len <= module.SEARCH_BODY_PREVIEW_CHARS
    assert route_preview_len <= module.SEARCH_ROUTE_SIGNALS_PREVIEW_CHARS
    assert payload_len < 1000
    assert compressed_count == indexed["document_count"]
    assert raw_unavailable_state == ("current", "indexed")

    hook_results = module.search_sessions(aoa_root=aoa_root, query="hook timed out", explain=True)
    assert hook_results["ok"] is True
    assert hook_results["result_count"] >= 1
    hook_hit = hook_results["results"][0]
    assert hook_hit["doc_type"] == "event"
    assert hook_hit["refs"]["raw"] == "raw:line:5"
    assert hook_hit["refs"]["segment"]
    assert hook_hit["refs"]["raw_block"] == "raw/blocks/000__initial-to-latest.raw.jsonl"
    assert hook_hit["freshness"]["status"] == "fresh"
    assert hook_hit["explain"]["why_this_is_not_authority"]

    tail_results = module.search_sessions(aoa_root=aoa_root, query="compressed_body_tail_anchor", explain=True)
    assert tail_results["ok"] is True
    assert tail_results["result_count"] >= 1

    correction_results = module.search_sessions(
        aoa_root=aoa_root,
        query="имена общие",
        conversation_act="operator_correction",
        explain=True,
    )
    assert correction_results["result_count"] == 1
    assert correction_results["results"][0]["conversation_act"] == "operator_correction"
    assert correction_results["results"][0]["refs"]["raw"] == "raw:line:3"

    raw_unavailable = module.search_sessions(aoa_root=aoa_root, query="raw unavailable", archive_status="raw_unavailable")
    assert raw_unavailable["result_count"] >= 1
    assert raw_unavailable["results"][0]["archive_status"] == "raw_unavailable"

    session_dir = aoa_root / "sessions" / "2026-05-12__001__важная-мысль-имена-должны-держать-мост-якорь"
    index_path = session_dir / "segments" / "000__initial-to-latest.index.json"
    broken = json.loads(index_path.read_text(encoding="utf-8"))
    broken["stale_marker"] = True
    index_path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")

    stale_results = module.search_sessions(aoa_root=aoa_root, query="hook timed out", explain=True)
    assert stale_results["results"][0]["freshness"]["status"] == "stale"
    assert "segment_index_sha_mismatch" in stale_results["results"][0]["freshness"]["reasons"]

    fresh_filler_index = tmp_path / "fresh-filler.index.json"
    fresh_filler_index.write_text(json.dumps({"status": "fresh"}) + "\n", encoding="utf-8")
    fresh_filler_sha = module.sha256_file(fresh_filler_index)
    conn = sqlite3.connect(str(module.search_db_path(aoa_root)))
    conn.row_factory = sqlite3.Row
    try:
        source_row = conn.execute(
            "SELECT * FROM documents WHERE body LIKE ? ORDER BY rowid DESC LIMIT 1",
            ("%hook timed out%",),
        ).fetchone()
        assert source_row is not None
        columns = [str(row["name"]) for row in conn.execute("PRAGMA table_info(documents)").fetchall()]
        insert_columns = [column for column in columns if column != "rowid"]
        placeholders = ", ".join("?" for _ in insert_columns)
        column_sql = ", ".join(insert_columns)
        for index in range(205):
            body = f"hook timed out fresh filler {index}"
            row_payload = {column: source_row[column] for column in insert_columns}
            row_payload.update(
                {
                    "id": f"fresh-filler-{index}",
                    "session_id": "fresh-filler-session",
                    "session_label": f"9999-12-31__{index:03d}__fresh-filler",
                    "session_title": "fresh filler",
                    "session_date": "9999-12-31",
                    "segment_index_path": str(fresh_filler_index),
                    "segment_index_sha256": fresh_filler_sha,
                    "freshness_status": "current",
                    "stale_reason": "",
                    "title": body,
                    "body": body,
                    "payload_json": "{}",
                }
            )
            cursor = conn.execute(
                f"INSERT INTO documents ({column_sql}) VALUES ({placeholders})",
                [row_payload[column] for column in insert_columns],
            )
            rowid = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO documents_fts(rowid, title, body, session_label, session_title) VALUES (?, ?, ?, ?, ?)",
                (rowid, body, body, row_payload["session_label"], row_payload["session_title"]),
            )
            body_bytes = body.encode("utf-8")
            conn.execute(
                "INSERT OR REPLACE INTO document_bodies(doc_rowid, body_zlib, body_sha256, body_chars) VALUES (?, ?, ?, ?)",
                (
                    rowid,
                    sqlite3.Binary(module.zlib.compress(body_bytes, level=6)),
                    module.hashlib.sha256(body_bytes).hexdigest(),
                    len(body),
                ),
            )
        conn.commit()
    finally:
        conn.close()

    live_stale_filtered = module.search_sessions(
        aoa_root=aoa_root,
        query="hook timed out",
        freshness_status="stale",
        explain=True,
    )
    assert live_stale_filtered["result_count"] >= 1
    assert live_stale_filtered["results"][0]["freshness"]["status"] == "stale"
    assert "segment_index_sha_mismatch" in live_stale_filtered["results"][0]["freshness"]["reasons"]
    assert "freshness_status_filter_applied_after_live_check:stale" in live_stale_filtered["diagnostics"]
    candidate_count = next(
        int(item.split(":", 1)[1])
        for item in live_stale_filtered["diagnostics"]
        if item.startswith("freshness_status_candidate_count:")
    )
    assert candidate_count > 200


def test_search_index_raw_text_uses_segment_line_limits_without_reclassifying(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-search-index-fast-raw.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "search-index-fast-raw", "cwd": str(workspace)}},
            {
                "timestamp": "2026-05-12T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "Осталось проверить fast-raw-anchor отдельно."}],
                },
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "search-index-fast-raw",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    def fail_reclassify(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("search-index raw text extraction must not run full raw classification")

    monkeypatch.setattr(module, "classify_raw_event", fail_reclassify)
    indexed = module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=True)

    assert indexed["ok"] is True
    assert indexed["event_document_count"] == 2
    results = module.search_sessions(
        aoa_root=aoa_root,
        query="fast-raw-anchor",
        agent_event="assistant_open_thread",
        explain=True,
    )
    assert results["result_count"] == 1
    assert results["results"][0]["agent_event"] == "assistant_open_thread"
    assert results["results"][0]["refs"]["raw"] == "raw:line:2"


def test_freshness_filter_preserves_search_order_before_stored_hits(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-search-order.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "search-order-session", "cwd": str(workspace)}},
            {
                "timestamp": "2026-05-12T00:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "search order seed"}]},
            },
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "search-order-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    indexed = module.search_index_sessions(aoa_root=aoa_root, target="all")
    assert indexed["ok"] is True

    fresh_index = tmp_path / "rank-order-fresh.index.json"
    fresh_index.write_text(json.dumps({"status": "fresh"}) + "\n", encoding="utf-8")
    fresh_sha = module.sha256_file(fresh_index)
    stale_index = tmp_path / "rank-order-stale.index.json"
    stale_index.write_text(json.dumps({"status": "before"}) + "\n", encoding="utf-8")
    stale_sha = module.sha256_file(stale_index)
    stale_index.write_text(json.dumps({"status": "after"}) + "\n", encoding="utf-8")

    conn = sqlite3.connect(str(module.search_db_path(aoa_root)))
    conn.row_factory = sqlite3.Row
    try:
        source_row = conn.execute("SELECT * FROM documents ORDER BY rowid LIMIT 1").fetchone()
        assert source_row is not None
        columns = [str(row["name"]) for row in conn.execute("PRAGMA table_info(documents)").fetchall()]
        insert_columns = [column for column in columns if column != "rowid"]
        placeholders = ", ".join("?" for _ in insert_columns)
        column_sql = ", ".join(insert_columns)

        def insert_search_doc(
            *,
            doc_id: str,
            session_date: str,
            body: str,
            freshness_status: str,
            segment_index_path: Path,
            segment_index_sha256: str,
            stale_reason: str = "",
        ) -> None:
            row_payload = {column: source_row[column] for column in insert_columns}
            row_payload.update(
                {
                    "id": doc_id,
                    "session_id": "rank-order-session",
                    "session_label": doc_id,
                    "session_title": "rank order",
                    "session_date": session_date,
                    "segment_index_path": str(segment_index_path),
                    "segment_index_sha256": segment_index_sha256,
                    "freshness_status": freshness_status,
                    "stale_reason": stale_reason,
                    "title": body,
                    "body": body,
                    "payload_json": "{}",
                }
            )
            cursor = conn.execute(
                f"INSERT INTO documents ({column_sql}) VALUES ({placeholders})",
                [row_payload[column] for column in insert_columns],
            )
            rowid = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO documents_fts(rowid, title, body, session_label, session_title) VALUES (?, ?, ?, ?, ?)",
                (rowid, body, body, row_payload["session_label"], row_payload["session_title"]),
            )
            body_bytes = body.encode("utf-8")
            conn.execute(
                "INSERT OR REPLACE INTO document_bodies(doc_rowid, body_zlib, body_sha256, body_chars) VALUES (?, ?, ?, ?)",
                (
                    rowid,
                    sqlite3.Binary(module.zlib.compress(body_bytes, level=6)),
                    module.hashlib.sha256(body_bytes).hexdigest(),
                    len(body),
                ),
            )

        for index in range(200):
            insert_search_doc(
                doc_id=f"rank-order-fresh-{index}",
                session_date="9999-12-31",
                body=f"rank order fresh filler {index}",
                freshness_status="current",
                segment_index_path=fresh_index,
                segment_index_sha256=fresh_sha,
            )
        insert_search_doc(
            doc_id="rank-order-live-stale",
            session_date="9999-12-30",
            body="higher ranked live stale row",
            freshness_status="current",
            segment_index_path=stale_index,
            segment_index_sha256=stale_sha,
        )
        insert_search_doc(
            doc_id="rank-order-stored-stale",
            session_date="9999-12-29",
            body="lower ranked stored stale row",
            freshness_status="stale",
            segment_index_path=fresh_index,
            segment_index_sha256=fresh_sha,
            stale_reason="indexed_stale",
        )
        conn.commit()
    finally:
        conn.close()

    filtered = module.search_sessions(
        aoa_root=aoa_root,
        query="",
        freshness_status="stale",
        limit=1,
        explain=True,
    )

    assert filtered["ok"] is True
    assert filtered["result_count"] == 1
    assert filtered["results"][0]["doc_id"] == "rank-order-live-stale"
    assert filtered["results"][0]["freshness"]["status"] == "stale"
    assert "segment_index_sha_mismatch" in filtered["results"][0]["freshness"]["reasons"]
    candidate_count = next(
        int(item.split(":", 1)[1])
        for item in filtered["diagnostics"]
        if item.startswith("freshness_status_candidate_count:")
    )
    assert candidate_count == 201


def test_scoped_search_index_refresh_preserves_other_session_state(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    sessions = [
        ("target-refresh-session", "Target refresh body"),
        ("other-search-session", "Other searchable body"),
    ]
    for session_id, text in sessions:
        transcript = tmp_path / f"rollout-2026-06-13T00-00-00-{session_id}.jsonl"
        write_jsonl(
            transcript,
            [
                {"timestamp": "2026-06-13T00:00:00Z", "type": "session_meta", "payload": {"id": session_id, "cwd": str(repo)}},
                {"timestamp": "2026-06-13T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": text}]}},
                {"timestamp": "2026-06-13T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": f"Answer for {session_id}"}]}},
            ],
        )
        module.handle_hook_event(
            "Stop",
            {
                "session_id": session_id,
                "transcript_path": str(transcript),
                "cwd": str(repo),
                "hook_event_name": "Stop",
            },
            workspace_root=workspace,
            aoa_root=aoa_root,
        )

    full = module.search_index_sessions(aoa_root=aoa_root, target="all")
    assert full["ok"] is True
    assert full["session_document_count"] == 2

    scoped_default = module.search_index_default_rebuild(target="target-refresh-session")
    assert scoped_default is False
    assert module.search_index_default_rebuild(target="all") is True
    assert module.search_index_default_rebuild(target="all", limit=1) is False

    target_label = module.resolve_session_record(aoa_root, "target-refresh-session")["session_label"]
    scoped = module.search_index_sessions(aoa_root=aoa_root, target=str(target_label), rebuild=scoped_default)
    assert scoped["ok"] is True
    assert scoped["session_document_count"] == 1
    assert scoped["removed_document_count"] >= 1

    conn = sqlite3.connect(str(module.search_db_path(aoa_root)))
    try:
        state_count = conn.execute("SELECT COUNT(*) FROM session_index_state").fetchone()[0]
        freshness_state_count = conn.execute("SELECT COUNT(*) FROM search_freshness_state").fetchone()[0]
        freshness_statuses = {row[0] for row in conn.execute("SELECT DISTINCT status FROM search_freshness_state").fetchall()}
        labels = {row[0] for row in conn.execute("SELECT session_label FROM session_index_state").fetchall()}
        other_docs = conn.execute("SELECT COUNT(*) FROM documents WHERE session_id = ?", ("other-search-session",)).fetchone()[0]
    finally:
        conn.close()
    assert state_count == 2
    assert freshness_state_count == 2
    assert freshness_statuses == {"current"}
    assert str(target_label) in labels
    assert other_docs > 0


def test_budgeted_full_search_rebuild_does_not_replace_existing_db(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    for index in range(3):
        session_id = f"atomic-rebuild-{index}"
        transcript = tmp_path / f"rollout-2026-06-13T00-0{index}-00-{session_id}.jsonl"
        write_jsonl(
            transcript,
            [
                {"timestamp": f"2026-06-13T00:0{index}:00Z", "type": "session_meta", "payload": {"id": session_id, "cwd": str(repo)}},
                {"timestamp": f"2026-06-13T00:0{index}:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": f"atomic body {index}"}]}},
                {"timestamp": f"2026-06-13T00:0{index}:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": f"atomic answer {index}"}]}},
            ],
        )
        module.handle_hook_event(
            "Stop",
            {
                "session_id": session_id,
                "transcript_path": str(transcript),
                "cwd": str(repo),
                "hook_event_name": "Stop",
            },
            workspace_root=workspace,
            aoa_root=aoa_root,
        )

    full = module.search_index_sessions(aoa_root=aoa_root, target="all")
    assert full["ok"] is True
    db_path = module.search_db_path(aoa_root)
    before_size = db_path.stat().st_size

    partial = module.search_index_sessions(aoa_root=aoa_root, target="all", rebuild=True, budget_seconds=0.000001)
    assert partial["ok"] is False
    assert partial["budget_exhausted"] is True
    assert partial["discarded_build_db_path"].endswith(f".{module.SEARCH_DB_NAME}.rebuild-{os.getpid()}")
    assert not Path(partial["discarded_build_db_path"]).exists()
    assert db_path.stat().st_size == before_size

    conn = sqlite3.connect(str(db_path))
    try:
        state_count = conn.execute("SELECT COUNT(*) FROM session_index_state").fetchone()[0]
        freshness_state_count = conn.execute("SELECT COUNT(*) FROM search_freshness_state").fetchone()[0]
        document_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    finally:
        conn.close()
    assert state_count == 3
    assert freshness_state_count == 3
    assert document_count == full["document_count"]


def test_projection_state_selection_uses_full_dirty_id_list_not_sample_only() -> None:
    records = [{"session_id": f"session-{index}", "session_label": f"label-{index}"} for index in range(45)]
    dirty_ids = [f"session-{index}" for index in range(45)]
    selected = module.records_matching_projection_states(records, dirty_ids)

    assert len(selected) == 45
    assert selected[0]["session_id"] == "session-0"
    assert selected[-1]["session_id"] == "session-44"


def test_search_document_storage_compacts_payloads_without_losing_route_postings(tmp_path: Path) -> None:
    conn = module.init_search_db(tmp_path / "search" / module.SEARCH_DB_NAME, rebuild=True)
    route_signals = module.packed_route_values(module.route_signal_token("tool", f"live-tool-{index}") for index in range(500))
    target_route_signal = module.route_signal_token(
        module.route_key_slug("tool", fallback=""),
        module.route_key_slug("live-tool-499", fallback=""),
    )
    module.insert_search_document(
        conn,
        {
            "id": "stress-doc",
            "doc_type": "event",
            "session_id": "session-stress",
            "session_label": "2026-06-12__001__route-stress",
            "session_title": "Route stress",
            "session_date": "2026-06-12",
            "event_id": "000001",
            "event_type": "TOOL_CALL",
            "route_layers": module.packed_route_values(["tool"]),
            "route_signals": route_signals,
            "title": "huge route signal payload",
            "body": "route posting body",
            "raw_text_status": "indexed",
        },
    )
    conn.commit()

    stored = conn.execute("SELECT route_signals, payload_json FROM documents WHERE id = ?", ("stress-doc",)).fetchone()
    assert stored is not None
    stored_route_signals = stored["route_signals"]
    payload = json.loads(stored["payload_json"])

    assert len(stored_route_signals) <= module.SEARCH_ROUTE_SIGNALS_PREVIEW_CHARS
    assert target_route_signal not in stored_route_signals
    assert "route_signals" not in payload
    assert payload == {"raw_text_status": "indexed"}
    assert conn.execute("SELECT COUNT(*) FROM document_routes").fetchone()[0] == 500
    assert (
        conn.execute(
            """
            SELECT 1
            FROM document_routes
            JOIN route_terms ON route_terms.id = document_routes.route_id
            WHERE route_terms.route_signal = ?
            LIMIT 1
            """,
            (target_route_signal,),
        ).fetchone()
        is not None
    )
    conn.close()


def test_route_term_cache_is_scoped_to_search_connection(tmp_path: Path) -> None:
    entry = {"layer": "entity", "key": "shared", "route_signal": "entity:shared"}

    first = module.init_search_db(tmp_path / "first.sqlite3", rebuild=True)
    first_route_id = module.route_term_id(first, entry)
    first_cache = getattr(first, "aoa_route_term_cache")

    assert first_route_id == 1
    assert first_cache[("entity", "shared")] == first_route_id
    assert module.SEARCH_ROUTE_TERM_CACHE == {}
    first.close()

    second = module.init_search_db(tmp_path / "second.sqlite3", rebuild=True)
    second.execute(
        "INSERT INTO route_terms(id, layer, key, route_signal) VALUES (?, ?, ?, ?)",
        (77, "entity", "shared", "entity:shared"),
    )
    second.commit()
    second_route_id = module.route_term_id(second, entry)
    second_cache = getattr(second, "aoa_route_term_cache")

    assert second_route_id == 77
    assert second_cache[("entity", "shared")] == second_route_id
    assert second_route_id != first_route_id
    second.close()


def test_trace_route_resolves_operational_anchors_to_evidence(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-memo"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-26T00-00-00-trace-route.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-05-26T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "trace-route-session", "cwd": str(repo), "model": "gpt-5"},
            },
            {
                "timestamp": "2026-05-26T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Debug aoa-memo-writeback skill; inspect skills/aoa-memo-writeback/SKILL.md.",
                        }
                    ],
                },
            },
            {
                "timestamp": "2026-05-26T00:00:02Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-skill",
                    "arguments": json.dumps({"cmd": "sed -n '1,120p' skills/aoa-memo-writeback/SKILL.md", "workdir": str(repo)}),
                },
            },
            {
                "timestamp": "2026-05-26T00:00:03Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-mcp",
                    "arguments": json.dumps(
                        {
                            "cmd": "sed -n '1,160p' mcp/services/aoa-memo-mcp/src/aoa_memo_mcp/core.py",
                            "workdir": str(repo),
                        }
                    ),
                },
            },
            {
                "timestamp": "2026-05-26T00:00:04Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "PreCompact hook completed; Stop hook queued deferred sync."}],
                },
            },
            {
                "timestamp": "2026-05-26T00:00:05Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-gh",
                    "arguments": json.dumps({"cmd": "gh pr create --draft --title trace-route", "workdir": str(repo)}),
                },
            },
            {
                "timestamp": "2026-05-26T00:00:06Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "apply_patch",
                    "call_id": "call-patch",
                    "arguments": "*** Begin Patch\n*** End Patch\n",
                },
            },
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "trace-route-session",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    index_payload = module.search_index_sessions(aoa_root=aoa_root, target="all")
    assert index_payload["ok"] is True

    def candidate_tokens(payload: dict[str, Any]) -> set[str]:
        return {
            f"{item.get('layer')}:{item.get('key')}"
            for item in payload.get("route_candidates", [])
            if isinstance(item, dict) and item.get("key")
        }

    def matched_tokens(payload: dict[str, Any]) -> set[str]:
        tokens: set[str] = set()
        for item in payload.get("results", []):
            if isinstance(item, dict):
                tokens.update(str(route) for route in item.get("matched_routes", []))
        return tokens

    skill_trace = module.trace_route(aoa_root=aoa_root, anchor="aoa-memo-writeback", limit=20, per_route_limit=5)
    assert skill_trace["ok"] is True
    assert "entity:aoa_memo_writeback" in candidate_tokens(skill_trace)
    assert "entity:aoa_memo_writeback" in matched_tokens(skill_trace)
    assert skill_trace["result_count"] >= 1

    mcp_trace = module.trace_route(aoa_root=aoa_root, anchor="aoa-memo-mcp", limit=20, per_route_limit=5, write_report=True)
    assert mcp_trace["ok"] is True
    assert "mcp:aoa_memo_mcp" in candidate_tokens(mcp_trace)
    assert "mcp:aoa_memo_mcp" in matched_tokens(mcp_trace)
    assert Path(mcp_trace["report_json"]).exists()
    assert Path(mcp_trace["report_markdown"]).exists()

    hook_trace = module.trace_route(aoa_root=aoa_root, anchor="PreCompact", kind="hook", limit=20, per_route_limit=5)
    assert hook_trace["ok"] is True
    assert "hook_health:precompact" in candidate_tokens(hook_trace)
    assert "hook_health:precompact" in matched_tokens(hook_trace)

    tool_trace = module.trace_route(aoa_root=aoa_root, anchor="exec_command", kind="tool", limit=20, per_route_limit=5)
    assert tool_trace["ok"] is True
    assert "tool:exec_command" in candidate_tokens(tool_trace)
    assert "tool:exec_command" in matched_tokens(tool_trace)

    github_trace = module.trace_route(aoa_root=aoa_root, anchor="GitHub", kind="github", limit=20, per_route_limit=5)
    assert github_trace["ok"] is True
    assert "external_snapshot:github" in candidate_tokens(github_trace)
    assert "external_snapshot:github" in matched_tokens(github_trace)


def test_search_provider_status_keeps_host_backends_optional(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-provider.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "provider-session", "cwd": str(workspace)}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Find hook timeout evidence"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "provider-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")

    status = module.search_provider_status(aoa_root=aoa_root)

    assert status["ok"] is True
    assert status["default_provider"] == "portable_sqlite"
    assert status["providers"]["portable_sqlite"]["status"] == "ready"
    assert status["freshness_mode"] == "hot"
    assert status["providers"]["portable_sqlite"]["freshness"]["source_scan"] is False
    assert status["providers"]["abyss_machine_nervous"]["status"] == "disabled_by_default"
    assert "Host providers are optional accelerators" in status["authority_law"]


def test_search_provider_status_hot_route_uses_persisted_state_without_archive_scan(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-13T00-00-00-provider-hot.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-13T00:00:00Z", "type": "session_meta", "payload": {"id": "provider-hot", "cwd": str(workspace)}},
            {"timestamp": "2026-06-13T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Find hot state evidence"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "provider-hot",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")
    monkeypatch.setattr(
        module,
        "chronological_session_records",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("archive scan should not run")),
    )

    status = module.search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite")
    provider = status["providers"]["portable_sqlite"]
    freshness = provider["freshness"]

    assert status["ok"] is True
    assert status["freshness_mode"] == "hot"
    assert provider["status"] == "ready"
    assert freshness["mode"] == "hot_persisted_state"
    assert freshness["source_scan"] is False
    assert freshness["freshness_state_status_counts"] == {"current": 1}


def test_search_provider_status_hot_route_reports_missing_freshness_state(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-13T00-00-00-provider-missing-state.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-13T00:00:00Z", "type": "session_meta", "payload": {"id": "provider-missing-state", "cwd": str(workspace)}},
            {"timestamp": "2026-06-13T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Find missing state evidence"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "provider-missing-state",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")
    conn = sqlite3.connect(str(module.search_db_path(aoa_root)))
    try:
        conn.execute("DELETE FROM search_freshness_state WHERE session_id = ?", ("provider-missing-state",))
        conn.commit()
    finally:
        conn.close()

    status = module.search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite")
    provider = status["providers"]["portable_sqlite"]
    freshness = provider["freshness"]

    assert status["ok"] is False
    assert provider["status"] == "stale"
    assert "search_freshness_state_missing" in provider["diagnostics"]
    assert freshness["status"] == "stale"
    assert freshness["missing_freshness_state_count"] == 1
    assert freshness["actionable_dirty_session_count"] == 1


def test_sync_marks_search_freshness_stale_until_scoped_search_index_refreshes(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-13T00-00-00-provider-sync-stale.jsonl"
    base_rows = [
        {"timestamp": "2026-06-13T00:00:00Z", "type": "session_meta", "payload": {"id": "provider-sync-stale", "cwd": str(workspace)}},
        {"timestamp": "2026-06-13T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Find sync stale evidence"}]}},
    ]
    write_jsonl(transcript, base_rows)
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "provider-sync-stale",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")

    write_jsonl(
        transcript,
        [
            *base_rows,
            {"timestamp": "2026-06-13T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Updated answer after initial search index."}]}},
        ],
    )
    synced = module.handle_hook_event(
        "Stop",
        {
            "session_id": "provider-sync-stale",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    assert synced["archive"]["search_freshness_state"]["status"] == "stale"

    stale = module.search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite")
    assert stale["ok"] is False
    assert stale["providers"]["portable_sqlite"]["freshness"]["actionable_dirty_session_ids"] == ["provider-sync-stale"]

    label = module.resolve_session_record(aoa_root, "provider-sync-stale")["session_label"]
    refreshed = module.search_index_sessions(aoa_root=aoa_root, target=str(label), rebuild=False)
    assert refreshed["ok"] is True

    current = module.search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite")
    assert current["ok"] is True
    assert current["providers"]["portable_sqlite"]["freshness"]["status"] == "current"


def test_search_provider_status_detects_session_projection_drift(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-13T00-00-00-provider-drift.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-13T00:00:00Z", "type": "session_meta", "payload": {"id": "provider-drift", "cwd": str(workspace)}},
            {"timestamp": "2026-06-13T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Find fresh search evidence"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "provider-drift",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")
    record = module.resolve_session_record(aoa_root, "provider-drift")
    session_dir = module.session_dir_from_record(record)
    session_index_path = session_dir / module.SESSION_INDEX_JSON
    session_index_payload = json.loads(session_index_path.read_text(encoding="utf-8"))
    session_index_payload["test_search_drift"] = "Generated source drift."
    session_index_path.write_text(json.dumps(session_index_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    hot_before = module.search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite")
    assert hot_before["providers"]["portable_sqlite"]["freshness"]["status"] == "current"

    status = module.search_provider_status(
        aoa_root=aoa_root,
        provider_name="portable_sqlite",
        freshness_mode="deep",
        record_freshness_state=True,
    )
    provider = status["providers"]["portable_sqlite"]

    assert status["ok"] is False
    assert provider["ok"] is False
    assert provider["status"] == "stale"
    assert "session_projection_dirty" in provider["diagnostics"]
    assert provider["freshness"]["status"] == "stale"
    assert provider["freshness"]["scope"] == "all_sessions"
    assert provider["freshness"]["dirty_session_count"] == 1
    assert provider["freshness"]["state_refresh"]["updated_count"] == 1

    hot_after = module.search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite")
    hot_provider = hot_after["providers"]["portable_sqlite"]
    assert hot_after["ok"] is False
    assert hot_provider["freshness"]["status"] == "stale"
    assert hot_provider["freshness"]["actionable_dirty_session_ids"] == ["provider-drift"]


def test_search_provider_status_defers_recent_live_codex_projection_drift(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / ".codex" / "sessions" / "2026" / "06" / "15" / "rollout-2026-06-15T00-00-00-live-provider-drift.jsonl"
    transcript.parent.mkdir(parents=True)
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-15T00:00:00Z", "type": "session_meta", "payload": {"id": "live-provider-drift", "cwd": str(workspace)}},
            {"timestamp": "2026-06-15T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Find fresh search evidence from a live transcript"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "live-provider-drift",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")
    record = module.resolve_session_record(aoa_root, "live-provider-drift")
    session_dir = module.session_dir_from_record(record)
    session_index_path = session_dir / module.SESSION_INDEX_JSON
    session_index_payload = json.loads(session_index_path.read_text(encoding="utf-8"))
    session_index_payload["test_search_drift"] = "Generated source drift from a recent live transcript."
    session_index_path.write_text(json.dumps(session_index_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.utime(transcript, None)
    os.utime(session_index_path, None)

    status = module.search_provider_status(
        aoa_root=aoa_root,
        provider_name="portable_sqlite",
        freshness_mode="deep",
        record_freshness_state=True,
    )
    provider = status["providers"]["portable_sqlite"]
    freshness = provider["freshness"]

    assert status["ok"] is True
    assert provider["ok"] is True
    assert provider["status"] == "ready_with_deferred_live_updates"
    assert "session_projection_dirty" not in provider["diagnostics"]
    assert freshness["status"] == "current_with_deferred_live_updates"
    assert freshness["dirty_session_count"] == 1
    assert freshness["actionable_dirty_session_count"] == 0
    assert freshness["deferred_live_session_count"] == 1
    assert freshness["dirty_session_ids"] == ["live-provider-drift"]
    assert freshness["actionable_dirty_session_ids"] == []
    assert freshness["reasons"] == ["recent_live_projection_updates_deferred"]
    assert freshness["deferred_live_sessions"][0]["live_transcript_path"] == str(transcript)
    assert freshness["state_refresh"]["status_counts"] == {"deferred_live": 1}

    hot_after = module.search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite")
    hot_provider = hot_after["providers"]["portable_sqlite"]
    hot_freshness = hot_provider["freshness"]
    assert hot_after["ok"] is True
    assert hot_provider["status"] == "ready_with_deferred_live_updates"
    assert hot_freshness["status"] == "current_with_deferred_live_updates"
    assert hot_freshness["deferred_live_session_count"] == 1
    assert hot_freshness["deferred_live_sessions"][0]["deferred_live_reason"] == "recent_live_codex_transcript_update"


def test_auto_maintenance_clean_hot_and_catchup_noop_preserve_search_store(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / ".codex" / "sessions" / "2026" / "06" / "18" / "rollout-2026-06-18T00-00-00-clean-noop.jsonl"
    transcript.parent.mkdir(parents=True)
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-18T00:00:00Z", "type": "session_meta", "payload": {"id": "clean-noop", "cwd": str(repo), "model": "gpt-5"}},
            {"timestamp": "2026-06-18T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Build clean no-op maintenance evidence"}]}},
            {"timestamp": "2026-06-18T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Clean no-op answer."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "clean-noop",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    record = module.resolve_session_record(aoa_root, "clean-noop")
    quiet_ts = time.time() - module.GRAPH_HOT_LIVE_DEFER_SECONDS - 60
    for path in [transcript, *[item for item in Path(record["path"]).rglob("*") if item.is_file()]]:
        os.utime(path, (quiet_ts, quiet_ts))
    assert module.search_index_sessions(aoa_root=aoa_root, target="all")["ok"] is True
    assert module.build_agent_atlas(aoa_root=aoa_root, target="all", clean=True)["ok"] is True
    assert module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)["ok"] is True
    assert module.route_cache_freshness_gates(aoa_root=aoa_root, target="all")["ok"] is True

    db_path = module.search_db_path(aoa_root)
    wal_path = Path(str(db_path) + "-wal")

    def search_store_stats() -> tuple[int, int]:
        return (
            db_path.stat().st_mtime_ns,
            wal_path.stat().st_size if wal_path.exists() else 0,
        )

    before_hot = search_store_stats()
    hot = module.auto_maintenance(
        workspace_root=workspace,
        aoa_root=aoa_root,
        profile="hot",
        target="all",
        apply=True,
        since_days=30,
    )
    after_hot = search_store_stats()

    assert hot["ok"] is True
    assert hot["status"] == "nothing_to_do"
    assert hot["mutates"] is False
    assert hot["freshness_after"] == hot["freshness_before"]
    assert hot["maintenance"]["action_counts"] == {"skipped_clean": 1}
    hot_action = hot["maintenance"]["actions"][0]
    assert hot_action["action_kind"] == "skipped_clean"
    assert hot_action["skip_reason"] == "freshness_gate_clean_no_actionable_search_atlas_or_graph_work"
    assert hot_action["dirty_count"] == 0
    assert hot_action["deferred_count"] == 0
    assert after_hot == before_hot

    before_catchup = search_store_stats()
    catchup = module.auto_maintenance(
        workspace_root=workspace,
        aoa_root=aoa_root,
        profile="catchup",
        target="all",
        apply=True,
    )
    after_catchup = search_store_stats()

    assert catchup["ok"] is True
    assert catchup["status"] == "nothing_to_do"
    assert catchup["mutates"] is False
    assert catchup["repair_graph"] is False
    assert catchup["maintenance"]["actions"][0]["action_kind"] == "skipped_clean"
    assert after_catchup == before_catchup


def test_hot_auto_maintenance_waits_for_recent_live_deferred_without_reindexing(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / ".codex" / "sessions" / "2026" / "06" / "18" / "rollout-2026-06-18T00-00-00-live-wait.jsonl"
    transcript.parent.mkdir(parents=True)
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-18T00:00:00Z", "type": "session_meta", "payload": {"id": "live-wait", "cwd": str(repo), "model": "gpt-5"}},
            {"timestamp": "2026-06-18T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Wait for recent live source"}]}},
            {"timestamp": "2026-06-18T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Recent live answer."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "live-wait",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    assert module.search_index_sessions(aoa_root=aoa_root, target="all")["ok"] is True
    assert module.build_agent_atlas(aoa_root=aoa_root, target="all", clean=True)["ok"] is True
    assert module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)["ok"] is True

    record = module.resolve_session_record(aoa_root, "live-wait")
    segment_index_path = next((Path(record["path"]) / "segments").glob("*.index.json"))
    segment_index = json.loads(segment_index_path.read_text(encoding="utf-8"))
    segment_index["events"][0].setdefault("facets", {}).setdefault("route_signals", []).append(
        {"layer": "entity", "key": "live_wait_anchor", "route_signal": "entity:live_wait_anchor"}
    )
    segment_index_path.write_text(json.dumps(segment_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.utime(transcript, None)
    os.utime(segment_index_path, None)

    deferred = module.search_provider_status(
        aoa_root=aoa_root,
        provider_name="portable_sqlite",
        freshness_mode="deep",
        record_freshness_state=True,
    )
    assert deferred["providers"]["portable_sqlite"]["freshness"]["status"] == "current_with_deferred_live_updates"

    db_path = module.search_db_path(aoa_root)
    wal_path = Path(str(db_path) + "-wal")
    before = (db_path.stat().st_mtime_ns, wal_path.stat().st_size if wal_path.exists() else 0)
    hot = module.auto_maintenance(
        workspace_root=workspace,
        aoa_root=aoa_root,
        profile="hot",
        target="all",
        apply=True,
        since_days=30,
    )
    after = (db_path.stat().st_mtime_ns, wal_path.stat().st_size if wal_path.exists() else 0)

    assert hot["ok"] is True
    assert hot["status"] == "wait_live_catchup"
    assert hot["mutates"] is False
    assert hot["deferred_live_after"] is True
    assert hot["deferred_live_selection_count"] == 1
    assert hot["selection_scope"]["quiescence"]["deferred_live_session_count"] == 1
    action = hot["maintenance"]["actions"][0]
    assert action["action_kind"] == "skipped_clean"
    assert action["deferred_count"] == 1
    assert action["skip_reason"] == "recent_live_sources_deferred_until_quiet_window"
    assert after == before


def test_auto_maintenance_hands_off_deferred_live_after_quiet_window(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / ".codex" / "sessions" / "2026" / "06" / "18" / "rollout-2026-06-18T00-00-00-live-handoff.jsonl"
    transcript.parent.mkdir(parents=True)
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-18T00:00:00Z", "type": "session_meta", "payload": {"id": "live-handoff", "cwd": str(repo), "model": "gpt-5"}},
            {"timestamp": "2026-06-18T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Index live handoff"}]}},
            {"timestamp": "2026-06-18T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Initial indexed answer."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "live-handoff",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    assert module.search_index_sessions(aoa_root=aoa_root, target="all")["ok"] is True
    assert module.build_agent_atlas(aoa_root=aoa_root, target="all", clean=True)["ok"] is True
    assert module.build_session_graph(aoa_root=aoa_root, target="all", write=True, include_rows=False)["ok"] is True

    record = module.resolve_session_record(aoa_root, "live-handoff")
    segment_index_path = next((Path(record["path"]) / "segments").glob("*.index.json"))
    segment_index = json.loads(segment_index_path.read_text(encoding="utf-8"))
    segment_index["events"][0].setdefault("facets", {}).setdefault("route_signals", []).append(
        {"layer": "entity", "key": "live_handoff_anchor", "route_signal": "entity:live_handoff_anchor"}
    )
    segment_index_path.write_text(json.dumps(segment_index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.utime(transcript, None)
    os.utime(segment_index_path, None)

    deferred = module.search_provider_status(
        aoa_root=aoa_root,
        provider_name="portable_sqlite",
        freshness_mode="deep",
        record_freshness_state=True,
    )
    assert deferred["ok"] is True
    assert deferred["providers"]["portable_sqlite"]["freshness"]["status"] == "current_with_deferred_live_updates"
    before = module.session_memory_maintenance_status(workspace_root=workspace, aoa_root=aoa_root, include_timers=False)
    assert before["recommendation"] == "wait_live_catchup"
    assert before["agent_route"]["live_catchup_pending"] is True

    quiet_ts = time.time() - module.GRAPH_HOT_LIVE_DEFER_SECONDS - 60
    for path in [transcript, *[item for item in Path(record["path"]).rglob("*") if item.is_file()]]:
        os.utime(path, (quiet_ts, quiet_ts))
    catchup = module.auto_maintenance(
        workspace_root=workspace,
        aoa_root=aoa_root,
        profile="hot",
        target="all",
        apply=True,
        budget_seconds=120,
    )
    assert catchup["ok"] is True
    assert catchup["maintenance"]["search_reindex_session_count"] >= 1

    current = module.search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite")
    assert current["ok"] is True
    assert current["providers"]["portable_sqlite"]["freshness"]["status"] == "current"
    after = module.session_memory_maintenance_status(workspace_root=workspace, aoa_root=aoa_root, include_timers=False)
    assert after["recommendation"] == "use_graph_search"
    assert after["agent_route"]["action"] == "use_graph_search"
    assert after["agent_route"]["live_catchup_pending"] is False


def test_search_provider_status_cli_can_scope_freshness_to_session(tmp_path: Path, capsys: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-13T00-00-00-provider-session-scope.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-13T00:00:00Z", "type": "session_meta", "payload": {"id": "provider-session-scope", "cwd": str(workspace)}},
            {"timestamp": "2026-06-13T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Find scoped freshness evidence"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "provider-session-scope",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")
    record = module.resolve_session_record(aoa_root, "provider-session-scope")
    session_dir = module.session_dir_from_record(record)
    session_index_path = session_dir / module.SESSION_INDEX_JSON
    session_index_payload = json.loads(session_index_path.read_text(encoding="utf-8"))
    session_index_payload["test_search_drift"] = "Generated source drift."
    session_index_path.write_text(json.dumps(session_index_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    args = module.build_parser().parse_args(
        [
            "search-provider-status",
            "--workspace-root",
            str(workspace),
            "--aoa-root",
            str(aoa_root),
            "--provider",
            "portable_sqlite",
            "--session",
            "provider-session-scope",
        ]
    )
    rc = module.command_search_provider_status(args)
    payload = json.loads(capsys.readouterr().out)
    freshness = payload["providers"]["portable_sqlite"]["freshness"]

    assert rc == 1
    assert freshness["scope"] == "selected_records"
    assert freshness["selected_session_state_count"] == 1
    assert freshness["dirty_session_count"] == 1
    assert freshness["dirty_session_ids"] == ["provider-session-scope"]


def test_index_maintenance_stabilizes_latest_selection_for_post_checks(tmp_path: Path, monkeypatch: Any) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    first_dir = aoa_root / "sessions" / "2026-06-04__001__first-live-session"
    second_dir = aoa_root / "sessions" / "2026-06-13__001__second-live-session"
    first_dir.mkdir(parents=True)
    second_dir.mkdir(parents=True)
    first_record = {
        "session_id": "first-session",
        "session_label": first_dir.name,
        "session_dir": str(first_dir),
        "display": {"path": str(first_dir)},
    }
    second_record = {
        "session_id": "second-session",
        "session_label": second_dir.name,
        "session_dir": str(second_dir),
        "display": {"path": str(second_dir)},
    }
    calls: dict[str, Any] = {"resolve_count": 0, "readiness_records": []}

    def floating_latest_resolver(_aoa_root: Path, target: str | None) -> dict[str, Any]:
        calls["resolve_count"] += 1
        assert target == "latest"
        return first_record if calls["resolve_count"] == 1 else second_record

    def fake_projection(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "session_id": record["session_id"],
                "session_label": record["session_label"],
                "fingerprint": f"fingerprint:{record['session_id']}",
                "latest_source_mtime": 100.0,
            }
            for record in records
        ]

    search_state_calls = 0

    def fake_search_state(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal search_state_calls
        search_state_calls += 1
        if search_state_calls == 1:
            return {
                "status": "stale",
                "needs_refresh": True,
                "db_mtime": 0.0,
                "dirty_session_ids": ["first-session"],
                "dirty_sessions": [{**first_record, "reasons": ["source_fingerprint_changed"]}],
                "reasons": ["session_projection_dirty"],
                "diagnostics": [],
            }
        return {
            "status": "current",
            "needs_refresh": False,
            "db_mtime": 200.0,
            "dirty_session_ids": [],
            "dirty_sessions": [],
            "reasons": [],
            "diagnostics": [],
        }

    def fake_route_readiness(**kwargs: Any) -> dict[str, Any]:
        calls["readiness_records"].append(kwargs.get("selected_records"))
        return {
            "ok": True,
            "target": kwargs["target"],
            "selected_count": len(kwargs.get("selected_records") or []),
            "covered_requirement_count": 1,
            "required_requirement_count": 1,
            "remaining": [],
            "diagnostics": [],
        }

    monkeypatch.setattr(module, "resolve_session_record", floating_latest_resolver)
    monkeypatch.setattr(module, "latest_index_source_mtime", lambda _aoa_root, records: (100.0, [str(module.session_dir_from_record(records[0]) / "SESSION.md")]))
    monkeypatch.setattr(module, "route_index_drift_records", lambda _records: [])
    monkeypatch.setattr(module, "token_accounting_backfill", lambda **_kwargs: {"ok": True, "selected_count": 1, "counts": {"current": 1}, "diagnostics": []})
    monkeypatch.setattr(module, "search_projection_fingerprints_for_records", fake_projection)
    monkeypatch.setattr(module, "projection_fingerprints_for_records", fake_projection)
    monkeypatch.setattr(module, "sqlite_search_index_state", fake_search_state)
    monkeypatch.setattr(module, "atlas_index_state", lambda *_args, **_kwargs: {"status": "current", "needs_refresh": False, "dirty_session_ids": [], "dirty_sessions": [], "reasons": [], "diagnostics": []})
    monkeypatch.setattr(module, "graph_store_state", lambda **_kwargs: {"status": "deferred_not_checked", "needs_maintenance": None, "needs_full_rebuild": False, "reasons": [], "diagnostics": []})
    monkeypatch.setattr(module, "search_index_sessions", lambda **_kwargs: {"ok": True, "selected_count": 1, "processed_count": 1, "remaining_count": 0, "budget_exhausted": False, "diagnostics": []})
    monkeypatch.setattr(module, "build_agent_atlas", lambda **_kwargs: {"ok": True, "selected_count": 0, "processed_count": 0, "remaining_count": 0, "budget_exhausted": False, "diagnostics": []})
    monkeypatch.setattr(module, "route_layer_readiness", fake_route_readiness)

    payload = module.maintain_indexes(aoa_root=aoa_root, target="latest", apply=True, repair_graph=False)

    assert payload["ok"] is True
    assert calls["resolve_count"] == 1
    assert calls["readiness_records"]
    assert calls["readiness_records"][0][0]["session_id"] == "first-session"
    assert payload["final_search_index"]["status"] == "current"


def test_search_sessions_use_fast_provider_presence_probe(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-13T00-00-00-fast-provider.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-13T00:00:00Z", "type": "session_meta", "payload": {"id": "fast-provider-session", "cwd": str(workspace)}},
            {"timestamp": "2026-06-13T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Find agent response evidence quickly"}]}},
            {"timestamp": "2026-06-13T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Проверяю и отвечаю."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "fast-provider-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")

    search = module.search_sessions(aoa_root=aoa_root, query="ответ", limit=1)
    status = search["provider"]["status"]
    provider = status["providers"]["portable_sqlite"]

    assert status["status_mode"] == "fast_presence_probe"
    assert provider["count_mode"] == "not_counted_fast"
    assert provider["has_documents"] is True
    assert provider["has_route_index"] is True
    assert provider["has_route_terms"] is True
    assert "document_count" not in provider


def test_search_read_routes_remain_available_during_wal_writer(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    repo = workspace / "aoa-session-memory"
    repo.mkdir(parents=True)
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-06-14T00-00-00-wal-writer-session.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-14T00:00:00Z", "type": "session_meta", "payload": {"id": "wal-writer-session", "cwd": str(repo)}},
            {"timestamp": "2026-06-14T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Keep search reads available"}]}},
            {"timestamp": "2026-06-14T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "wal answer committed for readers"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "wal-writer-session",
            "transcript_path": str(transcript),
            "cwd": str(repo),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    indexed = module.search_index_sessions(aoa_root=aoa_root, target="all")
    assert indexed["ok"] is True

    baseline = module.search_sessions(aoa_root=aoa_root, query="wal answer", limit=1)
    assert baseline["ok"] is True
    assert baseline["result_count"] == 1

    writer: sqlite3.Connection | None = None
    try:
        writer = module.init_search_db(module.search_db_path(aoa_root), rebuild=False)
        journal_mode = str(writer.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        assert journal_mode == "wal"
        writer.execute("BEGIN EXCLUSIVE")
        writer.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('concurrent_writer_probe', 'open')")

        status = module.search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite")
        search = module.search_sessions(aoa_root=aoa_root, query="wal answer", limit=1)
        agent_events = module.search_agent_event_documents(aoa_root=aoa_root, session="wal-writer-session", limit=1)
    finally:
        if writer is not None:
            writer.rollback()
            writer.close()

    assert status["providers"]["portable_sqlite"]["status"] == "ready"
    assert search["ok"] is True
    assert search["provider"]["status"]["providers"]["portable_sqlite"]["status"] == "ready"
    assert search["result_count"] == 1
    assert agent_events["ok"] is True
    assert agent_events["provider"]["status"]["providers"]["portable_sqlite"]["status"] == "ready"
    assert agent_events["result_count"] == 1


def test_search_read_routes_report_locked_search_db_without_traceback(tmp_path: Path, monkeypatch: Any) -> None:
    aoa_root = tmp_path / ".aoa"
    db_path = module.search_db_path(aoa_root)
    db_path.parent.mkdir(parents=True)
    db_path.touch()
    real_connect = sqlite3.connect
    search_connects: list[str] = []

    def locked_connect(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
        database_text = str(database)
        if database_text.startswith("file:") and "mode=ro" in database_text:
            search_connects.append(database_text)
            raise sqlite3.OperationalError("database is locked")
        return real_connect(database, *args, **kwargs)

    monkeypatch.setattr(module.sqlite3, "connect", locked_connect)

    status = module.search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite")
    provider = status["providers"]["portable_sqlite"]
    search = module.search_sessions(aoa_root=aoa_root, query="anything", limit=1)
    agent_events = module.search_agent_event_documents(aoa_root=aoa_root, limit=1)

    assert provider["status"] == "sqlite_locked"
    assert provider["diagnostics"] == ["sqlite_locked:database is locked"]
    assert search["ok"] is False
    assert search["provider"]["status"] == "sqlite_locked"
    assert search["diagnostics"] == ["sqlite_locked:database is locked"]
    assert agent_events["ok"] is False
    assert agent_events["provider"]["status"] == "sqlite_locked"
    assert agent_events["diagnostics"] == ["sqlite_locked:database is locked"]
    assert search_connects


def test_search_provider_status_detects_structural_schema_drift(tmp_path: Path) -> None:
    aoa_root = tmp_path / ".aoa"
    db_path = module.search_db_path(aoa_root)
    db_path.parent.mkdir(parents=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (str(module.SEARCH_SCHEMA_VERSION),))
    conn.execute(
        """
        CREATE TABLE documents (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT NOT NULL UNIQUE,
            doc_type TEXT NOT NULL,
            session_id TEXT,
            session_label TEXT,
            session_act TEXT,
            route_layers TEXT,
            route_signals TEXT,
            payload_json TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE VIRTUAL TABLE documents_fts USING fts5(title, body, session_label, session_title, content='documents', content_rowid='rowid')")
    conn.execute("CREATE TABLE document_bodies (doc_rowid INTEGER PRIMARY KEY, body_zlib BLOB NOT NULL, body_sha256 TEXT NOT NULL, body_chars INTEGER NOT NULL)")
    conn.execute("CREATE TABLE route_terms (id INTEGER PRIMARY KEY AUTOINCREMENT, layer TEXT NOT NULL, key TEXT NOT NULL, route_signal TEXT NOT NULL)")
    conn.execute("CREATE TABLE document_routes (doc_rowid INTEGER NOT NULL, route_id INTEGER NOT NULL)")
    conn.execute("CREATE TABLE session_index_state (session_id TEXT PRIMARY KEY, session_label TEXT, source_fingerprint TEXT NOT NULL, source_latest_mtime REAL, search_schema_version TEXT, route_signal_classifier_version INTEGER, indexed_at TEXT, document_count INTEGER)")
    conn.execute("INSERT INTO documents (id, doc_type, payload_json) VALUES ('doc-1', 'session', '{}')")
    conn.commit()
    conn.close()

    status = module.search_provider_status(aoa_root=aoa_root, provider_name="portable_sqlite")
    provider = status["providers"]["portable_sqlite"]
    state = module.sqlite_search_index_state(aoa_root, latest_source_mtime=0)

    assert provider["ok"] is False
    assert provider["status"] == "stale"
    assert "search_schema_missing_column:documents.agent_event" in provider["diagnostics"]
    assert "search_schema_missing_column:documents.task_episode_id" in provider["diagnostics"]
    assert "search_schema_missing_column:documents.agent_event" in state["reasons"]
    assert state["needs_refresh"] is True


def test_host_search_provider_overlay_never_replaces_aoa_refs(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    (aoa_root / "config").mkdir(parents=True, exist_ok=True)
    config = module.default_search_provider_config()
    config["providers"]["abyss_machine_nervous"]["enabled"] = True
    (aoa_root / module.SEARCH_PROVIDER_CONFIG_PATH).write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-host-provider.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "host-provider-session", "cwd": str(workspace)}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Stop hook failed because hook timed out"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "host-provider-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")

    def fake_run_json_command(command: list[str], **_kwargs: object) -> dict[str, object]:
        if command[:3] == ["abyss-machine", "stack-bridge", "validate"]:
            return {"ok": True, "status": "ok", "command": command, "payload": {"schema": "stack", "generated_at": "now", "summary": {"fails": 0, "warnings": 0, "checks": 1}}}
        if command[:3] == ["abyss-machine", "nervous", "quality-audit"]:
            return {"ok": True, "status": "ok", "command": command, "payload": {"schema": "quality", "generated_at": "now", "summary": {"fails": 0, "warnings": 1, "checks": 1}}}
        if command[:3] == ["abyss-machine", "nervous", "semantic-status"]:
            return {
                "ok": True,
                "status": "ok",
                "command": command,
                "payload": {
                    "schema": "semantic",
                    "generated_at": "now",
                    "ok": True,
                    "ready": True,
                    "warnings": [],
                    "embedding": {"model_dir": "/models/embed", "model_exists": True, "device": "GPU", "dimension": 1024},
                    "counts": {"vectors": 12},
                    "freshness": {"stale": False, "source_chunks": 12, "delta_chunks": 0, "partial": False},
                },
            }
        if command[:3] == ["abyss-machine", "nervous", "recall"]:
            return {
                "ok": True,
                "status": "ok",
                "command": command,
                "payload": {
                    "schema": "abyss_machine_nervous_retrieval_pack_v1",
                    "generated_at": "now",
                    "mode": "lexical",
                    "query": "hook timed out",
                    "summary": {"evidence_items": 1},
                    "evidence": [{"id": "host-context"}],
                },
            }
        raise AssertionError(command)

    def fake_run_json_url(url: str, **_kwargs: object) -> dict[str, object]:
        assert url == "http://127.0.0.1:5405/health"
        return {
            "ok": True,
            "status": "ok",
            "url": url,
            "payload": {
                "ok": True,
                "service": "rerank-api",
                "model": "qwen3-reranker-0.6b-int8-ov",
                "backend": "openvino_qwen3_reranker",
                "device": "GPU",
                "model_dir_exists": True,
                "fake_mode": False,
            },
        }

    monkeypatch.setattr(module, "run_json_command", fake_run_json_command)
    monkeypatch.setattr(module, "run_json_url", fake_run_json_url)

    guarded = module.search_sessions(
        aoa_root=aoa_root,
        query="hook timed out",
        provider="abyss_machine_nervous",
        doc_type="event",
        explain=True,
    )
    assert guarded["ok"] is True
    assert guarded["provider"]["authoritative_result_provider"] == "portable_sqlite"
    assert guarded["provider"]["status"]["providers"]["abyss_machine_nervous"]["status"] == "ready_with_warnings"
    assert guarded["provider"]["overlay"] is None
    assert guarded["results"][0]["refs"]["raw"] == "raw:line:2"
    assert "host provider has warnings" in guarded["diagnostics"][0]

    with_overlay = module.search_sessions(
        aoa_root=aoa_root,
        query="hook timed out",
        provider="abyss_machine_nervous",
        doc_type="event",
        include_host_context=True,
        allow_host_warnings=True,
    )
    assert with_overlay["provider"]["overlay"]["truth_level"] == "host_context_only_not_aoa_authority"
    assert with_overlay["provider"]["overlay"]["evidence_count"] == 1
    assert with_overlay["results"][0]["refs"]["raw"] == "raw:line:2"
    provider_models = with_overlay["provider"]["status"]["providers"]["abyss_machine_nervous"]["models"]
    assert provider_models["embedding"]["status"] == "ready"
    assert provider_models["reranker"]["status"] == "ready"


def test_local_semantic_overlay_and_rerank_keep_portable_refs_authoritative(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-local-rerank.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "local-rerank-session", "cwd": str(workspace)}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "timeout archive map needs a broad cleanup"}]}},
            {"timestamp": "2026-05-12T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "timeout hook failure has the stronger recovery route"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "local-rerank-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    module.search_index_sessions(aoa_root=aoa_root, target="all")

    def fake_run_json_command(command: list[str], **_kwargs: object) -> dict[str, object]:
        if command[:3] == ["abyss-machine", "stack-bridge", "validate"]:
            return {"ok": True, "status": "ok", "command": command, "payload": {"schema": "stack", "generated_at": "now", "summary": {"fails": 0, "warnings": 0, "checks": 1}}}
        if command[:3] == ["abyss-machine", "nervous", "quality-audit"]:
            return {"ok": True, "status": "ok", "command": command, "payload": {"schema": "quality", "generated_at": "now", "summary": {"fails": 0, "warnings": 0, "checks": 1}}}
        if command[:3] == ["abyss-machine", "nervous", "semantic-status"]:
            return {
                "ok": True,
                "status": "ok",
                "command": command,
                "payload": {
                    "schema": "semantic",
                    "generated_at": "now",
                    "ok": True,
                    "ready": True,
                    "warnings": [],
                    "embedding": {"model_dir": "/models/embed", "model_exists": True, "device": "GPU", "dimension": 1024},
                    "counts": {"vectors": 2},
                    "freshness": {"stale": False, "source_chunks": 2, "delta_chunks": 0, "partial": False},
                },
            }
        if command[:3] == ["abyss-machine", "nervous", "semantic-search"]:
            return {
                "ok": True,
                "status": "ok",
                "command": command,
                "payload": {
                    "schema": "abyss_machine_nervous_semantic_search_v1",
                    "generated_at": "now",
                    "query": "timeout",
                    "results": [{"source_id": "host", "document_schema": "host_fact", "title": "host semantic route", "score": 0.9, "snippet": "host context"}],
                    "summary": {"results": 1, "semantic_run_id": "semantic-test", "partial": False},
                    "embedding_status": {"ok": True, "dim": 1024, "device": "GPU", "model_dir": "/models/embed"},
                },
            }
        raise AssertionError(command)

    def fake_run_json_url(url: str, **kwargs: object) -> dict[str, object]:
        if url.endswith("/health"):
            return {
                "ok": True,
                "status": "ok",
                "url": url,
                "payload": {"ok": True, "service": "rerank-api", "model": "reranker", "backend": "test", "device": "GPU"},
            }
        if url.endswith("/rerank"):
            payload = kwargs.get("payload")
            assert isinstance(payload, dict)
            assert payload["query"] == "timeout"
            documents = payload["documents"]
            assert isinstance(documents, list)
            return {
                "ok": True,
                "status": "ok",
                "url": url,
                "payload": {
                    "model": "reranker",
                    "results": [
                        {"index": 0, "relevance_score": 0.1, "raw_logit_diff": -1.0},
                        {"index": 1, "relevance_score": 0.95, "raw_logit_diff": 2.0},
                    ],
                    "meta": {"backend": "test", "device": "GPU", "documents": len(documents), "returned": len(documents), "total_ms": 12.3},
                },
            }
        raise AssertionError(url)

    monkeypatch.setattr(module, "run_json_command", fake_run_json_command)
    monkeypatch.setattr(module, "run_json_url", fake_run_json_url)

    payload = module.search_sessions(
        aoa_root=aoa_root,
        query="timeout",
        doc_type="event",
        limit=2,
        include_semantic_context=True,
        rerank_local=True,
        explain=True,
    )

    assert payload["ok"] is True
    assert payload["provider"]["authoritative_result_provider"] == "portable_sqlite"
    assert payload["provider"]["semantic_overlay"]["truth_level"] == "host_semantic_context_only_not_aoa_authority"
    assert payload["provider"]["semantic_overlay"]["result_count"] == 1
    assert payload["provider"]["local_rerank"]["truth_level"] == "local_rerank_ordering_not_aoa_authority"
    assert payload["results"][0]["host_rerank"]["original_position"] == 2
    assert payload["results"][0]["host_rerank"]["score"] == 0.95
    assert payload["results"][0]["refs"]["raw"].startswith("raw:line:")


def test_retrieval_packet_routes_continuation_to_refs_and_phase_candidates(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-retrieve.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "retrieve-session", "cwd": str(workspace)}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Continue the aoa-techniques session from exact raw refs"}]}},
            {"timestamp": "2026-05-12T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: continue from the phase map and verify open threads"}]}},
            {"timestamp": "2026-05-12T00:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Open thread: continue long techniques work after checking evidence"}]}},
            {"timestamp": "2026-05-12T00:00:04Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Final state: retrieval packet should name next route"}]}},
        ],
    )
    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "retrieve-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    session_dir = Path(str(receipt["session_dir"]))
    naming_dir = session_dir / "naming"
    naming_dir.mkdir(parents=True, exist_ok=True)
    phase_payload = {
        "artifact_type": "session_phase_discovery",
        "candidate_count": 1,
        "review_queue_count": 1,
        "candidates": [
            {
                "segment_id": "000",
                "name": "techniques continuation evidence route",
                "confidence": "medium",
                "name_basis": "specific_user_intent",
                "quality_flags": [],
                "evidence": ["raw:line:2"],
                "coverage": {"raw_ranges": [{"from_line": 1, "to_line": 5}]},
            }
        ],
        "review_queue": [
            {
                "segment_id": "000",
                "name": "techniques continuation evidence route",
                "reason": "needs_reviewed_name",
                "evidence": ["raw:line:2"],
            }
        ],
    }
    (naming_dir / "phase-discovery.json").write_text(json.dumps(phase_payload, ensure_ascii=False), encoding="utf-8")
    module.search_index_sessions(aoa_root=aoa_root, target="all")

    packet = module.retrieval_packet(
        aoa_root=aoa_root,
        recipe="continue-techniques-session",
        query="aoa-techniques continue evidence",
        session="retrieve-session",
        limit=4,
    )

    assert packet["ok"] is True
    assert packet["session"]["session_id"] == "retrieve-session"
    assert packet["evidence_hits"]
    assert packet["evidence_hits"][0]["refs"]["raw"].startswith("raw:line:")
    assert packet["phase_discovery"]["present"] is True
    assert packet["phase_discovery"]["review_queue_count"] == 1
    assert packet["continuation_signals"]
    assert any("rehydrate" in route for route in packet["next_routes"])
    assert any("phase-review-assist" in route for route in packet["next_routes"])


def test_retrieval_packet_unknown_recipe_returns_structured_diagnostic(tmp_path: Path) -> None:
    aoa_root = tmp_path / "AbyssOS/.aoa"

    packet = module.retrieval_packet(aoa_root=aoa_root, recipe="review", query="decision review")

    assert packet["ok"] is False
    assert packet["artifact_type"] == "retrieval_packet"
    assert packet["recipe"] == "review"
    assert packet["diagnostics"] == ["unknown recipe: review"]


def test_archive_compaction_audit_retries_when_archive_changes_mid_read(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-audit-race.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "audit-race", "cwd": str(workspace)}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Audit race"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "audit-race",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    original_stats = module.raw_compaction_stats
    mutated = {"done": False}

    def mutate_once(raw_path: Path):
        if not mutated["done"] and raw_path.name == "session.raw.jsonl":
            mutated["done"] = True
            with raw_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(
                        {
                            "timestamp": "2026-05-12T00:00:02Z",
                            "type": "response_item",
                            "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "after mutation"}]},
                        },
                        ensure_ascii=False,
                )
                    + "\n"
                )
        return original_stats(raw_path)

    monkeypatch.setattr(module, "raw_compaction_stats", mutate_once)

    audits = module.archive_compaction_audit(aoa_root)

    assert mutated["done"] is True
    assert audits[0]["matches_expected_segments"] is True
    assert audits[0]["diagnostics"] == ["archive_changed_during_audit_retry", "archive_snapshot_stabilized_after_retry:1"]


def test_classifier_avoids_stream_status_and_policy_noise(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-noise.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "noise-session", "cwd": str(workspace)}},
            {
                "timestamp": "2026-05-12T00:00:00Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Give a final judgment for the current review."}]},
            },
            {
                "timestamp": "2026-05-12T00:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "developer",
                    "content": [{"type": "input_text", "text": "Do not write secrets. Final assumption compact policy."}],
                },
            },
            {
                "timestamp": "2026-05-12T00:00:02Z",
                "type": "event_msg",
                "payload": {"type": "agent_message", "message": "Decision: inspect before editing"},
            },
            {
                "timestamp": "2026-05-12T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: inspect before editing"}]},
            },
            {
                "timestamp": "2026-05-12T00:00:04Z",
                "type": "event_msg",
                "payload": {
                    "type": "exec_command_end",
                    "call_id": "call-doc",
                    "exit_code": 0,
                    "status": "completed",
                    "aggregated_output": "docs mention error: examples, but the command succeeded",
                },
            },
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "noise-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = Path(str(receipt["session_dir"]))
    segment_index = json.loads((session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8"))
    records = {event["event_id"]: event for event in segment_index["events"]}

    assert records["000002"]["type"] == "USER_INTENT"
    assert "final_state_signal" not in records["000002"]["tags"]
    assert records["000003"]["type"] == "CONTEXT_STATE"
    assert "security_policy_signal" in records["000003"]["tags"]
    assert "final_state_signal" not in records["000003"]["tags"]
    assert records["000004"]["type"] == "ASSISTANT_MESSAGE"
    assert "decision_signal" in records["000004"]["tags"]
    assert records["000005"]["type"] == "DECISION"
    assert records["000006"]["type"] == "COMMAND_OUTPUT"
    assert records["000006"]["outcome"] == "succeeded"
    assert "error_signal" not in records["000006"]["tags"]


def test_empty_nonzero_command_output_is_not_promoted_to_error(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-empty-nonzero.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "empty-nonzero", "cwd": str(workspace)}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Search for a marker"}]}},
            {"timestamp": "2026-05-12T00:00:02Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-rg", "arguments": json.dumps({"cmd": "rg -n missing-marker README.md"})}},
            {"timestamp": "2026-05-12T00:00:03Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-rg", "output": "Chunk ID: x\nProcess exited with code 1\nOriginal token count: 0\nOutput:\n"}},
        ],
    )

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "empty-nonzero",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = aoa_root / "sessions" / "2026-05-12__001__search-for-a-marker"
    segment_index = json.loads((session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8"))
    output_event = {event["event_id"]: event for event in segment_index["events"]}["000004"]
    assert output_event["type"] == "COMMAND_OUTPUT"
    assert output_event["outcome"] == "failed"
    assert "empty_nonzero_output_signal" in output_event["tags"]
    assert "error_signal" not in output_event["tags"]


def test_security_risk_is_strict_and_tmp_cleanup_is_not_risk(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-security.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "security-session", "cwd": str(workspace)}},
            {
                "timestamp": "2026-05-12T00:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Do not write secrets into exports."}]},
            },
            {
                "timestamp": "2026-05-12T00:00:02Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Secret/data leak check completed before export."}]},
            },
            {
                "timestamp": "2026-05-12T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "MAILERSEND_API_KEY is configured; value is not shown."}]},
            },
            {
                "timestamp": "2026-05-12T00:00:04Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Token leaked in logs; rotate it."}]},
            },
            {
                "timestamp": "2026-05-12T00:00:05Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-tmp", "arguments": json.dumps({"cmd": "rm -rf /tmp/aoa-demo && mkdir -p /tmp/aoa-demo"})},
            },
            {
                "timestamp": "2026-05-12T00:00:06Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-cache",
                    "arguments": json.dumps({"cmd": "rm -rf /srv/AbyssOS/.aoa/scripts/__pycache__ /srv/AbyssOS/.aoa/tests/.pytest_cache"}),
                },
            },
            {
                "timestamp": "2026-05-12T00:00:07Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "name": "exec_command",
                    "call_id": "call-find-cache",
                    "arguments": json.dumps({"cmd": "find /srv/AbyssOS/.aoa -type d -name __pycache__ -prune -exec rm -rf {} +"}),
                },
            },
            {
                "timestamp": "2026-05-12T00:00:08Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-risk", "arguments": json.dumps({"cmd": "rm -rf .aoa/recurrence"})},
            },
            {
                "timestamp": "2026-05-12T00:00:09Z",
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "call-doc",
                    "output": (
                        "# AGENTS.md\n"
                        "## Hard no\n"
                        "- do not print or commit real secrets\n"
                        "- do not read or expose secret-bearing files from live hosts\n"
                        "## Review guidelines\n"
                        "- committed live secrets or secret-bearing rendered configs\n"
                    ),
                },
            },
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "security-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = Path(str(receipt["session_dir"]))
    segment_index = json.loads((session_dir / "segments" / "000__initial-to-latest.index.json").read_text(encoding="utf-8"))
    records = {event["event_id"]: event for event in segment_index["events"]}

    assert records["000002"]["type"] == "ASSISTANT_MESSAGE"
    assert "security_policy_signal" in records["000002"]["tags"]
    assert records["000003"]["type"] == "ASSISTANT_MESSAGE"
    assert "security_policy_signal" in records["000003"]["tags"]
    assert records["000004"]["type"] == "SECURITY_TOUCHPOINT"
    assert "security_touchpoint_signal" in records["000004"]["tags"]
    assert records["000005"]["type"] == "SECURITY_OR_SECRET_RISK"
    assert records["000006"]["type"] == "FILE_WRITE"
    assert records["000006"]["facets"]["command_kind"] == "temporary_cleanup"
    assert records["000007"]["type"] == "FILE_WRITE"
    assert records["000007"]["facets"]["command_kind"] == "temporary_cleanup"
    assert records["000008"]["type"] == "FILE_WRITE"
    assert records["000008"]["facets"]["command_kind"] == "temporary_cleanup"
    assert records["000009"]["type"] == "SECURITY_OR_SECRET_RISK"
    assert records["000010"]["type"] == "SECURITY_TOUCHPOINT"
    assert "security_touchpoint_signal" in records["000010"]["tags"]


def test_reindex_sessions_regenerates_universal_indexes_from_raw(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-reindex.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "reindex-session", "cwd": str(workspace)}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Reindex this"}]}},
            {"timestamp": "2026-05-12T00:00:02Z", "type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-rg", "arguments": json.dumps({"cmd": "rg -n x README.md"})}},
            {"timestamp": "2026-05-12T00:00:03Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-rg", "output": "Process exited with code 0\nOutput:\n"}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "reindex-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    session_dir = aoa_root / "sessions" / "2026-05-12__001__reindex-this"
    index_path = session_dir / "segments" / "000__initial-to-latest.index.json"
    broken = json.loads(index_path.read_text(encoding="utf-8"))
    broken.pop("by_family", None)
    for event in broken["events"]:
        event.pop("family", None)
    index_path.write_text(json.dumps(broken, ensure_ascii=False), encoding="utf-8")

    payload = module.reindex_sessions(aoa_root=aoa_root, target="all", write_report=True)

    rebuilt = json.loads(index_path.read_text(encoding="utf-8"))
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    registry = json.loads((aoa_root / "session-registry.json").read_text(encoding="utf-8"))
    assert payload["counts"] == {"reindexed": 1}
    assert payload["results"][0]["raw_block_count"] == 1
    assert payload["results"][0]["raw_blocks_index"] == str(session_dir / "raw" / "blocks.index.json")
    assert Path(payload["report_json"]).exists()
    assert "workspace_navigation" in rebuilt["by_family"]
    assert rebuilt["events"][2]["family"] == "workspace_navigation"
    assert manifest["index_schema"]["universal_event_facets"] is True
    assert manifest["raw_blocks"]["blocks"][0]["role"] == "initial-to-latest"
    assert registry["sessions"][0]["raw_blocks"]["block_count"] == 1

    bounded = module.reindex_sessions(aoa_root=aoa_root, target="all", max_raw_bytes=1)
    assert bounded["counts"] == {"skipped": 1}
    assert bounded["results"][0]["status"] == "skipped"
    assert bounded["results"][0]["diagnostics"][0].startswith("raw_too_large:")


def test_raw_unavailable_writes_diagnostic(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    missing = tmp_path / "missing.jsonl"

    receipt = module.handle_hook_event(
        "SessionStart",
        {
            "session_id": "missing-session",
            "transcript_path": str(missing),
            "cwd": str(workspace),
            "hook_event_name": "SessionStart",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    assert receipt["ok"] is True
    session_dir = Path(receipt["session_dir"])
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_status"] == "raw_unavailable"
    assert manifest["session_id"] == "missing-session"
    assert manifest["display"]["label"].endswith("__codex-in-abyssos")
    assert manifest["display"]["path"] == str(session_dir)
    assert list((session_dir / "incidents").glob("*__INCIDENT.md"))
    assert list((session_dir / "incidents").glob("*__DIAGNOSTIC.json"))


def test_user_prompt_submit_is_light_by_default(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-session-light.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "session-light"}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user"}},
        ],
    )
    monkeypatch.delenv("AOA_SESSION_MEMORY_FULL_PROMPT_SYNC", raising=False)

    receipt = module.handle_hook_event(
        "UserPromptSubmit",
        {
            "session_id": "session-light",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "UserPromptSubmit",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = aoa_root / "sessions" / "session-light"
    assert receipt["ok"] is True
    assert "prompt_hook_light_recorded" in receipt["actions"]
    assert (session_dir / "hooks" / "events.jsonl").exists()
    assert not (session_dir / "raw" / "session.raw.jsonl").exists()
    assert not (session_dir / "session.manifest.json").exists()


def test_user_prompt_submit_mirrors_prompt_to_typing_bridge(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-session-typing-bridge.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "session-typing-bridge"}},
        ],
    )

    calls: list[dict[str, Any]] = []

    def fake_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append({"command": command, "input": kwargs.get("input")})
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {
                    "ok": True,
                    "status": "ingested",
                    "typing_event": {
                        "event_id": "typing-codex-prompt",
                        "status": "captured",
                        "capture_gate_decision": "allow_text",
                    },
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(module.shutil, "which", lambda name: "/usr/bin/abyss-machine" if name == "abyss-machine" else None)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.delenv("AOA_SESSION_MEMORY_FULL_PROMPT_SYNC", raising=False)

    receipt = module.handle_hook_event(
        "UserPromptSubmit",
        {
            "session_id": "session-typing-bridge",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "UserPromptSubmit",
            "prompt": "live Codex prompt bridge probe",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    assert receipt["ok"] is True
    assert "typing_prompt_mirrored" in receipt["actions"]
    assert receipt["typing_bridge"]["event_id"] == "typing-codex-prompt"
    assert receipt["typing_bridge"]["capture_gate_decision"] == "allow_text"
    assert calls
    assert calls[0]["command"] == ["/usr/bin/abyss-machine", "typing", "codex-prompt-hook", "--json"]
    assert "live Codex prompt bridge probe" in calls[0]["input"]


def test_session_start_is_light_by_default_when_raw_exists(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-session-start-light.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "session-start-light"}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Start should stay light"}]}},
        ],
    )
    monkeypatch.delenv("AOA_SESSION_MEMORY_FULL_START_SYNC", raising=False)

    receipt = module.handle_hook_event(
        "SessionStart",
        {
            "session_id": "session-start-light",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "SessionStart",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = aoa_root / "sessions" / "session-start-light"
    assert receipt["ok"] is True
    assert "session_start_hook_light_recorded" in receipt["actions"]
    assert "raw_sync_deferred" in receipt["actions"]
    assert "indexing_deferred" in receipt["actions"]
    assert "background_sync_queued" in receipt["actions"]
    assert receipt["background_job"].endswith(".json")
    assert (session_dir / "hooks" / "events.jsonl").exists()
    assert not (session_dir / "raw" / "session.raw.jsonl").exists()
    assert not (session_dir / "session.manifest.json").exists()


def test_large_lifecycle_hook_defers_raw_mirror_by_size(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-session-large-hook.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "session-large-hook"}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Large hook mirror"}]}},
        ],
    )
    monkeypatch.delenv("AOA_SESSION_MEMORY_FULL_COMPACT_SYNC", raising=False)
    monkeypatch.setenv("AOA_SESSION_MEMORY_HOOK_MIRROR_MAX_BYTES", "1")

    receipt = module.handle_hook_event(
        "PreCompact",
        {
            "session_id": "session-large-hook",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "PreCompact",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = aoa_root / "sessions" / "session-large-hook"
    assert receipt["ok"] is True
    assert "raw_mirror_deferred" in receipt["actions"]
    assert "indexing_deferred" in receipt["actions"]
    assert "background_sync_queued" in receipt["actions"]
    assert receipt["raw"]["mirror_status"] == "deferred_from_hook"
    assert (session_dir / "hooks" / "events.jsonl").exists()
    assert not (session_dir / "raw" / "session.raw.jsonl").exists()
    assert not (session_dir / "session.manifest.json").exists()


def test_hook_worker_processes_deferred_sync_job(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-session-worker-auto.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "session-worker-auto"}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Worker automatic sync"}]}},
            {"timestamp": "2026-05-12T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: worker syncs outside hook"}]}},
        ],
    )
    monkeypatch.delenv("AOA_SESSION_MEMORY_FULL_START_SYNC", raising=False)

    receipt = module.handle_hook_event(
        "SessionStart",
        {
            "session_id": "session-worker-auto",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "SessionStart",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    assert "background_sync_queued" in receipt["actions"]
    payload = module.run_hook_worker(workspace_root=workspace, aoa_root=aoa_root, limit=5)

    session_dir = aoa_root / "sessions" / "2026-05-12__001__worker-automatic-sync"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["processed"] == 1
    assert manifest["archive_status"] == "indexed"
    assert manifest["latest_event_count"] == 3
    assert (session_dir / "segments" / "000__initial-to-latest.index.json").exists()
    assert not list((aoa_root / module.HOOK_JOBS_ROOT / "pending").glob("*.json"))
    assert list((aoa_root / module.HOOK_JOBS_ROOT / "done").glob("*.json"))


def test_hook_worker_skips_fresh_deferred_sync_job(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-session-worker-fresh.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "session-worker-fresh"}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Worker freshness guard"}]}},
            {"timestamp": "2026-05-12T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: build once"}]}},
        ],
    )
    monkeypatch.delenv("AOA_SESSION_MEMORY_FULL_START_SYNC", raising=False)

    receipt = module.handle_hook_event(
        "SessionStart",
        {
            "session_id": "session-worker-fresh",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "SessionStart",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    assert "background_sync_queued" in receipt["actions"]

    first = module.run_hook_worker(workspace_root=workspace, aoa_root=aoa_root, limit=5)
    assert first["ok"] is True
    assert first["results"][0]["status"] == "synced"

    job_path = module.enqueue_hook_sync_job(
        aoa_root,
        event_name="Stop",
        event={"session_id": "session-worker-fresh", "transcript_path": str(transcript), "cwd": str(workspace)},
        session_id="session-worker-fresh",
        transcript_path=transcript,
        reason="test_duplicate_fresh_sync",
    )
    assert job_path is not None

    second = module.run_hook_worker(workspace_root=workspace, aoa_root=aoa_root, limit=5)
    session_dir = aoa_root / "sessions" / "2026-05-12__001__worker-freshness-guard"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert second["ok"] is True
    assert second["processed"] == 1
    assert second["results"][0]["status"] == "already_synced"
    assert second["results"][0]["freshness"]["reason"] == "indexed_archive_matches_transcript_snapshot"
    assert manifest["archive_status"] == "indexed"
    assert manifest["latest_event_count"] == 3
    assert "HookWorker:Stop" in manifest["hooks_seen"]
    assert not list((aoa_root / module.HOOK_JOBS_ROOT / "pending").glob("*.json"))


def test_hook_worker_recovers_orphaned_running_job(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-session-worker-orphan.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "session-worker-orphan"}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Recover orphaned worker job"}]}},
        ],
    )
    running_dir = aoa_root / module.HOOK_JOBS_ROOT / "running"
    running_dir.mkdir(parents=True)
    running_job = running_dir / "orphaned-sync.json"
    running_job.write_text(
        json.dumps(
            {
                "schema_version": module.SCHEMA_VERSION,
                "job_type": "hook_sync_transcript",
                "queued_at": "2026-05-12T00:00:02Z",
                "event_name": "PreCompact",
                "session_id": "session-worker-orphan",
                "transcript_path": str(transcript),
                "cwd": str(workspace),
                "reason": "test_orphaned_running_job",
                "event": {"session_id": "session-worker-orphan", "transcript_path": str(transcript), "cwd": str(workspace)},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    payload = module.run_hook_worker(workspace_root=workspace, aoa_root=aoa_root, limit=5)
    session_dir = aoa_root / "sessions" / "2026-05-12__001__recover-orphaned-worker-job"

    assert payload["ok"] is True
    assert payload["processed"] == 1
    assert payload["recovered_running"][0]["status"] == "requeued_orphaned_running_job"
    assert payload["results"][0]["status"] == "synced"
    assert not list(running_dir.glob("*.json"))
    assert (session_dir / "session.manifest.json").exists()


def test_hook_worker_respects_job_limit(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"

    for index in range(7):
        session_id = f"session-worker-drain-{index}"
        transcript = tmp_path / f"rollout-2026-05-12T00-00-0{index}-{session_id}.jsonl"
        write_jsonl(
            transcript,
            [
                {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": session_id}},
                {
                    "timestamp": "2026-05-12T00:00:01Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": f"Worker drain {index}"}],
                    },
                },
            ],
        )
        job_path = module.enqueue_hook_sync_job(
            aoa_root,
            event_name="SessionStart",
            event={"session_id": session_id, "transcript_path": str(transcript), "cwd": str(workspace)},
            session_id=session_id,
            transcript_path=transcript,
            reason="test_worker_drain",
        )
        assert job_path is not None

    payload = module.run_hook_worker(workspace_root=workspace, aoa_root=aoa_root, limit=2)

    assert payload["ok"] is True
    assert payload["processed"] == 2
    assert len(list((aoa_root / module.HOOK_JOBS_ROOT / "pending").glob("*.json"))) == 5
    assert len(list((aoa_root / module.HOOK_JOBS_ROOT / "done").glob("*.json"))) == 2


def test_hook_worker_defers_sync_jobs_over_raw_budget(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-session-worker-huge.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "session-worker-huge"}},
            {
                "timestamp": "2026-05-12T00:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Huge worker budget"}]},
            },
        ],
    )
    monkeypatch.setenv("AOA_SESSION_MEMORY_HOOK_WORKER_MAX_RAW_BYTES", "1")
    job_path = module.enqueue_hook_sync_job(
        aoa_root,
        event_name="SessionStart",
        event={"session_id": "session-worker-huge", "transcript_path": str(transcript), "cwd": str(workspace)},
        session_id="session-worker-huge",
        transcript_path=transcript,
        reason="test_worker_budget",
    )
    assert job_path is not None

    payload = module.run_hook_worker(workspace_root=workspace, aoa_root=aoa_root, limit=5)

    assert payload["ok"] is True
    assert payload["processed"] == 1
    assert payload["results"][0]["status"] == "deferred_over_worker_budget"
    assert payload["results"][0]["transcript_bytes"] > payload["results"][0]["max_raw_bytes"]
    assert not (aoa_root / "sessions" / "session-worker-huge" / "session.manifest.json").exists()
    assert not list((aoa_root / module.HOOK_JOBS_ROOT / "pending").glob("*.json"))
    assert len(list((aoa_root / module.HOOK_JOBS_ROOT / "done").glob("*.json"))) == 1


def test_hook_registry_lock_contention_defers_registry_update(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-12T00-00-00-session-lock.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-12T00:00:00Z", "type": "session_meta", "payload": {"id": "session-lock"}},
            {"timestamp": "2026-05-12T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Registry lock hook"}]}},
        ],
    )
    lock_path = aoa_root / ".session-registry.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_handle:
        module.fcntl.flock(lock_handle, module.fcntl.LOCK_EX)
        receipt = module.handle_hook_event(
            "Stop",
            {
                "session_id": "session-lock",
                "transcript_path": str(transcript),
                "cwd": str(workspace),
                "hook_event_name": "Stop",
            },
            workspace_root=workspace,
            aoa_root=aoa_root,
        )

    session_dir = aoa_root / "sessions" / "2026-05-12__001__registry-lock-hook"
    assert receipt["ok"] is True
    assert "segments_indexed" in receipt["actions"]
    assert "registry_update_deferred" in receipt["actions"]
    assert (session_dir / "session.manifest.json").exists()
    assert not (aoa_root / "session-registry.json").exists()


def test_raw_unavailable_registry_deferral_queues_retry_job(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    missing = tmp_path / "missing.jsonl"
    lock_path = aoa_root / ".session-registry.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("w", encoding="utf-8") as lock_handle:
        module.fcntl.flock(lock_handle, module.fcntl.LOCK_EX)
        receipt = module.handle_hook_event(
            "SessionStart",
            {
                "session_id": "missing-registry-retry",
                "transcript_path": str(missing),
                "cwd": str(workspace),
                "hook_event_name": "SessionStart",
            },
            workspace_root=workspace,
            aoa_root=aoa_root,
        )

    assert receipt["ok"] is True
    assert "registry_update_deferred" in receipt["actions"]
    assert "registry_update_retry_queued" in receipt["actions"]
    assert receipt["registry_update_job"].endswith("__registry-update.json")
    assert not (aoa_root / "session-registry.json").exists()

    worker = module.run_hook_worker(workspace_root=workspace, aoa_root=aoa_root, limit=5)
    registry = json.loads((aoa_root / "session-registry.json").read_text(encoding="utf-8"))

    assert worker["ok"] is True
    assert worker["processed"] == 1
    assert worker["results"][0]["status"] == "registry_updated"
    assert registry["sessions"][0]["session_id"] == "missing-registry-retry"


def test_codex_hook_output_uses_only_protocol_fields() -> None:
    receipt = {
        "ok": True,
        "session_dir": "/workspace/.aoa/sessions/demo",
        "display_name": "2026-05-12__001__demo",
        "navigation_path": "/workspace/.aoa/sessions/demo",
        "actions": ["hook_event_recorded"],
    }

    prompt_payload = module.codex_hook_output("UserPromptSubmit", receipt)
    stop_payload = module.codex_hook_output("Stop", receipt)
    pre_compact_payload = module.codex_hook_output("PreCompact", receipt)
    post_compact_payload = module.codex_hook_output("PostCompact", receipt)
    start_payload = module.codex_hook_output("SessionStart", receipt)

    assert prompt_payload == {"continue": True}
    assert stop_payload == {"continue": True}
    assert pre_compact_payload == {"continue": True}
    assert post_compact_payload == {"continue": True}
    assert "aoaSessionMemory" not in start_payload
    assert set(start_payload) == {"continue", "hookSpecificOutput"}
    assert start_payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"


def test_record_hook_receipt_writes_bounded_runtime_trace(tmp_path: Path) -> None:
    session_dir = tmp_path / "AbyssOS" / ".aoa" / "sessions" / "session-receipt"

    module.record_hook_receipt(
        {
            "hook_event_name": "Stop",
            "ok": True,
            "session_id": "session-receipt",
            "session_dir": str(session_dir),
            "actions": ["hook_event_recorded", "indexing_deferred"],
            "errors": [],
        },
        duration_ms=123,
    )

    rows = [
        json.loads(line)
        for line in (session_dir / "hooks" / "receipts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert rows == [
        {
            "schema_version": 1,
            "timestamp": rows[0]["timestamp"],
            "hook_event_name": "Stop",
            "ok": True,
            "session_id": "session-receipt",
            "actions": ["hook_event_recorded", "indexing_deferred"],
            "errors": [],
            "duration_ms": 123,
        }
    ]


def test_hooks_config_builder_uses_supplied_roots(tmp_path: Path) -> None:
    workspace = tmp_path / "portable-workspace"
    aoa_root = workspace / ".aoa"

    config = module.build_user_hooks_config(workspace, aoa_root)

    assert set(config["hooks"]) == {"SessionStart", "UserPromptSubmit", "PreCompact", "PostCompact", "Stop"}
    assert config["hooks"]["SessionStart"][0]["matcher"] == "startup|resume"
    rendered = json.dumps(config, ensure_ascii=False)
    assert str(module.default_source_aoa_root()) not in rendered
    for event_name in config["hooks"]:
        command = config["hooks"][event_name][0]["hooks"][0]["command"]
        assert str(workspace) in command
        assert str(aoa_root / "scripts" / "aoa_session_memory.py") in command
        assert f"--event-name {event_name}" in command


def test_codex_hook_lookup_tracks_trust_and_expected_commands(tmp_path: Path) -> None:
    workspace = tmp_path / "portable-workspace"
    aoa_root = workspace / ".aoa"
    expected_commands = module.expected_hook_commands(workspace, aoa_root)
    hooks = [
        {
            "key": "/home/user/.codex/hooks.json:pre_compact:0:0",
            "eventName": "preCompact",
            "command": expected_commands["PreCompact"],
            "currentHash": "sha256:pre",
            "trustStatus": "trusted",
            "enabled": True,
        },
        {
            "key": "/home/user/.codex/hooks.json:post_compact:0:0",
            "eventName": "postCompact",
            "command": expected_commands["PostCompact"],
            "currentHash": "sha256:post",
            "trustStatus": "untrusted",
            "enabled": True,
        },
        {
            "key": "/home/user/.codex/hooks.json:stop:0:0",
            "eventName": "stop",
            "command": "python3 wrong.py",
            "currentHash": "sha256:wrong",
            "trustStatus": "trusted",
            "enabled": True,
        },
    ]

    lookup = module.hook_lookup_from_app_hooks(hooks, expected_commands)
    trust_state = module.hook_trust_state_from_lookup(lookup)

    assert lookup["PreCompact"]["present"] is True
    assert lookup["PreCompact"]["trusted"] is True
    assert lookup["PostCompact"]["present"] is True
    assert lookup["PostCompact"]["trusted"] is False
    assert lookup["Stop"]["present"] is False
    assert trust_state == {
        "/home/user/.codex/hooks.json:pre_compact:0:0": {"trusted_hash": "sha256:pre"},
        "/home/user/.codex/hooks.json:post_compact:0:0": {"trusted_hash": "sha256:post"},
    }


def test_default_aoa_root_uses_script_parent() -> None:
    assert module.aoa_root_for() == SCRIPT.parents[1]


def test_lifecycle_hooks_queue_compaction_archive_and_worker_indexes(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-14T00-00-00-session-compact.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-14T00:00:00Z", "type": "session_meta", "payload": {"id": "session-compact"}},
            {"timestamp": "2026-05-14T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Archive compaction intervals"}]}},
            {"timestamp": "2026-05-14T00:00:02Z", "type": "turn_context", "payload": {"summary": "first compaction"}},
            {"timestamp": "2026-05-14T00:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: keep interval archive"}]}},
        ],
    )
    monkeypatch.delenv("AOA_SESSION_MEMORY_FULL_COMPACT_SYNC", raising=False)
    monkeypatch.delenv("AOA_SESSION_MEMORY_FULL_STOP_SYNC", raising=False)
    monkeypatch.setenv("AOA_SESSION_MEMORY_STOP_SYNC_MAX_BYTES", "0")

    pre = module.handle_hook_event(
        "PreCompact",
        {
            "session_id": "session-compact",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "PreCompact",
            "trigger": "auto",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    post = module.handle_hook_event(
        "PostCompact",
        {
            "session_id": "session-compact",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "PostCompact",
            "trigger": "auto",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    assert pre["ok"] is True
    assert post["ok"] is True
    assert "indexing_deferred" in pre["actions"]
    assert "indexing_deferred" in post["actions"]
    assert "background_sync_queued" in pre["actions"]
    assert "background_sync_queued" in post["actions"]
    light_session_dir = aoa_root / "sessions" / "2026-05-14__001__codex-in-abyssos"
    light_manifest = json.loads((light_session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert light_manifest["archive_status"] == "raw_mirrored_index_deferred"
    assert light_manifest["hooks_seen"] == ["PostCompact", "PreCompact"]
    assert light_manifest["segments"] == []
    assert (light_session_dir / "raw" / "session.raw.jsonl").exists()

    worker = module.run_hook_worker(workspace_root=workspace, aoa_root=aoa_root, limit=5)
    assert worker["ok"] is True
    assert worker["processed"] == 2
    session_dir = aoa_root / "sessions" / "2026-05-14__001__archive-compaction-intervals"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_status"] == "indexed"
    assert manifest["archive_format_version"] == 2
    assert manifest["hooks_seen"] == ["HookWorker:PostCompact", "HookWorker:PreCompact", "PostCompact", "PreCompact"]
    assert [segment["role"] for segment in manifest["segments"]] == ["initial-to-compaction", "compaction-to-latest"]
    assert not light_session_dir.exists()
    raw_blocks = manifest["raw_blocks"]["blocks"]
    assert [block["role"] for block in raw_blocks] == ["initial-to-compaction", "compaction-to-latest"]
    assert raw_blocks[0]["status"] == "sealed"
    assert raw_blocks[1]["status"] == "open"
    assert (session_dir / "raw" / "blocks.index.json").exists()
    assert (session_dir / "raw" / "compaction-events.jsonl").exists()
    assert (session_dir / "raw" / "blocks" / "000__initial-to-compaction.raw.jsonl").exists()
    first_segment_index = json.loads((session_dir / "segments" / "000__initial-to-compaction.index.json").read_text(encoding="utf-8"))
    assert first_segment_index["source_block"]["rel"] == "raw/blocks/000__initial-to-compaction.raw.jsonl"
    assert manifest["segments"][0]["raw_block"]["rel"] == "raw/blocks/000__initial-to-compaction.raw.jsonl"
    compaction_events = [
        json.loads(line)
        for line in (session_dir / "raw" / "compaction-events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert compaction_events
    assert compaction_events[0]["segment_id"] == "000"

    stop = module.handle_hook_event(
        "Stop",
        {
            "session_id": "session-compact",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    assert stop["ok"] is True
    assert "indexing_deferred" in stop["actions"]
    assert "background_sync_queued" in stop["actions"]
    stop_manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert stop_manifest["archive_status"] == "raw_mirrored_index_deferred"
    assert stop_manifest["hooks_seen"] == ["HookWorker:PostCompact", "HookWorker:PreCompact", "PostCompact", "PreCompact", "Stop"]
    assert stop_manifest["segments"] == []
    assert stop_manifest["latest_event_count"] == 0

    deferred_audit = module.completion_audit(workspace_root=workspace, aoa_root=aoa_root, check_codex=False)
    topology = [
        item for item in deferred_audit["checklist"] if item["requirement"] == "Segment topology matches raw compaction boundaries"
    ][0]
    assert topology["status"] == "missing"
    assert topology["evidence"]["deferred_archives"][0]["archive_status"] == "raw_mirrored_index_deferred"

    stop_worker = module.run_hook_worker(workspace_root=workspace, aoa_root=aoa_root, limit=5)
    assert stop_worker["ok"] is True
    assert stop_worker["processed"] == 1
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_status"] == "indexed"
    assert [segment["role"] for segment in manifest["segments"]] == ["initial-to-compaction", "compaction-to-latest"]

    synced = module.sync_session_from_transcript(
        aoa_root=aoa_root,
        event={"session_id": "session-compact", "transcript_path": str(transcript), "cwd": str(workspace)},
        transcript_path=transcript,
        hook_event_name="ManualSync",
    )
    assert synced["segment_count"] == 2
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_status"] == "indexed"
    assert manifest["archive_format_version"] == 2
    assert "ManualSync" in manifest["hooks_seen"]
    assert "Stop" in manifest["hooks_seen"]
    assert [segment["role"] for segment in manifest["segments"]] == ["initial-to-compaction", "compaction-to-latest"]
    assert manifest["segments"][0]["raw_block"]["sha256"]
    packet = module.rehydrate_packet(aoa_root, "latest")
    assert "AoA Session Rehydration Packet" in packet
    assert "2026-05-14__001__archive-compaction-intervals" in packet
    assert "`DECISION`" in packet


def test_real_codex_compacted_events_define_segments(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-14T01-00-00-session-real-compact.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-14T01:00:00Z", "type": "session_meta", "payload": {"id": "session-real-compact"}},
            {"timestamp": "2026-05-14T01:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Real compact markers"}]}},
            {"timestamp": "2026-05-14T01:00:02Z", "type": "compacted", "payload": {"message": "", "replacement_history": [{"type": "message", "role": "user"}]}},
            {"timestamp": "2026-05-14T01:00:03Z", "type": "event_msg", "payload": {"type": "context_compacted"}},
            {"timestamp": "2026-05-14T01:00:04Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: real markers are boundaries"}]}},
        ],
    )

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "session-real-compact",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    assert receipt["ok"] is True
    session_dir = aoa_root / "sessions" / "2026-05-14__001__real-compact-markers"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert [segment["role"] for segment in manifest["segments"]] == [
        "initial-to-compaction",
        "compaction-to-latest",
    ]
    first_index = json.loads(Path(manifest["segments"][0]["index"]).read_text(encoding="utf-8"))
    assert first_index["source_range"] == {"from_line": 1, "to_line": 4}
    assert first_index["by_type"]["COMPACTION_EVENT"] == ["000003", "000004"]


def test_stress_pass_audits_first_compaction_intervals(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-14T03-00-00-session-stress.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-14T03:00:00Z", "type": "session_meta", "payload": {"id": "session-stress"}},
            {"timestamp": "2026-05-14T03:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Stress compact intervals"}]}},
            {"timestamp": "2026-05-14T03:00:02Z", "type": "compacted", "payload": {"replacement_history": []}},
            {"timestamp": "2026-05-14T03:00:03Z", "type": "turn_context", "payload": {"summary": "none"}},
            {"timestamp": "2026-05-14T03:00:04Z", "type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_count": 100}}},
            {"timestamp": "2026-05-14T03:00:05Z", "type": "event_msg", "payload": {"type": "context_compacted"}},
            {"timestamp": "2026-05-14T03:00:06Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "first interval closed"}]}},
            {"timestamp": "2026-05-14T03:00:07Z", "type": "compacted", "payload": {"replacement_history": []}},
            {"timestamp": "2026-05-14T03:00:08Z", "type": "event_msg", "payload": {"type": "context_compacted"}},
            {"timestamp": "2026-05-14T03:00:09Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "tail"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "session-stress",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    stress = module.session_stress_pass(aoa_root, "latest", compaction_count=2, write=True)

    assert stress["ok"] is True
    assert stress["selected_segment_ids"] == ["000", "001"]
    assert stress["selected_source_span"] == {"from_line": 1, "to_line": 9}
    assert stress["selected_event_counts"]["COMPACTION_EVENT"] == 4
    assert Path(stress["artifacts"]["json"]).exists()
    assert Path(stress["artifacts"]["markdown"]).exists()
    compact_print = module.stress_pass_print_payload(stress)
    assert "segment_summaries" not in compact_print
    assert compact_print["segment_summary_count"] == 2
    assert compact_print["segment_summaries_omitted"] == 0

    show = module.session_show_payload(aoa_root, "latest", max_segments=1)
    assert show["manifest"]["segment_count"] == 3
    assert len(show["manifest"]["segments_preview"]) == 1
    assert show["manifest"]["segments_truncated"] is True
    full = module.session_show_payload(aoa_root, "latest", full=True)
    assert len(full["manifest"]["segments"]) == 3


def test_session_source_uses_hook_metadata_for_manual_sync(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    write_jsonl(
        session_dir / "hooks" / "events.jsonl",
        [
            {
                "schema_version": 1,
                "timestamp": "2026-05-14T04:00:00Z",
                "hook_event_name": "Stop",
                "event": {
                    "cwd": "/workspace/AbyssOS",
                    "model": "gpt-5.5",
                    "permission_mode": "bypassPermissions",
                    "turn_id": "turn-from-hook",
                },
            }
        ],
    )

    source = module.session_source(
        {"cwd": "/workspace/AbyssOS"},
        tmp_path / "session.raw.jsonl",
        hook_source=module.hook_source_metadata(session_dir),
    )

    assert source["model"] == "gpt-5.5"
    assert source["permission_mode"] == "bypassPermissions"
    assert source["last_turn_id"] == "turn-from-hook"


def test_validate_pipeline_runs_end_to_end(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    payload = module.validate_pipeline(workspace_root=workspace, aoa_root=workspace / ".aoa")

    assert payload["ok"] is True
    checks = {check["name"]: check["ok"] for check in payload["checks"]}
    assert checks["generated_hook_config_events"] is True
    assert checks["precompact_receipt_ok"] is True
    assert checks["postcompact_receipt_ok"] is True
    assert checks["stop_receipt_ok"] is True
    assert checks["segments_include_compaction_interval"] is True
    assert checks["rehydrate_packet_preserves_decision_route"] is True
    assert checks["first_pass_distillation_has_candidates"] is True


def test_install_portable_bundle_creates_clean_target(tmp_path: Path) -> None:
    source_aoa = SCRIPT.parents[1]
    workspace = tmp_path / "TargetWorkspace"
    aoa_root = workspace / ".aoa"

    payload = module.install_portable_bundle(
        source_aoa_root=source_aoa,
        workspace_root=workspace,
        aoa_root=aoa_root,
        overwrite=True,
    )

    assert payload["ok"] is True
    assert (aoa_root / "INSTALL.md").exists()
    assert (aoa_root / "DESIGN.AGENTS.md").exists()
    assert (aoa_root / "config" / "AGENTS.md").exists()
    assert (aoa_root / "config" / "atlas-policy.json").exists()
    assert (aoa_root / "config" / "search-providers.json").exists()
    assert (aoa_root / "hooks" / "AGENTS.md").exists()
    assert (aoa_root / "maps" / "AGENTS.md").exists()
    assert (aoa_root / "maps" / "START.md").exists()
    assert (aoa_root / "maps" / "by-work-context" / "README.md").exists()
    assert (aoa_root / "maps" / "by-work-context" / "entries" / ".gitkeep").exists()
    assert not (aoa_root / "maps" / "INDEX.md").exists()
    assert not (aoa_root / module.ENTITY_REGISTRY_PATH).exists()
    assert not (aoa_root / module.ENTITY_REGISTRY_MARKDOWN).exists()
    assert not list((aoa_root / "maps" / "by-work-context" / "entries").glob("*.json"))
    assert (aoa_root / "schemas" / "AGENTS.md").exists()
    assert (aoa_root / "schemas" / "atlas-route-entry.schema.json").exists()
    assert (aoa_root / "scripts" / "AGENTS.md").exists()
    assert (aoa_root / "sessions" / "AGENTS.md").exists()
    assert (aoa_root / "skills" / "AGENTS.md").exists()
    assert (aoa_root / "tests" / "AGENTS.md").exists()
    assert (aoa_root / "scripts" / "aoa_session_memory.py").exists()
    assert (aoa_root / "tests" / "test_session_memory.py").exists()
    registry = json.loads((aoa_root / "session-registry.json").read_text(encoding="utf-8"))
    assert registry["sessions"] == []
    session_entries = sorted(path.name for path in (aoa_root / "sessions").iterdir())
    sessions_index = json.loads((aoa_root / "sessions" / module.SESSIONS_INDEX_JSON).read_text(encoding="utf-8"))
    assert session_entries == [module.SESSIONS_AGENTS_MARKDOWN, module.SESSIONS_INDEX_MARKDOWN, module.SESSIONS_INDEX_JSON]
    assert sessions_index["read_order"][0] == module.SESSIONS_AGENTS_MARKDOWN
    assert sessions_index["session_count"] == 0
    hook_example = json.loads((aoa_root / "hooks" / "codex-hooks.user.example.json").read_text(encoding="utf-8"))
    rendered_hooks = json.dumps(hook_example, ensure_ascii=False)
    assert str(module.default_source_aoa_root()) not in rendered_hooks
    assert str(workspace) in rendered_hooks
    assert str(aoa_root) in rendered_hooks

    validation = module.validate_pipeline(workspace_root=workspace, aoa_root=aoa_root)
    assert validation["ok"] is True


def test_agent_atlas_policy_matches_source_skeleton() -> None:
    source_aoa = SCRIPT.parents[1]
    policy = json.loads((source_aoa / "config" / "atlas-policy.json").read_text(encoding="utf-8"))
    axis_names = [axis["name"] for axis in policy["axes"]]

    assert policy["entry_contract"]["truth_status"] == "route_signal_not_reviewed_truth"
    assert "by-work-context" in axis_names
    assert "by-route-next-action" in axis_names
    assert "by-evidence-provenance" in axis_names
    assert "by-operator-preference" in axis_names

    for axis_name in axis_names:
        axis_dir = source_aoa / "maps" / axis_name
        assert axis_dir.is_dir()
        assert (axis_dir / "README.md").exists()
        assert (axis_dir / "entries" / ".gitkeep").exists()

    schema = json.loads((source_aoa / "schemas" / "atlas-route-entry.schema.json").read_text(encoding="utf-8"))
    assert "artifact_identity" in schema["required"]
    assert schema["properties"]["axis"]["pattern"] == "^by-[a-z0-9-]+$"
    assert schema["$defs"]["artifactIdentity"]["properties"]["owner_repo"]["const"] == "aoa-session-memory"


def test_completion_audit_portable_bundle_accepts_clean_source_without_runtime_sessions(
    tmp_path: Path, monkeypatch
) -> None:
    source_aoa = SCRIPT.parents[1]
    workspace = tmp_path / "TargetWorkspace"
    bundle_root = tmp_path / "aoa-session-memory"
    module.copy_portable_bundle(source_aoa_root=source_aoa, target_aoa_root=bundle_root, overwrite=True)
    (bundle_root / ".git").mkdir()

    def fake_remote(repo_root: Path, remote: str = "origin") -> str | None:
        if repo_root == bundle_root:
            return "git@github.com:8Dionysus/aoa-session-memory.git"
        return None

    monkeypatch.setattr(module, "git_remote_url", fake_remote)

    payload = module.completion_audit(
        workspace_root=workspace,
        aoa_root=bundle_root,
        check_codex=False,
        portable_bundle=True,
    )

    assert payload["ok"] is True
    assert payload["audit_mode"] == "portable_bundle"
    statuses = {item["requirement"]: item["status"] for item in payload["checklist"]}
    assert statuses["Portable bundle intentionally excludes local raw session archives"] == "covered"
    assert statuses["Portable bundle carries compaction logic without bundled live raw proof"] == "covered"
    assert statuses["Portable bundle has clean runtime topology without bundled segment drift"] == "covered"
    assert statuses["Portable hook examples cover required lifecycle events"] == "covered"
    assert statuses["Search provider config keeps portable SQLite authoritative and host backends optional"] == "covered"
    assert statuses["User-level router skill can be installed from the portable bundle"] == "covered"
    assert statuses["Portable bundle intentionally excludes live hook receipt archives"] == "covered"

    maintenance = module.session_memory_maintenance_status(
        workspace_root=workspace,
        aoa_root=bundle_root,
        include_timers=False,
    )
    assert maintenance["ok"] is True
    assert maintenance["recommendation"] == "install_or_bootstrap_runtime"
    assert maintenance["agent_route"]["action"] == "install_or_bootstrap_runtime"
    assert maintenance["agent_route"]["bootstrap_required"] is True
    assert maintenance["portable_clean_runtime"]["ok"] is True
    assert maintenance["diagnostics"] == []


def test_force_export_clear_preserves_git_metadata(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    git_dir = target / ".git"
    stale_dir = target / "stale"
    stale_file = target / "stale.txt"
    git_dir.mkdir(parents=True)
    (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    stale_dir.mkdir()
    (stale_dir / "old.txt").write_text("old\n", encoding="utf-8")
    stale_file.write_text("old\n", encoding="utf-8")

    module.clear_export_target_for_force(target)

    assert git_dir.exists()
    assert (git_dir / "HEAD").exists()
    assert not stale_dir.exists()
    assert not stale_file.exists()


def test_install_portable_bundle_preserves_existing_sessions(tmp_path: Path) -> None:
    source_aoa = SCRIPT.parents[1]
    workspace = tmp_path / "ExistingWorkspace"
    aoa_root = workspace / ".aoa"
    session_dir = aoa_root / "sessions" / "2026-05-12__001__existing-session"
    session_dir.mkdir(parents=True)
    registry_path = aoa_root / "session-registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sessions": [
                    {
                        "session_id": "existing-session",
                        "session_label": "2026-05-12__001__existing-session",
                        "path": str(session_dir),
                    }
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    module.install_portable_bundle(
        source_aoa_root=source_aoa,
        workspace_root=workspace,
        aoa_root=aoa_root,
        overwrite=True,
    )

    assert session_dir.exists()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry["sessions"][0]["session_id"] == "existing-session"


def test_install_user_skill_symlinks_router_and_is_idempotent(tmp_path: Path) -> None:
    source_aoa = SCRIPT.parents[1]
    skills_dir = tmp_path / "skills"
    source_skill = source_aoa / "skills" / module.USER_LEVEL_SKILL_NAME

    payload = module.install_user_skill(aoa_root=source_aoa, skills_dir=skills_dir)

    target = skills_dir / module.USER_LEVEL_SKILL_NAME
    assert payload["ok"] is True
    assert payload["installed"] is True
    assert target.is_symlink()
    assert target.resolve() == source_skill.resolve()
    state = module.user_skill_install_state(source_aoa, skills_dir)
    assert state["ok"] is True
    assert state["linked_to_source"] is True

    second = module.install_user_skill(aoa_root=source_aoa, skills_dir=skills_dir)
    assert second["ok"] is True
    assert second["already_installed"] is True
    assert second["installed"] is False


def test_install_user_skill_backs_up_conflicting_target_on_force(tmp_path: Path) -> None:
    source_aoa = SCRIPT.parents[1]
    skills_dir = tmp_path / "skills"
    target = skills_dir / module.USER_LEVEL_SKILL_NAME
    target.mkdir(parents=True)
    (target / "SKILL.md").write_text("---\nname: old\ndescription: old\n---\n", encoding="utf-8")

    blocked = module.install_user_skill(aoa_root=source_aoa, skills_dir=skills_dir)
    assert blocked["ok"] is False
    assert blocked["installed"] is False
    assert target.is_dir()

    replaced = module.install_user_skill(aoa_root=source_aoa, skills_dir=skills_dir, force=True)
    assert replaced["ok"] is True
    assert replaced["installed"] is True
    assert replaced["backup_path"]
    assert Path(replaced["backup_path"]).exists()
    assert target.is_symlink()


def test_install_user_skill_accepts_relative_aoa_root(tmp_path: Path, monkeypatch) -> None:
    aoa_root = tmp_path / "bundle"
    source = aoa_root / "skills" / module.USER_LEVEL_SKILL_NAME
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: aoa-session-memory-global-route\ndescription: route\n---\n",
        encoding="utf-8",
    )
    skills_dir = tmp_path / "user-skills"

    monkeypatch.chdir(aoa_root)
    payload = module.install_user_skill(aoa_root=Path("."), skills_dir=skills_dir)

    target = skills_dir / module.USER_LEVEL_SKILL_NAME
    assert payload["ok"] is True
    assert target.is_symlink()
    assert target.resolve() == source.resolve()


def test_import_codex_sessions_dry_run_import_and_skip(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    source_root = tmp_path / "codex-sessions"
    transcript = source_root / "2026" / "05" / "02" / "rollout-2026-05-02T12-00-00-import-session.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-05-02T12:00:00Z",
                "type": "session_meta",
                "payload": {"id": "import-session", "cwd": str(workspace), "timestamp": "2026-05-02T12:00:00Z"},
            },
            {
                "timestamp": "2026-05-02T12:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Import old session properly"}],
                },
            },
        ],
    )

    dry = module.import_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        dry_run=True,
        write_report=True,
    )

    assert dry["ok"] is True
    assert dry["counts"] == {"planned": 1}
    assert Path(dry["report_json"]).exists()
    assert Path(dry["report_markdown"]).exists()

    imported = module.import_codex_sessions(aoa_root=aoa_root, source_root=source_root, since="2026-05-01")
    assert imported["ok"] is True
    assert imported["counts"] == {"imported": 1}
    session_dir = Path(imported["results"][0]["session_dir"])
    assert session_dir.name == "2026-05-02__001__import-session-properly"
    assert (session_dir / "raw" / "session.raw.jsonl").exists()

    skipped = module.import_codex_sessions(aoa_root=aoa_root, source_root=source_root, since="2026-05-01")
    assert skipped["ok"] is True
    assert skipped["counts"] == {"skipped_existing": 1}


def test_sweep_codex_sessions_repairs_missing_and_stale_transcripts(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    source_root = tmp_path / "codex-sessions"
    transcript = source_root / "2026" / "05" / "03" / "rollout-2026-05-03T12-00-00-sweep-session.jsonl"
    rows = [
        {
            "timestamp": "2026-05-03T12:00:00Z",
            "type": "session_meta",
            "payload": {"id": "sweep-session", "cwd": str(workspace), "timestamp": "2026-05-03T12:00:00Z"},
        },
        {
            "timestamp": "2026-05-03T12:00:01Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Sweep the missing Codex transcript"}],
            },
        },
    ]
    write_jsonl(transcript, rows)
    old_transcript = source_root / "2026" / "04" / "01" / "rollout-2026-04-01T12-00-00-old-sweep-session.jsonl"
    write_jsonl(
        old_transcript,
        [
            {
                "timestamp": "2026-04-01T12:00:00Z",
                "type": "session_meta",
                "payload": {"id": "old-sweep-session", "cwd": str(workspace), "timestamp": "2026-04-01T12:00:00Z"},
            },
            {
                "timestamp": "2026-04-01T12:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Old sweep session"}]},
            },
        ],
    )

    dry = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        min_age_seconds=0,
        write_report=True,
    )

    assert dry["ok"] is True
    assert dry["discovered_count"] == 1
    assert dry["counts"] == {"planned": 1}
    assert dry["repair_candidate_count"] == 1
    assert dry["results"][0]["freshness_reason"] == "missing_manifest"
    assert Path(dry["report_json"]).exists()
    assert Path(dry["report_markdown"]).exists()

    synced = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        apply=True,
        min_age_seconds=0,
    )
    assert synced["ok"] is True
    assert synced["counts"] == {"synced": 1}
    session_dir = Path(synced["results"][0]["session_dir"])
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert manifest["archive_status"] == "indexed"
    assert manifest["latest_event_count"] == 2
    assert "CodexSessionSweep" in manifest["hooks_seen"]

    fresh = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        min_age_seconds=0,
    )
    assert fresh["counts"] == {"skipped_fresh": 1}

    write_jsonl(
        transcript,
        rows
        + [
            {
                "timestamp": "2026-05-03T12:00:02Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Sweeper catches stale transcripts."}]},
            }
        ],
    )

    stale = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        min_age_seconds=0,
    )
    assert stale["counts"] == {"planned": 1}
    assert stale["results"][0]["freshness_reason"] == "source_size_changed"

    resynced = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        apply=True,
        min_age_seconds=0,
    )
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert resynced["counts"] == {"synced": 1}
    assert manifest["latest_event_count"] == 3


def test_sweep_codex_sessions_repairs_deferred_stop_archive(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    source_root = tmp_path / "codex-sessions"
    transcript = source_root / "2026" / "05" / "04" / "rollout-2026-05-04T12-00-00-sweep-deferred.jsonl"
    write_jsonl(
        transcript,
        [
            {
                "timestamp": "2026-05-04T12:00:00Z",
                "type": "session_meta",
                "payload": {"id": "sweep-deferred", "cwd": str(workspace), "timestamp": "2026-05-04T12:00:00Z"},
            },
            {
                "timestamp": "2026-05-04T12:00:01Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Close with deferred Stop archive"}],
                },
            },
        ],
    )
    monkeypatch.delenv("AOA_SESSION_MEMORY_FULL_STOP_SYNC", raising=False)
    monkeypatch.setenv("AOA_SESSION_MEMORY_STOP_SYNC_MAX_BYTES", "0")

    receipt = module.handle_hook_event(
        "Stop",
        {
            "session_id": "sweep-deferred",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    assert receipt["ok"] is True
    assert "indexing_deferred" in receipt["actions"]
    assert "background_sync_queued" in receipt["actions"]
    deferred_dir = module.session_dir_for_id(aoa_root, "sweep-deferred")
    deferred_manifest = json.loads((deferred_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert deferred_manifest["archive_status"] == "raw_mirrored_index_deferred"

    dry = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        min_age_seconds=0,
    )
    assert dry["counts"] == {"planned": 1}
    assert dry["results"][0]["freshness_reason"] == "archive_not_indexed"

    synced = module.sweep_codex_sessions(
        aoa_root=aoa_root,
        source_root=source_root,
        since="2026-05-01",
        apply=True,
        min_age_seconds=0,
    )
    session_dir = module.session_dir_for_id(aoa_root, "sweep-deferred")
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert synced["counts"] == {"synced": 1}
    assert manifest["archive_status"] == "indexed"
    assert manifest["latest_event_count"] == 2
    assert "CodexSessionSweep" in manifest["hooks_seen"]


def test_codex_grounding_accepts_expected_config_and_markers(tmp_path: Path) -> None:
    workspace = tmp_path / "Workspace"
    aoa_root = workspace / ".aoa"
    (workspace / ".codex").mkdir(parents=True)
    (workspace / ".codex" / "config.toml").write_text(
        "\n".join(
            [
                "model_context_window = 400000",
                "model_auto_compact_token_limit = 320000",
                "",
                "[features]",
                "hooks = true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    native = tmp_path / "codex-native"
    native.write_bytes(
        b"SessionStart user-prompt-submit.command.input PreCompact pre-compact.command "
        b"PostCompact post-compact.command stopReason"
    )
    native.chmod(0o755)

    payload = module.codex_grounding(
        workspace_root=workspace,
        aoa_root=aoa_root,
        codex_native_bin=native,
        codex_version_output="codex-cli 0.130.0",
    )

    assert payload["ok"] is True
    assert payload["compact_ratio"] == 0.8
    assert all(payload["schema_markers"].values())


def test_resolve_codex_native_binary_supports_nested_npm_vendor_layout(tmp_path: Path, monkeypatch) -> None:
    package_root = tmp_path / "npm-global" / "lib" / "node_modules" / "@openai" / "codex"
    wrapper = package_root / "bin" / "codex.js"
    native = (
        package_root
        / "node_modules"
        / "@openai"
        / "codex-linux-x64"
        / "vendor"
        / "x86_64-unknown-linux-musl"
        / "bin"
        / "codex"
    )
    bin_dir = tmp_path / "bin"
    wrapper.parent.mkdir(parents=True)
    native.parent.mkdir(parents=True)
    bin_dir.mkdir()
    wrapper.write_text("#!/usr/bin/env node\n", encoding="utf-8")
    native.write_text("#!/bin/sh\n", encoding="utf-8")
    wrapper.chmod(0o755)
    native.chmod(0o755)
    (bin_dir / "codex").symlink_to(wrapper)
    monkeypatch.setenv("PATH", str(bin_dir))

    assert module.resolve_codex_native_binary("codex") == native


def test_codex_grounding_uses_user_compact_config_and_project_codex_hooks(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "Workspace"
    aoa_root = workspace / ".aoa"
    codex_home = tmp_path / "codex-home"
    (workspace / ".codex").mkdir(parents=True)
    codex_home.mkdir()
    (workspace / ".codex" / "config.toml").write_text(
        "\n".join(
            [
                "[features]",
                "codex_hooks = true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (codex_home / "config.toml").write_text(
        "\n".join(
            [
                "model_context_window = 400000",
                "model_auto_compact_token_limit = 320000",
                "",
                "[features]",
                "hooks = true",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    native = tmp_path / "codex-native"
    native.write_bytes(
        b"SessionStart user-prompt-submit.command.input PreCompact pre-compact.command "
        b"PostCompact post-compact.command stopReason"
    )
    native.chmod(0o755)

    payload = module.codex_grounding(
        workspace_root=workspace,
        aoa_root=aoa_root,
        codex_native_bin=native,
        codex_version_output="codex-cli 0.130.0",
    )

    assert payload["ok"] is True
    assert payload["hooks_enabled_sources"] == ["project", "user"]
    assert payload["model_context_window_source"] == "user"
    assert payload["model_auto_compact_token_limit_source"] == "user"


def test_completion_audit_reports_covered_segments_and_remaining_live_hooks(tmp_path: Path) -> None:
    workspace = tmp_path / "Workspace"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-14T02-00-00-session-audit.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-14T02:00:00Z", "type": "session_meta", "payload": {"id": "session-audit"}},
            {"timestamp": "2026-05-14T02:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Audit compact markers"}]}},
            {"timestamp": "2026-05-14T02:00:02Z", "type": "compacted", "payload": {"replacement_history": []}},
            {"timestamp": "2026-05-14T02:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "session-audit",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    payload = module.completion_audit(workspace_root=workspace, aoa_root=aoa_root, check_codex=False)

    assert payload["ok"] is False
    statuses = {item["requirement"]: item["status"] for item in payload["checklist"]}
    assert statuses["Real Codex compaction boundaries are detected from raw transcripts"] == "covered"
    assert statuses["Segment topology matches raw compaction boundaries"] == "covered"
    assert statuses["User-level router skill is installed for the current Codex user"] == "remaining"
    assert statuses["Live PreCompact and PostCompact hook receipts observed in archived sessions"] == "remaining"


def test_completion_audit_defers_recent_live_segment_mismatch(tmp_path: Path) -> None:
    workspace = tmp_path / "Workspace"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / ".codex" / "sessions" / "2026" / "06" / "15" / "rollout-2026-06-15T00-00-00-live-segment-mismatch.jsonl"
    transcript.parent.mkdir(parents=True)
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-06-15T00:00:00Z", "type": "session_meta", "payload": {"id": "live-segment-mismatch"}},
            {"timestamp": "2026-06-15T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Audit live mismatch"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "live-segment-mismatch",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    record = module.resolve_session_record(aoa_root, "live-segment-mismatch")
    session_dir = module.session_dir_from_record(record)
    raw_path = session_dir / "raw" / "session.raw.jsonl"
    with raw_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"timestamp": "2026-06-15T00:00:02Z", "type": "compacted", "payload": {}}, ensure_ascii=False) + "\n")
        handle.write(
            json.dumps(
                {
                    "timestamp": "2026-06-15T00:00:03Z",
                    "type": "response_item",
                    "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "after live compact"}]},
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    os.utime(transcript, None)
    os.utime(raw_path, None)

    payload = module.completion_audit(workspace_root=workspace, aoa_root=aoa_root, check_codex=False)
    topology = [
        item for item in payload["checklist"] if item["requirement"] == "Segment topology matches raw compaction boundaries"
    ][0]

    assert topology["status"] == "covered"
    assert topology["evidence"]["mismatch_count"] == 0
    assert topology["evidence"]["live_deferred_mismatch_count"] == 1
    assert topology["evidence"]["live_deferred_mismatches"][0]["session_id"] == "live-segment-mismatch"


def test_completion_audit_handles_raw_unavailable_archives(tmp_path: Path) -> None:
    workspace = tmp_path / "Workspace"
    aoa_root = workspace / ".aoa"
    missing = tmp_path / "missing-transcript.jsonl"
    module.handle_hook_event(
        "SessionStart",
        {
            "session_id": "missing-audit-session",
            "transcript_path": str(missing),
            "cwd": str(workspace),
            "hook_event_name": "SessionStart",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    payload = module.completion_audit(workspace_root=workspace, aoa_root=aoa_root, check_codex=False)

    unavailable = [
        item for item in payload["archive_compaction_audit"] if item["session_id"] == "missing-audit-session"
    ][0]
    assert unavailable["archive_status"] == "raw_unavailable"
    assert unavailable["raw_exists"] is False
    assert unavailable["expected_segment_count"] == 0


def test_first_pass_distillation_writes_reviewable_route_map(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    (aoa_root / "config").mkdir(parents=True, exist_ok=True)
    (aoa_root / "config" / "event-distillation-routes.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "routes": {
                    "DECISION": ["adr", "principle"],
                    "ERROR": ["root_cause"],
                    "COMMAND": ["command_recipe"],
                    "COMMAND_OUTPUT": ["verification_signal"],
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    transcript = tmp_path / "rollout-2026-05-15T00-00-00-session-distill.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-15T00:00:00Z", "type": "session_meta", "payload": {"id": "session-distill"}},
            {"timestamp": "2026-05-15T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Distill route map"}]}},
            {"timestamp": "2026-05-15T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: route events through review"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "session-distill",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    payload = module.distill_session_first_pass(aoa_root, "latest")

    assert payload["ok"] is True
    session_dir = aoa_root / "sessions" / "2026-05-15__001__distill-route-map"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    distillation_index = json.loads((session_dir / "distillation" / "distillation.index.json").read_text(encoding="utf-8"))
    distillation_md = (session_dir / "distillation" / "001__first-pass__experience-map.md").read_text(encoding="utf-8")
    assert manifest["distillation_status"] == "first_pass_distilled"
    assert manifest["distillation_iteration"] == 1
    assert manifest["distillation"]["candidate_count"] >= 1
    assert distillation_index["status"] == "provisional"
    assert "DECISION" in distillation_index["candidates_by_type"]
    assert "raw=`raw:line:" in distillation_md


def test_batch_distill_builds_first_wave_queue_and_applies(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    (workspace / "AGENTS.md").parent.mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_text("project law\n", encoding="utf-8")
    (workspace / "DESIGN.md").write_text("project design\n", encoding="utf-8")
    (aoa_root / "config").mkdir(parents=True, exist_ok=True)
    (aoa_root / "config" / "event-distillation-routes.json").write_text(
        json.dumps({"schema_version": 1, "routes": {"PROCESS_LESSON": ["skill_amendment"]}}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    transcript = tmp_path / "rollout-2026-05-16T00-00-00-batch-distill.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-16T00:00:00Z", "type": "session_meta", "payload": {"id": "batch-distill"}},
            {"timestamp": "2026-05-16T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Build the conveyor"}]}},
            {"timestamp": "2026-05-16T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Process lesson: first wave writes only provisional evidence maps"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "batch-distill",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    planned = module.batch_distill_sessions(aoa_root=aoa_root, since="2026-05-16", write_report=True)

    assert planned["ok"] is True
    assert planned["counts"] == {"planned": 1}
    assert Path(planned["report_json"]).exists()
    assert "manual_review" in planned["results"][0]["lanes"]
    assert "mechanics_candidate" in planned["results"][0]["lanes"]
    assert planned["results"][0]["auto_actions"] == ["write_provisional_first_pass_distillation"]
    assert planned["results"][0]["project_grounding"]["status"] == "grounded"
    assert {item["name"] for item in planned["results"][0]["project_grounding"]["files"]} == {"AGENTS.md", "DESIGN.md"}

    applied = module.batch_distill_sessions(aoa_root=aoa_root, since="2026-05-16", apply=True)

    session_dir = aoa_root / "sessions" / "2026-05-16__001__build-the-conveyor"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert applied["counts"] == {"distilled": 1}
    assert manifest["distillation_status"] == "first_pass_distilled"
    assert (session_dir / "distillation" / "distillation.index.json").exists()


def test_manual_review_wave_writes_packets_and_promotion_layer(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    (workspace / "AGENTS.md").parent.mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_text("project law\n", encoding="utf-8")
    (aoa_root / "config").mkdir(parents=True, exist_ok=True)
    (aoa_root / "config" / "event-distillation-routes.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "routes": {
                    "DECISION": ["adr"],
                    "PROCESS_LESSON": ["skill_amendment"],
                    "ERROR": ["root_cause"],
                },
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    transcript = tmp_path / "rollout-2026-05-16T00-00-00-manual-review.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-16T00:00:00Z", "type": "session_meta", "payload": {"id": "manual-review", "cwd": str(workspace)}},
            {"timestamp": "2026-05-16T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Review this session"}]}},
            {"timestamp": "2026-05-16T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: keep raw evidence before summaries"}]}},
            {"timestamp": "2026-05-16T00:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Process lesson: review packets must stay provisional"}]}},
            {"timestamp": "2026-05-16T00:00:04Z", "type": "response_item", "payload": {"type": "function_call_output", "call_id": "call-fail", "output": "Process exited with code 1\nOutput:\nerror: broken fixture\n"}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "manual-review",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    planned = module.manual_review_wave(aoa_root=aoa_root, workspace_root=workspace, since="2026-05-16", priority="sample")
    applied = module.manual_review_wave(aoa_root=aoa_root, workspace_root=workspace, since="2026-05-16", priority="sample", apply=True, write_report=True)
    layer = module.build_promotion_review_layer(aoa_root=aoa_root, since="2026-05-16", write_report=True)

    session_dir = aoa_root / "sessions" / "2026-05-16__001__review-this-session"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    packet_path = Path(applied["results"][0]["manual_review_packet"])
    promotion_path = Path(applied["results"][0]["promotion_index"])
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    promotion = json.loads(promotion_path.read_text(encoding="utf-8"))
    assert planned["counts"] == {"planned": 1}
    assert planned["wave_id"] == "manual-review-wave1"
    assert applied["counts"] == {"packet_written": 1}
    assert applied["wave_id"] == "manual-review-wave1"
    assert applied["results"][0]["wave_sequence"] == 1
    assert applied["results"][0]["manual_review_priority"] == "sample"
    assert applied["results"][0]["owner_resolution"]["status"] == "resolved"
    assert Path(applied["report_json"]).exists()
    assert manifest["review_status"] == "manual_review_open"
    assert manifest["manual_review"]["wave_count"] == 1
    assert manifest["promotion"]["wave_count"] == 1
    assert manifest["review_index"]["status"] == "open_for_future_passes"
    assert packet_path.name == "001__manual-review-wave1__manual-review-packet.json"
    assert packet_path.parent.name == "waves"
    assert packet["review_truth_status"] == "not_reviewed_truth"
    assert packet["open_status"] == "open_for_future_passes"
    assert packet["wave_sequence"] == 1
    assert packet["promotion_candidate_count"] >= 2
    assert promotion["promoted_claim_count"] == 0
    assert promotion["status"] == "promotion_candidates_unreviewed"
    assert promotion["open_status"] == "open_for_future_passes"
    assert layer["selected_count"] == 1
    assert layer["candidate_count"] == promotion["candidate_count"]
    assert layer["raw_candidate_count"] == promotion["candidate_count"]
    assert layer["promoted_claim_count"] == 0

    second = module.manual_review_wave(aoa_root=aoa_root, workspace_root=workspace, since="2026-05-16", priority="sample", apply=True)
    second_packet_path = Path(second["results"][0]["manual_review_packet"])
    second_promotion_path = Path(second["results"][0]["promotion_index"])
    second_manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    second_layer = module.build_promotion_review_layer(aoa_root=aoa_root, since="2026-05-16")

    assert second["wave_id"] == "manual-review-wave2"
    assert second["results"][0]["wave_sequence"] == 2
    assert second_packet_path.name == "002__manual-review-wave2__manual-review-packet.json"
    assert packet_path.exists()
    assert second_packet_path.exists()
    assert promotion_path.exists()
    assert second_promotion_path.exists()
    assert second_manifest["manual_review"]["wave_count"] == 2
    assert second_manifest["promotion"]["wave_count"] == 2
    assert (session_dir / "distillation" / "review.index.json").exists()
    assert second_layer["selected_count"] == 1
    assert second_layer["candidate_count"] == promotion["candidate_count"]
    assert second_layer["raw_candidate_count"] == promotion["candidate_count"] * 2
    assert second_layer["promoted_claim_count"] == 0


def test_batch_distill_uses_workspace_grounding_fallback(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    (workspace / "AGENTS.md").parent.mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_text("workspace law\n", encoding="utf-8")
    transcript = tmp_path / "rollout-2026-05-16T00-00-00-grounding-fallback.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-16T00:00:00Z", "type": "session_meta", "payload": {"id": "grounding-fallback"}},
            {"timestamp": "2026-05-16T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Ground this session"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "grounding-fallback",
            "transcript_path": str(transcript),
            "cwd": str(tmp_path / "missing-cwd"),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    planned = module.batch_distill_sessions(aoa_root=aoa_root, workspace_root=workspace, since="2026-05-16")

    grounding = planned["results"][0]["project_grounding"]
    assert grounding["status"] == "workspace_fallback_grounded"
    assert grounding["fallback_used"] is True
    assert grounding["files"][0]["path"] == str(workspace / "AGENTS.md")


def test_owner_path_inference_is_fail_open_when_home_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("HOME", raising=False)

    owner = module.inferred_owner_root_for_path("~/missing")
    assert owner in {None, "/home/dionysus"}


def test_owner_resolution_uses_indexed_paths_when_grounding_falls_back(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    (workspace / "AGENTS.md").parent.mkdir(parents=True, exist_ok=True)
    (workspace / "AGENTS.md").write_text("workspace law\n", encoding="utf-8")
    transcript = tmp_path / "rollout-2026-05-16T00-00-00-owner-resolution.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-16T00:00:00Z", "type": "session_meta", "payload": {"id": "owner-resolution"}},
            {"timestamp": "2026-05-16T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Find the real owner"}]}},
            {
                "timestamp": "2026-05-16T00:00:02Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-owner", "arguments": json.dumps({"cmd": "rg -n TODO /srv/aoa-sdk/README.md"})},
            },
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "owner-resolution",
            "transcript_path": str(transcript),
            "cwd": str(tmp_path / "missing-cwd"),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    planned = module.batch_distill_sessions(aoa_root=aoa_root, workspace_root=workspace, since="2026-05-16")
    owner = planned["results"][0]["owner_resolution"]

    assert planned["results"][0]["project_grounding"]["status"] == "workspace_fallback_grounded"
    assert owner["status"] == "resolved_from_evidence"
    assert owner["owner_root"] == "/srv/aoa-sdk"
    assert owner["confidence"] == "medium"


def test_repair_session_titles_skips_ide_context_prompt(tmp_path: Path) -> None:
    aoa_root = tmp_path / ".aoa"
    session_dir = aoa_root / "sessions" / "2026-05-17__001__files-mentioned-by-the-user"
    raw_path = session_dir / "raw" / "session.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {"timestamp": "2026-05-17T10:00:00Z", "type": "session_meta", "payload": {"id": "weak-title-session"}},
            {
                "timestamp": "2026-05-17T10:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Files mentioned by the user:\n- /srv/AbyssOS/.aoa/DESIGN.md"}]},
            },
            {
                "timestamp": "2026-05-17T10:00:02Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Repair the session naming topology"}]},
            },
        ],
    )
    manifest = {
        "schema_version": 1,
        "session_id": "weak-title-session",
        "created_at": "2026-05-17T10:00:00Z",
        "updated_at": "2026-05-17T10:00:03Z",
        "source": {"transcript_path": "/tmp/rollout-2026-05-17T10-00-00-weak-title-session.jsonl"},
        "archive_status": "indexed",
        "distillation_status": "raw_archived",
        "raw": {"path": str(raw_path)},
        "segments": [],
        "latest_event_count": 3,
        "display": {
            "date": "2026-05-17",
            "sequence": 1,
            "title": "Files mentioned by the user",
            "title_source": "first_user_message",
            "label": "2026-05-17__001__files-mentioned-by-the-user",
            "path": str(session_dir),
            "archive_path": str(session_dir),
            "navigation_path": str(session_dir),
        },
        "session_label": "2026-05-17__001__files-mentioned-by-the-user",
        "session_title": "Files mentioned by the user",
    }
    (session_dir / "session.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8")
    module.update_registry(aoa_root, manifest, session_dir)

    planned = module.repair_session_titles(aoa_root=aoa_root, since="2026-05-17")
    applied = module.repair_session_titles(aoa_root=aoa_root, since="2026-05-17", apply=True)

    repaired_dir = aoa_root / "sessions" / "2026-05-17__001__repair-the-session-naming-topology"
    repaired_manifest = json.loads((repaired_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert planned["counts"] == {"planned": 1}
    assert "weak_title" in planned["results"][0]["reasons"]
    assert applied["counts"] == {"repaired": 1}
    assert repaired_manifest["display"]["title"] == "Repair the session naming topology"
    assert repaired_manifest["raw"]["path"] == str(repaired_dir / "raw" / "session.raw.jsonl")
    assert not session_dir.exists()


def test_semantic_session_name_anchors_raw_without_renaming_archive(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-18T00-00-00-semantic-name.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-18T00:00:00Z", "type": "session_meta", "payload": {"id": "semantic-name-session", "cwd": str(workspace)}},
            {"timestamp": "2026-05-18T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Continue the work"}]}},
            {"timestamp": "2026-05-18T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Finish the aoa-techniques final residual promotion pass"}]}},
            {"timestamp": "2026-05-18T00:00:03Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: use raw refs before promotion."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "semantic-name-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = aoa_root / "sessions" / "2026-05-18__001__continue-the-work"
    manifest_before = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    raw_sha = manifest_before["raw"]["sha256"]
    payload = module.set_session_semantic_name(
        aoa_root=aoa_root,
        target="continue-the-work",
        name="aoa-techniques continuation",
        scope="session",
        kind="session_essence",
        evidence_refs=["raw:line:2", "raw:line:3"],
        from_line=2,
        to_line=4,
        coverage_note="Umbrella continuation intent and later specific phase.",
        source="operator",
        note="Mutable session-level name, anchored to raw evidence.",
        apply=True,
        verify_raw_hash=True,
    )
    phase_payload = module.set_session_semantic_name(
        aoa_root=aoa_root,
        target="continue-the-work",
        name="aoa-techniques final residual promotion pass",
        scope="phase",
        kind="dominant_topic",
        evidence_refs=["raw:line:3"],
        from_line=3,
        to_line=4,
        coverage_note="Later phase, not the umbrella session name.",
        source="operator",
        note="Dominant later topic, anchored to raw evidence.",
        apply=True,
        verify_raw_hash=True,
    )

    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    semantic_by_slug = {item["slug"]: item for item in manifest["semantic_names"]["names"]}
    semantic = semantic_by_slug["aoa-techniques-continuation"]
    phase = semantic_by_slug["aoa-techniques-final-residual-promotion-pass"]
    registry_record = module.resolve_session_record(aoa_root, "aoa-techniques-continuation")
    phase_record = module.resolve_session_record(aoa_root, "aoa-techniques-final-residual-promotion-pass")
    packet = module.rehydrate_packet(aoa_root, "aoa-techniques-final-residual-promotion-pass")
    session_md = (session_dir / "SESSION.md").read_text(encoding="utf-8")
    name_index = json.loads((aoa_root / module.SESSION_NAME_INDEX_JSON).read_text(encoding="utf-8"))
    name_index_md = (aoa_root / module.SESSION_NAME_INDEX_MARKDOWN).read_text(encoding="utf-8")
    sessions_index = json.loads((aoa_root / "sessions" / module.SESSIONS_INDEX_JSON).read_text(encoding="utf-8"))
    sessions_index_md = (aoa_root / "sessions" / module.SESSIONS_INDEX_MARKDOWN).read_text(encoding="utf-8")

    assert payload["ok"] is True
    assert phase_payload["ok"] is True
    assert payload["status"] == "applied"
    assert session_dir.exists()
    assert manifest["display"]["label"] == "2026-05-18__001__continue-the-work"
    assert manifest["raw"]["sha256"] == raw_sha
    assert manifest["semantic_names"]["active_session"] == "aoa-techniques-continuation"
    assert manifest["semantic_names"]["active"] == "aoa-techniques-final-residual-promotion-pass"
    assert semantic["scope"] == "session"
    assert phase["scope"] == "phase"
    assert semantic["anchor"]["session_id"] == "semantic-name-session"
    assert semantic["anchor"]["canonical_label"] == "2026-05-18__001__continue-the-work"
    assert semantic["anchor"]["raw_sha256"] == raw_sha
    assert semantic["evidence"] == ["raw:line:2", "raw:line:3"]
    assert phase["evidence"] == ["raw:line:3"]
    assert phase["coverage"]["raw_ranges"] == [{"from_line": 3, "to_line": 4}]
    assert registry_record["session_id"] == "semantic-name-session"
    assert phase_record["session_id"] == "semantic-name-session"
    assert "Session Name Anchor" in packet
    assert "Phase And Topic Names" in packet
    assert "raw:line:3" in packet
    assert "semantic_active_session" in session_md
    assert name_index["named_session_count"] == 1
    assert "aoa-techniques-final-residual-promotion-pass" in name_index["slug_index"]
    assert "aoa-techniques-continuation" in name_index_md
    assert sessions_index["artifact_type"] == "sessions_directory_index"
    assert sessions_index["session_count"] == 1
    assert sessions_index["named_session_count"] == 1
    assert sessions_index["sessions"][0]["entry"] == "2026-05-18__001__continue-the-work/SESSION.md"
    assert "aoa-techniques-continuation" in sessions_index_md
    assert "aoa-techniques-final-residual-promotion-pass" in sessions_index_md
    assert "2026-05-18__001__continue-the-work/SESSION.md" in sessions_index_md


def test_naming_wave_build_apply_and_audit_semantic_names(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-19T00-00-00-naming-wave.jsonl"
    rows: list[dict[str, object]] = [
        {"timestamp": "2026-05-19T00:00:00Z", "type": "session_meta", "payload": {"id": "naming-wave-session", "cwd": str(workspace / ".aoa")}},
        {"timestamp": "2026-05-19T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Build the mass naming wave route"}]}},
        {"timestamp": "2026-05-19T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Decision: keep semantic naming separate from physical relabel."}]}},
    ]
    for index in range(3, 24):
        rows.append(
            {
                "timestamp": f"2026-05-19T00:00:{index:02d}Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": f"Progress marker {index}"}]},
            }
        )
    write_jsonl(transcript, rows)
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "naming-wave-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace / ".aoa"),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    wave = module.build_naming_wave(aoa_root, target="all", write=True, wave_id="naming-wave-test")
    item = next(item for item in wave["items"] if item["session_id"] == "naming-wave-session")
    assert wave["policy"]["semantic_names_only"] is True
    assert item["action"] == "semantic_session_name_review"
    assert item["physical_relabel_allowed"] is False
    assert item["archive_label_change"] is False
    assert item["candidate"]["evidence"] == ["raw:line:2"]
    assert item["reviewed_name"] == ""
    assert Path(wave["plan_path"]).exists()

    plan = json.loads(Path(wave["plan_path"]).read_text(encoding="utf-8"))
    for plan_item in plan["items"]:
        if plan_item["session_id"] == "naming-wave-session":
            plan_item["reviewed_name"] = "session-memory-naming-wave-route"
    plan_path = Path(wave["plan_path"])
    plan_path.write_text(json.dumps(plan, ensure_ascii=False) + "\n", encoding="utf-8")

    preview = module.apply_naming_wave(aoa_root, plan_path=plan_path)
    applied = module.apply_naming_wave(aoa_root, plan_path=plan_path, apply=True, write_report=True)
    session_dir = aoa_root / "sessions" / "2026-05-19__001__build-the-mass-naming-wave-route"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    audit = module.naming_quality_audit(aoa_root, target="session-memory-naming-wave-route", plan_path=plan_path, sample_size=1, sample_seed="test")

    assert preview["status"] == "preview_ready"
    assert preview["refreshed_indexes"] == []
    assert applied["status"] == "applied"
    assert applied["counts"]["applied"] == 1
    assert session_dir.exists()
    assert manifest["semantic_names"]["active_session"] == "session-memory-naming-wave-route"
    assert manifest["display"]["label"] == "2026-05-19__001__build-the-mass-naming-wave-route"
    assert audit["results"][0]["level"] == "ok"
    assert not audit["results"][0]["flags"]
    assert audit["quality_sample_size"] == 1
    assert audit["quality_sample"][0]["evidence_preview"][0]["text"] == "Build the mass naming wave route"
    assert Path(applied["report_json"]).exists()
    assert (aoa_root / module.SESSION_NAME_INDEX_JSON).exists()
    assert (aoa_root / "sessions" / module.SESSIONS_INDEX_JSON).exists()


def test_naming_wave_evidence_skips_agents_instruction_envelope(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-19T00-30-00-envelope-skip.jsonl"
    rows: list[dict[str, object]] = [
        {"timestamp": "2026-05-19T00:30:00Z", "type": "session_meta", "payload": {"id": "envelope-skip-session", "cwd": str(workspace)}},
        {"timestamp": "2026-05-19T00:30:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "# AGENTS.md instructions for /workspace\n<INSTRUCTIONS>project law</INSTRUCTIONS>"}]}},
        {"timestamp": "2026-05-19T00:30:02Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Name the real session from the real request"}]}},
    ]
    for index in range(3, 24):
        rows.append(
            {
                "timestamp": f"2026-05-19T00:30:{index:02d}Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": f"Progress marker {index}"}]},
            }
        )
    write_jsonl(transcript, rows)
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "envelope-skip-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    wave = module.build_naming_wave(aoa_root, target="envelope-skip-session", write=True, wave_id="naming-wave-envelope")
    item = wave["items"][0]

    assert item["candidate"]["evidence"] == ["raw:line:3"]
    assert item["proposed_name"].endswith("name-the-real-session-from-the-real-request")
    assert "agents-md" not in item["proposed_name"]


def test_naming_wave_uses_raw_request_after_setup_prefix_title(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-19T00-40-00-setup-prefix.jsonl"
    prompt = (
        "Работай в /srv/work/rios-de-color. Отвечай только на русском. "
        "Сначала прочитай: 1. AGENTS.md 2. AUDIT_STATE.md 3. ROADMAP_MAY.md. "
        "Проверь SocratiCode по runbook."
    )
    rows: list[dict[str, object]] = [
        {"timestamp": "2026-05-19T00:40:00Z", "type": "session_meta", "payload": {"id": "setup-prefix-session", "cwd": str(workspace)}},
        {"timestamp": "2026-05-19T00:40:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}]}},
    ]
    for index in range(2, 24):
        rows.append(
            {
                "timestamp": f"2026-05-19T00:40:{index:02d}Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": f"Progress marker {index}"}]},
            }
        )
    write_jsonl(transcript, rows)
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "setup-prefix-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    wave = module.build_naming_wave(aoa_root, target="setup-prefix-session", write=True, wave_id="naming-wave-setup-prefix")
    item = wave["items"][0]
    name_terms = set(module.semantic_name_slug(item["proposed_name"]).split("-"))

    assert item["candidate"]["evidence"] == ["raw:line:2"]
    assert "socraticode" in name_terms
    assert not ({"работай", "отвечай", "сначала"} & name_terms)


def test_naming_wave_uses_full_raw_when_short_title_is_context_noise(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-19T00-45-00-pr-review-title.jsonl"
    prompt = (
        "Read-only audit. Context: user provided PR review comments for aoa-evals, aoa-stats, aoa-memo. "
        "Work in /srv. Do not edit. Inspect current state against: aoa-evals PR138 verdict_shape categorical."
    )
    rows: list[dict[str, object]] = [
        {"timestamp": "2026-05-19T00:45:00Z", "type": "session_meta", "payload": {"id": "pr-review-title-session", "cwd": str(workspace)}},
        {"timestamp": "2026-05-19T00:45:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": prompt}]}},
    ]
    for index in range(2, 24):
        rows.append(
            {
                "timestamp": f"2026-05-19T00:45:{index:02d}Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": f"Progress marker {index}"}]},
            }
        )
    write_jsonl(transcript, rows)
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "pr-review-title-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    wave = module.build_naming_wave(aoa_root, target="pr-review-title-session", write=True, wave_id="naming-wave-pr-review-title")
    item = wave["items"][0]
    name_slug = module.semantic_name_slug(item["proposed_name"])

    assert item["candidate"]["evidence"] == ["raw:line:2"]
    assert "context" not in name_slug
    assert "aoa-evals" in name_slug
    assert "pr-review-comments-audit" in name_slug


def test_naming_wave_preflight_sync_updates_stale_source_before_naming(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-19T01-00-00-sync-wave.jsonl"
    rows = [
        {"timestamp": "2026-05-19T01:00:00Z", "type": "session_meta", "payload": {"id": "sync-wave-session", "cwd": str(workspace)}},
        {"timestamp": "2026-05-19T01:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Start the sync wave"}]}},
    ]
    write_jsonl(transcript, rows)
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "sync-wave-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    rows.append(
        {"timestamp": "2026-05-19T01:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "New source transcript evidence."}]}}
    )
    write_jsonl(transcript, rows)

    wave = module.build_naming_wave(aoa_root, target="sync-wave-session", write=True, wave_id="naming-wave-sync")
    item = wave["items"][0]
    applied = module.apply_naming_wave(aoa_root, plan_path=Path(wave["plan_path"]), apply=True, apply_preflight=True)
    manifest_path = next((aoa_root / "sessions").glob("*/session.manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert item["action"] == "sync_source_transcript"
    assert item["readiness"]["status"] == "needs_sync"
    assert applied["counts"]["synced"] == 1
    assert manifest["archive_status"] == "indexed"
    assert manifest["latest_event_count"] == 3
    assert manifest["raw"]["line_count"] == 3


def test_naming_wave_preflight_reindexes_deferred_archives(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-19T02-00-00-reindex-wave.jsonl"
    rows = [
        {"timestamp": "2026-05-19T02:00:00Z", "type": "session_meta", "payload": {"id": "reindex-wave-session", "cwd": str(workspace)}},
        {"timestamp": "2026-05-19T02:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Reindex the deferred naming wave archive"}]}},
        {"timestamp": "2026-05-19T02:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Keep raw first, then refresh indexes."}]}},
    ]
    write_jsonl(transcript, rows)
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "reindex-wave-session",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )
    session_dir = next((aoa_root / "sessions").glob("*reindex-the-deferred-naming-wave-archive"))
    manifest_path = session_dir / "session.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["archive_status"] = "raw_mirrored_index_deferred"
    manifest["raw"]["sha256"] = None
    manifest["raw"]["line_count"] = None
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8")

    wave = module.build_naming_wave(aoa_root, target="reindex-wave-session", write=True, wave_id="naming-wave-reindex")
    item = wave["items"][0]
    applied = module.apply_naming_wave(aoa_root, plan_path=Path(wave["plan_path"]), apply=True, apply_preflight=True)
    refreshed = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert item["action"] == "reindex_session"
    assert item["readiness"]["status"] == "needs_reindex"
    assert applied["counts"]["reindexed"] == 1
    assert refreshed["archive_status"] == "indexed"
    assert refreshed["raw"]["line_count"] == 3
    assert refreshed["raw"]["sha256"]


def test_naming_golden_set_quality_examples_are_enforced() -> None:
    golden_path = module.NAMING_GOLDEN_SET_PATH
    payload = json.loads((SCRIPT.parents[1] / golden_path).read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in payload["cases"]}
    specific = module.session_name_candidate_quality(
        "repository-route-surfaces-refactor-and-release-validation",
        evidence=["raw:line:2"],
    )
    generic = module.session_name_candidate_quality("Continue the work", evidence=["raw:line:2"])
    language_instruction = cases["language_instruction_prefix_not_name"]
    stripped_seed = module.useful_name_seed(language_instruction["title"])
    language_instruction_quality = module.session_name_candidate_quality(
        language_instruction["title"],
        evidence=["raw:line:2"],
    )
    readlist_instruction = cases["workdir_language_readlist_prefix_not_name"]
    readlist_seed = module.useful_name_seed(readlist_instruction["title"])
    readlist_slug = module.semantic_name_slug(readlist_seed)
    role_prompt = cases["role_prompt_prefix_not_name"]
    role_prompt_seed = module.useful_name_seed(role_prompt["title"])
    role_prompt_quality = module.session_name_candidate_quality(
        role_prompt["warn_name"],
        evidence=["raw:line:2"],
    )
    russian_role_prompt = cases["russian_role_prompt_prefix_not_name"]
    russian_role_prompt_seed = module.useful_name_seed(russian_role_prompt["title"])
    russian_role_prompt_quality = module.session_name_candidate_quality(
        russian_role_prompt["warn_name"],
        evidence=["raw:line:2"],
    )
    role_context = cases["role_context_prefix_not_name"]
    role_context_seed = module.useful_name_seed(role_context["title"])
    task_in_workspace = cases["task_in_shared_workspace_prefix_not_name"]
    task_in_workspace_seed = module.useful_name_seed(task_in_workspace["title"])
    russian_do_not_edit = cases["russian_do_not_edit_prefix_not_name"]
    russian_do_not_edit_seed = module.useful_name_seed(russian_do_not_edit["title"])
    truncated_do_not_edit = cases["truncated_russian_do_not_edit_title_is_generic"]
    truncated_do_not_edit_seed = module.useful_name_seed(truncated_do_not_edit["title"])
    truncated_do_not_edit_quality = module.session_name_candidate_quality(
        truncated_do_not_edit["warn_name"],
        evidence=["raw:line:2"],
    )
    domain_scaffold_short = cases["domain_scaffold_short_name_requires_review"]
    domain_scaffold_short_quality = module.session_name_candidate_quality(
        domain_scaffold_short["warn_name"],
        evidence=["raw:line:2"],
    )
    read_only_wave = cases["read_only_inside_wave_title_not_name"]
    read_only_wave_seed = module.useful_name_seed(read_only_wave["title"])
    pr_review_context = cases["pr_review_context_seed"]
    pr_review_context_seed = module.useful_name_seed(pr_review_context["title"])
    pr_review_large_list = cases["pr_review_large_list_context_seed"]
    pr_review_large_list_seed = module.useful_name_seed(pr_review_large_list["title"])
    experience_wave_artifact = cases["experience_wave_branch_and_artifact_seed"]
    experience_wave_artifact_seed = module.useful_name_seed(experience_wave_artifact["title"])
    experience_wave_archive = cases["experience_wave_seed_archive_seed"]
    experience_wave_archive_seed = module.useful_name_seed(experience_wave_archive["title"])
    experience_wave_planning = cases["experience_wave_planning_full_raw_seed"]
    experience_wave_planning_seed = module.useful_name_seed(experience_wave_planning["title"])
    experience_wave_ownership = cases["experience_wave_role_ownership_seed"]
    experience_wave_ownership_seed = module.useful_name_seed(experience_wave_ownership["title"])
    final_verdict_artifact = cases["final_verdict_uses_artifact_topic_seed"]
    final_verdict_artifact_seed = module.useful_name_seed(final_verdict_artifact["title"])
    repo_final_judgment = cases["repo_final_judgment_uses_review_artifact_seed"]
    repo_final_judgment_seed = module.useful_name_seed(repo_final_judgment["title"])
    russian_scout = cases["russian_experience_scout_uses_lane_and_repos"]
    russian_scout_seed = module.useful_name_seed(russian_scout["title"])
    wave_sidecar = cases["wave_sidecar_uses_named_topics"]
    wave_sidecar_seed = module.useful_name_seed(wave_sidecar["title"])
    wave2_archive_topic = cases["wave2_archive_topic_seed"]
    wave2_archive_topic_seed = module.useful_name_seed(wave2_archive_topic["title"])
    wave5_cartography = cases["wave5_seed_cartography_uses_seed_dir"]
    wave5_cartography_seed = module.useful_name_seed(wave5_cartography["title"])
    pr_gate = cases["pr_gate_watcher_seed"]
    pr_gate_seed = module.useful_name_seed(pr_gate["title"])
    remaining_pr_gate = cases["remaining_pr_gate_watcher_seed"]
    remaining_pr_gate_seed = module.useful_name_seed(remaining_pr_gate["title"])
    socraticode_runbook = cases["socraticode_runbook_seed"]
    socraticode_runbook_seed = module.useful_name_seed(socraticode_runbook["title"])
    russian_seed_planting = cases["russian_seed_planting_meaning_seed"]
    russian_seed_planting_seed = module.useful_name_seed(russian_seed_planting["title"])
    slash_phrase = cases["slash_phrase_is_not_path_domain"]
    slash_phrase_domain = module.detect_session_domain([slash_phrase["title"]])
    procedural_name = cases["procedural_name_requires_review"]
    procedural_name_quality = module.session_name_candidate_quality(
        procedural_name["warn_name"],
        evidence=["raw:line:2"],
    )
    truncated_tail = cases["truncated_tail_requires_review"]
    truncated_tail_quality = module.session_name_candidate_quality(
        truncated_tail["warn_name"],
        evidence=["raw:line:2"],
    )
    scope_only_branch = cases["scope_only_branch_requires_review"]
    scope_only_branch_quality = module.session_name_candidate_quality(
        scope_only_branch["warn_name"],
        evidence=["raw:line:2"],
    )
    working_context = cases["working_context_prefix_not_name"]
    working_context_seed = module.useful_name_seed(working_context["title"])
    working_context_domain = module.detect_session_domain([working_context["title"]])
    github_owner_context = cases["github_owner_prefix_not_name"]
    github_owner_context_seed = module.useful_name_seed(github_owner_context["title"])
    read_only_task_for_wave = cases["read_only_task_for_wave_prefix_not_name"]
    read_only_task_for_wave_seed = module.useful_name_seed(read_only_task_for_wave["title"])
    fallback_quality_case = cases["fallback_domain_action_requires_review"]["quality"]
    path_attachment = cases["path_attachment_domain_uses_stem"]
    path_attachment_domain = module.detect_session_domain([path_attachment["title"]])
    quoted_path_attachment = cases["quoted_path_attachment_uses_stem"]
    quoted_path_seed = module.useful_name_seed(quoted_path_attachment["title"])
    repo_topology_refactor = cases["russian_repo_topology_refactor_path_not_name"]
    repo_topology_refactor_seed = module.useful_name_seed(repo_topology_refactor["title"])
    systemic_seed_case_ids = [
        "next_wave_deployment_scout_seed",
        "next_wave_certification_scout_seed",
        "experience_wave_owner_landing_plan_seed",
        "owner_split_final_judgment_seed",
        "wave2_second_pass_judgment_seed",
        "wave2_authority_note_judgment_seed",
        "repo_fix_round_final_verdict_seed",
        "repo_diff_review_seed",
        "experience_wave2_seed_scope_authority_review_seed",
        "experience_wave2_certification_watchtower_seed",
        "experience_wave1_seed_authority_risk_seed",
        "titan_wave0_risk_review_seed",
        "titan_wave0_final_judgment_seed",
        "titan_wave0_structural_framing_seed",
        "titan_wave1_center_bridge_risk_seed",
        "wave1_center_bridge_surface_seed",
        "wave1_dionysus_provenance_bridge_seed",
        "experience_v12_v20_wave0_lineage_seed",
        "wave4_polis_constitution_seed",
        "dionysus_closeout_map_seed",
        "dionysus_closeout_lineage_audit_seed",
        "dionysus_closeout_final_judgment_seed",
        "compact_hook_probe_seed",
        "post_w10_gap_audit_seed",
        "post_w10_runtime_gap_audit_seed",
        "srv_mirror_drift_seed",
        "cross_repo_wave5_review_gate_seed",
        "wave5_review_uses_review_not_provenance_seed",
        "wave5_rereview_gets_distinct_seed",
        "multi_repo_fix_map_seed",
        "rfc3339_lineage_seed",
    ]

    assert payload["artifact_type"] == "naming_golden_set"
    assert specific["level"] == cases["specific_repo_refactor"]["expected_quality_level"]
    assert "generic_name" not in specific["flags"]
    assert generic["level"] == cases["generic_continue_requires_signals"]["expected_quality_level"]
    assert cases["generic_continue_requires_signals"]["expected_flag"] in generic["flags"]
    assert stripped_seed == language_instruction["expected_seed"]
    assert not module.semantic_name_slug(stripped_seed).startswith(language_instruction["forbidden_slug_prefix"])
    assert "instruction_text_in_name" in language_instruction_quality["flags"]
    assert readlist_seed == readlist_instruction["expected_seed"]
    assert not set(readlist_slug.split("-")) & set(readlist_instruction["forbidden_slug_terms"])
    assert role_prompt_seed == role_prompt["expected_seed"]
    assert role_prompt["expected_flag"] in role_prompt_quality["flags"]
    assert russian_role_prompt_seed == russian_role_prompt["expected_seed"]
    assert russian_role_prompt["expected_flag"] in russian_role_prompt_quality["flags"]
    assert role_context_seed == role_context["expected_seed"]
    assert task_in_workspace_seed == task_in_workspace["expected_seed"]
    assert russian_do_not_edit_seed == russian_do_not_edit["expected_seed"]
    assert module.title_is_generic_for_naming(truncated_do_not_edit_seed, "first_user_message") is truncated_do_not_edit["expected_generic"]
    assert truncated_do_not_edit["expected_flag"] in truncated_do_not_edit_quality["flags"]
    assert domain_scaffold_short_quality["level"] == domain_scaffold_short["expected_quality_level"]
    assert domain_scaffold_short["expected_flag"] in domain_scaffold_short_quality["flags"]
    assert read_only_wave_seed == read_only_wave["expected_seed"]
    assert pr_review_context_seed == pr_review_context["expected_seed"]
    assert pr_review_large_list_seed == pr_review_large_list["expected_seed"]
    assert experience_wave_artifact_seed == experience_wave_artifact["expected_seed"]
    assert experience_wave_archive_seed == experience_wave_archive["expected_seed"]
    assert experience_wave_planning_seed == experience_wave_planning["expected_seed"]
    assert experience_wave_ownership_seed == experience_wave_ownership["expected_seed"]
    assert final_verdict_artifact_seed == final_verdict_artifact["expected_seed"]
    assert repo_final_judgment_seed == repo_final_judgment["expected_seed"]
    assert russian_scout_seed == russian_scout["expected_seed"]
    assert wave_sidecar_seed == wave_sidecar["expected_seed"]
    assert wave2_archive_topic_seed == wave2_archive_topic["expected_seed"]
    assert wave5_cartography_seed == wave5_cartography["expected_seed"]
    assert pr_gate_seed == pr_gate["expected_seed"]
    assert remaining_pr_gate_seed == remaining_pr_gate["expected_seed"]
    assert socraticode_runbook_seed == socraticode_runbook["expected_seed"]
    assert russian_seed_planting_seed == russian_seed_planting["expected_seed"]
    assert slash_phrase_domain == slash_phrase["expected_domain"]
    assert procedural_name["expected_flag"] in procedural_name_quality["flags"]
    assert truncated_tail["expected_flag"] in truncated_tail_quality["flags"]
    assert scope_only_branch["expected_flag"] in scope_only_branch_quality["flags"]
    assert working_context_seed == working_context["expected_seed"]
    assert working_context_domain == working_context["expected_domain"]
    assert github_owner_context_seed == github_owner_context["expected_seed"]
    assert read_only_task_for_wave_seed == read_only_task_for_wave["expected_seed"]
    fallback_quality = module.adjust_quality_for_candidate_basis(
        module.session_name_candidate_quality("agents-of-abyss-repo-ordering-session", evidence=["raw:line:2"]),
        "domain_and_event_signals",
    )
    assert fallback_quality["level"] == fallback_quality_case["level"]
    assert fallback_quality_case["flag"] in fallback_quality["flags"]
    assert path_attachment_domain == path_attachment["expected_domain"]
    assert quoted_path_seed == quoted_path_attachment["expected_seed"]
    assert repo_topology_refactor_seed == repo_topology_refactor["expected_seed"]
    for case_id in systemic_seed_case_ids:
        case = cases[case_id]
        assert module.useful_name_seed(case["title"]) == case["expected_seed"]
    assert cases["semantic_only_no_physical_relabel"]["expected_policy"]["physical_relabel_allowed"] is False


def test_naming_evidence_quality_warns_on_command_output_only_refs(tmp_path: Path) -> None:
    session_dir = tmp_path / "session"
    raw_path = session_dir / "raw" / "session.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {"timestamp": "2026-05-20T00:00:00Z", "type": "session_meta", "payload": {"id": "evidence-quality"}},
            {
                "timestamp": "2026-05-20T00:00:01Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Name the session from the operator request"}]},
            },
            {
                "timestamp": "2026-05-20T00:00:02Z",
                "type": "response_item",
                "payload": {"type": "function_call_output", "output": "sed: can't read /srv/AbyssOS/docs/START_HERE.md: No such file or directory"},
            },
        ],
    )

    assert module.naming_evidence_quality_flags(session_dir, ["raw:line:2"]) == []
    flags = module.naming_evidence_quality_flags(session_dir, ["raw:line:3"])
    ordered = module.prioritized_naming_evidence_refs(session_dir, ["raw:line:3", "raw:line:2"])

    assert "weak_raw_evidence_refs" in flags
    assert "command_output_evidence_only" in flags
    assert ordered[:2] == ["raw:line:2", "raw:line:3"]


def test_deferred_mirror_preserves_semantic_name_verified_anchor(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-18T00-00-00-anchor-preserve.jsonl"
    rows = [
        {"timestamp": "2026-05-18T00:00:00Z", "type": "session_meta", "payload": {"id": "anchor-preserve", "cwd": str(workspace)}},
        {"timestamp": "2026-05-18T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Preserve the semantic naming bridge"}]}},
        {"timestamp": "2026-05-18T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Use verified raw anchors."}]}},
    ]
    write_jsonl(transcript, rows)
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "anchor-preserve",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    session_dir = aoa_root / "sessions" / "2026-05-18__001__preserve-the-semantic-naming-bridge"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    raw_sha = manifest["raw"]["sha256"]
    raw_line_count = manifest["raw"]["line_count"]
    module.set_session_semantic_name(
        aoa_root=aoa_root,
        target="anchor-preserve",
        name="semantic naming bridge preservation",
        scope="session",
        evidence_refs=["raw:line:2"],
        from_line=1,
        to_line=raw_line_count,
        coverage_note="Initial named raw snapshot.",
        apply=True,
        verify_raw_hash=True,
    )

    write_jsonl(
        transcript,
        rows
        + [
            {
                "timestamp": "2026-05-18T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "The session continued after naming."}]},
            }
        ],
    )
    module.mirror_transcript_without_indexing(
        aoa_root=aoa_root,
        event={"session_id": "anchor-preserve", "transcript_path": str(transcript), "cwd": str(workspace)},
        transcript_path=transcript,
        hook_event_name="PreCompact",
        now="2026-05-18T00:01:00Z",
    )

    deferred_manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    semantic = deferred_manifest["semantic_names"]["names"][0]
    anchor = semantic["anchor"]
    readiness = module.session_naming_readiness(aoa_root, session_dir, deferred_manifest)

    assert deferred_manifest["archive_status"] == "raw_mirrored_index_deferred"
    assert deferred_manifest["raw"]["sha256"] is None
    assert deferred_manifest["raw"]["line_count"] is None
    assert anchor["raw_sha256"] == raw_sha
    assert anchor["raw_line_count"] == raw_line_count
    assert anchor["raw_anchor_status"] == "deferred_refresh_preserved_verified_anchor"
    assert readiness["status"] == "needs_reindex"
    assert readiness["evidence"]["observed_raw_line_count"] == raw_line_count + 1
    assert readiness["evidence"]["raw_line_count_source"] == "raw_probe_deferred"
    assert f"active_session_name_coverage_stale:{raw_line_count}<{raw_line_count + 1}" in readiness["warnings"]

    write_jsonl(
        transcript,
        rows
        + [
            {
                "timestamp": "2026-05-18T00:00:03Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "The session continued after naming."}]},
            },
            {
                "timestamp": "2026-05-18T00:00:04Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Source is now ahead of the archive."}]},
            },
        ],
    )
    source_ahead_readiness = module.session_naming_readiness(aoa_root, session_dir, deferred_manifest)

    assert source_ahead_readiness["status"] == "needs_sync"
    assert source_ahead_readiness["route"] == "sync_source_transcript_before_naming"
    assert "source_transcript_newer_than_raw_archive" in source_ahead_readiness["reasons"]
    assert source_ahead_readiness["evidence"]["source_transcript_newer_than_raw_archive"] is True


def test_replacing_active_session_name_does_not_create_implicit_alias(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-18T00-00-00-no-alias.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-18T00:00:00Z", "type": "session_meta", "payload": {"id": "no-implicit-alias", "cwd": str(workspace)}},
            {"timestamp": "2026-05-18T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Name the whole session correctly"}]}},
            {"timestamp": "2026-05-18T00:00:02Z", "type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "First name is too narrow."}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "no-implicit-alias",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    first = module.set_session_semantic_name(
        aoa_root=aoa_root,
        target="no-implicit-alias",
        name="narrow session name",
        scope="session",
        evidence_refs=["raw:line:2"],
        from_line=1,
        to_line=2,
        apply=True,
        verify_raw_hash=True,
    )
    second = module.set_session_semantic_name(
        aoa_root=aoa_root,
        target="no-implicit-alias",
        name="correct session name",
        scope="session",
        evidence_refs=["raw:line:2", "raw:line:3"],
        from_line=1,
        to_line=3,
        apply=True,
        verify_raw_hash=True,
    )

    session_dir = aoa_root / "sessions" / "2026-05-18__001__name-the-whole-session-correctly"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    names = manifest["semantic_names"]["names"]
    name_index = json.loads((aoa_root / module.SESSION_NAME_INDEX_JSON).read_text(encoding="utf-8"))

    assert first["status"] == "applied"
    assert second["status"] == "applied"
    assert manifest["semantic_names"]["active_session"] == "correct-session-name"
    assert [item["slug"] for item in names if item["scope"] == "session"] == ["correct-session-name"]
    assert not any(item.get("status") == "alias" for item in names)
    assert "narrow-session-name" not in name_index["slug_index"]


def test_naming_readiness_routes_before_bulk_renaming(tmp_path: Path) -> None:
    aoa_root = tmp_path / ".aoa"

    def add_manifest(
        label: str,
        title: str,
        *,
        session_id: str,
        status: str,
        segment_count: int,
        event_count: int,
        title_source: str = "first_user_message",
        with_transcript_hint: bool | None = None,
    ) -> None:
        session_dir = aoa_root / "sessions" / label
        raw_path = session_dir / "raw" / "session.raw.jsonl"
        segment_dir = session_dir / "segments"
        if with_transcript_hint is None:
            with_transcript_hint = status != "raw_unavailable"
        source_transcript_path = str(tmp_path / f"{session_id}.jsonl") if with_transcript_hint else None
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        segment_dir.mkdir(parents=True, exist_ok=True)
        if status != "raw_unavailable":
            raw_path.write_text("\n".join("{}" for _ in range(max(event_count, 1))) + "\n", encoding="utf-8")
        segments = []
        for index in range(segment_count):
            stem = f"{index:03}__initial-to-latest"
            md_path = segment_dir / f"{stem}.md"
            index_path = segment_dir / f"{stem}.index.json"
            md_path.write_text("# segment\n", encoding="utf-8")
            index_path.write_text('{"events":[]}\n', encoding="utf-8")
            segments.append(
                {
                    "segment_id": f"{index:03}",
                    "role": "initial-to-latest",
                    "markdown": str(md_path),
                    "index": str(index_path),
                    "event_count": 1,
                    "source_range": {"from_line": index + 1, "to_line": index + 1},
                }
            )
        manifest = {
            "schema_version": 1,
            "session_id": session_id,
            "display": {
                "date": label[:10],
                "sequence": 1,
                "title": title,
                "title_source": title_source,
                "label": label,
                "path": str(session_dir),
                "archive_path": str(session_dir),
                "navigation_path": str(session_dir),
            },
            "session_label": label,
            "session_title": title,
            "created_at": "2026-05-20T00:00:00Z",
            "updated_at": "2026-05-20T00:00:00Z",
            "source": {"cwd": str(tmp_path), "transcript_path": source_transcript_path},
            "archive_status": status,
            "distillation_status": "first_pass_distilled",
            "raw": {
                "path": str(raw_path),
                "bytes": raw_path.stat().st_size if raw_path.exists() else 0,
                "sha256": "sha256-fixture" if raw_path.exists() else None,
                "line_count": event_count if raw_path.exists() else None,
            },
            "segments": segments,
            "latest_event_count": event_count,
        }
        (session_dir / "session.manifest.json").write_text(json.dumps(manifest, ensure_ascii=False) + "\n", encoding="utf-8")
        module.update_registry(aoa_root, manifest, session_dir)

    add_manifest(
        "2026-05-20__001__large-real-work",
        "Large real work",
        session_id="large-real-work",
        status="indexed",
        segment_count=25,
        event_count=2500,
    )
    add_manifest(
        "2026-05-20__002__codex-in-abyssos",
        "Codex in AbyssOS",
        session_id="weak-cwd-title",
        status="indexed",
        segment_count=3,
        event_count=300,
        title_source="cwd",
    )
    add_manifest(
        "2026-05-20__003__missing-raw",
        "Codex in memories",
        session_id="missing-raw",
        status="raw_unavailable",
        segment_count=0,
        event_count=0,
        title_source="cwd",
    )
    add_manifest(
        "2026-05-20__004__missing-raw-with-path",
        "Codex in memories",
        session_id="missing-raw-with-path",
        status="raw_unavailable",
        segment_count=0,
        event_count=0,
        title_source="cwd",
        with_transcript_hint=True,
    )
    add_manifest(
        "2026-05-20__005__deferred-index",
        "Deferred index",
        session_id="deferred-index",
        status="raw_mirrored_index_deferred",
        segment_count=2,
        event_count=200,
    )
    add_manifest(
        "2026-05-20__006__named-with-open-phase-queue",
        "Named with open phase queue",
        session_id="named-open-phase-queue",
        status="indexed",
        segment_count=25,
        event_count=2500,
    )
    named_session_dir = aoa_root / "sessions" / "2026-05-20__006__named-with-open-phase-queue"
    named_manifest_path = named_session_dir / "session.manifest.json"
    named_manifest = json.loads(named_manifest_path.read_text(encoding="utf-8"))
    named_manifest["semantic_names"] = {
        "schema_version": 1,
        "active": "named-open-phase-queue",
        "active_session": "named-open-phase-queue",
        "names": [
            {
                "schema_version": 1,
                "name": "Named open phase queue",
                "slug": "named-open-phase-queue",
                "scope": "session",
                "kind": "session_essence",
                "status": "active",
                "coverage": {"raw_ranges": [{"from_line": 1, "to_line": 2500}]},
            }
        ],
    }
    named_manifest_path.write_text(json.dumps(named_manifest, ensure_ascii=False) + "\n", encoding="utf-8")
    module.update_registry(aoa_root, named_manifest, named_session_dir)
    named_phase_dir = named_session_dir / "naming"
    named_phase_dir.mkdir(parents=True, exist_ok=True)
    (named_phase_dir / "phase-discovery.json").write_text(
        json.dumps(
            {
                "artifact_type": "session_phase_discovery",
                "session_dir": str(named_session_dir),
                "raw_path": str(named_session_dir / "raw" / "session.raw.jsonl"),
                "candidate_count": 3,
                "review_queue_count": 2,
                "candidates": [
                    {
                        "segment_id": "000",
                        "name": "raw validation",
                        "slug": "raw-validation",
                        "confidence": "low",
                        "name_basis": "linked_path_event_signals",
                        "quality_flags": ["no_specific_user_intent"],
                        "coverage": {"raw_ranges": [{"from_line": 1, "to_line": 10}]},
                        "evidence": ["raw:line:1"],
                        "review": {"status": "needs_semantic_synthesis"},
                    },
                    {
                        "segment_id": "001",
                        "name": "docs implementation",
                        "slug": "docs-implementation",
                        "confidence": "low",
                        "name_basis": "linked_path_event_signals",
                        "quality_flags": ["no_specific_user_intent"],
                        "coverage": {"raw_ranges": [{"from_line": 11, "to_line": 20}]},
                        "evidence": ["raw:line:11"],
                        "review": {"status": "needs_semantic_synthesis"},
                    },
                    {
                        "segment_id": "002",
                        "name": "ready phase",
                        "slug": "ready-phase",
                        "confidence": "high",
                        "name_basis": "specific_user_intent",
                        "quality_flags": [],
                        "coverage": {"raw_ranges": [{"from_line": 21, "to_line": 30}]},
                        "evidence": ["raw:line:21"],
                        "review": {"status": "ready_for_raw_check"},
                    },
                ],
                "review_queue": [
                    {"segment_id": "000", "name": "raw validation", "review": {"status": "needs_semantic_synthesis"}},
                    {"segment_id": "001", "name": "docs implementation", "review": {"status": "needs_semantic_synthesis"}},
                ],
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = module.build_naming_readiness_report(aoa_root, refresh_indexes=True)
    by_label = {item["session_label"]: item["naming_readiness"] for item in payload["results"]}
    name_index = json.loads((aoa_root / module.SESSION_NAME_INDEX_JSON).read_text(encoding="utf-8"))
    sessions_index_md = (aoa_root / "sessions" / module.SESSIONS_INDEX_MARKDOWN).read_text(encoding="utf-8")

    assert by_label["2026-05-20__001__large-real-work"]["status"] == "needs_phase_discovery"
    assert by_label["2026-05-20__001__large-real-work"]["route"] == "phase_topic_discovery_before_session_name"
    assert by_label["2026-05-20__002__codex-in-abyssos"]["status"] == "ready_for_semantic_name"
    assert by_label["2026-05-20__002__codex-in-abyssos"]["route"] == "direct_semantic_name_from_index_and_raw_refs"
    assert by_label["2026-05-20__003__missing-raw"]["status"] == "diagnostic_only"
    assert by_label["2026-05-20__003__missing-raw"]["route"] == "leave_raw_unavailable_diagnostic"
    assert by_label["2026-05-20__004__missing-raw-with-path"]["status"] == "blocked"
    assert by_label["2026-05-20__004__missing-raw-with-path"]["route"] == "recover_raw_before_naming"
    assert by_label["2026-05-20__005__deferred-index"]["status"] == "needs_reindex"
    assert by_label["2026-05-20__005__deferred-index"]["route"] == "reindex_before_naming"
    assert by_label["2026-05-20__006__named-with-open-phase-queue"]["status"] == "named"
    assert by_label["2026-05-20__006__named-with-open-phase-queue"]["route"] == "review_open_phase_discovery_for_named_session"
    assert by_label["2026-05-20__006__named-with-open-phase-queue"]["priority"] > 0
    assert "phase_discovery_review_queue_open" in by_label["2026-05-20__006__named-with-open-phase-queue"]["reasons"]
    assert "phase_discovery_review_queue_open:2" in by_label["2026-05-20__006__named-with-open-phase-queue"]["warnings"]
    assert by_label["2026-05-20__006__named-with-open-phase-queue"]["evidence"]["phase_discovery_review_queue_count"] == 2
    assert by_label["2026-05-20__006__named-with-open-phase-queue"]["evidence"]["phase_discovery_review_queue_sample"][0]["name"] == "raw validation"
    assert name_index["naming_readiness_counts"]["by_status"]["needs_phase_discovery"] == 1
    assert name_index["naming_readiness_counts"]["by_status"]["ready_for_semantic_name"] == 1
    assert name_index["naming_readiness_counts"]["by_status"]["diagnostic_only"] == 1
    assert name_index["naming_readiness_counts"]["by_status"]["blocked"] == 1
    assert name_index["naming_readiness_counts"]["by_status"]["needs_reindex"] == 1
    assert name_index["naming_readiness_counts"]["by_status"]["named"] == 1
    assert "Naming Work Queue" in sessions_index_md
    assert "phase_topic_discovery_before_session_name" in sessions_index_md
    assert "review_open_phase_discovery_for_named_session" in sessions_index_md

    applied = module.review_phase_name_candidate(
        aoa_root,
        "2026-05-20__006__named-with-open-phase-queue",
        "000",
        reviewed_name="Raw route review",
        apply=True,
    )
    assert applied["status"] == "applied"
    updated_phase_discovery = json.loads((named_phase_dir / "phase-discovery.json").read_text(encoding="utf-8"))
    assert updated_phase_discovery["candidates"][0]["review"]["status"] == "applied_reviewed_name"
    assert updated_phase_discovery["candidates"][0]["review"]["applied_name"] == "Raw route review"
    assert updated_phase_discovery["review_queue_count"] == 1
    assert updated_phase_discovery["review_queue"][0]["segment_id"] == "001"


def test_phase_discovery_writes_open_candidates_and_updates_readiness(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-21T00-00-00-phase-discovery.jsonl"
    rows: list[dict[str, object]] = [
        {"timestamp": "2026-05-21T00:00:00Z", "type": "session_meta", "payload": {"id": "phase-discovery", "cwd": str(workspace)}},
        {
            "timestamp": "2026-05-21T00:00:01Z",
            "type": "response_item",
            "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Repair session naming layers in .aoa"}]},
        },
        {
            "timestamp": "2026-05-21T00:00:02Z",
            "type": "response_item",
            "payload": {"type": "function_call", "name": "exec_command", "call_id": "call-rg", "arguments": json.dumps({"cmd": "rg -n naming .aoa/NAMING.md"})},
        },
        {
            "timestamp": "2026-05-21T00:00:03Z",
            "type": "response_item",
            "payload": {"type": "function_call_output", "call_id": "call-rg", "output": "NAMING.md:1:naming\nProcess exited with code 0"},
        },
    ]
    for index in range(4, 23):
        rows.append(
            {
                "timestamp": f"2026-05-21T00:00:{index:02d}Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": f"Checkpoint {index}"}]},
            }
        )
    rows.extend(
        [
            {"timestamp": "2026-05-21T00:00:23Z", "type": "turn_context", "payload": {"summary": "context compacted after naming layer work"}},
            {
                "timestamp": "2026-05-21T00:00:24Z",
                "type": "response_item",
                "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Continue phase naming from raw anchors"}]},
            },
            {
                "timestamp": "2026-05-21T00:00:25Z",
                "type": "response_item",
                "payload": {"type": "function_call", "name": "apply_patch", "call_id": "call-patch"},
            },
            {
                "timestamp": "2026-05-21T00:00:26Z",
                "type": "response_item",
                "payload": {"type": "function_call_output", "call_id": "call-patch", "output": "Success. Updated the following files:\nM .aoa/NAMING.md"},
            },
        ]
    )
    write_jsonl(transcript, rows)

    module.handle_hook_event(
        "Stop",
        {
            "session_id": "phase-discovery",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    payload = module.discover_session_phases(aoa_root, "phase-discovery", write=True)
    assert payload["candidate_count"] == 2
    assert payload["candidates"][0]["status"] == "candidate_unreviewed"
    assert payload["candidates"][0]["evidence"][0].startswith("raw:line:")
    assert payload["candidates"][0]["name_basis"] == "specific_user_intent"
    assert payload["candidates"][0]["linked_signals"]["support_event_types"]["USER_INTENT"] == 1
    assert payload["candidates"][0]["review"]["status"] == "ready_for_raw_check"
    assert payload["review_queue_count"] == 0
    assert payload["candidate_quality_counts"]["by_review_status"]["ready_for_raw_check"] == 2
    assert (Path(payload["artifact_json"])).exists()
    assert (Path(payload["artifact_markdown"])).exists()

    readiness = module.build_naming_readiness_report(aoa_root, target="phase-discovery")
    item = readiness["results"][0]["naming_readiness"]
    assert item["status"] == "phase_discovery_ready"
    assert item["route"] == "review_phase_discovery_before_session_name"

    preview = module.review_phase_name_candidate(aoa_root, "phase-discovery", "000")
    assert preview["ok"]
    assert preview["status"] == "ready_for_raw_check"
    assert preview["raw_samples"]
    assert "--use-candidate --apply --write-report" in preview["next_command"]

    applied = module.review_phase_name_candidate(
        aoa_root,
        "phase-discovery",
        "000",
        reviewed_name="Naming layer repair",
        apply=True,
        write_report=True,
    )
    manifest = json.loads(next((aoa_root / "sessions").glob("*/session.manifest.json")).read_text(encoding="utf-8"))
    phase_names = [
        item
        for item in manifest["semantic_names"]["names"]
        if item["scope"] == "phase" and item["name"] == "Naming layer repair"
    ]
    assert applied["status"] == "applied"
    assert applied["semantic_name_result"]["status"] == "applied"
    assert phase_names
    assert (aoa_root / module.SESSION_NAME_INDEX_JSON).exists()
    assert (aoa_root / "sessions" / module.SESSIONS_INDEX_JSON).exists()
    assert Path(applied["report_json"]).exists()
    assert Path(applied["report_markdown"]).exists()

    phase_artifact = Path(payload["artifact_json"])
    weak_payload = json.loads(phase_artifact.read_text(encoding="utf-8"))
    weak_payload["candidates"][0]["name"] = ".aoa validation"
    weak_payload["candidates"][0]["review"]["status"] = "needs_semantic_synthesis"
    phase_artifact.write_text(json.dumps(weak_payload, ensure_ascii=False) + "\n", encoding="utf-8")
    rejected = module.review_phase_name_candidate(aoa_root, "phase-discovery", "000", use_candidate=True, apply=True)
    assert not rejected["ok"]
    assert "weak_candidate_requires_reviewed_name" in rejected["diagnostics"]

    assist = module.build_phase_review_assist(
        aoa_root,
        "phase-discovery",
        limit=2,
        from_segment="000",
        write=True,
        write_report=True,
    )
    assert assist["ok"]
    assert assist["selected_count"] == 2
    assert assist["packets"][0]["segment_id"] == "000"
    assert assist["packets"][0]["existing_phase_name"] == "Naming layer repair"
    assert assist["packets"][0]["read_first"]
    assert (
        assist["packets"][0]["synthesis_inputs"]["progress_markers"]
        or assist["packets"][0]["synthesis_inputs"]["decisions_and_closeout"]
        or assist["packets"][0]["synthesis_inputs"]["commands"]
    )
    assert assist["plan_template"]["items"][0]["segment_id"] == "000"
    assert Path(assist["artifact_json"]).exists()
    assert Path(assist["artifact_markdown"]).exists()
    assert Path(assist["plan_template_path"]).exists()
    assist_markdown = Path(assist["artifact_markdown"]).read_text(encoding="utf-8")
    assert "## Fast Queue" in assist_markdown
    assert "#### Commands" in assist_markdown or "#### Decisions And Closeout" in assist_markdown

    plan = assist["plan_template"]
    plan["items"][0]["reviewed_name"] = ""
    plan["items"][1]["reviewed_name"] = "Plan applied phase name"
    plan_path = Path(assist["plan_template_path"]).with_name("phase-review-plan.json")
    plan_path.write_text(json.dumps(plan, ensure_ascii=False) + "\n", encoding="utf-8")

    preview_plan = module.apply_phase_review_plan(aoa_root, "phase-discovery", plan_path=plan_path)
    assert preview_plan["ok"]
    assert preview_plan["status"] == "preview_ready"
    assert preview_plan["preview_count"] == 1
    assert preview_plan["skipped_count"] == 1

    applied_plan = module.apply_phase_review_plan(
        aoa_root,
        "phase-discovery",
        plan_path=plan_path,
        apply=True,
        write_report=True,
    )
    assert applied_plan["ok"]
    assert applied_plan["status"] == "applied"
    assert applied_plan["applied_count"] == 1
    assert applied_plan["skipped_count"] == 1
    assert Path(applied_plan["report_json"]).exists()
    assert Path(applied_plan["report_markdown"]).exists()
    manifest = json.loads(next((aoa_root / "sessions").glob("*/session.manifest.json")).read_text(encoding="utf-8"))
    assert any(
        item["scope"] == "phase" and item["name"] == "Plan applied phase name"
        for item in manifest["semantic_names"]["names"]
    )


def test_semantic_session_name_rejects_unanchored_out_of_range_evidence(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    transcript = tmp_path / "rollout-2026-05-18T00-00-00-bad-semantic-name.jsonl"
    write_jsonl(
        transcript,
        [
            {"timestamp": "2026-05-18T00:00:00Z", "type": "session_meta", "payload": {"id": "bad-semantic-name", "cwd": str(workspace)}},
            {"timestamp": "2026-05-18T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Short session"}]}},
        ],
    )
    module.handle_hook_event(
        "Stop",
        {
            "session_id": "bad-semantic-name",
            "transcript_path": str(transcript),
            "cwd": str(workspace),
            "hook_event_name": "Stop",
        },
        workspace_root=workspace,
        aoa_root=aoa_root,
    )

    payload = module.set_session_semantic_name(
        aoa_root=aoa_root,
        target="short-session",
        name="aoa-techniques final residual promotion pass",
        evidence_refs=["raw:line:99"],
        apply=True,
    )
    session_dir = aoa_root / "sessions" / "2026-05-18__001__short-session"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))

    assert payload["ok"] is False
    assert payload["status"] == "diagnostic"
    assert any("semantic_name_evidence_out_of_range" in item for item in payload["diagnostics"])
    assert "semantic_names" not in manifest


def test_registry_update_recovers_from_invalid_registry_when_manifests_exist(tmp_path: Path) -> None:
    workspace = tmp_path / "AbyssOS"
    aoa_root = workspace / ".aoa"
    for session_id, title in [("registry-a", "First recovery session"), ("registry-b", "Second recovery session")]:
        transcript = tmp_path / f"{session_id}.jsonl"
        write_jsonl(
            transcript,
            [
                {"timestamp": "2026-05-19T00:00:00Z", "type": "session_meta", "payload": {"id": session_id, "cwd": str(workspace)}},
                {"timestamp": "2026-05-19T00:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": title}]}},
            ],
        )
        module.handle_hook_event(
            "Stop",
            {
                "session_id": session_id,
                "transcript_path": str(transcript),
                "cwd": str(workspace),
                "hook_event_name": "Stop",
            },
            workspace_root=workspace,
            aoa_root=aoa_root,
        )

    registry_path = aoa_root / module.REGISTRY_NAME
    registry_path.write_text('{"sessions":[]}\n{"broken":true}\n', encoding="utf-8")
    session_dir = aoa_root / "sessions" / "2026-05-19__001__first-recovery-session"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    module.update_registry(aoa_root, manifest, session_dir)

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    name_index = json.loads((aoa_root / module.SESSION_NAME_INDEX_JSON).read_text(encoding="utf-8"))
    sessions_index = json.loads((aoa_root / "sessions" / module.SESSIONS_INDEX_JSON).read_text(encoding="utf-8"))
    assert len(registry["sessions"]) == 2
    assert name_index["session_count"] == 2
    assert sessions_index["session_count"] == 2


def test_rebuild_session_labels_backfills_existing_archive(tmp_path: Path) -> None:
    aoa_root = tmp_path / ".aoa"
    legacy_dir = aoa_root / "codex-sessions" / "legacy-session"
    raw_path = legacy_dir / "raw" / "session.raw.jsonl"
    write_jsonl(
        raw_path,
        [
            {"timestamp": "2026-05-13T10:00:00Z", "type": "session_meta", "payload": {"id": "legacy-session"}},
            {"timestamp": "2026-05-13T10:00:00Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "# AGENTS.md instructions for /tmp\n\n<INSTRUCTIONS>skip me</INSTRUCTIONS>"}]}},
            {"timestamp": "2026-05-13T10:00:01Z", "type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Backfill readable names"}]}},
        ],
    )
    (legacy_dir / "session.manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "session_id": "legacy-session",
                "created_at": "2026-05-13T10:00:00Z",
                "updated_at": "2026-05-13T10:00:02Z",
                "source": {"transcript_path": "/tmp/rollout-2026-05-13T10-00-00-legacy-session.jsonl"},
                "archive_status": "indexed",
                "distillation_status": "raw_archived",
                "raw": {"path": str(raw_path)},
                "segments": [],
                "latest_event_count": 3,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    payload = module.rebuild_session_labels(aoa_root)

    session_dir = aoa_root / "sessions" / "2026-05-13__001__backfill-readable-names"
    manifest = json.loads((session_dir / "session.manifest.json").read_text(encoding="utf-8"))
    assert payload["sessions"][0]["label"] == "2026-05-13__001__backfill-readable-names"
    assert manifest["display"]["label"] == "2026-05-13__001__backfill-readable-names"
    assert manifest["display"]["path"] == str(session_dir)
    assert manifest["raw"]["path"] == str(session_dir / "raw" / "session.raw.jsonl")
    assert not legacy_dir.exists()
    registry = json.loads((aoa_root / "session-registry.json").read_text(encoding="utf-8"))
    assert registry["sessions"][0]["session_label"] == "2026-05-13__001__backfill-readable-names"
